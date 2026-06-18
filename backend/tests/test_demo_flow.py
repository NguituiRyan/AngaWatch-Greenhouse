"""Demo-core test.

Builds a standalone **sync** SQLite engine (the seed + demo use the sync session
path), runs the seed, then drives the importable demo core
(``run_blight_core`` = inject blight window -> evaluate -> dispatch) and asserts
that a HIGH late-blight ``RiskAssessment`` and an ``Alert`` row are produced.

It deliberately does NOT touch the async billing/control steps (those need the
configured async engine); the contract only requires this test to prove the
detect -> alert core of the demo.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.models import Alert, Reading, RiskAssessment
from app.db.models.common import RiskLevel, RiskModelType
from app.seed import constants as C
from app.seed.demo import (
    find_blight_assessment,
    inject_blight_window,
    inject_humidity_break,
    run_blight_core,
    run_risk_evaluation,
)
from app.seed.seed import get_demo_org, seed_demo


@pytest.fixture
def sync_session():
    """A sync SQLite session with the full schema created."""
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


def test_seed_is_idempotent(sync_session: Session) -> None:
    now = datetime.now(UTC)
    first = seed_demo(sync_session, now=now)
    assert first.created is True
    assert first.organization.slug == C.ORG_SLUG
    assert len(first.users) == len(C.DEMO_USERS)
    assert first.readings_created > 0

    # Re-running must NOT create a second org and must report created=False.
    second = seed_demo(sync_session, now=now)
    assert second.created is False
    assert second.organization.id == first.organization.id

    # Exactly one org with the demo slug.
    assert get_demo_org(sync_session) is not None


def test_seed_creates_full_hierarchy(sync_session: Session) -> None:
    result = seed_demo(sync_session)
    assert result.farm.latitude == C.FARM_LAT
    assert result.greenhouse.name == C.GREENHOUSE_NAME
    assert result.device.device_uid == C.DEVICE_UID
    assert result.vent.name == C.VENT_ACTUATOR_NAME
    assert result.crop_cycle.current_stage == C.CROP_CYCLE_STAGE
    # The tomato crop carries per-stage NPK targets.
    assert result.crop.npk_targets["flowering"]["k"] == C.TOMATO_NPK_TARGETS["flowering"]["k"]


def test_baseline_has_no_blight_risk(sync_session: Session) -> None:
    now = datetime.now(UTC)
    result = seed_demo(sync_session, now=now)
    assessments = run_risk_evaluation(sync_session, result.greenhouse.id, now=now)
    blight = find_blight_assessment(assessments)
    # Healthy baseline: either no blight assessment at all, or below MEDIUM.
    if blight is not None:
        assert blight.level.rank < RiskLevel.MEDIUM.rank


def test_blight_core_produces_high_risk_and_alert(sync_session: Session) -> None:
    """The marquee assertion: inject -> evaluate -> dispatch yields HIGH + an Alert."""
    now = datetime.now(UTC)
    result = seed_demo(sync_session, now=now)

    core = run_blight_core(sync_session, result.greenhouse, result.device.id, now=now)

    # A HIGH late-blight RiskAssessment was persisted.
    assert core.blight is not None, "expected a late-blight assessment"
    assert core.blight.model_type == RiskModelType.LATE_BLIGHT
    assert core.blight.level == RiskLevel.HIGH, f"got {core.blight.level}"

    # The assessment row is actually in the DB.
    persisted = sync_session.scalars(
        select(RiskAssessment)
        .where(RiskAssessment.greenhouse_id == result.greenhouse.id)
        .where(RiskAssessment.model_type == RiskModelType.LATE_BLIGHT)
        .where(RiskAssessment.level == RiskLevel.HIGH)
    ).all()
    assert persisted, "HIGH blight assessment not persisted"

    # An Alert row was produced for the blight risk.
    alert_rows = sync_session.scalars(
        select(Alert)
        .where(Alert.greenhouse_id == result.greenhouse.id)
        .where(Alert.model_type == RiskModelType.LATE_BLIGHT)
    ).all()
    assert alert_rows, "no Alert row produced for the blight risk"
    assert alert_rows[0].level == RiskLevel.HIGH

    # dispatch_alert returned the dispatched alert(s) and logged a delivery attempt.
    assert core.alerts, "dispatch produced no alerts"
    assert any(a.dispatch_log for a in core.alerts), "no dispatch-log entries recorded"


def test_humidity_break_resolves_risk(sync_session: Session) -> None:
    """After the vents open and the canopy dries, the blight run breaks."""
    now = datetime.now(UTC)
    result = seed_demo(sync_session, now=now)

    inject_blight_window(sync_session, result.greenhouse, result.device.id, now=now)
    before = find_blight_assessment(
        run_risk_evaluation(sync_session, result.greenhouse.id, now=now)
    )
    assert before is not None and before.level == RiskLevel.HIGH

    # Vents open -> dry readings break the trailing wet-hour run.
    inject_humidity_break(sync_session, result.greenhouse, result.device.id, now=now)
    after = find_blight_assessment(run_risk_evaluation(sync_session, result.greenhouse.id, now=now))
    after_rank = after.level.rank if after is not None else RiskLevel.NONE.rank
    assert after_rank < before.level.rank, "risk did not fall after the humidity break"


def test_injected_readings_are_wet(sync_session: Session) -> None:
    """Sanity: injected blight readings satisfy the wet-hour predicate."""
    now = datetime.now(UTC)
    result = seed_demo(sync_session, now=now)
    inject_blight_window(sync_session, result.greenhouse, result.device.id, now=now)

    recent = sync_session.scalars(
        select(Reading)
        .where(Reading.greenhouse_id == result.greenhouse.id)
        .order_by(Reading.time.desc())
        .limit(C.BLIGHT_INJECT_HOURS)
    ).all()
    assert recent
    for r in recent:
        assert r.rh_pct is not None and r.rh_pct >= 90.0
        assert r.air_temp_c is not None and 10.0 <= r.air_temp_c <= 26.0
