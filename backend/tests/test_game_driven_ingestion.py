"""Foundation 3C — game-driven ingestion runner, checkpoint, and resume.

These tests drive the REAL canonical path: the real box-score parser, the real
reconciliation planner, and the real GameLog writer. Only the MLB client is
stubbed. A hand-rolled persist would be a second reconciliation implementation,
which is exactly the class of drift this suite exists to prevent.
"""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from services import sync as sync_service
from tests.game_driven_fixtures import (
    AWAY_TEAM,
    BoxscoreClient,
    HOME_TEAM,
    REFERENCE,
    boxscore,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
from utils.db import db


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


@pytest.fixture
def stub_client(monkeypatch):
    """Install a box-score client; reconciliation stays entirely canonical."""

    def _install(boxscores_by_game, *, fail_games=()):
        client = BoxscoreClient(boxscores_by_game, fail_games=fail_games)
        monkeypatch.setattr(sync_service, 'mlb_client', client)
        return client

    return _install


def _run(mode=game_driven_ingestion.MODE_WRITE, **kwargs):
    return game_driven_ingestion.run_game_driven_ingestion(
        REFERENCE, mode=mode, **kwargs,
    )


def _one_reliever(game_pk, mlb_id, **stat_overrides):
    return {game_pk: boxscore([(mlb_id, 'home', pitching_stats(**stat_overrides))])}


# ── Mode gating ──────────────────────────────────────────────────────────────


def test_the_lane_is_off_by_default(app, monkeypatch):
    monkeypatch.delenv(game_driven_ingestion.MODE_ENV_VAR, raising=False)

    assert game_driven_ingestion.ingestion_mode() == game_driven_ingestion.MODE_OFF
    assert game_driven_ingestion.enabled() is False
    assert game_driven_ingestion.publication_authoritative() is False


def test_an_unrecognised_mode_falls_back_to_off(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'sort-of-on')

    assert game_driven_ingestion.ingestion_mode() == game_driven_ingestion.MODE_OFF


def test_off_mode_does_no_work(app, stub_client):
    with app.app_context():
        _schedule(910001)
        _pitcher(5000)
        db.session.commit()
        client = stub_client(_one_reliever(910001, 5000))

        report = _run(mode=game_driven_ingestion.MODE_OFF)

        assert report['status'] == 'disabled'
        assert client.calls == []


# ── Persistence ─────────────────────────────────────────────────────────────


def test_first_processing_inserts_rows_and_completes_the_work_item(app, stub_client):
    with app.app_context():
        _schedule(910002)
        _pitcher(5001)
        _pitcher(5002)
        db.session.commit()
        stub_client({910002: boxscore([
            (5001, 'home', pitching_stats(innings='6.0', games_started=1)),
            (5002, 'home', pitching_stats(innings='1.0')),
        ])})

        report = _run()

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


def test_replaying_an_unchanged_game_creates_no_duplicates_and_no_changes(
    app, stub_client,
):
    with app.app_context():
        _schedule(910003)
        _pitcher(5003)
        db.session.commit()
        stub_client(_one_reliever(910003, 5003))

        first = _run()
        second = _run()

        assert first['rows_inserted'] == 1
        assert second['rows_inserted'] == 0
        assert second['rows_updated'] == 0
        assert second['rows_unchanged'] == 1
        assert second['corrections_applied'] == 0
        assert GameLog.query.filter_by(mlb_game_pk=910003).count() == 1


def test_a_corrected_replay_updates_governed_fields_and_records_the_correction(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(910004)
        _pitcher(5004)
        db.session.commit()

        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_one_reliever(910004, 5004, earned_runs=1)),
        )
        _run()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_one_reliever(910004, 5004, earned_runs=3)),
        )
        report = _run()

        assert report['rows_updated'] == 1
        assert report['corrections_applied'] == 1
        assert report['statistical_corrections'] == 1
        assert 'earned_runs' in report['changed_fields_counts']
        assert GameLog.query.filter_by(mlb_game_pk=910004).count() == 1
        row = GameLog.query.filter_by(mlb_game_pk=910004).one()
        assert row.earned_runs == 3

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910004).one()
        assert item.correction_count == 1
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


