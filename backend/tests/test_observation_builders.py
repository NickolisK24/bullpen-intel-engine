from observations import (
    FreshnessObservationBuilder,
    InventoryObservationBuilder,
    ObservationTrustStatus,
    ReadinessObservationBuilder,
    TrustObservationBuilder,
    WorkloadPressureObservationBuilder,
    build_observation_collection,
    observation_governance_errors,
    serialize_collection,
    serialize_observation,
)


def sample_state(**overrides):
    state = {
        'observation_id': 'inventory:sample:2026-06-04',
        'evidence': [
            {
                'evidence_id': 'sample-inventory-count',
                'source': 'recommendation_engine_v2_bullpen_state',
                'source_type': 'trusted_platform_state',
                'label': 'Available inventory count',
                'value': 5,
                'freshness_status': 'current',
                'data_through': '2026-06-04',
                'generated_at': '2026-06-04T18:00:00Z',
                'metadata': {'field': 'available_count'},
            }
        ],
        'limitations': [
            {
                'limitation_type': 'public_workload_data_only',
                'summary': 'Observation is limited to public workload data.',
                'source': 'governance_boundary',
            }
        ],
        'confidence': {
            'status': 'medium',
            'reason': 'Trusted platform state is sufficient for this observation.',
        },
        'freshness': {
            'status': 'current',
            'data_through': '2026-06-04',
            'generated_at': '2026-06-04T18:00:00Z',
        },
        'trust_status': ObservationTrustStatus.SUPPORTED,
        'generated_at': '2026-06-04T18:00:00Z',
    }
    state.update(overrides)
    return state


def test_valid_builder_output_creates_governed_observation():
    observation = InventoryObservationBuilder().build(sample_state())

    payload = serialize_observation(observation)

    assert payload['observation_type'] == 'inventory'
    assert payload['family'] == 'inventory'
    assert payload['severity'] == 'monitor'
    assert payload['title'] == 'The current bullpen snapshot shows fewer usable arms.'
    assert payload['evidence'][0]['evidence_id'] == 'sample-inventory-count'
    assert payload['freshness']['status'] == 'current'
    assert payload['confidence']['status'] == 'medium'
    assert payload['trust_status'] == 'supported'
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert observation_governance_errors(payload) == []


def test_observation_family_builders_emit_expected_types():
    builders = (
        (ReadinessObservationBuilder(), 'readiness'),
        (WorkloadPressureObservationBuilder(), 'workload_pressure'),
        (FreshnessObservationBuilder(), 'freshness'),
        (TrustObservationBuilder(), 'trust'),
    )

    for builder, expected_type in builders:
        observation = builder.build(
            sample_state(observation_id=f'{expected_type}:sample:2026-06-04')
        )
        payload = serialize_observation(observation)

        assert payload['observation_type'] == expected_type
        assert payload['family'] == expected_type
        assert payload['ranking_applied'] is False
        assert payload['selection_made'] is False


def test_missing_evidence_suppresses_output():
    state = sample_state()
    state.pop('evidence')

    assert InventoryObservationBuilder().build(state) is None


def test_missing_freshness_suppresses_output():
    state = sample_state()
    state.pop('freshness')

    assert InventoryObservationBuilder().build(state) is None


def test_missing_confidence_suppresses_output():
    state = sample_state()
    state.pop('confidence')

    assert InventoryObservationBuilder().build(state) is None


def test_missing_trust_suppresses_output():
    state = sample_state()
    state.pop('trust_status')

    assert InventoryObservationBuilder().build(state) is None


def test_prohibited_language_is_suppressed():
    observation = InventoryObservationBuilder().build(
        sample_state(title='Use Pitcher X.')
    )

    assert observation is None


def test_collection_assembly_preserves_governance_flags():
    collection = build_observation_collection(
        'bullpen-observations:sample:2026-06-04',
        (
            (InventoryObservationBuilder(), sample_state()),
            (
                TrustObservationBuilder(),
                sample_state(
                    observation_id='trust:sample:2026-06-04',
                    title='Pitcher Y is the best option.',
                ),
            ),
        ),
        generated_at='2026-06-04T18:00:00Z',
        freshness={'status': 'current'},
        confidence={'status': 'medium'},
    )

    payload = serialize_collection(collection)

    assert payload['observation_count'] == 1
    assert payload['suppressed_count'] == 1
    assert payload['suppression_reasons'] == ['trust_observation_suppressed']
    assert payload['ranking_applied'] is False
    assert payload['selection_made'] is False
    assert observation_governance_errors(payload) == []


def test_builder_output_serializes_safely():
    observation = WorkloadPressureObservationBuilder().build(
        sample_state(observation_id='workload_pressure:sample:2026-06-04')
    )

    payload = serialize_observation(observation)

    assert payload['observation_type'] == 'workload_pressure'
    assert payload['title'] == 'Recent bullpen workload is running hot.'
    assert observation_governance_errors(payload) == []


def test_builders_require_only_supplied_state():
    builder = InventoryObservationBuilder()
    observation = builder.build(sample_state())

    assert observation is not None
    assert builder.build({}) is None
