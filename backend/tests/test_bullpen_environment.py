from services.bullpen_environment import (
    FLAG_HEAVY_CHURN,
    FLAG_LIMITED_READ_INPUTS,
    FLAG_MODERATE_CHURN,
    FLAG_SOURCE_LIMITATIONS,
    FLAG_TRUST_CAPACITY_LOSS,
    SOURCE_CAPACITY,
    SOURCE_ROTATION,
    SOURCE_STABILITY,
    STATUS_LIMITED,
    STATUS_MULTI_SOURCE,
    STATUS_PRESSURE,
    STATUS_STABLE,
    build_league_bullpen_environment_payload,
    build_team_bullpen_environment,
)


ROTATION_SOURCE_LIMITATION = (
    'Rotation support uses currently assigned pitchers because game logs do not yet store team-at-appearance.'
)
ROTATION_OPENER_LIMITATION = (
    'Opener/bulk and bullpen games are classified by game shape: an opener is not '
    'counted as a rotation start, and bulk-follower innings are tracked separately '
    'rather than as rotation-driven bullpen pressure.'
)
STABILITY_USAGE_LIMITATION = (
    'Bullpen stability uses usage patterns and roster status only; roster-move data is not used.'
)
STABILITY_SOURCE_LIMITATION = (
    'Bullpen stability uses currently assigned pitchers because game logs do not yet store team-at-appearance.'
)


def capacity(status='clear', unavailable_pct=0, trust_status='clear', trust_unavailable_pct=0, limitations=None):
    return {
        'capability': 'bullpen_capacity_intelligence_v1',
        'source': 'backend',
        'team_id': 1,
        'team_name': 'Test Team',
        'team_abbreviation': 'TST',
        'capacity_loss': {
            'status': status,
            'unavailable_capacity_pct': unavailable_pct,
            'summary': 'capacity summary',
            'definitions': {},
            'limitations': list(limitations or []),
        },
        'trust_capacity_loss': {
            'status': trust_status,
            'trust_capacity_unavailable_pct': trust_unavailable_pct,
            'summary': 'trust summary',
            'definitions': {},
            'limitations': [],
        },
    }


def rotation(status='neutral', limitations=None, source_limitations=None):
    return {
        'capability': 'rotation_support_pressure_v1',
        'source': 'backend',
        'team_id': 1,
        'team_name': 'Test Team',
        'team_abbreviation': 'TST',
        'status': status,
        'short_start_rate': 0.0 if status in {'neutral', 'supportive'} else 0.67,
        'summary': 'rotation summary',
        'definitions': {},
        'limitations': list(limitations or []),
        'source_limitations': list(source_limitations or [
            ROTATION_SOURCE_LIMITATION,
            ROTATION_OPENER_LIMITATION,
        ]),
    }


def stability(status='stable', limitations=None, source_limitations=None):
    return {
        'capability': 'bullpen_stability_v1',
        'source': 'backend',
        'team_id': 1,
        'team_name': 'Test Team',
        'team_abbreviation': 'TST',
        'status': status,
        'new_or_reintroduced_arm_count': 0 if status == 'stable' else 2,
        'summary': 'stability summary',
        'definitions': {},
        'limitations': list(limitations or []),
        'source_limitations': list(source_limitations or [
            STABILITY_USAGE_LIMITATION,
            STABILITY_SOURCE_LIMITATION,
        ]),
    }


def environment(cap=None, rot=None, stab=None):
    return build_team_bullpen_environment(
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
        capacity_intelligence=capacity() if cap is None else cap,
        rotation_support_pressure=rotation() if rot is None else rot,
        bullpen_stability=stability() if stab is None else stab,
    )


def test_stable_environment_has_no_primary_pressure_sources():
    result = environment()

    assert result['status'] == STATUS_STABLE
    assert result['primary_pressure_sources'] == []
    assert result['supporting_reads']['capacity_loss_status'] == 'clear'
    assert result['supporting_reads']['rotation_support_status'] == 'neutral'
    assert result['supporting_reads']['bullpen_stability_status'] == 'stable'
    assert FLAG_SOURCE_LIMITATIONS in result['context_flags']
    assert 'does not order teams' in result['definitions']['primary_pressure_sources']


