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
    parser.add_argument('--output')
    return parser.parse_args(argv)


def main(argv=None):
    args = _args(argv)
    from app import create_app
    from services.sync_pipeline_shadow import run_production_shadow_cycle

    app = create_app(os.environ.get('APP_ENV', 'production'))
    with app.app_context():
        result = run_production_shadow_cycle(
            baseball_date=args.baseball_date,
            max_jobs=args.max_jobs,
        )
    body = json.dumps(result, indent=2, sort_keys=True, default=str)
    print(body)
    if args.output:
        Path(args.output).write_text(body + '\n', encoding='utf-8')
    return 0 if result['status'] == 'success' else 1


if __name__ == '__main__':
    raise SystemExit(main())
