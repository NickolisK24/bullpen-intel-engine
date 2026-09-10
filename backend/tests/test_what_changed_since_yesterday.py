import json

import pytest

from services.what_changed_since_yesterday import (
    CAPABILITY,
    CHANGE_COVERAGE_SAFETY,
    CHANGE_IDENTITY,
    CHANGE_RESOURCE_HEALTH,
    CHANGE_RESTED_OPTIONS,
    CHANGE_TRUST_STRUCTURE,
    CHANGE_USABLE_DEPTH,
    REASON_COMPARISON_WITHHELD,
    REASON_CURRENT_SLATE_COVERAGE_MISSING,
    REASON_CURRENT_SLATE_INCOMPLETE,
    REASON_CURRENT_SNAPSHOT_UNTRUSTED,
    REASON_DATA_THROUGH_MISSING,
    REASON_NO_PRIOR_SNAPSHOT,
    REASON_PRIOR_SLATE_COVERAGE_MISSING,
    REASON_PRIOR_SLATE_INCOMPLETE,
    REASON_PRIOR_SNAPSHOT_UNPUBLISHED,
    REASON_SNAPSHOTS_NOT_COMPARABLE,
    REASON_VALIDATIONS_FAILED,
    STATE_CHANGES_DETECTED,
    STATE_INSUFFICIENT_CONTEXT,
    STATE_NO_MEANINGFUL_CHANGES,
    STATUS_AVAILABLE,
    STATUS_INSUFFICIENT_CONTEXT,
    build_team_what_changed_since_yesterday,
    build_what_changed_since_yesterday_payload,
)


def snapshot(
    *,
    team_id=1,
    team_name='Test Team',
    team_abbreviation='TST',
    capacity_state='reduced',
    resource_state='moderate',
    active=7,
    clean=4,
    trusted_group=4,
    anchor=1,
    leverage=2,
    trusted=1,
    coverage_label='Stable Coverage Safety',
    identity_key='flexible_distribution',
    identity_label='Flexible Distribution Bullpen',
    identity_confidence='medium',
    resource_confidence='high',
    hierarchy_confidence='high',
):
    return {
        'capability': 'bullpen_capacity_intelligence_v1',
        'version': 'test',
        'source': 'backend',
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'resource_health': {
            'confidence': resource_confidence,
            'capacity_state': capacity_state,
            'resource_health_state': resource_state,
            'bullpen_capacity': {
                'capacity_state': capacity_state,
                'active_reliever_count': active,
                'clean_active_reliever_count': clean,
            },
            'organizational_resource_health': {
                'resource_health_state': resource_state,
            },
        },
        'trust_hierarchy': {
            'anchor_count': anchor,
            'leverage_count': leverage,
            'trusted_count': trusted,
            'depth_count': 1,
            'unknown_count': 0,
            'trusted_group_size': trusted_group,
            'top_trust_bucket_available_count': 1,
            'hierarchy_confidence': hierarchy_confidence,
            'limitations': [],
        },
        'trust_capacity_loss': {
            'trust_arms_unavailable': 0,
            'trust_capacity_unavailable_pct': 0,
        },
        'coverage_safety': {
            'label': coverage_label,
        },
        'bullpen_identity': {
            'identity_key': identity_key,
            'identity_label': identity_label,
            'confidence': identity_confidence,
        },
    }


def slate_coverage(
    slate_date,
    *,
    complete=True,
    coverage_known=True,
    validations_passed=True,
):
    return {
        'slate_date': slate_date,
        'coverage_known': coverage_known,
        'games_scheduled': 1,
        'games_final': 1,
        'games_fully_ingested': 1 if complete else 0,
        'games_incomplete': 0 if complete else 1,
        'complete_enough_to_publish': complete,
        'validations_passed': validations_passed,
        'reason_codes': ['slate_complete'] if complete and validations_passed else ['slate_incomplete'],
    }


def dashboard_payload(
    items,
    *,
    data_through='2026-06-19',
    include_slate_coverage=True,
    complete=True,
    coverage_known=True,
    validations_passed=True,
):
    freshness = {
        'data_through': data_through,
        'availability_reference_date': data_through,
    }
    if include_slate_coverage:
        freshness['slate_coverage'] = slate_coverage(
            data_through,
            complete=complete,
            coverage_known=coverage_known,
            validations_passed=validations_passed,
        )
    return {
        'freshness': freshness,
        'capacity_intelligence': {
            'teams': items,
            'by_team_id': {str(item['team_id']): item for item in items},
        },
    }


def current_metadata(data_through='2026-06-19', *, trusted=True):
    return {
        'source': 'live_dashboard_build',
        'trusted_current_payload': trusted,
        'data_through': data_through,
    }


