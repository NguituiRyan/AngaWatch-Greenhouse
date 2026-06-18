"""Billing tests: feature gating, STK initiation, and callback reconciliation.

These run against the async in-memory SQLite ``db`` fixture from ``conftest`` and
use the offline :class:`MockPaymentProvider` (no M-Pesa credentials configured),
exercising the full initiate -> callback -> activate flow.
"""

from __future__ import annotations

import base64
import json
import uuid

import httpx
import pytest
import respx
from httpx import Response

from app.billing.base import CallbackResult, STKPushRequest
from app.billing.mpesa import MpesaProvider, _password, _timestamp
from app.billing.providers import MockPaymentProvider, get_payment_provider
from app.billing.service import (
    can_transition,
    handle_stk_callback,
    initiate_subscription,
    org_has_feature,
)
from app.db.models import User
from app.db.models.billing import Installment, Payment
from app.db.models.common import (
    PaymentStatus,
    PlanType,
    SubscriptionStatus,
    UserRole,
)


@pytest.fixture
async def billing_user(db, org) -> User:
    """A user created without bcrypt hashing.

    The shared ``user`` fixture in conftest hashes a password via passlib/bcrypt,
    which is broken in some environments (bcrypt 5.x dropped the API passlib
    1.7.x relies on). Billing only needs a ``user.id``, so we store a placeholder
    hash directly to keep these tests independent of that hashing path.
    """
    u = User(
        org_id=org.id,
        email=f"billing-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 16,
        full_name="Billing User",
        role=UserRole.COOP_ADMIN,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


def _success_callback(checkout_request_id: str, *, amount: int = 1500) -> dict:
    """A Daraja-shaped successful STK callback envelope."""
    return {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mer-123",
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": amount},
                        {"Name": "MpesaReceiptNumber", "Value": "QGH7XYZ123"},
                        {"Name": "PhoneNumber", "Value": 254700000001},
                    ]
                },
            }
        }
    }


# ---- provider selection / mock ------------------------------------------
async def test_provider_defaults_to_mock_offline() -> None:
    provider = get_payment_provider()
    assert isinstance(provider, MockPaymentProvider)


async def test_mock_stk_push_returns_synthetic_ids() -> None:
    provider = MockPaymentProvider()
    result = await provider.stk_push(
        STKPushRequest(phone="254700000001", amount=1500, account_reference="AW-1")
    )
    assert result.ok is True
    assert result.merchant_request_id
    assert result.checkout_request_id


async def test_mock_parse_callback_echoes_success() -> None:
    provider = MockPaymentProvider()
    cb: CallbackResult = provider.parse_callback(_success_callback("chk-1"))
    assert cb.success is True
    assert cb.checkout_request_id == "chk-1"
    assert cb.mpesa_receipt == "QGH7XYZ123"
    assert cb.amount == 1500.0


# ---- feature gating ------------------------------------------------------
async def test_org_has_feature_false_without_subscription(db, org) -> None:
    assert await org_has_feature(db, org.id, "predictive_alerts") is False


async def test_org_has_feature_false_for_unknown_org(db) -> None:
    assert await org_has_feature(db, uuid.uuid4(), "predictive_alerts") is False


# ---- state-machine helper -----------------------------------------------
def test_state_machine_transitions() -> None:
    assert can_transition(SubscriptionStatus.TRIAL, SubscriptionStatus.ACTIVE) is True
    assert can_transition(SubscriptionStatus.TRIAL, SubscriptionStatus.TRIAL) is True
    assert can_transition(SubscriptionStatus.CANCELLED, SubscriptionStatus.ACTIVE) is False
    assert can_transition(SubscriptionStatus.ACTIVE, SubscriptionStatus.PAST_DUE) is True


# ---- initiate ------------------------------------------------------------
async def test_initiate_subscription_creates_pending_payment(db, org, billing_user) -> None:
    sub, payment, result = await initiate_subscription(
        db,
        org_id=org.id,
        user_id=billing_user.id,
        plan_type=PlanType.SUBSCRIPTION,
        phone="254700000001",
        amount=1500,
    )

    assert result.ok is True
    assert sub.status == SubscriptionStatus.TRIAL
    assert payment.status == PaymentStatus.PENDING
    assert payment.checkout_request_id == result.checkout_request_id
    assert payment.subscription_id == sub.id

    # Persisted as a real pending row.
    fetched = await db.get(Payment, payment.id)
    assert fetched is not None
    assert fetched.status == PaymentStatus.PENDING


async def test_initiate_subscription_is_idempotent_on_subscription(db, org, billing_user) -> None:
    sub1, _, _ = await initiate_subscription(
        db,
        org_id=org.id,
        user_id=billing_user.id,
        plan_type=PlanType.SUBSCRIPTION,
        phone="254700000001",
        amount=1500,
    )
    sub2, _, _ = await initiate_subscription(
        db,
        org_id=org.id,
        user_id=billing_user.id,
        plan_type=PlanType.SUBSCRIPTION,
        phone="254700000001",
        amount=1500,
    )
    assert sub1.id == sub2.id


