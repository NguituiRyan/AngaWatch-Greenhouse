"""Greenhouse DTOs: create / update / read."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field

from app.api.schemas.common import ORMModel


class GreenhouseCreate(BaseModel):
    farm_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=160)
    zone: str | None = Field(None, max_length=80)
    structure_type: str | None = Field(None, max_length=80)
    area_m2: float | None = Field(None, ge=0)
    install_date: date | None = None
    notes: str | None = None


class GreenhouseUpdate(BaseModel):
    farm_id: uuid.UUID | None = None
    name: str | None = Field(None, min_length=1, max_length=160)
    zone: str | None = Field(None, max_length=80)
    structure_type: str | None = Field(None, max_length=80)
    area_m2: float | None = Field(None, ge=0)
    install_date: date | None = None
    notes: str | None = None


class GreenhouseOut(ORMModel):
    id: uuid.UUID
    org_id: uuid.UUID
    farm_id: uuid.UUID
    name: str
    zone: str | None = None
    structure_type: str | None = None
    area_m2: float | None = None
    install_date: date | None = None
    notes: str | None = None
