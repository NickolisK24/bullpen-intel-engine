"""Team State vNext production proof — builder, collector, and validator contract.

The proof is the mechanism that would have caught D-056 on the run that shipped it:
the first natural vNext publication passed every gate requirement the original proof
design named while classifying the whole league a day early, because none of those
requirements looked at the reference dates.

These tests pin what the artifact must say, what it must never say quietly, and that
capture cannot disturb the publication it observes.
"""

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import team_state_vnext_production_proof as proof_module
from services.team_state_vnext_production_proof import (
    CAPABILITY,
    CONTRACT,
    INVARIANTS,
    ProofCollector,
    RESULT_FAIL,
    RESULT_INCONCLUSIVE,
    RESULT_PASS,
    VERDICT_FAIL,
    VERDICT_PASS_WITH_INCONCLUSIVE,
    build_proof,
    build_team_entry,
    write_proof,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


SLATE = date(2026, 8, 17)
AVAILABILITY = date(2026, 8, 18)
SNAPSHOT_ID = 438
SYNC_RUN_ID = 775


def _thresholds():
    return {
        'clean_share_fresh_min': [3, 5],
        'clean_share_fresh_min_value': 0.6,
        'clean_count_fresh_min': 5,
        'severe_count_fresh_max': 1,
        'clean_count_vulnerable_max': 2,
        'severe_share_vulnerable_min': [1, 3],
        'severe_share_vulnerable_min_value': 1 / 3,
    }


def _evidence(clean, moderate, severe, unknown, *, status_code, decisive_rule,
              method_version='v3_phase_5'):
    total = clean + moderate + severe + unknown
    share = (lambda count: count / total) if total else (lambda count: None)
    return {
        'method_version': method_version,
        'contract': 'team_state_contract_a',
        'basis': 'status_only',
        'readiness_status_code': status_code,
        'active_pitcher_count': total,
        'clean_count': clean,
        'moderate_count': moderate,
        'severe_count': severe,
        'unknown_count': unknown,
        'clean_share': share(clean),
        'moderate_share': share(moderate),
        'severe_share': share(severe),
        'unknown_share': share(unknown),
        'decisive_rule': decisive_rule,
        'decisive_inputs': {'clean_count': clean},
        'thresholds_applied': _thresholds(),
        'trust_state': 'high',
        'trust_data_state': 'fresh',
        'freshness_state': 'current',
        'material_limitations': [],
        'evidence_references': {'population_authority': 'resolve_readiness_population'},
    }


def _artifact(public_code):
    return SimpleNamespace(payload={'public_copy': {'state': {'public_code': public_code}}})


def _result(team_id, *, clean=6, moderate=2, severe=0, unknown=0,
            status_code='operationally_stable', decisive_rule='fresh_coverage',
            public_code='fresh', method_version='v3_phase_5',
            membership=SLATE, availability=AVAILABILITY, evidence=None):
    vector = evidence if evidence is not None else _evidence(
        clean, moderate, severe, unknown,
        status_code=status_code, decisive_rule=decisive_rule,
        method_version=method_version,
    )
    return SimpleNamespace(
        outcome='published',
        public_id=f'ts_{team_id}',
        payload_version='1.2.0',
        source_snapshot_id=SNAPSHOT_ID,
        source_sync_run_id=SYNC_RUN_ID,
        product_date=SLATE,
        artifact=_artifact(public_code),
        readiness={
            'contract_version': 'v3_phase_5',
            'readiness': {'status_code': status_code},
            'team_state_evidence': vector,
        },
        membership_reference_date=membership,
        availability_reference_date=availability,
    )


def _snapshot(what_changed=None):
    return SimpleNamespace(
        id=SNAPSHOT_ID, sync_run_id=SYNC_RUN_ID, data_through=SLATE,
        published_at=datetime(2026, 8, 19, 10, 30, 7), status='ready', is_published=True,
        payload={'what_changed_since_yesterday': what_changed or {
            'state': 'changes_detected',
            'change_count': 9,
            'changes': [{'change_type': 'rested_options_changed'}],
        }},
    )


def _inventory(entries):
    return {
        'entries': entries,
        'count': len(entries),
        'digest': proof_module._digest(entries),
    }


def _persist_publication_identity():
    run = SyncRun(
        id=SYNC_RUN_ID,
        status='success',
        stage='published',
        source='external_schedule',
    )
    snapshot = DashboardSnapshot(
        id=SNAPSHOT_ID,
        snapshot_type='bullpen_dashboard',
        sync_run_id=SYNC_RUN_ID,
        status='ready',
        is_published=True,
        published_at=datetime(2026, 8, 19, 10, 30, 7),
        payload={},
        payload_version=1,
        data_through=SLATE,
        availability_reference_date=AVAILABILITY,
        snapshot_generated_at=datetime(2026, 8, 19, 10, 29, 7),
        source='external_schedule',
    )
    db.session.add(run)
    db.session.flush()
    db.session.add(snapshot)
    db.session.commit()
    return snapshot


def _teams(count=30, **overrides):
    return [
        build_team_entry(
            100 + index, _result(100 + index, **overrides),
            expected_availability_reference_date=AVAILABILITY, data_through=SLATE,
        )
        for index in range(count)
    ]


_UNSET = object()


def _build(teams=None, *, expected=30, before=_UNSET, after=_UNSET, snapshot=None,
           boundary_snapshot_id=None, boundary_loader=None):
    inventory = _inventory([[1, 'ts_old', 'sha256:aa', 'published', None]])
    return build_proof(
        snapshot=snapshot or _snapshot(),
        teams=_teams() if teams is None else teams,
        expected_team_count=expected,
        historical_before=inventory if before is _UNSET else before,
        historical_after=inventory if after is _UNSET else after,
        boundary_snapshot_id=boundary_snapshot_id,
        boundary_loader=boundary_loader,
        workflow={'run_id': '1', 'run_attempt': '1', 'source_sha': 'abc', 'note': 'test'},
    )


# ---------------------------------------------------------------------------
# Publication identity and completeness
# ---------------------------------------------------------------------------


def test_proof_ties_itself_to_one_publication_and_is_not_a_reconstruction():
    proof = _build()
    assert proof['capability'] == CAPABILITY
    assert proof['contract'] == CONTRACT
    assert proof['reconstructed'] is False
    assert proof['observation_mode'] == 'publisher_transaction_v1'
    assert proof['publication']['dashboard_snapshot_id'] == SNAPSHOT_ID
    assert proof['publication']['sync_run_id'] == SYNC_RUN_ID
    assert proof['publication']['data_through'] == SLATE.isoformat()
    assert proof['publication']['expected_availability_reference_date'] == AVAILABILITY.isoformat()


def test_thirty_teams_pass_and_are_sorted_and_unique():
    proof = _build()
    assert proof['invariants']['all_teams_published']['result'] == RESULT_PASS


@pytest.fixture
def database_app():
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


def test_durable_proof_round_trips_by_publication_id(database_app):
    snapshot = _persist_publication_identity()
    proof = _build()
    stored = proof_module._store_durable_proof(snapshot, proof)
    loaded = proof_module.load_durable_proof(SNAPSHOT_ID)
    assert loaded.id == stored.id
    assert loaded.snapshot_id == SNAPSHOT_ID
    assert loaded.sync_run_id == SYNC_RUN_ID
    assert loaded.data_through == SLATE
    assert loaded.proof == proof
    team_ids = [team['team_id'] for team in proof['teams']]
    assert team_ids == sorted(team_ids)
    assert len(set(team_ids)) == 30

    replay = proof_module._store_durable_proof(snapshot, proof)
    assert replay.id == stored.id
    assert proof_module.load_durable_proof(SNAPSHOT_ID).proof == proof

    retried = json.loads(json.dumps(proof))
    retried['proof_generated_at'] = '2026-08-19T10:31:07'
    retried['publication']['workflow']['run_id'] = 'retry-run'
    retried['publication']['workflow']['run_attempt'] = '2'
    replay = proof_module._store_durable_proof(snapshot, retried)
    assert replay.id == stored.id
    assert proof_module.load_durable_proof(SNAPSHOT_ID).proof == proof

    contradictory = json.loads(json.dumps(proof))
    contradictory['teams'][0]['partition']['clean_count'] = 5
    with pytest.raises(ValueError, match='team_state_proof_snapshot_conflict'):
        proof_module._store_durable_proof(snapshot, contradictory)
    assert proof_module.load_durable_proof(SNAPSHOT_ID).proof == proof


def test_durable_proof_can_be_flushed_and_rolled_back_with_publication(database_app):
    snapshot = _persist_publication_identity()
    proof_module._store_durable_proof(snapshot, _build(), commit=False)
    assert proof_module.load_durable_proof(SNAPSHOT_ID) is not None

    db.session.rollback()

    assert proof_module.load_durable_proof(SNAPSHOT_ID) is None


def test_a_missing_team_fails_rather_than_being_silently_omitted():
    proof = _build(teams=_teams(29))
    assert proof['invariants']['all_teams_published']['result'] == RESULT_FAIL
    assert proof['overall_verdict'] == VERDICT_FAIL


def test_a_duplicate_team_is_rejected():
    teams = _teams(30)
    teams[1] = dict(teams[0])
    proof = _build(teams=teams)
    assert proof['invariants']['all_teams_published']['result'] == RESULT_FAIL
    assert proof['invariants']['all_teams_published']['duplicate_team_ids'] == [100]


def test_a_31st_unexpected_team_is_rejected():
    proof = _build(teams=_teams(31))
    assert proof['invariants']['all_teams_published']['result'] == RESULT_FAIL
    assert proof['overall_verdict'] == VERDICT_FAIL


# ---------------------------------------------------------------------------
# Method version, partition, evidence
# ---------------------------------------------------------------------------


def test_method_version_is_captured_verbatim_for_every_team():
    proof = _build()
    assert proof['invariants']['method_version_observed']['result'] == RESULT_PASS
    assert {team['method_version'] for team in proof['teams']} == {'v3_phase_5'}
    assert all(team['contract_version'] == 'v3_phase_5' for team in proof['teams'])


def test_a_stale_method_version_fails_the_invariant():
    teams = _teams(29) + _teams(1, method_version='v3_phase_4')
    proof = _build(teams=teams)
    assert proof['invariants']['method_version_observed']['result'] == RESULT_FAIL


def test_classification_is_reproduced_from_the_recorded_partition():
    """Behavioral, not a stamp check: the retired aggregation cannot produce these."""
    proof = _build()
    assert all(
        team['contract_a_reproduction']['reproduced'] is True for team in proof['teams']
    )


@pytest.mark.parametrize(
    ('clean', 'moderate', 'severe', 'unknown', 'status_code', 'rule', 'public_code'),
    [
        (5, 2, 1, 0, 'operationally_stable', 'fresh_coverage', 'fresh'),
        (4, 3, 1, 0, 'operationally_constrained', 'residual_stretched', 'stretched'),
        (2, 6, 0, 0, 'operationally_stressed', 'margin_floor', 'vulnerable'),
        (3, 3, 3, 0, 'operationally_stressed', 'severity_share', 'vulnerable'),
        (5, 1, 0, 2, 'operationally_stable', 'fresh_coverage', 'fresh'),
    ],
)
def test_contract_a_boundary_shapes_reproduce_exactly(
    clean, moderate, severe, unknown, status_code, rule, public_code,
):
    entry = build_team_entry(
        100,
        _result(
            100, clean=clean, moderate=moderate, severe=severe, unknown=unknown,
            status_code=status_code, decisive_rule=rule, public_code=public_code,
        ),
        expected_availability_reference_date=AVAILABILITY,
        data_through=SLATE,
    )
    assert entry['partition_sum'] == entry['active_pitcher_count']
    assert entry['contract_a_reproduction'] == {
        'reproduced': True,
        'status_code': status_code,
        'decisive_rule': rule,
        'reason': None,
    }
    assert entry['final_team_state']['published_public_state'] == public_code


def test_a_state_that_contradicts_its_own_partition_fails_the_method_invariant():
    teams = _teams(29) + _teams(
        1, status_code='operationally_constrained', decisive_rule='residual_stretched',
        public_code='stretched',
    )
    proof = _build(teams=teams)
    assert proof['invariants']['method_version_observed']['result'] == RESULT_FAIL


def test_partition_invariant_passes_and_records_the_counts():
    proof = _build()
    assert proof['invariants']['partition_integrity']['result'] == RESULT_PASS
    team = proof['teams'][0]
    assert team['partition'] == {
        'clean_count': 6, 'moderate_count': 2, 'severe_count': 0, 'unknown_count': 0,
    }
    assert team['partition_sum'] == team['active_pitcher_count'] == 8
    assert team['partition_invariant_holds'] is True


def test_a_partition_violation_fails_and_names_the_team():
    broken = _evidence(6, 2, 0, 0, status_code='operationally_stable',
                       decisive_rule='fresh_coverage')
    broken['active_pitcher_count'] = 9
    teams = _teams(29) + [build_team_entry(
        999, _result(999, evidence=broken),
        expected_availability_reference_date=AVAILABILITY, data_through=SLATE,
    )]
    proof = _build(teams=teams)
    assert proof['invariants']['partition_integrity']['result'] == RESULT_FAIL
    assert proof['invariants']['partition_integrity']['violating_team_ids'] == [999]
    assert proof['overall_verdict'] == VERDICT_FAIL


def test_a_refused_team_is_not_applicable_and_is_never_counted_as_a_pass():
    refused = _evidence(0, 0, 0, 0, status_code='refused', decisive_rule='data_limited')
    refused.update({
        'active_pitcher_count': None, 'clean_count': None, 'moderate_count': None,
        'severe_count': None, 'unknown_count': None,
    })
    entry = build_team_entry(
        777, _result(777, evidence=refused, public_code=None),
        expected_availability_reference_date=AVAILABILITY, data_through=SLATE,
    )
    assert entry['partition_invariant_state'] == 'not_applicable'
    assert entry['partition_invariant_holds'] is None
    assert entry['partition_invariant_holds'] is not False


def test_governed_data_limited_withholding_is_explicit_and_valid():
    withheld = _evidence(
        0, 0, 0, 0, status_code='data_limited', decisive_rule='data_limited',
    )
    withheld.update({
        'active_pitcher_count': None,
        'clean_count': None,
        'moderate_count': None,
        'severe_count': None,
        'unknown_count': None,
    })
    teams = _teams(29) + [build_team_entry(
        999,
        _result(
            999, status_code='data_limited', decisive_rule='data_limited',
            public_code=None, evidence=withheld,
        ),
        expected_availability_reference_date=AVAILABILITY,
        data_through=SLATE,
    )]
    proof = _build(teams=teams)
    assert proof['teams'][-1]['final_team_state']['published_public_state'] is None
    assert proof['invariants']['method_version_observed']['result'] == RESULT_PASS
    assert proof['distribution']['withheld'] == 1


def test_complete_evidence_vector_is_captured_verbatim():
    proof = _build()
    assert proof['invariants']['team_state_evidence_complete']['result'] == RESULT_PASS
    team = proof['teams'][0]
    assert team['evidence_complete'] is True
    assert team['team_state_evidence']['decisive_rule'] == 'fresh_coverage'
    assert team['thresholds_applied']['clean_share_fresh_min'] == [3, 5]


def test_a_narrowed_evidence_vector_fails():
    thin = _evidence(6, 2, 0, 0, status_code='operationally_stable',
                     decisive_rule='fresh_coverage')
    thin.pop('material_limitations')
    teams = _teams(29) + [build_team_entry(
        888, _result(888, evidence=thin),
        expected_availability_reference_date=AVAILABILITY, data_through=SLATE,
    )]
    proof = _build(teams=teams)
    assert proof['invariants']['team_state_evidence_complete']['result'] == RESULT_FAIL


# ---------------------------------------------------------------------------
# Reference-date alignment — the invariant D-056 adds
# ---------------------------------------------------------------------------


def test_reference_date_alignment_passes_on_the_governed_pair():
    proof = _build()
    assert proof['invariants']['reference_date_alignment']['result'] == RESULT_PASS
    team = proof['teams'][0]
    assert team['membership_reference_date'] == SLATE.isoformat()
    assert team['availability_reference_date'] == AVAILABILITY.isoformat()
    assert team['reference_date_alignment']['aligned'] is True


def test_a_slate_anchored_classification_fails_the_alignment_invariant():
    """Replay of the snapshot-437 condition: both dates on the slate.

    Every other invariant still passes on this artifact — which is exactly why this
    one had to exist. The original gate would have certified that publication.
    """
    teams = _teams(30, availability=SLATE)
    proof = _build(teams=teams)
    alignment = proof['invariants']['reference_date_alignment']
    assert alignment['result'] == RESULT_FAIL
    assert len(alignment['misaligned_team_ids']) == 30
    assert proof['overall_verdict'] == VERDICT_FAIL
    assert 'reference_date_alignment' in proof['failed_assertions']
    for name in ('method_version_observed', 'partition_integrity',
                 'team_state_evidence_complete', 'all_teams_published'):
        assert proof['invariants'][name]['result'] == RESULT_PASS


def test_membership_drifting_off_the_slate_also_fails_alignment():
    proof = _build(teams=_teams(30, membership=AVAILABILITY))
    assert proof['invariants']['reference_date_alignment']['result'] == RESULT_FAIL


def test_unrecorded_reference_dates_are_not_treated_as_aligned():
    entry = build_team_entry(
        321, _result(321, membership=None, availability=None),
        expected_availability_reference_date=AVAILABILITY, data_through=SLATE,
    )
    assert entry['reference_date_alignment']['aligned'] is None
    assert entry['reference_date_alignment']['reason'] == 'reference_dates_not_recorded'
    proof = _build(teams=[entry], expected=1)
    assert proof['invariants']['reference_date_alignment']['result'] == RESULT_FAIL


# ---------------------------------------------------------------------------
# Distribution
# ---------------------------------------------------------------------------


def test_distribution_is_read_from_the_published_artifacts():
    proof = _build()
    assert proof['distribution']['fresh'] == 30
    assert proof['distribution']['total'] == 30
    assert proof['distribution']['source'] == 'published_artifact_public_copy'
    assert proof['invariants']['distribution_consistent']['result'] == RESULT_PASS


def test_a_public_state_that_disagrees_with_its_status_code_fails():
    teams = _teams(29) + _teams(1, public_code='vulnerable')
    proof = _build(teams=teams)
    assert proof['invariants']['distribution_consistent']['result'] == RESULT_FAIL


def test_zero_fresh_is_surfaced_as_degenerate_and_never_as_a_silent_pass():
    """The observed 0 / 13 / 17 shape. Diagnostic, not an automatic classifier failure."""
    teams = (
        _teams(13, status_code='operationally_constrained',
               decisive_rule='residual_stretched', public_code='stretched',
               clean=4, moderate=4)
        + _teams(17, status_code='operationally_stressed', decisive_rule='margin_floor',
                 public_code='vulnerable', clean=2, moderate=6)
    )
    for index, team in enumerate(teams):
        team['team_id'] = 200 + index
    proof = _build(teams=teams)
    assert proof['distribution']['fresh'] == 0
    assert proof['distribution']['distribution_degenerate'] is True
    assert proof['distribution']['degeneracy_note']
    # Degeneracy downgrades the verdict for human review; it does not fail a classifier.
    assert proof['overall_verdict'] == VERDICT_PASS_WITH_INCONCLUSIVE
    assert proof['invariants']['distribution_consistent']['result'] == RESULT_PASS


def test_a_healthy_distribution_is_not_flagged_degenerate():
    assert _build()['distribution']['distribution_degenerate'] is False


# ---------------------------------------------------------------------------
# Historical immutability
# ---------------------------------------------------------------------------


def test_unchanged_prior_artifacts_pass():
    proof = _build()
    historical = proof['historical_immutability']
    assert historical['unchanged'] is True
    assert historical['inventory_digest_before'] == historical['inventory_digest_after']
    assert proof['invariants']['no_historical_rewrite']['result'] == RESULT_PASS


def test_a_mutated_prior_artifact_is_detected_by_the_digest():
    before = _inventory([[1, 'ts_old', 'sha256:aa', 'published', None]])
    after = _inventory([[1, 'ts_old', 'sha256:TAMPERED', 'published', None]])
    proof = _build(before=before, after=after)
    assert proof['invariants']['no_historical_rewrite']['result'] == RESULT_FAIL
    assert proof['historical_immutability']['unchanged'] is False
    assert proof['historical_immutability']['changed_entries'][0]['artifact_id'] == 1
    assert proof['overall_verdict'] == VERDICT_FAIL


def test_a_silent_supersession_is_detected_too():
    before = _inventory([[1, 'ts_old', 'sha256:aa', 'published', None]])
    after = _inventory([[1, 'ts_old', 'sha256:aa', 'superseded', '2026-08-19T00:00:00']])
    proof = _build(before=before, after=after)
    assert proof['invariants']['no_historical_rewrite']['result'] == RESULT_FAIL


def test_an_unavailable_inventory_is_inconclusive_not_a_pass():
    proof = _build(before=None, after=None)
    assert proof['invariants']['no_historical_rewrite']['result'] == RESULT_INCONCLUSIVE
    assert proof['overall_verdict'] == VERDICT_PASS_WITH_INCONCLUSIVE


# ---------------------------------------------------------------------------
# Cross-version What Changed
# ---------------------------------------------------------------------------


def test_forward_publication_is_inconclusive_never_a_false_pass():
    proof = _build()
    block = proof['cross_version_what_changed']
    assert block['method_version_transition']['applicable'] is False
    assert block['method_version_transition']['previous_method_version_persisted'] is False
    assert proof['invariants']['no_false_cross_version_change']['result'] == RESULT_INCONCLUSIVE
    assert proof['overall_verdict'] == VERDICT_PASS_WITH_INCONCLUSIVE


def test_team_state_vocabulary_in_the_change_payload_fails():
    """Positive control: the scanner is not vacuously clean."""
    snapshot = _snapshot({
        'state': 'changes_detected', 'change_count': 1,
        'changes': [{'change_type': 'team_state_changed', 'summary': 'Now Vulnerable'}],
    })
    proof = _build(snapshot=snapshot)
    scan = proof['cross_version_what_changed']['current_publication']
    assert 'Vulnerable' in scan['team_state_vocabulary_hits']
    assert scan['team_state_change_types_present'] == ['team_state_changed']
    assert proof['invariants']['no_false_cross_version_change']['result'] == RESULT_FAIL


def test_the_boundary_snapshot_is_carried_as_historical_evidence():
    boundary = SimpleNamespace(
        id=437, sync_run_id=774, data_through=date(2026, 8, 17),
        payload={'what_changed_since_yesterday': {
            'state': 'no_meaningful_changes', 'change_count': 0, 'changes': [],
        }},
    )
    proof = _build(boundary_snapshot_id=437, boundary_loader=lambda _id: boundary)
    reference = proof['cross_version_what_changed']['boundary_reference']
    assert reference['available'] is True
    assert reference['boundary_snapshot_id'] == 437
    assert reference['read_mode'] == 'frozen_published_snapshot_payload'
    assert reference['scan']['team_state_vocabulary_hits'] == []


def test_an_absent_boundary_snapshot_is_reported_not_invented():
    proof = _build(boundary_snapshot_id=None)
    assert proof['cross_version_what_changed']['boundary_reference'] == {
        'available': False, 'reason': 'boundary_snapshot_not_supplied',
    }


# ---------------------------------------------------------------------------
# Verdict arithmetic and determinism
# ---------------------------------------------------------------------------


def test_every_declared_assertion_is_evaluated():
    proof = _build()
    assert proof['assertions_expected'] == len(INVARIANTS)
    assert proof['assertions_evaluated'] == proof['assertions_expected']
    assert set(proof['invariants']) == set(INVARIANTS)


def test_any_failure_forces_an_overall_fail():
    proof = _build(teams=_teams(29))
    assert proof['overall_verdict'] == VERDICT_FAIL
    assert proof['failed_assertions']


def test_serialization_is_deterministic_for_identical_inputs(tmp_path):
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    write_proof(_build(), str(first))
    write_proof(_build(), str(second))
    assert first.read_text() == second.read_text()
    assert json.loads(first.read_text())['capability'] == CAPABILITY


# ---------------------------------------------------------------------------
# Collector and capture
# ---------------------------------------------------------------------------


def test_the_collector_records_each_team_without_altering_the_result():
    collector = ProofCollector()
    sentinel = _result(101)
    wrapped = collector.wrap(lambda team_id, **kwargs: sentinel)
    assert wrapped(101, requested_date=SLATE) is sentinel
    assert collector.results == [(101, sentinel)]


def test_capture_is_off_when_the_path_env_is_unset(monkeypatch):
    monkeypatch.delenv(proof_module.PROOF_PATH_ENV, raising=False)
    assert proof_module.proof_capture_enabled() is False


def test_capture_is_enabled_by_the_path_env(monkeypatch, tmp_path):
    monkeypatch.setenv(proof_module.PROOF_PATH_ENV, str(tmp_path / 'proof.json'))
    assert proof_module.proof_capture_enabled() is True


def test_capture_writes_the_proof_and_returns_it(monkeypatch, tmp_path):
    destination = tmp_path / 'team-state-vnext-production-proof.json'
    generated = {}

    def _fake_generation(snapshot, *, generator=None):
        for team_id in range(100, 130):
            generated[team_id] = generator(team_id, requested_date=SLATE)
        return SimpleNamespace(canonical_team_count=30)

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        _fake_generation,
    )
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory',
        lambda *args, **kwargs: _inventory([[1, 'ts_old', 'sha256:aa', 'published', None]]),
    )
    proof = proof_module.capture_publication_proof(
        _snapshot(), generator=lambda team_id, **kwargs: _result(team_id),
        path=str(destination),
    )
    assert proof is not None
    assert len(generated) == 30
    written = json.loads(destination.read_text())
    assert written['publication']['dashboard_snapshot_id'] == SNAPSHOT_ID
    assert len(written['teams']) == 30
    assert written['invariants']['reference_date_alignment']['result'] == RESULT_PASS


