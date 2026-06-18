"""Billing service: feature gating + subscription lifecycle (async).

These are the cross-module seams other code depends on:

* :func:`org_has_feature` — premium feature gate (used by ``require_feature``).
* :func:`initiate_subscription` — create/get a trial subscription, a pending
  payment, and fire an STK push.
* :func:`handle_stk_callback` — reconcile a Daraja callback by
  ``checkout_request_id`` and, on success, advance the subscription state
  machine ``trial -> active`` and mark a matching installment paid.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.billing.base import PLAN_FEATURES, STKPushRequest, STKPushResult
from app.billing.providers import get_payment_provider
from app.core.logging import get_logger
from app.db.models.billing import Installment, Payment, Subscription
from app.db.models.common import (
    PaymentProviderType,
    PaymentStatus,
    PlanType,
    SubscriptionStatus,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger(__name__)

# Active (or trial) subscriptions grant their plan's features.
_GRANTING_STATUSES: frozenset[SubscriptionStatus] = frozenset(
    {SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE}
)

# Subscription state-machine transitions.
_TRANSITIONS: dict[SubscriptionStatus, frozenset[SubscriptionStatus]] = {
    SubscriptionStatus.TRIAL: frozenset({SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED}),
    SubscriptionStatus.ACTIVE: frozenset(
        {
            SubscriptionStatus.PAST_DUE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.CANCELLED,
        }
    ),
    SubscriptionStatus.PAST_DUE: frozenset(
        {
            SubscriptionStatus.ACTIVE,
            SubscriptionStatus.SUSPENDED,
            SubscriptionStatus.CANCELLED,
        }
    ),
    SubscriptionStatus.SUSPENDED: frozenset(
        {SubscriptionStatus.ACTIVE, SubscriptionStatus.CANCELLED}
    ),
    SubscriptionStatus.CANCELLED: frozenset(),
}

_DEFAULT_PERIOD = timedelta(days=30)


def can_transition(current: SubscriptionStatus, target: SubscriptionStatus) -> bool:
    """Return True if ``current -> target`` is a legal subscription transition.

    A no-op transition (``current == target``) is always allowed (idempotent).
    """
    if current == target:
        return True
    return target in _TRANSITIONS.get(current, frozenset())


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _features_for_plan(plan_type: PlanType) -> frozenset[str]:
    return PLAN_FEATURES.get(plan_type, frozenset())


async def org_has_feature(db: AsyncSession, org_id: uuid.UUID, feature: str) -> bool:
    """True if the org has an active/trial subscription whose plan grants ``feature``."""
    stmt = select(Subscription).where(
        Subscription.org_id == org_id,
        Subscription.status.in_(_GRANTING_STATUSES),
    )
    result = await db.execute(stmt)
    return any(feature in _features_for_plan(sub.plan_type) for sub in result.scalars())


async def _get_or_create_trial_subscription(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID | None,
    plan_type: PlanType,
    plan_name: str,
    amount: int,
) -> Subscription:
    """Return an existing non-terminal subscription for the org, or create a trial."""
    stmt = select(Subscription).where(
        Subscription.org_id == org_id,
        Subscription.status != SubscriptionStatus.CANCELLED,
    )
    existing = (await db.execute(stmt)).scalars().first()
    if existing is not None:
        return existing

    now = _utcnow()
    sub = Subscription(
        org_id=org_id,
        user_id=user_id,
        plan_type=plan_type,
        plan_name=plan_name,
        status=SubscriptionStatus.TRIAL,
        price=amount,
        currency="KES",
        features=dict.fromkeys(_features_for_plan(plan_type), True),
        trial_ends_at=now + timedelta(days=14),
    )
    db.add(sub)
    await db.flush()
    return sub


async def initiate_subscription(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    plan_type: PlanType,
    phone: str,
    amount: int,
    plan_name: str = "standard",
) -> tuple[Subscription, Payment, STKPushResult]:
    """Create/get a trial subscription, a pending payment, and fire the STK push.

    The STK push is best-effort: the :class:`Payment` row is always persisted
    (status ``pending``) with whatever correlation ids the provider returns, so
    the later callback can reconcile it.
    """
    sub = await _get_or_create_trial_subscription(
        db,
        org_id=org_id,
        user_id=user_id,
        plan_type=plan_type,
        plan_name=plan_name,
        amount=amount,
    )

    account_reference = f"AW-{str(org_id)[:8]}"
    payment = Payment(
        org_id=org_id,
        subscription_id=sub.id,
        provider=PaymentProviderType.MPESA,
        amount=amount,
        currency="KES",
        status=PaymentStatus.PENDING,
        phone=phone,
        account_reference=account_reference,
        initiated_at=_utcnow(),
    )
    db.add(payment)
    await db.flush()

    provider = get_payment_provider()
    result = await provider.stk_push(
        STKPushRequest(
            phone=phone,
            amount=int(amount),
            account_reference=account_reference,
            description="AngaWatch subscription",
        )
    )

    payment.merchant_request_id = result.merchant_request_id
    payment.checkout_request_id = result.checkout_request_id
    if result.raw:
        payment.raw_callback = {"stk_request": result.raw}
    if not result.ok:
        payment.result_desc = result.error
        log.warning(
            "billing.initiate.stk_failed",
            org_id=str(org_id),
            error=result.error,
        )

    await db.commit()
    await db.refresh(sub)
    await db.refresh(payment)
    return sub, payment, result


def _activate_subscription(sub: Subscription, now: datetime) -> None:
    """Advance ``trial/past_due -> active`` and (re)set the billing period."""
    if can_transition(sub.status, SubscriptionStatus.ACTIVE):
        sub.status = SubscriptionStatus.ACTIVE
    if sub.started_at is None:
        sub.started_at = now
    sub.current_period_start = now
    sub.current_period_end = now + _DEFAULT_PERIOD


async def handle_stk_callback(db: AsyncSession, payload: dict) -> Payment:
    """Reconcile a Daraja STK callback against the matching :class:`Payment`.

    Looks the payment up by ``checkout_request_id``; updates its status, receipt
    and raw callback; and, on success, activates the linked subscription and
    marks the earliest unpaid matching installment paid.

    Raises :class:`LookupError` when no payment matches the callback.
    """
    provider = get_payment_provider()
    cb = provider.parse_callback(payload)

    if not cb.checkout_request_id:
        raise LookupError("callback missing CheckoutRequestID")

    stmt = select(Payment).where(Payment.checkout_request_id == cb.checkout_request_id)
    payment = (await db.execute(stmt)).scalars().first()
    if payment is None:
        raise LookupError(f"no payment for checkout_request_id={cb.checkout_request_id}")

    now = _utcnow()
    payment.result_code = cb.result_code
    payment.result_desc = cb.result_desc
    payment.raw_callback = cb.raw
    payment.completed_at = now
    if cb.mpesa_receipt:
        payment.mpesa_receipt = cb.mpesa_receipt
    if cb.merchant_request_id and not payment.merchant_request_id:
        payment.merchant_request_id = cb.merchant_request_id

    if cb.success:
        payment.status = PaymentStatus.SUCCESS
        await _apply_successful_payment(db, payment, now)
    else:
        payment.status = PaymentStatus.FAILED
        log.info(
            "billing.callback.failed",
            checkout_request_id=cb.checkout_request_id,
            result_code=cb.result_code,
        )

    await db.commit()
    await db.refresh(payment)
    return payment


async def _apply_successful_payment(db: AsyncSession, payment: Payment, now: datetime) -> None:
    """On a successful payment: activate the subscription + settle an installment."""
    if payment.subscription_id is None:
        return

    sub = await db.get(Subscription, payment.subscription_id)
    if sub is not None:
        _activate_subscription(sub, now)

    # Settle the earliest unpaid installment for this subscription (rent-to-own).
    inst_stmt = (
        select(Installment)
        .where(
            Installment.subscription_id == payment.subscription_id,
            Installment.paid.is_(False),
        )
        .order_by(Installment.sequence)
    )
    installment = (await db.execute(inst_stmt)).scalars().first()
    if installment is not None:
        installment.paid = True
        installment.paid_at = now
        installment.payment_id = payment.id
        payment.installment_id = installment.id

    log.info(
        "billing.callback.success",
        subscription_id=str(payment.subscription_id),
        receipt=payment.mpesa_receipt,
    )
