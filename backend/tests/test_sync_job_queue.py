from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from threading import Barrier, Event

import pytest
from flask import Flask
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.sync_job import SyncJob, SyncJobAttempt
from models.sync_run import SyncRun
from services import sync_jobs, sync_metadata
from utils.db import db


PRODUCT_DATE = date(2026, 9, 5)
T0 = datetime(2026, 9, 5, 12, 0, 0)


@pytest.fixture
def app():
    app = Flask('test_sync_job_queue')
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _enqueue(
    *,
    dedupe_key='FETCH_GAME:777123:v1',
    scope_key='777123',
    priority=100,
    available_at=T0,
    max_attempts=3,
    sync_run_id=None,
    parent_job_id=None,
):
    return sync_jobs.enqueue_job(
        job_type=sync_jobs.JobType.FETCH_GAME,
        scope_type=sync_jobs.JobScopeType.GAME,
        scope_key=scope_key,
        product_date=PRODUCT_DATE,
        dedupe_key=dedupe_key,
        payload={'game_pk': 777123, 'source_version': 'v1'},
        payload_schema_version=1,
        priority=priority,
        max_attempts=max_attempts,
        available_at=available_at,
        sync_run_id=sync_run_id,
        parent_job_id=parent_job_id,
    )


def _run():
    run = SyncRun(
        job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
        status=sync_metadata.STATUS_RUNNING,
        stage=sync_metadata.STAGE_STARTED,
        source='test',
        started_at=T0,
        created_at=T0,
    )
    db.session.add(run)
    db.session.commit()
    return run


def test_schema_has_queue_indexes_attempt_table_and_active_dedupe(app):
    with app.app_context():
        inspector = inspect(db.engine)
        indexes = {row['name'] for row in inspector.get_indexes('sync_jobs')}
        assert {
            'ix_sync_jobs_claim_ready',
            'ix_sync_jobs_lease_expiry',
            'uq_sync_jobs_active_dedupe_key',
        } <= indexes
        assert 'sync_job_attempts' in inspector.get_table_names()

        first = _enqueue()
        duplicate = SyncJob(
            job_name=first.job_name,
            job_family=first.job_family,
            lane=first.lane,
            scope_type=first.scope_type,
            scope_key=first.scope_key,
            product_date=first.product_date,
            dedupe_key=first.dedupe_key,
            priority=first.priority,
            status=sync_jobs.STATUS_PENDING,
            max_attempts=3,
            available_at=T0,
            created_at=T0,
            updated_at=T0,
        )
        db.session.add(duplicate)
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_enqueue_validates_and_preserves_payload_priority_availability_and_run(app):
    with app.app_context():
        run = _run()
        job = _enqueue(priority=7, available_at=T0 + timedelta(hours=1), sync_run_id=run.id)

        assert job.status == sync_jobs.STATUS_PENDING
        assert job.job_name == sync_jobs.JobType.FETCH_GAME.value
        assert job.scope_type == sync_jobs.JobScopeType.GAME.value
        assert job.details_json == {'game_pk': 777123, 'source_version': 'v1'}
        assert job.payload_schema_version == 1
        assert job.priority == 7
        assert job.first_available_at == T0 + timedelta(hours=1)
        assert job.available_at == T0 + timedelta(hours=1)
        assert job.sync_run_id == run.id
        assert job.attempts == 0

        with pytest.raises(sync_jobs.InvalidJobError):
            sync_jobs.enqueue_job(
                job_type='invented_job',
                scope_type='game',
                scope_key='1',
                product_date=PRODUCT_DATE,
                dedupe_key='bad',
            )


def test_repeated_enqueue_returns_active_job_and_new_version_can_coexist(app):
    with app.app_context():
        first = _enqueue()
        repeated = _enqueue(priority=999)
        next_version = _enqueue(
            dedupe_key='FETCH_GAME:777123:v2',
            scope_key='777123',
        )

        assert repeated.id == first.id
        assert repeated.priority == 100
        assert next_version.id != first.id
        assert SyncJob.query.count() == 2


