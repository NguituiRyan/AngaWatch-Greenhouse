"""Cross-module API smoke test: one user's journey through the REST surface.

Drives the public HTTP API end to end via the ASGI ``client`` fixture, touching
every major router in a single flow:

1. ``POST /auth/register`` + ``POST /auth/login`` -> JWT,
2. build farm -> greenhouse -> device, ``POST /ingest`` telemetry,
3. ``GET .../readings`` (+ latest) and ``GET .../risk``,
4. list an alert and ``POST /alerts/{id}/ack`` it,
5. list actuators and ``POST /actuators/{id}/command`` (mock driver acks),
6. ``POST /billing/subscribe`` (STK) then ``POST /billing/mpesa/callback``.

Alerts and actuators have no public create endpoint (they originate from the
risk engine / provisioning), so those two rows are seeded directly into the same
in-memory DB the client uses, scoped to the registered org. Everything else goes
through HTTP, which is what makes this an integration smoke test for the wiring
between the routers, the service layer, and the DB session dependency.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest_asyncio

from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    AlertStatus,
    PlanType,
    RiskLevel,
    RiskModelType,
    SubscriptionStatus,
)
from app.db.models.control import ActuatorDevice
from app.db.models.intelligence import Alert

API = "/api/v1"


@pytest_asyncio.fixture(autouse=True)
def _patch_password_hashing(monkeypatch):
    """Swap bcrypt for a pure-Python hash.

    The installed ``bcrypt`` raises on passlib's >72-byte backend probe in this
    environment. The real register/login path hashes + verifies a password, so we
    swap the passlib context for a network-free, bcrypt-free scheme. This patches
    only the security module's ``_pwd`` global (read on every call) — no
    foundation file is edited.
    """
    from passlib.context import CryptContext

    ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")
    monkeypatch.setattr("app.core.security._pwd", ctx, raising=False)


async def _register_and_login(client) -> tuple[str, dict[str, str]]:
    """Register a fresh org owner and return ``(org_id, auth_headers)``."""
    email = f"owner-{uuid.uuid4().hex[:8]}@demo-coop.ke"
    reg = await client.post(
        f"{API}/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "Smoke Owner",
            "org_name": "Smoke Coop",
        },
    )
    assert reg.status_code == 201, reg.text

    login = await client.post(
        f"{API}/auth/login",
        data={"username": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me = await client.get(f"{API}/organizations/me", headers=headers)
    assert me.status_code == 200, me.text
    return me.json()["id"], headers


async def test_api_smoke_full_journey(client, session_factory):
    org_id, headers = await _register_and_login(client)

    # ---- Build the farm -> greenhouse -> device chain over HTTP. ----
    farm = (await client.post(f"{API}/farms", headers=headers, json={"name": "Smoke Farm"})).json()
    gh = (
        await client.post(
            f"{API}/greenhouses",
            headers=headers,
            json={"farm_id": farm["id"], "name": "GH-1"},
        )
    ).json()
    device_uid = f"NODE-{uuid.uuid4().hex[:6]}"
    dev = await client.post(
        f"{API}/devices",
        headers=headers,
        json={"device_uid": device_uid, "name": "Node 1", "greenhouse_id": gh["id"]},
    )
    assert dev.status_code == 201, dev.text

    # ---- Ingest telemetry, then read it back. ----
    ts = datetime.now(UTC).isoformat()
    ingest = await client.post(
        f"{API}/ingest",
        headers=headers,
        json={
            "device_id": device_uid,
            "ts": ts,
            "air_temp_c": 27.5,
            "rh_pct": 88.0,
            "soil_moisture_pct": 30.0,
            "battery_v": 3.9,
            "rssi": -70,
        },
    )
    assert ingest.status_code == 200, ingest.text
    assert ingest.json()["stored"] is True

    readings = await client.get(f"{API}/greenhouses/{gh['id']}/readings", headers=headers)
    assert readings.status_code == 200, readings.text
    assert len(readings.json()) == 1
    assert readings.json()[0]["air_temp_c"] == 27.5

    latest = await client.get(f"{API}/greenhouses/{gh['id']}/readings/latest", headers=headers)
    assert latest.status_code == 200
    assert latest.json()["rh_pct"] == 88.0

    # ---- Risk endpoint responds (no persisted assessments yet -> empty list). ----
    risk = await client.get(f"{API}/greenhouses/{gh['id']}/risk", headers=headers)
    assert risk.status_code == 200, risk.text
    assert risk.json() == []

    # ---- Seed an alert + actuator directly (no public create endpoint). ----
    async with session_factory() as s:
        alert = Alert(
            org_id=uuid.UUID(org_id),
            greenhouse_id=uuid.UUID(gh["id"]),
            model_type=RiskModelType.LATE_BLIGHT,
            level=RiskLevel.HIGH,
            title="Late blight risk: ventilate now",
            dedup_key=f"late_blight:{gh['id']}",
            status=AlertStatus.SENT,
            first_seen_at=datetime.now(UTC),
        )
        actuator = ActuatorDevice(
            org_id=uuid.UUID(org_id),
            greenhouse_id=uuid.UUID(gh["id"]),
            name="GH1-VENT-01",
            actuator_type=ActuatorType.VENT,
            state=ActuatorState.CLOSED,
            is_online=True,
        )
        s.add_all([alert, actuator])
        await s.commit()
        alert_id = str(alert.id)
        actuator_id = str(actuator.id)

    # ---- List + ack the alert. ----
    alerts = await client.get(f"{API}/alerts", headers=headers)
    assert alerts.status_code == 200, alerts.text
    assert alert_id in [a["id"] for a in alerts.json()]

    ack = await client.post(f"{API}/alerts/{alert_id}/ack", headers=headers)
    assert ack.status_code == 200, ack.text
    assert ack.json()["status"] == AlertStatus.ACKED.value
    assert ack.json()["acked_at"] is not None

    # ---- List actuators + issue a manual command (mock driver acks). ----
    acts = await client.get(f"{API}/greenhouses/{gh['id']}/actuators", headers=headers)
    assert acts.status_code == 200, acts.text
    assert actuator_id in [a["id"] for a in acts.json()]

    cmd = await client.post(
        f"{API}/actuators/{actuator_id}/command",
        headers=headers,
        json={"command": "open"},
    )
    assert cmd.status_code == 201, cmd.text
    body = cmd.json()
    assert body["command"] == "open"
    assert body["status"] == "acked"
    assert body["source"] == "manual"

    feed = await client.get(f"{API}/control/commands", headers=headers)
    assert feed.status_code == 200
    assert body["id"] in [c["id"] for c in feed.json()]

    # ---- Subscribe (STK) then post the Daraja success callback. ----
    sub_resp = await client.post(
        f"{API}/billing/subscribe",
        headers=headers,
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
                        {"Name": "MpesaReceiptNumber", "Value": "SMOKE123"},
                        {"Name": "PhoneNumber", "Value": 254700000001},
                    ]
                },
            }
        }
    }
    cb_resp = await client.post(f"{API}/billing/mpesa/callback", json=cb_payload)
    assert cb_resp.status_code == 200, cb_resp.text
    assert cb_resp.json()["ResultCode"] == 0

    sub_view = await client.get(f"{API}/billing/subscription", headers=headers)
    assert sub_view.status_code == 200
    assert sub_view.json()["status"] == SubscriptionStatus.ACTIVE.value
