"""
Generate an Availability Engine threshold audit from local database data.

The script applies services.availability.classify_availability to existing
fatigue/game-log rows and writes a Markdown or JSON report. It does not change
thresholds, fatigue scoring, API responses, or frontend output.
"""

from argparse import ArgumentParser
from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.availability_snapshot import (  # noqa: E402
    CURRENT_AVAILABILITY_MODE,
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from services.availability_threshold_audit import (  # noqa: E402
    render_json_report,
    render_markdown_report,
    summarize_records,
)


DEFAULT_OUTPUT = ROOT / 'reports' / 'availability_threshold_audit.md'


def parse_date(value):
    if value is None:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def build_audit(reference_date=None, near_threshold_limit=12):
    ref = reference_date or date.today()
    rows = latest_fatigue_rows()
    current_records = classify_latest_fatigue_rows(
        rows,
        reference_date=ref,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    snapshot_records = classify_latest_fatigue_rows(
        rows,
        reference_date=ref,
        mode=LATEST_WORKLOAD_SNAPSHOT_MODE,
    )
    return {
        'reference_date': ref,
        'current': summarize_records(current_records, near_threshold_limit=near_threshold_limit),
        'latest_workload_snapshot': summarize_records(snapshot_records, near_threshold_limit=near_threshold_limit),
    }


def write_report(report_text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding='utf-8')


def print_summary(audit, output_path):
    current = audit['current']
    snapshot = audit['latest_workload_snapshot']
    print(f'Availability threshold audit written to {output_path}')
    print(f"Current total pitchers: {current['total_pitchers']}")
    print(f"Current status distribution: {current['status_distribution']}")
    print(f"Current data state distribution: {current['data_state_distribution']}")
    print(f"Latest-workload snapshot status distribution: {snapshot['status_distribution']}")
    print(f"Latest-workload snapshot data state distribution: {snapshot['data_state_distribution']}")


def main():
    parser = ArgumentParser(description='Audit Availability Engine threshold behavior.')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Report path to write.')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Report format.')
    parser.add_argument('--reference-date', help='YYYY-MM-DD date for current availability audit. Defaults to today.')
    parser.add_argument('--near-threshold-limit', type=int, default=12, help='Number of near-threshold examples per section.')
    args = parser.parse_args()

    reference_date = parse_date(args.reference_date)
    output_path = Path(args.output)

    app = create_app()
    with app.app_context():
        generated_at = datetime.now(timezone.utc)
        audit = build_audit(reference_date=reference_date, near_threshold_limit=args.near_threshold_limit)
        if args.format == 'json':
            report = render_json_report(
                audit['current'],
                snapshot_summary=audit['latest_workload_snapshot'],
                generated_at=generated_at,
                reference_date=audit['reference_date'],
            )
        else:
            report = render_markdown_report(
                audit['current'],
                snapshot_summary=audit['latest_workload_snapshot'],
                generated_at=generated_at,
                reference_date=audit['reference_date'],
            )
        write_report(report, output_path)
        print_summary(audit, output_path)


if __name__ == '__main__':
    main()
