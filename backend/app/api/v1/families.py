import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import AccessLevel, Family, FamilyAccess, Role, User
from app.schemas.family import (
    AccessOut, FamilyCreate, FamilyOut, FamilyUpdate, GrantAccessRequest,
)
from app.services.access import get_family_access
from app.services.audit import log_event

router = APIRouter(prefix="/families", tags=["families"])
citizen_only = require_roles(Role.CITIZEN)
family_user = require_roles(Role.CITIZEN, Role.NGO)

PRIVACY_NOTICE_VERSION = "1.0"


def _require_owner(access: FamilyAccess) -> None:
    if access.access_level != AccessLevel.OWNER:
        raise HTTPException(403, "Only the family owner can manage who has access.")


def _access_out(access: FamilyAccess, name: str) -> AccessOut:
    return AccessOut(
        id=access.id, user_id=access.user_id, user_name=name,
        access_level=access.access_level, granted_at=access.updated_at,
    )


@router.post("", response_model=FamilyOut, status_code=status.HTTP_201_CREATED)
def create_family(
    payload: FamilyCreate, user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    data = payload.model_dump(exclude={"consent_given"})
    family = Family(
        **data,
        consent_given_at=datetime.now(timezone.utc),
        privacy_notice_version=PRIVACY_NOTICE_VERSION,
        created_by_user_id=user.id,
    )
    db.add(family)
    db.flush()
    db.add(FamilyAccess(
        family_id=family.id, user_id=user.id,
        access_level=AccessLevel.OWNER, granted_by_user_id=user.id,
    ))
    log_event(db, actor=user, action="FAMILY_CREATED", entity_type="family", entity_id=family.id)
    db.commit()
    db.refresh(family)
    return family


@router.get("", response_model=list[FamilyOut])
def list_my_families(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Family)
        .join(FamilyAccess, FamilyAccess.family_id == Family.id)
        .where(
            FamilyAccess.user_id == user.id,
            FamilyAccess.revoked_at.is_(None),
            Family.deleted_at.is_(None),
        )
        .order_by(Family.created_at.desc())
        .limit(limit).offset(offset)
    )
    return db.scalars(stmt).all()


@router.get("/{family_id}", response_model=FamilyOut)
def get_family(family_id: uuid.UUID, user: User = Depends(family_user), db: Session = Depends(get_db)):
    family, _ = get_family_access(db, user, family_id)
    return family


@router.patch("/{family_id}", response_model=FamilyOut)
def update_family(
    family_id: uuid.UUID, payload: FamilyUpdate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id, write=True)
    changes = payload.model_dump(exclude_unset=True)
    real = {k: v for k, v in changes.items() if getattr(family, k) != v}
    for k, v in real.items():
        setattr(family, k, v)
    if real:
        log_event(
            db, actor=user, action="FAMILY_UPDATED", entity_type="family",
            entity_id=family.id, to_value=",".join(sorted(real))[:100],  # field names only
        )
    db.commit()
    db.refresh(family)
    return family


# ----- sharing with an NGO support worker -----
@router.get("/{family_id}/access", response_model=list[AccessOut])
def list_access(family_id: uuid.UUID, user: User = Depends(citizen_only), db: Session = Depends(get_db)):
    family, mine = get_family_access(db, user, family_id)
    _require_owner(mine)
    rows = db.execute(
        select(FamilyAccess, User.full_name)
        .join(User, User.id == FamilyAccess.user_id)
        .where(FamilyAccess.family_id == family.id, FamilyAccess.revoked_at.is_(None))
        .order_by(FamilyAccess.created_at)
    ).all()
    return [_access_out(a, name) for a, name in rows]


@router.post("/{family_id}/access", response_model=AccessOut, status_code=201)
def grant_support_access(
    family_id: uuid.UUID, payload: GrantAccessRequest,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    family, mine = get_family_access(db, user, family_id, write=True)
    _require_owner(mine)

    target = db.scalar(
        select(User).where(
            User.email == payload.email.lower(), User.role == Role.NGO, User.is_active.is_(True)
        )
    )
    if target is None:
        raise HTTPException(404, "No active support-worker account with that email.")

    access = db.scalar(
        select(FamilyAccess).where(FamilyAccess.family_id == family.id, FamilyAccess.user_id == target.id)
    )
    if access:  # re-activate a previously revoked grant (unique per family+user)
        access.revoked_at = None
        access.access_level = AccessLevel.SUPPORT_WORKER
        access.granted_by_user_id = user.id
    else:
        access = FamilyAccess(
            family_id=family.id, user_id=target.id,
            access_level=AccessLevel.SUPPORT_WORKER, granted_by_user_id=user.id,
        )
        db.add(access)
    db.flush()
    log_event(
        db, actor=user, action="FAMILY_ACCESS_GRANTED", entity_type="family",
        entity_id=family.id, to_value="SUPPORT_WORKER",
    )
    db.commit()
    db.refresh(access)
    return _access_out(access, target.full_name)


@router.delete("/{family_id}/access/{access_id}", status_code=204)
def revoke_access(
    family_id: uuid.UUID, access_id: uuid.UUID,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    family, mine = get_family_access(db, user, family_id, write=True)
    _require_owner(mine)
    target = db.scalar(
        select(FamilyAccess).where(
            FamilyAccess.id == access_id,
            FamilyAccess.family_id == family.id,
            FamilyAccess.revoked_at.is_(None),
        )
    )
    if target is None:
        raise HTTPException(404, "Access grant not found.")
    if target.access_level == AccessLevel.OWNER:
        raise HTTPException(400, "The owner's access cannot be removed.")
    target.revoked_at = datetime.now(timezone.utc)
    log_event(
        db, actor=user, action="FAMILY_ACCESS_REVOKED", entity_type="family",
        entity_id=family.id, from_value=target.access_level.value,
    )
    db.commit()