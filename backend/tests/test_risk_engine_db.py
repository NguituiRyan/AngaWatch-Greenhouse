"""DB integration tests for the risk-engine orchestrator (sync SQLite).

Builds a minimal tenant tree (Org -> Farm -> Greenhouse -> Device) plus 10 hours
of cool-wet readings and asserts ``evaluate_greenhouse`` persists a HIGH blight
``RiskAssessment`` + ``Alert`` + ``Recommendation``, and that re-running dedups.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import (
    Alert,
    Crop,
    CropCycle,
    Device,
    Farm,
    Greenhouse,
    Organization,
    Reading,
    Recommendation,
    RiskAssessment,
)
from app.db.models.common import CropStage, DeviceType, RiskLevel, RiskModelType
from app.risk_engine.defaults import seed_risk_configs
from app.risk_engine.engine import evaluate_greenhouse

NOW = datetime(2026, 6, 19, 6, 0, tzinfo=UTC)


@pytest.fixture
def sync_session():
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


def _seed_tree(session: Session) -> tuple[Organization, Greenhouse, Device]:
    org = Organization(name="Demo Coop", slug=f"demo-{uuid.uuid4().hex[:8]}")
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
        device_uid="GH1-NODE-01",
        name="Node 01",
        device_type=DeviceType.SENSOR_NODE,
    )
    session.add(device)
    session.flush()
    return org, gh, device


def _seed_crop_cycle(session: Session, org: Organization, gh: Greenhouse) -> CropCycle:
    crop = Crop(
        name="tomato",
        npk_targets={"flowering": {"n": 150, "p": 50, "k": 250}},
    )
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
    session.flush()
    return cycle


def _seed_wet_readings(session: Session, org_id, gh_id, device_id, hours: int = 10) -> None:
    """Insert ``hours`` of consecutive cool-wet hourly readings ending at NOW."""
    start = NOW - timedelta(hours=hours - 1)
    for i in range(hours):
        session.add(
            Reading(
                device_id=device_id,
                time=start + timedelta(hours=i),
                org_id=org_id,
                greenhouse_id=gh_id,
                air_temp_c=20.0,
                rh_pct=95.0,
                soil_moisture_pct=40.0,
            )
        )
    session.flush()


def test_evaluate_persists_high_blight_with_alert_and_recommendation(sync_session: Session) -> None:
    org, gh, device = _seed_tree(sync_session)
    _seed_crop_cycle(sync_session, org, gh)
    _seed_wet_readings(sync_session, org.id, gh.id, device.id, hours=10)
    seed_risk_configs(sync_session, org_id=org.id)

    assessments = evaluate_greenhouse(sync_session, gh.id, now=NOW)

    # A blight assessment must exist and be HIGH.
    blight = [a for a in assessments if a.model_type is RiskModelType.LATE_BLIGHT]
    assert len(blight) == 1
    assert blight[0].level is RiskLevel.HIGH
    assert blight[0].details["wet_hours"] == 10

    # Persisted to DB.
    db_assessments = sync_session.scalars(
        select(RiskAssessment).where(RiskAssessment.model_type == RiskModelType.LATE_BLIGHT)
    ).all()
    assert len(db_assessments) == 1

    # An Alert + Recommendation were created for the HIGH blight result.
    alert = sync_session.scalars(
        select(Alert).where(Alert.model_type == RiskModelType.LATE_BLIGHT)
    ).first()
    assert alert is not None
    assert alert.level is RiskLevel.HIGH
    assert alert.org_id == org.id
    assert alert.greenhouse_id == gh.id

    rec = sync_session.scalars(
        select(Recommendation).where(Recommendation.alert_id == alert.id)
    ).first()
    assert rec is not None
    assert rec.message_en
    assert rec.message_sw
    assert rec.message_en != rec.message_sw
    assert rec.action_code


def test_rerun_dedupes_alert(sync_session: Session) -> None:
    org, gh, device = _seed_tree(sync_session)
    _seed_wet_readings(sync_session, org.id, gh.id, device.id, hours=10)
    seed_risk_configs(sync_session, org_id=org.id)

    evaluate_greenhouse(sync_session, gh.id, now=NOW)
    # Re-run shortly after: within cooldown the same dedup_key must not duplicate.
    evaluate_greenhouse(sync_session, gh.id, now=NOW + timedelta(hours=1))

    alerts = sync_session.scalars(
        select(Alert).where(Alert.model_type == RiskModelType.LATE_BLIGHT)
    ).all()
    assert len(alerts) == 1

    # Two assessments persisted (one per run) even though the alert deduped.
    assessments = sync_session.scalars(
        select(RiskAssessment).where(RiskAssessment.model_type == RiskModelType.LATE_BLIGHT)
    ).all()
    assert len(assessments) == 2


def test_disabled_config_skips_model(sync_session: Session) -> None:
    org, gh, device = _seed_tree(sync_session)
    _seed_wet_readings(sync_session, org.id, gh.id, device.id, hours=10)
    seed_risk_configs(sync_session, org_id=org.id)

    # Disable the blight config for this org.
    from app.db.models.intelligence import RiskModelConfig

    cfg = sync_session.scalars(
        select(RiskModelConfig).where(RiskModelConfig.model_type == RiskModelType.LATE_BLIGHT)
    ).first()
    cfg.enabled = False
    sync_session.commit()

    assessments = evaluate_greenhouse(sync_session, gh.id, now=NOW)
    assert not any(a.model_type is RiskModelType.LATE_BLIGHT for a in assessments)


def test_no_readings_produces_no_assessments(sync_session: Session) -> None:
    org, gh, device = _seed_tree(sync_session)
    seed_risk_configs(sync_session, org_id=org.id)
    assert evaluate_greenhouse(sync_session, gh.id, now=NOW) == []
