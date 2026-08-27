"""Run a source-authorized BaseballOS production schedule window."""

import argparse
import logging
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(description='Run due BaseballOS sync work safely.')
    parser.add_argument('--mode', required=True, choices=('daily', 'postgame', 'morning'))
    parser.add_argument('--execution-source', required=True)
    parser.add_argument('--scheduled-for', required=True, help='Intended UTC window, ISO-8601.')
    parser.add_argument('--days-back', type=int, default=7)
    parser.add_argument('--public-only', action='store_true')
    parser.add_argument('--recovery-reason', default='')
    parser.add_argument('--confirm-recovery', default='')
    parser.add_argument('--operator', default='')
    parser.add_argument('--output')
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from services.sync_execution_context import (
        SyncExecutionAuthorizationError, validate_execution_context,
    )
    try:
        context = validate_execution_context(
            mode=args.mode,
            source=args.execution_source,
            scheduled_for=args.scheduled_for,
            recovery_reason=args.recovery_reason,
            recovery_confirmation=args.confirm_recovery,
            operator=args.operator,
        )
    except SyncExecutionAuthorizationError as exc:
        logging.getLogger(__name__).error(
            'Production sync request refused before application/database initialization '
            '(reason=%s).', exc.reason,
        )
        return 2

    from app import app
    from services.sync_due import run_due_sync
    from utils.summary_output import SummaryOutputError, serialize_summary, write_summary

    try:
        result = run_due_sync(
            app,
            context,
            days_back=args.days_back,
            public_only=args.public_only,
        )
    except Exception as exc:  # command boundary must surface failure
        logging.getLogger(__name__).exception('Due sync failed: %s', exc)
        return 1

    summary = {
        'status': result.get('status'),
        'mode': context.mode,
        'source': context.source,
        'intended_window': context.intended_window,
        'scheduled_for': context.scheduled_for.isoformat(),
        'result': result,
    }
    print(serialize_summary(summary))
    exit_code = 0 if result.get('status') in {'executed', 'already_satisfied'} else 1
    if args.output:
        try:
            write_summary(summary, args.output)
        except SummaryOutputError as exc:
            logging.getLogger(__name__).error(
                'Due sync summary output failed (reason=%s).', exc.reason,
            )
            return exit_code or 1
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
