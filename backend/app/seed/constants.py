"""Demo constants — the single source of truth for the seed, the simulator and the demo.

Everything the scripted hackathon story needs to *agree on* lives here: the org
slug, the Nakuru farm coordinates, the greenhouse / device / actuator uids, the
three demo users (and their shared password), and the tomato crop's per-stage NPK
targets + stage durations.

The simulator package keeps its own copies of a couple of these (``demo-coop``,
``GH1-NODE-01``) on purpose so it can run with zero backend dependencies; the
values MUST match what is defined here. See ``simulator/simulator/config.py``.
"""

from __future__ import annotations

from typing import Final

from app.db.models.common import (
    ActuatorType,
    AlertChannelType,
    CropStage,
    Language,
    PlanType,
    UserRole,
)

# ---------------------------------------------------------------------------
# Organization (tenant)
# ---------------------------------------------------------------------------
ORG_SLUG: Final[str] = "demo-coop"
ORG_NAME: Final[str] = "Demo Cooperative"
ORG_COUNTRY: Final[str] = "Kenya"
ORG_TIMEZONE: Final[str] = "Africa/Nairobi"
ORG_CONTACT_EMAIL: Final[str] = "info@demo-coop.ke"
ORG_CONTACT_PHONE: Final[str] = "+254700000000"

# ---------------------------------------------------------------------------
# Farm — near Nakuru, Kenya
# ---------------------------------------------------------------------------
FARM_NAME: Final[str] = "Nakuru Demo Farm"
FARM_COUNTY: Final[str] = "Nakuru"
FARM_LOCATION: Final[str] = "Nakuru, Kenya"
FARM_LAT: Final[float] = -0.303
FARM_LON: Final[float] = 36.080
FARM_AREA_HA: Final[float] = 1.5

# ---------------------------------------------------------------------------
# Greenhouse + devices
# ---------------------------------------------------------------------------
GREENHOUSE_NAME: Final[str] = "GH-1"
GREENHOUSE_ZONE: Final[str] = "Block A"
GREENHOUSE_STRUCTURE_TYPE: Final[str] = "tunnel"
GREENHOUSE_AREA_M2: Final[float] = 240.0

DEVICE_UID: Final[str] = "GH1-NODE-01"
DEVICE_NAME: Final[str] = "GH-1 sensor node"
DEVICE_FIRMWARE: Final[str] = "1.0.0"

VENT_ACTUATOR_NAME: Final[str] = "GH1-VENT-01"
VENT_ACTUATOR_TYPE: Final[ActuatorType] = ActuatorType.VENT
# Safety interlock defaults — keep a motor from rapid-cycling, cap open time.
VENT_ACTUATOR_CONFIG: Final[dict] = {
    "driver": "mock",
    "max_open_min": 120,
    "min_cycle_interval_s": 30,
}

# ---------------------------------------------------------------------------
# Users — password is shared across the three demo accounts.
# ---------------------------------------------------------------------------
DEMO_PASSWORD: Final[str] = "password123"


class DemoUser:
    """A lightweight record for one seeded user (kept dependency-free)."""

    __slots__ = ("email", "full_name", "role", "phone", "language", "channel")

    def __init__(
        self,
        *,
        email: str,
        full_name: str,
        role: UserRole,
        phone: str | None = None,
        language: Language = Language.EN,
        channel: AlertChannelType = AlertChannelType.WHATSAPP,
    ) -> None:
        self.email = email
        self.full_name = full_name
        self.role = role
        self.phone = phone
        self.language = language
        self.channel = channel


DEMO_USERS: Final[tuple[DemoUser, ...]] = (
    DemoUser(
        email="admin@demo-coop.ke",
        full_name="Coop Admin",
        role=UserRole.COOP_ADMIN,
        phone="+254700000002",
        language=Language.EN,
        channel=AlertChannelType.WHATSAPP,
    ),
    DemoUser(
        email="agronomist@demo-coop.ke",
        full_name="Demo Agronomist",
        role=UserRole.AGRONOMIST,
        phone="+254700000003",
        language=Language.EN,
        channel=AlertChannelType.WHATSAPP,
    ),
    DemoUser(
        email="farmer@demo-coop.ke",
        full_name="Demo Farmer",
        role=UserRole.FARMER,
        phone="+254700000001",
        language=Language.SW,
        channel=AlertChannelType.SMS,
    ),
)

