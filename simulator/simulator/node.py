"""The virtual sensor node — diurnal baseline physics for one greenhouse node.

A :class:`VirtualNode` owns the slowly-evolving state of one node (cumulative
water flow, NPK depletion, battery drain, pheromone trap count) and turns a
simulated wall-clock time into a *baseline* telemetry reading following
realistic diurnal curves for a Kenyan highland greenhouse near Nakuru
(roughly equatorial, ~1900 m elevation, mild days / cool nights).

Scenarios (see :mod:`simulator.scenarios`) take this baseline reading and
reshape it to drive a specific risk condition. The node never raises: every
value it emits is within the physical bounds of
``app.schemas.telemetry.TelemetryIn``.

All field names match the telemetry contract exactly:
``device_id, ts, air_temp_c, rh_pct, leaf_wetness, soil_moisture_pct,
soil_temp_c, ppfd, co2_ppm, npk_n_ppm, npk_p_ppm, npk_k_ppm,
water_flow_l_total, water_flow_l_per_min, pheromone_count, battery_v, rssi``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime

# Local solar timezone offset for Nakuru (Africa/Nairobi = UTC+3). The diurnal
# curves are driven by *local* hour-of-day so dusk/overnight line up with the
# risk engine, which computes dusk/quiet-hours in Africa/Nairobi.
NAIROBI_UTC_OFFSET_HOURS = 3.0


def local_hour(ts: datetime) -> float:
    """Return fractional local hour-of-day (0..24) for an aware/naive UTC ts.

    Naive datetimes are treated as UTC. The result is the Africa/Nairobi local
    hour, which is what every diurnal curve below is phased against.
    """
    # Seconds since midnight UTC.
    utc_seconds = ts.hour * 3600 + ts.minute * 60 + ts.second + ts.microsecond / 1e6
    local_seconds = (utc_seconds + NAIROBI_UTC_OFFSET_HOURS * 3600.0) % 86400.0
    return local_seconds / 3600.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(slots=True)
class VirtualNode:
    """One simulated sensor node with evolving state.

    Parameters
    ----------
    device_id:
        The device_uid string used in the telemetry payload and MQTT topic.
    seed:
        Per-node phase offset so multiple nodes in one greenhouse don't emit
        identical values. Deterministic: no RNG is used.
    """

    device_id: str
    seed: int = 0

    # ---- evolving state ----
    water_flow_l_total: float = 0.0
    pheromone_count: int = 0
    battery_v: float = 4.05
    # Soil moisture and NPK drift slowly; seeded so they are stateful across
    # successive readings (irrigation/fertigation events refill them).
    soil_moisture_pct: float = 62.0
    npk_n_ppm: float = 140.0
    npk_p_ppm: float = 48.0
    npk_k_ppm: float = 210.0
    _ticks: int = field(default=0, repr=False)

    # Small deterministic per-node phase wobble (radians).
    @property
    def _phase(self) -> float:
        return (self.seed % 7) * 0.13

    def _wave(self, hour: float, peak_hour: float, span: float = 12.0) -> float:
        """A 0..1 cosine bump peaking at ``peak_hour`` (local), period 24h."""
        # cos peaks (=1) when (hour - peak_hour) == 0.
        angle = (hour - peak_hour) / span * math.pi + self._phase
        return (math.cos(angle) + 1.0) / 2.0

    def baseline(self, ts: datetime) -> dict[str, object]:
        """Produce the baseline (scenario-free) telemetry dict for ``ts``.

        This advances the node's slow state by one tick (battery drain, a touch
        of soil-moisture dry-down, a small pheromone trickle) and returns a
        fully-populated reading following diurnal curves.
        """
        self._ticks += 1
        hour = local_hour(ts)

        # --- Air temperature: cool nights (~14C at 05:00), warm afternoon
        #     (~28C at 15:00). ---
        temp_bump = self._wave(hour, peak_hour=15.0)
        air_temp_c = 14.0 + 14.0 * temp_bump  # 14..28

        # --- Relative humidity is anti-correlated with temperature: humid and
        #     cool overnight (~92%), drier mid-afternoon (~55%). ---
        rh_pct = 92.0 - 37.0 * temp_bump  # 55..92

        # --- Soil temperature lags air temperature and is damped. ---
        soil_temp_c = 17.0 + 6.0 * self._wave(hour, peak_hour=17.0)  # 17..23

        # --- PPFD: zero at night, bell-shaped over the day, peak ~13:00. ---
        ppfd = self._daylight_ppfd(hour)

        # --- Leaf wetness tracks high RH / condensation overnight. ---
        leaf_wetness = _clamp((rh_pct - 70.0) * 3.0, 0.0, 100.0)

        # --- CO2: elevated overnight (respiration, vents shut ~700ppm),
        #     drawn down by photosynthesis in daylight (~420ppm). ---
        co2_ppm = 420.0 + 280.0 * (1.0 - self._daylight_fraction(hour))

        # --- Soil moisture: slow dry-down with a morning irrigation refill at
        #     ~06:00 local. ---
        self._advance_soil(hour)

        # --- NPK: very slow depletion; refilled on fertigation in scenarios. ---
        self._advance_npk()

        # --- Water flow: a scheduled morning irrigation pulse ~06:00-06:30. ---
        flow_per_min = self._irrigation_flow(hour)
        self.water_flow_l_total += flow_per_min * (1.0 / 60.0)

        # --- Pheromone trap: slow ambient trickle. ---
        if self._ticks % 20 == 0:
            self.pheromone_count += 1

        # --- Battery: gentle drain, solar top-up during daylight. ---
        self._advance_battery(hour)

        # --- RSSI: stable link with a tiny deterministic wobble. ---
        rssi = int(-65 + 4 * math.sin(self._ticks * 0.3 + self._phase))

        return {
            "device_id": self.device_id,
            "ts": ts,
            "air_temp_c": round(air_temp_c, 2),
            "rh_pct": round(rh_pct, 2),
            "leaf_wetness": round(leaf_wetness, 2),
            "soil_moisture_pct": round(self.soil_moisture_pct, 2),
            "soil_temp_c": round(soil_temp_c, 2),
            "ppfd": round(ppfd, 1),
            "co2_ppm": round(co2_ppm, 1),
            "npk_n_ppm": round(self.npk_n_ppm, 1),
            "npk_p_ppm": round(self.npk_p_ppm, 1),
            "npk_k_ppm": round(self.npk_k_ppm, 1),
            "water_flow_l_total": round(self.water_flow_l_total, 3),
            "water_flow_l_per_min": round(flow_per_min, 3),
            "pheromone_count": int(self.pheromone_count),
            "battery_v": round(self.battery_v, 3),
            "rssi": int(_clamp(rssi, -120, -1)),
        }

    # ------------------------------------------------------------------ #
    # Internal diurnal helpers
    # ------------------------------------------------------------------ #
    def _daylight_fraction(self, hour: float) -> float:
        """0 at night, 1 at solar noon — drives photosynthesis-linked terms."""
        if hour < 6.0 or hour > 18.0:
            return 0.0
        # Half-sine from sunrise (06:00) to sunset (18:00).
        return math.sin((hour - 6.0) / 12.0 * math.pi)

    def _daylight_ppfd(self, hour: float) -> float:
        """Photosynthetic photon flux density, peak ~1500 umol/m2/s at noon."""
        return 1500.0 * self._daylight_fraction(hour)

    def _advance_soil(self, hour: float) -> None:
        # Morning irrigation refill window 06:00-06:30 local.
        if 6.0 <= hour < 6.5:
            self.soil_moisture_pct = _clamp(self.soil_moisture_pct + 4.0, 0.0, 75.0)
        else:
            # Gentle dry-down, faster in the heat of the afternoon.
            dry = 0.05 + 0.05 * self._daylight_fraction(hour)
            self.soil_moisture_pct = _clamp(self.soil_moisture_pct - dry, 5.0, 75.0)

    def _advance_npk(self) -> None:
        self.npk_n_ppm = _clamp(self.npk_n_ppm - 0.05, 0.0, 10000.0)
        self.npk_p_ppm = _clamp(self.npk_p_ppm - 0.02, 0.0, 10000.0)
        self.npk_k_ppm = _clamp(self.npk_k_ppm - 0.06, 0.0, 10000.0)

    def _irrigation_flow(self, hour: float) -> float:
        # Scheduled morning irrigation pulse ~06:00-06:30 local.
        if 6.0 <= hour < 6.5:
            return 8.0
        return 0.0

    def _advance_battery(self, hour: float) -> None:
        # Drain a touch each tick; solar charge during daylight keeps it healthy.
        solar = self._daylight_fraction(hour)
        self.battery_v = _clamp(self.battery_v - 0.0008 + 0.0015 * solar, 3.4, 4.2)
