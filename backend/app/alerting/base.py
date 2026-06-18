"""Alerting interfaces: a channel adapter ABC + message/result dataclasses + registry.

Adapters (console, Africa's Talking SMS/USSD, WhatsApp Cloud API) implement
``AlertChannel``. The dispatcher (``app.alerting.dispatcher``) handles templating,
language, per-user preference, quiet hours, dedup and escalation — adapters only
move bytes.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

from app.db.models.common import AlertChannelType, Language


@dataclass(slots=True)
class OutgoingMessage:
    to: str  # phone number (E.164) or channel-specific recipient id
    body: str
    title: str | None = None
    language: Language = Language.EN
    template_name: str | None = None
    template_params: dict = field(default_factory=dict)
    meta: dict = field(default_factory=dict)


@dataclass(slots=True)
class DeliveryResult:
    ok: bool
    channel: AlertChannelType
    provider_message_id: str | None = None
    status: str = "unknown"
    error: str | None = None
    raw: dict = field(default_factory=dict)


class AlertChannel(ABC):
    """One delivery channel. Implementations must be safe to call from Celery tasks."""

    channel: ClassVar[AlertChannelType]

    @abstractmethod
    def send(self, message: OutgoingMessage) -> DeliveryResult:
        raise NotImplementedError

    def is_configured(self) -> bool:
        """Whether credentials are present; falls back to console when False."""
        return True


class ChannelRegistry:
    def __init__(self) -> None:
        self._channels: dict[AlertChannelType, AlertChannel] = {}

    def register(self, channel: AlertChannel) -> AlertChannel:
        self._channels[channel.channel] = channel
        return channel

    def get(self, channel: AlertChannelType) -> AlertChannel | None:
        return self._channels.get(channel)

    def all(self) -> dict[AlertChannelType, AlertChannel]:
        return dict(self._channels)


channel_registry = ChannelRegistry()
