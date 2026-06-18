"""``pest_surge`` scenario — Tuta absoluta pheromone-trap surge.

The Tuta absoluta risk model elevates pressure when ``pheromone_count`` exceeds
the trap threshold (default 30) and accumulates degree-days above a base temp.
This scenario ramps the pheromone trap catch on the node well past the
threshold and keeps daytime temperatures warm to accumulate degree-days.

It is stateful: the trap count climbs on every tick so a short run still
crosses the threshold quickly for the demo.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode

# How many moths each tick adds to the trap once the surge is "on".
SURGE_PER_TICK = 4
# Cap so we never blow past the telemetry contract bound (<= 100000).
SURGE_CAP = 5000


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object]:
    """Ramp pheromone_count past the trap threshold and warm the days."""
    # Mutate node state so the surge persists across ticks (stateful trap).
    node.pheromone_count = min(SURGE_CAP, node.pheromone_count + SURGE_PER_TICK)
    reading["pheromone_count"] = int(node.pheromone_count)

    # Warm but non-lethal days speed degree-day accumulation (favourable for
    # the pest). Bump the daytime air temp a couple of degrees.
    air = float(reading.get("air_temp_c") or 20.0)
    if 8.0 <= hour <= 18.0:
        air = min(34.0, air + 3.0)
        reading["air_temp_c"] = round(air, 2)
    return reading
