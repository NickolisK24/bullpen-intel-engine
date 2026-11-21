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


def test_league_reports_old_receipts_without_treating_them_as_parity(tmp_path):
    from sync_v3.archived_comparisons import compare_archived_league
    path = tmp_path / 'proof.zip'
    reference = from_observed_publication(path, write_proof(path))
    teams = [dict(team_id=int(team), team_state=deepcopy(receipt['value']))
             for team, receipt in reference.team_receipts.items()]
    listing = dict(status='candidate_preview', generation='candidate', data_through='2026-10-28',
                   availability_reference='2026-10-30', teams=teams)
    del reference.team_receipts['111']['season_context']
    reference.team_receipts['119']['value']['available'] = True
    partial = compare_archived_league(listing, reference)
    assert partial['status'] == 'archived_competition_context_missing'
    assert partial['clubs_compared'] == 29 and partial['clubs_missing_context'] == [111]
    assert set(partial['differences']) == {'119'}
    reference.team_receipts['119']['season_context']['team_id'] = 111
    with pytest.raises(ValueError, match='club context'):
        compare_archived_league(listing, reference)


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
    assert older['clubs_missing_context'] == [111] and older['clubs_compared'] == 29

    assert older['archived_claims_withheld_under_replayed_rules'] == {}
    clubs[111].update(status='season_complete', basis='postseason_series_lost', last_final_game_date='2026-10-10')
    reference.team_receipts['111']['value'].update(available=True, public_label='Fresh')
    older = compare_archived_competition(report, reference)
    assert older['archived_claims_withheld_under_replayed_rules'] == {
        '111': dict(archived_label='Fresh', replayed_outcome='season_complete', replayed_reason='postseason_series_lost')}
    clubs[119]['basis'] = 'different_basis'
    mixed = compare_archived_competition(report, reference)
    assert mixed['status'] == 'archived_competition_context_missing' and mixed['clubs_compared'] == 29
    assert mixed['differences']['119']['season_context']['basis']['candidate'] == 'different_basis'
    archived = reference.team_receipts['119']['season_context']
    for key, wrong in [('team_id', 111), ('reference_date', '2026-10-29')]:
        original = archived[key]
        archived[key] = wrong
        refused = compare_archived_competition(report, reference)
        assert refused['status'] == 'club_reference_mismatch' and refused['clubs_compared'] == 0
        archived[key] = original
    clubs[111]['team_id'] = 119
    assert compare_archived_competition(report, reference)['status'] == 'club_reference_mismatch'


def test_earlier_publication_can_supply_an_absent_route_only_to_a_new_edition(tmp_path):
    from contextlib import closing
    from dataclasses import replace
    from datetime import date
    import os
    import psycopg2
    from sync_v3.generation import freeze_generation, verify_generation
    from sync_v3.public_identities import load_reference
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    path = tmp_path / 'proof.zip'
    primary = from_observed_publication(path, write_proof(path))
    day = date(2017, 8, 28)
    earlier = replace(primary, observed_at='2026-10-30T10:00:00Z', rows=[primary.rows[0], dict(id=51, mlb_id=544150)])
    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        with pytest.raises(ValueError, match='earlier observed publication'):
            install(owner, identity_export=earlier, earlier_identity_exports=[primary])
        install(owner, identity_export=primary)
        first = freeze_generation(worker, day)
        with owner, owner.cursor() as cur:
            load_reference(cur, earlier)
        second = freeze_generation(worker, day)
        assert first != second
        with owner, owner.cursor() as cur:
            load_reference(cur, dict(source='BaseballOS.pitchers', observed_at='2020-01-01T00:00:00Z',
                                     rows=[dict(id=52, mlb_id=544151)]))
        assert freeze_generation(worker, day) == second
        for digest, expected in [(first, primary.rows), (second, [*primary.rows, earlier.rows[-1]])]:
            verify_generation(worker, digest)
            with worker, worker.cursor() as cur:
                cur.execute("""SELECT mlb_id,pitcher_id FROM candidate.edition_pitcher_ids(%s)""", (digest,))
                assert sorted(cur.fetchall()) == sorted((r['mlb_id'], r['id']) for r in expected)
        with pytest.raises(psycopg2.errors.ForeignKeyViolation), owner, owner.cursor() as cur:
            load_reference(cur, replace(earlier, observed_at='2026-10-20T10:00:00Z', rows=[dict(id=51, mlb_id=544151)]))
        assert freeze_generation(worker, day) == second


def test_postseason_round_receipts_cannot_cross_pitcher_stage_or_season():
    from datetime import date, datetime, timezone
    from sync_v3.discovery import pitcher_requests
    from sync_v3.sources import inspect_response

    day = date(2026, 10, 19)
    base = pitcher_requests(day, [669330])
    *regular, stage = pitcher_requests(day, [669330], postseason_rounds=['L', 'L'])
    assert tuple(regular) == base and stage.params()['gameType'] == 'L'
    split = dict(player={'id': 669330}, sport={'id': 1}, season='2026', gameType='L')
    group = dict(type={'displayName': 'gameLog'}, group={'displayName': 'pitching'})
    def inspect(rows):
        return inspect_response(stage, dict(stats=[dict(group, splits=rows)]), datetime.now(timezone.utc))
    assert inspect([split]).status == inspect([]).status == 'received'
    for wrong in [dict(gameType='R'), dict(player={'id': 1}), dict(season='2025'), dict(sport={'id': 11})]:
        with pytest.raises(ValueError, match='requested player, round or season'):
            inspect([dict(split, **wrong)])
    with pytest.raises(ValueError, match='Unknown postseason round'):
        pitcher_requests(day, [669330], postseason_rounds=['P'])


def test_postseason_arm_comparison_requires_consistent_final_and_game_log():
    from datetime import date
    from sync_v3.postseason_arm_comparison import _compare_arm

    stats = dict(gamesPitched=1, gamesStarted=0, outs=3, inningsPitched='1.0', numberOfPitches=11,
                 saves=0, holds=0, saveOpportunities=0, gamesFinished=0)
    split = dict(game={'gamePk': 849815}, gameType='L', date='2026-10-19', team={'id': 139}, stat=stats)
    line = dict(pitcher_mlb_id=669330, game_pk=849815, game_date='2026-10-19', team_id=139, round='L',
                outs_recorded=3, pitches_thrown=11)
    def compare(splits, lines):
        return _compare_arm(669330, splits, lines, date(2026, 10, 20), dict(archived={}))
    checked = compare([split], [line])
    assert checked['games_compared'] == [849815] and checked['reason'] is None and not checked['matches']
    assert compare([], [])['reason'] == 'no_recent_verified_workload'
    assert compare([split, dict(date='2026-10-21')], [line]) == checked
    assert compare([dict(split, gameType='D')], [line])['reason'] == 'round_and_final_disagree'
    assert compare([split, split], [line])['reason'] == 'duplicate_game_log_appearance'
    assert compare([dict(split, stat=dict(stats, numberOfPitches=True))], [line])['reason'] == 'invalid_round_game_log'
    assert compare([split], [])['reason'] == 'game_log_and_final_population_conflict'
    assert compare([split], [dict(line, team_id=158)])['reason'] == 'missing_or_conflicting_workload'
