import argparse
import logging
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Manual, read-only review tool; never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            "Generate the live stored-slate Today's Story editorial review. "
            'Read-only: no sync, no snapshot write, no publishing.'
        )
    )
    parser.add_argument('--reference-date', dest='reference_date',
                        help='Optional completed-game context date, YYYY-MM-DD.')
    parser.add_argument('--output-md', dest='output_md',
                        default=str(REPO_ROOT / 'artifacts' / 'todays_story_editorial_review_E2C5C_live.md'),
                        help='Markdown artifact path.')
    return parser.parse_args(argv)


def _parse_date(value):
    if not value:
        return None
    return date.fromisoformat(value)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.todays_story_editorial_review import (
        build_todays_story_editorial_review,
        write_todays_story_editorial_review,
    )

    report = build_todays_story_editorial_review(
        app=app,
        reference_date=_parse_date(args.reference_date),
    )
    output = write_todays_story_editorial_review(report, args.output_md)
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
