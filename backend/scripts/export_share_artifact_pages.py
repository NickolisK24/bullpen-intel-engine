#!/usr/bin/env python3
"""Export crawler-visible pages for every immutable public Share Artifact."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import selectinload


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from app import app
from models.share_artifact import (
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    ShareArtifact,
)
from services.share_artifact_previews import (
    DEFAULT_OG_IMAGE_PATH,
    DEFAULT_SITE_URL,
    build_share_artifact_preview,
    write_share_artifact_pages,
)
from utils.db import db
from utils.summary_output import SummaryOutputError, serialize_summary, write_summary


EXIT_OK = 0
EXIT_EXPORT_FAILED = 1
EXIT_RESULT_OUTPUT_FAILED = 2
logger = logging.getLogger('baseballos.share_artifact_preview_export')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Export static route-specific immutable share artifact pages.'
    )
    parser.add_argument(
        '--output',
        default=str(REPO_ROOT / 'frontend' / 'public'),
        help='Frontend public root that should receive share/PUBLIC_ID/index.html.',
    )
    parser.add_argument(
        '--site-url',
        default=os.environ.get('BASEBALLOS_SITE_URL', DEFAULT_SITE_URL),
        help='Canonical public frontend origin.',
    )
    parser.add_argument(
        '--og-image',
        default=os.environ.get('BASEBALLOS_OG_IMAGE', DEFAULT_OG_IMAGE_PATH),
        help='BaseballOS raster social image path or absolute URL.',
    )
    parser.add_argument('--result-out', help='Write the structured export result JSON here.')
    return parser.parse_args(argv)


def public_artifacts(session=None):
    session = session or db.session
    return (
        session.query(ShareArtifact)
        .options(
            selectinload(ShareArtifact.evidence),
            selectinload(ShareArtifact.outgoing_relations),
            selectinload(ShareArtifact.incoming_relations),
        )
        .filter(
            ShareArtifact.lifecycle_state.in_((
                LIFECYCLE_PUBLISHED,
                LIFECYCLE_SUPERSEDED,
            ))
        )
        .order_by(ShareArtifact.public_id.asc())
        .all()
    )


def emit_result(result, result_out):
    print(serialize_summary(result))
    if not result_out:
        return True
    try:
        write_summary(result, result_out)
    except SummaryOutputError as exc:
        logger.error(
            'Structured share preview result output failed (reason=%s).', exc.reason,
        )
        return False
    return True


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    exported_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    try:
        with app.app_context():
            artifacts = public_artifacts()
            previews = [
                build_share_artifact_preview(
                    artifact,
                    site_url=args.site_url,
                    og_image_path=args.og_image,
                )
                for artifact in artifacts
            ]
            output = write_share_artifact_pages(
                previews,
                args.output,
                site_url=args.site_url,
                og_image_path=args.og_image,
            )
    except Exception as exc:
        logger.exception('Share artifact preview export failed closed.')
        result = {
            'status': 'failed',
            'exported_at': exported_at,
            'reason': type(exc).__name__,
            'pages_written': 0,
        }
        emit_result(result, args.result_out)
        return EXIT_EXPORT_FAILED

    lifecycle_counts = Counter(row['lifecycle_state'] for row in previews)
    artifact_type_counts = Counter(row['artifact_type'] for row in previews)
    result = {
        'status': 'ok',
        'exported_at': exported_at,
        'artifacts': len(artifacts),
        'previews': len(previews),
        'lifecycle_counts': dict(sorted(lifecycle_counts.items())),
        'artifact_type_counts': dict(sorted(artifact_type_counts.items())),
        'output': output,
    }
    if not emit_result(result, args.result_out):
        return EXIT_RESULT_OUTPUT_FAILED
    return EXIT_OK


if __name__ == '__main__':
    raise SystemExit(main())