def test_terminal_job_releases_dedupe_identity_without_losing_payload(app):
    with app.app_context():
        first = _enqueue()
        claimed = sync_jobs.claim_next_job('worker-a', now=T0)
        token = claimed.claim_token
        sync_jobs.succeed_job(
            first.id,
            worker_id='worker-a',
            claim_token=token,
            result={'rows': 4},
            now=T0 + timedelta(seconds=1),
        )

        replacement = _enqueue()
        assert replacement.id != first.id
        assert db.session.get(SyncJob, first.id).details_json == {
            'game_pk': 777123,
            'source_version': 'v1',
        }
        assert db.session.get(SyncJob, first.id).result_json == {'rows': 4}
        assert db.session.get(SyncJob, first.id).claimed_at == T0


def test_claim_respects_availability_priority_and_terminal_states(app):
    with app.app_context():
        future = _enqueue(
            dedupe_key='future', scope_key='future', priority=0,
            available_at=T0 + timedelta(minutes=5),
        )
        normal = _enqueue(
            dedupe_key='normal', scope_key='normal', priority=100,
        )
        high = _enqueue(
            dedupe_key='high', scope_key='high', priority=10,
        )
        terminal = _enqueue(
            dedupe_key='terminal', scope_key='terminal', priority=1,
        )
        terminal.status = sync_jobs.STATUS_SUCCEEDED
        terminal.completed_at = T0
        db.session.commit()

        claimed = sync_jobs.claim_next_job('worker-a', now=T0)
        assert claimed.id == high.id
        sync_jobs.succeed_job(
            claimed.id,
            worker_id='worker-a',
            claim_token=claimed.claim_token,
            now=T0 + timedelta(seconds=1),
        )
        second = sync_jobs.claim_next_job('worker-a', now=T0 + timedelta(seconds=2))
        assert second.id == normal.id
        assert second.id not in {future.id, terminal.id}


def test_claim_records_fenced_attempt_and_live_lease_is_not_stolen(app):
    with app.app_context():
        job = _enqueue()
        claimed = sync_jobs.claim_next_job(
            'worker-a', lease_seconds=30, now=T0
        )
        assert claimed.id == job.id
        assert claimed.status == sync_jobs.STATUS_RUNNING
        assert claimed.worker_id == 'worker-a'
        assert claimed.claim_token
        assert claimed.claimed_at == T0
        assert claimed.lease_until == T0 + timedelta(seconds=30)
        assert claimed.attempts == 1
        assert SyncJobAttempt.query.filter_by(sync_job_id=job.id).count() == 1

        with pytest.raises(sync_jobs.LeaseOwnershipError):
            sync_jobs.succeed_job(
                job.id,
                worker_id='worker-b',
                claim_token=claimed.claim_token,
                now=T0 + timedelta(seconds=10),
            )
        assert sync_jobs.claim_next_job(
            'worker-b', now=T0 + timedelta(seconds=20)
        ) is None


def test_heartbeat_is_owner_safe_bounded_and_cannot_revive_expired_lease(app):
    with app.app_context():
        claimed = sync_jobs.claim_next_job('worker-a', now=T0) if _enqueue() else None
        token = claimed.claim_token

        with pytest.raises(sync_jobs.LeaseOwnershipError):
            sync_jobs.heartbeat_job(
                claimed.id,
                worker_id='worker-b',
                claim_token=token,
                now=T0 + timedelta(seconds=10),
            )

        extended = sync_jobs.heartbeat_job(
            claimed.id,
            worker_id='worker-a',
            claim_token=token,
            extension_seconds=300,
            max_lease_seconds=600,
            now=T0 + timedelta(seconds=10),
        )
        assert extended.lease_until == T0 + timedelta(seconds=310)

        with pytest.raises(sync_jobs.LeaseExpiredError):
            sync_jobs.heartbeat_job(
                claimed.id,
                worker_id='worker-a',
                claim_token=token,
                now=T0 + timedelta(seconds=311),
            )


