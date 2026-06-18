"""Pluggable, parameter-driven agronomic risk engine (the core IP).

Public surface::

    from app.risk_engine import RiskModel, RiskContext, RiskResult, registry

Concrete models live in ``app.risk_engine.models`` and self-register via the
``@register`` decorator. The orchestrator in ``app.risk_engine.engine`` loads
recent readings per greenhouse, builds a ``RiskContext``, runs every enabled
model, and persists ``RiskAssessment`` + ``Alert`` + ``Recommendation`` rows.
"""

from app.risk_engine.base import (
    ReadingPoint,
    RiskContext,
    RiskModel,
    RiskResult,
    WeatherPoint,
    registry,
)

__all__ = [
    "ReadingPoint",
    "RiskContext",
    "RiskModel",
    "RiskResult",
    "WeatherPoint",
    "registry",
]
