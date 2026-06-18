"""Device CRUD. Org-scoped; a device's greenhouse (if set) must be in-org too."""

# ruff: noqa: TC001, TC002, TC003 — FastAPI resolves dep/param annotations at runtime.

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import Scope
from app.api.schemas.device import DeviceCreate, DeviceOut, DeviceUpdate
from app.core.logging import get_logger
from app.db.models import Device, Greenhouse

log = get_logger(__name__)

router = APIRouter(prefix="/devices", tags=["devices"])


async def _get_owned_device(scope: Scope, device_id: uuid.UUID) -> Device:
    dev = await scope.db.scalar(
        select(Device).where(Device.id == device_id, Device.org_id == scope.org_id)
    )
    if dev is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Device not found")
    return dev


async def _assert_greenhouse_in_org(scope: Scope, greenhouse_id: uuid.UUID) -> None:
    owned = await scope.db.scalar(
        select(Greenhouse.id).where(
            Greenhouse.id == greenhouse_id, Greenhouse.org_id == scope.org_id
        )
    )
    if owned is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")


@router.get("", response_model=list[DeviceOut])
async def list_devices(scope: Scope, greenhouse_id: uuid.UUID | None = None) -> list[Device]:
    stmt = select(Device).where(Device.org_id == scope.org_id)
    if greenhouse_id is not None:
        stmt = stmt.where(Device.greenhouse_id == greenhouse_id)
    rows = await scope.db.scalars(stmt.order_by(Device.created_at))
    return list(rows)


@router.post("", response_model=DeviceOut, status_code=status.HTTP_201_CREATED)
async def create_device(payload: DeviceCreate, scope: Scope) -> Device:
    if payload.greenhouse_id is not None:
        await _assert_greenhouse_in_org(scope, payload.greenhouse_id)
    dev = Device(org_id=scope.org_id, **payload.model_dump())
    scope.db.add(dev)
    try:
        await scope.db.flush()
    except IntegrityError as exc:
        await scope.db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="device_uid already registered"
        ) from exc
    await scope.db.refresh(dev)
    log.info("device.create", device_id=str(dev.id), org_id=str(scope.org_id))
    return dev


@router.get("/{device_id}", response_model=DeviceOut)
async def get_device(device_id: uuid.UUID, scope: Scope) -> Device:
    return await _get_owned_device(scope, device_id)


@router.patch("/{device_id}", response_model=DeviceOut)
async def update_device(device_id: uuid.UUID, payload: DeviceUpdate, scope: Scope) -> Device:
    dev = await _get_owned_device(scope, device_id)
    data = payload.model_dump(exclude_unset=True)
    if "greenhouse_id" in data and data["greenhouse_id"] is not None:
        await _assert_greenhouse_in_org(scope, data["greenhouse_id"])
    for field, value in data.items():
        setattr(dev, field, value)
    await scope.db.flush()
    await scope.db.refresh(dev)
    return dev


@router.delete("/{device_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_device(device_id: uuid.UUID, scope: Scope) -> None:
    dev = await _get_owned_device(scope, device_id)
    await scope.db.delete(dev)
    await scope.db.flush()
    log.info("device.delete", device_id=str(device_id), org_id=str(scope.org_id))
