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
import re

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

# ── Product understanding observation (D2A-3) ─────────────────────────────────
# A pure observation: a BaseballOS story was successfully presented to the user.
# It records ONLY the presentation fact — never engagement, understanding, or
# completion. Future phases will define what understanding means FROM this data;
# this phase only collects it.
#
# History note (V3-1): through V2, story_viewed was emitted on RENDER — when a
# story card mounted, whether or not it ever appeared on screen. From V3-1 the
# in-product surfaces no longer emit story_viewed on render; the honest
# on-screen-presentation fact is story_impression (below). story_viewed is
# reserved for a future, meaningful-consumption trigger. Its name, endpoint, and
# historical rows are preserved unchanged.
STORY_VIEWED = 'story_viewed'

# ── Story impression observation (V3-1) ───────────────────────────────────────
# A story card actually appeared on screen (viewport ≈ 50%+ visible), as opposed
# to merely being rendered into the DOM. The honest successor to the old
# render-fired story_viewed volume: a presentation fact only — WHICH story
# appeared, for WHICH team, on WHICH surface, and to WHOM — inferring nothing
# about engagement, dwell, reading, or understanding. (Viewport visibility is
# used only as a client-side trigger; no viewport / scroll / coordinate / dwell
# data is ever sent or stored — the payload is the same minimal presentation
# fact as story_viewed.)
STORY_IMPRESSION = 'story_impression'

PRODUCT_OBSERVATION_EVENTS = (STORY_VIEWED, STORY_IMPRESSION)

# ── Story team-board open (V3-2) ──────────────────────────────────────────────
# The reader followed a story's primary CTA into the Team Board — the high-intent
# story → team-board conversion. It is the explicit successor to the generic
# story_interacted(select) the Stories feed used to emit; that legacy event is no
# longer emitted for Team Board opens. Fires once per physical click (NOT deduped
# per session — each open is a distinct intent signal). Grouped under the
# interaction events below.
STORY_TEAM_BOARD_OPENED = 'story_team_board_opened'

# ── Story share click (V3-3) ──────────────────────────────────────────────────
# The reader activated the Share control from a story context. Fired on click/tap
# INTENT — never on native-share / clipboard success, which cannot be reliably
# interpreted. Fires once per physical click (NOT deduped). Honest about scope:
# today's Share shares the TEAM page, not a unique story URL, so the payload
# carries share_target='team' alongside the story descriptors. Grouped under the
# interaction events below.
STORY_SHARE_CLICKED = 'story_share_clicked'

# Story-event names accepted by the owned generic /story-event ingestion
# endpoint. A small owned allowlist; an unrecognized name records nothing
# (best-effort, never fabricated). Extended per V3 phase as new story behaviors
# are defined (V3-1: story_impression; V3-2: + story_team_board_opened;
# V3-3: + story_share_clicked).
STORY_EVENT_NAMES = (STORY_IMPRESSION, STORY_TEAM_BOARD_OPENED, STORY_SHARE_CLICKED)

# ── Product interaction observation (D2A-7) ───────────────────────────────────
# A user intentionally performed an explicit interaction with a rendered story
# (e.g. selecting/opening/expanding it via existing UI). It records ONLY that the
# interaction occurred — never engagement, interest, completion, or understanding.
STORY_INTERACTED = 'story_interacted'

PRODUCT_INTERACTION_EVENTS = (STORY_INTERACTED, STORY_TEAM_BOARD_OPENED, STORY_SHARE_CLICKED)

