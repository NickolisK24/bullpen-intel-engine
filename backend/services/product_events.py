"""Canonical product event emission (Phase D2A-1).

The one place BaseballOS writes Product Intelligence facts. Everything that wants
to record "this happened" calls through here, so the event vocabulary and the
write discipline live in a single module instead of being scattered across the
isolated tracking mechanisms they replace.

Design rules (from the approved D2A-0 architecture):

  • Events are immutable facts. We only ever append — never update, never delete.
  • Current state stays derived elsewhere (``digest_deliveries``,
    ``notification_prefs``); this log never holds derived status.
  • Emission is additive and fault-isolated: recording an event must never change
    or break an existing production behavior. ``record_event`` is wrapped so a
    telemetry failure degrades to "no event recorded" — it never raises into the
    caller. The event is added to the caller's session and committed atomically
    with the state change it describes; the table is deliberately foreign-key-free
    and minimally constrained (only ``event_name`` + ``occurred_at`` are
    NOT NULL, both always set here) so an append cannot fail a caller's commit.

This module records measurement only. It never composes content, never sends
email, and never makes a send / suppress / opt-in decision.
"""

from __future__ import annotations

import logging

from models.product_event import EVENT_SCHEMA_VERSION, ProductEvent
from services.notification_prefs import CADENCE_OFF
from utils.db import db
from utils.time import utc_now_naive

logger = logging.getLogger('baseballos.product_events')


# ── Canonical event names (the D2A-1 vocabulary) ──────────────────────────────
# Only the existing digest lifecycle is canonicalized in D2A-1. In-product
# behavior (today_loaded, story_viewed, …) and the intelligence layers are
# deliberately NOT defined here yet — they belong to later D2A phases.
DIGEST_GENERATED = 'digest_generated'
DIGEST_SUPPRESSED = 'digest_suppressed'
DIGEST_SENT = 'digest_sent'
DIGEST_OPENED = 'digest_opened'
DIGEST_CLICKED = 'digest_clicked'
DIGEST_RETURNED = 'digest_returned'
DIGEST_UNSUBSCRIBED = 'digest_unsubscribed'
DIGEST_REENABLED = 'digest_reenabled'

DIGEST_LIFECYCLE_EVENTS = (
    DIGEST_GENERATED, DIGEST_SUPPRESSED, DIGEST_SENT, DIGEST_OPENED,
    DIGEST_CLICKED, DIGEST_RETURNED, DIGEST_UNSUBSCRIBED, DIGEST_REENABLED,
)

# ── Product behavior events (D2A-2) ───────────────────────────────────────────
# Owned, first-party facts about what a user does AFTER returning. Only these
# three are added in D2A-2; story_viewed / story_engaged / Understanding Session
# and the intelligence layers remain intentionally deferred.
TODAY_LOADED = 'today_loaded'
SIGNED_IN = 'signed_in'
FOLLOWED_TEAM_CHANGED = 'followed_team_changed'

PRODUCT_BEHAVIOR_EVENTS = (TODAY_LOADED, SIGNED_IN, FOLLOWED_TEAM_CHANGED)

# ── Sources (where a fact originated) ─────────────────────────────────────────
SOURCE_DIGEST_JOB = 'digest_job'
SOURCE_TRACKING_PIXEL = 'tracking_pixel'
SOURCE_CLICK_REDIRECT = 'click_redirect'
SOURCE_ONE_CLICK = 'one_click'
SOURCE_SETTINGS = 'settings'
SOURCE_SIGN_IN = 'sign_in'
# In-product action surface (e.g. team-following changes inside the app).
SOURCE_APP = 'app'

# Arrival sources for today_loaded — how the user reached the Today view. Kept to
# a small, owned allowlist; anything else normalizes to 'direct'.
SOURCE_DIGEST = 'digest'
SOURCE_DIRECT = 'direct'
SOURCE_ORGANIC = 'organic'
ARRIVAL_SOURCES = (SOURCE_DIGEST, SOURCE_DIRECT, SOURCE_ORGANIC)

