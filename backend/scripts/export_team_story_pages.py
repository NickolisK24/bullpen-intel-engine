"""Export the static per-team preview pages the Vercel frontend serves.

ONE trusted publication per run (DIST-003 / #594).

This used to read its story copy from the published dashboard snapshot and its
board copy from ``api.bullpen._build_team_board`` — the live builder, running
against mutable acquisition tables. A single generated page could therefore
combine a snapshot-time story headline with a live-table board read, two
different baseball dates, and disclose neither.

Now the run resolves the latest valid dashboard snapshot once, takes its story
feed from that snapshot's payload, takes every board from
``build_published_team_board`` (the same trusted publication path a public
``/api/bullpen/teams/{id}/board`` request is served from in production), and
stamps each page with the snapshot it came from. Any board that resolves from a
different snapshot cannot be combined with that story feed, so its claim is
withheld rather than published with two clocks.

Fail closed: with no valid published snapshot the run writes nothing and exits
non-zero. It never falls back to the live builder, and it never fabricates a
present-tense claim. The previously generated pages stay in place — and because
they now carry their own data-through date, leaving them is honest: they visibly
describe an earlier baseball date instead of silently claiming tonight.

The run's structured result travels on its own channel. ``--result-out`` names a
file this process writes atomically; stdout stays a mixed human/diagnostic
stream and carries the same JSON only as a courtesy. The two are not
interchangeable, and the difference is not theoretical: importing this script's
own dependencies prints a scheduler banner to stdout before ``main`` runs, so
capturing stdout as machine evidence produces a file that does not parse.
"""

import argparse
import logging
import os
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from app import app
from models.pitcher import Pitcher
from services.team_story_previews import (
    DEFAULT_OG_IMAGE_PATH,
    DEFAULT_SITE_URL,
    REPRESENTATION_WITHHELD,
    build_team_story_previews,
    write_team_story_pages,
)
from services import dashboard_snapshot as dashboard_snapshot_service
from services.public_serving_authority import build_published_team_board
from utils.db import db
from utils.summary_output import (
    SummaryOutputError,
    serialize_summary,
    write_summary,
)

EXPECTED_MLB_TEAM_COUNT = 30

# Exit codes. A trusted-publication failure is deliberately distinguishable from
# an ordinary count mismatch so the workflow log says which one happened.
EXIT_OK = 0
EXIT_COUNT_MISMATCH = 1
EXIT_NO_TRUSTED_PUBLICATION = 2
EXIT_RESULT_OUTPUT_FAILED = 3

export_logger = logging.getLogger('baseballos.team_story_export')


def parse_args():
    parser = argparse.ArgumentParser(
        description='Export static per-team story preview pages for the Vercel frontend.'
    )
    parser.add_argument(
        '--output',
        default=str(REPO_ROOT / 'frontend' / 'public'),
        help='Frontend public root that should receive team/ABBR/index.html files.',
    )
    parser.add_argument(
        '--site-url',
        default=os.environ.get('BASEBALLOS_SITE_URL', DEFAULT_SITE_URL),
        help='Canonical public frontend origin.',
    )
    parser.add_argument(
        '--og-image',
        default=os.environ.get('BASEBALLOS_OG_IMAGE', DEFAULT_OG_IMAGE_PATH),
        help='Generic BaseballOS OG image path or absolute URL.',
    )
    parser.add_argument(
        '--expected-team-count',
        type=int,
        default=EXPECTED_MLB_TEAM_COUNT,
        help='Expected number of MLB team preview pages to emit.',
    )
    parser.add_argument(
        '--result-out',
        help=(
            'Write the structured export result JSON to this path. This is the '
            'machine-readable channel the delivery gate reads; stdout is not.'
        ),
    )
    return parser.parse_args()


