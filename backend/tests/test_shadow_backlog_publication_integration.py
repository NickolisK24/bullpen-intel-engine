"""The shadow-backlog distinction end to end, through the real gates.

Separating observation backlog from publication blockers is only safe if it
changes exactly one thing: whether the game-driven lane's own bookkeeping can
withhold the public snapshot. Everything that protects the BASEBALL record must
behave exactly as it did before.

These drive the REAL slate-coverage decision, the REAL appearance-ledger gate,
and the REAL snapshot publish path against PostgreSQL. Nothing that decides
withholding is stubbed in the scenario it is being tested in.

  A  healthy legacy truth + shadow backlog  -> may publish
  B  a genuine missing final game           -> still withheld
  C  partial appearances                    -> still withheld
  D  a non-game-log critical failure        -> still withheld
"""

from datetime import date, datetime

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.dashboard_snapshot import DashboardSnapshot  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import appearance_ledger
from services import dashboard_snapshot
from services import game_driven_ingestion
from services import game_ingestion_completeness as completeness
from services import publication_criticality
from services import slate_coverage
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db
from utils.time import utc_now_naive


SLATE = date(2026, 7, 29)
SHADOW = game_driven_ingestion.MODE_SHADOW

# A smaller slate than the audited 105: this file is about the INTEGRATION of
# the gates, and the 105/42/63 arithmetic is proven in
# test_shadow_publication_completeness_scope.py.
BACKLOG_GAMES = 6


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json',
    )
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


# ── Fixture ────────────────────────────────────────────────────────────────

def _schedule(game_pk, *, state=ScheduledGame.STATE_FINAL):
    for team_id, opponent, side in ((116, 142, 'home'), (142, 116, 'away')):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=SLATE,
            status_state=state, status_code='F', game_type='R',
            home_away=side, opponent_team_id=opponent,
        ))


def _marker(game_pk, *, status=PostgameProcessedGame.STATUS_FULLY_PROCESSED):
    db.session.add(PostgameProcessedGame(
        mlb_game_pk=game_pk, game_date=SLATE, processing_status=status,
    ))


def _appearance(game_pk, mlb_id):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'Arm {mlb_id}', team_id=116,
        team_abbreviation='TST', position='P', active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=SLATE,
        innings_pitched=1.0, innings_pitched_outs=3,
    ))


def _seed_shadow_backlog(*, appearances_per_game=2):
    """Final games, fully represented, with NO durable work items.

    This is the shadow lane's real production shape: the games are complete in
    every sense the public product cares about, and the lane has no bookkeeping
    for them because it has never been allowed to write any.
    """
    mlb_id = 970000
    game_pks = []
    for index in range(BACKLOG_GAMES):
        game_pk = 960000 + index
        game_pks.append(game_pk)
        _schedule(game_pk)
        _marker(game_pk)
        for _ in range(appearances_per_game):
            _appearance(game_pk, mlb_id)
            mlb_id += 1
    db.session.commit()
    return game_pks


def _schedule_rows():
    return ScheduledGame.query.filter_by(game_date=SLATE).all()


def _markers():
    return PostgameProcessedGame.query.filter_by(game_date=SLATE).all()


def _game_lane(*, mode=SHADOW, non_gamelog_failed=0):
    """The publication-critical result the daily sync would build."""
    proof = completeness.build_game_ingestion_completeness(
        SLATE, lane_mode=mode,
    )
    return proof, sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': mode,
            'report': {'best_effort_games_deferred': 0},
            'completeness': proof,
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=non_gamelog_failed,
    )


def _coverage(critical_complete):
    return slate_coverage.compute_slate_coverage(
        SLATE, sync_status='partial',
        publication_critical_complete=critical_complete,
        schedule_rows=_schedule_rows(), postgame_markers=_markers(),
        schedule_material_available=True,
    )


def _payload():
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': utc_now_naive().isoformat(),
        'ranking_applied': False, 'selection_made': False,
        'scope': 'bullpen_eligible', 'context': {},
        'roles': {'order': [], 'counts': {}, 'total': 0},
        'landscape': {},
        'freshness': {
            'data_through': SLATE.isoformat(),
            'availability_reference_date': SLATE.isoformat(),
            'reference_date': SLATE.isoformat(),
            'sync_status': 'partial', 'last_successful_sync': None,
        },
        'availability_summary': {},
    }


def _publish(critical_complete):
    run = SyncRun(job_name='daily_sync')
    db.session.add(run)
    db.session.flush()
    return dashboard_snapshot.store_dashboard_snapshot(
        _payload(), sync_run_id=run.id, source='test', publish=True,
        publication_critical_complete=critical_complete,
    )


# ── A: healthy legacy truth + shadow backlog ───────────────────────────────

def test_A_a_shadow_backlog_alone_does_not_withhold(app, monkeypatch):
    """The defect this package repairs, proven at the publish path."""
    monkeypatch.setattr(
        dashboard_snapshot.appearance_ledger,
        'appearance_ledger_publish_block',
        lambda **_kwargs: (None, {'reasons': []}),
    )
    _seed_shadow_backlog()

    proof, critical = _game_lane()

    # The backlog is real and remains visible.
    assert proof['observation']['unresolved_game_count'] == BACKLOG_GAMES
    assert proof['observation']['complete'] is False
    # And contributes nothing to the gate.
    assert critical['complete'] is True
    assert critical['publication_critical_unresolved'] == 0

    coverage = _coverage(critical['complete'])
    assert coverage['validations_passed'] is True
    assert coverage['complete_enough_to_publish'] is True

    snapshot = _publish(critical['complete'])
    assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
    assert snapshot.is_published is True


