"""Print the read-only CR-03 SP-05 roster-authority coverage report."""

import argparse
from datetime import date, datetime
import json
import os
from pathlib import Path
import sys
from zoneinfo import ZoneInfo


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _args(argv=None):
    parser = argparse.ArgumentParser(
        description='Report current SP-05 roster authority without source reads or writes.',
    )
    parser.add_argument('--baseball-date', type=date.fromisoformat)
    parser.add_argument('--output')
    return parser.parse_args(argv)


def main(argv=None):
    args = _args(argv)
    from app import create_app
    from services.roster_authority_health import roster_authority_coverage

    target_date = args.baseball_date or datetime.now(
        ZoneInfo('America/New_York')
    ).date()
    app = create_app(os.environ.get('APP_ENV', 'production'))
    with app.app_context():
        report = roster_authority_coverage(target_date)
    body = json.dumps(report, indent=2, sort_keys=True)
    print(body)
    if args.output:
        Path(args.output).write_text(body + '\n', encoding='utf-8')
    return 0 if report['status'] == 'complete' else 1


if __name__ == '__main__':
    raise SystemExit(main())
