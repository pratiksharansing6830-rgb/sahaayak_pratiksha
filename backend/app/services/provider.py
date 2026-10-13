import uuid
from datetime import date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Child, Family, FollowUp, FollowUpAction, Priority, Referral, Role, ServiceCategory,
    ServiceListing, ServiceNeed, User,
)
from app.services.audit import log_event
from app.services.continuity import ACTIVE_FOLLOWUP

C = ServiceCategory
PROVIDER_CATEGORIES: dict[Role, set[ServiceCategory]] = {
    Role.SCHOOL: {C.EDUCATION},
    Role.HEALTHCARE: {C.HEALTHCARE},
    Role.NGO: {C.NUTRITION, C.WELLBEING, C.PROTECTION, C.INCLUSION},
}


def provider_categories(user: User) -> set[ServiceCategory]:
    return PROVIDER_CATEGORIES.get(user.role, set())


def scoped(user: User, *entities):
    """Every referral this provider may see: their organisation's listings, their categories only."""
    return (
        select(*entities).select_from(Referral)
        .join(ServiceListing, ServiceListing.id == Referral.service_listing_id)
        .join(ServiceNeed, ServiceNeed.id == Referral.need_id)
        .join(Child, Child.id == ServiceNeed.child_id)
        .join(Family, Family.id == Child.family_id)
        .where(
            ServiceListing.organization_id == user.organization_id,
            ServiceNeed.category.in_(list(provider_categories(user))),
            Child.deleted_at.is_(None),
            Family.deleted_at.is_(None),
        )
    )


def get_provider_referral(db: Session, user: User, referral_id: uuid.UUID):
    """Returns (referral, need, child, family, listing) or 404."""
    row = db.execute(
        scoped(user, Referral, ServiceNeed, Child, Family, ServiceListing).where(Referral.id == referral_id)
    ).first()
    if row is None:
        raise HTTPException(404, "Referral not found.")
    return tuple(row)


def add_followup(
    db: Session, need: ServiceNeed, action: FollowUpAction, description: str, actor: User, *,
    priority: Priority = Priority.MEDIUM, referral_id=None, days: int = 7,
):
    """Create a follow-up unless an active one of the same type exists."""
    dup = db.scalar(select(FollowUp.id).where(
        FollowUp.need_id == need.id, FollowUp.action_type == action,
        FollowUp.status.in_(ACTIVE_FOLLOWUP)).limit(1))
    if dup:
        return None
    fu = FollowUp(
        need_id=need.id, referral_id=referral_id, action_type=action,
        description=description[:500], assigned_role=Role.CITIZEN, priority=priority,
        due_date=date.today() + timedelta(days=days),
    )
    try:
        with db.begin_nested():
            db.add(fu)
            db.flush()
    except IntegrityError:
        return None
    log_event(db, actor=actor, action="FOLLOWUP_CREATED", entity_type="follow_up",
              entity_id=fu.id, to_value=action.value)
    return fu