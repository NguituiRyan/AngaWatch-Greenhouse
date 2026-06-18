"""Synchronous alert dispatcher: recipients, language, quiet-hours, channels, escalation.

``dispatch_alert`` is the workhorse. Given a ``PENDING`` (or re-dispatched) ``Alert`` it:

1. loads the linked ``Recommendation`` (preferring its EN/SW message, else a template),
2. resolves recipients = active org users, honouring ``notify_*`` prefs and
   ``preferred_channel``,
3. evaluates each user's quiet-hours in the **org timezone** (``zoneinfo``); users in
   quiet hours are suppressed for this round,
4. renders the message in each user's language,
5. sends via ``channel_registry.get(channel)`` with a console fallback when the chosen
   channel is missing/unconfigured,
6. appends one ``{channel, status, provider_id, at, error}`` entry per attempt to
   ``alert.dispatch_log`` and sets ``Alert.status`` to SENT / FAILED / SUPPRESSED,
7. bumps ``escalation_level`` when an un-acked alert is dispatched again.

Importing this module imports ``app.alerting.adapters`` so the channel registry is wired.
"""

from __future__ import annotations

from datetime import UTC, datetime, time
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from sqlalchemy import select

# Side effect: registers console / SMS / WhatsApp adapters into channel_registry.
import app.alerting.adapters  # noqa: F401
from app.alerting.base import OutgoingMessage, channel_registry
from app.alerting.templates.messages import render
from app.core.logging import get_logger
from app.db.models.common import (
    AlertChannelType,
    AlertStatus,
    Language,
)
from app.db.models.intelligence import Alert, Recommendation
from app.db.models.organization import Organization, User

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

log = get_logger("alerting.dispatcher")

_DEFAULT_TZ = "Africa/Nairobi"

# Which notify_* flag governs each non-console channel.
_CHANNEL_PREF_FLAG: dict[AlertChannelType, str] = {
    AlertChannelType.SMS: "notify_sms",
    AlertChannelType.WHATSAPP: "notify_whatsapp",
    AlertChannelType.USSD: "notify_ussd",
}


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _org_timezone(org: Organization | None) -> ZoneInfo:
    name = (org.timezone if org and org.timezone else _DEFAULT_TZ) or _DEFAULT_TZ
    try:
        return ZoneInfo(name)
    except Exception:  # pragma: no cover - bad tz string in data
        return ZoneInfo(_DEFAULT_TZ)


def _in_quiet_hours(start: time | None, end: time | None, *, local_now: datetime) -> bool:
    """Return True if ``local_now`` falls inside the [start, end) quiet window.

    Handles windows that wrap past midnight (e.g. 22:00 -> 06:00). Both bounds must be
    set for a window to apply.
    """
    if start is None or end is None:
        return False
    now_t = local_now.timetz().replace(tzinfo=None)
    now_t = time(now_t.hour, now_t.minute, now_t.second)
    if start == end:
        return False
    if start < end:
        return start <= now_t < end
    # Wraps midnight.
    return now_t >= start or now_t < end


def _channel_allowed(user: User, channel: AlertChannelType) -> bool:
    """Whether the user opted in to this channel (console is always allowed)."""
    if channel == AlertChannelType.CONSOLE:
        return True
    flag = _CHANNEL_PREF_FLAG.get(channel)
    if flag is None:
        return True
    return bool(getattr(user, flag, False))


def _resolve_channel(user: User) -> AlertChannelType:
    """Pick the user's effective channel, downgrading to console when unavailable.

    Preference order: the user's ``preferred_channel`` if opted-in and a configured
    adapter exists, else console (the always-available fallback).
    """
    preferred = user.preferred_channel
    if _channel_allowed(user, preferred):
        adapter = channel_registry.get(preferred)
        if adapter is not None and adapter.is_configured():
            return preferred
    return AlertChannelType.CONSOLE


def _user_message(rec: Recommendation | None, alert: Alert, lang: Language) -> str:
    """Prefer the recommendation's stored EN/SW text; fall back to a template."""
    if rec is not None:
        if rec.overridden and rec.override_message:
            return rec.override_message
        text = rec.message_sw if lang == Language.SW else rec.message_en
        if text:
            return text
    action_code = rec.action_code if rec is not None else "generic"
    context = {"greenhouse": str(alert.greenhouse_id), "title": alert.title}
    return render(action_code, lang, context)


def _load_recommendation(session: Session, alert: Alert) -> Recommendation | None:
    return session.scalars(
        select(Recommendation).where(Recommendation.alert_id == alert.id)
    ).first()


