#!/usr/bin/env python3
"""ESP32 node EMULATOR — a no-hardware stand-in for an AngaWatch greenhouse node.

It behaves exactly like the WiFi+MQTT firmware over the wire, so you can exercise
the full closed loop (telemetry up + commands down + state ack) against a running
broker without a physical board:

  * publishes telemetry JSON to   farm/{org}/{uid}/telemetry   every interval
  * subscribes to commands on      farm/{org}/{uid}/command
  * on a command: flips a virtual relay, prints it, and publishes an ack to
                                   farm/{org}/{uid}/state   ({command_id, actuator_uid, state, ok})

Usage (point it at your broker; org id is the seeded demo org)::

    python scripts/esp_emulator.py --org-id <ORG_ID> --uid GH1-NODE-01 \
        --host localhost --port 1883 --scenario normal --interval 5

Pure stdlib + paho-mqtt; does NOT import the backend, so it mirrors a real device.
"""

from __future__ import annotations

import argparse
import json
import math
import signal
import time
from datetime import UTC, datetime

import paho.mqtt.client as mqtt
from paho.mqtt.enums import CallbackAPIVersion

# Command verb -> resulting relay/actuator state (mirrors the backend).
_VERB_STATE = {"open": "open", "close": "closed", "on": "on", "off": "off"}


class NodeEmulator:
    def __init__(self, args: argparse.Namespace) -> None:
        self.org_id = args.org_id
        self.uid = args.uid
        self.actuator_uid = args.actuator_uid
        self.scenario = args.scenario
        self.interval = args.interval
        self.host = args.host
        self.port = args.port
        self.relay_state = "closed"  # virtual vent relay
        self._tick = 0
        self.telemetry_topic = f"farm/{self.org_id}/{self.uid}/telemetry"
        self.command_topic = f"farm/{self.org_id}/{self.uid}/command"
        self.state_topic = f"farm/{self.org_id}/{self.uid}/state"

        self.client = mqtt.Client(
            callback_api_version=CallbackAPIVersion.VERSION2,
            client_id=f"esp-emulator-{self.uid}",
        )
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message
        self.client.reconnect_delay_set(min_delay=1, max_delay=30)

    # ---- sensor synthesis -------------------------------------------------
    def _sample(self) -> dict:
        """Produce one contract-shaped telemetry sample for the scenario."""
        # Gentle diurnal wiggle so charts look alive.
        wiggle = math.sin(self._tick / 6.0)
        if self.scenario == "blight":
            air_temp, rh, leaf = 18.0 + wiggle, 95.0, 100.0
        elif self.scenario == "heat":
            air_temp, rh, leaf = 37.0 + wiggle, 45.0, 0.0
        else:  # normal
            air_temp, rh, leaf = 24.0 + 2 * wiggle, 64.0 + 3 * wiggle, 8.0
        return {
            "device_id": self.uid,
            "ts": int(time.time()),
            "air_temp_c": round(air_temp, 2),
            "rh_pct": round(rh, 2),
            "leaf_wetness": leaf,
            "ppfd": 600.0,
            "co2_ppm": 450.0,
            "soil_moisture_pct": round(42.0 + 3 * wiggle, 2),
            "soil_temp_c": 22.0,
            "npk_n_ppm": 165,
            "npk_p_ppm": 78,
            "npk_k_ppm": 215,
            "water_flow_l_total": 0.0,
            "water_flow_l_per_min": 0.0,
            "pheromone_count": 3,
            "battery_v": 3.9,
            "rssi": -67,
        }

    # ---- MQTT callbacks ---------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            print(f"[esp] connect failed: {reason_code}")
            return
        client.subscribe(self.command_topic, qos=1)
        print(f"[esp] connected to {self.host}:{self.port}")
        print(f"[esp]   telemetry -> {self.telemetry_topic}")
        print(f"[esp]   commands  <- {self.command_topic}")

    def _on_message(self, client, userdata, msg: mqtt.MQTTMessage) -> None:
        try:
            cmd = json.loads(msg.payload)
        except (ValueError, TypeError):
            print(f"[esp] bad command payload on {msg.topic}")
            return
        verb = str(cmd.get("command", "")).strip().lower()
        new_state = _VERB_STATE.get(verb)
        actuator_uid = cmd.get("actuator_uid") or self.actuator_uid
        command_id = cmd.get("command_id")
        if new_state is None:
            print(f"[esp] !! unknown command verb: {verb!r}")
            ack = {
                "command_id": command_id,
                "actuator_uid": actuator_uid,
                "state": self.relay_state,
                "ok": False,
                "error": f"unknown verb {verb}",
            }
        else:
            self.relay_state = new_state
            print(
                f"[esp] >> RELAY '{verb}' -> vent is now {self.relay_state.upper()} "
                f"(cmd {command_id})"
            )
            ack = {
                "command_id": command_id,
                "actuator_uid": actuator_uid,
                "state": self.relay_state,
                "ok": True,
            }
        ack["ts"] = datetime.now(UTC).isoformat()
        client.publish(self.state_topic, json.dumps(ack), qos=1)
        print(f"[esp]   ack -> {self.state_topic} {ack['state']} ok={ack['ok']}")

    # ---- run loop ---------------------------------------------------------
    def run(self) -> None:
        running = True

        def _stop(_sig, _frm):
            nonlocal running
            running = False

        for sig in (signal.SIGINT, signal.SIGTERM):
            with __import__("contextlib").suppress(ValueError, OSError):
                signal.signal(sig, _stop)

        self.client.connect_async(self.host, self.port, keepalive=60)
        self.client.loop_start()
        try:
            while running:
                sample = self._sample()
                self.client.publish(self.telemetry_topic, json.dumps(sample), qos=1)
                print(
                    f"[esp] telemetry t={sample['air_temp_c']}C rh={sample['rh_pct']}% "
                    f"vent={self.relay_state}"
                )
                self._tick += 1
                time.sleep(self.interval)
        finally:
            self.client.loop_stop()
            self.client.disconnect()
            print("[esp] stopped")


def main() -> None:
    p = argparse.ArgumentParser(description="AngaWatch ESP32 node emulator (MQTT).")
    p.add_argument(
        "--org-id", required=True, help="Organization UUID (seeded demo org)."
    )
    p.add_argument(
        "--uid", default="GH1-NODE-01", help="Device uid (matches a seeded device)."
    )
    p.add_argument("--actuator-uid", default="GH1-VENT-01", help="Vent actuator uid.")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument(
        "--interval", type=float, default=5.0, help="Telemetry interval (s)."
    )
    p.add_argument("--scenario", default="normal", choices=["normal", "blight", "heat"])
    NodeEmulator(p.parse_args()).run()


if __name__ == "__main__":
    main()
