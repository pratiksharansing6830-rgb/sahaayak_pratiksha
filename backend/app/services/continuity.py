from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Child,
    EducationStatus,
    FollowUp,
    FollowUpAction,
    FollowUpStatus,
    Migration,
    MigrationStatus,
    NeedStatus,
    NeedStatusEvent,
    Priority,
    Referral,
    ReferralStatus,
    Role,
    ServiceCategory,
    ServiceNeed,
    User,
)
from app.services.audit import log_event

S = NeedStatus
C = ServiceCategory

OPEN_STATUSES = frozenset({
    S.NEEDS_ASSESSMENT,
    S.PENDING,
    S.REFERRED,
    S.AWAITING_PROVIDER_RESPONSE,
    S.FOLLOW_UP_REQUIRED,
    S.BARRIER_IDENTIFIED,
    S.REVIEW_REQUIRED,
})
RESOLVED_STATUSES = frozenset({
    S.SUPPORT_CONFIRMED,
    S.NOT_REQUIRED,
    S.CLOSED,
})
ACTIVE_FOLLOWUP = (FollowUpStatus.OPEN, FollowUpStatus.IN_PROGRESS)

ACTIVE_REFERRALS = (
    ReferralStatus.RECORDED,
    ReferralStatus.ACCEPTED,
    ReferralStatus.INFO_REQUESTED,
)

# Every legal move. Some targets can only be reached by the system or a specific workflow;
# the API layer decides who may request which (see needs.py).
ALLOWED_TRANSITIONS: dict[NeedStatus, set[NeedStatus]] = {
    S.NEEDS_ASSESSMENT: {S.PENDING, S.NOT_REQUIRED},
    S.PENDING: {
        S.REFERRED, S.FOLLOW_UP_REQUIRED, S.BARRIER_IDENTIFIED,
        S.SUPPORT_CONFIRMED, S.NOT_REQUIRED, S.CLOSED,
    },
    S.REFERRED: {
        S.AWAITING_PROVIDER_RESPONSE, S.FOLLOW_UP_REQUIRED, S.BARRIER_IDENTIFIED,
        S.SUPPORT_CONFIRMED, S.PENDING, S.CLOSED,
    },
    S.AWAITING_PROVIDER_RESPONSE: {
        S.FOLLOW_UP_REQUIRED, S.BARRIER_IDENTIFIED,
        S.SUPPORT_CONFIRMED, S.PENDING, S.CLOSED,
    },
    S.FOLLOW_UP_REQUIRED: {
        S.PENDING, S.REFERRED, S.BARRIER_IDENTIFIED,
        S.SUPPORT_CONFIRMED, S.NOT_REQUIRED, S.CLOSED,
    },
    S.BARRIER_IDENTIFIED: {
        S.PENDING, S.FOLLOW_UP_REQUIRED, S.REFERRED,
        S.SUPPORT_CONFIRMED, S.NOT_REQUIRED, S.CLOSED,
    },
    S.REVIEW_REQUIRED: {
        S.PENDING, S.FOLLOW_UP_REQUIRED, S.SUPPORT_CONFIRMED,
        S.NOT_REQUIRED, S.CLOSED,
    },
    S.SUPPORT_CONFIRMED: {S.REVIEW_REQUIRED},
    S.NOT_REQUIRED: {S.NEEDS_ASSESSMENT},
    S.CLOSED: {S.NEEDS_ASSESSMENT},
}

# A new follow-up is created when a need enters one of these
# (REFERRED/AWAITING are handled by the referral workflow).
FOLLOWUP_ON_ENTRY = OPEN_STATUSES - {
    S.REFERRED,
    S.AWAITING_PROVIDER_RESPONSE,
}