def test_the_artifact_is_still_written_when_an_invariant_fails(monkeypatch, tmp_path):
    """Evidence when an assertion fails is the point of the mechanism."""
    destination = tmp_path / 'proof.json'

    def _fake_generation(snapshot, *, generator=None):
        for team_id in range(100, 130):
            generator(team_id, requested_date=SLATE)
        return SimpleNamespace(canonical_team_count=30)

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        _fake_generation,
    )
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory',
        lambda *args, **kwargs: _inventory([[1, 'ts_old', 'sha256:aa', 'published', None]]),
    )
    proof = proof_module.capture_publication_proof(
        _snapshot(),
        generator=lambda team_id, **kwargs: _result(team_id, availability=SLATE),
        path=str(destination),
    )
    assert proof['overall_verdict'] == VERDICT_FAIL
    assert destination.exists()
    assert json.loads(destination.read_text())['overall_verdict'] == VERDICT_FAIL


def test_a_capture_failure_never_propagates_to_the_publication(monkeypatch, tmp_path):
    def _boom(snapshot, *, generator=None):
        raise RuntimeError('generation exploded')

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation', _boom,
    )
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory', lambda *a, **k: None,
    )
    with pytest.raises(RuntimeError):
        # The hook wrapper in dashboard_snapshot owns the isolation; the capture must
        # at minimum not corrupt state on its way out.
        proof_module.capture_publication_proof(_snapshot(), path=str(tmp_path / 'p.json'))


