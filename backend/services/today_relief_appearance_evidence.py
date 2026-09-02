"""Authoritative relief-appearance evidence for the Today lead-story path.

This module performs narrowly scoped reads for each completed-game context. It
loads relief pitching lines for the exact MLB game and official game-side team.
For negative event claims it also requires the final, reconciled play-by-play
events that actually erased the lead or created the multi-inning late pressure;
aggregate box-line runs are never treated as causal attribution. It does not
infer historical ownership from a pitcher's current team, calculate workload,
or decide whether a story may be published.

The returned evidence is transient.  Callers receive copied context dicts with
``key_relief_appearances`` replaced by the authoritative database result; no
model row is changed and this module never commits a transaction.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Iterable

from sqlalchemy import and_, or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import (
    GamePlayByPlayEvent,
    PlayByPlayProcessedGame,
)
from utils.db import db


EVIDENCE_KEY = 'key_relief_appearances'

SCORING_EVENT_ROLE = 'claim_scoring_event_pitcher'
RELIEF_PARTICIPANT_ROLE = 'claim_supporting_relief_participant'

_SCORING_EVENT_CLAIM_TAGS = frozenset({
    'lost_game_shape',
    'late_pressure_accumulated',
})
_RELIEF_PARTICIPANT_CLAIM_TAGS = frozenset({
    'bullpen_kept_team_alive',
    'protected_game_shape',
    'bullpen_overexposed',
})


def enrich_today_contexts_with_relief_appearances(
    contexts: Iterable[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Return copied contexts enriched from batched authoritative reads.

    Rows qualify only when their stored appearance-team authority is resolved
    for the exact ``(game_pk, team_id)`` context and ``games_started`` explicitly
    marks a relief appearance.  Unknown role or team authority therefore fails
    closed. Participant receipts use stable MLB pitcher-id order. Event-linked
    receipts use first claim-event order from final play-by-play.
    """
    enriched: list[dict[str, Any]] = []
    identities: set[tuple[int, int]] = set()

    for context in contexts or []:
        if not isinstance(context, dict):
            raise TypeError('Today relief evidence requires context dictionaries')
        copied = dict(context)
        copied[EVIDENCE_KEY] = []
        enriched.append(copied)
        identity = _context_identity(copied)
        if identity is not None:
            identities.add(identity)

    if not identities:
        return enriched

    exact_identity_filters = [
        and_(
            GameLog.mlb_game_pk == game_pk,
            GameLog.appearance_team_id == team_id,
        )
        for game_pk, team_id in sorted(identities)
    ]
    rows = (
        db.session.query(GameLog, Pitcher)
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(
            or_(*exact_identity_filters),
            GameLog.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED,
            GameLog.games_started == 0,
        )
        .order_by(
            GameLog.mlb_game_pk.asc(),
            GameLog.appearance_team_id.asc(),
            Pitcher.mlb_id.asc(),
            GameLog.id.asc(),
        )
        .all()
    )

    by_identity: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for log, pitcher in rows:
        identity = (log.mlb_game_pk, log.appearance_team_id)
        if identity not in identities or not pitcher.full_name:
            continue
        by_identity[identity].append(_appearance_record(log, pitcher))

    event_links = _claim_event_links(enriched, by_identity)

    for context in enriched:
        identity = _context_identity(context)
        if identity is None:
            continue
        story_tag = context.get('bullpen_story_tag')
        appearances = by_identity.get(identity, ())
        if story_tag in _RELIEF_PARTICIPANT_CLAIM_TAGS:
            context[EVIDENCE_KEY] = [
                _with_participant_link(appearance)
                for appearance in appearances
            ]
            continue
        if story_tag in _SCORING_EVENT_CLAIM_TAGS:
            links_by_pitcher = event_links.get(identity, {})
            appearances_by_pitcher = {
                appearance.get('pitcher_mlb_id'): appearance
                for appearance in appearances
            }
            context[EVIDENCE_KEY] = [
                _with_scoring_event_link(
                    appearances_by_pitcher[pitcher_mlb_id],
                    linked_events,
                )
                for pitcher_mlb_id, linked_events in sorted(
                    links_by_pitcher.items(),
                    key=lambda item: min(event.event_index for event in item[1]),
                )
            ]
    return enriched


def _context_identity(context: dict[str, Any]) -> tuple[int, int] | None:
    game_pk = context.get('game_pk')
    team_id = context.get('team_id')
    if (
        isinstance(game_pk, bool)
        or isinstance(team_id, bool)
        or not isinstance(game_pk, int)
        or not isinstance(team_id, int)
    ):
        return None
    return game_pk, team_id


