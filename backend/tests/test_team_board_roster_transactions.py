"""TB-08 publication projection keeps events separate from present membership."""

from copy import deepcopy

from services.public_recent_transactions import CAPABILITY
from services.team_board_roster_transactions import (
    CONTRACT, author_frozen_roster_transactions,
)


def _source(status='available'):
    return {
        'capability': CAPABILITY, 'population_basis': 'qualified_events',
        'status': status, 'window_start_date': '2026-08-11',
        'window_end_date': '2026-08-18', 'represented_date': '2026-08-18',
        'limitations': [],
        'events': [
            {'event_id': 'option', 'player_id': 7, 'player_name': 'Arm Seven',
             'date': '2026-08-12', 'label': 'Optioned', 'direction': 'removal'},
            {'event_id': 'recall', 'player_id': 7, 'player_name': 'Arm Seven',
             'date': '2026-08-17', 'label': 'Recalled', 'direction': 'addition'},
            {'event_id': 'il', 'player_id': 8, 'player_name': 'Arm Eight',
             'date': '2026-08-16', 'label': 'Placed on injured list', 'direction': 'removal'},
        ],
    }


def _carrier(source=None, records=None, active_ids=None, overview=None):
    return author_frozen_roster_transactions(
        113, data_through='2026-08-18',
        transaction_read=source if source is not None else _source(),
        records=records if records is not None else [
            {'pitcher_id': 7, 'roster_status': {'is_active_mlb': True, 'label': 'Active'}},
            {'pitcher_id': 8, 'roster_status': {'is_inactive_context': True, 'label': '15-day IL'}},
        ],
        active_pitcher_ids=active_ids if active_ids is not None else [7],
        workload_overview=overview if overview is not None else {
            'concentration_7_day': {
                'status': 'complete', 'contributors': [
                    {'pitcher_id': 8, 'name': 'Arm Eight', 'current_active': False},
                    {'pitcher_id': 7, 'name': 'Arm Seven', 'current_active': True},
                ],
            },
        },
        team_board_package_contract='trusted_team_board_publication_v1',
    )


def test_current_roster_wins_over_older_option_and_recent_recall():
    carrier = _carrier()
    assert carrier['contract'] == CONTRACT
    assert carrier['current_group']['active_pitcher_ids'] == [7]
    assert [event['event_id'] for event in carrier['events']] == ['option', 'recall', 'il']
    assert [event['current_roster']['membership'] for event in carrier['events']] == [
        'active', 'active', 'off_active',
    ]
    assert carrier['events'][2]['current_roster']['label'] == '15-day IL'
    assert carrier['off_active_recent_contributors']['contributors'] == [
        {'pitcher_id': 8, 'name': 'Arm Eight', 'current_roster': {
            'status': 'complete', 'membership': 'off_active', 'label': '15-day IL',
        }},
    ]


def test_unverified_and_missing_roster_facts_never_become_current_truth():
    source = _source('partial')
    source['events'] = source['events'][:1]
    source['limitations'] = ['Some source events withheld.']
    carrier = _carrier(source, records=[], active_ids=[], overview={})
    assert carrier['status'] == 'partial'
    assert carrier['events'][0]['current_roster']['status'] == 'unavailable'
    assert carrier['events'][0]['current_roster']['membership'] is None
    assert carrier['off_active_recent_contributors']['status'] == 'unavailable'
    assert carrier['off_active_recent_contributors']['contributors'] == []
    assert carrier['limitations'] == ['Some source events withheld.']
    source['limitations'].append('Later mutation')
    assert carrier['limitations'] == ['Some source events withheld.']


def test_explicit_nonactive_roster_status_is_off_active_without_inactive_subtype():
    carrier = _carrier(records=[
        {'pitcher_id': 8, 'roster_status': {
            'is_active_mlb': False, 'is_inactive_context': False,
            'label': 'Off active roster',
        }},
    ], active_ids=[])
    assert carrier['events'][2]['current_roster'] == {
        'status': 'complete', 'membership': 'off_active', 'label': 'Off active roster',
    }


def test_off_active_history_never_changes_active_group_or_appearance_ownership():
    source = _source()
    source['events'] = [deepcopy(source['events'][0])]
    source['events'][0]['player_id'] = 99
    carrier = _carrier(source, records=[], active_ids=[7])
    assert carrier['current_group']['active_pitcher_ids'] == [7]
    assert carrier['events'][0]['current_roster']['membership'] is None
    assert 'appearance_team_id' not in str(carrier)
