"""Read-only identity diagnostic for one unresolved 2026 appearance-team row.

This diagnostic exists for the case where the guarded repair cannot find the target
pitcher's stored MLB id in the official box-score pitching lines. It exposes only a
bounded, private summary of the target row and official pitching identities so the
identity discrepancy can be understood before any repair contract is expanded.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

import sqlalchemy as sa

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db
from utils.innings import parse_mlb_innings_to_outs


CAPABILITY = 'unresolved_appearance_team_diagnostic_2026_v1'
EXPECTED_MIGRATION_HEAD = 'a4f1c7e9b3d2'
MAX_OFFICIAL_LINES = 20

RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
EXIT_BY_RESULT = {RESULT_PASS: 0, RESULT_FAIL: 1}


def _int_or_none(value) -> Optional[int]:
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _migration_head(session):
    try:
        rows = session.execute(
            sa.text('SELECT version_num FROM alembic_version ORDER BY version_num')
        ).fetchall()
        return sorted(str(row[0]) for row in rows)
    except Exception:  # diagnostic probe only
        session.rollback()
        return None


def _team_summary(boxscore, side):
    team = ((((boxscore or {}).get('teams') or {}).get(side) or {}).get('team') or {})
    return {
        'side': side,
        'team_id': _int_or_none(team.get('id')),
        'team_name': team.get('name'),
    }


def _line_player_id(line):
    return _int_or_none(line.get('person_id') or line.get('player_id'))


def _line_stats(line):
    return line.get('stats') or {}


def _official_line_summary(line):
    stats = _line_stats(line)
    innings = stats.get('inningsPitched')
    try:
        outs = parse_mlb_innings_to_outs(innings) if innings not in (None, '') else None
    except (TypeError, ValueError):
        outs = None
    return {
        'player_id': _line_player_id(line),
        'name': line.get('name'),
        'side': line.get('side'),
        'team_id': _int_or_none(line.get('team_id')),
        'games_started': _int_or_none(stats.get('gamesStarted')),
        'innings_pitched': innings,
        'innings_pitched_outs': outs,
        'hits_allowed': _int_or_none(stats.get('hits')),
        'runs_allowed': _int_or_none(stats.get('runs')),
        'earned_runs': _int_or_none(stats.get('earnedRuns')),
        'walks': _int_or_none(stats.get('baseOnBalls')),
        'strikeouts': _int_or_none(stats.get('strikeOuts')),
        'home_runs_allowed': _int_or_none(stats.get('homeRuns')),
    }


def _target_summary(row, pitcher):
    return {
        'game_log_id': row.id,
        'game_pk': row.mlb_game_pk,
        'game_date': row.game_date.isoformat(),
        'pitcher_id': row.pitcher_id,
        'pitcher_mlb_id': _int_or_none(getattr(pitcher, 'mlb_id', None)),
        'pitcher_name': getattr(pitcher, 'full_name', None),
        'opponent': row.opponent,
        'opponent_abbreviation': row.opponent_abbreviation,
        'games_started': row.games_started,
        'innings_pitched_outs': row.innings_pitched_outs,
        'hits_allowed': row.hits_allowed,
        'runs_allowed': row.runs_allowed,
        'earned_runs': row.earned_runs,
        'walks': row.walks,
        'strikeouts': row.strikeouts,
        'home_runs_allowed': row.home_runs_allowed,
        'appearance_team_status': row.appearance_team_status,
        'appearance_team_source': row.appearance_team_source,
        'appearance_team_reason': row.appearance_team_reason,
    }


def _stat_match(target, official):
    fields = (
        'innings_pitched_outs',
        'hits_allowed',
        'runs_allowed',
        'earned_runs',
        'walks',
        'strikeouts',
        'home_runs_allowed',
    )
    if any(official.get(field) is None for field in fields):
        return False
    if any(target.get(field) != official.get(field) for field in fields):
        return False
    target_started = target.get('games_started')
    official_started = official.get('games_started')
    return target_started is None or official_started is None or target_started == official_started


def run_diagnostic(
    *,
    game_log_id: int,
    expected_game_pk: int,
    expected_game_date: date,
    client=mlb_client,
    session=None,
):
    session = session or db.session
    migration_head = _migration_head(session)
    payload = {
        'capability': CAPABILITY,
        'mode': 'read_only',
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'database_writes_performed': False,
    }
    if migration_head != [EXPECTED_MIGRATION_HEAD]:
        payload.update({
            'result': RESULT_FAIL,
            'exit_code': EXIT_BY_RESULT[RESULT_FAIL],
            'decision_reasons': ['migration_head_mismatch'],
        })
        return payload

    try:
        row = session.get(GameLog, game_log_id)
        if row is None:
            raise LookupError('target_game_log_missing')
        if row.mlb_game_pk != expected_game_pk or row.game_date != expected_game_date:
            raise ValueError('target_identity_mismatch')
        pitcher = session.get(Pitcher, row.pitcher_id)
        if pitcher is None:
            raise LookupError('target_pitcher_missing')

        boxscore = client.get_game_boxscore(expected_game_pk)
        official_lines = [
            _official_line_summary(line)
            for line in sync_service._extract_pitching_lines_from_boxscore(boxscore)
        ]
        official_lines.sort(
            key=lambda item: (
                item.get('side') or '',
                item.get('player_id') is None,
                item.get('player_id') or 0,
                item.get('name') or '',
            )
        )
        target = _target_summary(row, pitcher)
        target_mlb_id = target.get('pitcher_mlb_id')
        identity_matches = [
            line for line in official_lines if line.get('player_id') == target_mlb_id
        ]
        stat_matches = [line for line in official_lines if _stat_match(target, line)]

        payload.update({
            'result': RESULT_PASS,
            'exit_code': EXIT_BY_RESULT[RESULT_PASS],
            'decision_reasons': ['official_pitching_identity_diagnostic_complete'],
            'target': target,
            'official_game_teams': [
                _team_summary(boxscore, 'away'),
                _team_summary(boxscore, 'home'),
            ],
            'official_pitching_line_count': len(official_lines),
            'official_pitching_lines_returned': min(len(official_lines), MAX_OFFICIAL_LINES),
            'official_pitching_lines_truncated': len(official_lines) > MAX_OFFICIAL_LINES,
            'official_pitching_lines': official_lines[:MAX_OFFICIAL_LINES],
            'target_mlb_id_present': len(identity_matches) == 1,
            'target_mlb_id_match_count': len(identity_matches),
            'exact_stat_match_count': len(stat_matches),
            'exact_stat_matches': stat_matches[:MAX_OFFICIAL_LINES],
        })
        return payload
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        reason = str(exc) if str(exc) in {
            'target_game_log_missing',
            'target_identity_mismatch',
            'target_pitcher_missing',
        } else 'diagnostic_execution_failed'
        payload.update({
            'result': RESULT_FAIL,
            'exit_code': EXIT_BY_RESULT[RESULT_FAIL],
            'decision_reasons': [reason],
            'error_type': type(exc).__name__,
        })
        return payload
