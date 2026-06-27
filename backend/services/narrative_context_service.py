"""Narrative Context Engine (COIN Phase 3.5).

Sits between Completed Game Context and Story Generation:

    CompletedGameContext  ->  NarrativeContext  ->  Story Generation

Its job is to turn a derived completed-game context into structured baseball
intelligence — "editorial facts", not prose. It reads a CompletedGameContext
(model instance or dict) and returns a deterministic ``NarrativeContext``:
which story to tell, how urgent it is, reusable headline/summary keys, and the
structured observations and facts a writer would lean on. It generates NO
natural language, calls NO model, and invents nothing — every field is derived
deterministically from the context.

Fail-closed: LOW-confidence (or missing) context collapses to
``insufficient_context`` at LOW priority with no observations or facts, so an
incomplete game can never be dressed up as a story.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.completed_game_context_service import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CREATED_SHAPE_VALUES,
    TAG_BULLPEN_KEPT_TEAM_ALIVE,
    TAG_BULLPEN_OVEREXPOSED,
    TAG_INSUFFICIENT_CONTEXT,
    TAG_LATE_PRESSURE_ACCUMULATED,
    TAG_LOST_GAME_SHAPE,
    TAG_PROTECTED_GAME_SHAPE,
    TAG_STARTER_COVERED_BULLPEN,
)
from services.game_shape import SHAPE_SHORT_START
from utils.time import utc_now_naive


STORY_VERSION = 'narrative_context_v1'
CONTEXT_TYPE_COMPLETED_GAME = 'completed_game'

# ── Story priority ────────────────────────────────────────────────────────────
PRIORITY_CRITICAL = 'CRITICAL'
PRIORITY_HIGH = 'HIGH'
PRIORITY_MEDIUM = 'MEDIUM'
PRIORITY_LOW = 'LOW'

# Importance (magnitude of the swing) — distinct from editorial priority.
IMPORTANCE_HIGH = 'HIGH'
IMPORTANCE_MEDIUM = 'MEDIUM'
IMPORTANCE_LOW = 'LOW'

# A lead/deficit of this size reads as a "major" swing (collapse / big comeback).
MAJOR_SWING_RUNS = 4
NOTABLE_SWING_RUNS = 2
MULTIPLE_LATE_RUNS = 2
DEEP_START_IP = 6.0

# Base priority per primary story. Escalations (e.g. a 4+ run collapse or
# comeback) are applied on top of this, conservatively.
_BASE_PRIORITY = {
    TAG_LOST_GAME_SHAPE: PRIORITY_CRITICAL,
    TAG_BULLPEN_KEPT_TEAM_ALIVE: PRIORITY_HIGH,
    TAG_PROTECTED_GAME_SHAPE: PRIORITY_HIGH,
    TAG_LATE_PRESSURE_ACCUMULATED: PRIORITY_HIGH,
    TAG_BULLPEN_OVEREXPOSED: PRIORITY_MEDIUM,
    TAG_STARTER_COVERED_BULLPEN: PRIORITY_MEDIUM,
    TAG_INSUFFICIENT_CONTEXT: PRIORITY_LOW,
}

# Reusable headline identifiers (stories translate these later, never the reverse).
_HEADLINE_KEYS = {
    TAG_LOST_GAME_SHAPE: 'lost_game_shape',
    TAG_PROTECTED_GAME_SHAPE: 'protected_game_shape',
    TAG_BULLPEN_KEPT_TEAM_ALIVE: 'bullpen_kept_team_alive',
    TAG_BULLPEN_OVEREXPOSED: 'bullpen_overexposed',
    TAG_LATE_PRESSURE_ACCUMULATED: 'late_pressure_accumulated',
    TAG_STARTER_COVERED_BULLPEN: 'starter_carried_game',
    TAG_INSUFFICIENT_CONTEXT: 'insufficient_context',
}
# Special-case headline: a protected lead with zero late damage is a clean hold.
HEADLINE_BULLPEN_STABILIZED = 'bullpen_stabilized'

_SUMMARY_KEYS = {
    TAG_LOST_GAME_SHAPE: 'game_shape_not_protected',
    TAG_PROTECTED_GAME_SHAPE: 'game_shape_protected',
    TAG_BULLPEN_KEPT_TEAM_ALIVE: 'bullpen_preserved_comeback',
    TAG_BULLPEN_OVEREXPOSED: 'bullpen_carried_heavy_load',
    TAG_LATE_PRESSURE_ACCUMULATED: 'late_pressure_mounted',
    TAG_STARTER_COVERED_BULLPEN: 'starter_limited_bullpen_exposure',
    TAG_INSUFFICIENT_CONTEXT: 'insufficient_context',
}

# Order in which a secondary story is preferred when several signals are present.
_SECONDARY_PRIORITY = (
    TAG_LOST_GAME_SHAPE,
    TAG_BULLPEN_KEPT_TEAM_ALIVE,
    TAG_PROTECTED_GAME_SHAPE,
    TAG_LATE_PRESSURE_ACCUMULATED,
    TAG_BULLPEN_OVEREXPOSED,
    TAG_STARTER_COVERED_BULLPEN,
)


@dataclass(frozen=True)
class NarrativeContext:
    """Structured, prose-free baseball intelligence for one completed game/team."""

    primary_story: str
    secondary_story: str | None
    story_priority: str
    confidence: str
    headline_key: str
    summary_key: str
    supporting_observations: list[str] = field(default_factory=list)
    supporting_facts: dict[str, Any] = field(default_factory=dict)
    game_importance: str = IMPORTANCE_LOW
    context_type: str = CONTEXT_TYPE_COMPLETED_GAME
    story_version: str = STORY_VERSION
    team_id: int | None = None
    game_pk: int | None = None
    generated_at: Any = None

    def to_dict(self) -> dict:
        return {
            'primary_story': self.primary_story,
            'secondary_story': self.secondary_story,
            'story_priority': self.story_priority,
            'confidence': self.confidence,
            'headline_key': self.headline_key,
            'summary_key': self.summary_key,
            'supporting_observations': list(self.supporting_observations),
            'supporting_facts': dict(self.supporting_facts),
            'game_importance': self.game_importance,
            'context_type': self.context_type,
            'story_version': self.story_version,
            'team_id': self.team_id,
            'game_pk': self.game_pk,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
        }


def _value(obj: Any, name: str, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _int(value):
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _insufficient(team_id, game_pk, confidence, generated_at) -> NarrativeContext:
    """The single fail-closed shape: no story, no observations, no facts."""
    return NarrativeContext(
        primary_story=TAG_INSUFFICIENT_CONTEXT,
        secondary_story=None,
        story_priority=PRIORITY_LOW,
        confidence=confidence,
        headline_key=_HEADLINE_KEYS[TAG_INSUFFICIENT_CONTEXT],
        summary_key=_SUMMARY_KEYS[TAG_INSUFFICIENT_CONTEXT],
        supporting_observations=[],
        supporting_facts={},
        game_importance=IMPORTANCE_LOW,
        team_id=team_id,
        game_pk=game_pk,
        generated_at=generated_at,
    )


def _active_secondary_signals(ctx) -> set[str]:
    """Story tags (besides the primary) whose conditions hold for this game.

    Derived only from stored context fields — no re-fetch, no invention.
    """
    shape_created = _value(ctx, 'game_shape_created') in CREATED_SHAPE_VALUES
    late_7_9 = _int(_value(ctx, 'runs_allowed_innings_7_to_9')) or 0
    starter_ip = _value(ctx, 'starter_ip')
    deep_clean = (
        starter_ip is not None and starter_ip >= DEEP_START_IP
        and (_int(_value(ctx, 'late_runs_allowed')) or 0) == 0
    )

    signals: set[str] = set()
    if _value(ctx, 'lead_lost') is True and shape_created:
        signals.add(TAG_LOST_GAME_SHAPE)
    if _value(ctx, 'lead_protected') is True and shape_created:
        signals.add(TAG_PROTECTED_GAME_SHAPE)
    if _value(ctx, 'comeback_completed') is True:
        signals.add(TAG_BULLPEN_KEPT_TEAM_ALIVE)
    if late_7_9 >= MULTIPLE_LATE_RUNS:
        signals.add(TAG_LATE_PRESSURE_ACCUMULATED)
    if _value(ctx, 'game_shape_created') == SHAPE_SHORT_START:
        signals.add(TAG_BULLPEN_OVEREXPOSED)
    if deep_clean:
        signals.add(TAG_STARTER_COVERED_BULLPEN)
    return signals


def _supporting_observations(ctx) -> list[str]:
    """Concise deterministic observation identifiers for present facts only."""
    observations: list[str] = []

    if _value(ctx, 'game_shape_created') in CREATED_SHAPE_VALUES:
        observations.append('starter_created_game_shape')

    starter_ip = _value(ctx, 'starter_ip')
    if starter_ip is not None and starter_ip >= DEEP_START_IP:
        observations.append('deep_start')

    if (_int(_value(ctx, 'lead_when_bullpen_entered')) or 0) > 0:
        observations.append('lead_entering_bullpen')
    elif (_int(_value(ctx, 'deficit_when_bullpen_entered')) or 0) > 0:
        observations.append('deficit_entering_bullpen')

    if _value(ctx, 'lead_protected') is True:
        observations.append('bullpen_preserved_lead')
    if _value(ctx, 'lead_lost') is True:
        observations.append('bullpen_lost_lead')

    late_total = _int(_value(ctx, 'late_runs_allowed')) or 0
    late_7_9 = _int(_value(ctx, 'runs_allowed_innings_7_to_9')) or 0
    if late_total > 0:
        observations.append('late_runs_allowed')
    if late_7_9 >= MULTIPLE_LATE_RUNS:
        observations.append('multiple_late_runs')
        observations.append('late_scoring_sequence')

    if _value(ctx, 'comeback_completed') is True:
        observations.append('comeback_completed')

    if _value(ctx, 'bullpen_story_tag') == TAG_BULLPEN_OVEREXPOSED:
        observations.append('bullpen_worked_long')

    if _int(_value(ctx, 'turning_inning')) is not None:
        observations.append('turning_point_identified')

    return observations


def _supporting_facts(ctx) -> dict[str, Any]:
    """Structured evidence — only non-null fields, no exaggeration of gaps."""
    candidates = {
        'largest_lead': _int(_value(ctx, 'largest_lead')),
        'largest_deficit': _int(_value(ctx, 'largest_deficit')),
        'late_runs_allowed': _int(_value(ctx, 'late_runs_allowed')),
        'runs_allowed_innings_7_to_9': _int(_value(ctx, 'runs_allowed_innings_7_to_9')),
        'bullpen_entry_inning': _int(_value(ctx, 'bullpen_entry_inning')),
        'bullpen_entry_score_for': _int(_value(ctx, 'bullpen_entry_score_for')),
        'bullpen_entry_score_against': _int(_value(ctx, 'bullpen_entry_score_against')),
        'starter_exit_score_for': _int(_value(ctx, 'starter_exit_score_for')),
        'starter_exit_score_against': _int(_value(ctx, 'starter_exit_score_against')),
        'turning_inning': _int(_value(ctx, 'turning_inning')),
    }
    facts = {key: val for key, val in candidates.items() if val is not None}

    # Tri-state outcome flags: include only when actually determined.
    for flag in ('lead_protected', 'lead_lost', 'game_shape_protected'):
        val = _value(ctx, flag)
        if val is not None:
            facts[flag] = bool(val)

    shape = _value(ctx, 'game_shape_created')
    if shape:
        facts['game_shape_created'] = shape
    return facts


def _swing_runs(ctx) -> int:
    return max(_int(_value(ctx, 'largest_lead')) or 0,
               _int(_value(ctx, 'largest_deficit')) or 0)


def _story_priority(primary: str, ctx) -> str:
    base = _BASE_PRIORITY.get(primary, PRIORITY_LOW)
    swing = _swing_runs(ctx)
    # A big lead surrendered, or a big deficit erased, escalates to CRITICAL.
    if primary == TAG_BULLPEN_KEPT_TEAM_ALIVE and swing >= MAJOR_SWING_RUNS:
        return PRIORITY_CRITICAL
    return base


def _game_importance(primary: str, ctx) -> str:
    if primary == TAG_INSUFFICIENT_CONTEXT:
        return IMPORTANCE_LOW
    swing = _swing_runs(ctx)
    lead_situation = (
        _value(ctx, 'lead_lost') is True
        or _value(ctx, 'lead_protected') is True
        or _value(ctx, 'comeback_completed') is True
    )
    if lead_situation and swing >= MAJOR_SWING_RUNS:
        return IMPORTANCE_HIGH
    if (_int(_value(ctx, 'runs_allowed_innings_7_to_9')) or 0) >= MULTIPLE_LATE_RUNS:
        return IMPORTANCE_MEDIUM
    if lead_situation and swing >= NOTABLE_SWING_RUNS:
        return IMPORTANCE_MEDIUM
    return IMPORTANCE_LOW


def _headline_key(primary: str, ctx) -> str:
    if primary == TAG_PROTECTED_GAME_SHAPE \
            and (_int(_value(ctx, 'late_runs_allowed')) or 0) == 0:
        return HEADLINE_BULLPEN_STABILIZED
    return _HEADLINE_KEYS.get(primary, _HEADLINE_KEYS[TAG_INSUFFICIENT_CONTEXT])


def build_narrative_context(completed_game_context) -> NarrativeContext:
    """Convert one CompletedGameContext (model or dict) into a NarrativeContext.

    Deterministic and fail-closed: returns ``insufficient_context`` whenever the
    context is missing, LOW confidence, or carries no recognized story.
    """
    generated_at = utc_now_naive()
    if completed_game_context is None:
        return _insufficient(None, None, CONFIDENCE_LOW, generated_at)

    team_id = _int(_value(completed_game_context, 'team_id'))
    game_pk = _int(_value(completed_game_context, 'game_pk'))
    confidence = _value(completed_game_context, 'confidence') or CONFIDENCE_LOW

    primary = _value(completed_game_context, 'bullpen_story_tag')
    if confidence not in (CONFIDENCE_MEDIUM, CONFIDENCE_HIGH) \
            or primary not in _BASE_PRIORITY \
            or primary == TAG_INSUFFICIENT_CONTEXT:
        return _insufficient(team_id, game_pk, confidence, generated_at)

    secondary = None
    for candidate in _SECONDARY_PRIORITY:
        if candidate != primary and candidate in _active_secondary_signals(completed_game_context):
            secondary = candidate
            break

    return NarrativeContext(
        primary_story=primary,
        secondary_story=secondary,
        story_priority=_story_priority(primary, completed_game_context),
        confidence=confidence,
        headline_key=_headline_key(primary, completed_game_context),
        summary_key=_SUMMARY_KEYS.get(primary, _SUMMARY_KEYS[TAG_INSUFFICIENT_CONTEXT]),
        supporting_observations=_supporting_observations(completed_game_context),
        supporting_facts=_supporting_facts(completed_game_context),
        game_importance=_game_importance(primary, completed_game_context),
        team_id=team_id,
        game_pk=game_pk,
        generated_at=generated_at,
    )


def build_narrative_contexts(completed_game_contexts) -> list[NarrativeContext]:
    """Map a collection of CompletedGameContext rows to NarrativeContext objects."""
    return [build_narrative_context(ctx) for ctx in (completed_game_contexts or [])]
