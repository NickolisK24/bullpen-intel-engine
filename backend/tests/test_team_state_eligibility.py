"""Tests for the Team State V1 eligibility engine + canonical payload builder
(Share Cards SC-02).

SC-02 produces deterministic eligibility decisions and canonical payloads; it
does not publish artifacts or render cards. These tests cover eligibility, trust
failures, stale-snapshot rejection, missing evidence, payload determinism and
stability, versioning, authority validation, payload equality/difference,
fail-closed behavior, and persistence compatibility with the merged SC-01
Share Artifact domain.
"""

from datetime import date, datetime

import pytest
from flask import Flask

import models.share_artifact  # noqa: F401
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from services import team_state_source as source_module
from services.share_artifacts import publish_new_share_artifact, verify_share_artifact_integrity
from services.team_state_eligibility import (
    BLOCK_AUTHORITY_VALIDATION_FAILED,
    BLOCK_INCOMPLETE_EVIDENCE,
    BLOCK_INSUFFICIENT_TRUST,
    BLOCK_MISSING_SNAPSHOT,
    BLOCK_STALE_SNAPSHOT,
    BLOCK_UNSUPPORTED_TEAM_STATE,
    TEAM_STATE_V1,
    TRUST_FAIL_CLOSED,
    TRUST_INSUFFICIENT,
    TRUST_TRUSTED,
    evaluate_team_state_eligibility,
)
from services.team_state_payload import (
    TEAM_STATE_ARTIFACT_TYPE,
    TeamStatePayloadContract,
    TeamStatePayloadRefused,
    TeamStatePayloadRegistry,
    TeamStatePayloadVersionError,
    build_team_state_payload,
    team_state_payload_registry,
)
from services.team_state_source import (
    TeamStateSnapshotAuthority,
    TeamStateSource,
    gather_team_state_source,
)
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


TEAM_ID = 147
SNAPSHOT_ID = 5001


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


# ---------------------------------------------------------------------------
# Governed input builders (mirror the team_operations readiness contract)
# ---------------------------------------------------------------------------


def _readiness(
    *,
    status_code='operationally_constrained',
    confidence='high',
    data_state='fresh',
    freshness_state='current',
    contract_state='degraded',
    team_id=TEAM_ID,
    failed_closed=False,
    fail_closed_state='degraded_safe_output',
    constraints=None,
    extra=None,
):
    payload = {
        'capability': 'team_operations_bullpen_readiness',
        'scope': 'team_bullpen_readiness',
        'contract': 'team_operations_bullpen_readiness_api_contract',
        'contract_version': 'v3_phase_4',
        'contract_state': contract_state,
        'ranking_applied': False,
        'selection_made': False,
        'generated_at': '2026-07-20T12:00:00Z',
        'team': {
            'team_id': team_id,
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        'readiness': {
            'status': 'Operationally Constrained',
            'status_code': status_code,
            'summary': 'Two late-inning arms are down.',
            'basis': [],
        },
        'constraints': constraints if constraints is not None else [
            {
                'constraint_id': 'workload_high',
                'category': 'workload',
                'severity': 'caution',
                'affected_area': 'bullpen',
                'count': 2,
                'message': 'Heavy recent relief workload.',
                'evidence': [],
            },
        ],
        'trust_metadata': {
            'confidence': confidence,
            'confidence_reasons': [],
            'data_state': data_state,
            'source_evidence_state': 'complete',
            'governance_state': 'compliant',
            'generated_at': '2026-07-20T12:00:00Z',
            'limitations': [],
            'explanations': [],
            'refusal_reasons': [],
            'trust_validation_errors': [],
            'ranking_applied': False,
            'selection_made': False,
        },
        'freshness': {
            'freshness_state': freshness_state,
            'data_through': '2026-07-20',
            'latest_workload_date': '2026-07-20',
            'last_successful_sync': '2026-07-20T11:00:00Z',
            'latest_sync_status': 'success',
            'latest_fatigue_calculated_at': '2026-07-20T11:30:00Z',
            'generated_at': '2026-07-20T12:00:00Z',
            'stale_warning': None,
            'missing_data_warning': None,
            'limitations': [],
        },
        'fail_closed': {
            'failed_closed': failed_closed,
            'state': fail_closed_state,
        },
        'refusal': {'refused': False},
    }
    if extra:
        payload.update(extra)
    return payload


def _authority(*, trusted=True, unavailable_reason=None, snapshot_id=SNAPSHOT_ID, sync_run_id=None):
    reason = unavailable_reason if unavailable_reason is not None else (None if trusted else 'snapshot_stale')
    return TeamStateSnapshotAuthority(
        snapshot_id=snapshot_id,
        sync_run_id=sync_run_id,
        data_through=date(2026, 7, 20),
        published_at=datetime(2026, 7, 20, 13, 0, 0),
        unavailable_reason=reason,
    )


def _source(*, team_valid=True, snapshot=None, readiness=None, team_id=TEAM_ID):
    return TeamStateSource(
        team_id=team_id,
        team_valid=team_valid,
        snapshot=snapshot if snapshot is not None else _authority(),
        readiness=readiness if readiness is not None else _readiness(),
    )


# ---------------------------------------------------------------------------
# Eligibility — happy path
# ---------------------------------------------------------------------------


def test_eligible_source_passes_all_gates():
    result = evaluate_team_state_eligibility(_source())
    assert result.eligible is True
    assert result.blocking_conditions == ()
    assert result.trust_state == TRUST_TRUSTED
    assert result.payload_version == TEAM_STATE_V1
    assert result.evidence_summary['team_id'] == TEAM_ID
    assert result.evidence_summary['readiness_status_code'] == 'operationally_constrained'


@pytest.mark.parametrize('status_code', [
    'operationally_stable',
    'operationally_constrained',
    'operationally_stressed',
])
def test_all_supported_states_are_eligible(status_code):
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(status_code=status_code)))
    assert result.eligible is True