# Convenient direct handles used by the demo narration.
ADMIN_EMAIL: Final[str] = "admin@demo-coop.ke"
AGRONOMIST_EMAIL: Final[str] = "agronomist@demo-coop.ke"
FARMER_EMAIL: Final[str] = "farmer@demo-coop.ke"
FARMER_PHONE: Final[str] = "+254700000001"

# ---------------------------------------------------------------------------
# Tomato crop — per-stage NPK targets (ppm) + stage durations (days).
# Kenya field placeholders, calibratable. NutrientModel reads ``npk_targets``;
# ``stage_durations_days`` drives auto stage progression of a CropCycle.
# ---------------------------------------------------------------------------
CROP_NAME: Final[str] = "tomato"
CROP_VARIETY: Final[str] = "Anna F1"

TOMATO_NPK_TARGETS: Final[dict[str, dict[str, float]]] = {
    CropStage.SEEDLING.value: {"n": 80.0, "p": 50.0, "k": 80.0},
    CropStage.VEGETATIVE.value: {"n": 150.0, "p": 60.0, "k": 150.0},
    CropStage.FLOWERING.value: {"n": 170.0, "p": 80.0, "k": 220.0},
    CropStage.FRUITING.value: {"n": 180.0, "p": 70.0, "k": 280.0},
    CropStage.RIPENING.value: {"n": 120.0, "p": 50.0, "k": 250.0},
    CropStage.HARVEST.value: {"n": 100.0, "p": 40.0, "k": 200.0},
}

TOMATO_STAGE_DURATIONS_DAYS: Final[dict[str, int]] = {
    CropStage.SEEDLING.value: 21,
    CropStage.VEGETATIVE.value: 25,
    CropStage.FLOWERING.value: 20,
    CropStage.FRUITING.value: 25,
    CropStage.RIPENING.value: 20,
    CropStage.HARVEST.value: 30,
}

# ---------------------------------------------------------------------------
# Crop cycle — planted ~45 days before "now", currently flowering.
# ---------------------------------------------------------------------------
CROP_CYCLE_PLANTED_DAYS_AGO: Final[int] = 45
CROP_CYCLE_STAGE: Final[CropStage] = CropStage.FLOWERING
# Expected harvest ~ planting + sum of stage durations.
CROP_CYCLE_TO_HARVEST_DAYS: Final[int] = sum(TOMATO_STAGE_DURATIONS_DAYS.values())

# ---------------------------------------------------------------------------
# Subscription (TRIAL) — unlocks premium/predictive features once paid.
# ---------------------------------------------------------------------------
SUBSCRIPTION_PLAN_TYPE: Final[PlanType] = PlanType.SUBSCRIPTION
SUBSCRIPTION_PLAN_NAME: Final[str] = "standard"
SUBSCRIPTION_PRICE_KES: Final[int] = 500
SUBSCRIPTION_CURRENCY: Final[str] = "KES"
SUBSCRIPTION_TRIAL_DAYS: Final[int] = 14

# ---------------------------------------------------------------------------
# Historical readings (seed) — ~36h of healthy NORMAL data at hourly cadence.
# ---------------------------------------------------------------------------
HISTORY_HOURS: Final[int] = 36
HISTORY_INTERVAL_MINUTES: Final[int] = 60

# Healthy "normal" baseline values used to synthesise history. These sit clearly
# OUTSIDE every risk threshold so a freshly-seeded greenhouse reads "all clear".
NORMAL_BASELINE: Final[dict[str, float]] = {
    "air_temp_c": 24.0,
    "rh_pct": 65.0,
    "leaf_wetness": 10.0,
    "ppfd": 600.0,
    "co2_ppm": 450.0,
    "soil_moisture_pct": 45.0,
    "soil_temp_c": 22.0,
    "npk_n_ppm": 165.0,
    "npk_p_ppm": 78.0,
    "npk_k_ppm": 215.0,
    "water_flow_l_per_min": 0.0,
    "battery_v": 3.9,
}

