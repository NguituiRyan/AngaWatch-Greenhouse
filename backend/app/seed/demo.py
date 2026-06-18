"""The scripted AngaWatch hackathon demo: ``python -m app.seed.demo``.

A narrated, end-to-end run of the platform's value proposition: *catch a crop
disease before it spreads, tell the farmer in their language, and act on it.*

The story (each stage prints a clear header):

  1. SEED        — ensure the demo dataset exists (idempotent).
  2. ALL CLEAR   — show the healthy baseline risk.
  3. BLIGHT DUSK — inject a wet, cool evening (~12h of rh>=90, 16-26 C).
  4. DETECT      — run the risk engine; show the HIGH late-blight assessment
                   + the bilingual (EN/SW) recommendation.
  5. ALERT       — dispatch the alert to the console (and any sandbox channel).
  6. UNLOCK      — initiate a subscription + feed a success callback so the
                   predictive features unlock (trial -> active).
  7. ACT         — enqueue + execute an "open vent" command; note the humidity
                   break the vents create.
  8. RESOLVE     — inject the post-break dry hours and re-run the engine to show
                   the risk falling back to clear.

``--direct`` (the default) runs entirely in-process against a **sync** session,
so the whole thing works offline with zero brokers. The blight injection,
evaluation and dispatch are factored into importable functions that take a
``Session`` (``inject_blight_window``, ``run_risk_evaluation``,
``dispatch_alerts`` / ``run_blight_core``) so the test suite drives the exact
same code path.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.alerting.dispatcher import dispatch_alert
from app.core.logging import get_logger
from app.db.models import (
    ActuatorDevice,
    Alert,
    Greenhouse,
    Organization,
    Reading,
    Recommendation,
    RiskAssessment,
    User,
)
from app.db.models.common import (
    AlertStatus,
    CommandSource,
    PlanType,
    RiskLevel,
    RiskModelType,
)
from app.risk_engine.engine import evaluate_greenhouse
from app.seed import constants as C
from app.seed.seed import seed_demo

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = get_logger("demo")


# ---------------------------------------------------------------------------
# Console narration helpers
# ---------------------------------------------------------------------------
def _header(num: int, title: str) -> None:
    bar = "=" * 70
    print(f"\n{bar}\n  STAGE {num}: {title}\n{bar}")


def _say(text: str = "") -> None:
    print(f"  {text}" if text else "")


# ---------------------------------------------------------------------------
# Core, importable building blocks (each takes a Session) — reused by the test.
# ---------------------------------------------------------------------------
def inject_blight_window(
    session: Session,
    greenhouse: Greenhouse,
    device_id,
    *,
    now: datetime | None = None,
    hours: int = C.BLIGHT_INJECT_HOURS,
) -> int:
    """Inject ~``hours`` of consecutive wet, cool readings ending at ``now``.

    Each reading has ``rh_pct >= 90`` and ``16 <= air_temp_c <= 26`` so it counts
    as a "wet hour"; a run of >= ``high_hours`` (default 10) drives the
    late-blight model to HIGH. Returns the number of readings inserted.
    """
    now = now or datetime.now(UTC)
    # Clear any existing (seed) readings inside the window so the trailing run is
    # a *contiguous* wet streak — otherwise dry seed rows on a different cadence
    # would interrupt the consecutive wet-hour count the blight model needs.
    window_start = now - timedelta(hours=hours)
    _clear_window(session, greenhouse.id, device_id, window_start)

    created = 0
    # Oldest first; one wet reading per hour, ending at `now`.
    for i in range(hours, -1, -1):
        ts = now - timedelta(hours=i)
        _upsert_reading(
            session,
            device_id=device_id,
            org_id=greenhouse.org_id,
            greenhouse_id=greenhouse.id,
            ts=ts,
            air_temp_c=C.BLIGHT_AIR_TEMP_C,
            rh_pct=C.BLIGHT_RH_PCT,
            leaf_wetness=C.BLIGHT_LEAF_WETNESS,
            co2_ppm=C.BLIGHT_CO2_PPM,
            now=now,
        )
        created += 1
    session.commit()
    logger.info("demo.inject_blight", readings=created, greenhouse_id=str(greenhouse.id))
    return created


def inject_humidity_break(
    session: Session,
    greenhouse: Greenhouse,
    device_id,
    *,
    now: datetime | None = None,
    hours: int = C.RESOLVE_INJECT_HOURS,
) -> int:
    """Inject post-vent "dry" readings that break the trailing wet-hour run.

    With vents open the canopy dries out: ``rh_pct`` drops below the wet-hour
    threshold, so the most recent readings are no longer wet and the consecutive
    wet-run that drove the HIGH verdict is interrupted.
    """
    now = now or datetime.now(UTC)
    # Clear the trailing window so the freshly injected dry readings are what the
    # model sees at the recent edge (interrupting the wet run cleanly).
    window_start = now - timedelta(hours=hours)
    _clear_window(session, greenhouse.id, device_id, window_start)

    created = 0
    for i in range(hours, -1, -1):
        ts = now - timedelta(hours=i)
        _upsert_reading(
            session,
            device_id=device_id,
            org_id=greenhouse.org_id,
            greenhouse_id=greenhouse.id,
            ts=ts,
            air_temp_c=C.RESOLVED_AIR_TEMP_C,
            rh_pct=C.RESOLVED_RH_PCT,
            leaf_wetness=C.RESOLVED_LEAF_WETNESS,
            co2_ppm=C.NORMAL_BASELINE["co2_ppm"],
            now=now,
        )
        created += 1
    session.commit()
    logger.info("demo.inject_break", readings=created, greenhouse_id=str(greenhouse.id))
    return created


def _clear_window(session: Session, greenhouse_id, device_id, window_start: datetime) -> int:
    """Delete readings for the device at/after ``window_start`` (tz-safe).

    SQLite stores naive datetimes and Postgres stores aware ones, so we load the
    candidate rows and compare in Python after normalising both sides to UTC —
    that keeps the demo working identically on either backend. Returns the count
    of rows removed.
    """
    rows = session.scalars(
        select(Reading)
        .where(Reading.greenhouse_id == greenhouse_id)
        .where(Reading.device_id == device_id)
    ).all()
    start = _as_utc(window_start)
    removed = 0
    for r in rows:
        if _as_utc(r.time) >= start:
            session.delete(r)
            removed += 1
    session.flush()
    return removed


def _as_utc(dt: datetime) -> datetime:
    """Return ``dt`` as an aware UTC datetime (naive values are assumed UTC)."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _upsert_reading(
    session: Session,
    *,
    device_id,
    org_id,
    greenhouse_id,
    ts: datetime,
    air_temp_c: float,
    rh_pct: float,
    leaf_wetness: float,
    co2_ppm: float,
    now: datetime,
) -> None:
    """Insert (or overwrite, by PK) one reading at ``ts``.

    Readings have a composite PK ``(device_id, time)``; the demo deliberately
    overwrites any history row at the same timestamp so the injected wet window
    is what the engine sees.
    """
    existing = session.get(Reading, (device_id, ts))
    base = C.NORMAL_BASELINE
    if existing is not None:
        existing.air_temp_c = air_temp_c
        existing.rh_pct = rh_pct
        existing.leaf_wetness = leaf_wetness
        existing.co2_ppm = co2_ppm
        existing.ingested_at = now
        return
    session.add(
        Reading(
            device_id=device_id,
            time=ts,
            org_id=org_id,
            greenhouse_id=greenhouse_id,
            air_temp_c=air_temp_c,
            rh_pct=rh_pct,
            leaf_wetness=leaf_wetness,
            ppfd=0.0,
            co2_ppm=co2_ppm,
            soil_moisture_pct=base["soil_moisture_pct"],
            soil_temp_c=base["soil_temp_c"],
            npk_n_ppm=base["npk_n_ppm"],
            npk_p_ppm=base["npk_p_ppm"],
            npk_k_ppm=base["npk_k_ppm"],
            water_flow_l_total=0.0,
            water_flow_l_per_min=0.0,
            pheromone_count=2,
            battery_v=base["battery_v"],
            rssi=-66,
            ingested_at=now,
        )
    )


