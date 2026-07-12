from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.team_game_pitching_split import TeamGamePitchingSplit
from services.rotation_support_pressure import (
    INCOMPLETE_HISTORICAL_ATTRIBUTION_LIMITATION,
    INCOMPLETE_STARTER_IDENTIFICATION_LIMITATION,
    LIMITED_SAMPLE_LIMITATION,
    MATERIAL_EXCLUSION_LIMITATION,
    OPENER_BULK_LIMITATION,
    PARTIAL_SOURCE_COVERAGE_LIMITATION,
    STATUS_LIMITED,
    STATUS_SUPPORTIVE,
    build_team_rotation_support_pressure_from_splits,
    recent_team_game_splits,
)
from services.roster_status import STATUS_MINORS
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.innings import outs_to_decimal_innings


REF = date(2026, 6, 18)
TEAM_A = 116
TEAM_B = 142


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _pitcher(name, mlb_id, team_id, *, active=True, roster_status=None):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        active=active,
        roster_status=roster_status,
        roster_status_updated_at=datetime.utcnow() if roster_status else None,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _scheduled_game(game_pk, days_ago, *, team_id=TEAM_A, opponent_id=TEAM_B):
    game_day = REF - timedelta(days=days_ago)
    db.session.add(ScheduledGame(
        team_id=team_id,
        game_pk=game_pk,
        game_date=game_day,
        game_datetime=datetime.combine(game_day, datetime.min.time()),
        status_state=ScheduledGame.STATE_FINAL,
        status_code='F',
        home_away='home',
        opponent_team_id=opponent_id,
        game_type='R',
    ))
    db.session.flush()
    return game_day


def _split(
    game_pk,
    days_ago,
    *,
    team_id=TEAM_A,
    starter_pitcher=None,
    starter_status=TeamGamePitchingSplit.STARTER_KNOWN,
    split_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    starter_outs=18,
    bullpen_outs=9,
    total_outs=27,
    reason_codes=None,
):
    game_day = REF - timedelta(days=days_ago)
    row = TeamGamePitchingSplit(
        team_id=team_id,
        mlb_game_pk=game_pk,
        game_date=game_day,
        game_type='R',
        opponent_team_id=TEAM_B if team_id == TEAM_A else TEAM_A,
        home_away='home',
        starter_pitcher_id=starter_pitcher.id if starter_pitcher is not None else None,
        starter_mlb_id=starter_pitcher.mlb_id if starter_pitcher is not None else None,
        starter_identity_status=starter_status,
        starter_outs_recorded=starter_outs,
        starter_pitches_thrown=76 if starter_outs is not None else None,
        starter_batters_faced=20 if starter_outs is not None else None,
        starter_games_started=1 if starter_status == TeamGamePitchingSplit.STARTER_KNOWN else None,
        bullpen_outs_recorded=bullpen_outs,
        bullpen_pitches_thrown=36 if bullpen_outs is not None else None,
        bullpen_batters_faced=10 if bullpen_outs is not None else None,
        relievers_used_count=1 if bullpen_outs is not None else None,
        total_team_outs=total_outs,
        total_team_pitches=112 if total_outs is not None else None,
        total_team_batters_faced=30 if total_outs is not None else None,
        split_completeness_status=split_status,
        split_reason_codes=list(reason_codes or []),
        suspended_resumed_linkage_status=TeamGamePitchingSplit.LINKAGE_NONE,
        calendar_context_status=TeamGamePitchingSplit.STATUS_COMPLETE,
        calendar_reason_codes=[],
        source='test:team_game_pitching_split',
    )
    db.session.add(row)
    db.session.flush()
    return row


def _game_log(pitcher, game_pk, days_ago, *, outs, games_started):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=REF - timedelta(days=days_ago),
        game_type='R',
        games_started=games_started,
        innings_pitched=outs_to_decimal_innings(outs),
        innings_pitched_outs=outs,
        pitches_thrown=12,
    ))
    db.session.flush()


def _payload(team_id=TEAM_A):
    window = recent_team_game_splits(team_id, reference_date=REF)
    return build_team_rotation_support_pressure_from_splits(
        window,
        team={
            'team_id': team_id,
            'team_name': f'Team {team_id}',
            'team_abbreviation': f'T{team_id}',
        },
        reference_date=REF,
    )


def test_transaction_assignment_changes_do_not_drop_historical_team_games(app):
    with app.app_context():
        traded = _pitcher('Traded Starter', 9001, TEAM_B)
        inactive = _pitcher('Inactive Starter', 9002, TEAM_A, active=False)
        optioned = _pitcher('Optioned Starter', 9003, TEAM_A, active=False, roster_status=STATUS_MINORS)

        for idx, starter in enumerate((traded, inactive, optioned), start=1):
            game_pk = 8100 + idx
            _scheduled_game(game_pk, idx)
            _split(game_pk, idx, starter_pitcher=starter, starter_outs=18, bullpen_outs=9)
        db.session.commit()

        payload = _payload()

        assert payload['status'] == STATUS_SUPPORTIVE
        assert payload['games_in_window'] == 3
        assert payload['games_analyzed'] == 3
        assert payload['starter_outs'] == 54
        assert payload['bullpen_outs_required'] == 27
        assert payload['games_excluded'] == 0
        assert INCOMPLETE_HISTORICAL_ATTRIBUTION_LIMITATION not in payload['limitations']
        assert 'split_row_missing' not in payload['excluded_game_reasons']