def active_teams():
    rows = (
        db.session.query(
            Pitcher.team_id,
            Pitcher.team_name,
            Pitcher.team_abbreviation,
        )
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
        .group_by(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .order_by(Pitcher.team_abbreviation)
        .all()
    )
    return [
        {
            'team_id': row.team_id,
            'team_name': row.team_name,
            'team_abbreviation': row.team_abbreviation,
        }
        for row in rows
    ]


def load_trusted_publication():
    """The one trusted dashboard snapshot this run publishes from, or ``None``.

    There is deliberately no live-build fallback. A run with no valid published
    snapshot has no trusted publication to cite and must not publish a claim.
    """
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None or not isinstance(snapshot.payload, dict):
        return None
    return snapshot


def build_team_boards(teams):
    """One trusted published board per team — never the live mutable builder."""
    boards = []
    eligible = [team for team in teams if team.get('team_id') is not None]
    for index, team in enumerate(eligible, start=1):
        export_logger.info(
            'Building trusted team board %s/%s: %s (team_id=%s)',
            index,
            len(eligible),
            team.get('team_abbreviation') or team.get('team_name'),
            team['team_id'],
        )
        boards.append(build_published_team_board(team['team_id']))
    return boards


def emit_result(result, result_out):
    """Emit ONE result object on both channels; report whether evidence landed.

    stdout keeps its existing JSON line, unchanged, for humans and for local
    operators. It is not the machine channel and never was safe as one: this
    script's own imports print ``[scheduler] AUTO_SYNC disabled — daily
    scheduler not started.`` to stdout before ``main`` is ever entered, so
    anything that captures stdout captures a diagnostic line ahead of the JSON.
    Scheduled run 31693516516 captured exactly that, and the delivery gate —
    correctly — refused to publish from a file whose first byte was not JSON.

    ``--result-out`` is the machine channel: the SAME object, serialized the
    same way, written atomically by this process instead of reconstructed by a
    shell reading a mixed stream.

    Returns ``False`` when a requested result file could not be written, so the
    caller can refuse to exit zero without provenance.
    """
    print(serialize_summary(result))
    if not result_out:
        return True
    try:
        write_summary(result, result_out)
    except SummaryOutputError as exc:
        # Only the safe classification is reported; the underlying message can
        # carry a filesystem path.
        export_logger.error(
            'Structured export result output failed (reason=%s). This run '
            'produced no machine-readable delivery evidence.',
            exc.reason,
        )
        return False
    return True


def main():
    args = parse_args()
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    with app.app_context():
        snapshot = load_trusted_publication()
        if snapshot is None:
            export_logger.error(
                'No valid published dashboard snapshot is available; refusing to '
                'generate team preview pages. Previously generated pages are left '
                'in place and continue to state the baseball date they describe.'
            )
            # Diagnostic evidence for a refusal, not a rescue. This run exits
            # non-zero either way, so the distinguishable trusted-publication
            # code stays the reported one; emit_result has already logged any
            # write failure loudly. A failure result in the file can never
            # authorize publication — the gate requires status 'ok'.
            emit_result({
                'status': 'no_trusted_publication',
                'generated_at': generated_at,
                'pages_written': 0,
            }, args.result_out)
            return EXIT_NO_TRUSTED_PUBLICATION

        payload = snapshot.payload
        snapshot_id = snapshot.id
        teams = active_teams()
        boards = build_team_boards(teams)
        previews = build_team_story_previews(
            teams,
            dashboard_payload=payload,
            boards=boards,
            generated_at=generated_at,
            expected_snapshot_id=snapshot_id,
            site_url=args.site_url,
            og_image_path=args.og_image,
        )
        output = write_team_story_pages(
            previews,
            args.output,
            site_url=args.site_url,
            og_image_path=args.og_image,
        )
        snapshot_data_through = (
            snapshot.data_through.isoformat() if snapshot.data_through else None
        )

    withheld_reasons = Counter(
        preview['withheld_reason']
        for preview in previews
        if preview.get('representation') == REPRESENTATION_WITHHELD
    )
    if withheld_reasons:
        export_logger.warning(
            'Withheld a dated claim for %s team page(s): %s',
            sum(withheld_reasons.values()),
            dict(withheld_reasons),
        )

    result = {
        'status': 'ok',
        'teams': len(teams),
        'previews': len(previews),
        'story_previews': sum(1 for preview in previews if preview['has_story']),
        'dated_previews': sum(
            1 for preview in previews
            if preview.get('representation') != REPRESENTATION_WITHHELD
        ),
        'withheld_previews': sum(withheld_reasons.values()),
        'withheld_reasons': dict(withheld_reasons),
        'withheld_teams': output['withheld_teams'],
        'payload_source': 'published_dashboard_snapshot',
        'publication_snapshot_id': snapshot_id,
        'publication_data_through': snapshot_data_through,
        'generated_at': generated_at,
        'output': output,
    }
    emitted = emit_result(result, args.result_out)

    expected_count = args.expected_team_count
    if output['count'] == len(teams) == expected_count:
        exit_code = EXIT_OK
    else:
        exit_code = EXIT_COUNT_MISMATCH

    # A run that was asked for durable evidence and could not produce it must
    # never exit zero: a missing result file and a clean publication would
    # otherwise be indistinguishable downstream.
    if not emitted:
        return exit_code or EXIT_RESULT_OUTPUT_FAILED
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
