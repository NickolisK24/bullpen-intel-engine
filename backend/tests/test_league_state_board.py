from types import SimpleNamespace

from services.league_state_board import build_league_state_board


def _record(team_id, status):
    return {
        'pitcher': SimpleNamespace(team_id=team_id),
        'availability': {'availability_status': status},
    }


def test_league_board_groups_every_team_once_and_fails_closed():
    teams = [
        {'team_id': 2, 'team_name': 'Beta', 'team_abbreviation': 'BET'},
        {'team_id': 1, 'team_name': 'Alpha', 'team_abbreviation': 'ALP'},
        {'team_id': 3, 'team_name': 'Gamma', 'team_abbreviation': 'GAM'},
    ]
    states = {
        1: {'available': True, 'public_state': 'fresh', 'public_label': 'Fresh'},
        2: {'available': True, 'public_state': 'stretched', 'public_label': 'Stretched'},
        3: {'available': False, 'outcome': 'data_limited'},
    }
    payload = build_league_state_board(
        teams=teams,
        records=[_record(1, 'Available'), _record(1, 'Monitor'), _record(2, 'Limited')],
        team_state_for_team=states.__getitem__,
        freshness={'data_through': '2026-08-13'},
    )

    assert payload['group_order'] == ['fresh', 'stretched', 'vulnerable', 'withheld']
    assert payload['teams_expected'] == 3
    assert payload['teams_in_current_state'] == 2
    assert payload['teams_withheld'] == 1
    flattened = [team for group in payload['groups'] for team in group['teams']]
    assert [team['team_id'] for team in flattened] == [1, 2, 3]
    assert len({team['team_id'] for team in flattened}) == 3
    assert flattened[0]['clean_option_count'] == 1
    assert flattened[0]['active_read_count'] == 2
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False


def test_unsupported_available_state_is_withheld_not_invented():
    payload = build_league_state_board(
        teams=[{'team_id': 1, 'team_name': 'Alpha', 'team_abbreviation': 'ALP'}],
        records=[],
        team_state_for_team=lambda _team_id: {
            'available': True,
            'public_state': 'watch',
            'public_label': 'Watch',
        },
    )

    assert payload['teams_in_current_state'] == 0
    assert payload['groups'][-1]['teams'][0]['team_state']['public_state'] == 'watch'