# ---------------------------------------------------------------------------
# Authority validation
# ---------------------------------------------------------------------------


def test_unknown_team_fails_authority():
    result = evaluate_team_state_eligibility(_source(team_valid=False))
    assert result.eligible is False
    assert BLOCK_AUTHORITY_VALIDATION_FAILED in result.blocking_conditions
    assert 'team_id_not_recognized' in result.reasons


def test_readiness_team_mismatch_fails_authority():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(team_id=999)))
    assert result.eligible is False
    assert BLOCK_AUTHORITY_VALIDATION_FAILED in result.blocking_conditions
    assert 'readiness_team_mismatch' in result.reasons


# ---------------------------------------------------------------------------
# Snapshot gates
# ---------------------------------------------------------------------------


def test_missing_snapshot_blocks():
    missing = TeamStateSnapshotAuthority(None, None, None, None, 'snapshot_missing')
    result = evaluate_team_state_eligibility(_source(snapshot=missing))
    assert result.eligible is False
    assert BLOCK_MISSING_SNAPSHOT in result.blocking_conditions


def test_untrusted_stale_snapshot_blocks():
    result = evaluate_team_state_eligibility(
        _source(snapshot=_authority(trusted=False, unavailable_reason='snapshot_stale'))
    )
    assert result.eligible is False
    assert BLOCK_STALE_SNAPSHOT in result.blocking_conditions
    assert any(r.startswith('snapshot:') for r in result.reasons)


def test_untrusted_coverage_snapshot_blocks_incomplete():
    result = evaluate_team_state_eligibility(
        _source(snapshot=_authority(trusted=False, unavailable_reason='slate_coverage_incomplete'))
    )
    assert result.eligible is False
    assert BLOCK_INCOMPLETE_EVIDENCE in result.blocking_conditions


# ---------------------------------------------------------------------------
# Stale / incomplete via governed readiness enums
# ---------------------------------------------------------------------------


def test_stale_freshness_state_blocks():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(freshness_state='stale')))
    assert result.eligible is False
    assert BLOCK_STALE_SNAPSHOT in result.blocking_conditions


def test_incomplete_freshness_state_blocks():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(freshness_state='incomplete')))
    assert result.eligible is False
    assert BLOCK_INCOMPLETE_EVIDENCE in result.blocking_conditions


def test_stale_data_state_blocks():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(data_state='stale')))
    assert result.eligible is False
    assert BLOCK_STALE_SNAPSHOT in result.blocking_conditions


