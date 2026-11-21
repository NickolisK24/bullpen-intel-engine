from datetime import date

import pytest

from sync_v3.product_reads import _historical_availability


def _side():
    arms = {}
    for pid, status in enumerate(('Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable'), start=1):
        arms[str(pid)] = dict(reason=None, read=dict(last_workload='2024-08-07', games_compared=[7000 + pid],
                              availability=dict(data_state='fresh', availability_status=status)))
    return dict(team=137, competition=dict(team_id=137, status='active', reference_date='2024-08-08'),
                arms=arms, mode='retrospective_candidate', current_serving_eligible=False, team_state={'available':True},
                reason=None, membership_date='2024-08-07', reference_date='2024-08-08')


def _compare(facts, identities=None):
    if identities is None:
        identities = {int(pid): dict(team_id=137, public_id=None) for pid in facts['arms']}
    return _historical_availability(facts, identities, date(2024, 8, 7), date(2024, 8, 8))


def test_complete_historical_population_folds_both_restricted_statuses():
    assert _compare(_side()) == dict(available=1, on_watch=1, limited=1, unavailable=2)


@pytest.mark.parametrize(('path', 'value'), [
    (('reference_date',), '2024-08-09'), (('membership_date',), '2024-08-06'),
    (('competition', 'status'), 'season_complete'), (('competition', 'team_id'), 111),
    (('arms', '3', 'read', 'last_workload'), '2024-08-08'), (('arms', '3', 'read', 'last_workload'), '2024-01-01'),
    (('arms', '3', 'read', 'games_compared'), []),
    (('arms', '3', 'read', 'availability', 'availability_status'), 'unknown'),
    (('arms', '3', 'read', 'availability', 'data_state'), 'stale'),
])
def test_one_unqualified_arm_or_club_date_withholds_population(path, value):
    facts = _side()
    target = facts
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value
    assert _compare(facts) is None


def test_missing_or_conflicting_active_roster_membership_withholds_population():
    facts = _side()
    identities = {int(pid): dict(team_id=137) for pid in facts['arms']}
    del identities[2]
    assert _compare(facts, identities) is None
    identities[2] = dict(team_id=111)
    assert _compare(facts, identities) is None
