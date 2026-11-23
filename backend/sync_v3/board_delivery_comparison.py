"""Compare selected v3 Boards with saved public core/details responses. Offline only."""

import argparse
from datetime import date
import json
from pathlib import Path
import re

from services.mlb_club_directory import MLB_TEAM_IDS
from services.pitcher_public_labels import build_public_arm_read, public_arm_context
from services.team_board_delivery import normalize_team_board_identity
from services.team_board_v2 import (
    CORE_CAPABILITY, CORE_CONTRACT_VERSION, DETAILS_CAPABILITY, DETAILS_CONTRACT_VERSION,
)


def compare_club(board, core, details, pitcher_ids, product_day):
    """The served database owns its route IDs. Join across databases only by MLB ID."""
    team = board['team']['team_id']
    identity = normalize_team_board_identity(core['publication_identity'])
    if (core['freshness']['data_through'] != board['data_through']
            or core['freshness']['availability_reference_date'] != board['availability_reference']):
        raise ValueError(f'Club {team}: workload or availability date differs')
    if (board['status'] != 'represented' or board['current_serving_eligible'] is not False
            or (core['capability'], core['contract_version']) != (CORE_CAPABILITY, CORE_CONTRACT_VERSION)
            or (details['capability'], details['contract_version']) != (DETAILS_CAPABILITY, DETAILS_CONTRACT_VERSION)
            or any(identity[key] <= 0 for key in ('snapshot_id', 'sync_run_id', 'dashboard_payload_version'))
            or core['publication_identity'] != details['publication_identity']
            or any(r['team']['team_abbreviation'] != board['team']['team_abbreviation'] for r in (core, details))
            or identity['team_abbreviation'] != board['team']['team_abbreviation']
            or any(r['team']['team_id'] != team or r['represented_date'] != board['data_through'] for r in (core, details))
            or (identity['team_id'], identity['represented_date'], identity['availability_reference_date'])
            != (team, board['data_through'], board['availability_reference'])):
        raise ValueError('Board selection and public delivery identities disagree')
    state = board['team']['team_state']
    if state != core['team_state']:
        raise ValueError(f'Club {team}: Team State differs')
    expected = {a['mlb_id']: a for a in board['active_bullpen']}
    rows = core['active_bullpen']['arms']
    served = {pitcher_ids[a['pitcher_id']]: a for a in rows}
    if (len(expected) != len(board['active_bullpen']) or len(served) != len(rows)
            or served.keys() != expected.keys() or core['active_bullpen']['arm_count'] not in (None, len(rows))):
        raise ValueError(f'Club {team}: active membership differs')
    roster = {'is_active_mlb': True, 'is_authoritative': True}
    current = 0
    for player, arm in expected.items():
        source = arm['read'] or {}
        availability = source.get('availability') or {}
        context = public_arm_context(freshness=core['freshness'], product_day=product_day,
                                     club_active=state['available'], roster=roster,
                                     data_state=availability.get('data_state'), latest_game_date=source.get('last_workload'))
        is_current = context['mode'] == 'current'
        label = build_public_arm_read(availability if is_current else None, roster_status=roster)
        actual = served[player]
        if (context != actual['arm_context'] or label != actual['public_labels']['read']
                or (is_current and source.get('arm_read') != label)
                or availability.get('availability_status') != actual['availability']['status']):
            raise ValueError(f'Club {team}, MLB pitcher {player}: served availability or display differs')
        current += int(is_current)
    return dict(team=team, arms=len(rows), current=current, withheld_current=len(rows)-current)


def compare_edition(boards, delivered, pitcher_ids, product_day):
    if set(boards) != set(MLB_TEAM_IDS) or set(delivered) != set(MLB_TEAM_IDS):
        raise ValueError('Expected all 30 MLB clubs on both sides')
    if (any(type(k) is not int or k <= 0 or type(v) is not int or v <= 0 for k, v in pitcher_ids.items())
            or len(set(pitcher_ids.values())) != len(pitcher_ids)):
        raise ValueError('Ambiguous pitcher identity map')
    revisions = set()
    publications = set()
    clubs = []
    for team in sorted(MLB_TEAM_IDS):
        board, (core, details) = boards[team], delivered[team]
        if board['team']['team_id'] != team:
            raise ValueError('Selected Board belongs to another club')
        revision, digest = board['selection_revision'], board['generation']
        if type(revision) is not int or revision <= 0 or not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
            raise ValueError('Missing selected generation')
        revisions.add((revision, digest, board['data_through'], board['availability_reference']))
        clubs.append(compare_club(board, core, details, pitcher_ids, product_day))
        identity = core['publication_identity']
        publications.add(tuple(sorted((k, v) for k, v in identity.items() if k not in ('team_id', 'team_abbreviation'))))
    if len(revisions) != 1 or len(publications) != 1:
        raise ValueError('Mixed editions across the league')
    return dict(scope='team_board_core_delivery_comparison', revision=revision, generation=digest,
                snapshot_id=identity['snapshot_id'], sync_run_id=identity['sync_run_id'], clubs=clubs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('boards', type=Path, help='Directory containing selected board-TEAM.json responses')
    parser.add_argument('delivered', type=Path, help='Directory containing TEAM.json [core, details] pairs')
    parser.add_argument('pitcher_ids', type=Path, help='JSON mapping of serving database Pitcher.id to MLB ID')
    parser.add_argument('--product-day', type=date.fromisoformat, required=True)
    args = parser.parse_args()

    def read(path):
        return json.loads(path.read_text())

    print(json.dumps(compare_edition(
        {t: read(args.boards / f'board-{t}.json') for t in MLB_TEAM_IDS},
        {t: read(args.delivered / f'{t}.json') for t in MLB_TEAM_IDS},
        {int(k): v for k, v in read(args.pitcher_ids).items()}, args.product_day,
    ), indent=2))


if __name__ == '__main__':
    main()
