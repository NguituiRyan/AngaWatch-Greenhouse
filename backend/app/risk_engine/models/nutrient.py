"""Nutrient (NPK) deficit model.

Compares the latest soil N/P/K readings against the crop-stage targets supplied
to the context (``ctx.extra["npk_targets"]`` is the ``Crop.npk_targets[stage]``
dict resolved by the orchestrator). A nutrient is *deficient* when it falls below
``(1 - deficit_fraction)`` of its target; the worst relative deficit drives the
verdict (MEDIUM, or HIGH past ``severe_fraction``). The recommendation names the
deficient nutrients so a fertigation mix can be adjusted.

Targets are crop/stage specific and are owned by the crop catalog, so this model
holds only the comparison tolerances as calibratable params.
"""

from __future__ import annotations

import contextlib
from typing import ClassVar

from app.db.models.common import RiskLevel, RiskModelType
from app.risk_engine.base import RiskContext, RiskModel, RiskResult, registry

_NUTRIENT_FIELDS = {
    "n": "npk_n_ppm",
    "p": "npk_p_ppm",
    "k": "npk_k_ppm",
}
_NUTRIENT_LABELS = {"n": "nitrogen", "p": "phosphorus", "k": "potassium"}
_NUTRIENT_LABELS_SW = {"n": "naitrojeni", "p": "fosforasi", "k": "potasiamu"}


@registry.register
class NutrientRiskModel(RiskModel):
    """Latest NPK vs crop-stage target comparison."""

    model_type: ClassVar[RiskModelType] = RiskModelType.NUTRIENT
    name: ClassVar[str] = "Nutrient (NPK) deficit"
    default_params: ClassVar[dict] = {
        # Below (1 - deficit_fraction) * target -> deficient.
        "deficit_fraction": 0.15,
        # Below (1 - severe_fraction) * target -> severe (HIGH).
        "severe_fraction": 0.35,
        "cooldown_hours": 24,
    }

    def evaluate(self, ctx: RiskContext) -> RiskResult | None:
        params = self.resolve_params(ctx)
        deficit_fraction = float(params["deficit_fraction"])
        severe_fraction = float(params["severe_fraction"])

        latest = ctx.latest
        if latest is None:
            return None

        targets = self._resolve_targets(ctx)
        if not targets:
            return None

        deficits: list[dict] = []
        worst_relative = 0.0
        for key, field in _NUTRIENT_FIELDS.items():
            target = targets.get(key)
            value = getattr(latest, field)
            if target is None or value is None or target <= 0:
                continue
            relative = (target - value) / target  # >0 means below target
            if relative > deficit_fraction:
                deficits.append(
                    {
                        "nutrient": key,
                        "value_ppm": value,
                        "target_ppm": target,
                        "relative_deficit": round(relative, 3),
                    }
                )
                worst_relative = max(worst_relative, relative)

        if not deficits:
            return None

        level = RiskLevel.HIGH if worst_relative >= severe_fraction else RiskLevel.MEDIUM
        score = min(1.0, worst_relative / severe_fraction) if severe_fraction else 1.0

        names_en = ", ".join(_NUTRIENT_LABELS[d["nutrient"]] for d in deficits)
        names_sw = ", ".join(_NUTRIENT_LABELS_SW[d["nutrient"]] for d in deficits)
        codes = "".join(d["nutrient"].upper() for d in deficits)

        en = (
            f"Soil nutrients low for {ctx.crop_stage or 'current stage'}: {names_en} "
            f"below target. Adjust the fertigation mix to top up {codes}."
        )
        sw = (
            f"Virutubisho vya udongo viko chini kwa hatua ya {ctx.crop_stage or 'sasa'}: "
            f"{names_sw} viko chini ya lengo. Rekebisha mchanganyiko wa mbolea kuongeza {codes}."
        )

        return RiskResult(
            model_type=self.model_type,
            level=level,
            score=round(score, 3),
            title="Nutrient deficit detected",
            action_code="adjust_fertigation",
            message_en=en,
            message_sw=sw,
            dedup_key=f"{self.model_type.value}:{ctx.greenhouse_id}:{codes}",
            window_start=latest.time,
            window_end=latest.time,
            details={
                "deficits": deficits,
                "targets": targets,
                "crop_stage": ctx.crop_stage,
                "deficit_fraction": deficit_fraction,
                "severe_fraction": severe_fraction,
            },
        )

    @staticmethod
    def _resolve_targets(ctx: RiskContext) -> dict[str, float]:
        """Pull the {n,p,k} ppm targets for the current stage from the context.

        The orchestrator places the stage-resolved target dict in
        ``ctx.extra["npk_targets"]``. Keys are normalised to lowercase n/p/k.
        """
        raw = (ctx.extra or {}).get("npk_targets")
        if not isinstance(raw, dict):
            return {}
        out: dict[str, float] = {}
        for key in ("n", "p", "k"):
            for candidate in (key, key.upper()):
                if candidate in raw and raw[candidate] is not None:
                    with contextlib.suppress(TypeError, ValueError):
                        out[key] = float(raw[candidate])
                    break
        return out
