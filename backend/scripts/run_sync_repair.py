"""Safe operator entry point for SP-13 repair, backfill, and replay requests."""

import argparse
import json
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'


def _parser():
    parser = argparse.ArgumentParser(description='Plan or submit a governed BaseballOS repair.')
    subparsers = parser.add_subparsers(dest='command', required=True)
    for name in ('targeted', 'backfill', 'full-reconciliation'):
        child = subparsers.add_parser(name)
        child.add_argument('--start-date', required=True)
        child.add_argument('--end-date')
        child.add_argument('--domain', required=True, choices=(
            'schedule', 'final_game', 'roster', 'transactions', 'pregame', 'live',
            'downstream', 'multi_domain',
        ))
        child.add_argument('--game-pk', type=int, action='append', default=[])
        child.add_argument('--team-id', type=int, action='append', default=[])
        child.add_argument('--pitcher-id', type=int, action='append', default=[])
        child.add_argument('--reason', required=True)
        child.add_argument('--requested-by', default='operator')
        child.add_argument('--apply', action='store_true', help='Dispatch work; default is dry-run.')
        child.add_argument('--confirm-broad-scope', action='store_true')
    replay = subparsers.add_parser('replay')
    replay.add_argument('--date', required=True)
    replay.add_argument('--impact-plan-id', type=int, action='append', required=True)
    replay.add_argument('--method-version', action='append', default=[], metavar='DOMAIN=VERSION')
    replay.add_argument('--rules-version')
    replay.add_argument('--reason', required=True)
    replay.add_argument('--requested-by', default='operator')
    replay.add_argument('--apply', action='store_true', help='Dispatch work; default is dry-run.')
    return parser


def _method_versions(values):
    result = {}
    for value in values:
        key, separator, version = value.partition('=')
        if not separator or not key.strip() or not version.strip():
            raise ValueError('--method-version must use DOMAIN=VERSION.')
        result[key.strip()] = version.strip()
    return result


def main(argv=None):
    args = _parser().parse_args(argv)
    from app import app
    from services.repair_orchestration import submit_repair_request

    if args.command == 'replay':
        method_versions = _method_versions(args.method_version)
        if bool(method_versions) == bool(args.rules_version):
            raise SystemExit('Specify exactly one of --method-version or --rules-version.')
        mode = 'method_replay' if method_versions else 'rule_replay'
        domain = 'downstream'
        start_date = end_date = args.date
        scope = {'impact_plan_ids': args.impact_plan_id}
        allow_large = False
    else:
        mode = {
            'targeted': 'targeted_repair',
            'backfill': 'historical_backfill',
            'full-reconciliation': 'full_reconciliation',
        }[args.command]
        domain = args.domain
        start_date = args.start_date
        end_date = args.end_date or args.start_date
        scope = {
            'game_pks': args.game_pk, 'team_ids': args.team_id,
            'pitcher_ids': args.pitcher_id,
        }
        method_versions = {}
        args.rules_version = None
        allow_large = args.confirm_broad_scope

    with app.app_context():
        from services.migration_authority import require_verify_only, verify_heads
        from services.sync_pipeline_shadow import current_migration_heads
        from services.sync_pipeline_certification import EXPECTED_MIGRATION_HEAD
        require_verify_only()
        verify_heads(current_migration_heads(), EXPECTED_MIGRATION_HEAD)
        result = submit_repair_request(
            mode=mode, source_domain=domain,
            baseball_date_start=start_date, baseball_date_end=end_date,
            scope=scope, requested_scope_type='date_range', reason=args.reason,
            requested_by=args.requested_by, dry_run=not args.apply,
            requested_rules_version=args.rules_version,
            requested_method_versions=method_versions,
            allow_large_scope=allow_large,
        )
        output = {
            'repair_request_id': result.request.id,
            'request_key': result.request.request_key,
            'mode': result.request.mode,
            'status': result.request.status,
            'dry_run': result.request.dry_run,
            'reused_active_request': result.reused_active_request,
            'planner_job_id': result.job.id if result.job else None,
        }
    print(json.dumps(output, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
