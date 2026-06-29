from services.story_selection_trace_v1 import (
    CAPABILITY,
    CONTEXT_SIGNAL_ACCURACY_REVIEW_SIGNALS,
    CONTEXT_SIGNAL_CLASSIFICATIONS,
    MISSING_BEAT_REVIEW_TARGETS,
    PATH_CANONICAL_DASHBOARD,
    PATH_DETERMINISTIC_EDITORIAL_CORPUS,
    PATH_FOUR_BEAT_AUDIT,
    PATH_HOME_TODAY,
    PATH_STORIES_PAGE,
    PATH_TEAM_PREVIEWS,
    PATH_TEAM_STORY_API,
    PATH_TODAY_LEAD_STORY,
    STORY_GENERATION_PATHS,
    build_story_selection_trace,
)
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
)

import test_story_editorial_regression_v1 as editorial


EXPECTED_DETERMINISTIC_DISTRIBUTION = {
    BEAT_AVAILABILITY_DEPTH: 4,
    BEAT_BRIDGE: 4,
    BEAT_COVERAGE_PRESSURE: 5,
    BEAT_DEPTH_CONSTRAINT: 4,
    BEAT_ROUTE_CHANGE: 4,
    BEAT_SUSTAINABILITY_QUESTION: 5,
    BEAT_TRUST_LANE: 4,
}

PRIOR_AUDIT_COLLAPSE_DISTRIBUTION = {
    BEAT_COVERAGE_PRESSURE: 1,
    BEAT_DEPTH_CONSTRAINT: 17,
    BEAT_ROUTE_CHANGE: 12,
    BEAT_SUSTAINABILITY_QUESTION: 0,
}


def _trace():
    return build_story_selection_trace(
        team_contexts=editorial._thirty_team_contexts(),
        as_of_date=editorial.DATE,
    )


def _format_distribution(distribution):
    counts = distribution['story_type_counts']
    rendered = ', '.join(f'{beat}={count}' for beat, count in counts.items() if count)
    return (
        f"story_count={distribution['story_count']}; "
        f"distinct={distribution['distinct_beat_count']}; "
        f"max={distribution['max_beat']}:{distribution['max_beat_count']} "
        f"({distribution['max_beat_share']:.1%}); "
        f"route+depth={distribution['route_depth_count']} "
        f"({distribution['route_depth_share']:.1%}); "
        f"counts={rendered}"
    )


def test_story_generation_paths_are_documented_and_distinct():
    paths = {path['path']: path for path in STORY_GENERATION_PATHS}

    assert {
        PATH_CANONICAL_DASHBOARD,
        PATH_STORIES_PAGE,
        PATH_HOME_TODAY,
        PATH_TEAM_STORY_API,
        PATH_TEAM_PREVIEWS,
        PATH_TODAY_LEAD_STORY,
        PATH_FOUR_BEAT_AUDIT,
        PATH_DETERMINISTIC_EDITORIAL_CORPUS,
    } <= set(paths)

    assert paths[PATH_CANONICAL_DASHBOARD]['selection_engine'] == 'story_intelligence_service_v1'
    assert paths[PATH_TEAM_STORY_API]['selection_engine'] == 'story_intelligence_service_v1'
    assert paths[PATH_STORIES_PAGE]['selection_engine'] == 'dashboard.stories'
    assert paths[PATH_HOME_TODAY]['selection_engine'] == 'dashboard.stories'
    assert paths[PATH_TEAM_PREVIEWS]['selection_engine'] == 'dashboard.stories'
    assert paths[PATH_TODAY_LEAD_STORY]['selection_engine'] == 'COIN story package selection'
    assert paths[PATH_FOUR_BEAT_AUDIT]['selection_engine'] == 'story_audit_preview_v1'


def test_selection_trace_explains_each_team_in_public_corpus():
    trace = _trace()

    assert trace['capability'] == CAPABILITY
    assert trace['source_engine'] == 'story_intelligence_service_v1'
    assert trace['public_contract'] == 'baseballos_canonical_story_v1'
    assert trace['multiple_selection_paths_present'] is True
    assert trace['team_count'] == 30
    assert len(trace['trace']) == 30

    for row in trace['trace']:
        assert row['team']['team_id']
        assert row['team']['team_name']
        assert row['selected_beat']
        assert row['selected_observation_type']
        assert row['selection_strength'] > 0
        assert row['selection_reasons']
        assert row['primary_inputs']
        assert row['candidate_count'] >= 1
        assert row['candidate_profiles']
        assert row['fallback_status']['fallback_used'] is False


def test_selection_trace_distribution_matches_deterministic_public_corpus():
    trace = _trace()
    distribution = trace['beat_distribution']
    editorial_distribution = editorial._beat_distribution(editorial._public_stories())

    assert distribution['story_type_counts'] == EXPECTED_DETERMINISTIC_DISTRIBUTION
    assert distribution['story_type_counts'] == editorial_distribution['counts']
    assert distribution['distinct_beat_count'] == 7
    assert distribution['max_beat_count'] == 5, _format_distribution(distribution)
    assert distribution['route_depth_count'] == 8, _format_distribution(distribution)


