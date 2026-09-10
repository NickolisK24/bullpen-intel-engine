import argparse
import logging
import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Manual, read-only review tool; never start the in-process scheduler.
os.environ['AUTO_SYNC'] = 'false'


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=(
            'Generate the Pitcher/Team Context explanation editorial corpus. '
            'Read-only: no sync, no snapshot write, no publishing.'
        )
    )
    parser.add_argument(
        '--output-md',
        dest='output_md',
        default=str(REPO_ROOT / 'artifacts' / 'context_explanation_editorial_review_E2D1.md'),
        help='Markdown artifact path.',
    )
    parser.add_argument(
        '--review-label',
        dest='review_label',
        help='Optional title label for the generated review artifact.',
    )
    parser.add_argument(
        '--include-fixtures',
        action='store_true',
        help=(
            'Fill uncaptured healthy-state categories with deterministic fixture '
            'examples that exercise the same backend helper paths.'
        ),
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )

    from app import app
    from services.context_explanation_editorial_review import (
        build_context_explanation_editorial_review,
        write_context_explanation_editorial_review,
    )

    report = build_context_explanation_editorial_review(
        app=app,
        artifact_path=args.output_md,
        review_label=args.review_label,
        include_fixture_examples=args.include_fixtures,
    )
    output = write_context_explanation_editorial_review(report, args.output_md)
    print(output)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