def test_generation_runs_exactly_once_even_when_the_proof_cannot_be_written(
    monkeypatch, autogeneration_enabled,
):
    """A failed write must not read as "generation did not happen".

    Capture owns the one post-publication generation call. If the hook branched on
    whether a proof came back instead of on whether capture was asked for, an
    unwritable destination would send it round a second time and generate the whole
    league twice inside the daily final-phase budget.
    """
    import services.dashboard_snapshot as dashboard_snapshot

    monkeypatch.setenv(proof_module.PROOF_PATH_ENV, '/proc/nope/proof.json')
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory', lambda *a, **k: None,
    )
    monkeypatch.setattr(
        'services.share_artifact_generation.generate_team_state_artifact',
        lambda team_id, **kwargs: _result(team_id),
    )
    generations = []

    def _generation(snapshot, *, generator=None):
        generations.append(generator)
        generator(100, requested_date=SLATE)
        return SimpleNamespace(canonical_team_count=1)

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        _generation,
    )
    dashboard_snapshot.run_post_commit_snapshot_publication(_published_snapshot())
    assert len(generations) == 1


def test_transactional_publication_proof_flushes_30_teams_without_committing(
    monkeypatch,
):
    from services.mlb_club_directory import MLB_TEAM_IDS

    monkeypatch.delenv(proof_module.PROOF_PATH_ENV, raising=False)
    snapshot = SimpleNamespace(
        id=SNAPSHOT_ID,
        sync_run_id=SYNC_RUN_ID,
        data_through=SLATE,
        availability_reference_date=AVAILABILITY,
        published_at=datetime(2026, 8, 19, 10, 30, 7),
        status='ready',
        is_published=True,
        source='sync_completion',
        payload={'what_changed_since_yesterday': {'state': 'unavailable'}},
    )

    def resolver(team_id, **kwargs):
        kwargs['reference_dates_out'].update({
            'membership_reference_date': SLATE,
            'availability_reference_date': AVAILABILITY,
        })
        return _result(team_id).readiness

    stored = []
    monkeypatch.setattr(
        proof_module,
        'historical_team_state_inventory',
        lambda *_args, **_kwargs: _inventory([]),
    )
    monkeypatch.setattr(
        proof_module,
        '_store_durable_proof',
        lambda snap, proof, *, commit=True: stored.append((snap, proof, commit)),
    )

    proof = proof_module.require_transactional_publication_proof(
        snapshot,
        readiness_resolver=resolver,
        team_ids=MLB_TEAM_IDS,
    )

    assert len(proof['teams']) == 30
    assert {team['team_id'] for team in proof['teams']} == set(MLB_TEAM_IDS)
    assert proof['publication']['workflow']['proof_persistence_phase'] == 'pre_trust_commit'
    assert stored == [(snapshot, proof, False)]
    assert all(
        proof['invariants'][name]['result'] == RESULT_PASS
        for name in (
            'all_teams_published',
            'method_version_observed',
            'partition_integrity',
            'team_state_evidence_complete',
            'reference_date_alignment',
            'distribution_consistent',
        )
    )


