"""Foundation 3C — game-driven ingestion runner, checkpoint, and resume."""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import game_driven_ingestion
from services import game_appearance_extraction as extraction
from utils.db import db


REFERENCE = date(2026, 7, 29)
HOME_TEAM = 147
AWAY_TEAM = 111


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


def _schedule(game_pk, *, game_date=REFERENCE, start_hour=19):
    for team_id, opponent_id, side in (
        (HOME_TEAM, AWAY_TEAM, 'home'),
        (AWAY_TEAM, HOME_TEAM, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id,
            game_pk=game_pk,
            game_date=game_date,
            game_datetime=datetime(
                game_date.year, game_date.month, game_date.day, start_hour, 5,
            ),
            opponent_team_id=opponent_id,
            home_away=side,
            game_type='R',
            status_code='F',
            status_state=ScheduledGame.STATE_FINAL,
        ))


def _pitcher(mlb_id, *, team_id=HOME_TEAM):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=f'Arm {mlb_id}',
        team_id=team_id,
        team_abbreviation='TST',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    return pitcher


def _appearance(pitcher_mlb_id, *, game_pk, outs=3, earned_runs=0, starter=False):
    return {
        'game_pk': game_pk,
        'game_date': REFERENCE,
        'pitcher_mlb_id': pitcher_mlb_id,
        'team_id': HOME_TEAM,
        'opponent_team_id': AWAY_TEAM,
        'side': 'home',
        'appearance_role': 'start' if starter else 'relief',
        'games_started': 1 if starter else 0,
        'is_starter': starter,
        'is_reliever': not starter,
        'outs_recorded': outs,
        'innings_pitched': outs / 3.0,
        'earned_runs': earned_runs,
        'runs_allowed': earned_runs,
        'hits_allowed': 1,
        'walks': 0,
        'strikeouts': 2,
        'home_runs_allowed': 0,
        'batters_faced': 4,
        'pitches_thrown': 15,
        'source_authority': extraction.SOURCE_AUTHORITY,
    }


class FakeLane:
    """Deterministic stand-in for the fetch/extract/persist trio.

    It performs the same canonical GameLog upsert the real path performs
    (same natural key, same integer-outs authority) so idempotence, replay, and
    correction behaviour are exercised for real against the database.
    """

    def __init__(self, appearances_by_game, *, fail_games=(), unsafe_games=()):
        self.appearances_by_game = appearances_by_game
        self.fail_games = set(fail_games)
        self.unsafe_games = set(unsafe_games)
        self.fetch_calls = []
        self.persist_calls = []

    def fetch(self, item):
        self.fetch_calls.append(item.game_pk)
        if item.game_pk in self.fail_games:
            raise TimeoutError('fetch failed')
        return {'gamePk': item.game_pk}, {'boxscore': item.game_pk}

    def extract(self, item, game_payload, boxscore):
        return list(self.appearances_by_game.get(item.game_pk, ()))

    def persist(self, item, game_payload, boxscore, *, sync_run_id=None):
        self.persist_calls.append(item.game_pk)
        inserted = updated = 0
        for record in self.appearances_by_game.get(item.game_pk, ()):
            pitcher = Pitcher.query.filter_by(
                mlb_id=record['pitcher_mlb_id']
            ).first()
            row = GameLog.query.filter_by(
                pitcher_id=pitcher.id, mlb_game_pk=item.game_pk
            ).first()
            if row is None:
                row = GameLog(pitcher_id=pitcher.id, mlb_game_pk=item.game_pk)
                db.session.add(row)
                inserted += 1
            elif int(row.innings_pitched_outs or 0) != record['outs_recorded'] or (
                int(row.earned_runs or 0) != int(record['earned_runs'] or 0)
            ):
                updated += 1
            row.game_date = record['game_date']
            row.game_type = 'R'
            row.games_started = record['games_started']
            row.innings_pitched_outs = record['outs_recorded']
            row.innings_pitched = record['outs_recorded'] / 3.0
            row.earned_runs = record['earned_runs']
            row.runs_allowed = record['runs_allowed']
            row.hits_allowed = record['hits_allowed']
            row.walks = record['walks']
            row.strikeouts = record['strikeouts']
            row.home_runs_allowed = record['home_runs_allowed']
            row.appearance_team_id = record['team_id']
            row.appearance_team_status = GameLog.APPEARANCE_TEAM_RESOLVED
            row.appearance_team_source = 'test'
        db.session.flush()
        return {
            'inserted': inserted,
            'updated': updated,
            'unsafe': 1 if item.game_pk in self.unsafe_games else 0,
            'unresolved_pitchers': 0,
        }

    def handlers(self):
        return {
            'process_game': self.persist,
            'fetch_boxscore': self.fetch,
        }


