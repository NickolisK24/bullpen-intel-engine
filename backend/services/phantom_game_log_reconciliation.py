"""Official-boxscore guard for phantom pitcher game-log rows.

MLB's per-pitcher gameLog feed can list a player for a completed game even when the
final box score contains no pitching appearance. BaseballOS must not convert such a
listing into workload or performance evidence.

A row is eligible for removal only when every condition is proven:

* the stored GameLog identity matches the requested game/date/pitcher guard;
* the row is an all-zero, zero-out pitching line;
* the game has complete final-box-score pitching sections for both sides;
* the stored pitcher's stable MLB id is absent from every official pitching line;
* no database row has a foreign-key dependency on the GameLog;
* apply is explicitly authorized and the reviewed evidence fingerprint still matches.

A legitimate 0.0-IP appearance is preserved whenever its MLB id appears in the final
box-score pitching section. Current ``Pitcher.team_id`` is never evidence.
"""

from __future__ import annotations

from datetime import date
import hashlib
import json
from typing import Optional

import sqlalchemy as sa

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import appearance_team_authority as ata
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db


CAPABILITY = 'phantom_game_log_reconciliation_v1'
CONTRACT_VERSION = 'phantom_game_log_reconciliation.v1'
EXPECTED_MIGRATION_HEAD = 'a4f1c7e9b3d2'
CONFIRMATION_PHRASE = 'RUN_PHANTOM_GAME_LOG_RECONCILIATION'

RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_REFUSED = 'refused'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {
    RESULT_PASS: 0,
    RESULT_FAIL: 1,
    RESULT_REFUSED: 1,
    RESULT_INCONCLUSIVE: 2,
}

_ZERO_INT_FIELDS = (
    'innings_pitched_outs',
    'pitches_thrown',
    'strikes',
    'hits_allowed',
    'runs_allowed',
    'earned_runs',
    'walks',
    'strikeouts',
    'home_runs_allowed',
    'batters_faced',
    'balls',
    'games_finished',
    'inherited_runners',
    'inherited_runners_scored',
)
_ZERO_BOOL_FIELDS = (
    'save_situation',
    'hold',
    'blown_save',
    'win',
    'loss',
    'save',
)


def _int_or_none(value) -> Optional[int]:
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256_json(payload) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _migration_head(session):
    try:
        rows = session.execute(
            sa.text('SELECT version_num FROM alembic_version ORDER BY version_num')
        ).fetchall()
        return sorted(str(row[0]) for row in rows)
    except Exception:  # diagnostic probe only
        session.rollback()
        return None


def zero_stat_signature(row: GameLog) -> dict:
    """Return the bounded stored evidence used by the phantom contract."""
    return {
        'games_started': row.games_started,
        **{field: getattr(row, field, None) for field in _ZERO_INT_FIELDS},
        **{field: bool(getattr(row, field, False)) for field in _ZERO_BOOL_FIELDS},
    }


def is_all_zero_non_appearance_candidate(row: GameLog) -> bool:
    """Strict candidate shape; official absence is still required separately."""
    if row.games_started not in (None, 0):
        return False
    for field in _ZERO_INT_FIELDS:
        if getattr(row, field, None) not in (None, 0):
            return False
    for field in _ZERO_BOOL_FIELDS:
        if bool(getattr(row, field, False)):
            return False
    return True


def _official_pitching_lines(boxscore) -> list[dict]:
    lines = []
    for line in sync_service._extract_pitching_lines_from_boxscore(boxscore):
        player_id = _int_or_none(line.get('person_id') or line.get('player_id'))
        side = line.get('side')
        team_id = _int_or_none(line.get('team_id'))
        lines.append({
            'player_id': player_id,
            'name': line.get('name'),
            'side': side,
            'team_id': team_id,
        })
    lines.sort(key=lambda item: (
        item.get('side') or '',
        item.get('player_id') is None,
        item.get('player_id') or 0,
        item.get('name') or '',
    ))
    return lines


def _boxscore_team(boxscore, side) -> dict:
    team = ((((boxscore or {}).get('teams') or {}).get(side) or {}).get('team') or {})
    return {
        'side': side,
        'team_id': _int_or_none(team.get('id')),
        'team_name': team.get('name'),
    }