def test_missing_readiness_blocks_incomplete():
    result = evaluate_team_state_eligibility(
        TeamStateSource(team_id=TEAM_ID, team_valid=True, snapshot=_authority(), readiness=None)
    )
    assert result.eligible is False
    assert BLOCK_INCOMPLETE_EVIDENCE in result.blocking_conditions
    assert 'readiness_evidence_missing' in result.reasons


# ---------------------------------------------------------------------------
# Trust failures
# ---------------------------------------------------------------------------


def test_low_confidence_is_insufficient_trust():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(confidence='low')))
    assert result.eligible is False
    assert BLOCK_INSUFFICIENT_TRUST in result.blocking_conditions
    assert result.trust_state == TRUST_INSUFFICIENT


def test_unknown_confidence_is_insufficient_trust():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(confidence='unknown')))
    assert result.eligible is False
    assert BLOCK_INSUFFICIENT_TRUST in result.blocking_conditions


def test_fail_closed_readiness_is_fail_closed_trust():
    result = evaluate_team_state_eligibility(
        _source(readiness=_readiness(failed_closed=True, fail_closed_state='critical_failure'))
    )
    assert result.eligible is False
    assert BLOCK_INSUFFICIENT_TRUST in result.blocking_conditions
    assert result.trust_state == TRUST_FAIL_CLOSED
    assert 'readiness_fail_closed' in result.reasons


def test_governance_violation_is_fail_closed_trust():
    poisoned = _readiness()
    poisoned['team_state_rank'] = 1  # forbidden Team Operations field name fragment
    poisoned['prediction'] = 'wins tonight'
    result = evaluate_team_state_eligibility(_source(readiness=poisoned))
    assert result.eligible is False
    assert BLOCK_INSUFFICIENT_TRUST in result.blocking_conditions
    assert result.trust_state == TRUST_FAIL_CLOSED
    assert 'readiness_governance_violation' in result.reasons


def test_untrusted_contract_state_blocks():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(contract_state='unavailable')))
    assert result.eligible is False
    assert BLOCK_INSUFFICIENT_TRUST in result.blocking_conditions


# ---------------------------------------------------------------------------
# Unsupported team state
# ---------------------------------------------------------------------------


def test_data_limited_state_is_unsupported():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(status_code='data_limited')))
    assert result.eligible is False
    assert BLOCK_UNSUPPORTED_TEAM_STATE in result.blocking_conditions


def test_refused_state_is_unsupported():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(status_code='refused')))
    assert result.eligible is False
    assert BLOCK_UNSUPPORTED_TEAM_STATE in result.blocking_conditions


def test_unknown_status_code_is_unsupported():
    result = evaluate_team_state_eligibility(_source(readiness=_readiness(status_code='vibes_good')))
    assert result.eligible is False
    assert BLOCK_UNSUPPORTED_TEAM_STATE in result.blocking_conditions


def test_multiple_blocking_conditions_are_all_reported():
    result = evaluate_team_state_eligibility(
        _source(team_valid=False, readiness=_readiness(confidence='low', status_code='data_limited'))
    )
    assert result.eligible is False
    assert BLOCK_AUTHORITY_VALIDATION_FAILED in result.blocking_conditions
    assert BLOCK_INSUFFICIENT_TRUST in result.blocking_conditions
    assert BLOCK_UNSUPPORTED_TEAM_STATE in result.blocking_conditions


# ---------------------------------------------------------------------------
# Payload builder — determinism, stability, content
# ---------------------------------------------------------------------------


def test_payload_builds_for_eligible_source():
    payload = build_team_state_payload(_source())
    assert payload.payload_version == TEAM_STATE_V1
    assert payload.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    assert payload.team_id == TEAM_ID
    assert payload.source_snapshot_id == SNAPSHOT_ID
    assert payload.document['team']['team_id'] == TEAM_ID
    assert payload.document['authority']['source_snapshot_id'] == SNAPSHOT_ID
    assert payload.document['team_state']['status_code'] == 'operationally_constrained'
    assert payload.document['payload_version'] == TEAM_STATE_V1
    # No presentation / renderer keys leak into the intelligence document.
    for banned in ('html', 'css', 'image', 'png', 'og', 'render', 'template'):
        assert banned not in payload.document


