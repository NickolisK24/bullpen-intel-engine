import argparse
import json
import logging
import os
import sys
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
    build_team_story_previews,
    write_team_story_pages,
)
from services import dashboard_snapshot as dashboard_snapshot_service
from utils.db import db

EXPECTED_MLB_TEAM_COUNT = 30


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


def build_team_boards(teams):
    from api.bullpen import _build_team_board

    export_logger = logging.getLogger('baseballos.team_story_export')
    boards = []
    eligible = [team for team in teams if team.get('team_id') is not None]
    for index, team in enumerate(eligible, start=1):
        export_logger.info(
            'Building team board %s/%s: %s (team_id=%s)',
            index,
            len(eligible),
            team.get('team_abbreviation') or team.get('team_name'),
            team['team_id'],
        )
        boards.append(_build_team_board(team['team_id']))
    return boards


def load_dashboard_payload():
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is not None and isinstance(snapshot.payload, dict):
        return snapshot.payload, 'published_dashboard_snapshot'

    from api.bullpen import build_bullpen_dashboard_payload

    return build_bullpen_dashboard_payload(use_published_freshness=False), 'live_dashboard_build'


def main():
    args = parse_args()
    logging.basicConfig(
        level=os.environ.get('LOG_LEVEL', 'INFO').upper(),
        format='%(asctime)s %(levelname)s %(name)s %(message)s',
    )
    with app.app_context():
        payload, payload_source = load_dashboard_payload()
        teams = active_teams()
        boards = build_team_boards(teams)
        previews = build_team_story_previews(
            teams,
            dashboard_payload=payload,
            boards=boards,
            site_url=args.site_url,
            og_image_path=args.og_image,
        )
        output = write_team_story_pages(
            previews,
            args.output,
            site_url=args.site_url,
            og_image_path=args.og_image,
        )
    result = {
        'status': 'ok',
        'teams': len(teams),
        'previews': len(previews),
        'story_previews': sum(1 for preview in previews if preview['has_story']),
        'neutral_previews': sum(1 for preview in previews if not preview['has_story']),
        'payload_source': payload_source,
        'output': output,
    }
    print(json.dumps(result, sort_keys=True))
    expected_count = args.expected_team_count
    return 0 if output['count'] == len(teams) == expected_count else 1


if __name__ == '__main__':
    raise SystemExit(main())
