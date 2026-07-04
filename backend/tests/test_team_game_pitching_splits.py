from datetime import date, datetime, timedelta
import json

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import services.sync as sync_service
import services.team_game_pitching_splits as split_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import sync_metadata
from utils.db import db
import models.prospect  # noqa: F401


@pytest.fixture
def app():
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


@pytest.fixture
def client(app):
    return app.test_client()


def _add_pitcher(mlb_id, team_id, name=None):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name or f'Pitcher {mlb_id}',
        team_id=team_id,
        team_abbreviation=f'T{team_id}',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _add_log(
    pitcher,
    game_pk,
    game_date,
    *,
    games_started,
    outs,
    pitches,
    batters_faced,
    balls,
):
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        games_started=games_started,
        innings_pitched=outs / 3.0,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        batters_faced=batters_faced,
        balls=balls,
    )
    db.session.add(log)
    db.session.flush()
    return log


def _seed_game(
    game_pk,
    game_date,
    *,
    home_id=116,
    away_id=142,
    status_state=ScheduledGame.STATE_FINAL,
    doubleheader='N',
    game_number=1,
    series_game_number=1,
    games_in_series=3,
    original_product_date=None,
    resumed_product_date=None,
    resumed_from_game_pk=None,
):
    db.session.add_all([
        ScheduledGame(
            team_id=home_id,
            game_pk=game_pk,
            game_date=game_date,
            game_datetime=datetime.combine(game_date, datetime.min.time()),
            status_state=status_state,
            status_code='F' if status_state == ScheduledGame.STATE_FINAL else 'S',
            home_away='home',
            opponent_team_id=away_id,
            game_type='R',
            doubleheader=doubleheader,
            game_number=game_number,
            series_game_number=series_game_number,
            games_in_series=games_in_series,
            original_product_date=original_product_date,
            resumed_product_date=resumed_product_date,
            resumed_from_game_pk=resumed_from_game_pk,
        ),
        ScheduledGame(
            team_id=away_id,
            game_pk=game_pk,
            game_date=game_date,
            game_datetime=datetime.combine(game_date, datetime.min.time()),
            status_state=status_state,
            status_code='F' if status_state == ScheduledGame.STATE_FINAL else 'S',
            home_away='away',
            opponent_team_id=home_id,
            game_type='R',
            doubleheader=doubleheader,
            game_number=game_number,
            series_game_number=series_game_number,
            games_in_series=games_in_series,
            original_product_date=original_product_date,
            resumed_product_date=resumed_product_date,
            resumed_from_game_pk=resumed_from_game_pk,
        ),
    ])
    db.session.flush()


def _seed_calendar_marker(team_id, game_pk, game_date, *, state=ScheduledGame.STATE_SCHEDULED):
    db.session.add(ScheduledGame(
        team_id=team_id,
        game_pk=game_pk,
        game_date=game_date,
        status_state=state,
        home_away='home',
        opponent_team_id=999,
        game_type='R',
    ))
    db.session.flush()


def _seed_complete_pitching_lines(game_pk, game_date, *, home_id=116, away_id=142):
    id_base = game_pk * 10
    home_starter = _add_pitcher(id_base + 1, home_id, 'Home Starter')
    home_reliever = _add_pitcher(id_base + 2, home_id, 'Home Reliever')
    away_starter = _add_pitcher(id_base + 3, away_id, 'Away Starter')
    away_reliever = _add_pitcher(id_base + 4, away_id, 'Away Reliever')
    _add_log(
        home_starter,
        game_pk,
        game_date,
        games_started=1,
        outs=15,
        pitches=80,
        batters_faced=20,
        balls=30,
    )
    _add_log(
        home_reliever,
        game_pk,
        game_date,
        games_started=0,
        outs=12,
        pitches=45,
        batters_faced=13,
        balls=18,
    )
    _add_log(
        away_starter,
        game_pk,
        game_date,
        games_started=1,
        outs=18,
        pitches=90,
        batters_faced=24,
        balls=35,
    )
    _add_log(
        away_reliever,
        game_pk,
        game_date,
        games_started=0,
        outs=9,
        pitches=33,
        batters_faced=10,
        balls=12,
    )
    db.session.commit()


def _split(team_id, game_pk):
    return TeamGamePitchingSplit.query.filter_by(
        team_id=team_id,
        mlb_game_pk=game_pk,
    ).one()


