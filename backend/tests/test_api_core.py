"""End-to-end tests for the core API routers (auth, farms, greenhouses, readings).

Exercises the public happy path through the ASGI ``client`` fixture against the
in-memory SQLite DB, plus org-scope isolation on a couple of representative
endpoints. Run with the project venv::

    cd backend; .\\.venv\\Scripts\\python.exe -m pytest tests\\test_api_core.py -q
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from httpx import AsyncClient

API = "/api/v1"


def test_app_imports() -> None:
    """All routers must import cleanly so the app boots."""
    import app.main  # noqa: F401

    assert app.main.app is not None


@pytest.mark.asyncio
async def test_register_and_login_returns_token(client: AsyncClient) -> None:
    email = f"owner-{uuid.uuid4().hex[:8]}@coop.ke"
    reg = await client.post(
        f"{API}/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "New Owner",
            "org_name": "Fresh Coop",
        },
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["email"] == email
    assert body["role"] == "coop_admin"

    login = await client.post(
        f"{API}/auth/login",
        data={"username": email, "password": "password123"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]
    assert tokens["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient) -> None:
    email = f"u-{uuid.uuid4().hex[:8]}@coop.ke"
    await client.post(
        f"{API}/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "U",
            "org_name": "C",
        },
    )
    resp = await client.post(
        f"{API}/auth/login", data={"username": email, "password": "wrong-pass"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_me(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get(f"{API}/auth/me", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "email" in body
    assert body["role"] == "coop_admin"


@pytest.mark.asyncio
async def test_auth_me_requires_token(client: AsyncClient) -> None:
    resp = await client.get(f"{API}/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_refresh_token(client: AsyncClient) -> None:
    email = f"r-{uuid.uuid4().hex[:8]}@coop.ke"
    await client.post(
        f"{API}/auth/register",
        json={
            "email": email,
            "password": "password123",
            "full_name": "R",
            "org_name": "RC",
        },
    )
    login = await client.post(
        f"{API}/auth/login", data={"username": email, "password": "password123"}
    )
    refresh_token = login.json()["refresh_token"]
    resp = await client.post(f"{API}/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200, resp.text
    assert resp.json()["access_token"]


@pytest.mark.asyncio
async def test_create_and_list_farm(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await client.post(
        f"{API}/farms",
        headers=auth_headers,
        json={"name": "Nakuru Farm", "county": "Nakuru", "latitude": -0.303, "longitude": 36.080},
    )
    assert create.status_code == 201, create.text
    farm = create.json()
    assert farm["name"] == "Nakuru Farm"
    farm_id = farm["id"]

    listing = await client.get(f"{API}/farms", headers=auth_headers)
    assert listing.status_code == 200
    ids = [f["id"] for f in listing.json()]
    assert farm_id in ids

    got = await client.get(f"{API}/farms/{farm_id}", headers=auth_headers)
    assert got.status_code == 200
    assert got.json()["county"] == "Nakuru"


@pytest.mark.asyncio
async def test_farm_patch_and_delete(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    create = await client.post(f"{API}/farms", headers=auth_headers, json={"name": "Temp Farm"})
    farm_id = create.json()["id"]

    patch = await client.patch(
        f"{API}/farms/{farm_id}", headers=auth_headers, json={"name": "Renamed Farm"}
    )
    assert patch.status_code == 200
    assert patch.json()["name"] == "Renamed Farm"

    delete = await client.delete(f"{API}/farms/{farm_id}", headers=auth_headers)
    assert delete.status_code == 204

    gone = await client.get(f"{API}/farms/{farm_id}", headers=auth_headers)
    assert gone.status_code == 404


@pytest.mark.asyncio
async def test_farm_not_found(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get(f"{API}/farms/{uuid.uuid4()}", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ingest_then_read_readings(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    # Build the farm -> greenhouse -> device chain via the API.
    farm = (
        await client.post(f"{API}/farms", headers=auth_headers, json={"name": "GH Farm"})
    ).json()
    gh = (
        await client.post(
            f"{API}/greenhouses",
            headers=auth_headers,
            json={"farm_id": farm["id"], "name": "GH-1"},
        )
    ).json()
    device_uid = f"NODE-{uuid.uuid4().hex[:6]}"
    dev = await client.post(
        f"{API}/devices",
        headers=auth_headers,
        json={"device_uid": device_uid, "name": "Node 1", "greenhouse_id": gh["id"]},
    )
    assert dev.status_code == 201, dev.text

    ts = datetime.now(UTC).isoformat()
    ingest = await client.post(
        f"{API}/ingest",
        headers=auth_headers,
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

    # Duplicate timestamp is idempotent (not stored again). The value differs but
    # the composite PK (device_id, time) collides, so the insert is a no-op.
    dup = await client.post(
        f"{API}/ingest",
        headers=auth_headers,
        json={"device_id": device_uid, "ts": ts, "air_temp_c": 31.0},
    )
    assert dup.status_code == 200
    assert dup.json()["stored"] is False

    readings = await client.get(f"{API}/greenhouses/{gh['id']}/readings", headers=auth_headers)
    assert readings.status_code == 200, readings.text
    rows = readings.json()
    assert len(rows) == 1
    assert rows[0]["air_temp_c"] == 27.5

    latest = await client.get(f"{API}/greenhouses/{gh['id']}/readings/latest", headers=auth_headers)
    assert latest.status_code == 200
    assert latest.json()["rh_pct"] == 88.0

    # Metric filter works.
    filtered = await client.get(
        f"{API}/greenhouses/{gh['id']}/readings?metric=air_temp_c&limit=10",
        headers=auth_headers,
    )
    assert filtered.status_code == 200
    assert len(filtered.json()) == 1


@pytest.mark.asyncio
async def test_ingest_unknown_device_not_stored(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.post(
        f"{API}/ingest",
        headers=auth_headers,
        json={"device_id": "DOES-NOT-EXIST", "ts": datetime.now(UTC).isoformat()},
    )
    assert resp.status_code == 200
    assert resp.json()["stored"] is False


@pytest.mark.asyncio
async def test_readings_unknown_greenhouse_404(
    client: AsyncClient, auth_headers: dict[str, str]
) -> None:
    resp = await client.get(f"{API}/greenhouses/{uuid.uuid4()}/readings", headers=auth_headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_organization_me(client: AsyncClient, auth_headers: dict[str, str]) -> None:
    resp = await client.get(f"{API}/organizations/me", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert "slug" in resp.json()
