"""Weather polling service: fetch + persist observations and forecasts per farm.

Feeds the late-blight (forecast fusion) and water/irrigation models. Async because
the real providers use ``httpx.AsyncClient``; the Celery task wraps this with
``asyncio.run`` over an async session.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.db.models import Farm, WeatherForecast, WeatherObservation
from app.weather.base import WeatherProvider
from app.weather.providers import build_provider

logger = get_logger(__name__)


async def poll_farm(
    db: AsyncSession,
    farm: Farm,
    *,
    provider: WeatherProvider | None = None,
    forecast_hours: int = 24,
) -> None:
    """Poll current + forecast weather for ``farm`` and persist it (org-scoped).

    No-ops with a warning when the farm has no coordinates. Commits on success so
    it is safe to call standalone or in a loop.
    """
    if farm.latitude is None or farm.longitude is None:
        logger.warning("weather.poll.skip_no_location", farm_id=str(farm.id))
        return

    prov = provider or build_provider(settings.weather_provider)
    now = await prov.current(farm.latitude, farm.longitude)
    db.add(
        WeatherObservation(
            org_id=farm.org_id,
            farm_id=farm.id,
            observed_at=now.observed_at,
            source=now.source,
            air_temp_c=now.air_temp_c,
            rh_pct=now.rh_pct,
            wind_speed_ms=now.wind_speed_ms,
            rainfall_mm=now.rainfall_mm,
            clouds_pct=now.clouds_pct,
            raw=now.raw,
        )
    )

    issued_at = datetime.now(UTC)
    points = await prov.forecast(farm.latitude, farm.longitude, hours=forecast_hours)
    for point in points:
        db.add(
            WeatherForecast(
                org_id=farm.org_id,
                farm_id=farm.id,
                issued_at=issued_at,
                forecast_for=point.forecast_for,
                source=point.source,
                air_temp_c=point.air_temp_c,
                rh_pct=point.rh_pct,
                rain_prob=point.rain_prob,
                rainfall_mm=point.rainfall_mm,
                wind_speed_ms=point.wind_speed_ms,
            )
        )

    await db.commit()
    logger.info("weather.poll.done", farm_id=str(farm.id), forecasts=len(points), source=now.source)
