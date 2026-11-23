import json
from datetime import date
from pathlib import Path

import pytest

from sync_v3.board_delivery_comparison import compare_club, compare_edition

DAY = date(2017, 8, 29)


@pytest.fixture
def selection():
    path = Path(__file__).parent / 'fixtures' / 'sync_v3_board_delivery.json'
    board, core, details = json.loads(path.read_text())
    # Serving IDs belong to the serving database, independently of MLB IDs.
    ids = {}
    for local_id, row in enumerate(core['active_bullpen']['arms'], start=1):
        ids[local_id] = row['pitcher_id']
        row['pitcher_id'] = local_id
    return board, core, details, ids


def test_supported_and_withheld_reads(selection):
    assert compare_club(*selection, DAY) == dict(team=117, arms=2, current=1, withheld_current=1)


@pytest.mark.parametrize('invalid', ['stale_read', 'details', 'club', 'missing_arm', 'state'])
def test_refuse_material_difference(selection, invalid):
    board, core, details, ids = selection
    if invalid == 'stale_read':
        core['active_bullpen']['arms'][0]['public_labels']['read'] = board['active_bullpen'][0]['read']['arm_read']
    elif invalid == 'details':
        details['publication_identity']['snapshot_id'] += 1
    elif invalid == 'club':
        details['team']['team_id'] += 1
    elif invalid == 'missing_arm':
        core['active_bullpen']['arms'].pop()
    else:
        core['team_state']['public_state'] = 'fresh'
    with pytest.raises(ValueError):
        compare_club(board, core, details, ids, DAY)


def test_refuse_incomplete_league(selection):
    board, core, details, ids = selection
    with pytest.raises(ValueError, match='30 MLB clubs'):
        compare_edition({117: board}, {117: (core, details)}, ids, DAY)
