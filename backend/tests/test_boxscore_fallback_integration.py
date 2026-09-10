"""End-to-end box-score fallback behaviour through the real daily lane.

The unit suites prove the authority rule and the single-appearance write path.
These scenarios run the whole ``sync_recent_logs`` lane against PostgreSQL 16 —
the engine production uses — because three of the properties that matter only
exist at lane scale:

* the fallback accounting has to reach the run summary, or an operator reading
  an artifact cannot tell a quiet day from an uninstrumented one;
* the box-score fetch has to stay bounded across a whole horizon, not just
  within one appearance;
* a source failure has to remain a counted non-event rather than a lane
  failure — the fallback is an enrichment, and enrichment must never be able to
  take the daily correction lane down.

Scenarios are lettered so the artifact and the review can refer to them.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database, create_test_schema, drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import gamelog_source_authority as authority
from services import sync as sync_service
from utils.db import db


SLATE = date(2026, 6, 20)
REFERENCE = date(2026, 6, 21)
GAME_PK = 970001
PITCHER_MLB_ID = 970100
OTHER_PITCHER_MLB_ID = 970200
HOME_TEAM_ID = 111
AWAY_TEAM_ID = 222


@pytest.fixture
def app():
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


def _schedule(game_pk=GAME_PK):
    for team_id, opponent_id, side in (
        (HOME_TEAM_ID, AWAY_TEAM_ID, 'home'),
        (AWAY_TEAM_ID, HOME_TEAM_ID, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=SLATE,
            game_datetime=datetime(2026, 6, 20, 19, 5),
            opponent_team_id=opponent_id, home_away=side, game_type='R',
            status_code='F', status_state=ScheduledGame.STATE_FINAL,
        ))


def _pitcher(mlb_id=PITCHER_MLB_ID, name='Test Arm'):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=HOME_TEAM_ID,
        team_abbreviation='HOM', active=True,
    )
    db.session.add(pitcher)
    return pitcher


def _row(pitcher, *, balls=20, game_pk=GAME_PK):
    row = GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=SLATE,
        game_type='R', innings_pitched_outs=9, innings_pitched=3.0,
        pitches_thrown=45, strikes=26, balls=balls, hits_allowed=2,
        runs_allowed=1, earned_runs=1, walks=1, strikeouts=4,
        home_runs_allowed=0, games_started=0, batters_faced=12,
        opponent='Away Club', opponent_abbreviation='AWY',
        last_stat_correction_source=sync_service.DAILY_GAME_LOG_CORRECTION_SOURCE,
        stat_correction_count=1,
    )
    db.session.add(row)
    return row


def _lines(*, balls=19, strikes=26, pitches=45, player_id=PITCHER_MLB_ID):
    return [{
        'player_id': player_id, 'side': 'home', 'team_id': HOME_TEAM_ID,
        'stats': {
            'balls': balls, 'strikes': strikes, 'numberOfPitches': pitches,
            'inningsPitched': '3.0',
        },
    }]


def _splits(*, with_balls=None, **stat_overrides):
    stat = {
        'inningsPitched': '3.0', 'strikes': 26, 'numberOfPitches': 45,
        'hits': 2, 'runs': 1, 'earnedRuns': 1, 'baseOnBalls': 1,
        'strikeOuts': 4, 'homeRuns': 0, 'battersFaced': 12, 'gamesStarted': 0,
    }
    if with_balls is not None:
        stat['balls'] = with_balls
    stat.update(stat_overrides)
    return [{
        'date': SLATE.isoformat(),
        'game': {
            'gamePk': GAME_PK, 'gameType': 'R',
            'status': {
                'statusCode': 'F', 'detailedState': 'Final',
                'abstractGameState': 'Final',
            },
        },
        'opponent': {'id': AWAY_TEAM_ID, 'name': 'Away Club'},
        'stat': stat,
    }]


@pytest.fixture
def lane(app, monkeypatch):
    """A one-appearance horizon with controllable sources."""
    state = {'boxscore_calls': [], 'split_calls': []}

    def lines(game_pk):
        state['boxscore_calls'].append(game_pk)
        return state['lines'](game_pk)

    def splits(mlb_id, season=None):
        state['split_calls'].append(mlb_id)
        return state['splits'](mlb_id)

    state['lines'] = lambda game_pk: _lines()
    state['splits'] = lambda mlb_id: _splits()
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines', lines)
    monkeypatch.setattr(sync_service.mlb_client, 'get_pitcher_game_logs', splits)

    _schedule()
    pitcher = _pitcher()
    db.session.flush()
    _row(pitcher)
    db.session.commit()
    state['pitcher'] = pitcher
    return state


def _run():
    result = sync_service.sync_recent_logs(
        days_back=7, reference_date=REFERENCE,
    )
    db.session.commit()
    return result


# ── A. A lane with nothing to enrich still reports the fallback ─────────────


def test_scenario_a_a_split_that_supplies_the_field_leaves_zeros(lane):
    lane['splits'] = lambda mlb_id: _splits(with_balls=20)
    result = _run()

    assert result['boxscore_fallback_eligible_rows'] == 0
    assert result['boxscore_fallback_applied_rows'] == 0
    assert result['boxscore_fallback_fetches'] == 0
    assert result['boxscore_fallback_authority'] == authority.AUTHORITY_CONTRACT
    assert lane['boxscore_calls'] == []


# ── B. The defect class, corrected through the whole lane ──────────────────


def test_scenario_b_the_uncorrectable_field_is_corrected_and_counted(lane):
    result = _run()

    row = GameLog.query.one()
    assert row.balls == 19
    assert result['logs_corrected'] == 1
    assert result['boxscore_fallback_eligible_rows'] == 1
    assert result['boxscore_fallback_applied_rows'] == 1
    assert result['boxscore_fallback_corrected_rows'] == 1
    assert result['boxscore_fallback_refused_rows'] == 0


def test_scenario_b_the_correction_names_the_source_that_supplied_it(lane):
    _run()
    row = GameLog.query.one()
    assert row.last_stat_correction_source == (
        authority.CORRECTION_SOURCE_BOXSCORE_FALLBACK
    )


# ── C. Cost stays bounded across the horizon ───────────────────────────────


def test_scenario_c_one_box_score_read_serves_every_pitcher_in_the_game(lane):
    other = _pitcher(mlb_id=OTHER_PITCHER_MLB_ID, name='Second Arm')
    db.session.flush()
    _row(other)
    db.session.commit()
    lane['lines'] = lambda game_pk: (
        _lines() + _lines(player_id=OTHER_PITCHER_MLB_ID)
    )

    result = _run()

    assert lane['boxscore_calls'] == [GAME_PK]
    assert result['boxscore_fallback_fetches'] == 1
    assert result['boxscore_fallback_corrected_rows'] == 2


# ── D. A source failure is a non-event, not a lane failure ─────────────────


def test_scenario_d_an_unreachable_box_score_does_not_fail_the_lane(lane):
    def boom(game_pk):
        raise RuntimeError('source unavailable')

    lane['lines'] = boom
    result = _run()

    assert GameLog.query.one().balls == 20
    assert result['records_failed'] == 0
    assert result['errors'] == 0
    assert result['boxscore_fallback_fetch_failures'] == 1
    assert result['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_BOXSCORE_UNAVAILABLE: 1,
    }


# ── E. Incoherent evidence is refused, visibly ─────────────────────────────


def test_scenario_e_an_incoherent_line_is_refused_by_name(lane):
    lane['lines'] = lambda game_pk: _lines(balls=30)
    result = _run()

    assert GameLog.query.one().balls == 20
    assert result['logs_corrected'] == 0
    assert result['boxscore_fallback_refused_rows'] == 1
    assert result['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_INCONSISTENT_TRIPLE: 1,
    }


# ── F. Agreement is supplied, not rewritten ────────────────────────────────


def test_scenario_f_a_row_that_already_agrees_is_left_alone(lane):
    GameLog.query.one().balls = 19
    db.session.commit()

    result = _run()

    row = GameLog.query.one()
    assert row.stat_correction_count == 1
    assert row.last_stat_correction_source == (
        sync_service.DAILY_GAME_LOG_CORRECTION_SOURCE
    )
    assert result['boxscore_fallback_applied_rows'] == 1
    assert result['boxscore_fallback_unchanged_rows'] == 1
    assert result['boxscore_fallback_corrected_rows'] == 0


# ── G. A new appearance carries the field from the start ───────────────────


def test_scenario_g_an_inserted_row_carries_the_fallback_value(lane):
    GameLog.query.delete()
    db.session.commit()

    result = _run()

    assert GameLog.query.one().balls == 19
    assert result['new_logs_added'] == 1
    assert result['boxscore_fallback_inserted_rows'] == 1


# ── H. The lane converges instead of replaying ─────────────────────────────


def test_scenario_h_a_second_run_corrects_nothing_further(lane):
    _run()
    second = _run()

    row = GameLog.query.one()
    assert row.balls == 19
    assert row.stat_correction_count == 2
    assert second['logs_corrected'] == 0
    assert second['boxscore_fallback_corrected_rows'] == 0
    assert second['boxscore_fallback_unchanged_rows'] == 1


# ── I. Instrumentation is unconditional ────────────────────────────────────


def test_scenario_i_an_empty_lane_still_reports_every_fallback_key(app):
    result = sync_service.sync_recent_logs(
        days_back=7, reference_date=REFERENCE,
    )
    for key in authority.empty_summary():
        assert key in result


# ── J. The evidence record is complete and says nothing it should not ──────


def test_scenario_j_each_applied_value_carries_reviewable_provenance(lane):
    result = _run()
    record = result['boxscore_fallback_records'][0]

    assert record['game_pk'] == GAME_PK
    assert record['pitcher_mlb_id'] == PITCHER_MLB_ID
    assert record['fields'] == ['balls']
    assert record['source_authority'] == authority.AUTHORITY_CONTRACT
    assert record['source_authority_version'] == authority.AUTHORITY_VERSION
    assert record['correction_source'] == (
        authority.CORRECTION_SOURCE_BOXSCORE_FALLBACK
    )
    assert record['source_revision']
    assert record['plan_fingerprint']
    assert record['applied_target_state_digest']
    assert record['outcome'] == authority.OUTCOME_CORRECTED


def test_scenario_j_the_record_carries_no_source_payload(lane):
    """Provenance, not a payload dump.

    The record names what was decided and on what evidence. Raw source stats,
    player names, and anything else the run happened to hold are not part of
    that, and must not leak into an artifact through this path.
    """
    result = _run()
    record = result['boxscore_fallback_records'][0]

    assert set(record) == {
        'game_pk', 'pitcher_mlb_id', 'fields', 'difference_classifications',
        'source_authority', 'source_authority_version', 'correction_source',
        'source_revision', 'plan_fingerprint', 'applied_target_state_digest',
        'outcome',
    }
