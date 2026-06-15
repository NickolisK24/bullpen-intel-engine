from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import event

import models.prospect  # noqa: F401  (register on db.metadata)
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    SNAPSHOT_REFERENCE_STRATEGY,
    SNAPSHOT_WARNING,
    availability_mode_metadata,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db
from utils.time import utc_now_naive


@pytest.fixture
def client():
    with _SnapshotAppClient() as test_client:
        yield test_client


@pytest.fixture
def production_client():
    with _SnapshotAppClient(app_env='production', admin_token='secret') as test_client:
        yield test_client


@pytest.fixture
def development_open_client():
    with _SnapshotAppClient(app_env='development', admin_token=None) as test_client:
        yield test_client


@pytest.fixture
def production_no_token_client():
    with _SnapshotAppClient(app_env='production', admin_token=None) as test_client:
        yield test_client


class _SnapshotAppClient:
    def __init__(self, app_env='development', admin_token='secret'):
        self.app = Flask(__name__)
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
        self.app.config['APP_ENV'] = app_env
        self.app.config['ADMIN_API_TOKEN'] = admin_token
        db.init_app(self.app)
        self.app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
        self.context = None

    def __enter__(self):
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()
        return self.app.test_client()

    def __exit__(self, exc_type, exc, tb):
        db.session.remove()
        db.drop_all()
        self.context.pop()


def _risk_for_score(raw_score):
    if raw_score >= 85:
        return 'CRITICAL'
    if raw_score >= 70:
        return 'HIGH'
    if raw_score >= 40:
        return 'MODERATE'
    return 'LOW'


def _add_pitcher(name, latest_game_date=None, raw_score=20.0, log_pitches=None, mlb_seed=1):
    pitcher = Pitcher(
        mlb_id=700000 + mlb_seed,
        full_name=name,
        team_id=1,
        team_name='Snapshot Club',
        team_abbreviation='SNP',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()

    for index, pitches in enumerate(log_pitches or []):
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=800000 + (mlb_seed * 100) + index,
            game_date=latest_game_date - timedelta(days=index),
            pitches_thrown=pitches,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            games_started=0,
        ))

    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=utc_now_naive(),
        raw_score=raw_score,
        pitch_count_score=0.0,
        rest_days_score=0.0,
        appearances_score=0.0,
        innings_score=0.0,
        leverage_score=0.0,
        days_since_last_appearance=0,
        appearances_last_7=len(log_pitches or []),
        appearances_last_14=len(log_pitches or []),
        pitches_last_7_days=sum(log_pitches or []),
        innings_last_7_days=float(len(log_pitches or [])),
        risk_level=_risk_for_score(raw_score),
    ))
    db.session.commit()
    return pitcher


def test_current_mode_remains_calendar_based_and_can_be_available(client):
    with client.application.app_context():
        ref = date.today()
        _add_pitcher(
            'Light Current Workload',
            latest_game_date=ref - timedelta(days=3),
            raw_score=18.0,
            log_pitches=[8],
        )

        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(),
            reference_date=ref,
            mode=CURRENT_AVAILABILITY_MODE,
        )

    assert records[0]['evaluation_date'] == ref
    assert records[0]['availability']['availability_status'] == 'Available'
    assert records[0]['availability']['confidence'] == 'high'
    assert records[0]['availability']['data_state'] == 'fresh'


def test_current_mode_batches_availability_evidence_queries(client):
    with client.application.app_context():
        ref = date.today()
        for seed in range(1, 6):
            _add_pitcher(
                f'Current Batch Arm {seed}',
                latest_game_date=ref - timedelta(days=seed % 4),
                raw_score=18.0 + seed,
                log_pitches=[8 + seed],
                mlb_seed=seed,
            )

        rows = latest_fatigue_rows()
        game_log_selects = []

        def collect_game_log_selects(_conn, _cursor, statement, _params, _context, _executemany):
            normalized = ' '.join(statement.lower().split())
            if normalized.startswith('select') and 'from game_logs' in normalized:
                game_log_selects.append(normalized)

        event.listen(db.engine, 'before_cursor_execute', collect_game_log_selects)
        try:
            records = classify_latest_fatigue_rows(
                rows,
                reference_date=ref,
                mode=CURRENT_AVAILABILITY_MODE,
            )
        finally:
            event.remove(db.engine, 'before_cursor_execute', collect_game_log_selects)

    assert len(records) == 5
    assert all(record['availability']['data_state'] == 'fresh' for record in records)
    assert len(game_log_selects) <= 2


