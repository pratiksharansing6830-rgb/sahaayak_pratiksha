import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col
from app.models.enums import ServiceCategory, VerificationStatus


class ServiceListing(Base, UUIDPk, TimestampMixin):
    """Directory entry. A listing is only a *potentially suitable* service."""

    __tablename__ = "service_listings"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[ServiceCategory] = enum_col(
        ServiceCategory, nullable=False, index=True
    )
    description: Mapped[str | None] = mapped_column(Text)
    address: Mapped[str | None] = mapped_column(String(300))
    district: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    state: Mapped[str] = mapped_column(String(100), nullable=False)
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    coordinates_approximate: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    contact_phone: Mapped[str | None] = mapped_column(String(30))
    operating_hours: Mapped[str | None] = mapped_column(String(200))
    data_source: Mapped[str | None] = mapped_column(String(200))
    verification_status: Mapped[VerificationStatus] = enum_col(
        VerificationStatus,
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default="UNVERIFIED",
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")