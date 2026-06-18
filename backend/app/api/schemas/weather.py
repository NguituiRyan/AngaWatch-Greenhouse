"""Weather DTOs: latest observation + forecast bundle for a farm."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.api.schemas.common import ORMModel


class WeatherObservationOut(ORMModel):
    id: uuid.UUID
    farm_id: uuid.UUID
    observed_at: datetime
    source: str
    air_temp_c: float | None = None
    rh_pct: float | None = None
    wind_speed_ms: float | None = None
    rainfall_mm: float | None = None
    clouds_pct: float | None = None


class WeatherForecastOut(ORMModel):
    id: uuid.UUID
    farm_id: uuid.UUID
    issued_at: datetime
    forecast_for: datetime
    source: str
    air_temp_c: float | None = None
    rh_pct: float | None = None
    rain_prob: float | None = None
    rainfall_mm: float | None = None
    wind_speed_ms: float | None = None


class FarmWeatherOut(BaseModel):
    """Combined view: the latest observation plus upcoming forecasts."""

    farm_id: uuid.UUID
    observation: WeatherObservationOut | None = None
    forecasts: list[WeatherForecastOut] = []