def test_payload_is_deterministic():
    a = build_team_state_payload(_source())
    b = build_team_state_payload(_source())
    assert a.document == b.document
    assert a.trust_metadata == b.trust_metadata


def test_payload_document_excludes_build_time_timestamps():
    # generated_at is volatile; it must not appear in the canonical document.
    readiness = _readiness()
    readiness['generated_at'] = '2026-07-20T23:59:59Z'
    a = build_team_state_payload(_source(readiness=readiness))
    readiness2 = _readiness()
    readiness2['generated_at'] = '2000-01-01T00:00:00Z'
    b = build_team_state_payload(_source(readiness=readiness2))
    assert a.document == b.document


def test_equivalent_sources_produce_equal_payloads():
    a = build_team_state_payload(_source(readiness=_readiness(status_code='operationally_stable')))
    b = build_team_state_payload(_source(readiness=_readiness(status_code='operationally_stable')))
    assert a.document == b.document


def test_different_status_produces_different_payload():
    a = build_team_state_payload(_source(readiness=_readiness(status_code='operationally_stable')))
    b = build_team_state_payload(_source(readiness=_readiness(status_code='operationally_stressed')))
    assert a.document != b.document
    assert a.document['team_state']['status_code'] != b.document['team_state']['status_code']


def test_different_team_produces_different_payload():
    a = build_team_state_payload(_source(team_id=TEAM_ID, readiness=_readiness(team_id=TEAM_ID)))
    b = build_team_state_payload(_source(team_id=121, readiness=_readiness(team_id=121)))
    assert a.document != b.document


def test_different_snapshot_produces_different_payload():
    a = build_team_state_payload(_source(snapshot=_authority(snapshot_id=5001)))
    b = build_team_state_payload(_source(snapshot=_authority(snapshot_id=5002)))
    assert a.document != b.document
    assert a.document['authority']['source_snapshot_id'] != b.document['authority']['source_snapshot_id']


def test_payload_carries_governed_constraints_only():
    payload = build_team_state_payload(_source())
    constraint = payload.document['team_state']['constraints'][0]
    assert set(constraint).issubset({'constraint_id', 'category', 'severity', 'affected_area', 'message'})
    # The raw readiness constraint carried count/evidence; those are dropped.
    assert 'count' not in constraint
    assert 'evidence' not in constraint


def test_payload_evidence_inputs_are_governed():
    payload = build_team_state_payload(_source())
    roles = {item.role for item in payload.evidence}
    assert 'team_state_readiness' in roles
    assert 'team_state_constraint' in roles
    keys = [item.evidence_key for item in payload.evidence]
    assert all(key.startswith(f'team_state:{TEAM_ID}:') for key in keys)


# ---------------------------------------------------------------------------
# Fail-closed behavior
# ---------------------------------------------------------------------------


def test_build_refuses_when_ineligible():
    with pytest.raises(TeamStatePayloadRefused) as excinfo:
        build_team_state_payload(_source(readiness=_readiness(status_code='refused')))
    assert BLOCK_UNSUPPORTED_TEAM_STATE in excinfo.value.eligibility.blocking_conditions


def test_build_refuses_on_missing_snapshot():
    missing = TeamStateSnapshotAuthority(None, None, None, None, 'snapshot_missing')
    with pytest.raises(TeamStatePayloadRefused):
        build_team_state_payload(_source(snapshot=missing))


# ---------------------------------------------------------------------------
# Versioning
# ---------------------------------------------------------------------------


def test_default_version_is_registered():
    assert TEAM_STATE_V1 in team_state_payload_registry.versions()
    contract = team_state_payload_registry.get(TEAM_STATE_V1)
    assert contract.version == TEAM_STATE_V1


def test_unknown_version_raises():
    with pytest.raises(TeamStatePayloadVersionError):
        build_team_state_payload(_source(), version='team-state-9.9.9')