def _appearance_record(log: GameLog, pitcher: Pitcher) -> dict[str, Any]:
    return {
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'name': pitcher.full_name,
        'game_pk': log.mlb_game_pk,
        'appearance_team_id': log.appearance_team_id,
        'innings': log.innings_pitched,
        'innings_pitched_outs': log.innings_pitched_outs,
        'pitches_thrown': log.pitches_thrown,
        # Preserve unknown official values.  Missing data is not a zero-run line.
        'runs_allowed': log.runs_allowed,
    }


def _with_participant_link(appearance: dict[str, Any]) -> dict[str, Any]:
    record = dict(appearance)
    record['claim_evidence_role'] = RELIEF_PARTICIPANT_ROLE
    return record


def _with_scoring_event_link(
    appearance: dict[str, Any],
    events: list[GamePlayByPlayEvent],
) -> dict[str, Any]:
    record = dict(appearance)
    record['claim_evidence_role'] = SCORING_EVENT_ROLE
    record['claim_event_indexes'] = sorted({event.event_index for event in events})
    record['claim_event_innings'] = sorted({
        event.inning for event in events if event.inning is not None
    })
    source_play_ids = sorted({
        event.source_play_id for event in events if event.source_play_id
    })
    if source_play_ids:
        record['claim_source_play_ids'] = source_play_ids
    return record


def _claim_event_links(
    contexts: list[dict[str, Any]],
    appearances_by_identity: dict[tuple[int, int], list[dict[str, Any]]],
) -> dict[tuple[int, int], dict[int, list[GamePlayByPlayEvent]]]:
    claim_contexts = {
        identity: context
        for context in contexts
        for identity in [_context_identity(context)]
        if identity is not None
        and context.get('bullpen_story_tag') in _SCORING_EVENT_CLAIM_TAGS
    }
    if not claim_contexts:
        return {}

    game_pks = sorted({game_pk for game_pk, _team_id in claim_contexts})
    markers = (
        PlayByPlayProcessedGame.query
        .filter(PlayByPlayProcessedGame.mlb_game_pk.in_(game_pks))
        .all()
    )
    authoritative_markers = {
        marker.mlb_game_pk: marker
        for marker in markers
        if marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
        and marker.unresolved_pitcher_count == 0
        and marker.reconciliation_mismatch_count == 0
        and bool(marker.event_fingerprint)
    }
    authoritative_games = set(authoritative_markers)
    if not authoritative_games:
        return {}

    rows = (
        GamePlayByPlayEvent.query
        .filter(GamePlayByPlayEvent.mlb_game_pk.in_(sorted(authoritative_games)))
        .order_by(
            GamePlayByPlayEvent.mlb_game_pk.asc(),
            GamePlayByPlayEvent.event_index.asc(),
            GamePlayByPlayEvent.id.asc(),
        )
        .all()
    )
    by_game: dict[int, list[GamePlayByPlayEvent]] = defaultdict(list)
    for event in rows:
        by_game[event.mlb_game_pk].append(event)

    links: dict[tuple[int, int], dict[int, list[GamePlayByPlayEvent]]] = {}
    for identity, context in claim_contexts.items():
        game_pk, team_id = identity
        story_tag = context.get('bullpen_story_tag')
        events = by_game.get(game_pk, ())
        marker = authoritative_markers.get(game_pk)
        if not _marker_and_events_match_context(marker, context, events):
            continue
        selected = (
            _lost_lead_claim_events(events, team_id)
            if story_tag == 'lost_game_shape'
            else _late_pressure_claim_events(events, team_id)
        )
        if not _claim_events_match_context(context, events, selected):
            continue
        appearance_ids = {
            appearance.get('pitcher_mlb_id')
            for appearance in appearances_by_identity.get(identity, ())
        }
        if any(
            event.pitcher_mlb_id is None
            or event.pitcher_mlb_id not in appearance_ids
            for event in selected
        ):
            # A partially linked causal set is worse than no named set: it would
            # silently omit one of the event-driving appearances.
            continue
        by_pitcher: dict[int, list[GamePlayByPlayEvent]] = defaultdict(list)
        for event in selected:
            if event.pitcher_mlb_id is not None:
                by_pitcher[event.pitcher_mlb_id].append(event)
        if by_pitcher:
            links[identity] = dict(by_pitcher)
    return links


def _marker_and_events_match_context(
    marker: PlayByPlayProcessedGame | None,
    context: dict[str, Any],
    events: Iterable[GamePlayByPlayEvent],
) -> bool:
    identity = _context_identity(context)
    if marker is None or identity is None:
        return False
    game_pk, team_id = identity
    rows = list(events)
    if (
        marker.mlb_game_pk != game_pk
        or team_id not in {marker.home_team_id, marker.away_team_id}
        or marker.events_stored <= 0
        or marker.events_stored != len(rows)
    ):
        return False
    home_away = context.get('home_away')
    if home_away not in {'home', 'away'}:
        return False
    if (
        (home_away == 'home' and marker.home_team_id != team_id)
        or (home_away == 'away' and marker.away_team_id != team_id)
    ):
        return False
    context_date = context.get('game_date')
    if context_date is None or str(marker.game_date) != str(context_date):
        return False
    return all(
        event.mlb_game_pk == game_pk
        and event.home_team_id == marker.home_team_id
        and event.away_team_id == marker.away_team_id
        for event in rows
    )


