"""Organization DTOs."""

# ruff: noqa: TC001, TC002, TC003 — Pydantic v2 resolves annotations at runtime.

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field

from app.api.schemas.common import ORMModel


class OrganizationOut(ORMModel):
    id: uuid.UUID
    name: str
    slug: str
    is_reseller: bool
    white_label: bool
    country: str
    timezone: str
    contact_email: str | None = None
    contact_phone: str | None = None


class OrganizationUpdate(BaseModel):
    name: str | None = Field(None, max_length=160)
    contact_email: str | None = Field(None, max_length=160)
    contact_phone: str | None = Field(None, max_length=32)
    country: str | None = Field(None, max_length=64)
    timezone: str | None = Field(None, max_length=48)
