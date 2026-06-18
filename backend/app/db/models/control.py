"""Closed-loop control: actuators, automation rules, command queue (with safety)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    CommandSource,
    CommandStatus,
)

if TYPE_CHECKING:
    from app.db.models.farm import Greenhouse


class ActuatorDevice(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "actuator_devices"

    greenhouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # The node that physically drives this actuator (relay/GPIO), if any.
    device_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("devices.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    actuator_type: Mapped[ActuatorType] = mapped_column(enum_column(ActuatorType), nullable=False)
    state: Mapped[ActuatorState] = mapped_column(
        enum_column(ActuatorState), default=ActuatorState.UNKNOWN, nullable=False
    )
    is_online: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Safety interlock defaults (e.g. max open minutes, min cycle interval).
    config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    last_state_change: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    greenhouse: Mapped[Greenhouse] = relationship(back_populates="actuator_devices")
    commands: Mapped[list[ControlCommand]] = relationship(back_populates="actuator")


class AutomationRule(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """condition -> action. Wave 0: stored & manually triggerable. Wave 1: auto-fired.

    ``condition`` example: {"metric": "rh_pct", "op": ">=", "value": 90, "duration_min": 600}
    ``action`` example:    {"actuator_type": "vent", "command": "open"}
    ``safety_interlocks``: {"max_open_min": 120, "min_air_temp_c": 12}
    """

    __tablename__ = "automation_rules"

    greenhouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    condition: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    action: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    safety_interlocks: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_triggered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ControlCommand(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "control_commands"

    actuator_device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("actuator_devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    automation_rule_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("automation_rules.id", ondelete="SET NULL"), nullable=True
    )
    command: Mapped[str] = mapped_column(String(40), nullable=False)  # open|close|on|off
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[CommandStatus] = mapped_column(
        enum_column(CommandStatus), default=CommandStatus.QUEUED, nullable=False
    )
    source: Mapped[CommandSource] = mapped_column(
        enum_column(CommandSource), default=CommandSource.MANUAL, nullable=False
    )
    issued_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    actuator: Mapped[ActuatorDevice] = relationship(back_populates="commands")