# ---- callback reconciliation (the headline flow) ------------------------
async def test_successful_callback_activates_and_unlocks_feature(db, org, billing_user) -> None:
    # No premium yet (trial of SUBSCRIPTION plan already grants it, so assert pre-state).
    assert await org_has_feature(db, org.id, "predictive_alerts") is False

    sub, payment, result = await initiate_subscription(
        db,
        org_id=org.id,
        user_id=billing_user.id,
        plan_type=PlanType.SUBSCRIPTION,
        phone="254700000001",
        amount=1500,
    )

    updated = await handle_stk_callback(
        db, _success_callback(result.checkout_request_id, amount=1500)
    )

    assert updated.status == PaymentStatus.SUCCESS
    assert updated.mpesa_receipt == "QGH7XYZ123"

    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.ACTIVE
    assert sub.current_period_start is not None
    assert sub.current_period_end is not None

    assert await org_has_feature(db, org.id, "predictive_alerts") is True


async def test_successful_callback_marks_installment_paid(db, org, billing_user) -> None:
    sub, payment, result = await initiate_subscription(
        db,
        org_id=org.id,
        user_id=billing_user.id,
        plan_type=PlanType.RENT_TO_OWN,
        phone="254700000001",
        amount=2000,
    )

    inst = Installment(
        org_id=org.id,
        subscription_id=sub.id,
        sequence=1,
        amount=2000,
        currency="KES",
        due_date=sub.trial_ends_at,
        paid=False,
    )
    db.add(inst)
    await db.commit()

    await handle_stk_callback(db, _success_callback(result.checkout_request_id, amount=2000))

    await db.refresh(inst)
    assert inst.paid is True
    assert inst.paid_at is not None
    assert inst.payment_id == payment.id


async def test_failed_callback_marks_payment_failed(db, org, billing_user) -> None:
    sub, payment, result = await initiate_subscription(
        db,
        org_id=org.id,
        user_id=billing_user.id,
        plan_type=PlanType.SUBSCRIPTION,
        phone="254700000001",
        amount=1500,
    )

    failed_payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "mer-123",
                "CheckoutRequestID": result.checkout_request_id,
                "ResultCode": 1032,
                "ResultDesc": "Request cancelled by user",
            }
        }
    }
    updated = await handle_stk_callback(db, failed_payload)
    assert updated.status == PaymentStatus.FAILED

    await db.refresh(sub)
    assert sub.status == SubscriptionStatus.TRIAL


async def test_callback_without_matching_payment_raises(db, org) -> None:
    with pytest.raises(LookupError):
        await handle_stk_callback(db, _success_callback("does-not-exist"))


# ---- real MpesaProvider HTTP flow (mocked transport) --------------------
async def test_mpesa_provider_password_and_stk_flow() -> None:
    ts = "20260101120000"
    expected_password = base64.b64encode(f"174379passkey{ts}".encode()).decode()
    assert _password("174379", "passkey", ts) == expected_password
    assert len(_timestamp()) == 14  # YYYYMMDDHHMMSS

    provider = MpesaProvider(
        consumer_key="ck",
        consumer_secret="cs",
        shortcode="174379",
        passkey="passkey",
        callback_base_url="https://example.ngrok.io",
        environment="sandbox",
    )

    with respx.mock(base_url="https://sandbox.safaricom.co.ke") as mock:
        mock.get("/oauth/v1/generate").mock(
            return_value=Response(200, json={"access_token": "tok-abc", "expires_in": "3599"})
        )
        stk_route = mock.post("/mpesa/stkpush/v1/processrequest").mock(
            return_value=Response(
                200,
                json={
                    "MerchantRequestID": "mer-1",
                    "CheckoutRequestID": "chk-1",
                    "ResponseCode": "0",
                    "ResponseDescription": "Success. Request accepted for processing",
                    "CustomerMessage": "Success",
                },
            )
        )

        result = await provider.stk_push(
            STKPushRequest(phone="254700000001", amount=1500, account_reference="AW-12345678")
        )

    assert result.ok is True
    assert result.merchant_request_id == "mer-1"
    assert result.checkout_request_id == "chk-1"
    # The STK request carried a bearer token and the callback URL.
    sent = stk_route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer tok-abc"
    body = json.loads(sent.content)
    assert body["CallBackURL"].endswith("/api/v1/billing/mpesa/callback")
    assert body["BusinessShortCode"] == "174379"


async def test_mpesa_provider_network_error_returns_not_ok() -> None:
    provider = MpesaProvider(
        consumer_key="ck",
        consumer_secret="cs",
        shortcode="174379",
        passkey="passkey",
        callback_base_url="https://example.ngrok.io",
    )
    with respx.mock(base_url="https://sandbox.safaricom.co.ke") as mock:
        mock.get("/oauth/v1/generate").mock(side_effect=httpx.ConnectError("boom"))
        result = await provider.stk_push(
            STKPushRequest(phone="254700000001", amount=1500, account_reference="AW-1")
        )
    assert result.ok is False
    assert result.error


# ---- celery task wiring --------------------------------------------------
def test_reconcile_task_is_registered() -> None:
    import app.billing.tasks  # noqa: F401  (registers the task on import)
    from app.workers.celery_app import celery_app

    assert "app.billing.tasks.reconcile_pending_payments" in celery_app.tasks