# (why it is in this status, what to do next)
STATUS_TEXT: dict[NeedStatus, tuple[str, str | None]] = {
    S.NEEDS_ASSESSMENT: (
        "We do not know yet whether this child needs support in this area. "
        "No record does not mean no need.",
        "Answer a few questions so this need can be assessed.",
    ),
    S.PENDING: (
        "A need has been identified but no support has been arranged yet.",
        "Find a suitable service and record a contact attempt.",
    ),
    S.REFERRED: (
        "A referral has been recorded. The provider has not confirmed anything yet.",
        "Wait for the provider's response, or follow up.",
    ),
    S.AWAITING_PROVIDER_RESPONSE: (
        "We are waiting for the provider to respond.",
        "Follow up if there is no response by the due date.",
    ),
    S.FOLLOW_UP_REQUIRED: (
        "A follow-up action is needed before this can move forward.",
        "Complete the open follow-up task.",
    ),
    S.BARRIER_IDENTIFIED: (
        "Something is blocking support, for example missing documents or no places available.",
        "Review the barrier, then try another service or provide the missing information.",
    ),
    S.REVIEW_REQUIRED: (
        "Something changed, such as the destination, so earlier information may no longer apply.",
        "Review this need again for the new situation.",
    ),
    S.SUPPORT_CONFIRMED: (
        "Support has been confirmed. The evidence shows who confirmed it.",
        None,
    ),
    S.NOT_REQUIRED: (
        "Marked as not needed. This is not the same as support received.",
        "Reopen this if the situation changes.",
    ),
    S.CLOSED: (
        "Closed without confirming that support was received. See the closure reason.",
        "Reopen this if the child still needs support.",
    ),
}

ACTION_FOR: dict[ServiceCategory, FollowUpAction] = {
    C.EDUCATION: FollowUpAction.CONTACT_SCHOOL,
    C.HEALTHCARE: FollowUpAction.CONTACT_HEALTHCARE,
    C.NUTRITION: FollowUpAction.EXPLORE_ALTERNATIVE,
    C.WELLBEING: FollowUpAction.EXPLORE_ALTERNATIVE,
    C.PROTECTION: FollowUpAction.SCHEDULE_FOLLOW_UP,
    C.INCLUSION: FollowUpAction.EXPLORE_ALTERNATIVE,
}

ACTION_TEXT: dict[FollowUpAction, str] = {
    FollowUpAction.CONTACT_SCHOOL: (
        "Contact a school at the destination about enrolment or transfer."
    ),
    FollowUpAction.CONTACT_HEALTHCARE: (
        "Contact a health facility at the destination about records and care."
    ),
    FollowUpAction.EXPLORE_ALTERNATIVE: (
        "Look for a suitable service at the destination and record a contact attempt."
    ),
    FollowUpAction.SCHEDULE_FOLLOW_UP: (
        "Schedule a check-in to review this child's situation."
    ),
    FollowUpAction.REQUEST_MISSING_INFO: (
        "Answer questions about this child's situation so the need can be assessed."
    ),
}


# ---------- Rules: what need does a child have in each category? ----------
def initial_need(
    child: Child,
    category: ServiceCategory,
) -> tuple[NeedStatus, str]:
    """Deterministic rules. Never copies free-text notes into the description."""
    if category == C.EDUCATION:
        if child.education_status == EducationStatus.UNKNOWN:
            return (
                S.NEEDS_ASSESSMENT,
                "Education status is not known. Check whether this child is attending school.",
            )
        if child.education_status == EducationStatus.ENROLLED:
            return (
                S.PENDING,
                "The child is enrolled at the current location. Schooling at the destination "
                "still has to be arranged.",
            )
        return S.PENDING, "The child is not currently in school. Enrolment is needed."

    if category == C.HEALTHCARE:
        return (
            S.NEEDS_ASSESSMENT,
            "Check the child's health records, immunisation status and the nearest "
            "health facility at the destination.",
        )

    if category == C.NUTRITION:
        return (
            S.NEEDS_ASSESSMENT,
            "Check whether the child can keep getting school meals or community nutrition "
            "support at the destination.",
        )

    if category == C.WELLBEING:
        return (
            S.NEEDS_ASSESSMENT,
            "Check how the child is coping with the move and whether wellbeing support would help.",
        )

    if category == C.PROTECTION:
        return (
            S.NEEDS_ASSESSMENT,
            "Check that the child will be safe and supported during and after the move.",
        )

    # INCLUSION
    if child.accommodations_note:
        return (
            S.PENDING,
            "The child has recorded accommodation needs. Check that suitable support is "
            "available at the destination.",
        )

    return (
        S.NEEDS_ASSESSMENT,
        "Check whether the child needs disability-related support or accommodations.",
    )


