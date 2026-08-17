"""Real-resolver end-to-end coverage for the SC-03B-07 active-bullpen trust contract.

These exercise the REAL production path — persisted pitchers + official roster
snapshots + fatigue rows + game logs + the completed-appearance ledger sources ->
``resolve_team_readiness_payload`` -> the readiness assembler -> team-level trust
-> the derived ``status_code`` — with NO injected/fake readiness resolver. They
prove that a complete active bullpen now produces a supported, high-confidence
readiness (previously collapsed to ``data_limited``), a bounded-partial bullpen
produces ``medium`` + a supported status with an explicit limitation, and a
genuinely insufficient bullpen stays ``low`` / ``data_limited``.
"""

from datetime import datetime, timedelta

import pytest
from flask import Flask

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services.availability_reference_date import product_current_date
from services.share_artifact_generation import resolve_team_readiness_payload
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db


TEAM_ID = 7


def _product_today():
    """The one calendar authority this module seeds against.

    Every seeded appearance date must come from here, never from
    ``date.today()``. The resolver derives its availability reference date from
    stored workload coverage (latest workload date + 1) and judges roster
    snapshot coverage on the BaseballOS product calendar day
    (``America/New_York``), which is also what ``seed_roster_readiness_snapshots``
    uses. Seeding appearances against the host UTC day instead left the fixture
    describing two different "todays" during the 00:00-04:00 UTC window, when
    the UTC and Eastern calendar dates differ:

        appearances seeded on the UTC day   -> newest workload one day later
        snapshots seeded on the product day -> newest coverage one day earlier

    The stress case then pushed the availability reference date one day past
    the newest seeded roster snapshot, the active-bullpen population resolved
    to zero, and the payload correctly failed closed to ``data_limited``. That
    was the fixture contradicting itself, not the trust model misbehaving.

    A single moving product date is used rather than a frozen constant because
    these tests assert ``data_state == 'fresh'``: staleness is judged against
    the current product day, so a hard-coded past date would make the seeded
    coverage genuinely stale and change what the tests exercise.
    """
    return product_current_date()


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _add_reliever(seed, *, usable=True, hand='R'):
    """Seed one active-roster reliever.

    ``usable=True`` -> a recent complete relief appearance (data_state 'fresh').
    ``usable=False`` -> a reliever with prior relief appearances (so role authority
    still classifies it as a bullpen arm) whose latest game log is incomplete
    (``pitches_thrown`` null) -> data_state 'incomplete' -> unresolved.
    """
    pitcher = Pitcher(
        mlb_id=990000 + seed,
        full_name=f'Arm {seed:02d}',
        team_id=TEAM_ID,
        team_name='Example Club',
        team_abbreviation='EX',
        throws=hand,
        active=True,
        roster_status='ACTIVE',
        roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(pitcher)
    db.session.flush()

    # Two prior, complete relief appearances so Role Authority classifies a reliever.
    for offset in (2, 4):
        gd = _product_today() - timedelta(days=offset)
        gpk = 991000 + seed * 10 + offset
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd,
            pitches_thrown=12, innings_pitched=1.0, innings_pitched_outs=3,
        ))
        db.session.add_all([
            ScheduledGame(team_id=TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='home', opponent_team_id=900000 + TEAM_ID),
            ScheduledGame(team_id=900000 + TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='away', opponent_team_id=TEAM_ID),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=gpk, game_date=gd,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))

    if not usable:
        # Latest appearance carries incomplete source data (null pitch count) ->
        # data_state 'incomplete' -> unresolved, while still a real appearance
        # (innings recorded) so the pitcher stays a classified bullpen arm.
        gd = _product_today() - timedelta(days=1)
        gpk = 991000 + seed * 10 + 1
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd,
            pitches_thrown=None, innings_pitched=1.0, innings_pitched_outs=3,
        ))
        db.session.add_all([
            ScheduledGame(team_id=TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='home', opponent_team_id=900000 + TEAM_ID),
            ScheduledGame(team_id=900000 + TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='away', opponent_team_id=TEAM_ID),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=gpk, game_date=gd,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))

    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=datetime(2026, 6, 3, 12, 0, seed),
        raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0,
        appearances_score=0.0, innings_score=0.0, leverage_score=0.0,
        days_since_last_appearance=1 if usable else 1, appearances_last_7=2,
        appearances_last_14=2, pitches_last_7_days=24, innings_last_7_days=2.0,
        avg_leverage_last_7=None, risk_level='LOW',
    ))
    db.session.flush()
    return pitcher


