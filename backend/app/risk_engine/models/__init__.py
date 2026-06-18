"""Concrete risk models. Importing this package registers every model.

Each module decorates its model with ``@registry.register`` so simply importing
this package (a side effect of importing ``app.risk_engine.engine``) populates the
process-wide registry with: late_blight, tuta_absoluta, microclimate, nutrient,
water.
"""

from __future__ import annotations

from app.risk_engine.models.blight import BlightRiskModel
from app.risk_engine.models.microclimate import MicroclimateRiskModel
from app.risk_engine.models.nutrient import NutrientRiskModel
from app.risk_engine.models.tuta import TutaRiskModel
from app.risk_engine.models.water import WaterRiskModel

__all__ = [
    "BlightRiskModel",
    "MicroclimateRiskModel",
    "NutrientRiskModel",
    "TutaRiskModel",
    "WaterRiskModel",
]
