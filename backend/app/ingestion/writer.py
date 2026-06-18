"""Persist validated telemetry into the ``readings`` hypertable.

The writer is the boundary between the wire format (:class:`TelemetryIn`) and the
ORM. It is **sync** (called from the MQTT consumer and from Celery), idempotent
(duplicate ``(device_id, time)`` is a no-op), and tenant-safe (``org_id`` is
denormalized onto every reading so window queries never join back through
``devices``).

Idempotency is implemented portably: the composite PK ``(device_id, time)``
raises an :class:`IntegrityError` on a duplicate insert on both PostgreSQL and
SQLite, which we catch, roll back, and report as ``False``. This avoids relying
on dialect-specific ``ON CONFLICT`` so the same code path is exercised by the
SQLite-backed tests and the Timescale-backed deployment.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.logging import get_logger
from app.db.models import Device, Reading
from app.db.models.common import DeviceStatus

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

    from app.schemas.telemetry import TelemetryIn

logger = get_logger(__name__)

# Telemetry fields copied verbatim from :class:`TelemetryIn` onto :class:`Reading`.
# ``device_id``/``ts`` map to the PK columns and are handled separately.
_READING_FIELDS: tuple[str, ...] = (
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
)


def resolve_device(session: Session, device_uid: str) -> Device | None:
    """Look up a :class:`Device` by its hardware ``device_uid`` (the MQTT id).

    Returns ``None`` when no device is registered for ``device_uid`` — the
    caller logs and drops the reading rather than auto-provisioning, so unknown
    nodes cannot silently pollute a tenant's data.
    """
    stmt = select(Device).where(Device.device_uid == device_uid)
    return session.execute(stmt).scalar_one_or_none()


def persist_reading(session: Session, *, org_id: uuid.UUID, telem: TelemetryIn) -> bool:
    """Insert one telemetry reading; return ``True`` if stored, ``False`` if dropped.

    ``False`` is returned for an unknown device, a tenant mismatch, or a
    duplicate ``(device_id, time)`` (idempotent re-delivery). On a duplicate the
    :class:`IntegrityError` is caught, the session rolled back, and ``False``
    returned, which works identically on PostgreSQL and SQLite.

    Side effects on success: ``org_id``/``greenhouse_id`` are denormalized onto
    the reading, ``ingested_at`` is stamped, and the device's denormalized health
    fields (``last_seen_at``/``last_battery_v``/``last_rssi``/``status``) are
    refreshed.
    """
    device = resolve_device(session, telem.device_id)
    if device is None:
        logger.warning("ingest.unknown_device", device_uid=telem.device_id)
        return False

    # Strict tenant isolation: a node may only write into its own org.
    if device.org_id != org_id:
        logger.warning(
            "ingest.org_mismatch",
            device_uid=telem.device_id,
            topic_org_id=str(org_id),
            device_org_id=str(device.org_id),
        )
        return False

    now = datetime.now(UTC)
    reading = Reading(
        device_id=device.id,
        time=telem.ts,
        org_id=device.org_id,
        greenhouse_id=device.greenhouse_id,
        ingested_at=now,
        **{field: getattr(telem, field) for field in _READING_FIELDS},
    )
    session.add(reading)

    # Refresh denormalized device health before the commit so it lands atomically
    # with the reading (or rolls back together on a duplicate).
    device.last_seen_at = telem.ts
    if telem.battery_v is not None:
        device.last_battery_v = telem.battery_v
    if telem.rssi is not None:
        device.last_rssi = telem.rssi
    if device.status != DeviceStatus.ACTIVE:
        device.status = DeviceStatus.ACTIVE

    try:
        session.commit()
    except IntegrityError:
        # Duplicate PK (idempotent re-delivery) or a concurrent insert race.
        session.rollback()
        logger.debug(
            "ingest.duplicate",
            device_uid=telem.device_id,
            ts=telem.ts.isoformat(),
        )
        return False

    logger.info(
        "ingest.stored",
        device_uid=telem.device_id,
        greenhouse_id=str(device.greenhouse_id) if device.greenhouse_id else None,
        ts=telem.ts.isoformat(),
    )
    return True
