"""
Pipeline resilience integration tests.

Cover the work-package acceptance criteria end to end against in-memory SQLite
(no Postgres / MLB / network):

  * one poisoned record in a 30-record batch → 29 succeed, 1 dead-lettered,
    run marked 'partial', the domain still refreshes;
  * a network kill mid-sync → run recorded 'failed', no partial data presented;
  * a crashing job still writes its sync_runs row;
  * pipeline-health reflects all of the above.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
from services import sync_metadata
from services.availability_explanations import FETCH_FAILED_WORKLOAD_REASON
from services.availability_snapshot import classify_latest_fatigue_rows
from services.mlb_api import MlbApiFetchError, mlb_client
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
import models.prospect  # noqa: F401
from api.bullpen import bullpen_bp
from api.system import system_bp


def _valid_split(pk, game_date, innings='1.0', games_started=0):
    return {
        'game': {
            'gamePk': pk,
            'gameType': 'R',
            'status': {
                'statusCode': 'F',
                'detailedState': 'Final',
                'abstractGameState': 'Final',
            },
        },
        'date': game_date.isoformat(),
        'opponent': {'id': 2, 'name': 'Opp'},
        'stat': {
            'inningsPitched': innings,
            'gamesStarted': games_started,
            'numberOfPitches': 12,
            'strikes': 8,
        },
    }


def _poison_split(pk):
    # Valid-looking keys but an unparseable date → raises during ingest, so the
    # record is dead-lettered rather than silently dropped.
    return {
        'game': {
            'gamePk': pk,
            'gameType': 'R',
            'status': {
                'statusCode': 'F',
                'detailedState': 'Final',
                'abstractGameState': 'Final',
            },
        },
        'date': 'not-a-real-date',
        'opponent': {'id': 2, 'name': 'Opp'},
        'stat': {'inningsPitched': '1.0'},
    }


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    # Roster / team-assignment sub-syncs are out of scope here — stub them so
    # the test exercises the game-log batch and run wiring.
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 0, 'pitchers_changed': 0, 'reassigned_count': 0,
        'no_organization_count': 0, 'unknown_count': 0, 'errors': 0,
        'by_status': {},
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda: {
        'pitchers_refreshed': 0, 'pitchers_changed': 0, 'unknown_count': 0,
        'errors': 0, 'by_status': {},
    })
    # No boxscore leverage backfill calls.
    monkeypatch.setattr(mlb_client, 'get_game_pitching_lines', lambda game_pk: [])

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(system_bp, url_prefix='/api/system')
    with app.app_context():
        create_test_schema(app)
        pitcher = Pitcher(mlb_id=100, full_name='Reliever A', team_id=1,
                          team_abbreviation='AAA', active=True)
        db.session.add(pitcher)
        db.session.commit()
        yield app
        db.session.remove()
        drop_test_schema(app)


class TestPartialFailure:
    def test_one_poisoned_record_dead_letters_and_marks_partial(self, app, monkeypatch):
        with app.app_context():
            today = date.today()
            # 29 valid records (distinct game_pks, all within the 7-day window)
            # plus 1 poisoned record.
            splits = [
                _valid_split(1000 + i, today - timedelta(days=i % 5))
                for i in range(29)
            ]
            splits.append(_poison_split(9999))

            monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs',
                                lambda mlb_id, season=None: splits)

            run_id = sync_metadata.start_sync_run(source='test')
            result = sync_service.sync_recent_logs(days_back=7, sync_run_id=run_id)

            assert result['new_logs_added'] == 29
            assert result['records_failed'] == 1
            assert db.session.query(db.func.count(GameLog.id)).scalar() == 29

            failures = SyncFailure.query.all()
            assert len(failures) == 1
            assert failures[0].entity_type == 'game_log_record'
            assert failures[0].resolved is False
            assert failures[0].sync_run_id == run_id
            # The retry payload carries enough to re-attempt the record.
            assert failures[0].payload['game_pk'] == 9999

    def test_sync_stores_mlb_innings_notation_as_outs(self, app, monkeypatch):
        with app.app_context():
            today = date.today()
            splits = [_valid_split(4000, today, innings='0.2')]
            monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs',
                                lambda mlb_id, season=None: splits)

            result = sync_service.sync_recent_logs(days_back=7)
            assert result['new_logs_added'] == 1

            log = GameLog.query.one()
            assert log.innings_pitched_outs == 2
            assert log.innings_pitched == pytest.approx(2 / 3)

    def test_sync_stores_games_started_from_mlb_source(self, app, monkeypatch):
        with app.app_context():
            today = date.today()
            splits = [_valid_split(4100, today, games_started=1)]
            monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs',
                                lambda mlb_id, season=None: splits)

            result = sync_service.sync_recent_logs(days_back=7)
            assert result['new_logs_added'] == 1

            log = GameLog.query.one()
            assert log.games_started == 1

    def test_failed_fetch_dead_letters_but_successful_empty_does_not(self, app, monkeypatch):
        with app.app_context():
            first = Pitcher.query.filter_by(mlb_id=100).one()
            second = Pitcher(mlb_id=101, full_name='Reliever B', team_id=1,
                             team_abbreviation='AAA', active=True)
            db.session.add(second)
            db.session.flush()
            db.session.add(GameLog(
                pitcher_id=first.id,
                mlb_game_pk=5100,
                game_date=date.today() - timedelta(days=1),
                pitches_thrown=10,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                games_started=0,
                game_type='R',
            ))
            db.session.commit()

            def fake_logs(mlb_id, season=None):
                if mlb_id == 100:
                    raise MlbApiFetchError('timeout', endpoint='/people/100/stats')
                return []

            monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', fake_logs)

            run_id = sync_metadata.start_sync_run(source='test')
            result = sync_service.sync_recent_logs(days_back=7, sync_run_id=run_id)

            assert result['new_logs_added'] == 0
            assert result['records_failed'] == 1
            assert result['errors'] == 1
            assert db.session.query(db.func.count(GameLog.id)).scalar() == 1

            failures = SyncFailure.query.order_by(SyncFailure.id).all()
            assert len(failures) == 1
            assert failures[0].entity_type == 'pitcher_game_logs'
            assert failures[0].entity_ref == '100'
            assert failures[0].sync_run_id == run_id

    def test_successful_fetch_resolves_prior_pitcher_fetch_dead_letter(self, app, monkeypatch):
        with app.app_context():
            pitcher = Pitcher.query.filter_by(mlb_id=100).one()
            db.session.add(SyncFailure(
                entity_type='pitcher_game_logs',
                entity_ref='100',
                payload={'pitcher_id': pitcher.id, 'mlb_id': 100},
                error='timeout',
                resolved=False,
            ))
            db.session.commit()
            monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs',
                                lambda mlb_id, season=None: [])

            result = sync_service.sync_recent_logs(days_back=7)

            assert result['records_failed'] == 0
            failure = SyncFailure.query.one()
            assert failure.resolved is True
            assert failure.resolved_at is not None

    def test_unresolved_pitcher_fetch_failure_degrades_availability_confidence(self, app):
        with app.app_context():
            pitcher = Pitcher.query.filter_by(mlb_id=100).one()
            today = date.today()
            db.session.add(GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=5200,
                game_date=today,
                pitches_thrown=8,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                games_started=0,
                game_type='R',
            ))
            score = FatigueScore(
                pitcher_id=pitcher.id,
                raw_score=10.0,
                risk_level='LOW',
                calculated_at=datetime.utcnow(),
            )
            db.session.add(score)
            db.session.add(SyncFailure(
                entity_type='pitcher_game_logs',
                entity_ref='100',
                payload={'pitcher_id': pitcher.id, 'mlb_id': 100},
                error='timeout',
                resolved=False,
            ))
            db.session.commit()

            records = classify_latest_fatigue_rows(
                [(score, pitcher)],
                reference_date=today,
            )
            availability = records[0]['availability']

            assert availability['availability_status'] == 'Monitor'
            assert availability['confidence'] == 'low'
            assert availability['data_state'] == 'incomplete'
            assert FETCH_FAILED_WORKLOAD_REASON in availability['reasons']
            assert availability['inputs']['workload_fetch_failed'] is True

    def test_unresolved_pitcher_fetch_failure_preserves_prior_fatigue_score(self, app):
        with app.app_context():
            pitcher = Pitcher.query.filter_by(mlb_id=100).one()
            today = date.today()
            db.session.add(GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=5300,
                game_date=today,
                pitches_thrown=8,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                games_started=0,
                game_type='R',
            ))
            db.session.add(FatigueScore(
                pitcher_id=pitcher.id,
                raw_score=10.0,
                risk_level='LOW',
                calculated_at=datetime.utcnow(),
            ))
            db.session.add(SyncFailure(
                entity_type='pitcher_game_logs',
                entity_ref='100',
                payload={'pitcher_id': pitcher.id, 'mlb_id': 100},
                error='timeout',
                resolved=False,
            ))
            db.session.commit()

            updated = sync_service.recalculate_all_fatigue(
                reference_date=today + timedelta(days=1),
            )

            assert updated == 0
            assert FatigueScore.query.filter_by(pitcher_id=pitcher.id).count() == 1

    def test_sync_endpoint_marks_run_partial_and_domain_refreshes(self, app, monkeypatch):
        today = date.today()
        splits = [
            _valid_split(2000 + i, today - timedelta(days=i % 5))
            for i in range(29)
        ]
        splits.append(_poison_split(8888))
        monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs',
                            lambda mlb_id, season=None: splits)

        client = app.test_client()
        res = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert res.status_code == 200
        body = res.get_json()
        assert body['sync_run_status'] == 'partial'
        assert body['records_failed'] == 1

        with app.app_context():
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert run.status == 'partial'
            assert run.records_failed == 1
            # The domain still refreshed despite the dead-letter.
            assert run.latest_workload_date is not None
            assert run.new_logs_added == 29

        # Freshness still updates: a partial run counts as a successful write.
        status = client.get('/api/bullpen/sync/status').get_json()
        assert status['status'] == 'partial'
        assert status['last_successful_sync'] is not None


class TestNetworkKill:
    def test_network_kill_midsync_records_failed_and_presents_no_fresh_data(self, app, monkeypatch):
        # Simulate the network dropping mid-sync: the pull raises and never
        # returns a partial result.
        def boom(days_back=7, sync_run_id=None, **kw):
            raise ConnectionError('network dropped mid-sync')

        monkeypatch.setattr(sync_service, 'sync_recent_logs', boom)

        client = app.test_client()
        res = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert res.status_code == 500

        with app.app_context():
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert run is not None
            assert run.status == 'failed'
            assert run.completed_at is not None
            # No partial data was committed.
            assert db.session.query(db.func.count(GameLog.id)).scalar() == 0

        # With no successful sync ever, nothing is presented as fresh.
        status = client.get('/api/bullpen/sync/status').get_json()
        assert status['status'] == 'failed'
        assert status['last_successful_sync'] is None
        assert status['freshness']['is_current'] is False


class TestCrashingJobRecordsRun:
    def test_crashing_daily_job_still_writes_a_sync_runs_row(self, app, monkeypatch):
        # The very first sub-sync crashes — the job must still record its run.
        def explode():
            raise RuntimeError('roster source exploded')

        monkeypatch.setattr(sync_service, 'sync_team_assignments', explode)

        status = sync_service.run_daily_sync(app, days_back=7)
        assert status['status'] == 'failed'

        with app.app_context():
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert run is not None
            assert run.status == 'failed'
            assert run.completed_at is not None
            assert 'roster source exploded' in (run.error_message or '')


class TestPipelineHealthEndpoint:
    def test_pipeline_health_reflects_partial_run_and_dead_letters(self, app, monkeypatch):
        today = date.today()
        splits = [
            _valid_split(3000 + i, today - timedelta(days=i % 5))
            for i in range(29)
        ]
        splits.append(_poison_split(7777))
        monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs',
                            lambda mlb_id, season=None: splits)

        client = app.test_client()
        client.post('/api/bullpen/sync', json={'days_back': 7})

        health = client.get('/api/system/pipeline-health').get_json()
        assert health['capability'] == 'pipeline_health'
        assert 'source_readiness' in health
        assert health['source_readiness']['families']['finality_authority']['status'] == 'ready'
        assert health['dead_letters']['unresolved_count'] == 1
        assert len(health['dead_letters']['recent']) == 1

        jobs = {job['job_name']: job for job in health['jobs']}
        assert 'daily_sync' in jobs
        assert jobs['daily_sync']['status'] == 'partial'
        assert jobs['daily_sync']['last_run']['records_failed'] == 1
        # Per-domain freshness is classified.
        assert health['domains']['workload']['state'] in (
            'fresh', 'stale', 'unavailable', 'missing'
        )
