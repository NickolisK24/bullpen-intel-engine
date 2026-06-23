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

from services.four_beat_real_quality_audit import (  # noqa: E402
    DEFAULT_EXPECTED_TEAM_COUNT,
    build_four_beat_real_quality_audit,
    write_json_report,
)
from services.story_audit_preview_v1 import build_story_audit_preview  # noqa: E402


DEFAULT_OUTPUT = REPO_ROOT / 'artifacts' / 'four_beat_real_quality_audit_v1.json'


def parse_args():
    parser = argparse.ArgumentParser(
        description='Export an internal Four Beat real-output quality audit.'
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
    parser.add_argument(
        '--initial-summary-json',
        default=None,
        help='Optional compact JSON summary from the pre-fix audit pass.',
    )
    parser.add_argument(
        '--initial-finding',
        action='append',
        default=[],
        help='Pre-fix audit finding to include in the artifact. May be repeated.',
    )
    parser.add_argument(
        '--fix-applied',
        action='append',
        default=[],
        help='Fix summary to include in the artifact. May be repeated.',
    )
    return parser.parse_args()


def _initial_summary(raw):
    if not raw:
        return {}
    return json.loads(raw)


def print_summary(report, output_path):
    summary = report['post_fix_summary']
    print(f'Four Beat real quality audit written to {output_path}')
    print(f"Teams reviewed: {summary['team_count']}")
    print(f"Story states: {summary['story_count']}")
    print(f"Neutral states: {summary['neutral_count']}")
    print(
        'Beat distribution: '
        f"{json.dumps(summary['beat_distribution'], sort_keys=True)}"
    )
    print(
        'Flagged issue counts: '
        f"{json.dumps(summary['flagged_issue_counts'], sort_keys=True)}"
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

    with flask_app.app_context():
        audit_preview = build_story_audit_preview()
        report = build_four_beat_real_quality_audit(
            audit_preview,
            generated_at=datetime.now(timezone.utc),
            expected_team_count=args.expected_team_count,
            payload_source='live_story_audit_preview',
            initial_audit_summary=_initial_summary(args.initial_summary_json),
            initial_findings=args.initial_finding,
            fixes_applied=args.fix_applied,
        )

    output_path = write_json_report(report, args.output)
    print_summary(report, output_path)
    return 0 if report['complete_team_count'] and not report['unexpected_story_type_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
