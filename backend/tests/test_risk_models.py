"""Unit tests for the Tuta, microclimate, nutrient and water models."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import ReadingPoint, RiskContext
from app.risk_engine.models.microclimate import MicroclimateRiskModel
from app.risk_engine.models.nutrient import NutrientRiskModel
from app.risk_engine.models.tuta import TutaRiskModel
from app.risk_engine.models.water import WaterRiskModel

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=UTC)


def _ctx(readings, **kw) -> RiskContext:
    return RiskContext(
        org_id="org",
        greenhouse_id="gh",
        now=NOW,
        readings=readings,
        params=kw.pop("params", {}),
        **kw,
    )


# --------------------------- Tuta absoluta ---------------------------------
def test_tuta_generation_crossed_is_high() -> None:
    # Constant 30C for 30 days at base 10 => 20 DD/day * 30 = 600 DD >> 208.
    start = NOW - timedelta(days=30)
    readings = [
        ReadingPoint(time=start + timedelta(days=d), air_temp_c=30.0, pheromone_count=0)
        for d in range(31)
    ]
    result = TutaRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.model_type is RiskModelType.TUTA_ABSOLUTA
    assert result.level is RiskLevel.HIGH
    assert result.details["generation_crossed"] is True
    assert result.details["degree_days"] > 208


def test_tuta_pheromone_elevates_to_high() -> None:
    # Low heat (no generation), but a big trap catch => HIGH on trap signal.
    start = NOW - timedelta(days=2)
    readings = [
        ReadingPoint(time=start + timedelta(hours=h), air_temp_c=12.0, pheromone_count=45)
        for h in range(0, 49, 6)
    ]
    result = TutaRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.level is RiskLevel.HIGH
    assert result.details["trap_elevated"] is True
    assert result.details["max_pheromone_count"] == 45


def test_tuta_no_signal_when_cool_and_no_traps() -> None:
    start = NOW - timedelta(days=2)
    readings = [
        ReadingPoint(time=start + timedelta(hours=h), air_temp_c=11.0, pheromone_count=2)
        for h in range(0, 49, 6)
    ]
    assert TutaRiskModel().evaluate(_ctx(readings)) is None


# --------------------------- Microclimate ----------------------------------
def test_microclimate_overheat_high() -> None:
    readings = [ReadingPoint(time=NOW, air_temp_c=38.0, rh_pct=50.0, soil_moisture_pct=40.0)]
    result = MicroclimateRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.level is RiskLevel.HIGH
    assert result.action_code == "vent_now"


def test_microclimate_humidity_medium() -> None:
    readings = [ReadingPoint(time=NOW, air_temp_c=24.0, rh_pct=90.0, soil_moisture_pct=40.0)]
    result = MicroclimateRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.level is RiskLevel.MEDIUM
    assert result.action_code == "reduce_humidity"


def test_microclimate_dry_soil_medium() -> None:
    readings = [ReadingPoint(time=NOW, air_temp_c=24.0, rh_pct=60.0, soil_moisture_pct=20.0)]
    result = MicroclimateRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.level is RiskLevel.MEDIUM
    assert result.action_code == "irrigate"


def test_microclimate_no_signal() -> None:
    readings = [ReadingPoint(time=NOW, air_temp_c=24.0, rh_pct=60.0, soil_moisture_pct=40.0)]
    assert MicroclimateRiskModel().evaluate(_ctx(readings)) is None


# --------------------------- Nutrient --------------------------------------
def test_nutrient_deficit_detected() -> None:
    readings = [
        ReadingPoint(time=NOW, npk_n_ppm=80.0, npk_p_ppm=50.0, npk_k_ppm=200.0),
    ]
    targets = {"n": 150.0, "p": 50.0, "k": 250.0}
    result = NutrientRiskModel().evaluate(
        _ctx(readings, crop_stage="flowering", extra={"npk_targets": targets})
    )
    assert result is not None
    assert result.model_type is RiskModelType.NUTRIENT
    # N is ~47% below target -> severe -> HIGH.
    assert result.level is RiskLevel.HIGH
    deficient = {d["nutrient"] for d in result.details["deficits"]}
    assert "n" in deficient
    assert "p" not in deficient  # P meets target


def test_nutrient_no_targets_no_signal() -> None:
    readings = [ReadingPoint(time=NOW, npk_n_ppm=10.0)]
    assert NutrientRiskModel().evaluate(_ctx(readings)) is None


def test_nutrient_on_target_no_signal() -> None:
    readings = [ReadingPoint(time=NOW, npk_n_ppm=150.0, npk_p_ppm=50.0, npk_k_ppm=250.0)]
    targets = {"n": 150.0, "p": 50.0, "k": 250.0}
    assert NutrientRiskModel().evaluate(_ctx(readings, extra={"npk_targets": targets})) is None


# --------------------------- Water -----------------------------------------
def test_water_leak_detection_high() -> None:
    start = NOW - timedelta(hours=2)
    readings = [
        ReadingPoint(
            time=start + timedelta(minutes=m),
            soil_moisture_pct=45.0,
            water_flow_l_per_min=3.0,
            water_flow_l_total=100.0 + m,
        )
        for m in range(0, 121, 30)
    ]
    result = WaterRiskModel().evaluate(_ctx(readings, extra={"irrigation_scheduled": False}))
    assert result is not None
    assert result.level is RiskLevel.HIGH
    assert result.action_code == "check_leak"
    assert result.details["situation"] == "leak"
    assert result.details["water_used_l"] == 120.0


def test_water_irrigate_when_dry_no_flow() -> None:
    readings = [
        ReadingPoint(time=NOW, soil_moisture_pct=18.0, water_flow_l_per_min=0.0),
    ]
    result = WaterRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.action_code == "irrigate"
    assert result.details["situation"] == "irrigate"


def test_water_critical_dry_is_high() -> None:
    readings = [ReadingPoint(time=NOW, soil_moisture_pct=10.0, water_flow_l_per_min=0.0)]
    result = WaterRiskModel().evaluate(_ctx(readings))
    assert result is not None
    assert result.level is RiskLevel.HIGH


def test_water_scheduled_flow_is_not_a_leak() -> None:
    readings = [
        ReadingPoint(time=NOW, soil_moisture_pct=45.0, water_flow_l_per_min=3.0),
    ]
    assert WaterRiskModel().evaluate(_ctx(readings, extra={"irrigation_scheduled": True})) is None


def test_registry_has_all_five_models() -> None:
    from app.risk_engine import models as _models  # noqa: F401  (register)
    from app.risk_engine.base import registry

    types = {m.model_type for m in registry.all()}
    assert types == {
        RiskModelType.LATE_BLIGHT,
        RiskModelType.TUTA_ABSOLUTA,
        RiskModelType.MICROCLIMATE,
        RiskModelType.NUTRIENT,
        RiskModelType.WATER,
    }
