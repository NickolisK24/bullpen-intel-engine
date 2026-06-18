from datetime import date, timedelta

from services.availability import STATUS_AVAILABLE, STATUS_LIMITED, STATUS_MONITOR, STATUS_UNAVAILABLE
from services.bullpen_stability import (
    CURRENT_ASSIGNMENT_LIMITATION,
    LIMITED_SAMPLE_LIMITATION,
    SMALL_DENOMINATOR_CHURN_LIMITATION,
    STATUS_HEAVY_CHURN,
    STATUS_LIMITED_READ,
    STATUS_MODERATE_CHURN,
    STATUS_STABLE,
    UNKNOWN_SPLIT_LIMITATION,
    USAGE_PATTERN_LIMITATION,
    build_team_bullpen_stability,
)
from utils.innings import outs_to_decimal_innings


REF = date(2026, 6, 18)


def record(pid, name=None, status=STATUS_AVAILABLE, *, eligible=True, is_active_mlb=True):
    return {
        'pitcher_id': pid,
        'name': name or f'Arm {pid}',
        'availability': {
            'availability_status': status,
            'confidence': 'high',
            'data_state': 'fresh',
            'reasons': [],
            'limitations': [],
        },
        'eligibility': {'eligible': eligible, 'role': 'Reliever', 'limitations': []},
        'roster_status': {
            'is_active_mlb': is_active_mlb,
            'is_inactive_context': not is_active_mlb,
        },
        'pitcher_labels': {
            'read': {
                'key': 'unavailable' if status == STATUS_UNAVAILABLE else 'clean_option',
            },
        },
    }


def log(pid, days_ago, outs=3, games_started=0):
    return {
        'pitcher_id': pid,
        'mlb_game_pk': pid * 100 + days_ago,
        'game_date': REF - timedelta(days=days_ago),
        'game_type': 'R',
        'games_started': games_started,
        'innings_pitched_outs': outs,
        'innings_pitched': outs_to_decimal_innings(outs),
        'pitches_thrown': 12,
    }


def stability(records, logs_by_pitcher):
    return build_team_bullpen_stability(
        records,
        logs_by_pitcher=logs_by_pitcher,
        team={'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'},
        reference_date=REF,
    )


def test_stable_bullpen_group_uses_recent_relief_core():
    records = [record(pid) for pid in range(1, 5)]
    logs = {
        pid: [log(pid, 8, 3), log(pid, 2, 3)]
        for pid in range(1, 5)
    }

    result = stability(records, logs)

    assert result['status'] == STATUS_STABLE
    assert result['window_days'] == 14
    assert result['active_bullpen_count'] == 4
    assert result['recently_used_bullpen_count'] == 4
    assert result['stable_core_count'] == 4
    assert result['new_or_reintroduced_arm_count'] == 0
    assert result['churn_share'] == 0.0
    assert result['limitations'] == []
    assert USAGE_PATTERN_LIMITATION in result['source_limitations']
    assert CURRENT_ASSIGNMENT_LIMITATION in result['source_limitations']


def test_moderate_churn_from_two_new_or_reintroduced_arms():
    records = [record(pid) for pid in range(1, 6)]
    logs = {
        1: [log(1, 9, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 3, 3)],
        3: [log(3, 7, 3), log(3, 1, 3)],
        4: [log(4, 1, 3)],
        5: [log(5, 2, 3)],
    }

    result = stability(records, logs)

    assert result['status'] == STATUS_MODERATE_CHURN
    assert result['new_or_reintroduced_arm_count'] == 2
    assert result['stable_core_count'] == 3
    assert result['churn_share'] == 0.4
    assert 'moderate churn' in result['summary']


def test_heavy_churn_from_multiple_new_or_reintroduced_arms():
    records = [record(pid) for pid in range(1, 7)]
    logs = {
        1: [log(1, 9, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 1, 3)],
        4: [log(4, 1, 3)],
        5: [log(5, 2, 3)],
        6: [log(6, 3, 3)],
    }

    result = stability(records, logs)

    assert result['status'] == STATUS_HEAVY_CHURN
    assert result['new_or_reintroduced_arm_count'] == 4
    assert result['churn_share'] == 0.67
    assert 'heavy churn' in result['summary']


def test_limited_read_when_recent_usage_sample_is_too_thin():
    records = [record(1), record(2)]
    logs = {
        1: [log(1, 2, 3)],
        2: [log(2, 1, 3)],
    }

    result = stability(records, logs)

    assert result['status'] == STATUS_LIMITED_READ
    assert result['recently_used_bullpen_count'] == 2
    assert LIMITED_SAMPLE_LIMITATION in result['limitations']


