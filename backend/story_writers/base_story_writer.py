"""Shared base for Story Writers (COIN Phase 4).

Story Writers are translators, not analysts. Each one receives a single
``NarrativeFeed`` (the object built in Phase 3.75) and turns it into
human-readable baseball language. They make NO baseball decisions: they never
query an engine, the database, or the completed-game/narrative layers; they
never compute a priority, confidence, observation, or story focus. Every such
decision was already made upstream and is simply read off the feed.

This module deliberately imports no engines, database access, or models — the
only input a writer is allowed is the feed payload (a NarrativeFeed dataclass or
its ``to_dict``). Phrasing is template-driven and deterministic: the same feed
always yields the same prose. Temporal language is gated strictly on the feed's
``safe_time_context``; writers never invent tomorrow / tonight / next-game framing.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any

from services.editorial_voice_contract_v1 import render_baseball_consequence
from utils.baseball_innings import format_baseball_innings


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
    'lost_game_shape': (
        'Lead surrendered late',
        'Late lead slipped away',
        'Lead disappeared late',
    ),
    'protected_game_shape': (
        'Lead protected',
        'Late lead held',
        'Bullpen finished the lead',
        'Lead carried home',
        'Bullpen held the finish',
        'Late lead closed out',
    ),
    'bullpen_stabilized': (
        'Bullpen slammed the door',
        'Lead finished cleanly',
        'Late innings stayed quiet',
        'Late innings held firm',
        'Bullpen closed it down',
        'Quiet finish from the pen',
    ),
    'bullpen_kept_team_alive': (
        'Bullpen kept it alive',
        'Relievers left room for the rally',
        'Bullpen gave the comeback room',
    ),
    'bullpen_overexposed': (
        'Bullpen stretched thin',
        'Short start stretched the bullpen',
        'Bullpen had to cover',
        'Relievers had to cover early',
        'Bullpen drew the long assignment',
        'Short start made it a bullpen finish',
    ),
    'late_pressure_accumulated': (
        'Late traffic mounted',
        'Late innings got heavy',
        'Bullpen worked through traffic',
    ),
    'starter_carried_game': (
        'Starter carried the load',
        'Starter spared the bullpen',
        'Deep start lightened the load',
        'Starter gave the bullpen a shorter day',
        'Starter covered the hard part',
        'Deep start kept the bullpen light',
    ),
    'insufficient_context': ('Not enough detail yet',),
}
_DEFAULT_HEADLINE = 'Bullpen note'
_WRITER_HEADLINE_OFFSET = {
    'team_story': 0,
    'dashboard': 1,
    'morning_brief': 2,
}

_BULLPEN_STATE_CONSEQUENCE_BY_OPTIONALITY = {
    'thin': 'availability_narrowed',
    'narrow': 'availability_narrowed',
    'flexible': 'late_inning_margin',
    'deep': 'late_inning_margin',
}
_BULLPEN_STATE_CONSEQUENCE_BY_CONCENTRATION = {
    'concentrated': 'workload_concentration',
    'narrow': 'workload_concentration',
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
    """Format innings for public evidence bullets ('6.0', '0.2')."""
    return format_baseball_innings(value)


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
    formatted = format_baseball_innings(value)
    if not formatted:
        return None
    whole, _, outs = formatted.partition('.')
    if outs == '0':
        return _num(whole)
    return formatted


def _stable_index(count: int, *parts: Any) -> int:
    """Deterministic variant selection from feed identifiers."""
    if count <= 1:
        return 0
    numeric_total = 0
    for value in parts:
        try:
            numeric_total += int(value)
        except (TypeError, ValueError):
            continue
    if numeric_total:
        return numeric_total % count

    raw = '|'.join(str(part or '') for part in parts)
    if not raw:
        return 0
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    return int(digest[:8], 16) % count


def _variant(forms, index: int) -> str | None:
    if not forms:
        return None
    if isinstance(forms, str):
        return forms
    return forms[index % len(forms)]


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
        forms = _HEADLINES.get(self.headline_key(), (_DEFAULT_HEADLINE,))
        return _variant(
            forms,
            self._voice_index(
                len(forms),
                _WRITER_HEADLINE_OFFSET.get(self.writer_name, 0),
            ),
        ) or _DEFAULT_HEADLINE

    def _voice_index(self, count: int, *extra: Any) -> int:
        return _stable_index(
            count,
            self._get('team_id'),
            self._get('game_pk'),
            self.primary_narrative(),
            self.headline_key(),
            *extra,
        )

    def _voice_variant(self, forms, *extra: Any) -> str | None:
        return _variant(forms, self._voice_index(len(forms), *extra))

    def _stable_parts(self, *extra: Any) -> tuple[Any, ...]:
        return (
            self._get('team_id'),
            self._get('game_pk'),
            self.primary_narrative(),
            self.headline_key(),
            *extra,
        )

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
        if isinstance(block, dict) and block:
            return block
        completed = self._get('completed_game_context')
        if not isinstance(completed, dict):
            return {}
        return {
            'name': completed.get('starter_name'),
            'innings': completed.get('starter_ip'),
            'pitch_count': completed.get('starter_pitch_count'),
            'exit_inning': completed.get('starter_exit_inning'),
            'exit_score_for': completed.get('starter_exit_score_for'),
            'exit_score_against': completed.get('starter_exit_score_against'),
            'game_shape_created': completed.get('game_shape_created'),
        }

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
        anchor = self._starter_covered_anchor()
        if not anchor:
            return self._lead_insufficient()
        consequence = self._bullpen_consequence_line(
            fallback_key='workload_spread',
            extra_stable_parts=('starter_covered_bullpen',),
        )
        line = f'{anchor}, keeping the bullpen out of the heaviest innings'
        if consequence:
            return f'{self._start(line)} {consequence}'
        return self._start(line)

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

    def _starter_innings_text(self):
        return _ip(self._starter().get('innings'))

    def _starter_pitch_count(self):
        return self._starter().get('pitch_count')

    def _starter_covered_anchor(self) -> str | None:
        name = self._starter_name()
        if not name:
            return None
        innings = self._starter_innings_text()
        if innings:
            return f'{name} worked {innings} innings'
        pitches = self._starter_pitch_count()
        try:
            pitch_count = int(pitches)
        except (TypeError, ValueError):
            pitch_count = None
        if pitch_count and pitch_count > 0:
            return f'{name} threw {pitches} pitches'
        return None

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
        if block is not None:
            return block
        fact = self.fact('deficit_when_bullpen_entered')
        if fact is not None:
            return fact
        completed = self._get('completed_game_context')
        if isinstance(completed, dict):
            return completed.get('deficit_when_bullpen_entered')
        return None

    def _entry_lead_value(self):
        block = (self.evidence_block('bullpen_entry_situation') or {}).get('lead_when_entered')
        if block is not None:
            return block
        fact = self.fact('lead_when_bullpen_entered')
        if fact is not None:
            return fact
        completed = self._get('completed_game_context')
        if isinstance(completed, dict):
            return completed.get('lead_when_bullpen_entered')
        return None

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
            'starter_covered_bullpen': self._compose_starter_covered,
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

        variant = self._voice_index(2, 'lost_body')
        if variant == 0:
            if team:
                opener = f'{starter} gave {team} {ipw} strong innings and a {_num(lead)}-run lead to protect'
            else:
                opener = f"{starter}'s {ipw} strong innings staked a {_num(lead)}-run lead heading to the late innings"
        elif team:
            opener = f'{starter} gave {team} {ipw} innings and a {_num(lead)}-run lead'
        else:
            opener = f'{starter} worked {ipw} innings before a {_num(lead)}-run lead reached the bullpen'
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
        entry_lead = self._entry_lead_value()
        has_takeaway = bool(self.wants_observations() and self.story_takeaway())
        names = self._key_relief_names()
        sentences = []

        variant = self._voice_index(6, 'protected_body', lead, late, self._entry_inning_value())
        if include_opening and starter and ipw and lead:
            if variant in (0, 3):
                opener = (f'{starter} handed {team} a {_num(lead)}-run lead after {ipw} innings'
                          if team else
                          f'{starter} worked {ipw} innings and handed off a {_num(lead)}-run lead')
            elif variant in (1, 4):
                opener = (f'{starter} left {team} {_num(lead)} runs up after {ipw} innings'
                          if team else
                          f'{starter} left after {ipw} innings with a {_num(lead)}-run lead')
            else:
                opener = (f'{starter} built {team} a {_num(lead)}-run cushion over {ipw} innings'
                          if team else
                          f'{starter} built a {_num(lead)}-run cushion over {ipw} innings')
            sentences.append(self._start(opener))
            sentences.append(_variant((
                'The bullpen brought it home.',
                'The relievers handled the finish.',
                'The late innings held from there.',
            ), variant))
        elif starter and ipw and lead:
            if variant == 0:
                opener = (f'{starter} worked {ipw} innings and left with a {_num(lead)}-run lead, '
                          f'and the bullpen brought it home')
            elif variant == 1:
                if inning and entry_lead and not has_takeaway:
                    if self._entry_inning_value() and int(self._entry_inning_value()) >= 8:
                        opener = (f'{starter} reached the {inning} with a '
                                  f'{_num(entry_lead)}-run lead, and the bullpen finished it')
                    elif int(self._entry_inning_value()) == 6:
                        opener = (f'{starter} gave the bullpen {ipw} innings and a '
                                  f'{_num(entry_lead)}-run lead to carry home')
                    else:
                        opener = (f'{starter} left the bullpen a {_num(entry_lead)}-run lead '
                                  f'in the {inning}, and the relievers protected it')
                else:
                    opener = (f'{starter} handed off after {ipw} innings with a '
                              f'{_num(lead)}-run lead, and the bullpen finished it')
            elif variant == 2:
                opener = (f'{starter} gave the bullpen a {_num(lead)}-run lead after '
                          f'{ipw} innings, and the late innings held')
            elif variant == 3:
                opener = (f'{starter} left after {ipw} innings with {_num(lead)} runs of '
                          f'cushion, and the bullpen protected it')
            elif variant == 4:
                opener = (f'{starter} covered {ipw} innings before the bullpen took a '
                          f'{_num(lead)}-run lead to the finish')
            else:
                opener = (f'{starter} put a {_num(lead)}-run lead in place over {ipw} '
                          f'innings, and the relievers carried it home')
            sentences.append(self._start(opener))
        else:
            if variant in (0, 3):
                line = 'the bullpen protected '
                line += f'a {_num(lead)}-run lead' if lead else 'the lead'
                if inning:
                    line += f' from the {inning} inning on'
                line += ', closing out the win'
            elif variant in (1, 4):
                line = 'the relievers carried '
                line += f'a {_num(lead)}-run lead' if lead else 'the lead'
                line += ' through the finish'
            else:
                line = 'the late innings held around '
                line += f'a {_num(lead)}-run lead' if lead else 'the lead'
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
        entry_deficit = self._entry_deficit_value()
        inning = _ordinal(self._entry_inning_value())
        names = self._key_relief_names()
        sentences = []

        variant = self._voice_index(2, 'kept_alive_body')
        if starter and ipw and deficit:
            if variant == 0:
                if team:
                    opener = (f"{starter}'s {ipw} innings left {team} chasing a "
                              f'{_num(deficit)}-run deficit, but the bullpen kept it from growing')
                elif entry_deficit and inning:
                    opener = (f'{starter} worked {ipw} innings before the bullpen entered '
                              f'in the {inning} trailing by {_num(entry_deficit)}, '
                              f'and the deficit held there')
                elif inning:
                    opener = (f"{starter}'s {ipw} innings left a {_num(deficit)}-run deficit, "
                              f'and the bullpen kept it close from the {inning} on')
                else:
                    opener = (f"{starter}'s {ipw} innings left a {_num(deficit)}-run deficit to "
                              f'erase, but the bullpen kept it from growing')
            elif team:
                opener = (f'{starter} left {team} down {_num(deficit)} after {ipw} innings, '
                          f'and the bullpen held the game there')
            else:
                opener = (f'{starter} left a {_num(deficit)}-run deficit after {ipw} innings, '
                          f'and the bullpen held the game there')
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
        entry_inning = _ordinal(self._entry_inning_value())
        entry_lead = self._entry_lead_value()
        entry_deficit = self._entry_deficit_value()
        variant = self._voice_index(2, 'overexposed_body')
        if starter and ipw:
            if variant == 0:
                if entry_inning and entry_lead:
                    line = (f"{starter}'s {ipw}-inning start brought the bullpen in "
                            f'by the {entry_inning} with a {_num(entry_lead)}-run lead')
                elif entry_inning and entry_deficit:
                    line = (f"{starter}'s {ipw}-inning start brought the bullpen in "
                            f'by the {entry_inning} already trailing by {_num(entry_deficit)}')
                else:
                    line = f"{starter}'s {ipw}-inning start left the bullpen to cover the rest"
            else:
                line = f"{starter}'s {ipw}-inning start pushed the rest of the game to the bullpen"
        else:
            line = 'a short start left the bullpen to cover the rest'
        if late:
            line += f', including {_num(late)} late {"run" if late == 1 else "runs"}'
        return self._start(line)

    def _compose_starter_covered(self, include_opening, include_consequence) -> str:
        anchor = self._starter_covered_anchor()
        if not anchor:
            return self._lead_insufficient()
        consequence = self._bullpen_consequence_line(
            fallback_key='workload_spread',
            extra_stable_parts=('starter_covered_bullpen', 'body'),
        )
        completed = self._get('completed_game_context')
        starter_player_id = completed.get('starter_player_id') if isinstance(completed, dict) else None
        variant = self._voice_index(
            8,
            'starter_covered_body',
            self._starter_pitch_count(),
            self._entry_inning_value(),
            self._late_runs_value(),
            starter_player_id,
        )
        if variant == 0:
            line = f'{anchor}, keeping the bullpen out of the heaviest innings'
        elif variant == 1:
            line = f'{anchor}, so the bullpen only had to finish the shorter piece'
        elif variant == 2:
            line = f'{anchor}, leaving the bullpen with a shorter finish'
        elif variant == 3:
            line = f'{anchor}, and the bullpen handled the final stretch'
        elif variant == 4:
            line = f'{anchor}, keeping the relief workload short'
        elif variant == 5:
            line = f'{anchor}, giving the bullpen a lighter finish'
        elif variant == 6:
            line = f'{anchor}, leaving the bullpen with fewer innings to cover'
        else:
            line = f'{anchor}, before the bullpen took over for a shorter handoff'
        sentences = [self._start(line)]
        if consequence:
            sentences.append(consequence)
        return ' '.join(sentences)

    def _bullpen_consequence_key(self, fallback_key: str | None = None) -> str | None:
        optionality = self.availability_snapshot().get('optionality_band')
        concentration = self.workload_snapshot().get('concentration_band')
        if optionality in _BULLPEN_STATE_CONSEQUENCE_BY_OPTIONALITY:
            return _BULLPEN_STATE_CONSEQUENCE_BY_OPTIONALITY[optionality]
        if concentration in _BULLPEN_STATE_CONSEQUENCE_BY_CONCENTRATION:
            return _BULLPEN_STATE_CONSEQUENCE_BY_CONCENTRATION[concentration]
        return fallback_key

    def _bullpen_consequence_line(
        self,
        *,
        fallback_key: str | None = None,
        extra_stable_parts: tuple[Any, ...] = (),
    ) -> str | None:
        key = self._bullpen_consequence_key(fallback_key)
        if not key:
            return None
        line = render_baseball_consequence(
            key,
            stable_parts=self._stable_parts(
                self.availability_snapshot().get('optionality_band'),
                self.workload_snapshot().get('concentration_band'),
                *extra_stable_parts,
            ),
        )
        return line or None

    def bullpen_state_sentence(self) -> str | None:
        """A natural present-tense read of the bullpen's standing, or None."""
        if self.is_low_confidence():
            return None
        return self._bullpen_consequence_line()

    def story_takeaway(self) -> str | None:
        """The closing "so what" — a factual baseball consequence, or None.

        Ties the game's finish to where the relief corps now stands. No
        prediction, no advice; falls back to no tail when the feed has no state.
        """
        return self._bullpen_consequence_line(extra_stable_parts=('team_story',))

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
        elif primary == 'starter_covered_bullpen':
            anchor = self._starter_covered_anchor()
            if anchor:
                clause = f'{anchor} and kept the bullpen workload light'
            else:
                clause = f'{team} {self.short_summary()}'
        else:
            clause = f'{team} {self.short_summary()}'
        return self._start(clause)

    def brief_today_line(self) -> str | None:
        """The morning brief's bullpen read — causal when yesterday changed it."""
        consequence = self._bullpen_consequence_line(extra_stable_parts=('brief',))
        if consequence is None:
            return None
        primary = self.primary_narrative()
        if primary == 'lost_game_shape':
            return f'The late damage leaves the bullpen with less margin. {consequence}'
        if primary == 'bullpen_overexposed':
            return f'The extra bullpen work leaves less margin if the starter exits early. {consequence}'
        return consequence

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
            anchor = self._starter_covered_anchor()
            return f'kept the bullpen light after {anchor}' if anchor else 'has no completed-game read yet'
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
        -> late runs -> key relief -> available relievers. Drawn only from
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
            lines.append('Available relievers: ' + ', '.join(names[:4]))

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