def run_risk_evaluation(
    session: Session, greenhouse_id, *, now: datetime | None = None
) -> list[RiskAssessment]:
    """Run every enabled risk model for one greenhouse; persist + return results."""
    return evaluate_greenhouse(session, greenhouse_id, now=now)


def find_blight_assessment(
    assessments: list[RiskAssessment],
) -> RiskAssessment | None:
    """Pick the late-blight assessment out of a list of model results."""
    for a in assessments:
        if a.model_type == RiskModelType.LATE_BLIGHT:
            return a
    return None


def dispatch_pending_blight_alerts(session: Session, greenhouse_id) -> list[Alert]:
    """Dispatch all PENDING late-blight alerts for the greenhouse; return them."""
    alerts = list(
        session.scalars(
            select(Alert)
            .where(Alert.greenhouse_id == greenhouse_id)
            .where(Alert.model_type == RiskModelType.LATE_BLIGHT)
            .where(Alert.status.in_([AlertStatus.PENDING, AlertStatus.ESCALATED]))
        ).all()
    )
    dispatched: list[Alert] = []
    for alert in alerts:
        dispatched.append(dispatch_alert(session, alert))
    return dispatched


@dataclass(slots=True)
class BlightCoreResult:
    """What :func:`run_blight_core` produced — the test asserts on these."""

    assessments: list[RiskAssessment]
    blight: RiskAssessment | None
    alerts: list[Alert]


