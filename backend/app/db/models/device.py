"""Physical sensor/gateway devices. ``device_uid`` is the id used in MQTT topics."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, OrgScopedMixin, TimestampMixin, UUIDPkMixin, enum_column
from app.db.models.common import DeviceStatus, DeviceType

if TYPE_CHECKING:
    from app.db.models.farm import Greenhouse
    from app.db.models.reading import Reading


class Device(Base, UUIDPkMixin, OrgScopedMixin, TimestampMixin):
    __tablename__ = "devices"

    greenhouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("greenhouses.id", ondelete="SET NULL"), index=True, nullable=True
    )
    # Hardware identifier that appears in `farm/{org_id}/{device_uid}/telemetry`.
    device_uid: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    device_type: Mapped[DeviceType] = mapped_column(
        enum_column(DeviceType), default=DeviceType.SENSOR_NODE, nullable=False
    )
    status: Mapped[DeviceStatus] = mapped_column(
        enum_column(DeviceStatus), default=DeviceStatus.ACTIVE, nullable=False
    )
    firmware_version: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Denormalized health (also derivable from readings) for fast device-health UI.
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_battery_v: Mapped[float | None] = mapped_column(Float, nullable=True)
    last_rssi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    greenhouse: Mapped[Greenhouse | None] = relationship(back_populates="devices")
    readings: Mapped[list[Reading]] = relationship(back_populates="device")
