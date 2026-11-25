"""Compare the public League, Tonight and all club Boards with a single publication."""
import argparse
from datetime import datetime, timezone
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
    arms = {}
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
        arms[team] = len(pitchers)
    if league_edition() != (authority, states):
        raise ValueError('The published edition changed during verification')
    return dict(snapshot=snapshot, sync=sync, data_through=through, availability=reference,
                clubs=len(states), board_arms=arms, games=len(tonight['games']),
                compared_generation=binding['generation'] if binding else None,
                measured_at=datetime.now(timezone.utc).isoformat(), seconds=round(monotonic()-started, 2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--snapshot', type=int, required=True)
    parser.add_argument('--sync', type=int, required=True)
    parser.add_argument('--binding', type=Path, help='Independently reviewed source-generation receipt')
    args = parser.parse_args()
    with requests.Session() as session:
        result = verify(session, args.base_url, args.snapshot, args.sync,
                        json.loads(args.binding.read_text()) if args.binding else None)
    print(json.dumps(result))
