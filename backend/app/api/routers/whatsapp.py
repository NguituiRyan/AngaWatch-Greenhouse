"""Meta WhatsApp Cloud API webhook: verification (GET) + inbound messages (POST).

GET verifies the subscription by echoing ``hub.challenge`` when
``hub.verify_token`` matches ``settings.whatsapp_verify_token``. POST logs inbound
payloads (delivery/inbound handling is Wave 1; we just acknowledge for now).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.logging import get_logger

router = APIRouter(prefix="/whatsapp", tags=["whatsapp"])

log = get_logger(__name__)


@router.get("/webhook", response_class=PlainTextResponse)
async def verify_webhook(
    mode: str | None = Query(default=None, alias="hub.mode"),
    token: str | None = Query(default=None, alias="hub.verify_token"),
    challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> str:
    """Echo ``hub.challenge`` when the verify token matches (Meta handshake)."""
    if token == settings.whatsapp_verify_token and challenge is not None:
        log.info("whatsapp.webhook.verified", mode=mode)
        return challenge
    log.warning("whatsapp.webhook.verify_failed", mode=mode)
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="verify token mismatch")


@router.post("/webhook")
async def inbound_webhook(request: Request) -> dict[str, str]:
    """Acknowledge an inbound WhatsApp event (logged; processing is Wave 1 TODO)."""
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001 — Meta sometimes posts empty/non-JSON pings
        payload = {}
    log.info("whatsapp.webhook.inbound", keys=list(payload.keys()))
    # TODO(Wave 1): parse statuses + inbound messages, map to org via phone, and
    # feed farmer replies into the alert ack / recommendation acceptance loop.
    return {"status": "received"}
