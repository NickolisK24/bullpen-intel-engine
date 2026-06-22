"""Canonical BaseballOS story adapter (Phase 1, additive).

This module wraps Story Intelligence V1 (the structural base) into a single,
forward-facing canonical story contract, and assembles those per-team stories
into a feed. It is a contract/presentation layer only:

- It does not author new prose. Headlines and paragraphs come verbatim from the
  Story Intelligence writer; a suppressed team yields a neutral item, never an
  invented story.
- It does not create metrics, rank teams, alter availability/fatigue/trust, or
  change any existing engine.
- Feed team set and ordering mirror the existing four-beat feed only for
  compatibility; the structural story content is Story Intelligence V1.

Known blocker (intentionally not solved in Phase 1): Story Intelligence V1 has
no true positive rest/depth public beat. When a positive observation
(`optionality_strength`) is read, the canonical item preserves the positive
tone/category but is flagged in `quality_status` and `limitations` rather than
rewritten into upbeat copy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from services.story_intelligence_service_v1 import build_team_story
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_CORE_TRANSITION,
    TYPE_DEPTH_PRESSURE,
    TYPE_OPTIONALITY_STRENGTH,
    TYPE_ROTATION_PRESSURE,
    TYPE_STABLE_CORE,
    TYPE_TRUST_LANE_PRESSURE,
)
from services.story_four_beat_interpreter_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
)

CAPABILITY = 'baseballos_canonical_story_v1'
VERSION = '2026-06-22.phase_1'
SOURCE_ENGINE = 'story_intelligence_service_v1'

QUALITY_PUBLISHED = 'published'
QUALITY_REVIEW = 'review'
QUALITY_SUPPRESSED = 'suppressed'

# Suppression reasons surfaced when no story should publish.
SUPPRESSION_UNAVAILABLE = 'story_unavailable'
SUPPRESSION_SUPPRESSED = 'story_suppressed'

# Positive depth/rest reads (optionality / stable core) now publish under the
# availability_depth beat. The limitation below is only attached defensively if a
# positive observation is somehow still reframed into a non-positive beat.
POSITIVE_OBSERVATION_TYPES = {TYPE_OPTIONALITY_STRENGTH, TYPE_STABLE_CORE}
POSITIVE_BEATS = {BEAT_AVAILABILITY_DEPTH}
POSITIVE_BEAT_LIMITATION = 'positive_rest_depth_public_beat_not_yet_supported'

FEED_FALLBACK = 'No bullpen story has enough movement yet today.'

FEED_LIMITATIONS = (
    'wraps_story_intelligence_v1_per_team',
    'feed_team_set_and_order_mirror_four_beat_feed',
    'atomic_evidence_extraction_deferred',
    'no_new_prose_or_metrics_created',
)

# ── League context / quiet-day strategy ──────────────────────────────────────
# A canonical feed must have an honest answer for quiet days, when few clubs have
# a publishable story. The league context describes today's league-wide bullpen
# environment from real counts, or returns a truthful neutral fallback. It never
# fabricates a team-specific narrative and makes no predictions.

LEAGUE_CONTEXT_CAPABILITY = 'baseballos_league_context_v1'
QUALITY_NEUTRAL = 'neutral'

# Day classes by number of publishable team stories. Thresholds map to the Home
# surfaces a future migration would fill: "Three Things To Watch" needs ~3 stories
# and the feed shows up to ~8. So <=2 stories cannot fill the watch strip (quiet),
# 3-5 is a thin news day (low_story), and >5 is a normal news day.
DAY_NORMAL = 'normal'
DAY_LOW_STORY = 'low_story'
DAY_QUIET = 'quiet'
DAY_NO_STORY = 'no_story'

QUIET_STORY_MAX = 2
LOW_STORY_MAX = 5

# League environment modes.
LEAGUE_MODE_BROADLY_CONSTRAINED = 'broadly_constrained'
LEAGUE_MODE_PRESSURE_CONCENTRATED = 'pressure_concentrated'
LEAGUE_MODE_DEPTH_HEALTHY = 'depth_healthy'
LEAGUE_MODE_AVAILABILITY_TIGHTENING = 'availability_tightening'
LEAGUE_MODE_AVAILABILITY_EASING = 'availability_easing'
LEAGUE_MODE_BROADLY_STABLE = 'broadly_stable'
LEAGUE_MODE_NEUTRAL = 'neutral'

# Share-of-league thresholds (denominator = clubs with bullpen data, ~30 in
# season). >=40% of clubs under real pressure is well above a normal day
# (widespread); <=25% means pressure is contained to a minority (concentrated);
# >=50% of clubs with rested depth is a broadly healthy league.
BROADLY_CONSTRAINED_SHARE = 0.40
PRESSURE_CONCENTRATED_SHARE = 0.25
DEPTH_HEALTHY_SHARE = 0.50

# Story-mix fallback (used when no league availability signal is supplied): at
# most this many pressure stories means pressure is concentrated, not broad.
CONCENTRATED_STORY_MAX = 3

LEAGUE_CONTEXT_LIMITATIONS = (
    'derived_from_published_team_stories_and_league_availability_counts',
    'no_predictions_or_betting_content',
    'day_over_day_availability_trend_optional_and_not_fabricated',
)

# ── Story continuity ─────────────────────────────────────────────────────────
# Continuity is keyed to canonical story identity (team + date via story_id) and
# compares today's canonical story with the prior snapshot's canonical story for
# the same team. The core state (new / changed / resolved / unavailable / a
# continuing state) depends only on structured fields (story_type + whether the
# story published), so it is stable against prose rewording. The unchanged vs
# ongoing split uses the deterministic, engine-authored headline as a secondary
# signal only.
CONTINUITY_NEW = 'new'
CONTINUITY_ONGOING = 'ongoing'
CONTINUITY_CHANGED = 'changed'
CONTINUITY_UNCHANGED = 'unchanged'
CONTINUITY_RESOLVED = 'resolved'
CONTINUITY_UNAVAILABLE = 'unavailable'

LEAGUE_CONTINUITY_NEW = 'new'
LEAGUE_CONTINUITY_UNCHANGED = 'unchanged'
LEAGUE_CONTINUITY_CHANGED = 'changed'

# The four authored paragraphs, mapped to public-safe beat labels. Labels mirror
# the existing Team Board StoryCard so a future UI can render either source.
_BEAT_DEFS = (
    ('observation', 'What changed', 'observation_paragraph'),
    ('baseline', 'Comparison point', 'baseline_paragraph'),
    ('cause', 'Why it happened', 'cause_paragraph'),
    ('constraint', 'What it creates', 'constraint_paragraph'),
)

# The two evidentiary beats carry the factual support for share cards.
_EVIDENCE_BEAT_KEYS = ('baseline', 'cause')

# Internal observation type -> (tone, category). Derived from the underlying read
# because the public beats are all pressure-framed (see the positive-beat blocker).
# Trust-lane is its own category so the feed can surface "bodies available, trusted
# lane thin" distinctly; its tone is the supported `watch` token (a monitor signal)
# so every surface renders it cleanly rather than as a neutral fallback.
_OBSERVATION_TONE = {
    TYPE_ROTATION_PRESSURE: ('stress', 'stressed'),
    TYPE_CONCENTRATION_PRESSURE: ('stress', 'stressed'),
    TYPE_DEPTH_PRESSURE: ('stress', 'stressed'),
    TYPE_TRUST_LANE_PRESSURE: ('watch', 'trust_lane'),
    TYPE_CORE_TRANSITION: ('watch', 'watch'),
    TYPE_STABLE_CORE: ('rest', 'rested'),
    TYPE_OPTIONALITY_STRENGTH: ('rest', 'rested'),
}

# Fallback when the internal observation type is unavailable.
_BEAT_TONE = {
    BEAT_COVERAGE_PRESSURE: ('stress', 'stressed'),
    BEAT_DEPTH_CONSTRAINT: ('stress', 'stressed'),
    BEAT_SUSTAINABILITY_QUESTION: ('watch', 'watch'),
    BEAT_ROUTE_CHANGE: ('watch', 'watch'),
    BEAT_AVAILABILITY_DEPTH: ('rest', 'rested'),
    BEAT_TRUST_LANE: ('watch', 'trust_lane'),
}

_DEFAULT_TONE = ('watch', 'watch')

_SHARE_SUMMARY_MAX = 200


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _clean(value: Any) -> str:
    return ' '.join(str(value).split()) if isinstance(value, str) else ''


def _date_str(value: Any):
    if value is None:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _int(value: Any):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def story_id_for(team_id: Any, date_value: Any) -> str:
    """Stable deterministic id: team + date only.

    Beat/story type is intentionally excluded so share links and continuity
    survive an intraday beat change for the same team and date.
    """
    return f"{team_id}:{_date_str(date_value)}"


def _tone_category(observation_type, story_type):
    if observation_type in _OBSERVATION_TONE:
        return _OBSERVATION_TONE[observation_type]
    if story_type in _BEAT_TONE:
        return _BEAT_TONE[story_type]
    return _DEFAULT_TONE


def _beats_from_written(written: dict) -> list[dict]:
    beats = []
    for key, label, field in _BEAT_DEFS:
        text = _clean(written.get(field))
        if text:
            beats.append({'key': key, 'label': label, 'text': text})
    return beats


def _narrative_from_beats(beats: list[dict]) -> str:
    return '\n\n'.join(beat['text'] for beat in beats)


def _evidence_from_beats(beats: list[dict]) -> list[dict]:
    return [
        {'key': beat['key'], 'label': beat['label'], 'text': beat['text']}
        for beat in beats
        if beat['key'] in _EVIDENCE_BEAT_KEYS
    ]


def _share_title(team_name, story_type_label, headline):
    name = _clean(team_name)
    label = _clean(story_type_label)
    if name and label:
        return f"{name} bullpen: {label.lower()}"
    return headline or None


def _share_summary(beats: list[dict]):
    if not beats:
        return None
    text = beats[0]['text']
    if len(text) <= _SHARE_SUMMARY_MAX:
        return text
    clipped = text[:_SHARE_SUMMARY_MAX].rsplit(' ', 1)[0].rstrip(',.;:')
    return f"{clipped}…"


def _suppression_reason(service_payload, payload: dict) -> str:
    reason = payload.get('neutral_reason')
    if reason:
        return reason
    return SUPPRESSION_UNAVAILABLE if service_payload is None else SUPPRESSION_SUPPRESSED


def canonical_story_from_service_payload(service_payload, *, team_id=None, team=None, date=None) -> dict:
    """Map one Story Intelligence V1 ``build_team_story`` payload to a canonical story.

    Returns a neutral, clearly-suppressed item when no story is available — it
    never invents a headline or narrative.
    """
    payload = _dict(service_payload)
    team = _dict(team)

    resolved_team_id = payload.get('team_id') or team.get('team_id') or team_id
    team_name = payload.get('team_name') or team.get('team_name')
    team_abbreviation = payload.get('team_abbreviation') or team.get('team_abbreviation')
    date_value = _date_str(date) or _date_str(payload.get('as_of_date'))

    story_available = payload.get('story_available') is True

    item = {
        'story_id': story_id_for(resolved_team_id, date_value),
        'team_id': resolved_team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'date': date_value,
        'story_available': story_available,
        'suppression_reason': None,
        'story_type': payload.get('story_type'),
        'category': None,
        'tone': None,
        'headline': None,
        'narrative': None,
        'beats': [],
        'evidence': [],
        'freshness': _dict(payload.get('freshness')),
        'trust_metadata': _dict(payload.get('trust_metadata')),
        'limitations': list(payload.get('limitations') or []),
        'share_ready': False,
        'share_title': None,
        'share_summary': None,
        'source_engine': SOURCE_ENGINE,
        'quality_status': QUALITY_SUPPRESSED,
        # Populated at feed assembly, which has the prior-snapshot context.
        'continuity': None,
    }

    if not story_available:
        # Do not fabricate a story. Leave the prose fields empty and explain why.
        item['story_type'] = None
        item['suppression_reason'] = _suppression_reason(service_payload, payload)
        return item

    written = _dict(payload.get('written_story'))
    selected = _dict(payload.get('selected_observation'))
    frame = _dict(payload.get('construction_frame'))
    observation_type = selected.get('type') or frame.get('observation_type')
    story_type = payload.get('story_type')
    story_type_label = payload.get('story_type_label') or _dict(payload.get('public_story_beat')).get('story_type_label')

    beats = _beats_from_written(written)
    narrative = _narrative_from_beats(beats)
    headline = _clean(written.get('headline'))
    tone, category = _tone_category(observation_type, story_type)

    item.update({
        'category': category,
        'tone': tone,
        'headline': headline or None,
        'narrative': narrative or None,
        'beats': beats,
        'evidence': _evidence_from_beats(beats),
        'share_ready': bool(headline and narrative),
        'share_title': _share_title(team_name, story_type_label, headline or None),
        'share_summary': _share_summary(beats),
        'quality_status': QUALITY_PUBLISHED,
    })

    # A positive read should publish under a positive beat. Only if one is ever
    # still reframed into a non-positive beat do we flag it for review rather than
    # present it as a clean pressure story; valid positive stories publish as-is.
    if observation_type in POSITIVE_OBSERVATION_TYPES and story_type not in POSITIVE_BEATS:
        if POSITIVE_BEAT_LIMITATION not in item['limitations']:
            item['limitations'].append(POSITIVE_BEAT_LIMITATION)
        item['quality_status'] = QUALITY_REVIEW

    return item


def classify_story_day(publishable_count) -> str:
    """Classify the day by how many teams have a publishable story."""
    count = _int(publishable_count) or 0
    if count <= 0:
        return DAY_NO_STORY
    if count <= QUIET_STORY_MAX:
        return DAY_QUIET
    if count <= LOW_STORY_MAX:
        return DAY_LOW_STORY
    return DAY_NORMAL


def _select_league_mode(
    *,
    day_class,
    pressure_count,
    rest_count,
    constrained_count,
    constrained_share,
    available_share,
    trend,
):
    """Pick one honest league mode + copy. Returns (mode, headline, summary, generated)."""
    # 1. Widespread pressure across the league.
    if constrained_share is not None and constrained_share >= BROADLY_CONSTRAINED_SHARE:
        detail = f'{constrained_count} clubs are' if constrained_count else 'A large share of clubs are'
        return (
            LEAGUE_MODE_BROADLY_CONSTRAINED,
            'Bullpen pressure is unusually widespread across the league today.',
            f'{detail} carrying real late-inning workload pressure, more than a typical day.',
            True,
        )

    # 2. Pressure exists but is contained to a minority of clubs.
    pressure_present = (constrained_count is not None and constrained_count >= 1) or pressure_count >= 1
    pressure_contained = (
        (constrained_share is not None and constrained_share <= PRESSURE_CONCENTRATED_SHARE)
        or (constrained_share is None and pressure_count <= CONCENTRATED_STORY_MAX)
    )
    if pressure_present and pressure_contained:
        clubs = constrained_count if constrained_count else pressure_count
        return (
            LEAGUE_MODE_PRESSURE_CONCENTRATED,
            "Today's bullpen pressure is concentrated in a small set of clubs.",
            f'Most bullpens are in normal shape; the meaningful workload pressure is contained to {clubs} clubs.',
            True,
        )

    # 3. Broad, healthy depth with little pressure.
    depth_broad = (
        (available_share is not None and available_share >= DEPTH_HEALTHY_SHARE)
        or (available_share is None and rest_count >= 2 and pressure_count == 0)
    )
    if depth_broad:
        return (
            LEAGUE_MODE_DEPTH_HEALTHY,
            'Most bullpens carry healthy late-inning depth today.',
            'A broad share of clubs have rested late-inning options, with little widespread pressure.',
            True,
        )

    # 4. Optional day-over-day availability trend (only when a real signal is supplied).
    if trend == 'tightening':
        return (
            LEAGUE_MODE_AVAILABILITY_TIGHTENING,
            'League-wide bullpen availability is tightening.',
            'Fewer rested relievers are available across the league than the recent baseline.',
            True,
        )
    if trend == 'easing':
        return (
            LEAGUE_MODE_AVAILABILITY_EASING,
            'League-wide bullpen availability is easing.',
            'More rested relievers are available across the league than the recent baseline.',
            True,
        )

    # 5. Quiet day with no clear league signal: an honest, non-dramatic stable read.
    if day_class in (DAY_QUIET, DAY_NO_STORY):
        return (
            LEAGUE_MODE_BROADLY_STABLE,
            'No major bullpen story is emerging today.',
            'Bullpen conditions are broadly stable, with no widespread availability pressure across the league.',
            False,
        )

    # 6. Otherwise a truthful neutral observation, with no forced drama.
    return (
        LEAGUE_MODE_NEUTRAL,
        'No single bullpen pattern stands out across the league today.',
        "Today's read sits with the individual team stories; there is no league-wide bullpen theme.",
        False,
    )


def build_league_context(items, *, league_signal=None, as_of_date=None, prior_league_context=None) -> dict:
    """Build the league-context section for the canonical feed.

    Describes today's league-wide bullpen environment from real counts (the
    published team-story mix plus an optional league availability signal), or a
    truthful neutral fallback. No team-specific narrative is invented.
    """
    rows = [item for item in (items or []) if isinstance(item, dict)]
    publishable = [item for item in rows if item.get('story_available') is True]
    pressure = [item for item in publishable if item.get('category') == 'stressed']
    rest = [item for item in publishable if item.get('category') == 'rested']
    watch = [item for item in publishable if item.get('category') == 'watch']
    day_class = classify_story_day(len(publishable))

    signal = _dict(league_signal)
    team_count = _int(signal.get('team_count'))
    constrained_count = _int(signal.get('constrained_team_count'))
    available_count = _int(signal.get('available_team_count'))
    trend = signal.get('availability_trend')
    if trend not in ('easing', 'tightening'):
        trend = None

    constrained_share = (
        constrained_count / team_count
        if team_count and constrained_count is not None
        else None
    )
    available_share = (
        available_count / team_count
        if team_count and available_count is not None
        else None
    )

    mode, headline, summary, generated = _select_league_mode(
        day_class=day_class,
        pressure_count=len(pressure),
        rest_count=len(rest),
        constrained_count=constrained_count,
        constrained_share=constrained_share,
        available_share=available_share,
        trend=trend,
    )

    evidence = {
        'team_story_count': len(rows),
        'publishable_story_count': len(publishable),
        'pressure_story_count': len(pressure),
        'rest_story_count': len(rest),
        'watch_story_count': len(watch),
        'league_team_count': team_count,
        'constrained_team_count': constrained_count,
        'available_team_count': available_count,
        'constrained_team_share': round(constrained_share, 3) if constrained_share is not None else None,
        'available_team_share': round(available_share, 3) if available_share is not None else None,
        'availability_trend': trend,
    }

    return {
        'capability': LEAGUE_CONTEXT_CAPABILITY,
        'mode': mode,
        'day_class': day_class,
        'headline': headline,
        'summary': summary,
        'evidence': evidence,
        'generated': generated,
        'quality_status': QUALITY_PUBLISHED if generated else QUALITY_NEUTRAL,
        'as_of_date': _date_str(as_of_date),
        'continuity': _league_continuity(mode, prior_league_context),
        'limitations': list(LEAGUE_CONTEXT_LIMITATIONS),
    }


def _league_continuity(today_mode, prior_league_context=None) -> dict:
    """Continuity for the league read: did today's league mode change from prior?"""
    prior = prior_league_context if isinstance(prior_league_context, dict) else None
    prior_mode = prior.get('mode') if prior else None
    prior_date = prior.get('as_of_date') if prior else None
    if prior is None:
        state, reason = LEAGUE_CONTINUITY_NEW, 'no_prior_league_context'
    elif today_mode == prior_mode:
        state, reason = LEAGUE_CONTINUITY_UNCHANGED, 'league_mode_persisted'
    else:
        state, reason = LEAGUE_CONTINUITY_CHANGED, 'league_mode_changed'
    return {
        'state': state,
        'reason': reason,
        'previous_mode': prior_mode,
        'changed_since': prior_date,
    }


