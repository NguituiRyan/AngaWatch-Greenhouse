"""Tests for the device simulator.

These assert that:

* every scenario yields schema-shaped dicts (exact contract field names) with
  in-range values, across a full simulated 24h;
* ``blight_dusk`` actually reaches the late-blight wet-hour condition
  (``rh >= 90`` with ``16 <= air_temp <= 26``) sustained for ~10 hours;
* ``offline`` drops messages during its gap;
* the ``Simulation`` core and the ``main()`` CLI (``--once`` / ``--count``)
  behave.

The simulator must run without the backend, so the telemetry contract is
re-declared here locally rather than imported from ``app.schemas.telemetry``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from simulator.config import SCENARIOS, SimulatorConfig
from simulator.node import VirtualNode, local_hour
from simulator.run import Simulation, main
from simulator.scenarios import SCENARIO_REGISTRY, get_scenario

# ---- Local copy of the telemetry contract (field name -> (min, max) or None) ----
# None bounds mean "no numeric bound" (still must be the right type). Mirrors
# app.schemas.telemetry.TelemetryIn.
REQUIRED_FIELDS = {"device_id", "ts"}
NUMERIC_BOUNDS: dict[str, tuple[float | None, float | None]] = {
    "air_temp_c": (-40, 80),
    "rh_pct": (0, 100),
    "leaf_wetness": (0, 100),
    "ppfd": (0, 4000),
    "co2_ppm": (0, 10000),
    "soil_moisture_pct": (0, 100),
    "soil_temp_c": (-40, 80),
    "npk_n_ppm": (0, 10000),
    "npk_p_ppm": (0, 10000),
    "npk_k_ppm": (0, 10000),
    "water_flow_l_total": (0, None),
    "water_flow_l_per_min": (0, 10000),
    "pheromone_count": (0, 100000),
    "battery_v": (0, 15),
    "rssi": (-150, 0),
}
ALL_FIELDS = REQUIRED_FIELDS | set(NUMERIC_BOUNDS)


def _assert_schema_shaped(reading: dict[str, object]) -> None:
    """Assert a reading has exactly the contract fields, all in range."""
    assert set(reading.keys()) == ALL_FIELDS, (
        f"unexpected fields: {set(reading.keys()) ^ ALL_FIELDS}"
    )
    assert isinstance(reading["device_id"], str) and reading["device_id"]
    assert isinstance(reading["ts"], datetime)
    for field, (lo, hi) in NUMERIC_BOUNDS.items():
        val = reading[field]
        assert isinstance(val, (int, float)), f"{field} not numeric: {val!r}"
        if lo is not None:
            assert val >= lo, f"{field}={val} below min {lo}"
        if hi is not None:
            assert val <= hi, f"{field}={val} above max {hi}"
    # Contract: pheromone_count and rssi are integers.
    assert isinstance(reading["pheromone_count"], int)
    assert isinstance(reading["rssi"], int)


def _day_of_readings(scenario_name: str, *, step_minutes: int = 30) -> list[dict[str, object]]:
    """Run one node through a full simulated 24h under a scenario.

    Returns the list of *emitted* readings (offline gaps are skipped). Uses a
    midnight-UTC start so we sweep the whole local day.
    """
    node = VirtualNode(device_id="GH1-NODE-01", seed=0)
    apply = get_scenario(scenario_name)
    start = datetime(2026, 6, 19, 0, 0, tzinfo=UTC)
    out: list[dict[str, object]] = []
    ts = start
    for _ in range(int(24 * 60 / step_minutes)):
        reading = node.baseline(ts)
        shaped = apply(reading, hour=local_hour(ts), node=node)
        if shaped is not None:
            out.append(shaped)
        ts += timedelta(minutes=step_minutes)
    return out


# --------------------------------------------------------------------------- #
# Schema / range coverage for every scenario
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("scenario_name", SCENARIOS)
def test_scenario_yields_in_range_schema_dicts(scenario_name: str) -> None:
    readings = _day_of_readings(scenario_name)
    # Every scenario except a fully-silent one must emit *something*.
    assert readings, f"{scenario_name} emitted nothing across 24h"
    for reading in readings:
        _assert_schema_shaped(reading)


def test_registry_covers_all_scenarios() -> None:
    assert set(SCENARIO_REGISTRY) == set(SCENARIOS)


def test_baseline_is_in_range() -> None:
    node = VirtualNode(device_id="GH1-NODE-01")
    ts = datetime(2026, 6, 19, 9, 0, tzinfo=UTC)
    _assert_schema_shaped(node.baseline(ts))


# --------------------------------------------------------------------------- #
# blight_dusk MUST reach the sustained wet-hour condition
# --------------------------------------------------------------------------- #
def _is_wet_hour(reading: dict[str, object]) -> bool:
    rh = reading["rh_pct"]
    air = reading["air_temp_c"]
    return rh >= 90 and 10 <= air <= 26  # type: ignore[operator]


def test_blight_dusk_reaches_wet_condition() -> None:
    """At least one reading hits rh>=90 with air in the blight band."""
    readings = _day_of_readings("blight_dusk", step_minutes=30)
    wet = [r for r in readings if _is_wet_hour(r)]
    assert wet, "blight_dusk never produced a wet-hour reading"
    # Every wet-hour reading must satisfy the risk-engine band (10..26 C, rh>=90).
    for r in wet:
        assert 10 <= r["air_temp_c"] <= 26  # type: ignore[operator]
        assert r["rh_pct"] >= 90  # type: ignore[operator]


def test_blight_dusk_sustains_about_ten_wet_hours() -> None:
    """The wet window must span ~10 consecutive simulated hours.

    We sample one reading per simulated hour through the dusk/overnight window
    and require at least 10 consecutive wet hours — the threshold the late
    blight HIGH rule needs (``high_hours=10``).
    """
    node = VirtualNode(device_id="GH1-NODE-01")
    apply = get_scenario("blight_dusk")
    # Start at 16:00 local. local = UTC + 3, so 13:00 UTC == 16:00 Nairobi.
    ts = datetime(2026, 6, 19, 13, 0, tzinfo=UTC)
    flags: list[bool] = []
    for _ in range(14):  # 16:00 -> 06:00 local
        reading = node.baseline(ts)
        shaped = apply(reading, hour=local_hour(ts), node=node)
        assert shaped is not None
        flags.append(_is_wet_hour(shaped))
        ts += timedelta(hours=1)

    # Longest run of consecutive wet hours.
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    assert best >= 10, f"longest sustained wet window was only {best}h (need >=10)"


# --------------------------------------------------------------------------- #
# Individual scenario behaviours
# --------------------------------------------------------------------------- #
def test_normal_does_not_sustain_blight_window() -> None:
    """The healthy baseline must NOT reach the 10h sustained wet window.

    Otherwise ``normal`` would spuriously trip the late-blight HIGH rule.
    """
    node = VirtualNode(device_id="GH1-NODE-01")
    apply = get_scenario("normal")
    ts = datetime(2026, 6, 19, 0, 0, tzinfo=UTC)
    flags: list[bool] = []
    for _ in range(24):
        shaped = apply(node.baseline(ts), hour=local_hour(ts), node=node)
        assert shaped is not None
        flags.append(_is_wet_hour(shaped))
        ts += timedelta(hours=1)
    best = run = 0
    for f in flags:
        run = run + 1 if f else 0
        best = max(best, run)
    assert best < 10, f"normal baseline sustained {best}h wet (would trip blight)"


def test_heat_stress_exceeds_vent_threshold() -> None:
    readings = _day_of_readings("heat_stress")
    assert any(r["air_temp_c"] > 35 for r in readings)  # type: ignore[operator]


def test_pest_surge_crosses_trap_threshold() -> None:
    readings = _day_of_readings("pest_surge")
    assert any(r["pheromone_count"] > 30 for r in readings)  # type: ignore[operator]


def test_nutrient_depletion_drops_below_targets() -> None:
    readings = _day_of_readings("nutrient_depletion")
    # Nitrogen should fall into the deficient band well below flowering targets.
    assert any(r["npk_n_ppm"] <= 55 for r in readings)  # type: ignore[operator]


def test_leak_produces_unscheduled_flow() -> None:
    """There is flow outside the 06:00-06:30 irrigation window."""
    node = VirtualNode(device_id="GH1-NODE-01")
    apply = get_scenario("leak")
    # 12:00 local == 09:00 UTC: far from the irrigation window.
    ts = datetime(2026, 6, 19, 9, 0, tzinfo=UTC)
    reading = apply(node.baseline(ts), hour=local_hour(ts), node=node)
    assert reading is not None
    assert reading["water_flow_l_per_min"] > 0  # type: ignore[operator]


def test_offline_drops_messages_during_gap() -> None:
    node = VirtualNode(device_id="GH1-NODE-01")
    apply = get_scenario("offline")
    # 10:00 local == 07:00 UTC: inside the 09:00-12:00 gap.
    gap_ts = datetime(2026, 6, 19, 7, 0, tzinfo=UTC)
    assert apply(node.baseline(gap_ts), hour=local_hour(gap_ts), node=node) is None
    # 15:00 local == 12:00 UTC: outside the gap.
    ok_ts = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)
    assert apply(node.baseline(ok_ts), hour=local_hour(ok_ts), node=node) is not None


def test_normal_is_pass_through() -> None:
    node = VirtualNode(device_id="GH1-NODE-01")
    ts = datetime(2026, 6, 19, 9, 0, tzinfo=UTC)
    base = node.baseline(ts)
    same = get_scenario("normal")(dict(base), hour=local_hour(ts), node=node)
    assert same == base


# --------------------------------------------------------------------------- #
# Simulation core + CLI
# --------------------------------------------------------------------------- #
def test_simulation_emits_per_node() -> None:
    config = SimulatorConfig(node_count=3, scenario="normal")
    sim = Simulation.from_config(config, start=datetime(2026, 6, 19, 9, 0, tzinfo=UTC))
    assert {n.device_id for n in sim.nodes} == {
        "GH1-NODE-01",
        "GH1-NODE-01-02",
        "GH1-NODE-01-03",
    }
    emitted = sim.tick()
    assert len(emitted) == 3
    for topic, reading in emitted:
        assert topic.startswith("farm/demo-coop/")
        assert topic.endswith("/telemetry")
        _assert_schema_shaped(reading)


def test_simulation_advances_clock_with_accel() -> None:
    config = SimulatorConfig(interval_seconds=5, time_accel=720)  # 5s -> 1h
    start = datetime(2026, 6, 19, 0, 0, tzinfo=UTC)
    sim = Simulation.from_config(config, start=start)
    sim.tick()
    assert sim.sim_time == start + timedelta(seconds=5 * 720)


def test_topic_format() -> None:
    config = SimulatorConfig(org_id="demo-coop")
    assert config.topic("GH1-NODE-01") == "farm/demo-coop/GH1-NODE-01/telemetry"


def test_main_once_dry_run_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--once", "--dry-run", "--scenario", "normal"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "farm/demo-coop/GH1-NODE-01/telemetry" in out


def test_main_count_dry_run(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["--count", "3", "--dry-run", "--scenario", "blight_dusk"])
    assert rc == 0
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "/telemetry" in ln]
    assert len(lines) == 3
