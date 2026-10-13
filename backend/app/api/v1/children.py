import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import Child, Role, User
from app.schemas.family import ChildCreate, ChildOut, ChildUpdate
from app.services.access import get_child_for_user, get_family_access
from app.services.audit import log_event

router = APIRouter(tags=["children"])
citizen_only = require_roles(Role.CITIZEN)
family_user = require_roles(Role.CITIZEN, Role.NGO)


@router.post("/families/{family_id}/children", response_model=ChildOut, status_code=201)
def add_child(
    family_id: uuid.UUID, payload: ChildCreate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id, write=True)
    child = Child(family_id=family.id, **payload.model_dump())
    db.add(child)
    db.flush()
    log_event(db, actor=user, action="CHILD_CREATED", entity_type="child", entity_id=child.id)
    db.commit()
    db.refresh(child)
    return child


@router.get("/families/{family_id}/children", response_model=list[ChildOut])
def list_children(
    family_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(family_user), db: Session = Depends(get_db),
):
    family, _ = get_family_access(db, user, family_id)
    stmt = (
        select(Child)
        .where(Child.family_id == family.id, Child.deleted_at.is_(None))
        .order_by(Child.created_at).limit(limit).offset(offset)
    )
    return db.scalars(stmt).all()


@router.get("/children/{child_id}", response_model=ChildOut)
def get_child(child_id: uuid.UUID, user: User = Depends(family_user), db: Session = Depends(get_db)):
    child, _ = get_child_for_user(db, user, child_id)
    return child


@router.patch("/children/{child_id}", response_model=ChildOut)
def update_child(
    child_id: uuid.UUID, payload: ChildUpdate,
    user: User = Depends(citizen_only), db: Session = Depends(get_db),
):
    child, _ = get_child_for_user(db, user, child_id, write=True)
    changes = payload.model_dump(exclude_unset=True)
    real = {k: v for k, v in changes.items() if getattr(child, k) != v}
    for k, v in real.items():
        setattr(child, k, v)
    if real:
        log_event(
            db, actor=user, action="CHILD_UPDATED", entity_type="child",
            entity_id=child.id, to_value=",".join(sorted(real))[:100],  # field names only
        )
    db.commit()
    db.refresh(child)
    return child


@router.delete("/children/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_child(child_id: uuid.UUID, user: User = Depends(citizen_only), db: Session = Depends(get_db)):
    child, _ = get_child_for_user(db, user, child_id, write=True)
    child.deleted_at = datetime.now(timezone.utc)  # soft delete: history is kept
    log_event(db, actor=user, action="CHILD_REMOVED", entity_type="child", entity_id=child.id)
    db.commit()