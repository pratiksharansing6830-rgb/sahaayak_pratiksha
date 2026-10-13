import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import (
    ConfirmationMethod, ContactAttempt, FollowUpAction, Migration, NeedStatus,
    OutcomeConfirmation, Priority, ProviderResponse, ProviderResponseType, Referral,
    ReferralStatus, Role, ServiceCategory, User,
)
from app.schemas.provider import (
    FamilyMessageOut, ProviderConfirm, ProviderDashboard, ProviderReferralOut, ProviderRespond,
)
from app.schemas.referral import REFERRAL_TEXT, ProviderResponseOut
from app.services.audit import log_event
from app.services.continuity import (
    OPEN_STATUSES, close_active_followups, transition_need,
)
from app.services.provider import add_followup, get_provider_referral, scoped

router = APIRouter(prefix="/provider", tags=["provider"])

S, RS, R = NeedStatus, ReferralStatus, ProviderResponseType
ACTIVE_REFERRAL = (RS.RECORDED, RS.ACCEPTED, RS.INFO_REQUESTED)
IN_FLIGHT = (S.REFERRED, S.AWAITING_PROVIDER_RESPONSE)

RESPONSE_FROM = {
    R.RECEIVED: {RS.RECORDED},
    R.ACCEPTED: {RS.RECORDED, RS.INFO_REQUESTED},
    R.INFO_REQUESTED: {RS.RECORDED, RS.INFO_REQUESTED, RS.ACCEPTED},
    R.DECLINED: {RS.RECORDED, RS.INFO_REQUESTED, RS.ACCEPTED},
}

STATUS_FOR = {
    R.ACCEPTED: RS.ACCEPTED,
    R.INFO_REQUESTED: RS.INFO_REQUESTED,
    R.DECLINED: RS.DECLINED,
}


def provider_user(
    user: User = Depends(require_roles(Role.SCHOOL, Role.HEALTHCARE, Role.NGO)),
) -> User:
    if user.organization_id is None:
        raise HTTPException(403, "Your account is not linked to an organisation.")
    return user


def _age(child) -> int | None:
    if child.date_of_birth:
        t, d = date.today(), child.date_of_birth
        return t.year - d.year - ((t.month, t.day) < (d.month, d.day))
    return child.approx_age_years


def _view(db: Session, ref, need, child, family, listing) -> ProviderReferralOut:
    mig = db.get(Migration, need.migration_id) if need.migration_id else None

    responses = db.scalars(
        select(ProviderResponse)
        .where(ProviderResponse.referral_id == ref.id)
        .order_by(ProviderResponse.responded_at)
    ).all()

    messages = db.scalars(
        select(ContactAttempt)
        .where(ContactAttempt.referral_id == ref.id)
        .order_by(ContactAttempt.attempted_at)
    ).all()

    cat = need.category

    return ProviderReferralOut(
        id=ref.id,
        status=ref.status,
        plain_status=REFERRAL_TEXT[ref.status],
        referred_at=ref.referred_at,
        service_name=listing.name,
        category=cat,
        need_description=need.need_description,
        need_is_open=need.status in OPEN_STATUSES,
        child_name=child.full_name,
        child_age_years=_age(child),
        education_status=child.education_status
        if cat == ServiceCategory.EDUCATION else None,
        current_school_name=child.current_school_name
        if cat == ServiceCategory.EDUCATION else None,
        accommodations_note=child.accommodations_note
        if cat == ServiceCategory.INCLUSION else None,
        destination_district=mig.destination_district if mig else None,
        planned_date=mig.planned_date if mig else None,
        preferred_language=family.preferred_language,
        family_contact_phone=family.contact_phone
        if ref.status == RS.ACCEPTED else None,
        referral_note=ref.note,
        responses=[ProviderResponseOut.model_validate(r) for r in responses],
        family_messages=[
            FamilyMessageOut(
                method=m.method,
                result=m.result,
                note=m.note,
                attempted_at=m.attempted_at,
            )
            for m in messages
        ],
    )


def _check_actionable(ref, need, *, allow_confirmed: bool = False) -> None:
    if ref.status not in ACTIVE_REFERRAL:
        raise HTTPException(
            409,
            f"This referral is {ref.status.value} and can no longer be answered.",
        )

    if need.status == S.REVIEW_REQUIRED:
        raise HTTPException(
            409,
            "The family is reviewing this need because their situation changed.",
        )

    if need.status not in OPEN_STATUSES and not (
        allow_confirmed and need.status == S.SUPPORT_CONFIRMED
    ):
        raise HTTPException(409, "This need has already been resolved.")


