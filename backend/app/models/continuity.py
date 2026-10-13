import uuid
from datetime import date, datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Index, String, Text, text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPk, enum_col
from app.models.enums import (
    ConfirmationMethod, ContactMethod, ContactResult, FollowUpAction, FollowUpStatus,
    NeedStatus, Priority, ProviderResponseType, ReferralStatus, Role, ServiceCategory,
)


class ServiceNeed(Base, UUIDPk, TimestampMixin):
    """One continuity record: one child, one service category, one migration context."""

    __tablename__ = "service_needs"
    __table_args__ = (
        # No duplicate needs, even if refresh logic runs twice.
        Index(
            "uq_need_child_cat_migration",
            "child_id", "category", "migration_id",
            unique=True,
            postgresql_where=text("migration_id IS NOT NULL"),
        ),
        Index(
            "uq_need_child_cat_no_migration",
            "child_id", "category",
            unique=True,
            postgresql_where=text("migration_id IS NULL"),
        ),
    )

    child_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("children.id"), index=True, nullable=False
    )
    migration_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("family_migrations.id"), index=True
    )
    category: Mapped[ServiceCategory] = enum_col(
        ServiceCategory, nullable=False, index=True
    )
    status: Mapped[NeedStatus] = enum_col(
        NeedStatus,
        nullable=False,
        default=NeedStatus.NEEDS_ASSESSMENT,
        server_default="NEEDS_ASSESSMENT",
        index=True,
    )
    need_description: Mapped[str] = mapped_column(Text, nullable=False)
    status_explanation: Mapped[str | None] = mapped_column(Text)
    next_action: Mapped[str | None] = mapped_column(Text)
    assigned_role: Mapped[Role | None] = enum_col(Role)
    due_date: Mapped[date | None] = mapped_column()
    closure_reason: Mapped[str | None] = mapped_column(Text)  # for NOT_REQUIRED / CLOSED


class NeedStatusEvent(Base, UUIDPk):
    """Append-only history of every status change."""

    __tablename__ = "need_status_events"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_needs.id"), index=True, nullable=False
    )
    from_status: Mapped[NeedStatus | None] = enum_col(NeedStatus)
    to_status: Mapped[NeedStatus] = enum_col(NeedStatus, nullable=False)
    changed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    changed_by_role: Mapped[Role | None] = enum_col(Role)
    reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class Referral(Base, UUIDPk, TimestampMixin):
    __tablename__ = "referrals"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_needs.id"), index=True, nullable=False
    )
    service_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_listings.id"), index=True
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    status: Mapped[ReferralStatus] = enum_col(
        ReferralStatus,
        nullable=False,
        default=ReferralStatus.RECORDED,
        server_default="RECORDED",
        index=True,
    )
    referred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)


class ContactAttempt(Base, UUIDPk):
    __tablename__ = "contact_attempts"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_needs.id"), index=True, nullable=False
    )
    referral_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("referrals.id"), index=True
    )
    service_listing_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("service_listings.id")
    )
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    method: Mapped[ContactMethod] = enum_col(ContactMethod, nullable=False)
    result: Mapped[ContactResult] = enum_col(ContactResult, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    note: Mapped[str | None] = mapped_column(Text)


class ProviderResponse(Base, UUIDPk):
    __tablename__ = "provider_responses"

    referral_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("referrals.id"), index=True, nullable=False
    )
    responder_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    response_type: Mapped[ProviderResponseType] = enum_col(
        ProviderResponseType, nullable=False
    )
    message: Mapped[str | None] = mapped_column(Text)
    barrier: Mapped[str | None] = mapped_column(String(300))
    responded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )


class FollowUp(Base, UUIDPk, TimestampMixin):
    __tablename__ = "follow_ups"
    __table_args__ = (
        # At most one ACTIVE follow-up per need + action type.
        Index(
            "uq_followup_active_per_need_action",
            "need_id", "action_type",
            unique=True,
            postgresql_where=text("status IN ('OPEN', 'IN_PROGRESS')"),
        ),
    )

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_needs.id"), index=True, nullable=False
    )
    referral_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("referrals.id"))
    action_type: Mapped[FollowUpAction] = enum_col(FollowUpAction, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    assigned_role: Mapped[Role | None] = enum_col(Role)
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    priority: Mapped[Priority] = enum_col(
        Priority, nullable=False, default=Priority.MEDIUM, server_default="MEDIUM"
    )
    due_date: Mapped[date | None] = mapped_column(index=True)
    status: Mapped[FollowUpStatus] = enum_col(
        FollowUpStatus,
        nullable=False,
        default=FollowUpStatus.OPEN,
        server_default="OPEN",
        index=True,
    )
    barrier: Mapped[str | None] = mapped_column(String(300))
    next_action: Mapped[str | None] = mapped_column(Text)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OutcomeConfirmation(Base, UUIDPk):
    """Evidence that support was actually received. Only created via the confirm workflow."""

    __tablename__ = "outcome_confirmations"

    need_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("service_needs.id"), index=True, nullable=False
    )
    referral_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("referrals.id"))
    outcome: Mapped[str] = mapped_column(String(300), nullable=False)
    method: Mapped[ConfirmationMethod] = enum_col(ConfirmationMethod, nullable=False)
    confirmed_by_user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), nullable=False
    )
    confirmed_by_role: Mapped[Role] = enum_col(Role, nullable=False)
    provider_verified: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    reference_note: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )