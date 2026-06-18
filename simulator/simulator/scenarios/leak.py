"""``leak`` scenario — water flowing with no scheduled irrigation.

The water risk model flags a leak (HIGH) when there is flow
(``water_flow_l_per_min`` > 0) with no scheduled irrigation. This scenario
injects a steady unscheduled flow *outside* the morning irrigation window and
keeps accumulating the total, while soil moisture creeps up abnormally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode

# Litres/min of the (unscheduled) leak.
LEAK_FLOW_L_PER_MIN = 3.5
# The legitimate morning irrigation window — we only "leak" outside it.
IRRIGATION_START = 6.0
IRRIGATION_END = 6.5


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object]:
    """Inject continuous unscheduled flow outside the irrigation window."""
    if IRRIGATION_START <= hour < IRRIGATION_END:
        # During the scheduled window the baseline flow is expected; leave it.
        return reading

    # Unscheduled flow: pump/valve stuck open or a burst line.
    node.water_flow_l_total += LEAK_FLOW_L_PER_MIN * (1.0 / 60.0)
    reading["water_flow_l_per_min"] = LEAK_FLOW_L_PER_MIN
    reading["water_flow_l_total"] = round(node.water_flow_l_total, 3)
    # Saturating soil from the constant flow.
    node.soil_moisture_pct = min(75.0, node.soil_moisture_pct + 0.3)
    reading["soil_moisture_pct"] = round(node.soil_moisture_pct, 2)
    return reading
