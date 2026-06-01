from datetime import date, timedelta
from dataclasses import dataclass

from services.availability import _add_reason, classify_availability
from services.availability_explanations import (
    CATEGORY_APPEARANCE_FREQUENCY,
    CATEGORY_DATA_STATE,
    CATEGORY_FATIGUE,
    CATEGORY_PITCH_COUNT,
    CATEGORY_REST,
    INCOMPLETE_WORKLOAD_LIMITATION,
    INCOMPLETE_WORKLOAD_REASON,
    MISSING_WORKLOAD_LIMITATION,
    MISSING_WORKLOAD_REASON,
    STALE_WORKLOAD_LIMITATION,
    appearance_frequency_reason,
    back_to_back_reason,
    categorize_reason,
    fatigue_score_reason,
    pitch_count_reason,
    rest_reason,
    stale_workload_reason,
)


@dataclass
class ScoreStub:
    raw_score: float
    risk_level: str = 'LOW'


def test_pitch_and_appearance_reasons_use_consistent_window_wording():
    assert pitch_count_reason(1, 'yesterday') == '1 pitch yesterday'
    assert pitch_count_reason(42, 'yesterday') == '42 pitches yesterday'
    assert pitch_count_reason(54, '3 days') == '54 pitches in 3 days'
    assert appearance_frequency_reason(1, '3 days') == '1 appearance in 3 days'
    assert appearance_frequency_reason(4, '5 days') == '4 appearances in 5 days'
    assert back_to_back_reason() == 'Back-to-back appearances'


def test_rest_and_fatigue_reasons_read_as_explanations():
    assert rest_reason(0) == 'No rest since last appearance'
    assert rest_reason(1) == 'Only 1 day of rest'
    assert fatigue_score_reason(55.0) == 'Fatigue score is 55'
    assert fatigue_score_reason(55.34) == 'Fatigue score is 55.3'


def test_data_state_reason_and_limitation_wording_is_trust_first(make_log):
    ref = date(2026, 6, 1)

    missing = classify_availability(score=None, game_logs=[], reference_date=ref)
    assert missing['reasons'] == [MISSING_WORKLOAD_REASON]
    assert MISSING_WORKLOAD_LIMITATION in missing['limitations']

    incomplete = classify_availability(
        score=ScoreStub(raw_score=20.0),
        game_logs=[make_log(ref - timedelta(days=1), pitches_thrown=None)],
        reference_date=ref,
    )
    assert INCOMPLETE_WORKLOAD_REASON in incomplete['reasons']
    assert INCOMPLETE_WORKLOAD_LIMITATION in incomplete['limitations']

    stale = classify_availability(
        score=ScoreStub(raw_score=20.0),
        game_logs=[],
        reference_date=ref,
        latest_game_date=ref - timedelta(days=30),
    )
    assert stale['reasons'] == [stale_workload_reason(14)]
    assert STALE_WORKLOAD_LIMITATION in stale['limitations']


def test_reason_append_prevents_duplicates():
    reasons = []

    _add_reason(reasons, '4 appearances in 5 days')
    _add_reason(reasons, '4 appearances in 5 days')
    _add_reason(reasons, 'Back-to-back appearances')

    assert reasons == ['4 appearances in 5 days', 'Back-to-back appearances']


def test_workload_reason_order_is_stable_and_deduplicated(make_log):
    ref = date(2026, 6, 1)
    logs = [
        make_log(ref, pitches_thrown=10),
        make_log(ref - timedelta(days=1), pitches_thrown=40),
        make_log(ref - timedelta(days=2), pitches_thrown=10),
        make_log(ref - timedelta(days=4), pitches_thrown=15),
    ]

    result = classify_availability(
        score=ScoreStub(raw_score=78.2),
        game_logs=logs,
        reference_date=ref,
    )

    assert result['reasons'] == [
        '40 pitches yesterday',
        '60 pitches in 3 days',
        '75 pitches in 5 days',
        '3 appearances in 3 days',
        '4 appearances in 5 days',
        'Back-to-back appearances',
        '3 appearances in 4 days',
        'No rest since last appearance',
        'Fatigue score is 78.2',
    ]


def test_reason_categories_cover_generated_reason_families():
    assert categorize_reason('42 pitches yesterday') == CATEGORY_PITCH_COUNT
    assert categorize_reason('Back-to-back appearances') == CATEGORY_APPEARANCE_FREQUENCY
    assert categorize_reason('Only 1 day of rest') == CATEGORY_REST
    assert categorize_reason('Fatigue score is 55') == CATEGORY_FATIGUE
    assert categorize_reason(stale_workload_reason(14)) == CATEGORY_DATA_STATE
