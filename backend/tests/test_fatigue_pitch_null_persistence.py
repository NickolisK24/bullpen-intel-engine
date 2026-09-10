"""Unknown seven-day pitch evidence survives the real fatigue writer as NULL."""

from datetime import timedelta

import pytest
from flask import Flask

from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import sync as sync_service
from services.availability_reference_date import product_current_date
from services.fatigue import calculate_fatigue
from services.public_fatigue_view import public_workload_facts
from services.roster_status import STATUS_ACTIVE
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


TEAM_ID = 116


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    flask_app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')

    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _add_pitcher(mlb_id, name):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=TEAM_ID,
        team_name='Detroit Tigers',
        team_abbreviation='DET',
        position='RP',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _add_relief_log(pitcher, game_pk, game_date, pitches):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        pitches_thrown=pitches,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        games_started=0,
        game_type='R',
    ))


def _seed_unknown_and_zero_controls(reference_date):
    unknown = _add_pitcher(5116001, 'Unknown Pitch Evidence')
    _add_relief_log(
        unknown,
        95116001,
        reference_date - timedelta(days=2),
        pitches=None,
    )

    legitimate_zero = _add_pitcher(5116002, 'Legitimate Seven Day Zero')
    _add_relief_log(
        legitimate_zero,
        95116002,
        reference_date - timedelta(days=10),
        pitches=18,
    )
    db.session.commit()
    return unknown, legitimate_zero


def _logs_for(pitcher, reference_date):
    return (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher.id,
            GameLog.game_date >= reference_date - timedelta(days=14),
            GameLog.game_date <= reference_date,
        )
        .order_by(GameLog.game_date.desc())
        .all()
    )


def _latest_score(pitcher_id):
    return (
        FatigueScore.query
        .filter_by(pitcher_id=pitcher_id)
        .order_by(FatigueScore.calculated_at.desc(), FatigueScore.id.desc())
        .first()
    )


def _write_scores(reference_date):
    unknown, legitimate_zero = _seed_unknown_and_zero_controls(reference_date)
    assert sync_service.recalculate_all_fatigue(reference_date=reference_date) == 2
    db.session.expire_all()
    return unknown, legitimate_zero


def test_recalculate_all_fatigue_preserves_unknown_pitch_null_and_legitimate_zero(app):
    reference_date = product_current_date()
    unknown, legitimate_zero = _seed_unknown_and_zero_controls(reference_date)

    unknown_calculated = calculate_fatigue(
        unknown,
        _logs_for(unknown, reference_date),
        reference_date=reference_date,
    )
    assert unknown_calculated.pitches_last_7_days is None
    assert unknown_calculated.appearances_last_7 == 1
    assert unknown_calculated.days_since_last_appearance == 2
    assert unknown_calculated.pitch_count_score is None

    zero_calculated = calculate_fatigue(
        legitimate_zero,
        _logs_for(legitimate_zero, reference_date),
        reference_date=reference_date,
    )
    assert zero_calculated.pitches_last_7_days == 0
    assert zero_calculated.appearances_last_7 == 0
    assert zero_calculated.pitch_count_score == 0.0

    assert sync_service.recalculate_all_fatigue(reference_date=reference_date) == 2
    db.session.expire_all()

    unknown_persisted = _latest_score(unknown.id)
    zero_persisted = _latest_score(legitimate_zero.id)
    assert unknown_persisted.pitches_last_7_days is None
    assert unknown_persisted.appearances_last_7 == 1
    assert unknown_persisted.days_since_last_appearance == 2
    assert unknown_persisted.pitch_count_score is None
    assert public_workload_facts(unknown_persisted)['pitches_last_7_days'] is None

    assert zero_persisted.pitches_last_7_days == 0
    assert zero_persisted.appearances_last_7 == 0
    assert zero_persisted.pitch_count_score == 0.0
    assert public_workload_facts(zero_persisted)['pitches_last_7_days'] == 0


def test_pitches_last_7_days_has_no_orm_or_server_default():
    column = FatigueScore.__table__.c.pitches_last_7_days
    assert column.nullable is True
    assert column.default is None
    assert column.server_default is None


def test_public_fatigue_routes_preserve_persisted_null_and_zero(app):
    reference_date = product_current_date()
    unknown, legitimate_zero = _write_scores(reference_date)
    client = app.test_client()

    fatigue = client.get('/api/bullpen/fatigue?include_stale=true').get_json()
    fatigue_by_mlb_id = {row['pitcher']['mlb_id']: row for row in fatigue}
    assert fatigue_by_mlb_id[unknown.mlb_id]['pitches_last_7_days'] is None
    assert fatigue_by_mlb_id[legitimate_zero.mlb_id]['pitches_last_7_days'] == 0

    detail = client.get(f'/api/bullpen/fatigue/{unknown.id}').get_json()
    assert detail['current_fatigue']['pitches_last_7_days'] is None

    bullpen = client.get(
        f'/api/bullpen/teams/{TEAM_ID}/bullpen?include_stale=true'
    ).get_json()
    bullpen_by_mlb_id = {row['pitcher']['mlb_id']: row for row in bullpen}
    assert bullpen_by_mlb_id[unknown.mlb_id]['fatigue']['pitches_last_7_days'] is None
    assert bullpen_by_mlb_id[legitimate_zero.mlb_id]['fatigue']['pitches_last_7_days'] == 0
