"""Channel-agnostic alerting: dispatcher + adapters (console/SMS/USSD/WhatsApp)."""

from app.alerting.base import (
    AlertChannel,
    DeliveryResult,
    OutgoingMessage,
    channel_registry,
)

__all__ = [
    "AlertChannel",
    "DeliveryResult",
    "OutgoingMessage",
    "channel_registry",
]
