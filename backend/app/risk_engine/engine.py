"""Risk-engine orchestrator.

``evaluate_greenhouse`` is the single sync entry point that the Celery task and
any seed/demo code call. For one greenhouse it:

1. loads the recent reading window (~48h) as ``ReadingPoint``s,
2. loads the active ``CropCycle`` (for crop name + stage + NPK targets),
3. loads the recent ``WeatherForecast`` for the farm as ``WeatherPoint``s,
4. resolves each model's params by merging ``RiskModelConfig.params`` over the
   model ``default_params`` with precedence greenhouse > org > global,
5. runs every enabled model and persists a ``RiskAssessment`` per result,
6. for actionable results (MEDIUM+), upserts an ``Alert`` deduplicated by
   ``dedup_key`` within the model's ``cooldown_hours`` and attaches a
   ``Recommendation`` (EN + SW).

It is intentionally pure SQLAlchemy-2.0 sync so it runs under Celery and against
SQLite in tests.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.common import AlertStatus
from app.db.models.crop import Crop, CropCycle
from app.db.models.farm import Greenhouse
from app.db.models.intelligence import Alert, Recommendation, RiskAssessment, RiskModelConfig
from app.db.models.reading import Reading
from app.db.models.weather import WeatherForecast
from app.risk_engine import models as _models  # noqa: F401  (registers all models)
from app.risk_engine.base import ReadingPoint, RiskContext, RiskResult, WeatherPoint, registry

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

logger = get_logger(__name__)

# How far back to load the reading window. Blight needs ~10+ wet hours; 48h gives
# headroom for irregular sampling and forecast fusion.
READING_WINDOW_HOURS = 48
FORECAST_WINDOW_HOURS = 24


def evaluate_greenhouse(
    session: Session,
    greenhouse_id: uuid.UUID | str,
    now: datetime | None = None,
) -> list[RiskAssessment]:
    """Run every enabled risk model for one greenhouse and persist the outcome.

    Returns the list of persisted ``RiskAssessment`` rows (one per model that
    produced a verdict). Commits its own work.
    """
    now = now or datetime.now(UTC)

    greenhouse = session.get(Greenhouse, greenhouse_id)
    if greenhouse is None:
        logger.warning("risk.eval.greenhouse_missing", greenhouse_id=str(greenhouse_id))
        return []

    org_id = greenhouse.org_id
    readings = _load_readings(session, greenhouse_id, now)
    cycle = _load_active_cycle(session, org_id, greenhouse_id)
    crop_name, crop_stage, npk_targets = _resolve_crop(session, cycle)
    forecast = _load_forecast(session, org_id, greenhouse.farm_id, now)
    configs = _load_configs(session, org_id, greenhouse_id)

    assessments: list[RiskAssessment] = []
    for model in registry.all():
        params, enabled = _resolve_params(model, configs)
        if not enabled:
            continue

        ctx = RiskContext(
            org_id=str(org_id),
            greenhouse_id=str(greenhouse_id),
            now=now,
            readings=readings,
            params=params,
            crop=crop_name,
            crop_stage=crop_stage,
            crop_cycle_id=str(cycle.id) if cycle else None,
            forecast=forecast,
            extra={"npk_targets": npk_targets} if npk_targets else {},
        )

        try:
            result = model.evaluate(ctx)
        except Exception:  # pragma: no cover - defensive; one bad model must not stop the rest
            logger.exception("risk.eval.model_error", model=model.model_type.value)
            continue
        if result is None:
            continue

        assessment = _persist_assessment(session, org_id, greenhouse_id, cycle, result, now)
        assessments.append(assessment)

        if result.is_actionable:
            cooldown_hours = int(params.get("cooldown_hours", 12))
            _upsert_alert_and_recommendation(
                session, org_id, greenhouse_id, assessment, result, now, cooldown_hours
            )

    session.commit()
    logger.info(
        "risk.eval.done",
        greenhouse_id=str(greenhouse_id),
        assessments=len(assessments),
    )
    return assessments


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
def _load_readings(
    session: Session, greenhouse_id: uuid.UUID | str, now: datetime
) -> list[ReadingPoint]:
    since = now - timedelta(hours=READING_WINDOW_HOURS)
    rows = session.scalars(
        select(Reading)
        .where(Reading.greenhouse_id == greenhouse_id)
        .where(Reading.time >= since)
        .order_by(Reading.time.asc())
    ).all()
    return [_to_reading_point(r) for r in rows]


def _to_reading_point(r: Reading) -> ReadingPoint:
    return ReadingPoint(
        time=r.time,
        air_temp_c=r.air_temp_c,
        rh_pct=r.rh_pct,
        leaf_wetness=r.leaf_wetness,
        ppfd=r.ppfd,
        co2_ppm=r.co2_ppm,
        soil_moisture_pct=r.soil_moisture_pct,
        soil_temp_c=r.soil_temp_c,
        npk_n_ppm=r.npk_n_ppm,
        npk_p_ppm=r.npk_p_ppm,
        npk_k_ppm=r.npk_k_ppm,
        water_flow_l_total=r.water_flow_l_total,
        water_flow_l_per_min=r.water_flow_l_per_min,
        pheromone_count=r.pheromone_count,
        battery_v=r.battery_v,
        rssi=r.rssi,
    )


def _load_active_cycle(
    session: Session, org_id: uuid.UUID, greenhouse_id: uuid.UUID | str
) -> CropCycle | None:
    return session.scalars(
        select(CropCycle)
        .where(CropCycle.org_id == org_id)
        .where(CropCycle.greenhouse_id == greenhouse_id)
        .where(CropCycle.is_active.is_(True))
        .order_by(CropCycle.planting_date.desc())
        .limit(1)
    ).first()


def _resolve_crop(
    session: Session, cycle: CropCycle | None
) -> tuple[str | None, str | None, dict | None]:
    """Return (crop_name, stage_value, stage_npk_targets) for the active cycle."""
    if cycle is None:
        return None, None, None
    stage = cycle.current_stage.value
    crop = session.get(Crop, cycle.crop_id)
    targets = None
    if crop and isinstance(crop.npk_targets, dict):
        stage_targets = crop.npk_targets.get(stage)
        if isinstance(stage_targets, dict):
            targets = stage_targets
    return cycle.crop_name, stage, targets


def _load_forecast(
    session: Session, org_id: uuid.UUID, farm_id: uuid.UUID, now: datetime
) -> list[WeatherPoint]:
    horizon = now + timedelta(hours=FORECAST_WINDOW_HOURS)
    rows = session.scalars(
        select(WeatherForecast)
        .where(WeatherForecast.org_id == org_id)
        .where(WeatherForecast.farm_id == farm_id)
        .where(WeatherForecast.forecast_for >= now - timedelta(hours=1))
        .where(WeatherForecast.forecast_for <= horizon)
        .order_by(WeatherForecast.forecast_for.asc())
    ).all()
    return [
        WeatherPoint(
            forecast_for=row.forecast_for,
            air_temp_c=row.air_temp_c,
            rh_pct=row.rh_pct,
            rain_prob=row.rain_prob,
            rainfall_mm=row.rainfall_mm,
        )
        for row in rows
    ]


def _load_configs(
    session: Session, org_id: uuid.UUID, greenhouse_id: uuid.UUID | str
) -> list[RiskModelConfig]:
    """Load every config row applicable to this greenhouse (global/org/greenhouse)."""
    return list(
        session.scalars(
            select(RiskModelConfig).where(
                (RiskModelConfig.org_id == org_id) | (RiskModelConfig.org_id.is_(None)),
            )
        ).all()
    )


# ---------------------------------------------------------------------------
# Param resolution (precedence: greenhouse > org > global)
# ---------------------------------------------------------------------------
def _resolve_params(model, configs: list[RiskModelConfig]) -> tuple[dict, bool]:
    """Merge config params over the model defaults with scope precedence.

    Returns ``(params, enabled)``. The most specific config row wins both for the
    ``enabled`` flag and for each param key (greenhouse beats org beats global).
    """
    relevant = [c for c in configs if c.model_type == model.model_type]
    # Rank: greenhouse (2) > org (1) > global (0). Sort ascending so we apply in
    # least-specific-first order and let the most specific overwrite.
    relevant.sort(key=_config_specificity)

    params = dict(model.default_params)
    enabled = True
    for cfg in relevant:
        if isinstance(cfg.params, dict):
            params.update(cfg.params)
        enabled = cfg.enabled  # most specific (last) wins
    return params, enabled


def _config_specificity(cfg: RiskModelConfig) -> int:
    if cfg.greenhouse_id is not None:
        return 2
    if cfg.org_id is not None:
        return 1
    return 0


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------
def _persist_assessment(
    session: Session,
    org_id: uuid.UUID,
    greenhouse_id: uuid.UUID | str,
    cycle: CropCycle | None,
    result: RiskResult,
    now: datetime,
) -> RiskAssessment:
    assessment = RiskAssessment(
        org_id=org_id,
        greenhouse_id=greenhouse_id,
        crop_cycle_id=cycle.id if cycle else None,
        model_type=result.model_type,
        level=result.level,
        score=result.score,
        window_start=result.window_start,
        window_end=result.window_end,
        details=result.details,
        evaluated_at=now,
    )
    session.add(assessment)
    session.flush()
    return assessment


def _upsert_alert_and_recommendation(
    session: Session,
    org_id: uuid.UUID,
    greenhouse_id: uuid.UUID | str,
    assessment: RiskAssessment,
    result: RiskResult,
    now: datetime,
    cooldown_hours: int,
) -> None:
    """Create or refresh the dedup'd Alert + its Recommendation for an actionable result."""
    existing = _find_recent_alert(session, org_id, result.dedup_key, now, cooldown_hours)

    if existing is not None:
        # Within cooldown: update the linkage/level but do not create a duplicate.
        existing.risk_assessment_id = assessment.id
        existing.level = result.level
        if existing.recommendation is not None:
            _refresh_recommendation(existing.recommendation, result)
        else:
            session.add(_build_recommendation(org_id, existing, assessment, result))
        logger.info(
            "risk.alert.deduped",
            dedup_key=result.dedup_key,
            greenhouse_id=str(greenhouse_id),
        )
        return

    alert = Alert(
        org_id=org_id,
        greenhouse_id=greenhouse_id,
        risk_assessment_id=assessment.id,
        model_type=result.model_type,
        level=result.level,
        title=result.title,
        dedup_key=result.dedup_key,
        status=AlertStatus.PENDING,
        dispatch_log=[],
        first_seen_at=now,
    )
    session.add(alert)
    session.flush()
    session.add(_build_recommendation(org_id, alert, assessment, result))


def _find_recent_alert(
    session: Session,
    org_id: uuid.UUID,
    dedup_key: str,
    now: datetime,
    cooldown_hours: int,
) -> Alert | None:
    cutoff = now - timedelta(hours=cooldown_hours)
    return session.scalars(
        select(Alert)
        .where(Alert.org_id == org_id)
        .where(Alert.dedup_key == dedup_key)
        .where(Alert.status != AlertStatus.ACKED)
        .where(Alert.first_seen_at >= cutoff)
        .order_by(Alert.first_seen_at.desc())
        .limit(1)
    ).first()


def _build_recommendation(
    org_id: uuid.UUID,
    alert: Alert,
    assessment: RiskAssessment,
    result: RiskResult,
) -> Recommendation:
    return Recommendation(
        org_id=org_id,
        alert_id=alert.id,
        risk_assessment_id=assessment.id,
        action_code=result.action_code,
        message_en=result.message_en,
        message_sw=result.message_sw,
        priority=result.level.rank,
    )


def _refresh_recommendation(rec: Recommendation, result: RiskResult) -> None:
    if rec.overridden:
        return
    rec.action_code = result.action_code
    rec.message_en = result.message_en
    rec.message_sw = result.message_sw
    rec.priority = result.level.rank
