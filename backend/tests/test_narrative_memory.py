from datetime import date, timedelta
from types import SimpleNamespace

from flask import Flask
from tests.db_config import configure_test_database

import models.fatigue_score  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.narrative_memory import (
    build_bullpen_recovery_continuity,
    build_pitcher_usage_trend_continuity,
    build_team_pitcher_usage_trend_continuity,
    build_team_workload_concentration_continuity,
    build_workload_concentration_continuity,
)
from utils.db import db


REFERENCE_DATE = date(2026, 6, 12)


def pitcher(pitcher_id, name):
    return SimpleNamespace(id=pitcher_id, full_name=name)


def game_log(pitcher_id, days_ago, game_pk, pitches=14, games_started=0, name=None):
    return SimpleNamespace(
        pitcher_id=pitcher_id,
        pitcher_name=name,
        game_date=REFERENCE_DATE - timedelta(days=days_ago),
        mlb_game_pk=game_pk,
        pitches_thrown=pitches,
        games_started=games_started,
    )


def test_workload_concentration_identifies_repeated_core_usage():
    pitchers = [
        pitcher(1, 'Late Arm One'),
        pitcher(2, 'Late Arm Two'),
        pitcher(3, 'Middle Arm'),
        pitcher(4, 'Depth Arm'),
    ]
    logs = [
        game_log(1, 0, 100, pitches=18),
        game_log(1, 2, 102, pitches=17),
        game_log(1, 4, 104, pitches=16),
        game_log(1, 6, 106, pitches=15),
        game_log(2, 0, 100, pitches=13),
        game_log(2, 3, 103, pitches=14),
        game_log(2, 5, 105, pitches=12),
        game_log(3, 1, 101, pitches=11),
        game_log(3, 7, 107, pitches=10),
        game_log(4, 8, 108, pitches=9),
    ]

    result = build_workload_concentration_continuity(
        logs,
        pitchers=pitchers,
        reference_date=REFERENCE_DATE,
        window_days=10,
    )

    assert result['capability'] == 'workload_concentration_continuity'
    assert result['state'] == 'concentrated'
    assert result['window_start'] == '2026-06-03'
    assert result['window_end'] == '2026-06-12'
    assert result['data_through_date'] == '2026-06-12'
    assert result['evidence']['bullpen_appearances'] == 10
    assert result['evidence']['top_pitcher']['pitcher_name'] == 'Late Arm One'
    assert result['evidence']['top_pitcher_appearance_share'] == 0.4
    assert result['evidence']['top_two_appearance_share'] == 0.7
    assert [arm['pitcher_id'] for arm in result['evidence']['core_arms']] == [1, 2]
    assert 'handled 7 of 10 stored bullpen appearances' in result['summary']


def test_workload_concentration_excludes_starters_and_reports_thin_evidence():
    logs = [
        game_log(1, 0, 100, pitches=82, games_started=1),
        game_log(2, 0, 100, pitches=12),
        game_log(2, 2, 102, pitches=11),
    ]

    result = build_workload_concentration_continuity(
        logs,
        reference_date=REFERENCE_DATE,
        window_days=7,
    )

    assert result['state'] == 'limited'
    assert result['evidence']['bullpen_appearances'] == 2
    assert result['evidence']['top_pitcher']['pitcher_id'] == 2
    assert any('Fewer than 5 stored bullpen appearances' in item for item in result['limitations'])


def test_workload_concentration_suppresses_material_unknown_start_share():
    logs = [
        game_log(1, 0, 100, pitches=12, games_started=0),
        game_log(2, 1, 101, pitches=13, games_started=None),
        game_log(3, 2, 102, pitches=14, games_started=None),
        game_log(4, 3, 103, pitches=15, games_started=None),
    ]

    result = build_workload_concentration_continuity(
        logs,
        reference_date=REFERENCE_DATE,
        window_days=7,
    )

    assert result['state'] == 'limited'
    assert result['evidence']['bullpen_appearances'] == 1
    assert result['evidence']['unknown_start_rows_excluded'] == 3
    assert result['evidence']['start_classification_state'] == 'material_unknown'
    assert any('More than 25%' in item for item in result['limitations'])


