"""MQTT publisher — a thin wrapper over paho-mqtt v2.

Publishes telemetry JSON to ``farm/{org_id}/{device_uid}/telemetry``. It is
written against the paho-mqtt **v2** callback API (``CallbackAPIVersion.VERSION2``)
which is what ships in paho-mqtt >= 2.0.

The publisher is deliberately forgiving: if the broker is unreachable it logs a
warning and keeps the loop alive (so a demo that has no broker still prints
what *would* be published). A :class:`NullPublisher` is provided for tests and
``--dry-run`` mode so nothing touches the network.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Protocol

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

logger = logging.getLogger("simulator.publisher")


def _json_default(obj: Any) -> Any:
    """JSON-encode datetimes as ISO-8601 (the contract accepts ISO ``ts``)."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def encode_payload(reading: dict[str, object]) -> str:
    """Serialize a telemetry dict to the JSON wire format."""
    return json.dumps(reading, default=_json_default, separators=(",", ":"))


class Publisher(Protocol):
    """Anything that can publish an encoded reading to a topic."""

    def publish(self, topic: str, reading: dict[str, object]) -> None: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...


class MqttPublisher:
    """Publishes telemetry over MQTT using a paho-mqtt v2 client."""

    def __init__(
        self,
        host: str,
        port: int,
        *,
        username: str | None = None,
        password: str | None = None,
        client_id: str = "angawatch-simulator",
        qos: int = 0,
    ) -> None:
        self.host = host
        self.port = port
        self.qos = qos
        self._connected = False
        self._client = mqtt.Client(
            CallbackAPIVersion.VERSION2,
            client_id=client_id,
            protocol=mqtt.MQTTv311,
        )
        if username:
            self._client.username_pw_set(username, password or None)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    # ---- paho v2 callbacks ----
    def _on_connect(self, client, userdata, flags, reason_code, properties=None) -> None:  # noqa: ANN001
        if reason_code == 0 or getattr(reason_code, "is_failure", False) is False:
            self._connected = True
            logger.info("MQTT connected to %s:%s", self.host, self.port)
        else:
            logger.warning("MQTT connect failed: %s", reason_code)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None) -> None:  # noqa: ANN001
        self._connected = False
        logger.info("MQTT disconnected (%s)", reason_code)

    def connect(self) -> None:
        """Connect and start the network loop in a background thread."""
        try:
            self._client.connect(self.host, self.port, keepalive=60)
            self._client.loop_start()
        except OSError as exc:
            logger.warning(
                "MQTT broker %s:%s unreachable (%s); continuing offline",
                self.host,
                self.port,
                exc,
            )

    def disconnect(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception as exc:  # pragma: no cover - best-effort teardown
            logger.debug("MQTT disconnect error: %s", exc)

    def publish(self, topic: str, reading: dict[str, object]) -> None:
        payload = encode_payload(reading)
        info = self._client.publish(topic, payload, qos=self.qos)
        # paho returns rc!=0 when not connected; surface it but don't crash.
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning("publish to %s returned rc=%s (broker down?)", topic, info.rc)


class NullPublisher:
    """A no-op publisher for tests / ``--dry-run`` (records nothing on the wire)."""

    def __init__(self) -> None:
        self.published: list[tuple[str, dict[str, object]]] = []

    def connect(self) -> None:  # noqa: D401 - trivial
        """No-op."""

    def disconnect(self) -> None:  # noqa: D401 - trivial
        """No-op."""

    def publish(self, topic: str, reading: dict[str, object]) -> None:
        self.published.append((topic, reading))