# ── V4 product-loop analytics (V4.0) ──────────────────────────────────────────
# Owned, first-party observations for the existing V4-relevant surfaces/actions.
# These events measure route views and explicit intent signals only. They never
# influence baseball reads, scoring, thresholds, freshness, or user-facing claims.
APP_VIEWED = 'app_viewed'
HOMEPAGE_VIEWED = 'homepage_viewed'
BULLPEN_BOARD_VIEWED = 'bullpen_board_viewed'
TEAM_SURFACE_VIEWED = 'team_surface_viewed'
PITCHER_SURFACE_VIEWED = 'pitcher_surface_viewed'
METHODOLOGY_VIEWED = 'methodology_viewed'
TRUST_SURFACE_VIEWED = 'trust_surface_viewed'
FRESHNESS_SURFACE_VIEWED = 'freshness_surface_viewed'
SOCIAL_OUTBOUND_CLICKED = 'social_outbound_clicked'
NEWSLETTER_INTEREST_CLICKED = 'newsletter_interest_clicked'
TEAM_INTEREST_CLICKED = 'team_interest_clicked'
SHARE_INTENT_CLICKED = 'share_intent_clicked'

V4_PRODUCT_EVENTS = (
    APP_VIEWED, HOMEPAGE_VIEWED, BULLPEN_BOARD_VIEWED, TEAM_SURFACE_VIEWED,
    PITCHER_SURFACE_VIEWED, METHODOLOGY_VIEWED, TRUST_SURFACE_VIEWED,
    FRESHNESS_SURFACE_VIEWED, SOCIAL_OUTBOUND_CLICKED, NEWSLETTER_INTEREST_CLICKED,
    TEAM_INTEREST_CLICKED, SHARE_INTENT_CLICKED,
)

# Reserved by the V4 roadmap/catalog but intentionally not accepted until the
# corresponding product surfaces exist.
V4_RESERVED_EVENT_NAMES = (
    'feedback_intent_clicked',
    'team_follow_started',
    'team_follow_completed',
    'daily_home_viewed',
    'what_changed_viewed',
    'team_page_viewed',
    'share_card_clicked',
    'share_card_downloaded',
    'digest_signup_started',
    'digest_signup_completed',
    'correction_submitted',
    'pro_waitlist_started',
    'pro_waitlist_completed',
)

# ── Digest deliverability (D2A-7, provider-backed) ────────────────────────────
# Facts reported by the email provider (Resend) about a sent digest's fate. They
# never change digest behavior or existing metrics; they only observe delivery.
DIGEST_DELIVERED = 'digest_delivered'
DIGEST_BOUNCED = 'digest_bounced'
DIGEST_COMPLAINT = 'digest_complaint'

DIGEST_DELIVERABILITY_EVENTS = (DIGEST_DELIVERED, DIGEST_BOUNCED, DIGEST_COMPLAINT)

# The full canonical vocabulary, used by the operator heartbeat so every event
# type (including ones not yet seen) is enumerable.
CANONICAL_PRODUCT_EVENTS = (
    DIGEST_LIFECYCLE_EVENTS
    + DIGEST_DELIVERABILITY_EVENTS
    + PRODUCT_BEHAVIOR_EVENTS
    + PRODUCT_OBSERVATION_EVENTS
    + PRODUCT_INTERACTION_EVENTS
    + V4_PRODUCT_EVENTS
)

# ── Sources (where a fact originated) ─────────────────────────────────────────
SOURCE_DIGEST_JOB = 'digest_job'
SOURCE_TRACKING_PIXEL = 'tracking_pixel'
SOURCE_CLICK_REDIRECT = 'click_redirect'
SOURCE_ONE_CLICK = 'one_click'
SOURCE_SETTINGS = 'settings'
SOURCE_SIGN_IN = 'sign_in'
# In-product action surface (e.g. team-following changes inside the app).
SOURCE_APP = 'app'
# Origin for provider-reported deliverability facts (Resend webhook).
SOURCE_EMAIL_PROVIDER = 'email_provider'

# Arrival sources for today_loaded — how the user reached the Today view. Kept to
# a small, owned allowlist; anything else normalizes to 'direct'.
SOURCE_DIGEST = 'digest'
SOURCE_DIRECT = 'direct'
SOURCE_ORGANIC = 'organic'
ARRIVAL_SOURCES = (SOURCE_DIGEST, SOURCE_DIRECT, SOURCE_ORGANIC)