def test_bullpen_recovery_continuity_detects_more_rest_and_less_concentration():
    pitchers = [
        pitcher(1, 'Heavy Arm'),
        pitcher(2, 'Setup Arm'),
        pitcher(3, 'Middle Arm'),
        pitcher(4, 'Lefty Arm'),
        pitcher(5, 'Depth Arm'),
    ]
    logs = [
        # Prior segment: two arms carry the work.
        game_log(1, 13, 200, pitches=20),
        game_log(1, 12, 201, pitches=19),
        game_log(1, 11, 202, pitches=18),
        game_log(1, 10, 203, pitches=17),
        game_log(1, 7, 205, pitches=16),
        game_log(2, 12, 201, pitches=14),
        game_log(2, 9, 204, pitches=13),
        game_log(2, 7, 205, pitches=12),
        # Recent segment: work spreads out, and the last two days are quieter.
        game_log(3, 6, 207, pitches=12),
        game_log(4, 5, 208, pitches=11),
        game_log(5, 3, 210, pitches=10),
    ]

    result = build_bullpen_recovery_continuity(
        logs,
        pitchers=pitchers,
        pitcher_pool=pitchers,
        reference_date=REFERENCE_DATE,
        window_days=14,
    )

    assert result['capability'] == 'bullpen_recovery_continuity'
    assert result['state'] == 'workload_easing'
    assert result['evidence']['prior_segment']['appearances'] == 8
    assert result['evidence']['recent_segment']['appearances'] == 3
    assert result['evidence']['rested_options_change'] > 0
    assert result['evidence']['top_pitcher_share_change'] < 0
    assert result['evidence']['workload_easing_signal_count'] >= 2
    assert 'flexibility improving' in result['summary']


def test_bullpen_recovery_does_not_overclaim_on_one_signal():
    pitchers = [pitcher(1, 'Heavy Arm'), pitcher(2, 'Support Arm'), pitcher(3, 'Depth Arm')]
    logs = [
        game_log(1, 13, 600, pitches=10),
        game_log(2, 12, 601, pitches=10),
        game_log(1, 11, 602, pitches=10),
        game_log(2, 10, 603, pitches=10),
        game_log(1, 9, 604, pitches=10),
        game_log(2, 8, 605, pitches=10),
        game_log(1, 6, 607, pitches=10),
        game_log(2, 5, 608, pitches=10),
        game_log(3, 4, 609, pitches=10),
        game_log(1, 3, 610, pitches=10),
        game_log(2, 2, 611, pitches=10),
        game_log(3, 1, 612, pitches=10),
    ]

    result = build_bullpen_recovery_continuity(
        logs,
        pitchers=pitchers,
        pitcher_pool=pitchers,
        reference_date=REFERENCE_DATE,
        window_days=14,
    )

    assert result['state'] == 'no_clear_workload_easing'
    assert result['evidence']['workload_easing_signals']['top_pitcher_share_decreased'] is True
    assert result['evidence']['workload_easing_signal_count'] == 1
    assert 'does not show clear workload easing' in result['summary']


def test_pitcher_usage_trend_counts_last_observed_games():
    team_logs = []
    pitcher_logs = []
    usage_games = {0, 1, 3, 5, 7, 9}
    for days_ago in range(10):
        game_pk = 300 + days_ago
        team_logs.append(game_log(2, days_ago, game_pk, pitches=10))
        if days_ago in usage_games:
            log = game_log(1, days_ago, game_pk, pitches=15)
            team_logs.append(log)
            pitcher_logs.append(log)

    result = build_pitcher_usage_trend_continuity(
        pitcher_logs,
        team_logs=team_logs,
        pitcher=pitcher(1, 'Busy Reliever'),
        reference_date=REFERENCE_DATE,
        window_days=10,
        game_windows=(6, 10),
    )

    assert result['capability'] == 'pitcher_usage_trend_continuity'
    assert result['state'] == 'stable'
    assert result['evidence']['appearance_frequency'] == [
        {'game_window': 6, 'observed_games': 6, 'appearances': 4},
        {'game_window': 10, 'observed_games': 10, 'appearances': 6},
    ]
    assert result['evidence']['window_appearances'] == 6
    assert 'appeared in 4 of the last 6 observed bullpen games' in result['summary']
    assert any('Observed game counts' in item for item in result['limitations'])


