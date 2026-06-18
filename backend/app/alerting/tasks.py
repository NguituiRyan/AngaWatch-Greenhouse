"""Celery task: periodically flush pending alerts through the dispatcher.

Registered as ``app.alerting.tasks.dispatch_pending_alerts`` (the dotted name the beat
schedule in ``app.workers.celery_app`` references). The body uses the sync session.
"""

from __future__ import annotations

from app.alerting.dispatcher import dispatch_pending
from app.core.logging import get_logger
from app.db.session import get_sync_session
from app.workers.celery_app import celery_app

log = get_logger("alerting.tasks")


@celery_app.task(name="app.alerting.tasks.dispatch_pending_alerts")
def dispatch_pending_alerts() -> int:
    """Dispatch all pending/escalated alerts; return how many were processed."""
    session = get_sync_session()
    try:
        count = dispatch_pending(session)
        log.info("alerting.tasks.dispatch_pending_alerts", processed=count)
        return count
    finally:
        session.close()
