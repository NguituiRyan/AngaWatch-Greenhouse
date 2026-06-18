"""Billing: subscription state machine + installments + M-Pesa payments."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import (
    PaymentProviderType,
    PaymentStatus,
    PlanType,
    SubscriptionStatus,
)

if TYPE_CHECKING:
    from app.db.models.organization import Organization


class Subscription(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """plan_type: subscription | rent_to_own | daas. Gates premium features."""

    __tablename__ = "subscriptions"

    farm_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("farms.id", ondelete="SET NULL"), nullable=True
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    plan_type: Mapped[PlanType] = mapped_column(
        enum_column(PlanType), default=PlanType.SUBSCRIPTION, nullable=False
    )
    plan_name: Mapped[str] = mapped_column(String(80), default="standard", nullable=False)
    status: Mapped[SubscriptionStatus] = mapped_column(
        enum_column(SubscriptionStatus), default=SubscriptionStatus.TRIAL, nullable=False
    )
    price: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    billing_interval: Mapped[str] = mapped_column(String(20), default="monthly", nullable=False)
    # Feature flags this plan unlocks (predictive_alerts, history, automation...).
    features: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    trial_ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    current_period_start: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    current_period_end: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="subscriptions")
    installments: Mapped[list[Installment]] = relationship(
        back_populates="subscription", cascade="all, delete-orphan"
    )
    payments: Mapped[list[Payment]] = relationship(back_populates="subscription")


class Installment(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """Rent-to-own schedule line."""

    __tablename__ = "installments"

    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    due_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    paid: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )

    subscription: Mapped[Subscription] = relationship(back_populates="installments")


class Payment(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """An M-Pesa STK payment attempt and its reconciliation state."""

    __tablename__ = "payments"

    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    installment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("installments.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[PaymentProviderType] = mapped_column(
        enum_column(PaymentProviderType), default=PaymentProviderType.MPESA, nullable=False
    )
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        enum_column(PaymentStatus), default=PaymentStatus.PENDING, nullable=False
    )
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    account_reference: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # M-Pesa STK correlation ids + raw callback for reconciliation/audit.
    merchant_request_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    checkout_request_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    mpesa_receipt: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    result_desc: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_callback: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    initiated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription: Mapped[Subscription | None] = relationship(back_populates="payments")
