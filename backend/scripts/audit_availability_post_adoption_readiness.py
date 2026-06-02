"""
Generate post-adoption readiness audits for the Availability Engine.

This script is evidence-only. It verifies consistency after the governed
Unavailable 3-day pitch threshold adoption and writes Markdown reports.
"""

from argparse import ArgumentParser
from datetime import date, datetime
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from services.availability_post_adoption_readiness import (  # noqa: E402
    collect_readiness_evidence,
    final_classification,
    governance_status,
    render_reports,
)


DEFAULT_REPORTS_DIR = ROOT / 'reports'


def parse_date(value):
    if value is None:
        return date.today()
    return datetime.strptime(value, '%Y-%m-%d').date()


def main():
    parser = ArgumentParser(
        description='Audit Availability Engine readiness after threshold adoption.'
    )
    parser.add_argument(
        '--reports-dir',
        default=str(DEFAULT_REPORTS_DIR),
        help='Directory where Markdown audit reports are written.',
    )
    parser.add_argument(
        '--reference-date',
        help='YYYY-MM-DD current-availability date. Defaults to today.',
    )
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        evidence = collect_readiness_evidence(
            app,
            REPO_ROOT,
            reference_date=parse_date(args.reference_date),
        )
        paths = render_reports(evidence, args.reports_dir)

    print(f"Final classification: {final_classification(evidence)}")
    print(f"Documentation status: {evidence['documentation']['status']}")
    print(f"API status: {evidence['api']['status']}")
    print(f"Dashboard status: {evidence['dashboard']['status']}")
    print(f"Explanation status: {evidence['explanation']['status']}")
    print(f"Snapshot status: {evidence['snapshot']['status']}")
    print(f"Reachability status: {evidence['reachability']['status']}")
    print(f"Governance status: {governance_status(evidence)}")
    print(f"Recommendation status: {evidence['recommendation']['status']}")
    print('Reports written:')
    for key, path in paths.items():
        print(f"- {key}: {path}")


if __name__ == '__main__':
    main()
