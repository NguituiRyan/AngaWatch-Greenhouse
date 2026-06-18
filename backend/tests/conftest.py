"""Shared test fixtures.

Unit tests for the risk engine need nothing but synthetic ``ReadingPoint``s.
DB/API tests run against an in-memory SQLite database (shared across connections
via ``StaticPool``) with the FastAPI ``get_db`` dependency overridden. SQLite is
fine here because the model uses portable types (generic JSON, Uuid, DateTime);
TimescaleDB specifics live only in migration 0002, which no-ops off PostgreSQL.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.models import Organization, User
from app.db.models.common import UserRole


@pytest_asyncio.fixture
async def engine():
    eng = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session_factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db(session_factory) -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as s:
        yield s


@pytest_asyncio.fixture
async def org(db) -> Organization:
    o = Organization(name="Demo Coop", slug=f"demo-{uuid.uuid4().hex[:8]}")
    db.add(o)
    await db.commit()
    await db.refresh(o)
    return o


@pytest_asyncio.fixture
async def user(db, org) -> User:
    u = User(
        org_id=org.id,
        email=f"farmer-{uuid.uuid4().hex[:6]}@example.com",
        hashed_password=hash_password("password123"),
        full_name="Test Farmer",
        role=UserRole.COOP_ADMIN,
    )
    db.add(u)
    await db.commit()
    await db.refresh(u)
    return u


@pytest_asyncio.fixture
async def auth_headers(user) -> dict[str, str]:
    token = create_access_token(user_id=str(user.id), org_id=str(user.org_id), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def client(session_factory) -> AsyncGenerator[AsyncClient, None]:
    """ASGI client with ``get_db`` overridden to use the in-memory DB."""
    from app.db.session import get_db
    from app.main import app

    async def _override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as s:
            try:
                yield s
                await s.commit()
            except Exception:
                await s.rollback()
                raise

    app.dependency_overrides[get_db] = _override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
