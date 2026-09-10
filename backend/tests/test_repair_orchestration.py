from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from threading import Barrier

import pytest
from flask import Flask

from models.canonical_impact import CanonicalImpactPlan
from models.daily_closure import BaseballDateClosure, BaseballDateClosureVersion
from models.repair_request import RepairRequest, RepairRequestChunk
from models.scheduled_game import ScheduledGame
from models.sync_job import SyncJob
from services.repair_orchestration import (
    MAX_STANDARD_BACKFILL_DAYS,
    check_repair_request,
    dispatch_repair_request,
    plan_repair_request,
    submit_repair_request,
)
from services.derived_intelligence import execute_derived_intelligence_plan
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


DAY = date(2026, 9, 8)


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


def _scheduled_game(game_pk=777123, state='final'):
    row = ScheduledGame(
        team_id=110, game_pk=game_pk, game_date=DAY,
        opponent_team_id=111, home_away='home', status_state=state,
        operational_state=state, source='test',
    )
    db.session.add(row)
    db.session.commit()
    return row


def test_dry_run_persists_plan_without_dispatch_or_authority_mutation(app):
    result = submit_repair_request(
        mode='targeted_repair', source_domain='final_game',
        baseball_date_start=DAY, scope={'game_pk': 777123},
        reason='verify official final line', dry_run=True, enqueue=False,
    )
    request = plan_repair_request(result.request.id)
    assert request.status == 'completed'
    assert request.plan_fingerprint
    assert request.outcome_json == {
        'dry_run': True, 'mutations_performed': 0, 'jobs_dispatched': 0,
        'publication_advanced': False, 'closure_changed': False,
    }
    assert RepairRequestChunk.query.one().status == 'succeeded'
    assert SyncJob.query.count() == 0


def test_backfill_requires_bounds_and_explicit_confirmation_for_large_scope(app):
    with pytest.raises(ValueError, match='on or after'):
        submit_repair_request(
            mode='historical_backfill', source_domain='schedule',
            baseball_date_start=DAY, baseball_date_end=date(2026, 9, 1),
            reason='invalid bounds', enqueue=False,
        )
    with pytest.raises(ValueError, match='broad-scope confirmation'):
        submit_repair_request(
            mode='historical_backfill', source_domain='schedule',
            baseball_date_start=DAY,
            baseball_date_end=DAY + timedelta(days=MAX_STANDARD_BACKFILL_DAYS),
            reason='too broad without confirmation', enqueue=False,
        )


def test_final_repair_routes_to_sp07_and_active_duplicate_reuses_request(app):
    _scheduled_game()
    first = submit_repair_request(
        mode='targeted_repair', source_domain='final_game',
        baseball_date_start=DAY, scope={'game_pk': 777123},
        reason='repair corrected final', dry_run=False, enqueue=False,
    )
    duplicate = submit_repair_request(
        mode='targeted_repair', source_domain='final_game',
        baseball_date_start=DAY, scope={'game_pk': 777123},
        reason='second audit reason', dry_run=False, enqueue=False,
    )
    assert duplicate.reused_active_request is True
    assert duplicate.request.id == first.request.id
    request = dispatch_repair_request(first.request.id, parent_job_id=None)
    jobs = SyncJob.query.filter_by(job_name='reconcile_final_game').all()
    assert len(jobs) == 1
    assert jobs[0].details_json['repair_request_id'] == request.id
    assert jobs[0].details_json['game_pk'] == 777123
    assert CanonicalImpactPlan.query.count() == 0


def test_overlapping_repair_modes_reuse_active_owner_job(app):
    _scheduled_game()
    targeted = submit_repair_request(
        mode='targeted_repair', source_domain='final_game',
        baseball_date_start=DAY, scope={'game_pk': 777123},
        reason='targeted final repair', dry_run=False, enqueue=False,
    ).request
    broad = submit_repair_request(
        mode='full_reconciliation', source_domain='multi_domain',
        baseball_date_start=DAY, scope={'game_pk': 777123},
        reason='bounded date reconciliation', dry_run=False, enqueue=False,
    ).request
    dispatch_repair_request(targeted.id)
    dispatch_repair_request(broad.id)
    final_jobs = SyncJob.query.filter_by(job_name='reconcile_final_game').all()
    assert len(final_jobs) == 1
    assert targeted.chunks[0].child_job_ids_json[0] == final_jobs[0].id
    assert final_jobs[0].id in broad.chunks[0].child_job_ids_json


def test_each_backfill_date_is_a_resumable_transaction_chunk(app):
    result = submit_repair_request(
        mode='historical_backfill', source_domain='transactions',
        baseball_date_start=DAY, baseball_date_end=date(2026, 9, 10),
        reason='fill bounded transaction evidence', dry_run=False, enqueue=False,
    )
    request = dispatch_repair_request(result.request.id)
    chunks = RepairRequestChunk.query.order_by(RepairRequestChunk.chunk_order).all()
    assert [row.baseball_date_start for row in chunks] == [
        date(2026, 9, 8), date(2026, 9, 9), date(2026, 9, 10),
    ]
    assert all(len(row.child_job_ids_json) == 1 for row in chunks)
    assert SyncJob.query.filter_by(job_name='fetch_transactions').count() == 3
    assert request.estimated_counts_json['maximum_chunks'] == 3


