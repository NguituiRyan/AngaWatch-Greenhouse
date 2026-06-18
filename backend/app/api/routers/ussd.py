"""Africa's Talking USSD webhook.

AT posts ``application/x-www-form-urlencoded`` with ``sessionId``, ``phoneNumber``
and ``text`` and expects a ``text/plain`` body starting with ``CON``/``END``.

The menu logic lives in :func:`app.alerting.ussd.handle_ussd`, which is a pure
function over a *sync* session, so we run it in a threadpool with a fresh sync
session (``get_sync_session``) to avoid blocking the event loop.
"""

from __future__ import annotations

from fastapi import APIRouter, Form
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import PlainTextResponse

from app.alerting.ussd import handle_ussd
from app.core.logging import get_logger
from app.db.session import get_sync_session

router = APIRouter(tags=["ussd"])

log = get_logger(__name__)


def _handle_sync(session_id: str, phone: str, text: str) -> str:
    session = get_sync_session()
    try:
        return handle_ussd(session, session_id=session_id, phone=phone, text=text)
    finally:
        session.close()


@router.post("/ussd", response_class=PlainTextResponse)
async def ussd_webhook(
    sessionId: str = Form(default=""),  # noqa: N803 — AT field name
    phoneNumber: str = Form(default=""),  # noqa: N803 — AT field name
    text: str = Form(default=""),
) -> str:
    """Render the USSD pull menu for the dialing phone number."""
    log.info("ussd.request", session_id=sessionId, phone=phoneNumber)
    return await run_in_threadpool(_handle_sync, sessionId, phoneNumber, text)