# followed_team_changed actions (kept in the payload).
FOLLOW_ACTION_FOLLOW = 'follow'
FOLLOW_ACTION_UNFOLLOW = 'unfollow'
FOLLOW_ACTION_SET_PRIMARY = 'set_primary'

# Attribution source for a return (kept in the payload, not promoted to a column).
RETURN_VIA_CLICK = 'click'
RETURN_VIA_SIGN_IN = 'sign_in'

# Cap matching ProductEvent.anon_id (String(64)); pseudonymous, never PII.
ANON_ID_MAX_LEN = 64


def normalize_arrival_source(value):
    """Coerce a client-supplied arrival source to the owned allowlist."""
    if isinstance(value, str) and value.strip().lower() in ARRIVAL_SOURCES:
        return value.strip().lower()
    return SOURCE_DIRECT


def normalize_anon_id(value):
    """Coerce a client-supplied pseudonymous id to a safe, length-capped string."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:ANON_ID_MAX_LEN]


# ── Core writer ───────────────────────────────────────────────────────────────

def record_event(event_name, *, occurred_at=None, user_id=None, anon_id=None,
                 team_id=None, run_id=None, delivery_id=None, source=None,
                 payload=None):
    """Append one immutable product event to the canonical log.

    Best-effort and fault-isolated: the event is added to the current session
    (committed by the caller alongside the state change it describes), and any
    failure is swallowed so telemetry can never break a production behavior.
    Returns the pending ``ProductEvent`` (not yet committed), or ``None`` on
    failure.
    """
    try:
        event = ProductEvent(
            event_name=event_name,
            occurred_at=occurred_at or utc_now_naive(),
            schema_version=EVENT_SCHEMA_VERSION,
            user_id=user_id,
            anon_id=anon_id,
            team_id=team_id,
            run_id=run_id,
            delivery_id=delivery_id,
            source=source,
            payload=payload or None,
        )
        db.session.add(event)
        return event
    except Exception:  # pragma: no cover - telemetry must never break the caller
        logger.exception('product_events: failed to record %s', event_name)
        return None


# ── Digest lifecycle emitters (canonicalize existing production facts) ─────────

def record_digest_generated(*, user_id, team_id, run_id, reference_date,
                            digest_type, has_meaningful_change, occurred_at=None):
    """A digest payload was composed for an eligible user during a run."""
    return record_event(
        DIGEST_GENERATED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        run_id=run_id, source=SOURCE_DIGEST_JOB,
        payload={
            'reference_date': reference_date,
            'digest_type': digest_type,
            'has_meaningful_change': bool(has_meaningful_change),
        },
    )


def record_digest_sent(*, user_id, team_id, run_id, delivery_id, digest_type,
                       occurred_at=None):
    """A digest was sent to a user (recorded at the same point as the delivery)."""
    return record_event(
        DIGEST_SENT, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        run_id=run_id, delivery_id=delivery_id, source=SOURCE_DIGEST_JOB,
        payload={'digest_type': digest_type},
    )


def record_digest_suppressed(*, user_id, team_id, run_id, reason, digest_type,
                             occurred_at=None):
    """The engine suppressed a generated digest (no meaningful change, etc.)."""
    return record_event(
        DIGEST_SUPPRESSED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        run_id=run_id, source=SOURCE_DIGEST_JOB,
        payload={'reason': reason, 'digest_type': digest_type},
    )


def record_digest_opened(*, delivery_id, user_id=None, team_id=None, occurred_at=None):
    """An email open was observed via the tracking pixel (every open is a fact)."""
    return record_event(
        DIGEST_OPENED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        delivery_id=delivery_id, source=SOURCE_TRACKING_PIXEL,
    )


def record_digest_clicked(*, delivery_id, user_id=None, team_id=None, occurred_at=None):
    """A deep-link click was observed via the click redirect (every click a fact)."""
    return record_event(
        DIGEST_CLICKED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        delivery_id=delivery_id, source=SOURCE_CLICK_REDIRECT,
    )


def record_digest_returned(*, user_id, delivery_id=None, team_id=None,
                           attribution_source, source, occurred_at=None):
    """A digest-driven return was attributed to a delivery (first return only)."""
    return record_event(
        DIGEST_RETURNED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        delivery_id=delivery_id, source=source,
        payload={'attribution_source': attribution_source},
    )


# ── Opt-in transitions (unsubscribe / re-enable) ──────────────────────────────

def record_digest_unsubscribed(*, user_id, source, occurred_at=None):
    """The user turned the digest off (one-click link or settings)."""
    return record_event(
        DIGEST_UNSUBSCRIBED, occurred_at=occurred_at, user_id=user_id, source=source,
    )


def record_digest_reenabled(*, user_id, source, occurred_at=None):
    """The user turned the digest back on after having it off."""
    return record_event(
        DIGEST_REENABLED, occurred_at=occurred_at, user_id=user_id, source=source,
    )


def _opted_in(prefs):
    """Effective opt-in: enabled AND cadence not 'off' (mirrors digest_opted_in)."""
    if not isinstance(prefs, dict):
        return False
    return bool(prefs.get('digest_enabled')) and prefs.get('digest_cadence') != CADENCE_OFF


def record_digest_optin_change(user, before_prefs, after_prefs, *, source,
                               occurred_at=None):
    """Emit the unsubscribe / re-enable fact for an opt-in transition, if any.

    Compares effective opt-in before vs after. opted-in → opted-out is an
    unsubscribe; opted-out → opted-in is a re-enable. A change that does not cross
    the opt-in boundary (e.g. daily → weekly) records nothing — there is no fact.
    """
    before = _opted_in(before_prefs)
    after = _opted_in(after_prefs)
    user_id = getattr(user, 'id', None)
    if before and not after:
        return record_digest_unsubscribed(user_id=user_id, source=source, occurred_at=occurred_at)
    if after and not before:
        return record_digest_reenabled(user_id=user_id, source=source, occurred_at=occurred_at)
    return None


# ── Product behavior emitters (D2A-2) ─────────────────────────────────────────

def record_today_loaded(*, user_id=None, anon_id=None, team_id=None, source=None,
                        occurred_at=None):
    """A user successfully arrived inside BaseballOS (the Today view).

    Anonymous-safe: user_id and anon_id are both optional. The smallest useful
    payload is the columns themselves (team_id + arrival source); no body payload.
    """
    return record_event(
        TODAY_LOADED, occurred_at=occurred_at, user_id=user_id, anon_id=anon_id,
        team_id=team_id, source=source or SOURCE_DIRECT,
    )


def record_signed_in(*, user_id, anon_id=None, new_user=False, occurred_at=None):
    """A user authenticated. anon_id (when supplied) bridges pre-auth behavior to
    this user for future User Intelligence."""
    return record_event(
        SIGNED_IN, occurred_at=occurred_at, user_id=user_id, anon_id=anon_id,
        source=SOURCE_SIGN_IN, payload={'new_user': bool(new_user)},
    )


def record_followed_team_changed(*, user_id, team_id, action,
                                 prior_primary_team_id=None, primary_team_id=None,
                                 source=SOURCE_APP, occurred_at=None):
    """A user changed their team preferences (follow / unfollow / set primary).

    Observation only — it never alters following behavior. The before/after
    primary is kept in the payload to support future Team Intelligence.
    """
    return record_event(
        FOLLOWED_TEAM_CHANGED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        source=source,
        payload={
            'action': action,
            'prior_primary_team_id': prior_primary_team_id,
            'primary_team_id': primary_team_id,
        },
    )
