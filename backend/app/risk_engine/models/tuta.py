"""Tuta absoluta (tomato leafminer) generation-pressure model.

Tuta development is driven by accumulated heat. We sum *growing degree-days*
above ``base_temp_c`` across the reading window and project how far the current
generation has progressed toward the next emergence (``generation_dd``). When the
accumulated degree-days since the last generation reset crosses the threshold a
new generation is emerging and the spray window is open. Pheromone trap catches
above ``trap_threshold`` independently elevate the pressure (confirmed adult
flight), pushing MEDIUM up to HIGH.

Degree-days are estimated per reading interval using the average air temperature
between consecutive samples, prorated by the elapsed time, so the model is robust
to irregular sampling. All thresholds are field-calibratable; values here are
documented Kenya placeholders.
"""

from __future__ import annotations

from typing import ClassVar

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import RiskContext, RiskModel, RiskResult, registry


@registry.register
class TutaRiskModel(RiskModel):
    """Degree-day generation tracker with pheromone-trap escalation."""

    model_type: ClassVar[RiskModelType] = RiskModelType.TUTA_ABSOLUTA
    name: ClassVar[str] = "Tuta absoluta (degree-day)"
    default_params: ClassVar[dict] = {
        # Lower development threshold for Tuta absoluta.
        "base_temp_c": 10.0,
        # Degree-days for one complete generation (egg -> adult). Calibrate.
        "generation_dd": 208.0,
        # Pheromone catches above this in the window confirm adult flight.
        "trap_threshold": 30,
        # Fraction of a generation that already warrants a MEDIUM warning.
        "warn_fraction": 0.75,
        "cooldown_hours": 24,
    }

    def evaluate(self, ctx: RiskContext) -> RiskResult | None:
        params = self.resolve_params(ctx)
        base_temp = float(params["base_temp_c"])
        generation_dd = float(params["generation_dd"])
        trap_threshold = int(params["trap_threshold"])
        warn_fraction = float(params.get("warn_fraction", 0.75))

        readings = ctx.readings
        if len(readings) < 2:
            return None

        # Allow a carry-in of degree-days accumulated before this window (e.g. the
        # orchestrator can pass the last generation reset). Default: window start.
        dd = float(ctx.extra.get("tuta_dd_carry", 0.0)) if ctx.extra else 0.0
        dd += self._accumulate_degree_days(readings, base_temp)

        # Pheromone pressure: max trap count observed in the window.
        trap_counts = [r.pheromone_count for r in readings if r.pheromone_count is not None]
        max_trap = max(trap_counts) if trap_counts else 0
        trap_elevated = max_trap > trap_threshold

        fraction = dd / generation_dd if generation_dd else 0.0
        window_start = readings[0].time
        window_end = readings[-1].time

        generation_crossed = dd >= generation_dd
        building = fraction >= warn_fraction

        if not generation_crossed and not building and not trap_elevated:
            return None

        # Level logic: a crossed generation, or trap-confirmed adults, is HIGH.
        level = RiskLevel.HIGH if (generation_crossed or trap_elevated) else RiskLevel.MEDIUM

        score = min(1.0, fraction)
        if trap_elevated:
            score = max(score, 0.9)

        details = {
            "degree_days": round(dd, 2),
            "generation_dd": generation_dd,
            "generation_fraction": round(fraction, 3),
            "generation_crossed": generation_crossed,
            "base_temp_c": base_temp,
            "max_pheromone_count": max_trap,
            "trap_threshold": trap_threshold,
            "trap_elevated": trap_elevated,
        }

        if generation_crossed:
            title = "Tuta absoluta: new generation emerging"
            action_code = "tuta_spray_window"
            en = (
                f"Tuta absoluta has accumulated {dd:.0f} degree-days "
                f"(~{fraction:.0%} of a generation). A new generation is emerging - "
                "the spray window is open, scout leaves and check pheromone traps."
            )
            sw = (
                f"Tuta absoluta imekusanya digrii-siku {dd:.0f} "
                f"(~{fraction:.0%} ya kizazi). Kizazi kipya kinaibuka - "
                "nyunyizia dawa sasa, kagua majani na mitego ya kemikali."
            )
        elif trap_elevated:
            title = "Tuta absoluta: adult flight detected"
            action_code = "tuta_scout_and_spray"
            en = (
                f"Pheromone traps caught {max_trap} moths (> {trap_threshold}). "
                "Adult Tuta flight is active - scout for mines and time a spray."
            )
            sw = (
                f"Mitego imekamata nondo {max_trap} (> {trap_threshold}). "
                "Tuta wazima wanaruka - kagua mashambulizi na panga kunyunyizia dawa."
            )
        else:
            title = "Tuta absoluta: generation building"
            action_code = "tuta_monitor"
            en = (
                f"Tuta degree-days at {dd:.0f} (~{fraction:.0%} of a generation). "
                "Pressure is building - increase trap checks and prepare to spray."
            )
            sw = (
                f"Digrii-siku za Tuta ziko {dd:.0f} (~{fraction:.0%} ya kizazi). "
                "Hatari inajengeka - ongeza ukaguzi wa mitego na uandae dawa."
            )

        return RiskResult(
            model_type=self.model_type,
            level=level,
            score=round(score, 3),
            title=title,
            action_code=action_code,
            message_en=en,
            message_sw=sw,
            dedup_key=f"{self.model_type.value}:{ctx.greenhouse_id}:{level.value}",
            window_start=window_start,
            window_end=window_end,
            details=details,
        )

    @staticmethod
    def _accumulate_degree_days(readings, base_temp: float) -> float:
        """Integrate (mean_temp - base_temp)+ over each inter-sample interval (in days).

        Readings without an ``air_temp_c`` are skipped; the next reading that does
        carry a temperature pairs with the previous one that had a temperature.
        """
        dd = 0.0
        prev = None
        for rp in readings:
            if rp.air_temp_c is None:
                continue
            if prev is not None:
                hours = (rp.time - prev.time).total_seconds() / 3600.0
                if hours > 0:
                    mean_temp = (rp.air_temp_c + prev.air_temp_c) / 2.0
                    contribution = (mean_temp - base_temp) * (hours / 24.0)
                    if contribution > 0:
                        dd += contribution
            prev = rp
        return dd