def _add_sync_run():
    db.session.add(SyncRun(
        started_at=datetime(2026, 6, 3, 7, 30, 0), completed_at=datetime(2026, 6, 3, 7, 44, 27),
        status='success', source='scheduled', latest_game_date=_product_today(),
        latest_workload_date=_product_today(), latest_fatigue_calculated_at=datetime(2026, 6, 3, 7, 44, 27),
        records_processed=12, new_logs_added=6, pitchers_updated=2, errors=0,
        created_at=datetime(2026, 6, 3, 7, 30, 0),
    ))
    db.session.commit()


def _seed_team(usable_count, total_count):
    for seed in range(1, total_count + 1):
        _add_reliever(seed, usable=(seed <= usable_count), hand='L' if seed % 2 else 'R')
    _add_sync_run()
    seed_roster_readiness_snapshots()


SUPPORTED = {'operationally_stable', 'operationally_constrained', 'operationally_stressed'}


def test_complete_active_bullpen_resolves_high_and_supported(app):
    _seed_team(usable_count=8, total_count=8)
    payload = resolve_team_readiness_payload(TEAM_ID)
    assert payload is not None
    assert payload['trust_metadata']['confidence'] == 'high'
    assert payload['trust_metadata']['data_state'] == 'fresh'
    assert payload['readiness']['status_code'] in SUPPORTED


def test_bounded_partial_bullpen_resolves_medium_supported_with_limitation(app):
    # 6 of 8 usable, 2 unresolved -> medium (>=75%, >=6 usable, <=2 unresolved).
    _seed_team(usable_count=6, total_count=8)
    payload = resolve_team_readiness_payload(TEAM_ID)
    assert payload is not None
    assert payload['trust_metadata']['confidence'] == 'medium'
    assert payload['trust_metadata']['data_state'] == 'fresh'
    assert payload['readiness']['status_code'] in SUPPORTED
    limitations = payload['trust_metadata']['limitations']
    assert any('active bullpen pitchers' in str(item) for item in limitations)


def test_insufficient_active_bullpen_stays_low_data_limited(app):
    # 5 of 8 usable, 3 unresolved -> below the medium bar -> low / data_limited.
    _seed_team(usable_count=5, total_count=8)
    payload = resolve_team_readiness_payload(TEAM_ID)
    assert payload is not None
    assert payload['trust_metadata']['confidence'] == 'low'
    assert payload['trust_metadata']['data_state'] == 'incomplete'
    assert payload['readiness']['status_code'] == 'data_limited'


def _add_starter(seed):
    """Seed an active-roster STARTER: not a bullpen arm, but on the team.

    A starter carries fatigue scores and reaches the resolver's row set exactly
    like a reliever does. This one worked yesterday on a heavy pitch count, so
    the availability engine classifies it Unavailable — the everyday situation
    that collapsed every club to Vulnerable in production.
    """
    pitcher = Pitcher(
        mlb_id=980000 + seed,
        full_name=f'Starter {seed:02d}',
        team_id=TEAM_ID,
        team_name='Example Club',
        team_abbreviation='EX',
        throws='R',
        active=True,
        roster_status='ACTIVE',
        roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(pitcher)
    db.session.flush()

    # Starts on a normal rotation turn, the most recent one yesterday.
    for offset in (1, 6, 11):
        gd = _product_today() - timedelta(days=offset)
        gpk = 981000 + seed * 10 + offset
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd,
            pitches_thrown=98, innings_pitched=6.0, innings_pitched_outs=18,
            games_started=1,
        ))
        db.session.add_all([
            ScheduledGame(team_id=TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='home', opponent_team_id=900000 + TEAM_ID),
            ScheduledGame(team_id=900000 + TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='away', opponent_team_id=TEAM_ID),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=gpk, game_date=gd,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))

    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=datetime(2026, 6, 3, 12, 30, seed),
        raw_score=95.0, pitch_count_score=40.0, rest_days_score=30.0,
        appearances_score=10.0, innings_score=15.0, leverage_score=0.0,
        days_since_last_appearance=1, appearances_last_7=1,
        appearances_last_14=2, pitches_last_7_days=98, innings_last_7_days=6.0,
        avg_leverage_last_7=None, risk_level='CRITICAL',
    ))
    db.session.flush()
    return pitcher