@router.get("/referrals", response_model=list[ProviderReferralOut])
def list_referrals(
    status: ReferralStatus | None = None,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(provider_user),
    db: Session = Depends(get_db),
):
    from app.models import Child, Family, ServiceListing, ServiceNeed

    stmt = scoped(
        user,
        Referral,
        ServiceNeed,
        Child,
        Family,
        ServiceListing,
    )

    if status:
        stmt = stmt.where(Referral.status == status)

    stmt = (
        stmt
        .order_by(Referral.referred_at.desc())
        .limit(limit)
        .offset(offset)
    )

    return [_view(db, *row) for row in db.execute(stmt).all()]


@router.get("/referrals/{referral_id}", response_model=ProviderReferralOut)
def get_referral(
    referral_id: uuid.UUID,
    user: User = Depends(provider_user),
    db: Session = Depends(get_db),
):
    return _view(db, *get_provider_referral(db, user, referral_id))


@router.post(
    "/referrals/{referral_id}/respond",
    response_model=ProviderReferralOut,
)
def respond(
    referral_id: uuid.UUID,
    payload: ProviderRespond,
    user: User = Depends(provider_user),
    db: Session = Depends(get_db),
):
    ref, need, child, family, listing = get_provider_referral(
        db, user, referral_id
    )

    rtype = R(payload.response_type)

    _check_actionable(ref, need)

    if ref.status not in RESPONSE_FROM[rtype]:
        raise HTTPException(
            409,
            f"A referral that is {ref.status.value} cannot be answered "
            f"with {rtype.value}.",
        )

    if rtype == R.RECEIVED and db.scalar(
        select(ProviderResponse.id)
        .where(
            ProviderResponse.referral_id == ref.id,
            ProviderResponse.response_type == R.RECEIVED,
        )
        .limit(1)
    ):
        raise HTTPException(
            409,
            "Receipt of this referral was already recorded.",
        )

    old = ref.status

    db.add(
        ProviderResponse(
            referral_id=ref.id,
            responder_user_id=user.id,
            response_type=rtype,
            message=payload.message,
            barrier=payload.barrier,
        )
    )

    if rtype in STATUS_FOR:
        ref.status = STATUS_FOR[rtype]

    db.flush()

    log_event(
        db,
        actor=user,
        action="PROVIDER_RESPONDED",
        entity_type="referral",
        entity_id=ref.id,
        from_value=old.value,
        to_value=rtype.value,
    )

    if rtype == R.RECEIVED:
        if need.status == S.REFERRED:
            transition_need(
                db,
                need,
                S.AWAITING_PROVIDER_RESPONSE,
                user,
                reason="Provider received the referral",
            )

    elif rtype == R.INFO_REQUESTED:
        if need.status in IN_FLIGHT:
            transition_need(
                db,
                need,
                S.FOLLOW_UP_REQUIRED,
                user,
                reason="Provider asked for more information",
                explanation="The provider needs more information before they can help.",
                next_action="Send the information the provider asked for.",
            )

        add_followup(
            db,
            need,
            FollowUpAction.REQUEST_MISSING_INFO,
            f"{listing.name} needs more information: {payload.message}",
            user,
            priority=Priority.HIGH,
            referral_id=ref.id,
            days=3,
        )

    elif rtype == R.ACCEPTED:
        if need.status in (S.FOLLOW_UP_REQUIRED, S.BARRIER_IDENTIFIED):
            transition_need(
                db,
                need,
                S.REFERRED,
                user,
                reason="Provider accepted the referral",
            )

        close_active_followups(
            db,
            need,
            "Provider accepted the referral.",
            only_action=FollowUpAction.REQUEST_MISSING_INFO,
        )

        need.status_explanation = (
            "The provider accepted the referral. This is not confirmation "
            "that support was received."
        )

        need.next_action = (
            "Wait for the provider to arrange support. "
            "The outcome is confirmed separately."
        )

    elif rtype == R.DECLINED:
        others = db.scalar(
            select(Referral.id)
            .where(
                Referral.need_id == need.id,
                Referral.id != ref.id,
                Referral.status.in_(ACTIVE_REFERRAL),
            )
            .limit(1)
        )

        if others is None:
            close_active_followups(
                db,
                need,
                "Provider declined the referral.",
                only_action=FollowUpAction.REQUEST_MISSING_INFO,
            )

            if need.status in IN_FLIGHT + (S.FOLLOW_UP_REQUIRED,):
                transition_need(
                    db,
                    need,
                    S.BARRIER_IDENTIFIED,
                    user,
                    reason="Provider declined the referral",
                    explanation=(
                        "The provider could not help with this referral. "
                        f"Reason given: {payload.barrier}"
                    ),
                )

            add_followup(
                db,
                need,
                FollowUpAction.EXPLORE_ALTERNATIVE,
                "The provider declined. Look for another suitable service "
                "and record a contact attempt.",
                user,
                priority=Priority.HIGH,
                referral_id=ref.id,
            )

    db.commit()

    return _view(db, ref, need, child, family, listing)


