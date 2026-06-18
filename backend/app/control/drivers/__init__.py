"""Actuator drivers — self-register into ``driver_registry`` on import.

The ``mock`` driver is ALWAYS registered so the control stack runs offline. The
``mqtt`` relay driver is also registered (it tolerates broker absence at apply
time, falling back to a non-acked result rather than raising), so a deployment
with a real broker can select it without code changes.

Import this module for its side effects::

    import app.control.drivers  # noqa: F401  -> mock + mqtt registered
"""

from __future__ import annotations

from app.control.base import driver_registry
from app.control.drivers.mock import MockActuatorDriver
from app.control.drivers.mqtt_relay import MqttRelayDriver

# ``mock`` is always present.
driver_registry.register(MockActuatorDriver())
# ``mqtt`` is registered too; it degrades gracefully when no broker is reachable.
driver_registry.register(MqttRelayDriver())

__all__ = ["MockActuatorDriver", "MqttRelayDriver"]
