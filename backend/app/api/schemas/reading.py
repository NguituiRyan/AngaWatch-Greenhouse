"""Reading DTOs: the timeseries point view and the HTTP ingest acknowledgement."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from app.api.schemas.common import ORMModel


class ReadingOut(ORMModel):
    """One telemetry row. ``time`` is the device timestamp (UTC)."""

    device_id: uuid.UUID
    time: datetime
    greenhouse_id: uuid.UUID | None = None

    air_temp_c: float | None = None
    rh_pct: float | None = None
    leaf_wetness: float | None = None
    ppfd: float | None = None
    co2_ppm: float | None = None

    soil_moisture_pct: float | None = None
    soil_temp_c: float | None = None
    npk_n_ppm: float | None = None
    npk_p_ppm: float | None = None
    npk_k_ppm: float | None = None

    water_flow_l_total: float | None = None
    water_flow_l_per_min: float | None = None

    pheromone_count: int | None = None

    battery_v: float | None = None
    rssi: int | None = None


class IngestResponse(BaseModel):
    """Result of an HTTP ``/ingest`` call (mirrors the writer's bool return)."""

    stored: bool
