"""User notification preferences (Phase D2D).

A deliberately small preference layer over ``User.notification_prefs`` (the JSON
column reserved in D1B). It holds preferences only — never intelligence — and
fails safe: a user is opted OUT of the digest unless they have explicitly
enabled it. No migration is needed because the column already exists.

Schema (kept intentionally small):

    {
        "digest_enabled": bool,                     # master opt-in; default False
        "digest_cadence": "daily" | "weekly" | "off"  # default "daily"
    }
"""

from __future__ import annotations


CADENCE_DAILY = 'daily'
CADENCE_WEEKLY = 'weekly'
CADENCE_OFF = 'off'
VALID_CADENCES = (CADENCE_DAILY, CADENCE_WEEKLY, CADENCE_OFF)

DEFAULT_CADENCE = CADENCE_DAILY

# Day-of-week a weekly digest fires on (Monday=0, matching date.weekday()).
# Weekly cadence is honored by the daily job; no separate weekly scheduler is
# added.
WEEKLY_DIGEST_WEEKDAY = 0


def default_prefs():
    """Safe defaults: the digest is OFF until a user explicitly opts in."""
    return {'digest_enabled': False, 'digest_cadence': DEFAULT_CADENCE}


def _coerce_bool(value, fallback=False):
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ('1', 'true', 'yes', 'on')
    return fallback


def _coerce_cadence(value, fallback=DEFAULT_CADENCE):
    if isinstance(value, str) and value.strip().lower() in VALID_CADENCES:
        return value.strip().lower()
    return fallback


def normalize_prefs(raw):
    """Normalize any stored/loaded prefs into the small canonical schema."""
    prefs = default_prefs()
    if isinstance(raw, dict):
        prefs['digest_enabled'] = _coerce_bool(raw.get('digest_enabled'), False)
        prefs['digest_cadence'] = _coerce_cadence(raw.get('digest_cadence'), DEFAULT_CADENCE)
    return prefs


def get_digest_prefs(user):
    """Read a user's normalized digest preferences (safe defaults when unset)."""
    return normalize_prefs(getattr(user, 'notification_prefs', None))


def digest_opted_in(user):
    """True only when the user explicitly enabled the digest and it isn't 'off'."""
    prefs = get_digest_prefs(user)
    return bool(prefs['digest_enabled']) and prefs['digest_cadence'] != CADENCE_OFF


def cadence_due(cadence, reference_date):
    """Whether a cadence should fire on ``reference_date`` (under a daily job).

    'daily' fires every day; 'weekly' fires only on ``WEEKLY_DIGEST_WEEKDAY``;
    'off' never fires. Unknown cadences fall back to the default (daily). A null
    reference_date is treated as "due" so callers without a date still send.
    """
    cadence = _coerce_cadence(cadence)
    if cadence == CADENCE_OFF:
        return False
    if cadence == CADENCE_WEEKLY:
        if reference_date is None:
            return True
        return reference_date.weekday() == WEEKLY_DIGEST_WEEKDAY
    return True  # daily


def apply_digest_prefs(user, *, enabled=None, cadence=None):
    """Update a user's digest prefs in-place and return the normalized result.

    Only provided fields change; the rest keep their current normalized value.
    The JSON column is reassigned (not mutated in place) so SQLAlchemy flags the
    change. The caller is responsible for committing the session.
    """
    prefs = get_digest_prefs(user)
    if enabled is not None:
        prefs['digest_enabled'] = _coerce_bool(enabled, prefs['digest_enabled'])
    if cadence is not None:
        prefs['digest_cadence'] = _coerce_cadence(cadence, prefs['digest_cadence'])
    user.notification_prefs = {
        'digest_enabled': prefs['digest_enabled'],
        'digest_cadence': prefs['digest_cadence'],
    }
    return dict(user.notification_prefs)


def disable_digest(user):
    """Turn the digest fully off (used by one-click unsubscribe)."""
    return apply_digest_prefs(user, enabled=False, cadence=CADENCE_OFF)
