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

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Build internal Phase 0D appearance context evidence for one product date.'
    )
    parser.add_argument(
        '--date',
        required=True,
        dest='product_date',
        help='Product date to build, YYYY-MM-DD.',
    )
    parser.add_argument(
        '--source',
        default='manual',
        help='Source label to store on created evidence objects.',
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    product_date = date.fromisoformat(args.product_date)
    source = str(args.source or 'manual')[:40]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.appearance_context_evidence import build_appearance_context_evidence
    from utils.db import db

    with app.app_context():
        result = build_appearance_context_evidence(
            product_date,
            source=source,
            commit=True,
        )
    db.session.remove()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
