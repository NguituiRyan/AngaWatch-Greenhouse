"""AngaWatch edge gateway.

A small, standalone store-and-forward bridge that runs on-farm (e.g. a Raspberry
Pi next to the local Mosquitto broker). It subscribes to the LOCAL broker on
``farm/#``, durably buffers every telemetry message to an on-disk SQLite queue,
and batch-forwards buffered messages to the CLOUD broker whenever it is
reachable. When the cloud link is down (a near-universal condition on rural
Kenyan connectivity) messages keep accumulating on disk and are retried with
exponential backoff, so no readings are lost — offline-first by construction.

This package deliberately depends only on ``paho-mqtt`` and the Python standard
library (``sqlite3``); it does NOT import the ``app.*`` backend package, so it
can be deployed on a minimal edge device.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
