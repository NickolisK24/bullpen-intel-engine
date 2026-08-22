"""Reproduction + repair proof for the daily-sync publication-critical contract.

Production incident (run 30124220074 / snapshot 270): a best-effort per-pitcher
game-log CORRECTION lane exhausted its runtime budget, marked the whole SyncRun
``partial``, and the slate-coverage gate withheld the trusted snapshot even though
schedule finality, postgame markers, and the appearance ledger were all complete.

These tests exercise the REAL slate-coverage decision and the REAL snapshot
publish path (the coverage gate is never mocked). Scenarios:

* A — critical complete, best-effort partial -> snapshot may publish.
* B — a publication-critical failure -> snapshot withheld.
* C — unknown criticality -> snapshot withheld.
* D — a genuine finality/slate gap -> snapshot withheld even under a partial that
      would otherwise be allowed.
"""

from datetime import date

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
from services import dashboard_snapshot
from services import publication_criticality as pc
from services import slate_coverage
from services.mlb_api import MlbApiFetchError, mlb_client
from services.roster_status import STATUS_ACTIVE, STATUS_IL_10, STATUS_UNKNOWN
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


SLATE = date(2026, 7, 23)
GAME_PK = 771001


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


# ===========================================================================
# Gate-level — the real compute_slate_coverage decision (no DB, deterministic)
# ===========================================================================


def _final_game_rows(status_state=ScheduledGame.STATE_FINAL):
    return [
        ScheduledGame(team_id=116, game_pk=GAME_PK, game_date=SLATE,
                      status_state=status_state, status_code='F', game_type='R',
                      home_away='home', opponent_team_id=142),
        ScheduledGame(team_id=142, game_pk=GAME_PK, game_date=SLATE,
                      status_state=status_state, status_code='F', game_type='R',
                      home_away='away', opponent_team_id=116),
    ]


def _fully_processed_marker():
    return [PostgameProcessedGame(mlb_game_pk=GAME_PK, game_date=SLATE,
                                  processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED)]


def test_A_partial_but_publication_critical_complete_is_publishable():
    coverage = slate_coverage.compute_slate_coverage(
        SLATE, sync_status='partial', publication_critical_complete=True,
        schedule_rows=_final_game_rows(), postgame_markers=_fully_processed_marker(),
        schedule_material_available=True,
    )
    assert coverage['validations_passed'] is True
    assert coverage['complete_enough_to_publish'] is True
    assert 'partial_sync' not in coverage['reason_codes']


def test_B_partial_default_still_withholds_unchanged_behavior():
    # No publication_critical_complete supplied -> prior conservative behavior.
    coverage = slate_coverage.compute_slate_coverage(
        SLATE, sync_status='partial',
        schedule_rows=_final_game_rows(), postgame_markers=_fully_processed_marker(),
        schedule_material_available=True,
    )
    assert coverage['complete_enough_to_publish'] is False
    assert 'partial_sync' in coverage['reason_codes']


def test_D_genuine_finality_gap_withholds_even_when_critical_complete():
    coverage = slate_coverage.compute_slate_coverage(
        SLATE, sync_status='partial', publication_critical_complete=True,
        schedule_rows=_final_game_rows(status_state=ScheduledGame.STATE_SCHEDULED),
        postgame_markers=[], schedule_material_available=True,
    )
    assert coverage['complete_enough_to_publish'] is False
    assert 'scheduled_games_not_final' in coverage['reason_codes']


def test_C_unknown_criticality_shortfall_withholds_end_to_end():
    # Real chain: an unknown-criticality game-log item makes the real completeness
    # result incomplete, and the real coverage gate then withholds even though the
    # current slate's games / markers are otherwise complete. (Fail closed.)
    result = pc.build_publication_critical_result(
        critical_total=400, critical_completed=400, critical_failed=0,
        critical_unresolved=0, unknown_criticality=1,
        best_effort_total=50, best_effort_deferred=0, authority_available=True,
    )
    assert result['complete'] is False
    assert pc.REASON_UNKNOWN_CRITICALITY in result['reason_codes']
    coverage = slate_coverage.compute_slate_coverage(
        SLATE, sync_status='partial', publication_critical_complete=result['complete'],
        schedule_rows=_final_game_rows(), postgame_markers=_fully_processed_marker(),
        schedule_material_available=True,
    )
    assert coverage['complete_enough_to_publish'] is False
    assert 'partial_sync' in coverage['reason_codes']


