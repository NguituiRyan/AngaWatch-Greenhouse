"""Farm records: generic journal + spray/harvest/expense logs (Wave 1 features, wired now)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, DateTime, Float, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.crop import CropCycle


class FarmRecord(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """Generic, typed journal entry; specialised logs below cover the common cases."""

    __tablename__ = "farm_records"

    greenhouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="SET NULL"), nullable=True
    )
    crop_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="SET NULL"), nullable=True
    )
    record_type: Mapped[str] = mapped_column(String(60), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class SprayLog(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "spray_logs"

    crop_cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    product: Mapped[str] = mapped_column(String(120), nullable=False)
    active_ingredient: Mapped[str | None] = mapped_column(String(120), nullable=True)
    dose: Mapped[float | None] = mapped_column(Float, nullable=True)
    dose_unit: Mapped[str | None] = mapped_column(String(24), nullable=True)
    target: Mapped[str | None] = mapped_column(String(120), nullable=True)  # pest/disease
    phi_days: Mapped[int | None] = mapped_column(
        Numeric(4, 0), nullable=True
    )  # pre-harvest interval
    applied_at: Mapped[date] = mapped_column(Date, nullable=False)
    applied_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    crop_cycle: Mapped[CropCycle] = relationship(back_populates="spray_logs")


class HarvestLog(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "harvest_logs"

    crop_cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    quantity_kg: Mapped[float] = mapped_column(Float, nullable=False)
    grade: Mapped[str | None] = mapped_column(String(24), nullable=True)
    harvested_at: Mapped[date] = mapped_column(Date, nullable=False)
    harvested_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    crop_cycle: Mapped[CropCycle] = relationship(back_populates="harvest_logs")


class Expense(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "expenses"

    farm_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("farms.id", ondelete="SET NULL"), nullable=True
    )
    crop_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="SET NULL"), nullable=True
    )
    category: Mapped[str] = mapped_column(String(60), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    incurred_at: Mapped[date] = mapped_column(Date, nullable=False)
