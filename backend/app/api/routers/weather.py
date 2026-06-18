"""Weather: latest observation + upcoming forecasts for an owned farm."""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import Scope
from app.api.schemas.weather import (
    FarmWeatherOut,
    WeatherForecastOut,
    WeatherObservationOut,
)
from app.db.models import Farm, WeatherForecast, WeatherObservation

router = APIRouter(prefix="/farms", tags=["weather"])


@router.get("/{farm_id}/weather", response_model=FarmWeatherOut)
async def farm_weather(
    farm_id: uuid.UUID,
    scope: Scope,
    forecast_limit: int = Query(24, ge=1, le=200),
) -> FarmWeatherOut:
    """Return the latest observation plus upcoming forecasts for an owned farm."""
    farm = await scope.db.scalar(
        select(Farm.id).where(Farm.id == farm_id, Farm.org_id == scope.org_id)
    )
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")

    observation = await scope.db.scalar(
        select(WeatherObservation)
        .where(
            WeatherObservation.org_id == scope.org_id,
            WeatherObservation.farm_id == farm_id,
        )
        .order_by(WeatherObservation.observed_at.desc())
        .limit(1)
    )

    forecasts = await scope.db.scalars(
        select(WeatherForecast)
        .where(
            WeatherForecast.org_id == scope.org_id,
            WeatherForecast.farm_id == farm_id,
            WeatherForecast.forecast_for >= datetime.now(UTC),
        )
        .order_by(WeatherForecast.forecast_for)
        .limit(forecast_limit)
    )

    return FarmWeatherOut(
        farm_id=farm_id,
        observation=(WeatherObservationOut.model_validate(observation) if observation else None),
        forecasts=[WeatherForecastOut.model_validate(f) for f in forecasts],
    )
