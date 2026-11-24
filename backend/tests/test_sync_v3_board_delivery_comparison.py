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


def test_handoff_requires_every_selected_club_and_its_receipt():
    from types import SimpleNamespace

    from scripts.rehearse_selected_publication import selection_receipt, verify_frozen_states
    from services.mlb_club_directory import MLB_TEAM_IDS

    digest = 'a' * 64
    through = date(2017, 8, 28)
    state = dict(available=True, public_state='fresh', data_through=through.isoformat())
    citation = dict(input_digest='b' * 64, facts_digest='c' * 64, revision=1)
    league = dict(status='represented', current_serving_eligible=False, selection_revision=5,
                  generation=digest, data_through=through.isoformat(), availability_reference=DAY.isoformat(),
                  teams=[dict(team_id=t, team_state=dict(state)) for t in MLB_TEAM_IDS],
                  citations={t: dict(readiness=citation) for t in MLB_TEAM_IDS})
    binding = selection_receipt(league, 5, digest)
    captured = {str(t): dict(dashboard_snapshot_id=7, team_id=t, value=dict(state)) for t in MLB_TEAM_IDS}
    snap = SimpleNamespace(id=7, data_through=through, availability_reference_date=DAY,
                           payload={'trusted_team_boards': {'frozen_team_state_by_team_id': captured}})
    verify_frozen_states(snap, binding)
    with pytest.raises(ValueError, match='no longer selected'):
        selection_receipt(league, 4, digest)
    with pytest.raises(ValueError, match='all 30'):
        selection_receipt(dict(league, teams=league['teams'][1:]), 5, digest)
    captured['111']['value']['public_state'] = 'vulnerable'
    with pytest.raises(ValueError, match='disagree for 111'):
        verify_frozen_states(snap, binding)
    del captured['111']
    with pytest.raises(ValueError, match='populations disagree'):
        verify_frozen_states(snap, binding)


def test_tonight_edition_keeps_its_workload_availability_and_slate_dates_distinct():
    from copy import deepcopy
    from scripts.verify_selected_delivery import verify_tonight_edition

    binding = {'data_through': '2026-10-28', 'availability_reference': '2026-10-29'}
    day = '2026-11-24'
    publication = {'dashboard_snapshot_id': 5847, 'sync_run_id': 98739,
                   'team_board_package_contract': 'trusted_team_board_publication_v1'}
    edition = {'baseball_date': day, 'data_through': binding['data_through'],
               'availability_reference_date': binding['availability_reference'], 'publication': publication}
    page = {'contract': 'tonight_v1', 'edition': edition, 'games': [], 'summary': {'game_count': 0}, 'quiet_day': True}
    verify_tonight_edition(page, (5847, 98739), binding, day)
    for key, wrong in [('availability_reference_date', day), ('data_through', day), ('baseball_date', '2026-10-29')]:
        changed = deepcopy(page)
        changed['edition'][key] = wrong
        with pytest.raises(ValueError):
            verify_tonight_edition(changed, (5847, 98739), binding, day)
    wrong_package = deepcopy(page)
    wrong_package['edition']['publication']['team_board_package_contract'] = None
    for changed in [wrong_package, dict(page, contract='other'), dict(page, quiet_day=False),
                    dict(page, summary={'game_count': 1}), dict(page, games=None)]:
        with pytest.raises(ValueError):
            verify_tonight_edition(changed, (5847, 98739), binding, day)
    cancelled = dict(page, quiet_day=False, games=[{'game_pk': 123, 'state': 'cancelled'}])
    verify_tonight_edition(cancelled, (5847, 98739), binding, day)


def test_played_day_verification_refuses_a_selection_for_another_slate():
    from types import SimpleNamespace
    from scripts.verify_selected_delivery import verify_delivery

    snapshot = SimpleNamespace(id=1, sync_run_id=2, availability_reference_date=DAY,
                               payload={'v3_rehearsal_selection': {'availability_reference': DAY.isoformat()}})
    with pytest.raises(ValueError, match='requested product day'):
        verify_delivery(None, snapshot, {'availability_reference': DAY.isoformat()}, product_day=date(2017, 8, 30))


