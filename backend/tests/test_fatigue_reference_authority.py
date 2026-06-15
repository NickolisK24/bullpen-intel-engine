"""
Canonical fatigue recalculation authority.

These tests pin the rule that every production-facing recalculation path scores
fatigue against ONE reference date — the latest completed MLB workload date + 1
day ("tonight's availability") — so the same game logs always produce the same
fatigue scores (and therefore the same league-wide bullpen snapshot) no matter
which path last ran: the scheduled APScheduler sync, the GitHub Actions / manual
sync endpoint, or the recalculate endpoint.

Before this authority existed, the scheduled job scored each pitcher at their own
last game date while the sync endpoint scored against the host's runtime "today",
so one database could tell two different stories.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database

import services.sync as sync_service
from api.bullpen import bullpen_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from services.fatigue import calculate_fatigue
from services.sync_metadata import canonical_fatigue_reference_date
from services.roster_status import STATUS_ACTIVE
from utils.db import db


MAX_WORKLOAD_DATE = date(2026, 6, 9)
CANONICAL_REFERENCE = date(2026, 6, 10)  # latest workload + 1 day


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    flask_app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    with flask_app.app_context():
        db.create_all()
        try:
            yield flask_app
        finally:
            db.session.remove()
            db.drop_all()


def _add_pitcher(mlb_id, name, abbr='REF', team_id=1):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name='Reference Team',
        team_abbreviation=abbr,
        position='RP',
        active=True,
        roster_status=STATUS_ACTIVE,
        roster_status_source='test_fixture',
        roster_status_updated_at=datetime(2026, 6, 9, 12, 0, 0),
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _add_log(pitcher, game_pk, game_date, pitches, innings=1.0):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        pitches_thrown=pitches,
        innings_pitched=innings,
        innings_pitched_outs=round(innings * 3),
        game_type='R',
    ))
    db.session.commit()


def _seed_population():
    """One recent reliever (inside the canonical window) and one stale reliever."""
    recent = _add_pitcher(910001, 'Recent Reliever', abbr='REC')
    _add_log(recent, 910010, date(2026, 6, 8), pitches=50)
    _add_log(recent, 910011, MAX_WORKLOAD_DATE, pitches=30)

    stale = _add_pitcher(910002, 'Stale Reliever', abbr='STL')
    _add_log(stale, 910020, date(2026, 5, 1), pitches=40)
    return recent, stale


def _latest_scores_by_pitcher():
    rows = (
        db.session.query(FatigueScore)
        .order_by(FatigueScore.pitcher_id, FatigueScore.calculated_at)
        .all()
    )
    latest = {}
    for row in rows:
        latest[row.pitcher_id] = row  # last write wins (ordered ascending)
    return latest


# ── 1. The canonical reference date IS latest-workload + 1 day ──────────────

def test_canonical_reference_is_latest_workload_plus_one_day(app):
    _seed_population()
    assert canonical_fatigue_reference_date() == CANONICAL_REFERENCE


def test_canonical_reference_is_none_without_any_workload(app):
    _add_pitcher(910099, 'No Logs Reliever')
    assert canonical_fatigue_reference_date() is None


# ── 2. Production recalc uses the canonical reference, not per-pitcher date ──

def test_recalculate_uses_canonical_reference_not_per_pitcher_last_game(app):
    recent, stale = _seed_population()

    updated = sync_service.recalculate_all_fatigue()

    latest = _latest_scores_by_pitcher()
    # Recent reliever is scored at the canonical reference (max + 1 day), so the
    # rest gap is 1 day — NOT 0, which the old per-last-game-date path produced.
    assert latest[recent.id].days_since_last_appearance == 1
    # The stale reliever has no appearance inside the canonical window, so the
    # canonical authority leaves them unscored (consistent across every path).
    assert stale.id not in latest
    assert updated == 1


def test_recalculate_is_independent_of_runtime_today(app, monkeypatch):
    recent, _stale = _seed_population()

    class FarFutureDate(date):
        @classmethod
        def today(cls):
            return date(2027, 1, 1)

    # Even if the host clock is wildly off, the anchor is the data, not today.
    monkeypatch.setattr(sync_service, 'date', FarFutureDate)
    sync_service.recalculate_all_fatigue()

    latest = _latest_scores_by_pitcher()
    assert latest[recent.id].days_since_last_appearance == 1


# ── 3. Every production path produces equivalent fatigue output ─────────────

def test_recalculate_is_deterministic_for_fixed_game_logs(app):
    recent, _stale = _seed_population()

    sync_service.recalculate_all_fatigue()
    first = {pid: row.raw_score for pid, row in _latest_scores_by_pitcher().items()}

    sync_service.recalculate_all_fatigue()
    second = {pid: row.raw_score for pid, row in _latest_scores_by_pitcher().items()}

    assert first == second


def test_scheduled_authority_and_recalculate_endpoint_agree(app):
    recent, _stale = _seed_population()

    # Path used by the scheduled APScheduler sync AND the GitHub Actions /
    # manual sync endpoint (both call recalculate_all_fatigue() with no args).
    sync_service.recalculate_all_fatigue()
    scheduled = {pid: row.raw_score for pid, row in _latest_scores_by_pitcher().items()}

    # The admin recalculate endpoint delegates to the same canonical authority.
    client = app.test_client()
    res = client.post('/api/bullpen/fatigue/recalculate')
    assert res.status_code == 200

    endpoint = {pid: row.raw_score for pid, row in _latest_scores_by_pitcher().items()}
    assert scheduled == endpoint


# ── 4. No regression: only the reference-date authority changed ─────────────

def test_recalculate_delegates_to_unchanged_scoring_engine(app):
    recent, _stale = _seed_population()

    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == recent.id,
            GameLog.game_date >= date(2026, 5, 27),
            GameLog.game_date <= CANONICAL_REFERENCE,
        )
        .order_by(GameLog.game_date.desc())
        .all()
    )
    expected = calculate_fatigue(recent, logs, reference_date=CANONICAL_REFERENCE)

    sync_service.recalculate_all_fatigue()
    stored = _latest_scores_by_pitcher()[recent.id]

    # Same raw score and risk band: the weights, thresholds and formula are
    # untouched — only the reference-date authority was centralized.
    assert stored.raw_score == pytest.approx(expected.raw_score)
    assert stored.risk_level == expected.risk_level


# ── 5. Dashboard snapshot is deterministic for the same persisted state ─────

def _add_success_sync_run():
    db.session.add(SyncRun(
        started_at=datetime(2026, 6, 9, 11, 0, 0),
        completed_at=datetime(2026, 6, 9, 11, 0, 30),
        status='success',
        source='github_actions',
        latest_game_date=MAX_WORKLOAD_DATE,
        latest_workload_date=MAX_WORKLOAD_DATE,
        latest_fatigue_calculated_at=datetime(2026, 6, 9, 11, 0, 30),
        pitchers_updated=1,
        errors=0,
        created_at=datetime(2026, 6, 9, 11, 0, 0),
    ))
    db.session.commit()


def test_dashboard_snapshot_is_deterministic_and_data_anchored(app):
    _seed_population()
    sync_service.recalculate_all_fatigue()
    _add_success_sync_run()

    client = app.test_client()
    first = client.get('/api/bullpen/dashboard').get_json()
    second = client.get('/api/bullpen/dashboard').get_json()

    # Same persisted game logs + fatigue scores + sync metadata → identical story.
    assert first['availability_summary']['statuses'] == second['availability_summary']['statuses']
    assert first['landscape']['available_bullpens'] == second['landscape']['available_bullpens']
    assert first['landscape']['constrained_bullpens'] == second['landscape']['constrained_bullpens']
    assert first['landscape']['monitoring_concentration'] == second['landscape']['monitoring_concentration']

    # And the snapshot is anchored to the data-derived canonical reference.
    assert first['freshness']['availability_reference_date'] == CANONICAL_REFERENCE.isoformat()
