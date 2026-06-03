from copy import deepcopy

from recommendation import RecommendationContext
from team_operations import (
    ALLOWED_READINESS_STATUS_CODES,
    assemble_bullpen_readiness,
    team_operations_governance_errors,
)


FORBIDDEN_RANKING_KEYS = {
    'rank',
    'ranking',
    'winner',
    'priority',
    'priority_score',
    'score',
    'score_ordering',
}

FORBIDDEN_SELECTION_KEYS = {
    'selected_pitcher',
    'selected_pitcher_id',
    'selected_candidate',
    'selected_candidate_id',
    'pitcher_choice',
    'use_this_pitcher',
}

FORBIDDEN_DECISION_LABEL_KEYS = {
    'recommended_pitcher',
    'recommended_pitcher_id',
    'recommended_option',
    'preferred_pitcher',
    'preferred_option',
    'best_candidate',
    'best_pitcher',
    'top_candidate',
}

FORBIDDEN_LABEL_TEXT = ('best', 'preferred', 'recommended')
ALLOWED_GOVERNANCE_KEYS = {'ranking_applied', 'selection_made'}


def valid_trust_metadata():
    return {
        'confidence': 'high',
        'confidence_reasons': ['fresh_data', 'complete_metadata'],
        'data_state': 'fresh',
        'source_evidence_state': 'represented',
        'governance_state': 'compliant',
        'generated_at': '2026-06-03T12:00:00Z',
        'limitations': [],
        'explanations': [],
        'refusal_reasons': [],
        'trust_validation_errors': [],
        'ranking_applied': False,
        'selection_made': False,
    }


def valid_freshness_metadata():
    return {
        'freshness_state': 'current',
        'data_through': '2026-06-03',
        'latest_workload_date': '2026-06-03',
        'last_successful_sync': '2026-06-03T11:30:00Z',
        'latest_sync_status': 'success',
        'latest_fatigue_calculated_at': '2026-06-03T11:45:00Z',
        'generated_at': '2026-06-03T12:00:00Z',
        'stale_warning': None,
        'missing_data_warning': None,
        'limitations': [],
    }


def pitcher_records():
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'right',
        },
        {
            'availability_status': 'monitor',
            'workload_category': 'moderate',
            'throwing_hand': 'right',
        },
        {
            'availability_status': 'limited',
            'workload_category': 'low',
            'throwing_hand': 'right',
        },
    )


def team_payload():
    return {
        'team_id': 111,
        'team_name': 'Example Club',
        'team_abbreviation': 'EX',
    }


def readiness_payload(**overrides):
    args = {
        'team': team_payload(),
        'pitcher_records': pitcher_records(),
        'trust_metadata': valid_trust_metadata(),
        'freshness': valid_freshness_metadata(),
    }
    args.update(overrides)
    return assemble_bullpen_readiness(**args)


def payload_keys(payload):
    keys = set()
    if isinstance(payload, dict):
        for key, value in payload.items():
            keys.add(key)
            keys.update(payload_keys(value))
    elif isinstance(payload, list):
        for value in payload:
            keys.update(payload_keys(value))
    return keys


def payload_strings(payload):
    values = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            values.append(str(key))
            values.extend(payload_strings(value))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(payload_strings(value))
    elif isinstance(payload, str):
        values.append(payload)
    return values


def governance_flag_values(payload):
    values = []
    if isinstance(payload, dict):
        if 'ranking_applied' in payload:
            values.append(payload['ranking_applied'])
        if 'selection_made' in payload:
            values.append(payload['selection_made'])
        for value in payload.values():
            values.extend(governance_flag_values(value))
    elif isinstance(payload, list):
        for value in payload:
            values.extend(governance_flag_values(value))
    return values


