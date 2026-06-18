"""Farm-record DTOs: spray logs, harvest logs, expenses (Wave 1 scaffold)."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class SprayLogIn(BaseModel):
    crop_cycle_id: uuid.UUID
    product: str = Field(..., min_length=1, max_length=120)
    active_ingredient: str | None = None
    dose: float | None = None
    dose_unit: str | None = None
    target: str | None = None
    phi_days: int | None = None
    applied_at: date
    notes: str | None = None


class SprayLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    crop_cycle_id: uuid.UUID
    product: str
    active_ingredient: str | None = None
    dose: float | None = None
    dose_unit: str | None = None
    target: str | None = None
    phi_days: int | None = None
    applied_at: date
    applied_by: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime


class HarvestLogIn(BaseModel):
    crop_cycle_id: uuid.UUID
    quantity_kg: float = Field(..., ge=0)
    grade: str | None = None
    harvested_at: date
    notes: str | None = None


class HarvestLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    crop_cycle_id: uuid.UUID
    quantity_kg: float
    grade: str | None = None
    harvested_at: date
    harvested_by: uuid.UUID | None = None
    notes: str | None = None
    created_at: datetime


class ExpenseIn(BaseModel):
    farm_id: uuid.UUID | None = None
    crop_cycle_id: uuid.UUID | None = None
    category: str = Field(..., min_length=1, max_length=60)
    amount: float = Field(..., ge=0)
    currency: str = "KES"
    description: str | None = None
    incurred_at: date


class ExpenseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    farm_id: uuid.UUID | None = None
    crop_cycle_id: uuid.UUID | None = None
    category: str
    amount: float
    currency: str
    description: str | None = None
    incurred_at: date
    created_at: datetime