def test_tonight_delivery_requires_exact_game_and_side_identity():
    from copy import deepcopy
    from scripts.verify_selected_delivery import compare_slate

    state = {'public_state': 'fresh'}
    game = dict(game_pk=101, game_number=1, first_pitch_utc='2017-08-29T23:00:00Z', state='scheduled',
                home=dict(team_id=111, team_state=state), away=dict(team_id=147, team_state=state))
    selected = dict(status='represented', selection_revision=5, generation='abc', data_through='2017-08-28',
                    availability_reference='2017-08-29', games=[game], league_changes=[])
    binding = dict(revision=5, generation='abc', data_through='2017-08-28', availability_reference='2017-08-29',
                   teams={'111': dict(state=state), '147': dict(state=state)})
    for side in ('away', 'home'):
        game[side].update(rest={}, workload_7d={}, multi_day_usage={}, rotation=None, key_arms=[], change_refs=[])
    assert compare_slate(selected, {'league_changes': [], 'games': [deepcopy(game)]}, binding) == {}
    changed = deepcopy(game)
    changed['home']['rest'] = None
    assert compare_slate(selected, {'league_changes': [], 'games': [changed]}, binding) == {
        'rest': [dict(game_pk=101, side='home', team_id=111)],
    }
    with pytest.raises(ValueError, match='Duplicate'):
        compare_slate(selected, {'league_changes': [], 'games': [game, game]}, binding)
    with pytest.raises(ValueError, match='inventory'):
        compare_slate(selected, {'league_changes': [], 'games': []}, binding)
    with pytest.raises(ValueError, match='home'):
        compare_slate(selected, {'league_changes': [], 'games': [dict(game, home=game['away'])]}, binding)
    with pytest.raises(ValueError, match='pinned'):
        compare_slate(dict(selected, selection_revision=4), {'league_changes': [], 'games': [game]}, binding)

    event = dict(change_id='one', team_id=111, source_ref='snapshot/1', headline='Recorded change')
    selected['league_changes'] = [event]
    game['home']['change_refs'] = ['one']
    assert compare_slate(selected, deepcopy(selected), binding) == {}
    served = deepcopy(selected)
    served['league_changes'][0]['headline'] = 'Different claim'
    assert set(compare_slate(selected, served, binding)) == {'change_contents'}
    served['games'][0]['away']['change_refs'] = ['one']
    with pytest.raises(ValueError, match='ordered club events'):
        compare_slate(selected, served, binding)
    selected['league_changes'].append(event)
    with pytest.raises(ValueError, match='unique identity'):
        compare_slate(selected, selected, binding)


def test_tonight_delivery_compares_league_changes_without_game_cards():
    from scripts.verify_selected_delivery import compare_slate

    binding = dict(revision=1, generation='abc', data_through='2017-08-28', availability_reference='2017-08-29')
    boston = dict(team_id=111, change_id='bos', source_ref='retained/bos', headline='Boston change')
    baltimore = dict(team_id=110, change_id='bal', source_ref='retained/bal', headline='Baltimore change')
    selected = dict(status='represented', selection_revision=1, generation='abc', data_through='2017-08-28',
                    availability_reference='2017-08-29', games=[], league_changes=[boston, baltimore])
    missing = compare_slate(selected, dict(selected, league_changes=[boston]), binding)
    assert missing['change_contents'] == [dict(team_id=110)]
    reordered = compare_slate(selected, dict(selected, league_changes=[baltimore, boston]), binding)
    assert reordered == {'league_change_order': dict(selected=[111, 110], served=[110, 111])}
    changed = compare_slate(selected, dict(selected, league_changes=[boston, dict(baltimore, headline='Different claim')]), binding)
    assert changed == {'change_contents': [dict(team_id=110)]}
    assert compare_slate(selected, dict(selected), binding) == {}
