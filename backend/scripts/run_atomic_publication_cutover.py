"""Inspect or publish one reviewed SP-10 cohort through the SP-11 worker."""

import argparse
import json
import os
from pathlib import Path
import sys


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _args(argv=None):
    parser = argparse.ArgumentParser(
        description='Inspect eligible cohorts or publish one explicitly selected cohort.',
    )
    parser.add_argument('mode', choices=('inspect', 'publish'))
    parser.add_argument('--cohort-id', type=int)
    parser.add_argument('--confirm', default='')
    parser.add_argument('--limit', type=int, default=20)
    parser.add_argument('--output')
    return parser.parse_args(argv)


def main(argv=None):
    args = _args(argv)
    if args.mode == 'publish' and (not args.cohort_id or args.confirm != 'PUBLISH'):
        raise SystemExit('publish requires --cohort-id and --confirm PUBLISH')

    from app import create_app
    from services.atomic_publication_cutover import (
        inspect_publication_cohort,
        inspect_publication_candidates,
        publish_selected_cohort,
    )

    app = create_app(os.environ.get('APP_ENV', 'production'))
    with app.app_context():
        result = (
            (
                inspect_publication_cohort(args.cohort_id)
                if args.cohort_id
                else inspect_publication_candidates(limit=args.limit)
            )
            if args.mode == 'inspect'
            else publish_selected_cohort(args.cohort_id)
        )
    body = json.dumps(result, indent=2, sort_keys=True, default=str)
    print(body)
    if args.output:
        Path(args.output).write_text(body + '\n', encoding='utf-8')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
