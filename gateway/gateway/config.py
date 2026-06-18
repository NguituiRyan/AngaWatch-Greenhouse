"""12-factor configuration for the edge gateway, sourced from environment vars.

The gateway is a standalone process with no dependency on the backend's
``pydantic-settings`` stack, so configuration is a small frozen dataclass built
from ``os.environ``. Every tunable has a sensible default that lets the gateway
run on a developer laptop against a single local broker with zero setup.

Environment variables
---------------------
Local (on-farm) broker — the source of truth the nodes publish to:
    ``GATEWAY_LOCAL_HOST``      (default ``localhost``)
    ``GATEWAY_LOCAL_PORT``      (default ``1883``)
    ``GATEWAY_LOCAL_USERNAME``  (optional)
    ``GATEWAY_LOCAL_PASSWORD``  (optional)

Cloud broker — the upstream sink we forward to when reachable:
    ``GATEWAY_CLOUD_HOST``      (default ``localhost``)
    ``GATEWAY_CLOUD_PORT``      (default ``1883``)
    ``GATEWAY_CLOUD_USERNAME``  (optional)
    ``GATEWAY_CLOUD_PASSWORD``  (optional)
    ``GATEWAY_CLOUD_TLS``       (default ``false``)

Bridge behaviour:
    ``GATEWAY_SUBSCRIBE_TOPIC``     (default ``farm/#``)
    ``GATEWAY_DB_PATH``            (default ``gateway_buffer.sqlite``)
    ``GATEWAY_BATCH_SIZE``         (default ``100``)
    ``GATEWAY_FLUSH_INTERVAL``     seconds between flush attempts (default ``5.0``)
    ``GATEWAY_BACKOFF_INITIAL``    initial retry backoff seconds (default ``2.0``)
    ``GATEWAY_BACKOFF_MAX``        backoff ceiling seconds (default ``300.0``)
    ``GATEWAY_PURGE_AFTER_DAYS``   drop sent rows older than N days (default ``7``)
    ``GATEWAY_QOS``               MQTT QoS for sub + forward publish (default ``1``)
    ``GATEWAY_CLIENT_ID_PREFIX``  (default ``angawatch-gateway``)
    ``LOG_LEVEL``                 (default ``INFO``)
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_str(key: str, default: str) -> str:
    val = os.environ.get(key)
    return val if val not in (None, "") else default


def _env_opt(key: str) -> str | None:
    val = os.environ.get(key)
    return val if val not in (None, "") else None


def _env_int(key: str, default: int) -> int:
    raw = os.environ.get(key)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(key: str, default: float) -> float:
    raw = os.environ.get(key)
    if raw in (None, ""):
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_bool(key: str, default: bool) -> bool:
    raw = os.environ.get(key)
    if raw in (None, ""):
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class BrokerConfig:
    """Connection parameters for one MQTT broker endpoint."""

    host: str
    port: int
    username: str | None = None
    password: str | None = None
    tls: bool = False

    @property
    def endpoint(self) -> str:
        return f"{self.host}:{self.port}"


@dataclass(frozen=True, slots=True)
class GatewayConfig:
    """Resolved, immutable gateway configuration."""

    local: BrokerConfig
    cloud: BrokerConfig
    subscribe_topic: str
    db_path: str
    batch_size: int
    flush_interval: float
    backoff_initial: float
    backoff_max: float
    purge_after_days: int
    qos: int
    client_id_prefix: str
    log_level: str

    @classmethod
    def from_env(cls) -> GatewayConfig:
        """Build a config snapshot from the current process environment."""
        local = BrokerConfig(
            host=_env_str("GATEWAY_LOCAL_HOST", "localhost"),
            port=_env_int("GATEWAY_LOCAL_PORT", 1883),
            username=_env_opt("GATEWAY_LOCAL_USERNAME"),
            password=_env_opt("GATEWAY_LOCAL_PASSWORD"),
            tls=_env_bool("GATEWAY_LOCAL_TLS", False),
        )
        cloud = BrokerConfig(
            host=_env_str("GATEWAY_CLOUD_HOST", "localhost"),
            port=_env_int("GATEWAY_CLOUD_PORT", 1883),
            username=_env_opt("GATEWAY_CLOUD_USERNAME"),
            password=_env_opt("GATEWAY_CLOUD_PASSWORD"),
            tls=_env_bool("GATEWAY_CLOUD_TLS", False),
        )
        return cls(
            local=local,
            cloud=cloud,
            subscribe_topic=_env_str("GATEWAY_SUBSCRIBE_TOPIC", "farm/#"),
            db_path=_env_str("GATEWAY_DB_PATH", "gateway_buffer.sqlite"),
            batch_size=max(1, _env_int("GATEWAY_BATCH_SIZE", 100)),
            flush_interval=max(0.1, _env_float("GATEWAY_FLUSH_INTERVAL", 5.0)),
            backoff_initial=max(0.1, _env_float("GATEWAY_BACKOFF_INITIAL", 2.0)),
            backoff_max=max(1.0, _env_float("GATEWAY_BACKOFF_MAX", 300.0)),
            purge_after_days=max(0, _env_int("GATEWAY_PURGE_AFTER_DAYS", 7)),
            qos=min(2, max(0, _env_int("GATEWAY_QOS", 1))),
            client_id_prefix=_env_str("GATEWAY_CLIENT_ID_PREFIX", "angawatch-gateway"),
            log_level=_env_str("LOG_LEVEL", "INFO"),
        )