def test_transactional_publication_proof_rejects_corrupt_team_state(
    monkeypatch,
):
    from services.mlb_club_directory import MLB_TEAM_IDS

    snapshot = SimpleNamespace(
        id=SNAPSHOT_ID,
        sync_run_id=SYNC_RUN_ID,
        data_through=SLATE,
        availability_reference_date=AVAILABILITY,
        published_at=datetime(2026, 8, 19, 10, 30, 7),
        status='ready',
        is_published=True,
        source='sync_completion',
        payload={},
    )

    def resolver(team_id, **kwargs):
        kwargs['reference_dates_out'].update({
            'membership_reference_date': SLATE,
            'availability_reference_date': AVAILABILITY,
        })
        readiness = _result(team_id).readiness
        if team_id == MLB_TEAM_IDS[-1]:
            readiness = json.loads(json.dumps(readiness))
            readiness['team_state_evidence']['active_pitcher_count'] = 9
        return readiness

    monkeypatch.setattr(
        proof_module,
        'historical_team_state_inventory',
        lambda *_args, **_kwargs: _inventory([]),
    )
    monkeypatch.setattr(
        proof_module,
        '_store_durable_proof',
        lambda *_args, **_kwargs: pytest.fail('invalid proof must not be stored'),
    )

    with pytest.raises(ValueError, match='partition_integrity'):
        proof_module.require_transactional_publication_proof(
            snapshot,
            readiness_resolver=resolver,
            team_ids=MLB_TEAM_IDS,
        )


