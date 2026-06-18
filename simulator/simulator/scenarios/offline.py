"""``offline`` scenario — the node goes dark for a stretch (dropped messages).

Returning ``None`` from a scenario tells the run loop to publish nothing for
that tick, simulating a node that lost power / connectivity. This drives the
"device offline / stale data" path: the backend stops seeing ``last_seen_at``
updates for the gap.

The gap is defined on the local hour-of-day so it is deterministic and
reproducible: by default the node is silent from 09:00 to 12:00 local. Outside
the gap the (slightly battery-degraded) baseline reading is published normally.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode

# Local-time outage window (node drops messages): 09:00 -> 12:00.
GAP_START_HOUR = 9.0
GAP_END_HOUR = 12.0


def in_gap(hour: float) -> bool:
    """True when the node should be silent (drop the message)."""
    return GAP_START_HOUR <= hour < GAP_END_HOUR


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object] | None:
    """Drop the message during the outage window; otherwise pass through."""
    if in_gap(hour):
        return None
    # Just outside the gap, show a depressed battery to hint at the cause.
    node.battery_v = max(3.4, node.battery_v - 0.002)
    reading["battery_v"] = round(node.battery_v, 3)
    return reading