# Surfaces a story can be presented on (stored in the event's source column).
# A small owned allowlist; anything unrecognized is recorded as None (unknown)
# rather than fabricated.
STORY_SURFACE_HOME = 'home'
STORY_SURFACE_STORIES = 'stories'
STORY_SURFACE_DIGEST_WEB = 'digest_web'
STORY_SURFACES = (STORY_SURFACE_HOME, STORY_SURFACE_STORIES, STORY_SURFACE_DIGEST_WEB)

# followed_team_changed actions (kept in the payload).
FOLLOW_ACTION_FOLLOW = 'follow'
FOLLOW_ACTION_UNFOLLOW = 'unfollow'
FOLLOW_ACTION_SET_PRIMARY = 'set_primary'

# story_interacted interaction kinds (the observable UI action; kept in payload).
# A small owned allowlist; anything unrecognized is recorded as None rather than
# fabricated. These name the action only — they assert nothing about engagement.
STORY_INTERACTION_EXPAND = 'expand'
STORY_INTERACTION_OPEN = 'open'
STORY_INTERACTION_SELECT = 'select'
STORY_INTERACTIONS = (STORY_INTERACTION_EXPAND, STORY_INTERACTION_OPEN, STORY_INTERACTION_SELECT)

# story_share_clicked share targets (kept in the payload). Today the Share control
# shares the team page, so the only owned value is 'team'; anything else records as
# None rather than fabricated. Names the share destination scope — it asserts
# nothing about whether the native share / copy actually completed.
SHARE_TARGET_TEAM = 'team'
SHARE_TARGETS = (SHARE_TARGET_TEAM,)

# Attribution source for a return (kept in the payload, not promoted to a column).
RETURN_VIA_CLICK = 'click'
RETURN_VIA_SIGN_IN = 'sign_in'

# Cap matching ProductEvent.anon_id (String(64)); pseudonymous, never PII.
ANON_ID_MAX_LEN = 64
# Caps for client-supplied story descriptors (story id like "<team_id>:<date>",
# and the existing canonical story_type). Bounded so a client cannot bloat a row.
STORY_FIELD_MAX_LEN = 64
V4_EVENT_PROPERTY_MAX_LEN = 64
V4_ROUTE_MAX_LEN = 128
V4_SOURCE_MAX_LEN = 32
TEAM_ABBREV_MAX_LEN = 5
_SAFE_SLUG_RE = re.compile(r'^[a-z0-9][a-z0-9_.:-]*$')
_SAFE_FRESHNESS_RE = re.compile(r'^[a-z0-9][a-z0-9_.:-]*$')
_SAFE_TEAM_ABBREV_RE = re.compile(r'^[A-Z0-9]{2,5}$')


def normalize_arrival_source(value):
    """Coerce a client-supplied arrival source to the owned allowlist."""
    if isinstance(value, str) and value.strip().lower() in ARRIVAL_SOURCES:
        return value.strip().lower()
    return SOURCE_DIRECT


def normalize_story_surface(value):
    """Coerce a client-supplied story surface to the owned allowlist, else None."""
    if isinstance(value, str) and value.strip().lower() in STORY_SURFACES:
        return value.strip().lower()
    return None


def normalize_story_interaction(value):
    """Coerce a client-supplied interaction kind to the owned allowlist, else None."""
    if isinstance(value, str) and value.strip().lower() in STORY_INTERACTIONS:
        return value.strip().lower()
    return None


def normalize_story_event_name(value):
    """Coerce a client-supplied story-event name to the owned allowlist, else None."""
    if isinstance(value, str) and value.strip().lower() in STORY_EVENT_NAMES:
        return value.strip().lower()
    return None


def normalize_share_target(value):
    """Coerce a client-supplied share target to the owned allowlist, else None."""
    if isinstance(value, str) and value.strip().lower() in SHARE_TARGETS:
        return value.strip().lower()
    return None


def normalize_v4_event_name(value):
    """Coerce a client-supplied V4 event name to the owned allowlist, else None."""
    if isinstance(value, str) and value.strip().lower() in V4_PRODUCT_EVENTS:
        return value.strip().lower()
    return None


