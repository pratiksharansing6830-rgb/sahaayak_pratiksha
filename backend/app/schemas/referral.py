import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.enums import (
    ContactMethod, ContactResult, ProviderResponseType, ReferralStatus, VerificationStatus,
)

REFERRAL_TEXT: dict[ReferralStatus, str] = {
    ReferralStatus.RECORDED: "Recorded by the family. The provider has not responded yet.",
    ReferralStatus.ACCEPTED: "The provider accepted the referral. This does not mean support has been received.",
    ReferralStatus.INFO_REQUESTED: "The provider needs more information before they can help.",
    ReferralStatus.DECLINED: "The provider declined. Try another service.",
    ReferralStatus.NO_RESPONSE: "The provider has not responded. Follow up or try another service.",
    ReferralStatus.WITHDRAWN: "Withdrawn by the family.",
}


class ReferralCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service_listing_id: uuid.UUID
    note: str | None = Field(default=None, max_length=500)


class ProviderResponseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    response_type: ProviderResponseType
    message: str | None
    barrier: str | None
    responded_at: datetime


class ReferralOut(BaseModel):
    id: uuid.UUID
    need_id: uuid.UUID
    service_listing_id: uuid.UUID | None
    service_name: str | None
    service_verification_status: VerificationStatus | None
    status: ReferralStatus
    plain_status: str
    referred_at: datetime
    note: str | None
    provider_responses: list[ProviderResponseOut]


class ContactAttemptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    service_listing_id: uuid.UUID | None = None
    referral_id: uuid.UUID | None = None
    method: ContactMethod
    result: ContactResult
    note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def needs_a_target(self):
        if self.service_listing_id is None and self.referral_id is None:
            raise ValueError("Say which service (service_listing_id) or referral (referral_id) was contacted.")
        return self


class ContactAttemptOut(BaseModel):
    id: uuid.UUID
    need_id: uuid.UUID
    referral_id: uuid.UUID | None
    service_listing_id: uuid.UUID | None
    service_name: str | None
    method: ContactMethod
    result: ContactResult
    attempted_at: datetime
    note: str | None