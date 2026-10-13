import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import Organization, Role, ServiceListing, User, VerificationStatus
from app.schemas.service import ServiceCreate, ServiceOut, ServiceUpdate, to_service_out
from app.services.audit import log_event
from app.services.locations import require_location

router = APIRouter(prefix="/admin/services", tags=["admin"])
admin_only = require_roles(Role.ADMIN)


def _check_org(db: Session, org_id):
    if org_id and not db.get(Organization, org_id):
        raise HTTPException(404, "Organization not found.")


@router.post("", response_model=ServiceOut, status_code=201)
def create_service(payload: ServiceCreate, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    loc = require_location(payload.district, None)
    _check_org(db, payload.organization_id)
    data = payload.model_dump()
    data["district"], data["state"] = loc.district, loc.state
    s = ServiceListing(**data)
    if s.verification_status == VerificationStatus.VERIFIED:
        s.last_verified_at = datetime.now(timezone.utc)
    db.add(s)
    db.flush()
    log_event(db, actor=admin, action="SERVICE_CREATED", entity_type="service_listing",
              entity_id=s.id, to_value=s.verification_status.value)
    db.commit()
    db.refresh(s)
    return to_service_out(s)


@router.get("", response_model=list[ServiceOut])
def list_services(
    district: str | None = None,
    include_inactive: bool = False,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: User = Depends(admin_only), db: Session = Depends(get_db),
):
    stmt = select(ServiceListing).order_by(ServiceListing.created_at.desc()).limit(limit).offset(offset)
    if district:
        stmt = stmt.where(ServiceListing.district == require_location(district, None).district)
    if not include_inactive:
        stmt = stmt.where(ServiceListing.is_active.is_(True))
    return [to_service_out(s) for s in db.scalars(stmt).all()]


@router.patch("/{service_id}", response_model=ServiceOut)
def update_service(
    service_id: uuid.UUID, payload: ServiceUpdate,
    admin: User = Depends(admin_only), db: Session = Depends(get_db),
):
    s = db.get(ServiceListing, service_id)
    if s is None:
        raise HTTPException(404, "Service not found.")
    changes = payload.model_dump(exclude_unset=True)
    if "district" in changes:
        changes["district"] = require_location(changes["district"], None).district
    if "organization_id" in changes:
        _check_org(db, changes["organization_id"])

    merged = {f: changes.get(f, getattr(s, f))
              for f in ("latitude", "longitude", "verification_status", "data_source")}
    if (merged["latitude"] is None) != (merged["longitude"] is None):
        raise HTTPException(422, "Give both latitude and longitude, or neither.")
    if merged["verification_status"] == VerificationStatus.VERIFIED and not merged["data_source"]:
        raise HTTPException(422, "A verified listing needs a data_source.")

    old_status = s.verification_status
    real = {k: v for k, v in changes.items() if getattr(s, k) != v}
    for k, v in real.items():
        setattr(s, k, v)
    if real:
        log_event(db, actor=admin, action="SERVICE_UPDATED", entity_type="service_listing",
                  entity_id=s.id, to_value=",".join(sorted(real))[:100])
    if "verification_status" in real:
        if s.verification_status == VerificationStatus.VERIFIED:
            s.last_verified_at = datetime.now(timezone.utc)
        log_event(db, actor=admin, action="SERVICE_VERIFICATION_CHANGED", entity_type="service_listing",
                  entity_id=s.id, from_value=old_status.value, to_value=s.verification_status.value)
    db.commit()
    db.refresh(s)
    return to_service_out(s)


@router.delete("/{service_id}", status_code=204)
def deactivate_service(service_id: uuid.UUID, admin: User = Depends(admin_only), db: Session = Depends(get_db)):
    s = db.get(ServiceListing, service_id)
    if s is None:
        raise HTTPException(404, "Service not found.")
    s.is_active = False  # kept so existing referrals still make sense
    log_event(db, actor=admin, action="SERVICE_DEACTIVATED", entity_type="service_listing", entity_id=s.id)
    db.commit()