def _looks_like_pii(value):
    return '@' in value or '\n' in value or '\r' in value


def normalize_v4_slug(value, *, max_len=V4_EVENT_PROPERTY_MAX_LEN):
    """Coerce a client-supplied event descriptor to a small safe slug or None."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()[:max_len]
    if not cleaned or _looks_like_pii(cleaned):
        return None
    if not _SAFE_SLUG_RE.match(cleaned):
        return None
    return cleaned


def normalize_v4_source(value):
    """Normalize where a V4 observation originated (footer, cta, card, etc.)."""
    return normalize_v4_slug(value, max_len=V4_SOURCE_MAX_LEN)


def normalize_v4_surface(value):
    """Normalize the product surface that emitted a V4 observation."""
    return normalize_v4_slug(value, max_len=V4_EVENT_PROPERTY_MAX_LEN)


def normalize_v4_route(value):
    """Normalize a route path without query strings, fragments, or PII."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().split('?', 1)[0].split('#', 1)[0][:V4_ROUTE_MAX_LEN]
    if not cleaned.startswith('/') or _looks_like_pii(cleaned):
        return None
    if any(ch.isspace() for ch in cleaned):
        return None
    return cleaned


def normalize_v4_team_abbrev(value):
    """Normalize an already-visible public team abbreviation."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().upper()[:TEAM_ABBREV_MAX_LEN]
    if _SAFE_TEAM_ABBREV_RE.match(cleaned):
        return cleaned
    return None


def normalize_v4_player_id(value):
    """Normalize an already-visible public player id. Free-form names are dropped."""
    if value is None or isinstance(value, bool):
        return None
    try:
        player_id = int(value)
    except (TypeError, ValueError):
        return None
    if player_id <= 0 or player_id >= 10**12:
        return None
    return player_id


def normalize_v4_freshness_state(value):
    """Normalize a safe freshness-state slug already present in the data contract."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()[:V4_EVENT_PROPERTY_MAX_LEN]
    if not cleaned or _looks_like_pii(cleaned):
        return None
    if not _SAFE_FRESHNESS_RE.match(cleaned):
        return None
    return cleaned


def normalize_short_text(value, *, max_len=STORY_FIELD_MAX_LEN):
    """Coerce a client-supplied descriptor to a safe, length-capped string or None."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    return cleaned[:max_len]


def normalize_anon_id(value):
    """Coerce a client-supplied pseudonymous id to a safe, length-capped string."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned or _looks_like_pii(cleaned):
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


# ── Product understanding observation emitter (D2A-3) ──────────────────────────

def record_story_viewed(*, user_id=None, anon_id=None, team_id=None, story_id=None,
                        story_type=None, surface=None, occurred_at=None):
    """A BaseballOS story was successfully presented to the user.

    Observation only: it records WHICH story (story_id + the existing canonical
    story_type), for WHICH team, on WHICH surface, and to WHOM (user and/or
    anon_id). It deliberately records nothing about engagement, dwell, scroll, or
    completion — those are not facts this phase can trustworthily observe. The
    surface is stored in the event's source column; story descriptors live in the
    payload.
    """
    return record_event(
        STORY_VIEWED, occurred_at=occurred_at, user_id=user_id, anon_id=anon_id,
        team_id=team_id, source=surface,
        payload={'story_id': story_id, 'story_type': story_type},
    )


# ── Story observation emitter (V3-1, generic owned story-event seam) ───────────

