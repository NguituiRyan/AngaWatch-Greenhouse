"""Command queue + execution service (async — used by the API request path).

Two seams the rest of the platform depends on:

- :func:`enqueue_command` — persist a ``ControlCommand`` in ``QUEUED`` state.
- :func:`execute_command` — load the actuator + its driver, enforce safety
  interlocks, apply the command, update actuator state, and mark the command
  ``ACKED`` / ``FAILED``.

Drivers are selected from ``app.control.drivers.driver_registry``; the default
is the always-present ``mock`` driver so the stack runs offline. Importing this
module imports ``app.control.drivers`` for its registration side effects.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import app.control.drivers  # noqa: F401 — registers mock + mqtt drivers
from app.control.base import ActuatorDriver, CommandResult, driver_registry
from app.core.logging import get_logger
from app.db.models.common import ActuatorState, CommandSource, CommandStatus
from app.db.models.control import ActuatorDevice, ControlCommand

logger = get_logger(__name__)

# Default driver when the actuator config does not pin one.
DEFAULT_DRIVER_NAME = "mock"


class SafetyInterlockError(Exception):
    """Raised when a command violates an actuator's configured safety interlock."""


def _coerce_state(new_state: str | None) -> ActuatorState | None:
    """Map a driver's free-form state string to an ``ActuatorState`` enum."""
    if new_state is None:
        return None
    try:
        return ActuatorState(new_state.strip().lower())
    except ValueError:
        return None


def _driver_for(actuator: ActuatorDevice) -> ActuatorDriver:
    """Resolve the driver for an actuator, defaulting to the mock driver.

    The actuator's ``config["driver"]`` may pin a registered driver name; if it
    is missing or unknown, fall back to the always-present ``mock`` driver.
    """
    name = None
    if isinstance(actuator.config, dict):
        name = actuator.config.get("driver")
    driver = driver_registry.get(name) if name else None
    if driver is None:
        driver = driver_registry.get(DEFAULT_DRIVER_NAME)
    if driver is None:  # pragma: no cover - mock is always registered
        raise RuntimeError("no actuator driver available (mock missing)")
    return driver


def _check_interlocks(actuator: ActuatorDevice, *, now: datetime) -> None:
    """Enforce basic safety interlocks from ``ActuatorDevice.config``.

    Currently supported:
    - ``min_cycle_interval_s`` / ``min_cycle_interval_min``: reject a command if
      the actuator changed state too recently (protects motors/relays from
      rapid cycling).

    Raises :class:`SafetyInterlockError` when a command must be blocked.
    """
    config = actuator.config if isinstance(actuator.config, dict) else {}

    interval_s = config.get("min_cycle_interval_s")
    if interval_s is None and config.get("min_cycle_interval_min") is not None:
        interval_s = float(config["min_cycle_interval_min"]) * 60.0

    if interval_s and actuator.last_state_change is not None:
        last = actuator.last_state_change
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        elapsed = (now - last).total_seconds()
        if elapsed < float(interval_s):
            raise SafetyInterlockError(
                f"min cycle interval not met: {elapsed:.0f}s < {float(interval_s):.0f}s"
            )


async def enqueue_command(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actuator_device_id: uuid.UUID,
    command: str,
    source: CommandSource,
    issued_by: uuid.UUID | None = None,
    params: dict | None = None,
) -> ControlCommand:
    """Persist a ``ControlCommand`` in ``QUEUED`` state and return it.

    Does NOT actuate anything — that is :func:`execute_command`. The command is
    stamped ``issued_at`` now (UTC) and scoped to ``org_id``.
    """
    cmd = ControlCommand(
        org_id=org_id,
        actuator_device_id=actuator_device_id,
        command=command,
        params=params or {},
        status=CommandStatus.QUEUED,
        source=source,
        issued_by=issued_by,
        issued_at=datetime.now(UTC),
    )
    db.add(cmd)
    await db.commit()
    await db.refresh(cmd)
    logger.info(
        "control_command_enqueued",
        command_id=str(cmd.id),
        org_id=str(org_id),
        actuator_device_id=str(actuator_device_id),
        command=command,
        source=str(source),
    )
    return cmd


