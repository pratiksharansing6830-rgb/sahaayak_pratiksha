import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col
from app.models.enums import MigrationStatus


class Migration(Base, UUIDPk, TimestampMixin):
    __tablename__ = "family_migrations"
    __table_args__ = (
        CheckConstraint(
            "status <> 'COMPLETED' OR actual_date IS NOT NULL",
            name="ck_completed_needs_actual_date",
        ),
    )

    family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("families.id"), index=True, nullable=False
    )
    origin_district: Mapped[str] = mapped_column(String(100), nullable=False)
    origin_state: Mapped[str] = mapped_column(String(100), nullable=False)
    destination_district: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    destination_state: Mapped[str] = mapped_column(String(100), nullable=False)
    planned_date: Mapped[date | None] = mapped_column()
    actual_date: Mapped[date | None] = mapped_column()
    status: Mapped[MigrationStatus] = enum_col(
        MigrationStatus,
        nullable=False,
        default=MigrationStatus.PLANNED,
        server_default="PLANNED",
        index=True,
    )
    work_category: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)