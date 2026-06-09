from services.bullpen_board import BOARD_GROUP_ORDER, build_team_context
from services.bullpen_stress import build_bullpen_stress


def groups(**counts):
    return [
        {'status': status, 'count': int(counts.get(status, 0))}
        for status in BOARD_GROUP_ORDER
    ]


def stress_for(**counts):
    context = build_team_context(groups(**counts), freshness={'is_current': True})
    return context, build_bullpen_stress(context)


def assert_no_forbidden_language(stress):
    text = str(stress).lower()
    for term in (
        'predict',
        'prediction',
        'recommend',
        'recommended',
        'best option',
        'likely to lose',
        'blow a save',
        'betting',
    ):
        assert term not in text


class TestBullpenStressMapping:
    def test_stress_state_mirrors_existing_health_state(self):
        context, stress = stress_for(Available=5, Monitor=1)

        assert stress['state'] == context['health']['state']
        assert stress['source'] == 'team_context.health'

    def test_manageable_maps_to_user_copy(self):
        _context, stress = stress_for(Available=5, Monitor=1)

        assert stress['state'] == 'manageable'
        assert stress['label'] == 'Manageable'
        assert stress['summary'] == 'Bullpen workload is in manageable shape.'
        assert 'bullpen_shape_manageable' in stress['reason_codes']

    def test_monitoring_maps_to_user_copy(self):
        _context, stress = stress_for(Available=3, Monitor=3)

        assert stress['state'] == 'monitoring'
        assert stress['label'] == 'Monitoring'
        assert stress['summary'] == 'Several arms require monitoring.'
        assert 'monitor_group_pressure' in stress['reason_codes']

    def test_elevated_maps_to_user_copy(self):
        _context, stress = stress_for(Available=3, Monitor=1, Avoid=1)

        assert stress['state'] == 'elevated'
        assert stress['label'] == 'Elevated'
        assert stress['summary'] == 'Bullpen workload pressure is elevated.'
        assert 'workload_pressure_elevated' in stress['reason_codes']

    def test_constrained_maps_to_user_copy(self):
        _context, stress = stress_for(Available=2, Monitor=1, Avoid=2, Unavailable=1)

        assert stress['state'] == 'constrained'
        assert stress['label'] == 'Constrained'
        assert stress['summary'] == 'Bullpen options are constrained.'
        assert 'bullpen_options_constrained' in stress['reason_codes']

    def test_no_data_maps_to_no_read(self):
        _context, stress = stress_for()

        assert stress['state'] == 'no_data'
        assert stress['label'] == 'No Read'
        assert stress['summary'] == 'Not enough current bullpen data to assess stress.'
        assert 'no_current_bullpen_data' in stress['reason_codes']

    def test_no_numeric_stress_score_is_present(self):
        _context, stress = stress_for(Available=5, Monitor=1)

        assert 'score' not in stress
        assert 'stress_score' not in stress
        assert 'severity_rank' not in stress

    def test_no_prediction_or_recommendation_language_is_emitted(self):
        _context, stress = stress_for(Available=2, Monitor=1, Avoid=2, Unavailable=1)

        assert_no_forbidden_language(stress)

    def test_stale_context_uses_no_read_copy_without_changing_source_state(self):
        context = build_team_context(
            groups(Available=5, Monitor=1),
            freshness={'is_current': False},
        )
        stress = build_bullpen_stress(context)

        assert context['health']['state'] == 'manageable'
        assert stress['state'] == 'manageable'
        assert stress['label'] == 'No Read'
        assert stress['summary'] == 'Bullpen stress read is limited by data freshness.'
        assert stress['is_stale'] is True
        assert 'freshness_limited' in stress['reason_codes']
        assert 'Manageable' not in stress['label']

    def test_confidence_and_limitations_pass_through(self):
        context = build_team_context(
            groups(Available=3, Monitor=1, Avoid=1),
            freshness={'is_current': False},
        )
        stress = build_bullpen_stress(context)

        assert stress['confidence'] == context['confidence']
        assert stress['limitations'] == context['limitations']
        assert stress['reasons'] == context['health']['reasons']
