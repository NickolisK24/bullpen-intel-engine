"""Narrative Feed Builder (COIN Phase 3.75).

Sits between the Narrative Context Engine and Story Writers:

    CompletedGameContext -> Narrative Context Engine -> Narrative Feed Builder
        -> Story Writers -> Frontend / API / Social

It is an editor assembling notes, not a writer. Given one team it packages
everything a Story Writer needs into a single deterministic ``NarrativeFeed``:
the narrative context (primary/secondary story, priority, keys, observations,
facts) plus read-only snapshots of the team's existing bullpen intelligence
(availability, workload, bullpen state), a recommended story focus, and the
safe relative-time framing that downstream prose is allowed to use.

It performs NO baseball reasoning beyond assembling already-derived intelligence
and choosing safe presentation metadata. It generates no prose, calls no model,
and never recomputes the bullpen engines — it reads what they already produced
(via ``build_team_bullpen_context``) and packages it. Fail-closed: a LOW /
insufficient narrative collapses the recommended focus to ``insufficient_context``
and the time framing to ``CURRENT_STATUS``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from services.completed_game_context_service import TAG_INSUFFICIENT_CONTEXT
from services.narrative_context_service import (
    build_narrative_context,
    NarrativeContext,
    PRIORITY_CRITICAL,
    PRIORITY_HIGH,
)
from utils.time import utc_now_naive


FEED_VERSION = 'narrative_feed_v1'

# ── Recommended story focus identifiers ───────────────────────────────────────
FOCUS_GAME_CONTEXT = 'game_context'
FOCUS_BULLPEN_AVAILABILITY = 'bullpen_availability'
FOCUS_LATE_INNING_EXECUTION = 'late_inning_execution'
FOCUS_WORKLOAD_PRESSURE = 'workload_pressure'
FOCUS_BULLPEN_DEPTH = 'bullpen_depth'
FOCUS_COVERAGE_FLEXIBILITY = 'coverage_flexibility'
FOCUS_MULTIPLE_STORYLINES = 'multiple_storylines'
FOCUS_INSUFFICIENT_CONTEXT = 'insufficient_context'

# ── Safe time context (relative-time language the writer may use) ─────────────
TIME_AFTER_MOST_RECENT_GAME = 'AFTER_MOST_RECENT_GAME'
TIME_ENTERING_TODAY = 'ENTERING_TODAY'   # reserved for schedule-aware phases
TIME_CURRENT_STATUS = 'CURRENT_STATUS'
TIME_INSUFFICIENT_CONTEXT = 'INSUFFICIENT_CONTEXT'

# Map a primary story to the focus its game narrative leads with.
_FOCUS_BY_PRIMARY = {
    'lost_game_shape': FOCUS_GAME_CONTEXT,
    'protected_game_shape': FOCUS_GAME_CONTEXT,
    'bullpen_kept_team_alive': FOCUS_GAME_CONTEXT,
    'late_pressure_accumulated': FOCUS_LATE_INNING_EXECUTION,
    'bullpen_overexposed': FOCUS_WORKLOAD_PRESSURE,
    'starter_covered_bullpen': FOCUS_BULLPEN_DEPTH,
}

# Bands that read as a thin / concentrated / deep bullpen state.
_THIN_BANDS = frozenset({'thin', 'narrow'})
_CONCENTRATED_BANDS = frozenset({'concentrated', 'narrow'})
_DEEP_BANDS = frozenset({'deep', 'flexible'})


@dataclass(frozen=True)
class NarrativeFeed:
    """One deterministic editorial brief — the only input a Story Writer needs."""

    team_id: int | None
    game_pk: int | None
    feed_version: str
    confidence: str
    story_priority: str
    game_importance: str
    primary_narrative: str
    secondary_narrative: str | None
    headline_key: str
    summary_key: str
    supporting_observations: list[str] = field(default_factory=list)
    supporting_facts: dict[str, Any] = field(default_factory=dict)
    completed_game_context: dict | None = None
    narrative_context: dict | None = None
    availability_snapshot: dict = field(default_factory=dict)
    workload_snapshot: dict = field(default_factory=dict)
    bullpen_snapshot: dict = field(default_factory=dict)
    recommended_story_focus: str = FOCUS_INSUFFICIENT_CONTEXT
    safe_time_context: str = TIME_CURRENT_STATUS
    generated_at: Any = None

    def to_dict(self) -> dict:
        return {
            'team_id': self.team_id,
            'game_pk': self.game_pk,
            'feed_version': self.feed_version,
            'generated_at': self.generated_at.isoformat() if self.generated_at else None,
            'confidence': self.confidence,
            'story_priority': self.story_priority,
            'game_importance': self.game_importance,
            'primary_narrative': self.primary_narrative,
            'secondary_narrative': self.secondary_narrative,
            'headline_key': self.headline_key,
            'summary_key': self.summary_key,
            'supporting_observations': list(self.supporting_observations),
            'supporting_facts': dict(self.supporting_facts),
            'completed_game_context': self.completed_game_context,
            'narrative_context': self.narrative_context,
            'availability_snapshot': dict(self.availability_snapshot),
            'workload_snapshot': dict(self.workload_snapshot),
            'bullpen_snapshot': dict(self.bullpen_snapshot),
            'recommended_story_focus': self.recommended_story_focus,
            'safe_time_context': self.safe_time_context,
        }


def _as_dict(obj) -> dict | None:
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj
    to_dict = getattr(obj, 'to_dict', None)
    if callable(to_dict):
        return to_dict()
    return None


def _sub(team_context, key) -> dict:
    if not isinstance(team_context, dict):
        return {}
    value = team_context.get(key)
    return value if isinstance(value, dict) else {}


def _availability_snapshot(team_context) -> dict:
    """Available / limited / unavailable relievers — read from optionality layer."""
    opt = _sub(team_context, 'bullpen_optionality_context')
    return {
        'context_available': bool(opt.get('context_available')),
        'available_arms_count': opt.get('available_arms_count'),
        'monitor_arms_count': opt.get('monitor_arms_count'),
        'limited_arms_count': opt.get('limited_arms_count'),
        'restricted_arms_count': opt.get('restricted_arms_count'),
        'unavailable_arms_count': opt.get('unavailable_arms_count'),
        'unknown_status_count': opt.get('unknown_status_count'),
        'optionality_band': opt.get('optionality_band'),
    }


def _workload_snapshot(team_context) -> dict:
    """Bullpen innings / recent workload / concentrated usage — read, not recomputed."""
    conc = _sub(team_context, 'bullpen_concentration_context')
    rotation = _sub(team_context, 'rotation_context')
    return {
        'context_available': 'concentration_band' in conc,
        'bullpen_workload_total_10d': conc.get('bullpen_workload_total_10d'),
        'bullpen_workload_appearances_10d': conc.get('bullpen_workload_appearances_10d'),
        'top_three_workload_share_10d': conc.get('top_three_workload_share_10d'),
        'concentration_band': conc.get('concentration_band'),
        'window_days': conc.get('window_days'),
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
    }


def _bullpen_snapshot(team_context) -> dict:
    """Coverage depth / clean options / leverage flexibility / role stability."""
    opt = _sub(team_context, 'bullpen_optionality_context')
    stability = _sub(team_context, 'role_stability_context')
    injury = _sub(team_context, 'injury_context')
    clean = opt.get('clean_workload_options')
    secondary = opt.get('secondary_options')
    return {
        'context_available': bool(opt.get('context_available')),
        'clean_options_count': len(clean) if isinstance(clean, list) else None,
        'secondary_options_count': len(secondary) if isinstance(secondary, list) else None,
        'practical_close_game_paths_count': opt.get('practical_close_game_paths_count'),
        'optionality_band': opt.get('optionality_band'),
        'stability_band': stability.get('stability_band'),
        'core_retention_count': stability.get('core_retention_count'),
        'depth_pressure_band': injury.get('depth_pressure_band'),
        'inactive_bullpen_arms_count': injury.get('inactive_bullpen_arms_count'),
    }


def _bullpen_state_focus(availability_snapshot, workload_snapshot) -> str | None:
    """A secondary focus implied by the current bullpen state, or None."""
    optionality_band = availability_snapshot.get('optionality_band')
    concentration_band = workload_snapshot.get('concentration_band')
    if optionality_band in _THIN_BANDS:
        return FOCUS_BULLPEN_AVAILABILITY
    if concentration_band in _CONCENTRATED_BANDS:
        return FOCUS_WORKLOAD_PRESSURE
    if optionality_band in _DEEP_BANDS:
        return FOCUS_COVERAGE_FLEXIBILITY
    return None


def _recommended_story_focus(narrative: NarrativeContext, availability_snapshot,
                             workload_snapshot) -> str:
    if narrative.primary_story == TAG_INSUFFICIENT_CONTEXT:
        return FOCUS_INSUFFICIENT_CONTEXT
    game_focus = _FOCUS_BY_PRIMARY.get(narrative.primary_story, FOCUS_GAME_CONTEXT)
    bullpen_focus = _bullpen_state_focus(availability_snapshot, workload_snapshot)
    if narrative.story_priority in (PRIORITY_CRITICAL, PRIORITY_HIGH) \
            and bullpen_focus is not None and bullpen_focus != game_focus:
        return FOCUS_MULTIPLE_STORYLINES
    return game_focus


def _safe_time_context(narrative: NarrativeContext, has_completed_game,
                       has_team_context) -> str:
    # A valid (non-insufficient) narrative already passed the confidence gate,
    # so the writer may reference the most recent game.
    if narrative.primary_story != TAG_INSUFFICIENT_CONTEXT:
        return TIME_AFTER_MOST_RECENT_GAME
    # Otherwise stick to present-tense status if we know anything at all.
    if has_team_context or has_completed_game:
        return TIME_CURRENT_STATUS
    return TIME_INSUFFICIENT_CONTEXT


def build_narrative_feed(
    team_id,
    *,
    reference_date=None,
    completed_game_context=None,
    team_context=None,
) -> NarrativeFeed:
    """Assemble one deterministic NarrativeFeed for a team.

    Reads (never recomputes) the existing layers: the team's most recent
    CompletedGameContext, its NarrativeContext (derived deterministically), and
    its bullpen intelligence via ``build_team_bullpen_context``. Pass
    ``completed_game_context`` and/or ``team_context`` to inject already-loaded
    intelligence (and to keep the builder pure for tests); when omitted they are
    read on demand inside an app context.
    """
    if completed_game_context is None:
        completed_game_context = _load_latest_completed_game_context(team_id)
    if team_context is None:
        team_context = _load_team_context(team_id, reference_date)

    completed_dict = _as_dict(completed_game_context)
    narrative = build_narrative_context(completed_game_context)

    availability_snapshot = _availability_snapshot(team_context)
    workload_snapshot = _workload_snapshot(team_context)
    bullpen_snapshot = _bullpen_snapshot(team_context)

    has_team_context = isinstance(team_context, dict) and team_context.get('team_id') is not None

    resolved_team_id = team_id if team_id is not None else narrative.team_id

    return NarrativeFeed(
        team_id=resolved_team_id,
        game_pk=narrative.game_pk,
        feed_version=FEED_VERSION,
        confidence=narrative.confidence,
        story_priority=narrative.story_priority,
        game_importance=narrative.game_importance,
        primary_narrative=narrative.primary_story,
        secondary_narrative=narrative.secondary_story,
        headline_key=narrative.headline_key,
        summary_key=narrative.summary_key,
        supporting_observations=list(narrative.supporting_observations),
        supporting_facts=dict(narrative.supporting_facts),
        completed_game_context=completed_dict,
        narrative_context=narrative.to_dict(),
        availability_snapshot=availability_snapshot,
        workload_snapshot=workload_snapshot,
        bullpen_snapshot=bullpen_snapshot,
        recommended_story_focus=_recommended_story_focus(
            narrative, availability_snapshot, workload_snapshot
        ),
        safe_time_context=_safe_time_context(
            narrative, completed_dict is not None, has_team_context
        ),
        generated_at=utc_now_naive(),
    )


def _load_latest_completed_game_context(team_id):
    """Read the team's most recent CompletedGameContext row (single query)."""
    from models.completed_game_context import CompletedGameContext

    return (
        CompletedGameContext.query
        .filter_by(team_id=team_id)
        .order_by(CompletedGameContext.game_date.desc(),
                  CompletedGameContext.game_pk.desc())
        .first()
    )


def _load_team_context(team_id, reference_date):
    """Read the team's bullpen intelligence via the existing orchestrator."""
    from services.bullpen_context import build_team_bullpen_context

    return build_team_bullpen_context(team_id, reference_date=reference_date)
