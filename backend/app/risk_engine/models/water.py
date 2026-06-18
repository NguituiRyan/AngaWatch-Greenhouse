"""Water management + leak-detection model.

Combines drip-line flow with soil moisture to decide between three situations:

* **Irrigate** - soil is dry (``soil_moisture_pct < soil_min``) and no water is
  flowing (``water_flow_l_per_min`` near zero): the crop needs water (MEDIUM, or
  HIGH when critically dry).
* **Leak** - water is flowing (``water_flow_l_per_min > flow_active``) while the
  soil is already wet and there is no scheduled irrigation window: likely a stuck
  valve or burst line (HIGH).
* **Normal** - otherwise no alert.

Regardless of the verdict, the model rolls up the per-cycle water total (max
``water_flow_l_total`` minus the window's starting total) into ``details`` so the
dashboard can show a water-use / savings figure. Whether irrigation is scheduled
is read from ``ctx.extra["irrigation_scheduled"]`` (defaults to False).
"""

from __future__ import annotations

from typing import ClassVar

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import RiskContext, RiskModel, RiskResult, registry


@registry.register
class WaterRiskModel(RiskModel):
    """Soil + flow fusion for irrigation need and leak detection."""

    model_type: ClassVar[RiskModelType] = RiskModelType.WATER
    name: ClassVar[str] = "Water management"
    default_params: ClassVar[dict] = {
        "soil_min": 25.0,
        "soil_critical": 15.0,
        # Soil considered "already wet" above this when judging leaks.
        "soil_wet": 35.0,
        # L/min above which flow is considered active.
        "flow_active": 0.5,
        "cooldown_hours": 6,
    }

    def evaluate(self, ctx: RiskContext) -> RiskResult | None:
        params = self.resolve_params(ctx)
        soil_min = float(params["soil_min"])
        soil_critical = float(params["soil_critical"])
        soil_wet = float(params["soil_wet"])
        flow_active = float(params["flow_active"])

        latest = ctx.latest
        if latest is None:
            return None

        details = self._water_totals(ctx)
        details.update(
            {
                "soil_moisture_pct": latest.soil_moisture_pct,
                "water_flow_l_per_min": latest.water_flow_l_per_min,
                "soil_min": soil_min,
                "flow_active": flow_active,
            }
        )

        soil = latest.soil_moisture_pct
        flow = latest.water_flow_l_per_min
        flowing = flow is not None and flow > flow_active
        scheduled = bool((ctx.extra or {}).get("irrigation_scheduled", False))

        # ---- Leak detection: flow while soil already wet and not scheduled. ----
        if flowing and not scheduled and (soil is None or soil >= soil_wet):
            details["situation"] = "leak"
            en = (
                f"Water is flowing at {flow:.1f} L/min with no scheduled irrigation "
                f"and wet soil ({soil:.0f}%). Possible leak or stuck valve - "
                "shut the supply and inspect the drip line."
                if soil is not None
                else f"Water is flowing at {flow:.1f} L/min with no scheduled "
                "irrigation. Possible leak or stuck valve - shut the supply and inspect."
            )
            sw = (
                f"Maji yanatiririka kwa {flow:.1f} L/dakika bila ratiba ya umwagiliaji "
                "na udongo tayari una unyevu. Yawezekana kuna uvujaji au valvu imekwama - "
                "funga maji na ukague mfumba."
            )
            return RiskResult(
                model_type=self.model_type,
                level=RiskLevel.HIGH,
                score=1.0,
                title="Possible water leak",
                action_code="check_leak",
                message_en=en,
                message_sw=sw,
                dedup_key=f"{self.model_type.value}:{ctx.greenhouse_id}:leak",
                window_start=ctx.readings[0].time,
                window_end=latest.time,
                details=details,
            )

        # ---- Irrigation need: dry soil, no flow. ----
        if soil is not None and soil < soil_min and not flowing:
            critical = soil < soil_critical
            level = RiskLevel.HIGH if critical else RiskLevel.MEDIUM
            details["situation"] = "irrigate"
            en = (
                f"Soil moisture {soil:.0f}% is below {soil_min:.0f}% and no water is "
                "flowing. Start irrigation"
                + (" immediately to prevent wilting." if critical else " soon.")
            )
            sw = (
                f"Unyevu wa udongo {soil:.0f}% uko chini ya {soil_min:.0f}% na hakuna "
                "maji yanayotiririka. Anza umwagiliaji"
                + (" mara moja kuzuia kunyauka." if critical else " hivi karibuni.")
            )
            return RiskResult(
                model_type=self.model_type,
                level=level,
                score=1.0 if critical else 0.6,
                title="Irrigation needed",
                action_code="irrigate",
                message_en=en,
                message_sw=sw,
                dedup_key=f"{self.model_type.value}:{ctx.greenhouse_id}:irrigate",
                window_start=ctx.readings[0].time,
                window_end=latest.time,
                details=details,
            )

        return None

    @staticmethod
    def _water_totals(ctx: RiskContext) -> dict:
        """Roll up per-cycle water usage from the cumulative flow totals in the window."""
        totals = [r.water_flow_l_total for r in ctx.readings if r.water_flow_l_total is not None]
        if not totals:
            return {"water_used_l": 0.0, "window_start_total_l": None, "window_end_total_l": None}
        start = min(totals)
        end = max(totals)
        return {
            "water_used_l": round(end - start, 2),
            "window_start_total_l": round(start, 2),
            "window_end_total_l": round(end, 2),
        }
