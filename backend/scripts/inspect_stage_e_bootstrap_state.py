#!/usr/bin/env python
"""Read-only production state snapshot for the Foundation 3C Stage E closeout.

Stage E makes one claim: the 109-game bootstrap is complete, and verifying it
changes nothing. Both halves need measuring, so this takes the same
deterministic snapshot before and after the full replay and the validator
compares them.

The transaction is set read-only and a write probe must be REFUSED before a
single row is read. `session.bind` is None until the session has been used, so
the engine is resolved explicitly — reading it lazily is how a guard like this
silently degrades into no protection at all. There is no mutation fallback: if
read-only cannot be proven, nothing is inspected.

DEAD LETTERS ARE COUNTED TWO WAYS ON PURPOSE. The governed count covers only the
109 bootstrap games and must be zero. The global count covers the whole system,
was already 1,389 at R6 closeout, and has nothing to do with Foundation 3C.
Reporting one number would either hide a governed failure or falsely claim the
system has no dead letters.

TEMPORARY. Retained only until Stage E2 removes it with the Stage E workflow.

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
if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import stage_e_bootstrap_scope as scope  # noqa: E402


EXIT_OK = 0
EXIT_ERROR = 2

PHASE_BEFORE = 'before'
PHASE_AFTER = 'after'
PHASES = (PHASE_BEFORE, PHASE_AFTER)

REFERENCE_DATE = scope.REFERENCE_DATE
GOVERNED_GAME_PKS = scope.SORTED_SET


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


def collect_state(game_pks=GOVERNED_GAME_PKS) -> dict:
    """The deterministic evidence the before/after comparison rests on."""
    from datetime import date

    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.sync_failure import SyncFailure
    from services import game_driven_ingestion
    from services import game_ingestion_completeness
    from services import game_ingestion_planner
    from services import game_log_reconciliation as reconciliation
    from services import pitcher_identity_reconciliation as identity

    game_pks = sorted(game_pks)
    reference_date = date.fromisoformat(REFERENCE_DATE)

    logs = (
        GameLog.query
        .filter(GameLog.mlb_game_pk.in_(game_pks))
        .order_by(GameLog.mlb_game_pk, GameLog.pitcher_id)
        .all()
    )
    pitcher_by_id = {
        row.id: row for row in Pitcher.query.filter(
            Pitcher.id.in_(sorted({log.pitcher_id for log in logs}) or [-1])
        ).all()
    }

    # ── Baseball-data families, hashed independently ────────────────────────
    content_rows = [
        (
            row.mlb_game_pk,
            getattr(pitcher_by_id.get(row.pitcher_id), 'mlb_id', None),
            row.earned_runs, row.runs_allowed, row.hits_allowed, row.walks,
            row.strikeouts, row.home_runs_allowed, row.batters_faced,
            row.strikes, row.pitches_thrown, row.games_started, row.opponent,
            row.opponent_abbreviation, _iso(row.game_date), row.game_type,
        )
        for row in logs
    ]
    canonical_outs_rows = [
        (
            row.mlb_game_pk,
            getattr(pitcher_by_id.get(row.pitcher_id), 'mlb_id', None),
            row.innings_pitched_outs, row.innings_pitched,
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

    pitchers = sorted(pitcher_by_id.values(), key=lambda row: row.id)
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

    # ── Governed control state ──────────────────────────────────────────────
    governed_items = (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.mlb_game_pk.in_(game_pks))
        .order_by(GameIngestionWorkItem.mlb_game_pk, GameIngestionWorkItem.id)
        .all()
    )
    governed_work_items = {
        str(item.mlb_game_pk): {
            'status': item.status,
            'attempt_count': item.attempt_count or 0,
            'criticality': item.criticality,
            'error_class': item.error_class,
            'rows_expected': item.rows_expected,
            'rows_reconciled': item.rows_reconciled,
            'completed': item.status == GameIngestionWorkItem.STATUS_COMPLETED,
        }
        for item in governed_items
    }
    # Counted from ROWS, not the keyed mapping: a duplicate work item for one
    # game collapses to a single key and would otherwise be invisible.
    duplicate_governed_game_pks = sorted({
        item.mlb_game_pk for item in governed_items
        if sum(1 for other in governed_items
               if other.mlb_game_pk == item.mlb_game_pk) > 1
    })
    governed_completed_set = sorted({
        item.mlb_game_pk for item in governed_items
        if item.status == GameIngestionWorkItem.STATUS_COMPLETED
    })
    governed_unresolved_set = sorted({
        item.mlb_game_pk for item in governed_items
        if item.status in GameIngestionWorkItem.UNRESOLVED_STATUSES
    })
    governed_terminal_set = sorted({
        item.mlb_game_pk for item in governed_items
        if item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
    })
    governed_work_item_rows = [
        (item.mlb_game_pk, item.status, item.attempt_count or 0,
         item.rows_expected, item.rows_reconciled)
        for item in governed_items
    ]

    all_items = GameIngestionWorkItem.query.order_by(
        GameIngestionWorkItem.mlb_game_pk, GameIngestionWorkItem.id
    ).all()
    completed_work_item_set = sorted({
        item.mlb_game_pk for item in all_items
        if item.status == GameIngestionWorkItem.STATUS_COMPLETED
    })
    terminal_work_item_set = sorted({
        item.mlb_game_pk for item in all_items
        if item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
    })

    # ── Publication completeness, from one shared plan ──────────────────────
    plan = game_ingestion_planner.plan_game_work(reference_date)
    completeness = game_ingestion_completeness.build_game_ingestion_completeness(
        reference_date, plan=plan,
    )
    planned_items = list(plan.get('items') or [])
    critical_items = [
        item for item in planned_items
        if item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    ]
    outstanding_critical = sorted({
        item.game_pk for item in critical_items
        if item.candidate_reason != GameIngestionWorkItem.REASON_CORRECTED_FINAL
    })
    unresolved_items = sorted({
        item.mlb_game_pk for item in all_items
        if item.status in GameIngestionWorkItem.UNRESOLVED_STATUSES
        and item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    })
    unresolved_set = sorted(set(outstanding_critical) | set(unresolved_items))

    # ── Dead letters, counted two ways ──────────────────────────────────────
    governed_dead_letters = SyncFailure.query.filter(
        SyncFailure.entity_ref.in_([str(pk) for pk in game_pks])
    ).count()
    global_dead_letters = SyncFailure.query.count()

    return {
        'reference_date': REFERENCE_DATE,
        'governed_game_pks': game_pks,
        'governed_game_count': len(game_pks),
        'full_scope_digest': scope.scope_digest(game_pks),

        'game_log_row_count': len(logs),
        'game_log_content_hash': _hash(content_rows),
        'canonical_outs_hash': _hash(canonical_outs_rows),
        'correction_provenance_hash': _hash(correction_rows),
        'appearance_team_hash': _hash(appearance_team_rows),
        'pitcher_state_hash': _hash(pitcher_rows),
        'pitcher_count': len(pitchers),
        'pitcher_mlb_ids': sorted(row.mlb_id for row in pitchers),

        'governed_work_items': governed_work_items,
        'governed_work_item_count': len(governed_items),
        'governed_work_items_hash': _hash(governed_work_item_rows),
        'governed_completed_set': governed_completed_set,
        'governed_unresolved_set': governed_unresolved_set,
        'governed_terminal_set': governed_terminal_set,
        'duplicate_governed_game_pks': duplicate_governed_game_pks,
        'completed_work_item_set': completed_work_item_set,
        'terminal_work_item_set': terminal_work_item_set,
        'unresolved_set': unresolved_set,

        'governed_dead_letter_count': governed_dead_letters,
        'global_dead_letter_count': global_dead_letters,
        'r6_global_dead_letter_count': scope.R6_GLOBAL_DEAD_LETTER_COUNT,
        'global_dead_letter_delta': (
            global_dead_letters - scope.R6_GLOBAL_DEAD_LETTER_COUNT
        ),

        'version_constants': {
            'reconciliation_plan_version':
                reconciliation.RECONCILIATION_PLAN_VERSION,
            'parity_contract_version': reconciliation.PARITY_CONTRACT_VERSION,
            'innings_semantics_version':
                reconciliation.INNINGS_SEMANTICS_VERSION,
            'complete_plan_version': reconciliation.COMPLETE_PLAN_VERSION,
            'identity_plan_version': identity.IDENTITY_PLAN_VERSION,
        },
        'automated_lane': game_driven_ingestion.ingestion_mode(),
        'authoritative_mode': 'unapproved',

        'publication_completeness': {
            'expected_final_games': completeness.get('expected_final_games'),
            'completed_final_games': completeness.get('completed_final_games'),
            'unresolved_final_games': completeness.get('unresolved_final_games'),
            'terminal_failure_games': completeness.get('terminal_failure_games'),
            'correction_pending_games': completeness.get(
                'correction_pending_games'
            ),
            'critical_appearance_rows_expected': completeness.get(
                'critical_appearance_rows_expected'
            ),
            'critical_appearance_rows_reconciled': completeness.get(
                'critical_appearance_rows_reconciled'
            ),
            'publication_complete': bool(
                completeness.get('publication_complete')
            ),
        },
    }


def inspect(phase, game_pks=GOVERNED_GAME_PKS) -> dict:
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
        description='Read-only Foundation 3C Stage E bootstrap state snapshot.',
    )
    parser.add_argument('--phase', required=True, choices=list(PHASES))
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