def test_final_game_creates_two_team_game_split_rows_with_calendar_context(app):
    with app.app_context():
        game_day = date(2026, 6, 10)
        _seed_calendar_marker(116, 9001, game_day - timedelta(days=1))
        _seed_calendar_marker(116, 9002, game_day + timedelta(days=1))
        _seed_game(7001, game_day, series_game_number=2, game_number=1)
        _seed_complete_pitching_lines(7001, game_day)

        result = split_service.recompute_team_game_pitching_splits_for_game(7001)
        db.session.commit()

        assert result['rows_inserted'] == 2
        assert TeamGamePitchingSplit.query.count() == 2
        home = _split(116, 7001)
        away = _split(142, 7001)
        assert home.starter_identity_status == TeamGamePitchingSplit.STARTER_KNOWN
        assert home.split_completeness_status == TeamGamePitchingSplit.STATUS_COMPLETE
        assert home.starter_outs_recorded == 15
        assert home.bullpen_outs_recorded == 12
        assert home.bullpen_pitches_thrown == 45
        assert home.bullpen_batters_faced == 13
        assert home.relievers_used_count == 1
        assert home.total_team_outs == 27
        assert home.total_team_pitches == 125
        assert home.extra_inning_indicator is False
        assert home.off_day_before is False
        assert home.off_day_after is False
        assert home.consecutive_game_day_count_entering == 1
        assert home.series_game_number == 2
        assert home.game_number == 1
        assert home.doubleheader_flag is False
        assert home.calendar_context_status == TeamGamePitchingSplit.STATUS_COMPLETE
        assert away.starter_identity_status == TeamGamePitchingSplit.STARTER_KNOWN


def test_missing_starter_identity_marks_split_partial_and_safe_unknown(app):
    with app.app_context():
        game_day = date(2026, 6, 11)
        _seed_game(7002, game_day)
        pitcher = _add_pitcher(3001, 116)
        _add_log(
            pitcher,
            7002,
            game_day,
            games_started=None,
            outs=3,
            pitches=14,
            batters_faced=4,
            balls=5,
        )
        db.session.commit()

        split_service.recompute_team_game_pitching_splits_for_game(7002)
        db.session.commit()

        row = _split(116, 7002)
        assert row.starter_identity_status == TeamGamePitchingSplit.STARTER_UNKNOWN
        assert row.split_completeness_status == TeamGamePitchingSplit.STATUS_PARTIAL
        assert row.starter_pitcher_id is None
        assert row.bullpen_pitches_thrown is None
        assert row.relievers_used_count is None
        assert 'starter_games_started_unknown' in row.split_reason_codes


def test_ambiguous_starter_identity_marks_split_partial(app):
    with app.app_context():
        game_day = date(2026, 6, 12)
        _seed_game(7003, game_day)
        first = _add_pitcher(3101, 116)
        second = _add_pitcher(3102, 116)
        _add_log(first, 7003, game_day, games_started=1, outs=9, pitches=45,
                 batters_faced=12, balls=18)
        _add_log(second, 7003, game_day, games_started=1, outs=6, pitches=31,
                 batters_faced=8, balls=12)
        db.session.commit()

        split_service.recompute_team_game_pitching_splits_for_game(7003)
        db.session.commit()

        row = _split(116, 7003)
        assert row.starter_identity_status == TeamGamePitchingSplit.STARTER_AMBIGUOUS
        assert row.split_completeness_status == TeamGamePitchingSplit.STATUS_PARTIAL
        assert row.starter_pitcher_id is None
        assert row.relievers_used_count is None
        assert 'starter_identity_ambiguous' in row.split_reason_codes


def test_nullable_arithmetic_propagates_unknown_and_explicit_zero_remains_zero(app):
    with app.app_context():
        game_day = date(2026, 6, 13)
        _seed_game(7004, game_day)
        starter = _add_pitcher(3201, 116)
        reliever = _add_pitcher(3202, 116)
        _add_log(starter, 7004, game_day, games_started=1, outs=15, pitches=80,
                 batters_faced=20, balls=0)
        _add_log(reliever, 7004, game_day, games_started=0, outs=12, pitches=None,
                 batters_faced=13, balls=0)
        db.session.commit()

        split_service.recompute_team_game_pitching_splits_for_game(7004)
        db.session.commit()

        row = _split(116, 7004)
        assert row.starter_balls == 0
        assert row.bullpen_balls == 0
        assert row.bullpen_pitches_thrown is None
        assert row.total_team_pitches is None
        assert row.split_completeness_status == TeamGamePitchingSplit.STATUS_PARTIAL
        assert 'bullpen_pitches_unknown' in row.split_reason_codes
        assert 'total_team_pitches_unknown' in row.split_reason_codes


def test_doubleheader_games_remain_separate_by_game_pk(app):
    with app.app_context():
        game_day = date(2026, 6, 14)
        _seed_game(7005, game_day, doubleheader='Y', game_number=1)
        _seed_game(7006, game_day, doubleheader='Y', game_number=2)
        _seed_complete_pitching_lines(7005, game_day)
        _seed_complete_pitching_lines(7006, game_day)

        split_service.recompute_team_game_pitching_splits_for_game(7005)
        split_service.recompute_team_game_pitching_splits_for_game(7006)
        db.session.commit()

        first = _split(116, 7005)
        second = _split(116, 7006)
        assert first.mlb_game_pk != second.mlb_game_pk
        assert first.game_number == 1
        assert second.game_number == 2
        assert first.doubleheader_flag is True
        assert second.doubleheader_flag is True


