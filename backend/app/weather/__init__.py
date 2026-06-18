"""Weather fusion: a provider interface (OpenWeather / Tomorrow.io / mock) + poller."""

from app.weather.base import (
    ForecastPoint,
    WeatherNow,
    WeatherProvider,
    get_provider,
)

__all__ = ["ForecastPoint", "WeatherNow", "WeatherProvider", "get_provider"]
