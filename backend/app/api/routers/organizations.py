"""Organization endpoints: read your own org; super_admin may update any org."""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from app.api.deps import Scope, require_role
from app.api.schemas.org import OrganizationOut, OrganizationUpdate
from app.db.models import Organization
from app.db.models.common import UserRole

router = APIRouter(prefix="/organizations", tags=["organizations"])


async def _load_org(scope: Scope, org_id: uuid.UUID) -> Organization:
    org = await scope.db.scalar(select(Organization).where(Organization.id == org_id))
    if org is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Organization not found")
    return org


@router.get("/me", response_model=OrganizationOut)
async def read_my_org(scope: Scope) -> Organization:
    """Return the caller's organization."""
    return await _load_org(scope, scope.org_id)


@router.patch(
    "/me",
    response_model=OrganizationOut,
    dependencies=[Depends(require_role(UserRole.COOP_ADMIN))],
)
async def update_my_org(payload: OrganizationUpdate, scope: Scope) -> Organization:
    """Update the caller's organization (coop_admin / super_admin only)."""
    org = await _load_org(scope, scope.org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await scope.db.flush()
    await scope.db.refresh(org)
    return org


@router.patch(
    "/{org_id}",
    response_model=OrganizationOut,
    dependencies=[Depends(require_role(UserRole.SUPER_ADMIN))],
)
async def update_org(org_id: uuid.UUID, payload: OrganizationUpdate, scope: Scope) -> Organization:
    """Cross-tenant org update (super_admin only)."""
    org = await _load_org(scope, org_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(org, field, value)
    await scope.db.flush()
    await scope.db.refresh(org)
    return org
