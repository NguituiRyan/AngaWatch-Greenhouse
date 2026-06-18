"""Risk engine interfaces: the ``RiskModel`` ABC, its IO dataclasses, and a registry.

Deliberately free of any ORM/DB import so each model is a pure function of
(readings, params, forecast) and unit-testable with synthetic data.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar

from app.db.models.common import RiskLevel, RiskModelType


@dataclass(slots=True)
class ReadingPoint:
    """A single telemetry sample, decoupled from the ORM ``Reading`` row."""

    time: datetime
    air_temp_c: float | None = None
    rh_pct: float | None = None
    leaf_wetness: float | None = None
    ppfd: float | None = None
    co2_ppm: float | None = None
    soil_moisture_pct: float | None = None
    soil_temp_c: float | None = None
    npk_n_ppm: float | None = None
    npk_p_ppm: float | None = None
    npk_k_ppm: float | None = None
    water_flow_l_total: float | None = None
    water_flow_l_per_min: float | None = None
    pheromone_count: int | None = None
    battery_v: float | None = None
    rssi: int | None = None


@dataclass(slots=True)
class WeatherPoint:
    forecast_for: datetime
    air_temp_c: float | None = None
    rh_pct: float | None = None
    rain_prob: float | None = None
    rainfall_mm: float | None = None


@dataclass(slots=True)
class RiskContext:
    """Everything a model needs to make a call for one greenhouse, at ``now``."""

    org_id: str
    greenhouse_id: str
    now: datetime
    readings: list[ReadingPoint]  # ascending by time, recent window
    params: dict
    crop: str | None = None
    crop_stage: str | None = None
    crop_cycle_id: str | None = None
    forecast: list[WeatherPoint] = field(default_factory=list)
    # Free-form carry-through (e.g. last Tuta generation reset, scheduled irrigation).
    extra: dict = field(default_factory=dict)

    @property
    def latest(self) -> ReadingPoint | None:
        return self.readings[-1] if self.readings else None


@dataclass(slots=True)
class RiskResult:
    """A model's verdict. ``dedup_key`` collapses repeats of the same condition."""

    model_type: RiskModelType
    level: RiskLevel
    score: float
    title: str
    action_code: str
    message_en: str
    message_sw: str
    dedup_key: str
    window_start: datetime | None = None
    window_end: datetime | None = None
    details: dict = field(default_factory=dict)

    @property
    def is_actionable(self) -> bool:
        """Only MEDIUM+ verdicts become alerts; lower levels are logged assessments."""
        return self.level.rank >= RiskLevel.MEDIUM.rank


class RiskModel(ABC):
    """One agronomic model. Subclasses set class attrs and implement ``evaluate``.

    ``default_params`` documents and seeds the calibratable knobs; effective params
    are ``{**default_params, **config.params}`` resolved by the orchestrator.
    """

    model_type: ClassVar[RiskModelType]
    name: ClassVar[str]
    default_params: ClassVar[dict] = {}

    @abstractmethod
    def evaluate(self, ctx: RiskContext) -> RiskResult | None:
        """Return a verdict, or ``None`` when there is not enough data / no signal."""
        raise NotImplementedError

    def resolve_params(self, ctx: RiskContext) -> dict:
        return {**self.default_params, **(ctx.params or {})}


class RiskModelRegistry:
    """Self-registration so adding a model is a one-line decorator, no wiring."""

    def __init__(self) -> None:
        self._models: dict[RiskModelType, RiskModel] = {}

    def register(self, cls: type[RiskModel]) -> type[RiskModel]:
        self._models[cls.model_type] = cls()
        return cls

    def get(self, model_type: RiskModelType) -> RiskModel | None:
        return self._models.get(model_type)

    def all(self) -> list[RiskModel]:
        return list(self._models.values())

    def __len__(self) -> int:  # pragma: no cover
        return len(self._models)


registry = RiskModelRegistry()
"""Process-wide registry. Import models package to populate it."""