def run_blight_core(
    session: Session,
    greenhouse: Greenhouse,
    device_id,
    *,
    now: datetime | None = None,
) -> BlightCoreResult:
    """Inject the blight window, evaluate, and dispatch — the testable core.

    This is the heart of the demo with no narration or async billing/control: a
    single function the test calls to assert a HIGH blight ``RiskAssessment`` and
    an ``Alert`` row are produced.
    """
    now = now or datetime.now(UTC)
    inject_blight_window(session, greenhouse, device_id, now=now)
    assessments = run_risk_evaluation(session, greenhouse.id, now=now)
    blight = find_blight_assessment(assessments)
    alerts = dispatch_pending_blight_alerts(session, greenhouse.id)
    return BlightCoreResult(assessments=assessments, blight=blight, alerts=alerts)


# ---------------------------------------------------------------------------
# Async billing + control steps (the real seams are async).
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class UnlockResult:
    """Outcome of the subscription unlock step (for narration)."""

    status_before: str
    status_after: str
    feature_before: bool
    feature_after: bool
    receipt: str | None


async def _unlock_subscription_async(org_id, user_id) -> UnlockResult:
    """Initiate a subscription + feed a mock success callback; report the transition.

    Uses the API's async session against the configured database. The mock
    M-Pesa provider synthesises a checkout id and echoes a success callback, so
    the trial -> active activation runs offline. The free trial already grants
    premium features, so the headline change here is the subscription *status*
    advancing ``trial -> active`` (which keeps the features unlocked past the
    trial window).
    """
    from app.billing.service import (
        handle_stk_callback,
        initiate_subscription,
        org_has_feature,
    )
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        feature_before = await org_has_feature(db, org_id, "predictive_alerts")
        sub, payment, _stk = await initiate_subscription(
            db,
            org_id=org_id,
            user_id=user_id,
            plan_type=PlanType.SUBSCRIPTION,
            phone=C.FARMER_PHONE,
            amount=C.SUBSCRIPTION_PRICE_KES,
            plan_name=C.SUBSCRIPTION_PLAN_NAME,
        )
        status_before = sub.status.value
        # Simulate Daraja POSTing a success callback for our checkout request.
        callback = _mock_success_callback(payment.checkout_request_id, payment.amount)
        paid = await handle_stk_callback(db, callback)
        await db.refresh(sub)
        feature_after = await org_has_feature(db, org_id, "predictive_alerts")
        return UnlockResult(
            status_before=status_before,
            status_after=sub.status.value,
            feature_before=feature_before,
            feature_after=feature_after,
            receipt=paid.mpesa_receipt,
        )


async def _act_open_vent_async(org_id, vent_id, issued_by) -> str:
    """Enqueue + execute an 'open' command on the vent; return the actuator state."""
    from app.control.service import enqueue_command, execute_command
    from app.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        cmd = await enqueue_command(
            db,
            org_id=org_id,
            actuator_device_id=vent_id,
            command="open",
            source=CommandSource.AUTO,
            issued_by=issued_by,
            params={"reason": "late_blight_humidity_break"},
        )
        cmd = await execute_command(db, cmd.id)
        actuator = await db.get(ActuatorDevice, vent_id)
        state = actuator.state.value if actuator else "unknown"
        return f"{cmd.status.value}/{state}"


