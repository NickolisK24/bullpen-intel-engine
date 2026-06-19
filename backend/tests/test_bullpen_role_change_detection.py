import json

from services.bullpen_role_change_detection import (
    CAPABILITY,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_HISTORY,
    STATUS_UNAVAILABLE,
    build_role_change_detection_payload,
    has_role_change_detection_inputs,
)


def team_item(
    team_id=1,
    *,
    abbr='TST',
    capacity_state='healthy',
    resource_state='moderate',
    active=8,
    clean=5,
    anchor=1,
    leverage=4,
    trusted=1,
    trusted_group=None,
    top_available=1,
    trust_unavailable=0,
    trust_unavailable_pct=0,
    clean_trusted=None,
):
    trusted_group = (
        trusted_group
        if trusted_group is not None
        else anchor + leverage + trusted
    )
    item = {
        'team_id': team_id,
        'team_name': f'Team {team_id}',
        'team_abbreviation': abbr,
        'resource_health': {
            'resource_health_state': resource_state,
            'bullpen_capacity': {
                'capacity_state': capacity_state,
                'active_reliever_count': active,
                'clean_active_reliever_count': clean,
            },
        },
        'trust_hierarchy': {
            'anchor_count': anchor,
            'leverage_count': leverage,
            'trusted_count': trusted,
            'trusted_group_size': trusted_group,
            'top_trust_bucket_available_count': top_available,
            'hierarchy_confidence': 'high',
        },
        'trust_capacity_loss': {
            'trust_arms_available': max(trusted_group - trust_unavailable, 0),
            'trust_arms_unavailable': trust_unavailable,
            'trust_capacity_unavailable_pct': trust_unavailable_pct,
        },
    }
    if clean_trusted is not None:
        item['clean_trusted_options_count'] = clean_trusted
    return item


def payload(data_through='2026-06-19', teams=None, environments=None):
    teams = teams or [team_item()]
    environments = environments or {}
    return {
        'freshness': {'data_through': data_through},
        'capacity_intelligence': {
            'teams': teams,
            'by_team_id': {
                str(item['team_id']): item
                for item in teams
            },
        },
        'bullpen_environment': {
            'by_team_id': {
                str(key): value
                for key, value in environments.items()
            },
        },
    }


def change_types(result, team_id=1):
    team = result['by_team_id'][str(team_id)]
    return [item['type'] for item in team['changes']]


def first_change(result, change_type, team_id=1):
    team = result['by_team_id'][str(team_id)]
    return next(item for item in team['changes'] if item['type'] == change_type)


def test_insufficient_prior_history_returns_conservative_no_read():
    result = build_role_change_detection_payload(payload(), None)

    assert result['capability'] == CAPABILITY
    assert result['status'] == STATUS_INSUFFICIENT_HISTORY
    assert result['prior_date'] is None
    assert result['changes'] == []
    assert result['by_team_id']['1']['status'] == STATUS_INSUFFICIENT_HISTORY
    assert result['by_team_id']['1']['changes'] == []


def test_unavailable_without_current_payload():
    result = build_role_change_detection_payload(None, payload('2026-06-18'))

    assert result['status'] == STATUS_UNAVAILABLE
    assert result['teams'] == []
    assert result['changes'] == []
    assert result['teams_compared'] == 0


def test_prior_snapshot_without_comparable_team_intelligence_is_insufficient():
    current = payload('2026-06-19', [team_item(team_id=1)])
    prior = payload('2026-06-18', [team_item(team_id=2)])

    result = build_role_change_detection_payload(current, prior)

    assert result['status'] == STATUS_INSUFFICIENT_HISTORY
    assert result['teams_compared'] == 0
    assert result['by_team_id']['1']['status'] == STATUS_INSUFFICIENT_HISTORY
    assert result['by_team_id']['1']['changes'] == []


def test_comparable_input_detection_requires_date_and_capacity_intelligence():
    assert has_role_change_detection_inputs(payload()) is True
    assert has_role_change_detection_inputs({'freshness': {'data_through': '2026-06-19'}}) is False
    assert has_role_change_detection_inputs({
        'capacity_intelligence': {'teams': [team_item()]},
    }) is False


def test_unchanged_state_is_available_with_empty_changes():
    current = payload()
    prior = payload('2026-06-18')

    result = build_role_change_detection_payload(current, prior)

    assert result['status'] == STATUS_AVAILABLE
    assert result['teams_compared'] == 1
    assert result['by_team_id']['1']['status'] == STATUS_AVAILABLE
    assert result['by_team_id']['1']['changes'] == []
    assert result['change_count'] == 0