def test_retry_wait_backoff_and_attempt_exhaustion_are_durable(app):
    with app.app_context():
        job = _enqueue(max_attempts=2)
        first = sync_jobs.claim_next_job('worker-a', now=T0)
        sync_jobs.retry_job(
            job.id,
            RuntimeError('temporary'),
            worker_id='worker-a',
            claim_token=first.claim_token,
            retry_after_seconds=10,
            now=T0 + timedelta(seconds=1),
        )
        assert job.status == sync_jobs.STATUS_RETRY_WAIT
        assert job.first_available_at == T0
        assert job.available_at == T0 + timedelta(seconds=11)
        assert job.error_type == 'RuntimeError'
        assert sync_jobs.claim_next_job(
            'worker-b', now=T0 + timedelta(seconds=10)
        ) is None

        second = sync_jobs.claim_next_job(
            'worker-b', now=T0 + timedelta(seconds=11)
        )
        assert second.attempts == 2
        sync_jobs.retry_job(
            job.id,
            RuntimeError('still failing'),
            worker_id='worker-b',
            claim_token=second.claim_token,
            now=T0 + timedelta(seconds=12),
        )
        assert job.status == sync_jobs.STATUS_DEAD
        assert job.dead_at == T0 + timedelta(seconds=12)
        assert job.completed_at == job.dead_at
        assert job.attempts == 2
        assert [row.outcome for row in job.attempt_history.order_by(
            SyncJobAttempt.attempt_number
        )] == [sync_jobs.STATUS_RETRY_WAIT, sync_jobs.STATUS_DEAD]


def test_retry_uses_bounded_deterministic_exponential_backoff(app):
    with app.app_context():
        job = _enqueue()
        claimed = sync_jobs.claim_next_job('worker-a', now=T0)
        expected = sync_jobs.retry_delay_seconds(
            job_id=job.id,
            attempt_count=1,
        )
        assert 24 <= expected <= 36
        assert expected == sync_jobs.retry_delay_seconds(
            job_id=job.id,
            attempt_count=1,
        )

        sync_jobs.retry_job(
            job.id,
            RuntimeError('temporary'),
            worker_id='worker-a',
            claim_token=claimed.claim_token,
            now=T0 + timedelta(seconds=1),
        )
        assert job.available_at == T0 + timedelta(seconds=1 + expected)
        assert sync_jobs.retry_delay_seconds(
            job_id=job.id,
            attempt_count=99,
        ) <= sync_jobs.DEFAULT_RETRY_MAX_SECONDS


def test_nonretryable_failure_goes_dead_immediately(app):
    with app.app_context():
        job = _enqueue(max_attempts=5)
        claimed = sync_jobs.claim_next_job('worker-a', now=T0)
        sync_jobs.dead_job(
            job.id,
            ValueError('invalid payload'),
            worker_id='worker-a',
            claim_token=claimed.claim_token,
            now=T0 + timedelta(seconds=1),
        )
        assert job.status == sync_jobs.STATUS_DEAD
        assert job.attempts == 1
        assert job.error_type == 'ValueError'


def test_crash_recovery_reclaims_expired_lease_and_rejects_stale_completion(app):
    with app.app_context():
        job = _enqueue()
        worker_a = sync_jobs.claim_next_job(
            'worker-a', lease_seconds=10, now=T0
        )
        stale_token = worker_a.claim_token

        worker_b = sync_jobs.claim_next_job(
            'worker-b', lease_seconds=10, now=T0 + timedelta(seconds=11)
        )
        current_token = worker_b.claim_token
        assert worker_b.id == job.id
        assert current_token != stale_token
        assert worker_b.attempts == 2

        sync_jobs.succeed_job(
            job.id,
            worker_id='worker-b',
            claim_token=current_token,
            now=T0 + timedelta(seconds=12),
        )
        with pytest.raises((sync_jobs.JobStateError, sync_jobs.LeaseOwnershipError)):
            sync_jobs.succeed_job(
                job.id,
                worker_id='worker-a',
                claim_token=stale_token,
                now=T0 + timedelta(seconds=13),
            )

        attempts = job.attempt_history.order_by(SyncJobAttempt.attempt_number).all()
        assert [(row.worker_id, row.outcome) for row in attempts] == [
            ('worker-a', 'lease_expired'),
            ('worker-b', sync_jobs.STATUS_SUCCEEDED),
        ]


