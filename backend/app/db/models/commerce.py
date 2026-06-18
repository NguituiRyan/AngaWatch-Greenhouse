"""Commerce scaffolding: invoicing, input marketplace, market linkage, dryers (Wave 1+)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import InvoiceStatus, ListingStatus, OrderStatus

if TYPE_CHECKING:
    from app.db.models.billing import Subscription


class Invoice(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "invoices"

    number: Mapped[str] = mapped_column(String(40), unique=True, index=True, nullable=False)
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("buyers.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[InvoiceStatus] = mapped_column(
        enum_column(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    subtotal: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    tax: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    total: Mapped[float] = mapped_column(Numeric(12, 2), default=0, nullable=False)
    line_items: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    subscription: Mapped[Subscription | None] = relationship()


class InputProduct(Base, UUIDPkMixin, TimestampMixin):
    """Catalog item (seeds, fertilizer, fungicide). ``org_id`` null => shared catalog."""

    __tablename__ = "input_products"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str | None] = mapped_column(String(80), nullable=True)
    sku: Mapped[str | None] = mapped_column(String(60), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    supplier: Mapped[str | None] = mapped_column(String(160), nullable=True)


class InputOrder(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "input_orders"

    product_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("input_products.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    total: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[OrderStatus] = mapped_column(
        enum_column(OrderStatus), default=OrderStatus.PENDING, nullable=False
    )
    ordered_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    ordered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fulfilled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Buyer(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "buyers"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    buyer_type: Mapped[str | None] = mapped_column(
        String(60), nullable=True
    )  # exporter|local|processor
    contact: Mapped[str | None] = mapped_column(String(120), nullable=True)
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)


class MarketListing(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "market_listings"

    crop_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="SET NULL"), nullable=True
    )
    buyer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("buyers.id", ondelete="SET NULL"), nullable=True
    )
    produce: Mapped[str] = mapped_column(String(80), nullable=False)
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str | None] = mapped_column(String(24), nullable=True)
    price_per_kg: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[ListingStatus] = mapped_column(
        enum_column(ListingStatus), default=ListingStatus.OPEN, nullable=False
    )
    listed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DryerUnit(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """Solar dryer / post-harvest unit — reuses the sensing + alerting stack."""

    __tablename__ = "dryer_units"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    capacity_kg: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="idle", nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    install_date: Mapped[date | None] = mapped_column(Date, nullable=True)
