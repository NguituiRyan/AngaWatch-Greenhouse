"""Recommendation endpoints: list + agronomist override."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import Scope, require_role
from app.api.schemas.recommendations import OverrideIn, RecommendationOut
from app.core.logging import get_logger
from app.db.models.common import UserRole
from app.db.models.intelligence import Recommendation

router = APIRouter(prefix="/recommendations", tags=["recommendations"])

log = get_logger(__name__)


@router.get("", response_model=list[RecommendationOut])
async def list_recommendations(
    scope: Scope,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Recommendation]:
    """Return the org's recommendations, highest priority + newest first."""
    stmt = (
        select(Recommendation)
        .where(Recommendation.org_id == scope.org_id)
        .order_by(Recommendation.priority.desc(), Recommendation.created_at.desc())
        .limit(limit)
    )
    return list((await scope.db.scalars(stmt)).all())


@router.post(
    "/{recommendation_id}/override",
    response_model=RecommendationOut,
    dependencies=[Depends(require_role(UserRole.AGRONOMIST, UserRole.COOP_ADMIN))],
)
async def override_recommendation(
    recommendation_id: uuid.UUID,
    body: OverrideIn,
    scope: Scope,
) -> Recommendation:
    """Store an agronomist override (kept as a future training signal)."""
    rec = await scope.db.scalar(
        select(Recommendation).where(
            Recommendation.id == recommendation_id,
            Recommendation.org_id == scope.org_id,
        )
    )
    if rec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Recommendation not found"
        )

    rec.overridden = True
    rec.override_message = body.message
    rec.override_by = scope.user.id
    rec.override_at = datetime.now(UTC)
    await scope.db.flush()
    log.info(
        "recommendation.overridden",
        recommendation_id=str(rec.id),
        override_by=str(scope.user.id),
    )
    return rec