def prior_metadata(data_through='2026-06-18', *, published=True, status='ready'):
    return {
        'source': 'dashboard_snapshot',
        'snapshot_id': 18,
        'status': status,
        'is_published': published,
        'data_through': data_through,
    }


def trusted_comparison(current, prior, *, current_meta=None, prior_meta=None):
    return build_what_changed_since_yesterday_payload(
        current,
        prior,
        require_trusted_snapshots=True,
        current_snapshot_metadata=current_meta if current_meta is not None else current_metadata(),
        prior_snapshot_metadata=prior_meta if prior_meta is not None else prior_metadata(),
    )


def assert_withheld(result, *reason_codes):
    assert result['status'] == STATUS_INSUFFICIENT_CONTEXT
    assert result['state'] == STATE_INSUFFICIENT_CONTEXT
    assert result['change_count'] == 0
    assert result['changes'] == []
    assert result['teams_compared'] == 0
    assert REASON_COMPARISON_WITHHELD in result['reason_codes']
    for reason_code in reason_codes:
        assert reason_code in result['reason_codes']


def first_change(payload, change_type):
    for change in payload['changes']:
        if change['change_type'] == change_type:
            return change
    raise AssertionError(f'Missing change type: {change_type}')


def test_capacity_increase_detects_rested_options_growth():
    prior = snapshot(clean=2, active=7)
    current = snapshot(clean=5, active=7)

    result = build_team_what_changed_since_yesterday(current, prior)
    change = first_change(result, CHANGE_RESTED_OPTIONS)

    assert result['state'] == STATE_CHANGES_DETECTED
    assert change['change_direction'] == 'increased'
    assert change['significance'] == 'meaningful'
    assert change['change_summary'] == 'Rested options increased from 2 to 5.'
    assert change['supporting_facts'][0]['previous_value'] == 2
    assert change['supporting_facts'][0]['current_value'] == 5


def test_capacity_decrease_detects_usable_depth_loss():
    prior = snapshot(active=8, clean=4)
    current = snapshot(active=5, clean=4)

    result = build_team_what_changed_since_yesterday(current, prior)
    change = first_change(result, CHANGE_USABLE_DEPTH)

    assert change['change_direction'] == 'decreased'
    assert change['change_summary'] == 'Usable bullpen depth decreased from 8 to 5.'


def test_resource_health_change_detects_improvement_and_worsening():
    improved = build_team_what_changed_since_yesterday(
        snapshot(resource_state='strong'),
        snapshot(resource_state='strained'),
    )
    worsened = build_team_what_changed_since_yesterday(
        snapshot(resource_state='strained'),
        snapshot(resource_state='moderate'),
    )

    assert first_change(improved, CHANGE_RESOURCE_HEALTH)['change_direction'] == 'improved'
    assert first_change(worsened, CHANGE_RESOURCE_HEALTH)['change_direction'] == 'worsened'


def test_coverage_improvement_detects_thin_to_stable():
    result = build_team_what_changed_since_yesterday(
        snapshot(coverage_label='Stable Coverage Safety'),
        snapshot(coverage_label='Thin Coverage Safety'),
    )
    change = first_change(result, CHANGE_COVERAGE_SAFETY)

    assert change['change_direction'] == 'improved'
    assert change['significance'] == 'structural'
    assert change['change_summary'] == (
        'Coverage safety improved from Thin Coverage Safety to Stable Coverage Safety.'
    )


def test_coverage_decline_detects_stable_to_thin():
    result = build_team_what_changed_since_yesterday(
        snapshot(coverage_label='Thin Coverage Safety'),
        snapshot(coverage_label='Stable Coverage Safety'),
    )
    change = first_change(result, CHANGE_COVERAGE_SAFETY)

    assert change['change_direction'] == 'worsened'
    assert change['change_summary'] == (
        'Coverage safety worsened from Stable Coverage Safety to Thin Coverage Safety.'
    )


def test_trust_expansion_detects_material_trusted_group_growth():
    result = build_team_what_changed_since_yesterday(
        snapshot(trusted_group=5, anchor=1, leverage=3, trusted=1),
        snapshot(trusted_group=2, anchor=1, leverage=1, trusted=0),
    )
    change = first_change(result, CHANGE_TRUST_STRUCTURE)

    assert change['change_direction'] == 'expanded'
    assert change['change_summary'] == 'Trusted group expanded from 2 to 5.'