def record_story_event(event_name, *, user_id=None, anon_id=None, team_id=None,
                       story_id=None, story_type=None, surface=None,
                       share_target=None, occurred_at=None):
    """Append one owned story observation under a validated ``event_name``.

    The generic seam behind ``POST /api/product/story-event``. The caller validates
    ``event_name`` against ``STORY_EVENT_NAMES`` (the endpoint does this and ignores
    anything else); this records the standard story envelope — WHICH story
    (story_id + the existing canonical story_type), for WHICH team, on WHICH
    surface, and to WHOM. It infers nothing about engagement, dwell, or
    understanding. The surface is stored in the source column; story descriptors
    live in the payload.

    Phase V3-1 uses this for ``story_impression`` (a card appeared on screen),
    V3-2 for ``story_team_board_opened`` (the reader opened the Team Board), and
    V3-3 for ``story_share_clicked`` (the reader hit Share from a story context;
    ``share_target`` names the share destination scope, e.g. ``team``). The optional
    ``share_target`` is added to the payload only when present, so the other events
    keep their minimal ``{story_id, story_type}`` shape.
    """
    payload = {'story_id': story_id, 'story_type': story_type}
    if share_target is not None:
        payload['share_target'] = share_target
    return record_event(
        event_name, occurred_at=occurred_at, user_id=user_id, anon_id=anon_id,
        team_id=team_id, source=surface, payload=payload,
    )


# ── Product interaction observation emitter (D2A-7) ────────────────────────────

def record_story_interacted(*, user_id=None, anon_id=None, team_id=None, story_id=None,
                            story_type=None, surface=None, interaction_type=None,
                            occurred_at=None):
    """A user explicitly interacted with a rendered story (selection/open/expand).

    Observation only: it records WHICH story, on WHICH surface, by WHOM, and the
    name of the UI action — and nothing about engagement, interest, completion, or
    understanding. The surface is stored in the source column; story descriptors
    and the interaction kind live in the payload.
    """
    return record_event(
        STORY_INTERACTED, occurred_at=occurred_at, user_id=user_id, anon_id=anon_id,
        team_id=team_id, source=surface,
        payload={
            'story_id': story_id,
            'story_type': story_type,
            'interaction_type': interaction_type,
        },
    )


def record_v4_product_event(event_name, *, user_id=None, anon_id=None, team_id=None,
                            source=None, surface=None, route=None, team_abbrev=None,
                            player_id=None, freshness_state=None, occurred_at=None):
    """Append one V4 product-loop observation under a validated event name."""
    payload = {}
    if surface is not None:
        payload['surface'] = surface
    if route is not None:
        payload['route'] = route
    if team_abbrev is not None:
        payload['team_abbrev'] = team_abbrev
    if player_id is not None:
        payload['player_id'] = player_id
    if freshness_state is not None:
        payload['freshness_state'] = freshness_state

    return record_event(
        event_name, occurred_at=occurred_at, user_id=user_id, anon_id=anon_id,
        team_id=team_id, source=source, payload=payload,
    )


# ── Digest deliverability emitters (D2A-7, provider-backed) ────────────────────

def record_digest_delivered(*, user_id=None, delivery_id=None, team_id=None,
                            provider_message_id=None, occurred_at=None):
    """The provider confirmed a sent digest reached the recipient's mailbox."""
    return record_event(
        DIGEST_DELIVERED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        delivery_id=delivery_id, source=SOURCE_EMAIL_PROVIDER,
        payload={'provider_message_id': provider_message_id},
    )


def record_digest_bounced(*, user_id=None, delivery_id=None, team_id=None,
                          provider_message_id=None, bounce_type=None, occurred_at=None):
    """The provider reported a sent digest bounced (undeliverable)."""
    return record_event(
        DIGEST_BOUNCED, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        delivery_id=delivery_id, source=SOURCE_EMAIL_PROVIDER,
        payload={'provider_message_id': provider_message_id, 'bounce_type': bounce_type},
    )


def record_digest_complaint(*, user_id=None, delivery_id=None, team_id=None,
                            provider_message_id=None, occurred_at=None):
    """The provider reported a spam complaint against a sent digest."""
    return record_event(
        DIGEST_COMPLAINT, occurred_at=occurred_at, user_id=user_id, team_id=team_id,
        delivery_id=delivery_id, source=SOURCE_EMAIL_PROVIDER,
        payload={'provider_message_id': provider_message_id},
    )