def test_suspended_resumed_ambiguity_fails_closed(app):
    with app.app_context():
        game_day = date(2026, 6, 15)
        _seed_game(
            7007,
            game_day,
            resumed_from_game_pk=6001,
            resumed_product_date=game_day,
            original_product_date=None,
        )
        _seed_complete_pitching_lines(7007, game_day)

        split_service.recompute_team_game_pitching_splits_for_game(7007)
        db.session.commit()

        row = _split(116, 7007)
        assert row.starter_identity_status == TeamGamePitchingSplit.STARTER_UNKNOWN
        assert row.split_completeness_status == TeamGamePitchingSplit.STATUS_UNKNOWN
        assert row.calendar_context_status == TeamGamePitchingSplit.STATUS_UNKNOWN
        assert row.suspended_resumed_linkage_status == TeamGamePitchingSplit.LINKAGE_AMBIGUOUS
        assert 'suspended_resumed_ambiguous' in row.split_reason_codes
        assert 'suspended_resumed_ambiguous' in row.calendar_reason_codes


def test_recompute_is_idempotent_until_upstream_game_log_correction(app):
    with app.app_context():
        game_day = date(2026, 6, 16)
        _seed_game(7008, game_day)
        _seed_complete_pitching_lines(7008, game_day)

        split_service.recompute_team_game_pitching_splits_for_game(7008)
        db.session.commit()
        row = _split(116, 7008)
        assert row.correction_count == 0
        assert row.total_team_pitches == 125

        split_service.recompute_team_game_pitching_splits_for_game(7008)
        db.session.commit()
        row = _split(116, 7008)
        assert row.correction_count == 0

        reliever_log = (
            db.session.query(GameLog)
            .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
            .filter(GameLog.mlb_game_pk == 7008)
            .filter(Pitcher.team_id == 116)
            .filter(GameLog.games_started == 0)
            .one()
        )
        reliever_log.pitches_thrown = 50
        db.session.commit()

        split_service.recompute_team_game_pitching_splits_for_game(7008)
        db.session.commit()
        row = _split(116, 7008)
        assert row.correction_count == 1
        assert row.bullpen_pitches_thrown == 50
        assert row.total_team_pitches == 130
        assert row.correction_source == split_service.CORRECTION_SOURCE


def test_non_final_game_skips_split_storage(app):
    with app.app_context():
        game_day = date(2026, 6, 17)
        _seed_game(7009, game_day, status_state=ScheduledGame.STATE_SCHEDULED)
        _seed_complete_pitching_lines(7009, game_day)

        result = split_service.recompute_team_game_pitching_splits_for_game(7009)
        db.session.commit()

        assert result['status'] == 'skipped'
        assert result['reason'] == 'not_final'
        assert TeamGamePitchingSplit.query.count() == 0


def test_split_failure_does_not_corrupt_committed_game_logs(app, monkeypatch):
    with app.app_context():
        game_day = date(2026, 6, 18)
        pitcher = _add_pitcher(3301, 116)
        _add_log(pitcher, 7010, game_day, games_started=1, outs=3, pitches=12,
                 batters_faced=4, balls=5)
        db.session.commit()

        def fail_schedule_lookup(game_pk):
            raise RuntimeError(f'schedule lookup failed for {game_pk}')

        monkeypatch.setattr(split_service, '_scheduled_rows_for_game', fail_schedule_lookup)
        result = split_service.safe_recompute_team_game_pitching_splits_for_game(7010)

        assert result['status'] == 'failed'
        assert GameLog.query.count() == 1
        failure = SyncFailure.query.filter_by(
            entity_type=split_service.TEAM_GAME_PITCHING_SPLIT_FAILURE_ENTITY_TYPE,
        ).one()
        assert failure.entity_ref == '7010'


def test_split_rows_are_not_public_sync_status_serialized(
    client,
    monkeypatch,
    tmp_path,
):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(sync_metadata, 'product_current_date', lambda: date(2026, 6, 19))
    with client.application.app_context():
        game_day = date(2026, 6, 18)
        _seed_game(7011, game_day)
        _seed_complete_pitching_lines(7011, game_day)
        split_service.recompute_team_game_pitching_splits_for_game(7011)
        db.session.add(FatigueScore(
            pitcher_id=Pitcher.query.first().id,
            raw_score=10.0,
            calculated_at=datetime(2026, 6, 19, 9, 0, 0),
        ))
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=7011,
            game_date=game_day,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
        db.session.commit()

    response = client.get('/api/bullpen/sync/status')
    assert response.status_code == 200
    payload_text = json.dumps(response.get_json(), sort_keys=True)
    assert 'team_game_pitching_splits' not in payload_text
    assert 'calendar_context' not in payload_text
