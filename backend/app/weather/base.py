"""Weather provider interface + a factory selecting the impl from settings.

Concrete providers live in ``app.weather.providers``. The factory below is a
late-binding import so providers can register without a circular import.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.core.config import settings


@dataclass(slots=True)
class WeatherNow:
    observed_at: datetime
    air_temp_c: float | None = None
    rh_pct: float | None = None
    wind_speed_ms: float | None = None
    rainfall_mm: float | None = None
    clouds_pct: float | None = None
    source: str = "unknown"
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class ForecastPoint:
    forecast_for: datetime
    air_temp_c: float | None = None
    rh_pct: float | None = None
    rain_prob: float | None = None
    rainfall_mm: float | None = None
    wind_speed_ms: float | None = None
    source: str = "unknown"


class WeatherProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def current(self, lat: float, lon: float) -> WeatherNow:
        raise NotImplementedError

    @abstractmethod
    async def forecast(self, lat: float, lon: float, hours: int = 24) -> list[ForecastPoint]:
        raise NotImplementedError


def get_provider(name: str | None = None) -> WeatherProvider:
    """Resolve the configured provider. Defaults to ``settings.weather_provider``."""
    from app.weather.providers import build_provider

    return build_provider(name or settings.weather_provider)
