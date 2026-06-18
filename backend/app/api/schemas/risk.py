"""Risk assessment DTOs (read-only)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.common import RiskLevel, RiskModelType


class RiskAssessmentOut(BaseModel):
    """One persisted risk assessment for a greenhouse + model."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    crop_cycle_id: uuid.UUID | None = None
    model_type: RiskModelType
    level: RiskLevel
    score: float
    window_start: datetime | None = None
    window_end: datetime | None = None
    details: dict
    evaluated_at: datetime
