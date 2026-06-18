"""Concrete weather providers + a factory.

Three implementations are available:

* :class:`MockWeatherProvider` — fully **deterministic**. Temperature and
  relative humidity are derived from the hour-of-day via a diurnal sine wave; no
  RNG, no ``time.time()``/``Date.now``-style wall-clock reads enter the *values*.
  The curve is calibrated for Nakuru (Kenyan highlands, ~1900 m): mild afternoons
  (~25 C) and cool, humid nights. The overnight window deliberately crosses the
  late-blight wet-hour band (``rh >= 90`` while ``10 <= temp <= 26``) so the risk
  engine's forecast-fusion has realistic data to chew on.
* :class:`OpenWeatherProvider` / :class:`TomorrowIoProvider` — real HTTP clients
  built on ``httpx``. They are only constructed when the matching API key is
  configured; otherwise :func:`build_provider` falls back to the mock so the whole
  stack runs offline.

All providers return the plain dataclasses defined in :mod:`app.weather.base`.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.weather.base import ForecastPoint, WeatherNow, WeatherProvider

logger = get_logger(__name__)

# Local solar time matters for the diurnal curve; Nakuru sits in Africa/Nairobi.
_NAIROBI = ZoneInfo("Africa/Nairobi")

# ---- Mock climatology (field-calibratable placeholders for Nakuru) ----
# Daily mean temperature and the half-amplitude of the diurnal swing (deg C).
_TEMP_MEAN_C = 18.0
_TEMP_AMPLITUDE_C = 7.0
# The temperature peaks in mid-afternoon; expressed as an hour-of-day phase.
_TEMP_PEAK_HOUR = 14.0
# Relative humidity tracks the inverse of temperature: humid nights, drier days.
_RH_MEAN_PCT = 78.0
_RH_AMPLITUDE_PCT = 18.0
# Plausible static-ish ancillary fields.
_WIND_MEAN_MS = 2.4
_WIND_AMPLITUDE_MS = 1.6


def _diurnal_temp_c(hour_of_day: float) -> float:
    """Air temperature (deg C) for a fractional hour-of-day via a diurnal sine.

    Peaks at :data:`_TEMP_PEAK_HOUR` and troughs ~12 h later. Deterministic.
    """
    phase = 2.0 * math.pi * (hour_of_day - _TEMP_PEAK_HOUR) / 24.0
    return _TEMP_MEAN_C + _TEMP_AMPLITUDE_C * math.cos(phase)


def _diurnal_rh_pct(hour_of_day: float) -> float:
    """Relative humidity (%) for a fractional hour-of-day.

    Anti-phase with temperature so the pre-dawn hours are cool *and* humid — the
    exact regime late blight needs. Clamped to a sane ``[40, 99]`` band.
    """
    phase = 2.0 * math.pi * (hour_of_day - _TEMP_PEAK_HOUR) / 24.0
    rh = _RH_MEAN_PCT - _RH_AMPLITUDE_PCT * math.cos(phase)
    return max(40.0, min(99.0, rh))


def _diurnal_wind_ms(hour_of_day: float) -> float:
    """Wind speed (m/s); breezier by day, calm at night."""
    phase = 2.0 * math.pi * (hour_of_day - _TEMP_PEAK_HOUR) / 24.0
    return max(0.0, _WIND_MEAN_MS + _WIND_AMPLITUDE_MS * math.cos(phase))


def _fractional_hour(moment: datetime) -> float:
    """Local (Africa/Nairobi) fractional hour-of-day in ``[0, 24)``."""
    local = moment.astimezone(_NAIROBI)
    return local.hour + local.minute / 60.0 + local.second / 3600.0


def _rain_prob(rh_pct: float) -> float:
    """Crude rain probability: rises sharply once humidity is very high."""
    if rh_pct < 70.0:
        return 0.05
    return min(0.9, (rh_pct - 70.0) / 30.0)


class MockWeatherProvider(WeatherProvider):
    """Deterministic, offline-friendly provider for Nakuru-like conditions."""

    name = "mock"

    async def current(self, lat: float, lon: float) -> WeatherNow:
        # ``now`` is only used as the observation *timestamp*; the returned values
        # are a pure function of the hour-of-day, so two calls in the same hour
        # window agree and the provider is reproducible.
        now = datetime.now(UTC)
        hod = _fractional_hour(now)
        temp = _diurnal_temp_c(hod)
        rh = _diurnal_rh_pct(hod)
        return WeatherNow(
            observed_at=now,
            air_temp_c=round(temp, 2),
            rh_pct=round(rh, 2),
            wind_speed_ms=round(_diurnal_wind_ms(hod), 2),
            rainfall_mm=0.0,
            clouds_pct=round(min(100.0, max(0.0, rh - 20.0)), 1),
            source=self.name,
            raw={"lat": lat, "lon": lon, "hour_of_day": round(hod, 3)},
        )

    async def forecast(self, lat: float, lon: float, hours: int = 24) -> list[ForecastPoint]:
        # Anchor the forecast on the top of the current hour so points land on
        # clean hourly boundaries and the overnight wet window is reproducible.
        now = datetime.now(UTC)
        anchor = now.replace(minute=0, second=0, microsecond=0)
        points: list[ForecastPoint] = []
        for h in range(1, hours + 1):
            forecast_for = anchor + timedelta(hours=h)
            hod = _fractional_hour(forecast_for)
            temp = _diurnal_temp_c(hod)
            rh = _diurnal_rh_pct(hod)
            points.append(
                ForecastPoint(
                    forecast_for=forecast_for,
                    air_temp_c=round(temp, 2),
                    rh_pct=round(rh, 2),
                    rain_prob=round(_rain_prob(rh), 3),
                    rainfall_mm=0.0,
                    wind_speed_ms=round(_diurnal_wind_ms(hod), 2),
                    source=self.name,
                )
            )
        return points


class OpenWeatherProvider(WeatherProvider):
    """OpenWeather 'One Call' style client (guarded on an API key)."""

    name = "openweather"
    _CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
    _FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def current(self, lat: float, lon: float) -> WeatherNow:
        params = {"lat": lat, "lon": lon, "appid": self._api_key, "units": "metric"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self._CURRENT_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        main = data.get("main", {})
        wind = data.get("wind", {})
        rain = data.get("rain", {})
        clouds = data.get("clouds", {})
        return WeatherNow(
            observed_at=datetime.now(UTC),
            air_temp_c=main.get("temp"),
            rh_pct=main.get("humidity"),
            wind_speed_ms=wind.get("speed"),
            rainfall_mm=rain.get("1h", 0.0),
            clouds_pct=clouds.get("all"),
            source=self.name,
            raw=data,
        )

    async def forecast(self, lat: float, lon: float, hours: int = 24) -> list[ForecastPoint]:
        params = {"lat": lat, "lon": lon, "appid": self._api_key, "units": "metric"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(self._FORECAST_URL, params=params)
            resp.raise_for_status()
            data = resp.json()
        points: list[ForecastPoint] = []
        # OpenWeather free forecast is 3-hourly; expose up to ``ceil(hours/3)`` slots.
        max_slots = max(1, math.ceil(hours / 3))
        for entry in data.get("list", [])[:max_slots]:
            main = entry.get("main", {})
            wind = entry.get("wind", {})
            rain = entry.get("rain", {})
            points.append(
                ForecastPoint(
                    forecast_for=datetime.fromtimestamp(entry["dt"], tz=UTC),
                    air_temp_c=main.get("temp"),
                    rh_pct=main.get("humidity"),
                    rain_prob=entry.get("pop"),
                    rainfall_mm=rain.get("3h", 0.0),
                    wind_speed_ms=wind.get("speed"),
                    source=self.name,
                )
            )
        return points


class TomorrowIoProvider(WeatherProvider):
    """Tomorrow.io client (guarded on an API key)."""

    name = "tomorrowio"
    _BASE_URL = "https://api.tomorrow.io/v4/weather"

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    async def current(self, lat: float, lon: float) -> WeatherNow:
        params = {"location": f"{lat},{lon}", "apikey": self._api_key, "units": "metric"}
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._BASE_URL}/realtime", params=params)
            resp.raise_for_status()
            data = resp.json()
        values = data.get("data", {}).get("values", {})
        return WeatherNow(
            observed_at=datetime.now(UTC),
            air_temp_c=values.get("temperature"),
            rh_pct=values.get("humidity"),
            wind_speed_ms=values.get("windSpeed"),
            rainfall_mm=values.get("rainAccumulation", 0.0),
            clouds_pct=values.get("cloudCover"),
            source=self.name,
            raw=data,
        )

    async def forecast(self, lat: float, lon: float, hours: int = 24) -> list[ForecastPoint]:
        params = {
            "location": f"{lat},{lon}",
            "apikey": self._api_key,
            "units": "metric",
            "timesteps": "1h",
        }
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{self._BASE_URL}/forecast", params=params)
            resp.raise_for_status()
            data = resp.json()
        hourly = data.get("timelines", {}).get("hourly", [])
        points: list[ForecastPoint] = []
        for entry in hourly[:hours]:
            values = entry.get("values", {})
            points.append(
                ForecastPoint(
                    forecast_for=datetime.fromisoformat(entry["time"].replace("Z", "+00:00")),
                    air_temp_c=values.get("temperature"),
                    rh_pct=values.get("humidity"),
                    rain_prob=(values.get("precipitationProbability") or 0.0) / 100.0,
                    rainfall_mm=values.get("rainAccumulation", 0.0),
                    wind_speed_ms=values.get("windSpeed"),
                    source=self.name,
                )
            )
        return points


def build_provider(name: str) -> WeatherProvider:
    """Construct a provider by name, falling back to the mock when unconfigured.

    ``name`` is typically ``settings.weather_provider``. Real providers require
    their API key; if it is missing we log and return :class:`MockWeatherProvider`
    so the stack stays fully offline-capable.
    """
    normalized = (name or "mock").strip().lower()

    if normalized == "openweather":
        if settings.openweather_api_key:
            return OpenWeatherProvider(settings.openweather_api_key)
        logger.warning("weather.provider.fallback", requested="openweather", reason="no_api_key")
        return MockWeatherProvider()

    if normalized == "tomorrowio":
        if settings.tomorrowio_api_key:
            return TomorrowIoProvider(settings.tomorrowio_api_key)
        logger.warning("weather.provider.fallback", requested="tomorrowio", reason="no_api_key")
        return MockWeatherProvider()

    if normalized != "mock":
        logger.warning("weather.provider.unknown", requested=normalized)
    return MockWeatherProvider()