def test_trust_contraction_detects_material_trusted_group_narrowing():
    result = build_team_what_changed_since_yesterday(
        snapshot(trusted_group=2, anchor=1, leverage=1, trusted=0),
        snapshot(trusted_group=5, anchor=1, leverage=3, trusted=1),
    )
    change = first_change(result, CHANGE_TRUST_STRUCTURE)

    assert change['change_direction'] == 'narrowed'
    assert change['change_summary'] == 'Trusted group narrowed from 5 to 2.'


def test_identity_change_detects_structural_identity_movement():
    prior = snapshot(
        identity_key='flexible_distribution',
        identity_label='Flexible Distribution Bullpen',
    )
    current = snapshot(
        identity_key='resource_strained',
        identity_label='Resource-Strained Bullpen',
    )

    result = build_team_what_changed_since_yesterday(current, prior)
    change = first_change(result, CHANGE_IDENTITY)

    assert change['change_direction'] == 'changed'
    assert change['significance'] == 'structural'
    assert change['change_summary'] == (
        'Bullpen identity changed from Flexible Distribution Bullpen to Resource-Strained Bullpen.'
    )


def test_tiny_fluctuations_with_same_structure_do_not_emit_changes():
    result = build_team_what_changed_since_yesterday(
        snapshot(clean=5, active=8, trusted_group=4),
        snapshot(clean=4, active=7, trusted_group=4),
    )

    assert result['state'] == STATE_NO_MEANINGFUL_CHANGES
    assert result['changes'] == []
    assert result['change_count'] == 0


def test_league_payload_compares_teams_without_ranking_semantics():
    current = {
        'freshness': {'data_through': '2026-06-19'},
        'capacity_intelligence': {
            'teams': [
                snapshot(team_id=2, team_abbreviation='BBB', clean=5),
                snapshot(team_id=1, team_abbreviation='AAA', coverage_label='Stable Coverage Safety'),
            ],
        },
    }
    prior = {
        'freshness': {'data_through': '2026-06-18'},
        'capacity_intelligence': {
            'teams': [
                snapshot(team_id=2, team_abbreviation='BBB', clean=2),
                snapshot(team_id=1, team_abbreviation='AAA', coverage_label='Thin Coverage Safety'),
            ],
        },
    }

    result = build_what_changed_since_yesterday_payload(current, prior)

    assert result['capability'] == CAPABILITY
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False
    assert [team['team_abbreviation'] for team in result['teams']] == ['AAA', 'BBB']
    assert result['change_count'] == 2


def test_trusted_gate_allows_complete_published_comparable_snapshots():
    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
    )

    assert result['status'] == STATUS_AVAILABLE
    assert result['reason_codes'] == []
    assert result['change_count'] == 1
    assert first_change(result, CHANGE_RESTED_OPTIONS)['change_direction'] == 'increased'


def test_trusted_gate_withholds_missing_prior_snapshot():
    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        None,
        prior_meta=None,
    )

    assert_withheld(result, REASON_NO_PRIOR_SNAPSHOT)


def test_trusted_gate_withholds_unpublished_prior_snapshot():
    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
        prior_meta=prior_metadata(published=False),
    )

    assert_withheld(result, REASON_PRIOR_SNAPSHOT_UNPUBLISHED)


def test_trusted_gate_allows_rotated_prior_with_was_published_proof():
    # A prior-date snapshot rotated out of the served slot by a newer same-date
    # publish keeps is_published False but carries durable publication proof.
    rotated_prior = prior_metadata(published=False)
    rotated_prior['was_published'] = True

    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
        prior_meta=rotated_prior,
    )

    assert result['status'] == STATUS_AVAILABLE
    assert result['reason_codes'] == []
    assert first_change(result, CHANGE_RESTED_OPTIONS)['change_direction'] == 'increased'


def test_trusted_gate_allows_rotated_prior_proven_by_published_at():
    rotated_prior = prior_metadata(published=False)
    rotated_prior['published_at'] = '2026-06-18T09:15:00'

    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
        prior_meta=rotated_prior,
    )

    assert result['status'] == STATUS_AVAILABLE
    assert result['reason_codes'] == []


def test_trusted_gate_still_withholds_nonadjacent_prior_with_publication_proof():
    # Durable publication proof must never soften strict date adjacency: a real
    # off-day gap stays fail-closed even when the prior snapshot was published.
    rotated_prior = prior_metadata(data_through='2026-06-15', published=False)
    rotated_prior['was_published'] = True

    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-15'),
        prior_meta=rotated_prior,
    )

    assert_withheld(result, REASON_SNAPSHOTS_NOT_COMPARABLE)


def test_trusted_gate_withholds_prior_missing_slate_coverage():
    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload(
            [snapshot(clean=2)],
            data_through='2026-06-18',
            include_slate_coverage=False,
        ),
    )

    assert_withheld(result, REASON_PRIOR_SLATE_COVERAGE_MISSING)


