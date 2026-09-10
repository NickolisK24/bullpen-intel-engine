import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# This is an operator diagnostic command, not a web worker.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Report internal slate coverage blockers for BaseballOS freshness.'
    )
    parser.add_argument(
        '--slate-date',
        help='Baseball slate date to diagnose, YYYY-MM-DD. Defaults to the latest checked slate.',
    )
    parser.add_argument(
        '--reference-date',
        help='Product reference date for freshness aging, YYYY-MM-DD. Defaults to the product date.',
    )
    parser.add_argument(
        '--compact',
        action='store_true',
        help='Print compact JSON instead of indented JSON.',
    )
    parser.add_argument(
        '--fail-on-blocker',
        action='store_true',
        help='Exit 1 when the diagnosed slate is not publishable.',
    )
    return parser.parse_args(argv)


def _parse_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _snapshot_summary(snapshot, *, unavailable_reason_fn):
    if snapshot is None:
        return None
    summary = snapshot.to_dict()
    summary['unavailable_reason'] = unavailable_reason_fn(snapshot)
    return summary


def _source_readiness_summary(readiness):
    readiness = readiness or {}
    families = readiness.get('families') or {}
    return {
        'overall_status': readiness.get('overall_status'),
        'fail_closed': bool(readiness.get('fail_closed')),
        'blocking_source_families': list(readiness.get('blocking_source_families') or []),
        'families': {
            name: {
                'status': family.get('status'),
                'fail_closed': bool(family.get('fail_closed')),
                'reason_codes': list(family.get('reason_codes') or []),
                'coverage': family.get('coverage') or {},
                'details': family.get('details') or {},
            }
            for name, family in sorted(families.items())
        },
    }


def _coverage_diagnostics(coverage):
    coverage = coverage or {}
    return coverage.get('diagnostics') or {}


def _failed_games(diagnostics):
    blockers = diagnostics.get('postgame_blockers') or []
    return [
        {
            'slate_date': blocker.get('slate_date'),
            'mlb_game_pk': blocker.get('mlb_game_pk'),
            'away_team': blocker.get('away_team'),
            'home_team': blocker.get('home_team'),
            'game_status': blocker.get('game_status'),
            'status_state': blocker.get('status_state'),
            'marker_status': blocker.get('marker_status'),
            'reason_code': blocker.get('reason_code'),
            'diagnostic_domain': blocker.get('diagnostic_domain'),
            'incomplete_reason': blocker.get('incomplete_reason'),
            'attempt_count': blocker.get('attempt_count'),
            'pitching_lines_seen': blocker.get('pitching_lines_seen'),
            'pitcher_resolution_failures': blocker.get('pitcher_resolution_failures'),
            'correction_attempts_failed': blocker.get('correction_attempts_failed'),
            'last_attempted_at': blocker.get('last_attempted_at'),
            'failed_at': blocker.get('failed_at'),
            'pitcher_resolution_failure_details': blocker.get(
                'pitcher_resolution_failure_details',
                [],
            ),
        }
        for blocker in blockers
    ]


