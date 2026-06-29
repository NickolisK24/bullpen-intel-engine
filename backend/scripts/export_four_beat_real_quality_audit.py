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
    build_bounded_live_four_beat_real_quality_audit,
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
        '--limit',
        type=int,
        default=DEFAULT_EXPECTED_TEAM_COUNT,
        help='Maximum team count for the bounded live audit path.',
    )
    parser.add_argument(
        '--unbounded-live',
        action='store_true',
        help='Use the legacy unbounded live preview path.',
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
    print(f"Payload source: {report['payload_source']}")
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
    bounded = report.get('bounded_live_diagnostic') or {}
    if bounded:
        print(
            'Canonical trace distribution: '
            f"{json.dumps(bounded['canonical_trace_story_type_counts'], sort_keys=True)}"
        )
        print(
            'Prior collapse reproduced: '
            f"{json.dumps(bounded['prior_collapse_reproduced'])}"
        )
        missing_review = bounded.get('missing_beat_evidence_review') or {}
        if missing_review:
            compact = {
                beat: {
                    'candidate_evidence_team_count': review.get('candidate_evidence_team_count'),
                    'eligible_candidate_team_count': review.get('eligible_candidate_team_count'),
                    'top_candidate_score': review.get('top_candidate_score'),
                    'selected_team_count': review.get('selected_team_count'),
                }
                for beat, review in sorted(missing_review.items())
            }
            print(
                'Missing beat evidence review: '
                f"{json.dumps(compact, sort_keys=True)}"
            )
        context_review = bounded.get('context_signal_accuracy_review') or {}
        if context_review:
            compact = {
                signal: {
                    'classification': review.get('classification'),
                    'classification_counts': review.get('classification_counts'),
                    'blocker_reason_counts': review.get('blocker_reason_counts'),
                    'numeric_ranges': review.get('numeric_ranges'),
                }
                for signal, review in sorted(context_review.items())
            }
            print(
                'Context signal accuracy review: '
                f"{json.dumps(compact, sort_keys=True)}"
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
        if args.unbounded_live:
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
        else:
            report = build_bounded_live_four_beat_real_quality_audit(
                generated_at=datetime.now(timezone.utc),
                expected_team_count=args.expected_team_count,
                limit=args.limit,
                initial_audit_summary=_initial_summary(args.initial_summary_json),
                initial_findings=args.initial_finding,
                fixes_applied=args.fix_applied,
            )

    output_path = write_json_report(report, args.output)
    print_summary(report, output_path)
    return 0 if report['complete_team_count'] and not report['unexpected_story_type_count'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
