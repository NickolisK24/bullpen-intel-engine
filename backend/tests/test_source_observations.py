from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from threading import Barrier

import pytest
from flask import Flask
from sqlalchemy import inspect

import models.dashboard_snapshot  # noqa: F401
from models.source_observation import (
    SourceFetchAttempt,
    SourceObservation,
    SourcePayloadArtifact,
    SourceSubject,
)
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.source_observations import (
    FINGERPRINT_VERSION,
    ObservationCompleteness,
    ObservationOutcome,
    SourceProvider,
    SourceSubjectType,
    build_source_identity,
    latest_authoritative_observation,
    record_source_fetch_failure,
    record_source_observation,
    source_fingerprint,
)
from services.sync_control_plane import SourceDomain
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    dispose_test_database_engines,
    drop_test_schema,
)
from utils.db import db


BASEBALL_DATE = date(2026, 9, 5)
OBSERVED_AT = datetime(2026, 9, 5, 18, 0, 0)


@pytest.fixture
def app():
    app = Flask('test_source_observations')
    configure_test_database(app)
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)
            dispose_test_database_engines(app)


def _identity(**overrides):
    values = {
        'provider': SourceProvider.MLB_STATS_API,
        'source_domain': SourceDomain.BOXSCORE,
        'endpoint': '/game/{gamePk}/boxscore',
        'subject_type': SourceSubjectType.GAME,
        'subject_key': '777123',
        'request_parameters': {'gamePk': 777123, 'hydrate': ['team', 'person']},
        'baseball_date': BASEBALL_DATE,
    }
    values.update(overrides)
    return build_source_identity(**values)


def _record(payload, **kwargs):
    return record_source_observation(
        identity=kwargs.pop('identity', _identity()),
        payload=payload,
        observed_at=kwargs.pop('observed_at', OBSERVED_AT),
        record_count=kwargs.pop('record_count', 1),
        **kwargs,
    )


def test_request_identity_is_stable_across_parameter_ordering():
    left = _identity(request_parameters={
        'hydrate': ['team', 'person'], 'gamePk': 777123,
    })
    right = _identity(request_parameters={
        'gamePk': 777123, 'hydrate': ['team', 'person'],
    })
    changed = _identity(request_parameters={
        'gamePk': 777124, 'hydrate': ['team', 'person'],
    })

    assert left.request_identity == right.request_identity
    assert left.identity_key == right.identity_key
    assert changed.request_identity != left.request_identity
    assert changed.identity_key != left.identity_key


def test_fingerprint_is_deterministic_and_meaningful_sequences_remain_ordered():
    assert source_fingerprint({'b': 2, 'a': 1}) == source_fingerprint({'a': 1, 'b': 2})
    assert source_fingerprint({'pitches': [1, 2]}) != source_fingerprint(
        {'pitches': [2, 1]}
    )


def test_schema_supports_latest_lineage_date_and_execution_queries(app):
    with app.app_context():
        inspector = inspect(db.engine)
        assert {
            'source_subjects', 'source_payload_artifacts',
            'source_observations', 'source_fetch_attempts',
        } <= set(inspector.get_table_names())
        subject_indexes = {
            row['name'] for row in inspector.get_indexes('source_subjects')
        }
        observation_indexes = {
            row['name'] for row in inspector.get_indexes('source_observations')
        }
        assert {
            'ix_source_subjects_provider_domain',
            'ix_source_subjects_subject',
            'ix_source_subjects_baseball_date',
            'ix_source_subjects_request_identity',
        } <= subject_indexes
        assert {
            'ix_source_observations_subject_latest',
            'ix_source_observations_subject_authoritative',
            'ix_source_observations_fingerprint',
            'ix_source_observations_predecessor',
            'ix_source_observations_sync_run',
            'ix_source_observations_sync_job',
        } <= observation_indexes


def test_first_unchanged_and_changed_observations_preserve_lineage(app):
    with app.app_context():
        first = _record({'runs': 3})
        unchanged = _record({'runs': 3})
        changed = _record({'runs': 4}, correction=True)

        assert first.outcome == ObservationOutcome.NEW.value
        assert first.created is True
        assert first.changed is True
        assert first.observation.version_number == 1
        assert first.observation.fingerprint_version == FINGERPRINT_VERSION
        assert unchanged.outcome == ObservationOutcome.UNCHANGED.value
        assert unchanged.created is False
        assert unchanged.observation.id == first.observation.id
        assert changed.outcome == ObservationOutcome.CORRECTED.value
        assert changed.observation.version_number == 2
        assert changed.observation.predecessor_observation_id == first.observation.id
        assert SourceObservation.query.count() == 2
        assert SourceFetchAttempt.query.count() == 3
        assert SourcePayloadArtifact.query.count() == 2


def test_return_to_an_older_fingerprint_creates_a_new_version(app):
    with app.app_context():
        first = _record({'runs': 3})
        second = _record({'runs': 4})
        third = _record({'runs': 3})

        assert [first.observation.version_number, second.observation.version_number,
                third.observation.version_number] == [1, 2, 3]
        assert third.observation.predecessor_observation_id == second.observation.id
        assert third.observation.fingerprint == first.observation.fingerprint


