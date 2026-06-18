"""AngaWatch device simulator.

A standalone package (it does NOT import the backend ``app`` package) that
emulates greenhouse sensor nodes publishing telemetry over MQTT. It exists so
the whole AngaWatch stack can be demoed and tested offline, driving the
ingestion → risk → alert pipeline with deterministic, agronomically realistic
scenarios.

The telemetry dicts produced here mirror ``app.schemas.telemetry.TelemetryIn``
field-for-field, but the contract is duplicated by design: the simulator must
run with zero backend dependencies.
"""

from __future__ import annotations

__all__ = ["__version__"]

__version__ = "0.1.0"
