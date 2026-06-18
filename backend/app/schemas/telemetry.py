"""The telemetry contract. Nodes publish this JSON to ``farm/{org_id}/{device_id}/telemetry``.

Validation here is the ingestion gate: physically impossible values are rejected
(raising ``ValidationError``); missing optional sensors are allowed as ``None``.
``ts`` accepts epoch seconds, epoch millis, or ISO-8601 and is normalized to an
aware UTC datetime so ingestion + idempotency keys are timezone-safe.
"""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TelemetryIn(BaseModel):
    """One reading from one node. Mirrors the firmware payload exactly."""

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    device_id: str = Field(..., min_length=1, max_length=80)
    ts: datetime

    # ---- Microclimate ----
    air_temp_c: float | None = Field(None, ge=-40, le=80)
    rh_pct: float | None = Field(None, ge=0, le=100)
    leaf_wetness: float | None = Field(None, ge=0, le=100)
    ppfd: float | None = Field(None, ge=0, le=4000)
    co2_ppm: float | None = Field(None, ge=0, le=10000)

    # ---- Soil ----
    soil_moisture_pct: float | None = Field(None, ge=0, le=100)
    soil_temp_c: float | None = Field(None, ge=-40, le=80)
    npk_n_ppm: float | None = Field(None, ge=0, le=10000)
    npk_p_ppm: float | None = Field(None, ge=0, le=10000)
    npk_k_ppm: float | None = Field(None, ge=0, le=10000)

    # ---- Water ----
    water_flow_l_total: float | None = Field(None, ge=0)
    water_flow_l_per_min: float | None = Field(None, ge=0, le=10000)

    # ---- Pest ----
    pheromone_count: int | None = Field(None, ge=0, le=100000)

    # ---- Device health ----
    battery_v: float | None = Field(None, ge=0, le=15)
    rssi: int | None = Field(None, ge=-150, le=0)

    @field_validator("ts", mode="before")
    @classmethod
    def _parse_ts(cls, v: object) -> object:
        if isinstance(v, int | float):
            # Heuristic: values > 1e12 are epoch millis.
            seconds = v / 1000 if v > 1_000_000_000_000 else v
            return datetime.fromtimestamp(seconds, tz=UTC)
        if isinstance(v, str) and v.replace(".", "", 1).isdigit():
            seconds = float(v)
            seconds = seconds / 1000 if seconds > 1_000_000_000_000 else seconds
            return datetime.fromtimestamp(seconds, tz=UTC)
        return v

    @field_validator("ts")
    @classmethod
    def _ensure_utc(cls, v: datetime) -> datetime:
        return v.astimezone(UTC) if v.tzinfo else v.replace(tzinfo=UTC)


class TelemetryBatch(BaseModel):
    """Gateway store-and-forward batches multiple readings to save bandwidth."""

    model_config = ConfigDict(extra="ignore")

    org_id: str | None = None
    readings: list[TelemetryIn]
