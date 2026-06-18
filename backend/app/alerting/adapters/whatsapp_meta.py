"""Meta WhatsApp Cloud API channel (httpx). Falls back to console when unconfigured.

``is_configured()`` requires both ``whatsapp_access_token`` and
``whatsapp_phone_number_id``. We send a plain text message (the simplest body that
needs no pre-approved template); template params can be threaded through ``meta`` later.
"""

from __future__ import annotations

from typing import ClassVar

import httpx

from app.alerting.base import AlertChannel, DeliveryResult, OutgoingMessage
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.common import AlertChannelType

log = get_logger("alerting.whatsapp")

_TIMEOUT = 10.0


class WhatsAppMetaChannel(AlertChannel):
    """Sends WhatsApp messages via the Meta Cloud API graph endpoint."""

    channel: ClassVar[AlertChannelType] = AlertChannelType.WHATSAPP

    def is_configured(self) -> bool:
        return bool(settings.whatsapp_access_token and settings.whatsapp_phone_number_id)

    @property
    def _endpoint(self) -> str:
        return (
            f"https://graph.facebook.com/{settings.whatsapp_api_version}/"
            f"{settings.whatsapp_phone_number_id}/messages"
        )

    def send(self, message: OutgoingMessage) -> DeliveryResult:
        if not self.is_configured():
            log.warning("alert.whatsapp.unconfigured", to=message.to)
            return DeliveryResult(
                ok=False,
                channel=self.channel,
                status="unconfigured",
                error="whatsapp token/phone_number_id not set",
            )

        body = message.body
        if message.title:
            body = f"*{message.title}*\n{body}"
        payload = {
            "messaging_product": "whatsapp",
            "to": message.to,
            "type": "text",
            "text": {"body": body},
        }
        headers = {
            "Authorization": f"Bearer {settings.whatsapp_access_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = httpx.post(self._endpoint, json=payload, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            messages = data.get("messages", [])
            provider_id = messages[0].get("id") if messages else None
            ok = bool(messages)
            log.info("alert.whatsapp.send", to=message.to, ok=ok)
            return DeliveryResult(
                ok=ok,
                channel=self.channel,
                provider_message_id=provider_id,
                status="sent" if ok else "rejected",
                raw=data,
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            log.warning("alert.whatsapp.error", to=message.to, error=str(exc))
            return DeliveryResult(
                ok=False,
                channel=self.channel,
                status="error",
                error=str(exc),
            )