def test_snapshot_mode_uses_latest_workload_date_and_non_current_metadata(client):
    with client.application.app_context():
        latest = date.today() - timedelta(days=30)
        _add_pitcher(
            'Historical Snapshot Workload',
            latest_game_date=latest,
            raw_score=32.0,
            log_pitches=[18],
        )

        rows = latest_fatigue_rows()
        records = classify_latest_fatigue_rows(
            rows,
            reference_date=date.today(),
            mode=LATEST_WORKLOAD_SNAPSHOT_MODE,
        )
        meta = availability_mode_metadata(LATEST_WORKLOAD_SNAPSHOT_MODE, records=records)

    assert records[0]['evaluation_date'] == latest
    assert records[0]['availability']['inputs']['reference_date'] == latest.isoformat()
    assert records[0]['availability']['data_state'] == 'fresh'
    assert meta == {
        'mode': LATEST_WORKLOAD_SNAPSHOT_MODE,
        'snapshot_date': latest.isoformat(),
        'reference_strategy': SNAPSHOT_REFERENCE_STRATEGY,
        'is_current_availability': False,
        'warning': SNAPSHOT_WARNING,
    }


def test_snapshot_mode_produces_mixed_workload_statuses_from_sample_data(client):
    with client.application.app_context():
        anchor = date(2026, 5, 1)
        _add_pitcher('Snapshot Monitor', latest_game_date=anchor, raw_score=20.0, log_pitches=[5], mlb_seed=1)
        _add_pitcher('Snapshot Limited', latest_game_date=anchor, raw_score=20.0, log_pitches=[45], mlb_seed=2)
        _add_pitcher('Snapshot Avoid', latest_game_date=anchor, raw_score=20.0, log_pitches=[65], mlb_seed=3)
        _add_pitcher('Snapshot Unavailable', latest_game_date=anchor, raw_score=20.0, log_pitches=[90], mlb_seed=4)

        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(),
            reference_date=date.today(),
            mode=LATEST_WORKLOAD_SNAPSHOT_MODE,
        )
        by_name = {
            record['pitcher_name']: record['availability']
            for record in records
        }

    assert by_name['Snapshot Monitor']['availability_status'] == 'Monitor'
    assert by_name['Snapshot Limited']['availability_status'] == 'Limited'
    assert by_name['Snapshot Avoid']['availability_status'] == 'Avoid'
    assert by_name['Snapshot Unavailable']['availability_status'] == 'Unavailable'
    for availability in by_name.values():
        assert availability['data_state'] == 'fresh'
        assert availability['reasons']


def test_current_mode_keeps_stale_data_truthful(client):
    with client.application.app_context():
        _add_pitcher(
            'Stale Calendar Workload',
            latest_game_date=date.today() - timedelta(days=30),
            raw_score=78.0,
            log_pitches=[44],
        )

        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(),
            reference_date=date.today(),
            mode=CURRENT_AVAILABILITY_MODE,
        )

    availability = records[0]['availability']
    assert availability['availability_status'] == 'Monitor'
    assert availability['confidence'] == 'low'
    assert availability['data_state'] == 'stale'
    assert 'Recent usage information is incomplete, so workload data must not be treated as current availability' in availability['limitations']


def test_snapshot_mode_keeps_missing_data_truthful(client):
    with client.application.app_context():
        _add_pitcher(
            'Missing Workload History',
            latest_game_date=None,
            raw_score=22.0,
            log_pitches=[],
        )

        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(),
            reference_date=date.today(),
            mode=LATEST_WORKLOAD_SNAPSHOT_MODE,
        )

    availability = records[0]['availability']
    assert availability['availability_status'] == 'Monitor'
    assert availability['confidence'] == 'low'
    assert availability['data_state'] == 'missing'
    assert availability['reasons'] == ['Missing workload history or fatigue score']


def test_snapshot_endpoint_is_admin_gated_and_marks_non_current(client):
    with client.application.app_context():
        _add_pitcher(
            'Endpoint Snapshot Workload',
            latest_game_date=date(2026, 5, 1),
            raw_score=64.0,
            log_pitches=[45],
        )

    rejected = client.get('/api/bullpen/fatigue/snapshot')
    accepted = client.get(
        '/api/bullpen/fatigue/snapshot',
        headers={ADMIN_TOKEN_HEADER: 'secret'},
    )

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    body = accepted.get_json()
    assert body['meta']['mode'] == LATEST_WORKLOAD_SNAPSHOT_MODE
    assert body['meta']['snapshot_date'] == '2026-05-01'
    assert body['meta']['is_current_availability'] is False
    assert body['meta']['warning'] == SNAPSHOT_WARNING
    assert accepted.headers['X-BaseballOS-Data-Mode'] == LATEST_WORKLOAD_SNAPSHOT_MODE
    assert accepted.headers['X-BaseballOS-Current-Availability'] == 'false'
    assert body['data'][0]['availability_mode']['mode'] == LATEST_WORKLOAD_SNAPSHOT_MODE
    assert body['data'][0]['availability_mode']['is_current_availability'] is False
    assert body['data'][0]['availability']['data_state'] == 'fresh'


