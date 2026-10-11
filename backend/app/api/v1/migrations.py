import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import Migration, MigrationStatus, Role, User
from app.schemas.migration import (
    MigrationCreate, MigrationOut, MigrationStatusChange, MigrationUpdate, same_place,
)
from app.services.access import get_family_access, get_migration_for_user
from app.services.audit import log_event
from app.services.continuity import review_needs_after_destination_change
router = APIRouter(tags=["migrations"])
citizen_only = require_roles(Role.CITIZEN)
family_user = require_roles(Role.CITIZEN, Role.NGO)

S = MigrationStatus
ALLOWED_TRANSITIONS = {
    S.PLANNED: {S.ACTIVE, S.CANCELLED},
    S.ACTIVE: {S.COMPLETED, S.CANCELLED},
    S.COMPLETED: set(),
    S.CANCELLED: set(),
}
PLACE_FIELDS = ("origin_district", "origin_state", "destination_district", "destination_state")
LOCKED_AFTER_PLANNING = set(PLACE_FIELDS) | {"planned_date"}


@router.post("/families/{family_id}/migrations", response_model=MigrationOut, status_code=201)
def create_migration(
    family_id: uuid.UUID, payload: MigrationCreate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id, write=True)
    mig = Migration(family_id=family.id, **payload.model_dump())
    db.add(mig)
    db.flush()
    log_event(db, actor=user, action="MIGRATION_CREATED", entity_type="migration",
              entity_id=mig.id, to_value="PLANNED")
    db.commit()
    db.refresh(mig)
    return mig


@router.get("/families/{family_id}/migrations", response_model=list[MigrationOut])
def list_migrations(
    family_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id)
    stmt = (
        select(Migration).where(Migration.family_id == family.id)
        .order_by(Migration.created_at.desc()).limit(limit).offset(offset)
    )
    return db.scalars(stmt).all()


@router.get("/migrations/{migration_id}", response_model=MigrationOut)
def get_migration(migration_id: uuid.UUID, user: User = Depends(family_user), db: Session = Depends(get_db)):
    mig, _ = get_migration_for_user(db, user, migration_id)
    return mig


@router.patch("/migrations/{migration_id}", response_model=MigrationOut)
def update_migration(
    migration_id: uuid.UUID, payload: MigrationUpdate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    mig, _ = get_migration_for_user(db, user, migration_id, write=True)
    if mig.status in (S.COMPLETED, S.CANCELLED):
        raise HTTPException(409, "Completed or cancelled migrations can no longer be edited.")

    changes = payload.model_dump(exclude_unset=True)
    real = {k: v for k, v in changes.items() if getattr(mig, k) != v}
    if not real:
        return mig

    if mig.status != S.PLANNED and set(real) & LOCKED_AFTER_PLANNING:
        raise HTTPException(
            409,
            "Origin, destination and planned date can only change while the move is still planned. "
            "If the plan changed, cancel this migration and create a new one.",
        )

    merged = {f: real.get(f, getattr(mig, f)) for f in PLACE_FIELDS}
    if same_place(*(merged[f] for f in PLACE_FIELDS)):
        raise HTTPException(422, "Origin and destination must be different.")

    old_destination = mig.destination_district
    for k, v in real.items():
        setattr(mig, k, v)
    log_event(db, actor=user, action="MIGRATION_UPDATED", entity_type="migration",
              entity_id=mig.id, to_value=",".join(sorted(real))[:100])
    if "destination_district" in real or "destination_state" in real:
        log_event(db, actor=user, action="MIGRATION_DESTINATION_CHANGED", entity_type="migration",
                entity_id=mig.id, from_value=old_destination, to_value=mig.destination_district)
        review_needs_after_destination_change(db, mig, user)
   
    db.commit()
    db.refresh(mig)
    return mig


@router.post("/migrations/{migration_id}/status", response_model=MigrationOut)
def change_migration_status(
    migration_id: uuid.UUID, payload: MigrationStatusChange,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    mig, _ = get_migration_for_user(db, user, migration_id, write=True)
    new = payload.status
    old = mig.status
    if new not in ALLOWED_TRANSITIONS[old]:
        raise HTTPException(409, f"A {old.value} migration cannot be changed to {new.value}.")

    if new == S.ACTIVE:
        other = db.scalar(
            select(Migration.id).where(
                Migration.family_id == mig.family_id,
                Migration.status == S.ACTIVE,
                Migration.id != mig.id,
            ).limit(1)
        )
        if other:
            raise HTTPException(409, "This family already has a move in progress. Complete or cancel it first.")

    if new in (S.ACTIVE, S.COMPLETED):
        mig.actual_date = payload.actual_date or mig.actual_date or date.today()

    mig.status = new
    log_event(db, actor=user, action="MIGRATION_STATUS_CHANGED", entity_type="migration",
              entity_id=mig.id, from_value=old.value, to_value=new.value, reason=payload.reason)
    db.commit()
    db.refresh(mig)
    return mig