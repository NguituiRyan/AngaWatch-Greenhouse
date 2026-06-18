"""Aggregate every ORM model so ``Base.metadata`` is complete for Alembic + create_all.

Import order matters only for human readability; SQLAlchemy resolves relationships
by string name at mapper-configuration time.
"""

from app.db.base import Base
from app.db.models.billing import Installment, Payment, Subscription
from app.db.models.commerce import (
    Buyer,
    DryerUnit,
    InputOrder,
    InputProduct,
    Invoice,
    MarketListing,
)
from app.db.models.common import (
    ActuatorState,
    ActuatorType,
    AlertChannelType,
    AlertStatus,
    CommandSource,
    CommandStatus,
    CropStage,
    DeviceStatus,
    DeviceType,
    InvoiceStatus,
    Language,
    ListingStatus,
    OrderStatus,
    PaymentProviderType,
    PaymentStatus,
    PlanType,
    RiskLevel,
    RiskModelType,
    SubscriptionStatus,
    UserRole,
)
from app.db.models.control import ActuatorDevice, AutomationRule, ControlCommand
from app.db.models.crop import Crop, CropCycle
from app.db.models.device import Device
from app.db.models.farm import Farm, Greenhouse
from app.db.models.finance import CreditScore, FinancingProfile, TraceabilityRecord
from app.db.models.intelligence import (
    Alert,
    Recommendation,
    RiskAssessment,
    RiskModelConfig,
)
from app.db.models.organization import Organization, User
from app.db.models.reading import Reading
from app.db.models.records import Expense, FarmRecord, HarvestLog, SprayLog
from app.db.models.weather import WeatherForecast, WeatherObservation

__all__ = [
    "Base",
    # core
    "Organization",
    "User",
    "Farm",
    "Greenhouse",
    "Device",
    "Reading",
    "Crop",
    "CropCycle",
    # intelligence
    "RiskModelConfig",
    "RiskAssessment",
    "Alert",
    "Recommendation",
    # control
    "ActuatorDevice",
    "AutomationRule",
    "ControlCommand",
    # weather
    "WeatherObservation",
    "WeatherForecast",
    # records
    "FarmRecord",
    "SprayLog",
    "HarvestLog",
    "Expense",
    # commerce
    "Invoice",
    "InputProduct",
    "InputOrder",
    "Buyer",
    "MarketListing",
    "DryerUnit",
    # finance
    "FinancingProfile",
    "CreditScore",
    "TraceabilityRecord",
    # billing
    "Subscription",
    "Installment",
    "Payment",
    # enums
    "UserRole",
    "Language",
    "DeviceType",
    "DeviceStatus",
    "ActuatorType",
    "ActuatorState",
    "CropStage",
    "RiskModelType",
    "RiskLevel",
    "AlertChannelType",
    "AlertStatus",
    "CommandStatus",
    "CommandSource",
    "PlanType",
    "SubscriptionStatus",
    "PaymentStatus",
    "PaymentProviderType",
    "InvoiceStatus",
    "OrderStatus",
    "ListingStatus",
]
