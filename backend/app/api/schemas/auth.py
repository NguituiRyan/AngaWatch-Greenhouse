"""Auth DTOs: token pair, registration request, and the ``/auth/me`` view."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid

from pydantic import BaseModel, EmailStr, Field

from app.api.schemas.common import ORMModel
from app.db.models.common import Language, UserRole


class TokenResponse(BaseModel):
    """Issued by ``/auth/login`` and ``/auth/refresh``."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class RegisterRequest(BaseModel):
    """Self-service signup (creates an org) or in-org user creation by an admin.

    When ``org_name`` is provided and the request is unauthenticated, a fresh
    organization is created with the caller as its ``coop_admin``. When the
    request is authenticated, the new user is created inside the caller's org
    with the requested ``role`` (defaults to ``farmer``).
    """

    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=1, max_length=160)
    phone: str | None = Field(None, max_length=32)
    org_name: str | None = Field(None, max_length=160)
    role: UserRole | None = None


class UserOut(ORMModel):
    """The authenticated user (``/auth/me`` and registration response)."""

    id: uuid.UUID
    org_id: uuid.UUID
    email: str
    full_name: str
    phone: str | None = None
    role: UserRole
    is_active: bool
    preferred_language: Language
