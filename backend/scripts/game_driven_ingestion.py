#!/usr/bin/env python
"""Foundation 3C game-driven ingestion operator tool.

One entry point for the staged rollout and for governed operator repair.

    # Stage A — shadow plan only. No MLB request, no write.
    python scripts/game_driven_ingestion.py --plan-only

    # Stage B — shadow reconciliation. Fetches games, writes nothing.
    python scripts/game_driven_ingestion.py --mode shadow

    # Exclusive shadow of exactly five games — nothing else may enter the run.
    python scripts/game_driven_ingestion.py --mode shadow --only-game-pk 1 --only-game-pk 2

    # Controlled write of exactly those games, authorized by the fingerprint a
    # human reviewed in the shadow run above.
    python scripts/game_driven_ingestion.py --mode write --only-game-pk 1 --only-game-pk 2 --expected-plan-fingerprint <sha256>

    # Governed repair ADDED to the normal window (this does not bound the run).
    python scripts/game_driven_ingestion.py --mode write --game-pk 776543

Output is a single JSON document on stdout (or ``--output``). It contains
counts, timings, safe error classes, and the publication completeness proof —
never credentials, connection strings, headers, raw source payloads, or
exception text.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_ERROR = 2


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Run the Foundation 3C game-driven ingestion lane.',
    )
    parser.add_argument(
        '--mode',
        choices=['shadow', 'write', 'authoritative'],
        default='shadow',
        help='shadow reads only; write reconciles and checkpoints.',
    )
    parser.add_argument(
        '--plan-only',
        action='store_true',
        help='Build the work plan and stop. Makes no MLB request and no write.',
    )
    parser.add_argument(
        '--reference-date',
        help='Represented baseball date (YYYY-MM-DD). Defaults to today UTC.',
    )
    parser.add_argument(
        '--max-games', type=int, default=None,
        help='Bound how many planned games this invocation processes.',
    )
    parser.add_argument(
        '--time-budget-seconds', type=float, default=None,
        help='Stop intake at this elapsed time and leave the rest resumable.',
    )
    parser.add_argument(
        '--game-pk', type=int, action='append', default=None,
        help=(
            'Repeatable. ADDITIVE: plans the normal date window AND these '
            'games. It does NOT bound the run — use --only-game-pk for that.'
        ),
    )
    parser.add_argument(
        '--only-game-pk', type=int, action='append', default=None,
        help=(
            'Repeatable. EXCLUSIVE: run exactly these games and no others. '
            'The run fails before any MLB request if the planned set is not '
            'exactly this set.'
        ),
    )
    parser.add_argument(
        '--expected-plan-fingerprint',
        help=(
            'The reconciliation-plan fingerprint a human reviewed in shadow. '
            'Required for an exclusive write; the write refuses before any '
            'mutation unless the recomputed plan matches it exactly.'
        ),
    )
    parser.add_argument(
        '--include-backfill', action='store_true',
        help='Also plan governed final games older than the horizon (best effort).',
    )
    parser.add_argument('--output', help='Write the JSON report to this path.')
    args = parser.parse_args(argv)
    _validate_scope_arguments(parser, args)
    return args


def _validate_scope_arguments(parser, args) -> None:
    """Reject argument combinations that would make a scope claim untrue.

    Exclusive mode means "exactly these games". Anything that could widen or
    narrow that set — the additive option, a cap, a backfill sweep — makes the
    claim false, so it is refused rather than silently reinterpreted.
    """
    if args.only_game_pk is None:
        if args.expected_plan_fingerprint:
            parser.error(
                '--expected-plan-fingerprint requires --only-game-pk'
            )
        return

    if not args.only_game_pk:
        parser.error('--only-game-pk requires at least one game id')
    if args.game_pk:
        parser.error('--game-pk and --only-game-pk are mutually exclusive')
    if args.max_games is not None:
        parser.error('--max-games cannot bound an exclusive game set')
    if args.include_backfill:
        parser.error('--include-backfill cannot widen an exclusive game set')
    if args.mode == 'write' and not args.expected_plan_fingerprint:
        parser.error(
            'an exclusive write requires --expected-plan-fingerprint from a '
            'reviewed shadow run'
        )


def resolve_reference_date(raw):
    if raw:
        return date.fromisoformat(str(raw).strip())
    return datetime.now(timezone.utc).date()


def build_app():
    import app as app_module

    return app_module.create_app()


def run(args) -> tuple[int, dict]:
    reference_date = resolve_reference_date(args.reference_date)
    flask_app = build_app()

    from services import game_driven_ingestion
    from services import game_ingestion_completeness
    from services import game_ingestion_planner

    with flask_app.app_context():
        if args.plan_only:
            plan = game_ingestion_planner.plan_game_work(
                reference_date,
                explicit_game_pks=args.game_pk,
                only_game_pks=args.only_game_pk,
                include_backfill=args.include_backfill,
            )
            report = {
                'stage': 'shadow_plan',
                'mode': 'plan_only',
                'reference_date': reference_date.isoformat(),
                'plan': {
                    key: value for key, value in plan.items() if key != 'items'
                },
                'items': [item.to_dict() for item in plan['items']],
            }
            return EXIT_OK, report

        result = game_driven_ingestion.run_game_driven_ingestion(
            reference_date,
            mode=args.mode,
            time_budget_seconds=args.time_budget_seconds,
            explicit_game_pks=args.game_pk,
            only_game_pks=args.only_game_pk,
            expected_plan_fingerprint=args.expected_plan_fingerprint,
            include_backfill=args.include_backfill,
            max_games=args.max_games,
        )
        completeness = game_ingestion_completeness.build_game_ingestion_completeness(
            reference_date
        )
        result['publication_completeness'] = completeness
        exit_code = (
            EXIT_OK
            if result.get('status') == 'complete' and not result.get('games_failed')
            else EXIT_INCOMPLETE
        )
        return exit_code, result


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        exit_code, report = run(args)
    except Exception as exc:  # noqa: BLE001 - never leak exception text
        report = {
            'stage': 'error',
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
    # Never let a stray auto-sync start from an operator invocation.
    os.environ.setdefault('AUTO_SYNC', 'false')
    raise SystemExit(main())
