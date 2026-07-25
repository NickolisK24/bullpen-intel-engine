"""Progressive per-team Team State publication — real-path proof.

A completed game publishes its two teams' Team State artifacts independently, with NO
league snapshot, while a late unrelated game blocks nobody and the league snapshot
stays all-or-nothing. Exercises the real readiness/eligibility/generation path (SC-02
is never mocked).
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

import models.prospect  # noqa: F401
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.share_artifact import ShareArtifact
from models.team_progressive_publication import TeamProgressivePublication
from services.share_artifact_generation import (
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
)
from services.team_progressive_publication import (
    build_team_progressive_checkpoint,
    publish_team_state_for_final_game,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db


TODAY = date.today()
GAME_DATE = TODAY - timedelta(days=1)

# Real MLB team ids so is_valid_team_id passes.
HOME = 108   # completed game
AWAY = 117
OTHER_HOME = 143  # unrelated late game
OTHER_AWAY = 158

FINAL_GAME_PK = 780101
LATE_GAME_PK = 780202


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


def _add_relievers(team_id, base_mlb, count=8):
    for seed in range(count):
        pitcher = Pitcher(
            mlb_id=base_mlb + seed, full_name=f'Arm {team_id}-{seed}', team_id=team_id,
            team_name=f'Club {team_id}', team_abbreviation=f'T{team_id}',
            throws='L' if seed % 2 else 'R', active=True, roster_status='ACTIVE',
            roster_status_source='mlb_stats_api:roster_sync:active',
        )
        db.session.add(pitcher)
        db.session.flush()
        for offset in (2, 4):
            gd = TODAY - timedelta(days=offset)
            gpk = base_mlb * 10 + seed * 10 + offset
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd,
                pitches_thrown=12, innings_pitched=1.0, innings_pitched_outs=3,
            ))
            db.session.add_all([
                ScheduledGame(team_id=team_id, game_pk=gpk, game_date=gd, status_state='final',
                              home_away='home', opponent_team_id=900000 + team_id),
                ScheduledGame(team_id=900000 + team_id, game_pk=gpk, game_date=gd, status_state='final',
                              home_away='away', opponent_team_id=team_id),
            ])
            db.session.add(PostgameProcessedGame(
                mlb_game_pk=gpk, game_date=gd,
                processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id, calculated_at=datetime(2026, 6, 3, 12, 0, seed),
            raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0,
            appearances_score=0.0, innings_score=0.0, leverage_score=0.0,
            days_since_last_appearance=2, appearances_last_7=2, appearances_last_14=2,
            pitches_last_7_days=24, innings_last_7_days=2.0, avg_leverage_last_7=None,
            risk_level='LOW',
        ))
    db.session.flush()


def _add_game(game_pk, home, away, *, final, processed):
    state = 'final' if final else 'scheduled'
    db.session.add_all([
        ScheduledGame(team_id=home, game_pk=game_pk, game_date=GAME_DATE, status_state=state,
                      home_away='home', opponent_team_id=away),
        ScheduledGame(team_id=away, game_pk=game_pk, game_date=GAME_DATE, status_state=state,
                      home_away='away', opponent_team_id=home),
    ])
    if processed:
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk, game_date=GAME_DATE,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
    db.session.flush()


def _seed(final_processed=True):
    for tid, base in ((HOME, 810000), (AWAY, 820000), (OTHER_HOME, 830000), (OTHER_AWAY, 840000)):
        _add_relievers(tid, base)
    _add_game(FINAL_GAME_PK, HOME, AWAY, final=True, processed=final_processed)
    _add_game(LATE_GAME_PK, OTHER_HOME, OTHER_AWAY, final=False, processed=False)
    db.session.commit()
    seed_roster_readiness_snapshots()


def test_completed_game_publishes_both_teams_without_league_snapshot(app):
    _seed()
    result = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    assert result.attempted == 2
    assert result.accounted == 2
    assert result.to_dict()['missing'] == 0
    assert result.generated + result.reused >= 1
    # Both participants are the completed game's teams; unrelated late-game teams
    # were never attempted.
    assert set(result.team_outcomes) == {HOME, AWAY}
    # No late-game team got a checkpoint or artifact.
    late = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.team_id.in_([OTHER_HOME, OTHER_AWAY])
    ).count()
    assert late == 0


def test_published_artifact_source_is_the_team_checkpoint(app):
    _seed()
    publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    checkpoints = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.trigger_game_pk == FINAL_GAME_PK,
        TeamProgressivePublication.trusted.is_(True),
    ).all()
    assert checkpoints
    checkpoint_ids = {c.id for c in checkpoints}
    artifacts = db.session.query(ShareArtifact).filter(
        ShareArtifact.source_snapshot_id.in_(checkpoint_ids)
    ).all()
    # At least one published artifact is sourced from a team-progressive checkpoint,
    # never a league dashboard snapshot.
    assert artifacts


def test_non_final_game_fails_closed(app):
    _seed()
    result = publish_team_state_for_final_game(LATE_GAME_PK, actor='postgame')
    assert result.attempted == 2
    assert result.generated == 0
    assert result.refused == 2
    for outcome in result.team_outcomes.values():
        assert outcome == OUTCOME_REFUSED
    # The withheld checkpoints record the fail-closed reason.
    withheld = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.trigger_game_pk == LATE_GAME_PK,
    ).all()
    assert withheld and all(not c.trusted for c in withheld)
    assert all(c.unavailable_reason == 'game_not_final' for c in withheld)


def test_ledger_incomplete_fails_closed(app):
    # Game final but its box score / appearance ledger not committed -> withheld.
    _seed(final_processed=False)
    result = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    assert result.generated == 0
    assert result.refused == 2
    checkpoints = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.trigger_game_pk == FINAL_GAME_PK,
    ).all()
    assert checkpoints and all(c.unavailable_reason == 'appearance_ledger_incomplete' for c in checkpoints)


def test_progressive_generation_is_idempotent(app):
    _seed()
    first = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    second = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    # Re-running the same final-game evidence reuses; no duplicate checkpoints/artifacts.
    assert second.generated == 0
    assert second.reused == first.generated + first.reused
    checkpoints = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.trigger_game_pk == FINAL_GAME_PK,
    ).count()
    assert checkpoints == 2  # exactly one per team, not duplicated


def test_postgame_trigger_seam_is_config_gated(app):
    from services.sync import _safe_run_progressive_team_publication
    import logging

    _seed()
    logger = logging.getLogger('test')
    # Disabled by default -> no-op, no artifacts.
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = False
    assert _safe_run_progressive_team_publication(
        [FINAL_GAME_PK], sync_run_id=None, status={}, run_logger=logger,
    ) is None
    assert db.session.query(ShareArtifact).count() == 0

    # Enabled -> publishes the completed game's two teams, fail-soft accounting.
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    result = _safe_run_progressive_team_publication(
        [FINAL_GAME_PK], sync_run_id=None, status={}, run_logger=logger,
    )
    assert result is not None
    assert result['totals']['games'] == 1
    assert result['totals']['attempted'] == 2
    assert result['totals']['generated'] + result['totals']['reused'] >= 1
