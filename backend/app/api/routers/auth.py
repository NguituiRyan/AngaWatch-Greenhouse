"""Authentication: login, register, current user, and token refresh.

Login uses the OAuth2 password flow (``username`` == email). Registration either
bootstraps a brand-new organization (caller becomes its ``coop_admin``) or, when
the request is authenticated, creates a user inside the caller's org.
"""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select

from app.api.deps import CurrentUser, DBSession
from app.api.schemas.auth import (
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserOut,
)
from app.core.logging import get_logger
from app.core.security import (
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.db.models import Organization, User
from app.db.models.common import UserRole

log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    base = _SLUG_RE.sub("-", name.strip().lower()).strip("-") or "org"
    return f"{base[:60]}-{uuid.uuid4().hex[:6]}"


def _token_pair(user: User) -> TokenResponse:
    return TokenResponse(
        access_token=create_access_token(
            user_id=str(user.id), org_id=str(user.org_id), role=user.role.value
        ),
        refresh_token=create_refresh_token(user_id=str(user.id), org_id=str(user.org_id)),
    )


def _bearer_token(request: Request) -> str | None:
    """Extract a bearer token from the Authorization header, if present.

    Used by ``/register`` which is dual-mode: anonymous (org bootstrap) or
    authenticated (in-org user creation). A plain ``OAuth2PasswordBearer`` cannot
    be optional here, so we read the header directly.
    """
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        return token
    return None


@router.post("/login", response_model=TokenResponse)
async def login(
    db: DBSession,
    form: Annotated[OAuth2PasswordRequestForm, Depends()],
) -> TokenResponse:
    """Verify email + password and issue an access/refresh token pair."""
    user = await db.scalar(select(User).where(User.email == form.username))
    if user is None or not verify_password(form.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    user.last_login_at = datetime.now(UTC)
    log.info("auth.login", user_id=str(user.id), org_id=str(user.org_id))
    return _token_pair(user)


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest,
    db: DBSession,
    token: Annotated[str | None, Depends(_bearer_token)],
) -> User:
    """Create a user.

    * Unauthenticated + ``org_name`` set: bootstrap a new org; caller becomes its
      ``coop_admin``.
    * Authenticated (bearer token present): create a user inside the caller's org
      with the requested role (defaults to ``farmer``). Only coop_admin /
      super_admin may do so.
    """
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    caller: User | None = None
    if token:
        try:
            claims = decode_token(token)
            if claims.get("type") != "access":
                raise JWTError("not an access token")
            caller = await db.scalar(select(User).where(User.id == uuid.UUID(claims["sub"])))
        except (JWTError, KeyError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

    if caller is not None:
        # In-org user creation by an admin.
        if caller.role not in {UserRole.COOP_ADMIN, UserRole.SUPER_ADMIN}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only an admin may create users in an organization",
            )
        org_id = caller.org_id
        role = payload.role or UserRole.FARMER
    else:
        # Self-service org bootstrap.
        if not payload.org_name:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="org_name is required to create a new organization",
            )
        org = Organization(
            name=payload.org_name,
            slug=_slugify(payload.org_name),
            contact_email=str(payload.email),
            contact_phone=payload.phone,
        )
        db.add(org)
        await db.flush()
        org_id = org.id
        role = UserRole.COOP_ADMIN

    user = User(
        org_id=org_id,
        email=str(payload.email),
        phone=payload.phone,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=role,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user)
    log.info("auth.register", user_id=str(user.id), org_id=str(org_id), role=role.value)
    return user


@router.get("/me", response_model=UserOut)
async def me(current_user: CurrentUser) -> User:
    """Return the authenticated user."""
    return current_user


@router.post("/refresh", response_model=TokenResponse)
async def refresh(payload: RefreshRequest, db: DBSession) -> TokenResponse:
    """Exchange a valid refresh token for a fresh access/refresh pair."""
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != "refresh":
            raise JWTError("not a refresh token")
        user_id = uuid.UUID(claims["sub"])
    except (JWTError, KeyError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user = await db.scalar(select(User).where(User.id == user_id))
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _token_pair(user)
