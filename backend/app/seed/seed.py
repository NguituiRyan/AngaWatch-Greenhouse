"""Idempotent demo seed: ``python -m app.seed.seed``.

Creates (or finds, if already present) the full demo hierarchy in one **sync**
session so it can run under Celery, in a container, or against SQLite in tests:

    Organization(demo-coop)
      ├── 3 Users (admin / agronomist / farmer)
      ├── Farm (near Nakuru)
      │     └── Greenhouse GH-1
      │           ├── Device GH1-NODE-01 (sensor node)
      │           ├── ActuatorDevice GH1-VENT-01 (vent)
      │           └── CropCycle (tomato, planted ~45d ago, flowering)
      ├── Crop (tomato, per-stage NPK targets + stage durations)
      ├── Subscription (TRIAL)
      ├── RiskModelConfig defaults (via seed_risk_configs)
      └── ~36h of NORMAL hourly readings on GH1-NODE-01

Idempotency is keyed on the organization slug: if an org with ``ORG_SLUG``
already exists the seed is a no-op (it prints a summary and exits 0), so it is
safe to run on every container start / before the demo.

All public helpers take an explicit ``Session`` so tests and the demo can reuse
the exact same code path against an in-memory SQLite engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.core.config import settings
from app.core.logging import get_logger
from app.core.security import hash_password
from app.db.models import (
    ActuatorDevice,
    Crop,
    CropCycle,
    Device,
    Farm,
    Greenhouse,
    Organization,
    Reading,
    Subscription,
    User,
)
from app.db.models.common import (
    ActuatorState,
    DeviceStatus,
    DeviceType,
    SubscriptionStatus,
)
from app.risk_engine.defaults import seed_risk_configs
from app.seed import constants as C

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger("seed")


@dataclass(slots=True)
class SeedResult:
    """Handles to the key rows the seed creates, for the demo to reuse."""

    organization: Organization
    users: list[User]
    farm: Farm
    greenhouse: Greenhouse
    crop: Crop
    crop_cycle: CropCycle
    device: Device
    vent: ActuatorDevice
    subscription: Subscription
    readings_created: int
    created: bool  # False when the org already existed (idempotent skip)


# ---------------------------------------------------------------------------
# Lookups
# ---------------------------------------------------------------------------
def get_demo_org(session: Session) -> Organization | None:
    """Return the demo organization if it has already been seeded."""
    return session.scalars(select(Organization).where(Organization.slug == C.ORG_SLUG)).first()


def load_seed_handles(session: Session, org: Organization) -> SeedResult:
    """Re-build a :class:`SeedResult` from an already-seeded org (idempotent path)."""
    users = list(session.scalars(select(User).where(User.org_id == org.id)).all())
    farm = session.scalars(select(Farm).where(Farm.org_id == org.id)).first()
    greenhouse = session.scalars(
        select(Greenhouse).where(Greenhouse.name == C.GREENHOUSE_NAME, Greenhouse.org_id == org.id)
    ).first()
    crop = session.scalars(
        select(Crop).where(Crop.name == C.CROP_NAME, Crop.org_id == org.id)
    ).first()
    crop_cycle = (
        session.scalars(select(CropCycle).where(CropCycle.greenhouse_id == greenhouse.id)).first()
        if greenhouse
        else None
    )
    device = session.scalars(select(Device).where(Device.device_uid == C.DEVICE_UID)).first()
    vent = session.scalars(
        select(ActuatorDevice).where(
            ActuatorDevice.name == C.VENT_ACTUATOR_NAME, ActuatorDevice.org_id == org.id
        )
    ).first()
    subscription = session.scalars(
        select(Subscription).where(Subscription.org_id == org.id)
    ).first()
    reading_count = (
        session.query(Reading).filter(Reading.greenhouse_id == greenhouse.id).count()
        if greenhouse
        else 0
    )
    return SeedResult(
        organization=org,
        users=users,
        farm=farm,
        greenhouse=greenhouse,
        crop=crop,
        crop_cycle=crop_cycle,
        device=device,
        vent=vent,
        subscription=subscription,
        readings_created=reading_count,
        created=False,
    )


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------
def seed_demo(session: Session, *, now: datetime | None = None) -> SeedResult:
    """Idempotently seed the demo dataset; return handles to the created rows.

    If the demo org already exists this is a no-op that returns the existing
    rows (``created=False``). Otherwise it creates the whole hierarchy + history
    and commits once at the end.
    """
    now = now or datetime.now(UTC)

    existing = get_demo_org(session)
    if existing is not None:
        logger.info("seed.skip_existing", org_slug=C.ORG_SLUG, org_id=str(existing.id))
        # Risk configs are seeded idempotently too, in case an older seed predates them.
        seed_risk_configs(session, org_id=existing.id)
        return load_seed_handles(session, existing)

    org = _create_org(session)
    users = _create_users(session, org)
    farm = _create_farm(session, org)
    greenhouse = _create_greenhouse(session, org, farm)
    crop = _create_crop(session, org)
    crop_cycle = _create_crop_cycle(session, org, greenhouse, crop, now=now)
    device = _create_device(session, org, greenhouse, now=now)
    vent = _create_vent(session, org, greenhouse, device)
    subscription = _create_subscription(session, org, users, now=now)
    session.flush()

    readings_created = _create_history(session, org, greenhouse, device, now=now)

    session.commit()

    # Risk-model config defaults (global + org-scoped). Commits its own work.
    seed_risk_configs(session)
    seed_risk_configs(session, org_id=org.id)

    logger.info(
        "seed.done",
        org_id=str(org.id),
        users=len(users),
        readings=readings_created,
    )
    return SeedResult(
        organization=org,
        users=users,
        farm=farm,
        greenhouse=greenhouse,
        crop=crop,
        crop_cycle=crop_cycle,
        device=device,
        vent=vent,
        subscription=subscription,
        readings_created=readings_created,
        created=True,
    )


def _create_org(session: Session) -> Organization:
    org = Organization(
        name=C.ORG_NAME,
        slug=C.ORG_SLUG,
        country=C.ORG_COUNTRY,
        timezone=C.ORG_TIMEZONE,
        contact_email=C.ORG_CONTACT_EMAIL,
        contact_phone=C.ORG_CONTACT_PHONE,
    )
    session.add(org)
    session.flush()
    return org


def _create_users(session: Session, org: Organization) -> list[User]:
    hashed = hash_password(C.DEMO_PASSWORD)
    users: list[User] = []
    for spec in C.DEMO_USERS:
        user = User(
            org_id=org.id,
            email=spec.email,
            phone=spec.phone,
            hashed_password=hashed,
            full_name=spec.full_name,
            role=spec.role,
            is_active=True,
            preferred_language=spec.language,
            preferred_channel=spec.channel,
        )
        session.add(user)
        users.append(user)
    session.flush()
    return users


def _create_farm(session: Session, org: Organization) -> Farm:
    farm = Farm(
        org_id=org.id,
        name=C.FARM_NAME,
        county=C.FARM_COUNTY,
        location=C.FARM_LOCATION,
        latitude=C.FARM_LAT,
        longitude=C.FARM_LON,
        area_ha=C.FARM_AREA_HA,
    )
    session.add(farm)
    session.flush()
    return farm


def _create_greenhouse(session: Session, org: Organization, farm: Farm) -> Greenhouse:
    greenhouse = Greenhouse(
        org_id=org.id,
        farm_id=farm.id,
        name=C.GREENHOUSE_NAME,
        zone=C.GREENHOUSE_ZONE,
        structure_type=C.GREENHOUSE_STRUCTURE_TYPE,
        area_m2=C.GREENHOUSE_AREA_M2,
        install_date=date.today(),
    )
    session.add(greenhouse)
    session.flush()
    return greenhouse


def _create_crop(session: Session, org: Organization) -> Crop:
    crop = Crop(
        org_id=org.id,
        name=C.CROP_NAME,
        variety=C.CROP_VARIETY,
        npk_targets=C.TOMATO_NPK_TARGETS,
        stage_durations_days=C.TOMATO_STAGE_DURATIONS_DAYS,
        notes="Kenya field placeholders; calibrate per agronomist review.",
    )
    session.add(crop)
    session.flush()
    return crop


def _create_crop_cycle(
    session: Session,
    org: Organization,
    greenhouse: Greenhouse,
    crop: Crop,
    *,
    now: datetime,
) -> CropCycle:
    planting = (now - timedelta(days=C.CROP_CYCLE_PLANTED_DAYS_AGO)).date()
    harvest = planting + timedelta(days=C.CROP_CYCLE_TO_HARVEST_DAYS)
    cycle = CropCycle(
        org_id=org.id,
        greenhouse_id=greenhouse.id,
        crop_id=crop.id,
        crop_name=crop.name,
        planting_date=planting,
        expected_harvest_date=harvest,
        current_stage=C.CROP_CYCLE_STAGE,
        is_active=True,
    )
    session.add(cycle)
    session.flush()
    return cycle


def _create_device(
    session: Session, org: Organization, greenhouse: Greenhouse, *, now: datetime
) -> Device:
    device = Device(
        org_id=org.id,
        greenhouse_id=greenhouse.id,
        device_uid=C.DEVICE_UID,
        name=C.DEVICE_NAME,
        device_type=DeviceType.SENSOR_NODE,
        status=DeviceStatus.ACTIVE,
        firmware_version=C.DEVICE_FIRMWARE,
        last_seen_at=now,
        last_battery_v=C.NORMAL_BASELINE["battery_v"],
        latitude=C.FARM_LAT,
        longitude=C.FARM_LON,
    )
    session.add(device)
    session.flush()
    return device


def _create_vent(
    session: Session, org: Organization, greenhouse: Greenhouse, device: Device
) -> ActuatorDevice:
    vent = ActuatorDevice(
        org_id=org.id,
        greenhouse_id=greenhouse.id,
        device_id=device.id,
        name=C.VENT_ACTUATOR_NAME,
        actuator_type=C.VENT_ACTUATOR_TYPE,
        state=ActuatorState.CLOSED,
        is_online=True,
        # Driver from settings: "mock" (offline) or "mqtt" (real ESP relays).
        config={**C.VENT_ACTUATOR_CONFIG, "driver": settings.control_default_driver},
    )
    session.add(vent)
    session.flush()
    return vent


def _create_subscription(
    session: Session, org: Organization, users: list[User], *, now: datetime
) -> Subscription:
    admin = next((u for u in users if u.email == C.ADMIN_EMAIL), users[0] if users else None)
    sub = Subscription(
        org_id=org.id,
        user_id=admin.id if admin else None,
        plan_type=C.SUBSCRIPTION_PLAN_TYPE,
        plan_name=C.SUBSCRIPTION_PLAN_NAME,
        status=SubscriptionStatus.TRIAL,
        price=C.SUBSCRIPTION_PRICE_KES,
        currency=C.SUBSCRIPTION_CURRENCY,
        features={},
        trial_ends_at=now + timedelta(days=C.SUBSCRIPTION_TRIAL_DAYS),
    )
    session.add(sub)
    session.flush()
    return sub


def _create_history(
    session: Session,
    org: Organization,
    greenhouse: Greenhouse,
    device: Device,
    *,
    now: datetime,
) -> int:
    """Insert ~36h of healthy NORMAL hourly readings ending at ``now``.

    Values sit clearly outside every risk threshold so a freshly-seeded
    greenhouse reads "all clear". Returns the number of rows inserted.
    """
    base = C.NORMAL_BASELINE
    count = 0
    water_total = 0.0
    # Oldest first so cadence is ascending; one reading per HISTORY_INTERVAL_MINUTES.
    steps = (C.HISTORY_HOURS * 60) // C.HISTORY_INTERVAL_MINUTES
    for i in range(steps, -1, -1):
        ts = now - timedelta(minutes=i * C.HISTORY_INTERVAL_MINUTES)
        water_total += 0.0
        reading = Reading(
            device_id=device.id,
            time=ts,
            org_id=org.id,
            greenhouse_id=greenhouse.id,
            air_temp_c=base["air_temp_c"],
            rh_pct=base["rh_pct"],
            leaf_wetness=base["leaf_wetness"],
            ppfd=base["ppfd"],
            co2_ppm=base["co2_ppm"],
            soil_moisture_pct=base["soil_moisture_pct"],
            soil_temp_c=base["soil_temp_c"],
            npk_n_ppm=base["npk_n_ppm"],
            npk_p_ppm=base["npk_p_ppm"],
            npk_k_ppm=base["npk_k_ppm"],
            water_flow_l_total=water_total,
            water_flow_l_per_min=base["water_flow_l_per_min"],
            pheromone_count=2,
            battery_v=base["battery_v"],
            rssi=-65,
            ingested_at=now,
        )
        session.add(reading)
        count += 1
    return count


# ---------------------------------------------------------------------------
# Summary + CLI
# ---------------------------------------------------------------------------
def print_summary(result: SeedResult) -> None:
    """Print a human-readable summary of the seeded (or existing) dataset."""
    org = result.organization
    status = "created" if result.created else "already present (idempotent skip)"
    lines = [
        "",
        "=" * 64,
        "  AngaWatch demo seed",
        "=" * 64,
        f"  Organization : {org.name} ({org.slug})  [{status}]",
        f"  Org ID       : {org.id}",
        f"  Farm         : {result.farm.name} "
        f"(lat={result.farm.latitude}, lon={result.farm.longitude})",
        f"  Greenhouse   : {result.greenhouse.name}  id={result.greenhouse.id}",
        f"  Device       : {result.device.device_uid}",
        f"  Vent         : {result.vent.name} (state={result.vent.state.value})",
        f"  Crop cycle   : {result.crop_cycle.crop_name} "
        f"stage={result.crop_cycle.current_stage.value} "
        f"planted={result.crop_cycle.planting_date}",
        f"  Subscription : {result.subscription.plan_name} "
        f"({result.subscription.status.value})",
        f"  Readings     : {result.readings_created} on {result.device.device_uid}",
        "  Users:",
    ]
    for u in result.users:
        lines.append(
            f"    - {u.email:<26} role={u.role.value:<11} "
            f"lang={u.preferred_language.value} channel={u.preferred_channel.value}"
        )
    lines.append(f"  Password for all users: {C.DEMO_PASSWORD}")
    lines.append("=" * 64)
    print("\n".join(lines))


def main() -> int:
    """Run the seed against the configured sync database. Returns an exit code."""
    from app.db.session import get_sync_session

    session = get_sync_session()
    try:
        result = seed_demo(session)
        print_summary(result)
    except Exception as exc:  # pragma: no cover - operational guardrail
        logger.exception("seed.failed", error=str(exc))
        print(
            "\n[seed] FAILED -- is the database reachable and migrated?\n"
            f"       {type(exc).__name__}: {exc}\n"
            "       Try: docker compose up -d  &&  alembic upgrade head\n"
        )
        return 1
    finally:
        session.close()
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
