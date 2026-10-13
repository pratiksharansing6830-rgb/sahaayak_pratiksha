import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.enums import (
    ConfirmationMethod, FollowUpAction, FollowUpStatus, NeedStatus, Priority, Role,
    ServiceCategory,
)


# ---------- Output ----------
class NeedOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    child_id: uuid.UUID
    migration_id: uuid.UUID | None
    category: ServiceCategory
    status: NeedStatus
    need_description: str
    status_explanation: str | None
    next_action: str | None
    assigned_role: Role | None
    due_date: date | None
    closure_reason: str | None
    created_at: datetime
    updated_at: datetime
    is_open: bool = False


class StatusEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    from_status: NeedStatus | None
    to_status: NeedStatus
    changed_by_role: Role | None
    reason: str | None
    created_at: datetime


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    need_id: uuid.UUID
    referral_id: uuid.UUID | None
    action_type: FollowUpAction
    description: str
    assigned_role: Role | None
    priority: Priority
    due_date: date | None
    status: FollowUpStatus
    barrier: str | None
    next_action: str | None
    completed_at: datetime | None
    created_at: datetime
    is_overdue: bool = False


class OutcomeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    outcome: str
    method: ConfirmationMethod
    confirmed_by_role: Role
    provider_verified: bool
    reference_note: str | None
    confirmed_at: datetime


class NeedDetail(NeedOut):
    history: list[StatusEventOut] = Field(default_factory=list)
    follow_ups: list[FollowUpOut] = Field(default_factory=list)
    confirmations: list[OutcomeOut] = Field(default_factory=list)


class AssessResult(BaseModel):
    created_needs: int
    existing_needs: int
    needs: list[NeedOut]


class FollowUpCompleteResult(BaseModel):
    follow_up: FollowUpOut
    need: NeedOut  # returned so the client can see the need is still open


def to_need_out(need) -> NeedOut:
    from app.services.continuity import OPEN_STATUSES

    out = NeedOut.model_validate(need)
    out.is_open = need.status in OPEN_STATUSES
    return out


def to_followup_out(fu) -> FollowUpOut:
    from app.services.continuity import ACTIVE_FOLLOWUP

    out = FollowUpOut.model_validate(fu)
    out.is_overdue = (
        fu.status in ACTIVE_FOLLOWUP and fu.due_date is not None and fu.due_date < date.today()
    )
    return out


# ---------- Input ----------
class NeedStatusChange(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: NeedStatus
    reason: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def closing_needs_a_reason(self):
        if self.status in (NeedStatus.NOT_REQUIRED, NeedStatus.CLOSED):
            if not self.reason or len(self.reason) < 5:
                raise ValueError(
                    "A short reason (at least 5 characters) is required when marking a need "
                    "as not required or closed."
                )
        return self


class ConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    outcome: str = Field(min_length=1, max_length=300)
    method: ConfirmationMethod
    reference_note: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def document_needs_reference(self):
        if self.method == ConfirmationMethod.DOCUMENT_SEEN and not self.reference_note:
            raise ValueError("Say which document was seen (reference_note).")
        return self


class FollowUpCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action_type: FollowUpAction
    description: str = Field(min_length=1, max_length=500)
    priority: Priority = Priority.MEDIUM
    due_date: date | None = None

    @field_validator("due_date")
    @classmethod
    def not_past(cls, v):
        if v is not None and v < date.today():
            raise ValueError("Due date cannot be in the past.")
        return v


class FollowUpUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str | None = Field(default=None, min_length=1, max_length=500)
    priority: Priority | None = None
    due_date: date | None = None
    next_action: str | None = Field(default=None, max_length=500)
    barrier: str | None = Field(default=None, max_length=300)
    status: Literal["IN_PROGRESS"] | None = None

    @field_validator("due_date")
    @classmethod
    def not_past(cls, v):
        if v is not None and v < date.today():
            raise ValueError("Due date cannot be in the past.")
        return v

    @model_validator(mode="after")
    def required_not_null(self):
        for f in ("description", "priority", "status"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class FollowUpComplete(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    next_action: str | None = Field(default=None, max_length=500)


# ---------- Continuity summary ----------
class ConfirmationBrief(BaseModel):
    method: ConfirmationMethod
    provider_verified: bool
    confirmed_by_role: Role
    confirmed_at: datetime


class SummaryNeed(BaseModel):
    need_id: uuid.UUID
    migration_id: uuid.UUID | None
    category: ServiceCategory
    status: NeedStatus
    is_open: bool
    explanation: str
    next_action: str | None
    due_date: date | None
    overdue: bool
    confirmation: ConfirmationBrief | None


class SummaryChild(BaseModel):
    child_id: uuid.UUID
    child_name: str
    needs: list[SummaryNeed]
    not_assessed_categories: list[ServiceCategory]  # no record yet: NOT the same as "no need"


class UnresolvedItem(BaseModel):
    need_id: uuid.UUID
    child_id: uuid.UUID
    child_name: str
    category: ServiceCategory
    status: NeedStatus
    need_description: str
    why: str
    next_action: str | None
    due_date: date | None
    overdue: bool


class SummaryTotals(BaseModel):
    open: int
    overdue: int
    support_confirmed_by_provider: int
    support_confirmed_by_family: int
    not_required: int
    closed: int
    not_assessed: int


class ContinuitySummary(BaseModel):
    family_id: uuid.UUID
    generated_on: date
    totals: SummaryTotals
    children: list[SummaryChild]
    unresolved: list[UnresolvedItem]