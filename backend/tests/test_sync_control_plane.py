from datetime import date, datetime

import pytest
from flask import Flask
from sqlalchemy import inspect

from models.sync_failure import SyncFailure
from models.sync_run import SyncRun, SyncRunScope
from services import sync_control_plane as control_plane
from services import sync_metadata
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


BASEBALL_DATE = date(2026, 9, 4)


@pytest.fixture
def app():
    app = Flask('test_sync_control_plane')
    configure_test_database(app)
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_control_plane_vocabulary_covers_future_pipeline_lanes():
    assert {item.value for item in control_plane.RunType} == {
        'schedule_game_state',
        'roster_transactions',
        'pregame_context',
        'live_game',
        'final_game_reconciliation',
        'incremental_intelligence',
        'publication',
        'morning_reconciliation',
        'nightly_finalization',
        'targeted_repair',
        'backfill',
        'full_reconciliation',
    }
    assert {'pending', 'running', 'success', 'partial', 'failed', 'cancelled'} == {
        item.value for item in control_plane.RunStatus
    }


def test_pending_run_creation_start_and_queryable_scope(app):
    created_at = datetime(2026, 9, 5, 2, 15, 0)
    with app.app_context():
        run = control_plane.create_run(
            run_type=control_plane.RunType.FINAL_GAME_RECONCILIATION,
            trigger_type=control_plane.TriggerType.GAME_FINAL,
            source='test',
            job_name='sp01_test',
            baseball_date=BASEBALL_DATE,
            source_domain=control_plane.SourceDomain.BOXSCORE,
            started_at=created_at,
            scopes=control_plane.scope_entries(
                game_pks=(777001,),
                team_ids=(110, 147),
                pitcher_ids=(605400,),
                source_domains=(control_plane.SourceDomain.BOXSCORE,),
            ),
        )

        assert run.status == control_plane.RunStatus.PENDING.value
        assert run.stage == control_plane.RunStage.PENDING.value
        assert run.baseball_date == BASEBALL_DATE
        assert run.started_at == created_at
        assert len(run.correlation_id) == 36
        assert control_plane.runs_for_baseball_date(BASEBALL_DATE).one().id == run.id
        assert control_plane.runs_for_scope(
            control_plane.ScopeType.GAME, 777001
        ).one().id == run.id
        assert control_plane.runs_for_scope(
            control_plane.ScopeType.TEAM, 147
        ).one().id == run.id
        assert control_plane.runs_for_scope(
            control_plane.ScopeType.PITCHER, 605400
        ).one().id == run.id

        control_plane.start_run(run)
        control_plane.mark_stage(run, control_plane.RunStage.CANONICALIZE)
        assert run.status == control_plane.RunStatus.RUNNING.value
        assert run.stage == control_plane.RunStage.CANONICALIZE.value


def test_scope_table_is_unique_and_indexed(app):
    with app.app_context():
        inspector = inspect(db.engine)
        assert 'sync_run_scopes' in inspector.get_table_names()
        indexes = {item['name'] for item in inspector.get_indexes('sync_run_scopes')}
        assert 'ix_sync_run_scopes_type_key_run' in indexes

        run = control_plane.start_run(
            run_type=control_plane.RunType.LIVE_GAME,
            trigger_type=control_plane.TriggerType.SOURCE_CHANGE,
            source='test',
            job_name='scope_test',
        )
        entries = control_plane.scope_entries(team_ids=(110, 110))
        control_plane.add_scopes(run, entries)
        control_plane.add_scopes(run, entries)
        assert SyncRunScope.query.count() == 1


def test_zero_mutation_is_a_successful_first_class_outcome(app):
    with app.app_context():
        run = control_plane.start_run(
            run_type=control_plane.RunType.SCHEDULE_GAME_STATE,
            trigger_type=control_plane.TriggerType.SCHEDULED,
            source='test',
            job_name='zero_mutation_test',
            baseball_date=BASEBALL_DATE,
        )
        control_plane.record_outcome(
            run,
            source_reads=12,
            source_changes=0,
            canonical_mutations=0,
        )
        control_plane.finalize_run(
            run,
            control_plane.RunStatus.SUCCEEDED,
            stage=control_plane.RunStage.RECONCILE,
        )

        assert run.status == 'success'
        assert run.source_reads == 12
        assert run.source_changes == 0
        assert run.canonical_mutations == 0
        assert run.zero_mutation is True


def test_parent_child_inherits_correlation_without_delete_cascade(app):
    with app.app_context():
        parent = control_plane.start_run(
            run_type=control_plane.RunType.FINAL_GAME_RECONCILIATION,
            trigger_type=control_plane.TriggerType.GAME_FINAL,
            source='test',
            job_name='parent',
        )
        child = control_plane.start_run(
            run_type=control_plane.RunType.INCREMENTAL_INTELLIGENCE,
            trigger_type=control_plane.TriggerType.PARENT_RUN,
            source='test',
            job_name='child',
            parent_sync_run_id=parent.id,
        )

        assert child.parent_sync_run_id == parent.id
        assert child.correlation_id == parent.correlation_id
        assert parent.children == [child]

        db.session.delete(parent)
        db.session.commit()
        assert db.session.get(SyncRun, child.id) is not None