def test_single_capacity_pressure_source_reads_pressure_with_context():
    result = environment(cap=capacity(status='elevated', unavailable_pct=25))

    assert result['status'] == STATUS_PRESSURE
    assert result['primary_pressure_sources'] == [SOURCE_CAPACITY]
    assert result['supporting_reads']['capacity_unavailable_pct'] == 25
    assert 'unavailable capacity' in result['summary']


def test_multi_source_pressure_from_capacity_and_rotation_with_churn_context():
    result = environment(
        cap=capacity(status='elevated', unavailable_pct=32),
        rot=rotation(status='heavy_pressure'),
        stab=stability(status='moderate_churn'),
    )

    assert result['status'] == STATUS_MULTI_SOURCE
    assert result['primary_pressure_sources'] == [SOURCE_CAPACITY, SOURCE_ROTATION]
    assert FLAG_MODERATE_CHURN in result['context_flags']
    assert 'short-start workload' in result['summary']


def test_heavy_churn_is_an_explicit_primary_pressure_source():
    result = environment(stab=stability(status='heavy_churn'))

    assert result['status'] == STATUS_PRESSURE
    assert result['primary_pressure_sources'] == [SOURCE_STABILITY]
    assert FLAG_HEAVY_CHURN in result['context_flags']
    assert 'heavy churn' in result['summary']


def test_trust_capacity_loss_is_context_not_primary_pressure_source():
    result = environment(cap=capacity(trust_status='constrained', trust_unavailable_pct=50))

    assert result['status'] == STATUS_PRESSURE
    assert result['primary_pressure_sources'] == []
    assert FLAG_TRUST_CAPACITY_LOSS in result['context_flags']
    assert result['supporting_reads']['trust_capacity_unavailable_pct'] == 50


def test_limited_read_inputs_do_not_create_pressure_sources():
    result = environment(
        cap=capacity(status='limited_read', unavailable_pct=0),
        rot=rotation(status='supportive'),
        stab=stability(status='stable'),
    )

    assert result['status'] == STATUS_LIMITED
    assert result['primary_pressure_sources'] == []
    assert result['limited_layers'] == [SOURCE_CAPACITY]
    assert FLAG_LIMITED_READ_INPUTS in result['context_flags']
    assert any('limited' in limitation.lower() for limitation in result['limitations'])


def test_missing_inputs_produce_limited_read_without_inventing_pressure():
    result = environment(cap={})

    assert result['status'] == STATUS_LIMITED
    assert result['primary_pressure_sources'] == []
    assert result['missing_layers'] == [SOURCE_CAPACITY]
    assert FLAG_LIMITED_READ_INPUTS in result['context_flags']


def test_underlying_limitations_and_source_limitations_are_preserved():
    result = environment(
        cap=capacity(status='elevated', unavailable_pct=25, limitations=['capacity limitation']),
        rot=rotation(status='moderate_pressure', limitations=['rotation limitation']),
        stab=stability(status='stable', limitations=['stability limitation']),
    )

    assert 'capacity limitation' in result['limitations']
    assert 'rotation limitation' in result['limitations']
    assert 'stability limitation' in result['limitations']
    assert ROTATION_SOURCE_LIMITATION in result['source_limitations']
    assert ROTATION_OPENER_LIMITATION in result['source_limitations']
    assert STABILITY_USAGE_LIMITATION in result['source_limitations']
    assert STABILITY_SOURCE_LIMITATION in result['source_limitations']


def test_payload_language_avoids_predictions_recommendations_rankings_and_betting():
    result = environment(
        cap=capacity(status='elevated', unavailable_pct=25),
        rot=rotation(status='heavy_pressure'),
        stab=stability(status='moderate_churn'),
    )

    text = str(result).lower()
    for forbidden in ('prediction', 'predict', 'rank', 'recommend', 'recommended', 'betting', 'odds'):
        assert forbidden not in text


def test_league_payload_indexes_team_items_without_ranking():
    team = environment(cap=capacity(status='elevated', unavailable_pct=25))
    result = build_league_bullpen_environment_payload([team])

    assert result['capability'] == 'league_bullpen_environment_v1'
    assert result['source'] == 'backend'
    assert result['teams_evaluated'] == 1
    assert result['by_team_id']['1'] == team
