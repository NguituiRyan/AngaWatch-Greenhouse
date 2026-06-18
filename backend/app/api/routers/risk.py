"""Risk assessment endpoints.

- ``GET /greenhouses/{id}/risk`` — latest assessment per model for a greenhouse.
- ``GET /greenhouses/{id}/risk/history`` — full history (gated by the
  ``dashboard_history`` premium feature).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import OrgScope, Scope, require_feature
from app.api.schemas.risk import RiskAssessmentOut
from app.core.logging import get_logger
from app.db.models.farm import Greenhouse
from app.db.models.intelligence import RiskAssessment

router = APIRouter(tags=["risk"])

log = get_logger(__name__)


async def _ensure_greenhouse(scope: OrgScope, greenhouse_id: uuid.UUID) -> Greenhouse:
    gh = await scope.db.scalar(
        select(Greenhouse).where(
            Greenhouse.id == greenhouse_id,
            Greenhouse.org_id == scope.org_id,
        )
    )
    if gh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")
    return gh


@router.get("/greenhouses/{greenhouse_id}/risk", response_model=list[RiskAssessmentOut])
async def get_current_risk(greenhouse_id: uuid.UUID, scope: Scope) -> list[RiskAssessment]:
    """Return the latest :class:`RiskAssessment` per model type for the greenhouse."""
    await _ensure_greenhouse(scope, greenhouse_id)

    rows = (
        await scope.db.scalars(
            select(RiskAssessment)
            .where(
                RiskAssessment.org_id == scope.org_id,
                RiskAssessment.greenhouse_id == greenhouse_id,
            )
            .order_by(RiskAssessment.evaluated_at.desc())
        )
    ).all()

    # Keep only the most recent assessment per model type.
    latest: dict[str, RiskAssessment] = {}
    for ra in rows:
        latest.setdefault(ra.model_type.value, ra)
    return list(latest.values())


@router.get(
    "/greenhouses/{greenhouse_id}/risk/history",
    response_model=list[RiskAssessmentOut],
)
async def get_risk_history(
    greenhouse_id: uuid.UUID,
    scope: OrgScope = Depends(require_feature("dashboard_history")),
    model_type: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[RiskAssessment]:
    """Return the historical assessment timeline (premium: ``dashboard_history``)."""
    await _ensure_greenhouse(scope, greenhouse_id)

    stmt = select(RiskAssessment).where(
        RiskAssessment.org_id == scope.org_id,
        RiskAssessment.greenhouse_id == greenhouse_id,
    )
    if model_type:
        stmt = stmt.where(RiskAssessment.model_type == model_type)
    stmt = stmt.order_by(RiskAssessment.evaluated_at.desc()).limit(limit)

    return list((await scope.db.scalars(stmt)).all())
