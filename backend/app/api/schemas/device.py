"""Device DTOs: create / update / read."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.api.schemas.common import ORMModel
from app.db.models.common import DeviceStatus, DeviceType


class DeviceCreate(BaseModel):
    device_uid: str = Field(..., min_length=1, max_length=80)
    name: str = Field(..., min_length=1, max_length=120)
    greenhouse_id: uuid.UUID | None = None
    device_type: DeviceType = DeviceType.SENSOR_NODE
    firmware_version: str | None = Field(None, max_length=32)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class DeviceUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=120)
    greenhouse_id: uuid.UUID | None = None
    device_type: DeviceType | None = None
    status: DeviceStatus | None = None
    firmware_version: str | None = Field(None, max_length=32)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)


class DeviceOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    greenhouse_id: uuid.UUID | None = None
    device_uid: str
    name: str
    device_type: DeviceType
    status: DeviceStatus
    firmware_version: str | None = None
    last_seen_at: datetime | None = None
    last_battery_v: float | None = None
    last_rssi: int | None = None
    latitude: float | None = None
    longitude: float | None = None
