"""Automation rule engine (Wave 1 scaffold).

Wave 0 ships the data model (:class:`AutomationRule`) and MANUAL actuation via
:mod:`app.control.service`. This module is the Wave 1 *scaffold* that, when
auto-firing is switched on, will evaluate each enabled rule's condition against
the latest reading, respect the rule's ``safety_interlocks``, and enqueue a
``ControlCommand`` (source ``AUTO``).

It runs on the **sync** session (the Celery / scheduler path, same as the risk
engine), and is a **safe no-op when no rules are enabled** — it never raises and
returns an empty list in that case.

Status: SCAFFOLD. The condition-evaluation and interlock logic below is
intentionally conservative and heavily ``TODO``-marked; calibration and the
forecast-fused triggers land in Wave 1 proper.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.db.models.common import ActuatorState, CommandSource, CommandStatus
from app.db.models.control import ActuatorDevice, AutomationRule, ControlCommand
from app.db.models.farm import Greenhouse
from app.db.models.reading import Reading

logger = get_logger(__name__)

# Comparison operators a rule condition may use.
_OPS = {
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
}


def _latest_reading(session: Session, greenhouse_id: uuid.UUID) -> Reading | None:
    """Most recent reading for the greenhouse (denormalized ``greenhouse_id``)."""
    return session.scalar(
        select(Reading)
        .where(Reading.greenhouse_id == greenhouse_id)
        .order_by(Reading.time.desc())
        .limit(1)
    )


def _condition_met(condition: dict[str, Any], reading: Reading | None) -> bool:
    """Evaluate ``{"metric", "op", "value"}`` against a reading.

    TODO(Wave 1): support ``duration_min`` (sustained windows via rolling reads),
    forecast-fused pre-warning, and hysteresis so an actuator does not chatter
    around the threshold.
    """
    if not condition or reading is None:
        return False
    metric = condition.get("metric")
    op = condition.get("op")
    threshold = condition.get("value")
    if metric is None or op not in _OPS or threshold is None:
        return False
    current = getattr(reading, str(metric), None)
    if current is None:
        return False
    try:
        return bool(_OPS[op](current, threshold))
    except TypeError:
        return False


def _interlocks_ok(
    rule: AutomationRule,
    actuator: ActuatorDevice,
    reading: Reading | None,
    *,
    now: datetime,
) -> bool:
    """Respect ``rule.safety_interlocks`` before enqueuing an AUTO command.

    Supported now:
    - ``min_air_temp_c``: do not (e.g.) open vents below a floor temperature.
    - ``min_cycle_interval_s`` / ``min_cycle_interval_min``: do not re-fire if
      the actuator changed state too recently.

    TODO(Wave 1): ``max_open_min`` auto-close timers, quiet-hours windows, and
    coordination across competing rules on the same actuator.
    """
    interlocks = rule.safety_interlocks if isinstance(rule.safety_interlocks, dict) else {}

    min_air = interlocks.get("min_air_temp_c")
    if (
        min_air is not None
        and reading is not None
        and reading.air_temp_c is not None
        and reading.air_temp_c < float(min_air)
    ):
        return False

    interval_s = interlocks.get("min_cycle_interval_s")
    if interval_s is None and interlocks.get("min_cycle_interval_min") is not None:
        interval_s = float(interlocks["min_cycle_interval_min"]) * 60.0
    if interval_s and actuator.last_state_change is not None:
        last = actuator.last_state_change
        if last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if (now - last).total_seconds() < float(interval_s):
            return False

    return True


def _resolve_actuator(
    session: Session, greenhouse_id: uuid.UUID, action: dict[str, Any]
) -> ActuatorDevice | None:
    """Find the actuator a rule's ``action`` targets within the greenhouse.

    A rule ``action`` may target by ``actuator_device_id`` or by
    ``actuator_type`` (first matching online actuator in the greenhouse).
    """
    actuator_id = action.get("actuator_device_id")
    if actuator_id:
        return session.scalar(
            select(ActuatorDevice).where(
                ActuatorDevice.id == uuid.UUID(str(actuator_id)),
                ActuatorDevice.greenhouse_id == greenhouse_id,
            )
        )
    actuator_type = action.get("actuator_type")
    if actuator_type:
        return session.scalar(
            select(ActuatorDevice)
            .where(
                ActuatorDevice.greenhouse_id == greenhouse_id,
                ActuatorDevice.actuator_type == actuator_type,
            )
            .order_by(ActuatorDevice.is_online.desc())
            .limit(1)
        )
    return None


def _already_in_target_state(actuator: ActuatorDevice, command: str) -> bool:
    """True if the actuator is already in the state the command would produce."""
    target = {
        "open": ActuatorState.OPEN,
        "close": ActuatorState.CLOSED,
        "on": ActuatorState.ON,
        "off": ActuatorState.OFF,
    }.get(command.strip().lower())
    return target is not None and actuator.state == target


def evaluate_rules(session: Session, greenhouse_id: uuid.UUID) -> list[ControlCommand]:
    """Evaluate enabled automation rules for a greenhouse and enqueue commands.

    Wave 1 scaffold. Loads enabled :class:`AutomationRule` rows for the
    greenhouse, checks each ``condition`` against the latest reading, respects
    the rule's ``safety_interlocks``, and enqueues a ``QUEUED`` AUTO
    ``ControlCommand`` per firing rule. Returns the enqueued commands.

    Safe no-op when there are no enabled rules: returns ``[]`` without touching
    the database. Auto-firing is gated and conservative; see the module-level
    and inline ``TODO`` notes for what Wave 1 proper still owes.
    """
    greenhouse = session.get(Greenhouse, greenhouse_id)
    if greenhouse is None:
        logger.warning("automation_unknown_greenhouse", greenhouse_id=str(greenhouse_id))
        return []

    rules = list(
        session.scalars(
            select(AutomationRule)
            .where(
                AutomationRule.greenhouse_id == greenhouse_id,
                AutomationRule.enabled.is_(True),
            )
            .order_by(AutomationRule.priority.desc())
        )
    )
    if not rules:
        # Safe no-op: nothing enabled, do not query readings or write anything.
        return []

    now = datetime.now(UTC)
    reading = _latest_reading(session, greenhouse_id)
    enqueued: list[ControlCommand] = []

    for rule in rules:
        condition = rule.condition if isinstance(rule.condition, dict) else {}
        action = rule.action if isinstance(rule.action, dict) else {}

        if not _condition_met(condition, reading):
            continue

        command = action.get("command")
        if not command:
            logger.warning("automation_rule_no_command", rule_id=str(rule.id))
            continue

        actuator = _resolve_actuator(session, greenhouse_id, action)
        if actuator is None:
            logger.warning("automation_rule_no_actuator", rule_id=str(rule.id))
            continue

        # Skip if already in the desired state (avoid redundant cycling).
        if _already_in_target_state(actuator, command):
            continue

        if not _interlocks_ok(rule, actuator, reading, now=now):
            logger.info("automation_rule_interlock_blocked", rule_id=str(rule.id))
            continue

        # TODO(Wave 1): de-dupe against an in-flight QUEUED/SENT command for the
        # same actuator before enqueuing, and wire auto-close timers.
        cmd = ControlCommand(
            org_id=rule.org_id,
            actuator_device_id=actuator.id,
            automation_rule_id=rule.id,
            command=command,
            params=action.get("params", {}) or {},
            status=CommandStatus.QUEUED,
            source=CommandSource.AUTO,
            issued_at=now,
        )
        session.add(cmd)
        rule.last_triggered_at = now
        enqueued.append(cmd)
        logger.info(
            "automation_rule_fired",
            rule_id=str(rule.id),
            greenhouse_id=str(greenhouse_id),
            actuator_device_id=str(actuator.id),
            command=command,
        )

    if enqueued:
        session.commit()
        for cmd in enqueued:
            session.refresh(cmd)

    return enqueued
