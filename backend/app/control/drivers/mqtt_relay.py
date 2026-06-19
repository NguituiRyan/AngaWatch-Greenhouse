"""MQTT relay actuator driver — the hardware control path.

Publishes a command JSON to the relay-bearing node's command topic
``farm/{org_id}/{node_uid}/command`` (``settings.mqtt_command_topic_template``).
The ESP firmware subscribes to that topic, flips the relay, and publishes an ack
to ``farm/{org_id}/{node_uid}/state`` which the device-state consumer turns into
a confirmed ``ActuatorDevice.state`` + an ``ACKED`` command — closing the loop on
the dashboard.

It is fire-and-forget at the driver layer: a successful publish reports the
*implied* state with ``acked=False`` (the real ack arrives asynchronously over
MQTT). It tolerates broker absence — a connect/publish failure returns
``CommandResult(ok=False, ...)`` instead of raising, so the service layer can fall
back to the mock driver and the stack still runs offline.

Command payload (consumed by the firmware)::

    {"command_id", "actuator_uid", "actuator_type", "command", "params", "ts"}
"""

from __future__ import annotations

import contextlib
import json
from datetime import UTC, datetime

from app.control.base import ActuatorDriver, CommandResult
from app.core.config import settings
from app.core.logging import get_logger
from app.db.models.common import ActuatorType

logger = get_logger(__name__)

# State implied by each command verb (mirrors the mock driver).
_COMMAND_TO_STATE: dict[str, str] = {
    "open": "open",
    "close": "closed",
    "on": "on",
    "off": "off",
}


class MqttRelayDriver(ActuatorDriver):
    """Publishes a command JSON to a node's command topic via paho-mqtt."""

    name = "mqtt"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        connect_timeout_s: float = 1.0,
    ) -> None:
        self.host = host or settings.mqtt_host
        self.port = port or settings.mqtt_port
        self.connect_timeout_s = connect_timeout_s

    def _topic_for(self, *, org_id: str | None, node_uid: str, params: dict | None) -> str:
        # An explicit override always wins (used by tests / special routing).
        if params and isinstance(params.get("topic"), str):
            return params["topic"]
        return settings.mqtt_command_topic_template.format(
            org_id=org_id or "+", device_uid=node_uid
        )

    def apply(
        self,
        *,
        actuator_type: ActuatorType,
        target_uid: str,
        command: str,
        params: dict | None = None,
        org_id: str | None = None,
        node_uid: str | None = None,
        command_id: str | None = None,
    ) -> CommandResult:
        verb = command.strip().lower()
        new_state = _COMMAND_TO_STATE.get(verb)
        # Route to the relay-bearing node; fall back to the actuator's own uid.
        route_uid = node_uid or target_uid
        topic = self._topic_for(org_id=org_id, node_uid=route_uid, params=params)
        payload = json.dumps(
            {
                "command_id": command_id,
                "actuator_uid": target_uid,
                "actuator_type": str(actuator_type),
                "command": verb,
                "params": params or {},
                "ts": datetime.now(UTC).isoformat(),
            }
        )

        try:
            import paho.mqtt.client as mqtt  # local import: optional dependency
            from paho.mqtt.enums import CallbackAPIVersion
        except Exception as exc:  # pragma: no cover - paho is a declared dep
            logger.warning("mqtt_driver_paho_unavailable", error=str(exc))
            return CommandResult(ok=False, acked=False, error=f"paho unavailable: {exc}")

        client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"{settings.mqtt_client_id}-control",
        )
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password or "")

        try:
            client.connect(self.host, self.port, keepalive=max(1, int(self.connect_timeout_s)))
            info = client.publish(topic, payload, qos=1)
            with contextlib.suppress(Exception):  # paho version differences
                info.wait_for_publish(timeout=self.connect_timeout_s)
            client.disconnect()
        except Exception as exc:
            logger.warning(
                "mqtt_driver_publish_failed",
                host=self.host,
                port=self.port,
                topic=topic,
                error=str(exc),
            )
            return CommandResult(
                ok=False,
                acked=False,
                error=f"mqtt publish failed: {exc}",
                raw={"topic": topic, "payload": payload},
            )

        logger.info("mqtt_driver_published", topic=topic, command=verb, command_id=command_id)
        # Fire-and-forget: published, but the device ack arrives asynchronously
        # over the state topic. Report the optimistic implied state; the consumer
        # flips the command ACKED + confirms state when the ack lands.
        return CommandResult(
            ok=True,
            acked=False,
            new_state=new_state,
            raw={"topic": topic, "payload": payload, "driver": self.name},
        )
