import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import ServiceCategory, VerificationStatus
from app.schemas.family import PHONE_PATTERN
from app.services.locations import Location, haversine_km

AVAILABILITY_NOTE = "Potentially suitable service. Sahaayak does not confirm current availability."
DISTANCE_NOTE = "Approximate distance from the centre of the district, not from your home."
LOCATION_NOTE = "Approximate location (district centre)."


class ServiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    category: ServiceCategory
    description: str | None
    address: str | None
    district: str
    state: str
    latitude: float | None
    longitude: float | None
    coordinates_approximate: bool
    contact_phone: str | None
    operating_hours: str | None
    data_source: str | None
    verification_status: VerificationStatus
    last_verified_at: datetime | None
    is_active: bool
    is_sample: bool = False
    is_verified: bool = False
    distance_km_approx: float | None = None
    availability_note: str = AVAILABILITY_NOTE


class LocationOut(BaseModel):
    district: str
    state: str
    latitude: float
    longitude: float
    approximate: bool = True
    note: str = LOCATION_NOTE


class ServiceSearchResult(BaseModel):
    location: LocationOut
    total: int
    distance_note: str = DISTANCE_NOTE
    results: list[ServiceOut]


def to_service_out(s, origin: Location | None = None) -> ServiceOut:
    out = ServiceOut.model_validate(s)
    out.is_sample = s.verification_status == VerificationStatus.SAMPLE
    out.is_verified = s.verification_status == VerificationStatus.VERIFIED
    if origin is not None and s.latitude is not None and s.longitude is not None:
        out.distance_km_approx = round(
            haversine_km(origin.latitude, origin.longitude, s.latitude, s.longitude), 1
        )
    return out


class ServiceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=200)
    category: ServiceCategory
    description: str | None = Field(default=None, max_length=1000)
    address: str | None = Field(default=None, max_length=300)
    district: str = Field(min_length=1, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinates_approximate: bool = True
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    operating_hours: str | None = Field(default=None, max_length=200)
    data_source: str | None = Field(default=None, max_length=200)
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED
    organization_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def rules(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Give both latitude and longitude, or neither.")
        if self.verification_status == VerificationStatus.VERIFIED and not self.data_source:
            raise ValueError("A verified listing needs a data_source.")
        return self


class ServiceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: ServiceCategory | None = None
    description: str | None = Field(default=None, max_length=1000)
    address: str | None = Field(default=None, max_length=300)
    district: str | None = Field(default=None, min_length=1, max_length=100)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    coordinates_approximate: bool | None = None
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    operating_hours: str | None = Field(default=None, max_length=200)
    data_source: str | None = Field(default=None, max_length=200)
    verification_status: VerificationStatus | None = None
    organization_id: uuid.UUID | None = None
    is_active: bool | None = None

    @model_validator(mode="after")
    def required_not_null(self):
        for f in ("name", "category", "district", "coordinates_approximate",
                  "verification_status", "is_active"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self