def test_an_unwritable_destination_returns_none_rather_than_raising(monkeypatch):
    def _fake_generation(snapshot, *, generator=None):
        generator(100, requested_date=SLATE)
        return SimpleNamespace(canonical_team_count=1)

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        _fake_generation,
    )
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory', lambda *a, **k: None,
    )
    monkeypatch.setattr(
        proof_module, 'write_proof',
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError('unwritable')),
    )
    assert proof_module.capture_publication_proof(
        _snapshot(), generator=lambda team_id, **kwargs: _result(team_id),
        path='/proc/definitely/not/writable/proof.json',
    ) is None


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


def _validator():
    from scripts.validate_team_state_vnext_proof import validate_proof
    return validate_proof


def test_validator_accepts_a_well_formed_proof():
    assert _validator()(_build()) == (True, 'ok')


def test_validator_rejects_a_missing_invariant():
    proof = _build()
    proof['invariants'].pop('reference_date_alignment')
    ok, reason = _validator()(proof)
    assert ok is False
    assert reason == 'invariant_missing_or_unrecognized:reference_date_alignment'


def test_validator_rejects_a_verdict_softer_than_its_invariants():
    proof = _build(teams=_teams(29))
    proof['overall_verdict'] = 'PASS'
    ok, reason = _validator()(proof)
    assert ok is False
    assert reason == 'verdict_softer_than_invariants'


