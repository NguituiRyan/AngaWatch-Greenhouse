"""Tests for MQTT ingestion: the sync writer and the topic/payload parsing.

These run against a **sync** in-memory SQLite engine (shared across the test via
``StaticPool``) so the same idempotency path used in production (catch
``IntegrityError`` on the composite PK) is exercised without PostgreSQL.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Device, Organization, Reading
from app.db.models.common import DeviceStatus, DeviceType
from app.ingestion.consumer import parse_topic
from app.ingestion.writer import persist_reading, resolve_device
from app.schemas.telemetry import TelemetryIn


@pytest.fixture
def sync_session():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def org(sync_session: Session) -> Organization:
    o = Organization(name="Demo Coop", slug=f"demo-{uuid.uuid4().hex[:8]}")
    sync_session.add(o)
    sync_session.commit()
    sync_session.refresh(o)
    return o


@pytest.fixture
def device(sync_session: Session, org: Organization) -> Device:
    gh_id = uuid.uuid4()
    d = Device(
        org_id=org.id,
        greenhouse_id=gh_id,
        device_uid="GH1-NODE-01",
        name="GH-1 Sensor Node",
        device_type=DeviceType.SENSOR_NODE,
        status=DeviceStatus.INACTIVE,
    )
    sync_session.add(d)
    sync_session.commit()
    sync_session.refresh(d)
    return d


def _telem(ts: datetime, **overrides: object) -> TelemetryIn:
    base: dict[str, object] = {
        "device_id": "GH1-NODE-01",
        "ts": ts,
        "air_temp_c": 24.5,
        "rh_pct": 88.0,
        "soil_moisture_pct": 40.0,
        "pheromone_count": 5,
        "battery_v": 3.9,
        "rssi": -70,
    }
    base.update(overrides)
    return TelemetryIn.model_validate(base)


def test_resolve_device(sync_session: Session, device: Device) -> None:
    found = resolve_device(sync_session, "GH1-NODE-01")
    assert found is not None
    assert found.id == device.id
    assert resolve_device(sync_session, "DOES-NOT-EXIST") is None


def test_persist_reading_stores_and_denormalizes(
    sync_session: Session, org: Organization, device: Device
) -> None:
    ts = datetime(2026, 6, 19, 9, 0, tzinfo=UTC)
    ok = persist_reading(sync_session, org_id=org.id, telem=_telem(ts))
    assert ok is True

    reading = sync_session.get(Reading, (device.id, ts))
    assert reading is not None
    # Denormalized tenant/greenhouse columns + ingestion stamp.
    assert reading.org_id == org.id
    assert reading.greenhouse_id == device.greenhouse_id
    assert reading.ingested_at is not None
    assert reading.air_temp_c == 24.5


def test_persist_reading_updates_device_health(
    sync_session: Session, org: Organization, device: Device
) -> None:
    assert device.last_seen_at is None
    assert device.status == DeviceStatus.INACTIVE

    ts = datetime(2026, 6, 19, 9, 5, tzinfo=UTC)
    assert persist_reading(sync_session, org_id=org.id, telem=_telem(ts)) is True

    sync_session.refresh(device)
    # SQLite stores DateTime as tz-naive text, so compare the wall-clock value
    # (the writer stamps the aware UTC ts; the round-trip merely drops tzinfo).
    assert device.last_seen_at is not None
    assert device.last_seen_at.replace(tzinfo=UTC) == ts
    assert device.last_battery_v == 3.9
    assert device.last_rssi == -70
    # A reading flips a dormant device back to ACTIVE.
    assert device.status == DeviceStatus.ACTIVE


def test_persist_reading_is_idempotent(
    sync_session: Session, org: Organization, device: Device
) -> None:
    ts = datetime(2026, 6, 19, 9, 10, tzinfo=UTC)
    assert persist_reading(sync_session, org_id=org.id, telem=_telem(ts)) is True
    # Same (device_id, time) again → duplicate PK → False, no exception.
    assert persist_reading(sync_session, org_id=org.id, telem=_telem(ts)) is False

    count = len(sync_session.query(Reading).filter(Reading.device_id == device.id).all())
    assert count == 1


def test_persist_reading_unknown_device(sync_session: Session, org: Organization) -> None:
    ts = datetime(2026, 6, 19, 9, 15, tzinfo=UTC)
    telem = _telem(ts, device_id="NOT-REGISTERED")
    assert persist_reading(sync_session, org_id=org.id, telem=telem) is False


def test_persist_reading_org_mismatch(
    sync_session: Session, org: Organization, device: Device
) -> None:
    ts = datetime(2026, 6, 19, 9, 20, tzinfo=UTC)
    other_org = uuid.uuid4()
    assert persist_reading(sync_session, org_id=other_org, telem=_telem(ts)) is False
    assert sync_session.query(Reading).count() == 0


def test_out_of_range_payload_fails_validation() -> None:
    # rh_pct is bounded 0..100; 150 is physically impossible → ValidationError.
    with pytest.raises(ValidationError):
        TelemetryIn.model_validate(
            {
                "device_id": "GH1-NODE-01",
                "ts": datetime(2026, 6, 19, 9, 0, tzinfo=UTC),
                "rh_pct": 150.0,
            }
        )


def test_parse_topic_valid() -> None:
    org_id = uuid.uuid4()
    parsed = parse_topic(f"farm/{org_id}/GH1-NODE-01/telemetry")
    assert parsed is not None
    got_org, got_uid = parsed
    assert got_org == org_id
    assert got_uid == "GH1-NODE-01"


@pytest.mark.parametrize(
    "topic",
    [
        "farm/not-a-uuid/GH1-NODE-01/telemetry",
        "farm/GH1-NODE-01/telemetry",
        "sensors/123/GH1-NODE-01/telemetry",
        f"farm/{uuid.uuid4()}//telemetry",
        f"farm/{uuid.uuid4()}/GH1-NODE-01/status",
    ],
)
def test_parse_topic_invalid(topic: str) -> None:
    assert parse_topic(topic) is None
