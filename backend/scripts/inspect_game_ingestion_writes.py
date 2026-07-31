#!/usr/bin/env python
"""Read-only forensics for games already processed by the game-driven lane.

Answers one question about an already-written game: what durable evidence
survives about the mutations that were applied, and how much of the prior
state can honestly be reconstructed?

    python scripts/inspect_game_ingestion_writes.py --game-pk 823518 --game-pk 824735

It performs NO writes. Every database session it opens is set read-only at the
engine, and it actively probes that a write is refused before reporting
anything, so "read-only" is proven rather than asserted. It never re-fetches
MLB and never reconciles: it only reads what is already stored.

Output is one JSON document. It carries governed baseball fields and safe
provenance only — never credentials, connection strings, headers, raw payloads,
filesystem paths, or exception text.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


EXIT_OK = 0
EXIT_NOT_READ_ONLY = 1
EXIT_ERROR = 2

# What a reconstruction can honestly claim.
CONCLUSION_EXACT = 'exact_prior_values_reconstructed'
CONCLUSION_CATEGORIES = 'categories_reconstructed_prior_values_not_retained'
CONCLUSION_CODE_PATH_ONLY = 'not_reconstructible_code_path_cause_only'


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only inspection of already-written game ingestion.',
    )
    parser.add_argument(
        '--game-pk', type=int, action='append', required=True,
        help='Repeatable. Game identifiers to inspect.',
    )
    parser.add_argument('--output', help='Write the JSON report to this path.')
    return parser.parse_args(argv)


class ReadOnlyNotEnforced(RuntimeError):
    """The session could not be proven read-only, so nothing is inspected."""


def _enforce_read_only(session) -> dict:
    """Set the transaction read-only and PROVE a write is refused.

    Fails closed. ``session.bind`` is None until the session has been used, so
    the engine is resolved explicitly — reading it lazily is how a guard like
    this silently degrades to no protection at all.
    """
    from sqlalchemy import text

    bind = session.get_bind()
    dialect = bind.dialect.name
    protection = 'none'
    if dialect == 'postgresql':
        session.execute(text('SET TRANSACTION READ ONLY'))
        protection = 'postgresql_read_only_transaction'
    else:
        raise ReadOnlyNotEnforced(dialect)

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
        raise ReadOnlyNotEnforced(protection)
    return {
        'dialect': dialect,
        'protection': protection,
        'write_probe_refused': refused,
    }


def _row_evidence(row) -> dict:
    return {
        'game_log_id': row.id,
        'pitcher_id': row.pitcher_id,
        'innings_pitched_outs': row.innings_pitched_outs,
        'earned_runs': row.earned_runs,
        'runs_allowed': row.runs_allowed,
        'hits_allowed': row.hits_allowed,
        'walks': row.walks,
        'strikeouts': row.strikeouts,
        'home_runs_allowed': row.home_runs_allowed,
        'batters_faced': row.batters_faced,
        'strikes': row.strikes,
        'pitches_thrown': row.pitches_thrown,
        'games_started': row.games_started,
        'opponent_abbreviation': row.opponent_abbreviation,
        'appearance_team_id': row.appearance_team_id,
        'appearance_team_source': row.appearance_team_source,
        'appearance_team_status': row.appearance_team_status,
        'appearance_team_reason': row.appearance_team_reason,
        'stat_correction_count': row.stat_correction_count or 0,
        'last_stat_correction_at': (
            row.last_stat_correction_at.isoformat()
            if row.last_stat_correction_at else None
        ),
        'last_stat_correction_source': row.last_stat_correction_source,
        'last_stat_correction_sync_run_id': row.last_stat_correction_sync_run_id,
    }


def inspect(game_pks) -> dict:
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.postgame_processed_game import PostgameProcessedGame
    from models.sync_failure import SyncFailure
    from utils.db import db

    read_only = _enforce_read_only(db.session)

    games = []
    for game_pk in sorted(set(game_pks)):
        rows = (
            GameLog.query
            .filter(GameLog.mlb_game_pk == game_pk)
            .order_by(GameLog.id)
            .all()
        )
        work_item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=game_pk
        ).first()
        marker = PostgameProcessedGame.query.filter_by(
            mlb_game_pk=game_pk
        ).first()
        failures = (
            SyncFailure.query
            .filter(SyncFailure.entity_ref == str(game_pk))
            .order_by(SyncFailure.id)
            .all()
        )

        corrected_rows = [
            row for row in rows if (row.stat_correction_count or 0) > 0
        ]
        # A correction counter records THAT a row was corrected and by which
        # source and run — never what the row said before. Nothing durable
        # retains the prior values, so the honest conclusion is bounded.
        conclusion = (
            CONCLUSION_CATEGORIES if corrected_rows
            else CONCLUSION_CODE_PATH_ONLY
        )

        games.append({
            'game_pk': game_pk,
            'appearance_rows': len(rows),
            'rows_with_a_recorded_correction': len(corrected_rows),
            'correction_sources': sorted({
                row.last_stat_correction_source
                for row in corrected_rows if row.last_stat_correction_source
            }),
            'correction_sync_run_ids': sorted({
                row.last_stat_correction_sync_run_id
                for row in corrected_rows
                if row.last_stat_correction_sync_run_id is not None
            }),
            'work_item': work_item.to_dict() if work_item else None,
            'postgame_marker': marker.to_dict() if marker else None,
            'sync_failures': [
                {
                    'id': failure.id,
                    'entity_type': failure.entity_type,
                    'resolved': bool(failure.resolved),
                }
                for failure in failures
            ],
            'rows': [_row_evidence(row) for row in rows],
            'prior_value_reconstruction': {
                'conclusion': conclusion,
                'exact_prior_values_available': False,
                'why': (
                    'The canonical writer records that a correction occurred '
                    '(counter, timestamp, source, sync run) but does not retain '
                    'the superseded values. No durable before-image exists for '
                    'these rows.'
                ),
            },
        })

    after = _enforce_read_only(db.session)
    return {
        'result': 'OK',
        'read_only': read_only,
        'read_only_after': after,
        'games': games,
        'production_rows_mutated': 0,
    }


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        import app as app_module

        flask_app = app_module.create_app()
        with flask_app.app_context():
            report = inspect(args.game_pk)
            from utils.db import db

            db.session.rollback()
        exit_code = EXIT_OK
    except ReadOnlyNotEnforced:
        report = {
            'result': 'READ_ONLY_NOT_ENFORCED',
            'sanitized': True,
            'production_rows_mutated': 0,
        }
        exit_code = EXIT_NOT_READ_ONLY
    except Exception as exc:  # noqa: BLE001 - never leak exception text
        report = {
            'result': 'ERROR',
            'exception_type': type(exc).__name__,
            'sanitized': True,
        }
        exit_code = EXIT_ERROR

    encoded = json.dumps(report, indent=2, sort_keys=True, default=str)
    if args.output:
        target = Path(args.output)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded + '\n', encoding='utf-8')
    else:
        print(encoded)
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
