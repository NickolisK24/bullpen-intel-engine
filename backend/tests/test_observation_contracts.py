import pytest

from observations import (
    ALLOWED_OBSERVATION_FAMILIES,
    ALLOWED_OBSERVATION_SEVERITIES,
    ALLOWED_OBSERVATION_TRUST_STATUSES,
    ALLOWED_OBSERVATION_TYPES,
    OBSERVATION_SEVERITY_DESCRIPTIONS,
    BullpenObservation,
    ObservationCollection,
    ObservationEvidence,
    ObservationFamily,
    ObservationLimitation,
    ObservationSeverity,
    ObservationTrustStatus,
    ObservationType,
    collection_payload_errors,
    observation_governance_errors,
    require_collection_payload_valid,
    require_observation_payload_valid,
    serialize_collection,
    serialize_observation,
)


def representative_evidence():
    return ObservationEvidence(
        evidence_id='inventory-count-current',
        source='recommendation_engine_v2_bullpen_state',
        source_type='trusted_platform_state',
        label='Current inventory count',
        value=8,
        freshness_status='current',
        data_through='2026-06-04',
        generated_at='2026-06-04T18:00:00Z',
        metadata={'field': 'available_pitcher_count'},
    )


def representative_limitation():
    return ObservationLimitation(
        limitation_type='public_workload_data_only',
        summary='Observation is limited to public workload data tracked by BaseballOS.',
        severity=ObservationSeverity.INFORMATIONAL,
        source='governance_boundary',
    )


def representative_observation():
    return BullpenObservation(
        observation_id='inventory:current:2026-06-04',
        observation_type=ObservationType.INVENTORY,
        family=ObservationFamily.INVENTORY,
        severity=ObservationSeverity.INFORMATIONAL,
        title='Inventory state available',
        summary='Current bullpen inventory state is available from trusted evidence.',
        evidence=(representative_evidence(),),
        limitations=(representative_limitation(),),
        confidence={
            'status': 'medium',
            'reason': 'Public workload evidence is sufficient for inventory state.',
        },
        freshness={
            'status': 'current',
            'data_through': '2026-06-04',
            'generated_at': '2026-06-04T18:00:00Z',
        },
        trust_status=ObservationTrustStatus.SUPPORTED,
        explanation_reference='v4:availability:summary',
        generated_at='2026-06-04T18:00:00Z',
    )


