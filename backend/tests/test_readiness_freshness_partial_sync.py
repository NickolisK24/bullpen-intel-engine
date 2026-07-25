"""Real-path reproduction + repair proof for the readiness-freshness contract.

Production incident (snapshot 271 / sync_run 467, product_date 2026-07-23): all 30
teams were refused a Team State artifact with ``stale_snapshot`` /
``insufficient_trust`` / ``unsupported_team_state`` (``freshness_state:stale`` +
``data_state:stale`` + ``confidence:low`` + ``status_code_unsupported:data_limited``),
even though the serving trusted snapshot published under the publication-critical
contract. Root cause: the readiness read resolved freshness LIVE from a global
``max(GameLog.game_date)`` recompute that lagged the serving snapshot's authoritative
``data_through``. ``data_state:stale`` comes ONLY from ``source_current=False``
(``assess_team_coverage`` source-stale gate), i.e. live ``is_current=False``.

These exercise the REAL resolver/coverage/eligibility path (no mocked SC-02, no
mocked coverage gate). Divergence: relievers rested with game logs older than the
14-day window (so the live global recompute is stale) while a published, serving,
trusted snapshot with a current ``data_through`` exists and the appearance ledger is
complete. Fixtures:

* A — current serving snapshot supersedes the lagging live freshness -> current.
* B — publication-critical incomplete (untrusted snapshot) -> withheld (fail closed).
* C — no snapshot authority -> unchanged conservative live freshness (fail closed).
* D — snapshot data_through outside the window -> stale (fail closed).
* E — non-serving/unpublished snapshot -> fail closed.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import dashboard_snapshot as dashboard_snapshot_service
from services.share_artifact_generation import (
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
    generate_team_state_artifact,
    resolve_team_readiness_payload,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db


TEAM_ID = 7
TODAY = date.today()
# Relievers rested: latest appearance older than the 14-day active window, so the
# live global max(GameLog.game_date) recompute is stale.
OLD_APPEARANCE = TODAY - timedelta(days=20)
# The serving snapshot published on a current data_through (within the window).
SNAPSHOT_DATA_THROUGH = TODAY - timedelta(days=1)


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


def _add_reliever(seed):
    pitcher = Pitcher(
        mlb_id=970000 + seed, full_name=f'Rested {seed:02d}', team_id=TEAM_ID,
        team_name='Example Club', team_abbreviation='EX', throws='L' if seed % 2 else 'R',
        active=True, roster_status='ACTIVE',
        roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(pitcher)
    db.session.flush()
    # Two prior complete relief appearances (older than the active window) so Role
    # Authority classifies a reliever while availability sees the arm as rested.
    for offset in (0, 2):
        gd = OLD_APPEARANCE - timedelta(days=offset)
        gpk = 971000 + seed * 10 + offset
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
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=datetime(2026, 6, 3, 12, 0, seed),
        raw_score=10.0, pitch_count_score=0.0, rest_days_score=0.0,
        appearances_score=0.0, innings_score=0.0, leverage_score=0.0,
        days_since_last_appearance=20, appearances_last_7=0, appearances_last_14=0,
        pitches_last_7_days=0, innings_last_7_days=0.0, avg_leverage_last_7=None,
        risk_level='LOW',
    ))
    db.session.flush()
    return pitcher


def _add_stale_sync_run():
    db.session.add(SyncRun(
        started_at=datetime(2026, 6, 3, 7, 30, 0), completed_at=datetime(2026, 6, 3, 7, 44, 27),
        status='partial', source='scheduled', latest_game_date=OLD_APPEARANCE,
        latest_workload_date=OLD_APPEARANCE, latest_fatigue_calculated_at=datetime(2026, 6, 3, 7, 44, 27),
        records_processed=12, new_logs_added=0, pitchers_updated=2, errors=0,
        created_at=datetime(2026, 6, 3, 7, 30, 0),
    ))
    db.session.commit()


def _trusted_payload(data_through):
    ref = data_through.isoformat()
    return {
        'capability': 'bullpen_dashboard',
        'freshness': {
            'data_through': ref,
            'availability_reference_date': ref,
            'slate_coverage': {
                'slate_date': ref,
                'validations_passed': True,
                'complete_enough_to_publish': True,
                'coverage_known': True,
                'reason_codes': ['no_scheduled_games', 'slate_complete'],
                'degradation_reasons': [],
            },
        },
    }


def _make_snapshot(*, data_through=SNAPSHOT_DATA_THROUGH, is_published=True,
                   status=None, publish_time=True):
    run = SyncRun(
        started_at=datetime(2026, 6, 3, 7, 30, 0), completed_at=datetime(2026, 6, 3, 7, 44, 27),
        status='partial', source='scheduled', created_at=datetime(2026, 6, 3, 7, 30, 0),
    )
    db.session.add(run)
    db.session.flush()
    snap = DashboardSnapshot(
        snapshot_type=dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=status or dashboard_snapshot_service.SNAPSHOT_STATUS_READY,
        is_published=is_published,
        published_at=datetime(2026, 7, 24, 6, 0, 0) if publish_time else None,
        payload=_trusted_payload(data_through),
        payload_version=dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION,
        data_through=data_through,
        availability_reference_date=data_through,
        source='readiness_freshness_test',
    )
    db.session.add(snap)
    db.session.flush()
    return snap


def _seed_rested_team():
    for seed in range(1, 9):
        _add_reliever(seed)
    _add_stale_sync_run()
    seed_roster_readiness_snapshots()


# ---------------------------------------------------------------------------
# Fixture A — current serving snapshot supersedes the lagging live freshness.
# ---------------------------------------------------------------------------


def test_A_live_freshness_is_stale_without_snapshot(app):
    # Reproduces the incident: the live global game-log recompute is stale, so the
    # readiness read (no serving-snapshot anchor) hits the source-stale gate.
    _seed_rested_team()
    payload = resolve_team_readiness_payload(TEAM_ID)
    assert payload is not None
    assert payload['freshness']['freshness_state'] == 'stale'
    assert payload['trust_metadata']['data_state'] == 'stale'
    assert payload['trust_metadata']['confidence'] == 'low'


def test_A_current_serving_snapshot_restores_freshness(app):
    _seed_rested_team()
    snapshot = _make_snapshot()
    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=snapshot)
    assert payload is not None
    assert payload['freshness']['freshness_state'] == 'current'
    # The source-stale gate no longer fires; per-team coverage governs the verdict.
    assert payload['trust_metadata']['data_state'] != 'stale'
    assert payload['trust_metadata']['confidence'] in {'high', 'medium'}
    assert payload['readiness']['status_code'] in {
        'operationally_stable', 'operationally_constrained', 'operationally_stressed',
    }


# ---------------------------------------------------------------------------
# Fail-closed fixtures B–E.
# ---------------------------------------------------------------------------


def test_B_untrusted_snapshot_stays_stale(app):
    # Publication-critical incomplete manifests as an untrusted snapshot (the
    # publish gate would have withheld it); the anchor fails closed.
    _seed_rested_team()
    snapshot = _make_snapshot(is_published=False)
    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=snapshot)
    assert payload['freshness']['freshness_state'] == 'stale'
    assert payload['trust_metadata']['data_state'] == 'stale'


def test_C_no_snapshot_keeps_conservative_live_freshness(app):
    _seed_rested_team()
    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=None)
    assert payload['freshness']['freshness_state'] == 'stale'
    assert payload['trust_metadata']['data_state'] == 'stale'


def test_D_snapshot_outside_window_stays_stale(app):
    _seed_rested_team()
    snapshot = _make_snapshot(data_through=TODAY - timedelta(days=30))
    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=snapshot)
    assert payload['freshness']['freshness_state'] == 'stale'
    assert payload['trust_metadata']['data_state'] == 'stale'


def test_E_non_ready_snapshot_fails_closed(app):
    _seed_rested_team()
    snapshot = _make_snapshot(
        status=dashboard_snapshot_service.SNAPSHOT_STATUS_PENDING, is_published=False,
        publish_time=False,
    )
    payload = resolve_team_readiness_payload(TEAM_ID, source_snapshot=snapshot)
    assert payload['freshness']['freshness_state'] == 'stale'
    assert payload['trust_metadata']['data_state'] == 'stale'


# ---------------------------------------------------------------------------
# End-to-end generation through the REAL path (no mocked SC-02 / eligibility).
# ---------------------------------------------------------------------------


def test_A_generation_publishes_with_current_serving_snapshot(app):
    _seed_rested_team()
    snapshot = _make_snapshot()
    result = generate_team_state_artifact(TEAM_ID, snapshot=snapshot, request_source='test')
    assert result.outcome in {OUTCOME_PUBLISHED, OUTCOME_REUSED}
    assert result.artifact is not None


def test_generation_refuses_without_a_serving_snapshot(app):
    # No published serving snapshot exists -> gather resolves none -> refused. The
    # freshness anchor never manufactures a snapshot; absence still fails closed.
    _seed_rested_team()
    result = generate_team_state_artifact(TEAM_ID, request_source='test')
    assert result.outcome == OUTCOME_REFUSED