def _lost_lead_claim_events(
    events: Iterable[GamePlayByPlayEvent],
    team_id: int,
) -> list[GamePlayByPlayEvent]:
    """Return the last exact scoring sequence that erased the team's lead."""
    previous = (0, 0)
    open_sequence: list[GamePlayByPlayEvent] = []
    completed_sequences: list[list[GamePlayByPlayEvent]] = []

    for event in events:
        score = _team_score(event, team_id)
        if score is None:
            continue
        before_margin = previous[0] - previous[1]
        after_margin = score[0] - score[1]
        against_increased = score[1] > previous[1]
        is_opponent_scoring_event = (
            event.fielding_team_id == team_id
            and event.is_scoring_play is True
            and against_increased
        )

        if after_margin > 0:
            open_sequence = []
        elif is_opponent_scoring_event and before_margin > 0 and after_margin <= 0:
            open_sequence = [event]
            if after_margin < 0:
                completed_sequences.append(open_sequence)
                open_sequence = []
        elif (
            is_opponent_scoring_event
            and open_sequence
            and before_margin == 0
            and after_margin < 0
        ):
            open_sequence.append(event)
            completed_sequences.append(open_sequence)
            open_sequence = []

        previous = score

    return completed_sequences[-1] if completed_sequences else []


def _late_pressure_claim_events(
    events: Iterable[GamePlayByPlayEvent],
    team_id: int,
) -> list[GamePlayByPlayEvent]:
    """Return exact opponent scoring plays in the tag's seventh-inning-plus window."""
    previous = (0, 0)
    selected: list[GamePlayByPlayEvent] = []
    for event in events:
        score = _team_score(event, team_id)
        if score is None:
            continue
        if (
            event.fielding_team_id == team_id
            and event.is_scoring_play is True
            and event.inning is not None
            and event.inning >= 7
            and score[1] > previous[1]
        ):
            selected.append(event)
        previous = score
    return selected


def _team_score(
    event: GamePlayByPlayEvent,
    team_id: int,
) -> tuple[int, int] | None:
    if event.home_score_at_event is None or event.away_score_at_event is None:
        return None
    if event.home_team_id == team_id:
        return event.home_score_at_event, event.away_score_at_event
    if event.away_team_id == team_id:
        return event.away_score_at_event, event.home_score_at_event
    return None


def _claim_events_match_context(
    context: dict[str, Any],
    events: Iterable[GamePlayByPlayEvent],
    selected: list[GamePlayByPlayEvent],
) -> bool:
    """Reject mixed revisions before an event-to-person claim is published."""
    if not selected:
        return False
    identity = _context_identity(context)
    if identity is None:
        return False
    _game_pk, team_id = identity
    derived = _event_score_facts(events, team_id)
    if derived is None:
        return False

    required_pairs = (
        ('final_score_for', 'final_score_for'),
        ('final_score_against', 'final_score_against'),
        ('late_runs_allowed', 'late_runs_allowed'),
        ('runs_allowed_innings_7_to_9', 'runs_allowed_innings_7_to_9'),
    )
    for context_key, derived_key in required_pairs:
        value = context.get(context_key)
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value != derived[derived_key]
        ):
            return False

    story_tag = context.get('bullpen_story_tag')
    if story_tag == 'lost_game_shape':
        turning_inning = context.get('turning_inning')
        return (
            derived['final_score_for'] < derived['final_score_against']
            and isinstance(turning_inning, int)
            and not isinstance(turning_inning, bool)
            and selected[-1].inning == turning_inning
        )
    if story_tag == 'late_pressure_accumulated':
        return len({event.inning for event in selected}) >= 2
    return False


def _event_score_facts(
    events: Iterable[GamePlayByPlayEvent],
    team_id: int,
) -> dict[str, int] | None:
    previous = (0, 0)
    saw_score = False
    late_runs = 0
    runs_7_to_9 = 0
    for event in events:
        score = _team_score(event, team_id)
        if score is None:
            continue
        if score[0] < previous[0] or score[1] < previous[1]:
            return None
        against_delta = max(0, score[1] - previous[1])
        if event.fielding_team_id == team_id and against_delta:
            if event.inning is not None and event.inning >= 7:
                late_runs += against_delta
                if event.inning <= 9:
                    runs_7_to_9 += against_delta
        previous = score
        saw_score = True
    if not saw_score:
        return None
    return {
        'final_score_for': previous[0],
        'final_score_against': previous[1],
        'late_runs_allowed': late_runs,
        'runs_allowed_innings_7_to_9': runs_7_to_9,
    }
