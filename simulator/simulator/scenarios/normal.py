"""``normal`` scenario — healthy greenhouse, no risk should fire.

The baseline node curves are already calibrated to a healthy day, so this
scenario is a pass-through. It exists as the explicit "nothing wrong" control
for the demo and tests.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object]:
    """Return the baseline reading unchanged."""
    return reading