def test_the_canonical_uniqueness_makes_a_duplicate_row_impossible(app):
    with app.app_context():
        _schedule(910005)
        row_pitcher = _pitcher(5005)
        db.session.commit()
        db.session.add(GameLog(
            pitcher_id=row_pitcher.id, mlb_game_pk=910005, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3,
        ))
        db.session.commit()

        with pytest.raises(Exception):
            db.session.add(GameLog(
                pitcher_id=row_pitcher.id, mlb_game_pk=910005,
                game_date=REFERENCE, innings_pitched=1.0,
                innings_pitched_outs=3,
            ))
            db.session.commit()
        db.session.rollback()


def test_a_game_is_not_completed_when_its_writes_roll_back(app, monkeypatch):
    with app.app_context():
        _schedule(910006)
        _pitcher(5006)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_one_reliever(910006, 5006)),
        )

        original = sync_service.safe_recompute_team_game_pitching_splits_for_game

        def _explode(*args, **kwargs):
            raise RuntimeError('failed after the appearance writes flushed')

        monkeypatch.setattr(
            game_driven_ingestion, '_verify_game_completeness', _explode,
        )

        report = _run()

        assert original is not None
        assert report['games_completed'] == 0
        assert report['games_failed'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=910006).count() == 0
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910006).one()
        assert item.status != GameIngestionWorkItem.STATUS_COMPLETED
        assert item.completed_at is None


def test_an_unsafe_correction_blocks_completion(app, monkeypatch):
    with app.app_context():
        _schedule(910007)
        _pitcher(5007)
        db.session.commit()

        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_one_reliever(910007, 5007)),
        )
        _run()

        # The official line comes back missing a required correction key, so
        # the existing row's correction is not governed and must be refused.
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(_one_reliever(
                910007, 5007, earned_runs=4, complete=False,
            )),
        )
        report = _run()

        assert report['games_completed'] == 0
        assert report['rows_blocked'] == 1
        assert report['failure_classes'] == {
            game_driven_ingestion.ERROR_CORRECTION_CONFLICT: 1,
        }
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910007).one()
        assert item.error_class == game_driven_ingestion.ERROR_CORRECTION_CONFLICT


# ── Checkpoint and resume ───────────────────────────────────────────────────


def test_a_completed_game_stays_completed_across_runs(app, stub_client):
    with app.app_context():
        _schedule(910008)
        _pitcher(5008)
        db.session.commit()
        stub_client(_one_reliever(910008, 5008))

        _run()
        _run()

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910008).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


def test_a_failed_game_resumes_on_the_next_run(app, monkeypatch):
    with app.app_context():
        _schedule(910009)
        _pitcher(5009)
        db.session.commit()
        boxscores = _one_reliever(910009, 5009)

        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(boxscores, fail_games={910009}),
        )
        failed = _run()
        assert failed['games_failed'] == 1
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910009).one()
        assert item.status == GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE

        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )
        recovered = _run()

        assert recovered['games_completed'] == 1
        assert recovered['retry_count'] == 1
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910009).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


def test_repeated_failure_becomes_terminal_rather_than_looping_forever(
    app, stub_client,
):
    with app.app_context():
        _schedule(910010)
        db.session.commit()
        stub_client({910010: {}}, fail_games={910010})

        for _ in range(game_driven_ingestion.RETRY_LIMIT):
            _run()

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910010).one()
        assert item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE
        assert item.attempt_count >= game_driven_ingestion.RETRY_LIMIT


def test_budget_exhaustion_preserves_remaining_work_and_never_dead_letters_it(
    app, stub_client,
):
    with app.app_context():
        _schedule(910011, start_hour=13)
        _schedule(910012, start_hour=19)
        _pitcher(5011)
        db.session.commit()
        boxscores = dict(_one_reliever(910011, 5011))
        boxscores.update(_one_reliever(910012, 5011))
        stub_client(boxscores)

        report = _run(time_budget_seconds=0.0)

        assert report['budget_stop_triggered'] is True
        assert report['status'] == 'incomplete'
        assert report['budget_stop']['critical_games_remaining'] == 2
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

        resumed_report = _run()
        assert resumed_report['retry_count'] == 2
        assert resumed_report['games_completed'] == 2