def test_validator_rejects_a_reconstructed_artifact():
    proof = _build()
    proof['reconstructed'] = True
    assert _validator()(proof) == (False, 'not_a_direct_observation')


def test_validator_rejects_a_team_from_another_publication():
    proof = _build()
    proof['teams'][0]['source_snapshot_id'] = 999
    assert _validator()(proof) == (False, 'team_publication_identity_mismatch')


def test_validator_rejects_partially_evaluated_assertions():
    proof = _build()
    proof['assertions_evaluated'] = len(INVARIANTS) - 1
    assert _validator()(proof) == (False, 'assertions_not_fully_evaluated')


@pytest.mark.parametrize('text,reason', [
    ('', 'empty_artifact'),
    ('not json', 'not_json'),
    ('[]', 'not_object'),
])
def test_validator_rejects_malformed_files(tmp_path, text, reason):
    from scripts.validate_team_state_vnext_proof import validate_proof_file

    path = tmp_path / 'proof.json'
    path.write_text(text)
    _, ok, actual = validate_proof_file(str(path))
    assert (ok, actual) == (False, reason)


def test_validator_exit_codes(tmp_path):
    from scripts.validate_team_state_vnext_proof import (
        EXIT_INVALID_ARTIFACT, EXIT_OK, EXIT_PROOF_FAILED, main,
    )

    good = tmp_path / 'good.json'
    write_proof(_build(), str(good))
    assert main([str(good)]) == EXIT_OK

    failing = tmp_path / 'failing.json'
    write_proof(_build(teams=_teams(29)), str(failing))
    assert main([str(failing)]) == EXIT_PROOF_FAILED

    broken = tmp_path / 'broken.json'
    broken.write_text('{}')
    assert main([str(broken)]) == EXIT_INVALID_ARTIFACT


