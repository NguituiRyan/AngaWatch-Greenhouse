"""Password hashing + JWT helpers. Org-scoped claims travel in the token."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return _pwd.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd.verify(plain, hashed)


def _create_token(subject: str, claims: dict[str, Any], expires: timedelta) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + expires,
        "jti": str(uuid.uuid4()),
        **claims,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def create_access_token(*, user_id: str, org_id: str, role: str) -> str:
    return _create_token(
        subject=user_id,
        claims={"org_id": org_id, "role": role, "type": "access"},
        expires=timedelta(minutes=settings.access_token_expire_minutes),
    )


def create_refresh_token(*, user_id: str, org_id: str) -> str:
    return _create_token(
        subject=user_id,
        claims={"org_id": org_id, "type": "refresh"},
        expires=timedelta(days=settings.refresh_token_expire_days),
    )


def decode_token(token: str) -> dict[str, Any]:
    """Return the decoded claims or raise ``JWTError``."""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])


__all__ = [
    "JWTError",
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "hash_password",
    "verify_password",
]
