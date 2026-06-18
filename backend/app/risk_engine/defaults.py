"""Seed ``RiskModelConfig`` rows from each registered model's ``default_params``.

``seed_risk_configs`` is idempotent: it inserts a config row for any registered
model that does not already have one at the requested scope. Pass ``org_id`` to
seed org-scoped overrides; the default (``None``) seeds global defaults that apply
to every org until a more specific row overrides them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.logging import get_logger
from app.db.models.intelligence import RiskModelConfig
from app.risk_engine import models as _models  # noqa: F401  (registers all models)
from app.risk_engine.base import registry

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.orm import Session

logger = get_logger(__name__)


def seed_risk_configs(session: Session, org_id: uuid.UUID | str | None = None) -> None:
    """Create a ``RiskModelConfig`` per registered model at the given scope.

    Existing rows (same ``org_id`` + ``model_type``, greenhouse-unscoped) are left
    untouched so re-running the seed never clobbers calibrated params. Commits its
    own work.
    """
    existing_types = set(
        session.scalars(
            select(RiskModelConfig.model_type)
            .where(_scope_filter(org_id))
            .where(RiskModelConfig.greenhouse_id.is_(None))
        ).all()
    )

    created = 0
    for model in registry.all():
        if model.model_type in existing_types:
            continue
        session.add(
            RiskModelConfig(
                org_id=org_id,
                greenhouse_id=None,
                crop=None,
                model_type=model.model_type,
                name=model.name,
                enabled=True,
                params=dict(model.default_params),
            )
        )
        created += 1

    session.commit()
    logger.info("risk.seed.configs", org_id=str(org_id) if org_id else None, created=created)


def _scope_filter(org_id: uuid.UUID | str | None):
    if org_id is None:
        return RiskModelConfig.org_id.is_(None)
    return RiskModelConfig.org_id == org_id