def test_missing_expected_split_rows_fail_closed_with_typed_limitations(app):
    with app.app_context():
        starter = _pitcher('Known Starter', 9010, TEAM_A)
        for idx in range(1, 5):
            game_pk = 8200 + idx
            _scheduled_game(game_pk, idx)
            if idx <= 2:
                _split(game_pk, idx, starter_pitcher=starter, starter_outs=18, bullpen_outs=9)
        db.session.commit()

        payload = _payload()

        assert payload['status'] == STATUS_LIMITED
        assert payload['games_in_window'] == 4
        assert payload['games_analyzed'] == 2
        assert payload['games_excluded'] == 2
        assert payload['excluded_game_reasons'] == {'split_row_missing': 2}
        assert INCOMPLETE_HISTORICAL_ATTRIBUTION_LIMITATION in payload['limitations']
        assert PARTIAL_SOURCE_COVERAGE_LIMITATION in payload['limitations']
        assert MATERIAL_EXCLUSION_LIMITATION in payload['limitations']
        assert 'incomplete_historical_team_attribution' in payload['limitation_reasons']
        assert 'partial_source_coverage' in payload['limitation_reasons']


def test_starter_identity_and_zero_out_shape_uncertainty_fail_closed(app):
    with app.app_context():
        starter = _pitcher('Zero Out Starter', 9020, TEAM_A)
        _scheduled_game(8301, 1)
        _split(8301, 1, starter_pitcher=starter, starter_outs=0, bullpen_outs=27)
        _scheduled_game(8302, 2)
        _split(
            8302,
            2,
            starter_status=TeamGamePitchingSplit.STARTER_UNKNOWN,
            split_status=TeamGamePitchingSplit.STATUS_PARTIAL,
            starter_outs=None,
            bullpen_outs=None,
            total_outs=27,
            reason_codes=['starter_identity_unknown'],
        )
        _scheduled_game(8303, 3)
        _split(
            8303,
            3,
            starter_status=TeamGamePitchingSplit.STARTER_AMBIGUOUS,
            split_status=TeamGamePitchingSplit.STATUS_PARTIAL,
            starter_outs=None,
            bullpen_outs=None,
            total_outs=27,
            reason_codes=['starter_identity_ambiguous'],
        )
        db.session.commit()

        payload = _payload()

        assert payload['status'] == STATUS_LIMITED
        assert payload['games_analyzed'] == 0
        assert payload['games_excluded'] == 3
        assert payload['excluded_game_reasons'] == {
            'opener_bulk_unverified': 1,
            'starter_identity_unknown': 1,
            'starter_identity_ambiguous': 1,
        }
        assert INCOMPLETE_STARTER_IDENTIFICATION_LIMITATION in payload['limitations']
        assert OPENER_BULK_LIMITATION in payload['limitations']


def test_short_start_definition_is_fewer_than_fifteen_outs(app):
    with app.app_context():
        starter = _pitcher('Threshold Starter', 9030, TEAM_A)
        for game_pk, days_ago, outs in (
            (8401, 1, 14),
            (8402, 2, 15),
            (8403, 3, 18),
        ):
            _scheduled_game(game_pk, days_ago)
            _split(game_pk, days_ago, starter_pitcher=starter, starter_outs=outs, bullpen_outs=27 - outs)
        db.session.commit()

        payload = _payload()

        assert payload['games_analyzed'] == 3
        assert payload['short_start_count'] == 1
        assert payload['short_start_rate'] == 0.33
        assert payload['thresholds']['short_start_outs'] == 15
        assert payload['thresholds']['short_start_max_outs'] == 14


def test_verified_opener_bulk_and_bullpen_games_stay_separate(app):
    with app.app_context():
        opener = _pitcher('Verified Opener', 9040, TEAM_A)
        bulk = _pitcher('Verified Bulk', 9041, TEAM_A)
        relief_one = _pitcher('Bullpen Game One', 9042, TEAM_A)
        relief_two = _pitcher('Bullpen Game Two', 9043, TEAM_A)

        _scheduled_game(8501, 1)
        _split(8501, 1, starter_pitcher=opener, starter_outs=3, bullpen_outs=24)
        _game_log(opener, 8501, 1, outs=3, games_started=1)
        _game_log(bulk, 8501, 1, outs=24, games_started=0)

        _scheduled_game(8502, 2)
        _split(
            8502,
            2,
            starter_status=TeamGamePitchingSplit.STARTER_UNKNOWN,
            split_status=TeamGamePitchingSplit.STATUS_PARTIAL,
            starter_outs=None,
            bullpen_outs=None,
            total_outs=27,
            reason_codes=['starter_identity_unknown'],
        )
        _game_log(relief_one, 8502, 2, outs=15, games_started=0)
        _game_log(relief_two, 8502, 2, outs=12, games_started=0)
        db.session.commit()

        payload = _payload()

        assert payload['games_in_window'] == 2
        assert payload['games_analyzed'] == 0
        assert payload['games_excluded'] == 0
        assert payload['opener_bulk_games'] == 1
        assert payload['bulk_follower_outs'] == 24
        assert payload['bullpen_games'] == 1
        assert payload['bullpen_game_outs'] == 27
        assert payload['status'] == STATUS_LIMITED
        assert LIMITED_SAMPLE_LIMITATION in payload['limitations']
