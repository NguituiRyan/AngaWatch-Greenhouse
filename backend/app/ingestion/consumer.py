"""MQTT telemetry consumer (paho-mqtt v2).

Subscribes to ``settings.mqtt_telemetry_topic`` (default ``farm/+/+/telemetry``),
parses the topic ``farm/{org_id}/{device_uid}/telemetry``, validates the payload
against :class:`TelemetryIn`, and persists it via :func:`persist_reading` using a
fresh sync session per message.

Run it as a standalone worker::

    python -m app.ingestion.consumer

The loop is resilient: paho's automatic reconnect (``reconnect_delay_set``) keeps
the client alive across broker restarts, and per-message handlers never raise out
of ``on_message`` so one bad payload cannot kill the consumer.
"""

from __future__ import annotations

import contextlib
import json
import signal
import uuid
from typing import TYPE_CHECKING

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion
from pydantic import ValidationError

from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_sync_session
from app.ingestion.writer import persist_reading
from app.schemas.telemetry import TelemetryIn

if TYPE_CHECKING:
    from types import FrameType

logger = get_logger(__name__)

_TOPIC_PREFIX = "farm"
_TOPIC_SUFFIX = "telemetry"


def parse_topic(topic: str) -> tuple[uuid.UUID, str] | None:
    """Parse ``farm/{org_id}/{device_uid}/telemetry`` → ``(org_id, device_uid)``.

    Returns ``None`` (and the caller drops the message) when the topic does not
    match the expected shape or ``org_id`` is not a UUID.
    """
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != _TOPIC_PREFIX or parts[3] != _TOPIC_SUFFIX:
        return None
    org_id_raw, device_uid = parts[1], parts[2]
    if not device_uid:
        return None
    try:
        org_id = uuid.UUID(org_id_raw)
    except (ValueError, AttributeError):
        return None
    return org_id, device_uid


def _on_connect(
    client: mqtt.Client,
    userdata: object,
    flags: mqtt.ConnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    """Subscribe on (re)connect so the subscription survives reconnects."""
    if reason_code.is_failure:
        logger.error("mqtt.connect_failed", reason=str(reason_code))
        return
    topic = settings.mqtt_telemetry_topic
    client.subscribe(topic)
    logger.info("mqtt.connected", host=settings.mqtt_host, port=settings.mqtt_port, topic=topic)


def _on_disconnect(
    client: mqtt.Client,
    userdata: object,
    flags: mqtt.DisconnectFlags,
    reason_code: mqtt.ReasonCode,
    properties: mqtt.Properties | None,
) -> None:
    """Log disconnects; paho's loop handles the reconnect/backoff itself."""
    if reason_code is not None and reason_code.is_failure:
        logger.warning("mqtt.disconnected", reason=str(reason_code))
    else:
        logger.info("mqtt.disconnected")


def _on_message(client: mqtt.Client, userdata: object, msg: mqtt.MQTTMessage) -> None:
    """Validate one telemetry message and persist it. Never raises."""
    parsed = parse_topic(msg.topic)
    if parsed is None:
        logger.warning("mqtt.bad_topic", topic=msg.topic)
        return
    org_id, device_uid = parsed

    try:
        payload = json.loads(msg.payload)
    except (ValueError, TypeError) as exc:
        logger.warning("mqtt.bad_json", topic=msg.topic, error=str(exc))
        return

    # The topic's device_uid is authoritative; backfill it if the payload omits
    # device_id so a topic-only firmware still validates.
    if isinstance(payload, dict):
        payload.setdefault("device_id", device_uid)

    try:
        telem = TelemetryIn.model_validate(payload)
    except ValidationError as exc:
        logger.warning(
            "mqtt.invalid_payload",
            topic=msg.topic,
            device_uid=device_uid,
            errors=exc.error_count(),
        )
        return

    session = get_sync_session()
    try:
        persist_reading(session, org_id=org_id, telem=telem)
    except Exception:  # pragma: no cover - defensive; keep the loop alive
        logger.exception("mqtt.persist_error", topic=msg.topic, device_uid=device_uid)
        session.rollback()
    finally:
        session.close()


def build_client() -> mqtt.Client:
    """Construct a configured paho-mqtt v2 client (not yet connected)."""
    client = mqtt.Client(
        callback_api_version=CallbackAPIVersion.VERSION2,
        client_id=settings.mqtt_client_id,
    )
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
    client.on_connect = _on_connect
    client.on_disconnect = _on_disconnect
    client.on_message = _on_message
    # Exponential backoff between 1s and 120s for graceful reconnects.
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    return client


def main() -> None:
    """Connect, subscribe, and block forever consuming telemetry."""
    configure_logging()
    client = build_client()

    def _stop(signum: int, frame: FrameType | None) -> None:
        logger.info("mqtt.stopping", signal=signum)
        client.disconnect()

    for sig in (signal.SIGINT, signal.SIGTERM):
        # Signal handlers can only be set on the main thread; ignore otherwise.
        with contextlib.suppress(ValueError, OSError):
            signal.signal(sig, _stop)

    logger.info("mqtt.starting", host=settings.mqtt_host, port=settings.mqtt_port)
    client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=60)
    # loop_forever reconnects automatically on connection loss.
    client.loop_forever(retry_first_connection=True)


if __name__ == "__main__":  # pragma: no cover
    main()
