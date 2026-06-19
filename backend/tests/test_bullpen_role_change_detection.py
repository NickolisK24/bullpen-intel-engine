import json

import pytest

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
    coverage_label=None,
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
    if coverage_label is not None:
        item['coverage_safety'] = {'label': coverage_label}
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


def assert_safe_change(change, *, change_type, direction, severity, previous, current):
    assert change['type'] == change_type
    assert change['direction'] == direction
    assert change['severity'] == severity
    assert isinstance(change['summary'], str)
    assert change['summary']
    assert 'recommend' not in change['summary'].lower()
    assert 'should pitch' not in change['summary'].lower()
    assert change['evidence']['previous']['value'] == previous
    assert change['evidence']['current']['value'] == current


def assert_single_synthetic_change(
    *,
    previous_item,
    current_item,
    change_type,
    direction,
    severity,
    previous,
    current,
):
    result = build_role_change_detection_payload(
        payload('2026-06-19', [current_item]),
        payload('2026-06-18', [previous_item]),
    )
    team = result['by_team_id']['1']
    assert result['status'] == STATUS_AVAILABLE
    assert result['teams_compared'] == 1
    assert [item['type'] for item in team['changes']] == [change_type]
    assert_safe_change(
        team['changes'][0],
        change_type=change_type,
        direction=direction,
        severity=severity,
        previous=previous,
        current=current,
    )
    return result


STABLE_LABEL = 'Stable Coverage Safety'
THIN_LABEL = 'Thin Coverage Safety'


@pytest.mark.parametrize('name,previous_item,current_item,change_type,direction,severity,previous,current', [
    (
        'capacity decline',
        team_item(capacity_state='healthy', coverage_label=STABLE_LABEL),
        team_item(capacity_state='reduced', coverage_label=STABLE_LABEL),
        'capacity_state_change',
        'declined',
        'meaningful',
        'healthy',
        'reduced',
    ),
    (
        'capacity improvement',
        team_item(capacity_state='thin', coverage_label=STABLE_LABEL),
        team_item(capacity_state='reduced', coverage_label=STABLE_LABEL),
        'capacity_state_change',
        'improved',
        'meaningful',
        'thin',
        'reduced',
    ),
    (
        'resource health decline',
        team_item(resource_state='moderate', coverage_label=STABLE_LABEL),
        team_item(resource_state='strained', coverage_label=STABLE_LABEL),
        'resource_health_change',
        'declined',
        'meaningful',
        'moderate',
        'strained',
    ),
    (
        'resource health improvement',
        team_item(resource_state='strained', coverage_label=STABLE_LABEL),
        team_item(resource_state='moderate', coverage_label=STABLE_LABEL),
        'resource_health_change',
        'improved',
        'meaningful',
        'strained',
        'moderate',
    ),
    (
        'coverage safety decline',
        team_item(coverage_label=STABLE_LABEL),
        team_item(coverage_label=THIN_LABEL),
        'coverage_safety_change',
        'declined',
        'meaningful',
        STABLE_LABEL,
        THIN_LABEL,
    ),
    (
        'coverage safety improvement',
        team_item(coverage_label=THIN_LABEL),
        team_item(coverage_label=STABLE_LABEL),
        'coverage_safety_change',
        'improved',
        'meaningful',
        THIN_LABEL,
        STABLE_LABEL,
    ),
    (
        'anchor lost',
        team_item(anchor=1, trusted_group=7, coverage_label=STABLE_LABEL),
        team_item(anchor=0, trusted_group=7, coverage_label=STABLE_LABEL),
        'anchor_count_change',
        'contracted',
        'meaningful',
        1,
        0,
    ),
    (
        'anchor emerged',
        team_item(anchor=0, trusted_group=7, coverage_label=STABLE_LABEL),
        team_item(anchor=1, trusted_group=7, coverage_label=STABLE_LABEL),
        'anchor_count_change',
        'expanded',
        'meaningful',
        0,
        1,
    ),
    (
        'leverage group contracted',
        team_item(leverage=7, trusted_group=8, coverage_label=STABLE_LABEL),
        team_item(leverage=5, trusted_group=8, coverage_label=STABLE_LABEL),
        'leverage_count_change',
        'contracted',
        'meaningful',
        7,
        5,
    ),
    (
        'leverage group expanded',
        team_item(leverage=4, trusted_group=8, coverage_label=STABLE_LABEL),
        team_item(leverage=6, trusted_group=8, coverage_label=STABLE_LABEL),
        'leverage_count_change',
        'expanded',
        'meaningful',
        4,
        6,
    ),
    (
        'trusted group contracted',
        team_item(trusted_group=8, coverage_label=STABLE_LABEL),
        team_item(trusted_group=6, coverage_label=STABLE_LABEL),
        'trusted_group_change',
        'contracted',
        'meaningful',
        8,
        6,
    ),
    (
        'trusted group expanded',
        team_item(trusted_group=5, coverage_label=STABLE_LABEL),
        team_item(trusted_group=7, coverage_label=STABLE_LABEL),
        'trusted_group_change',
        'expanded',
        'meaningful',
        5,
        7,
    ),
    (
        'clean trusted options decreased',
        team_item(clean_trusted=5, coverage_label=STABLE_LABEL),
        team_item(clean_trusted=3, coverage_label=STABLE_LABEL),
        'clean_trusted_options_change',
        'contracted',
        'meaningful',
        5,
        3,
    ),
    (
        'clean trusted options increased',
        team_item(clean_trusted=3, coverage_label=STABLE_LABEL),
        team_item(clean_trusted=5, coverage_label=STABLE_LABEL),
        'clean_trusted_options_change',
        'expanded',
        'meaningful',
        3,
        5,
    ),
    (
        'trusted unavailability worsened',
        team_item(trust_unavailable=1, coverage_label=STABLE_LABEL),
        team_item(trust_unavailable=3, coverage_label=STABLE_LABEL),
        'trusted_unavailability_change',
        'declined',
        'meaningful',
        1,
        3,
    ),
    (
        'trusted unavailability improved',
        team_item(trust_unavailable=3, coverage_label=STABLE_LABEL),
        team_item(trust_unavailable=1, coverage_label=STABLE_LABEL),
        'trusted_unavailability_change',
        'improved',
        'meaningful',
        3,
        1,
    ),
])
def test_synthetic_role_change_scenarios_emit_single_safe_change(
    name,
    previous_item,
    current_item,
    change_type,
    direction,
    severity,
    previous,
    current,
):
    result = assert_single_synthetic_change(
        previous_item=previous_item,
        current_item=current_item,
        change_type=change_type,
        direction=direction,
        severity=severity,
        previous=previous,
        current=current,
    )
    encoded = json.dumps(result).lower()
    assert 'recommend' not in encoded
    assert 'should_pitch' not in encoded
    assert 'priority' not in encoded
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False


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
    second = build_role_change_detection_payload(current, prior)

    assert result == second
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
