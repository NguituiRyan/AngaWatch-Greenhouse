"""Farm CRUD. Every query is filtered by ``scope.org_id`` (tenant isolation)."""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import Scope
from app.api.schemas.farm import FarmCreate, FarmOut, FarmUpdate
from app.core.logging import get_logger
from app.db.models import Farm

log = get_logger(__name__)

router = APIRouter(prefix="/farms", tags=["farms"])


async def _get_owned_farm(scope: Scope, farm_id: uuid.UUID) -> Farm:
    farm = await scope.db.scalar(
        select(Farm).where(Farm.id == farm_id, Farm.org_id == scope.org_id)
    )
    if farm is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Farm not found")
    return farm


@router.get("", response_model=list[FarmOut])
async def list_farms(scope: Scope) -> list[Farm]:
    rows = await scope.db.scalars(
        select(Farm).where(Farm.org_id == scope.org_id).order_by(Farm.created_at)
    )
    return list(rows)


@router.post("", response_model=FarmOut, status_code=status.HTTP_201_CREATED)
async def create_farm(payload: FarmCreate, scope: Scope) -> Farm:
    farm = Farm(org_id=scope.org_id, **payload.model_dump())
    scope.db.add(farm)
    await scope.db.flush()
    await scope.db.refresh(farm)
    log.info("farm.create", farm_id=str(farm.id), org_id=str(scope.org_id))
    return farm


@router.get("/{farm_id}", response_model=FarmOut)
async def get_farm(farm_id: uuid.UUID, scope: Scope) -> Farm:
    return await _get_owned_farm(scope, farm_id)


@router.patch("/{farm_id}", response_model=FarmOut)
async def update_farm(farm_id: uuid.UUID, payload: FarmUpdate, scope: Scope) -> Farm:
    farm = await _get_owned_farm(scope, farm_id)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(farm, field, value)
    await scope.db.flush()
    await scope.db.refresh(farm)
    return farm


@router.delete("/{farm_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_farm(farm_id: uuid.UUID, scope: Scope) -> None:
    farm = await _get_owned_farm(scope, farm_id)
    await scope.db.delete(farm)
    await scope.db.flush()
    log.info("farm.delete", farm_id=str(farm_id), org_id=str(scope.org_id))