# ---------------------------------------------------------------------------
# Blight-conducive injection (demo) — ~12h of wet, cool evening readings.
# rh_pct >= 90 AND 16 <= air_temp_c <= 26 -> each reading is a "wet hour";
# >= 10 consecutive wet hours drives the late-blight model to HIGH.
# ---------------------------------------------------------------------------
BLIGHT_INJECT_HOURS: Final[int] = 12
BLIGHT_INJECT_INTERVAL_MINUTES: Final[int] = 60
BLIGHT_RH_PCT: Final[float] = 95.0
BLIGHT_AIR_TEMP_C: Final[float] = 18.0
BLIGHT_LEAF_WETNESS: Final[float] = 100.0
BLIGHT_CO2_PPM: Final[float] = 720.0

# After a humidity break (vents opened) RH drops below the wet-hour threshold so
# the consecutive wet-hour run is interrupted and the risk resolves.
RESOLVED_RH_PCT: Final[float] = 70.0
RESOLVED_AIR_TEMP_C: Final[float] = 24.0
RESOLVED_LEAF_WETNESS: Final[float] = 8.0

# How many post-break "dry" readings to inject so the trailing wet-run is broken.
RESOLVE_INJECT_HOURS: Final[int] = 3

__all__ = [
    "ORG_SLUG",
    "ORG_NAME",
    "ORG_COUNTRY",
    "ORG_TIMEZONE",
    "ORG_CONTACT_EMAIL",
    "ORG_CONTACT_PHONE",
    "FARM_NAME",
    "FARM_COUNTY",
    "FARM_LOCATION",
    "FARM_LAT",
    "FARM_LON",
    "FARM_AREA_HA",
    "GREENHOUSE_NAME",
    "GREENHOUSE_ZONE",
    "GREENHOUSE_STRUCTURE_TYPE",
    "GREENHOUSE_AREA_M2",
    "DEVICE_UID",
    "DEVICE_NAME",
    "DEVICE_FIRMWARE",
    "VENT_ACTUATOR_NAME",
    "VENT_ACTUATOR_TYPE",
    "VENT_ACTUATOR_CONFIG",
    "DEMO_PASSWORD",
    "DemoUser",
    "DEMO_USERS",
    "ADMIN_EMAIL",
    "AGRONOMIST_EMAIL",
    "FARMER_EMAIL",
    "FARMER_PHONE",
    "CROP_NAME",
    "CROP_VARIETY",
    "TOMATO_NPK_TARGETS",
    "TOMATO_STAGE_DURATIONS_DAYS",
    "CROP_CYCLE_PLANTED_DAYS_AGO",
    "CROP_CYCLE_STAGE",
    "CROP_CYCLE_TO_HARVEST_DAYS",
    "SUBSCRIPTION_PLAN_TYPE",
    "SUBSCRIPTION_PLAN_NAME",
    "SUBSCRIPTION_PRICE_KES",
    "SUBSCRIPTION_CURRENCY",
    "SUBSCRIPTION_TRIAL_DAYS",
    "HISTORY_HOURS",
    "HISTORY_INTERVAL_MINUTES",
    "NORMAL_BASELINE",
    "BLIGHT_INJECT_HOURS",
    "BLIGHT_INJECT_INTERVAL_MINUTES",
    "BLIGHT_RH_PCT",
    "BLIGHT_AIR_TEMP_C",
    "BLIGHT_LEAF_WETNESS",
    "BLIGHT_CO2_PPM",
    "RESOLVED_RH_PCT",
    "RESOLVED_AIR_TEMP_C",
    "RESOLVED_LEAF_WETNESS",
    "RESOLVE_INJECT_HOURS",
]