class TestObservationContracts:
    def test_governed_vocabularies_align_to_v5_taxonomy(self):
        assert ALLOWED_OBSERVATION_FAMILIES == {
            'inventory',
            'readiness',
            'workload_pressure',
            'constraint',
            'freshness',
            'trust',
            'availability_movement',
            'snapshot_change',
        }
        assert ALLOWED_OBSERVATION_TYPES == ALLOWED_OBSERVATION_FAMILIES
        assert ALLOWED_OBSERVATION_SEVERITIES == {
            'informational',
            'monitor',
            'elevated',
            'significant',
        }
        assert {
            'supported',
            'limited',
            'data_limited',
            'stale',
            'missing',
            'refused',
            'fail_closed',
            'unsupported',
        }.issubset(ALLOWED_OBSERVATION_TRUST_STATUSES)

    def test_valid_observation_contract_serializes_correctly(self):
        observation = representative_observation()
        payload = serialize_observation(observation)

        assert payload['capability'] == 'v5_bullpen_intelligence_surface'
        assert payload['contract'] == 'baseballos.v5.observation.domain'
        assert payload['contract_version'] == 'v5_phase_4'
        assert payload['observation_id'] == 'inventory:current:2026-06-04'
        assert payload['observation_type'] == 'inventory'
        assert payload['family'] == 'inventory'
        assert payload['severity'] == 'informational'
        assert payload['title'] == 'Inventory state available'
        assert payload['evidence'][0]['evidence_id'] == 'inventory-count-current'
        assert payload['limitations'][0]['limitation_type'] == 'public_workload_data_only'
        assert payload['confidence']['status'] == 'medium'
        assert payload['freshness']['status'] == 'current'
        assert payload['trust_status'] == 'supported'
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert observation_governance_errors(payload) == []

    def test_missing_evidence_fails_validation(self):
        with pytest.raises(ValueError, match='evidence must include at least one item'):
            BullpenObservation(
                observation_id='inventory:missing-evidence',
                observation_type=ObservationType.INVENTORY,
                family=ObservationFamily.INVENTORY,
                severity=ObservationSeverity.INFORMATIONAL,
                title='Inventory state available',
                summary='Current bullpen inventory state is available.',
                evidence=(),
                confidence={'status': 'medium'},
                freshness={'status': 'current'},
                trust_status=ObservationTrustStatus.SUPPORTED,
            )

    def test_missing_freshness_or_trust_fails_validation(self):
        with pytest.raises(ValueError, match='freshness is required'):
            BullpenObservation(
                observation_id='inventory:missing-freshness',
                observation_type=ObservationType.INVENTORY,
                family=ObservationFamily.INVENTORY,
                severity=ObservationSeverity.INFORMATIONAL,
                title='Inventory state available',
                summary='Current bullpen inventory state is available.',
                evidence=(representative_evidence(),),
                confidence={'status': 'medium'},
                freshness={},
                trust_status=ObservationTrustStatus.SUPPORTED,
            )

        payload = representative_observation().to_dict()
        payload.pop('trust_status')
        assert 'observation is missing required field trust_status.' in (
            require_errors := _payload_errors(payload)
        )
        assert require_errors

    def test_ranking_applied_cannot_be_configured_true(self):
        kwargs = _valid_observation_kwargs()

        with pytest.raises(TypeError, match='ranking_applied'):
            BullpenObservation(**kwargs, ranking_applied=True)

        payload = representative_observation().to_dict()
        payload['ranking_applied'] = True
        with pytest.raises(ValueError, match='ranking_applied must be false'):
            require_observation_payload_valid(payload)

    def test_selection_made_cannot_be_configured_true(self):
        kwargs = _valid_observation_kwargs()

        with pytest.raises(TypeError, match='selection_made'):
            BullpenObservation(**kwargs, selection_made=True)

        payload = representative_observation().to_dict()
        payload['selection_made'] = True
        with pytest.raises(ValueError, match='selection_made must be false'):
            require_observation_payload_valid(payload)

    @pytest.mark.parametrize(
        'title,summary,term',
        (
            (
                'Use Pitcher X tonight',
                'Current inventory state is available.',
                'use',
            ),
            (
                'Inventory state available',
                'Manager should pick the preferred pitcher.',
                'manager should',
            ),
            (
                'Inventory state available',
                'This creates a matchup advantage.',
                'matchup advantage',
            ),
        ),
    )
    def test_prohibited_language_fails_validation(self, title, summary, term):
        with pytest.raises(ValueError, match=term):
            BullpenObservation(
                **{
                    **_valid_observation_kwargs(),
                    'title': title,
                    'summary': summary,
                }
            )

    def test_severity_is_descriptive_only(self):
        observation = BullpenObservation(
            **{
                **_valid_observation_kwargs(),
                'severity': ObservationSeverity.ELEVATED,
                'title': 'Workload pressure elevated',
                'summary': 'Workload pressure is elevated across current inventory.',
            }
        )

        assert observation.to_dict()['severity'] == 'elevated'
        assert 'Descriptive state' in OBSERVATION_SEVERITY_DESCRIPTIONS['elevated']
        assert 'ranking' not in OBSERVATION_SEVERITY_DESCRIPTIONS['elevated']
        assert 'priority' not in OBSERVATION_SEVERITY_DESCRIPTIONS['elevated']

        with pytest.raises(ValueError, match='severity uses unsupported vocabulary'):
            BullpenObservation(
                **{
                    **_valid_observation_kwargs(),
                    'severity': 'action_priority',
                }
            )

    def test_collection_serialization_works(self):
        collection = ObservationCollection(
            collection_id='bullpen-observations:2026-06-04',
            observations=(representative_observation(),),
            generated_at='2026-06-04T18:00:00Z',
            freshness={'status': 'current', 'data_through': '2026-06-04'},
            confidence={'status': 'medium'},
            limitations=(representative_limitation(),),
            suppressed_count=1,
            suppression_reasons=('unsupported_trust_state',),
        )

        payload = serialize_collection(collection)

        assert payload['collection_id'] == 'bullpen-observations:2026-06-04'
        assert payload['observation_count'] == 1
        assert payload['observations'][0]['observation_type'] == 'inventory'
        assert payload['limitations'][0]['limitation_type'] == 'public_workload_data_only'
        assert payload['suppressed_count'] == 1
        assert payload['suppression_reasons'] == ['unsupported_trust_state']
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False
        assert collection_payload_errors(payload) == []
        require_collection_payload_valid(payload)

    def test_collection_governance_cannot_be_configured_true(self):
        with pytest.raises(TypeError, match='ranking_applied'):
            ObservationCollection(
                collection_id='invalid',
                ranking_applied=True,
            )

        with pytest.raises(TypeError, match='selection_made'):
            ObservationCollection(
                collection_id='invalid',
                selection_made=True,
            )

    def test_governance_scan_detects_forbidden_nested_fields(self):
        payload = representative_observation().to_dict()
        payload['evidence'][0]['recommended_pitcher'] = 'Pitcher A'

        assert observation_governance_errors(payload) == [
            'payload.evidence[0].recommended_pitcher uses a forbidden V5 observation field name.'
        ]


def _valid_observation_kwargs():
    return {
        'observation_id': 'inventory:current:2026-06-04',
        'observation_type': ObservationType.INVENTORY,
        'family': ObservationFamily.INVENTORY,
        'severity': ObservationSeverity.INFORMATIONAL,
        'title': 'Inventory state available',
        'summary': 'Current bullpen inventory state is available from trusted evidence.',
        'evidence': (representative_evidence(),),
        'limitations': (representative_limitation(),),
        'confidence': {'status': 'medium'},
        'freshness': {'status': 'current'},
        'trust_status': ObservationTrustStatus.SUPPORTED,
    }


def _payload_errors(payload):
    from observations import observation_payload_errors

    return observation_payload_errors(payload)