def test_A_the_same_backlog_withholds_before_the_repair_semantics(app):
    """The old reading is still available, and still withholds.

    Reading the observation count as a blocker is exactly what production did.
    Keeping that path exercised proves the difference is the SEMANTICS, not a
    change in what the lane observed.
    """
    _seed_shadow_backlog()
    proof = completeness.build_game_ingestion_completeness(
        SLATE, lane_mode=SHADOW,
    )
    old_reading = publication_criticality.build_publication_critical_result(
        critical_total=proof['expected_final_games'],
        critical_completed=proof['completed_final_games'],
        critical_unresolved=proof['unresolved_final_games'],
        authority_available=True,
    )
    assert old_reading['complete'] is False
    assert _coverage(old_reading['complete'])[
        'complete_enough_to_publish'
    ] is False


# ── B: a genuine missing final game while shadow ───────────────────────────

def test_B_a_final_game_missing_appearances_still_withholds(app):
    """The appearance-ledger gate is REAL here, not stubbed."""
    _seed_shadow_backlog()
    # One more official/stored final game with a marker and NO appearances.
    _schedule(965000)
    _marker(965000)
    db.session.commit()

    _proof, critical = _game_lane()
    # The game lane is content: it has no work-item evidence either way.
    assert critical['complete'] is True

    # The canonical appearance ledger is not.
    reason, ledger = appearance_ledger.appearance_ledger_publish_block(
        end_date=SLATE,
    )
    assert reason is not None
    assert ledger is None or ledger['complete'] is False

    snapshot = _publish(critical['complete'])
    assert snapshot.is_published is False
    assert snapshot.status != dashboard_snapshot.SNAPSHOT_STATUS_READY


def test_B_an_unprocessed_final_game_still_withholds_at_coverage(app):
    _seed_shadow_backlog()
    _schedule(965001)  # final, but no postgame marker at all
    db.session.commit()

    _proof, critical = _game_lane()
    assert critical['complete'] is True

    coverage = _coverage(critical['complete'])
    assert coverage['complete_enough_to_publish'] is False
    assert coverage['reason_codes']


# ── C: partial appearances while shadow ────────────────────────────────────

def test_C_partial_appearance_coverage_still_withholds(app):
    _seed_shadow_backlog()
    _schedule(966000)
    _marker(966000, status=PostgameProcessedGame.STATUS_INCOMPLETE)
    _appearance(966000, 979500)
    db.session.commit()

    _proof, critical = _game_lane()
    assert critical['complete'] is True

    reason, _ledger = appearance_ledger.appearance_ledger_publish_block(
        end_date=SLATE,
    )
    coverage = _coverage(critical['complete'])
    # Either canonical gate withholding is enough; both are explicit.
    assert (reason is not None) or (
        coverage['complete_enough_to_publish'] is False
    )
    assert not (
        reason is None and coverage['complete_enough_to_publish'] is True
    )


def test_C_an_expected_versus_reconciled_shortfall_still_withholds(app):
    """A completed work item claiming more rows than the ledger holds."""
    _seed_shadow_backlog()
    _schedule(966100)
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=966100, represented_date=SLATE, game_date=SLATE,
        status=GameIngestionWorkItem.STATUS_COMPLETED,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        rows_expected=5, rows_reconciled=5,
        completed_at=datetime(2026, 7, 29, 6, 0, 0),
    ))
    _appearance(966100, 979600)
    db.session.commit()

    proof, critical = _game_lane()
    gate = proof['publication_gate']
    assert gate['appearance_rows_expected'] > gate['appearance_rows_reconciled']
    assert gate['complete'] is False
    assert critical['complete'] is False

    assert _coverage(critical['complete'])[
        'complete_enough_to_publish'
    ] is False


# ── D: a non-game-log publication-critical failure ─────────────────────────

def test_D_a_non_gamelog_critical_failure_still_withholds(app):
    _seed_shadow_backlog()
    _proof, critical = _game_lane(non_gamelog_failed=1)

    assert critical['complete'] is False
    assert publication_criticality.REASON_NON_GAMELOG_FAILURE in (
        critical['reason_codes']
    )
    assert _coverage(critical['complete'])[
        'complete_enough_to_publish'
    ] is False

    snapshot = _publish(critical['complete'])
    assert snapshot.is_published is False


# ── The distinction changes nothing about the lane itself ──────────────────

def test_the_gate_evaluation_creates_no_work_item(app):
    """Evaluating the gate must not repair the backlog it declines to count."""
    _seed_shadow_backlog()
    before = GameIngestionWorkItem.query.count()

    for mode in (SHADOW, game_driven_ingestion.MODE_AUTHORITATIVE):
        _game_lane(mode=mode)
    db.session.rollback()

    assert GameIngestionWorkItem.query.count() == before == 0


def test_the_backlog_is_not_erased_by_being_non_blocking(app):
    _seed_shadow_backlog()
    proof, critical = _game_lane()

    assert critical['complete'] is True
    # Still counted, still named, still reported.
    assert proof['unresolved_final_games'] == BACKLOG_GAMES
    assert proof['observation']['unresolved_game_count'] == BACKLOG_GAMES
    assert proof['publication_gate']['observation_only_game_count'] == (
        BACKLOG_GAMES
    )
    membership = completeness.unresolved_final_game_membership(SLATE)
    assert len(membership['game_pks']) == BACKLOG_GAMES
