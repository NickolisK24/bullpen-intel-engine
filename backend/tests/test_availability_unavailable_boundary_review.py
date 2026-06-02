from datetime import date

from services.availability import (
    STATUS_AVOID,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    THRESHOLDS,
)
from services.availability_unavailable_boundary_review import (
    REVIEW_NEUTRAL,
    REVIEW_SUPPORTS,
    boundary_sensitivity,
    build_review,
    candidate_c,
    moved_boundary_cases,
    review_category,
    transition_counts,
)


def _record(pitcher_id, name, status, inputs, reasons=None):
    return {
        'pitcher_id': pitcher_id,
        'pitcher_name': name,
        'team': 'TST',
        'availability': {
            'availability_status': status,
            'confidence': 'high',
            'data_state': 'fresh',
            'reasons': reasons or [],
            'limitations': [],
            'inputs': inputs,
        },
    }


def _inputs(pitches_last_3_days, *, fatigue_score=40, pitches_yesterday=0, appearances_last_5_days=1):
    return {
        'fatigue_score': fatigue_score,
        'pitches_yesterday': pitches_yesterday,
        'pitches_last_3_days': pitches_last_3_days,
        'pitches_last_5_days': pitches_last_3_days,
        'appearances_last_3_days': 1,
        'appearances_last_5_days': appearances_last_5_days,
        'days_rest': 1,
    }


def test_candidate_c_only_raises_three_day_unavailable_threshold():
    candidate = candidate_c()

    assert THRESHOLDS.unavailable_pitches_last_3_days == 80
    assert candidate.thresholds.unavailable_pitches_last_3_days == 90
    assert candidate.thresholds.avoid_pitches_last_3_days == THRESHOLDS.avoid_pitches_last_3_days


def test_moved_boundary_cases_extracts_unavailable_to_avoid_transition():
    inputs = _inputs(85)
    baseline = [
        _record(1, 'Moved Pitcher', STATUS_UNAVAILABLE, inputs, reasons=['85 pitches in 3 days']),
        _record(2, 'Still Unavailable', STATUS_UNAVAILABLE, _inputs(90), reasons=['90 pitches in 3 days']),
        _record(3, 'Stable Monitor', STATUS_MONITOR, _inputs(20)),
    ]
    proposed = [
        _record(1, 'Moved Pitcher', STATUS_AVOID, inputs, reasons=['85 pitches in 3 days']),
        baseline[1],
        baseline[2],
    ]

    cases = moved_boundary_cases(baseline, proposed)

    assert len(cases) == 1
    assert cases[0]['pitcher_name'] == 'Moved Pitcher'
    assert cases[0]['original_status'] == STATUS_UNAVAILABLE
    assert cases[0]['candidate_status'] == STATUS_AVOID
    assert cases[0]['pitches_last_3_days'] == 85
    assert cases[0]['baseline_severe_signals'] == ['85 pitches in 3 days']
    assert cases[0]['candidate_severe_signals'] == []


def test_transition_counts_identifies_candidate_changes():
    moved_inputs = _inputs(85)
    baseline = [
        _record(1, 'Moved Pitcher', STATUS_UNAVAILABLE, moved_inputs),
        _record(2, 'Still Unavailable', STATUS_UNAVAILABLE, _inputs(90)),
        _record(3, 'Stable Monitor', STATUS_MONITOR, _inputs(20)),
    ]
    proposed = [
        _record(1, 'Moved Pitcher', STATUS_AVOID, moved_inputs),
        baseline[1],
        baseline[2],
    ]

    transitions = transition_counts(baseline, proposed)

    assert transitions['Unavailable -> Avoid'] == 1
    assert transitions['Unavailable -> Unavailable'] == 1
    assert transitions['Monitor -> Monitor'] == 1


def test_boundary_sensitivity_counts_three_day_pitch_values():
    moved_inputs = _inputs(85)
    baseline = [
        _record(1, 'Moved Pitcher', STATUS_UNAVAILABLE, moved_inputs),
        _record(2, 'Still Unavailable', STATUS_UNAVAILABLE, _inputs(90)),
        _record(3, 'Stable Monitor', STATUS_MONITOR, _inputs(20)),
    ]
    proposed = [
        _record(1, 'Moved Pitcher', STATUS_AVOID, moved_inputs),
        baseline[1],
        baseline[2],
    ]

    sensitivity = {
        row['pitches_last_3_days']: row
        for row in boundary_sensitivity(baseline, proposed, lower=85, upper=90)
    }

    assert sensitivity[85]['moved_unavailable_to_avoid'] == 1
    assert sensitivity[85]['candidate_avoid'] == 1
    assert sensitivity[90]['candidate_unavailable'] == 1
    assert sensitivity[90]['moved_unavailable_to_avoid'] == 0


def test_build_review_summarizes_moved_boundary_cases():
    moved_inputs = _inputs(85)
    baseline = [
        _record(1, 'Moved Pitcher', STATUS_UNAVAILABLE, moved_inputs),
        _record(2, 'Still Unavailable', STATUS_UNAVAILABLE, _inputs(90)),
    ]
    proposed = [
        _record(1, 'Moved Pitcher', STATUS_AVOID, moved_inputs),
        baseline[1],
    ]

    review = build_review(baseline, proposed, reference_date=date(2026, 6, 1))

    assert review['total_moved'] == 1
    assert review['baseline_unavailable'] == 2
    assert review['percent_unavailable_affected'] == 50.0
    assert review['recommendation_category'] == REVIEW_SUPPORTS
    assert review['distribution_analysis']['pitches_last_3_days_min'] == 85
    assert review['distribution_analysis']['pitches_last_3_days_max'] == 85


def test_review_category_is_neutral_when_no_pitchers_move():
    analysis = {
        'pitches_last_3_days_min': None,
        'pitches_last_3_days_max': None,
        'candidate_severe_signal_count_distribution': {},
    }

    assert review_category(analysis, total_moved=0) == REVIEW_NEUTRAL
