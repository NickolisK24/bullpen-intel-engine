"""Evidence-only audits for recent relief usage versus inactive roster status."""

from datetime import date, datetime, time, timedelta

from services.availability import ACTIVE_WINDOW_DAYS
from services.roster_status import INACTIVE_STATUSES


AUDIT_LEGITIMATE = 'legitimate'
AUDIT_POSSIBLE_STALE = 'possible_stale'
AUDIT_KIND = 'recent_relief_inactive_roster_status'


def _iso_or_none(value):
    return value.isoformat() if value else None


def _date_from(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None


def _datetime_from(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime.combine(value, time.min)
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        parsed = _date_from(text)
        return datetime.combine(parsed, time.min) if parsed else None


def _is_relief_log(log):
    games_started = getattr(log, 'games_started', None)
    return games_started == 0


def _latest_recent_relief_date(logs, active_cutoff):
    dates = [
        getattr(log, 'game_date', None)
        for log in (logs or [])
        if _is_relief_log(log)
        and getattr(log, 'game_date', None) is not None
        and getattr(log, 'game_date', None) >= active_cutoff
    ]
    return max(dates) if dates else None


def build_recent_inactive_roster_audit(roster_status, logs, reference_date):
    """
    Flag recent relief usage paired with an inactive roster status.

    This never changes availability. It only distinguishes current inactive
    evidence from possible stale/status contradictions for reviewers.
    """
    roster_status = roster_status or {}
    status = roster_status.get('status')
    if status not in INACTIVE_STATUSES:
        return None

    ref = reference_date or date.today()
    active_cutoff = ref - timedelta(days=ACTIVE_WINDOW_DAYS)
    latest_relief_date = _latest_recent_relief_date(logs, active_cutoff)
    if latest_relief_date is None:
        return None

    updated_at = _datetime_from(roster_status.get('updated_at'))
    updated_date = _date_from(updated_at)
    classification = AUDIT_LEGITIMATE
    reason = 'Inactive roster evidence is current with or newer than the recent relief appearance.'
    if updated_date is None or updated_date < latest_relief_date:
        classification = AUDIT_POSSIBLE_STALE
        reason = 'Inactive roster evidence predates a newer relief appearance; review for stale status evidence.'

    return {
        'kind': AUDIT_KIND,
        'classification': classification,
        'latest_relief_date': _iso_or_none(latest_relief_date),
        'roster_status_updated_at': _iso_or_none(updated_at),
        'active_cutoff_date': _iso_or_none(active_cutoff),
        'status': status,
        'label': roster_status.get('label'),
        'reason': reason,
    }


def with_recent_inactive_roster_audit(roster_status, logs, reference_date):
    payload = dict(roster_status or {})
    audit = build_recent_inactive_roster_audit(payload, logs, reference_date)
    if audit is not None:
        payload['recent_relief_audit'] = audit
    return payload
