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
        receipts[str(team)] = dict(team_id=team, represented_date=date, dashboard_snapshot_id=12,
                                   season_context=dict(reference_date=availability, team_id=team, status='active'),
                                   value=dict(contract='team_state_public_v1', data_through=date, available=False, public_label=None))
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


def test_archived_league_compares_only_matching_editions_and_all_clubs(tmp_path):
    from sync_v3.archived_comparisons import compare_archived_league
    path = tmp_path / 'proof.zip'
    reference = from_observed_publication(path, write_proof(path))
    teams = [dict(team_id=team, team_state=dict(contract='team_state_public_v1', data_through='2026-10-28', available=False, public_label=None))
             for team in MLB_TEAM_IDS]
    listing = dict(status='candidate_preview', generation='candidate', data_through='2026-10-28',
                   availability_reference='2026-10-30', teams=teams)
    aligned = compare_archived_league(listing, reference)
    assert aligned['status'] == 'team_state_fields_match' and aligned['clubs_compared'] == 30
    assert aligned['current_serving_eligible'] is False and aligned['archive']['inconclusive_assertions']
    different_day = compare_archived_league(dict(listing, availability_reference='2026-10-29'), reference)
    assert different_day['status'] == 'edition_dates_differ' and different_day['clubs_compared'] == 0
    duplicate = dict(listing, teams=teams[:-1] + teams[:1])
    assert compare_archived_league(duplicate, reference)['status'] == 'club_population_differs'
    # An absent field differs from an explicitly unavailable value.
    del teams[0]['team_state']['public_label']
    teams[0]['team_state']['available'] = 0
    mismatched = compare_archived_league(listing, reference)
    delta = mismatched['differences'][str(teams[0]['team_id'])]
    assert mismatched['status'] == 'team_state_fields_differ'
    assert delta['public_label'] == {'archive': None}
    assert delta['available'] == {'candidate': 0, 'archive': False}


def test_competition_compares_the_governed_scope_independently_of_the_edition(tmp_path):
    from sync_v3.archived_comparisons import compare_archived_competition
    path = tmp_path / 'proof.zip'
    reference = from_observed_publication(path, write_proof(path))
    clubs = {team: deepcopy(reference.team_receipts[str(team)]['season_context']) for team in MLB_TEAM_IDS}
    report = dict(retrospective=True, reference_date='2026-10-30', clubs=clubs, decision_sources={1: 1},
                  missing_decisions=[], calendar_source=1)
    result = compare_archived_competition(report, reference)
    assert result['status'] == 'competition_fields_match' and result['clubs_compared'] == 30
    assert result['season_complete_projections_compared'] == 0 and not result['current_serving_eligible']
    missing = compare_archived_competition(dict(report, missing_decisions=[2]), reference)
    assert missing['status'] == 'incomplete_competition_evidence' and missing['clubs_compared'] == 0
    other = compare_archived_competition(dict(report, reference_date='2026-10-29'), reference)
    assert other['status'] == 'competition_dates_differ' and other['clubs_compared'] == 0
    clubs[111]['basis'] = 'changed'
    delta = compare_archived_competition(report, reference)
    assert delta['differences']['111']['season_context']['basis'] == {'candidate': 'changed'}

    del reference.team_receipts['111']['season_context']
    older = compare_archived_competition(report, reference)
    assert older['status'] == 'archived_competition_context_missing'
    assert older['clubs_missing_context'] == [111] and older['clubs_compared'] == 0

    assert older['archived_claims_withheld_under_replayed_rules'] == {}
    clubs[111].update(status='season_complete', basis='postseason_series_lost', last_final_game_date='2026-10-10')
    reference.team_receipts['111']['value'].update(available=True, public_label='Fresh')
    older = compare_archived_competition(report, reference)
    assert older['archived_claims_withheld_under_replayed_rules'] == {
        '111': dict(archived_label='Fresh', replayed_outcome='season_complete', replayed_reason='postseason_series_lost')}
    clubs[111]['team_id'] = 119
    assert compare_archived_competition(report, reference)['status'] == 'club_reference_mismatch'
