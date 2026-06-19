#!/usr/bin/env python3
"""Verify the live MQTT closed loop against a running broker + ESP emulator.

Run from ``backend/`` with the venv so ``app.*`` imports resolve::

    backend/.venv/Scripts/python.exe ../scripts/verify_loop.py <ORG_ID>

Asserts, over a REAL broker:
  1. telemetry-up — a contract-valid TelemetryIn arrives on .../telemetry
  2. command-down — the REAL backend MqttRelayDriver publishes an 'open' command
  3. ack-up       — the device flips its relay and acks 'open' on .../state
"""

from __future__ import annotations

import json
import sys
import threading
import uuid

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

from app.control.drivers.mqtt_relay import MqttRelayDriver
from app.db.models.common import ActuatorType
from app.schemas.telemetry import TelemetryIn

ORG = sys.argv[1] if len(sys.argv) > 1 else str(uuid.uuid4())
UID = "GH1-NODE-01"
HOST, PORT = "localhost", 1883

got: dict[str, dict | None] = {"telemetry": None, "state": None}
ev_tel = threading.Event()
ev_state = threading.Event()


def on_connect(c, u, f, rc, p):
    c.subscribe(f"farm/{ORG}/{UID}/telemetry", qos=1)
    c.subscribe(f"farm/{ORG}/{UID}/state", qos=1)


def on_message(c, u, msg):
    if msg.topic.endswith("/telemetry") and got["telemetry"] is None:
        got["telemetry"] = json.loads(msg.payload)
        ev_tel.set()
    elif msg.topic.endswith("/state"):
        got["state"] = json.loads(msg.payload)
        ev_state.set()


def main() -> int:
    cli = mqtt.Client(CallbackAPIVersion.VERSION2, client_id="verify-loop")
    cli.on_connect = on_connect
    cli.on_message = on_message
    cli.connect(HOST, PORT, 60)
    cli.loop_start()
    try:
        # 1. telemetry up
        if not ev_tel.wait(20):
            print("[verify] FAIL: no telemetry received")
            return 1
        telem = TelemetryIn.model_validate({**got["telemetry"], "device_id": UID})
        print(
            f"[verify] 1/3 telemetry OK  air_temp={telem.air_temp_c}C rh={telem.rh_pct}%"
        )

        # 2. command down via the REAL backend driver
        cmd_id = str(uuid.uuid4())
        res = MqttRelayDriver().apply(
            actuator_type=ActuatorType.VENT,
            target_uid="GH1-VENT-01",
            command="open",
            org_id=ORG,
            node_uid=UID,
            command_id=cmd_id,
        )
        if not res.ok:
            print(f"[verify] FAIL: driver publish failed: {res.error}")
            return 1
        print(
            f"[verify] 2/3 command published  farm/{ORG}/{UID}/command  cmd={cmd_id[:8]}"
        )

        # 3. device ack up
        if not ev_state.wait(20):
            print("[verify] FAIL: no device ack received")
            return 1
        ack = got["state"]
        ok = ack.get("state") == "open" and ack.get("ok") is True
        if not ok or ack.get("command_id") != cmd_id:
            print(f"[verify] FAIL: bad ack: {ack}")
            return 1
        print(
            f"[verify] 3/3 device ACK OK  vent -> {ack['state']}  cmd={ack['command_id'][:8]}"
        )
        print(
            "[verify] PASS - full MQTT closed loop verified (telemetry up, command down, ack up)"
        )
        return 0
    finally:
        cli.loop_stop()
        cli.disconnect()


if __name__ == "__main__":
    raise SystemExit(main())