class TestTeamOperationsBullpenReadiness:
    def test_successful_readiness_assembly_produces_team_level_payload(self):
        payload = readiness_payload()

        assert payload['capability'] == 'team_operations_bullpen_readiness'
        assert payload['scope'] == 'team_bullpen_readiness'
        assert payload['contract_state'] == 'available'
        assert payload['team']['team_id'] == 111
        assert payload['readiness']['status_code'] == 'operationally_constrained'
        assert payload['availability_distribution']['total'] == 4
        assert payload['workload_pressure']['moderate_count'] == 1
        assert payload['coverage_inventory']['active_pitcher_count'] == 4
        assert payload['handedness_coverage']['left_handed_count'] == 1
        assert 'pitchers' not in payload
        assert 'candidate_groups' not in payload
        assert team_operations_governance_errors(payload) == []

    def test_governance_flags_are_always_false(self):
        payload = readiness_payload()

        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert payload['trust_metadata']['ranking_applied'] is False
        assert payload['trust_metadata']['selection_made'] is False
        assert all(value is False for value in governance_flag_values(payload))

        unsafe_trust = valid_trust_metadata()
        unsafe_trust['ranking_applied'] = True
        refused_payload = readiness_payload(trust_metadata=unsafe_trust)

        assert refused_payload['contract_state'] == 'refused'
        assert refused_payload['ranking_applied'] is False
        assert refused_payload['selection_made'] is False
        assert refused_payload['trust_metadata']['ranking_applied'] is False
        assert refused_payload['trust_metadata']['selection_made'] is False
        assert all(value is False for value in governance_flag_values(refused_payload))

    def test_missing_required_freshness_metadata_fails_closed(self):
        payload = readiness_payload(freshness=None)

        assert payload['contract_state'] == 'refused'
        assert payload['readiness']['status_code'] == 'refused'
        assert payload['refusal']['refused'] is True
        assert payload['refusal']['reason'] == 'freshness_metadata_missing'
        assert payload['fail_closed']['failed_closed'] is True
        assert payload['fail_closed']['critical_failure'] is True
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_missing_required_trust_metadata_fails_closed(self):
        payload = readiness_payload(trust_metadata=None)

        assert payload['contract_state'] == 'refused'
        assert payload['readiness']['status_code'] == 'refused'
        assert payload['refusal']['refused'] is True
        assert payload['refusal']['reason'] == 'trust_metadata_missing'
        assert payload['fail_closed']['failed_closed'] is True
        assert payload['trust_metadata']['confidence'] == 'unknown'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_refusal_inputs_fail_closed(self):
        payload = readiness_payload(
            refusal={
                'refused': True,
                'refusal_id': 'unsafe_context',
                'reason': 'governance_context_unsafe',
                'message': 'Readiness output is refused for this context.',
                'applies_to': 'readiness',
            }
        )

        assert payload['contract_state'] == 'refused'
        assert payload['readiness']['status_code'] == 'refused'
        assert payload['refusal']['refused'] is True
        assert payload['refusal']['refusal_id'] == 'unsafe_context'
        assert payload['refusal']['reason'] == 'governance_context_unsafe'
        assert payload['fail_closed']['state'] == 'critical_failure'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False

    def test_payload_contains_no_ranking_fields(self):
        payload = readiness_payload()
        keys = payload_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)

        assert FORBIDDEN_RANKING_KEYS.isdisjoint(keys)
        assert team_operations_governance_errors(payload) == []

    def test_payload_contains_no_selection_fields(self):
        payload = readiness_payload()
        keys = payload_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)

        assert FORBIDDEN_SELECTION_KEYS.isdisjoint(keys)
        assert team_operations_governance_errors(payload) == []

    def test_payload_contains_no_decision_labels(self):
        payload = readiness_payload()
        keys = payload_keys(payload).difference(ALLOWED_GOVERNANCE_KEYS)
        text = ' '.join(payload_strings(payload)).lower()

        assert FORBIDDEN_DECISION_LABEL_KEYS.isdisjoint(keys)
        assert all(label not in text for label in FORBIDDEN_LABEL_TEXT)

    def test_readiness_status_vocabulary_is_constrained(self):
        payload = readiness_payload()

        assert ALLOWED_READINESS_STATUS_CODES == {
            'operationally_stable',
            'operationally_constrained',
            'operationally_stressed',
            'data_limited',
            'refused',
        }
        assert payload['readiness']['status_code'] in ALLOWED_READINESS_STATUS_CODES

    def test_readiness_assembly_is_deterministic_for_identical_inputs(self):
        args = {
            'team': deepcopy(team_payload()),
            'pitcher_records': deepcopy(pitcher_records()),
            'trust_metadata': deepcopy(valid_trust_metadata()),
            'freshness': deepcopy(valid_freshness_metadata()),
        }

        first = assemble_bullpen_readiness(**deepcopy(args))
        second = assemble_bullpen_readiness(**deepcopy(args))

        assert first == second

    def test_certified_v2_recommendation_context_still_preserves_flags(self):
        payload = RecommendationContext().to_dict()

        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