def build_story_continuity(today_item, prior_item=None) -> dict:
    """Continuity state for one canonical story vs the prior snapshot's story.

    Keyed to canonical/team identity. The core state (new / changed / resolved /
    unavailable / a continuing state) depends only on story_type and whether the
    story published, so it is stable against prose rewording. The unchanged vs
    ongoing split uses the deterministic engine headline as a secondary signal.
    """
    today = _dict(today_item)
    prior = prior_item if isinstance(prior_item, dict) else None
    today_pub = today.get('story_available') is True
    prior_pub = bool(prior and prior.get('story_available') is True)

    today_type = today.get('story_type')
    previous_story_id = prior.get('story_id') if prior else None
    previous_story_type = prior.get('story_type') if prior else None
    previous_headline = prior.get('headline') if prior else None
    previous_date = prior.get('date') if prior else None

    if today_pub:
        if prior is None:
            state, reason = CONTINUITY_NEW, 'no_prior_canonical_story'
        elif not prior_pub:
            state, reason = CONTINUITY_NEW, 'prior_story_was_suppressed'
        elif today_type != previous_story_type:
            state, reason = CONTINUITY_CHANGED, 'story_type_changed'
        elif _clean(today.get('headline')) and _clean(today.get('headline')) == _clean(previous_headline):
            state, reason = CONTINUITY_UNCHANGED, 'story_unchanged'
        else:
            state, reason = CONTINUITY_ONGOING, 'story_type_persisted'
    else:
        if prior_pub:
            state, reason = CONTINUITY_RESOLVED, 'prior_story_no_longer_publishes'
        elif prior is None:
            state, reason = CONTINUITY_UNAVAILABLE, 'no_prior_canonical_story'
        else:
            state, reason = CONTINUITY_UNAVAILABLE, 'no_publishable_story_today'

    story_type_changed = (
        today_type != previous_story_type if (today_pub and prior_pub) else None
    )

    return {
        'state': state,
        'reason': reason,
        'previous_story_id': previous_story_id,
        'previous_story_type': previous_story_type,
        'previous_headline': previous_headline,
        'changed_since': previous_date,
        'compared': prior is not None,
        'evidence': {
            'today_publishable': today_pub,
            'prior_publishable': prior_pub,
            'prior_present': prior is not None,
            'story_type_changed': story_type_changed,
        },
    }