def test_trusted_gate_withholds_prior_incomplete_or_failed_validations():
    incomplete = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18', complete=False),
    )
    failed_validation = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload(
            [snapshot(clean=2)],
            data_through='2026-06-18',
            validations_passed=False,
        ),
    )

    assert_withheld(incomplete, REASON_PRIOR_SLATE_INCOMPLETE)
    assert_withheld(
        failed_validation,
        REASON_PRIOR_SLATE_INCOMPLETE,
        REASON_VALIDATIONS_FAILED,
    )


def test_trusted_gate_withholds_prior_missing_data_through():
    prior = dashboard_payload([snapshot(clean=2)], data_through='2026-06-18')
    prior['freshness'].pop('data_through')
    prior['freshness'].pop('availability_reference_date')

    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        prior,
        prior_meta=prior_metadata(data_through=None),
    )

    assert_withheld(result, REASON_DATA_THROUGH_MISSING)


def test_trusted_gate_withholds_current_missing_slate_coverage():
    result = trusted_comparison(
        dashboard_payload(
            [snapshot(clean=5)],
            data_through='2026-06-19',
            include_slate_coverage=False,
        ),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
    )

    assert_withheld(result, REASON_CURRENT_SLATE_COVERAGE_MISSING)


def test_trusted_gate_withholds_current_missing_data_through():
    current = dashboard_payload([snapshot(clean=5)], data_through='2026-06-19')
    current['freshness'].pop('data_through')
    current['freshness'].pop('availability_reference_date')

    result = trusted_comparison(
        current,
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
        current_meta=current_metadata(data_through=None),
    )

    assert_withheld(result, REASON_DATA_THROUGH_MISSING)


def test_trusted_gate_withholds_current_incomplete_or_failed_validations():
    incomplete = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19', complete=False),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
    )
    failed_validation = trusted_comparison(
        dashboard_payload(
            [snapshot(clean=5)],
            data_through='2026-06-19',
            validations_passed=False,
        ),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
    )

    assert_withheld(incomplete, REASON_CURRENT_SLATE_INCOMPLETE)
    assert_withheld(
        failed_validation,
        REASON_CURRENT_SLATE_INCOMPLETE,
        REASON_VALIDATIONS_FAILED,
    )


def test_trusted_gate_withholds_untrusted_current_payload():
    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through='2026-06-18'),
        current_meta=current_metadata(trusted=False),
    )

    assert_withheld(result, REASON_CURRENT_SNAPSHOT_UNTRUSTED)


@pytest.mark.parametrize('prior_date', ['2026-06-19', '2026-06-17'])
def test_trusted_gate_withholds_non_comparable_baseline_dates(prior_date):
    result = trusted_comparison(
        dashboard_payload([snapshot(clean=5)], data_through='2026-06-19'),
        dashboard_payload([snapshot(clean=2)], data_through=prior_date),
        prior_meta=prior_metadata(data_through=prior_date),
    )

    assert_withheld(result, REASON_SNAPSHOTS_NOT_COMPARABLE)


def test_governance_safety_no_recommendation_prediction_ranking_or_score_leakage():
    result = build_what_changed_since_yesterday_payload(
        {
            'freshness': {'data_through': '2026-06-19'},
            'capacity_intelligence': {'teams': [snapshot(clean=5)]},
        },
        {
            'freshness': {'data_through': '2026-06-18'},
            'capacity_intelligence': {'teams': [snapshot(clean=2)]},
        },
    )

    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False

    allowed_keys = {'ranking_applied', 'selection_made', 'prediction_applied'}
    blocked_text = (
        'recommend',
        'projected',
        'expected',
        'bet',
        'best reliever',
        'should use',
        'must use',
    )

    def visit(value, path=()):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered_key = key.lower()
                if key not in allowed_keys:
                    assert 'score' not in lowered_key, '.'.join((*path, key))
                    assert 'rank' not in lowered_key, '.'.join((*path, key))
                    assert 'recommend' not in lowered_key, '.'.join((*path, key))
                    assert 'prediction' not in lowered_key, '.'.join((*path, key))
                visit(child, (*path, key))
            return
        if isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, (*path, str(index)))
            return
        if isinstance(value, str):
            lowered = value.lower()
            assert 'score' not in lowered
            for blocked in blocked_text:
                assert blocked not in lowered

    visit(result)
    encoded = json.dumps({
        key: value
        for key, value in result.items()
        if key not in allowed_keys
    }).lower()
    assert 'score' not in encoded
    assert 'recommend' not in encoded
