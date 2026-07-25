"""Postgame progressive readiness order + expected-active-slate exit semantics.

Two repairs, proven against the real path:

1. Progressive per-team publication runs only AFTER the completed game's canonical
   readiness evidence is current and committed. The run-471 refusal
   (data_state=missing / confidence=unknown / data_limited) was the active-bullpen
   ROSTER AUTHORITY resolving empty because the global availability reference date
   advances to the day AFTER a completed game while that team's roster snapshot is
   dated at the slate. A team-progressive read is now anchored to the completed
   game's slate so the roster authority resolves for the exact slate it attests to.
   Progressive publication also runs after fatigue recalculation commits.

2. A postgame refresh that ingested cleanly is not marked failed merely because the
   LEAGUE snapshot is (correctly) still pending during an active slate.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import api.team_operations as team_ops
import services.sync as sync_service
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.share_artifact import ShareArtifact, SUBJECT_TYPE_TEAM_PROGRESSIVE
from models.sync_run import SyncRun
from services import sync_metadata
from services.share_artifact_generation import OUTCOME_REFUSED
from services.sync_publication_proof import (
    LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE,
    LEAGUE_PUBLICATION_FAILED,
    LEAGUE_PUBLICATION_PUBLISHED,
    build_candidate_publication_proof,
)
from services.team_progressive_publication import publish_team_state_for_final_game
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.test_postgame_refresh import _game, _patch_mlb, _run, _seed_pitchers
from utils.db import db
from utils.time import utc_now_naive


# ---------------------------------------------------------------------------
# Real-path ordering: fatigue recalculation before progressive publication
# ---------------------------------------------------------------------------


@pytest.fixture
def postgame_app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')

    def fake_complete(sync_run_id, **kwargs):
        run = sync_metadata.finish_sync_run(
            sync_run_id, status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            new_logs_added=kwargs.get('new_logs_added', 0),
            pitchers_updated=kwargs.get('pitchers_updated', 0),
            errors=kwargs.get('errors', 0), api_calls_made=kwargs.get('api_calls_made', 0),
            retries_used=kwargs.get('retries_used', 0), error_message=kwargs.get('error_message'),
            source=kwargs.get('source', 'test'), started_at=kwargs.get('started_at'),
            job_name=kwargs.get('job_name', sync_metadata.JOB_POSTGAME_REFRESH),
        )
        return run, SimpleNamespace(id=123)

    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', fake_complete)
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


def test_progressive_publication_runs_after_fatigue_recalculation(postgame_app, monkeypatch):
    order = []
    monkeypatch.setattr(
        sync_service, 'recalculate_all_fatigue',
        lambda reference_date=None: (order.append('fatigue'), 2)[1],
    )
    monkeypatch.setattr(
        sync_service, '_safe_run_progressive_team_publication',
        lambda game_pks, **kw: (order.append(('progressive', tuple(game_pks))), None)[1],
    )
    _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])
    _run(postgame_app)
    # Fatigue recalculation happens BEFORE progressive publication, and the completed
    # game_pk is handed off to it intact.
    assert order[0] == 'fatigue'
    assert order[1][0] == 'progressive'
    assert 7001 in order[1][1]


def test_fatigue_failure_skips_progressive_and_fails_closed(postgame_app, monkeypatch):
    called = []

    def boom(reference_date=None):
        raise RuntimeError('fatigue recalculation failed')

    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', boom)
    monkeypatch.setattr(
        sync_service, '_safe_run_progressive_team_publication',
        lambda *a, **k: called.append('progressive'),
    )
    _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])
    status = _run(postgame_app)
    # Progressive is never attempted on failed readiness; the run fails closed.
    assert 'progressive' not in called
    assert status['status'] == sync_metadata.STATUS_FAILED


# ---------------------------------------------------------------------------
# Roster-authority readiness: anchor the progressive read to the game's slate
# ---------------------------------------------------------------------------


TODAY = date.today()
SLATE = TODAY - timedelta(days=1)
HOME, AWAY = 108, 117
GAME_PK = 798001


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


def _relievers(team_id, base):
    for s in range(8):
        p = Pitcher(mlb_id=base + s, full_name=f'A{team_id}-{s}', team_id=team_id, team_name='C',
                    team_abbreviation=f'T{team_id}', throws='R', active=True, roster_status='ACTIVE',
                    roster_status_source='mlb_stats_api:roster_sync:active')
        db.session.add(p); db.session.flush()
        for off in (2, 4):
            gd = TODAY - timedelta(days=off)
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=base * 10 + s * 10 + off,
                                   game_date=gd, pitches_thrown=12, innings_pitched=1.0,
                                   innings_pitched_outs=3))
        if s < 3:
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=GAME_PK, game_date=SLATE,
                                   pitches_thrown=14, innings_pitched=1.0, innings_pitched_outs=3))
        db.session.add(FatigueScore(pitcher_id=p.id, calculated_at=datetime(2026, 6, 3, 12, 0, s),
            raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0, appearances_score=0.0,
            innings_score=0.0, leverage_score=0.0, days_since_last_appearance=2, appearances_last_7=2,
            appearances_last_14=2, pitches_last_7_days=24, innings_last_7_days=2.0,
            avg_leverage_last_7=None, risk_level='LOW'))
    db.session.flush()


def _seed_final_game(with_slate_roster=True):
    _relievers(HOME, 750000); _relievers(AWAY, 760000)
    db.session.add_all([
        ScheduledGame(team_id=HOME, game_pk=GAME_PK, game_date=SLATE, status_state='final',
                      home_away='home', opponent_team_id=AWAY),
        ScheduledGame(team_id=AWAY, game_pk=GAME_PK, game_date=SLATE, status_state='final',
                      home_away='away', opponent_team_id=HOME)])
    db.session.add(PostgameProcessedGame(mlb_game_pk=GAME_PK, game_date=SLATE,
        processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED))
    db.session.commit()
    if with_slate_roster:
        ts = utc_now_naive()
        run = SyncRun(job_name='r', started_at=ts, completed_at=ts, status='success',
                      stage='roster_status', source='r', created_at=ts)
        db.session.add(run); db.session.flush()
        for p in Pitcher.query.filter(Pitcher.active.is_(True)).all():
            db.session.add(RosterStatusSnapshot(pitcher_id=p.id, mlb_id=p.mlb_id, team_id=p.team_id,
                snapshot_date=SLATE, roster_status='ACTIVE', active_roster=True, forty_man_roster=True,
                source='mlb_stats_api:roster_sync:active', sync_run_id=run.id,
                first_seen_at=ts, updated_at=ts))
        db.session.commit()


def test_progressive_read_anchors_to_slate_when_reference_date_advances(app, monkeypatch):
    # Reproduce production run 471: the global availability reference date has advanced
    # to the day AFTER the completed game, while the team's roster snapshot is dated at
    # the slate. Anchoring the team-progressive read to the slate resolves the
    # active-bullpen authority and both teams publish.
    _seed_final_game(with_slate_roster=True)
    monkeypatch.setattr(team_ops, '_availability_reference_date',
                        lambda sync_status: SLATE + timedelta(days=1))
    result = publish_team_state_for_final_game(GAME_PK, actor='postgame')
    assert result.attempted == 2
    assert result.generated + result.reused == 2
    assert result.refused == 0
    published = db.session.query(ShareArtifact).filter(
        ShareArtifact.subject_type == SUBJECT_TYPE_TEAM_PROGRESSIVE).count()
    assert published >= 2


def test_progressive_read_fails_closed_when_slate_has_no_roster_authority(app, monkeypatch):
    # The anchor never manufactures readiness: a slate with NO roster snapshot still
    # refuses with the governed reason (fail closed).
    _seed_final_game(with_slate_roster=False)
    monkeypatch.setattr(team_ops, '_availability_reference_date',
                        lambda sync_status: SLATE + timedelta(days=1))
    result = publish_team_state_for_final_game(GAME_PK, actor='postgame')
    assert result.generated == 0
    assert result.refused == 2
    for outcome in result.team_outcomes.values():
        assert outcome == OUTCOME_REFUSED


# ---------------------------------------------------------------------------
# Exit semantics: expected active-slate pending vs genuine withholding
# ---------------------------------------------------------------------------


def _coverage(*, reason_codes, games_scheduled=5, games_final=3, games_fully_ingested=3,
              failed=0, incomplete=0, missing=0, coverage_known=True):
    return {
        'coverage_known': coverage_known,
        'reason_codes': list(reason_codes),
        'games_scheduled': games_scheduled,
        'games_final': games_final,
        'games_fully_ingested': games_fully_ingested,
        'marker_counts': {'failed': failed, 'incomplete': incomplete, 'missing': missing},
    }


def _candidate(coverage, *, status='pending', is_published=False, published_at=None):
    return SimpleNamespace(
        id=274, status=status, is_published=is_published, published_at=published_at,
        sync_run_id=471, data_through=SLATE, availability_reference_date=SLATE,
        payload={'freshness': {'slate_coverage': coverage}} if coverage is not None else {},
    )


def _proof(candidate, *, served_id=271, candidate_reason='dashboard_snapshot_slate_coverage_incomplete'):
    return build_candidate_publication_proof(
        candidate.id, candidate_required=True,
        snapshot_loader=lambda _id: candidate,
        served_snapshot_loader=lambda: SimpleNamespace(id=served_id),
        availability_reason=lambda c: candidate_reason,
    )


def test_expected_active_slate_pending_is_classified_not_failed():
    coverage = _coverage(reason_codes=['scheduled_games_not_final', 'completeness_unknown',
                                       'validations_failed'])
    proof = _proof(_candidate(coverage))
    # Still honestly unverified/pending...
    assert proof['verified'] is False
    assert proof['candidate_is_published'] is False
    assert proof['candidate_status'] == 'pending'
    # ...but classified as an EXPECTED active-slate pending, not a failure.
    assert proof['league_publication_status'] == LEAGUE_PUBLICATION_EXPECTED_PENDING_ACTIVE_SLATE


@pytest.mark.parametrize('coverage', [
    _coverage(reason_codes=['final_games_not_fully_ingested', 'validations_failed'],
              games_final=3, games_fully_ingested=2),
    _coverage(reason_codes=['postgame_markers_failed', 'validations_failed'], failed=1),
    _coverage(reason_codes=['postgame_markers_incomplete', 'validations_failed'], incomplete=1),
    _coverage(reason_codes=['schedule_missing', 'validations_failed']),
    _coverage(reason_codes=['partial_sync', 'scheduled_games_not_final', 'validations_failed']),
    _coverage(reason_codes=['no_scheduled_games', 'validations_failed'], games_scheduled=0),
])
def test_genuine_withholding_stays_failed(coverage):
    proof = _proof(_candidate(coverage))
    assert proof['verified'] is False
    assert proof['league_publication_status'] == LEAGUE_PUBLICATION_FAILED


def test_verified_publication_is_published():
    coverage = _coverage(reason_codes=['slate_complete'])
    candidate = _candidate(coverage, status='ready', is_published=True,
                           published_at=datetime(2026, 7, 24, 12, 0))
    proof = build_candidate_publication_proof(
        candidate.id, candidate_required=True,
        snapshot_loader=lambda _id: candidate,
        served_snapshot_loader=lambda: candidate,   # candidate IS serving
        availability_reason=lambda c: None,
    )
    assert proof['verified'] is True
    assert proof['league_publication_status'] == LEAGUE_PUBLICATION_PUBLISHED


def test_missing_final_game_is_not_expected_pending():
    # A scheduled game absent from coverage (schedule gap) is a failure, never pending.
    coverage = _coverage(reason_codes=['scheduled_games_not_final', 'schedule_missing',
                                       'validations_failed'])
    proof = _proof(_candidate(coverage))
    assert proof['league_publication_status'] == LEAGUE_PUBLICATION_FAILED
