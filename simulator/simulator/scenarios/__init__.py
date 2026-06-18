"""Scenario registry.

Each scenario is a callable that takes the node's baseline reading and reshapes
it to drive one risk condition. The signature is::

    def apply(reading: dict, *, hour: float, node: VirtualNode) -> dict | None

where ``hour`` is the Africa/Nairobi local hour-of-day (0..24) and ``node`` is
the :class:`~simulator.node.VirtualNode` (for stateful scenarios). Returning
``None`` means *drop this message* (used by the ``offline`` scenario to punch a
gap in the stream).

The reshaped dict keeps the exact telemetry contract field names; only values
change. Scenarios must keep every value within
``app.schemas.telemetry.TelemetryIn`` bounds.
"""

from __future__ import annotations

from collections.abc import Callable

from simulator.scenarios import (
    blight_dusk,
    heat_stress,
    leak,
    normal,
    nutrient_depletion,
    offline,
    pest_surge,
)

# A scenario function: (reading, *, hour, node) -> reading | None
Scenario = Callable[..., "dict[str, object] | None"]

SCENARIO_REGISTRY: dict[str, Scenario] = {
    "normal": normal.apply,
    "blight_dusk": blight_dusk.apply,
    "heat_stress": heat_stress.apply,
    "pest_surge": pest_surge.apply,
    "nutrient_depletion": nutrient_depletion.apply,
    "leak": leak.apply,
    "offline": offline.apply,
}


def get_scenario(name: str) -> Scenario:
    """Look up a scenario function by name, defaulting to ``normal``."""
    return SCENARIO_REGISTRY.get(name, normal.apply)


__all__ = ["SCENARIO_REGISTRY", "Scenario", "get_scenario"]
