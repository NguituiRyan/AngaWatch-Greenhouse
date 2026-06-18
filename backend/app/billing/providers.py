"""Payment-provider selection + the offline mock provider.

The factory :func:`get_payment_provider` returns the real Daraja
:class:`~app.billing.mpesa.MpesaProvider` only when both M-Pesa consumer
credentials are configured; otherwise it returns :class:`MockPaymentProvider`
so the whole stack runs with zero external accounts (mock-first rule).
"""

from __future__ import annotations

import uuid

from app.billing.base import (
    CallbackResult,
    PaymentProvider,
    STKPushRequest,
    STKPushResult,
)
from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class MockPaymentProvider(PaymentProvider):
    """Deterministic, network-free stand-in for the Daraja API.

    ``stk_push`` synthesises merchant/checkout ids; ``parse_callback`` echoes a
    success result (or whatever ``ResultCode`` the payload carries) so the full
    initiate -> callback -> activate flow can run in tests and demos offline.
    """

    name = "mock"

    async def stk_push(self, req: STKPushRequest) -> STKPushResult:
        merchant_id = f"mock-merchant-{uuid.uuid4().hex[:12]}"
        checkout_id = f"mock-checkout-{uuid.uuid4().hex[:12]}"
        log.info(
            "mock.stk_push",
            phone=req.phone,
            amount=req.amount,
            checkout_request_id=checkout_id,
        )
        return STKPushResult(
            ok=True,
            merchant_request_id=merchant_id,
            checkout_request_id=checkout_id,
            customer_message="Mock STK push accepted; awaiting callback.",
            raw={
                "MerchantRequestID": merchant_id,
                "CheckoutRequestID": checkout_id,
                "ResponseCode": "0",
                "ResponseDescription": "Success. Request accepted for processing",
                "CustomerMessage": "Mock STK push accepted; awaiting callback.",
            },
        )

    def parse_callback(self, payload: dict) -> CallbackResult:
        """Echo a normalized callback.

        Accepts either a raw Daraja-style envelope or a flat dict. Defaults to a
        successful result (``ResultCode`` 0) unless the payload says otherwise.
        """
        cb = payload.get("Body", {}).get("stkCallback", payload)
        result_code = cb.get("ResultCode", 0)
        try:
            result_code_int = int(result_code)
        except (TypeError, ValueError):
            result_code_int = 0
        success = result_code_int == 0

        items = (cb.get("CallbackMetadata") or {}).get("Item", []) or []
        meta = {item.get("Name"): item.get("Value") for item in items if "Name" in item}

        return CallbackResult(
            success=success,
            checkout_request_id=cb.get("CheckoutRequestID"),
            merchant_request_id=cb.get("MerchantRequestID"),
            result_code=result_code_int,
            result_desc=cb.get("ResultDesc", "The service request is processed successfully."),
            mpesa_receipt=meta.get("MpesaReceiptNumber") or cb.get("MpesaReceiptNumber"),
            amount=_as_float(meta.get("Amount") if meta else cb.get("Amount")),
            phone=(
                str(meta.get("PhoneNumber") or cb.get("PhoneNumber"))
                if (meta.get("PhoneNumber") or cb.get("PhoneNumber")) is not None
                else None
            ),
            raw=payload,
        )


def _as_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def get_payment_provider() -> PaymentProvider:
    """Return the M-Pesa provider when credentials are set, else the mock."""
    if settings.mpesa_consumer_key and settings.mpesa_consumer_secret:
        from app.billing.mpesa import MpesaProvider

        log.info("billing.provider.selected", provider="mpesa")
        return MpesaProvider.from_settings()

    log.info("billing.provider.selected", provider="mock")
    return MockPaymentProvider()
