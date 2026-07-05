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
        description='Run the internal Phase 0E legacy-read reconciliation audit.'
    )
    parser.add_argument(
        '--date',
        required=True,
        dest='product_date',
        help='Product date to audit, YYYY-MM-DD.',
    )
    parser.add_argument(
        '--source',
        default='manual',
        help='Source label to store with internal audit metadata.',
    )
    parser.add_argument(
        '--report-path',
        help='Directory or file path outside the repo for markdown and JSON report output.',
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    product_date = date.fromisoformat(args.product_date)
    source = str(args.source or 'manual')[:100]
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.legacy_read_reconciliation import (
        render_reconciliation_report,
        run_reconciliation_audit,
    )
    from utils.db import db

    with app.app_context():
        audit_result = run_reconciliation_audit(
            product_date,
            source=source,
            commit=False,
        )
        report_result = None
        if args.report_path:
            report_result = render_reconciliation_report(
                product_date,
                output_path=args.report_path,
            )
        db.session.commit()
    db.session.remove()
    result = {
        'status': 'completed',
        'product_date': product_date.isoformat(),
        'audit': audit_result,
        'report': report_result,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
