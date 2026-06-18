"""Alert feed DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.db.models.common import AlertStatus, RiskLevel, RiskModelType


class AlertOut(BaseModel):
    """An alert row in the org feed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    risk_assessment_id: uuid.UUID | None = None
    model_type: RiskModelType
    level: RiskLevel
    title: str
    dedup_key: str
    status: AlertStatus
    escalation_level: int
    first_seen_at: datetime
    last_sent_at: datetime | None = None
    acked_at: datetime | None = None
    acked_by: uuid.UUID | None = None
