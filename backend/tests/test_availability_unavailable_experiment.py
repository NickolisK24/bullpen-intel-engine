from dataclasses import dataclass
from datetime import date, timedelta

from services.availability import (
    CONFIDENCE_LOW,
    STATUS_AVOID,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    THRESHOLDS,
)
from services.availability_unavailable_experiment import (
    UnavailableCandidate,
    classify_for_candidate,
    compare_records,
    unavailable_candidates,
    unavailable_severe_signals,
)


@dataclass
class ScoreStub:
    raw_score: float
    risk_level: str = 'LOW'


def _candidate(key):
    return next(candidate for candidate in unavailable_candidates() if candidate.key == key)


def _baseline_candidate():
    return UnavailableCandidate(
        key='baseline',
        label='Baseline',
        changed_rule='Current thresholds',
        thresholds=THRESHOLDS,
    )


def _record(pitcher_id, name, status, inputs, reasons=None, data_state='fresh', confidence='high'):
    return {
        'pitcher_id': pitcher_id,
        'pitcher_name': name,
        'team': 'TST',
        'availability': {
            'availability_status': status,
            'confidence': confidence,
            'data_state': data_state,
            'reasons': reasons or [],
            'limitations': [],
            'inputs': inputs,
        },
    }


def test_baseline_candidate_preserves_current_unavailable_outcome(make_log):
    ref = date(2026, 6, 1)
    logs = [
        make_log(ref, pitches_thrown=30),
        make_log(ref - timedelta(days=1), pitches_thrown=30),
        make_log(ref - timedelta(days=2), pitches_thrown=25),
    ]

    result = classify_for_candidate(
        score=ScoreStub(raw_score=20.0),
        game_logs=logs,
        reference_date=ref,
        latest_game_date=ref,
        candidate=_baseline_candidate(),
    )

    assert result['availability_status'] == STATUS_UNAVAILABLE
    assert result['inputs']['pitches_last_3_days'] == 85


def test_three_day_candidate_changes_only_intended_unavailable_behavior(make_log):
    ref = date(2026, 6, 1)
    candidate = _candidate('raise_three_day_90')
    logs = [
        make_log(ref, pitches_thrown=30),
        make_log(ref - timedelta(days=1), pitches_thrown=30),
        make_log(ref - timedelta(days=2), pitches_thrown=25),
    ]

    result = classify_for_candidate(
        score=ScoreStub(raw_score=20.0),
        game_logs=logs,
        reference_date=ref,
        latest_game_date=ref,
        candidate=candidate,
    )

    assert candidate.thresholds.avoid_pitches_last_3_days == THRESHOLDS.avoid_pitches_last_3_days
    assert candidate.thresholds.unavailable_pitches_last_3_days == 90
    assert result['availability_status'] == STATUS_AVOID
    assert result['inputs']['pitches_last_3_days'] == 85


def test_multi_signal_candidate_preserves_unavailable_only_with_multiple_severe_signals(make_log):
    ref = date(2026, 6, 1)
    candidate = _candidate('require_two_severe_signals')
    single_signal_logs = [
        make_log(ref, pitches_thrown=30),
        make_log(ref - timedelta(days=1), pitches_thrown=30),
        make_log(ref - timedelta(days=2), pitches_thrown=25),
    ]
    two_signal_logs = [
        make_log(ref, pitches_thrown=20),
        make_log(ref - timedelta(days=1), pitches_thrown=35),
        make_log(ref - timedelta(days=2), pitches_thrown=30),
    ]

    single_signal = classify_for_candidate(
        score=ScoreStub(raw_score=20.0),
        game_logs=single_signal_logs,
        reference_date=ref,
        latest_game_date=ref,
        candidate=candidate,
    )
    two_signal = classify_for_candidate(
        score=ScoreStub(raw_score=86.0),
        game_logs=two_signal_logs,
        reference_date=ref,
        latest_game_date=ref,
        candidate=candidate,
    )

    assert single_signal['availability_status'] == STATUS_AVOID
    assert unavailable_severe_signals(single_signal['inputs']) == ['85 pitches in 3 days']
    assert two_signal['availability_status'] == STATUS_UNAVAILABLE
    assert len(unavailable_severe_signals(two_signal['inputs'])) == 2


def test_candidate_thresholds_do_not_change_stale_or_missing_semantics(make_log):
    ref = date(2026, 6, 1)
    candidate = _candidate('raise_three_day_90')

    stale = classify_for_candidate(
        score=ScoreStub(raw_score=20.0),
        game_logs=[],
        reference_date=ref,
        latest_game_date=ref - timedelta(days=30),
        candidate=candidate,
    )
    missing = classify_for_candidate(
        score=None,
        game_logs=[],
        reference_date=ref,
        latest_game_date=None,
        candidate=candidate,
    )

    assert stale['availability_status'] == STATUS_MONITOR
    assert stale['confidence'] == CONFIDENCE_LOW
    assert stale['data_state'] == 'stale'
    assert missing['availability_status'] == STATUS_MONITOR
    assert missing['confidence'] == CONFIDENCE_LOW
    assert missing['data_state'] == 'missing'


def test_compare_records_counts_unavailable_transitions():
    candidate = _candidate('raise_three_day_90')
    baseline = [
        _record(
            1,
            'Moved Pitcher',
            STATUS_UNAVAILABLE,
            {
                'fatigue_score': 20,
                'pitches_yesterday': 0,
                'pitches_last_3_days': 85,
                'pitches_last_5_days': 85,
                'appearances_last_5_days': 3,
            },
            reasons=['85 pitches in 3 days'],
        ),
        _record(
            2,
            'Stable Pitcher',
            STATUS_MONITOR,
            {
                'fatigue_score': 42,
                'pitches_yesterday': 0,
                'pitches_last_3_days': 20,
                'pitches_last_5_days': 20,
                'appearances_last_5_days': 1,
            },
        ),
    ]
    proposed = [
        _record(
            1,
            'Moved Pitcher',
            STATUS_AVOID,
            baseline[0]['availability']['inputs'],
            reasons=['85 pitches in 3 days'],
        ),
        baseline[1],
    ]

    comparison = compare_records(baseline, proposed, candidate)

    assert comparison['status_delta'][STATUS_UNAVAILABLE] == -1
    assert comparison['status_delta'][STATUS_AVOID] == 1
    assert comparison['unavailable_moves'] == {STATUS_AVOID: 1}
    assert comparison['transitions']['Unavailable -> Avoid'] == 1