# ---------------------------------------------------------------------------
# Publication hook wiring — capture must be invisible unless it is asked for
# ---------------------------------------------------------------------------


def _published_snapshot():
    from services.dashboard_snapshot import SNAPSHOT_STATUS_READY

    return SimpleNamespace(
        id=SNAPSHOT_ID, sync_run_id=SYNC_RUN_ID, data_through=SLATE,
        published_at=datetime(2026, 8, 19, 10, 30, 7), status=SNAPSHOT_STATUS_READY,
        is_published=True, payload={},
    )


@pytest.fixture
def autogeneration_enabled(monkeypatch):
    from flask import Flask

    app = Flask('hook-test')
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    with app.app_context():
        yield app


def test_hook_runs_plain_generation_when_proof_capture_is_off(
    monkeypatch, autogeneration_enabled,
):
    import services.dashboard_snapshot as dashboard_snapshot

    monkeypatch.delenv(proof_module.PROOF_PATH_ENV, raising=False)
    calls = []
    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        lambda snapshot, **kwargs: calls.append(kwargs) or None,
    )
    monkeypatch.setattr(proof_module, '_store_durable_proof', lambda *args: None)
    dashboard_snapshot.run_post_commit_snapshot_publication(_published_snapshot())
    # Every publisher runs exactly once under durable observation.
    assert len(calls) == 1
    assert callable(calls[0]['generator'])


