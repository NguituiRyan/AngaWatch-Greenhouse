"""The store-and-forward MQTT bridge.

:class:`Forwarder` ties everything together:

1. It subscribes to the **local** broker on the configured topic (``farm/#``).
   Every inbound message is written to the durable :class:`SqliteBuffer` in the
   network callback — and nowhere else — so a crash between receive and forward
   loses nothing.
2. A background flush loop wakes every ``flush_interval`` seconds, pulls a batch
   of unsent rows, and republishes them to the **cloud** broker.
3. If the cloud broker is unreachable (the common case on rural links) the loop
   simply leaves the rows buffered and retries with exponential backoff. The
   moment connectivity returns, the whole backlog drains in batches.

paho-mqtt's automatic reconnect handles transient drops on both ends; the SQLite
buffer handles longer outages. Together they give at-least-once delivery to the
cloud with zero data loss across power cuts and offline periods.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from typing import TYPE_CHECKING

import paho.mqtt.client as mqtt

if TYPE_CHECKING:
    from gateway.config import BrokerConfig, GatewayConfig
    from gateway.store import SqliteBuffer

logger = logging.getLogger("gateway.forwarder")


def _new_client(client_id: str, broker: BrokerConfig) -> mqtt.Client:
    """Construct a paho client configured for ``broker`` (auth + optional TLS)."""
    client = mqtt.Client(
        callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        client_id=client_id,
        clean_session=False,  # durable session so QoS>=1 survives brief drops
    )
    if broker.username:
        client.username_pw_set(broker.username, broker.password)
    if broker.tls:
        client.tls_set()
    # paho's built-in reconnect with bounded backoff covers transient blips.
    client.reconnect_delay_set(min_delay=1, max_delay=120)
    return client


class Forwarder:
    """Bridge local-broker telemetry to the cloud broker via a durable buffer."""

    def __init__(self, config: GatewayConfig, buffer: SqliteBuffer) -> None:
        self._cfg = config
        self._buffer = buffer
        self._stop = threading.Event()
        self._cloud_connected = threading.Event()
        self._wakeup = threading.Event()

        suffix = f"{os.getpid()}"
        self._local = _new_client(f"{config.client_id_prefix}-local-{suffix}", config.local)
        self._cloud = _new_client(f"{config.client_id_prefix}-cloud-{suffix}", config.cloud)

        self._local.on_connect = self._on_local_connect
        self._local.on_message = self._on_message
        self._cloud.on_connect = self._on_cloud_connect
        self._cloud.on_disconnect = self._on_cloud_disconnect

        self._flush_thread: threading.Thread | None = None
        self._last_purge = 0.0

    # -- local broker callbacks -------------------------------------------

    def _on_local_connect(
        self,
        client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        *_: object,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.error("local connect failed: %s", reason_code)
            return
        client.subscribe(self._cfg.subscribe_topic, qos=self._cfg.qos)
        logger.info(
            "connected to LOCAL broker %s; subscribed to %s",
            self._cfg.local.endpoint,
            self._cfg.subscribe_topic,
        )

    def _on_message(self, _client: mqtt.Client, _userdata: object, msg: mqtt.MQTTMessage) -> None:
        """Durably buffer every inbound message — the only place we receive data."""
        try:
            self._buffer.enqueue(msg.topic, msg.payload, ts=time.time())
        except Exception:  # noqa: BLE001 - never let a bad message kill the net thread
            logger.exception("failed to buffer message on topic %s", msg.topic)
            return
        # Nudge the flush loop so a fresh message forwards promptly when online.
        self._wakeup.set()

    # -- cloud broker callbacks -------------------------------------------

    def _on_cloud_connect(
        self,
        _client: mqtt.Client,
        _userdata: object,
        _flags: object,
        reason_code: object,
        *_: object,
    ) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.warning("cloud connect reported failure: %s", reason_code)
            self._cloud_connected.clear()
            return
        self._cloud_connected.set()
        self._wakeup.set()  # drain any backlog immediately on (re)connect
        logger.info("connected to CLOUD broker %s", self._cfg.cloud.endpoint)

    def _on_cloud_disconnect(
        self, _client: mqtt.Client, _userdata: object, *args: object
    ) -> None:
        self._cloud_connected.clear()
        logger.warning(
            "disconnected from CLOUD broker %s; buffering locally",
            self._cfg.cloud.endpoint,
        )

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        """Connect both brokers and start the flush loop (non-blocking)."""
        logger.info(
            "starting gateway: local=%s cloud=%s db=%s batch=%d flush=%.1fs",
            self._cfg.local.endpoint,
            self._cfg.cloud.endpoint,
            self._cfg.db_path,
            self._cfg.batch_size,
            self._cfg.flush_interval,
        )
        # Connect cloud lazily/async so a cloud outage never blocks local ingest.
        self._cloud.connect_async(self._cfg.cloud.host, self._cfg.cloud.port, keepalive=60)
        self._cloud.loop_start()

        self._local.connect_async(self._cfg.local.host, self._cfg.local.port, keepalive=60)
        self._local.loop_start()

        self._flush_thread = threading.Thread(target=self._flush_loop, name="flush", daemon=True)
        self._flush_thread.start()

    def stop(self) -> None:
        """Signal shutdown and tear down broker connections."""
        logger.info("stopping gateway")
        self._stop.set()
        self._wakeup.set()
        if self._flush_thread is not None:
            self._flush_thread.join(timeout=self._cfg.flush_interval + 5.0)
        for client in (self._local, self._cloud):
            try:
                client.loop_stop()
                client.disconnect()
            except Exception:  # noqa: BLE001 - best effort teardown
                logger.debug("error during client teardown", exc_info=True)

    def run_forever(self) -> None:
        """Blocking convenience entrypoint: start, then sleep until stopped."""
        self.start()
        try:
            while not self._stop.is_set():
                self._stop.wait(timeout=1.0)
        except KeyboardInterrupt:  # pragma: no cover - signal path
            logger.info("keyboard interrupt received")
        finally:
            self.stop()

    # -- flush loop --------------------------------------------------------

    def _flush_loop(self) -> None:
        """Repeatedly drain the buffer to the cloud, backing off on failure."""
        backoff = self._cfg.backoff_initial
        while not self._stop.is_set():
            wait = self._cfg.flush_interval
            if not self._cloud_connected.is_set():
                # Offline: don't hammer; wait the current backoff then retry.
                wait = min(backoff, self._cfg.backoff_max)
            else:
                forwarded, had_error = self._flush_once()
                if had_error:
                    backoff = min(backoff * 2.0, self._cfg.backoff_max)
                    wait = backoff
                else:
                    backoff = self._cfg.backoff_initial
                    # If we just emptied a full batch there may be more; keep
                    # draining quickly instead of sleeping the full interval.
                    if forwarded >= self._cfg.batch_size:
                        wait = 0.0
            self._maybe_purge()
            if wait > 0.0:
                self._wakeup.wait(timeout=wait)
            self._wakeup.clear()

    def _flush_once(self) -> tuple[int, bool]:
        """Forward one batch. Returns ``(num_forwarded, had_error)``."""
        batch = self._buffer.pending(limit=self._cfg.batch_size)
        if not batch:
            return 0, False

        sent_ids: list[int] = []
        for message in batch:
            if self._stop.is_set() or not self._cloud_connected.is_set():
                break
            info = self._cloud.publish(message.topic, payload=message.payload, qos=self._cfg.qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning("cloud publish failed rc=%s for id=%s", info.rc, message.id)
                break
            # For QoS>=1 wait for broker handshake so "sent" truly means acked.
            if self._cfg.qos > 0:
                try:
                    info.wait_for_publish(timeout=10.0)
                except (ValueError, RuntimeError):
                    logger.warning("publish wait failed for id=%s", message.id)
                    break
                if not info.is_published():
                    logger.warning("publish not confirmed for id=%s", message.id)
                    break
            sent_ids.append(message.id)

        if sent_ids:
            self._buffer.mark_sent(sent_ids)
            logger.info("forwarded %d message(s) to cloud", len(sent_ids))
        had_error = len(sent_ids) < len(batch)
        if had_error:
            # Bump attempt counters on the ones we couldn't push this round.
            failed = [m.id for m in batch if m.id not in set(sent_ids)]
            self._buffer.mark_attempted(failed)
        return len(sent_ids), had_error

    def _maybe_purge(self) -> None:
        """Periodically reclaim disk from old, already-forwarded rows."""
        now = time.time()
        if now - self._last_purge < 3600.0:  # at most hourly
            return
        self._last_purge = now
        try:
            self._buffer.purge(older_than_days=self._cfg.purge_after_days)
        except Exception:  # noqa: BLE001 - purge is best-effort housekeeping
            logger.debug("purge failed", exc_info=True)
