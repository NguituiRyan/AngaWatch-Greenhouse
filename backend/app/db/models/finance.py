"""Finance & compliance scaffolding: financing/credit-scoring + traceability/export."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.crop import CropCycle


class FinancingProfile(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "financing_profiles"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    requested_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="KES", nullable=False)
    purpose: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(40), default="draft", nullable=False)


class CreditScore(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """Derived from farm activity (yield consistency, payment history, sensor uptime)."""

    __tablename__ = "credit_scores"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    band: Mapped[str | None] = mapped_column(String(24), nullable=True)  # A|B|C|D
    factors: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    computed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TraceabilityRecord(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """Links a CropCycle to its spray + harvest logs for GlobalGAP / organic export."""

    __tablename__ = "traceability_records"

    crop_cycle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    standard: Mapped[str] = mapped_column(String(40), default="globalgap", nullable=False)
    spray_log_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    harvest_log_ids: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    export_ready: Mapped[bool] = mapped_column(default=False, nullable=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    crop_cycle: Mapped[CropCycle] = relationship()
