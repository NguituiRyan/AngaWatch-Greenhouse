"""Device → cloud control feedback: handle actuator state/ack messages.

The ESP firmware publishes to ``farm/{org_id}/{node_uid}/state`` after it flips a
relay::

    {"command_id"?, "actuator_uid": "GH1-VENT-01", "state": "open", "ok": true, "ts": ...}

This sync handler (driven by the MQTT consumer) confirms the real
``ActuatorDevice.state`` and marks the correlated ``ControlCommand`` ``ACKED`` —
so the dashboard reflects what the hardware actually did, not just the optimistic
state the API set on publish.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.common import ActuatorState, CommandStatus
from app.db.models.control import ActuatorDevice, ControlCommand

logger = get_logger(__name__)


def _coerce_state(value: object) -> ActuatorState | None:
    if not isinstance(value, str):
        return None
    try:
        return ActuatorState(value.strip().lower())
    except ValueError:
        return None


def handle_state_message(
    session: Session,
    *,
    org_id: uuid.UUID,
    device_uid: str,
    payload: dict,
) -> ControlCommand | None:
    """Apply a device-reported actuator state/ack. Returns the acked command, if any.

    Idempotent and defensive: unknown actuators/commands are logged and skipped
    rather than raising (the consumer must never die on a bad message).
    """
    actuator_uid = payload.get("actuator_uid") or device_uid
    actuator = session.scalar(
        select(ActuatorDevice).where(
            ActuatorDevice.org_id == org_id,
            ActuatorDevice.name == actuator_uid,
        )
    )
    if actuator is None:
        logger.warning("control.state.unknown_actuator", org_id=str(org_id), uid=actuator_uid)
        return None

    now = datetime.now(UTC)
    state = _coerce_state(payload.get("state"))
    if state is not None:
        actuator.state = state
        actuator.last_state_change = now
    actuator.is_online = True

    ok = bool(payload.get("ok", True))

    # Correlate to a command: prefer the explicit command_id, else the most recent
    # not-yet-acked command for this actuator.
    cmd: ControlCommand | None = None
    raw_id = payload.get("command_id")
    if raw_id:
        try:
            cmd = session.scalar(
                select(ControlCommand).where(
                    ControlCommand.id == uuid.UUID(str(raw_id)),
                    ControlCommand.org_id == org_id,
                )
            )
        except (ValueError, AttributeError):
            cmd = None
    if cmd is None:
        cmd = session.scalar(
            select(ControlCommand)
            .where(
                ControlCommand.org_id == org_id,
                ControlCommand.actuator_device_id == actuator.id,
                ControlCommand.status.in_([CommandStatus.SENT, CommandStatus.QUEUED]),
            )
            .order_by(ControlCommand.issued_at.desc())
            .limit(1)
        )

    if cmd is not None:
        cmd.status = CommandStatus.ACKED if ok else CommandStatus.FAILED
        cmd.acked_at = now
        if not ok:
            cmd.error = str(payload.get("error") or "device reported failure")

    session.commit()
    logger.info(
        "control.state.applied",
        org_id=str(org_id),
        actuator_uid=actuator_uid,
        state=state.value if state else None,
        command_id=str(cmd.id) if cmd else None,
        ok=ok,
    )
    return cmd
