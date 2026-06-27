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

# Short descriptors of the bullpen's standing, written so they read after both
# "the relief corps is ___" and "leaves the relief corps ___". Band-supported.
_OPTIONALITY_PHRASE = {
    'thin': 'down to fewer rested options',
    'narrow': 'down to a short list of clean arms',
    'flexible': 'in good shape',
    'deep': 'deep in fresh arms',
}
_CONCENTRATION_PHRASE = {
    'concentrated': 'leaning on a few arms',
    'narrow': 'leaning heavily on a few arms',
}

# Plain-language reads of the narrative's observation identifiers. Only the
# identifiers actually present on the feed are translated; nothing is invented.
_OBSERVATION_PHRASES = {
    'starter_created_game_shape': 'The starter set the bullpen up to finish the game.',
    'deep_start': 'The starter went deep and held down the bullpen workload.',
    'lead_entering_bullpen': 'The bullpen took over with a lead in hand.',
    'deficit_entering_bullpen': 'The bullpen took over while trailing.',
    'bullpen_preserved_lead': 'The relievers held the lead.',
    'bullpen_lost_lead': 'The relievers could not hold the lead.',
    'late_runs_allowed': 'The damage came after the starter exited.',
    'multiple_late_runs': 'The runs piled up late rather than in one moment.',
    'comeback_completed': 'The offense finished the comeback the bullpen kept alive.',
    'bullpen_worked_long': 'The bullpen was asked to cover a long runway.',
    'turning_point_identified': 'One late inning swung the game.',
}

# Near-duplicate observations are merged into a single line so the "why" section
# explains rather than repeats. Each group fires only when 2+ of its members are
# present; its members are then consumed and not emitted individually.
_OBSERVATION_GROUPS = (
    (frozenset({'starter_created_game_shape', 'deep_start'}),
     'The starter went deep and set the bullpen up to finish the game.'),
    (frozenset({'late_runs_allowed', 'multiple_late_runs'}),
     'The damage came after the starter exited and piled up late.'),
)


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
    """Format innings for evidence bullets ('6.0', '0.2') without altering it."""
    if value is None:
        return None
    try:
        return f'{float(value):.1f}'
    except (TypeError, ValueError):
        return None


_NUMBER_WORDS = {
    0: 'no', 1: 'one', 2: 'two', 3: 'three', 4: 'four', 5: 'five', 6: 'six',
    7: 'seven', 8: 'eight', 9: 'nine', 10: 'ten', 11: 'eleven', 12: 'twelve',
}


def _num(value) -> str | None:
    """Small counts as words for prose ('four'); larger ones stay numeric."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return _NUMBER_WORDS.get(n, str(n))


def _innings_word(value) -> str | None:
    """Whole innings as a word ('six'); fractional stays as a number ('5.1')."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return _num(int(f)) if f.is_integer() else f'{f:.1f}'


def _join_names(names) -> str:
    names = [n for n in names if n]
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f'{names[0]} and {names[1]}'
    return ', '.join(names[:-1]) + f', and {names[-1]}'


