"""Late-blight risk model.

Late blight (*Phytophthora infestans*) on tomato develops when leaves stay wet
and cool for a sustained period. We approximate the classic "wet-hour" disease
pressure rule: an hour counts as a *wet hour* when ``rh_pct >= rh_threshold`` and
``temp_min <= air_temp_c <= temp_max``. We accumulate the most recent run of
consecutive wet hours in the reading window; once that run reaches ``high_hours``
the verdict is HIGH (ventilate / spray a preventive fungicide tonight), and
between ``med_hours`` and ``high_hours`` it is MEDIUM.

Forecast fusion: even when the in-greenhouse window has not yet formed a full
wet period, an overnight forecast that implies the threshold conditions will be
met is used to *pre-warn* (escalate MEDIUM -> HIGH, or raise a fresh MEDIUM).

All thresholds are field-calibratable via ``RiskModelConfig.params``; the values
here are documented Kenya placeholders.
"""

from __future__ import annotations

from datetime import timedelta
from typing import ClassVar

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import ReadingPoint, RiskContext, RiskModel, RiskResult, registry


@registry.register
class BlightRiskModel(RiskModel):
    """Consecutive wet-hour accumulator with overnight forecast fusion."""

    model_type: ClassVar[RiskModelType] = RiskModelType.LATE_BLIGHT
    name: ClassVar[str] = "Late blight (wet-hour)"
    default_params: ClassVar[dict] = {
        # An hour is "wet" when rh >= rh_threshold and temp in [temp_min, temp_max].
        "rh_threshold": 90.0,
        "temp_min": 10.0,
        "temp_max": 26.0,
        # Consecutive wet-hour thresholds for the verdict.
        "high_hours": 10,
        "med_hours": 6,
        # Suppress repeat alerts for this many hours (used by the orchestrator).
        "cooldown_hours": 12,
        # Forecast fusion: how many upcoming hours of forecast to inspect.
        "forecast_lookahead_hours": 12,
    }

    @staticmethod
    def _is_wet(rp: ReadingPoint, rh_threshold: float, temp_min: float, temp_max: float) -> bool:
        if rp.rh_pct is None or rp.air_temp_c is None:
            return False
        return rp.rh_pct >= rh_threshold and temp_min <= rp.air_temp_c <= temp_max

    def evaluate(self, ctx: RiskContext) -> RiskResult | None:
        params = self.resolve_params(ctx)
        rh_threshold = float(params["rh_threshold"])
        temp_min = float(params["temp_min"])
        temp_max = float(params["temp_max"])
        high_hours = int(params["high_hours"])
        med_hours = int(params["med_hours"])

        readings = ctx.readings
        if not readings:
            return None

        # Accumulate the *trailing* run of consecutive wet hours (most recent first).
        # Readings are ascending; iterate from the end and stop at the first dry hour.
        wet_run = 0
        wet_start = None
        for rp in reversed(readings):
            if self._is_wet(rp, rh_threshold, temp_min, temp_max):
                wet_run += 1
                wet_start = rp.time
            else:
                break

        window_end = readings[-1].time

        # ---- Forecast fusion: count contiguous upcoming wet hours overnight. ----
        forecast_wet = self._forecast_wet_hours(ctx, rh_threshold, temp_min, temp_max, params)

        # Effective pressure combines observed trailing wet hours with the forecast
        # run that would continue/begin from the current window.
        effective = wet_run + forecast_wet

        if effective < med_hours:
            return None

        level = RiskLevel.HIGH if effective >= high_hours else RiskLevel.MEDIUM
        # Score is a 0..1 saturation of effective hours against the HIGH threshold.
        score = min(1.0, effective / float(high_hours)) if high_hours else 1.0

        details = {
            "wet_hours": wet_run,
            "forecast_wet_hours": forecast_wet,
            "effective_wet_hours": effective,
            "rh_threshold": rh_threshold,
            "temp_min": temp_min,
            "temp_max": temp_max,
            "high_hours": high_hours,
            "med_hours": med_hours,
            "forecast_fused": forecast_wet > 0,
        }

        if level is RiskLevel.HIGH:
            action_code = "ventilate_and_spray"
            title = "Late blight risk HIGH"
            en = (
                f"High late-blight pressure: {effective}h of cool wet conditions "
                f"(RH>={rh_threshold:.0f}%, {temp_min:.0f}-{temp_max:.0f} C). "
                "Ventilate now and apply a preventive fungicide tonight."
            )
            sw = (
                f"Hatari kubwa ya ukungu (blight): saa {effective} za unyevu na baridi "
                f"(unyevu>={rh_threshold:.0f}%, {temp_min:.0f}-{temp_max:.0f} C). "
                "Pitisha hewa sasa na nyunyizia dawa ya kuzuia ukungu usiku huu."
            )
        else:
            action_code = "ventilate_now"
            title = "Late blight risk MEDIUM"
            en = (
                f"Building late-blight pressure: {effective}h of cool wet conditions. "
                "Open vents to dry the canopy and prepare a preventive spray."
            )
            sw = (
                f"Hatari ya ukungu inajengeka: saa {effective} za unyevu na baridi. "
                "Fungua matundu ili kukausha majani na uandae dawa ya kuzuia."
            )
            if details["forecast_fused"]:
                en += " Forecast shows the wet window will continue overnight."
                sw += " Utabiri unaonyesha unyevu utaendelea usiku."

        return RiskResult(
            model_type=self.model_type,
            level=level,
            score=round(score, 3),
            title=title,
            action_code=action_code,
            message_en=en,
            message_sw=sw,
            dedup_key=f"{self.model_type.value}:{ctx.greenhouse_id}:{level.value}",
            window_start=wet_start,
            window_end=window_end,
            details=details,
        )

    @staticmethod
    def _forecast_wet_hours(
        ctx: RiskContext,
        rh_threshold: float,
        temp_min: float,
        temp_max: float,
        params: dict,
    ) -> int:
        """Count the leading run of wet hours in the upcoming forecast window.

        Only the forecast points at/after ``ctx.now`` within the lookahead horizon
        are considered, and we stop at the first non-wet hour so the count is a
        contiguous overnight run that would extend the current pressure.
        """
        forecast = ctx.forecast
        if not forecast:
            return 0
        lookahead = int(params.get("forecast_lookahead_hours", 12))
        horizon = ctx.now + timedelta(hours=lookahead)
        upcoming = sorted(
            (wp for wp in forecast if ctx.now <= wp.forecast_for <= horizon),
            key=lambda wp: wp.forecast_for,
        )
        run = 0
        for wp in upcoming:
            if wp.rh_pct is None or wp.air_temp_c is None:
                break
            if wp.rh_pct >= rh_threshold and temp_min <= wp.air_temp_c <= temp_max:
                run += 1
            else:
                break
        return run
