"""Payment provider interface + feature-gating definitions.

The M-Pesa Daraja sandbox implementation lives in ``app.billing.mpesa``; the
subscription state machine + gating live in ``app.billing.service``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.db.models.common import PlanType

# ---- Feature gating -------------------------------------------------------
# Free tier sees live readings + instant threshold alerts (also computed on the
# firmware). Premium unlocks the predictive models, history and automation.
PREMIUM_FEATURES: frozenset[str] = frozenset(
    {
        "predictive_alerts",  # late blight + Tuta forecasting
        "dashboard_history",  # historical charts beyond 24h
        "automation",  # closed-loop control rules
        "weather_fusion",
        "agronomist_review",
        "export_reports",  # traceability / GlobalGAP
    }
)

PLAN_FEATURES: dict[PlanType, frozenset[str]] = {
    PlanType.SUBSCRIPTION: PREMIUM_FEATURES,
    PlanType.RENT_TO_OWN: PREMIUM_FEATURES,
    PlanType.DAAS: frozenset({"dashboard_history", "export_reports"}),
}


@dataclass(slots=True)
class STKPushRequest:
    phone: str  # 2547XXXXXXXX
    amount: int  # whole KES
    account_reference: str
    description: str = "AngaWatch subscription"


@dataclass(slots=True)
class STKPushResult:
    ok: bool
    merchant_request_id: str | None = None
    checkout_request_id: str | None = None
    customer_message: str | None = None
    error: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class CallbackResult:
    """Normalized M-Pesa STK callback."""

    success: bool
    checkout_request_id: str | None
    merchant_request_id: str | None
    result_code: int | None
    result_desc: str | None
    mpesa_receipt: str | None = None
    amount: float | None = None
    phone: str | None = None
    raw: dict = field(default_factory=dict)


class PaymentProvider(ABC):
    name: str = "base"

    @abstractmethod
    async def stk_push(self, req: STKPushRequest) -> STKPushResult:
        raise NotImplementedError

    @abstractmethod
    def parse_callback(self, payload: dict) -> CallbackResult:
        raise NotImplementedError