def _mock_success_callback(checkout_request_id: str | None, amount) -> dict:
    """Build a Daraja-style success ``stkCallback`` envelope for the mock provider."""
    return {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "demo-merchant",
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": 0,
                "ResultDesc": "The service request is processed successfully.",
                "CallbackMetadata": {
                    "Item": [
                        {"Name": "Amount", "Value": float(amount or C.SUBSCRIPTION_PRICE_KES)},
                        {"Name": "MpesaReceiptNumber", "Value": "DEMO12345"},
                        {"Name": "PhoneNumber", "Value": C.FARMER_PHONE.lstrip("+")},
                    ]
                },
            }
        }
    }


# ---------------------------------------------------------------------------
# The narrated script (direct mode).
# ---------------------------------------------------------------------------
def run_direct_demo(session: Session, *, now: datetime | None = None) -> int:
    """Run the full narrated demo in-process. Returns an exit code (0 = ok)."""
    now = now or datetime.now(UTC)

    # ---- Stage 1: SEED ----
    _header(1, "SEED - ensure the demo cooperative exists")
    result = seed_demo(session, now=now)
    org = result.organization
    greenhouse = result.greenhouse
    device = result.device
    vent = result.vent
    _say(f"Org '{org.slug}' {'created' if result.created else 'already present'}.")
    _say(
        f"Greenhouse {greenhouse.name} growing {result.crop_cycle.crop_name} "
        f"({result.crop_cycle.current_stage.value})."
    )
    _say(f"{result.readings_created} historical readings on {device.device_uid}.")

    # ---- Stage 2: ALL CLEAR ----
    _header(2, "ALL CLEAR - the healthy baseline")
    baseline = run_risk_evaluation(session, greenhouse.id, now=now)
    _summarise_assessments(baseline, label="baseline")
    _say("No actionable risk: free-tier farmers see live readings + instant alerts.")

    # ---- Stage 3: BLIGHT DUSK ----
    _header(3, "BLIGHT DUSK - a wet, cool evening rolls in")
    n = inject_blight_window(session, greenhouse, device.id, now=now)
    _say(
        f"Injected {n} hourly readings with RH>={C.BLIGHT_RH_PCT:.0f}% and "
        f"air temp ~{C.BLIGHT_AIR_TEMP_C:.0f} C (the late-blight band)."
    )
    _say("Leaves are wet and cool overnight - exactly how Phytophthora infestans spreads.")

    # ---- Stage 4: DETECT ----
    _header(4, "DETECT - the predictive risk engine fires")
    assessments = run_risk_evaluation(session, greenhouse.id, now=now)
    blight = find_blight_assessment(assessments)
    if blight is None:
        _say("ERROR: expected a late-blight assessment but none was produced.")
        return 1
    _say(f"Late blight: {blight.level.value.upper()}  (score={blight.score})")
    wet = blight.details.get("effective_wet_hours") or blight.details.get("wet_hours")
    _say(f"Evidence: {wet} consecutive wet hours observed.")
    rec = _load_recommendation_for(session, blight)
    if rec is not None:
        _say("")
        _say("Recommendation (EN): " + rec.message_en)
        _say("Pendekezo (SW):      " + rec.message_sw)

    # ---- Stage 5: ALERT ----
    _header(5, "ALERT - notify every farmer in their language")
    alerts = dispatch_pending_blight_alerts(session, greenhouse.id)
    if not alerts:
        _say("No new alert dispatched (it may already be within its cooldown window).")
    for alert in alerts:
        _say(
            f"Alert '{alert.title}' -> status={alert.status.value}, "
            f"{len(alert.dispatch_log)} delivery log entries."
        )
    _say("Console channel is always on; SMS/WhatsApp fall back to console when unconfigured.")

    # ---- Stage 6: UNLOCK ----
    _header(6, "UNLOCK - pay-as-you-grow predictive features (M-Pesa)")
    admin = _user_by_email(result.users, C.ADMIN_EMAIL)
    try:
        unlock = asyncio.run(_unlock_subscription_async(org.id, admin.id if admin else None))
        _say(
            f"Subscription status before payment: {unlock.status_before}  "
            f"(trial already grants predictive features: "
            f"{'yes' if unlock.feature_before else 'no'})."
        )
        _say(
            "Initiated STK push (mock) and received a SUCCESS callback "
            f"(receipt {unlock.receipt})."
        )
        _say(
            f"Subscription status after payment:  {unlock.status_after}  "
            f"(predictive features stay unlocked: "
            f"{'yes' if unlock.feature_after else 'no'})."
        )
    except Exception as exc:  # pragma: no cover - async DB may be unreachable in --direct
        _say(f"(Billing step skipped: {type(exc).__name__}: {exc})")

    # ---- Stage 7: ACT ----
    _header(7, "ACT - open the vents to break the humidity")
    try:
        outcome = asyncio.run(_act_open_vent_async(org.id, vent.id, admin.id if admin else None))
        _say(f"Vent command result (status/state): {outcome}")
        _say(
            "Opening the vents exchanges the saturated air - RH drops, "
            "the canopy dries, the wet-hour run is broken."
        )
    except Exception as exc:  # pragma: no cover - async DB may be unreachable in --direct
        _say(f"(Control step skipped: {type(exc).__name__}: {exc})")

    # ---- Stage 8: RESOLVE ----
    _header(8, "RESOLVE - the risk clears")
    m = inject_humidity_break(session, greenhouse, device.id, now=now)
    _say(
        f"Injected {m} post-break readings with RH~{C.RESOLVED_RH_PCT:.0f}% "
        "(below the wet-hour threshold)."
    )
    final = run_risk_evaluation(session, greenhouse.id, now=now)
    final_blight = find_blight_assessment(final)
    final_level = final_blight.level if final_blight is not None else RiskLevel.NONE
    _say(f"Late blight now: {final_level.value.upper()} " f"(was {blight.level.value.upper()}).")
    if final_level.rank < blight.level.rank:
        _say("Risk resolved: the vents broke the wet window. The crop is saved.")
    else:
        _say("Still elevated - keep ventilating and apply preventive spray tonight.")
    _say("")
    _say("End of demo. This is the AngaWatch loop: detect -> advise -> act -> resolve.")
    return 0


