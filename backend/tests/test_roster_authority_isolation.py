from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import importlib.util
from pathlib import Path
from alembic.migration import MigrationContext
from alembic.operations import Operations

import pytest
import sqlalchemy as sa

from models.pitcher import Pitcher
from models.roster_membership import RosterMembershipInterval, RosterMembershipMutation
from models.source_observation import SourceObservation
from services.repair_orchestration import submit_repair_request, plan_repair_request, dispatch_repair_request
from services.roster_authority_health import roster_authority_coverage
from services.roster_authority_scope import classify_roster_team, roster_confirmation_routes
from services.roster_transaction_authority import (
    reconcile_team_roster, observe_team_roster, current_memberships,
)
from tests.test_roster_transaction_authority import app, RosterClient, _entry, SLATE, NOW
from utils.db import db


def _player():
    return {**_entry(681895, 'Evan Sisk'), 'parentTeamId': 134}


def _parent_client():
    return RosterClient({'40Man': [_player()]})


def _repair():
    submission = submit_repair_request(
        mode='targeted_repair', source_domain='roster', baseball_date_start=SLATE,
        scope={'team_ids': [134]}, reason='AUDIT-R1 authority correction',
        requested_by='Nikko', dry_run=False, enqueue=False,
    )
    plan_repair_request(submission.request.id)
    dispatch_repair_request(submission.request.id)
    return submission.request.id


def test_parent_and_affiliate_evidence_coexist_without_mlb_mutation(app):
    reconcile_team_roster(134, SLATE, client=_parent_client())
    before = current_memberships(134, 'forty_man_roster')[0].id
    for roster in ({'active': [_player()], '40Man': [_player()]}, {}):
        summary = reconcile_team_roster(484, SLATE, client=RosterClient(roster))
        assert summary['mutation_count'] == 0
        assert summary['evidence_only']
        assert not summary['authoritative']
    assert current_memberships(134, 'forty_man_roster')[0].id == before
    assert Pitcher.query.one().team_id == 134
    assert SourceObservation.query.count() >= 4
    assert RosterMembershipInterval.query.filter_by(team_id=484).count() == 0


def test_only_complete_parent_absence_removes_mlb_membership(app):
    reconcile_team_roster(134, SLATE, client=_parent_client())
    reconcile_team_roster(134, SLATE, client=RosterClient(completeness={'40Man': 'partial'}))
    assert len(current_memberships(134, 'forty_man_roster')) == 1
    reconcile_team_roster(134, SLATE, client=RosterClient())
    assert current_memberships(134, 'forty_man_roster') == []


def test_transaction_affiliate_routes_parent_and_unknown_stays_explicit():
    clubs, unresolved = roster_confirmation_routes([134, 484, 999999], metadata={
        484: {'sport_id': 11, 'parent_org_id': 134},
    })
    assert clubs == [134]
    assert unresolved == [999999]
    assert classify_roster_team(484, records=[_player()])['team_class'] == 'affiliate'
    assert not classify_roster_team(484, records=[_player()])['mlb_membership_authority']
    assert not classify_roster_team(134, records=[{'parentTeamId': 147}])['mlb_membership_authority']


def _old_defect():
    reconcile_team_roster(134, SLATE, client=_parent_client())
    prior = current_memberships(134, 'forty_man_roster')[0]
    affiliate = observe_team_roster(484, SLATE, '40Man', client=RosterClient({'40Man': [_player()]}))
    prior.effective_end_date = SLATE
    prior.closed_by_observation_id = affiliate.result.observation.id
    prior.end_precision = 'date'
    invalid = RosterMembershipInterval(
        pitcher_id=prior.pitcher_id, player_mlb_id=prior.player_mlb_id,
        team_id=484, organization_id=484, membership_type='forty_man_roster',
        effective_start_date=SLATE, authority_type='official_mlb_roster_v1',
        opened_by_observation_id=affiliate.result.observation.id,
    )
    db.session.add(invalid)
    prior.pitcher.team_id = 484
    db.session.commit()
    return prior.id, invalid.id


def test_sp13_correction_preserves_bad_history_and_restores_unchanged_source(app):
    old_id, affiliate_id = _old_defect()
    request_id = _repair()
    result = reconcile_team_roster(134, SLATE, client=_parent_client(), repair_request_id=request_id)
    assert result['source_changes'] == 0
    assert result['mutation_count'] == 2
    assert db.session.get(RosterMembershipInterval, old_id).effective_end_date == SLATE
    assert not db.session.get(RosterMembershipInterval, old_id).is_current_version
    assert not db.session.get(RosterMembershipInterval, affiliate_id).is_current_version
    restored = current_memberships(134, 'forty_man_roster')[0]
    assert restored.supersedes_interval_id == old_id
    assert restored.closed_by_observation_id is None
    void = RosterMembershipInterval.query.filter_by(supersedes_interval_id=affiliate_id).one()
    assert void.is_void and void.organization_id == 134
    assert Pitcher.query.one().team_id == 134
    assert {m.team_id for m in RosterMembershipMutation.query.filter_by(mutation_type='membership_corrected')} == {134}
    again = reconcile_team_roster(134, SLATE, client=_parent_client(), repair_request_id=request_id)
    assert again['mutation_count'] == 0
    report = roster_authority_coverage(SLATE, expected_team_ids=[134])
    assert report['forty_man_exact_match_count'] == 1
    assert report['affiliate_ownership_violation_count'] == 0