def _validate_official_boxscore(boxscore) -> tuple[Optional[dict], Optional[str]]:
    teams = [_boxscore_team(boxscore, 'away'), _boxscore_team(boxscore, 'home')]
    if any(item['team_id'] is None for item in teams):
        return None, 'official_boxscore_team_identity_missing'

    lines = _official_pitching_lines(boxscore)
    if not lines:
        return None, 'official_pitching_sections_missing'
    if any(item['player_id'] is None for item in lines):
        return None, 'official_pitching_identity_missing'
    if any(item['side'] not in ('away', 'home') for item in lines):
        return None, 'official_pitching_side_missing'
    if any(item['team_id'] is None for item in lines):
        return None, 'official_pitching_team_identity_missing'
    if not any(item['side'] == 'away' for item in lines):
        return None, 'official_away_pitching_section_missing'
    if not any(item['side'] == 'home' for item in lines):
        return None, 'official_home_pitching_section_missing'

    player_ids = [item['player_id'] for item in lines]
    if len(player_ids) != len(set(player_ids)):
        return None, 'official_pitching_identity_contradictory'

    expected_team_by_side = {item['side']: item['team_id'] for item in teams}
    if any(item['team_id'] != expected_team_by_side[item['side']] for item in lines):
        return None, 'official_pitching_team_identity_contradictory'

    return {'teams': teams, 'pitching_lines': lines}, None


def _dependent_rows(game_log_id: int, session) -> list[dict]:
    """Fail closed if any loaded table has an FK reference to this GameLog."""
    dependencies = []
    for table in db.metadata.sorted_tables:
        if table.name == GameLog.__tablename__:
            continue
        for foreign_key in table.foreign_keys:
            if (
                foreign_key.column.table.name == GameLog.__tablename__
                and foreign_key.column.name == 'id'
            ):
                count = session.execute(
                    sa.select(sa.func.count())
                    .select_from(table)
                    .where(foreign_key.parent == game_log_id)
                ).scalar_one()
                if int(count or 0) > 0:
                    dependencies.append({
                        'table': table.name,
                        'column': foreign_key.parent.name,
                        'count': int(count),
                    })
    dependencies.sort(key=lambda item: (item['table'], item['column']))
    return dependencies


def _build_plan(
    *,
    game_log_id: int,
    expected_game_pk: int,
    expected_game_date: date,
    expected_pitcher_mlb_id: int,
    client,
    session,
):
    row = session.get(GameLog, game_log_id)
    if row is None:
        return None, 'target_game_log_missing'
    if row.mlb_game_pk != expected_game_pk or row.game_date != expected_game_date:
        return None, 'target_identity_mismatch'
    if row.game_date.year != 2026:
        return None, 'target_outside_2026'
    if row.appearance_team_status != ata.STATUS_UNRESOLVED:
        return None, 'target_state_not_unresolved'
    if row.appearance_team_id is not None:
        return None, 'target_unresolved_with_team'
    if not is_all_zero_non_appearance_candidate(row):
        return None, 'target_not_all_zero_non_appearance_candidate'

    pitcher = session.get(Pitcher, row.pitcher_id)
    if pitcher is None:
        return None, 'target_pitcher_missing'
    pitcher_mlb_id = _int_or_none(pitcher.mlb_id)
    if pitcher_mlb_id != expected_pitcher_mlb_id:
        return None, 'target_pitcher_identity_mismatch'

    boxscore = client.get_game_boxscore(expected_game_pk)
    official, official_error = _validate_official_boxscore(boxscore)
    if official_error:
        return None, official_error

    matches = [
        line for line in official['pitching_lines']
        if line['player_id'] == pitcher_mlb_id
    ]
    if len(matches) == 1:
        return None, 'official_pitching_line_present'
    if len(matches) > 1:
        return None, 'official_pitching_identity_contradictory'

    dependencies = _dependent_rows(row.id, session)
    if dependencies:
        return None, 'dependent_rows_present'

    canonical = {
        'contract_version': CONTRACT_VERSION,
        'target': {
            'game_log_id': row.id,
            'game_pk': row.mlb_game_pk,
            'game_date': row.game_date.isoformat(),
            'pitcher_id': row.pitcher_id,
            'pitcher_mlb_id': pitcher_mlb_id,
            'pitcher_name': pitcher.full_name,
            'appearance_team_status': row.appearance_team_status,
            'appearance_team_source': row.appearance_team_source,
            'appearance_team_reason': row.appearance_team_reason,
            'zero_stat_signature': zero_stat_signature(row),
        },
        'official_evidence': {
            'teams': official['teams'],
            'pitching_line_count': len(official['pitching_lines']),
            'pitching_player_ids': [
                line['player_id'] for line in official['pitching_lines']
            ],
            'target_pitcher_present': False,
        },
        'dependent_rows': dependencies,
        'proposed_action': 'delete_phantom_game_log',
    }
    return {
        'fingerprint': _sha256_json(canonical),
        **canonical,
    }, None


