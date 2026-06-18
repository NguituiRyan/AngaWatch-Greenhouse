"""``nutrient_depletion`` scenario — NPK drawn below crop-stage targets.

The nutrient risk model compares the latest NPK readings against crop-stage
targets and recommends fertigation on a deficit. This scenario forces the
node's nutrient state low (nitrogen and potassium especially) and keeps
draining it on every tick so the deficit deepens over the run.

Stateful: it pulls down the node's ``npk_*`` fields directly so successive
readings reflect a worsening deficit rather than a flat low value.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode

# Deficient floors (ppm) — clearly below typical tomato flowering targets.
N_FLOOR = 35.0
P_FLOOR = 12.0
K_FLOOR = 60.0
DRAIN_PER_TICK = 0.5


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object]:
    """Pin NPK into a deficient band and keep draining it."""
    node.npk_n_ppm = max(N_FLOOR, node.npk_n_ppm - DRAIN_PER_TICK)
    node.npk_p_ppm = max(P_FLOOR, node.npk_p_ppm - DRAIN_PER_TICK * 0.4)
    node.npk_k_ppm = max(K_FLOOR, node.npk_k_ppm - DRAIN_PER_TICK)

    # Snap into the deficient band immediately on first apply so a short demo
    # run is already below target.
    node.npk_n_ppm = min(node.npk_n_ppm, 55.0)
    node.npk_p_ppm = min(node.npk_p_ppm, 18.0)
    node.npk_k_ppm = min(node.npk_k_ppm, 90.0)

    reading["npk_n_ppm"] = round(node.npk_n_ppm, 1)
    reading["npk_p_ppm"] = round(node.npk_p_ppm, 1)
    reading["npk_k_ppm"] = round(node.npk_k_ppm, 1)
    return reading
