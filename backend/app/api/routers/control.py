"""Closed-loop control endpoints: actuators, manual commands, command feed."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import Scope
from app.api.schemas.control import ActuatorOut, CommandIn, ControlCommandOut
from app.control.service import enqueue_command, execute_command
from app.core.logging import get_logger
from app.db.models.common import CommandSource
from app.db.models.control import ActuatorDevice, ControlCommand
from app.db.models.farm import Greenhouse

router = APIRouter(tags=["control"])

log = get_logger(__name__)


@router.get("/greenhouses/{greenhouse_id}/actuators", response_model=list[ActuatorOut])
async def list_actuators(greenhouse_id: uuid.UUID, scope: Scope) -> list[ActuatorDevice]:
    """List a greenhouse's actuators (org-scoped)."""
    gh = await scope.db.scalar(
        select(Greenhouse).where(Greenhouse.id == greenhouse_id, Greenhouse.org_id == scope.org_id)
    )
    if gh is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Greenhouse not found")

    rows = (
        await scope.db.scalars(
            select(ActuatorDevice)
            .where(
                ActuatorDevice.org_id == scope.org_id,
                ActuatorDevice.greenhouse_id == greenhouse_id,
            )
            .order_by(ActuatorDevice.name)
        )
    ).all()
    return list(rows)


@router.post(
    "/actuators/{actuator_id}/command",
    response_model=ControlCommandOut,
    status_code=status.HTTP_201_CREATED,
)
async def send_command(
    actuator_id: uuid.UUID,
    body: CommandIn,
    scope: Scope,
) -> ControlCommand:
    """Manually enqueue + execute a command against an org-scoped actuator."""
    actuator = await scope.db.scalar(
        select(ActuatorDevice).where(
            ActuatorDevice.id == actuator_id,
            ActuatorDevice.org_id == scope.org_id,
        )
    )
    if actuator is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Actuator not found")

    cmd = await enqueue_command(
        scope.db,
        org_id=scope.org_id,
        actuator_device_id=actuator.id,
        command=body.command,
        source=CommandSource.MANUAL,
        issued_by=scope.user.id,
        params=body.params,
    )
    cmd = await execute_command(scope.db, cmd.id)
    log.info(
        "control.manual_command",
        command_id=str(cmd.id),
        status=str(cmd.status),
        issued_by=str(scope.user.id),
    )
    return cmd


@router.get("/control/commands", response_model=list[ControlCommandOut])
async def list_commands(
    scope: Scope,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[ControlCommand]:
    """Return the org's control-command history, newest first."""
    stmt = (
        select(ControlCommand)
        .where(ControlCommand.org_id == scope.org_id)
        .order_by(ControlCommand.issued_at.desc())
        .limit(limit)
    )
    return list((await scope.db.scalars(stmt)).all())
