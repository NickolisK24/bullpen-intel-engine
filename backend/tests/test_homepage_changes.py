from services.homepage_changes import build_homepage_changes_payload


def _payload(data_through, entries, story_context=None, continuity=None):
    return {
        'freshness': {
            'data_through': data_through,
        },
        'landscape': {
            'constrained_bullpens': entries.get('constrained_bullpens', []),
            'monitoring_concentration': entries.get('monitoring_concentration', []),
            'available_bullpens': entries.get('available_bullpens', []),
        },
        'story_context': story_context or {'teams': {}},
        'continuity': continuity or {'teams': {}},
    }


def _team(team_id, name, available, monitor, restricted):
    return {
        'team_id': team_id,
        'team_name': name,
        'team_abbreviation': name[:3].upper(),
        'total_relievers': available + monitor + restricted,
        'available': available,
        'monitor': monitor,
        'restricted': restricted,
    }


def test_homepage_changes_compare_dashboard_windows_without_new_surface_flags():
    previous = _payload('2026-06-04', {
        'monitoring_concentration': [
            _team(1, 'Padres', available=2, monitor=4, restricted=0),
            _team(2, 'Guardians', available=2, monitor=2, restricted=1),
            _team(3, 'Mets', available=3, monitor=3, restricted=2),
        ],
    })
    current = _payload('2026-06-05', {
        'monitoring_concentration': [
            _team(1, 'Padres', available=1, monitor=6, restricted=0),
            _team(2, 'Guardians', available=4, monitor=1, restricted=0),
            _team(3, 'Mets', available=4, monitor=1, restricted=1),
        ],
    })

    payload = build_homepage_changes_payload(current, previous)

    assert payload['capability'] == 'homepage_bullpen_changes_v1'
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert payload['comparison'] == {
        'current_data_through': '2026-06-05',
        'previous_data_through': '2026-06-04',
    }
    assert [item['team_name'] for item in payload['items']] == [
        'Padres',
        'Mets',
        'Guardians',
    ]
    assert payload['items'][0]['change'] == 'Watch-list arms increased from 4 to 6.'
    assert payload['items'][0]['why_changed'] == (
        'More relievers now sit in the watch-list workload band than in the prior window.'
    )
    assert 'snapshot' not in str(payload).lower()


def test_homepage_changes_use_existing_story_context_as_the_why():
    previous = _payload('2026-06-04', {
        'monitoring_concentration': [
            _team(1, 'Padres', available=2, monitor=4, restricted=0),
        ],
    })
    current = _payload(
        '2026-06-05',
        {
            'monitoring_concentration': [
                _team(1, 'Padres', available=1, monitor=6, restricted=0),
            ],
        },
        story_context={
            'teams': {
                '1': {
                    'by_type': {
                        'usage_demand': {
                            'context_note': (
                                'Recent short starts have increased pressure on the middle innings.'
                            ),
                        },
                    },
                },
            },
        },
    )

    payload = build_homepage_changes_payload(current, previous)

    assert payload['items'][0]['why_changed'] == (
        'Recent short starts have increased pressure on the middle innings.'
    )


def test_homepage_changes_hide_without_prior_window_or_team_movement():
    current = _payload('2026-06-05', {
        'monitoring_concentration': [
            _team(1, 'Padres', available=2, monitor=4, restricted=0),
        ],
    })
    same = _payload('2026-06-05', {
        'monitoring_concentration': [
            _team(1, 'Padres', available=2, monitor=4, restricted=0),
        ],
    })
    previous = _payload('2026-06-04', {
        'monitoring_concentration': [
            _team(1, 'Padres', available=2, monitor=4, restricted=0),
        ],
    })

    assert build_homepage_changes_payload(current, None)['items'] == []
    assert build_homepage_changes_payload(current, same)['items'] == []
    assert build_homepage_changes_payload(current, previous)['items'] == []
