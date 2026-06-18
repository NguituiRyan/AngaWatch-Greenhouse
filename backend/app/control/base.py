"""Control interfaces: actuator driver ABC + command result + driver registry.

Wave 0 ships a ``mock`` driver (and an MQTT relay driver stub) and MANUAL
actuation from the dashboard. The automation rule engine (``app.control.automation``)
evaluates ``AutomationRule`` conditions and enqueues ``ControlCommand`` rows;
Wave 1 turns auto-firing on (e.g. open vents to break a blight humidity window).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.db.models.common import ActuatorType


@dataclass(slots=True)
class CommandResult:
    ok: bool
    acked: bool = False
    new_state: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


class ActuatorDriver(ABC):
    """Moves a physical actuator. Implementations: mock, mqtt-relay, (future) LoRa."""

    name: str = "base"

    @abstractmethod
    def apply(
        self,
        *,
        actuator_type: ActuatorType,
        target_uid: str,
        command: str,
        params: dict | None = None,
    ) -> CommandResult:
        raise NotImplementedError


class DriverRegistry:
    def __init__(self) -> None:
        self._drivers: dict[str, ActuatorDriver] = {}

    def register(self, driver: ActuatorDriver) -> ActuatorDriver:
        self._drivers[driver.name] = driver
        return driver

    def get(self, name: str) -> ActuatorDriver | None:
        return self._drivers.get(name)


driver_registry = DriverRegistry()
