from datetime import date

from pydantic import BaseModel

from app.core.config import settings
from app.models.enums import ServiceCategory


class PrivacyInfo(BaseModel):
    min_group_size: int
    rule: str
    data_basis: str


def privacy_info() -> PrivacyInfo:
    n = settings.min_group_size
    return PrivacyInfo(
        min_group_size=n,
        rule=(
            f"Figures count distinct children or families. Groups with fewer than {n} are left out, "
            f"and small figures inside larger groups are hidden (null)."
        ),
        data_basis=(
            "Only records entered in Sahaayak by families and providers. "
            "Sample directory entries are never counted. Nothing is estimated."
        ),
    )


class FiltersOut(BaseModel):
    from_date: date | None = None
    to_date: date | None = None
    district: str | None = None
    category: ServiceCategory | None = None


# ---------- Overview ----------
class ConfirmationRate(BaseModel):
    children_with_referral: int | None
    children_provider_confirmed: int | None
    rate_percent: float | None
    note: str


class Overview(BaseModel):
    privacy: PrivacyInfo
    generated_on: date
    filters: FiltersOut
    families_registered: int | None
    children_registered: int | None
    migrations_by_status: dict[str, int | None]  # distinct families
    children_with_open_needs: int | None
    open_needs: int | None
    children_with_overdue_needs: int | None
    children_with_overdue_followups: int | None
    children_with_followups_due: int | None
    children_support_confirmed_by_provider: int | None
    children_support_confirmed_by_family_only: int | None
    confirmation_rate: ConfirmationRate
    notes: list[str]


# ---------- Unresolved needs ----------
class CategoryRow(BaseModel):
    category: ServiceCategory
    children_with_open_needs: int
    open_needs: int
    children_overdue: int | None
    children_awaiting_provider: int | None


class CategoryResponse(BaseModel):
    privacy: PrivacyInfo
    filters: FiltersOut
    rows: list[CategoryRow]
    groups_hidden: int
    note: str


# ---------- Destinations ----------
class DestinationRow(BaseModel):
    destination_district: str
    families_moving: int
    planned: int | None
    active: int | None
    completed: int | None
    children_with_open_needs: int | None


class DestinationResponse(BaseModel):
    privacy: PrivacyInfo
    filters: FiltersOut
    rows: list[DestinationRow]
    groups_hidden: int
    note: str


# ---------- Trends ----------
class TrendPoint(BaseModel):
    month: str
    new_families: int | None
    families_with_new_migrations: int | None
    children_with_provider_confirmed_outcomes: int | None


class TrendResponse(BaseModel):
    privacy: PrivacyInfo
    points: list[TrendPoint]
    note: str


# ---------- Service gaps ----------
class GapRow(BaseModel):
    destination_district: str
    category: ServiceCategory
    children_with_open_needs: int
    directory_listings: int
    verified_listings: int
    coverage: str  # NONE | LOW | SOME
    potential_gap: bool
    explanation: str


class GapResponse(BaseModel):
    privacy: PrivacyInfo
    filters: FiltersOut
    rows: list[GapRow]
    groups_hidden: int
    note: str


# ---------- Priority ----------
class PriorityFactor(BaseModel):
    name: str
    points: float
    max_points: float
    detail: str


class PriorityRow(BaseModel):
    destination_district: str
    category: ServiceCategory
    score: float
    band: str  # LOW | MEDIUM | HIGH
    children_with_open_needs: int
    factors: list[PriorityFactor]


class PriorityResponse(BaseModel):
    privacy: PrivacyInfo
    filters: FiltersOut
    disclaimer: str
    rows: list[PriorityRow]
    groups_hidden: int


# ---------- Alerts ----------
class Alert(BaseModel):
    code: str
    severity: str  # WATCH | ATTENTION
    title: str
    destination_district: str | None
    category: ServiceCategory | None
    children_count: int
    observation: str
    window: str
    limitations: str
    suggested_action: str
    basis: str = "RULE_BASED"


class AlertsResponse(BaseModel):
    privacy: PrivacyInfo
    generated_on: date
    filters: FiltersOut
    alerts: list[Alert]
    note: str