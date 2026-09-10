"""
Appearance Ledger integrity: reconciliation and the fail-closed publish gate.

An incomplete appearance ledger must never publish as current. These tests
seed the exact July 4, 2026 failure signature (a final game with no
appearance rows in the trailing window) and prove the dashboard snapshot
publisher withholds publication, while a fully reconciled ledger publishes.
"""

from datetime import date, timedelta

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from services import appearance_ledger, dashboard_snapshot
from utils.db import db
from utils.time import utc_now_naive


DATA_THROUGH = date(2026, 7, 5)
JULY_4 = date(2026, 7, 4)


@pytest.fixture
def app():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _seed_final_game(game_pk, game_date, *, home=108, away=111):
    db.session.add_all([
        ScheduledGame(
            team_id=home, game_pk=game_pk, game_date=game_date,
            status_state=ScheduledGame.STATE_FINAL, home_away='home',
            opponent_team_id=away,
        ),
        ScheduledGame(
            team_id=away, game_pk=game_pk, game_date=game_date,
            status_state=ScheduledGame.STATE_FINAL, home_away='away',
            opponent_team_id=home,
        ),
    ])


def _seed_marker(game_pk, game_date, *, lines_seen, status=None):
    db.session.add(PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=game_date,
        processing_status=status or PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        pitching_lines_seen=lines_seen,
        attempt_count=1,
    ))


def _seed_appearances(game_pk, game_date, count, *, mlb_id_base=900000):
    for offset in range(count):
        pitcher = Pitcher(
            mlb_id=mlb_id_base + game_pk * 100 + offset,
            full_name=f'Reliever {game_pk}-{offset}',
            team_id=108,
            active=True,
        )
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=game_pk,
            game_date=game_date,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            pitches_thrown=12,
        ))


# ── Ledger reconciliation ────────────────────────────────────────────────────

def test_empty_window_is_complete(app):
    with app.app_context():
        ledger = appearance_ledger.build_appearance_ledger(end_date=DATA_THROUGH)
    assert ledger['complete'] is True
    assert ledger['expected_games'] == 0
    assert ledger['reasons'] == []


def test_reconciled_game_is_complete(app):
    with app.app_context():
        _seed_final_game(824600, JULY_4)
        _seed_marker(824600, JULY_4, lines_seen=2)
        _seed_appearances(824600, JULY_4, 2)
        db.session.commit()
        ledger = appearance_ledger.build_appearance_ledger(end_date=DATA_THROUGH)

    assert ledger['complete'] is True
    assert ledger['expected_games'] == 1
    assert ledger['represented_games'] == 1
    assert ledger['expected_appearances'] == 2
    assert ledger['stored_appearances'] == 2


def test_final_game_without_appearance_rows_is_a_deficit(app):
    """The July 4 signature: schedule says final, game_logs holds nothing."""
    with app.app_context():
        _seed_final_game(824600, JULY_4)
        db.session.commit()
        ledger = appearance_ledger.build_appearance_ledger(end_date=DATA_THROUGH)

    assert ledger['complete'] is False
    assert appearance_ledger.REASON_MISSING_GAMES in ledger['reasons']
    assert ledger['missing_games'][0]['game_pk'] == 824600
    assert ledger['per_date'][JULY_4.isoformat()]['missing_game_pks'] == [824600]


def test_stored_rows_below_ingested_lines_is_a_deficit(app):
    with app.app_context():
        _seed_final_game(824601, JULY_4)
        _seed_marker(824601, JULY_4, lines_seen=9)
        _seed_appearances(824601, JULY_4, 8)
        db.session.commit()
        ledger = appearance_ledger.build_appearance_ledger(end_date=DATA_THROUGH)

    assert ledger['complete'] is False
    assert appearance_ledger.REASON_COUNT_DEFICITS in ledger['reasons']
    deficit = ledger['count_deficit_games'][0]
    assert deficit['game_pk'] == 824601
    assert deficit['expected_appearances'] == 9
    assert deficit['stored_appearances'] == 8


def test_incomplete_marker_on_final_game_is_a_deficit(app):
    with app.app_context():
        _seed_final_game(824602, JULY_4)
        _seed_marker(
            824602, JULY_4, lines_seen=4,
            status=PostgameProcessedGame.STATUS_INCOMPLETE,
        )
        _seed_appearances(824602, JULY_4, 4)
        db.session.commit()
        ledger = appearance_ledger.build_appearance_ledger(end_date=DATA_THROUGH)

    assert ledger['complete'] is False
    assert appearance_ledger.REASON_INCOMPLETE_MARKERS in ledger['reasons']
    assert ledger['incomplete_marker_games'][0]['game_pk'] == 824602


