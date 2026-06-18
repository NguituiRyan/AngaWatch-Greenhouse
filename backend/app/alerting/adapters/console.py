"""Console channel: always configured, prints a structured line. The universal fallback.

This adapter never needs credentials, so the whole alerting stack runs offline. The
dispatcher falls back to it whenever a richer channel (SMS/WhatsApp) is unconfigured.
"""

from __future__ import annotations

from typing import ClassVar

from app.alerting.base import AlertChannel, DeliveryResult, OutgoingMessage
from app.core.logging import get_logger
from app.db.models.common import AlertChannelType

log = get_logger("alerting.console")


class ConsoleChannel(AlertChannel):
    """Emits a structured log event instead of hitting an external provider."""

    channel: ClassVar[AlertChannelType] = AlertChannelType.CONSOLE

    def is_configured(self) -> bool:  # noqa: D102 - always available
        return True

    def send(self, message: OutgoingMessage) -> DeliveryResult:
        log.info(
            "alert.console.send",
            to=message.to,
            language=message.language.value,
            title=message.title,
            body=message.body,
        )
        return DeliveryResult(
            ok=True,
            channel=self.channel,
            provider_message_id=None,
            status="printed",
        )
