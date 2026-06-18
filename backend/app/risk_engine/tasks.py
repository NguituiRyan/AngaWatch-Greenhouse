"""Celery task: evaluate every greenhouse on the beat schedule.

Registered as ``app.risk_engine.tasks.evaluate_all_greenhouses`` (referenced by
the beat schedule in ``app.workers.celery_app``). Uses a sync session and runs
``evaluate_greenhouse`` for each greenhouse, isolating per-greenhouse failures so
one bad zone never aborts the whole sweep.
"""

from __future__ import annotations

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.farm import Greenhouse
from app.db.session import get_sync_session
from app.risk_engine.engine import evaluate_greenhouse
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="app.risk_engine.tasks.evaluate_all_greenhouses")
def evaluate_all_greenhouses() -> int:
    """Evaluate risk for all greenhouses. Returns the count evaluated."""
    session = get_sync_session()
    evaluated = 0
    try:
        greenhouse_ids = list(session.scalars(select(Greenhouse.id)).all())
        for gh_id in greenhouse_ids:
            try:
                evaluate_greenhouse(session, gh_id)
                evaluated += 1
            except Exception:  # pragma: no cover - one zone must not abort the sweep
                logger.exception("risk.task.greenhouse_failed", greenhouse_id=str(gh_id))
                session.rollback()
    finally:
        session.close()

    logger.info("risk.task.sweep_done", evaluated=evaluated)
    return evaluated
