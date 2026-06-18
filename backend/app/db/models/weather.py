"""Weather observations + forecasts per farm location (fused into blight/water models)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.farm import Farm


class WeatherObservation(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "weather_observations"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    observed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    air_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    clouds_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    farm: Mapped[Farm] = relationship()


class WeatherForecast(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "weather_forecasts"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    forecast_for: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    air_temp_c: Mapped[float | None] = mapped_column(Float, nullable=True)
    rh_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    rain_prob: Mapped[float | None] = mapped_column(Float, nullable=True)
    rainfall_mm: Mapped[float | None] = mapped_column(Float, nullable=True)
    wind_speed_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    farm: Mapped[Farm] = relationship()
