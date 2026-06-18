"""Farm-record endpoints (Wave 1 scaffold): spray logs, harvest logs, expenses.

These are minimal org-scoped list+create endpoints. Cross-entity rollups
(per-cycle PHI compliance, cost-of-production, yield analytics) are deferred —
see the TODOs.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status
from sqlalchemy import select

from app.api.deps import Scope
from app.api.schemas.records import (
    ExpenseIn,
    ExpenseOut,
    HarvestLogIn,
    HarvestLogOut,
    SprayLogIn,
    SprayLogOut,
)
from app.core.logging import get_logger
from app.db.models.records import Expense, HarvestLog, SprayLog

router = APIRouter(tags=["records"])

log = get_logger(__name__)


# ---- Spray logs -----------------------------------------------------------
@router.get("/spray-logs", response_model=list[SprayLogOut])
async def list_spray_logs(
    scope: Scope,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SprayLog]:
    stmt = (
        select(SprayLog)
        .where(SprayLog.org_id == scope.org_id)
        .order_by(SprayLog.applied_at.desc())
        .limit(limit)
    )
    return list((await scope.db.scalars(stmt)).all())


@router.post("/spray-logs", response_model=SprayLogOut, status_code=status.HTTP_201_CREATED)
async def create_spray_log(body: SprayLogIn, scope: Scope) -> SprayLog:
    row = SprayLog(
        org_id=scope.org_id,
        crop_cycle_id=body.crop_cycle_id,
        product=body.product,
        active_ingredient=body.active_ingredient,
        dose=body.dose,
        dose_unit=body.dose_unit,
        target=body.target,
        phi_days=body.phi_days,
        applied_at=body.applied_at,
        applied_by=scope.user.id,
        notes=body.notes,
    )
    scope.db.add(row)
    await scope.db.flush()
    return row


# ---- Harvest logs ---------------------------------------------------------
@router.get("/harvest-logs", response_model=list[HarvestLogOut])
async def list_harvest_logs(
    scope: Scope,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[HarvestLog]:
    stmt = (
        select(HarvestLog)
        .where(HarvestLog.org_id == scope.org_id)
        .order_by(HarvestLog.harvested_at.desc())
        .limit(limit)
    )
    return list((await scope.db.scalars(stmt)).all())


@router.post("/harvest-logs", response_model=HarvestLogOut, status_code=status.HTTP_201_CREATED)
async def create_harvest_log(body: HarvestLogIn, scope: Scope) -> HarvestLog:
    row = HarvestLog(
        org_id=scope.org_id,
        crop_cycle_id=body.crop_cycle_id,
        quantity_kg=body.quantity_kg,
        grade=body.grade,
        harvested_at=body.harvested_at,
        harvested_by=scope.user.id,
        notes=body.notes,
    )
    scope.db.add(row)
    await scope.db.flush()
    return row


# ---- Expenses -------------------------------------------------------------
@router.get("/expenses", response_model=list[ExpenseOut])
async def list_expenses(
    scope: Scope,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Expense]:
    stmt = (
        select(Expense)
        .where(Expense.org_id == scope.org_id)
        .order_by(Expense.incurred_at.desc())
        .limit(limit)
    )
    return list((await scope.db.scalars(stmt)).all())


@router.post("/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
async def create_expense(body: ExpenseIn, scope: Scope) -> Expense:
    row = Expense(
        org_id=scope.org_id,
        farm_id=body.farm_id,
        crop_cycle_id=body.crop_cycle_id,
        category=body.category,
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        incurred_at=body.incurred_at,
    )
    scope.db.add(row)
    await scope.db.flush()
    return row


# TODO(Wave 1): add per-crop-cycle rollups — PHI-window compliance from spray
# logs, cost-of-production from expenses, and yield/grade analytics from harvest
# logs — exposed as a dedicated /records/{cycle}/summary endpoint (501 until then).
