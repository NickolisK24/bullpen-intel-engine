from copy import deepcopy
from hashlib import sha256
import json
from zipfile import ZipFile

import pytest

from services.mlb_club_directory import MLB_TEAM_IDS
from services.team_state_vnext_production_proof import _digest
from sync_v3.public_identities import from_observed_publication


def write_proof(path, defect=None):
    date = '2026-10-28'
    availability = '2026-10-30'
    receipts = {}
    inputs = {}
    for team in MLB_TEAM_IDS:
        receipts[str(team)] = dict(team_id=team, represented_date=date, dashboard_snapshot_id=12)
        group = dict(team_id=team, membership_reference_date=date, availability_reference_date=availability,
                     member_pitcher_ids=[team], records=[dict(team_id=team, pitcher_id=team, mlb_id=team + 1000)])
        inputs[str(team)] = dict(arm_reads=group)
    digest = _digest(receipts)
    observation = dict(status='proof_valid', publication_observed=True, differences=[], snapshot_id=12,
                       data_through=date, observed_team_count=30, canonical_team_count=30,
                       expected_receipt_digest=digest, receipt_digest=digest)
    pub = dict(snapshot_is_published=True, snapshot_status='ready', dashboard_snapshot_id=12,
               data_through=date, expected_membership_reference_date=date,
               expected_availability_reference_date=availability, published_at='2026-11-20T10:00:00',
               sync_run_id=15)
    proof = dict(contract='team_state_vnext_production_proof_v1', observation_mode='publisher_transaction_v1',
                 reconstructed=False, failed_assertions=[], assertions_evaluated=8, assertions_expected=8,
                 publication=pub, snapshot_team_state_receipts=receipts, snapshot_team_state_generation_inputs=inputs,
                 overall_verdict='PASS_WITH_INCONCLUSIVE', inconclusive_assertions=['cross_version'],
                 postcommit_observation=deepcopy(observation), snapshot_team_state_receipt_digest=digest)
    if defect == 'receipt':
        receipts['111']['represented_date'] = availability
    if defect == 'observation':
        observation['snapshot_id'] += 1
    if defect == 'population':
        inputs['111']['arm_reads']['member_pitcher_ids'] = []
    if defect == 'duplicate':
        inputs['111']['arm_reads']['records'][0]['mlb_id'] = 1114
    if defect == 'availability':
        inputs['111']['arm_reads']['availability_reference_date'] = date
    if defect == 'failed':
        proof['overall_verdict'] = 'FAIL'
    with ZipFile(path, 'w') as archive:
        archive.writestr('team-state-vnext-production-proof.json', json.dumps(proof))
        archive.writestr('observation.json', json.dumps(observation))
    return sha256(path.read_bytes()).hexdigest()


def test_observed_subset_preserves_source_and_inconclusive_assertions(tmp_path):
    path = tmp_path / 'proof.zip'
    digest = write_proof(path)
    reference = from_observed_publication(path, digest)
    assert len(reference.rows) == 30
    assert dict(id=111, mlb_id=1111) in reference.rows
    assert reference.provenance['archive_sha256'] == digest
    assert reference.provenance['inconclusive_assertions'] == ['cross_version']
    assert reference.observed_at == '2026-11-20T10:00:00+00:00'


@pytest.mark.parametrize('defect', ['receipt', 'observation', 'population', 'duplicate', 'availability', 'failed', 'digest'])
def test_refuses_unverified_identity_evidence(tmp_path, defect):
    path = tmp_path / 'proof.zip'
    digest = write_proof(path, defect)
    with pytest.raises(ValueError):
        from_observed_publication(path, '0' * 64 if defect == 'digest' else digest)