def test_pitcher_usage_trend_reports_no_appearance_in_last_seven_days():
    old_log = game_log(1, 8, 408, pitches=12)
    team_logs = [old_log]
    for days_ago in range(7):
        team_logs.append(game_log(2, days_ago, 400 + days_ago, pitches=9))

    result = build_pitcher_usage_trend_continuity(
        [old_log],
        team_logs=team_logs,
        pitcher=pitcher(1, 'Rested Reliever'),
        reference_date=REFERENCE_DATE,
        window_days=10,
        game_windows=(6,),
    )

    assert result['state'] == 'idle'
    assert result['evidence']['days_since_last_appearance'] == 8
    assert result['evidence']['appearance_frequency'][0]['appearances'] == 0
    assert result['summary'] == 'Rested Reliever has no stored bullpen appearance in the last 7 days.'


def test_narrative_memory_output_is_deterministic_and_contract_complete():
    pitchers = [pitcher(1, 'Alpha Arm'), pitcher(2, 'Beta Arm')]
    logs = [
        game_log(2, 0, 500, pitches=12),
        game_log(1, 1, 501, pitches=13),
        game_log(1, 3, 503, pitches=12),
        game_log(2, 4, 504, pitches=11),
        game_log(1, 6, 506, pitches=10),
    ]

    first = build_workload_concentration_continuity(
        logs,
        pitchers=pitchers,
        reference_date=REFERENCE_DATE,
        window_days=7,
    )
    second = build_workload_concentration_continuity(
        list(reversed(logs)),
        pitchers=list(reversed(pitchers)),
        reference_date=REFERENCE_DATE,
        window_days=7,
    )

    assert first == second
    for key in ('window_start', 'window_end', 'data_through_date', 'evidence', 'limitations'):
        assert key in first
    assert first['evidence']['top_pitcher']['pitcher_name'] == 'Alpha Arm'


def test_no_bullpen_appearances_returns_limited_contract_with_starter_evidence():
    logs = [
        game_log(1, 0, 700, pitches=82, games_started=1),
        game_log(2, 1, 701, pitches=76, games_started=1),
    ]

    result = build_workload_concentration_continuity(
        logs,
        reference_date=REFERENCE_DATE,
        window_days=7,
    )

    assert result['state'] == 'limited'
    assert result['data_through_date'] is None
    assert result['evidence']['bullpen_appearances'] == 0
    assert result['evidence']['excluded_starter_appearances'] == 2
    assert result['evidence']['top_pitcher'] is None
    assert any('Fewer than 5 stored bullpen appearances' in item for item in result['limitations'])


def test_tied_pitcher_summary_ordering_is_stable_by_name_then_id():
    pitchers = [
        pitcher(3, 'Charlie Arm'),
        pitcher(2, 'Bravo Arm'),
        pitcher(1, 'Bravo Arm'),
    ]
    logs = [
        game_log(3, 0, 800, pitches=12),
        game_log(2, 1, 801, pitches=12),
        game_log(1, 2, 802, pitches=12),
        game_log(3, 3, 803, pitches=12),
        game_log(2, 4, 804, pitches=12),
        game_log(1, 5, 805, pitches=12),
    ]

    result = build_workload_concentration_continuity(
        logs,
        pitchers=pitchers,
        reference_date=REFERENCE_DATE,
        window_days=7,
    )

    assert [row['pitcher_id'] for row in result['evidence']['top_two_pitchers']] == [1, 2]


