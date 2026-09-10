"""The bounded, read-only impact plan that has to run before the repair does.

The authority question was settled by audit; the scope question was not. Before
a writer is allowed to correct a field across a rolling horizon, someone has to
be able to answer, with evidence: *which rows, how many, and does anything move
that is not the approved field?*

The planner answers it in two narrowing stages — box score first (one fetch per
game, keeping only rows that would actually change), split second (one fetch
per candidate pitcher, rebuilding the appearance the way the daily lane would
and running the real planner over it).

These tests own three properties that make the resulting artifact worth
trusting:

* it enumerates a finite, explicit set rather than estimating one;
* it reports what it could **not** confirm instead of quietly narrowing;
* it writes nothing.
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
from scripts import plan_boxscore_balls_fallback_impact as planner
from services import sync as sync_service
from utils.db import db


SLATE = date(2026, 6, 20)
GAME_PK = 970001
OTHER_GAME_PK = 970002
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


def _splits(*, game_pk=GAME_PK, with_balls=None, **stat_overrides):
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
        'game': {'gamePk': game_pk, 'gameType': 'R'},
        'opponent': {'id': AWAY_TEAM_ID, 'name': 'Away Club'},
        'stat': stat,
    }]


def _empty_plan(**overrides):
    plan = {
        'boxscore_fetches': 0, 'boxscore_fetch_failures': 0,
        'split_fetches': 0, 'split_fetch_failures': 0,
    }
    plan.update(overrides)
    return plan


@pytest.fixture
def horizon(app, monkeypatch):
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines',
                        lambda game_pk: _lines())
    monkeypatch.setattr(sync_service.mlb_client, 'get_pitcher_game_logs',
                        lambda mlb_id, season=None: _splits())
    _schedule()
    pitcher = _pitcher()
    db.session.flush()
    row = _row(pitcher)
    db.session.commit()
    return {'pitcher': pitcher, 'row': row,
            'by_id': {pitcher.id: pitcher}}


def _stage_one(horizon, plan=None):
    plan = plan if plan is not None else _empty_plan()
    rows = GameLog.query.all()
    return planner._boxscore_stage(
        rows, plan=plan, pitcher_by_id=horizon['by_id'],
    ), plan


# ── Stage one: narrowing by box score ───────────────────────────────────────


def test_a_row_the_box_score_would_move_becomes_a_candidate(horizon):
    candidates, plan = _stage_one(horizon)
    assert len(candidates) == 1
    assert candidates[0]['stored']['balls'] == 20
    assert candidates[0]['boxscore']['balls'] == 19
    assert plan['boxscore_fetches'] == 1


def test_a_row_that_already_agrees_is_dropped_and_counted(horizon):
    horizon['row'].balls = 19
    db.session.commit()

    candidates, plan = _stage_one(horizon)
    assert candidates == []
    assert plan['rows_skipped'] == {planner.SKIP_ROW_ALREADY_MATCHING: 1}


def test_an_incoherent_box_score_never_produces_a_candidate(horizon, monkeypatch):
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines',
                        lambda game_pk: _lines(balls=30))
    candidates, plan = _stage_one(horizon)
    assert candidates == []
    assert plan['rows_skipped'] == {planner.SKIP_ROW_INVALID_LINE: 1}


def test_an_unreachable_box_score_is_reported_not_treated_as_agreement(
    horizon, monkeypatch,
):
    def boom(game_pk):
        raise RuntimeError('unavailable')

    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines', boom)
    candidates, plan = _stage_one(horizon)
    assert candidates == []
    assert plan['rows_skipped'] == {planner.SKIP_ROW_NO_BOXSCORE: 1}
    assert plan['boxscore_fetch_failures'] == 1
    assert 'RuntimeError' in plan['fetch_error_classes']


def test_a_game_is_fetched_once_however_many_rows_it_has(horizon):
    other = _pitcher(mlb_id=OTHER_PITCHER_MLB_ID, name='Second Arm')
    db.session.flush()
    _row(other)
    db.session.commit()
    horizon['by_id'][other.id] = other

    calls = []
    original = sync_service.mlb_client.get_game_pitching_lines

    def counted(game_pk):
        calls.append(game_pk)
        return _lines() + _lines(player_id=OTHER_PITCHER_MLB_ID)

    sync_service.mlb_client.get_game_pitching_lines = counted
    try:
        candidates, plan = _stage_one(horizon)
    finally:
        sync_service.mlb_client.get_game_pitching_lines = original

    assert len(candidates) == 2
    assert calls == [GAME_PK]
    assert plan['boxscore_fetches'] == 1


def test_a_row_with_no_line_for_its_pitcher_is_skipped(horizon, monkeypatch):
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_pitching_lines',
                        lambda game_pk: _lines(player_id=OTHER_PITCHER_MLB_ID))
    candidates, plan = _stage_one(horizon)
    assert candidates == []
    assert plan['rows_skipped'] == {planner.SKIP_ROW_NO_LINE: 1}


# ── Stage two: confirming against the real split ────────────────────────────


def test_a_confirmed_candidate_reports_the_plan_the_writer_would_make(horizon):
    candidates, plan = _stage_one(horizon)
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    assert len(confirmed) == 1
    item = confirmed[0]
    assert item['action'] == 'update'
    assert item['changed_fields'] == ['balls']
    assert item['stored_balls'] == 20
    assert item['proposed_balls'] == 19
    assert item['out_of_scope_fields'] == []
    assert item['split_supplies_balls'] is False
    assert 'balls' in item['split_uncomparable_fields']
    assert item['source_revision']


def test_a_split_that_supplies_the_field_is_not_the_fallbacks_business(
    horizon, monkeypatch,
):
    """The candidate came from the box score; the split settles it.

    A split carrying its own ``balls`` means the daily lane can already correct
    the field, so the fallback has nothing to add and the row is not part of
    this repair's affected set.
    """
    monkeypatch.setattr(sync_service.mlb_client, 'get_pitcher_game_logs',
                        lambda mlb_id, season=None: _splits(with_balls=21))
    candidates, plan = _stage_one(horizon)
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    assert confirmed == []
    assert plan['unconfirmed_candidates'] == {
        planner.UNCONFIRMED_SPLIT_SUPPLIES_FIELD: 1,
    }
    assert 'fallback_refusals' not in plan


def test_a_candidate_with_no_split_for_the_game_is_reported_unconfirmed(
    horizon, monkeypatch,
):
    monkeypatch.setattr(sync_service.mlb_client, 'get_pitcher_game_logs',
                        lambda mlb_id, season=None: _splits(game_pk=OTHER_GAME_PK))
    candidates, plan = _stage_one(horizon)
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    assert confirmed == []
    assert plan['unconfirmed_candidates'] == {
        planner.UNCONFIRMED_NO_SPLIT_FOR_GAME: 1,
    }


def test_an_unreachable_split_is_reported_rather_than_assumed(
    horizon, monkeypatch,
):
    def boom(mlb_id, season=None):
        raise RuntimeError('unavailable')

    monkeypatch.setattr(sync_service.mlb_client, 'get_pitcher_game_logs', boom)
    candidates, plan = _stage_one(horizon)
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    assert confirmed == []
    assert plan['split_fetch_failures'] == 1
    assert plan['unconfirmed_candidates'] == {
        planner.UNCONFIRMED_SPLIT_UNAVAILABLE: 1,
    }


def test_a_pitcher_with_several_affected_appearances_is_fetched_once(horizon):
    _schedule(OTHER_GAME_PK)
    _row(horizon['pitcher'], game_pk=OTHER_GAME_PK)
    db.session.commit()

    calls = []
    original = sync_service.mlb_client.get_pitcher_game_logs

    def counted(mlb_id, season=None):
        calls.append(mlb_id)
        return _splits() + _splits(game_pk=OTHER_GAME_PK)

    sync_service.mlb_client.get_pitcher_game_logs = counted
    try:
        candidates, plan = _stage_one(horizon)
        confirmed = planner._split_stage(
            candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
        )
    finally:
        sync_service.mlb_client.get_pitcher_game_logs = original

    assert len(confirmed) == 2
    assert calls == [PITCHER_MLB_ID]
    assert plan['split_fetches'] == 1


def test_the_candidate_limit_reports_what_it_did_not_examine(horizon):
    """A bound that hides its own effect would make a partial plan read as a
    complete enumeration."""
    candidates, plan = _stage_one(horizon)
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=0,
    )
    assert confirmed == []
    assert plan['unconfirmed_candidates'] == {planner.UNCONFIRMED_TRUNCATED: 1}


def test_a_change_outside_the_approved_field_is_surfaced_not_silently_kept(
    horizon, monkeypatch,
):
    """The out-of-scope check has to be able to fire.

    Here the split also revises strikeouts, so the plan legitimately moves two
    fields — and the planner says so, which is what would block the repair as
    scoped rather than letting it through.
    """
    monkeypatch.setattr(sync_service.mlb_client, 'get_pitcher_game_logs',
                        lambda mlb_id, season=None: _splits(strikeOuts=7))
    candidates, plan = _stage_one(horizon)
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    assert confirmed[0]['out_of_scope_fields'] == ['strikeouts']


def test_a_candidate_the_authority_refuses_is_reported_not_planned(horizon):
    """The fail-closed backstop between the two stages.

    Stage one validated the line, so a refusal here would mean the stages
    disagree about the same evidence. The planner reports that rather than
    preferring one of them.
    """
    candidates, plan = _stage_one(horizon)
    candidates[0]['boxscore_stats'] = {
        'balls': 30, 'strikes': 26, 'numberOfPitches': 45,
    }
    confirmed = planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    assert confirmed == []
    assert plan['unconfirmed_candidates'] == {
        planner.UNCONFIRMED_FALLBACK_REFUSED: 1,
    }
    assert plan['fallback_refusals'] == {'boxscore_values_inconsistent': 1}


# ── Read-only, and provably so ──────────────────────────────────────────────


def test_planning_writes_nothing(horizon):
    before = planner._horizon_fingerprint(GameLog.query.all())
    candidates, plan = _stage_one(horizon)
    planner._split_stage(
        candidates, plan=plan, pitcher_by_id=horizon['by_id'], limit=100,
    )
    db.session.rollback()

    row = GameLog.query.one()
    assert row.balls == 20
    assert row.stat_correction_count in (None, 0)
    assert planner._horizon_fingerprint(GameLog.query.all()) == before


def test_the_horizon_fingerprint_moves_when_a_reported_value_moves(horizon):
    before = planner._horizon_fingerprint(GameLog.query.all())
    horizon['row'].balls = 19
    db.session.commit()
    assert planner._horizon_fingerprint(GameLog.query.all()) != before


def test_the_horizon_is_bounded_by_the_requested_window(horizon):
    rows, cutoff, reference = planner._horizon_rows(7)
    assert (reference - cutoff).days == 7
    assert all(cutoff <= row.game_date <= reference for row in rows)
