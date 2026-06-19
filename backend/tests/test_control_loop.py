"""Hardware control loop: MQTT command routing + device state/ack ingestion."""

from __future__ import annotations

import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.control.base import ActuatorDriver, CommandResult
from app.control.drivers.mqtt_relay import MqttRelayDriver
from app.control.ingest import handle_state_message
from app.control.service import _apply_with_fallback
from app.db.base import Base
from app.db.models import ActuatorDevice, ControlCommand, Device, Farm, Greenhouse, Organization
from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    CommandSource,
    CommandStatus,
)


def _session() -> Session:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)()


def _seed_actuator(session: Session) -> tuple[Organization, ActuatorDevice, Device]:
    org = Organization(name="Coop", slug=f"c-{uuid.uuid4().hex[:6]}")
    session.add(org)
    session.flush()
    farm = Farm(org_id=org.id, name="Farm")
    session.add(farm)
    session.flush()
    gh = Greenhouse(org_id=org.id, farm_id=farm.id, name="GH-1")
    session.add(gh)
    session.flush()
    device = Device(org_id=org.id, greenhouse_id=gh.id, device_uid="GH1-NODE-01", name="node")
    session.add(device)
    session.flush()
    vent = ActuatorDevice(
        org_id=org.id,
        greenhouse_id=gh.id,
        device_id=device.id,
        name="GH1-VENT-01",
        actuator_type=ActuatorType.VENT,
        state=ActuatorState.CLOSED,
    )
    session.add(vent)
    session.commit()
    return org, vent, device


def _make_command(session: Session, org_id, actuator_id) -> ControlCommand:
    from datetime import UTC, datetime

    cmd = ControlCommand(
        org_id=org_id,
        actuator_device_id=actuator_id,
        command="open",
        params={},
        status=CommandStatus.SENT,
        source=CommandSource.MANUAL,
        issued_at=datetime.now(UTC),
    )
    session.add(cmd)
    session.commit()
    return cmd


# ---- MQTT command routing -------------------------------------------------


def test_command_topic_uses_org_and_node_uid():
    driver = MqttRelayDriver()
    topic = driver._topic_for(org_id="ORG", node_uid="GH1-NODE-01", params=None)
    assert topic == "farm/ORG/GH1-NODE-01/command"
    # An explicit override wins.
    assert driver._topic_for(org_id="ORG", node_uid="x", params={"topic": "t/y"}) == "t/y"


def test_mqtt_driver_is_graceful_when_broker_down():
    # Point at a closed port: connect is refused -> ok=False, no exception.
    driver = MqttRelayDriver(port=1, connect_timeout_s=1.0)
    result = driver.apply(
        actuator_type=ActuatorType.VENT,
        target_uid="GH1-VENT-01",
        command="open",
        org_id="o",
        node_uid="GH1-NODE-01",
        command_id="c",
    )
    assert result.ok is False
    assert result.acked is False


# ---- Fallback -------------------------------------------------------------


class _FailingDriver(ActuatorDriver):
    name = "failing"

    def apply(self, **kwargs) -> CommandResult:
        return CommandResult(ok=False, acked=False, error="broker down")


def test_apply_with_fallback_uses_mock_on_failure():
    org_id = uuid.uuid4()
    actuator = ActuatorDevice(
        org_id=org_id,
        greenhouse_id=uuid.uuid4(),
        name="GH1-VENT-01",
        actuator_type=ActuatorType.VENT,
        state=ActuatorState.CLOSED,
    )
    cmd = ControlCommand(
        org_id=org_id,
        actuator_device_id=uuid.uuid4(),
        command="open",
        params={},
        status=CommandStatus.QUEUED,
        source=CommandSource.MANUAL,
        issued_at=__import__("datetime").datetime.now(__import__("datetime").UTC),
    )
    cmd.id = uuid.uuid4()
    result = _apply_with_fallback(
        _FailingDriver(),
        actuator=actuator,
        cmd=cmd,
        target_uid="GH1-VENT-01",
        node_uid="GH1-NODE-01",
    )
    assert result.ok and result.acked  # mock acked
    assert result.new_state == "open"
    assert result.raw.get("fell_back_from") == "failing"


# ---- Device state/ack ingestion -------------------------------------------


def test_state_message_confirms_actuator_and_acks_command():
    session = _session()
    org, vent, _ = _seed_actuator(session)
    cmd = _make_command(session, org.id, vent.id)

    acked = handle_state_message(
        session,
        org_id=org.id,
        device_uid="GH1-NODE-01",
        payload={
            "command_id": str(cmd.id),
            "actuator_uid": "GH1-VENT-01",
            "state": "open",
            "ok": True,
        },
    )
    assert acked is not None and acked.id == cmd.id
    session.refresh(vent)
    session.refresh(cmd)
    assert vent.state == ActuatorState.OPEN
    assert vent.is_online is True
    assert cmd.status == CommandStatus.ACKED
    assert cmd.acked_at is not None


def test_state_message_correlates_latest_when_no_command_id():
    session = _session()
    org, vent, _ = _seed_actuator(session)
    cmd = _make_command(session, org.id, vent.id)

    acked = handle_state_message(
        session,
        org_id=org.id,
        device_uid="GH1-NODE-01",
        payload={"actuator_uid": "GH1-VENT-01", "state": "open", "ok": True},
    )
    assert acked is not None and acked.id == cmd.id
    assert acked.status == CommandStatus.ACKED


def test_state_message_unknown_actuator_returns_none():
    session = _session()
    org, _vent, _ = _seed_actuator(session)
    out = handle_state_message(
        session,
        org_id=org.id,
        device_uid="GH1-NODE-01",
        payload={"actuator_uid": "DOES-NOT-EXIST", "state": "open"},
    )
    assert out is None


def test_state_message_failure_marks_command_failed():
    session = _session()
    org, vent, _ = _seed_actuator(session)
    cmd = _make_command(session, org.id, vent.id)
    handle_state_message(
        session,
        org_id=org.id,
        device_uid="GH1-NODE-01",
        payload={
            "command_id": str(cmd.id),
            "actuator_uid": "GH1-VENT-01",
            "ok": False,
            "error": "jam",
        },
    )
    session.refresh(cmd)
    assert cmd.status == CommandStatus.FAILED
    assert "jam" in (cmd.error or "")