def test_correction_changes_roster_watermark_and_routes_one_parent_plan(app):
    from services.canonical_impact import plan_canonical_impact
    from services.derived_intelligence import capture_input_manifest
    from tests.test_derived_intelligence import _plan
    from models.sync_job import SyncJob
    from datetime import timedelta

    old_id, _ = _old_defect()
    prior = db.session.get(RosterMembershipInterval, old_id)
    prior.effective_start_date = SLATE - timedelta(days=1)
    plan = _plan(authority='roster_authoritative', domains=['organizational_depth'], teams=[134], games=[], pitchers=[])
    plan.baseball_date = SLATE
    db.session.commit()
    before = capture_input_manifest(plan)
    request_id = _repair()
    result = reconcile_team_roster(134, SLATE, client=_parent_client(), repair_request_id=request_id)
    assert capture_input_manifest(plan) != before
    jobs = [db.session.get(SyncJob, value) for value in result['downstream_job_ids']]
    assert len(jobs) == 1
    planned = plan_canonical_impact(jobs[0].details_json)
    assert planned.plan.affected_team_ids_json == [134]
    assert planned.plan.baseball_date == SLATE
    after = capture_input_manifest(plan)
    reconcile_team_roster(484, SLATE, client=RosterClient())
    assert capture_input_manifest(plan) == after


def test_health_detects_complete_source_but_incorrect_canonical_set(app):
    _old_defect()
    report = roster_authority_coverage(SLATE, expected_team_ids=[134])
    assert report['forty_man_exact_match_count'] == 0
    assert report['teams'][0]['forty_man']['missing_canonical_member_ids'] == [681895]
    assert report['affiliate_ownership_violation_count'] == 2


def test_correction_cannot_be_requested_outside_applied_sp13_scope(app):
    _old_defect()
    with pytest.raises(ValueError, match='running applied SP-13'):
        reconcile_team_roster(134, SLATE, client=_parent_client(), repair_request_id=99999)
    db.session.rollback()


def test_large_correction_batch_keeps_bounded_dedupe_and_exact_payload(app):
    from types import SimpleNamespace
    from services.roster_transaction_authority import _enqueue_membership_impact
    reconcile_team_roster(134, SLATE, client=_parent_client())
    interval = current_memberships(134, 'forty_man_roster')[0]
    mutations = [SimpleNamespace(id=100000 + n, pitcher_id=interval.pitcher_id) for n in range(100)]
    job = _enqueue_membership_impact(
        134, SLATE, mutations, {'40Man': SimpleNamespace(id=interval.opened_by_observation_id)},
        sync_run_id=None, parent_job_id=None, commit=True,
    )
    assert len(job.dedupe_key) <= 255
    assert job.details_json['membership_mutation_ids'] == [row.id for row in mutations]


def test_postgresql_concurrent_parent_affiliate_and_scoped_invariant(app):
    if db.engine.dialect.name != 'postgresql':
        pytest.skip('PostgreSQL concurrency/invariant proof')
    barrier = Barrier(2)

    def run(team_id):
        with app.app_context():
            barrier.wait(timeout=10)
            result = reconcile_team_roster(team_id, SLATE, client=RosterClient({'active': [_player()], '40Man': [_player()]}))
            db.session.remove()
            return result

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(run, [134, 484]))
    assert sorted(row['mutation_count'] for row in results) == [0, 2]
    assert len(current_memberships(134, 'forty_man_roster')) == 1

    assert current_memberships(484, 'forty_man_roster') == []
    source = current_memberships(134, 'forty_man_roster')[0]
    assignment = RosterMembershipInterval(
        pitcher_id=source.pitcher_id, player_mlb_id=source.player_mlb_id,
        team_id=484, organization_id=134, membership_type='minor_assignment',
        effective_start_date=SLATE, authority_type='test_official_assignment',
        opened_by_observation_id=source.opened_by_observation_id,
    )
    db.session.add(assignment)
    db.session.commit()
    with pytest.raises(sa.exc.IntegrityError):
        with db.session.begin_nested():
            db.session.add(RosterMembershipInterval(
                pitcher_id=source.pitcher_id, player_mlb_id=source.player_mlb_id,
                team_id=134, organization_id=134, membership_type='forty_man_roster',
                effective_start_date=SLATE, authority_type='official_mlb_roster_v1',
                opened_by_observation_id=source.opened_by_observation_id,
            ))
            db.session.flush()
    assert len(current_memberships(134, 'forty_man_roster')) == 1

def test_migration_preserves_rows_and_refuses_to_erase_void_history(app):
    path = Path(__file__).resolve().parents[1] / 'migrations/versions/d2e5f8a1b4c7_isolate_roster_authority.py'
    spec = importlib.util.spec_from_file_location('r1_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    reconcile_team_roster(134, SLATE, client=_parent_client())
    db.session.remove()
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        migration.downgrade()
        migration.upgrade()
        assert connection.execute(sa.text('SELECT count(*) FROM roster_membership_intervals')).scalar_one() == 1
    prior_id, affiliate_id = _old_defect()
    reconcile_team_roster(134, SLATE, client=_parent_client(), repair_request_id=_repair())
    db.session.remove()
    with db.engine.begin() as connection:
        migration.op = Operations(MigrationContext.configure(connection))
        with pytest.raises(RuntimeError, match='downgrade refused'):
            migration.downgrade()
