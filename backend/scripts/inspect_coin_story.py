import argparse
import json
import logging
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Manual, read-only inspection tool; never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Preview the COIN story package and rendered drafts for a team. '
            'Read-only: builds nothing public, writes nothing, publishes nothing.'
        )
    )
    parser.add_argument('--team-id', dest='team_id', type=int, required=True,
                        help='MLB team id to inspect.')
    parser.add_argument('--reference-date', dest='reference_date',
                        help='Optional reference date, YYYY-MM-DD.')
    parser.add_argument('--writer', dest='writer', default='all',
                        choices=['team_story', 'dashboard', 'morning_brief', 'all'],
                        help='Which writer to render (default: all allowed targets).')
    parser.add_argument('--include-unpublishable', dest='include_unpublishable',
                        action='store_true',
                        help='Render drafts even when the package is not publishable '
                             '(clearly flagged as internal preview).')
    parser.add_argument('--pretty', dest='pretty', action='store_true',
                        help='Pretty-print the JSON output.')
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
    from services import coin_story_inspection

    result = coin_story_inspection.inspect_team_story(
        args.team_id,
        app=app,
        reference_date=_parse_date(args.reference_date),
        writer=args.writer,
        include_unpublishable=bool(args.include_unpublishable),
    )

    if args.pretty:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
