from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.api.deps import require_roles
from app.core.database import get_db
from app.models import Role, ServiceCategory, User
from app.schemas.gov import (
    AlertsResponse,
    CategoryResponse,
    DestinationResponse,
    GapResponse,
    Overview,
    PriorityResponse,
    TrendResponse,
)
from app.services import gov as svc
from app.services.audit import log_event
from app.services.locations import require_location

router = APIRouter(prefix="/gov", tags=["government"])
gov_only = require_roles(Role.GOVERNMENT)


def gov_access(
    request: Request,
    user: User = Depends(gov_only),
    db: Session = Depends(get_db),
) -> User:
    log_event(
        db,
        actor=user,
        action="GOV_REPORT_VIEWED",
        entity_type="gov_report",
        to_value=request.url.path.rsplit("/", 1)[-1],
    )
    db.commit()
    return user


def date_filters(
    from_date: date | None = None,
    to_date: date | None = None,
) -> svc.Filters:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(422, "from_date must not be after to_date.")
    return svc.Filters(from_date=from_date, to_date=to_date)


def area_filters(
    from_date: date | None = None,
    to_date: date | None = None,
    district: str | None = Query(None, max_length=100),
    category: ServiceCategory | None = None,
) -> svc.Filters:
    f = date_filters(from_date, to_date)
    f.district = (
        require_location(district, None).district if district else None
    )
    f.category = category
    return f


@router.get("/overview", response_model=Overview)
def get_overview(
    f: svc.Filters = Depends(date_filters),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.overview(db, f)


@router.get("/unresolved-by-category", response_model=CategoryResponse)
def get_unresolved(
    f: svc.Filters = Depends(area_filters),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.unresolved_by_category(db, f)


@router.get("/destinations", response_model=DestinationResponse)
def get_destinations(
    f: svc.Filters = Depends(area_filters),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.destinations(db, f)


@router.get("/trends", response_model=TrendResponse)
def get_trends(
    months: int = Query(12, ge=1, le=24),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.trends(db, months)


@router.get("/service-gaps", response_model=GapResponse)
def get_service_gaps(
    f: svc.Filters = Depends(area_filters),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.service_gaps(db, f)


@router.get("/priority", response_model=PriorityResponse)
def get_priority(
    limit: int = Query(20, ge=1, le=100),
    f: svc.Filters = Depends(area_filters),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.priority(db, f, limit)


@router.get("/alerts", response_model=AlertsResponse)
def get_alerts(
    f: svc.Filters = Depends(area_filters),
    user: User = Depends(gov_access),
    db: Session = Depends(get_db),
):
    return svc.alerts(db, f)