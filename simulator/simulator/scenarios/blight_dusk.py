"""``blight_dusk`` scenario — late-blight wet-window forming overnight.

This is the marquee scenario: it MUST drive the late-blight risk model to fire.
That model counts "wet hours" where ``rh_pct >= 90`` AND ``10 <= air_temp_c <= 26``;
``>= 10h`` sustained -> HIGH ("ventilate now / apply preventive fungicide tonight").

So from dusk (~17:00 local) through the overnight hours into the early morning
(~03:00 local) we pin:

* ``rh_pct`` to >= 90 (saturated, condensing canopy),
* ``air_temp_c`` into the 16-26 C blight-favourable band,
* ``leaf_wetness`` high (free water on leaves).

That is a ~10-hour wet window straddling midnight, which is exactly the
sustained condition the risk engine needs. Outside that window the reading is
left as the healthy baseline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulator.node import VirtualNode

# Local-time wet window: 17:00 -> 03:00 next day (10 hours), straddling midnight.
WET_START_HOUR = 17.0
WET_END_HOUR = 3.0


def in_wet_window(hour: float) -> bool:
    """True if the local hour-of-day is inside the dusk->overnight wet window."""
    # Window wraps past midnight, so it's [17,24) OR [0,3).
    return hour >= WET_START_HOUR or hour < WET_END_HOUR


def apply(reading: dict[str, object], *, hour: float, node: VirtualNode) -> dict[str, object]:
    """Force the blight wet-window conditions during dusk/overnight hours."""
    if not in_wet_window(hour):
        return reading

    # Saturated, condensing canopy: RH pinned >= 90 (use 95 for headroom).
    reading["rh_pct"] = 95.0
    # Cool-but-mild blight band. Keep well inside 16-26: a touch warmer right
    # after dusk, settling to ~17 deep overnight, never escaping the band.
    if hour >= WET_START_HOUR:
        # 17:00 -> 24:00 : ease from ~22 down toward ~18.
        air = 22.0 - (hour - WET_START_HOUR) * 0.5
    else:
        # 00:00 -> 03:00 : coolest part of the night, ~17.5.
        air = 17.5
    reading["air_temp_c"] = round(max(16.0, min(26.0, air)), 2)
    # Free water on the leaves.
    reading["leaf_wetness"] = 100.0
    # Vents shut overnight -> CO2 climbs a bit; harmless but realistic.
    reading["co2_ppm"] = 720.0
    return reading
