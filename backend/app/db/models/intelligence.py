"""The core IP layer: calibratable model config + assessments, alerts, recommendations."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import (
    AlertStatus,
    Language,
    RiskLevel,
    RiskModelType,
)

if TYPE_CHECKING:
    from app.db.models.organization import User


class RiskModelConfig(Base, UUIDPkMixin, TimestampMixin):
    """Calibratable parameters for one risk model.

    Scope precedence (most specific wins): greenhouse_id > org_id > global(null).
    ``params`` holds the model-specific knobs (e.g. blight rh/temp thresholds,
    Tuta base temp + generation degree-days). Defaults are seeded and documented.
    """

    __tablename__ = "risk_model_configs"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    greenhouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="CASCADE"), index=True, nullable=True
    )
    crop: Mapped[str | None] = mapped_column(String(80), nullable=True)
    model_type: Mapped[RiskModelType] = mapped_column(enum_column(RiskModelType), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    params: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class RiskAssessment(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "risk_assessments"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    greenhouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    crop_cycle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("crop_cycles.id", ondelete="SET NULL"), nullable=True
    )
    model_type: Mapped[RiskModelType] = mapped_column(enum_column(RiskModelType), nullable=False)
    level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel), nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Evidence: wet_hours, dd_accumulated, latest values, forecast fusion, etc.
    details: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    alerts: Mapped[list[Alert]] = relationship(back_populates="risk_assessment")
    recommendation: Mapped[Recommendation | None] = relationship(
        back_populates="risk_assessment", uselist=False
    )


class Alert(Base, UUIDPkMixin, TimestampMixin):
    """A dispatchable alert. ``dedup_key`` collapses repeats of the same condition."""

    __tablename__ = "alerts"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    greenhouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    risk_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True
    )
    model_type: Mapped[RiskModelType] = mapped_column(enum_column(RiskModelType), nullable=False)
    level: Mapped[RiskLevel] = mapped_column(enum_column(RiskLevel), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    dedup_key: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    status: Mapped[AlertStatus] = mapped_column(
        enum_column(AlertStatus), default=AlertStatus.PENDING, nullable=False
    )
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Per-channel dispatch attempts: [{channel, status, provider_id, at, error}]
    dispatch_log: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    acked_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    risk_assessment: Mapped[RiskAssessment | None] = relationship(back_populates="alerts")
    recommendation: Mapped[Recommendation | None] = relationship(
        back_populates="alert", uselist=False
    )


class Recommendation(Base, UUIDPkMixin, TimestampMixin):
    """Plain-language action (EN + SW). Agronomist overrides are kept as training signal."""

    __tablename__ = "recommendations"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    alert_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("alerts.id", ondelete="CASCADE"), nullable=True
    )
    risk_assessment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("risk_assessments.id", ondelete="SET NULL"), nullable=True
    )
    action_code: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "ventilate_now"
    message_en: Mapped[str] = mapped_column(Text, nullable=False)
    message_sw: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    default_language: Mapped[Language] = mapped_column(
        enum_column(Language), default=Language.EN, nullable=False
    )

    # Agronomist review loop — stored as a future training signal.
    overridden: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    override_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    override_by: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    override_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    farmer_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    alert: Mapped[Alert | None] = relationship(back_populates="recommendation")
    risk_assessment: Mapped[RiskAssessment | None] = relationship(back_populates="recommendation")
    reviewer: Mapped[User | None] = relationship(foreign_keys=[override_by])
