"""Shared base for Story Writers (COIN Phase 4).

Story Writers are translators, not analysts. Each one receives a single
``NarrativeFeed`` (the object built in Phase 3.75) and turns it into
human-readable baseball language. They make NO baseball decisions: they never
query an engine, the database, or the completed-game/narrative layers; they
never compute a priority, confidence, observation, or story focus. Every such
decision was already made upstream and is simply read off the feed.

This module deliberately imports nothing from ``services`` or ``models`` — the
only input a writer is allowed is the feed payload (a NarrativeFeed dataclass or
its ``to_dict``). Phrasing is template-driven and deterministic: the same feed
always yields the same prose. Temporal language is gated strictly on the feed's
``safe_time_context``; writers never invent tomorrow / tonight / next-game framing.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


# Safe relative-time framing. These mirror the narrative_feed_builder vocabulary,
# but are redeclared here so writers depend on the feed payload alone.
TIME_AFTER_MOST_RECENT_GAME = 'AFTER_MOST_RECENT_GAME'
TIME_ENTERING_TODAY = 'ENTERING_TODAY'
TIME_CURRENT_STATUS = 'CURRENT_STATUS'
TIME_INSUFFICIENT_CONTEXT = 'INSUFFICIENT_CONTEXT'

_TIME_PREFIX = {
    TIME_AFTER_MOST_RECENT_GAME: 'After their most recent game',
    TIME_ENTERING_TODAY: 'Entering today',
    TIME_CURRENT_STATUS: 'Currently',
    TIME_INSUFFICIENT_CONTEXT: '',
}

CONFIDENCE_LOW = 'LOW'
PRIMARY_INSUFFICIENT = 'insufficient_context'

# Short headlines keyed by the feed's headline_key (translation, not a decision).
_HEADLINES = {
    'lost_game_shape': 'Lead surrendered late',
    'protected_game_shape': 'Lead protected',
    'bullpen_stabilized': 'Bullpen slammed the door',
    'bullpen_kept_team_alive': 'Bullpen kept it alive',
    'bullpen_overexposed': 'Bullpen stretched thin',
    'late_pressure_accumulated': 'Late traffic mounted',
    'starter_carried_game': 'Starter carried the load',
    'insufficient_context': 'Not enough detail yet',
}
_DEFAULT_HEADLINE = 'Bullpen note'

# Plain-language reads of the bullpen-state bands carried on the feed snapshots.
_OPTIONALITY_PHRASE = {
    'thin': 'thin on rested arms',
    'narrow': 'short on clean options',
    'flexible': 'in flexible shape',
    'deep': 'deep on options',
}
_CONCENTRATION_PHRASE = {
    'concentrated': 'leaning on a few arms',
    'narrow': 'leaning heavily on a few arms',
}


@dataclass(frozen=True)
class StoryDraft:
    """A rendered story: prose plus the governance metadata it was written under."""

    writer: str
    headline: str
    body: str
    confidence: str
    story_priority: str
    game_importance: str
    safe_time_context: str
    recommended_story_focus: str
    primary_narrative: str
    team_id: int | None
    game_pk: int | None

    @property
    def text(self) -> str:
        return f'{self.headline}\n{self.body}'

    def to_dict(self) -> dict:
        return {
            'writer': self.writer,
            'headline': self.headline,
            'body': self.body,
            'confidence': self.confidence,
            'story_priority': self.story_priority,
            'game_importance': self.game_importance,
            'safe_time_context': self.safe_time_context,
            'recommended_story_focus': self.recommended_story_focus,
            'primary_narrative': self.primary_narrative,
            'team_id': self.team_id,
            'game_pk': self.game_pk,
        }


def _runs_word(n) -> str:
    return f'{n} run' if n == 1 else f'{n} runs'


def _ordinal(n) -> str | None:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return None
    if 10 <= (n % 100) <= 20:
        suffix = 'th'
    else:
        suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
    return f'{n}{suffix}'


class BaseStoryWriter:
    """Common feed accessors and shared sentence templates.

    Subclasses implement ``write()`` and compose the shared helpers into their
    own style. They must not reach beyond ``self._feed``.
    """

    writer_name = 'base'

    def __init__(self, feed):
        self._feed = self._coerce(feed)

    @staticmethod
    def _coerce(feed) -> dict:
        if isinstance(feed, dict):
            return dict(feed)
        to_dict = getattr(feed, 'to_dict', None)
        if callable(to_dict):
            return to_dict()
        raise TypeError('Story writers require a NarrativeFeed or its dict form')

    # ── Read-only feed accessors ──────────────────────────────────────────────
    def _get(self, key, default=None):
        return self._feed.get(key, default)

    def confidence(self) -> str:
        return self._get('confidence', CONFIDENCE_LOW)

    def story_priority(self) -> str:
        return self._get('story_priority', 'LOW')

    def game_importance(self) -> str:
        return self._get('game_importance', 'LOW')

    def primary_narrative(self) -> str:
        return self._get('primary_narrative', PRIMARY_INSUFFICIENT)

    def secondary_narrative(self):
        return self._get('secondary_narrative')

    def headline_key(self) -> str:
        return self._get('headline_key', PRIMARY_INSUFFICIENT)

    def safe_time_context(self) -> str:
        return self._get('safe_time_context', TIME_CURRENT_STATUS)

    def recommended_story_focus(self) -> str:
        return self._get('recommended_story_focus', PRIMARY_INSUFFICIENT)

    def supporting_facts(self) -> dict:
        facts = self._get('supporting_facts')
        return facts if isinstance(facts, dict) else {}

    def fact(self, key, default=None):
        return self.supporting_facts().get(key, default)

    def availability_snapshot(self) -> dict:
        snap = self._get('availability_snapshot')
        return snap if isinstance(snap, dict) else {}

    def workload_snapshot(self) -> dict:
        snap = self._get('workload_snapshot')
        return snap if isinstance(snap, dict) else {}

    def is_low_confidence(self) -> bool:
        return (
            self.confidence() == CONFIDENCE_LOW
            or self.primary_narrative() == PRIMARY_INSUFFICIENT
        )

    # ── Shared translation helpers ────────────────────────────────────────────
    def time_prefix(self) -> str:
        return _TIME_PREFIX.get(self.safe_time_context(), '')

    def headline_text(self) -> str:
        return _HEADLINES.get(self.headline_key(), _DEFAULT_HEADLINE)

    def _start(self, rest: str) -> str:
        """Open a sentence with the feed's permitted time framing (or none)."""
        rest = rest.strip()
        prefix = self.time_prefix()
        if prefix:
            return f'{prefix}, {rest}.'
        return rest[:1].upper() + rest[1:] + '.'

    def lead_sentence(self) -> str:
        primary = self.primary_narrative()
        if self.is_low_confidence():
            return self._lead_insufficient()
        builder = {
            'lost_game_shape': self._lead_lost,
            'protected_game_shape': self._lead_protected,
            'bullpen_kept_team_alive': self._lead_kept_alive,
            'bullpen_overexposed': self._lead_overexposed,
            'late_pressure_accumulated': self._lead_late_pressure,
            'starter_covered_bullpen': self._lead_starter_covered,
        }.get(primary)
        return builder() if builder is not None else self._lead_insufficient()

    def _lead_lost(self) -> str:
        lead = self.fact('largest_lead')
        late = self.fact('late_runs_allowed')
        inning = _ordinal(self.fact('bullpen_entry_inning'))
        clause = 'the bullpen inherited '
        clause += f'a {lead}-run lead' if lead else 'a lead'
        if inning:
            clause += f' in the {inning} inning'
        clause += " but couldn't protect it"
        if late:
            clause += f', allowing {_runs_word(late)} over the late innings'
        clause += ', turning a strong start into a difficult finish'
        return self._start(clause)

    def _lead_protected(self) -> str:
        lead = self.fact('largest_lead')
        late = self.fact('late_runs_allowed')
        inning = _ordinal(self.fact('bullpen_entry_inning'))
        clause = 'the bullpen protected '
        clause += f'a {lead}-run lead' if lead else 'the lead'
        if inning:
            clause += f' from the {inning} inning on'
        if late == 0:
            clause += ' without giving anything back'
        clause += ', closing out the win'
        return self._start(clause)

    def _lead_kept_alive(self) -> str:
        deficit = self.fact('largest_deficit')
        clause = 'the bullpen held the line'
        if deficit:
            clause += f' after the team fell behind by {deficit}'
        clause += ', keeping it close enough to complete the comeback'
        return self._start(clause)

    def _lead_overexposed(self) -> str:
        late = self.fact('late_runs_allowed')
        clause = 'a short start forced the bullpen to cover heavy innings'
        if late:
            clause += f', including {_runs_word(late)} late'
        return self._start(clause)

    def _lead_late_pressure(self) -> str:
        late = self.fact('runs_allowed_innings_7_to_9')
        clause = 'the bullpen pitched through repeated late traffic'
        if late:
            clause += f', allowing {_runs_word(late)} across the 7th through 9th'
        return self._start(clause)

    def _lead_starter_covered(self) -> str:
        return self._start(
            "the starter worked deep and kept the bullpen's exposure light"
        )

    def _lead_insufficient(self) -> str:
        return self._start(
            "there isn't enough completed-game detail to characterize the "
            "bullpen's most recent work"
        )

    def bullpen_state_clause(self) -> str | None:
        """A present-tense, time-free read of the bullpen-state bands, or None."""
        optionality = self.availability_snapshot().get('optionality_band')
        concentration = self.workload_snapshot().get('concentration_band')
        if optionality in _OPTIONALITY_PHRASE:
            return f'the bullpen profiles as {_OPTIONALITY_PHRASE[optionality]}'
        if concentration in _CONCENTRATION_PHRASE:
            return f'the bullpen is {_CONCENTRATION_PHRASE[concentration]}'
        return None

    def short_summary(self) -> str:
        """A terse clause for compact surfaces (dashboard)."""
        if self.is_low_confidence():
            return 'no completed-game read yet'
        primary = self.primary_narrative()
        lead = self.fact('largest_lead')
        late79 = self.fact('runs_allowed_innings_7_to_9')
        if primary == 'lost_game_shape':
            return f'blew a {lead}-run lead late' if lead else "couldn't hold the lead"
        if primary == 'protected_game_shape':
            return f'protected a {lead}-run lead' if lead else 'protected the lead'
        if primary == 'bullpen_kept_team_alive':
            return 'kept the comeback alive'
        if primary == 'bullpen_overexposed':
            return 'covered heavy innings on a short start'
        if primary == 'late_pressure_accumulated':
            return f'worked through {_runs_word(late79)} late' if late79 else 'worked through late traffic'
        if primary == 'starter_covered_bullpen':
            return 'barely used behind a deep start'
        return 'no completed-game read yet'

    def _draft(self, headline: str, body: str) -> StoryDraft:
        return StoryDraft(
            writer=self.writer_name,
            headline=headline,
            body=body,
            confidence=self.confidence(),
            story_priority=self.story_priority(),
            game_importance=self.game_importance(),
            safe_time_context=self.safe_time_context(),
            recommended_story_focus=self.recommended_story_focus(),
            primary_narrative=self.primary_narrative(),
            team_id=self._get('team_id'),
            game_pk=self._get('game_pk'),
        )

    def write(self) -> StoryDraft:  # pragma: no cover - interface
        raise NotImplementedError
