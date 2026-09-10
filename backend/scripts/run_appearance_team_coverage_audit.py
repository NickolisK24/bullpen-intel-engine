"""Run the Foundation 1 appearance-team production audit against DATABASE_URL.

The command reads aggregate and bounded row-level diagnostics only. It never
backfills data, changes an appearance, commits a transaction, or exposes a web
route. Clean JSON can be written to ``--output`` for a private workflow artifact.

Result contract:
    PASS (exit 0)
        The Foundation 1 migration is the sole database head, stored-state
        invariants are valid, and every row created on/after ``--new-row-since``
        is resolved.
    INCONCLUSIVE (exit 1)
        The schema and stored states are valid, but no post-cutover row exists or
        at least one post-cutover row is validly unresolved/conflicted.
    FAIL (exit 2)
        The migration head is wrong, aggregate counts disagree, a malformed
        stored state exists, or the audit itself cannot complete.

Only exception class names are reported. Exception messages are deliberately
discarded because database errors can contain connection details.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator diagnostic command, not a web worker: never start background sync.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'appearance_team_production_audit_v1'
COVERAGE_CAPABILITY = 'appearance_team_coverage_v1'
# Advanced by Foundation 3C (b9d4e17c3a80): the game-driven ingestion
# work-state checkpoint is purely additive — one new table, no change to
# game_logs, scheduled_games, or pitchers — so the schema this tool was
# validated against is unchanged. The pin still refuses to run against an
# unexpected head.
EXPECTED_MIGRATION_HEAD = 'b9d4e17c3a80'
MODE = 'read_only'
RESULT_PASS = 'PASS'
RESULT_INCONCLUSIVE = 'INCONCLUSIVE'
RESULT_FAIL = 'FAIL'
EXIT_BY_RESULT = {
    RESULT_PASS: 0,
    RESULT_INCONCLUSIVE: 1,
    RESULT_FAIL: 2,
}
DEFAULT_ROW_LIMIT = 50
MAX_ROW_LIMIT = 100


def _utc_timestamp(value):
    candidate = str(value or '').strip()
    if candidate.endswith('Z'):
        candidate = candidate[:-1] + '+00:00'
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            'new-row-since must be an ISO-8601 timestamp with a timezone.'
        ) from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError(
            'new-row-since must include an explicit timezone.'
        )
    return parsed.astimezone(timezone.utc)


def _bounded_row_limit(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise argparse.ArgumentTypeError('row-limit must be an integer.') from exc
    if parsed < 1 or parsed > MAX_ROW_LIMIT:
        raise argparse.ArgumentTypeError(
            f'row-limit must be between 1 and {MAX_ROW_LIMIT}.'
        )
    return parsed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Run the read-only Foundation 1 appearance-team production audit '
            'against DATABASE_URL.'
        ),
    )
    parser.add_argument(
        '--new-row-since',
        required=True,
        type=_utc_timestamp,
        help=(
            'Inclusive Foundation 1 production cutover timestamp in ISO-8601 '
            'format with a timezone.'
        ),
    )
    parser.add_argument(
        '--row-limit',
        type=_bounded_row_limit,
        default=DEFAULT_ROW_LIMIT,
        help=(
            'Maximum non-resolved rows included in the artifact '
            f'(default {DEFAULT_ROW_LIMIT}; max {MAX_ROW_LIMIT}).'
        ),
    )
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Print compact JSON instead of indented JSON.',
    )
    parser.add_argument(
        '--output',
        type=Path,
        help='Optional path to also write the clean JSON audit artifact.',
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress the result line written to stderr.',
    )
    return parser.parse_args(argv)


def _serialize(payload, *, compact):
    return json.dumps(
        payload,
        indent=None if compact else 2,
        sort_keys=True,
        default=str,
    )


def _emit(payload, *, compact, output):
    encoded = _serialize(payload, compact=compact)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + '\n', encoding='utf-8')
    print(encoded)


def _count(query):
    return int(query.count())


def _migration_summary(session):
    from sqlalchemy import text

    current_heads = sorted(
        str(row[0])
        for row in session.execute(
            text('SELECT version_num FROM alembic_version ORDER BY version_num')
        )
    )
    return {
        'expected_head': EXPECTED_MIGRATION_HEAD,
        'current_heads': current_heads,
        'head_matches': current_heads == [EXPECTED_MIGRATION_HEAD],
    }


def _coverage_contract(coverage):
    status_total = sum(
        int(coverage.get(field, 0))
        for field in ('resolved', 'unresolved', 'conflict', 'null_legacy')
    )
    source_total = sum(int(value) for value in (coverage.get('by_source') or {}).values())
    season_total = sum(
        int(value)
        for counts in (coverage.get('by_season') or {}).values()
        for value in counts.values()
    )
    total = int(coverage.get('total_game_logs', 0))
    return {
        'status_total': status_total,
        'source_total': source_total,
        'season_total': season_total,
        'totals_match': status_total == source_total == season_total == total,
    }


def _status_counts(session, query):
    from models.game_log import GameLog
    from services.appearance_team_authority import (
        STATUS_CONFLICT,
        STATUS_RESOLVED,
        STATUS_UNRESOLVED,
    )

    total = _count(query.with_entities(GameLog.id))
    return {
        'total': total,
        'resolved': _count(
            query.filter(GameLog.appearance_team_status == STATUS_RESOLVED)
        ),
        'unresolved': _count(
            query.filter(GameLog.appearance_team_status == STATUS_UNRESOLVED)
        ),
        'conflict': _count(
            query.filter(GameLog.appearance_team_status == STATUS_CONFLICT)
        ),
        'null_legacy': _count(
            query.filter(GameLog.appearance_team_status.is_(None))
        ),
    }


def _new_row_attribution(session, *, since):
    from models.game_log import GameLog

    # SQL timestamps are stored as naive UTC throughout this model.
    since_naive_utc = since.astimezone(timezone.utc).replace(tzinfo=None)
    query = session.query(GameLog).filter(GameLog.created_at >= since_naive_utc)
    counts = _status_counts(session, query)
    return {
        'since_utc': since.isoformat().replace('+00:00', 'Z'),
        **counts,
        'status_recorded': counts['total'] - counts['null_legacy'],
    }


def _invalid_state_summary(session):
    from models.game_log import GameLog
    from services.appearance_team_authority import (
        REASON_CONFLICT,
        REASON_CORRECTED,
        REASON_RESOLVED_BOXSCORE,
        REASON_RESOLVED_SCHEDULE,
        REASON_UNRESOLVED,
        SOURCE_BOXSCORE,
        SOURCE_CONFLICT,
        SOURCE_SCHEDULE,
        STATUS_CONFLICT,
        STATUS_RESOLVED,
        STATUS_UNRESOLVED,
    )

    allowed_statuses = (STATUS_RESOLVED, STATUS_UNRESOLVED, STATUS_CONFLICT)
    resolved_reasons = (
        REASON_RESOLVED_BOXSCORE,
        REASON_RESOLVED_SCHEDULE,
        REASON_CORRECTED,
    )
    counts = {
        'unknown_status': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status.isnot(None),
                ~GameLog.appearance_team_status.in_(allowed_statuses),
            )
        ),
        'resolved_missing_team': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status == STATUS_RESOLVED,
                GameLog.appearance_team_id.is_(None),
            )
        ),
        'resolved_invalid_provenance': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status == STATUS_RESOLVED,
                (
                    ~GameLog.appearance_team_source.in_(
                        (SOURCE_BOXSCORE, SOURCE_SCHEDULE)
                    )
                )
                | GameLog.appearance_team_source.is_(None)
                | (~GameLog.appearance_team_reason.in_(resolved_reasons))
                | GameLog.appearance_team_reason.is_(None),
            )
        ),
        'unresolved_with_team': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status == STATUS_UNRESOLVED,
                GameLog.appearance_team_id.isnot(None),
            )
        ),
        'unresolved_invalid_provenance': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status == STATUS_UNRESOLVED,
                (
                    GameLog.appearance_team_source.isnot(None)
                    | (GameLog.appearance_team_reason != REASON_UNRESOLVED)
                    | GameLog.appearance_team_reason.is_(None)
                ),
            )
        ),
        'conflict_with_team': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status == STATUS_CONFLICT,
                GameLog.appearance_team_id.isnot(None),
            )
        ),
        'conflict_invalid_provenance': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status == STATUS_CONFLICT,
                (
                    (GameLog.appearance_team_source != SOURCE_CONFLICT)
                    | GameLog.appearance_team_source.is_(None)
                    | (GameLog.appearance_team_reason != REASON_CONFLICT)
                    | GameLog.appearance_team_reason.is_(None)
                ),
            )
        ),
        'legacy_with_authority': _count(
            session.query(GameLog).filter(
                GameLog.appearance_team_status.is_(None),
                (
                    GameLog.appearance_team_id.isnot(None)
                    | GameLog.appearance_team_source.isnot(None)
                    | GameLog.appearance_team_reason.isnot(None)
                ),
            )
        ),
    }
    return {
        'total': sum(counts.values()),
        'counts': counts,
    }


def _non_resolved_summary(session, *, row_limit):
    from models.game_log import GameLog
    from services.appearance_team_authority import STATUS_RESOLVED

    base = session.query(GameLog).filter(
        (GameLog.appearance_team_status != STATUS_RESOLVED)
        | GameLog.appearance_team_status.is_(None)
    )
    total = _count(base)
    rows = (
        base.order_by(GameLog.game_date.desc(), GameLog.id.desc())
        .limit(row_limit)
        .all()
    )
    return {
        'total': total,
        'row_limit': row_limit,
        'returned': len(rows),
        'truncated': total > len(rows),
        'rows': [
            {
                'game_log_id': row.id,
                'pitcher_id': row.pitcher_id,
                'mlb_game_pk': row.mlb_game_pk,
                'game_date': (
                    row.game_date.isoformat() if row.game_date is not None else None
                ),
                'status': row.appearance_team_status,
                'source': row.appearance_team_source,
                'reason': row.appearance_team_reason,
            }
            for row in rows
        ],
    }


def _classify(*, migration, coverage_contract, new_rows, invalid_states):
    reasons = []
    if not migration['head_matches']:
        reasons.append('migration_head_mismatch')
    if not coverage_contract.get('totals_match'):
        reasons.append('coverage_totals_mismatch')
    if invalid_states.get('total', 0) > 0:
        reasons.append('invalid_stored_states')
    if new_rows.get('null_legacy', 0) > 0:
        reasons.append('post_cutover_rows_missing_attribution_status')
    if reasons:
        return RESULT_FAIL, reasons

    if new_rows.get('total', 0) == 0:
        return RESULT_INCONCLUSIVE, ['no_post_cutover_rows']
    if new_rows.get('unresolved', 0) > 0 or new_rows.get('conflict', 0) > 0:
        return RESULT_INCONCLUSIVE, ['post_cutover_rows_not_resolved']
    return RESULT_PASS, ['post_cutover_rows_fully_resolved']


def _build_payload(*, session, new_row_since, row_limit):
    from services.appearance_team_coverage import (
        build_appearance_team_coverage,
    )

    migration = _migration_summary(session)
    if not migration['head_matches']:
        return {
            'capability': CAPABILITY,
            'coverage_capability': COVERAGE_CAPABILITY,
            'status': 'complete',
            'result': RESULT_FAIL,
            'mode': MODE,
            'database_writes_performed': False,
            'migration': migration,
            'decision_reasons': ['migration_head_mismatch'],
        }

    coverage = build_appearance_team_coverage(session=session)
    coverage_contract = _coverage_contract(coverage)
    new_rows = _new_row_attribution(session, since=new_row_since)
    invalid_states = _invalid_state_summary(session)
    non_resolved = _non_resolved_summary(session, row_limit=row_limit)
    result, reasons = _classify(
        migration=migration,
        coverage_contract=coverage_contract,
        new_rows=new_rows,
        invalid_states=invalid_states,
    )
    return {
        'capability': CAPABILITY,
        'coverage_capability': coverage.get('capability'),
        'status': 'complete',
        'result': result,
        'mode': MODE,
        'database_writes_performed': False,
        'migration': migration,
        'coverage': {
            key: value
            for key, value in coverage.items()
            if key != 'capability'
        },
        'coverage_contract': coverage_contract,
        'new_row_attribution': new_rows,
        'invalid_states': invalid_states,
        'non_resolved': non_resolved,
        'decision_reasons': reasons,
    }


def _failure_payload(exc):
    return {
        'capability': CAPABILITY,
        'coverage_capability': COVERAGE_CAPABILITY,
        'status': 'failed',
        'result': RESULT_FAIL,
        'mode': MODE,
        'database_writes_performed': False,
        # Exception messages can contain connection details. Report only the type.
        'error_type': type(exc).__name__,
        'decision_reasons': ['audit_execution_failed'],
    }


def main(argv=None):
    args = _parse_args(argv)

    try:
        from app import app
        from utils.db import db

        with app.app_context():
            payload = _build_payload(
                session=db.session,
                new_row_since=args.new_row_since,
                row_limit=args.row_limit,
            )
    except Exception as exc:
        payload = _failure_payload(exc)

    _emit(payload, compact=args.compact, output=args.output)
    if not args.quiet:
        print(
            '[appearance-team-audit] '
            f"result={payload['result']} "
            f"error_type={payload.get('error_type')}",
            file=sys.stderr,
        )
    return EXIT_BY_RESULT[payload['result']]


if __name__ == '__main__':
    sys.exit(main())
