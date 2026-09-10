"""Run one bounded, fail-closed production shadow cycle."""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _args(argv=None):
    parser = argparse.ArgumentParser(description='Run one bounded sync-pipeline shadow cycle.')
    parser.add_argument('--baseball-date', type=date.fromisoformat)
    parser.add_argument('--max-jobs', type=int, default=24)
    parser.add_argument(
        '--include-continuous-observation',
        action='store_true',
        help='Also run one bounded CU shadow-detection cycle.',
    )
    parser.add_argument(
        '--include-morning',
        action='store_true',
        help='Plan the non-publishing SP-12 morning contract once for the date.',
    )
    parser.add_argument('--output')
    return parser.parse_args(argv)


def main(argv=None):
    args = _args(argv)
    from app import create_app
    from services.continuous_execution import (
        ActivationMode,
        ContinuousExecutionConfig,
        run_continuous_cycle,
    )
    from services.sync_pipeline_shadow import run_production_shadow_cycle
    from services.roster_authority_health import roster_authority_coverage

    app = create_app(os.environ.get('APP_ENV', 'production'))
    with app.app_context():
        result = run_production_shadow_cycle(
            baseball_date=args.baseball_date,
            max_jobs=args.max_jobs,
            include_morning=args.include_morning,
        )
        if args.include_morning:
            target_date = date.fromisoformat(result['baseball_date'])
            result['roster_authority'] = roster_authority_coverage(target_date)
        if args.include_continuous_observation:
            observation = run_continuous_cycle(config=ContinuousExecutionConfig(
                mode=ActivationMode.SHADOW_DETECT,
                enabled=True,
                production_publication_enabled=False,
            ))
            result['continuous_observation'] = observation.to_dict()
            if observation.status not in {'complete', 'skipped'}:
                result['status'] = 'partial'
    body = json.dumps(result, indent=2, sort_keys=True, default=str)
    print(body)
    if args.output:
        Path(args.output).write_text(body + '\n', encoding='utf-8')
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
