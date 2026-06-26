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

# Manual, read-only review tool; never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Generate an internal COIN story review corpus for selected teams. '
            'Read-only: builds nothing public, writes only local review artifacts.'
        )
    )
    parser.add_argument('--team-id', dest='team_ids', type=int, action='append',
                        help='Team id to include; repeatable. Defaults to '
                             '137, 133, 139, 147 when omitted.')
    parser.add_argument('--reference-date', dest='reference_date',
                        help='Optional reference date, YYYY-MM-DD.')
    parser.add_argument('--writer', dest='writer', default='all',
                        choices=['team_story', 'dashboard', 'morning_brief', 'all'],
                        help='Which writer to render (default: all allowed targets).')
    parser.add_argument('--include-unpublishable', dest='include_unpublishable',
                        action='store_true',
                        help='Render drafts even when a package is not publishable.')
    parser.add_argument('--strict', dest='strict', action='store_true',
                        help='Abort on the first team failure instead of recording it.')
    parser.add_argument('--output-json', dest='output_json',
                        help='Write the JSON corpus to this path.')
    parser.add_argument('--output-md', dest='output_md',
                        help='Write a readable Markdown corpus to this path.')
    parser.add_argument('--pretty', dest='pretty', action='store_true',
                        help='Pretty-print JSON output (stdout and file).')
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
    from services import coin_story_corpus

    corpus = coin_story_corpus.generate_corpus(
        args.team_ids,
        app=app,
        reference_date=_parse_date(args.reference_date),
        writer=args.writer,
        include_unpublishable=bool(args.include_unpublishable),
        strict=bool(args.strict),
    )

    if args.output_json:
        coin_story_corpus.write_corpus_json(corpus, args.output_json, pretty=args.pretty)
    if args.output_md:
        coin_story_corpus.write_corpus_markdown(corpus, args.output_md)

    if args.pretty:
        print(json.dumps(corpus, indent=2, sort_keys=True))
    else:
        print(json.dumps(corpus, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
