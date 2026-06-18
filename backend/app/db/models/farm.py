"""Farm and Greenhouse (zone). A greenhouse is the unit the risk engine evaluates."""

from __future__ import annotations

import uuid
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Float, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.db.models.control import ActuatorDevice
    from app.db.models.crop import CropCycle
    from app.db.models.device import Device
    from app.db.models.organization import Organization


class Farm(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "farms"

    name: Mapped[str] = mapped_column(String(160), nullable=False)
    county: Mapped[str | None] = mapped_column(String(80), nullable=True)  # e.g. Kiambu, Nakuru
    location: Mapped[str | None] = mapped_column(String(160), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    area_ha: Mapped[float | None] = mapped_column(Float, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="farms")
    greenhouses: Mapped[list[Greenhouse]] = relationship(
        back_populates="farm", cascade="all, delete-orphan"
    )


class Greenhouse(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    """A controlled zone inside a farm. Risk assessments are per-greenhouse."""

    __tablename__ = "greenhouses"

    farm_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("farms.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    zone: Mapped[str | None] = mapped_column(String(80), nullable=True)
    structure_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    area_m2: Mapped[float | None] = mapped_column(Float, nullable=True)
    install_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    farm: Mapped[Farm] = relationship(back_populates="greenhouses")
    devices: Mapped[list[Device]] = relationship(back_populates="greenhouse")
    crop_cycles: Mapped[list[CropCycle]] = relationship(back_populates="greenhouse")
    actuator_devices: Mapped[list[ActuatorDevice]] = relationship(back_populates="greenhouse")
