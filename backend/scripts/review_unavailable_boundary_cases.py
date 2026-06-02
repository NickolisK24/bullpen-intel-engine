"""
Generate a human-reviewable Candidate C Unavailable boundary report.

The script compares current thresholds with Candidate C from the unavailable
threshold experiment. It writes evidence only and does not modify production
thresholds or API behavior.
"""

from argparse import ArgumentParser
from datetime import date, datetime, timezone
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.availability_snapshot import latest_fatigue_rows  # noqa: E402
from services.availability_unavailable_boundary_review import (  # noqa: E402
    build_review_from_rows,
    render_json_report,
    render_markdown_report,
)


DEFAULT_OUTPUT = ROOT / 'reports' / 'availability_unavailable_boundary_review.md'


def parse_date(value):
    if value is None:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def write_report(report_text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding='utf-8')


def print_summary(review, output_path):
    print(f'Availability Unavailable boundary review written to {output_path}')
    print(f"Total moved pitchers: {review['total_moved']}")
    print(f"Transitions: {review['transition_counts']}")
    print(f"Unavailable bucket affected: {review['percent_unavailable_affected']}%")
    print(f"Recommendation category: {review['recommendation_category']}")


def main():
    parser = ArgumentParser(description='Review Candidate C Unavailable boundary cases.')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Report path to write.')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Report format.')
    parser.add_argument('--reference-date', help='YYYY-MM-DD date for review. Defaults to today.')
    args = parser.parse_args()

    reference_date = parse_date(args.reference_date) or date.today()
    output_path = Path(args.output)

    app = create_app()
    with app.app_context():
        rows = latest_fatigue_rows()
        generated_at = datetime.now(timezone.utc)
        review = build_review_from_rows(rows, reference_date=reference_date)
        if args.format == 'json':
            report = render_json_report(review, generated_at=generated_at)
        else:
            report = render_markdown_report(review, generated_at=generated_at)
        write_report(report, output_path)
        print_summary(review, output_path)


if __name__ == '__main__':
    main()
