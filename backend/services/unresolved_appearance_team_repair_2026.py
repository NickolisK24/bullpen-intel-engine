"""Governed one-row repair for an explicit unresolved 2026 appearance-team record.

This service is intentionally narrower than the historical Foundation 2 backfill. The
backfill targets only legacy NULL rows and must never overwrite an explicit unresolved
state. This repair instead targets one exact GameLog identity, re-derives its team from
the official MLB box-score pitching side, produces a deterministic fingerprint in dry
run, and writes only the four appearance_team_* columns after explicit approval.
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


CAPABILITY = 'unresolved_appearance_team_repair_2026_v1'
CONTRACT_VERSION = 'unresolved_appearance_team_repair_2026.v1'
# Advanced by Foundation 3C (b9d4e17c3a80): the game-driven ingestion
# work-state checkpoint is purely additive — one new table, no change to
# game_logs, scheduled_games, or pitchers — so the schema this tool was
# validated against is unchanged. The pin still refuses to run against an
# unexpected head.
EXPECTED_MIGRATION_HEAD = 'b9d4e17c3a80'
CONFIRMATION_PHRASE = 'RUN_UNRESOLVED_APPEARANCE_TEAM_REPAIR_2026'

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


def _int_or_none(value) -> Optional[int]:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


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


def _side_team_id(boxscore, side):
    team = ((((boxscore or {}).get('teams') or {}).get(side) or {}).get('team') or {})
    return _int_or_none(team.get('id'))


def _unique_pitching_line(boxscore, pitcher_mlb_id):
    matches = []
    for line in sync_service._extract_pitching_lines_from_boxscore(boxscore):
        player_id = _int_or_none(line.get('person_id') or line.get('player_id'))
        if player_id == pitcher_mlb_id:
            matches.append(line)
    if len(matches) != 1:
        return None, (
            'official_pitching_line_missing'
            if not matches
            else 'official_pitching_line_contradictory'
        )
    return matches[0], None


def _build_plan(*, game_log_id, expected_game_pk, expected_game_date, client, session):
    row = session.get(GameLog, game_log_id)
    if row is None:
        return None, 'target_game_log_missing'
    if row.mlb_game_pk != expected_game_pk or row.game_date != expected_game_date:
        return None, 'target_identity_mismatch'
    if row.game_date.year != 2026:
        return None, 'target_outside_2026'
    if row.appearance_team_status == ata.STATUS_RESOLVED:
        return None, 'target_already_resolved'
    if row.appearance_team_status != ata.STATUS_UNRESOLVED:
        return None, 'target_state_not_unresolved'
    if row.appearance_team_id is not None:
        return None, 'target_unresolved_with_team'

    pitcher = session.get(Pitcher, row.pitcher_id)
    if pitcher is None or _int_or_none(pitcher.mlb_id) is None:
        return None, 'target_pitcher_authority_missing'
    pitcher_mlb_id = int(pitcher.mlb_id)

    boxscore = client.get_game_boxscore(expected_game_pk)
    line, line_error = _unique_pitching_line(boxscore, pitcher_mlb_id)
    if line_error:
        return None, line_error

    side = line.get('side')
    if side not in ('home', 'away'):
        return None, 'official_pitching_side_missing'
    opposite = 'away' if side == 'home' else 'home'
    side_team_id = _side_team_id(boxscore, side)
    opponent_team_id = _side_team_id(boxscore, opposite)
    line_team_id = _int_or_none(line.get('team_id'))
    if side_team_id is None or opponent_team_id is None:
        return None, 'official_boxscore_team_identity_missing'
    if line_team_id is not None and line_team_id != side_team_id:
        return None, 'official_boxscore_team_identity_contradictory'

    resolution = ata.resolve_for_write(
        boxscore_team_id=side_team_id,
        game_pk=expected_game_pk,
        opponent_team_id=opponent_team_id,
        session=session,
    )
    if not resolution.resolved:
        return None, (
            'official_team_authority_conflict'
            if resolution.status == ata.STATUS_CONFLICT
            else 'official_team_authority_unresolved'
        )

    canonical = {
        'contract_version': CONTRACT_VERSION,
        'game_log_id': row.id,
        'game_pk': row.mlb_game_pk,
        'game_date': row.game_date.isoformat(),
        'pitcher_id': row.pitcher_id,
        'pitcher_mlb_id': pitcher_mlb_id,
        'stored': {
            'appearance_team_id': row.appearance_team_id,
            'appearance_team_source': row.appearance_team_source,
            'appearance_team_status': row.appearance_team_status,
            'appearance_team_reason': row.appearance_team_reason,
        },
        'official_evidence': {
            'side': side,
            'team_id': side_team_id,
            'opponent_team_id': opponent_team_id,
        },
        'proposed': resolution.to_write_fields(),
    }
    return {
        'fingerprint': _sha256_json(canonical),
        'target': {
            'game_log_id': row.id,
            'game_pk': row.mlb_game_pk,
            'game_date': row.game_date.isoformat(),
            'pitcher_id': row.pitcher_id,
            'pitcher_mlb_id': pitcher_mlb_id,
        },
        'official_evidence': canonical['official_evidence'],
        'proposed': canonical['proposed'],
    }, None


def _base_payload(*, mode, migration_head):
    return {
        'capability': CAPABILITY,
        'contract_version': CONTRACT_VERSION,
        'mode': mode,
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'database_writes_performed': False,
    }


def run_repair(
    *,
    game_log_id: int,
    expected_game_pk: int,
    expected_game_date: date,
    apply: bool = False,
    confirmation: Optional[str] = None,
    expected_fingerprint: Optional[str] = None,
    client=mlb_client,
    session=None,
):
    session = session or db.session
    mode = 'apply' if apply else 'dry_run'
    migration_head = _migration_head(session)
    payload = _base_payload(mode=mode, migration_head=migration_head)
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
            client=client,
            session=session,
        )
        if plan_error:
            result = RESULT_INCONCLUSIVE if plan_error == 'target_already_resolved' else RESULT_FAIL
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
                'decision_reasons': ['official_boxscore_plan_ready'],
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
        ):
            session.rollback()
            payload.update({
                'result': RESULT_REFUSED,
                'exit_code': EXIT_BY_RESULT[RESULT_REFUSED],
                'decision_reasons': ['target_changed_since_plan'],
            })
            return payload

        proposed = plan['proposed']
        row.appearance_team_id = proposed['appearance_team_id']
        row.appearance_team_source = proposed['appearance_team_source']
        row.appearance_team_status = proposed['appearance_team_status']
        row.appearance_team_reason = proposed['appearance_team_reason']
        session.commit()

        payload.update({
            'result': RESULT_PASS,
            'exit_code': EXIT_BY_RESULT[RESULT_PASS],
            'decision_reasons': ['unresolved_appearance_team_repaired'],
            'rows_written': 1,
            'database_writes_performed': True,
        })
        return payload
    except Exception as exc:  # noqa: BLE001
        session.rollback()
        payload.update({
            'result': RESULT_FAIL,
            'exit_code': EXIT_BY_RESULT[RESULT_FAIL],
            'decision_reasons': ['repair_execution_failed'],
            'error_type': type(exc).__name__,
        })
        return payload
