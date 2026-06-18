"""Tests for the control / automation module.

Covers the two cross-module seams (``enqueue_command`` -> QUEUED,
``execute_command`` -> ACKED + actuator state flips), driver registration, the
mock + mqtt drivers, the safety interlocks, and the automation scaffold's
safe-no-op + firing behaviour.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.control import driver_registry
from app.control.automation import evaluate_rules
from app.control.drivers.mock import MockActuatorDriver
from app.control.drivers.mqtt_relay import MqttRelayDriver
from app.control.service import enqueue_command, execute_command
from app.db.base import Base
from app.db.models import (
    ActuatorDevice,
    AutomationRule,
    ControlCommand,
    Organization,
    Reading,
)
from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    CommandSource,
    CommandStatus,
)
from app.db.models.farm import Farm, Greenhouse


def _sync_session() -> Session:
    """A throwaway in-memory sync session for the automation (Celery-path) tests."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


@pytest_asyncio.fixture
async def greenhouse(db, org) -> Greenhouse:
    farm = Farm(org_id=org.id, name="Nakuru Farm", latitude=-0.303, longitude=36.080)
    db.add(farm)
    await db.commit()
    await db.refresh(farm)

    gh = Greenhouse(org_id=org.id, farm_id=farm.id, name="GH-1")
    db.add(gh)
    await db.commit()
    await db.refresh(gh)
    return gh


@pytest_asyncio.fixture
async def vent(db, org, greenhouse) -> ActuatorDevice:
    a = ActuatorDevice(
        org_id=org.id,
        greenhouse_id=greenhouse.id,
        name="GH1-VENT-01",
        actuator_type=ActuatorType.VENT,
        state=ActuatorState.CLOSED,
        is_online=True,
        config={},
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


# --------------------------------------------------------------------------- #
# Drivers
# --------------------------------------------------------------------------- #
def test_mock_driver_registered() -> None:
    """The mock driver is always present in the registry."""
    driver = driver_registry.get("mock")
    assert driver is not None
    assert driver.name == "mock"


def test_mqtt_driver_registered() -> None:
    """Importing drivers also registers the mqtt relay driver."""
    driver = driver_registry.get("mqtt")
    assert driver is not None
    assert driver.name == "mqtt"


def test_mock_driver_acks_and_reports_state() -> None:
    res = MockActuatorDriver().apply(
        actuator_type=ActuatorType.VENT, target_uid="GH1-VENT-01", command="open"
    )
    assert res.ok is True
    assert res.acked is True
    assert res.new_state == "open"


def test_mock_driver_unknown_command_fails() -> None:
    res = MockActuatorDriver().apply(
        actuator_type=ActuatorType.VENT, target_uid="GH1-VENT-01", command="wiggle"
    )
    assert res.ok is False
    assert res.acked is False
    assert res.error is not None


def test_mqtt_driver_tolerates_broker_absence() -> None:
    """No broker reachable -> graceful failure result, not an exception."""
    driver = MqttRelayDriver(host="127.0.0.1", port=1, connect_timeout_s=0.5)
    res = driver.apply(actuator_type=ActuatorType.VENT, target_uid="GH1-VENT-01", command="open")
    assert res.ok is False
    assert res.error is not None


# --------------------------------------------------------------------------- #
# Service: enqueue + execute
# --------------------------------------------------------------------------- #
async def test_enqueue_command_queued(db, org, vent) -> None:
    cmd = await enqueue_command(
        db,
        org_id=org.id,
        actuator_device_id=vent.id,
        command="open",
        source=CommandSource.MANUAL,
    )
    assert cmd.status == CommandStatus.QUEUED
    assert cmd.issued_at is not None
    assert cmd.org_id == org.id
    assert cmd.command == "open"


async def test_execute_command_acked_and_state_open(db, org, vent) -> None:
    cmd = await enqueue_command(
        db,
        org_id=org.id,
        actuator_device_id=vent.id,
        command="open",
        source=CommandSource.MANUAL,
    )
    executed = await execute_command(db, cmd.id)

    assert executed.status == CommandStatus.ACKED
    assert executed.acked_at is not None

    await db.refresh(vent)
    assert vent.state == ActuatorState.OPEN
    assert vent.last_state_change is not None


async def test_execute_command_missing_actuator_fails(db, org) -> None:
    """A command pointing at a non-existent actuator fails cleanly."""
    cmd = ControlCommand(
        org_id=org.id,
        actuator_device_id=uuid.uuid4(),
        command="open",
        status=CommandStatus.QUEUED,
        source=CommandSource.MANUAL,
        issued_at=datetime.now(UTC),
    )
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)

    executed = await execute_command(db, cmd.id)
    assert executed.status == CommandStatus.FAILED
    assert executed.error == "actuator not found"