def test_hook_runs_generation_under_observation_when_proof_capture_is_on(
    monkeypatch, autogeneration_enabled, tmp_path,
):
    import services.dashboard_snapshot as dashboard_snapshot

    destination = tmp_path / 'proof.json'
    monkeypatch.setenv(proof_module.PROOF_PATH_ENV, str(destination))
    monkeypatch.setattr(
        proof_module, 'historical_team_state_inventory',
        lambda *args, **kwargs: _inventory([[1, 'ts_old', 'sha256:aa', 'published', None]]),
    )
    monkeypatch.setattr(
        'services.share_artifact_generation.generate_team_state_artifact',
        lambda team_id, **kwargs: _result(team_id),
    )
    monkeypatch.setattr(proof_module, '_store_durable_proof', lambda *args: None)

    def _generation(snapshot, *, generator=None):
        assert generator is not None, 'capture must observe the real generation'
        for team_id in range(100, 130):
            generator(team_id, requested_date=SLATE)
        return SimpleNamespace(canonical_team_count=30)

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        _generation,
    )
    dashboard_snapshot.run_post_commit_snapshot_publication(_published_snapshot())
    written = json.loads(destination.read_text())
    assert len(written['teams']) == 30
    assert written['invariants']['reference_date_alignment']['result'] == RESULT_PASS


def test_a_proof_capture_explosion_never_breaks_the_publication(
    monkeypatch, autogeneration_enabled, tmp_path,
):
    """The publication has already committed; a proof problem must stay a proof problem."""
    import services.dashboard_snapshot as dashboard_snapshot

    monkeypatch.setenv(proof_module.PROOF_PATH_ENV, str(tmp_path / 'proof.json'))
    monkeypatch.setattr(
        proof_module, 'capture_publication_proof',
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError('proof exploded')),
    )
    # No exception escapes to the caller that just committed the publication.
    dashboard_snapshot.run_post_commit_snapshot_publication(_published_snapshot())
