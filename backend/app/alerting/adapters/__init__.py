"""Instantiate every channel adapter and register it into ``channel_registry``.

Importing this package (``app.alerting.adapters``) wires up all channels as a side
effect — the dispatcher relies on that. Console is always present; SMS and WhatsApp
register too but report ``is_configured() == False`` until their credentials exist,
at which point the dispatcher routes to them (and falls back to console otherwise).
"""

from __future__ import annotations

from app.alerting.adapters.console import ConsoleChannel
from app.alerting.adapters.sms_africastalking import AfricasTalkingSMSChannel
from app.alerting.adapters.whatsapp_meta import WhatsAppMetaChannel
from app.alerting.base import channel_registry

# Singletons, registered keyed by their ``channel`` enum value.
console_channel = channel_registry.register(ConsoleChannel())
sms_channel = channel_registry.register(AfricasTalkingSMSChannel())
whatsapp_channel = channel_registry.register(WhatsAppMetaChannel())

__all__ = [
    "AfricasTalkingSMSChannel",
    "ConsoleChannel",
    "WhatsAppMetaChannel",
    "console_channel",
    "sms_channel",
    "whatsapp_channel",
]
