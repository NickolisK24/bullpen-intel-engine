"""Compare the public League, Tonight and all club Boards with a single publication."""
import argparse
from datetime import date, datetime, timezone
import os
import json
from pathlib import Path
from time import monotonic

import requests

from services.mlb_club_directory import MLB_TEAM_IDS


def verify(session, base_url, snapshot, sync, binding=None):
    started = monotonic()

    def read(path):
        response = session.get(base_url.rstrip('/') + path, timeout=30)
        response.raise_for_status()
        return response.json()

    def league_edition():
        league = read('/api/bullpen/team-states')
        identity = league['publication_authority']
        states = {row['team_id']: row['team_state'] for row in league['teams']}
        if (identity['snapshot_id'], identity['sync_run_id']) != (snapshot, sync):
            raise ValueError('League is serving another publication')
        if set(states) != set(MLB_TEAM_IDS) or len(league['teams']) != len(states):
            raise ValueError('League has incomplete or ambiguous club identities')
        return identity, states

    authority, states = league_edition()
    through = authority['data_through']
    reference = authority['availability_reference_date']
    if binding and (binding['data_through'] != through or binding['availability_reference'] != reference
                    or {int(k): v['state'] for k, v in binding['teams'].items()} != states):
        raise ValueError('Public Team State differs from the independently reviewed generation')
    tonight = read('/api/bullpen/intelligence/tonight?contract=tonight_v1')
    edition = tonight['edition']
    identity = edition['publication']
    if ((identity['dashboard_snapshot_id'], identity['sync_run_id']) != (snapshot, sync)
            or edition['data_through'] != through or edition['availability_reference_date'] != reference):
        raise ValueError('Tonight has different publication identifiers or dates')
    if binding:
        from sync_v3.staging_product_delivery import verify_slate
        verify_slate(tonight['games'], binding)
    arm_ids = {}
    for team, state in sorted(states.items()):
        board = read(f'/api/bullpen/teams/{team}/board-v2/core')
        identity = board['publication_identity']
        if ((identity['snapshot_id'], identity['sync_run_id']) != (snapshot, sync) or identity['team_id'] != team
                or identity['represented_date'] != through or identity['availability_reference_date'] != reference
                or board['team_state'] != state):
            raise ValueError(f'Board for club {team} disagrees with the League')
        pitchers = [row['pitcher_id'] for row in board['active_bullpen']['arms']]
        if len(pitchers) != len(set(pitchers)):
            raise ValueError(f'Duplicate Board pitcher for club {team}')
        arm_ids[team] = sorted(pitchers)
    if league_edition() != (authority, states):
        raise ValueError('The published edition changed during verification')
    from hashlib import sha256
    from services.tonight_read_model import content_sha256
    frozen = dict(snapshot=snapshot, sync=sync, data_through=through, availability=reference,
                  states=states, board_pitchers=arm_ids, tonight=content_sha256(tonight))
    fingerprint = sha256(json.dumps(frozen, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return dict(snapshot=snapshot, sync=sync, data_through=through, availability=reference,
                public_edition_sha256=fingerprint, tonight_sha256=frozen['tonight'], product_day=edition.get('baseball_date'),
                clubs=len(states), board_arms={team: len(staff) for team, staff in arm_ids.items()}, games=len(tonight['games']),
                compared_generation=binding['generation'] if binding else None,
                measured_at=datetime.now(timezone.utc).isoformat(), seconds=round(monotonic()-started, 2))


def capture_legacy_predecessor(served):
    """Read the selected legacy edition using the operator's existing PostgreSQL read binding."""
    from flask import Flask
    from sqlalchemy import text
    from sqlalchemy.engine import make_url
    from models.dashboard_snapshot import DashboardSnapshot
    from services.dashboard_snapshot import SNAPSHOT_TYPE_BULLPEN_DASHBOARD
    from sync_v3.staging_product_delivery import legacy_predecessor_receipt
    from utils.db import db

    url = make_url(os.environ['SYNC_V3_PREFLIGHT_DATABASE_URL'])
    if url.get_backend_name() != 'postgresql':
        raise ValueError('First-handoff preflight requires the product PostgreSQL database')
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_ENGINE_OPTIONS={
        'connect_args': {'options': '-c default_transaction_read_only=on', 'connect_timeout': 10}})
    db.init_app(app)
    with app.app_context(), db.session.begin():
        db.session.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
        database = db.session.execute(text('SELECT current_database()')).scalar_one()
        selected = DashboardSnapshot.query.filter_by(snapshot_type=SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                                                     is_published=True).one()
        if (selected.id, selected.sync_run_id) != (served['snapshot'], served['sync']):
            raise ValueError('Database selector differs from the verified public edition')
        pin = legacy_predecessor_receipt(selected, date.fromisoformat(served['product_day']))
        if pin['tonight_sha256'] != served['tonight_sha256']:
            raise ValueError('Stored Tonight content differs from the served predecessor')
        return dict(database=database, database_edition=pin, public_edition_sha256=served['public_edition_sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--snapshot', type=int, required=True)
    parser.add_argument('--sync', type=int, required=True)
    parser.add_argument('--binding', type=Path, help='Independently reviewed source-generation receipt')
    parser.add_argument('--expect-public-sha256', help='Public edition fingerprint captured before the handoff')
    parser.add_argument('--capture-legacy-predecessor', action='store_true',
                        help='Include the first-handoff receipt using SYNC_V3_PREFLIGHT_DATABASE_URL')
    args = parser.parse_args()
    with requests.Session() as session:
        result = verify(session, args.base_url, args.snapshot, args.sync,
                        json.loads(args.binding.read_text()) if args.binding else None)
    if args.expect_public_sha256 and result['public_edition_sha256'] != args.expect_public_sha256:
        parser.exit(1, 'Public edition differs from the approved rollback receipt\n')
    if args.capture_legacy_predecessor:
        result['legacy_predecessor'] = capture_legacy_predecessor(result)
    print(json.dumps(result))
