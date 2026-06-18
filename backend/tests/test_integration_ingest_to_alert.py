"""Cross-module integration: telemetry ingest -> risk eval -> alert dispatch.

This exercises the full *sync* pipeline (the path Celery and the MQTT consumer
run in production) end to end against an in-memory SQLite DB:

1. Seed a minimal tenant tree: Organization -> Farm -> Greenhouse -> Device,
   plus an active tomato ``CropCycle`` and a notifiable ``User``.
2. Persist a blight-conducive evening of hourly readings *through the real
   ingestion writer* (:func:`app.ingestion.writer.persist_reading`) — each
   reading is validated as a :class:`TelemetryIn` first, just like the wire
   path, so device resolution, denormalization and idempotency are all tested.
3. Run :func:`app.risk_engine.engine.evaluate_greenhouse` and assert it persists
   a HIGH late-blight :class:`RiskAssessment` and a PENDING :class:`Alert`.
4. Run :func:`app.alerting.dispatcher.dispatch_alert` and assert the alert
   reaches ``SENT`` with a console attempt recorded in ``dispatch_log``.

The value of this test over the per-module unit tests is that the *seam* between
ingestion and the risk engine is real: readings land via ``persist_reading``
(not hand-built ``Reading`` rows), so a drift in the denormalized
``org_id``/``greenhouse_id`` columns or the ``device_uid`` resolution would be
caught here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

# Importing the dispatcher wires the channel registry (console always present).
from app.alerting.dispatcher import dispatch_alert
from app.db.base import Base
from app.db.models import (
    Alert,
    Crop,
    CropCycle,
    Device,
    Farm,
    Greenhouse,
    Organization,
    Recommendation,
    RiskAssessment,
    User,
)
from app.db.models.common import (
    AlertChannelType,
    AlertStatus,
    CropStage,
    DeviceType,
    Language,
    RiskLevel,
    RiskModelType,
    UserRole,
)
from app.ingestion.writer import persist_reading
from app.risk_engine.defaults import seed_risk_configs
from app.risk_engine.engine import evaluate_greenhouse
from app.schemas.telemetry import TelemetryIn

# "Now" anchored at a fixed instant so the reading window is deterministic.
NOW = datetime(2026, 6, 19, 6, 0, tzinfo=UTC)
DEVICE_UID = "GH1-NODE-01"

# Placeholder hash: we never authenticate here and the local bcrypt build
# self-tests on import in a way that raises in this environment, so we store a
# constant directly rather than calling ``hash_password`` (same trick as the
# alerting unit tests).
_FAKE_HASH = "x" * 60


@pytest.fixture
def sync_session() -> Session:
    """A sync SQLite session shared across connections via ``StaticPool``."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _seed_tenant(session: Session) -> tuple[Organization, Greenhouse, Device]:
    """Build Org -> Farm -> Greenhouse -> Device and a notifiable user."""
    org = Organization(
        name="Demo Coop",
        slug=f"demo-{uuid.uuid4().hex[:8]}",
        timezone="Africa/Nairobi",
    )
    session.add(org)
    session.flush()

    farm = Farm(org_id=org.id, name="Nakuru Farm", latitude=-0.303, longitude=36.080)
    session.add(farm)
    session.flush()

    gh = Greenhouse(org_id=org.id, farm_id=farm.id, name="GH-1")
    session.add(gh)
    session.flush()

    device = Device(
        org_id=org.id,
        greenhouse_id=gh.id,
        device_uid=DEVICE_UID,
        name="Node 01",
        device_type=DeviceType.SENSOR_NODE,
    )
    session.add(device)

    # A farmer who will receive the dispatched alert. ``preferred_channel`` is
    # WhatsApp but unconfigured -> the dispatcher falls back to console.
    user = User(
        org_id=org.id,
        email=f"farmer-{uuid.uuid4().hex[:6]}@demo-coop.ke",
        phone="+254700000001",
        hashed_password=_FAKE_HASH,
        full_name="Test Farmer",
        role=UserRole.FARMER,
        preferred_language=Language.EN,
        preferred_channel=AlertChannelType.WHATSAPP,
    )
    session.add(user)

    # Active tomato cycle at flowering (drives crop/stage context in the engine).
    crop = Crop(name="tomato", npk_targets={"flowering": {"n": 150, "p": 50, "k": 250}})
    session.add(crop)
    session.flush()
    cycle = CropCycle(
        org_id=org.id,
        greenhouse_id=gh.id,
        crop_id=crop.id,
        crop_name="tomato",
        planting_date=date(2026, 5, 5),
        current_stage=CropStage.FLOWERING,
        is_active=True,
    )
    session.add(cycle)
    session.commit()
    return org, gh, device


