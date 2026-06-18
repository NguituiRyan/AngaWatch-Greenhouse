"""Africa's Talking USSD pull-menu handler.

``handle_ussd`` is a pure function over the DB: it maps the dialing ``phone`` to a
``User`` (and their org), then renders a ``CON``/``END`` menu string per the AT USSD
protocol. ``text`` is the accumulated user input, ``*``-delimited (empty on first dial).

Menu:
    1. Latest readings
    2. Current risk
    3. Alerts
    4. Subscription balance

The text is rendered in the matched user's ``preferred_language``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import desc, select

from app.core.logging import get_logger
from app.db.models.billing import Subscription
from app.db.models.common import (
    AlertStatus,
    Language,
    SubscriptionStatus,
)
from app.db.models.intelligence import Alert, RiskAssessment
from app.db.models.organization import User
from app.db.models.reading import Reading

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = get_logger("alerting.ussd")


def _t(lang: Language, en: str, sw: str) -> str:
    return sw if lang == Language.SW else en


def _user_by_phone(session: Session, phone: str) -> User | None:
    return session.scalars(
        select(User).where(User.phone == phone, User.is_active.is_(True))
    ).first()


def _latest_reading(session: Session, org_id) -> Reading | None:
    return session.scalars(
        select(Reading).where(Reading.org_id == org_id).order_by(desc(Reading.time)).limit(1)
    ).first()


def _menu_latest_readings(session: Session, user: User, lang: Language) -> str:
    r = _latest_reading(session, user.org_id)
    if r is None:
        return "END " + _t(
            lang,
            "No readings yet. Please check back later.",
            "Hakuna takwimu bado. Tafadhali angalia baadaye.",
        )
    parts = []
    if r.air_temp_c is not None:
        parts.append(_t(lang, f"Temp {r.air_temp_c:.0f}C", f"Joto {r.air_temp_c:.0f}C"))
    if r.rh_pct is not None:
        parts.append(_t(lang, f"Humidity {r.rh_pct:.0f}%", f"Unyevu %{r.rh_pct:.0f}"))
    if r.soil_moisture_pct is not None:
        parts.append(
            _t(lang, f"Soil {r.soil_moisture_pct:.0f}%", f"Udongo %{r.soil_moisture_pct:.0f}")
        )
    body = ", ".join(parts) if parts else _t(lang, "No values", "Hakuna thamani")
    header = _t(lang, "Latest readings", "Takwimu za hivi karibuni")
    return f"END {header}:\n{body}"


def _menu_current_risk(session: Session, user: User, lang: Language) -> str:
    rows = list(
        session.scalars(
            select(RiskAssessment)
            .where(RiskAssessment.org_id == user.org_id)
            .order_by(desc(RiskAssessment.evaluated_at))
            .limit(5)
        ).all()
    )
    if not rows:
        return "END " + _t(lang, "No risk data yet.", "Hakuna data ya hatari bado.")
    # Keep one (latest) per model_type.
    seen: dict[str, RiskAssessment] = {}
    for row in rows:
        seen.setdefault(row.model_type.value, row)
    lines = [f"{mt.replace('_', ' ').title()}: {ra.level.value.upper()}" for mt, ra in seen.items()]
    header = _t(lang, "Current risk", "Hatari ya sasa")
    return f"END {header}:\n" + "\n".join(lines)


def _menu_alerts(session: Session, user: User, lang: Language) -> str:
    rows = list(
        session.scalars(
            select(Alert)
            .where(
                Alert.org_id == user.org_id,
                Alert.status.notin_([AlertStatus.ACKED, AlertStatus.SUPPRESSED]),
            )
            .order_by(desc(Alert.first_seen_at))
            .limit(3)
        ).all()
    )
    if not rows:
        return "END " + _t(lang, "No open alerts. All clear.", "Hakuna tahadhari. Salama.")
    lines = [f"- {a.title} ({a.level.value.upper()})" for a in rows]
    header = _t(lang, "Open alerts", "Tahadhari zilizo wazi")
    return f"END {header}:\n" + "\n".join(lines)


def _menu_subscription(session: Session, user: User, lang: Language) -> str:
    sub = session.scalars(
        select(Subscription)
        .where(Subscription.org_id == user.org_id)
        .order_by(desc(Subscription.created_at))
        .limit(1)
    ).first()
    if sub is None:
        return "END " + _t(lang, "No subscription on file.", "Hakuna usajili uliopo.")
    unpaid = 0.0
    for inst in sub.installments:
        if not inst.paid:
            unpaid += float(inst.amount or 0)
    status_word = sub.status.value
    if lang == Language.SW:
        sw_status = {
            SubscriptionStatus.TRIAL.value: "Jaribio",
            SubscriptionStatus.ACTIVE.value: "Inatumika",
            SubscriptionStatus.PAST_DUE.value: "Imepita muda",
            SubscriptionStatus.SUSPENDED.value: "Imesimamishwa",
            SubscriptionStatus.CANCELLED.value: "Imeghairiwa",
        }
        status_word = sw_status.get(sub.status.value, sub.status.value)
    header = _t(lang, "Subscription", "Usajili")
    plan = _t(lang, f"Plan: {sub.plan_name}", f"Mpango: {sub.plan_name}")
    state = _t(lang, f"Status: {status_word}", f"Hali: {status_word}")
    balance = _t(
        lang,
        f"Balance due: {sub.currency} {unpaid:.0f}",
        f"Salio: {sub.currency} {unpaid:.0f}",
    )
    return f"END {header}:\n{plan}\n{state}\n{balance}"


def handle_ussd(session: Session, *, session_id: str, phone: str, text: str) -> str:
    """Return a ``CON ...`` (more input) or ``END ...`` (terminal) USSD response.

    ``text`` is the cumulative AT input (``*``-joined). Empty string => main menu.
    """
    user = _user_by_phone(session, phone)
    if user is None:
        log.info("alerting.ussd.unknown_phone", phone=phone, session_id=session_id)
        return (
            "END This phone number is not registered with AngaWatch. "
            "Please contact your cooperative."
        )

    lang = user.preferred_language
    choice = (text or "").strip()

    if choice == "":
        greeting = _t(lang, "AngaWatch", "AngaWatch")
        return (
            f"CON {greeting}\n"
            + _t(lang, "1. Latest readings", "1. Takwimu za hivi karibuni")
            + "\n"
            + _t(lang, "2. Current risk", "2. Hatari ya sasa")
            + "\n"
            + _t(lang, "3. Alerts", "3. Tahadhari")
            + "\n"
            + _t(lang, "4. Subscription balance", "4. Salio la usajili")
        )

    # Only the top-level selection matters for this flat menu.
    top = choice.split("*")[0]
    if top == "1":
        return _menu_latest_readings(session, user, lang)
    if top == "2":
        return _menu_current_risk(session, user, lang)
    if top == "3":
        return _menu_alerts(session, user, lang)
    if top == "4":
        return _menu_subscription(session, user, lang)

    return "END " + _t(lang, "Invalid choice.", "Chaguo si sahihi.")


__all__ = ["handle_ussd"]
