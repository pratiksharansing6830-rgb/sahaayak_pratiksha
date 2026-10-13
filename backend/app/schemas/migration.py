import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import MigrationStatus


def same_place(od: str, os_: str, dd: str, ds: str) -> bool:
    return od.strip().lower() == dd.strip().lower() and os_.strip().lower() == ds.strip().lower()


class MigrationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin_district: str = Field(min_length=1, max_length=100)
    origin_state: str = Field(min_length=1, max_length=100)
    destination_district: str = Field(min_length=1, max_length=100)
    destination_state: str = Field(min_length=1, max_length=100)
    planned_date: date | None = None
    work_category: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def different_places(self):
        if same_place(self.origin_district, self.origin_state,
                      self.destination_district, self.destination_state):
            raise ValueError("Origin and destination must be different.")
        return self


class MigrationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    origin_district: str | None = Field(default=None, min_length=1, max_length=100)
    origin_state: str | None = Field(default=None, min_length=1, max_length=100)
    destination_district: str | None = Field(default=None, min_length=1, max_length=100)
    destination_state: str | None = Field(default=None, min_length=1, max_length=100)
    planned_date: date | None = None
    work_category: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def places_not_null(self):
        for f in ("origin_district", "origin_state", "destination_district", "destination_state"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class MigrationStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: MigrationStatus
    actual_date: date | None = None
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("actual_date")
    @classmethod
    def not_future(cls, v):
        if v is not None and v > date.today():
            raise ValueError("The actual move date cannot be in the future.")
        return v


class MigrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    origin_district: str
    origin_state: str
    destination_district: str
    destination_state: str
    planned_date: date | None
    actual_date: date | None
    status: MigrationStatus
    work_category: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime