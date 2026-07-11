from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from sqlalchemy.exc import IntegrityError

import api.bullpen as bullpen_api
import services.sync as sync_service
from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
import models.prospect  # noqa: F401
from services import dashboard_snapshot, schedule_ingestion, sync_metadata
from services.roster_status import STATUS_ACTIVE
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_api.bullpen_bp, url_prefix='/api/bullpen')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def client(app):
    return app.test_client()


def _sync_scaffolding(*_args, **_kwargs):
    return {
        'pitchers_refreshed': 0,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'by_status': {},
    }


def _complete_slate_coverage(slate_date):
    return {
        'slate_date': slate_date.isoformat() if slate_date else None,
        'games_scheduled': 0,
        'games_final': 0,
        'games_fully_ingested': 0,
        'games_incomplete': 0,
        'games_failed': 0,
        'games_postponed': 0,
        'games_suspended': 0,
        'games_included': 0,
        'validations_passed': True,
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'reason_codes': ['no_scheduled_games', 'slate_complete'],
        'degradation_reasons': [],
        'marker_counts': {
            'fully_processed': 0,
            'incomplete': 0,
            'failed': 0,
            'missing': 0,
        },
    }


def _seed_complete_slate(game_date, game_pks):
    for game_pk in game_pks:
        db.session.add_all([
            ScheduledGame(
                team_id=116,
                game_pk=game_pk,
                game_date=game_date,
                status_state='final',
                home_away='home',
                opponent_team_id=142,
            ),
            ScheduledGame(
                team_id=142,
                game_pk=game_pk,
                game_date=game_date,
                status_state='final',
                home_away='away',
                opponent_team_id=116,
            ),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk,
            game_date=game_date,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))


def _mlb_schedule_game(
    game_pk,
    game_date,
    *,
    status_code='F',
    detailed_state='Final',
    abstract_state='Final',
    home_id=108,
    away_id=111,
):
    return {
        'gamePk': game_pk,
        'officialDate': game_date.isoformat(),
        'gameDate': f'{game_date.isoformat()}T20:10:00Z',
        'gameType': 'R',
        'status': {
            'statusCode': status_code,
            'detailedState': detailed_state,
            'abstractGameState': abstract_state,
        },
        'teams': {
            'home': {'team': {'id': home_id, 'name': 'Home Club'}},
            'away': {'team': {'id': away_id, 'name': 'Away Club'}},
        },
    }


def _seed_stale_non_final_slate(game_date, game_pk=824010):
    db.session.add_all([
        ScheduledGame(
            team_id=108,
            game_pk=game_pk,
            game_date=game_date,
            game_type='R',
            status_code='I',
            status_state=ScheduledGame.STATE_OTHER,
            home_away='home',
            opponent_team_id=111,
        ),
        ScheduledGame(
            team_id=111,
            game_pk=game_pk,
            game_date=game_date,
            game_type='R',
            status_code='I',
            status_state=ScheduledGame.STATE_OTHER,
            home_away='away',
            opponent_team_id=108,
        ),
    ])


def _seed_full_postgame_marker(game_date, game_pk=824010):
    db.session.add(PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=game_date,
        processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
    ))


def _seed_game_appearance(game_date, game_pk=824010, mlb_id=910000):
    """A final game must hold appearance rows to pass the ledger gate."""
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=f'Ledger Reliever {mlb_id}',
        team_id=116,
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=12,
    ))


def _payload_requiring_slate_recheck(game_date):
    payload = _minimal_dashboard_payload()
    payload['freshness']['data_through'] = game_date.isoformat()
    payload['freshness']['latest_workload_date'] = game_date.isoformat()
    payload['freshness']['availability_reference_date'] = (
        game_date + timedelta(days=1)
    ).isoformat()
    payload['freshness']['sync_status'] = 'success'
    payload['freshness']['slate_coverage'] = {
        **_complete_slate_coverage(game_date),
        'games_scheduled': 1,
        'games_final': 0,
        'games_incomplete': 1,
        'validations_passed': False,
        'complete_enough_to_publish': False,
        'reason_codes': [
            'scheduled_games_not_final',
            'completeness_unknown',
            'validations_failed',
        ],
    }
    payload['freshness']['validations_passed'] = False
    payload['freshness']['complete_enough_to_publish'] = False
    return payload


def _seed_dashboard_data():
    workload_date = date.today() - timedelta(days=1)
    pitcher = Pitcher(
        mlb_id=101,
        full_name='Snapshot Reliever',
        team_id=1,
        team_name='Snapshot Club',
        team_abbreviation='SC',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.commit()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=1010,
        game_date=workload_date,
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=14,
        game_type='R',
    ))
    _seed_complete_slate(workload_date, [1010])
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        raw_score=12.0,
        risk_level='LOW',
        calculated_at=utc_now_naive(),
    ))
    db.session.add(SyncRun(
        started_at=utc_now_naive() - timedelta(minutes=2),
        completed_at=utc_now_naive() - timedelta(minutes=1),
        status='success',
        source='manual',
        latest_game_date=workload_date,
        latest_workload_date=workload_date,
        latest_fatigue_calculated_at=utc_now_naive(),
        records_processed=1,
        new_logs_added=1,
        pitchers_updated=1,
        errors=0,
        created_at=utc_now_naive() - timedelta(minutes=2),
    ))
    db.session.commit()
    return workload_date


def _create_sync_run(workload_date=None, *, stage='published'):
    workload_date = workload_date or date.today() - timedelta(days=1)
    run = SyncRun(
        started_at=utc_now_naive() - timedelta(minutes=4),
        completed_at=utc_now_naive() - timedelta(minutes=3),
        status='success',
        stage=stage,
        source='manual',
        latest_game_date=workload_date,
        latest_workload_date=workload_date,
        latest_fatigue_calculated_at=utc_now_naive() - timedelta(minutes=2),
        created_at=utc_now_naive() - timedelta(minutes=4),
    )
    db.session.add(run)
    db.session.flush()
    return run


def _build_published_dashboard_snapshot(source='test'):
    run = _create_sync_run()
    result = dashboard_snapshot.build_bullpen_dashboard_snapshot_v2(
        source=source,
        publish=True,
        sync_run_id=run.id,
    )
    return result, run


def _minimal_dashboard_payload():
    coverage = _complete_slate_coverage(None)
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': utc_now_naive().isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': 'bullpen_eligible',
        'context': {},
        'roles': {'order': [], 'counts': {}, 'total': 0},
        'landscape': {},
        'freshness': {
            'data_through': None,
            'availability_reference_date': None,
            'reference_date': date.today().isoformat(),
            'sync_status': 'never',
            'last_successful_sync': None,
            'slate_coverage': coverage,
            'validations_passed': True,
            'complete_enough_to_publish': True,
        },
        'availability_summary': {},
    }


class TestDashboardSnapshotService:
    def test_model_table_accepts_json_payload(self, app):
        with app.app_context():
            snapshot = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                payload={'capability': 'bullpen_dashboard'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
            )
            db.session.add(snapshot)
            db.session.commit()

            row = DashboardSnapshot.query.one()
            assert row.payload['capability'] == 'bullpen_dashboard'
            assert row.status == 'ready'

    def test_store_dashboard_snapshot_persists_contract_metadata(self, app):
        with app.app_context():
            _seed_dashboard_data()
            payload = bullpen_api.build_bullpen_dashboard_payload()
            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                payload,
                sync_run_id=1,
                source='test',
            )

            assert snapshot.status == 'ready'
            assert snapshot.payload_version == dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION
            assert snapshot.data_through is not None
            assert snapshot.availability_reference_date is not None
            assert snapshot.payload['capability'] == 'bullpen_dashboard'

    def test_latest_snapshot_uses_published_ready_row(self, app):
        with app.app_context():
            run = _create_sync_run()
            old_ready = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=True,
                published_at=utc_now_naive() - timedelta(minutes=10),
                payload={**_minimal_dashboard_payload(), 'name': 'old'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=10),
                source='test',
            )
            failed = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_FAILED,
                payload=None,
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
                error_message='failed build',
            )
            newer_ready = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=False,
                payload={**_minimal_dashboard_payload(), 'name': 'new'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=1),
                source='test',
            )
            db.session.add_all([old_ready, failed, newer_ready])
            db.session.commit()

            snapshot = dashboard_snapshot.get_latest_dashboard_snapshot()
            assert snapshot.payload['name'] == 'old'

            dashboard_snapshot.publish_dashboard_snapshot(newer_ready)
            snapshot = dashboard_snapshot.get_latest_dashboard_snapshot()
            assert snapshot.payload['name'] == 'new'
            assert old_ready.is_published is False

    def test_latest_published_snapshot_before_skips_unpublished_baseline(self, app):
        with app.app_context():
            run = _create_sync_run()
            current_data_through = date(2026, 6, 20)
            published_prior_date = date(2026, 6, 18)
            unpublished_prior_date = date(2026, 6, 19)
            published_prior = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=True,
                published_at=utc_now_naive() - timedelta(minutes=10),
                payload={**_minimal_dashboard_payload(), 'name': 'published-prior'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                data_through=published_prior_date,
                availability_reference_date=published_prior_date,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=10),
                source='test',
            )
            unpublished_prior = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=False,
                payload={**_minimal_dashboard_payload(), 'name': 'unpublished-prior'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                data_through=unpublished_prior_date,
                availability_reference_date=unpublished_prior_date,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=1),
                source='test',
            )
            db.session.add_all([published_prior, unpublished_prior])
            db.session.commit()

            snapshot = dashboard_snapshot.get_latest_published_dashboard_snapshot_before(
                current_data_through
            )

            assert snapshot.id == published_prior.id
            assert snapshot.payload['name'] == 'published-prior'

    def test_published_snapshot_requires_sync_run_provenance(self, app):
        with app.app_context():
            snapshot = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=True,
                payload={'name': 'unprovenanced'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
            )
            db.session.add(snapshot)
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()

    def test_publish_reconciles_prior_sync_pointer(self, app):
        with app.app_context():
            first_run = _create_sync_run()
            first = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=first_run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=False,
                payload={**_minimal_dashboard_payload(), 'name': 'first'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive() - timedelta(minutes=10),
                source='test',
            )
            db.session.add(first)
            db.session.flush()
            dashboard_snapshot.publish_dashboard_snapshot(first)
            first_run.published_dashboard_snapshot_id = first.id
            db.session.commit()

            second_run = _create_sync_run()
            second = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=second_run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_PENDING,
                is_published=False,
                payload={**_minimal_dashboard_payload(), 'name': 'second'},
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
            )
            db.session.add(second)
            db.session.flush()
            dashboard_snapshot.publish_dashboard_snapshot(second)

            db.session.refresh(first_run)
            db.session.refresh(second_run)
            db.session.refresh(first)
            db.session.refresh(second)
            assert first.is_published is False
            assert first.published_at is not None
            assert second.is_published is True
            assert second.published_at is not None
            assert first_run.published_dashboard_snapshot_id == second.id
            assert second_run.published_dashboard_snapshot_id == second.id
            active_snapshots = (
                DashboardSnapshot.query
                .filter(DashboardSnapshot.is_published == True)
                .all()
            )
            assert [row.id for row in active_snapshots] == [second.id]
            assert dashboard_snapshot.get_latest_dashboard_snapshot().id == second.id

    def test_snapshot_validation_rejects_payload_version_mismatch(self, app):
        with app.app_context():
            _seed_dashboard_data()
            payload = bullpen_api.build_bullpen_dashboard_payload()
            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                payload,
                sync_run_id=1,
                source='test',
            )
            snapshot.payload_version = dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION + 1
            db.session.commit()

            assert (
                dashboard_snapshot.snapshot_unavailable_reason(snapshot)
                == 'dashboard_snapshot_version_mismatch'
            )
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot() is None

    def test_build_dashboard_snapshot_records_failed_status(self, app):
        with app.app_context():
            run = _create_sync_run()
            db.session.commit()
            snapshot = dashboard_snapshot.build_dashboard_snapshot(
                lambda: (_ for _ in ()).throw(RuntimeError('builder failed')),
                sync_run_id=run.id,
                source='test',
            )

            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_FAILED
            assert snapshot.sync_run_id == run.id
            assert 'builder failed' in snapshot.error_message

    def test_snapshot_builder_v2_creates_dashboard_servable_snapshot(self, app):
        with app.app_context():
            _seed_dashboard_data()
            run = _create_sync_run()

            result = dashboard_snapshot.build_bullpen_dashboard_snapshot_v2(
                source='test',
                publish=True,
                sync_run_id=run.id,
            )

            assert result['status'] == 'ready'
            assert result['reason'] is None
            assert result['snapshot_served_by_dashboard'] is True
            assert result['snapshot_id'] is not None
            snapshot = db.session.get(DashboardSnapshot, result['snapshot_id'])
            assert snapshot is not None
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
            assert snapshot.payload['capability'] == 'bullpen_dashboard'
            assert snapshot.payload['freshness']['slate_coverage']['slate_date'] == (
                snapshot.data_through.isoformat()
            )
            assert (
                snapshot.payload['freshness']['slate_coverage']['complete_enough_to_publish']
                is True
            )
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == snapshot.id

    def test_new_snapshot_payload_without_slate_coverage_is_repaired_before_publish(self, app):
        with app.app_context():
            workload_date = _seed_dashboard_data()
            run = _create_sync_run(workload_date)
            payload = bullpen_api.build_bullpen_dashboard_payload()
            payload['freshness'].pop('slate_coverage', None)
            payload['freshness'].pop('validations_passed', None)
            payload['freshness'].pop('complete_enough_to_publish', None)

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                payload,
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            coverage = snapshot.payload['freshness']['slate_coverage']
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
            assert snapshot.is_published is True
            assert coverage['slate_date'] == workload_date.isoformat()
            assert coverage['complete_enough_to_publish'] is True
            assert coverage['reason_codes'] == ['slate_complete']

    def test_missing_slate_coverage_is_recomputed_and_still_withheld_when_incomplete(self, app):
        with app.app_context():
            workload_date = date.today() - timedelta(days=1)
            run = _create_sync_run(workload_date)
            payload = _minimal_dashboard_payload()
            payload['freshness']['data_through'] = workload_date.isoformat()
            payload['freshness']['latest_workload_date'] = workload_date.isoformat()
            payload['freshness']['availability_reference_date'] = (
                workload_date + timedelta(days=1)
            ).isoformat()
            payload['freshness'].pop('slate_coverage', None)
            payload['freshness'].pop('validations_passed', None)
            payload['freshness'].pop('complete_enough_to_publish', None)
            db.session.add_all([
                ScheduledGame(
                    team_id=116,
                    game_pk=7701,
                    game_date=workload_date,
                    status_state='final',
                    home_away='home',
                    opponent_team_id=142,
                ),
                ScheduledGame(
                    team_id=142,
                    game_pk=7701,
                    game_date=workload_date,
                    status_state='final',
                    home_away='away',
                    opponent_team_id=116,
                ),
            ])
            db.session.commit()

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                payload,
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            coverage = snapshot.payload['freshness']['slate_coverage']
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert snapshot.is_published is False
            assert snapshot.error_message == 'dashboard_snapshot_slate_coverage_incomplete'
            assert coverage['slate_date'] == workload_date.isoformat()
            assert coverage['complete_enough_to_publish'] is False
            assert 'postgame_markers_incomplete' in coverage['reason_codes']
            assert (
                dashboard_snapshot.snapshot_unavailable_reason(snapshot)
                == 'dashboard_snapshot_slate_coverage_incomplete'
            )

    def test_publish_refreshes_stale_non_final_slate_before_validation(self, app, monkeypatch):
        slate_date = date(2026, 7, 5)

        monkeypatch.setattr(
            schedule_ingestion.mlb_client,
            'get_schedule',
            lambda **_kwargs: [_mlb_schedule_game(824010, slate_date)],
        )
        with app.app_context():
            _seed_stale_non_final_slate(slate_date)
            _seed_full_postgame_marker(slate_date)
            _seed_game_appearance(slate_date)
            db.session.commit()
            run = _create_sync_run(slate_date)

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                _payload_requiring_slate_recheck(slate_date),
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            coverage = snapshot.payload['freshness']['slate_coverage']
            rows = ScheduledGame.query.filter_by(game_pk=824010).all()
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
            assert snapshot.is_published is True
            assert coverage['slate_date'] == '2026-07-05'
            assert coverage['games_scheduled'] == 1
            assert coverage['games_final'] == 1
            assert coverage['games_fully_ingested'] == 1
            assert coverage['complete_enough_to_publish'] is True
            assert coverage['reason_codes'] == ['slate_complete']
            assert {row.status_state for row in rows} == {ScheduledGame.STATE_FINAL}
            assert {row.status_code for row in rows} == {'F'}

    def test_publish_stays_limited_when_slate_source_is_still_non_final(self, app, monkeypatch):
        slate_date = date(2026, 7, 5)

        monkeypatch.setattr(
            schedule_ingestion.mlb_client,
            'get_schedule',
            lambda **_kwargs: [
                _mlb_schedule_game(
                    824010,
                    slate_date,
                    status_code='I',
                    detailed_state='In Progress',
                    abstract_state='Live',
                )
            ],
        )
        with app.app_context():
            _seed_stale_non_final_slate(slate_date)
            db.session.commit()
            run = _create_sync_run(slate_date)

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                _payload_requiring_slate_recheck(slate_date),
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            coverage = snapshot.payload['freshness']['slate_coverage']
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert snapshot.is_published is False
            assert snapshot.error_message == 'dashboard_snapshot_slate_coverage_incomplete'
            assert coverage['games_final'] == 0
            assert coverage['complete_enough_to_publish'] is False
            assert 'scheduled_games_not_final' in coverage['reason_codes']
            assert 'completeness_unknown' in coverage['reason_codes']
            assert 'validations_failed' in coverage['reason_codes']

    def test_publish_still_requires_markers_after_finality_refresh(self, app, monkeypatch):
        slate_date = date(2026, 7, 5)

        monkeypatch.setattr(
            schedule_ingestion.mlb_client,
            'get_schedule',
            lambda **_kwargs: [_mlb_schedule_game(824010, slate_date)],
        )
        with app.app_context():
            _seed_stale_non_final_slate(slate_date)
            db.session.commit()
            run = _create_sync_run(slate_date)

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                _payload_requiring_slate_recheck(slate_date),
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            coverage = snapshot.payload['freshness']['slate_coverage']
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert snapshot.is_published is False
            assert coverage['games_final'] == 1
            assert coverage['games_fully_ingested'] == 0
            assert 'final_games_not_fully_ingested' in coverage['reason_codes']
            assert 'postgame_markers_incomplete' in coverage['reason_codes']

    def test_publish_preserves_suspended_resumed_slate_safeguard(self, app, monkeypatch):
        slate_date = date(2026, 7, 5)

        monkeypatch.setattr(
            schedule_ingestion.mlb_client,
            'get_schedule',
            lambda **_kwargs: [
                _mlb_schedule_game(
                    824010,
                    slate_date,
                    status_code='U',
                    detailed_state='Suspended',
                    abstract_state='Live',
                ) | {'rescheduledGamePk': 824099, 'rescheduleDate': '2026-07-06'}
            ],
        )
        with app.app_context():
            _seed_stale_non_final_slate(slate_date)
            _seed_full_postgame_marker(slate_date)
            db.session.commit()
            run = _create_sync_run(slate_date)

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                _payload_requiring_slate_recheck(slate_date),
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            coverage = snapshot.payload['freshness']['slate_coverage']
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert snapshot.is_published is False
            assert coverage['games_suspended'] == 1
            assert coverage['games_final'] == 0
            assert 'suspended_games_not_final' in coverage['reason_codes']
            assert 'resumed_linkage_unresolved' in coverage['reason_codes']

    def test_incomplete_slate_snapshot_is_stored_but_not_published(self, app):
        with app.app_context():
            run = _create_sync_run()
            payload = _minimal_dashboard_payload()
            payload['freshness']['slate_coverage'] = {
                **_complete_slate_coverage(date(2026, 6, 25)),
                'games_scheduled': 1,
                'games_final': 1,
                'games_fully_ingested': 0,
                'games_incomplete': 1,
                'validations_passed': False,
                'complete_enough_to_publish': False,
                'reason_codes': [
                    'final_games_not_fully_ingested',
                    'postgame_markers_incomplete',
                    'validations_failed',
                ],
                'degradation_reasons': [
                    'Final games are not fully ingested for this slate.',
                    'One or more final games still have incomplete postgame processing markers.',
                    'Slate coverage validations did not pass.',
                ],
            }

            snapshot = dashboard_snapshot.store_dashboard_snapshot(
                payload,
                sync_run_id=run.id,
                source='test',
                publish=True,
            )

            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert snapshot.is_published is False
            assert snapshot.error_message == 'dashboard_snapshot_slate_coverage_incomplete'
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot() is None
            assert (
                dashboard_snapshot.snapshot_unavailable_reason(snapshot)
                == 'dashboard_snapshot_slate_coverage_incomplete'
            )

    def test_old_snapshot_without_slate_coverage_is_not_valid(self, app):
        with app.app_context():
            run = _create_sync_run()
            payload = _minimal_dashboard_payload()
            payload['freshness'].pop('slate_coverage')
            payload['freshness'].pop('validations_passed')
            payload['freshness'].pop('complete_enough_to_publish')
            snapshot = DashboardSnapshot(
                snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
                sync_run_id=run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=True,
                published_at=utc_now_naive(),
                payload=payload,
                payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
                snapshot_generated_at=utc_now_naive(),
                source='test',
            )
            db.session.add(snapshot)
            db.session.commit()

            assert (
                dashboard_snapshot.snapshot_unavailable_reason(snapshot)
                == 'dashboard_snapshot_slate_coverage_missing'
            )
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot() is None

    def test_snapshot_builder_v2_records_failure_without_raising(self, app, monkeypatch):
        def fail_builder():
            raise RuntimeError('builder exploded')

        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            fail_builder,
        )

        with app.app_context():
            result = dashboard_snapshot.build_bullpen_dashboard_snapshot_v2(source='test')

            assert result['status'] == 'failed'
            assert result['reason'] == 'dashboard_snapshot_not_ready'
            snapshot = db.session.get(DashboardSnapshot, result['snapshot_id'])
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_FAILED
            assert 'builder exploded' in snapshot.error_message

    def test_standalone_builder_does_not_publish_during_running_sync(self, app, monkeypatch):
        with app.app_context():
            _seed_dashboard_data()
            prior, _ = _build_published_dashboard_snapshot()
            prior_snapshot_id = prior['snapshot_id']
            active_run = SyncRun(
                started_at=utc_now_naive(),
                status='running',
                stage='log_ingestion',
                source='manual',
                created_at=utc_now_naive(),
            )
            db.session.add(active_run)
            db.session.commit()
            active_run_id = active_run.id

            monkeypatch.setattr(
                sync_metadata,
                '_uses_postgres_advisory_writer_lock',
                lambda: True,
            )

            def busy_lock(*, job_name=None, source=None, lock_scope=None):
                raise sync_metadata.SyncWriterConflict(
                    reason=sync_metadata.SYNC_WRITER_ALREADY_RUNNING,
                    job_name=job_name,
                    source=source,
                    active_run=db.session.get(SyncRun, active_run_id),
                )

            monkeypatch.setattr(
                sync_metadata,
                '_acquire_postgres_writer_lock',
                busy_lock,
            )

            result = dashboard_snapshot.build_bullpen_dashboard_snapshot_v2(source='test')

            assert result['status'] == 'blocked'
            assert result['reason'] == 'sync_writer_already_running'
            assert result['snapshot_served_by_dashboard'] is False
            assert db.session.get(SyncRun, active_run_id).status == 'running'
            assert (
                dashboard_snapshot.get_latest_valid_dashboard_snapshot().id
                == prior_snapshot_id
            )


class TestDashboardRouteSnapshotBehavior:
    def test_dashboard_route_serves_valid_cache_without_live_builder(self, client, monkeypatch):
        with client.application.app_context():
            _seed_dashboard_data()
            payload = bullpen_api.build_bullpen_dashboard_payload()
            dashboard_snapshot.store_dashboard_snapshot(payload, sync_run_id=1, source='test')
        client.application.config['APP_ENV'] = 'production'

        def fail_live_builder():
            raise AssertionError('live builder should not run')

        monkeypatch.setattr(bullpen_api, 'build_bullpen_dashboard_payload', fail_live_builder)

        response = client.get('/api/bullpen/dashboard')
        assert response.status_code == 200
        body = response.get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['snapshot']['served_from'] == 'cache'
        assert body['snapshot']['payload_version'] == 1

    def test_dashboard_route_serves_snapshot_created_by_builder_v2(self, client, monkeypatch):
        with client.application.app_context():
            _seed_dashboard_data()
            result, _ = _build_published_dashboard_snapshot()
            assert result['status'] == 'ready'
        client.application.config['APP_ENV'] = 'production'
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: pytest.fail('production dashboard must serve builder snapshot'),
        )

        body = client.get('/api/bullpen/dashboard').get_json()

        assert body['snapshot']['served_from'] == 'cache'
        assert body['snapshot']['snapshot_id'] == result['snapshot_id']
        assert body['capability'] == 'bullpen_dashboard'

    def test_dashboard_route_falls_back_when_cache_missing(self, client, monkeypatch):
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            _minimal_dashboard_payload,
        )

        response = client.get('/api/bullpen/dashboard')
        assert response.status_code == 200
        body = response.get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['snapshot']['served_from'] == 'live_fallback'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False

    def test_dashboard_route_returns_degraded_response_when_production_cache_missing(
        self,
        client,
        monkeypatch,
    ):
        client.application.config['APP_ENV'] = 'production'

        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: pytest.fail('production cache miss must not run live builder'),
        )

        response = client.get('/api/bullpen/dashboard')
        assert response.status_code == 200
        body = response.get_json()
        assert body['capability'] == 'bullpen_dashboard'
        assert body['status'] == 'snapshot_unavailable'
        assert body['reason'] == 'dashboard_snapshot_missing'
        assert body['snapshot']['served_from'] == 'snapshot_unavailable'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False

    def test_dashboard_route_falls_back_when_latest_snapshot_failed(self, client, monkeypatch):
        with client.application.app_context():
            dashboard_snapshot.mark_dashboard_snapshot_failed(
                RuntimeError('snapshot failed'),
                sync_run_id=10,
                source='test',
            )
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            _minimal_dashboard_payload,
        )

        body = client.get('/api/bullpen/dashboard').get_json()
        assert body['snapshot']['served_from'] == 'live_fallback'

    def test_dashboard_route_returns_degraded_response_when_production_snapshot_failed(
        self,
        client,
        monkeypatch,
    ):
        client.application.config['APP_ENV'] = 'production'
        with client.application.app_context():
            run = _create_sync_run()
            dashboard_snapshot.mark_dashboard_snapshot_failed(
                RuntimeError('snapshot failed'),
                sync_run_id=run.id,
                source='test',
            )
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: pytest.fail('production failed snapshot must not run live builder'),
        )

        body = client.get('/api/bullpen/dashboard').get_json()
        assert body['status'] == 'snapshot_unavailable'
        assert body['reason'] == 'dashboard_snapshot_not_ready'
        assert body['snapshot']['served_from'] == 'snapshot_unavailable'

    def test_public_payload_remains_backward_compatible(self, client):
        body = client.get('/api/bullpen/dashboard').get_json()
        for key in (
            'capability',
            'generated_at',
            'ranking_applied',
            'selection_made',
            'scope',
            'context',
            'roles',
            'landscape',
            'freshness',
            'availability_summary',
        ):
            assert key in body
        assert body['snapshot']['served_from'] in ('cache', 'live_fallback')


class TestDashboardSnapshotBuildEndpoint:
    def test_snapshot_build_endpoint_rejects_missing_configured_token(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv('DASHBOARD_SNAPSHOT_BUILD_TOKEN', 'secret')
        monkeypatch.setattr(
            dashboard_snapshot,
            'build_bullpen_dashboard_snapshot_v2',
            lambda **kwargs: pytest.fail('unauthorized request must not build snapshot'),
        )

        response = client.post('/api/bullpen/dashboard/snapshot/build')

        assert response.status_code == 401
        assert response.get_json() == {
            'status': 'error',
            'reason': 'dashboard_snapshot_build_token_required',
        }

    def test_snapshot_build_endpoint_rejects_invalid_token(self, client, monkeypatch):
        monkeypatch.setenv('DASHBOARD_SNAPSHOT_BUILD_TOKEN', 'secret')
        monkeypatch.setattr(
            dashboard_snapshot,
            'build_bullpen_dashboard_snapshot_v2',
            lambda **kwargs: pytest.fail('invalid token request must not build snapshot'),
        )

        response = client.post(
            '/api/bullpen/dashboard/snapshot/build',
            headers={'Authorization': 'Bearer wrong'},
        )

        assert response.status_code == 403
        assert response.get_json() == {
            'status': 'error',
            'reason': 'dashboard_snapshot_build_token_invalid',
        }

    def test_snapshot_build_endpoint_fails_closed_when_token_unconfigured(
        self,
        client,
        monkeypatch,
    ):
        client.application.config['APP_ENV'] = 'production'
        monkeypatch.delenv('DASHBOARD_SNAPSHOT_BUILD_TOKEN', raising=False)
        monkeypatch.setattr(
            dashboard_snapshot,
            'build_bullpen_dashboard_snapshot_v2',
            lambda **kwargs: pytest.fail('unconfigured endpoint must not build snapshot'),
        )

        response = client.post(
            '/api/bullpen/dashboard/snapshot/build',
            headers={'Authorization': 'Bearer secret'},
        )

        assert response.status_code == 503
        assert response.get_json() == {
            'status': 'error',
            'reason': 'dashboard_snapshot_build_token_not_configured',
        }

    def test_snapshot_build_endpoint_accepts_internal_token_header(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv('DASHBOARD_SNAPSHOT_BUILD_TOKEN', 'secret')
        with client.application.app_context():
            _seed_dashboard_data()

        response = client.post(
            '/api/bullpen/dashboard/snapshot/build',
            headers={'X-Internal-Token': 'secret'},
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body['status'] == 'ok'
        assert body['snapshot']['served_from'] == 'cache'
        assert body['snapshot']['snapshot_id'] is not None
        assert body['snapshot']['is_published'] is True
        assert body['snapshot']['payload_has_slate_coverage'] is True

    def test_snapshot_build_endpoint_valid_token_publishes_cache_snapshot(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv('DASHBOARD_SNAPSHOT_BUILD_TOKEN', 'secret')
        with client.application.app_context():
            _seed_dashboard_data()
            prior, _ = _build_published_dashboard_snapshot()
            prior_snapshot_id = prior['snapshot_id']

        response = client.post(
            '/api/bullpen/dashboard/snapshot/build',
            headers={'Authorization': 'Bearer secret'},
        )

        assert response.status_code == 200
        body = response.get_json()
        assert body['status'] == 'ok'
        assert body['snapshot']['served_from'] == 'cache'
        assert body['snapshot']['payload_version'] == dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION
        assert body['snapshot']['is_published'] is True
        assert body['snapshot']['payload_has_slate_coverage'] is True
        assert body['snapshot']['slate_coverage']['complete_enough_to_publish'] is True
        assert body['builder']['snapshot_served_by_dashboard'] is True
        assert body['snapshot']['snapshot_id'] != prior_snapshot_id

        client.application.config['APP_ENV'] = 'production'
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: pytest.fail('dashboard GET must serve existing published snapshot'),
        )
        dashboard = client.get('/api/bullpen/dashboard').get_json()
        assert dashboard['snapshot']['served_from'] == 'cache'
        assert dashboard['snapshot']['snapshot_id'] == body['snapshot']['snapshot_id']

    def test_snapshot_build_endpoint_returns_controlled_error_on_build_failure(
        self,
        client,
        monkeypatch,
    ):
        monkeypatch.setenv('DASHBOARD_SNAPSHOT_BUILD_TOKEN', 'secret')
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: (_ for _ in ()).throw(RuntimeError('builder exploded')),
        )

        response = client.post(
            '/api/bullpen/dashboard/snapshot/build',
            headers={'Authorization': 'Bearer secret'},
        )

        assert response.status_code == 500
        body = response.get_json()
        assert body['status'] == 'error'
        assert body['reason'] == 'dashboard_snapshot_not_ready'
        assert body['builder']['status'] == 'failed'
        assert body['builder']['snapshot_served_by_dashboard'] is False


class TestSyncSnapshotIntegration:
    def test_successful_manual_sync_publishes_dashboard_snapshot(self, client, monkeypatch):
        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': date.today().year,
            'cutoff': date.today().isoformat(),
        })
        monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)

        with client.application.app_context():
            _seed_dashboard_data()

        response = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert response.status_code == 200
        body = response.get_json()
        assert body['dashboard_snapshot_id'] is not None

        with client.application.app_context():
            snapshot = DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first()
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert snapshot is not None
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
            assert snapshot.is_published is True
            assert run.stage == 'published'
            assert run.published_dashboard_snapshot_id == snapshot.id

    def test_snapshot_build_failure_fails_manual_sync_without_publish(self, client, monkeypatch):
        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: (_ for _ in ()).throw(RuntimeError('builder exploded')),
        )
        with client.application.app_context():
            failed_result = dashboard_snapshot.build_bullpen_dashboard_snapshot_v2(source='test')
            assert failed_result['status'] == 'failed'

        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': date.today().year,
            'cutoff': date.today().isoformat(),
        })
        monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)

        response = client.post('/api/bullpen/sync', json={'days_back': 7})

        assert response.status_code == 500
        with client.application.app_context():
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert run.status == 'failed'
            assert run.failed_stage == 'dashboard_snapshot'
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot() is None

    def test_successful_scheduled_sync_publishes_dashboard_snapshot(self, app, monkeypatch):
        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': date.today().year,
            'cutoff': date.today().isoformat(),
        })
        monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)
        with app.app_context():
            _seed_dashboard_data()

        status = sync_service.run_daily_sync(app, days_back=7)
        assert status['status'] == 'success'
        assert status['dashboard_snapshot_id'] is not None

        with app.app_context():
            snapshot = DashboardSnapshot.query.order_by(DashboardSnapshot.id.desc()).first()
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert snapshot is not None
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
            assert snapshot.is_published is True
            assert run.stage == 'published'
            assert run.published_dashboard_snapshot_id == snapshot.id

    def test_failure_after_logs_keeps_previous_published_snapshot(self, client, monkeypatch):
        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)

        with client.application.app_context():
            _seed_dashboard_data()
            prior, _ = _build_published_dashboard_snapshot()
            prior_snapshot_id = prior['snapshot_id']

        def commit_new_log(**kwargs):
            pitcher = Pitcher.query.first()
            db.session.add(GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=9090,
                game_date=date.today(),
                games_started=0,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                pitches_thrown=12,
                game_type='R',
            ))
            db.session.commit()
            return {
                'new_logs_added': 1,
                'pitchers_touched': 1,
                'errors': 0,
                'records_failed': 0,
                'days_back': 7,
                'season': date.today().year,
                'cutoff': date.today().isoformat(),
            }

        monkeypatch.setattr(sync_service, 'sync_recent_logs', commit_new_log)
        monkeypatch.setattr(
            sync_service,
            'recalculate_all_fatigue',
            lambda: (_ for _ in ()).throw(RuntimeError('recalc crashed')),
        )

        response = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert response.status_code == 500

        client.application.config['APP_ENV'] = 'production'
        dashboard = client.get('/api/bullpen/dashboard').get_json()
        assert dashboard['snapshot']['snapshot_id'] == prior_snapshot_id
        assert dashboard['snapshot']['served_from'] == 'cache'
        assert (
            'latest_sync_failed_serving_previous_published_view'
            in dashboard['freshness']['reason_codes']
        )

        with client.application.app_context():
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert run.status == 'failed'
            assert run.failed_stage == 'fatigue_recalculation'
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == prior_snapshot_id

    def test_failure_after_recalc_keeps_previous_published_snapshot(self, client, monkeypatch):
        monkeypatch.setattr(sync_service, 'sync_team_assignments', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_roster_statuses', _sync_scaffolding)
        monkeypatch.setattr(sync_service, 'sync_recent_logs', lambda **kwargs: {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': date.today().year,
            'cutoff': date.today().isoformat(),
        })
        monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 1)

        with client.application.app_context():
            _seed_dashboard_data()
            prior, _ = _build_published_dashboard_snapshot()
            prior_snapshot_id = prior['snapshot_id']

        monkeypatch.setattr(
            bullpen_api,
            'build_bullpen_dashboard_payload',
            lambda: (_ for _ in ()).throw(RuntimeError('snapshot crashed')),
        )

        response = client.post('/api/bullpen/sync', json={'days_back': 7})
        assert response.status_code == 500

        client.application.config['APP_ENV'] = 'production'
        dashboard = client.get('/api/bullpen/dashboard').get_json()
        assert dashboard['snapshot']['snapshot_id'] == prior_snapshot_id

        with client.application.app_context():
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            assert run.status == 'failed'
            assert run.failed_stage == 'dashboard_snapshot'
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == prior_snapshot_id

    def test_pending_snapshot_does_not_advance_served_pointer_until_publish(self, app):
        with app.app_context():
            old_data_through = date.today() - timedelta(days=2)
            pending_data_through = date.today() - timedelta(days=1)
            old_run = _create_sync_run()
            old_snapshot = dashboard_snapshot.store_dashboard_snapshot(
                {
                    **_minimal_dashboard_payload(),
                    'freshness': {
                        **_minimal_dashboard_payload()['freshness'],
                        'data_through': old_data_through.isoformat(),
                        'availability_reference_date': (old_data_through + timedelta(days=1)).isoformat(),
                        'slate_coverage': _complete_slate_coverage(old_data_through),
                    },
                },
                sync_run_id=old_run.id,
                source='test',
            )
            pending_run = _create_sync_run()
            pending = dashboard_snapshot.store_dashboard_snapshot(
                {
                    **_minimal_dashboard_payload(),
                    'freshness': {
                        **_minimal_dashboard_payload()['freshness'],
                        'data_through': pending_data_through.isoformat(),
                        'availability_reference_date': date.today().isoformat(),
                        'slate_coverage': _complete_slate_coverage(pending_data_through),
                    },
                },
                sync_run_id=pending_run.id,
                source='test',
                publish=False,
            )

            assert pending.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == old_snapshot.id

            dashboard_snapshot.publish_dashboard_snapshot(pending)
            assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == pending.id

    def test_recalculate_all_fatigue_commits_only_after_all_scores(self, app, monkeypatch):
        with app.app_context():
            today = date.today() - timedelta(days=1)
            pitchers = [
                Pitcher(mlb_id=201, full_name='Atomic One', active=True),
                Pitcher(mlb_id=202, full_name='Atomic Two', active=True),
            ]
            db.session.add_all(pitchers)
            db.session.commit()
            for index, pitcher in enumerate(pitchers, start=1):
                db.session.add(GameLog(
                    pitcher_id=pitcher.id,
                    mlb_game_pk=9200 + index,
                    game_date=today,
                    games_started=0,
                    innings_pitched=1.0,
                    innings_pitched_outs=3,
                    pitches_thrown=12,
                    game_type='R',
                ))
            db.session.commit()

            calls = {'count': 0}

            def score_or_fail(pitcher, logs, reference_date=None):
                calls['count'] += 1
                if calls['count'] == 2:
                    raise RuntimeError('score failed')
                return FatigueScore(
                    pitcher_id=pitcher.id,
                    raw_score=10.0,
                    risk_level='LOW',
                    calculated_at=utc_now_naive(),
                )

            monkeypatch.setattr(sync_service, 'calculate_fatigue', score_or_fail)

            with pytest.raises(RuntimeError):
                sync_service.recalculate_all_fatigue(reference_date=date.today())
            db.session.rollback()

            assert FatigueScore.query.count() == 0

    def test_public_fatigue_list_uses_published_score_generation(self, client):
        with client.application.app_context():
            workload_date = date.today() - timedelta(days=1)
            pitcher = Pitcher(
                mlb_id=303,
                full_name='Published Arm',
                team_id=1,
                team_name='Published Club',
                team_abbreviation='PC',
                active=True,
                roster_status=STATUS_ACTIVE,
                roster_status_source='test_fixture',
                roster_status_updated_at=utc_now_naive(),
            )
            db.session.add(pitcher)
            db.session.commit()
            db.session.add(GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=9301,
                game_date=workload_date,
                games_started=0,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                pitches_thrown=12,
                game_type='R',
            ))
            _seed_complete_slate(workload_date, [9301])
            db.session.add(FatigueScore(
                pitcher_id=pitcher.id,
                raw_score=12.0,
                risk_level='LOW',
                calculated_at=utc_now_naive() - timedelta(minutes=5),
            ))
            db.session.add(SyncRun(
                started_at=utc_now_naive() - timedelta(minutes=4),
                completed_at=utc_now_naive() - timedelta(minutes=3),
                status='success',
                stage='published',
                source='manual',
                latest_game_date=workload_date,
                latest_workload_date=workload_date,
                latest_fatigue_calculated_at=utc_now_naive() - timedelta(minutes=5),
                created_at=utc_now_naive() - timedelta(minutes=4),
            ))
            db.session.flush()
            run = SyncRun.query.order_by(SyncRun.id.desc()).first()
            snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot_v2(
                source='test',
                publish=True,
                sync_run_id=run.id,
            )
            db.session.add(FatigueScore(
                pitcher_id=pitcher.id,
                raw_score=88.0,
                risk_level='CRITICAL',
                calculated_at=utc_now_naive() + timedelta(minutes=5),
            ))
            db.session.commit()
            assert snapshot['snapshot_id'] is not None

        response = client.get('/api/bullpen/fatigue?with_meta=true&limit=10')
        body = response.get_json()

        row = next(item for item in body['data'] if item['pitcher']['full_name'] == 'Published Arm')
        assert row['raw_score'] == 12.0