def build_canonical_story_feed(
    teams,
    *,
    as_of_date,
    story_builder: Callable | None = None,
    freshness=None,
    league_signal=None,
    prior_stories=None,
    prior_league_context=None,
) -> dict:
    """Build the canonical league-wide story feed.

    ``teams`` is an ordered list of team descriptors ``{team_id, team_name,
    team_abbreviation}`` (or bare ids). Order is preserved for available stories;
    suppressed teams are kept after them so consumers see every team considered.
    """
    builder = story_builder or build_team_story
    date_value = _date_str(as_of_date)

    items: list[dict] = []
    seen: set = set()
    for descriptor in teams or []:
        team = descriptor if isinstance(descriptor, dict) else {'team_id': descriptor}
        team_id = team.get('team_id')
        if team_id is None or team_id in seen:
            continue
        seen.add(team_id)
        try:
            service_payload = builder(team_id, as_of_date=as_of_date)
        except Exception:
            # An individual team's failure must not break the dashboard payload.
            service_payload = None
        items.append(
            canonical_story_from_service_payload(
                service_payload,
                team_id=team_id,
                team=team,
                date=as_of_date,
            )
        )

    # Attach continuity by comparing each story to the prior snapshot's canonical
    # story for the same team. Both published and suppressed items get a state.
    prior_index: dict = {}
    for prior in prior_stories or []:
        if isinstance(prior, dict) and prior.get('team_id') is not None:
            prior_index.setdefault(prior['team_id'], prior)
    for story in items:
        story['continuity'] = build_story_continuity(story, prior_index.get(story.get('team_id')))

    available = [story for story in items if story['story_available']]
    suppressed = [story for story in items if not story['story_available']]
    suppression_reasons: dict[str, int] = {}
    for story in suppressed:
        reason = story.get('suppression_reason') or 'unknown'
        suppression_reasons[reason] = suppression_reasons.get(reason, 0) + 1

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source_engine': SOURCE_ENGINE,
        'as_of_date': date_value,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'items': available + suppressed,
        'available_count': len(available),
        'suppressed_count': len(suppressed),
        'suppression_reasons': suppression_reasons,
        'fallback': FEED_FALLBACK,
        'freshness': _dict(freshness),
        'limitations': list(FEED_LIMITATIONS),
        'league_context': build_league_context(
            available + suppressed,
            league_signal=league_signal,
            as_of_date=as_of_date,
            prior_league_context=prior_league_context,
        ),
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'SOURCE_ENGINE',
    'QUALITY_PUBLISHED',
    'QUALITY_REVIEW',
    'QUALITY_SUPPRESSED',
    'QUALITY_NEUTRAL',
    'LEAGUE_CONTEXT_CAPABILITY',
    'POSITIVE_BEAT_LIMITATION',
    'POSITIVE_OBSERVATION_TYPES',
    'CONTINUITY_NEW',
    'CONTINUITY_ONGOING',
    'CONTINUITY_CHANGED',
    'CONTINUITY_UNCHANGED',
    'CONTINUITY_RESOLVED',
    'CONTINUITY_UNAVAILABLE',
    'story_id_for',
    'canonical_story_from_service_payload',
    'build_canonical_story_feed',
    'build_league_context',
    'build_story_continuity',
    'classify_story_day',
]
