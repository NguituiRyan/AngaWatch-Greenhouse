"""Microclimate guardrail model (mirrors the on-firmware safety checks).

This model evaluates the *latest* reading against simple comfort/safety bands so
it can also be implemented on the node firmware for offline protection:

* ``air_temp_c > temp_high`` -> heat stress, vent now (HIGH).
* ``rh_pct > rh_warn`` -> fungal-favourable humidity (MEDIUM).
* ``soil_moisture_pct < soil_min`` -> dry root zone, irrigate (MEDIUM, or HIGH
  when critically dry below ``soil_critical``).

The highest-severity condition wins; the other triggered conditions are recorded
in ``details`` so the recommendation can mention them. All bands are
field-calibratable; values here are documented Kenya placeholders.
"""

from __future__ import annotations

from typing import ClassVar

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import RiskContext, RiskModel, RiskResult, registry


@registry.register
class MicroclimateRiskModel(RiskModel):
    """Latest-reading temperature / humidity / soil-moisture guardrails."""

    model_type: ClassVar[RiskModelType] = RiskModelType.MICROCLIMATE
    name: ClassVar[str] = "Microclimate guardrails"
    default_params: ClassVar[dict] = {
        "temp_high": 35.0,
        "rh_warn": 85.0,
        "soil_min": 25.0,
        "soil_critical": 15.0,
        "cooldown_hours": 6,
    }

    def evaluate(self, ctx: RiskContext) -> RiskResult | None:
        params = self.resolve_params(ctx)
        temp_high = float(params["temp_high"])
        rh_warn = float(params["rh_warn"])
        soil_min = float(params["soil_min"])
        soil_critical = float(params["soil_critical"])

        latest = ctx.latest
        if latest is None:
            return None

        triggers: list[tuple[RiskLevel, str, str, str, str]] = []

        if latest.air_temp_c is not None and latest.air_temp_c > temp_high:
            triggers.append(
                (
                    RiskLevel.HIGH,
                    "vent_now",
                    "Greenhouse overheating",
                    f"Air temperature {latest.air_temp_c:.1f} C exceeds {temp_high:.0f} C. "
                    "Vent now to prevent heat stress and flower drop.",
                    f"Joto la hewa {latest.air_temp_c:.1f} C limezidi {temp_high:.0f} C. "
                    "Pitisha hewa sasa kuzuia mkazo wa joto na kudondoka kwa maua.",
                )
            )

        if latest.soil_moisture_pct is not None:
            if latest.soil_moisture_pct < soil_critical:
                triggers.append(
                    (
                        RiskLevel.HIGH,
                        "irrigate_now",
                        "Root zone critically dry",
                        f"Soil moisture {latest.soil_moisture_pct:.1f}% is below the critical "
                        f"{soil_critical:.0f}%. Irrigate immediately to avoid wilting.",
                        f"Unyevu wa udongo {latest.soil_moisture_pct:.1f}% uko chini ya "
                        f"{soil_critical:.0f}%. Mwagilia maji mara moja kuzuia kunyauka.",
                    )
                )
            elif latest.soil_moisture_pct < soil_min:
                triggers.append(
                    (
                        RiskLevel.MEDIUM,
                        "irrigate",
                        "Soil moisture low",
                        f"Soil moisture {latest.soil_moisture_pct:.1f}% is below {soil_min:.0f}%. "
                        "Schedule irrigation soon.",
                        f"Unyevu wa udongo {latest.soil_moisture_pct:.1f}% uko chini ya "
                        f"{soil_min:.0f}%. Panga kumwagilia hivi karibuni.",
                    )
                )

        if latest.rh_pct is not None and latest.rh_pct > rh_warn:
            triggers.append(
                (
                    RiskLevel.MEDIUM,
                    "reduce_humidity",
                    "Humidity favours fungal disease",
                    f"Relative humidity {latest.rh_pct:.0f}% exceeds {rh_warn:.0f}%. "
                    "Ventilate to reduce fungal disease risk.",
                    f"Unyevu wa hewa {latest.rh_pct:.0f}% umezidi {rh_warn:.0f}%. "
                    "Pitisha hewa kupunguza hatari ya magonjwa ya ukungu.",
                )
            )

        if not triggers:
            return None

        # Highest-severity trigger wins as the headline verdict.
        triggers.sort(key=lambda t: t[0].rank, reverse=True)
        level, action_code, title, en, sw = triggers[0]

        details = {
            "air_temp_c": latest.air_temp_c,
            "rh_pct": latest.rh_pct,
            "soil_moisture_pct": latest.soil_moisture_pct,
            "temp_high": temp_high,
            "rh_warn": rh_warn,
            "soil_min": soil_min,
            "soil_critical": soil_critical,
            "triggers": [t[1] for t in triggers],
        }
        score = 1.0 if level is RiskLevel.HIGH else 0.6

        return RiskResult(
            model_type=self.model_type,
            level=level,
            score=score,
            title=title,
            action_code=action_code,
            message_en=en,
            message_sw=sw,
            dedup_key=f"{self.model_type.value}:{ctx.greenhouse_id}:{action_code}",
            window_start=latest.time,
            window_end=latest.time,
            details=details,
        )
