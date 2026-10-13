import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.models.enums import AccessLevel, EducationStatus

PHONE_PATTERN = r"^[+0-9][0-9 \-]{6,19}$"
Language = Literal["en", "mr", "hi"]


def _reject_nulls(model: BaseModel, fields: tuple[str, ...]) -> None:
    for f in fields:
        if f in model.model_fields_set and getattr(model, f) is None:
            raise ValueError(f"{f} cannot be null")


def _validate_dob(v: date | None) -> date | None:
    if v is None:
        return v
    today = date.today()
    if v > today:
        raise ValueError("Date of birth cannot be in the future.")
    age = today.year - v.year - ((today.month, today.day) < (v.month, v.day))
    if age >= 18:
        raise ValueError("Sahaayak is for children under 18.")
    return v


# ---------- Family ----------
class FamilyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    household_name: str = Field(min_length=1, max_length=200)
    primary_caregiver_name: str = Field(min_length=1, max_length=200)
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    origin_district: str | None = Field(default=None, max_length=100)
    origin_state: str | None = Field(default=None, max_length=100)
    preferred_language: Language = "en"
    consent_given: bool

    @field_validator("consent_given")
    @classmethod
    def must_consent(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Consent to the privacy notice is required to create a family profile.")
        return v


class FamilyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    household_name: str | None = Field(default=None, min_length=1, max_length=200)
    primary_caregiver_name: str | None = Field(default=None, min_length=1, max_length=200)
    contact_phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    origin_district: str | None = Field(default=None, max_length=100)
    origin_state: str | None = Field(default=None, max_length=100)
    preferred_language: Language | None = None

    @model_validator(mode="after")
    def required_fields_not_null(self):
        _reject_nulls(self, ("household_name", "primary_caregiver_name", "preferred_language"))
        return self


class FamilyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    household_name: str
    primary_caregiver_name: str
    contact_phone: str | None
    origin_district: str | None
    origin_state: str | None
    preferred_language: str
    consent_given_at: datetime | None
    privacy_notice_version: str | None
    created_at: datetime
    updated_at: datetime


# ---------- Child ----------
class ChildCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str = Field(min_length=1, max_length=200)
    date_of_birth: date | None = None
    approx_age_years: int | None = Field(default=None, ge=0, le=17)
    education_status: EducationStatus = EducationStatus.UNKNOWN
    current_school_name: str | None = Field(default=None, max_length=200)
    accommodations_note: str | None = Field(default=None, max_length=1000)

    @field_validator("date_of_birth")
    @classmethod
    def check_dob(cls, v):
        return _validate_dob(v)

    @model_validator(mode="after")
    def need_age_information(self):
        if self.date_of_birth is None and self.approx_age_years is None:
            raise ValueError("Provide a date of birth or an approximate age.")
        return self


class ChildUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    date_of_birth: date | None = None
    approx_age_years: int | None = Field(default=None, ge=0, le=17)
    education_status: EducationStatus | None = None
    current_school_name: str | None = Field(default=None, max_length=200)
    accommodations_note: str | None = Field(default=None, max_length=1000)

    @field_validator("date_of_birth")
    @classmethod
    def check_dob(cls, v):
        return _validate_dob(v)

    @model_validator(mode="after")
    def required_fields_not_null(self):
        _reject_nulls(self, ("full_name", "education_status"))
        return self


class ChildOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    family_id: uuid.UUID
    full_name: str
    date_of_birth: date | None
    approx_age_years: int | None
    education_status: EducationStatus
    current_school_name: str | None
    accommodations_note: str | None
    created_at: datetime
    updated_at: datetime


# ---------- Sharing with a support worker ----------
class GrantAccessRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr


class AccessOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    user_name: str
    access_level: AccessLevel
    granted_at: datetime