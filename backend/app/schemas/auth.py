import uuid

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import Role


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # unknown fields (e.g. "role") are rejected

    email: EmailStr
    password: str = Field(min_length=8, max_length=72)  # bcrypt limit is 72
    full_name: str = Field(min_length=1, max_length=200)
    phone: str | None = Field(default=None, max_length=20)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    phone: str | None
    role: Role
    organization_id: uuid.UUID | None
    is_active: bool


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut