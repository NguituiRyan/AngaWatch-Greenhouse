"""Gateway entrypoint: ``python -m gateway.run``.

Wires up logging, loads :class:`GatewayConfig` from the environment, opens the
durable :class:`SqliteBuffer`, and runs the :class:`Forwarder` until interrupted
(Ctrl-C or SIGTERM, e.g. ``docker stop``).
"""

from __future__ import annotations

import logging
import signal
import sys
from typing import TYPE_CHECKING

from gateway.config import GatewayConfig
from gateway.forwarder import Forwarder
from gateway.store import SqliteBuffer

if TYPE_CHECKING:
    from types import FrameType

logger = logging.getLogger("gateway.run")


def _configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )


def main() -> int:
    """Run the gateway forever. Returns a process exit code."""
    config = GatewayConfig.from_env()
    _configure_logging(config.log_level)

    buffer = SqliteBuffer(config.db_path)
    forwarder = Forwarder(config, buffer)

    def _handle_signal(signum: int, _frame: FrameType | None) -> None:
        logger.info("received signal %s; shutting down", signum)
        forwarder.stop()

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    try:
        forwarder.run_forever()
    finally:
        buffer.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
