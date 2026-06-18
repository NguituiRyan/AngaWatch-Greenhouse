"""Africa's Talking SMS channel (httpx). Falls back to console when unconfigured.

``is_configured()`` checks ``settings.at_api_key``; the dispatcher routes to the
console adapter whenever that returns ``False`` so the stack runs with zero accounts.
"""

from __future__ import annotations

from typing import ClassVar

import httpx

from app.alerting.base import AlertChannel, DeliveryResult, OutgoingMessage
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.common import AlertChannelType

log = get_logger("alerting.sms")

_SANDBOX_URL = "https://api.sandbox.africastalking.com/version1/messaging"
_LIVE_URL = "https://api.africastalking.com/version1/messaging"
_TIMEOUT = 10.0


class AfricasTalkingSMSChannel(AlertChannel):
    """Sends SMS via the Africa's Talking bulk messaging API."""

    channel: ClassVar[AlertChannelType] = AlertChannelType.SMS

    def is_configured(self) -> bool:
        return bool(settings.at_api_key)

    @property
    def _endpoint(self) -> str:
        return _SANDBOX_URL if settings.at_use_sandbox else _LIVE_URL

    def send(self, message: OutgoingMessage) -> DeliveryResult:
        if not self.is_configured():
            # Defensive: dispatcher should already have routed to console.
            log.warning("alert.sms.unconfigured", to=message.to)
            return DeliveryResult(
                ok=False,
                channel=self.channel,
                status="unconfigured",
                error="at_api_key not set",
            )

        payload = {
            "username": settings.at_username,
            "to": message.to,
            "message": message.body,
            "from": settings.at_sender_id,
        }
        headers = {
            "apiKey": settings.at_api_key or "",
            "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            resp = httpx.post(self._endpoint, data=payload, headers=headers, timeout=_TIMEOUT)
            resp.raise_for_status()
            data = resp.json()
            recipients = data.get("SMSMessageData", {}).get("Recipients", [])
            first = recipients[0] if recipients else {}
            provider_id = first.get("messageId")
            status = first.get("status", "submitted")
            ok = bool(recipients) and status.lower() in {"success", "sent", "submitted"}
            log.info("alert.sms.send", to=message.to, status=status, ok=ok)
            return DeliveryResult(
                ok=ok,
                channel=self.channel,
                provider_message_id=provider_id,
                status=status,
                raw=data,
            )
        except (httpx.HTTPError, ValueError, KeyError) as exc:  # network/JSON errors
            log.warning("alert.sms.error", to=message.to, error=str(exc))
            return DeliveryResult(
                ok=False,
                channel=self.channel,
                status="error",
                error=str(exc),
            )