def _run(lane, *, mode=game_driven_ingestion.MODE_WRITE, **kwargs):
    original = game_driven_ingestion._resolve_handlers
    game_driven_ingestion._resolve_handlers = lambda process_game, fetch: {
        'fetch': lane.fetch, 'extract': lane.extract, 'persist': lane.persist,
    }
    try:
        return game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE,
            mode=mode,
            process_game=lane.persist,
            fetch_boxscore=lane.fetch,
            **kwargs,
        )
    finally:
        game_driven_ingestion._resolve_handlers = original


# ── Mode gating ──────────────────────────────────────────────────────────────


def test_the_lane_is_off_by_default(app, monkeypatch):
    monkeypatch.delenv(game_driven_ingestion.MODE_ENV_VAR, raising=False)

    assert game_driven_ingestion.ingestion_mode() == game_driven_ingestion.MODE_OFF
    assert game_driven_ingestion.enabled() is False
    assert game_driven_ingestion.publication_authoritative() is False


def test_an_unrecognised_mode_falls_back_to_off(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'sort-of-on')

    assert game_driven_ingestion.ingestion_mode() == game_driven_ingestion.MODE_OFF


def test_off_mode_does_no_work(app):
    with app.app_context():
        _schedule(910001)
        db.session.commit()
        lane = FakeLane({910001: []})

        report = _run(lane, mode=game_driven_ingestion.MODE_OFF)

        assert report['status'] == 'disabled'
        assert lane.fetch_calls == []


# ── Persistence ─────────────────────────────────────────────────────────────


def test_first_processing_inserts_rows_and_completes_the_work_item(app):
    with app.app_context():
        _schedule(910002)
        _pitcher(5001)
        _pitcher(5002)
        db.session.commit()
        lane = FakeLane({910002: [
            _appearance(5001, game_pk=910002, outs=18, starter=True),
            _appearance(5002, game_pk=910002, outs=3),
        ]})

        report = _run(lane)

        assert report['games_completed'] == 1
        assert report['rows_inserted'] == 2
        assert GameLog.query.filter_by(mlb_game_pk=910002).count() == 2

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910002).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED
        assert item.rows_expected == 2
        assert item.rows_reconciled == 2
        assert item.relief_rows_reconciled == 1
        assert item.completed_at is not None
        assert item.source_revision


def test_replaying_an_unchanged_game_creates_no_duplicates_and_no_changes(app):
    with app.app_context():
        _schedule(910003)
        _pitcher(5003)
        db.session.commit()
        appearances = {910003: [_appearance(5003, game_pk=910003)]}

        first = _run(FakeLane(appearances))
        second = _run(FakeLane(appearances))

        assert first['rows_inserted'] == 1
        assert second['rows_inserted'] == 0
        assert second['rows_updated'] == 0
        assert second['rows_unchanged'] == 1
        assert second['corrections_applied'] == 0
        assert GameLog.query.filter_by(mlb_game_pk=910003).count() == 1


def test_a_corrected_replay_updates_governed_fields_and_records_the_correction(app):
    with app.app_context():
        _schedule(910004)
        _pitcher(5004)
        db.session.commit()

        _run(FakeLane({910004: [_appearance(5004, game_pk=910004, earned_runs=1)]}))
        report = _run(
            FakeLane({910004: [_appearance(5004, game_pk=910004, earned_runs=3)]})
        )

        assert report['rows_updated'] == 1
        assert report['corrections_applied'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=910004).count() == 1
        row = GameLog.query.filter_by(mlb_game_pk=910004).one()
        assert row.earned_runs == 3

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910004).one()
        assert item.correction_count == 1
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


def test_the_canonical_uniqueness_makes_a_duplicate_row_impossible(app):
    with app.app_context():
        _schedule(910005)
        pitcher = _pitcher(5005)
        db.session.commit()
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=910005, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3,
        ))
        db.session.commit()

        with pytest.raises(Exception):
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=910005, game_date=REFERENCE,
                innings_pitched=1.0, innings_pitched_outs=3,
            ))
            db.session.commit()
        db.session.rollback()


