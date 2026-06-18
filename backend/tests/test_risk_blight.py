"""Unit tests for the late-blight wet-hour model (pure, synthetic ReadingPoints)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import ReadingPoint, RiskContext, WeatherPoint
from app.risk_engine.models.blight import BlightRiskModel

NOW = datetime(2026, 6, 19, 6, 0, tzinfo=UTC)


def _ctx(readings: list[ReadingPoint], forecast: list[WeatherPoint] | None = None) -> RiskContext:
    return RiskContext(
        org_id="org",
        greenhouse_id="gh",
        now=NOW,
        readings=readings,
        params={},
        forecast=forecast or [],
    )


def _hourly(specs: list[tuple[float, float]], start: datetime | None = None) -> list[ReadingPoint]:
    """Build ascending hourly readings from (rh, temp) tuples ending at NOW."""
    start = start or (NOW - timedelta(hours=len(specs) - 1))
    return [
        ReadingPoint(time=start + timedelta(hours=i), rh_pct=rh, air_temp_c=temp)
        for i, (rh, temp) in enumerate(specs)
    ]


def test_ten_wet_hours_is_high() -> None:
    # 10 consecutive hours of rh>=90 and temp in 16..26 -> HIGH.
    readings = _hourly([(95.0, 20.0)] * 10)
    result = BlightRiskModel().evaluate(_ctx(readings))

    assert result is not None
    assert result.model_type is RiskModelType.LATE_BLIGHT
    assert result.level is RiskLevel.HIGH
    assert result.details["wet_hours"] == 10
    assert result.details["effective_wet_hours"] >= 10
    assert result.score == 1.0
    assert result.is_actionable
    assert "ventilate" in result.action_code


def test_seven_wet_hours_is_medium() -> None:
    # 7 consecutive wet hours -> between med_hours (6) and high_hours (10) => MEDIUM.
    readings = _hourly([(92.0, 18.0)] * 7)
    result = BlightRiskModel().evaluate(_ctx(readings))

    assert result is not None
    assert result.level is RiskLevel.MEDIUM
    assert result.details["wet_hours"] == 7
    assert result.is_actionable


def test_no_signal_when_dry() -> None:
    # Humidity below threshold -> no wet hours -> no verdict.
    readings = _hourly([(70.0, 20.0)] * 12)
    assert BlightRiskModel().evaluate(_ctx(readings)) is None


def test_no_signal_when_too_cold() -> None:
    # RH high but temperature below temp_min (10) -> not a wet hour.
    readings = _hourly([(95.0, 8.0)] * 12)
    assert BlightRiskModel().evaluate(_ctx(readings)) is None


def test_no_signal_when_too_hot() -> None:
    # RH high but temperature above temp_max (26) -> not a wet hour.
    readings = _hourly([(95.0, 30.0)] * 12)
    assert BlightRiskModel().evaluate(_ctx(readings)) is None


def test_only_trailing_run_counts() -> None:
    # A dry hour breaks the run: 4 dry + 5 wet at the end => 5 wet hours, below med.
    readings = _hourly([(70.0, 20.0)] * 4 + [(95.0, 20.0)] * 5)
    assert BlightRiskModel().evaluate(_ctx(readings)) is None


def test_below_medium_threshold_no_verdict() -> None:
    # 5 wet hours (< med_hours 6) and no forecast -> None.
    readings = _hourly([(95.0, 20.0)] * 5)
    assert BlightRiskModel().evaluate(_ctx(readings)) is None


def test_forecast_fusion_escalates_medium_to_high() -> None:
    # 7 observed wet hours (MEDIUM on its own) + 4 forecast wet hours overnight
    # => effective 11 >= high_hours => HIGH, fused flag set.
    readings = _hourly([(92.0, 18.0)] * 7)
    forecast = [
        WeatherPoint(forecast_for=NOW + timedelta(hours=i), rh_pct=95.0, air_temp_c=18.0)
        for i in range(1, 5)
    ]
    result = BlightRiskModel().evaluate(_ctx(readings, forecast))

    assert result is not None
    assert result.level is RiskLevel.HIGH
    assert result.details["forecast_fused"] is True
    assert result.details["forecast_wet_hours"] == 4


def test_forecast_alone_below_medium_is_none() -> None:
    # No observed wet hours, only 3 forecast wet hours (< med 6) -> None.
    readings = _hourly([(70.0, 20.0)] * 6)
    forecast = [
        WeatherPoint(forecast_for=NOW + timedelta(hours=i), rh_pct=95.0, air_temp_c=18.0)
        for i in range(1, 4)
    ]
    assert BlightRiskModel().evaluate(_ctx(readings, forecast)) is None


def test_empty_readings_returns_none() -> None:
    assert BlightRiskModel().evaluate(_ctx([])) is None
