"""Alert feed endpoints: list org alerts and acknowledge one."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import Scope
from app.api.schemas.alerts import AlertOut
from app.core.logging import get_logger
from app.db.models.common import AlertStatus
from app.db.models.intelligence import Alert

router = APIRouter(prefix="/alerts", tags=["alerts"])

log = get_logger(__name__)


@router.get("", response_model=list[AlertOut])
async def list_alerts(
    scope: Scope,
    status_filter: AlertStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Alert]:
    """Return the org's alert feed, newest first, optionally filtered by status."""
    stmt = select(Alert).where(Alert.org_id == scope.org_id)
    if status_filter is not None:
        stmt = stmt.where(Alert.status == status_filter)
    stmt = stmt.order_by(Alert.first_seen_at.desc()).limit(limit)
    return list((await scope.db.scalars(stmt)).all())


@router.post("/{alert_id}/ack", response_model=AlertOut)
async def ack_alert(alert_id: uuid.UUID, scope: Scope) -> Alert:
    """Acknowledge an alert: set status ``ACKED`` and stamp ``acked_by``/``acked_at``."""
    alert = await scope.db.scalar(
        select(Alert).where(Alert.id == alert_id, Alert.org_id == scope.org_id)
    )
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

    alert.status = AlertStatus.ACKED
    alert.acked_at = datetime.now(UTC)
    alert.acked_by = scope.user.id
    await scope.db.flush()
    log.info("alert.acked", alert_id=str(alert.id), acked_by=str(scope.user.id))
    return alert