def test_registry_supports_coexisting_versions():
    registry = TeamStatePayloadRegistry()
    registry.register(TeamStatePayloadContract('team-state-1.0.0', lambda s, e: {}, 'v1'))
    registry.register(TeamStatePayloadContract('team-state-1.1.0', lambda s, e: {}, 'v1.1'))
    assert registry.versions() == ('team-state-1.0.0', 'team-state-1.1.0')
    assert registry.latest().version == 'team-state-1.1.0'
    with pytest.raises(TeamStatePayloadVersionError):
        registry.register(TeamStatePayloadContract('team-state-1.0.0', lambda s, e: {}, 'dup'))


def test_payload_document_stamps_its_contract_version():
    payload = build_team_state_payload(_source())
    assert payload.document['payload_version'] == TEAM_STATE_V1
    assert payload.trust_metadata['payload_version'] == TEAM_STATE_V1


# ---------------------------------------------------------------------------
# Evidence gatherer adapter
# ---------------------------------------------------------------------------


def test_gatherer_validates_team_and_flags_missing_snapshot(app):
    db.session.add(Pitcher(mlb_id=900001, full_name='Active Arm', team_id=TEAM_ID, active=True))
    db.session.commit()

    source = gather_team_state_source(TEAM_ID, readiness_payload=_readiness())
    assert source.team_valid is True
    # No dashboard snapshot seeded -> snapshot resolves as missing (fail closed).
    assert source.snapshot.is_present is False
    assert source.snapshot.unavailable_reason == source_module.SNAPSHOT_MISSING_REASON

    result = evaluate_team_state_eligibility(source)
    assert result.eligible is False
    assert BLOCK_MISSING_SNAPSHOT in result.blocking_conditions


def test_gatherer_rejects_unknown_team(app):
    source = gather_team_state_source(999999, readiness_payload=_readiness(team_id=999999))
    assert source.team_valid is False
    result = evaluate_team_state_eligibility(source)
    assert BLOCK_AUTHORITY_VALIDATION_FAILED in result.blocking_conditions


def test_gatherer_packages_supplied_snapshot(app, monkeypatch):
    class _Snap:
        id = SNAPSHOT_ID
        sync_run_id = None
        data_through = date(2026, 7, 20)
        published_at = datetime(2026, 7, 20, 13, 0, 0)

    monkeypatch.setattr(source_module, 'snapshot_unavailable_reason', lambda snap: None)
    db.session.add(Pitcher(mlb_id=900002, full_name='Active Arm', team_id=TEAM_ID, active=True))
    db.session.commit()

    source = gather_team_state_source(TEAM_ID, readiness_payload=_readiness(), snapshot=_Snap())
    assert source.snapshot.is_trusted is True
    assert source.snapshot.snapshot_id == SNAPSHOT_ID
    assert evaluate_team_state_eligibility(source).eligible is True


# ---------------------------------------------------------------------------
# Persistence compatibility with SC-01
# ---------------------------------------------------------------------------


def test_payload_persists_as_sc01_share_artifact(app):
    run = SyncRun(job_name='team_state_test')
    db.session.add(run)
    db.session.flush()

    source = _source(snapshot=_authority(sync_run_id=run.id))
    payload = build_team_state_payload(source)

    artifact = publish_new_share_artifact(**payload.to_share_artifact_kwargs())

    assert artifact.lifecycle_state == 'published'
    assert artifact.team_id == TEAM_ID
    assert artifact.source_snapshot_id == SNAPSHOT_ID
    assert artifact.source_sync_run_id == run.id
    assert artifact.render_version == TEAM_STATE_V1
    assert artifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    assert artifact.payload == payload.document
    assert len(artifact.evidence) == len(payload.evidence)
    assert verify_share_artifact_integrity(artifact) is True


def test_equivalent_payloads_deduplicate_through_sc01(app):
    run = SyncRun(job_name='team_state_test')
    db.session.add(run)
    db.session.flush()

    kwargs = build_team_state_payload(_source(snapshot=_authority(sync_run_id=run.id))).to_share_artifact_kwargs()
    first = publish_new_share_artifact(**kwargs)
    second = publish_new_share_artifact(
        **build_team_state_payload(_source(snapshot=_authority(sync_run_id=run.id))).to_share_artifact_kwargs()
    )
    assert first.id == second.id  # SC-01 deduplicates equivalent published artifacts
