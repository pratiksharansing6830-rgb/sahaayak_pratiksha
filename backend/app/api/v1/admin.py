import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.core.security import hash_password
from app.models import (
    AuditEvent,
    Organization,
    Role,
    ServiceListing,
    User,
)
from app.schemas.admin import (
    AdminCreateUser,
    AdminUpdateUser,
    AuditEventOut,
    OrganizationCreate,
    OrganizationOut,
)
from app.schemas.auth import UserOut
from app.services.audit import log_event

router = APIRouter(prefix="/admin", tags=["admin"])
admin_only = require_roles(Role.ADMIN)


def _val(x) -> str | None:
    if x is None:
        return None
    return x.value if isinstance(x, Enum) else str(x)


@router.post("/organizations", response_model=OrganizationOut, status_code=201)
def create_organization(
    payload: OrganizationCreate,
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    org = Organization(**payload.model_dump())
    db.add(org)
    db.flush()
    log_event(
        db,
        actor=admin,
        action="ORGANIZATION_CREATED",
        entity_type="organization",
        entity_id=org.id,
    )
    db.commit()
    db.refresh(org)
    return org


@router.get("/organizations", response_model=list[OrganizationOut])
def list_organizations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    stmt = (
        select(Organization)
        .order_by(Organization.name)
        .limit(limit)
        .offset(offset)
    )
    return db.scalars(stmt).all()


@router.post("/users", response_model=UserOut, status_code=201)
def create_user(
    payload: AdminCreateUser,
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    email = payload.email.lower()

    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(
            status_code=409,
            detail="An account with this email already exists.",
        )

    if payload.organization_id and not db.get(
        Organization, payload.organization_id
    ):
        raise HTTPException(status_code=404, detail="Organization not found.")

    user = User(
        email=email,
        password_hash=hash_password(payload.password),
        full_name=payload.full_name.strip(),
        phone=payload.phone,
        role=payload.role,
        organization_id=payload.organization_id,
    )
    db.add(user)
    db.flush()

    log_event(
        db,
        actor=admin,
        action="USER_CREATED_BY_ADMIN",
        entity_type="user",
        entity_id=user.id,
        to_value=payload.role.value,
    )

    db.commit()
    db.refresh(user)
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(
    role: Role | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    stmt = (
        select(User)
        .order_by(User.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if role:
        stmt = stmt.where(User.role == role)

    return db.scalars(stmt).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(
    user_id: uuid.UUID,
    payload: AdminUpdateUser,
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    user = db.get(User, user_id)

    if user is None:
        raise HTTPException(status_code=404, detail="User not found.")

    changes = payload.model_dump(exclude_unset=True)

    if user.id == admin.id:
        if changes.get("is_active") is False or (
            "role" in changes and changes["role"] != Role.ADMIN
        ):
            raise HTTPException(
                status_code=400,
                detail="Admins cannot deactivate or demote themselves.",
            )

    if changes.get("organization_id") and not db.get(
        Organization, changes["organization_id"]
    ):
        raise HTTPException(status_code=404, detail="Organization not found.")

    for field, new_value in changes.items():
        old_value = getattr(user, field)

        if old_value == new_value:
            continue

        setattr(user, field, new_value)

        log_event(
            db,
            actor=admin,
            action=f"USER_{field.upper()}_CHANGED",
            entity_type="user",
            entity_id=user.id,
            from_value=_val(old_value),
            to_value=_val(new_value),
        )

    db.commit()
    db.refresh(user)
    return user


@router.get("/audit-events", response_model=list[AuditEventOut])
def list_audit_events(
    action: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    stmt = (
        select(AuditEvent)
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
        .offset(offset)
    )

    if action:
        stmt = stmt.where(AuditEvent.action == action)

    return db.scalars(stmt).all()


@router.get("/health")
def platform_health(
    admin: User = Depends(admin_only),
    db: Session = Depends(get_db),
):
    """Return platform health counts without personal data."""
    db.execute(text("SELECT 1"))

    by_role = {role.value: 0 for role in Role}

    for role, count in db.execute(
        select(User.role, func.count()).group_by(User.role)
    ).all():
        by_role[role.value] = count

    by_verification: dict[str, int] = {}

    for verification_status, count in db.execute(
        select(ServiceListing.verification_status, func.count())
        .where(ServiceListing.is_active.is_(True))
        .group_by(ServiceListing.verification_status)
    ).all():
        key = (
            verification_status.value
            if isinstance(verification_status, Enum)
            else str(verification_status)
        )
        by_verification[key] = count

    day = datetime.now(timezone.utc) - timedelta(days=1)

    return {
        "database": "connected",
        "users_by_role": by_role,
        "active_users": db.scalar(
            select(func.count())
            .select_from(User)
            .where(User.is_active.is_(True))
        ),
        "organizations": db.scalar(
            select(func.count()).select_from(Organization)
        ),
        "active_listings_by_verification": by_verification,
        "audit_events_last_24h": db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(AuditEvent.created_at >= day)
        ),
        "failed_logins_last_24h": db.scalar(
            select(func.count())
            .select_from(AuditEvent)
            .where(
                AuditEvent.action == "LOGIN_FAILED",
                AuditEvent.created_at >= day,
            )
        ),
    }