def test_success_run_is_unaffected_by_publication_critical_flag():
    coverage = slate_coverage.compute_slate_coverage(
        SLATE, sync_status='success', publication_critical_complete=None,
        schedule_rows=_final_game_rows(), postgame_markers=_fully_processed_marker(),
        schedule_material_available=True,
    )
    assert coverage['complete_enough_to_publish'] is True


# ===========================================================================
# Publish-path — the real store/publish decision consumes the coverage result.
# The appearance-ledger gate is UNCHANGED and separately covered; it is stubbed
# to pass here so this test isolates the coverage-gate publish decision (the
# coverage gate itself is never mocked).
# ===========================================================================


def _seed_complete_slate():
    for row in _final_game_rows():
        db.session.add(row)
    for marker in _fully_processed_marker():
        db.session.add(marker)
    db.session.flush()


def _partial_payload():
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': utc_now_naive().isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': 'bullpen_eligible',
        'context': {},
        'roles': {'order': [], 'counts': {}, 'total': 0},
        'landscape': {},
        'freshness': {
            'data_through': SLATE.isoformat(),
            'availability_reference_date': SLATE.isoformat(),
            'reference_date': SLATE.isoformat(),
            'sync_status': 'partial',
            'last_successful_sync': None,
        },
        'availability_summary': {},
    }


def _run(app):
    run = SyncRun(job_name='daily_sync')
    db.session.add(run)
    db.session.flush()
    return run


def test_A_publish_path_publishes_when_critical_complete(app, monkeypatch):
    monkeypatch.setattr(
        dashboard_snapshot.appearance_ledger, 'appearance_ledger_publish_block',
        lambda **_kwargs: (None, {'reasons': []}),
    )
    _seed_complete_slate()
    run = _run(app)
    snapshot = dashboard_snapshot.store_dashboard_snapshot(
        _partial_payload(), sync_run_id=run.id, source='test', publish=True,
        publication_critical_complete=True,
    )
    assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
    assert snapshot.is_published is True


def test_B_publish_path_withholds_when_critical_incomplete(app, monkeypatch):
    monkeypatch.setattr(
        dashboard_snapshot.appearance_ledger, 'appearance_ledger_publish_block',
        lambda **_kwargs: (None, {'reasons': []}),
    )
    _seed_complete_slate()
    run = _run(app)
    snapshot = dashboard_snapshot.store_dashboard_snapshot(
        _partial_payload(), sync_run_id=run.id, source='test', publish=True,
        publication_critical_complete=False,
    )
    assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
    assert snapshot.is_published is False
    assert snapshot.error_message == dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE


# ===========================================================================
# Lane-level — sync_recent_logs orders publication-critical first and classifies
# the budget-exhausted remainder by criticality (WS-B / WS-C).
# ===========================================================================


def _seed_lane_pitcher(mlb_id, roster_status, *, position='P', name=None):
    p = Pitcher(mlb_id=mlb_id, full_name=f'P{mlb_id}', team_id=108,
                team_abbreviation='LAA', active=True, roster_status=roster_status,
                position=position)
    if name is not None:
        p.full_name = name
    db.session.add(p)
    db.session.flush()
    return p


def test_publication_critical_pitchers_are_ingested_first(app, monkeypatch):
    # Two active-roster (critical) + two IL (best-effort), interleaved by id.
    _seed_lane_pitcher(910001, STATUS_IL_10)
    _seed_lane_pitcher(910002, STATUS_ACTIVE)
    _seed_lane_pitcher(910003, STATUS_IL_10)
    _seed_lane_pitcher(910004, STATUS_ACTIVE)
    called_order = []
    monkeypatch.setattr(
        mlb_client, 'get_pitcher_game_logs',
        lambda mlb_id, season=None: called_order.append(mlb_id) or [],
    )
    sync_service.sync_recent_logs(days_back=7, reference_date=SLATE)
    # The two active-roster pitchers (critical) are fetched before either IL arm.
    assert set(called_order[:2]) == {910002, 910004}
    assert set(called_order[2:]) == {910001, 910003}


