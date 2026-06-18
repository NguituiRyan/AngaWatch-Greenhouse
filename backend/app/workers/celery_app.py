"""Celery app + beat schedule for scheduled risk evaluation, weather polling, dispatch.

Task bodies live in each domain (``app.<domain>.tasks``) and are discovered via
``autodiscover_tasks``. Beat entries reference tasks by dotted name so importing
this module never requires the task modules to exist yet.
"""

from __future__ import annotations

from celery import Celery
from celery.schedules import crontab  # noqa: F401  (available for cron-style schedules)

from app.core.config import settings
from app.core.logging import configure_logging

configure_logging()

celery_app = Celery(
    "angawatch",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=settings.tz,
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_max_tasks_per_child=200,
)

# Domains that expose a ``tasks`` module.
celery_app.autodiscover_tasks(
    [
        "app.risk_engine",
        "app.weather",
        "app.alerting",
        "app.control",
        "app.billing",
    ]
)

celery_app.conf.beat_schedule = {
    "evaluate-risk": {
        "task": "app.risk_engine.tasks.evaluate_all_greenhouses",
        "schedule": settings.risk_eval_interval_minutes * 60.0,
    },
    "poll-weather": {
        "task": "app.weather.tasks.poll_all_farms",
        "schedule": settings.weather_poll_interval_minutes * 60.0,
    },
    "dispatch-alerts": {
        "task": "app.alerting.tasks.dispatch_pending_alerts",
        "schedule": 60.0,
    },
    "reconcile-payments": {
        "task": "app.billing.tasks.reconcile_pending_payments",
        "schedule": 300.0,
    },
}
