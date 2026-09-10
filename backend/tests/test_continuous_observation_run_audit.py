from datetime import date, datetime

from flask import Flask

from models.sync_failure import SyncFailure
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from scripts.inspect_continuous_observation_runs import inspect_runs
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


def test_report_is_read_only_and_exposes_exact_failure_evidence():
    app = Flask(__name__)
    configure_test_database(app)
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            run = SyncRun(
                id=6498,
                job_name='continuous_cycle',
                status='partial',
                stage='continuous_complete',
                source='continuous',
                started_at=datetime(2026, 9, 10, 0, 6, 21),
                records_failed=2,
                warnings_count=2,
                outcome_json={'unchanged_games': 1},
                error_message=(
                    '{"failures":[{"scope":"observation","error":"stale"}]}'
                ),
            )
            db.session.add(run)
            # SyncFailure intentionally has no ORM relationship to SyncRun, so
            # make the parent durable before PostgreSQL enforces the FK.
            db.session.flush()
            db.session.add(SyncFailure(
                sync_run_id=6498,
                job_name='continuous_cycle',
                entity_type='game',
                entity_ref='823172',
                failure_class='stale_observation',
                stage='observation',
                retryable=False,
                error='older_upstream_observation',
            ))
            db.session.add(SyncJob(
                id=328,
                job_name='continuous_final_game_reconciliation',
                job_family='continuous_final_game',
                lane='internal',
                scope_key='game:823090',
                product_date=date(2026, 9, 9),
                status='failed',
                attempts=2,
                max_attempts=5,
                details_json={'game_pk': 823090, 'stage': 'canonical_pending'},
            ))
            run.error_message = (
                '{"failures":[{"scope":"plan_authorization",'
                '"error":"ValueError","work_job_id":328}]}'
            )
            db.session.commit()

            before = SyncRun.query.count(), SyncFailure.query.count()
            report = inspect_runs([6498, 9999])
            after = SyncRun.query.count(), SyncFailure.query.count()

            assert before == after
            assert report['read_only'] is True
            assert report['runs'][0]['error_summary']['failures'][0] == {
                'scope': 'plan_authorization', 'error': 'ValueError',
                'work_job_id': 328,
            }
            assert report['runs'][0]['sync_failures'][0]['retryable'] is False
            assert report['runs'][0]['referenced_jobs'][0]['details'] == {
                'game_pk': 823090, 'stage': 'canonical_pending',
            }
            assert report['runs'][1] == {'sync_run_id': 9999, 'found': False}
        finally:
            db.session.remove()
            drop_test_schema(app)
