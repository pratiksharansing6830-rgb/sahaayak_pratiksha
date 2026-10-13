import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import (
    Child, FollowUp, FollowUpAction, FollowUpStatus, Role, ServiceCategory, ServiceNeed, User,
)
from app.schemas.continuity import (
    FollowUpComplete, FollowUpCompleteResult, FollowUpCreate, FollowUpOut, FollowUpUpdate,
    to_followup_out, to_need_out,
)
from app.services.access import get_family_access, get_followup_for_user, get_need_for_user
from app.services.audit import log_event
from app.services.continuity import ACTIVE_FOLLOWUP, OPEN_STATUSES

router = APIRouter(tags=["follow-ups"])
citizen_only = require_roles(Role.CITIZEN)
family_user = require_roles(Role.CITIZEN, Role.NGO)


@router.post("/needs/{need_id}/follow-ups", response_model=FollowUpOut, status_code=201)
def create_follow_up(
    need_id: uuid.UUID, payload: FollowUpCreate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    need, _, _ = get_need_for_user(db, user, need_id, write=True)
    if need.status not in OPEN_STATUSES:
        raise HTTPException(409, "This need is already resolved, so it cannot get new follow-ups.")
    if payload.action_type == FollowUpAction.ESCALATE_SAFEGUARDING and need.category != ServiceCategory.PROTECTION:
        raise HTTPException(422, "Safeguarding escalation is only available for protection needs.")

    duplicate = db.scalar(
        select(FollowUp.id).where(
            FollowUp.need_id == need.id,
            FollowUp.action_type == payload.action_type,
            FollowUp.status.in_(ACTIVE_FOLLOWUP),
        ).limit(1)
    )
    if duplicate:
        raise HTTPException(409, "An open follow-up of this type already exists for this need.")

    fu = FollowUp(
        need_id=need.id, action_type=payload.action_type, description=payload.description,
        priority=payload.priority, due_date=payload.due_date or (date.today() + timedelta(days=7)),
        assigned_role=Role.NGO if payload.action_type == FollowUpAction.ESCALATE_SAFEGUARDING else Role.CITIZEN,
    )
    try:
        with db.begin_nested():
            db.add(fu)
            db.flush()
    except IntegrityError:
        raise HTTPException(409, "An open follow-up of this type already exists for this need.")
    log_event(db, actor=user, action="FOLLOWUP_CREATED", entity_type="follow_up",
              entity_id=fu.id, to_value=fu.action_type.value)
    db.commit()
    db.refresh(fu)
    return to_followup_out(fu)


@router.get("/families/{family_id}/follow-ups", response_model=list[FollowUpOut])
def list_follow_ups(
    family_id: uuid.UUID,
    status: FollowUpStatus | None = None,
    overdue_only: bool = False,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id)
    stmt = (
        select(FollowUp)
        .join(ServiceNeed, ServiceNeed.id == FollowUp.need_id)
        .join(Child, Child.id == ServiceNeed.child_id)
        .where(Child.family_id == family.id, Child.deleted_at.is_(None))
    )
    if status:
        stmt = stmt.where(FollowUp.status == status)
    if overdue_only:
        stmt = stmt.where(FollowUp.status.in_(ACTIVE_FOLLOWUP), FollowUp.due_date < date.today())
    stmt = stmt.order_by(FollowUp.due_date.asc().nulls_last(), FollowUp.created_at.desc())
    return [to_followup_out(f) for f in db.scalars(stmt.limit(limit).offset(offset)).all()]


@router.patch("/follow-ups/{follow_up_id}", response_model=FollowUpOut)
def update_follow_up(
    follow_up_id: uuid.UUID, payload: FollowUpUpdate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    fu, _, _, _ = get_followup_for_user(db, user, follow_up_id, write=True)
    if fu.status not in ACTIVE_FOLLOWUP:
        raise HTTPException(409, "Only open follow-ups can be edited.")
    changes = payload.model_dump(exclude_unset=True)
    if changes.pop("status", None):
        changes["status"] = FollowUpStatus.IN_PROGRESS
    real = {k: v for k, v in changes.items() if getattr(fu, k) != v}
    for k, v in real.items():
        setattr(fu, k, v)
    if real:
        log_event(db, actor=user, action="FOLLOWUP_UPDATED", entity_type="follow_up",
                  entity_id=fu.id, to_value=",".join(sorted(real))[:100])
    db.commit()
    db.refresh(fu)
    return to_followup_out(fu)


@router.post("/follow-ups/{follow_up_id}/complete", response_model=FollowUpCompleteResult)
def complete_follow_up(
    follow_up_id: uuid.UUID, payload: FollowUpComplete | None = None,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    fu, need, _, _ = get_followup_for_user(db, user, follow_up_id, write=True)
    if fu.status not in ACTIVE_FOLLOWUP:
        raise HTTPException(409, "This follow-up is already finished.")
    fu.status = FollowUpStatus.COMPLETED
    fu.completed_at = datetime.now(timezone.utc)
    if payload and payload.next_action is not None:
        fu.next_action = payload.next_action
    # Deliberately NOT touching the need: finishing a task is not the same as resolving the need.
    log_event(db, actor=user, action="FOLLOWUP_COMPLETED", entity_type="follow_up", entity_id=fu.id)
    db.commit()
    db.refresh(fu)
    db.refresh(need)
    return FollowUpCompleteResult(follow_up=to_followup_out(fu), need=to_need_out(need))


@router.post("/follow-ups/{follow_up_id}/cancel", response_model=FollowUpOut)
def cancel_follow_up(
    follow_up_id: uuid.UUID, user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    fu, _, _, _ = get_followup_for_user(db, user, follow_up_id, write=True)
    if fu.status not in ACTIVE_FOLLOWUP:
        raise HTTPException(409, "This follow-up is already finished.")
    fu.status = FollowUpStatus.CANCELLED
    log_event(db, actor=user, action="FOLLOWUP_CANCELLED", entity_type="follow_up", entity_id=fu.id)
    db.commit()
    db.refresh(fu)
    return to_followup_out(fu)