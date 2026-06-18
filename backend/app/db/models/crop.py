"""Crop catalog + per-greenhouse crop cycles (tomato first)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import CropStage

if TYPE_CHECKING:
    from app.db.models.farm import Greenhouse
    from app.db.models.records import HarvestLog, SprayLog


class Crop(Base, UUIDPkMixin, TimestampMixin):
    """Shared agronomic library entry. ``org_id`` is nullable => global default crop.

    ``npk_targets`` maps crop stage -> {n,p,k} ppm targets used by NutrientModel;
    ``stage_durations_days`` drives auto stage progression of a CropCycle.
    """

    __tablename__ = "crops"

    org_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)  # e.g. "tomato"
    variety: Mapped[str | None] = mapped_column(String(80), nullable=True)
    npk_targets: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    stage_durations_days: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    cycles: Mapped[list[CropCycle]] = relationship(back_populates="crop")


class CropCycle(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "crop_cycles"

    org_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    greenhouse_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="CASCADE"), index=True, nullable=False
    )
    crop_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("crops.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    crop_name: Mapped[str] = mapped_column(String(80), nullable=False)
    planting_date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_harvest_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    current_stage: Mapped[CropStage] = mapped_column(
        enum_column(CropStage), default=CropStage.SEEDLING, nullable=False
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    greenhouse: Mapped[Greenhouse] = relationship(back_populates="crop_cycles")
    crop: Mapped[Crop] = relationship(back_populates="cycles")
    spray_logs: Mapped[list[SprayLog]] = relationship(back_populates="crop_cycle")
    harvest_logs: Mapped[list[HarvestLog]] = relationship(back_populates="crop_cycle")
