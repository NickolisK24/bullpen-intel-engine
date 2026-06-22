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
)
from services.story_four_beat_interpreter_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
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
_OBSERVATION_TONE = {
    TYPE_ROTATION_PRESSURE: ('stress', 'stressed'),
    TYPE_CONCENTRATION_PRESSURE: ('stress', 'stressed'),
    TYPE_DEPTH_PRESSURE: ('stress', 'stressed'),
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


def build_canonical_story_feed(
    teams,
    *,
    as_of_date,
    story_builder: Callable | None = None,
    freshness=None,
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
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'SOURCE_ENGINE',
    'QUALITY_PUBLISHED',
    'QUALITY_REVIEW',
    'QUALITY_SUPPRESSED',
    'POSITIVE_BEAT_LIMITATION',
    'POSITIVE_OBSERVATION_TYPES',
    'story_id_for',
    'canonical_story_from_service_payload',
    'build_canonical_story_feed',
]
