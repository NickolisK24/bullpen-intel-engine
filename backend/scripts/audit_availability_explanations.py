"""
Generate an Availability Engine explanation-quality audit from local data.

The script applies the existing availability classification path and then
summarizes observed reasons, limitations, and reason categories. It does not
change thresholds, fatigue scoring, API responses, or frontend output.
"""

from argparse import ArgumentParser
from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.availability_explanation_audit import (  # noqa: E402
    audit_explanations,
    render_json_report,
    render_markdown_report,
)
from services.availability_snapshot import (  # noqa: E402
    CURRENT_AVAILABILITY_MODE,
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)


DEFAULT_OUTPUT = ROOT / 'reports' / 'availability_explanation_audit.md'


def parse_date(value):
    if value is None:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def build_audit(reference_date=None):
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
        'current': audit_explanations(current_records),
        'latest_workload_snapshot': audit_explanations(snapshot_records),
    }


def write_report(report_text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding='utf-8')


def _top_reasons(audit, limit=5):
    return [
        (row['text'], row['count'])
        for row in audit['reason_frequencies'][:limit]
    ]


def print_summary(audit, output_path):
    current = audit['current']
    snapshot = audit['latest_workload_snapshot']
    print(f'Availability explanation audit written to {output_path}')
    print(f"Current total pitchers: {current['total_pitchers']}")
    print(f"Current reason categories: {current['reason_category_distribution']}")
    print(f"Current top reasons: {_top_reasons(current)}")
    print(f"Latest-workload snapshot reason categories: {snapshot['reason_category_distribution']}")
    print(f"Latest-workload snapshot top reasons: {_top_reasons(snapshot)}")


def main():
    parser = ArgumentParser(description='Audit Availability Engine explanation quality.')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Report path to write.')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Report format.')
    parser.add_argument('--reference-date', help='YYYY-MM-DD date for current availability audit. Defaults to today.')
    args = parser.parse_args()

    reference_date = parse_date(args.reference_date)
    output_path = Path(args.output)

    app = create_app()
    with app.app_context():
        generated_at = datetime.now(timezone.utc)
        audit = build_audit(reference_date=reference_date)
        if args.format == 'json':
            report = render_json_report(
                audit['current'],
                snapshot_audit=audit['latest_workload_snapshot'],
                generated_at=generated_at,
                reference_date=audit['reference_date'],
            )
        else:
            report = render_markdown_report(
                audit['current'],
                snapshot_audit=audit['latest_workload_snapshot'],
                generated_at=generated_at,
                reference_date=audit['reference_date'],
            )
        write_report(report, output_path)
        print_summary(audit, output_path)


if __name__ == '__main__':
    main()
