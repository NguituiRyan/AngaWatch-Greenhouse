"""Celery task: poll weather for every farm on the beat schedule.

Registered as ``app.weather.tasks.poll_all_farms`` (referenced by the beat schedule
in ``app.workers.celery_app``). The providers are async, so the sync Celery task
drives an async session via ``asyncio.run``, isolating per-farm failures.
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.farm import Farm
from app.db.session import AsyncSessionLocal
from app.weather.service import poll_farm
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


async def _poll_all_farms() -> int:
    polled = 0
    async with AsyncSessionLocal() as db:
        farms = list((await db.scalars(select(Farm))).all())
        for farm in farms:
            try:
                await poll_farm(db, farm)
                polled += 1
            except Exception:  # pragma: no cover - one farm must not abort the sweep
                logger.exception("weather.task.farm_failed", farm_id=str(farm.id))
                await db.rollback()
    return polled


@celery_app.task(name="app.weather.tasks.poll_all_farms")
def poll_all_farms() -> int:
    """Poll weather for all farms. Returns the count polled."""
    polled = asyncio.run(_poll_all_farms())
    logger.info("weather.task.sweep_done", polled=polled)
    return polled