async def execute_command(db: AsyncSession, command_id: uuid.UUID) -> ControlCommand:
    """Execute a queued command: apply via driver, update state + status.

    Loads the command and its actuator, enforces safety interlocks, applies the
    command through the resolved driver (default ``mock``), updates
    ``ActuatorDevice.state`` + ``last_state_change`` on success, and sets the
    command status to ``ACKED`` (driver acked) or ``FAILED`` (interlock blocked,
    actuator missing, or driver error), stamping ``acked_at`` either way.
    """
    cmd = await db.get(ControlCommand, command_id)
    if cmd is None:
        raise ValueError(f"control command not found: {command_id}")

    now = datetime.now(UTC)
    cmd.sent_at = now

    actuator = await db.scalar(
        select(ActuatorDevice).where(
            ActuatorDevice.id == cmd.actuator_device_id,
            ActuatorDevice.org_id == cmd.org_id,
        )
    )
    if actuator is None:
        cmd.status = CommandStatus.FAILED
        cmd.error = "actuator not found"
        cmd.acked_at = now
        await db.commit()
        await db.refresh(cmd)
        logger.warning("control_command_no_actuator", command_id=str(command_id))
        return cmd

    # ---- Safety interlocks ----
    try:
        _check_interlocks(actuator, now=now)
    except SafetyInterlockError as exc:
        cmd.status = CommandStatus.FAILED
        cmd.error = f"safety interlock: {exc}"
        cmd.acked_at = now
        await db.commit()
        await db.refresh(cmd)
        logger.warning(
            "control_command_interlock_blocked",
            command_id=str(command_id),
            actuator_device_id=str(actuator.id),
            reason=str(exc),
        )
        return cmd

    # ---- Apply via driver ----
    driver = _driver_for(actuator)
    target_uid = actuator.name
    try:
        result: CommandResult = driver.apply(
            actuator_type=actuator.actuator_type,
            target_uid=target_uid,
            command=cmd.command,
            params=cmd.params or {},
        )
    except Exception as exc:  # defensive: a driver must never crash the request
        cmd.status = CommandStatus.FAILED
        cmd.error = f"driver error: {exc}"
        cmd.acked_at = now
        await db.commit()
        await db.refresh(cmd)
        logger.error(
            "control_command_driver_crash",
            command_id=str(command_id),
            driver=driver.name,
            error=str(exc),
        )
        return cmd

    if result.ok and result.acked:
        new_state = _coerce_state(result.new_state)
        if new_state is not None:
            actuator.state = new_state
            actuator.last_state_change = now
        cmd.status = CommandStatus.ACKED
        cmd.acked_at = now
        cmd.error = None
        logger.info(
            "control_command_acked",
            command_id=str(command_id),
            driver=driver.name,
            new_state=result.new_state,
        )
    elif result.ok and not result.acked:
        # Driver published but has no device ack yet (e.g. fire-and-forget MQTT).
        new_state = _coerce_state(result.new_state)
        if new_state is not None:
            actuator.state = new_state
            actuator.last_state_change = now
        cmd.status = CommandStatus.SENT
        cmd.error = None
        logger.info(
            "control_command_sent",
            command_id=str(command_id),
            driver=driver.name,
            new_state=result.new_state,
        )
    else:
        cmd.status = CommandStatus.FAILED
        cmd.error = result.error or "driver reported failure"
        cmd.acked_at = now
        logger.warning(
            "control_command_failed",
            command_id=str(command_id),
            driver=driver.name,
            error=cmd.error,
        )

    await db.commit()
    await db.refresh(cmd)
    return cmd