def test_a_game_is_not_completed_when_its_writes_roll_back(app):
    with app.app_context():
        _schedule(910006)
        _pitcher(5006)
        db.session.commit()

        class ExplodingLane(FakeLane):
            def persist(self, item, game_payload, boxscore, *, sync_run_id=None):
                super().persist(item, game_payload, boxscore, sync_run_id=sync_run_id)
                raise RuntimeError('write failed after partial flush')

        report = _run(
            ExplodingLane({910006: [_appearance(5006, game_pk=910006)]})
        )

        assert report['games_completed'] == 0
        assert report['games_failed'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=910006).count() == 0
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910006).one()
        assert item.status != GameIngestionWorkItem.STATUS_COMPLETED
        assert item.completed_at is None


def test_an_unsafe_correction_blocks_completion(app):
    with app.app_context():
        _schedule(910007)
        _pitcher(5007)
        db.session.commit()

        report = _run(FakeLane(
            {910007: [_appearance(5007, game_pk=910007)]},
            unsafe_games={910007},
        ))

        assert report['games_completed'] == 0
        assert report['failure_classes'] == {
            game_driven_ingestion.ERROR_CORRECTION_CONFLICT: 1,
        }
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910007).one()
        assert item.error_class == game_driven_ingestion.ERROR_CORRECTION_CONFLICT


# ── Checkpoint and resume ───────────────────────────────────────────────────


def test_a_completed_game_stays_completed_across_runs(app):
    with app.app_context():
        _schedule(910008)
        _pitcher(5008)
        db.session.commit()
        appearances = {910008: [_appearance(5008, game_pk=910008)]}

        _run(FakeLane(appearances))
        _run(FakeLane(appearances))

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910008).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


def test_a_failed_game_resumes_on_the_next_run(app):
    with app.app_context():
        _schedule(910009)
        _pitcher(5009)
        db.session.commit()
        appearances = {910009: [_appearance(5009, game_pk=910009)]}

        failed = _run(FakeLane(appearances, fail_games={910009}))
        assert failed['games_failed'] == 1
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910009).one()
        assert item.status == GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE

        recovered = _run(FakeLane(appearances))

        assert recovered['games_completed'] == 1
        assert recovered['retry_count'] == 1
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910009).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


def test_repeated_failure_becomes_terminal_rather_than_looping_forever(app):
    with app.app_context():
        _schedule(910010)
        db.session.commit()
        lane_spec = {910010: []}

        for _ in range(game_driven_ingestion.RETRY_LIMIT):
            _run(FakeLane(lane_spec, fail_games={910010}))

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910010).one()
        assert item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
        assert item.attempt_count >= game_driven_ingestion.RETRY_LIMIT


def test_budget_exhaustion_preserves_remaining_work_and_never_dead_letters_it(app):
    with app.app_context():
        _schedule(910011, start_hour=13)
        _schedule(910012, start_hour=19)
        _pitcher(5011)
        db.session.commit()
        appearances = {
            910011: [_appearance(5011, game_pk=910011)],
            910012: [_appearance(5011, game_pk=910012)],
        }

        report = _run(FakeLane(appearances), time_budget_seconds=0.0)

        assert report['budget_stop_triggered'] is True
        assert report['status'] == 'incomplete'
        assert report['budget_stop']['critical_games_remaining'] == 2
        # Nothing was fetched, nothing was dead-lettered, and both games are
        # resumable planned work.
        items = GameIngestionWorkItem.query.order_by(
            GameIngestionWorkItem.mlb_game_pk
        ).all()
        assert [item.status for item in items] == [
            GameIngestionWorkItem.STATUS_PLANNED,
            GameIngestionWorkItem.STATUS_PLANNED,
        ]
        assert all(
            item.error_class == game_driven_ingestion.ERROR_BUDGET_EXHAUSTED
            for item in items
        )

        # And the next run picks that preserved work straight back up.
        resumed = FakeLane(appearances)
        resumed_report = _run(resumed)
        assert resumed_report['retry_count'] == 2
        assert resumed_report['games_completed'] == 2
        assert sorted(resumed.fetch_calls) == [910011, 910012]


def test_the_next_run_starts_with_unresolved_critical_games(app):
    with app.app_context():
        _schedule(910013, start_hour=13)
        _schedule(910014, start_hour=19)
        _pitcher(5013)
        db.session.commit()
        appearances = {
            910013: [_appearance(5013, game_pk=910013)],
            910014: [_appearance(5013, game_pk=910014)],
        }

        # 910013 (earlier start time) completes; 910014 fails.
        first = _run(FakeLane(appearances, fail_games={910014}))
        assert first['games_completed'] == 1
        assert first['games_failed'] == 1

        second = FakeLane(appearances)
        _run(second)

        # The completed game is still re-checked for corrections, but the
        # unresolved one is fetched FIRST — the next run never restarts from
        # the beginning of the window.
        assert second.fetch_calls[0] == 910014