def _recipients(session: Session, alert: Alert) -> list[User]:
    return list(
        session.scalars(
            select(User).where(
                User.org_id == alert.org_id,
                User.is_active.is_(True),
            )
        ).all()
    )


def dispatch_alert(session: Session, alert: Alert) -> Alert:
    """Dispatch one alert to every eligible org user; return the updated ``Alert``.

    Sets ``alert.status`` to:
      * SENT       — at least one recipient received it,
      * SUPPRESSED — recipients exist but every one is in quiet hours,
      * FAILED     — all delivery attempts failed (or there were no recipients).

    Appends one dispatch-log entry per attempt and bumps ``escalation_level`` when the
    alert was previously sent and is still un-acked.
    """
    now = _now_utc()
    rec = _load_recommendation(session, alert)
    org = session.get(Organization, alert.org_id)
    tz = _org_timezone(org)
    local_now = now.astimezone(tz)

    # Escalation: a re-dispatch of an un-acked alert that already went out.
    if alert.last_sent_at is not None and alert.acked_at is None:
        alert.escalation_level += 1
        log.info(
            "alerting.escalate",
            alert_id=str(alert.id),
            escalation_level=alert.escalation_level,
        )

    recipients = _recipients(session, alert)
    log_entries: list[dict] = list(alert.dispatch_log or [])

    any_sent = False
    any_attempt = False
    any_eligible = False

    for user in recipients:
        in_quiet = _in_quiet_hours(
            user.quiet_hours_start, user.quiet_hours_end, local_now=local_now
        )
        if in_quiet:
            log_entries.append(
                {
                    "channel": "suppressed",
                    "status": "quiet_hours",
                    "provider_id": None,
                    "at": now.isoformat(),
                    "error": None,
                    "user_id": str(user.id),
                }
            )
            continue

        any_eligible = True
        channel = _resolve_channel(user)
        adapter = channel_registry.get(channel)
        if adapter is None:
            adapter = channel_registry.get(AlertChannelType.CONSOLE)
            channel = AlertChannelType.CONSOLE
        # Unconfigured non-console adapter -> console fallback.
        if adapter is not None and not adapter.is_configured():
            adapter = channel_registry.get(AlertChannelType.CONSOLE)
            channel = AlertChannelType.CONSOLE

        lang = user.preferred_language
        body = _user_message(rec, alert, lang)
        to = user.phone or user.email
        message = OutgoingMessage(
            to=to,
            body=body,
            title=alert.title,
            language=lang,
            meta={"alert_id": str(alert.id), "user_id": str(user.id)},
        )

        any_attempt = True
        if adapter is None:  # pragma: no cover - console always registered
            log_entries.append(
                {
                    "channel": channel.value,
                    "status": "no_adapter",
                    "provider_id": None,
                    "at": now.isoformat(),
                    "error": "no channel adapter available",
                    "user_id": str(user.id),
                }
            )
            continue

        result = adapter.send(message)
        any_sent = any_sent or result.ok
        log_entries.append(
            {
                "channel": result.channel.value,
                "status": result.status,
                "provider_id": result.provider_message_id,
                "at": now.isoformat(),
                "error": result.error,
                "user_id": str(user.id),
            }
        )

    alert.dispatch_log = log_entries

    if not any_eligible and recipients:
        # Everyone was in quiet hours.
        alert.status = AlertStatus.SUPPRESSED
    elif any_sent:
        alert.status = AlertStatus.SENT
        alert.last_sent_at = now
    elif any_attempt:
        alert.status = AlertStatus.FAILED
    else:
        # No recipients at all.
        alert.status = AlertStatus.FAILED

    session.add(alert)
    session.commit()
    session.refresh(alert)
    log.info(
        "alerting.dispatch",
        alert_id=str(alert.id),
        status=alert.status.value,
        recipients=len(recipients),
    )
    return alert


def dispatch_pending(session: Session) -> int:
    """Dispatch every PENDING (or ESCALATED) alert; return the count processed."""
    alerts = list(
        session.scalars(
            select(Alert).where(Alert.status.in_([AlertStatus.PENDING, AlertStatus.ESCALATED]))
        ).all()
    )
    count = 0
    for alert in alerts:
        try:
            dispatch_alert(session, alert)
            count += 1
        except Exception as exc:  # pragma: no cover - keep the loop alive
            session.rollback()
            log.warning("alerting.dispatch.error", alert_id=str(alert.id), error=str(exc))
    log.info("alerting.dispatch_pending", processed=count)
    return count
