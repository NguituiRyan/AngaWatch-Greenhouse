#!/usr/bin/env python3
"""Local dev MQTT broker (amqtt) — a Docker/Mosquitto-free broker for testing.

    python scripts/dev_broker.py     # listens on 0.0.0.0:1883, anonymous

Handy on machines without Docker: point the backend (MQTT_HOST=localhost), the
ingestion consumer, the simulator and the ESP emulator at it to run the whole
MQTT loop locally. NOT for production (anonymous, no TLS).
"""

from __future__ import annotations

import asyncio
import logging

from amqtt.broker import Broker

# amqtt 0.11 typed config: a single tcp listener is enough — the default plugin
# set already includes AnonymousAuthPlugin(allow_anonymous=True).
CONFIG = {
    "listeners": {"default": {"type": "tcp", "bind": "0.0.0.0:1883"}},
}


async def _run() -> None:
    broker = Broker(CONFIG)
    await broker.start()
    print("[broker] amqtt listening on 0.0.0.0:1883 (anonymous)")
    while True:
        await asyncio.sleep(3600)


def main() -> None:
    logging.basicConfig(level=logging.WARNING)
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