def _due_and_priority(
    category: ServiceCategory,
    migration: Migration | None,
) -> tuple[date, Priority]:
    today = date.today()
    due = today + timedelta(days=7)

    if migration is not None:
        if migration.status == MigrationStatus.PLANNED and migration.planned_date:
            due = max(today, migration.planned_date - timedelta(days=7))
        elif migration.status in (
            MigrationStatus.ACTIVE,
            MigrationStatus.COMPLETED,
        ):
            due = today + timedelta(days=3)

    urgent = due <= today + timedelta(days=3) or category == C.PROTECTION
    return due, (Priority.HIGH if urgent else Priority.MEDIUM)


# ---------- Follow-ups ----------
def ensure_followup(
    db: Session,
    need: ServiceNeed,
    actor: User | None,
    *,
    audit: bool = True,
):
    """Create one active follow-up for an open need, unless it already has one."""
    if need.status in RESOLVED_STATUSES:
        return None

    already = db.scalar(
        select(FollowUp.id)
        .where(
            FollowUp.need_id == need.id,
            FollowUp.status.in_(ACTIVE_FOLLOWUP),
        )
        .limit(1)
    )
    if already:
        return None

    migration = db.get(Migration, need.migration_id) if need.migration_id else None
    action = (
        FollowUpAction.REQUEST_MISSING_INFO
        if need.status == S.NEEDS_ASSESSMENT
        else ACTION_FOR[need.category]
    )
    due, priority = _due_and_priority(need.category, migration)

    followup = FollowUp(
        need_id=need.id,
        action_type=action,
        description=ACTION_TEXT[action],
        assigned_role=Role.CITIZEN,
        priority=priority,
        due_date=due,
    )

    try:
        with db.begin_nested():
            db.add(followup)
            db.flush()
    except IntegrityError:
        # The database index caught a race: someone else just created it.
        return None

    need.due_date = due

    if audit:
        log_event(
            db,
            actor=actor,
            action="FOLLOWUP_CREATED",
            entity_type="follow_up",
            entity_id=followup.id,
            to_value=action.value,
        )

    db.flush()
    return followup


def close_active_followups(
    db: Session,
    need: ServiceNeed,
    note: str,
    only_action: FollowUpAction | None = None,
) -> None:
    statement = select(FollowUp).where(
        FollowUp.need_id == need.id,
        FollowUp.status.in_(ACTIVE_FOLLOWUP),
    )

    if only_action is not None:
        statement = statement.where(FollowUp.action_type == only_action)

    for followup in db.scalars(statement).all():
        followup.status = FollowUpStatus.CANCELLED
        followup.next_action = note

    db.flush()


# ---------- The one place a need's status changes ----------
def transition_need(
    db: Session,
    need: ServiceNeed,
    to_status: NeedStatus,
    actor: User | None,
    *,
    reason: str | None = None,
    explanation: str | None = None,
    next_action: str | None = None,
) -> ServiceNeed:
    from_status = need.status

    if to_status not in ALLOWED_TRANSITIONS[from_status]:
        raise HTTPException(
            409,
            f"A need that is {from_status.value} cannot be changed to {to_status.value}.",
        )

    default_why, default_next = STATUS_TEXT[to_status]
    need.status = to_status
    need.status_explanation = explanation or default_why
    need.next_action = next_action if next_action is not None else default_next

    if to_status in (S.NOT_REQUIRED, S.CLOSED):
        need.closure_reason = reason
    elif from_status in (S.NOT_REQUIRED, S.CLOSED):
        need.closure_reason = None

    db.add(
        NeedStatusEvent(
            need_id=need.id,
            from_status=from_status,
            to_status=to_status,
            changed_by_user_id=actor.id if actor else None,
            changed_by_role=actor.role if actor else None,
            reason=reason,
        )
    )

    # The audit log gets the change but NOT the free-text reason (it can contain private details).
    log_event(
        db,
        actor=actor,
        action="NEED_STATUS_CHANGED",
        entity_type="service_need",
        entity_id=need.id,
        from_value=from_status.value,
        to_value=to_status.value,
    )
    db.flush()

    if from_status == S.NEEDS_ASSESSMENT and to_status in OPEN_STATUSES:
        close_active_followups(
            db,
            need,
            "Replaced: this need has now been assessed.",
            only_action=FollowUpAction.REQUEST_MISSING_INFO,
        )

    if to_status in RESOLVED_STATUSES:
        close_active_followups(
            db,
            need,
            "Closed because this need was resolved.",
        )
    elif to_status in FOLLOWUP_ON_ENTRY:
        ensure_followup(db, need, actor)

    return need