def test_snapshot_endpoint_denies_unauthorized_production_without_leaking_data(production_client):
    with production_client.application.app_context():
        _add_pitcher(
            'Protected Snapshot Workload',
            latest_game_date=date(2026, 5, 1),
            raw_score=64.0,
            log_pitches=[45],
        )

    res = production_client.get('/api/bullpen/fatigue/snapshot')

    assert res.status_code == 401
    body = res.get_json()
    assert 'error' in body
    assert 'data' not in body
    assert 'meta' not in body
    assert 'X-BaseballOS-Data-Mode' not in res.headers
    assert 'X-BaseballOS-Current-Availability' not in res.headers


def test_snapshot_endpoint_denies_production_when_admin_token_is_not_configured(production_no_token_client):
    with production_no_token_client.application.app_context():
        _add_pitcher(
            'Disabled Snapshot Workload',
            latest_game_date=date(2026, 5, 1),
            raw_score=64.0,
            log_pitches=[45],
        )

    res = production_no_token_client.get('/api/bullpen/fatigue/snapshot')

    assert res.status_code == 403
    body = res.get_json()
    assert 'error' in body
    assert 'ADMIN_API_TOKEN' in body['error']
    assert 'data' not in body
    assert 'meta' not in body


def test_snapshot_endpoint_allows_development_without_token_when_unconfigured(development_open_client):
    with development_open_client.application.app_context():
        _add_pitcher(
            'Development Snapshot Workload',
            latest_game_date=date(2026, 5, 1),
            raw_score=64.0,
            log_pitches=[45],
        )

    res = development_open_client.get('/api/bullpen/fatigue/snapshot')

    assert res.status_code == 200
    body = res.get_json()
    assert body['meta']['mode'] == LATEST_WORKLOAD_SNAPSHOT_MODE
    assert body['meta']['is_current_availability'] is False
    assert body['meta']['warning'] == SNAPSHOT_WARNING
    assert res.headers['X-BaseballOS-Data-Mode'] == LATEST_WORKLOAD_SNAPSHOT_MODE
    assert res.headers['X-BaseballOS-Current-Availability'] == 'false'


def test_public_current_fatigue_endpoint_remains_open_with_admin_token_configured(production_client):
    with production_client.application.app_context():
        _add_pitcher(
            'Public Current Workload',
            latest_game_date=date.today(),
            raw_score=24.0,
            log_pitches=[8],
        )

    res = production_client.get('/api/bullpen/fatigue?include_stale=true')

    assert res.status_code == 200
    body = res.get_json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]['availability']['inputs']['reference_date'] == date.today().isoformat()


def test_audit_script_uses_shared_snapshot_path():
    import scripts.audit_availability_thresholds as audit_script

    assert audit_script.LATEST_WORKLOAD_SNAPSHOT_MODE == LATEST_WORKLOAD_SNAPSHOT_MODE
    assert audit_script.classify_latest_fatigue_rows is classify_latest_fatigue_rows


def test_audit_build_uses_shared_current_and_snapshot_modes(monkeypatch):
    import scripts.audit_availability_thresholds as audit_script

    calls = []

    def fake_latest_fatigue_rows():
        return [('score', 'pitcher')]

    def fake_classify_latest_fatigue_rows(rows, reference_date=None, mode=None):
        calls.append({
            'rows': rows,
            'reference_date': reference_date,
            'mode': mode,
        })
        return [{
            'pitcher_id': 1,
            'pitcher_name': mode,
            'team': 'TST',
            'availability': {
                'availability_status': 'Available',
                'confidence': 'high',
                'data_state': 'fresh',
                'reasons': [],
                'limitations': [],
                'inputs': {
                    'fatigue_score': 10,
                    'pitches_yesterday': 0,
                    'pitches_last_3_days': 0,
                    'pitches_last_5_days': 0,
                    'appearances_last_3_days': 0,
                    'appearances_last_5_days': 0,
                },
            },
        }]

    monkeypatch.setattr(audit_script, 'latest_fatigue_rows', fake_latest_fatigue_rows)
    monkeypatch.setattr(audit_script, 'classify_latest_fatigue_rows', fake_classify_latest_fatigue_rows)

    ref = date(2026, 6, 1)
    audit = audit_script.build_audit(reference_date=ref, near_threshold_limit=1)

    assert [call['mode'] for call in calls] == [
        CURRENT_AVAILABILITY_MODE,
        LATEST_WORKLOAD_SNAPSHOT_MODE,
    ]
    assert all(call['reference_date'] == ref for call in calls)
    assert audit['current']['total_pitchers'] == 1
    assert audit['latest_workload_snapshot']['total_pitchers'] == 1
