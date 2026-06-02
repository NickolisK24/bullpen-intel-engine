"""
Run an Availability Engine Unavailable threshold comparison experiment.

The script compares current thresholds against candidate Unavailable-only
changes using latest-workload snapshot mode. It writes a report and does not
change production thresholds or API behavior.
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
from services.availability_unavailable_experiment import (  # noqa: E402
    build_experiment,
    render_json_report,
    render_markdown_report,
)


DEFAULT_OUTPUT = ROOT / 'reports' / 'availability_unavailable_threshold_experiment.md'


def parse_date(value):
    if value is None:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def write_report(report_text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(report_text, encoding='utf-8')


def print_summary(experiment, output_path):
    print(f'Availability Unavailable threshold experiment written to {output_path}')
    print(f"Baseline status distribution: {experiment['baseline_summary']['status_distribution']}")
    for comparison in experiment['comparisons']:
        candidate = comparison['candidate']
        moved = sum(comparison['unavailable_moves'].values())
        print(
            f"{candidate.key}: {comparison['candidate_summary']['status_distribution']} "
            f"(Unavailable delta {comparison['status_delta'].get('Unavailable', 0)}, moved {moved})"
        )
    print(f"Recommendation: {experiment['recommendation']['decision']}")


def main():
    parser = ArgumentParser(description='Compare Unavailable threshold candidates.')
    parser.add_argument('--output', default=str(DEFAULT_OUTPUT), help='Report path to write.')
    parser.add_argument('--format', choices=['markdown', 'json'], default='markdown', help='Report format.')
    parser.add_argument('--reference-date', help='YYYY-MM-DD date for experiment. Defaults to today.')
    args = parser.parse_args()

    reference_date = parse_date(args.reference_date) or date.today()
    output_path = Path(args.output)

    app = create_app()
    with app.app_context():
        rows = latest_fatigue_rows()
        generated_at = datetime.now(timezone.utc)
        experiment = build_experiment(rows, reference_date=reference_date)
        if args.format == 'json':
            report = render_json_report(experiment, generated_at=generated_at)
        else:
            report = render_markdown_report(experiment, generated_at=generated_at)
        write_report(report, output_path)
        print_summary(experiment, output_path)


if __name__ == '__main__':
    main()