def test_the_next_run_starts_with_unresolved_critical_games(app, monkeypatch):
    with app.app_context():
        _schedule(910013, start_hour=13)
        _schedule(910014, start_hour=19)
        _pitcher(5013)
        db.session.commit()
        boxscores = dict(_one_reliever(910013, 5013))
        boxscores.update(_one_reliever(910014, 5013))

        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient(boxscores, fail_games={910014}),
        )
        first = _run()
        assert first['games_completed'] == 1
        assert first['games_failed'] == 1

        second = BoxscoreClient(boxscores)
        monkeypatch.setattr(sync_service, 'mlb_client', second)
        _run()

        # The completed game is still re-checked for corrections, but the
        # unresolved one is fetched FIRST — the next run never restarts from
        # the beginning of the window.
        assert second.calls[0] == 910014


def test_a_budget_stop_never_demotes_an_already_completed_game(app, stub_client):
    with app.app_context():
        _schedule(910015)
        _pitcher(5015)
        db.session.commit()
        stub_client(_one_reliever(910015, 5015))

        _run()
        _run(time_budget_seconds=0.0)

        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=910015).one()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED


# ── Shadow mode ─────────────────────────────────────────────────────────────


def test_shadow_mode_projects_without_writing_anything(app, stub_client):
    with app.app_context():
        _schedule(910016)
        _pitcher(5016)
        db.session.commit()
        stub_client(_one_reliever(910016, 5016))

        report = _run(mode=game_driven_ingestion.MODE_SHADOW)

        assert report['rows_inserted'] == 1
        assert report['games'][0]['status'] == 'projected'
        assert GameLog.query.count() == 0
        assert GameIngestionWorkItem.query.count() == 0


def test_shadow_mode_projects_an_unchanged_game_as_a_no_op(app, stub_client):
    with app.app_context():
        _schedule(910017)
        _pitcher(5017)
        db.session.commit()
        stub_client(_one_reliever(910017, 5017))

        _run()
        report = _run(mode=game_driven_ingestion.MODE_SHADOW)

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
    'rows_blocked', 'changed_fields_counts', 'mutation_category_counts',
    'statistical_corrections', 'authority_reconciliations',
    'provenance_only_updates', 'parity_contract_version',
    'reconciliation_plan_version', 'reconciliation_plan_fingerprint',
)

REQUIRED_GAME_FIELDS = (
    'game_pk', 'represented_date', 'candidate_reason', 'criticality',
    'attempt_number', 'status', 'source_revision', 'appearances_extracted',
    'relief_appearances', 'inserted', 'updated', 'unchanged',
    'elapsed_seconds', 'error_class', 'blocked', 'changed_fields_counts',
    'mutation_category_counts', 'rows',
)


def test_every_required_run_and_per_game_counter_is_emitted(app, stub_client):
    with app.app_context():
        _schedule(910018)
        _pitcher(5018)
        db.session.commit()
        stub_client(_one_reliever(910018, 5018))

        report = _run()

        for field in REQUIRED_RUN_FIELDS:
            assert field in report, field
        for field in REQUIRED_GAME_FIELDS:
            assert field in report['games'][0], field


def test_reported_errors_are_safe_classes_only(app, stub_client):
    with app.app_context():
        _schedule(910019)
        db.session.commit()
        stub_client({910019: {}}, fail_games={910019})

        report = _run()

        assert set(report['failure_classes']) <= set(
            game_driven_ingestion.FAILURE_SEMANTICS
        )
        assert report['games'][0]['error_class'] == (
            game_driven_ingestion.ERROR_GAME_FETCH_FAILED
        )
        assert 'boxscore fetch failed' not in repr(report)


def test_a_final_game_with_no_pitching_appearances_fails_closed(app, stub_client):
    with app.app_context():
        _schedule(910020)
        db.session.commit()
        stub_client({910020: {'teams': {}}})

        report = _run()

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


