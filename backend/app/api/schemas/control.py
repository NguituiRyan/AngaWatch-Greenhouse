"""Actuator + control-command DTOs."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    CommandSource,
    CommandStatus,
)


class ActuatorOut(BaseModel):
    """An actuator device exposed to the API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    greenhouse_id: uuid.UUID
    name: str
    actuator_type: ActuatorType
    state: ActuatorState
    is_online: bool
    last_state_change: datetime | None = None


class CommandIn(BaseModel):
    """Manual command request body."""

    command: str = Field(..., min_length=1, max_length=40)
    params: dict | None = None


class ControlCommandOut(BaseModel):
    """A queued/executed control command."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    actuator_device_id: uuid.UUID
    automation_rule_id: uuid.UUID | None = None
    command: str
    params: dict
    status: CommandStatus
    source: CommandSource
    issued_by: uuid.UUID | None = None
    issued_at: datetime
    sent_at: datetime | None = None
    acked_at: datetime | None = None
    error: str | None = None
