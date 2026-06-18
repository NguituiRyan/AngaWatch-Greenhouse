"""Recommendation DTOs + agronomist override request."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.common import Language


class RecommendationOut(BaseModel):
    """A plain-language action (EN + SW) with optional agronomist override."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    alert_id: uuid.UUID | None = None
    risk_assessment_id: uuid.UUID | None = None
    action_code: str
    message_en: str
    message_sw: str
    priority: int
    default_language: Language
    overridden: bool
    override_message: str | None = None
    override_by: uuid.UUID | None = None
    override_at: datetime | None = None
    farmer_accepted: bool | None = None


class OverrideIn(BaseModel):
    """Agronomist override payload."""

    message: str = Field(..., min_length=1, max_length=2000)
