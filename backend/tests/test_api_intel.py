"""API tests for the intelligence/commerce routers.

Covers: alert feed listing + ack, the full manual control command flow
(actuator -> command -> ACKED), and the billing subscribe -> M-Pesa callback ->
ACTIVE flow that unlocks a feature-gated endpoint (risk history).

Supporting rows (farm, greenhouse, actuator, alert) are inserted directly with
the async ``db`` fixture so the suite is independent of sibling routers.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio

from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    AlertStatus,
    CommandStatus,
    PlanType,
    RiskLevel,
    RiskModelType,
    SubscriptionStatus,
)
from app.db.models.control import ActuatorDevice
from app.db.models.farm import Farm, Greenhouse
from app.db.models.intelligence import Alert

API = "/api/v1"


@pytest.fixture(autouse=True)
def _patch_password_hashing(monkeypatch):
    """Use a pure-Python hash for tests.

    The installed ``bcrypt`` raises on passlib's >72-byte backend probe in this
    environment. Auth here only needs a *valid* User row + a JWT (passwords are
    never verified by these endpoints), so we swap in a network-free, bcrypt-free
    hash. This patches only the test-side symbols — no foundation file changes.
    """
    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

    # ``hash_password``/``verify_password`` read ``_pwd`` from module globals on
    # every call, so swapping the context is enough — conftest's imported
    # ``hash_password`` function picks it up without further patching.
    monkeypatch.setattr("app.core.security._pwd", ctx, raising=False)


@pytest_asyncio.fixture
async def greenhouse(db, org) -> Greenhouse:
    farm = Farm(org_id=org.id, name="Nakuru Farm", latitude=-0.303, longitude=36.080)
    db.add(farm)
    await db.flush()
    gh = Greenhouse(org_id=org.id, farm_id=farm.id, name="GH-1")
    db.add(gh)
    await db.commit()
    await db.refresh(gh)
    return gh


@pytest_asyncio.fixture
async def actuator(db, org, greenhouse) -> ActuatorDevice:
    act = ActuatorDevice(
        org_id=org.id,
        greenhouse_id=greenhouse.id,
        name="GH1-VENT-01",
        actuator_type=ActuatorType.VENT,
        state=ActuatorState.CLOSED,
        is_online=True,
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act


@pytest_asyncio.fixture
async def alert(db, org, greenhouse) -> Alert:
    a = Alert(
        org_id=org.id,
        greenhouse_id=greenhouse.id,
        model_type=RiskModelType.LATE_BLIGHT,
        level=RiskLevel.HIGH,
        title="Late blight risk: ventilate now",
        dedup_key=f"late_blight:{greenhouse.id}",
        status=AlertStatus.SENT,
        first_seen_at=datetime.now(UTC),
    )
    db.add(a)
    await db.commit()
    await db.refresh(a)
    return a


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_list_alerts(client, auth_headers, alert):
    resp = await client.get(f"{API}/alerts", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == str(alert.id)
    assert body[0]["title"] == alert.title

    # Status filter narrows the feed.
    resp_acked = await client.get(f"{API}/alerts?status=acked", headers=auth_headers)
    assert resp_acked.status_code == 200
    assert resp_acked.json() == []


@pytest.mark.asyncio
async def test_ack_alert(client, auth_headers, user, alert):
    resp = await client.post(f"{API}/alerts/{alert.id}/ack", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == AlertStatus.ACKED.value
    assert body["acked_by"] == str(user.id)
    assert body["acked_at"] is not None


@pytest.mark.asyncio
async def test_ack_missing_alert_404(client, auth_headers):
    resp = await client.post(f"{API}/alerts/{uuid.uuid4()}/ack", headers=auth_headers)
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Control: full manual command flow
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_manual_control_command_flow(client, auth_headers, greenhouse, actuator):
    # 1. The actuator shows up under its greenhouse.
    list_resp = await client.get(
        f"{API}/greenhouses/{greenhouse.id}/actuators", headers=auth_headers
    )
    assert list_resp.status_code == 200, list_resp.text
    assert [a["id"] for a in list_resp.json()] == [str(actuator.id)]

    # 2. Issue a manual "open" command -> enqueue + execute -> mock acks.
    cmd_resp = await client.post(
        f"{API}/actuators/{actuator.id}/command",
        headers=auth_headers,
        json={"command": "open"},
    )
    assert cmd_resp.status_code == 201, cmd_resp.text
    cmd = cmd_resp.json()
    assert cmd["command"] == "open"
    assert cmd["status"] == CommandStatus.ACKED.value
    assert cmd["source"] == "manual"

    # 3. The command appears in the org-scoped command feed.
    feed = await client.get(f"{API}/control/commands", headers=auth_headers)
    assert feed.status_code == 200
    assert cmd["id"] in [c["id"] for c in feed.json()]


@pytest.mark.asyncio
async def test_command_unknown_actuator_404(client, auth_headers):
    resp = await client.post(
        f"{API}/actuators/{uuid.uuid4()}/command",
        headers=auth_headers,
        json={"command": "open"},
    )
    assert resp.status_code == 404


# --------------------------------------------------------------------------
# Billing: subscribe -> callback -> ACTIVE unlocks a gated endpoint
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_billing_subscribe_callback_unlocks_feature(client, auth_headers, greenhouse):
    # The premium history endpoint is locked before any subscription exists.
    locked = await client.get(
        f"{API}/greenhouses/{greenhouse.id}/risk/history", headers=auth_headers
    )
    assert locked.status_code == 402, locked.text

    # Subscribe -> mock STK push returns a checkout id (status pending until callback).
    sub_resp = await client.post(
        f"{API}/billing/subscribe",
        headers=auth_headers,
        json={
            "plan_type": PlanType.SUBSCRIPTION.value,
            "phone": "254700000001",
            "amount": 500,
        },
    )
    assert sub_resp.status_code == 200, sub_resp.text
    sub_body = sub_resp.json()
    assert sub_body["ok"] is True
    checkout_id = sub_body["checkout_request_id"]
    assert checkout_id

    # The trial subscription already grants premium features -> history unlocks.
    unlocked_trial = await client.get(
        f"{API}/greenhouses/{greenhouse.id}/risk/history", headers=auth_headers
    )
    assert unlocked_trial.status_code == 200, unlocked_trial.text

    # The pending payment is visible.
    payments = await client.get(f"{API}/billing/payments", headers=auth_headers)
    assert payments.status_code == 200
    assert any(p["checkout_request_id"] == checkout_id for p in payments.json())

    # Post the Daraja success callback (no auth) -> subscription becomes ACTIVE.
    cb_payload = {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": sub_body["merchant_request_id"],
                "CheckoutRequestID": checkout_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": 500},
                        {"Name": "MpesaReceiptNumber", "Value": "ABC123XYZ"},
                        {"Name": "PhoneNumber", "Value": 254700000001},
                    ]
                },
            }
        }
    }
    cb_resp = await client.post(f"{API}/billing/mpesa/callback", json=cb_payload)
    assert cb_resp.status_code == 200, cb_resp.text
    assert cb_resp.json()["ResultCode"] == 0

    # Subscription is now ACTIVE and the gated endpoint still works.
    sub_view = await client.get(f"{API}/billing/subscription", headers=auth_headers)
    assert sub_view.status_code == 200
    assert sub_view.json()["status"] == SubscriptionStatus.ACTIVE.value

    unlocked = await client.get(
        f"{API}/greenhouses/{greenhouse.id}/risk/history", headers=auth_headers
    )
    assert unlocked.status_code == 200, unlocked.text


# --------------------------------------------------------------------------
# Recommendations override (role-gated)
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_recommendation_override(client, auth_headers, db, org, greenhouse):
    from app.db.models.intelligence import Recommendation

    rec = Recommendation(
        org_id=org.id,
        action_code="ventilate_now",
        message_en="Ventilate the greenhouse now.",
        message_sw="Pitisha hewa kwenye chafu sasa.",
    )
    db.add(rec)
    await db.commit()
    await db.refresh(rec)

    resp = await client.post(
        f"{API}/recommendations/{rec.id}/override",
        headers=auth_headers,
        json={"message": "Hold off — humidity dropping per forecast."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["overridden"] is True
    assert body["override_message"].startswith("Hold off")
    assert body["override_by"] is not None


# --------------------------------------------------------------------------
# Records scaffold
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_create_and_list_expense(client, auth_headers):
    create = await client.post(
        f"{API}/expenses",
        headers=auth_headers,
        json={
            "category": "inputs",
            "amount": 1200.0,
            "currency": "KES",
            "incurred_at": "2026-06-01",
        },
    )
    assert create.status_code == 201, create.text
    assert create.json()["category"] == "inputs"

    listing = await client.get(f"{API}/expenses", headers=auth_headers)
    assert listing.status_code == 200
    assert len(listing.json()) == 1


# --------------------------------------------------------------------------
# WhatsApp webhook verification
# --------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_whatsapp_verify(client):
    from app.core.config import settings

    ok = await client.get(
        f"{API}/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.whatsapp_verify_token,
            "hub.challenge": "challenge-123",
        },
    )
    assert ok.status_code == 200
    assert ok.text == "challenge-123"

    bad = await client.get(
        f"{API}/whatsapp/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong",
            "hub.challenge": "challenge-123",
        },
    )
    assert bad.status_code == 403