@router.post(
    "/referrals/{referral_id}/confirm-outcome",
    response_model=ProviderReferralOut,
)
def confirm_outcome(
    referral_id: uuid.UUID,
    payload: ProviderConfirm,
    user: User = Depends(provider_user),
    db: Session = Depends(get_db),
):
    ref, need, child, family, listing = get_provider_referral(
        db, user, referral_id
    )

    _check_actionable(ref, need, allow_confirmed=True)

    if ref.status != RS.ACCEPTED:
        raise HTTPException(
            409,
            "Accept the referral first. Acceptance alone is not support received, "
            "and an outcome can only be confirmed for an accepted referral.",
        )

    if db.scalar(
        select(OutcomeConfirmation.id)
        .where(
            OutcomeConfirmation.referral_id == ref.id,
            OutcomeConfirmation.provider_verified.is_(True),
        )
        .limit(1)
    ):
        raise HTTPException(
            409,
            "An outcome was already confirmed for this referral.",
        )

    db.add(
        ProviderResponse(
            referral_id=ref.id,
            responder_user_id=user.id,
            response_type=R.SERVICE_PROVIDED,
            message=payload.outcome,
        )
    )

    db.add(
        OutcomeConfirmation(
            need_id=need.id,
            referral_id=ref.id,
            outcome=payload.outcome,
            method=ConfirmationMethod.PROVIDER_CONFIRMED,
            confirmed_by_user_id=user.id,
            confirmed_by_role=user.role,
            provider_verified=True,
            reference_note=payload.reference_note,
        )
    )

    db.flush()

    if need.status == S.SUPPORT_CONFIRMED:
        need.status_explanation = (
            f"Confirmed and verified by the provider ({listing.name})."
        )
    else:
        transition_need(
            db,
            need,
            S.SUPPORT_CONFIRMED,
            user,
            reason="Outcome confirmed by provider",
            explanation=f"Confirmed by the provider ({listing.name}).",
        )

    log_event(
        db,
        actor=user,
        action="OUTCOME_CONFIRMED",
        entity_type="service_need",
        entity_id=need.id,
        to_value="PROVIDER_CONFIRMED",
    )

    db.commit()

    return _view(db, ref, need, child, family, listing)


@router.get("/dashboard", response_model=ProviderDashboard)
def dashboard(
    user: User = Depends(provider_user),
    db: Session = Depends(get_db),
):
    counts = {s.value: 0 for s in RS}

    for st, n in db.execute(
        scoped(user, Referral.status, func.count()).group_by(Referral.status)
    ).all():
        counts[st.value] = n

    my_refs = scoped(user, Referral.id)

    confirmed_ids = set(
        db.scalars(
            select(OutcomeConfirmation.referral_id)
            .where(
                OutcomeConfirmation.provider_verified.is_(True),
                OutcomeConfirmation.referral_id.in_(my_refs),
            )
        ).all()
    )

    accepted_ids = set(
        db.scalars(
            my_refs.where(Referral.status == RS.ACCEPTED)
        ).all()
    )

    return ProviderDashboard(
        organization_id=user.organization_id,
        by_status=counts,
        awaiting_response=counts["RECORDED"],
        info_requested=counts["INFO_REQUESTED"],
        accepted_awaiting_outcome=len(accepted_ids - confirmed_ids),
        confirmed_outcomes=len(confirmed_ids),
    )