def build_diagnostic_report(
    *,
    sync_status,
    health,
    latest_published_snapshot=None,
    latest_snapshot_record=None,
    snapshot_unavailable_reason_fn,
):
    sync_status = sync_status or {}
    health = health or {}
    coverage = health.get('slate_coverage') or sync_status.get('slate_coverage') or {}
    diagnostics = _coverage_diagnostics(coverage)
    data = sync_status.get('data') or {}
    freshness = sync_status.get('freshness') or health.get('freshness') or {}
    latest_published = _snapshot_summary(
        latest_published_snapshot,
        unavailable_reason_fn=snapshot_unavailable_reason_fn,
    )
    latest_record = _snapshot_summary(
        latest_snapshot_record,
        unavailable_reason_fn=snapshot_unavailable_reason_fn,
    )

    latest_checked_date = (
        data.get('latest_workload_date')
        or data.get('latest_game_date')
        or coverage.get('slate_date')
    )
    latest_published_data_through = (
        latest_published.get('data_through')
        if latest_published
        else None
    )
    publishable = coverage.get('complete_enough_to_publish') is True

    return {
        'capability': 'slate_coverage_diagnostics',
        'latest_checked_date': latest_checked_date,
        'latest_checked_baseball_date': coverage.get('slate_date') or latest_checked_date,
        'latest_published_public_data_through': latest_published_data_through,
        'failed_slate_date': None if publishable else coverage.get('slate_date'),
        'publishable': publishable,
        'freshness': {
            'freshness_state': freshness.get('freshness_state'),
            'is_current': freshness.get('is_current'),
            'label': freshness.get('label'),
            'reason_codes': list(freshness.get('reason_codes') or []),
            'limitations': list(freshness.get('limitations') or []),
            'data_through': freshness.get('data_through') or data.get('latest_game_date'),
            'reference_date': freshness.get('reference_date'),
            'availability_reference_date': freshness.get('availability_reference_date'),
        },
        'sync_status': {
            'status': sync_status.get('status'),
            'last_checked': sync_status.get('last_checked'),
            'last_successful_sync': sync_status.get('last_successful_sync'),
            'last_completed_game_refresh': sync_status.get('last_completed_game_refresh'),
            'last_morning_full_sync': sync_status.get('last_morning_full_sync'),
            'metadata_source': sync_status.get('metadata_source'),
            'sync_authority': sync_status.get('sync_authority'),
        },
        'slate_coverage': {
            'slate_date': coverage.get('slate_date'),
            'complete_enough_to_publish': coverage.get('complete_enough_to_publish'),
            'coverage_known': coverage.get('coverage_known'),
            'validations_passed': coverage.get('validations_passed'),
            'reason_codes': list(coverage.get('reason_codes') or []),
            'degradation_reasons': list(coverage.get('degradation_reasons') or []),
            'games_scheduled': coverage.get('games_scheduled'),
            'games_final': coverage.get('games_final'),
            'games_fully_ingested': coverage.get('games_fully_ingested'),
            'games_incomplete': coverage.get('games_incomplete'),
            'games_failed': coverage.get('games_failed'),
            'games_postponed': coverage.get('games_postponed'),
            'games_suspended': coverage.get('games_suspended'),
            'games_unresolved': coverage.get('games_unresolved'),
            'games_included': coverage.get('games_included'),
            'marker_counts': coverage.get('marker_counts') or {},
            'diagnostics': diagnostics,
        },
        'failure_domains': list(diagnostics.get('failure_domains') or []),
        'failed_game_pks': list(diagnostics.get('failed_game_pks') or []),
        'failed_team_ids': list(diagnostics.get('failed_team_ids') or []),
        'failed_games': _failed_games(diagnostics),
        'postgame_blocker_reason_counts': (
            diagnostics.get('postgame_blocker_reason_counts') or {}
        ),
        'postgame_blocker_incomplete_reason_counts': (
            diagnostics.get('postgame_blocker_incomplete_reason_counts') or {}
        ),
        'non_final_game_count': diagnostics.get('non_final_game_count') or 0,
        'non_final_games': list(diagnostics.get('non_final_games') or []),
        'source_readiness': _source_readiness_summary(health.get('source_readiness')),
        'dashboard_snapshots': {
            'latest_published': latest_published,
            'latest_record': latest_record,
        },
    }


def build_report(*, slate_date=None, reference_date=None):
    from services import dashboard_snapshot, slate_coverage, source_readiness, sync_metadata

    ref = _parse_date(reference_date)
    target_slate = _parse_date(slate_date)
    sync_status = sync_metadata.build_sync_status_payload(reference_date=ref)
    health = sync_metadata.pipeline_health_payload(reference_date=ref)

    if target_slate is not None:
        metadata = sync_metadata.collect_data_metadata()
        coverage = slate_coverage.compute_slate_coverage(
            target_slate,
            sync_status=sync_status.get('status'),
            include_diagnostics=True,
        )
        health = dict(health)
        health['slate_coverage'] = coverage
        health['source_readiness'] = source_readiness.source_readiness_payload(
            metadata=metadata,
            sync_status=sync_status.get('status'),
            slate_coverage_payload=coverage,
            reference_date=ref,
        )

    latest_published = dashboard_snapshot.get_latest_dashboard_snapshot()
    latest_record = dashboard_snapshot.get_latest_dashboard_snapshot_record()
    return build_diagnostic_report(
        sync_status=sync_status,
        health=health,
        latest_published_snapshot=latest_published,
        latest_snapshot_record=latest_record,
        snapshot_unavailable_reason_fn=dashboard_snapshot.snapshot_unavailable_reason,
    )


def main(argv=None):
    args = _parse_args(argv)
    from app import app

    with app.app_context():
        report = build_report(
            slate_date=args.slate_date,
            reference_date=args.reference_date,
        )
    if args.compact:
        print(json.dumps(report, sort_keys=True))
    else:
        print(json.dumps(report, indent=2, sort_keys=True))
    if args.fail_on_blocker and report.get('publishable') is not True:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
