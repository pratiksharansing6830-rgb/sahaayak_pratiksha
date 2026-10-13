import uuid
from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint, DateTime, ForeignKey, SmallInteger, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col
from app.models.enums import AccessLevel, EducationStatus


class Family(Base, UUIDPk, TimestampMixin):
    __tablename__ = "families"

    household_name: Mapped[str] = mapped_column(String(200), nullable=False)
    primary_caregiver_name: Mapped[str] = mapped_column(String(200), nullable=False)
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    origin_district: Mapped[str | None] = mapped_column(String(100), index=True)
    origin_state: Mapped[str | None] = mapped_column(String(100))
    preferred_language: Mapped[str] = mapped_column(
        String(20), default="en", server_default="en"
    )
    consent_given_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    privacy_notice_version: Mapped[str | None] = mapped_column(String(20))
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    children: Mapped[list["Child"]] = relationship(back_populates="family")


class FamilyAccess(Base, UUIDPk, TimestampMixin):
    """Who may see a family's records (owner, members, assigned support workers)."""

    __tablename__ = "family_access"
    __table_args__ = (UniqueConstraint("family_id", "user_id", name="uq_family_user"),)

    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id"), index=True, nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    access_level: Mapped[AccessLevel] = enum_col(AccessLevel, nullable=False)
    granted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Child(Base, UUIDPk, TimestampMixin):
    __tablename__ = "children"
    __table_args__ = (
        CheckConstraint(
            "approx_age_years IS NULL OR (approx_age_years >= 0 AND approx_age_years <= 18)",
            name="ck_child_age_range",
        ),
    )

    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id"), index=True, nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    date_of_birth: Mapped[date | None] = mapped_column()
    approx_age_years: Mapped[int | None] = mapped_column(SmallInteger)
    education_status: Mapped[EducationStatus] = enum_col(
        EducationStatus,
        nullable=False,
        default=EducationStatus.UNKNOWN,
        server_default="UNKNOWN",
    )
    current_school_name: Mapped[str | None] = mapped_column(String(200))
    accommodations_note: Mapped[str | None] = mapped_column(Text)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    family: Mapped["Family"] = relationship(back_populates="children")