"""Tenant root: Organization (cooperative/reseller) and User."""

from __future__ import annotations

from datetime import datetime, time
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, String, Time
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import AlertChannelType, Language, UserRole

if TYPE_CHECKING:
    from app.db.models.billing import Subscription
    from app.db.models.farm import Farm


class Organization(Base, UUIDPkMixin, TimestampMixin):
    """A cooperative / tenant. ``is_reseller`` + ``white_label`` drive packaging."""

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    is_reseller: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    white_label: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    theme: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # white-label branding
    country: Mapped[str] = mapped_column(String(64), default="Kenya", nullable=False)
    timezone: Mapped[str] = mapped_column(String(48), default="Africa/Nairobi", nullable=False)
    contact_email: Mapped[str | None] = mapped_column(String(160), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)

    farms: Mapped[list[Farm]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    users: Mapped[list[User]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    subscriptions: Mapped[list[Subscription]] = relationship(back_populates="organization")


class User(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """Roles: farmer | agronomist | coop_admin | super_admin. Carries channel prefs."""

    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(160), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        enum_column(UserRole), default=UserRole.FARMER, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Channel preferences + quiet hours (local time, evaluated in org timezone).
    preferred_language: Mapped[Language] = mapped_column(
        enum_column(Language), default=Language.EN, nullable=False
    )
    preferred_channel: Mapped[AlertChannelType] = mapped_column(
        enum_column(AlertChannelType), default=AlertChannelType.WHATSAPP, nullable=False
    )
    notify_sms: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_whatsapp: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    notify_ussd: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    quiet_hours_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    quiet_hours_end: Mapped[time | None] = mapped_column(Time, nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="users")
