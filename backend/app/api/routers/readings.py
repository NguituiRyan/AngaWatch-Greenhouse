"""Reading timeseries + HTTP telemetry ingest.

``GET /greenhouses/{id}/readings`` returns a window of telemetry for a greenhouse
the caller owns. ``POST /ingest`` accepts a single :class:`TelemetryIn` payload
over HTTP (an alternative to MQTT) and writes it with the same idempotency and
denormalization rules as :func:`app.ingestion.writer.persist_reading`, but on the
async request session.
"""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import Scope
from app.api.schemas.reading import IngestResponse, ReadingOut
from app.core.logging import get_logger
from app.db.models import Device, Greenhouse, Reading
from app.db.models.common import DeviceStatus
from app.schemas.telemetry import TelemetryIn

log = get_logger(__name__)

router = APIRouter(tags=["readings"])

# Telemetry value columns selectable via ``?metric=``. Excludes PK/denorm columns.
_METRIC_COLUMNS: frozenset[str] = frozenset(
    {
        "air_temp_c",
        "rh_pct",
        "leaf_wetness",
        "ppfd",
        "co2_ppm",
        "soil_moisture_pct",
        "soil_temp_c",
        "npk_n_ppm",
        "npk_p_ppm",
        "npk_k_ppm",
        "water_flow_l_total",
        "water_flow_l_per_min",
        "pheromone_count",
        "battery_v",
        "rssi",
    }
)


async def _assert_greenhouse_in_org(scope: Scope, greenhouse_id: uuid.UUID) -> Greenhouse:
    gh = await scope.db.scalar(
        select(Greenhouse).where(Greenhouse.id == greenhouse_id, Greenhouse.org_id == scope.org_id)
    )
    if gh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    return gh


@router.get("/greenhouses/{greenhouse_id}/readings", response_model=list[ReadingOut])
async def list_readings(
    greenhouse_id: uuid.UUID,
    scope: Scope,
    metric: str | None = Query(None, description="Restrict to a single metric column"),
    start: datetime | None = Query(None, description="Inclusive lower bound (UTC)"),
    end: datetime | None = Query(None, description="Inclusive upper bound (UTC)"),
    limit: int = Query(500, ge=1, le=5000),
) -> list[Reading]:
    """Return a window of telemetry for an owned greenhouse (newest first)."""
    await _assert_greenhouse_in_org(scope, greenhouse_id)

    if metric is not None and metric not in _METRIC_COLUMNS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unknown metric '{metric}'"
        )

    stmt = select(Reading).where(
        Reading.org_id == scope.org_id,
        Reading.greenhouse_id == greenhouse_id,
    )
    if start is not None:
        stmt = stmt.where(Reading.time >= start)
    if end is not None:
        stmt = stmt.where(Reading.time <= end)
    if metric is not None:
        stmt = stmt.where(getattr(Reading, metric).is_not(None))

    stmt = stmt.order_by(Reading.time.desc()).limit(limit)
    rows = await scope.db.scalars(stmt)
    return list(rows)


@router.get("/greenhouses/{greenhouse_id}/readings/latest", response_model=ReadingOut)
async def latest_reading(greenhouse_id: uuid.UUID, scope: Scope) -> Reading:
    """Return the single most recent reading for an owned greenhouse."""
    await _assert_greenhouse_in_org(scope, greenhouse_id)
    reading = await scope.db.scalar(
        select(Reading)
        .where(Reading.org_id == scope.org_id, Reading.greenhouse_id == greenhouse_id)
        .order_by(Reading.time.desc())
        .limit(1)
    )
    if reading is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No readings for this greenhouse"
        )
    return reading


@router.post("/ingest", response_model=IngestResponse)
async def ingest(telem: TelemetryIn, scope: Scope) -> IngestResponse:
    """HTTP telemetry ingest for the caller's org.

    Resolves the device by ``device_uid``, enforces tenant ownership, and writes
    an idempotent reading with denormalized ``org_id``/``greenhouse_id``. Mirrors
    :func:`app.ingestion.writer.persist_reading` on the async session. Returns
    ``stored=False`` for unknown device, tenant mismatch, or duplicate timestamp.
    """
    device = await scope.db.scalar(
        select(Device).where(Device.device_uid == telem.device_id, Device.org_id == scope.org_id)
    )
    if device is None:
        log.warning("ingest.unknown_device", device_uid=telem.device_id)
        return IngestResponse(stored=False)

    now = datetime.now(UTC)
    reading = Reading(
        device_id=device.id,
        time=telem.ts,
        org_id=device.org_id,
        greenhouse_id=device.greenhouse_id,
        ingested_at=now,
        air_temp_c=telem.air_temp_c,
        rh_pct=telem.rh_pct,
        leaf_wetness=telem.leaf_wetness,
        ppfd=telem.ppfd,
        co2_ppm=telem.co2_ppm,
        soil_moisture_pct=telem.soil_moisture_pct,
        soil_temp_c=telem.soil_temp_c,
        npk_n_ppm=telem.npk_n_ppm,
        npk_p_ppm=telem.npk_p_ppm,
        npk_k_ppm=telem.npk_k_ppm,
        water_flow_l_total=telem.water_flow_l_total,
        water_flow_l_per_min=telem.water_flow_l_per_min,
        pheromone_count=telem.pheromone_count,
        battery_v=telem.battery_v,
        rssi=telem.rssi,
    )
    scope.db.add(reading)

    device.last_seen_at = telem.ts
    if telem.battery_v is not None:
        device.last_battery_v = telem.battery_v
    if telem.rssi is not None:
        device.last_rssi = telem.rssi
    if device.status != DeviceStatus.ACTIVE:
        device.status = DeviceStatus.ACTIVE

    try:
        await scope.db.flush()
    except IntegrityError:
        await scope.db.rollback()
        log.debug("ingest.duplicate", device_uid=telem.device_id, ts=telem.ts.isoformat())
        return IngestResponse(stored=False)

    log.info("ingest.stored", device_uid=telem.device_id, ts=telem.ts.isoformat())
    return IngestResponse(stored=True)