def test_partial_and_failure_are_associated_with_run_stage_and_domain(app):
    with app.app_context():
        run = control_plane.start_run(
            run_type=control_plane.RunType.FINAL_GAME_RECONCILIATION,
            trigger_type=control_plane.TriggerType.GAME_FINAL,
            source='test',
            job_name='partial_test',
            source_domain=control_plane.SourceDomain.BOXSCORE,
        )
        control_plane.mark_stage(run, control_plane.RunStage.ACQUIRE)
        failure = control_plane.record_failure(
            run,
            TimeoutError('optional PBP timed out'),
            failure_class=control_plane.FailureClass.TIMEOUT,
            stage=control_plane.RunStage.ACQUIRE,
            source_domain=control_plane.SourceDomain.PLAY_BY_PLAY,
            entity_type=control_plane.ScopeType.GAME.value,
            entity_ref='777001',
            retryable=True,
        )
        control_plane.record_outcome(run, warnings_count=1)
        control_plane.finalize_run(
            run,
            control_plane.RunStatus.PARTIAL,
            stage=control_plane.RunStage.RECONCILE,
        )

        stored = db.session.get(SyncFailure, failure.id)
        assert run.status == 'partial'
        assert stored.sync_run_id == run.id
        assert stored.stage == 'acquire'
        assert stored.failure_class == 'timeout'
        assert stored.source_domain == 'play_by_play'
        assert stored.entity_type == 'game'
        assert stored.retryable is True


def test_failed_run_preserves_terminal_stage_and_failed_stage(app):
    with app.app_context():
        run = control_plane.start_run(
            run_type=control_plane.RunType.PUBLICATION,
            trigger_type=control_plane.TriggerType.PARENT_RUN,
            source='test',
            job_name='failed_test',
        )
        control_plane.mark_stage(run, control_plane.RunStage.PUBLISH)
        control_plane.finalize_run(
            run,
            control_plane.RunStatus.FAILED,
            stage=control_plane.RunStage.FAILED,
            failed_stage=control_plane.RunStage.PUBLISH,
        )

        assert run.status == 'failed'
        assert run.stage == 'failed'
        assert run.failed_stage == 'publish'
        assert run.completed_at is not None


def test_repeated_finalization_does_not_corrupt_terminal_record(app):
    first_completed_at = datetime(2026, 9, 5, 4, 0, 0)
    with app.app_context():
        run = control_plane.start_run(
            run_type=control_plane.RunType.PUBLICATION,
            trigger_type=control_plane.TriggerType.PARENT_RUN,
            source='test',
            job_name='idempotence_test',
        )
        control_plane.finalize_run(
            run,
            control_plane.RunStatus.SUCCEEDED,
            stage=control_plane.RunStage.PUBLISHED,
            completed_at=first_completed_at,
        )
        control_plane.finalize_run(
            run,
            control_plane.RunStatus.FAILED,
            stage=control_plane.RunStage.FAILED,
            completed_at=datetime(2026, 9, 5, 5, 0, 0),
        )

        assert run.status == 'success'
        assert run.stage == 'published'
        assert run.completed_at == first_completed_at


def test_legacy_sync_metadata_boundary_uses_control_plane(app):
    with app.app_context():
        run_id = sync_metadata.start_sync_run(
            source='test',
            job_name=sync_metadata.JOB_DAILY_SYNC,
            baseball_date=BASEBALL_DATE,
            scopes=control_plane.scope_entries(league=True),
        )
        sync_metadata.finish_sync_run(
            run_id,
            status=sync_metadata.STATUS_SUCCESS,
            source_reads=3,
            source_changes=0,
            canonical_mutations=0,
            stage=sync_metadata.STAGE_LOG_INGESTION,
        )
        run = db.session.get(SyncRun, run_id)

        assert run.run_type == control_plane.RunType.FULL_RECONCILIATION.value
        assert run.trigger_type == control_plane.TriggerType.MANUAL.value
        assert run.status == sync_metadata.STATUS_SUCCESS
        assert run.stage == sync_metadata.STAGE_LOG_INGESTION
        assert run.zero_mutation is True
        assert run.scopes[0].to_dict() == {
            'scope_type': 'league',
            'scope_key': 'mlb',
        }


def test_invalid_vocabulary_is_rejected_before_persistence(app):
    with app.app_context(), pytest.raises(ValueError, match='Unsupported RunType'):
        control_plane.create_run(
            run_type='invented_lane',
            trigger_type=control_plane.TriggerType.MANUAL,
            source='test',
            job_name='invalid',
        )
        assert SyncRun.query.count() == 0


def test_legacy_scope_wrapper_keeps_telemetry_best_effort(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            control_plane,
            'add_scopes',
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                ValueError('invalid telemetry scope')
            ),
        )
        assert sync_metadata.add_sync_scopes(91, ()) is None