def test_job_failure_does_not_finalize_or_mutate_sync_run(app):
    with app.app_context():
        run = _run()
        job = _enqueue(sync_run_id=run.id)
        claimed = sync_jobs.claim_next_job('worker-a', now=T0)
        sync_jobs.retry_job(
            job.id,
            RuntimeError('queue failure'),
            worker_id='worker-a',
            claim_token=claimed.claim_token,
            retryable=False,
            now=T0 + timedelta(seconds=1),
        )
        db.session.refresh(run)
        assert run.status == sync_metadata.STATUS_RUNNING
        assert sync_jobs.job_state_summary(run.id)['counts'] == {
            sync_jobs.STATUS_DEAD: 1,
        }


def test_parent_job_is_queryable_and_parent_delete_preserves_child(app):
    with app.app_context():
        parent = _enqueue(dedupe_key='parent', scope_key='parent')
        child = _enqueue(
            dedupe_key='child', scope_key='child', parent_job_id=parent.id
        )
        assert child.parent_job_id == parent.id
        assert parent.children.one().id == child.id

        db.session.delete(parent)
        db.session.commit()
        db.session.refresh(child)
        assert child.parent_job_id is None


def test_execution_engine_runs_one_job_and_preserves_original_exception(app):
    with app.app_context():
        job = _enqueue()
        completed = sync_jobs.run_next_job(
            'worker-a',
            {sync_jobs.JobType.FETCH_GAME.value: lambda claimed: {'job': claimed.id}},
        )
        assert completed.id == job.id
        assert completed.status == sync_jobs.STATUS_SUCCEEDED

        failing = _enqueue(dedupe_key='failing', scope_key='failing')

        def _fail(_job):
            raise LookupError('handler failed')

        with pytest.raises(LookupError, match='handler failed'):
            sync_jobs.run_next_job(
                'worker-b',
                {sync_jobs.JobType.FETCH_GAME.value: _fail},
            )
        assert db.session.get(SyncJob, failing.id).status == sync_jobs.STATUS_RETRY_WAIT


def test_concurrent_enqueue_collapses_to_one_active_job_on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL concurrency contract')

    barrier = Barrier(2)

    def _enqueue_in_thread():
        with app.app_context():
            barrier.wait(timeout=10)
            job = _enqueue(dedupe_key='concurrent', scope_key='concurrent')
            return job.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: _enqueue_in_thread(), range(2)))

    with app.app_context():
        assert ids[0] == ids[1]
        assert SyncJob.query.filter_by(dedupe_key='concurrent').count() == 1


def test_postgresql_skip_locked_claims_different_rows_without_double_ownership(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL SKIP LOCKED contract')
        first = _enqueue(dedupe_key='locked-first', scope_key='first', priority=1)
        second = _enqueue(dedupe_key='locked-second', scope_key='second', priority=2)
        first_id, second_id = first.id, second.id

    locked = Event()
    release = Event()

    def _hold_first_claim():
        with app.app_context():
            claimed = sync_jobs.claim_next_job('worker-a', now=T0, commit=False)
            locked.set()
            release.wait(timeout=10)
            db.session.commit()
            return claimed.id

    def _claim_while_locked():
        assert locked.wait(timeout=10)
        with app.app_context():
            claimed = sync_jobs.claim_next_job('worker-b', now=T0)
            return claimed.id if claimed else None

    with ThreadPoolExecutor(max_workers=2) as pool:
        held_future = pool.submit(_hold_first_claim)
        second_future = pool.submit(_claim_while_locked)
        claimed_second = second_future.result(timeout=15)
        release.set()
        claimed_first = held_future.result(timeout=15)

    assert claimed_first == first_id
    assert claimed_second == second_id
    with app.app_context():
        rows = SyncJob.query.filter(SyncJob.id.in_((first_id, second_id))).all()
        assert {row.worker_id for row in rows} == {'worker-a', 'worker-b'}
