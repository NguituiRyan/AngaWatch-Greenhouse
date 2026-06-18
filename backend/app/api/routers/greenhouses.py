"""Greenhouse CRUD. Org-scoped; a greenhouse's parent farm must also be in-org."""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import Scope
from app.api.schemas.greenhouse import (
    GreenhouseCreate,
    GreenhouseOut,
    GreenhouseUpdate,
)
from app.core.logging import get_logger
from app.db.models import Farm, Greenhouse

log = get_logger(__name__)

router = APIRouter(prefix="/greenhouses", tags=["greenhouses"])


async def _get_owned_greenhouse(scope: Scope, greenhouse_id: uuid.UUID) -> Greenhouse:
    gh = await scope.db.scalar(
        select(Greenhouse).where(Greenhouse.id == greenhouse_id, Greenhouse.org_id == scope.org_id)
    )
    if gh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    return gh


async def _assert_farm_in_org(scope: Scope, farm_id: uuid.UUID) -> None:
    owned = await scope.db.scalar(
        select(Farm.id).where(Farm.id == farm_id, Farm.org_id == scope.org_id)
    )
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")


@router.get("", response_model=list[GreenhouseOut])
async def list_greenhouses(scope: Scope, farm_id: uuid.UUID | None = None) -> list[Greenhouse]:
    stmt = select(Greenhouse).where(Greenhouse.org_id == scope.org_id)
    if farm_id is not None:
        stmt = stmt.where(Greenhouse.farm_id == farm_id)
    rows = await scope.db.scalars(stmt.order_by(Greenhouse.created_at))
    return list(rows)


@router.post("", response_model=GreenhouseOut, status_code=status.HTTP_201_CREATED)
async def create_greenhouse(payload: GreenhouseCreate, scope: Scope) -> Greenhouse:
    await _assert_farm_in_org(scope, payload.farm_id)
    gh = Greenhouse(org_id=scope.org_id, **payload.model_dump())
    scope.db.add(gh)
    await scope.db.flush()
    await scope.db.refresh(gh)
    log.info("greenhouse.create", greenhouse_id=str(gh.id), org_id=str(scope.org_id))
    return gh


@router.get("/{greenhouse_id}", response_model=GreenhouseOut)
async def get_greenhouse(greenhouse_id: uuid.UUID, scope: Scope) -> Greenhouse:
    return await _get_owned_greenhouse(scope, greenhouse_id)


@router.patch("/{greenhouse_id}", response_model=GreenhouseOut)
async def update_greenhouse(
    greenhouse_id: uuid.UUID, payload: GreenhouseUpdate, scope: Scope
) -> Greenhouse:
    gh = await _get_owned_greenhouse(scope, greenhouse_id)
    data = payload.model_dump(exclude_unset=True)
    if "farm_id" in data and data["farm_id"] is not None:
        await _assert_farm_in_org(scope, data["farm_id"])
    for field, value in data.items():
        setattr(gh, field, value)
    await scope.db.flush()
    await scope.db.refresh(gh)
    return gh


@router.delete("/{greenhouse_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_greenhouse(greenhouse_id: uuid.UUID, scope: Scope) -> None:
    gh = await _get_owned_greenhouse(scope, greenhouse_id)
    await scope.db.delete(gh)
    await scope.db.flush()
    log.info("greenhouse.delete", greenhouse_id=str(greenhouse_id), org_id=str(scope.org_id))