# ---------- Assessment ----------
def assess_migration(
    db: Session,
    migration: Migration,
    family_id,
    actor: User,
):
    """Create any missing needs for this migration. Safe to run repeatedly."""
    children = db.scalars(
        select(Child)
        .where(
            Child.family_id == family_id,
            Child.deleted_at.is_(None),
        )
        .order_by(Child.created_at)
    ).all()

    created: list[ServiceNeed] = []
    existing = 0

    for child in children:
        for category in ServiceCategory:
            found = db.scalar(
                select(ServiceNeed.id).where(
                    ServiceNeed.child_id == child.id,
                    ServiceNeed.category == category,
                    ServiceNeed.migration_id == migration.id,
                )
            )

            if found:
                existing += 1
                continue

            status, description = initial_need(child, category)
            why, next_step = STATUS_TEXT[status]
            due, _ = _due_and_priority(category, migration)

            need = ServiceNeed(
                child_id=child.id,
                migration_id=migration.id,
                category=category,
                status=status,
                need_description=description,
                status_explanation=why,
                next_action=next_step,
                assigned_role=Role.CITIZEN,
                due_date=due,
            )

            try:
                with db.begin_nested():
                    db.add(need)
                    db.flush()
            except IntegrityError:
                existing += 1
                continue

            db.add(
                NeedStatusEvent(
                    need_id=need.id,
                    from_status=None,
                    to_status=status,
                    changed_by_user_id=actor.id,
                    changed_by_role=actor.role,
                    reason="Initial assessment",
                )
            )
            db.flush()
            ensure_followup(db, need, actor, audit=False)
            created.append(need)

    return created, existing


# ---------- Migration changes ----------
def review_needs_after_destination_change(
    db: Session,
    migration: Migration,
    actor: User,
) -> None:
    """Old confirmations and referrals must not silently stand for a new destination."""
    needs = db.scalars(
        select(ServiceNeed).where(ServiceNeed.migration_id == migration.id)
    ).all()

    for need in needs:
        if need.status == S.SUPPORT_CONFIRMED:
            transition_need(
                db,
                need,
                S.REVIEW_REQUIRED,
                actor,
                reason="Destination changed",
                explanation=(
                    "The destination changed, so the earlier confirmation may no longer apply."
                ),
            )
            continue

        active = db.scalars(
            select(Referral).where(
                Referral.need_id == need.id,
                Referral.status.in_(ACTIVE_REFERRALS),
            )
        ).all()

        if not active:
            continue

        for referral in active:
            old_status = referral.status
            referral.status = ReferralStatus.WITHDRAWN

            log_event(
                db,
                actor=actor,
                action="REFERRAL_WITHDRAWN",
                entity_type="referral",
                entity_id=referral.id,
                from_value=old_status.value,
                to_value="WITHDRAWN",
                reason="Destination changed",
            )

        db.flush()

        if need.status in (
            S.REFERRED,
            S.AWAITING_PROVIDER_RESPONSE,
            S.FOLLOW_UP_REQUIRED,
            S.BARRIER_IDENTIFIED,
        ):
            transition_need(
                db,
                need,
                S.PENDING,
                actor,
                reason="Destination changed",
                explanation=(
                    "The destination changed, so earlier referrals were withdrawn. "
                    "Find a service at the new destination."
                ),
            )