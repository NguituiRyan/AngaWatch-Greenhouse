"""Time-series telemetry. Stored in a TimescaleDB hypertable (partitioned on ``time``).

The hypertable + retention/compression policies are created by the Alembic
migration ``0002_timescale_hypertable`` (kept in SQL so the schema lives with the
app). The composite PK ``(device_id, time)`` makes ingestion idempotent: duplicate
telemetry is rejected with ``ON CONFLICT DO NOTHING``.

``org_id`` and ``greenhouse_id`` are denormalized here so tenant-scoped and
per-greenhouse window queries never need a join back through ``devices``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.device import Device


class Reading(Base):
    __tablename__ = "readings"
    __table_args__ = (
        Index("ix_readings_greenhouse_time", "greenhouse_id", "time"),
        Index("ix_readings_org_time", "org_id", "time"),
    )

    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("devices.id", ondelete="CASCADE"), primary_key=True
    )
    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)

    org_id: Mapped[uuid.UUID] = mapped_column(nullable=False)
    greenhouse_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    # ---- Microclimate ----
    air_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    leaf_wetness: Mapped[float | None] = mapped_column(Float, nullable=True)
    ppfd: Mapped[float | None] = mapped_column(Float, nullable=True)
    co2_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ---- Soil ----
    soil_moisture_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    soil_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    npk_n_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    npk_p_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)
    npk_k_ppm: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ---- Water ----
    water_flow_l_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    water_flow_l_per_min: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ---- Pest ----
    pheromone_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # ---- Device health ----
    battery_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)

    ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device: Mapped[Device] = relationship(back_populates="readings")
