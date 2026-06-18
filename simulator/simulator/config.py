"""Simulator configuration, read from the environment (12-factor).

All knobs map onto the ``SIM_*`` / ``MQTT_*`` variables documented in the repo
``.env.example``. Defaults are chosen so the simulator runs out-of-the-box
against a local Mosquitto broker and agrees with the demo constants baked into
the backend seed (org slug ``demo-coop``, device uid ``GH1-NODE-01``).
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

# The seven scenarios this simulator can drive. Kept here as the single source
# of truth so ``run.py``, the scenario registry, and the tests all agree.
SCENARIOS: tuple[str, ...] = (
    "normal",
    "blight_dusk",
    "heat_stress",
    "pest_surge",
    "nutrient_depletion",
    "leak",
    "offline",
)

# Demo defaults — must agree with backend ``app/seed/constants.py``.
DEFAULT_ORG_ID = "demo-coop"
DEFAULT_DEVICE_UID_PREFIX = "GH1-NODE-01"


def _get_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_str(name: str, default: str) -> str:
    raw = os.environ.get(name, "").strip()
    return raw or default


class SimulatorConfig(BaseModel):
    """Resolved simulator settings.

    Construct from the environment with :meth:`from_env`. ``org_id`` doubles as
    the MQTT topic tenant segment (``farm/{org_id}/{device_uid}/telemetry``).
    """

    mqtt_host: str = Field(default="localhost")
    mqtt_port: int = Field(default=1883, ge=1, le=65535)
    mqtt_username: str | None = None
    mqtt_password: str | None = None

    org_id: str = Field(default=DEFAULT_ORG_ID, min_length=1)
    node_count: int = Field(default=1, ge=1, le=1000)
    scenario: str = Field(default="normal")
    interval_seconds: float = Field(default=5.0, gt=0)
    time_accel: float = Field(default=1.0, gt=0)
    device_uid_prefix: str = Field(default=DEFAULT_DEVICE_UID_PREFIX, min_length=1)

    @classmethod
    def from_env(cls) -> SimulatorConfig:
        """Build a config from process environment variables."""
        scenario = _get_str("SIM_SCENARIO", "normal")
        if scenario not in SCENARIOS:
            scenario = "normal"
        return cls(
            mqtt_host=_get_str("MQTT_HOST", "localhost"),
            mqtt_port=_get_int("MQTT_PORT", 1883),
            mqtt_username=os.environ.get("MQTT_USERNAME") or None,
            mqtt_password=os.environ.get("MQTT_PASSWORD") or None,
            org_id=_get_str("SIM_ORG_ID", DEFAULT_ORG_ID),
            node_count=_get_int("SIM_NODE_COUNT", 1),
            scenario=scenario,
            interval_seconds=_get_float("SIM_INTERVAL_SECONDS", 5.0),
            time_accel=_get_float("SIM_TIME_ACCEL", 1.0),
            device_uid_prefix=_get_str("SIM_DEVICE_UID_PREFIX", DEFAULT_DEVICE_UID_PREFIX),
        )

    def device_uid(self, index: int) -> str:
        """Return the device_uid for node ``index`` (0-based).

        Node 0 uses the bare prefix so a single-node demo publishes as the
        canonical ``GH1-NODE-01``; additional nodes get a numeric suffix.
        """
        if index == 0:
            return self.device_uid_prefix
        return f"{self.device_uid_prefix}-{index + 1:02d}"

    def topic(self, device_uid: str) -> str:
        """The MQTT telemetry topic for a given device uid."""
        return f"farm/{self.org_id}/{device_uid}/telemetry"
