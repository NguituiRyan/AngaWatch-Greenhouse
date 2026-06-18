"""Billing endpoints: subscription view, subscribe (STK push), M-Pesa callback, payments."""

from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import select

from app.api.deps import DBSession, Scope
from app.api.schemas.billing import (
    CallbackAck,
    PaymentOut,
    STKResultOut,
    SubscribeIn,
    SubscriptionOut,
)
from app.billing.service import handle_stk_callback, initiate_subscription
from app.core.logging import get_logger
from app.db.models.billing import Payment, Subscription
from app.db.models.common import SubscriptionStatus

router = APIRouter(prefix="/billing", tags=["billing"])

log = get_logger(__name__)


@router.get("/subscription", response_model=SubscriptionOut | None)
async def get_subscription(scope: Scope) -> Subscription | None:
    """Return the org's current (non-cancelled preferred) subscription, if any."""
    stmt = (
        select(Subscription)
        .where(Subscription.org_id == scope.org_id)
        .order_by(
            (Subscription.status == SubscriptionStatus.CANCELLED).asc(),
            Subscription.created_at.desc(),
        )
    )
    return (await scope.db.scalars(stmt)).first()


@router.post("/subscribe", response_model=STKResultOut)
async def subscribe(body: SubscribeIn, scope: Scope) -> STKResultOut:
    """Create/get a trial subscription, a pending payment, and fire an STK push."""
    sub, payment, result = await initiate_subscription(
        scope.db,
        org_id=scope.org_id,
        user_id=scope.user.id,
        plan_type=body.plan_type,
        phone=body.phone,
        amount=body.amount,
        plan_name=body.plan_name,
    )
    return STKResultOut(
        ok=result.ok,
        subscription_id=sub.id,
        payment_id=payment.id,
        checkout_request_id=result.checkout_request_id,
        merchant_request_id=result.merchant_request_id,
        customer_message=result.customer_message,
        error=result.error,
    )


@router.post("/mpesa/callback", response_model=CallbackAck)
async def mpesa_callback(request: Request, db: DBSession) -> CallbackAck:
    """Daraja STK callback webhook (NO auth — Safaricom posts here).

    Uses the plain DB session dependency (no JWT) so anyone with the secret URL
    can post. Always responds with ``ResultCode 0`` so Daraja does not retry;
    reconciliation failures are logged, not surfaced to the caller.
    """
    payload = await request.json()
    try:
        payment = await handle_stk_callback(db, payload)
        log.info(
            "billing.callback.reconciled",
            payment_id=str(payment.id),
            status=str(payment.status),
        )
    except LookupError as exc:
        log.warning("billing.callback.unmatched", error=str(exc))

    return CallbackAck()


@router.get("/payments", response_model=list[PaymentOut])
async def list_payments(scope: Scope) -> list[Payment]:
    """Return the org's payment history, newest first."""
    stmt = (
        select(Payment).where(Payment.org_id == scope.org_id).order_by(Payment.initiated_at.desc())
    )
    return list((await scope.db.scalars(stmt)).all())
