"""Publication-time, descriptive Team Board deployment context.

This is a separate public projection from the internal entry-band and story
leverage evidence rules. It never substitutes save/hold or inning for a missing
recorded leverage index.
"""

from collections import Counter, defaultdict
from datetime import timedelta
from math import isfinite

from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from utils.db import db


CONTRACT = 'team_board_public_deployment_context_v1'
METHOD_VERSION = 'team_board_public_deployment_context_v1'
WINDOW_DAYS = 14
HIGH_LEVERAGE_MIN = 1.5
LOW_LEVERAGE_MAX = 0.85


def _domain(total, values, *, reason='evidence_missing'):
    known = len(values)
    status = (
        'unavailable' if total == 0 else
        'complete' if known == total else
        'partial' if known else 'unknown'
    )
    return {
        'status': status,
        'appearances': total,
        'known_appearances': known,
        'reason_codes': [] if status == 'complete' else [reason],
    }


def _recorded_li(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) and number >= 0 else None


def _entry_for(log, pitcher, events, marker):
    if marker is None or marker.processing_status != PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED:
        return None, None
    mlb_id = getattr(pitcher, 'mlb_id', None)
    team_id = getattr(log, 'appearance_team_id', None)
    if (
        mlb_id is None or team_id is None
        or marker.game_date != log.game_date
        or team_id not in (marker.home_team_id, marker.away_team_id)
    ):
        return None, None
    matching = [
        (index, event) for index, event in enumerate(events)
        if event.fielding_team_id == team_id and event.pitcher_mlb_id == mlb_id
    ]
    if not matching:
        return None, None
    index, first = matching[0]
    inning = first.inning if type(first.inning) is int and first.inning >= 1 else None
    # A second, disjoint stint cannot be represented as one entry.
    team_sequence = [event.pitcher_mlb_id for event in events if event.fielding_team_id == team_id]
    segments = [value for pos, value in enumerate(team_sequence) if pos == 0 or value != team_sequence[pos - 1]]
    if segments.count(mlb_id) != 1:
        return None, None
    if index == 0:
        return inning, None
    preceding = events[index - 1]
    home = preceding.home_score_at_event
    away = preceding.away_score_at_event
    if type(home) is not int or type(away) is not int or home < 0 or away < 0:
        return inning, None
    if first.fielding_team_id == first.home_team_id:
        margin = home - away
    elif first.fielding_team_id == first.away_team_id:
        margin = away - home
    else:
        margin = None
    return inning, margin


def build_public_deployment_context(
    team_id, rows, anchor, *, markers, events_by_game, pitcher_ids=(),
):
    """Project one team's official relief rows; inputs are already bounded to D-13..D."""
    start = anchor - timedelta(days=WINDOW_DAYS - 1)
    grouped = defaultdict(list)
    for log, pitcher in rows:
        if (
            log.appearance_team_id == team_id
            and log.game_date is not None
            and start <= log.game_date <= anchor
            and getattr(log, 'games_started', None) == 0
            and getattr(log, 'game_type', None) == 'R'
        ):
            grouped[pitcher.id].append((log, pitcher))
    for pitcher_id in pitcher_ids:
        if type(pitcher_id) is int and pitcher_id > 0:
            grouped.setdefault(pitcher_id, [])

    profiles = []
    for pitcher_id, appearances in sorted(grouped.items()):
        innings, margins, leverage = [], [], []
        for log, pitcher in appearances:
            inning, margin = _entry_for(
                log, pitcher, events_by_game.get(log.mlb_game_pk, []),
                markers.get(log.mlb_game_pk),
            )
            if inning is not None:
                innings.append(inning)
            if margin is not None:
                margins.append(margin)
            li = _recorded_li(getattr(log, 'leverage_index', None))
            if li is not None:
                leverage.append(li)
        total = len(appearances)
        inning_counts = Counter(innings)
        entry = {
            **_domain(total, innings, reason='entry_event_missing_or_incomplete'),
            'by_inning': [
                {'inning': inning, 'appearances': count}
                for inning, count in sorted(inning_counts.items())
            ],
            'eighth_or_later_appearances': sum(value for inning, value in inning_counts.items() if inning >= 8),
            'extra_inning_appearances': sum(value for inning, value in inning_counts.items() if inning >= 10),
        }
        score = {
            **_domain(total, margins, reason='entry_score_missing_or_incomplete'),
            'leading': sum(value > 0 for value in margins),
            'tied': sum(value == 0 for value in margins),
            'trailing': sum(value < 0 for value in margins),
        }
        li_context = {
            **_domain(total, leverage, reason='recorded_leverage_index_missing'),
            'basis': 'recorded_game_log_leverage_index_only',
            'high': sum(value >= HIGH_LEVERAGE_MIN for value in leverage),
            'middle': sum(LOW_LEVERAGE_MAX < value < HIGH_LEVERAGE_MIN for value in leverage),
            'low': sum(value <= LOW_LEVERAGE_MAX for value in leverage),
        }
        profiles.append({
            'pitcher_id': pitcher_id,
            'entry_inning': entry,
            'score_context': score,
            'leverage': li_context,
        })
    return {
        'contract': CONTRACT,
        'method_version': METHOD_VERSION,
        'team_id': team_id,
        'data_through': anchor.isoformat(),
        'window_days': WINDOW_DAYS,
        'population_basis': 'official_appearance_team_relief_appearances',
        'profiles': profiles,
        'role_movement': {'status': 'unavailable', 'reason_code': 'not_published'},
    }


def author_public_deployment_context(team_id, rows, anchor, *, pitcher_ids=()):
    """Two set-based projections; no per-pitcher or per-game database lookups."""
    game_pks = sorted({
        log.mlb_game_pk for log, _ in rows
        if log.appearance_team_id == team_id
        and log.game_date is not None
        and anchor - timedelta(days=WINDOW_DAYS - 1) <= log.game_date <= anchor
        and getattr(log, 'games_started', None) == 0
        and getattr(log, 'game_type', None) == 'R'
    })
    markers = {}
    events_by_game = defaultdict(list)
    if game_pks:
        markers = {
            marker.mlb_game_pk: marker for marker in
            PlayByPlayProcessedGame.query.filter(PlayByPlayProcessedGame.mlb_game_pk.in_(game_pks)).all()
        }
        eligible = sorted(
            game_pk for game_pk, marker in markers.items()
            if marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
        )
        if eligible:
            events = (
                db.session.query(
                    GamePlayByPlayEvent.mlb_game_pk,
                    GamePlayByPlayEvent.event_index,
                    GamePlayByPlayEvent.id,
                    GamePlayByPlayEvent.inning,
                    GamePlayByPlayEvent.pitcher_mlb_id,
                    GamePlayByPlayEvent.fielding_team_id,
                    GamePlayByPlayEvent.home_team_id,
                    GamePlayByPlayEvent.away_team_id,
                    GamePlayByPlayEvent.home_score_at_event,
                    GamePlayByPlayEvent.away_score_at_event,
                )
                .filter(GamePlayByPlayEvent.mlb_game_pk.in_(eligible))
                .order_by(GamePlayByPlayEvent.mlb_game_pk, GamePlayByPlayEvent.event_index, GamePlayByPlayEvent.id)
                .all()
            )
            for event in events:
                events_by_game[event.mlb_game_pk].append(event)
    return build_public_deployment_context(
        team_id, rows, anchor, markers=markers, events_by_game=events_by_game,
        pitcher_ids=pitcher_ids,
    )
