import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.enums import OrgType, Role

PROVIDER_ROLES = {Role.SCHOOL, Role.HEALTHCARE, Role.NGO}


class OrganizationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    org_type: OrgType
    district: str | None = Field(default=None, max_length=100)
    state: str | None = Field(default=None, max_length=100)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    org_type: OrgType
    district: str | None
    state: str | None
    is_active: bool


class AdminCreateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)
    role: Role
    organization_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def provider_needs_organization(self):
        if self.role in PROVIDER_ROLES and self.organization_id is None:
            raise ValueError("organization_id is required for school, healthcare and NGO users")
        return self


class AdminUpdateUser(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Role | None = None
    is_active: bool | None = None
    organization_id: uuid.UUID | None = None


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_role: Role | None
    action: str
    entity_type: str
    entity_id: uuid.UUID | None
    from_value: str | None
    to_value: str | None
    reason: str | None
    created_at: datetime