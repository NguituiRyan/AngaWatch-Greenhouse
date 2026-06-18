"""Celery tasks for billing reconciliation.

The beat schedule (``app.workers.celery_app``) calls
``app.billing.tasks.reconcile_pending_payments`` every few minutes to age out
pending STK payments. Daraja can drop callbacks, so this task is the safety net
that marks long-pending payments failed (and, in a real deployment, would query
the Daraja STK-status endpoint to resolve them definitively).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.billing import Payment
from app.db.models.common import PaymentStatus
from app.db.session import get_sync_session
from app.workers.celery_app import celery_app

log = get_logger(__name__)

# How long a payment may sit ``pending`` before we give up on its callback.
_PENDING_TTL = timedelta(minutes=15)


@celery_app.task(name="app.billing.tasks.reconcile_pending_payments")
def reconcile_pending_payments() -> int:
    """Expire pending payments older than the TTL. Returns the count updated."""
    cutoff = datetime.now(UTC) - _PENDING_TTL
    session = get_sync_session()
    updated = 0
    try:
        stmt = select(Payment).where(
            Payment.status == PaymentStatus.PENDING,
            Payment.initiated_at < cutoff,
        )
        for payment in session.execute(stmt).scalars():
            payment.status = PaymentStatus.FAILED
            payment.result_desc = payment.result_desc or "Timed out awaiting M-Pesa callback"
            payment.completed_at = datetime.now(UTC)
            updated += 1
        if updated:
            session.commit()
        log.info("billing.reconcile.done", expired=updated)
    except Exception:  # pragma: no cover - defensive
        session.rollback()
        raise
    finally:
        session.close()
    return updated