def test_capacity_resource_and_coverage_improvement_and_decline():
    prior = payload(
        '2026-06-18',
        [team_item(capacity_state='thin', resource_state='strained', clean=2, top_available=1)],
    )
    current = payload(
        '2026-06-19',
        [team_item(capacity_state='healthy', resource_state='moderate', clean=6, anchor=1, top_available=1)],
    )

    improved = build_role_change_detection_payload(current, prior)

    capacity = first_change(improved, 'capacity_state_change')
    resource = first_change(improved, 'resource_health_change')
    coverage = first_change(improved, 'coverage_safety_change')
    assert capacity['direction'] == 'improved'
    assert resource['direction'] == 'improved'
    assert coverage['direction'] == 'improved'
    assert coverage['summary'] == (
        'Coverage safety moved from Thin Coverage Safety to Strong Coverage Safety.'
    )

    declined = build_role_change_detection_payload(
        payload(
            '2026-06-20',
            [team_item(capacity_state='thin', resource_state='strained', clean=2, top_available=1)],
        ),
        current,
    )
    assert first_change(declined, 'capacity_state_change')['direction'] == 'declined'
    assert first_change(declined, 'resource_health_change')['direction'] == 'declined'
    assert first_change(declined, 'coverage_safety_change')['direction'] == 'declined'


def test_anchor_leverage_and_trusted_group_expansion_and_contraction():
    prior = payload(
        '2026-06-18',
        [team_item(anchor=0, leverage=2, trusted=1, trusted_group=3, top_available=2)],
    )
    current = payload(
        '2026-06-19',
        [team_item(anchor=1, leverage=4, trusted=2, trusted_group=7, top_available=1)],
    )

    expanded = build_role_change_detection_payload(current, prior)

    assert first_change(expanded, 'anchor_count_change')['direction'] == 'expanded'
    assert first_change(expanded, 'anchor_count_change')['severity'] == 'meaningful'
    assert first_change(expanded, 'anchor_count_change')['summary'] == 'Anchor emerged from 0 to 1.'
    assert first_change(expanded, 'leverage_count_change')['direction'] == 'expanded'
    assert first_change(expanded, 'trusted_group_change')['direction'] == 'expanded'

    contracted = build_role_change_detection_payload(
        payload(
            '2026-06-20',
            [team_item(anchor=0, leverage=2, trusted=1, trusted_group=3, top_available=2)],
        ),
        current,
    )
    assert first_change(contracted, 'anchor_count_change')['direction'] == 'contracted'
    assert first_change(contracted, 'anchor_count_change')['summary'] == 'Anchor lost from 1 to 0.'
    assert first_change(contracted, 'leverage_count_change')['direction'] == 'contracted'
    assert first_change(contracted, 'trusted_group_change')['direction'] == 'contracted'


def test_clean_trusted_options_and_trusted_unavailability_movement():
    prior = payload(
        '2026-06-18',
        [team_item(clean_trusted=1, trust_unavailable=2, trust_unavailable_pct=50)],
    )
    current = payload(
        '2026-06-19',
        [team_item(clean_trusted=3, trust_unavailable=0, trust_unavailable_pct=0)],
    )

    result = build_role_change_detection_payload(current, prior)

    clean_change = first_change(result, 'clean_trusted_options_change')
    unavailable_change = first_change(result, 'trusted_unavailability_change')
    assert clean_change['direction'] == 'expanded'
    assert clean_change['summary'] == 'Clean trusted options expanded from 1 to 3.'
    assert unavailable_change['direction'] == 'improved'
    assert unavailable_change['summary'] == 'Trusted unavailability improved from 2 to 0.'


def test_zero_clean_trusted_options_is_not_treated_as_missing():
    prior = payload('2026-06-18', [team_item(clean_trusted=0)])
    current = payload('2026-06-19', [team_item(clean_trusted=1)])

    result = build_role_change_detection_payload(current, prior)

    clean_change = first_change(result, 'clean_trusted_options_change')
    assert clean_change['evidence']['previous']['value'] == 0
    assert clean_change['evidence']['current']['value'] == 1


def test_deterministic_output_ordering():
    prior = payload(
        '2026-06-18',
        [
            team_item(
                capacity_state='thin',
                resource_state='strained',
                clean=2,
                anchor=0,
                leverage=2,
                trusted_group=3,
                clean_trusted=0,
                trust_unavailable=2,
                trust_unavailable_pct=50,
            ),
        ],
    )
    current = payload(
        '2026-06-19',
        [
            team_item(
                capacity_state='healthy',
                resource_state='moderate',
                clean=6,
                anchor=1,
                leverage=4,
                trusted_group=7,
                clean_trusted=2,
                trust_unavailable=0,
                trust_unavailable_pct=0,
            ),
        ],
    )

    result = build_role_change_detection_payload(current, prior)

    assert change_types(result) == [
        'capacity_state_change',
        'resource_health_change',
        'coverage_safety_change',
        'anchor_count_change',
        'leverage_count_change',
        'trusted_group_change',
        'clean_trusted_options_change',
        'trusted_unavailability_change',
    ]


def test_no_recommendation_fields_are_exposed():
    result = build_role_change_detection_payload(
        payload('2026-06-19', [team_item(anchor=2)]),
        payload('2026-06-18', [team_item(anchor=1)]),
    )

    encoded = json.dumps(result).lower()
    assert 'recommend' not in encoded
    assert 'should_pitch' not in encoded
    assert 'priority' not in encoded
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
