"""Shared enums used across the data model and the API/risk layers."""

from __future__ import annotations

import enum


class StrEnum(enum.StrEnum):
    """JSON/DB-friendly string enum (Python 3.12 ``enum.StrEnum``).

    ``str(member) == member.value`` and ``member == member.value`` hold, which is
    what the VARCHAR-backed ``enum_column`` and JSON serialization rely on.
    """


class UserRole(StrEnum):
    FARMER = "farmer"
    AGRONOMIST = "agronomist"
    COOP_ADMIN = "coop_admin"
    SUPER_ADMIN = "super_admin"


class Language(StrEnum):
    EN = "en"
    SW = "sw"


class DeviceType(StrEnum):
    SENSOR_NODE = "sensor_node"
    GATEWAY = "gateway"
    ACTUATOR = "actuator"


class DeviceStatus(StrEnum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAULT = "fault"


class ActuatorType(StrEnum):
    VENT = "vent"
    FAN = "fan"
    DRIP_VALVE = "drip_valve"
    FERTIGATION_PUMP = "fertigation_pump"


class ActuatorState(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class CropStage(StrEnum):
    SEEDLING = "seedling"
    VEGETATIVE = "vegetative"
    FLOWERING = "flowering"
    FRUITING = "fruiting"
    RIPENING = "ripening"
    HARVEST = "harvest"


class RiskModelType(StrEnum):
    LATE_BLIGHT = "late_blight"
    TUTA_ABSOLUTA = "tuta_absoluta"
    MICROCLIMATE = "microclimate"
    NUTRIENT = "nutrient"
    WATER = "water"


class RiskLevel(StrEnum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return {"none": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}[self.value]


class AlertChannelType(StrEnum):
    CONSOLE = "console"
    SMS = "sms"
    USSD = "ussd"
    WHATSAPP = "whatsapp"


class AlertStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    ACKED = "acked"
    ESCALATED = "escalated"
    SUPPRESSED = "suppressed"


class CommandStatus(StrEnum):
    QUEUED = "queued"
    SENT = "sent"
    ACKED = "acked"
    FAILED = "failed"
    EXPIRED = "expired"


class CommandSource(StrEnum):
    AUTO = "auto"
    MANUAL = "manual"


class PlanType(StrEnum):
    SUBSCRIPTION = "subscription"
    RENT_TO_OWN = "rent_to_own"
    DAAS = "daas"


class SubscriptionStatus(StrEnum):
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REVERSED = "reversed"


class PaymentProviderType(StrEnum):
    MPESA = "mpesa"
    MANUAL = "manual"


class InvoiceStatus(StrEnum):
    DRAFT = "draft"
    ISSUED = "issued"
    PAID = "paid"
    OVERDUE = "overdue"
    CANCELLED = "cancelled"


class OrderStatus(StrEnum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    FULFILLED = "fulfilled"
    CANCELLED = "cancelled"


class ListingStatus(StrEnum):
    OPEN = "open"
    MATCHED = "matched"
    CLOSED = "closed"