def _sentence(text: str) -> str:
    """Capitalize and terminate a standalone (non-leading) sentence."""
    text = text.strip()
    return text[:1].upper() + text[1:] + '.'


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
            clause += f' after {self._team_subject()} fell behind by {deficit}'
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

    # ── Composition fact accessors (evidence first, then narrative facts) ──────
    def _team_name(self) -> str | None:
        """The club's display name from the package, or None when absent."""
        completed = self._get('completed_game_context')
        name = completed.get('team_name') if isinstance(completed, dict) else None
        return name or None

    def _team_subject(self) -> str:
        # Prefer the club name. The story composers go name-led and avoid a generic
        # noun entirely when the name is missing; only the brief's recap needs a
        # last-resort subject, and "the club" is the honest one (never invent a name
        # or assert home/away we may not know).
        return self._team_name() or 'the club'

    def _team_possessive(self) -> str:
        team = self._team_subject()
        return team + "'" if team.endswith('s') else team + "'s"

    def _starter_name(self):
        return self._starter().get('name')

    def _starter_innings_word(self):
        return _innings_word(self._starter().get('innings'))

    def _key_relief_names(self) -> list[str]:
        appearances = self.evidence_block('key_relief_appearances') or []
        return [a['name'] for a in appearances if isinstance(a, dict) and a.get('name')]

    def _largest_lead_value(self):
        block = (self.evidence_block('largest_lead') or {}).get('runs')
        return block if block is not None else self.fact('largest_lead')

    def _largest_deficit_value(self):
        block = (self.evidence_block('largest_deficit') or {}).get('runs')
        return block if block is not None else self.fact('largest_deficit')

    def _late_runs_value(self):
        block = (self.evidence_block('late_runs') or {}).get('late_runs_allowed')
        return block if block is not None else self.fact('late_runs_allowed')

    def _entry_inning_value(self):
        block = (self.evidence_block('bullpen_entry_situation') or {}).get('inning')
        return block if block is not None else self.fact('bullpen_entry_inning')

    def _entry_deficit_value(self):
        block = (self.evidence_block('bullpen_entry_situation') or {}).get('deficit_when_entered')
        return block if block is not None else self.fact('deficit_when_bullpen_entered')

    # ── Priority-aware body composition ───────────────────────────────────────
    def compose_body(self) -> str:
        """Compose a coherent, priority-weighted, evidence-backed story body.

        CRITICAL adds an opening-context sentence and a consequence; HIGH keeps
        the consequence; MEDIUM stays to the narrative; LOW is the neutral
        fallback. Every clause is omitted when its fact is absent.
        """
        if self.is_low_confidence():
            return self._lead_insufficient()
        priority = self.story_priority()
        include_opening = priority == 'CRITICAL'
        include_consequence = priority in ('CRITICAL', 'HIGH')
        composer = {
            'lost_game_shape': self._compose_lost,
            'protected_game_shape': self._compose_protected,
            'bullpen_kept_team_alive': self._compose_kept_alive,
            'bullpen_overexposed': self._compose_overexposed,
        }.get(self.primary_narrative())
        if composer is None:
            return self.lead_sentence()
        return composer(include_opening, include_consequence)

    def _compose_lost(self, include_opening, include_consequence) -> str:
        # Always a CRITICAL read: build the lead, lose it, name the damage. Varied
        # rhythm (long, short, medium); no team-noun fallbacks, no "couldn't hold".
        team = self._team_name()
        starter, ipw = self._starter_name(), self._starter_innings_word()
        lead, late = self._largest_lead_value(), self._late_runs_value()
        names = self._key_relief_names()

        if not (starter and ipw and lead):
            base = f'a {_num(lead)}-run lead' if lead else 'a lead'
            line = f'{base} slipped away in the late innings'
            if late:
                line += f', with {_num(late)} runs crossing'
            return self._start(line)

        if team:
            opener = f'{starter} gave {team} {ipw} strong innings and a {_num(lead)}-run lead to protect'
        else:
            opener = f"{starter}'s {ipw} strong innings staked a {_num(lead)}-run lead heading to the late innings"
        sentences = [self._start(opener), "It didn't last."]

        closing = ''
        if late:
            closing = f'{_num(late)} late runs turned the game'
            if names:
                closing += f', with {_join_names(names)} surrendering the decisive blows'
        elif names:
            closing = f'{_join_names(names)} surrendered the decisive blows'
        if closing:
            sentences.append(_sentence(closing))
        return ' '.join(sentences)

    def _compose_protected(self, include_opening, include_consequence) -> str:
        team = self._team_name()
        starter, ipw = self._starter_name(), self._starter_innings_word()
        lead, late = self._largest_lead_value(), self._late_runs_value()
        inning = _ordinal(self._entry_inning_value())
        names = self._key_relief_names()
        sentences = []

        if include_opening and starter and ipw and lead:
            who = team or 'a lead'
            opener = (f'{starter} handed {team} a {_num(lead)}-run lead after {ipw} innings'
                      if team else
                      f'{starter} worked {ipw} innings and handed off a {_num(lead)}-run lead')
            sentences.append(self._start(opener))
            sentences.append('The bullpen brought it home.')
        elif starter and ipw and lead:
            opener = (f'{starter} worked {ipw} innings and left with a {_num(lead)}-run lead, '
                      f'and the bullpen brought it home')
            sentences.append(self._start(opener))
        else:
            line = 'the bullpen protected '
            line += f'a {_num(lead)}-run lead' if lead else 'the lead'
            if inning:
                line += f' from the {inning} inning on'
            line += ', closing out the win'
            sentences.append(self._start(line))

        if include_consequence and names:
            tail = f'{_join_names(names)} slammed the door'
            if late == 0:
                tail += ' without a run crossing'
            sentences.append(_sentence(tail))
        return ' '.join(sentences)

    def _compose_kept_alive(self, include_opening, include_consequence) -> str:
        team = self._team_name()
        starter, ipw = self._starter_name(), self._starter_innings_word()
        deficit = self._entry_deficit_value() or self._largest_deficit_value()
        names = self._key_relief_names()
        sentences = []

        if starter and ipw and deficit:
            if team:
                opener = (f"{starter}'s {ipw} innings left {team} chasing a "
                          f'{_num(deficit)}-run deficit, but the bullpen kept it from growing')
            else:
                opener = (f"{starter}'s {ipw} innings left a {_num(deficit)}-run deficit to "
                          f'erase, but the bullpen kept it from growing')
            sentences.append(self._start(opener))
        else:
            line = 'the bullpen kept the game within reach'
            if deficit:
                line += f' after a {_num(deficit)}-run deficit'
            sentences.append(self._start(line))

        if include_consequence:
            if names:
                sentences.append(_sentence(
                    f'{_join_names(names)} held the line, and the offense finished the rally'))
            else:
                sentences.append('The offense finished the rally.')
        return ' '.join(sentences)

    def _compose_overexposed(self, include_opening, include_consequence) -> str:
        # MEDIUM read: matter-of-fact, one sentence, no consequence pile-up.
        starter, ipw = self._starter_name(), self._starter_innings_word()
        late = self._late_runs_value()
        if starter and ipw:
            line = (f"{starter}'s {ipw}-inning start left the bullpen to cover the rest")
        else:
            line = 'a short start left the bullpen to cover the rest'
        if late:
            line += f', including {_num(late)} late {"run" if late == 1 else "runs"}'
        return self._start(line)

    def _bullpen_state_phrase(self) -> str | None:
        optionality = self.availability_snapshot().get('optionality_band')
        concentration = self.workload_snapshot().get('concentration_band')
        if optionality in _OPTIONALITY_PHRASE:
            return _OPTIONALITY_PHRASE[optionality]
        if concentration in _CONCENTRATION_PHRASE:
            return _CONCENTRATION_PHRASE[concentration]
        return None

    def bullpen_state_sentence(self) -> str | None:
        """A natural present-tense read of the bullpen's standing, or None."""
        if self.is_low_confidence():
            return None
        phrase = self._bullpen_state_phrase()
        return f'The relief corps is {phrase}.' if phrase else None

    def story_takeaway(self) -> str | None:
        """The closing "so what" — a factual baseball consequence, or None.

        Ties the game's finish to where the relief corps now stands. No
        prediction, no advice; falls back to the plain state read.
        """
        descriptor = self._bullpen_state_phrase()
        if descriptor is None:
            return None
        primary = self.primary_narrative()
        if primary == 'lost_game_shape':
            return f'That late collapse leaves the relief corps {descriptor}.'
        if primary == 'protected_game_shape':
            return f'The clean finish keeps the relief corps {descriptor}.'
        if primary == 'bullpen_kept_team_alive':
            return f'The comeback leaned on the bullpen, and the relief corps is {descriptor}.'
        return f'The relief corps is {descriptor}.'

    def brief_recap(self) -> str:
        """A single-sentence game recap for the morning brief (not the full story)."""
        team = self._team_subject()
        primary = self.primary_narrative()
        lead = self._largest_lead_value()
        deficit = self._entry_deficit_value() or self._largest_deficit_value()
        late = self._late_runs_value()
        if primary == 'lost_game_shape':
            clause = f'{team} carried '
            clause += f'a {_num(lead)}-run lead' if lead else 'a lead'
            clause += ' into the late innings and let it get away'
            if late:
                clause += f' on {_num(late)} late runs'
        elif primary == 'protected_game_shape':
            clause = f'{team} turned '
            clause += f'a {_num(lead)}-run lead' if lead else 'a lead'
            clause += ' into a win the bullpen never let slip'
        elif primary == 'bullpen_kept_team_alive':
            clause = f'{team} climbed out of'
            clause += f' a {_num(deficit)}-run hole' if deficit else ' a deficit'
            clause += ' the bullpen kept from growing'
        elif primary == 'bullpen_overexposed':
            clause = f'a short start put {self._team_possessive()} bullpen to work early'
        else:
            clause = f'{team} {self.short_summary()}'
        return self._start(clause)

    def brief_today_line(self) -> str | None:
        """The morning brief's bullpen read — causal when yesterday changed it."""
        descriptor = self._bullpen_state_phrase()
        if descriptor is None:
            return None
        primary = self.primary_narrative()
        if primary == 'lost_game_shape':
            return f"Yesterday's late damage leaves the relief corps {descriptor}."
        if primary == 'bullpen_overexposed':
            return f'The extra innings leave the relief corps {descriptor}.'
        return f'The relief corps is {descriptor}.'

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

    # ── Priority-driven section inclusion ─────────────────────────────────────
    def wants_observations(self) -> bool:
        # CRITICAL/HIGH carry the "Why BaseballOS sees it" list; MEDIUM does not.
        return not self.is_low_confidence() and self.story_priority() in ('CRITICAL', 'HIGH')

    def wants_evidence(self) -> bool:
        # CRITICAL/HIGH/MEDIUM prove the read with evidence; LOW does not.
        return not self.is_low_confidence() and self.story_priority() in ('CRITICAL', 'HIGH', 'MEDIUM')

    # ── Observation / evidence sections ───────────────────────────────────────
    def observation_lines(self) -> list[str]:
        """Translate present observations to plain language, merging near-duplicates."""
        if self.is_low_confidence():
            return []
        present = [o for o in self.supporting_observations() if o in _OBSERVATION_PHRASES]
        present_set = set(present)
        consumed: set[str] = set()
        lines: list[str] = []
        for observation in present:
            if observation in consumed:
                continue
            merged = None
            for members, phrase in _OBSERVATION_GROUPS:
                if observation in members and len(members & present_set) >= 2:
                    merged = phrase
                    consumed |= members
                    break
            line = merged if merged is not None else _OBSERVATION_PHRASES[observation]
            if line not in lines:
                lines.append(line)
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
        """Compact evidence bullets that tell the baseball story, in order.

        Order: starter -> largest lead/deficit -> bullpen entry -> turning point
        -> late runs -> key relief -> clean options. Drawn only from
        evidence_blocks; capped at five.
        """
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

        # "Largest lead / deficit" is one tier: show the side the story turns on,
        # so the bullet count stays tight and the key late facts survive.
        largest_lead = (blocks.get('largest_lead') or {}).get('runs')
        largest_deficit = (blocks.get('largest_deficit') or {}).get('runs')
        primary = self.primary_narrative()
        if primary in ('lost_game_shape', 'protected_game_shape') and largest_lead:
            lines.append(f'Largest lead: {largest_lead}')
        elif primary == 'bullpen_kept_team_alive' and largest_deficit:
            lines.append(f'Largest deficit: {largest_deficit}')
        elif largest_lead:
            lines.append(f'Largest lead: {largest_lead}')
        elif largest_deficit:
            lines.append(f'Largest deficit: {largest_deficit}')

        entry = blocks.get('bullpen_entry_situation') or {}
        if entry.get('inning') is not None:
            text = f"Bullpen entered in the {_ordinal(entry['inning'])}"
            if entry.get('lead_when_entered'):
                text += f" with a {entry['lead_when_entered']}-run lead"
            elif entry.get('deficit_when_entered'):
                text += f" trailing by {entry['deficit_when_entered']}"
            lines.append(text)

        turning = (blocks.get('turning_point') or {}).get('inning')
        if turning is not None:
            lines.append(f'Turning point: {_ordinal(turning)} inning')

        late = (blocks.get('late_runs') or {}).get('late_runs_allowed')
        if late is not None:
            lines.append(f'Late runs allowed: {late}')

        appearances = blocks.get('key_relief_appearances') or []
        formatted = [self._appearance_line(a) for a in appearances[:3]]
        formatted = [line for line in formatted if line]
        if formatted:
            lines.append('Key relief: ' + '; '.join(formatted))

        names = self.available_reliever_names()
        if names:
            lines.append('Clean options: ' + ', '.join(names[:4]))

        deduped = list(dict.fromkeys(lines))  # preserve order, drop any repeats
        return deduped[:5]

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