def test_team_workload_concentration_reads_persisted_game_logs():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        pitchers = [
            Pitcher(mlb_id=901, full_name='Persisted Arm One', team_id=90, team_name='Persisted',
                    team_abbreviation='PST', active=True),
            Pitcher(mlb_id=902, full_name='Persisted Arm Two', team_id=90, team_name='Persisted',
                    team_abbreviation='PST', active=True),
            Pitcher(mlb_id=903, full_name='Persisted Starter', team_id=90, team_name='Persisted',
                    team_abbreviation='PST', active=True),
        ]
        db.session.add_all(pitchers)
        db.session.commit()
        db.session.add_all([
            GameLog(pitcher_id=pitchers[0].id, mlb_game_pk=9000, game_date=REFERENCE_DATE,
                    pitches_thrown=15, innings_pitched=1.0, innings_pitched_outs=3,
                    games_started=0, game_type='R'),
            GameLog(pitcher_id=pitchers[0].id, mlb_game_pk=9002,
                    game_date=REFERENCE_DATE - timedelta(days=2),
                    pitches_thrown=14, innings_pitched=1.0, innings_pitched_outs=3,
                    games_started=0, game_type='R'),
            GameLog(pitcher_id=pitchers[0].id, mlb_game_pk=9004,
                    game_date=REFERENCE_DATE - timedelta(days=4),
                    pitches_thrown=13, innings_pitched=1.0, innings_pitched_outs=3,
                    games_started=0, game_type='R'),
            GameLog(pitcher_id=pitchers[1].id, mlb_game_pk=9000, game_date=REFERENCE_DATE,
                    pitches_thrown=12, innings_pitched=1.0, innings_pitched_outs=3,
                    games_started=0, game_type='R'),
            GameLog(pitcher_id=pitchers[1].id, mlb_game_pk=9003,
                    game_date=REFERENCE_DATE - timedelta(days=3),
                    pitches_thrown=11, innings_pitched=1.0, innings_pitched_outs=3,
                    games_started=0, game_type='R'),
            GameLog(pitcher_id=pitchers[2].id, mlb_game_pk=9001,
                    game_date=REFERENCE_DATE - timedelta(days=1),
                    pitches_thrown=84, innings_pitched=5.0, innings_pitched_outs=15,
                    games_started=1, game_type='R'),
        ])
        db.session.commit()

        result = build_team_workload_concentration_continuity(
            90,
            reference_date=REFERENCE_DATE,
            window_days=7,
        )

        assert result['state'] == 'concentrated'
        assert result['evidence']['bullpen_appearances'] == 5
        assert result['evidence']['top_pitcher']['pitcher_name'] == 'Persisted Arm One'
        assert result['evidence']['top_two_appearance_share'] == 1
        assert any('currently assigned to the team' in item for item in result['limitations'])

        db.session.remove()
        db.drop_all()


def test_team_pitcher_usage_wrapper_reads_latest_prior_appearance():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)

    with app.app_context():
        db.create_all()
        tracked = Pitcher(mlb_id=911, full_name='Quiet Arm', team_id=91, team_name='Persisted',
                          team_abbreviation='PST', active=True)
        active_teammate = Pitcher(mlb_id=912, full_name='Active Arm', team_id=91,
                                  team_name='Persisted', team_abbreviation='PST', active=True)
        db.session.add_all([tracked, active_teammate])
        db.session.commit()
        db.session.add(GameLog(
            pitcher_id=tracked.id,
            mlb_game_pk=9108,
            game_date=REFERENCE_DATE - timedelta(days=8),
            pitches_thrown=12,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            games_started=0,
            game_type='R',
        ))
        for days_ago in range(6):
            db.session.add(GameLog(
                pitcher_id=active_teammate.id,
                mlb_game_pk=9100 + days_ago,
                game_date=REFERENCE_DATE - timedelta(days=days_ago),
                pitches_thrown=9,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                games_started=0,
                game_type='R',
            ))
        db.session.commit()

        result = build_team_pitcher_usage_trend_continuity(
            91,
            tracked.id,
            reference_date=REFERENCE_DATE,
            window_days=7,
            game_windows=(6,),
        )

        assert result['state'] == 'idle'
        assert result['evidence']['days_since_last_appearance'] == 8
        assert result['evidence']['appearance_frequency'][0]['appearances'] == 0
        assert result['summary'] == 'Quiet Arm has no stored bullpen appearance in the last 7 days.'

        db.session.remove()
        db.drop_all()
