"""Weather provider determinism + poll_farm persistence."""

from __future__ import annotations

from sqlalchemy import func, select

from app.db.models import Farm, WeatherForecast, WeatherObservation
from app.weather.providers import (
    MockWeatherProvider,
    OpenWeatherProvider,
    build_provider,
)
from app.weather.service import poll_farm

_LAT, _LON = -0.303, 36.080  # Nakuru


async def test_mock_provider_is_deterministic():
    provider = MockWeatherProvider()
    a = await provider.current(_LAT, _LON)
    b = await provider.current(_LAT, _LON)
    assert a.air_temp_c == b.air_temp_c
    assert a.rh_pct == b.rh_pct
    assert a.source == "mock"
    assert isinstance(a.air_temp_c, float)


async def test_mock_forecast_length_and_shape():
    provider = MockWeatherProvider()
    points = await provider.forecast(_LAT, _LON, hours=12)
    assert len(points) == 12
    for p in points:
        assert p.air_temp_c is not None and p.rh_pct is not None
        assert 0.0 <= p.rain_prob <= 1.0
    # forecast points are strictly increasing in time
    times = [p.forecast_for for p in points]
    assert times == sorted(times)


async def test_mock_forecast_contains_blight_wet_window():
    """The overnight curve must cross the late-blight band so fusion has data."""
    provider = MockWeatherProvider()
    points = await provider.forecast(_LAT, _LON, hours=24)
    wet = [p for p in points if p.rh_pct >= 90 and 10 <= p.air_temp_c <= 26]
    assert wet, "mock forecast should include rh>=90 & 10<=temp<=26 hours"


async def test_poll_farm_persists_observation_and_forecast(db, org):
    farm = Farm(org_id=org.id, name="Nakuru Farm", latitude=_LAT, longitude=_LON)
    db.add(farm)
    await db.commit()
    await db.refresh(farm)

    await poll_farm(db, farm, provider=MockWeatherProvider(), forecast_hours=6)

    obs_count = await db.scalar(
        select(func.count())
        .select_from(WeatherObservation)
        .where(WeatherObservation.farm_id == farm.id)
    )
    fc_count = await db.scalar(
        select(func.count()).select_from(WeatherForecast).where(WeatherForecast.farm_id == farm.id)
    )
    assert obs_count == 1
    assert fc_count == 6


async def test_poll_farm_skips_without_location(db, org):
    farm = Farm(org_id=org.id, name="No GPS Farm")
    db.add(farm)
    await db.commit()
    await db.refresh(farm)

    await poll_farm(db, farm, provider=MockWeatherProvider())

    obs_count = await db.scalar(
        select(func.count())
        .select_from(WeatherObservation)
        .where(WeatherObservation.farm_id == farm.id)
    )
    assert obs_count == 0


def test_build_provider_falls_back_to_mock_without_key():
    # No API keys configured in the test environment -> mock fallback.
    assert isinstance(build_provider("openweather"), MockWeatherProvider)
    assert isinstance(build_provider("mock"), MockWeatherProvider)
    assert OpenWeatherProvider("k").name == "openweather"