def test_partial_transaction_authority_blocks_request_completion(app):
    result = submit_repair_request(
        mode='targeted_repair', source_domain='transactions',
        baseball_date_start=DAY, reason='verify transaction completeness',
        dry_run=False, enqueue=False,
    )
    request = dispatch_repair_request(result.request.id)
    child = db.session.get(SyncJob, request.chunks[0].child_job_ids_json[0])
    child.status = 'succeeded'
    child.result_json = {
        'errors': 1,
        'completeness': 'partial',
        'completeness_proof': {'limit_reached': True, 'limit': 1000},
    }
    db.session.commit()

    check_repair_request(request.id, schedule_recheck=False)

    current = db.session.get(RepairRequest, request.id)
    assert current.status == 'blocked'
    assert current.completed_at is None
    assert current.chunks[0].status == 'blocked'
    assert current.blockers[0].blocker_type == 'source_partial'
    assert current.blockers[0].retryable is True


def test_method_replay_creates_explicit_plan_without_fake_source_mutation(app):
    source = CanonicalImpactPlan(
        plan_fingerprint='a' * 64, rules_version='canonical-impact-v1',
        authority_class='final', baseball_date=DAY, correlation_id='original',
        affected_game_ids_json=[777123], affected_team_ids_json=[110],
        affected_pitcher_ids_json=[12], affected_domains_json=['workload'],
        source_observation_ids_json=[], status='dispatched',
    )
    db.session.add(source)
    db.session.commit()
    result = submit_repair_request(
        mode='method_replay', source_domain='downstream',
        baseball_date_start=DAY, scope={'impact_plan_id': source.id},
        reason='adopt governed workload method', dry_run=False, enqueue=False,
        requested_method_versions={'workload': 'workload-v-next'},
    )
    dispatch_repair_request(result.request.id)
    replay = CanonicalImpactPlan.query.filter(
        CanonicalImpactPlan.repair_request_id == result.request.id,
    ).one()
    assert replay.replay_from_plan_id == source.id
    assert replay.replay_kind == 'method_replay'
    assert replay.method_versions_override_json == {'workload': 'workload-v-next'}
    assert replay.publication_mode == 'historical'
    assert replay.mutation_refs == []
    assert SyncJob.query.filter_by(job_name='process_derived_intelligence').count() == 1
    executed = execute_derived_intelligence_plan(
        replay.id, domain_executor=lambda domain, snapshots: {'summary': {'domain': domain}},
    )
    assert executed.cohort.method_versions_json['workload'] == 'workload-v-next'
    assert executed.publication_job is None
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0


def test_historical_live_repair_preserves_explicit_gap(app):
    _scheduled_game()
    result = submit_repair_request(
        mode='historical_backfill', source_domain='live',
        baseball_date_start=DAY, reason='inspect missing live evidence',
        dry_run=False, enqueue=False,
    )
    request = dispatch_repair_request(result.request.id)
    assert request.blockers[0].blocker_type == 'unsupported_historical_context'
    for job in SyncJob.query.filter_by(job_name='reconcile_final_game').all():
        job.status = 'succeeded'
    db.session.commit()
    check_repair_request(request.id, schedule_recheck=False)
    assert db.session.get(RepairRequest, request.id).status == 'completed_partial'


def test_completed_closed_date_repair_rechecks_through_sp12(app):
    _scheduled_game()
    closure = BaseballDateClosure(
        baseball_date=DAY, status='closed', current_version_number=1,
        expected_games=1, resolved_games=1, final_games=1, reconciled_final_games=1,
        unresolved_games=0, expected_teams=30, reconciled_rosters=30,
        transaction_completeness='complete', pending_jobs=0, failed_jobs=0,
        required_publications_complete=True, optional_enrichment_outstanding=False,
        closure_fingerprint='f' * 64, closure_schema_version='baseball-date-closure-v1',
        recheck_policy_version='baseball-date-recheck-v1', closed_at=datetime(2026, 9, 9, 5),
    )
    db.session.add(closure)
    db.session.flush()
    db.session.add(BaseballDateClosureVersion(
        closure_id=closure.id, version_number=1, baseball_date=DAY,
        event_type='closed', closure_fingerprint='f' * 64, evidence_json={},
    ))
    db.session.commit()
    result = submit_repair_request(
        mode='targeted_repair', source_domain='final_game',
        baseball_date_start=DAY, scope={'game_pk': 777123},
        reason='closed date official correction', dry_run=False, enqueue=False,
    )
    request = dispatch_repair_request(result.request.id)
    child = db.session.get(SyncJob, request.chunks[0].child_job_ids_json[0])
    child.status = 'succeeded'
    db.session.commit()
    check_repair_request(request.id, schedule_recheck=False)
    assert db.session.get(RepairRequest, request.id).status == 'running'
    closure_jobs = SyncJob.query.filter_by(job_name='check_baseball_date_closure').all()
    assert len(closure_jobs) == 1
    assert closure_jobs[0].details_json['baseball_date'] == DAY.isoformat()
    closure_jobs[0].status = 'succeeded'
    db.session.commit()
    check_repair_request(request.id, schedule_recheck=False)
    assert db.session.get(RepairRequest, request.id).status == 'completed'


def test_postgresql_concurrent_identical_requests_share_active_request(app):
    if db.session.get_bind().dialect.name != 'postgresql':
        pytest.skip('PostgreSQL-only active-request uniqueness proof')
    barrier = Barrier(2)

    def submit():
        with app.app_context():
            barrier.wait()
            result = submit_repair_request(
                mode='targeted_repair', source_domain='transactions',
                baseball_date_start=DAY, reason='concurrent repair',
                dry_run=False, enqueue=False,
            )
            return result.request.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: submit(), range(2)))
    assert len(set(ids)) == 1
    assert RepairRequest.query.count() == 1
