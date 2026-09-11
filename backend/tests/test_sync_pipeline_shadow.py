from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from flask import Flask

from models.atomic_publication import AtomicPublicationCurrent
from models.source_observation import SourceObservation
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services import adaptive_game_state
from services.sync_pipeline_certification import ActivationControls, EXPECTED_MIGRATION_HEAD
from services.sync_pipeline_shadow import (
    DOWNSTREAM_JOB_RESERVE,
    FORBIDDEN_JOB_TYPES,
    SAFE_JOB_TYPES,
    ShadowConfigurationError,
    production_shadow_handlers,
    run_production_shadow_cycle,
    shadow_job_type_passes,
    validate_shadow_controls,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db

import models.dashboard_snapshot  # noqa: F401
import models.prospect  # noqa: F401


SLATE = date(2026, 9, 9)
NOW = datetime(2026, 9, 9, 14, 0)
SAFE_ENV = {
    'DATABASE_MIGRATION_MODE': 'verify_only',
    'SYNC_PIPELINE_ENABLED': 'true',
    'SYNC_PIPELINE_SHADOW_MODE': 'true',
    'SYNC_PIPELINE_PUBLICATION_ENABLED': 'false',
    'SYNC_PIPELINE_MORNING_ENABLED': 'false',
    'SYNC_PIPELINE_CLOSURE_ENABLED': 'false',
    'BASEBALLOS_LEGACY_PUBLICATION_ENABLED': 'true',
    'BASEBALLOS_LEGACY_SCHEDULERS_ENABLED': 'true',
}
WORKFLOW_PATH = Path(__file__).resolve().parents[2] / '.github/workflows/baseballos-sync.yml'


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


def _game():
    return {
        'gamePk': 889901,
        'officialDate': SLATE.isoformat(),
        'gameDate': '2026-09-09T23:10:00Z',
        'gameType': 'R',
        'gameNumber': 1,
        'doubleHeader': 'N',
        'status': {
            'statusCode': 'S',
            'detailedState': 'Scheduled',
            'abstractGameState': 'Preview',
        },
        'teams': {
            'home': {'team': {'id': 110}},
            'away': {'team': {'id': 111}},
        },
    }


class TeamsClient:
    def get_all_teams(self):
        return [{'id': value} for value in range(101, 131)]


def test_shadow_configuration_requires_pipeline_and_preserves_legacy_authority():
    controls = ActivationControls.from_environment(SAFE_ENV)
    assert validate_shadow_controls(controls) == ()

    pipeline_off = dict(SAFE_ENV, SYNC_PIPELINE_ENABLED='false')
    assert 'SYNC_PIPELINE_SHADOW_MODE_requires_SYNC_PIPELINE_ENABLED' in (
        validate_shadow_controls(ActivationControls.from_environment(pipeline_off))
    )
    publication_on = dict(SAFE_ENV, SYNC_PIPELINE_PUBLICATION_ENABLED='true')
    assert 'shadow_mode_cannot_publish' in (
        validate_shadow_controls(ActivationControls.from_environment(publication_on))
    )
    assert validate_shadow_controls(ActivationControls(
        pipeline_enabled=True, shadow_mode=False, publication_enabled=True,
        legacy_publication_enabled=True, legacy_schedulers_enabled=True,
    ))


def test_shadow_worker_allowlist_is_consumable_and_excludes_publication():
    handlers = production_shadow_handlers()
    assert set(handlers) == {item.value for item in SAFE_JOB_TYPES}
    assert not set(handlers).intersection(FORBIDDEN_JOB_TYPES)
    assert 'fetch_schedule' in handlers
    assert 'fetch_roster' in handlers
    assert 'fetch_transactions' in handlers
    assert 'process_derived_intelligence' in handlers


def test_shadow_morning_runs_once_and_reserves_bounded_roster_consumption(app):
    handlers = {
        item.value: (lambda job: {'handled': job.job_name})
        for item in SAFE_JOB_TYPES
    }
    first = run_production_shadow_cycle(
        now=NOW,
        baseball_date=SLATE,
        max_jobs=2,
        worker_id='shadow-morning-one',
        env=SAFE_ENV,
        migration_head_reader=lambda: (EXPECTED_MIGRATION_HEAD,),
        handlers=handlers,
        include_morning=True,
        morning_client=TeamsClient(),
    )
    second = run_production_shadow_cycle(
        now=NOW,
        baseball_date=SLATE,
        max_jobs=2,
        worker_id='shadow-morning-two',
        env=SAFE_ENV,
        migration_head_reader=lambda: (EXPECTED_MIGRATION_HEAD,),
        handlers=handlers,
        include_morning=True,
        morning_client=TeamsClient(),
    )

    assert first['morning_plan']['created'] is True
    assert second['morning_plan']['created'] is False
    assert first['morning_plan']['run_id'] == second['morning_plan']['run_id']
    assert all(
        row['job_type'] in {'fetch_roster', 'fetch_transactions'}
        for row in first['processed_jobs'] + second['processed_jobs']
    )
    assert SyncJob.query.filter_by(job_name='fetch_roster').count() == 30
    assert SyncJob.query.filter_by(job_name='fetch_transactions').count() == 1
    assert SyncJob.query.filter_by(job_name='publish_derived_cohort').count() == 0
    assert SyncJob.query.filter_by(job_name='check_baseball_date_closure').count() == 0
    assert first['publication_pointer_before'] == first['publication_pointer_after']
    assert second['publication_pointer_before'] == second['publication_pointer_after']


def test_shadow_cycle_reserves_downstream_capacity_after_acquisition():
    passes = shadow_job_type_passes(max_jobs=24, include_morning=True)

    assert len(passes) == 24
    assert passes[:12] == (('fetch_roster', 'fetch_transactions'),) * 12
    assert passes[12:18] == (SAFE_JOB_TYPES,) * 6
    assert passes[-DOWNSTREAM_JOB_RESERVE:] == (
        ('process_canonical_impact', 'process_derived_intelligence'),
    ) * DOWNSTREAM_JOB_RESERVE


def test_shadow_cycle_creates_run_job_and_source_lineage_without_pointer_change(
    app, monkeypatch,
):
    monkeypatch.setattr(
        'services.schedule_ingestion.mlb_client.get_schedule',
        lambda **_kwargs: [_game()],
    )
    result = run_production_shadow_cycle(
        now=NOW,
        baseball_date=SLATE,
        max_jobs=1,
        worker_id='shadow-test',
        env=SAFE_ENV,
        migration_head_reader=lambda: (EXPECTED_MIGRATION_HEAD,),
    )

    assert result['status'] == 'success'
    assert result['processed_job_ids'] == [result['seed_job_id']]
    assert result['sync_run_ids']
    assert result['source_observation_ids']
    assert result['processed_jobs'][0]['scope_key'] == '2026-09-09'
    assert result['source_observations'] == [{
        'id': result['source_observation_ids'][0],
        'sync_job_id': result['seed_job_id'],
        'sync_run_id': result['sync_run_ids'][0],
        'source_domain': 'schedule',
        'subject_type': 'date_range',
        'subject_key': '2026-09-09:2026-09-09',
        'version_number': 1,
        'outcome': 'new',
        'completeness': 'complete',
        'observed_at': result['source_observations'][0]['observed_at'],
    }]
    assert SyncRun.query.filter(SyncRun.id.in_(result['sync_run_ids'])).count() == 1
    assert SourceObservation.query.filter(
        SourceObservation.id.in_(result['source_observation_ids'])
    ).count() == 1
    assert db.session.get(SyncJob, result['seed_job_id']).status == 'succeeded'
    assert result['publication_pointer_before'] is None
    assert result['publication_pointer_after'] is None
    assert db.session.get(AtomicPublicationCurrent, 1) is None


def test_shadow_disabled_stops_before_planning_and_keeps_history(app):
    old = SyncJob(
        job_name='fetch_schedule', job_family='sync_pipeline_shadow',
        lane='sync_pipeline', scope_type='baseball_date', scope_key='2026-09-08',
        product_date=date(2026, 9, 8), payload_schema_version=1,
        dedupe_key='old-shadow-proof', priority=10, status='succeeded',
        attempts=1, max_attempts=3,
    )
    db.session.add(old)
    db.session.commit()
    disabled = dict(SAFE_ENV, SYNC_PIPELINE_SHADOW_MODE='false')

    with pytest.raises(ShadowConfigurationError):
        run_production_shadow_cycle(
            now=NOW,
            baseball_date=SLATE,
            env=disabled,
            migration_head_reader=lambda: (EXPECTED_MIGRATION_HEAD,),
        )

    assert SyncJob.query.count() == 1
    assert db.session.get(SyncJob, old.id).status == 'succeeded'


def test_shadow_cycle_rejects_a_publication_handler_before_claiming(app):
    handlers = production_shadow_handlers()
    handlers['publish_derived_cohort'] = lambda _job: {}
    with pytest.raises(ShadowConfigurationError, match='forbidden_job_type'):
        run_production_shadow_cycle(
            now=NOW,
            baseball_date=SLATE,
            env=SAFE_ENV,
            migration_head_reader=lambda: (EXPECTED_MIGRATION_HEAD,),
            handlers=handlers,
        )
    assert SyncJob.query.count() == 0


def test_manual_production_workflow_isolated_from_public_and_legacy_jobs():
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding='utf-8'))
    job = workflow['jobs']['sync-pipeline-shadow']
    assert "inputs.mode == 'shadow_sp'" in job['if']
    assert 'schedule' not in job['if']
    step = next(row for row in job['steps'] if row.get('name') == 'Run bounded production shadow cycle')
    assert step['env'] == {
        'APP_ENV': 'production',
        'DATABASE_URL': '${{ secrets.DATABASE_URL }}',
        'SECRET_KEY': '${{ secrets.SECRET_KEY }}',
        'ADMIN_API_TOKEN': '${{ secrets.BASEBALLOS_ADMIN_API_TOKEN }}',
        'AUTO_SYNC': 'false',
        'SYNC_PIPELINE_DEPLOY_SHA': '${{ github.sha }}',
        **SAFE_ENV,
    }
    assert 'db upgrade' not in step['run']
    assert 'scripts.database_migrations verify' in step['run']
    assert 'run_sync_pipeline_shadow.py' in step['run']
    assert '--include-continuous-observation' in step['run']
    assert '--include-morning' in step['run']
    assert 'run_continuous_cycle.py' not in step['run']
    assert 'publish' not in step['run'].lower()
    public_condition = workflow['jobs']['public-sync']['if']
    assert "inputs.mode == 'shadow_sp'" in public_condition