def test_empty_valid_is_complete_success_and_not_failure(app):
    with app.app_context():
        result = _record([], record_count=0, empty_valid=True)

        assert result.outcome == ObservationOutcome.EMPTY_VALID.value
        assert result.observation.completeness == ObservationCompleteness.COMPLETE.value
        assert result.observation.is_authoritative is True
        assert result.fetch_attempt.status == 'succeeded'
        assert result.fetch_attempt.record_count == 0


def test_partial_does_not_replace_last_complete_authority(app):
    with app.app_context():
        complete = _record({'records': [1, 2]}, record_count=2)
        partial = _record(
            {'records': [1]},
            record_count=1,
            completeness=ObservationCompleteness.PARTIAL,
        )
        repeated = _record(
            {'records': [1]},
            record_count=1,
            completeness=ObservationCompleteness.PARTIAL,
        )

        assert partial.observation.is_authoritative is False
        assert partial.outcome == ObservationOutcome.PARTIAL.value
        assert repeated.observation.id == partial.observation.id
        assert repeated.created is False
        assert latest_authoritative_observation(complete.subject).id == complete.observation.id


def test_failure_records_attempt_without_fake_observation(app):
    with app.app_context():
        current = _record({'runs': 3})
        result = record_source_fetch_failure(
            identity=_identity(),
            error=TimeoutError('provider timed out'),
            observed_at=OBSERVED_AT,
        )

        assert result.outcome == ObservationOutcome.FAILED.value
        assert result.observation is None
        assert result.fetch_attempt.completeness == ObservationCompleteness.FAILED.value
        assert result.fetch_attempt.error_class == 'TimeoutError'
        assert SourceObservation.query.count() == 1
        assert latest_authoritative_observation(current.subject).id == current.observation.id


def test_payload_artifacts_are_content_addressed_across_subjects(app):
    with app.app_context():
        first = _record({'value': 1})
        second = _record(
            {'value': 1},
            identity=_identity(subject_key='777124'),
        )

        assert first.observation.payload_artifact_id == second.observation.payload_artifact_id
        assert SourcePayloadArtifact.query.count() == 1


def test_caller_can_own_transaction_and_disable_payload_retention(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL transaction ownership contract')
        result = _record({'value': 1}, retain_payload=False, commit=False)
        assert result.observation.payload_artifact_id is None
        assert SourceObservation.query.count() == 1

        db.session.rollback()
        assert SourceSubject.query.count() == 0
        assert SourceObservation.query.count() == 0


def test_observation_can_link_to_run_and_job_without_conflating_lifecycle(app):
    with app.app_context():
        run = SyncRun(job_name='daily_sync', status='running', stage='started')
        db.session.add(run)
        db.session.flush()
        job = SyncJob(
            job_name='fetch_game',
            job_family='source_acquisition',
            lane='internal',
            scope_type='game',
            scope_key='777123',
            product_date=BASEBALL_DATE,
            status='pending',
            max_attempts=3,
            priority=100,
            sync_run_id=run.id,
        )
        db.session.add(job)
        db.session.commit()

        result = _record(
            {'runs': 3}, sync_run_id=run.id, sync_job_id=job.id
        )

        assert result.observation.sync_run_id == run.id
        assert result.observation.sync_job_id == job.id
        assert result.fetch_attempt.sync_run_id == run.id
        assert result.fetch_attempt.sync_job_id == job.id
        assert db.session.get(SyncRun, run.id).status == 'running'
        assert db.session.get(SyncJob, job.id).status == 'pending'


def _concurrent_record(app, identity, payload, barrier):
    with app.app_context():
        barrier.wait(timeout=10)
        result = record_source_observation(
            identity=identity,
            payload=payload,
            record_count=1,
        )
        observation_id = result.observation.id
        db.session.remove()
        return observation_id


def test_concurrent_identical_first_observation_creates_one_version_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL source-observation concurrency contract')
    identity = _identity()
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_concurrent_record, app, identity, {'runs': 3}, barrier)
            for _ in range(2)
        ]
        ids = [future.result(timeout=15) for future in futures]

    with app.app_context():
        assert ids[0] == ids[1]
        assert SourceObservation.query.count() == 1
        assert SourceFetchAttempt.query.count() == 2


def test_concurrent_changed_observation_creates_one_v2_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL source-observation concurrency contract')
        first = _record({'runs': 3})
        first_id = first.observation.id
    identity = _identity()
    barrier = Barrier(2)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(_concurrent_record, app, identity, {'runs': 4}, barrier)
            for _ in range(2)
        ]
        ids = [future.result(timeout=15) for future in futures]

    with app.app_context():
        assert ids[0] == ids[1]
        assert SourceObservation.query.count() == 2
        second = db.session.get(SourceObservation, ids[0])
        assert second.version_number == 2
        assert second.predecessor_observation_id == first_id
        assert SourceFetchAttempt.query.count() == 3
