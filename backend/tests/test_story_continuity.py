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


def _payload(data_through, *, constrained=None, monitoring=None, available=None, flagship_story=None):
    payload = {
        'freshness': {'data_through': data_through},
        'landscape': {
            'constrained_bullpens': constrained or [],
            'monitoring_concentration': monitoring or [],
            'available_bullpens': available or [],
        },
    }
    if flagship_story is not None:
        payload['flagship_story'] = flagship_story
    return payload


def _flagship_story(team_id=1, name='Padres', story_kind='team_workload_continuity'):
    theme_by_kind = {
        'team_pressure': 'pressure',
        'team_workload_continuity': 'workload',
        'team_recovery': 'recovery',
        'league_check_in': 'quiet',
    }
    story = {
        'story_kind': story_kind,
        'theme': theme_by_kind[story_kind],
    }
    if team_id is not None:
        story.update({
            'team_id': team_id,
            'team_name': name,
            'team_abbreviation': name[:3].upper(),
        })
    return story


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


def _mixed_landscape_payload(data_through, *, flagship_story=None):
    return _payload(
        data_through,
        constrained=[_team(1, 'Padres', available=4, monitor=0, restricted=1)],
        monitoring=[_team(2, 'Guardians', available=2, monitor=5, restricted=0)],
        available=[_team(3, 'Mets', available=7, monitor=1, restricted=0)],
        flagship_story=flagship_story,
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


def test_continuity_matches_visible_flagship_metadata_when_available():
    current = _mixed_landscape_payload(
        '2026-06-12',
        flagship_story=_flagship_story(3, 'Mets', 'team_recovery'),
    )
    prior = [
        _mixed_landscape_payload(
            '2026-06-11',
            flagship_story=_flagship_story(3, 'Mets', 'team_recovery'),
        )
    ]

    payload = build_story_continuity_payload(current, prior)

    assert len(payload['items']) == 1
    item = payload['items'][0]
    assert item['signature'] == 'team:3|theme:recovery'
    assert item['story_kind'] == 'team_recovery'
    assert item['status'] == 'ongoing'
    assert item['consecutive_days'] == 2


def test_unusable_flagship_metadata_falls_back_to_landscape_selection():
    current = _mixed_landscape_payload(
        '2026-06-12',
        flagship_story={'story_kind': 'team_recovery', 'theme': 'recovery'},
    )
    prior = [_workload_payload('2026-06-11', team_id=2, name='Guardians')]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['signature'] == 'team:2|theme:workload'
    assert item['story_kind'] == 'team_workload_continuity'
    assert item['status'] == 'ongoing'


def test_first_landscape_candidate_does_not_override_valid_flagship_candidate():
    current = _mixed_landscape_payload(
        '2026-06-12',
        flagship_story=_flagship_story(3, 'Mets', 'team_recovery'),
    )
    prior = [
        _mixed_landscape_payload(
            '2026-06-11',
            flagship_story=_flagship_story(3, 'Mets', 'team_recovery'),
        )
    ]

    payload = build_story_continuity_payload(current, prior)

    signatures = [item['signature'] for item in payload['items']]
    assert signatures == ['team:3|theme:recovery']
    assert 'team:1|theme:pressure' not in signatures


def test_prior_flagship_metadata_prevents_landscape_candidate_overmatch():
    current = _payload(
        '2026-06-12',
        monitoring=[_team(2, 'Guardians', available=2, monitor=5, restricted=0)],
        flagship_story=_flagship_story(2, 'Guardians', 'team_workload_continuity'),
    )
    prior = [
        _payload(
            '2026-06-11',
            monitoring=[_team(2, 'Guardians', available=2, monitor=5, restricted=0)],
            flagship_story=_flagship_story(2, 'Guardians', 'team_pressure'),
        )
    ]

    payload = build_story_continuity_payload(current, prior)

    item = payload['items'][0]
    assert item['signature'] == 'team:2|theme:workload'
    assert item['status'] == 'new'


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
    # Count includes the current briefing day plus two matching prior days.
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
