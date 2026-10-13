import uuid

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccessLevel, Child, Family, FamilyAccess, FollowUp, Migration,Referral, ServiceNeed, User,
)


def get_family_access(
    db: Session, user: User, family_id: uuid.UUID, *,
    write: bool = False, not_found: str = "Family not found.",
) -> tuple[Family, FamilyAccess]:
    """Return (family, access) or raise 404. Same 404 whether it doesn't exist or isn't yours."""
    family = db.scalar(select(Family).where(Family.id == family_id, Family.deleted_at.is_(None)))
    access = None
    if family is not None:
        access = db.scalar(
            select(FamilyAccess).where(
                FamilyAccess.family_id == family_id,
                FamilyAccess.user_id == user.id,
                FamilyAccess.revoked_at.is_(None),
            )
        )
    if family is None or access is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, not_found)
    if write and access.access_level == AccessLevel.SUPPORT_WORKER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "You have read-only access to this family.")
    return family, access


def get_child_for_user(db: Session, user: User, child_id: uuid.UUID, *, write: bool = False):
    msg = "Child not found."
    child = db.scalar(select(Child).where(Child.id == child_id, Child.deleted_at.is_(None)))
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    family, _ = get_family_access(db, user, child.family_id, write=write, not_found=msg)
    return child, family


def get_migration_for_user(db: Session, user: User, migration_id: uuid.UUID, *, write: bool = False):
    msg = "Migration not found."
    mig = db.get(Migration, migration_id)
    if mig is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    family, _ = get_family_access(db, user, mig.family_id, write=write, not_found=msg)
    return mig, family


def get_need_for_user(db: Session, user: User, need_id: uuid.UUID, *, write: bool = False):
    msg = "Need not found."
    need = db.get(ServiceNeed, need_id)
    if need is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    child = db.scalar(select(Child).where(Child.id == need.child_id, Child.deleted_at.is_(None)))
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    family, _ = get_family_access(db, user, child.family_id, write=write, not_found=msg)
    return need, child, family


def get_followup_for_user(db: Session, user: User, followup_id: uuid.UUID, *, write: bool = False):
    msg = "Follow-up not found."
    fu = db.get(FollowUp, followup_id)
    if fu is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    need = db.get(ServiceNeed, fu.need_id)
    child = db.scalar(select(Child).where(Child.id == need.child_id, Child.deleted_at.is_(None)))
    if child is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    family, _ = get_family_access(db, user, child.family_id, write=write, not_found=msg)
    return fu, need, child, family
def get_referral_for_user(db: Session, user: User, referral_id: uuid.UUID, *, write: bool = False):
    msg = "Referral not found."
    ref = db.get(Referral, referral_id)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    try:
        need, child, family = get_need_for_user(db, user, ref.need_id, write=write)
    except HTTPException as e:
        if e.status_code == status.HTTP_404_NOT_FOUND:
            raise HTTPException(status.HTTP_404_NOT_FOUND, msg)  # same message either way
        raise
    return ref, need, child, family