# ── Per-game transaction boundary ────────────────────────────────────────────
# Extracted from the temporary Foundation 3C R4/R6 rollout suites at Stage E so
# the guarantee outlives the workflows that first exercised it. The canonical
# writer commits ONCE PER GAME. Multi-game atomicity does not exist, and a
# governed run must never present a partial result as a whole one.


def test_a_failure_partway_leaves_earlier_games_durably_committed(
    app, monkeypatch, stub_client,
):
    """Game 3 fails; games 1 and 2 stay complete. This is by design.

    A rollout that assumed all-or-nothing would try to "repair" the survivors.
    They are correct, durable work and must be left alone.
    """
    with app.app_context():
        games = (970101, 970102, 970103, 970104)
        boxscores = {}
        for index, game_pk in enumerate(games):
            _schedule(game_pk)
            boxscores.update(_one_reliever(game_pk, 9700 + index))
        db.session.commit()
        stub_client(boxscores)

        real_process = game_driven_ingestion._process_one_game
        calls = {'n': 0}

        def failing(item, **kwargs):
            calls['n'] += 1
            if calls['n'] == 3:
                raise RuntimeError('injected failure on the third game')
            return real_process(item, **kwargs)

        monkeypatch.setattr(game_driven_ingestion, '_process_one_game', failing)
        with pytest.raises(RuntimeError):
            _run()
        db.session.rollback()

        completed = {
            item.mlb_game_pk for item in GameIngestionWorkItem.query.filter(
                GameIngestionWorkItem.status
                == GameIngestionWorkItem.STATUS_COMPLETED
            ).all()
        }
        # Exactly the two games that committed before the failure.
        assert len(completed) == 2
        assert completed <= set(games)
        # The failed game left no completed checkpoint behind.
        assert games[2] not in completed


def test_a_partial_run_never_reports_itself_as_complete(app, stub_client):
    """games_completed must not silently equal games_attempted."""
    with app.app_context():
        games = (970201, 970202, 970203)
        boxscores = {}
        for index, game_pk in enumerate(games):
            _schedule(game_pk)
            boxscores.update(_one_reliever(game_pk, 9720 + index))
        db.session.commit()
        stub_client(boxscores, fail_games=(games[1],))

        report = _run()

        assert report['games_attempted'] == 3
        assert report['games_completed'] == 2
        assert report['games_failed'] == 1
        assert report['games_completed'] != report['games_attempted']
        assert report['failure_classes']
        # The survivors are durable; the failure is visible rather than absorbed.
        assert GameIngestionWorkItem.query.filter(
            GameIngestionWorkItem.status
            == GameIngestionWorkItem.STATUS_COMPLETED
        ).count() == 2


def test_a_completed_game_replays_without_mutating_baseball_data(
    app, stub_client,
):
    """The bootstrap's core claim: replaying settled work changes nothing."""
    with app.app_context():
        game_pk = 970301
        _schedule(game_pk)
        db.session.commit()
        stub_client(_one_reliever(game_pk, 97030))

        _run()
        stored = [
            (row.mlb_game_pk, row.pitcher_id, row.innings_pitched_outs,
             row.earned_runs, row.strikeouts)
            for row in GameLog.query.order_by(GameLog.id).all()
        ]

        replay = _run(mode=game_driven_ingestion.MODE_SHADOW)
        db.session.rollback()

        assert replay['rows_inserted'] == 0
        assert replay['rows_updated'] == 0
        assert replay['rows_blocked'] == 0
        assert replay['complete_mutation_count'] == 0
        assert [
            (row.mlb_game_pk, row.pitcher_id, row.innings_pitched_outs,
             row.earned_runs, row.strikeouts)
            for row in GameLog.query.order_by(GameLog.id).all()
        ] == stored


# ── Permanent runtime boundary ───────────────────────────────────────────────
# Relocated from the temporary Foundation 3C Stage E suite at E2, before that
# suite was deleted. These assertions outlive the rollout: they guard the
# production components a future cleanup could delete "because the bootstrap is
# finished". The rollout is finished; the runtime is not.
#
# Deliberately NOT relocated: Stage E workflow filenames, artifact names, the
# 109 July 2026 game identifiers, temporary scope digests, workflow step order,
# artifact retention, and summary formatting. Those described a one-time
# rollout, not production behaviour.

