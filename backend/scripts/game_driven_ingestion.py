#!/usr/bin/env python
"""Foundation 3C game-driven ingestion operator tool.

One entry point for the staged rollout and for governed operator repair.

    # Stage A — shadow plan only. No MLB request, no write.
    python scripts/game_driven_ingestion.py --plan-only

    # Stage B — shadow reconciliation. Fetches games, writes nothing.
    python scripts/game_driven_ingestion.py --mode shadow

    # Stage C — controlled write. Reconciles and checkpoints; publication
    # authority is unchanged until GAME_DRIVEN_INGESTION_MODE=authoritative.
    python scripts/game_driven_ingestion.py --mode write --max-games 5

    # Governed repair of specific games.
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
        help='Repeatable. Plan these games as explicit_repair.',
    )
    parser.add_argument(
        '--include-backfill', action='store_true',
        help='Also plan governed final games older than the horizon (best effort).',
    )
    parser.add_argument('--output', help='Write the JSON report to this path.')
    return parser.parse_args(argv)


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