def test_selection_trace_reports_missing_beat_candidate_paths():
    trace = _trace()
    review = trace['missing_beat_evidence_review']

    assert set(review) == set(MISSING_BEAT_REVIEW_TARGETS)

    for beat in (BEAT_BRIDGE, BEAT_TRUST_LANE, BEAT_SUSTAINABILITY_QUESTION):
        row = review[beat]
        assert row['candidate_evidence_team_count'] >= 1
        assert row['eligible_candidate_team_count'] >= 1
        assert row['top_candidate_score'] is not None
        assert row['selected_team_count'] == EXPECTED_DETERMINISTIC_DISTRIBUTION[beat]
        assert len(row['teams']) == 30


def test_selection_trace_reports_context_signal_accuracy_review():
    trace = _trace()
    review = trace['context_signal_accuracy_review']

    assert set(review) == set(CONTEXT_SIGNAL_ACCURACY_REVIEW_SIGNALS)

    for signal, row in review.items():
        assert row['classification'] in CONTEXT_SIGNAL_CLASSIFICATIONS
        assert row['team_count'] == 30
        assert row['classification_counts']
        assert row['raw_value_counts']
        assert len(row['teams']) == 30
        assert row['teams'][0]['team']['team_id']
        assert row['teams'][0]['selected_beat']
        assert row['teams'][0]['classification'] in CONTEXT_SIGNAL_CLASSIFICATIONS
        assert row['teams'][0]['raw_values']


def test_selection_trace_reports_missing_beat_source_blockers():
    context = editorial._team_context(
        999,
        'Blocked Beat Club',
        'BBC',
    )

    trace = build_story_selection_trace(
        team_contexts=[context],
        as_of_date=editorial.DATE,
    )
    review = trace['missing_beat_evidence_review']

    assert review[BEAT_BRIDGE]['candidate_evidence_team_count'] == 0
    assert review[BEAT_BRIDGE]['eligible_candidate_team_count'] == 0
    assert review[BEAT_BRIDGE]['source_blocker_reason_counts']['no_starter_handoff_demand'] == 1
    assert 'late_core_not_settled' not in review[BEAT_BRIDGE]['source_blocker_reason_counts']

    assert review[BEAT_TRUST_LANE]['candidate_evidence_team_count'] == 0
    assert review[BEAT_TRUST_LANE]['eligible_candidate_team_count'] == 0
    assert (
        review[BEAT_TRUST_LANE]['source_blocker_reason_counts']
        ['insufficient_flagged_secondary_options']
        == 1
    )

    assert review[BEAT_SUSTAINABILITY_QUESTION]['candidate_evidence_team_count'] == 0
    assert review[BEAT_SUSTAINABILITY_QUESTION]['eligible_candidate_team_count'] == 0
    assert (
        review[BEAT_SUSTAINABILITY_QUESTION]['source_blocker_reason_counts']
        ['no_concentration_pressure_observation']
        == 1
    )

    accuracy = trace['context_signal_accuracy_review']
    starter = accuracy['starter_handoff_demand']['teams'][0]
    assert starter['blocker_reasons'] == ['no_starter_handoff_demand']
    assert starter['raw_values'] == {
        'rotation_context_available': True,
        'early_bullpen_entry_rate': 12.0,
        'bullpen_coverage_ip_7d': 3.0,
    }

    available = accuracy['available_arms_counts']['teams'][0]
    assert available['raw_values'] == {
        'optionality_context_available': True,
        'available_arms_count': 4,
    }


def test_context_signal_accuracy_review_flags_impossible_core_band():
    context = editorial._team_context(
        1000,
        'Impossible Core Club',
        'ICC',
        stability={
            'stability_band': 'stable',
            'core_retention_count': 1,
            'core_stability_pct': 33,
            'core_change_count': 2,
            'current_core_size': 3,
            'previous_core_size': 3,
        },
    )

    trace = build_story_selection_trace(
        team_contexts=[context],
        as_of_date=editorial.DATE,
    )
    review = trace['context_signal_accuracy_review']['stable_late_core_detection']

    assert review['classification'] == 'likely_incorrect'
    assert review['classification_counts'] == {'likely_incorrect': 1}
    assert review['teams'][0]['raw_values'] == {
        'stability_band': 'stable',
        'core_retention_count': 1,
        'core_stability_pct': 33,
        'core_change_count': 2,
        'current_core_size': 3,
        'previous_core_size': 3,
    }


def test_prior_audit_collapse_is_not_reproduced_by_current_public_trace():
    distribution = _trace()['beat_distribution']

    assert distribution['story_type_counts'] != {
        **EXPECTED_DETERMINISTIC_DISTRIBUTION,
        **PRIOR_AUDIT_COLLAPSE_DISTRIBUTION,
    }
    assert distribution['story_type_counts'][BEAT_DEPTH_CONSTRAINT] != 17
    assert distribution['story_type_counts'][BEAT_ROUTE_CHANGE] != 12
    assert distribution['story_type_counts'][BEAT_COVERAGE_PRESSURE] != 1
    assert distribution['story_type_counts'][BEAT_SUSTAINABILITY_QUESTION] != 0
    assert distribution['distinct_beat_count'] >= 3, _format_distribution(distribution)
    assert distribution['route_depth_share'] <= 0.80, _format_distribution(distribution)