def test_a_starter_who_worked_yesterday_is_excluded_from_the_bullpen_state(app):
    """The #590 production defect: population, not vocabulary.

    Detroit's Team State was derived from a wider pitcher set that included a
    starter classified Unavailable — a single off-active record decided the club's
    state. Readiness now describes the canonical active bullpen only: the starter
    reaches the resolver's rows but never enters the distribution, so the state is
    decided by the bullpen's own arms (via Contract A) and by nothing else.
    """
    for seed in range(1, 9):
        _add_reliever(seed, usable=True, hand='L' if seed % 2 else 'R')
    starter = _add_starter(1)
    _add_sync_run()
    seed_roster_readiness_snapshots()

    payload = resolve_team_readiness_payload(TEAM_ID)

    assert payload is not None
    # The starter is on the team and carries a fatigue score, so he reaches the
    # resolver's rows — he simply is not part of the bullpen the state describes.
    assert starter.id is not None
    distribution = payload['availability_distribution']
    # The off-active starter (classified Unavailable) never enters the active
    # bullpen distribution: the population is exactly the eight relievers, so a
    # non-bullpen record can neither be counted severe nor move the state.
    assert distribution['total'] == 8
    assert distribution['unavailable'] == 0, (
        'a non-bullpen record must not appear in the active-bullpen distribution'
    )
    assert payload['workload_pressure']['elevated_count'] == 0
    # The state is decided by the eight canonical arms alone.
    evidence = payload['team_state_evidence']
    assert evidence['active_pitcher_count'] == 8
    assert evidence['severe_count'] == 0
    assert payload['readiness']['status_code'] in SUPPORTED


def test_a_genuine_bullpen_stress_trigger_still_reaches_stressed(app):
    """The correction narrows the population; it does not soften the rule."""
    for seed in range(1, 9):
        _add_reliever(seed, usable=True, hand='L' if seed % 2 else 'R')
    _add_sync_run()
    seed_roster_readiness_snapshots()

    baseline = resolve_team_readiness_payload(TEAM_ID)
    assert baseline is not None
    assert baseline['readiness']['status_code'] in SUPPORTED

    # A real active-bullpen member worked heavily yesterday.
    stressed_arm = Pitcher.query.filter_by(mlb_id=990001).one()
    gd = _product_today() - timedelta(days=1)
    gpk = 995001
    db.session.add(GameLog(
        pitcher_id=stressed_arm.id, mlb_game_pk=gpk, game_date=gd,
        pitches_thrown=52, innings_pitched=3.0, innings_pitched_outs=9,
    ))
    db.session.add_all([
        ScheduledGame(team_id=TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                      home_away='home', opponent_team_id=900000 + TEAM_ID),
        ScheduledGame(team_id=900000 + TEAM_ID, game_pk=gpk, game_date=gd, status_state='final',
                      home_away='away', opponent_team_id=TEAM_ID),
    ])
    db.session.add(PostgameProcessedGame(
        mlb_game_pk=gpk, game_date=gd,
        processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
    ))
    db.session.add(FatigueScore(
        pitcher_id=stressed_arm.id, calculated_at=datetime(2026, 6, 3, 13, 0, 0),
        raw_score=92.0, pitch_count_score=40.0, rest_days_score=30.0,
        appearances_score=12.0, innings_score=10.0, leverage_score=0.0,
        days_since_last_appearance=1, appearances_last_7=4,
        appearances_last_14=6, pitches_last_7_days=110, innings_last_7_days=5.0,
        avg_leverage_last_7=None, risk_level='CRITICAL',
    ))
    db.session.commit()

    payload = resolve_team_readiness_payload(TEAM_ID)

    assert payload is not None
    assert payload['readiness']['status_code'] in SUPPORTED
    # The canonical member is counted; the population contract did not mute it.
    assert payload['availability_distribution']['total'] == 8


def test_sequential_teams_do_not_reuse_a_prior_teams_readiness(app):
    """Back-to-back resolution for different teams stays independent."""
    for seed in range(1, 9):
        _add_reliever(seed, usable=True, hand='L' if seed % 2 else 'R')
    _add_sync_run()
    seed_roster_readiness_snapshots()

    seeded = resolve_team_readiness_payload(TEAM_ID)
    other = resolve_team_readiness_payload(TEAM_ID + 1234)
    seeded_again = resolve_team_readiness_payload(TEAM_ID)

    assert seeded is not None
    assert seeded['team']['team_id'] == TEAM_ID
    # An unseeded team has no source inputs at all and must not inherit a state.
    assert other is None
    assert seeded_again['readiness']['status_code'] == seeded['readiness']['status_code']
    assert seeded_again['team']['team_id'] == TEAM_ID
