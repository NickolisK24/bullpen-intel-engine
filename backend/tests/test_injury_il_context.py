from types import SimpleNamespace

from services.injury_il_context import build_injury_il_context_from_contexts
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_BEREAVEMENT,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_OPTIONED,
    STATUS_PATERNITY,
    STATUS_RESTRICTED,
    STATUS_SUSPENDED,
    STATUS_UNKNOWN,
)


def _context(
    name,
    team_id,
    status,
    mlb_id=None,
    team_name=None,
    eligible=True,
):
    return {
        'pitcher': SimpleNamespace(
            id=mlb_id or team_id * 100,
            mlb_id=mlb_id or team_id * 100,
            full_name=name,
            team_id=team_id,
            team_name=team_name or f'Team {team_id}',
        ),
        'roster_status': {
            'status': status,
            'label': status.replace('_', '-').title(),
        },
        'eligibility': {
            'eligible': eligible,
        },
    }


def test_injured_list_statuses_count_as_injured_list():
    payload = build_injury_il_context_from_contexts([
        _context('IL Fifteen Arm', 1, STATUS_IL_15),
        _context('IL Sixty Arm', 2, STATUS_IL_60),
        _context('Active Arm', 3, STATUS_ACTIVE),
    ])

    assert payload['league']['injured_list_count'] == 2
    assert payload['league']['inactive_count'] == 0
    assert payload['league']['tracked_pitchers_count'] == 3


def test_optioned_minors_and_not_activated_count_as_inactive_roster():
    payload = build_injury_il_context_from_contexts([
        _context('Optioned Arm', 1, STATUS_OPTIONED),
        _context('Minors Arm', 1, STATUS_MINORS),
        _context('Forty Man Arm', 2, STATUS_40_MAN_ONLY),
    ])

    assert payload['league']['injured_list_count'] == 0
    assert payload['league']['inactive_count'] == 3


def test_real_inactive_statuses_count_as_inactive_roster():
    payload = build_injury_il_context_from_contexts([
        _context('Bereavement Arm', 1, STATUS_BEREAVEMENT),
        _context('Paternity Arm', 1, STATUS_PATERNITY),
        _context('Suspended Arm', 2, STATUS_SUSPENDED),
        _context('Restricted Arm', 2, STATUS_RESTRICTED),
    ])

    assert payload['league']['injured_list_count'] == 0
    assert payload['league']['inactive_count'] == 4


def test_active_and_unknown_statuses_do_not_inflate_unavailable_counts():
    payload = build_injury_il_context_from_contexts([
        _context('Active Rested Arm', 1, STATUS_ACTIVE),
        _context('Unknown Arm', 1, STATUS_UNKNOWN),
        {'pitcher': SimpleNamespace(id=303, mlb_id=303, full_name='Missing Status Arm', team_id=3, team_name='Team 3')},
    ])

    assert payload['league']['injured_list_count'] == 0
    assert payload['league']['inactive_count'] == 0
    assert payload['league']['tracked_pitchers_count'] == 3


def test_league_totals_and_multiple_unavailable_team_count_are_deterministic():
    payload = build_injury_il_context_from_contexts([
        _context('Team One Minors', 1, STATUS_MINORS),
        _context('Team One IL', 1, STATUS_IL_15),
        _context('Team Two Optioned', 2, STATUS_OPTIONED),
        _context('Team Three Active', 3, STATUS_ACTIVE),
    ])

    league = payload['league']
    assert league['injured_list_count'] == 1
    assert league['inactive_count'] == 2
    assert league['teams_with_multiple_unavailable'] == 1
    assert league['tracked_pitchers_count'] == 4


def test_population_count_uses_dashboard_bullpen_population_not_context_count():
    payload = build_injury_il_context_from_contexts(
        [
            _context('Visible Dashboard Arm', 1, STATUS_ACTIVE),
            _context('Team One IL', 1, STATUS_IL_15),
            _context('Team One Optioned', 1, STATUS_OPTIONED),
            _context('Team Two IL', 2, STATUS_IL_15),
        ],
        bullpen_population_count=1,
        team_ids={1},
    )

    league = payload['league']
    assert league['population_scope'] == 'dashboard_bullpen_population'
    assert league['bullpen_population_count'] == 1
    assert league['tracked_pitchers_count'] == 1
    assert league['injured_list_count'] == 1
    assert league['inactive_count'] == 1
    assert league['teams_with_multiple_unavailable'] == 1


def test_empty_dashboard_team_filter_does_not_count_other_populations():
    payload = build_injury_il_context_from_contexts(
        [
            _context('Team One IL', 1, STATUS_IL_15),
            _context('Team Two Optioned', 2, STATUS_OPTIONED),
        ],
        bullpen_population_count=0,
        team_ids=set(),
    )

    league = payload['league']
    assert league['bullpen_population_count'] == 0
    assert league['tracked_pitchers_count'] == 0
    assert league['injured_list_count'] == 0
    assert league['inactive_count'] == 0
    assert league['teams_with_multiple_unavailable'] == 0


def test_non_bullpen_contexts_do_not_inflate_injury_context_counts():
    payload = build_injury_il_context_from_contexts([
        _context('Bullpen IL Arm', 1, STATUS_IL_15, eligible=True),
        _context('Non Bullpen IL Arm', 1, STATUS_IL_15, eligible=False),
    ])

    assert payload['league']['injured_list_count'] == 1


def test_followed_team_payload_is_limited_to_requested_team():
    payload = build_injury_il_context_from_contexts(
        [
            _context('Other IL Arm', 1, STATUS_IL_15, team_name='Other Club'),
            _context('Followed IL Arm', 2, STATUS_IL_15, team_name='Followed Club'),
            _context('Followed Optioned Arm', 2, STATUS_OPTIONED, team_name='Followed Club'),
        ],
        followed_team_id=2,
    )

    followed = payload['followed_team']
    assert followed['team_id'] == 2
    assert followed['team_name'] == 'Followed Club'
    assert followed['injured_list_count'] == 1
    assert followed['inactive_count'] == 1
    assert [arm['name'] for arm in followed['unavailable_pitchers']] == [
        'Followed IL Arm',
        'Followed Optioned Arm',
    ]


def test_injury_il_context_does_not_enable_ranking_or_prediction():
    payload = build_injury_il_context_from_contexts([
        _context('IL Arm', 1, STATUS_IL_15),
    ])

    assert payload['ranking_applied'] is False
    assert payload['prediction_applied'] is False
    assert payload['selection_made'] is False
