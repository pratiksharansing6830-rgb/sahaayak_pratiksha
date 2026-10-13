import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import (
    Child, ConfirmationMethod, FollowUp, MigrationStatus, NeedStatus, NeedStatusEvent,
    OutcomeConfirmation, Role, ServiceCategory, ServiceNeed, User,
)
from app.schemas.continuity import (
    AssessResult, ConfirmRequest, ContinuitySummary, NeedDetail, NeedOut, NeedStatusChange,
    OutcomeOut, StatusEventOut, to_followup_out, to_need_out,
)
from app.services.access import (
    get_child_for_user, get_family_access, get_migration_for_user, get_need_for_user,
)
from app.services.audit import log_event
from app.services.continuity import (
    ALLOWED_TRANSITIONS, OPEN_STATUSES, assess_migration, transition_need,
)
from app.services.summary import build_summary

router = APIRouter(tags=["continuity"])
citizen_only = require_roles(Role.CITIZEN)
family_user = require_roles(Role.CITIZEN, Role.NGO)

S = NeedStatus
SYSTEM_ONLY = {
    S.SUPPORT_CONFIRMED: "Support can only be marked as received through the confirm-outcome step, with evidence.",
    S.REFERRED: "A need becomes REFERRED when a referral is recorded.",
    S.AWAITING_PROVIDER_RESPONSE: "A need becomes AWAITING_PROVIDER_RESPONSE when a referral is recorded.",
    S.REVIEW_REQUIRED: "A need is sent for review automatically when circumstances change.",
}
CITIZEN_CONFIRM_METHODS = {ConfirmationMethod.FAMILY_REPORTED, ConfirmationMethod.DOCUMENT_SEEN}


def build_detail(db: Session, need: ServiceNeed) -> NeedDetail:
    history = db.scalars(
        select(NeedStatusEvent).where(NeedStatusEvent.need_id == need.id).order_by(NeedStatusEvent.created_at)
    ).all()
    follow_ups = db.scalars(
        select(FollowUp).where(FollowUp.need_id == need.id).order_by(FollowUp.created_at.desc())
    ).all()
    confirmations = db.scalars(
        select(OutcomeConfirmation).where(OutcomeConfirmation.need_id == need.id)
        .order_by(OutcomeConfirmation.confirmed_at.desc())
    ).all()
    base = to_need_out(need).model_dump()
    return NeedDetail(
        **base,
        history=[StatusEventOut.model_validate(e) for e in history],
        follow_ups=[to_followup_out(f) for f in follow_ups],
        confirmations=[OutcomeOut.model_validate(c) for c in confirmations],
    )


@router.post("/migrations/{migration_id}/assess", response_model=AssessResult)
def assess(migration_id: uuid.UUID, user: User = Depends(citizen_only), db: Session = Depends(get_db)):
    mig, family = get_migration_for_user(db, user, migration_id, write=True)
    if mig.status == MigrationStatus.CANCELLED:
        raise HTTPException(409, "A cancelled migration cannot be assessed.")
    created, existing = assess_migration(db, mig, family.id, user)
    log_event(db, actor=user, action="MIGRATION_ASSESSED", entity_type="migration",
              entity_id=mig.id, to_value=f"{len(created)} new")
    db.commit()
    needs = db.scalars(
        select(ServiceNeed).join(Child, Child.id == ServiceNeed.child_id)
        .where(ServiceNeed.migration_id == mig.id, Child.deleted_at.is_(None))
        .order_by(ServiceNeed.created_at)
    ).all()
    return AssessResult(
        created_needs=len(created), existing_needs=existing, needs=[to_need_out(n) for n in needs]
    )


@router.get("/families/{family_id}/needs", response_model=list[NeedOut])
def list_family_needs(
    family_id: uuid.UUID,
    status: NeedStatus | None = None,
    category: ServiceCategory | None = None,
    open_only: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id)
    stmt = (
        select(ServiceNeed).join(Child, Child.id == ServiceNeed.child_id)
        .where(Child.family_id == family.id, Child.deleted_at.is_(None))
    )
    if status:
        stmt = stmt.where(ServiceNeed.status == status)
    if category:
        stmt = stmt.where(ServiceNeed.category == category)
    if open_only:
        stmt = stmt.where(ServiceNeed.status.in_(list(OPEN_STATUSES)))
    stmt = stmt.order_by(ServiceNeed.due_date.asc().nulls_last(), ServiceNeed.created_at.desc())
    return [to_need_out(n) for n in db.scalars(stmt.limit(limit).offset(offset)).all()]


@router.get("/children/{child_id}/needs", response_model=list[NeedOut])
def list_child_needs(
    child_id: uuid.UUID, open_only: bool = False,
    user: User = Depends(family_user), db: Session = Depends(get_db),
):
    child, _ = get_child_for_user(db, user, child_id)
    stmt = select(ServiceNeed).where(ServiceNeed.child_id == child.id)
    if open_only:
        stmt = stmt.where(ServiceNeed.status.in_(list(OPEN_STATUSES)))
    return [to_need_out(n) for n in db.scalars(stmt.order_by(ServiceNeed.created_at)).all()]


@router.get("/families/{family_id}/continuity-summary", response_model=ContinuitySummary)
def continuity_summary(family_id: uuid.UUID, user: User = Depends(family_user), db: Session = Depends(get_db)):
    family, _ = get_family_access(db, user, family_id)
    return build_summary(db, family)


@router.get("/needs/{need_id}", response_model=NeedDetail)
def get_need(need_id: uuid.UUID, user: User = Depends(family_user), db: Session = Depends(get_db)):
    need, _, _ = get_need_for_user(db, user, need_id)
    return build_detail(db, need)


@router.post("/needs/{need_id}/status", response_model=NeedOut)
def change_need_status(
    need_id: uuid.UUID, payload: NeedStatusChange,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id, write=True)
    if payload.status in SYSTEM_ONLY:
        raise HTTPException(409, SYSTEM_ONLY[payload.status])
    transition_need(db, need, payload.status, user, reason=payload.reason)
    db.commit()
    db.refresh(need)
    return to_need_out(need)


@router.post("/needs/{need_id}/confirm", response_model=NeedDetail)
def confirm_outcome(
    need_id: uuid.UUID, payload: ConfirmRequest,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id, write=True)

    if payload.method not in CITIZEN_CONFIRM_METHODS:
        raise HTTPException(403, "Only an authorised provider can record provider confirmation.")
    if need.category == ServiceCategory.PROTECTION:
        raise HTTPException(
            403, "Protection outcomes must be confirmed by an authorised provider or support worker."
        )
    if need.status == S.NEEDS_ASSESSMENT:
        raise HTTPException(409, "Assess this need first. Support cannot be confirmed before that.")
    if S.SUPPORT_CONFIRMED not in ALLOWED_TRANSITIONS[need.status]:
        raise HTTPException(409, f"Support cannot be confirmed while this need is {need.status.value}.")

    db.add(OutcomeConfirmation(
        need_id=need.id, outcome=payload.outcome, method=payload.method,
        confirmed_by_user_id=user.id, confirmed_by_role=user.role,
        provider_verified=False,  # a family's word is never provider-verified
        reference_note=payload.reference_note,
    ))
    db.flush()
    transition_need(
        db, need, S.SUPPORT_CONFIRMED, user, reason="Outcome confirmed",
        explanation="Confirmed by the family. Not yet verified by a provider.",
    )
    log_event(db, actor=user, action="OUTCOME_CONFIRMED", entity_type="service_need",
              entity_id=need.id, to_value=payload.method.value)
    db.commit()
    db.refresh(need)
    return build_detail(db, need)