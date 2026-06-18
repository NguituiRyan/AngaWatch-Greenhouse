"""``heat_stress`` scenario — midday over-temperature, vents needed.

The microclimate risk model raises HIGH ("vent now") when ``air_temp_c > 35``.
This scenario pushes the afternoon peak well above that threshold during the
hottest part of the day (roughly 11:00-16:00 local), pairs it with low RH (hot
dry air) and elevated soil temperature, and otherwise leaves the baseline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode

HOT_START_HOUR = 11.0
HOT_END_HOUR = 16.0


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object]:
    """Drive air_temp_c above 35 C during the midday heat window."""
    if not (HOT_START_HOUR <= hour <= HOT_END_HOUR):
        return reading

    # Peak ~13:30; bell over the window, topping out near 39 C.
    mid = (HOT_START_HOUR + HOT_END_HOUR) / 2.0
    closeness = 1.0 - abs(hour - mid) / ((HOT_END_HOUR - HOT_START_HOUR) / 2.0)
    air = 36.0 + 3.5 * max(0.0, closeness)  # 36..39.5
    reading["air_temp_c"] = round(min(45.0, air), 2)
    # Hot dry air: RH drops.
    reading["rh_pct"] = 35.0
    reading["leaf_wetness"] = 0.0
    # Soil heats up too.
    reading["soil_temp_c"] = 28.0
    return reading
