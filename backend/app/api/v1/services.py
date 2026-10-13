import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session
from app.services.locations import DISTRICTS, require_location
from app.api.deps import get_current_user
from app.core.database import get_db
from app.models import ServiceCategory, ServiceListing, User, VerificationStatus
from app.schemas.service import LocationOut, ServiceOut, ServiceSearchResult, to_service_out
from app.services.locations import require_location

router = APIRouter(prefix="/services", tags=["service directory"])


@router.get("", response_model=ServiceSearchResult)
def search_services(
    district: str = Query(..., min_length=1, max_length=100),
    state: str | None = Query(None, max_length=100),
    category: ServiceCategory | None = None,
    include_sample: bool = True,
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    loc = require_location(district, state)  # 422 if unknown: never defaults to another place
    base = select(ServiceListing).where(
        ServiceListing.district == loc.district, ServiceListing.is_active.is_(True)
    )
    if category:
        base = base.where(ServiceListing.category == category)
    if not include_sample:
        base = base.where(ServiceListing.verification_status != VerificationStatus.SAMPLE)

    total = db.scalar(select(func.count()).select_from(base.subquery()))
    rank = case(
        (ServiceListing.verification_status == VerificationStatus.VERIFIED, 0),
        (ServiceListing.verification_status == VerificationStatus.UNVERIFIED, 1),
        else_=2,
    )
    rows = db.scalars(base.order_by(rank, ServiceListing.name).limit(limit).offset(offset)).all()
    return ServiceSearchResult(
        location=LocationOut(
            district=loc.district, state=loc.state, latitude=loc.latitude, longitude=loc.longitude
        ),
        total=total,
        results=[to_service_out(s, loc) for s in rows],
    )

@router.get("/districts")
def list_districts(user: User = Depends(get_current_user)):
    return [{"name": n, "latitude": lat, "longitude": lng} for n, (lat, lng) in sorted(DISTRICTS.items())]
@router.get("/{service_id}", response_model=ServiceOut)
def get_service(
    service_id: uuid.UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db),
):
    s = db.scalar(select(ServiceListing).where(
        ServiceListing.id == service_id, ServiceListing.is_active.is_(True)))
    if s is None:
        raise HTTPException(404, "Service not found.")
    return to_service_out(s)