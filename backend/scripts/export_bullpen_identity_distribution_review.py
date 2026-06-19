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

from services.bullpen_identity_distribution_review import (  # noqa: E402
    DEFAULT_EXPECTED_TEAM_COUNT,
    build_bullpen_identity_distribution_review,
    write_json_report,
)


DEFAULT_OUTPUT = REPO_ROOT / 'artifacts' / 'bullpen_identity_distribution_review.json'


def parse_args():
    parser = argparse.ArgumentParser(
        description='Export an internal Bullpen Identity V1 distribution review.'
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
    print(f'Bullpen Identity distribution review written to {output_path}')
    print(f"Teams reviewed: {report['team_count']}")
    print(f"Identity distribution: {json.dumps(report['identity_distribution'], sort_keys=True)}")
    print(
        'Teams flagged for human review: '
        f"{len(report['review_findings']['teams_for_human_review'])}"
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

    with flask_app.app_context():
        dashboard_payload = build_bullpen_dashboard_payload(use_published_freshness=False)
        report = build_bullpen_identity_distribution_review(
            dashboard_payload,
            generated_at=datetime.now(timezone.utc),
            expected_team_count=args.expected_team_count,
            payload_source='live_dashboard_build',
        )

    output_path = write_json_report(report, args.output)
    print_summary(report, output_path)
    return 0 if report['complete_team_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
