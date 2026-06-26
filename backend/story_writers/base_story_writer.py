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

from dataclasses import dataclass, field
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

# Plain-language reads of the narrative's observation identifiers. Only the
# identifiers actually present on the feed are translated; nothing is invented.
_OBSERVATION_PHRASES = {
    'starter_created_game_shape': 'The starter created the conditions for the bullpen to finish the game.',
    'deep_start': 'The starter reduced the bullpen burden.',
    'lead_entering_bullpen': 'The bullpen entered with a lead.',
    'deficit_entering_bullpen': 'The bullpen entered while trailing.',
    'bullpen_preserved_lead': 'The bullpen protected the lead.',
    'bullpen_lost_lead': 'The bullpen did not protect the lead.',
    'late_runs_allowed': 'Runs came after the starter exited.',
    'multiple_late_runs': 'Damage accumulated late rather than from one isolated moment.',
    'comeback_completed': 'The team completed its comeback.',
    'bullpen_worked_long': 'The bullpen was asked to cover a long runway.',
    'turning_point_identified': 'The game turned on a specific late inning.',
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
    observations: list[str] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)

    @property
    def text(self) -> str:
        # Preserved: the core text is headline + body. The structured observation
        # and evidence sections are separate fields (rendered by consumers).
        return f'{self.headline}\n{self.body}'

    @property
    def rendered_text(self) -> str:
        """The full structured render: story, the 'why', and the evidence."""
        parts = [self.headline, '', self.body]
        if self.observations:
            parts += ['', 'Why BaseballOS sees it:']
            parts += [f'- {line}' for line in self.observations]
        if self.evidence:
            parts += ['', 'Evidence:']
            parts += [f'- {line}' for line in self.evidence]
        return '\n'.join(parts)

    def to_dict(self) -> dict:
        return {
            'writer': self.writer,
            'headline': self.headline,
            'body': self.body,
            'observations': list(self.observations),
            'evidence': list(self.evidence),
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


def _ip(value) -> str | None:
    """Format innings for prose ('6.0', '0.2') without altering the number."""
    if value is None:
        return None
    try:
        return f'{float(value):.1f}'
    except (TypeError, ValueError):
        return None


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

    def evidence_blocks(self) -> dict:
        blocks = self._get('evidence_blocks')
        return blocks if isinstance(blocks, dict) else {}

    def evidence_block(self, name) -> Any:
        return self.evidence_blocks().get(name)

    def supporting_observations(self) -> list:
        obs = self._get('supporting_observations')
        return obs if isinstance(obs, list) else []

    def available_reliever_names(self) -> list[str]:
        """Named rested/available arms from evidence, or [] when none are named."""
        blocks = self.evidence_blocks()
        relievers = blocks.get('available_relievers') or blocks.get('clean_options') or []
        return [r['name'] for r in relievers if isinstance(r, dict) and r.get('name')]

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

    def _starter(self) -> dict:
        block = self.evidence_block('starter_summary')
        return block if isinstance(block, dict) else {}

    def _starter_handoff_clause(self) -> str | None:
        """'after Logan Webb worked 6.0 innings' when known; else the entry inning."""
        starter = self._starter()
        name, ip = starter.get('name'), _ip(starter.get('innings'))
        if name and ip:
            return f'after {name} worked {ip} innings'
        inning = _ordinal(self.fact('bullpen_entry_inning'))
        return f'in the {inning} inning' if inning else None

    def _lead_lost(self) -> str:
        lead = self.fact('largest_lead')
        late = self.fact('late_runs_allowed')
        handoff = self._starter_handoff_clause()
        clause = 'the bullpen inherited '
        clause += f'a {lead}-run lead' if lead else 'a lead'
        if handoff:
            clause += f' {handoff}'
        clause += " but couldn't protect it"
        if late:
            clause += f', allowing {_runs_word(late)} over the late innings'
        clause += ', turning a strong start into a difficult finish'
        return self._start(clause)

    def _lead_protected(self) -> str:
        lead = self.fact('largest_lead')
        late = self.fact('late_runs_allowed')
        handoff = self._starter_handoff_clause()
        clause = 'the bullpen protected '
        clause += f'a {lead}-run lead' if lead else 'the lead'
        if handoff:
            clause += f' {handoff}'
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
        starter = self._starter()
        name, ip = starter.get('name'), _ip(starter.get('innings'))
        if name and ip:
            clause = f'a {ip}-inning start by {name} forced the bullpen to cover heavy innings'
        else:
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

    def _bullpen_state_phrase(self) -> str | None:
        optionality = self.availability_snapshot().get('optionality_band')
        concentration = self.workload_snapshot().get('concentration_band')
        if optionality in _OPTIONALITY_PHRASE:
            return _OPTIONALITY_PHRASE[optionality]
        if concentration in _CONCENTRATION_PHRASE:
            return _CONCENTRATION_PHRASE[concentration]
        return None

    def bullpen_state_clause(self) -> str | None:
        """A present-tense, time-free read of the bullpen-state bands, or None."""
        phrase = self._bullpen_state_phrase()
        return f'the bullpen profiles as {phrase}' if phrase else None

    def watch_sentence(self) -> str | None:
        """One safe, present-tense consequence line when late damage warrants it.

        No future/next-game framing — it states the current bullpen state left by
        the most recent late-game damage, and only fires when both are known.
        """
        if self.is_low_confidence():
            return None
        late = (self.evidence_block('late_runs') or {}).get('late_runs_allowed')
        phrase = self._bullpen_state_phrase()
        if late and phrase:
            return f'Recent late damage leaves the bullpen {phrase}.'
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

    # ── Observation / evidence sections ───────────────────────────────────────
    def observation_lines(self) -> list[str]:
        """Translate the present supporting observations into plain-language bullets."""
        if self.is_low_confidence():
            return []
        lines: list[str] = []
        for observation in self.supporting_observations():
            phrase = _OBSERVATION_PHRASES.get(observation)
            if phrase and phrase not in lines:
                lines.append(phrase)
        return lines[:4]

    def _appearance_line(self, appearance) -> str | None:
        if not isinstance(appearance, dict) or not appearance.get('name'):
            return None
        bits = []
        ip = _ip(appearance.get('innings'))
        if ip:
            bits.append(f'{ip} IP')
        if appearance.get('runs_allowed') is not None:
            bits.append(_runs_word(appearance['runs_allowed']))
        suffix = f" ({', '.join(bits)})" if bits else ''
        return f"{appearance['name']}{suffix}"

    def evidence_lines(self) -> list[str]:
        """Compact, prioritized evidence bullets drawn only from evidence_blocks."""
        if self.is_low_confidence():
            return []
        blocks = self.evidence_blocks()
        lines: list[str] = []

        starter = blocks.get('starter_summary') or {}
        if starter.get('name'):
            bits = [starter['name']]
            if _ip(starter.get('innings')):
                bits.append(f"{_ip(starter['innings'])} IP")
            if starter.get('pitch_count') is not None:
                bits.append(f"{starter['pitch_count']} pitches")
            lines.append('Starter: ' + ', '.join(bits))

        entry = blocks.get('bullpen_entry_situation') or {}
        if entry.get('inning') is not None:
            text = f"Bullpen entered in the {_ordinal(entry['inning'])}"
            if entry.get('lead_when_entered'):
                text += f" with a {entry['lead_when_entered']}-run lead"
            elif entry.get('deficit_when_entered'):
                text += f" trailing by {entry['deficit_when_entered']}"
            lines.append(text)

        largest_lead = (blocks.get('largest_lead') or {}).get('runs')
        if largest_lead:
            lines.append(f'Largest lead: {largest_lead}')
        largest_deficit = (blocks.get('largest_deficit') or {}).get('runs')
        if largest_deficit:
            lines.append(f'Largest deficit: {largest_deficit}')

        late = (blocks.get('late_runs') or {}).get('late_runs_allowed')
        if late is not None:
            lines.append(f'Late runs allowed: {late}')

        turning = (blocks.get('turning_point') or {}).get('inning')
        if turning is not None:
            lines.append(f'Turning point: {_ordinal(turning)} inning')

        appearances = blocks.get('key_relief_appearances') or []
        formatted = [self._appearance_line(a) for a in appearances[:3]]
        formatted = [line for line in formatted if line]
        if formatted:
            lines.append('Key relief: ' + '; '.join(formatted))

        names = self.available_reliever_names()
        if names:
            lines.append('Clean options: ' + ', '.join(names[:4]))

        return lines[:5]

    def _draft(self, headline: str, body: str, *, observations=None,
               evidence=None) -> StoryDraft:
        return StoryDraft(
            writer=self.writer_name,
            headline=headline,
            body=body,
            observations=list(observations or []),
            evidence=list(evidence or []),
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