def _ingest_blight_evening(session: Session, org_id, *, hours: int = 12) -> int:
    """Persist ``hours`` of cool-wet hourly readings via the ingestion writer.

    Each reading is RH 95% at 20 C — squarely inside the wet-hour window
    (RH>=90, 10<=temp<=26), so ``hours >= high_hours (10)`` yields a HIGH verdict.
    Returns the number of readings actually stored.
    """
    start = NOW - timedelta(hours=hours - 1)
    stored = 0
    for i in range(hours):
        telem = TelemetryIn(
            device_id=DEVICE_UID,
            ts=start + timedelta(hours=i),
            air_temp_c=20.0,
            rh_pct=95.0,
            soil_moisture_pct=40.0,
            battery_v=3.9,
            rssi=-70,
        )
        if persist_reading(session, org_id=org_id, telem=telem):
            stored += 1
    return stored


def test_full_pipeline_ingest_to_high_blight_alert_dispatched(sync_session: Session) -> None:
    org, gh, device = _seed_tenant(sync_session)

    # ---- 1. Ingest a blight-conducive evening through the real writer. ----
    stored = _ingest_blight_evening(sync_session, org.id, hours=12)
    assert stored == 12

    # The writer denormalized org/greenhouse onto every reading and refreshed
    # the device health fields — this is the ingestion->engine seam.
    sync_session.refresh(device)
    assert device.last_seen_at is not None
    assert device.last_battery_v == 3.9
    assert device.last_rssi == -70

    # Idempotent re-delivery of an already-stored reading is dropped.
    dup = TelemetryIn(
        device_id=DEVICE_UID, ts=NOW, air_temp_c=20.0, rh_pct=95.0, soil_moisture_pct=40.0
    )
    assert persist_reading(sync_session, org_id=org.id, telem=dup) is False

    # ---- 2. Risk engine turns the readings into a HIGH blight assessment. ----
    seed_risk_configs(sync_session, org_id=org.id)
    assessments = evaluate_greenhouse(sync_session, gh.id, now=NOW)

    blight = [a for a in assessments if a.model_type is RiskModelType.LATE_BLIGHT]
    assert len(blight) == 1
    assert blight[0].level is RiskLevel.HIGH
    assert blight[0].details["wet_hours"] == 12

    db_assessment = sync_session.scalars(
        select(RiskAssessment).where(
            RiskAssessment.model_type == RiskModelType.LATE_BLIGHT,
            RiskAssessment.greenhouse_id == gh.id,
        )
    ).first()
    assert db_assessment is not None
    assert db_assessment.level is RiskLevel.HIGH

    # ---- 3. The actionable result upserted a PENDING alert + recommendation. ----
    alert = sync_session.scalars(
        select(Alert).where(
            Alert.model_type == RiskModelType.LATE_BLIGHT,
            Alert.greenhouse_id == gh.id,
        )
    ).first()
    assert alert is not None
    assert alert.level is RiskLevel.HIGH
    assert alert.status is AlertStatus.PENDING
    assert alert.org_id == org.id

    rec = sync_session.scalars(
        select(Recommendation).where(Recommendation.alert_id == alert.id)
    ).first()
    assert rec is not None
    assert rec.message_en and rec.message_sw
    assert rec.message_en != rec.message_sw

    # ---- 4. Dispatch the alert: it reaches SENT via the console fallback. ----
    dispatched = dispatch_alert(sync_session, alert)

    assert dispatched.status is AlertStatus.SENT
    assert dispatched.last_sent_at is not None
    assert len(dispatched.dispatch_log) == 1
    entry = dispatched.dispatch_log[0]
    # WhatsApp is unconfigured offline -> console fallback, status "printed".
    assert entry["channel"] == AlertChannelType.CONSOLE.value
    assert entry["status"] == "printed"
    assert entry["error"] is None