def run_reconciliation(
    *,
    game_log_id: int,
    expected_game_pk: int,
    expected_game_date: date,
    expected_pitcher_mlb_id: int,
    apply: bool = False,
    confirmation: Optional[str] = None,
    expected_fingerprint: Optional[str] = None,
    client=mlb_client,
    session=None,
) -> dict:
    """Plan or apply the exact phantom-row deletion."""
    session = session or db.session
    mode = 'apply' if apply else 'dry_run'
    migration_head = _migration_head(session)
    payload = {
        'capability': CAPABILITY,
        'contract_version': CONTRACT_VERSION,
        'mode': mode,
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'database_writes_performed': False,
        'rows_deleted': 0,
    }
    if migration_head != [EXPECTED_MIGRATION_HEAD]:
        payload.update({
            'result': RESULT_FAIL,
            'exit_code': EXIT_BY_RESULT[RESULT_FAIL],
            'decision_reasons': ['migration_head_mismatch'],
        })
        return payload

    try:
        plan, plan_error = _build_plan(
            game_log_id=game_log_id,
            expected_game_pk=expected_game_pk,
            expected_game_date=expected_game_date,
            expected_pitcher_mlb_id=expected_pitcher_mlb_id,
            client=client,
            session=session,
        )
        if plan_error:
            result = (
                RESULT_INCONCLUSIVE
                if plan_error in ('target_game_log_missing', 'official_pitching_line_present')
                else RESULT_FAIL
            )
            payload.update({
                'result': result,
                'exit_code': EXIT_BY_RESULT[result],
                'decision_reasons': [plan_error],
            })
            return payload

        payload['plan'] = plan
        if not apply:
            payload.update({
                'result': RESULT_PASS,
                'exit_code': EXIT_BY_RESULT[RESULT_PASS],
                'decision_reasons': ['verified_phantom_non_appearance_plan_ready'],
            })
            return payload

        if confirmation != CONFIRMATION_PHRASE:
            payload.update({
                'result': RESULT_REFUSED,
                'exit_code': EXIT_BY_RESULT[RESULT_REFUSED],
                'decision_reasons': ['confirmation_mismatch'],
            })
            return payload
        if not expected_fingerprint or expected_fingerprint != plan['fingerprint']:
            payload.update({
                'result': RESULT_REFUSED,
                'exit_code': EXIT_BY_RESULT[RESULT_REFUSED],
                'decision_reasons': ['fingerprint_mismatch'],
            })
            return payload

        row = (
            session.query(GameLog)
            .filter(GameLog.id == game_log_id)
            .with_for_update()
            .one_or_none()
        )
        if (
            row is None
            or row.mlb_game_pk != expected_game_pk
            or row.game_date != expected_game_date
            or row.appearance_team_status != ata.STATUS_UNRESOLVED
            or row.appearance_team_id is not None
            or not is_all_zero_non_appearance_candidate(row)
        ):
            session.rollback()
            payload.update({
                'result': RESULT_REFUSED,
                'exit_code': EXIT_BY_RESULT[RESULT_REFUSED],
                'decision_reasons': ['target_changed_since_plan'],
            })
            return payload

        pitcher = session.get(Pitcher, row.pitcher_id)
        if pitcher is None or _int_or_none(pitcher.mlb_id) != expected_pitcher_mlb_id:
            session.rollback()
            payload.update({
                'result': RESULT_REFUSED,
                'exit_code': EXIT_BY_RESULT[RESULT_REFUSED],
                'decision_reasons': ['target_pitcher_changed_since_plan'],
            })
            return payload
        if _dependent_rows(row.id, session):
            session.rollback()
            payload.update({
                'result': RESULT_REFUSED,
                'exit_code': EXIT_BY_RESULT[RESULT_REFUSED],
                'decision_reasons': ['dependent_rows_changed_since_plan'],
            })
            return payload

        session.delete(row)
        session.commit()
        payload.update({
            'result': RESULT_PASS,
            'exit_code': EXIT_BY_RESULT[RESULT_PASS],
            'decision_reasons': ['verified_phantom_non_appearance_deleted'],
            'rows_deleted': 1,
            'database_writes_performed': True,
        })
        return payload
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        payload.update({
            'result': RESULT_FAIL,
            'exit_code': EXIT_BY_RESULT[RESULT_FAIL],
            'decision_reasons': ['phantom_reconciliation_execution_failed'],
            'error_type': type(exc).__name__,
        })
        return payload
