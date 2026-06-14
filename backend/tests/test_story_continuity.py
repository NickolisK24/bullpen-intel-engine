from services.story_continuity import build_story_continuity_payload


def _team(team_id, name, available=3, monitor=0, restricted=0):
    return {
        'team_id': team_id,
        'team_name': name,
        'team_abbreviation': name[:3].upper(),
        'total_relievers': available + monitor + restricted,
        'available': available,
        'monitor': monitor,
        'restricted': restricted,
    }


def _payload(data_through, *, constrained=None, monitoring=None, available=None):
    return {
        'freshness': {'data_through': data_through},
        'landscape': {
            'constrained_bullpens': constrained or [],
            'monitoring_concentration': monitoring or [],
            'available_bullpens': available or [],
        },
    }


def _workload_payload(data_through, team_id=1, name='Padres'):
    return _payload(
        data_through,
        monitoring=[_team(team_id, name, available=2, monitor=5, restricted=0)],
    )


def _pressure_payload(data_through, team_id=1, name='Padres'):
    return _payload(
        data_through,
        constrained=[_team(team_id, name, available=2, monitor=1, restricted=4)],
    )


def test_no_prior_story_data_suppresses_continuity_items():
    current = _workload_payload('2026-06-12')

    payload = build_story_continuity_payload(current, [])

    assert payload['capability'] == 'homepage_story_continuity_v1'
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert payload['items'] == []
    assert payload['limitations'] == ['No prior briefing snapshots are available.']


def test_new_story_when_signature_is_absent_from_prior_briefings():
    current = _workload_payload('2026-06-12')
    prior = [_pressure_payload('2026-06-11', team_id=2, name='Guardians')]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['signature'] == 'team:1|theme:workload'
    assert item['status'] == 'new'
    assert item['label'] == 'New Story'
    assert item['description'] == 'First appearance in the morning briefing.'
    assert item['consecutive_days'] is None


def test_ongoing_story_counts_consecutive_briefing_days():
    current = _workload_payload('2026-06-12')
    prior = [
        _workload_payload('2026-06-11'),
        _workload_payload('2026-06-10'),
        _pressure_payload('2026-06-09'),
    ]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['status'] == 'ongoing'
    assert item['label'] == 'Ongoing Story'
    assert item['consecutive_days'] == 3
    assert item['description'] == 'Observed for 3 consecutive briefing days.'


def test_returning_story_when_signature_skips_the_previous_briefing():
    current = _workload_payload('2026-06-12')
    prior = [
        _pressure_payload('2026-06-11', team_id=2, name='Guardians'),
        _workload_payload('2026-06-10'),
    ]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['status'] == 'returning'
    assert item['label'] == 'Returning Story'
    assert item['consecutive_days'] is None
    assert item['description'] == 'Previously observed earlier in the lookback window.'


def test_does_not_overmatch_different_teams():
    current = _workload_payload('2026-06-12', team_id=1, name='Padres')
    prior = [_workload_payload('2026-06-11', team_id=2, name='Guardians')]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['signature'] == 'team:1|theme:workload'
    assert item['status'] == 'new'


def test_does_not_overmatch_different_story_themes_for_the_same_team():
    current = _workload_payload('2026-06-12', team_id=1, name='Padres')
    prior = [_pressure_payload('2026-06-11', team_id=1, name='Padres')]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['signature'] == 'team:1|theme:workload'
    assert item['status'] == 'new'
