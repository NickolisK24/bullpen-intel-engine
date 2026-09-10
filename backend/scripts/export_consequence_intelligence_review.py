import argparse
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from services.consequence_intelligence_review import (  # noqa: E402
    DEFAULT_EXPECTED_TEAM_COUNT,
    build_consequence_intelligence_review,
    current_data_through_date,
    snapshot_record_metadata,
    write_json_report,
)


DEFAULT_OUTPUT = REPO_ROOT / 'artifacts' / 'consequence_intelligence_review.json'


def parse_args():
    parser = argparse.ArgumentParser(
        description='Export an internal Consequence Intelligence V1 review.'
    )
    parser.add_argument(
        '--output',
        default=str(DEFAULT_OUTPUT),
        help='JSON report path to write.',
    )
    parser.add_argument(
        '--expected-team-count',
        type=int,
        default=DEFAULT_EXPECTED_TEAM_COUNT,
        help='Expected number of MLB teams in the review.',
    )
    parser.add_argument(
        '--config',
        default=None,
        help='Optional Flask config name. Defaults to APP_ENV.',
    )
    return parser.parse_args()


def print_summary(report, output_path):
    summary = report['distribution_summary']
    print(f'Consequence Intelligence review written to {output_path}')
    print(f"Teams reviewed: {summary['teams_reviewed']}")
    print(f"Teams with comparison: {summary['teams_with_comparison_available']}")
    print(f"Teams with primary consequence: {summary['teams_with_primary_consequence']}")
    print(f"Teams without consequence: {summary['teams_without_consequence']}")
    print(
        'Consequence types: '
        f"{json.dumps(summary['consequence_counts_by_type'], sort_keys=True)}"
    )
    print(
        'Review flags: '
        f"{json.dumps(summary['review_flag_counts'], sort_keys=True)}"
    )


def main():
    args = parse_args()
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    if args.config:
        os.environ['APP_ENV'] = args.config

    from app import app as flask_app  # noqa: WPS433
    from api.bullpen import build_bullpen_dashboard_payload  # noqa: WPS433
    from services import dashboard_snapshot as snapshot_service  # noqa: WPS433

    with flask_app.app_context():
        current_payload = build_bullpen_dashboard_payload(use_published_freshness=False)
        current_data_through = current_data_through_date(current_payload)
        prior_snapshot = snapshot_service.get_latest_dashboard_snapshot_before(
            current_data_through
        )
        prior_payload = prior_snapshot.payload if prior_snapshot is not None else None
        report = build_consequence_intelligence_review(
            current_payload,
            prior_payload,
            generated_at=datetime.now(timezone.utc),
            expected_team_count=args.expected_team_count,
            current_payload_source='live_dashboard_build',
            prior_payload_source='ready_dashboard_snapshot_before_current_data_through',
            prior_snapshot_metadata=snapshot_record_metadata(prior_snapshot),
        )

    output_path = write_json_report(report, args.output)
    print_summary(report, output_path)
    return 0 if report['complete_team_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