# ---------------------------------------------------------------------------
# Small read helpers
# ---------------------------------------------------------------------------
def _summarise_assessments(assessments: list[RiskAssessment], *, label: str) -> None:
    if not assessments:
        _say(f"No assessments produced for the {label}.")
        return
    for a in assessments:
        marker = "!!" if a.level.rank >= RiskLevel.MEDIUM.rank else "  "
        _say(f"{marker} {a.model_type.value:<16} {a.level.value:<8} score={a.score}")


def _load_recommendation_for(session: Session, assessment: RiskAssessment) -> Recommendation | None:
    return session.scalars(
        select(Recommendation).where(Recommendation.risk_assessment_id == assessment.id).limit(1)
    ).first()


def _user_by_email(users: list[User], email: str) -> User | None:
    return next((u for u in users if u.email == email), None)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _force_utf8_stdout() -> None:
    """Best-effort: render the bilingual (EN/SW) narration cleanly on any console."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Returns a process exit code."""
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(description="AngaWatch scripted demo.")
    parser.add_argument(
        "--direct",
        action="store_true",
        default=True,
        help="Run the demo in-process against the sync DB (default).",
    )
    parser.parse_args(argv)

    from app.db.session import get_sync_session

    try:
        session = get_sync_session()
    except Exception as exc:  # pragma: no cover - bad config
        print(f"\n[demo] Could not open a DB session: {exc}\n")
        return 1

    try:
        # Probe the connection early so we can print a friendly message.
        session.execute(select(Organization).limit(1))
    except Exception as exc:  # pragma: no cover - DB unreachable
        print(
            "\n[demo] The database is not reachable.\n"
            f"       {type(exc).__name__}: {exc}\n"
            "       Start the stack first:  docker compose up -d\n"
            "       Then migrate + seed:    alembic upgrade head && python -m app.seed.seed\n"
        )
        session.close()
        return 1

    try:
        return run_direct_demo(session)
    except Exception as exc:  # pragma: no cover - operational guardrail
        logger.exception("demo.failed", error=str(exc))
        print(f"\n[demo] FAILED: {type(exc).__name__}: {exc}\n")
        return 1
    finally:
        session.close()


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main())
