"""Async engine + session for the API; sync engine for Celery/Alembic paths."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

# ---- Async (FastAPI request path) ----
async_engine = create_async_engine(
    settings.database_url,
    echo=settings.db_echo,
    pool_pre_ping=True,
    future=True,
)
AsyncSessionLocal = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

# ---- Sync (Celery tasks, ingestion writer, seed scripts) ----
sync_engine = create_engine(
    settings.database_url_sync,
    echo=settings.db_echo,
    pool_pre_ping=True,
    future=True,
)
SyncSessionLocal = sessionmaker(bind=sync_engine, expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_session() -> Session:
    """For Celery/ingestion/seed. Caller is responsible for commit/close."""
    return SyncSessionLocal()