def test_new_or_reintroduced_detection_uses_late_first_relief_appearance():
    records = [record(pid) for pid in range(1, 4)]
    logs = {
        1: [log(1, 9, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 1, 3)],
    }

    result = stability(records, logs)

    assert result['new_or_reintroduced_arm_count'] == 1
    assert result['new_or_reintroduced_arms'][0]['pitcher_id'] == 3
    assert result['new_or_reintroduced_arms'][0]['first_relief_date'] == '2026-06-17'
    assert result['status'] == STATUS_STABLE
    assert SMALL_DENOMINATOR_CHURN_LIMITATION in result['limitations']


def test_one_new_arm_in_three_used_arms_does_not_automatically_create_churn_status():
    records = [record(pid) for pid in range(1, 4)]
    logs = {
        1: [log(1, 8, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 1, 3)],
    }

    result = stability(records, logs)

    assert result['recently_used_bullpen_count'] == 3
    assert result['new_or_reintroduced_arm_count'] == 1
    assert result['churn_share'] == 0.33
    assert result['status'] == STATUS_STABLE
    assert SMALL_DENOMINATOR_CHURN_LIMITATION in result['limitations']


def test_inactive_and_unavailable_arms_are_counted_separately_from_usage_churn():
    records = [
        record(1),
        record(2),
        record(3, status=STATUS_MONITOR),
        record(4, status=STATUS_UNAVAILABLE),
        record(5, is_active_mlb=False),
    ]
    logs = {
        1: [log(1, 8, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 6, 3), log(3, 2, 3)],
        4: [log(4, 1, 3)],
        5: [log(5, 2, 3)],
    }

    result = stability(records, logs)

    assert result['inactive_or_unavailable_count'] == 2
    assert result['active_bullpen_count'] == 3
    assert result['recently_used_bullpen_count'] == 5


def test_inactive_or_unavailable_arms_alone_do_not_drive_churn_status():
    records = [
        record(1),
        record(2),
        record(3),
        record(4, status=STATUS_UNAVAILABLE),
        record(5, status=STATUS_UNAVAILABLE),
        record(6, is_active_mlb=False),
    ]
    logs = {
        1: [log(1, 8, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 6, 3), log(3, 2, 3)],
    }

    result = stability(records, logs)

    assert result['inactive_or_unavailable_count'] == 3
    assert result['active_bullpen_count'] == 3
    assert result['new_or_reintroduced_arm_count'] == 0
    assert result['status'] == STATUS_STABLE


def test_monitor_limited_and_avoid_reads_are_not_fully_unavailable():
    records = [
        record(1, status=STATUS_AVAILABLE),
        record(2, status=STATUS_MONITOR),
        record(3, status=STATUS_LIMITED),
        record(4, status='Avoid'),
    ]
    logs = {
        pid: [log(pid, 8, 3), log(pid, 2, 3)]
        for pid in range(1, 5)
    }

    result = stability(records, logs)

    assert result['inactive_or_unavailable_count'] == 0
    assert result['active_bullpen_count'] == 4


def test_ambiguous_non_bullpen_and_unknown_split_inputs_are_limited_not_invented():
    records = [
        record(1),
        record(2),
        record(3),
        record(99, eligible=False),
    ]
    logs = {
        1: [log(1, 3, 3)],
        2: [log(2, 2, 3, games_started=1)],
        3: [log(3, 1, 3, games_started=None)],
        99: [log(99, 1, 3)],
    }

    result = stability(records, logs)

    assert result['recently_used_bullpen_count'] == 1
    assert result['total_bullpen_count'] == 3
    assert result['status'] == STATUS_LIMITED_READ
    assert UNKNOWN_SPLIT_LIMITATION in result['limitations']


def test_payload_language_does_not_use_transaction_claims_without_source():
    records = [record(pid) for pid in range(1, 4)]
    logs = {
        1: [log(1, 8, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 1, 3)],
    }

    result = stability(records, logs)
    text = str(result).lower()

    for term in ('recall', 'called up', 'optioned', 'dfa'):
        assert term not in text


def test_percentage_and_window_math_are_stable():
    records = [record(pid) for pid in range(1, 7)]
    logs = {
        1: [log(1, 9, 3), log(1, 2, 3)],
        2: [log(2, 8, 3), log(2, 1, 3)],
        3: [log(3, 1, 3)],
        4: [log(4, 1, 3)],
        5: [log(5, 2, 3)],
        6: [log(6, 15, 3)],
    }

    result = stability(records, logs)

    assert result['window_days'] == 14
    assert result['reference_date'] == '2026-06-18'
    assert result['window_start'] == '2026-06-05'
    assert result['recently_used_bullpen_count'] == 5
    assert result['new_or_reintroduced_arm_count'] == 3
    assert result['churn_share'] == 0.6
    assert result['status'] == STATUS_HEAVY_CHURN
