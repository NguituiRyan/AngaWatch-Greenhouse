"""M-Pesa Daraja sandbox payment provider.

Implements the Lipa na M-Pesa Online (STK Push) flow against the Safaricom
Daraja API. Credentials come from :mod:`app.core.config`; when they are absent
the higher-level :func:`app.billing.providers.get_payment_provider` returns the
mock provider instead so the stack runs fully offline.

Reference: https://developer.safaricom.co.ke (sandbox base
``https://sandbox.safaricom.co.ke``).
"""

from __future__ import annotations

import base64
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from app.billing.base import (
    CallbackResult,
    PaymentProvider,
    STKPushRequest,
    STKPushResult,
)
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

_SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
_PRODUCTION_BASE = "https://api.safaricom.co.ke"
_NAIROBI = ZoneInfo("Africa/Nairobi")
_HTTP_TIMEOUT = 30.0


def _timestamp(now: datetime | None = None) -> str:
    """Daraja timestamp ``YYYYMMDDHHMMSS`` in Africa/Nairobi local time."""
    now = now or datetime.now(_NAIROBI)
    return now.astimezone(_NAIROBI).strftime("%Y%m%d%H%M%S")


def _password(shortcode: str, passkey: str, timestamp: str) -> str:
    """``base64(shortcode + passkey + timestamp)`` per the Daraja spec."""
    raw = f"{shortcode}{passkey}{timestamp}".encode()
    return base64.b64encode(raw).decode()


class MpesaProvider(PaymentProvider):
    """Real Daraja STK-push integration over httpx."""

    name = "mpesa"

    def __init__(
        self,
        *,
        consumer_key: str,
        consumer_secret: str,
        shortcode: str,
        passkey: str,
        callback_base_url: str,
        transaction_type: str = "CustomerPayBillOnline",
        environment: str = "sandbox",
    ) -> None:
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._shortcode = shortcode
        self._passkey = passkey
        self._callback_base_url = callback_base_url.rstrip("/")
        self._transaction_type = transaction_type
        self._base = _PRODUCTION_BASE if environment.lower() == "production" else _SANDBOX_BASE

    @classmethod
    def from_settings(cls) -> MpesaProvider:
        """Build a provider from the global ``settings`` singleton."""
        return cls(
            consumer_key=settings.mpesa_consumer_key or "",
            consumer_secret=settings.mpesa_consumer_secret or "",
            shortcode=settings.mpesa_shortcode,
            passkey=settings.mpesa_passkey,
            callback_base_url=settings.mpesa_callback_base_url,
            transaction_type=settings.mpesa_transaction_type,
            environment=settings.mpesa_environment,
        )

    # ---- OAuth -----------------------------------------------------------
    async def _get_access_token(self, client: httpx.AsyncClient) -> str:
        """Fetch a short-lived OAuth bearer token via HTTP Basic auth."""
        resp = await client.get(
            f"{self._base}/oauth/v1/generate",
            params={"grant_type": "client_credentials"},
            auth=(self._consumer_key, self._consumer_secret),
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        return str(token)

    # ---- STK push --------------------------------------------------------
    async def stk_push(self, req: STKPushRequest) -> STKPushResult:
        timestamp = _timestamp()
        password = _password(self._shortcode, self._passkey, timestamp)
        payload = {
            "BusinessShortCode": self._shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": self._transaction_type,
            "Amount": int(req.amount),
            "PartyA": req.phone,
            "PartyB": self._shortcode,
            "PhoneNumber": req.phone,
            "CallBackURL": f"{self._callback_base_url}/api/v1/billing/mpesa/callback",
            "AccountReference": req.account_reference[:12],
            "TransactionDesc": req.description[:13] or "AngaWatch",
        }
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                token = await self._get_access_token(client)
                resp = await client.post(
                    f"{self._base}/mpesa/stkpush/v1/processrequest",
                    json=payload,
                    headers={"Authorization": f"Bearer {token}"},
                )
                data = resp.json()
        except (httpx.HTTPError, KeyError, ValueError) as exc:  # network / parse failure
            log.warning("mpesa.stk_push.error", error=str(exc), phone=req.phone)
            return STKPushResult(ok=False, error=str(exc))

        # Daraja returns ResponseCode "0" on a successfully *initiated* request.
        response_code = str(data.get("ResponseCode", ""))
        ok = response_code == "0"
        if not ok:
            log.warning("mpesa.stk_push.rejected", response=data)
        return STKPushResult(
            ok=ok,
            merchant_request_id=data.get("MerchantRequestID"),
            checkout_request_id=data.get("CheckoutRequestID"),
            customer_message=data.get("CustomerMessage"),
            error=None if ok else data.get("errorMessage") or data.get("ResponseDescription"),
            raw=data,
        )

    # ---- Callback parsing ------------------------------------------------
    def parse_callback(self, payload: dict) -> CallbackResult:
        """Normalize the ``Body.stkCallback`` envelope Daraja POSTs back."""
        cb = payload.get("Body", {}).get("stkCallback", payload.get("stkCallback", payload))
        result_code = cb.get("ResultCode")
        try:
            result_code_int = int(result_code) if result_code is not None else None
        except (TypeError, ValueError):
            result_code_int = None
        success = result_code_int == 0

        items = (cb.get("CallbackMetadata") or {}).get("Item", []) or []
        meta = {item.get("Name"): item.get("Value") for item in items if "Name" in item}

        return CallbackResult(
            success=success,
            checkout_request_id=cb.get("CheckoutRequestID"),
            merchant_request_id=cb.get("MerchantRequestID"),
            result_code=result_code_int,
            result_desc=cb.get("ResultDesc"),
            mpesa_receipt=meta.get("MpesaReceiptNumber"),
            amount=_as_float(meta.get("Amount")),
            phone=str(meta["PhoneNumber"]) if meta.get("PhoneNumber") is not None else None,
            raw=payload,
        )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