async def test_execute_command_unknown_command_id_raises(db) -> None:
    with pytest.raises(ValueError):
        await execute_command(db, uuid.uuid4())


async def test_safety_interlock_blocks_rapid_cycle(db, org, vent) -> None:
    """min_cycle_interval_s blocks a command issued too soon after a change."""
    vent.config = {"min_cycle_interval_s": 600}
    vent.last_state_change = datetime.now(UTC) - timedelta(seconds=10)
    await db.commit()

    cmd = await enqueue_command(
        db,
        org_id=org.id,
        actuator_device_id=vent.id,
        command="open",
        source=CommandSource.MANUAL,
    )
    executed = await execute_command(db, cmd.id)
    assert executed.status == CommandStatus.FAILED
    assert "interlock" in (executed.error or "")


# --------------------------------------------------------------------------- #
# Automation scaffold (sync session)
# --------------------------------------------------------------------------- #
def _seed_sync_greenhouse(s: Session) -> tuple[Organization, Greenhouse]:
    """Create org + farm + greenhouse + a closed vent in a sync session."""
    o = Organization(name="Coop", slug=f"coop-{uuid.uuid4().hex[:8]}")
    s.add(o)
    s.flush()
    farm = Farm(org_id=o.id, name="F")
    s.add(farm)
    s.flush()
    gh = Greenhouse(org_id=o.id, farm_id=farm.id, name="GH-1")
    s.add(gh)
    s.flush()
    s.add(
        ActuatorDevice(
            org_id=o.id,
            greenhouse_id=gh.id,
            name="GH1-VENT-01",
            actuator_type=ActuatorType.VENT,
            state=ActuatorState.CLOSED,
            is_online=True,
            config={},
        )
    )
    s.flush()
    return o, gh


def _humidity_vent_rule(org_id: uuid.UUID, greenhouse_id: uuid.UUID) -> AutomationRule:
    return AutomationRule(
        org_id=org_id,
        greenhouse_id=greenhouse_id,
        name="Vent on high humidity",
        enabled=True,
        condition={"metric": "rh_pct", "op": ">=", "value": 90},
        action={"actuator_type": "vent", "command": "open"},
        safety_interlocks={},
    )


def test_evaluate_rules_no_rules_is_noop() -> None:
    """No enabled rules -> safe no-op returning an empty list."""
    with _sync_session() as s:
        assert evaluate_rules(s, uuid.uuid4()) == []


def test_evaluate_rules_fires_on_condition() -> None:
    """An enabled rule whose condition is met enqueues an AUTO command."""
    with _sync_session() as s:
        o, gh = _seed_sync_greenhouse(s)
        s.add(
            Reading(
                device_id=uuid.uuid4(),
                time=datetime.now(UTC),
                org_id=o.id,
                greenhouse_id=gh.id,
                rh_pct=95.0,
                air_temp_c=22.0,
            )
        )
        rule = _humidity_vent_rule(o.id, gh.id)
        s.add(rule)
        s.commit()

        out = evaluate_rules(s, gh.id)
        assert len(out) == 1
        assert out[0].command == "open"
        assert out[0].source == CommandSource.AUTO
        assert out[0].status == CommandStatus.QUEUED
        assert out[0].automation_rule_id == rule.id


def test_evaluate_rules_skips_when_condition_unmet() -> None:
    """Enabled rule, but the latest reading does not meet the threshold."""
    with _sync_session() as s:
        o, gh = _seed_sync_greenhouse(s)
        s.add(
            Reading(
                device_id=uuid.uuid4(),
                time=datetime.now(UTC),
                org_id=o.id,
                greenhouse_id=gh.id,
                rh_pct=60.0,
            )
        )
        s.add(_humidity_vent_rule(o.id, gh.id))
        s.commit()

        assert evaluate_rules(s, gh.id) == []
