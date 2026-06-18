"""Shared API dependencies: DB session, JWT auth, org scoping, role + feature gates.

Multi-tenant isolation rule: handlers receive ``current_user`` and MUST filter
every query by ``current_user.org_id``. ``OrgScopedSession`` bundles the session
with the caller's org_id to make that mechanical.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import JWTError, decode_token
from app.db.models.common import UserRole
from app.db.models.organization import User
from app.db.session import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=True)

DBSession = Annotated[AsyncSession, Depends(get_db)]

_CREDENTIALS_EXC = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: DBSession,
) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise _CREDENTIALS_EXC
        user_id = payload["sub"]
    except (JWTError, KeyError) as exc:
        raise _CREDENTIALS_EXC from exc

    user = await db.scalar(select(User).where(User.id == uuid.UUID(user_id)))
    if user is None or not user.is_active:
        raise _CREDENTIALS_EXC
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


@dataclass(slots=True)
class OrgScope:
    """Bundles the request session with the authenticated org_id + user."""

    db: AsyncSession
    org_id: uuid.UUID
    user: User


async def get_org_scope(user: CurrentUser, db: DBSession) -> OrgScope:
    return OrgScope(db=db, org_id=user.org_id, user=user)


Scope = Annotated[OrgScope, Depends(get_org_scope)]


def require_role(*roles: UserRole):
    """Dependency factory enforcing one of ``roles`` (super_admin always allowed)."""

    allowed = set(roles) | {UserRole.SUPER_ADMIN}

    async def _dep(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Requires role in {[r.value for r in roles]}",
            )
        return user

    return _dep


def require_feature(feature: str):
    """Gate premium features by subscription status (lazy import avoids cycles)."""

    async def _dep(scope: Scope) -> OrgScope:
        from app.billing.service import org_has_feature

        if not await org_has_feature(scope.db, scope.org_id, feature):
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail=f"Feature '{feature}' requires an active subscription",
            )
        return scope

    return _dep