def test_budget_exhaustion_classifies_remainder_by_criticality(app, monkeypatch):
    _seed_lane_pitcher(920001, STATUS_ACTIVE)
    _seed_lane_pitcher(920002, STATUS_IL_10)
    _seed_lane_pitcher(920003, STATUS_UNKNOWN)
    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', lambda *a, **k: [])
    # Zero budget -> everything deferred; classified by roster criticality.
    result = sync_service.sync_recent_logs(
        days_back=7, reference_date=SLATE, time_budget_seconds=0,
    )
    assert result['budget_exhausted_pitchers'] == 3
    assert result['critical_budget_exhausted'] == 1
    assert result['best_effort_budget_exhausted'] == 1
    assert result['unknown_budget_exhausted'] == 1
    assert result['lane_health'] == 'budget_exhausted'


def test_vargas_equivalent_fetch_failure_is_dead_lettered_best_effort(
    app, monkeypatch,
):
    _seed_lane_pitcher(
        545121, STATUS_ACTIVE, position='1B', name='Ildemaro Vargas',
    )

    def fail(_mlb_id, season=None):
        raise MlbApiFetchError(
            'ReadTimeout', endpoint='/people/545121/stats',
        )

    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', fail)
    result = sync_service.sync_recent_logs(
        days_back=7, reference_date=SLATE,
    )

    assert result['records_failed'] == 1
    assert result['critical_non_budget_failed'] == 0
    assert result['unknown_non_budget_failed'] == 0
    assert result['best_effort_non_budget_failed'] == 1
    failure = SyncFailure.query.one()
    assert failure.entity_type == 'pitcher_game_logs'
    assert failure.entity_ref == '545121'
    assert failure.resolved is False

    publication = sync_service._publication_critical_from_legacy_pull(
        pull=result, non_gamelog_critical_failed=0,
    )
    assert publication['complete'] is True
    assert publication['publication_critical_unresolved'] == 0
    assert publication['best_effort_deferred'] == 1
    monkeypatch.setattr(
        dashboard_snapshot.appearance_ledger, 'appearance_ledger_publish_block',
        lambda **_kwargs: (None, {'reasons': []}),
    )
    _seed_complete_slate()
    snapshot = dashboard_snapshot.store_dashboard_snapshot(
        _partial_payload(), sync_run_id=_run(app).id, source='test', publish=True,
        publication_critical_complete=publication['complete'],
    )
    assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
    assert snapshot.is_published is True


def test_active_bullpen_fetch_failure_still_blocks_publication(app, monkeypatch):
    _seed_lane_pitcher(545122, STATUS_ACTIVE, position='RP', name='Required Arm')

    def fail(_mlb_id, season=None):
        raise MlbApiFetchError(
            'ReadTimeout', endpoint='/people/545122/stats',
        )

    monkeypatch.setattr(mlb_client, 'get_pitcher_game_logs', fail)
    result = sync_service.sync_recent_logs(
        days_back=7, reference_date=SLATE,
    )
    publication = sync_service._publication_critical_from_legacy_pull(
        pull=result, non_gamelog_critical_failed=0,
    )

    assert result['critical_non_budget_failed'] == 1
    assert result['best_effort_non_budget_failed'] == 0
    assert publication['complete'] is False
    assert publication['publication_critical_unresolved'] == 1
    monkeypatch.setattr(
        dashboard_snapshot.appearance_ledger, 'appearance_ledger_publish_block',
        lambda **_kwargs: (None, {'reasons': []}),
    )
    _seed_complete_slate()
    snapshot = dashboard_snapshot.store_dashboard_snapshot(
        _partial_payload(), sync_run_id=_run(app).id, source='test', publish=True,
        publication_critical_complete=publication['complete'],
    )
    assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
    assert snapshot.is_published is False


def test_scoped_failure_accounting_falls_back_to_strict_legacy_behavior():
    publication = sync_service._publication_critical_from_legacy_pull(
        pull={
            'publication_critical_total': 1,
            'best_effort_total': 0,
            'gamelog_non_budget_failed': 1,
        },
        non_gamelog_critical_failed=0,
    )
    assert publication['complete'] is False
    assert publication['publication_critical_unresolved'] == 1
