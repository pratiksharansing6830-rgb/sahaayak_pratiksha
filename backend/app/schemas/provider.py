import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ContactMethod, ContactResult, EducationStatus, ReferralStatus, ServiceCategory,
)
from app.schemas.referral import ProviderResponseOut


class ProviderRespond(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    # SERVICE_PROVIDED is deliberately not allowed here: it only happens via confirm-outcome.
    response_type: Literal["RECEIVED", "ACCEPTED", "INFO_REQUESTED", "DECLINED"]
    message: str | None = Field(default=None, max_length=500)
    barrier: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def rules(self):
        if self.response_type == "INFO_REQUESTED" and not self.message:
            raise ValueError("Say what information is needed (message).")
        if self.response_type == "DECLINED" and not self.barrier:
            raise ValueError("Give the reason (barrier) so the family can look for another service.")
        return self


class ProviderConfirm(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    outcome: str = Field(min_length=1, max_length=300)
    reference_note: str | None = Field(default=None, max_length=500)


class FamilyMessageOut(BaseModel):
    method: ContactMethod
    result: ContactResult
    note: str | None
    attempted_at: datetime


class ProviderReferralOut(BaseModel):
    id: uuid.UUID
    status: ReferralStatus
    plain_status: str
    referred_at: datetime
    service_name: str
    category: ServiceCategory
    need_description: str
    need_is_open: bool
    child_name: str
    child_age_years: int | None
    education_status: EducationStatus | None      # education referrals only
    current_school_name: str | None               # education referrals only
    accommodations_note: str | None               # inclusion referrals only
    destination_district: str | None
    planned_date: date | None
    preferred_language: str
    family_contact_phone: str | None              # only after the provider accepts
    referral_note: str | None
    responses: list[ProviderResponseOut]
    family_messages: list[FamilyMessageOut]


class ProviderDashboard(BaseModel):
    organization_id: uuid.UUID
    by_status: dict[str, int]
    awaiting_response: int
    info_requested: int
    accepted_awaiting_outcome: int
    confirmed_outcomes: int