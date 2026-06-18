"""Farm DTOs: create / update / read."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.api.schemas.common import ORMModel


class FarmCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    county: str | None = Field(None, max_length=80)
    location: str | None = Field(None, max_length=160)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    area_ha: float | None = Field(None, ge=0)


class FarmUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=160)
    county: str | None = Field(None, max_length=80)
    location: str | None = Field(None, max_length=160)
    latitude: float | None = Field(None, ge=-90, le=90)
    longitude: float | None = Field(None, ge=-180, le=180)
    area_ha: float | None = Field(None, ge=0)


class FarmOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    name: str
    county: str | None = None
    location: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    area_ha: float | None = None
