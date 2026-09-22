"""Frozen, publication-time Recent Relief Work ledger for Team Board TB-10.

This module projects the official appearance-team rows already loaded by the
trusted Team Board publication assembler.  It owns no acquisition, selector,
or request-time authority.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, timedelta

from sqlalchemy import func, or_

from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from utils.games_started import RELIEF, games_started_state


CONTRACT = 'team_board_recent_relief_work_v1'
METHOD_VERSION = CONTRACT
LOOKBACK_DAYS = 30
DISPLAY_GAME_DATES = 5
MULTI_INNING_MIN_OUTS = 4
POPULATION_BASIS = 'official_final_appearance_team_relief_appearances'
ORDER_BASIS = 'game_date_desc_game_number_game_pk_then_pitcher_name_id'

EVIDENCE_STATES = {'complete', 'partial', 'unknown', 'unavailable'}


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _nonnegative(value):
    if type(value) is not int or value < 0:
        return None
    return value


def _innings(outs):
    return None if outs is None else f'{outs // 3}.{outs % 3}'


def _fact(value, *, reason='source_value_missing'):
    parsed = _nonnegative(value)
    if parsed is None:
        return {'value': None, 'status': 'unknown', 'reason_codes': [reason]}
    return {'value': parsed, 'status': 'complete', 'reason_codes': []}


def load_final_game_authority(team_ids, *, data_through):
    """Load final schedule authority once for every represented team."""
    represented = _parse_date(data_through)
    wanted = sorted({team_id for team_id in team_ids if type(team_id) is int})
    if represented is None or not wanted:
        return {}
    start = represented - timedelta(days=LOOKBACK_DAYS - 1)
    rows = (
        ScheduledGame.query
        .filter(
            ScheduledGame.team_id.in_(wanted),
            ScheduledGame.game_date >= start,
            ScheduledGame.game_date <= represented,
            ScheduledGame.status_state == ScheduledGame.STATE_FINAL,
        )
        .all()
    )
    result = defaultdict(dict)
    for row in rows:
        result[row.team_id][row.game_pk] = {
            'game_date': _iso(row.game_date),
            'game_number': row.game_number,
            'home_away': row.home_away,
            'status': 'final',
        }
    return dict(result)


def load_unresolved_current_roster_counts(team_ids, *, data_through):
    """Batch the legacy attribution disclosure without adding per-team reads."""
    represented = _parse_date(data_through)
    wanted = sorted({team_id for team_id in team_ids if type(team_id) is int})
    if represented is None or not wanted:
        return {}
    start = represented - timedelta(days=LOOKBACK_DAYS - 1)
    rows = (
        GameLog.query
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .with_entities(Pitcher.team_id, func.count(GameLog.id))
        .filter(
            Pitcher.team_id.in_(wanted),
            GameLog.game_date >= start,
            GameLog.game_date <= represented,
            or_(
                GameLog.appearance_team_status.is_(None),
                GameLog.appearance_team_status != GameLog.APPEARANCE_TEAM_RESOLVED,
            ),
        )
        .group_by(Pitcher.team_id)
        .all()
    )
    return {team_id: count for team_id, count in rows}


def author_frozen_recent_relief_work(
    team_id,
    rows,
    *,
    data_through,
    final_games,
    unresolved_current_roster_count=0,
    active_pitcher_ids=(),
    team_board_package_contract,
):
    """Project the bounded ledger from already-loaded publication rows."""
    represented = _parse_date(data_through)
    if represented is None:
        return _unavailable(
            team_id, data_through=None,
            package_contract=team_board_package_contract,
            reason='represented_date_unavailable',
        )

    final_games = final_games if isinstance(final_games, dict) else {}
    active_ids = {
        pitcher_id for pitcher_id in active_pitcher_ids
        if type(pitcher_id) is int and pitcher_id > 0
    }
    groups = defaultdict(lambda: defaultdict(list))
    excluded_nonfinal = 0
    for item in rows or []:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            continue
        log, pitcher = item
        if getattr(log, 'appearance_team_id', None) != team_id:
            continue
        try:
            role = games_started_state(getattr(log, 'games_started', None))
        except Exception:
            role = 'unknown'
        if role != RELIEF:
            continue
        game_pk = getattr(log, 'mlb_game_pk', None)
        final = final_games.get(game_pk)
        if (
            not isinstance(final, dict)
            or final.get('status') != 'final'
            or final.get('game_date') != _iso(getattr(log, 'game_date', None))
        ):
            excluded_nonfinal += 1
            continue
        groups[log.game_date][game_pk].append((log, pitcher))

    game_dates = sorted(groups, reverse=True)[:DISPLAY_GAME_DATES]
    games = []
    for game_date in game_dates:
        ordered_games = sorted(
            groups[game_date],
            key=lambda game_pk: _game_key(final_games.get(game_pk), game_pk),
        )
        for game_pk in ordered_games:
            appearances = sorted(
                groups[game_date][game_pk],
                key=lambda item: (
                    str(getattr(item[1], 'full_name', '') or '').lower(),
                    getattr(item[1], 'id', 0) or 0,
                    getattr(item[0], 'id', 0) or 0,
                ),
            )
            games.append(_game(
                team_id, game_pk, appearances, final_games[game_pk], active_ids,
            ))

    limitations = []
    if unresolved_current_roster_count:
        limitations.append(
            f'{unresolved_current_roster_count} in-window appearance '
            f'{"row is" if unresolved_current_roster_count == 1 else "rows are"} '
            'withheld because official team attribution is unresolved.'
        )
    if excluded_nonfinal:
        limitations.append(
            f'{excluded_nonfinal} relief appearance '
            f'{"row is" if excluded_nonfinal == 1 else "rows are"} withheld '
            'because final game authority is unavailable.'
        )

    status = 'partial' if limitations else 'complete'
    relief_by_date = _legacy_date_groups(games)
    return {
        'contract': CONTRACT,
        'method_version': METHOD_VERSION,
        'capability': 'public_team_relief_work',
        'team_board_package_contract': team_board_package_contract,
        'team_id': team_id,
        'data_through': represented.isoformat(),
        'population_basis': POPULATION_BASIS,
        'window': {
            'lookback_days': LOOKBACK_DAYS,
            'start': (represented - timedelta(days=LOOKBACK_DAYS - 1)).isoformat(),
            'through': represented.isoformat(),
            'display_latest_game_dates': DISPLAY_GAME_DATES,
            'semantics': 'latest_completed_game_dates_with_team_relief_appearances',
        },
        'status': status,
        'reason_code': 'relief_work_evidence_partial' if limitations else None,
        'limitations': limitations,
        'scope_sentence': 'Covers official final relief appearances made for this team.',
        'order_basis': ORDER_BASIS,
        'games': games,
        'relief_by_date': relief_by_date,
        'game_count': len(games),
        'appearance_count': sum(len(game['appearances']) for game in games),
        'capabilities': {
            'entry_context': {'status': 'unavailable', 'reason_code': 'not_published'},
            'leverage_context': {'status': 'unavailable', 'reason_code': 'not_published'},
        },
    }


def valid_frozen_recent_relief_work(
    carrier, *, team_id, data_through, team_board_package_contract,
):
    """Fail closed unless both frozen views describe the same ledger."""
    represented = _parse_date(data_through)
    if (
        not isinstance(carrier, Mapping)
        or represented is None
        or carrier.get('contract') != CONTRACT
        or carrier.get('method_version') != METHOD_VERSION
        or carrier.get('team_board_package_contract') != team_board_package_contract
        or carrier.get('team_id') != team_id
        or carrier.get('data_through') != represented.isoformat()
        or carrier.get('population_basis') != POPULATION_BASIS
        or carrier.get('order_basis') != ORDER_BASIS
        or carrier.get('status') not in {'complete', 'partial', 'unavailable'}
        or not isinstance(carrier.get('limitations'), list)
        or not isinstance(carrier.get('games'), list)
        or not isinstance(carrier.get('relief_by_date'), list)
    ):
        return False
    games = carrier['games']
    window = carrier.get('window')
    if carrier['status'] == 'unavailable':
        if window is not None or games or carrier['relief_by_date']:
            return False
    elif (
        not isinstance(window, Mapping)
        or window.get('lookback_days') != LOOKBACK_DAYS
        or window.get('start') != (
            represented - timedelta(days=LOOKBACK_DAYS - 1)
        ).isoformat()
        or window.get('through') != represented.isoformat()
        or window.get('display_latest_game_dates') != DISPLAY_GAME_DATES
        or window.get('semantics') != (
            'latest_completed_game_dates_with_team_relief_appearances'
        )
    ):
        return False
    appearances = []
    game_dates = []
    for game in games:
        if (
            not isinstance(game, Mapping)
            or type(game.get('mlb_game_pk')) is not int
            or game.get('mlb_game_pk') < 0
            or _parse_date(game.get('game_date')) is None
            or game.get('game_date') > represented.isoformat()
            or game.get('game_date') < window['start']
            or not isinstance(game.get('finality'), Mapping)
            or game['finality'].get('game_status') != 'final'
            or game['finality'].get('status') != 'complete'
            or game.get('evidence_status') not in EVIDENCE_STATES
            or not isinstance(game.get('appearances'), list)
        ):
            return False
        game_dates.append(game['game_date'])
        for appearance in game['appearances']:
            if (
                not isinstance(appearance, Mapping)
                or appearance.get('appearance_team_id') != team_id
                or appearance.get('mlb_game_pk') != game['mlb_game_pk']
                or appearance.get('game_date') != game['game_date']
                or type(appearance.get('pitcher_id')) is not int
                or not isinstance(appearance.get('current_roster'), Mapping)
                or not _valid_fact(appearance.get('outs'))
                or not _valid_fact(appearance.get('pitches'))
                or not _valid_fact(appearance.get('multi_inning'), boolean=True)
                or not _valid_fact(appearance.get('save'), boolean=True)
                or not _valid_fact(appearance.get('hold'), boolean=True)
                or not _valid_fact(appearance.get('game_finished'), boolean=True)
            ):
                return False
            appearances.append(appearance)
    if (
        game_dates != sorted(game_dates, reverse=True)
        or len(set(game_dates)) > DISPLAY_GAME_DATES
        or carrier.get('game_count') != len(games)
        or carrier.get('appearance_count') != len(appearances)
        or carrier['relief_by_date'] != _legacy_date_groups(games)
    ):
        return False
    return True


def _valid_fact(fact, *, boolean=False):
    if (
        not isinstance(fact, Mapping)
        or fact.get('status') not in EVIDENCE_STATES
        or not isinstance(fact.get('reason_codes'), list)
    ):
        return False
    value = fact.get('value')
    if fact['status'] != 'complete':
        return value is None
    return type(value) is bool if boolean else _nonnegative(value) is not None


def _legacy_date_groups(games):
    """Carry the already-frozen ledger through the established Team Board shape."""
    by_date = defaultdict(list)
    for game in games:
        by_date[game['game_date']].append(game)
    groups = []
    for game_date in sorted(by_date, reverse=True):
        date_games = by_date[game_date]
        appearances = [
            _legacy_appearance(item)
            for game in date_games
            for item in game['appearances']
        ]
        outs = [item.get('innings_pitched_outs') for item in appearances]
        pitches = [item.get('pitches_thrown') for item in appearances]
        outs_total = sum(outs) if all(value is not None for value in outs) else None
        pitches_total = (
            sum(pitches) if all(value is not None for value in pitches) else None
        )
        summary = f'{game_date} — {len(appearances)} relief '
        summary += 'appearance' if len(appearances) == 1 else 'appearances'
        if outs_total is not None:
            summary += f', {_innings(outs_total)} IP'
        if pitches_total is not None:
            summary += f', {pitches_total} pitches'
        groups.append({
            'game_date': game_date,
            'relief_appearances': len(appearances),
            'outs_total': outs_total,
            'pitches_total': pitches_total,
            'appearances_with_pitches': sum(
                1 for value in pitches if value is not None
            ),
            'game_pks': [game['mlb_game_pk'] for game in date_games],
            'game_count': len(date_games),
            'sentence': f'{summary}.',
            'games': [{
                'mlb_game_pk': game['mlb_game_pk'],
                'game_number': game.get('game_number'),
                'opponent': game.get('opponent'),
                'opponent_abbreviation': game.get('opponent_abbreviation'),
                'home_away': game.get('home_away'),
                'finality': game.get('finality'),
            } for game in date_games],
            'appearances': appearances,
        })
    return groups


def _legacy_appearance(item):
    roster = item.get('current_roster') or {}
    if roster.get('active') is True:
        roster_sentence = 'On the active roster per frozen MLB roster authority.'
    elif roster.get('status'):
        roster_sentence = f'Roster status: {roster["status"]} per frozen MLB roster authority.'
    else:
        roster_sentence = 'Current roster status unavailable.'
    return {
        'pitcher_id': item.get('pitcher_id'),
        'pitcher_mlb_id': item.get('pitcher_mlb_id'),
        'pitcher_full_name': item.get('pitcher_full_name'),
        'roster_status_sentence': roster_sentence,
        'mlb_game_pk': item.get('mlb_game_pk'),
        'appearance_team_id': item.get('appearance_team_id'),
        'game_date': item.get('game_date'),
        'innings_pitched': item.get('innings'),
        'innings_pitched_outs': (item.get('outs') or {}).get('value'),
        'pitches_thrown': (item.get('pitches') or {}).get('value'),
        'multi_inning': item.get('multi_inning'),
        'save': item.get('save'),
        'hold': item.get('hold'),
        'game_finished': item.get('game_finished'),
    }


def _game(team_id, game_pk, entries, final, active_pitcher_ids):
    appearances = [
        _appearance(team_id, log, pitcher, active_pitcher_ids)
        for log, pitcher in entries
    ]
    outs = [item['outs']['value'] for item in appearances]
    pitches = [item['pitches']['value'] for item in appearances]
    outs_complete = all(value is not None for value in outs)
    pitches_complete = all(value is not None for value in pitches)
    first_log = entries[0][0]
    return {
        'mlb_game_pk': game_pk,
        'game_date': _iso(first_log.game_date),
        'game_number': final.get('game_number'),
        'opponent': getattr(first_log, 'opponent', None),
        'opponent_abbreviation': getattr(first_log, 'opponent_abbreviation', None),
        'home_away': final.get('home_away'),
        'finality': {
            'status': 'complete',
            'game_status': 'final',
            'reason_codes': [],
        },
        'evidence_status': (
            'complete' if outs_complete and pitches_complete else 'partial'
        ),
        'relief_appearances': len(appearances),
        'outs_total': sum(outs) if outs_complete else None,
        'innings': _innings(sum(outs)) if outs_complete else None,
        'pitches_total': sum(pitches) if pitches_complete else None,
        'appearances': appearances,
    }


def _appearance(team_id, log, pitcher, active_pitcher_ids):
    outs = _fact(getattr(log, 'innings_pitched_outs', None), reason='outs_missing')
    pitches = _fact(getattr(log, 'pitches_thrown', None), reason='pitches_missing')
    multi = (
        {'value': outs['value'] >= MULTI_INNING_MIN_OUTS, 'status': 'complete', 'reason_codes': []}
        if outs['status'] == 'complete'
        else {'value': None, 'status': 'unknown', 'reason_codes': ['outs_missing']}
    )
    return {
        'pitcher_id': pitcher.id,
        'pitcher_mlb_id': pitcher.mlb_id,
        'pitcher_full_name': pitcher.full_name,
        'appearance_team_id': team_id,
        'mlb_game_pk': log.mlb_game_pk,
        'game_date': _iso(log.game_date),
        'current_roster': {
            'active': pitcher.id in active_pitcher_ids,
            'status': getattr(pitcher, 'roster_status', None),
        },
        'outs': outs,
        'innings': _innings(outs['value']),
        'pitches': pitches,
        'multi_inning': multi,
        'save': _boolean_fact(getattr(log, 'save', None), 'save_missing'),
        'hold': _boolean_fact(getattr(log, 'hold', None), 'hold_missing'),
        'game_finished': _finished_fact(getattr(log, 'games_finished', None)),
    }


def _boolean_fact(value, reason):
    if type(value) is bool:
        return {'value': value, 'status': 'complete', 'reason_codes': []}
    return {'value': None, 'status': 'unknown', 'reason_codes': [reason]}


def _finished_fact(value):
    if type(value) is int and value in (0, 1):
        return {'value': value == 1, 'status': 'complete', 'reason_codes': []}
    return {'value': None, 'status': 'unknown', 'reason_codes': ['games_finished_missing']}


def _game_key(final, game_pk):
    number = final.get('game_number') if isinstance(final, dict) else None
    return (0, number, game_pk) if type(number) is int else (1, 0, game_pk)


def _parse_date(value):
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _unavailable(team_id, *, data_through, package_contract, reason):
    return {
        'contract': CONTRACT,
        'method_version': METHOD_VERSION,
        'capability': 'public_team_relief_work',
        'team_board_package_contract': package_contract,
        'team_id': team_id,
        'data_through': data_through,
        'population_basis': POPULATION_BASIS,
        'window': None,
        'status': 'unavailable',
        'reason_code': reason,
        'limitations': [],
        'scope_sentence': 'Covers official final relief appearances made for this team.',
        'order_basis': ORDER_BASIS,
        'games': [],
        'relief_by_date': [],
        'game_count': 0,
        'appearance_count': 0,
        'capabilities': {
            'entry_context': {'status': 'unavailable', 'reason_code': 'not_published'},
            'leverage_context': {'status': 'unavailable', 'reason_code': 'not_published'},
        },
    }


__all__ = [
    'CONTRACT', 'DISPLAY_GAME_DATES', 'LOOKBACK_DAYS', 'METHOD_VERSION',
    'ORDER_BASIS', 'POPULATION_BASIS', 'author_frozen_recent_relief_work',
    'load_final_game_authority', 'load_unresolved_current_roster_counts',
    'valid_frozen_recent_relief_work',
]