def test_a_budget_stop_never_demotes_an_already_completed_game(app):
    with app.app_context():
        _schedule(910015)
        _pitcher(5015)
        db.session.commit()
        appearances = {910015: [_appearance(5015, game_pk=910015)]}

        _run(FakeLane(appearances))
        _run(FakeLane(appearances), time_budget_seconds=0.0)

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910015).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


# ── Shadow mode ─────────────────────────────────────────────────────────────


def test_shadow_mode_projects_without_writing_anything(app):
    with app.app_context():
        _schedule(910016)
        _pitcher(5016)
        db.session.commit()

        report = _run(
            FakeLane({910016: [_appearance(5016, game_pk=910016)]}),
            mode=game_driven_ingestion.MODE_SHADOW,
        )

        assert report['rows_inserted'] == 1
        assert report['games'][0]['status'] == 'projected'
        assert GameLog.query.count() == 0
        assert GameIngestionWorkItem.query.count() == 0


def test_shadow_mode_projects_an_unchanged_game_as_a_no_op(app):
    with app.app_context():
        _schedule(910017)
        _pitcher(5017)
        db.session.commit()
        appearances = {910017: [_appearance(5017, game_pk=910017)]}

        _run(FakeLane(appearances))
        report = _run(FakeLane(appearances), mode=game_driven_ingestion.MODE_SHADOW)

        assert report['rows_inserted'] == 0
        assert report['rows_updated'] == 0
        assert report['rows_unchanged'] == 1


# ── Observability ───────────────────────────────────────────────────────────


REQUIRED_RUN_FIELDS = (
    'planner_seconds', 'games_discovered', 'newly_final_count',
    'corrected_final_count', 'retry_count', 'games_fetched', 'fetch_seconds',
    'extraction_seconds', 'persistence_seconds', 'checkpoint_seconds',
    'rows_inserted', 'rows_updated', 'rows_unchanged', 'games_completed',
    'games_remaining', 'critical_games_unresolved',
    'best_effort_games_deferred', 'budget_stop_triggered',
)

REQUIRED_GAME_FIELDS = (
    'game_pk', 'represented_date', 'candidate_reason', 'criticality',
    'attempt_number', 'status', 'source_revision', 'appearances_extracted',
    'relief_appearances', 'inserted', 'updated', 'unchanged',
    'elapsed_seconds', 'error_class',
)


def test_every_required_run_and_per_game_counter_is_emitted(app):
    with app.app_context():
        _schedule(910018)
        _pitcher(5018)
        db.session.commit()

        report = _run(FakeLane({910018: [_appearance(5018, game_pk=910018)]}))

        for field in REQUIRED_RUN_FIELDS:
            assert field in report, field
        for field in REQUIRED_GAME_FIELDS:
            assert field in report['games'][0], field


def test_reported_errors_are_safe_classes_only(app):
    with app.app_context():
        _schedule(910019)
        db.session.commit()

        report = _run(FakeLane({910019: []}, fail_games={910019}))

        assert set(report['failure_classes']) <= set(
            game_driven_ingestion.FAILURE_SEMANTICS
        )
        assert report['games'][0]['error_class'] == (
            game_driven_ingestion.ERROR_GAME_FETCH_FAILED
        )
        assert 'fetch failed' not in repr(report)


def test_a_final_game_with_no_pitching_appearances_fails_closed(app):
    with app.app_context():
        _schedule(910020)
        db.session.commit()

        report = _run(FakeLane({910020: []}))

        assert report['games_completed'] == 0
        assert report['failure_classes'] == {
            game_driven_ingestion.ERROR_APPEARANCE_EXTRACTION_FAILED: 1,
        }


def test_every_declared_failure_class_has_declared_semantics():
    declared = {
        value for name, value in vars(game_driven_ingestion).items()
        if name.startswith('ERROR_') and isinstance(value, str)
    }

    assert declared == set(game_driven_ingestion.FAILURE_SEMANTICS)
    for semantics in game_driven_ingestion.FAILURE_SEMANTICS.values():
        assert set(semantics) == {
            'retryable', 'blocks_checkpoint', 'blocks_publication',
        }
        # Generic and specific failures alike fail closed.
        assert semantics['blocks_publication'] is True