def test_non_final_games_create_no_expectation(app):
    # Four distinct non-final games, one per non-final status state. Each row
    # gets an explicit, distinct game_pk so the (team_id, game_pk) identity is
    # deterministic across processes, Python versions, hash seeds, and dialects.
    non_final_games = (
        (ScheduledGame.STATE_SCHEDULED, 900601),
        (ScheduledGame.STATE_POSTPONED, 900602),
        (ScheduledGame.STATE_SUSPENDED, 900603),
        (ScheduledGame.STATE_OTHER, 900604),
    )
    assert len({game_pk for _, game_pk in non_final_games}) == len(non_final_games)

    with app.app_context():
        for state, game_pk in non_final_games:
            db.session.add(ScheduledGame(
                team_id=108, game_pk=game_pk,
                game_date=JULY_4, status_state=state,
            ))
        db.session.commit()
        ledger = appearance_ledger.build_appearance_ledger(end_date=DATA_THROUGH)

    assert ledger['expected_games'] == 0
    assert ledger['complete'] is True


def test_games_outside_window_are_ignored(app):
    with app.app_context():
        stale = DATA_THROUGH - timedelta(days=30)
        _seed_final_game(823000, stale)
        db.session.commit()
        ledger = appearance_ledger.build_appearance_ledger(
            end_date=DATA_THROUGH, window_days=10,
        )

    assert ledger['expected_games'] == 0
    assert ledger['complete'] is True


# ── Publish gate ─────────────────────────────────────────────────────────────

def _complete_slate_coverage(slate_date):
    return {
        'slate_date': slate_date.isoformat() if slate_date else None,
        'validations_passed': True,
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'reason_codes': ['slate_complete'],
        'marker_counts': {},
    }


def _pending_snapshot(data_through=DATA_THROUGH):
    run = SyncRun(
        started_at=utc_now_naive(),
        completed_at=utc_now_naive(),
        status='success',
        stage='published',
        source='test',
    )
    db.session.add(run)
    db.session.flush()
    payload = {
        'freshness': {
            'data_through': data_through.isoformat(),
            'latest_workload_date': data_through.isoformat(),
            'availability_reference_date': (
                (data_through + timedelta(days=1)).isoformat()
            ),
            'slate_coverage': _complete_slate_coverage(data_through),
        },
    }
    snapshot = DashboardSnapshot(
        snapshot_type=dashboard_snapshot.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=dashboard_snapshot.SNAPSHOT_STATUS_PENDING,
        is_published=False,
        payload=payload,
        payload_version=dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION,
        data_through=data_through,
        availability_reference_date=data_through + timedelta(days=1),
        snapshot_generated_at=utc_now_naive(),
        source='test',
    )
    db.session.add(snapshot)
    db.session.flush()
    return snapshot


def test_publish_gate_blocks_incomplete_ledger(app):
    with app.app_context():
        _seed_final_game(824600, JULY_4)  # final, zero appearance rows
        snapshot = _pending_snapshot()
        result = dashboard_snapshot.publish_dashboard_snapshot(snapshot)

        assert result.is_published is False
        assert result.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
        assert result.error_message == (
            dashboard_snapshot.DASHBOARD_SNAPSHOT_APPEARANCE_LEDGER_INCOMPLETE
        )
        # The withheld reason surfaces honestly to readers.
        assert dashboard_snapshot.snapshot_unavailable_reason(result) == (
            dashboard_snapshot.DASHBOARD_SNAPSHOT_APPEARANCE_LEDGER_INCOMPLETE
        )


def test_publish_gate_keeps_previous_snapshot_serving(app):
    with app.app_context():
        prior = _pending_snapshot(data_through=DATA_THROUGH - timedelta(days=1))
        published_prior = dashboard_snapshot.publish_dashboard_snapshot(prior)
        assert published_prior.is_published is True

        _seed_final_game(824600, JULY_4)  # hole appears
        blocked = dashboard_snapshot.publish_dashboard_snapshot(_pending_snapshot())

        latest = dashboard_snapshot.get_latest_dashboard_snapshot()
        assert blocked.is_published is False
        assert latest.id == published_prior.id


def test_publish_gate_passes_complete_ledger(app):
    with app.app_context():
        _seed_final_game(824600, JULY_4)
        _seed_marker(824600, JULY_4, lines_seen=2)
        _seed_appearances(824600, JULY_4, 2)
        snapshot = _pending_snapshot()
        result = dashboard_snapshot.publish_dashboard_snapshot(snapshot)

        assert result.is_published is True
        assert result.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
        assert result.error_message is None


def test_publish_gate_fails_closed_when_ledger_uncomputable(app, monkeypatch):
    def boom(**_kwargs):
        raise RuntimeError('ledger query exploded')

    monkeypatch.setattr(appearance_ledger, 'build_appearance_ledger', boom)
    with app.app_context():
        result = dashboard_snapshot.publish_dashboard_snapshot(_pending_snapshot())

        assert result.is_published is False
        assert result.error_message == (
            dashboard_snapshot.DASHBOARD_SNAPSHOT_APPEARANCE_LEDGER_INCOMPLETE
        )


def test_publish_gate_kill_switch_is_explicit(app, monkeypatch):
    monkeypatch.setenv('APPEARANCE_LEDGER_GATE_ENABLED', 'false')
    with app.app_context():
        _seed_final_game(824600, JULY_4)
        result = dashboard_snapshot.publish_dashboard_snapshot(_pending_snapshot())

        assert result.is_published is True
