"""Shared base config + tiny helpers for API DTOs (Pydantic v2)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    """Read-side base: populate response models straight from ORM rows."""

    model_config = ConfigDict(from_attributes=True)