PERMANENT_RUNTIME_FILES = (
    'backend/scripts/game_driven_ingestion.py',
    'backend/services/game_driven_ingestion.py',
    'backend/services/game_ingestion_planner.py',
    'backend/services/game_ingestion_completeness.py',
    'backend/services/game_log_reconciliation.py',
    'backend/services/pitcher_identity_reconciliation.py',
    'backend/models/game_ingestion_work_item.py',
)

PERMANENT_REGRESSION_FILES = (
    'backend/tests/test_canonical_innings_reconciliation.py',
    'backend/tests/test_exclusive_game_scope.py',
    'backend/tests/test_game_driven_ingestion.py',
    'backend/tests/test_game_ingestion_completeness.py',
    'backend/tests/test_pitcher_identity_authority.py',
    'backend/tests/test_publication_criticality.py',
    'backend/tests/test_shadow_write_reconciliation_parity.py',
)

_REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('path', PERMANENT_RUNTIME_FILES)
def test_a_permanent_runtime_component_is_present(path):
    """Bootstrap completion is not a reason to delete production behaviour."""
    assert (_REPO_ROOT / path).exists(), path


@pytest.mark.parametrize('path', PERMANENT_REGRESSION_FILES)
def test_a_permanent_regression_suite_is_present(path):
    assert (_REPO_ROOT / path).exists(), path


def test_the_unresolved_first_write_forensic_inspector_is_present():
    """The first-write provenance investigation is still open.

    Kept here rather than in a rollout suite precisely because the rollout
    suites are gone: this tooling belongs to a separate, unfinished question.
    """
    assert (
        _REPO_ROOT / 'backend' / 'scripts'
        / 'inspect_first_write_pitcher_identity.py'
    ).exists()


def test_the_permanent_runtime_contract_is_still_exposed():
    """Presence is not enough — the authority itself must still be there."""
    assert reconciliation.RECONCILIATION_PLAN_VERSION == '3'
    assert reconciliation.PARITY_CONTRACT_VERSION == '4'
    assert reconciliation.INNINGS_SEMANTICS_VERSION == '2'
    assert reconciliation.COMPLETE_PLAN_VERSION == '1'
    assert pitcher_identity.IDENTITY_PLAN_VERSION == '1'

    # The complete-plan fingerprint and its identity component.
    assert callable(reconciliation.plan_fingerprint)
    assert callable(pitcher_identity.fingerprint_component)

    # The run entry point and the governed modes.
    assert callable(game_driven_ingestion.run_game_driven_ingestion)
    assert game_driven_ingestion.MODE_OFF == 'off'
    assert game_driven_ingestion.MODE_SHADOW == 'shadow'
    assert game_driven_ingestion.MODE_WRITE == 'write'
    assert game_driven_ingestion.MODE_AUTHORITATIVE == 'authoritative'


def test_the_identity_decision_participates_in_the_complete_fingerprint():
    """Contract-4 coverage by value, asserted at the plan level.

    Two identity decisions that differ only in the values they would write must
    not share a fingerprint. This is the PR #576 repair, held here so it cannot
    be lost with a rollout suite.
    """
    base = {
        'game_pk': 970901, 'pitcher_mlb_id': 97090,
        'action': reconciliation.ACTION_UNCHANGED,
    }
    one = dict(base, pitcher_identity_action='create_minimal_identity',
               pitcher_identity_mutation_digest='digest-one')
    two = dict(base, pitcher_identity_action='create_minimal_identity',
               pitcher_identity_mutation_digest='digest-two')
    assert reconciliation.plan_fingerprint([one]) != (
        reconciliation.plan_fingerprint([two])
    )


def test_the_lane_default_is_off_without_any_environment_configuration(
    monkeypatch,
):
    """Removing the rollout workflows cannot have enabled anything."""
    monkeypatch.delenv(game_driven_ingestion.MODE_ENV_VAR, raising=False)
    assert game_driven_ingestion.ingestion_mode() == 'off'
    assert game_driven_ingestion.enabled() is False
    assert game_driven_ingestion.writes_enabled() is False
