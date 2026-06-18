"""Billing DTOs: subscription view, subscribe request, payment view."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.common import (
    PaymentProviderType,
    PaymentStatus,
    PlanType,
    SubscriptionStatus,
)


class SubscriptionOut(BaseModel):
    """The org's current subscription."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_type: PlanType
    plan_name: str
    status: SubscriptionStatus
    price: float
    currency: str
    billing_interval: str
    features: dict
    trial_ends_at: datetime | None = None
    current_period_start: datetime | None = None
    current_period_end: datetime | None = None
    started_at: datetime | None = None


class SubscribeIn(BaseModel):
    """Subscribe request -> fires an STK push."""

    plan_type: PlanType = PlanType.SUBSCRIPTION
    phone: str = Field(..., min_length=9, max_length=20)
    amount: int = Field(..., gt=0)
    plan_name: str = "standard"


class STKResultOut(BaseModel):
    """Outcome of the STK push initiated by a subscribe call."""

    ok: bool
    subscription_id: uuid.UUID
    payment_id: uuid.UUID
    checkout_request_id: str | None = None
    merchant_request_id: str | None = None
    customer_message: str | None = None
    error: str | None = None


class PaymentOut(BaseModel):
    """A payment attempt + reconciliation state."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    subscription_id: uuid.UUID | None = None
    installment_id: uuid.UUID | None = None
    provider: PaymentProviderType
    amount: float
    currency: str
    status: PaymentStatus
    phone: str | None = None
    account_reference: str | None = None
    merchant_request_id: str | None = None
    checkout_request_id: str | None = None
    mpesa_receipt: str | None = None
    result_code: int | None = None
    result_desc: str | None = None
    initiated_at: datetime
    completed_at: datetime | None = None


class CallbackAck(BaseModel):
    """Daraja webhook acknowledgement body (Daraja expects ResultCode 0)."""

    ResultCode: int = 0
    ResultDesc: str = "Accepted"
