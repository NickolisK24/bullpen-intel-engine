#!/usr/bin/env python
"""Read-only production state snapshot for the Foundation 3C R4 controlled write.

R4 claims that exactly one thing changed: five governed work items completed and
publication completeness moved 5/104 -> 10/99. Every baseball-data row must be
byte-identical afterwards.

A claim like that is only worth what it is measured against, so this tool takes
the same deterministic snapshot before and after the write and the validator
compares them. It hashes content rather than dumping it: a hash is enough to
prove nothing moved, and it cannot leak a payload.

The transaction is set read-only and a write probe must be REFUSED before a
single row is read. `session.bind` is None until the session has been used, so
the engine is resolved explicitly — reading it lazily is how a guard like this
silently degrades to no protection at all.

Output carries only safe structured evidence: game ids, MLB ids, counts,
statuses, and hashes. No credentials, connection strings, payloads, headers,
filesystem paths, or exception text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


EXIT_OK = 0
EXIT_ERROR = 2

REFERENCE_DATE = '2026-07-29'
SELECTED_GAME_PKS = (823110, 825055, 824004, 823438, 824408)

PHASE_BEFORE = 'before'
PHASE_AFTER = 'after'


class ReadOnlyNotEnforced(RuntimeError):
    """The session could not be proven read-only, so nothing is inspected."""


def _enforce_read_only(session) -> dict:
    """Set the transaction read-only and PROVE a write is refused."""
    from sqlalchemy import text

    bind = session.get_bind()
    dialect = bind.dialect.name
    if dialect != 'postgresql':
        raise ReadOnlyNotEnforced(dialect)

    session.execute(text('SET TRANSACTION READ ONLY'))
    try:
        session.execute(text(
            'UPDATE game_logs SET stat_correction_count = stat_correction_count '
            'WHERE 1 = 0'
        ))
        refused = False
    except Exception:  # noqa: BLE001 - the refusal itself is the signal
        session.rollback()
        session.execute(text('SET TRANSACTION READ ONLY'))
        refused = True

    if not refused:
        raise ReadOnlyNotEnforced('postgresql_read_only_transaction')
    return {
        'dialect': dialect,
        'protection': 'postgresql_read_only_transaction',
        'write_probe_refused': refused,
    }


def _hash(rows) -> str:
    """Deterministic content hash over a sorted, JSON-encoded row set."""
    encoded = json.dumps(
        sorted(rows), sort_keys=True, separators=(',', ':'), default=str,
    )
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()


def _iso(value):
    return value.isoformat() if value is not None else None


def collect_state(game_pks=SELECTED_GAME_PKS) -> dict:
    """The deterministic evidence the before/after comparison rests on."""
    from datetime import date

    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.sync_failure import SyncFailure
    from services import game_ingestion_completeness
    from utils.db import db

    game_pks = sorted(game_pks)

    logs = (
        GameLog.query
        .filter(GameLog.mlb_game_pk.in_(game_pks))
        .order_by(GameLog.mlb_game_pk, GameLog.pitcher_id)
        .all()
    )

    # ── GameLog content, correction provenance, appearance-team authority ────
    # Hashed as three independent families so the validator can say WHICH of
    # them moved rather than only that something did.
    content_rows = [
        (
            row.mlb_game_pk, row.pitcher_id, row.innings_pitched_outs,
            row.innings_pitched, row.earned_runs, row.runs_allowed,
            row.hits_allowed, row.walks, row.strikeouts, row.home_runs_allowed,
            row.batters_faced, row.strikes, row.pitches_thrown,
            row.games_started, row.opponent, row.opponent_abbreviation,
            _iso(row.game_date), row.game_type,
        )
        for row in logs
    ]
    correction_rows = [
        (
            row.mlb_game_pk, row.pitcher_id, row.stat_correction_count,
            _iso(row.last_stat_correction_at), row.last_stat_correction_source,
            row.last_stat_correction_sync_run_id,
        )
        for row in logs
    ]
    appearance_team_rows = [
        (
            row.mlb_game_pk, row.pitcher_id, row.appearance_team_id,
            row.appearance_team_source, row.appearance_team_status,
            row.appearance_team_reason,
        )
        for row in logs
    ]

    # ── Pitcher current state for exactly the arms in these games ───────────
    pitcher_ids = sorted({row.pitcher_id for row in logs})
    pitchers = (
        Pitcher.query
        .filter(Pitcher.id.in_(pitcher_ids or [-1]))
        .order_by(Pitcher.id)
        .all()
    )
    pitcher_rows = [
        (
            row.mlb_id, row.full_name, row.position, row.active, row.team_id,
            row.team_name, row.team_abbreviation, row.team_assignment_status,
            row.team_assignment_source, _iso(row.team_assignment_updated_at),
            row.roster_status, row.roster_status_source,
            row.roster_status_raw_code, row.roster_status_raw_description,
            _iso(row.roster_status_updated_at),
        )
        for row in pitchers
    ]

    # ── Governed control state: the ONLY thing R4 may change ────────────────
    work_items = (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.mlb_game_pk.in_(game_pks))
        .order_by(GameIngestionWorkItem.mlb_game_pk)
        .all()
    )
    selected_work_items = {
        str(item.mlb_game_pk): {
            'status': item.status,
            'attempt_count': item.attempt_count or 0,
            'candidate_reason': item.candidate_reason,
            'criticality': item.criticality,
            'rows_expected': item.rows_expected,
            'rows_reconciled': item.rows_reconciled,
            'correction_count': item.correction_count or 0,
            'error_class': item.error_class,
            'completed': item.status == GameIngestionWorkItem.STATUS_COMPLETED,
        }
        for item in work_items
    }
    # Every work item in the database, so an unexpected change to a game
    # OUTSIDE the approved five is detectable rather than invisible.
    all_work_items = [
        (item.mlb_game_pk, item.status, item.attempt_count or 0)
        for item in GameIngestionWorkItem.query.order_by(
            GameIngestionWorkItem.mlb_game_pk
        ).all()
    ]

    completeness = game_ingestion_completeness.build_game_ingestion_completeness(
        date.fromisoformat(REFERENCE_DATE)
    )

    dead_letters = SyncFailure.query.filter(
        SyncFailure.entity_ref.in_([str(pk) for pk in game_pks])
    ).count()

    return {
        'reference_date': REFERENCE_DATE,
        'selected_game_pks': game_pks,
        'game_log_row_count': len(logs),
        'game_log_content_hash': _hash(content_rows),
        'correction_provenance_hash': _hash(correction_rows),
        'appearance_team_hash': _hash(appearance_team_rows),
        'pitcher_state_hash': _hash(pitcher_rows),
        'pitcher_count': len(pitchers),
        'pitcher_mlb_ids': sorted(row.mlb_id for row in pitchers),
        'selected_work_items': selected_work_items,
        'selected_completed_count': sum(
            1 for item in selected_work_items.values() if item['completed']
        ),
        'all_work_items_hash': _hash(all_work_items),
        'all_work_item_count': len(all_work_items),
        'dead_letter_count': dead_letters,
        'publication_completeness': {
            'expected_final_games': completeness.get('expected_final_games'),
            'completed_final_games': completeness.get('completed_final_games'),
            'unresolved_final_games': completeness.get('unresolved_final_games'),
            'terminal_failure_games': completeness.get('terminal_failure_games'),
            'correction_pending_games': completeness.get(
                'correction_pending_games'
            ),
            'publication_complete': bool(
                completeness.get('publication_complete')
            ),
        },
    }


def inspect(phase, game_pks=SELECTED_GAME_PKS) -> dict:
    """Prove the session is read-only, THEN read. Fails closed."""
    from utils.db import db

    read_only = _enforce_read_only(db.session)
    state = collect_state(game_pks)
    state['phase'] = phase
    state['read_only'] = read_only
    state['read_only_after'] = _enforce_read_only(db.session)
    return state


def build_app():
    import app as app_module

    return app_module.create_app()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Read-only Foundation 3C R4 production state snapshot.',
    )
    parser.add_argument(
        '--phase', required=True, choices=[PHASE_BEFORE, PHASE_AFTER],
    )
    parser.add_argument('--output', required=True)
    args = parser.parse_args(argv)

    try:
        flask_app = build_app()
        with flask_app.app_context():
            report = inspect(args.phase)
        exit_code = EXIT_OK
    except ReadOnlyNotEnforced as failure:
        report = {
            'phase': args.phase,
            'result': 'ERROR',
            'error': 'read_only_not_enforced',
            'observed_protection': str(failure),
            'sanitized': True,
        }
        exit_code = EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - never leak exception text
        report = {
            'phase': args.phase,
            'result': 'ERROR',
            'exception_type': type(exc).__name__,
            'sanitized': True,
        }
        exit_code = EXIT_ERROR

    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
