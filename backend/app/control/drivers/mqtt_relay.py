"""MQTT relay actuator driver.

Publishes a command JSON to a per-actuator control topic. A real relay/GPIO node
subscribes to that topic, flips the output, and (in a later wave) publishes an
ack back. Wave 0 is fire-and-forget: we publish optimistically and report the
state the command implies, tolerating broker absence so the stack still runs
offline (a publish failure is surfaced as a non-acked ``CommandResult`` rather
than an exception).

Control topic: ``farm/{org_id}/{target_uid}/control`` — but since the driver is
stateless about org scoping, the caller passes the fully-resolved ``target_uid``
and we publish to ``control/{target_uid}`` by default (configurable via
``params["topic"]``).
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
    """Publishes a command JSON to a control topic via paho-mqtt.

    Tolerates broker absence: if paho is unavailable or the connect/publish
    fails, returns ``CommandResult(ok=False, acked=False, error=...)`` instead
    of raising, so a caller can fall back to the mock driver.
    """

    name = "mqtt"

    def __init__(
        self,
        *,
        host: str | None = None,
        port: int | None = None,
        topic_prefix: str = "control",
        connect_timeout_s: float = 2.0,
    ) -> None:
        self.host = host or settings.mqtt_host
        self.port = port or settings.mqtt_port
        self.topic_prefix = topic_prefix
        self.connect_timeout_s = connect_timeout_s

    def _topic_for(self, target_uid: str, params: dict | None) -> str:
        if params and isinstance(params.get("topic"), str):
            return params["topic"]
        return f"{self.topic_prefix}/{target_uid}"

    def apply(
        self,
        *,
        actuator_type: ActuatorType,
        target_uid: str,
        command: str,
        params: dict | None = None,
    ) -> CommandResult:
        verb = command.strip().lower()
        new_state = _COMMAND_TO_STATE.get(verb)
        topic = self._topic_for(target_uid, params)
        payload = json.dumps(
            {
                "target_uid": target_uid,
                "actuator_type": str(actuator_type),
                "command": verb,
                "params": params or {},
                "ts": datetime.now(UTC).isoformat(),
            }
        )

        try:
            import paho.mqtt.client as mqtt  # local import: optional dependency
        except Exception as exc:  # pragma: no cover - paho is a declared dep
            logger.warning("mqtt_driver_paho_unavailable", error=str(exc))
            return CommandResult(ok=False, acked=False, error=f"paho unavailable: {exc}")

        client = mqtt.Client(client_id=f"{settings.mqtt_client_id}-control")
        if settings.mqtt_username:
            client.username_pw_set(settings.mqtt_username, settings.mqtt_password or "")

        try:
            client.connect(self.host, self.port, keepalive=int(self.connect_timeout_s) or 1)
            info = client.publish(topic, payload, qos=1)
            # Best-effort flush; do not block the request path for long.
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

        logger.info(
            "mqtt_driver_published",
            host=self.host,
            port=self.port,
            topic=topic,
            command=verb,
        )
        # Fire-and-forget: we published but have no device ack yet. Report the
        # optimistic implied state; acked stays False until a real ack channel
        # lands in a later wave.
        return CommandResult(
            ok=True,
            acked=False,
            new_state=new_state,
            raw={"topic": topic, "payload": payload, "driver": self.name},
        )
