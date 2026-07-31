"""Foundation 3C — exclusive game scope for controlled production validation.

An operator asking for five specific games got all 109: ``--game-pk`` means
"ALSO plan these", not "plan ONLY these". A controlled write is only controlled
if its scope is exact, so exclusive mode enforces set equality and fails before
any MLB request or database write when the planned set is not exactly the
requested set.
"""

from datetime import date

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services import game_driven_ingestion
from services import game_ingestion_planner as planner
from services import sync as sync_service
from tests.game_driven_fixtures import (
    BoxscoreClient,
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


def _eligible_window(count=8, first=960001):
    """A normal date window with several independently eligible final games."""
    game_pks = []
    for index in range(count):
        game_pk = first + index
        _schedule(game_pk, start_hour=13 + index % 6)
        game_pks.append(game_pk)
    return game_pks


def _boxscores(game_pks, start_mlb_id=7500):
    boxscores = {}
    mlb_id = start_mlb_id
    for game_pk in game_pks:
        _pitcher(mlb_id)
        boxscores[game_pk] = boxscore([
            (mlb_id, 'home', pitching_stats()),
        ])
        mlb_id += 1
    return boxscores


def _fingerprint_tables():
    return {
        'game_logs': GameLog.query.count(),
        'pitchers': [
            (row.id, row.mlb_id, row.active, row.roster_status)
            for row in Pitcher.query.order_by(Pitcher.id).all()
        ],
        'work_items': [
            row.to_dict()
            for row in GameIngestionWorkItem.query.order_by(
                GameIngestionWorkItem.id
            ).all()
        ],
        'postgame_markers': PostgameProcessedGame.query.count(),
        'scheduled_games': ScheduledGame.query.count(),
        'sync_failures': SyncFailure.query.count(),
    }


# ═══════════════ Reproduction: additive scope ═══════════════════════════════


def test_the_additive_option_admits_unrelated_eligible_games(app):
    """Documented existing behaviour, and the reason exclusive mode exists."""
    with app.app_context():
        game_pks = _eligible_window()
        db.session.commit()

        plan = planner.plan_game_work(REFERENCE, explicit_game_pks=[game_pks[0]])

        planned = {item.game_pk for item in plan['items']}
        assert game_pks[0] in planned
        # Every other eligible game came along too.
        assert len(planned) == len(game_pks)


# ═══════════════ Exclusive planning ═════════════════════════════════════════


def test_exclusive_mode_plans_exactly_one_requested_game(app):
    with app.app_context():
        game_pks = _eligible_window()
        db.session.commit()

        plan = planner.plan_game_work(REFERENCE, only_game_pks=[game_pks[2]])

        assert [item.game_pk for item in plan['items']] == [game_pks[2]]
        assert plan['execution_scope_mode'] == planner.SCOPE_EXCLUSIVE
        assert plan['execution_scope_exact_match'] is True


def test_exclusive_mode_plans_exactly_five_in_deterministic_order(app):
    with app.app_context():
        game_pks = _eligible_window(count=12, first=960100)
        db.session.commit()
        requested = [game_pks[7], game_pks[1], game_pks[9], game_pks[3], game_pks[5]]

        first = planner.plan_game_work(REFERENCE, only_game_pks=requested)
        second = planner.plan_game_work(REFERENCE, only_game_pks=list(reversed(requested)))

        assert set(item.game_pk for item in first['items']) == set(requested)
        assert len(first['items']) == 5
        assert [item.game_pk for item in first['items']] == [
            item.game_pk for item in second['items']
        ]
        assert first['requested_game_count'] == 5
        assert first['planned_game_count'] == 5


def test_exclusive_mode_excludes_correction_horizon_and_retries(app):
    with app.app_context():
        game_pks = _eligible_window(count=4, first=960200)
        db.session.commit()
        # A completed game inside the correction horizon, and an unresolved
        # retry — both would normally be planned.
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=game_pks[1], represented_date=REFERENCE,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            status=GameIngestionWorkItem.STATUS_COMPLETED,
            attempt_count=1, rows_expected=2, rows_reconciled=2,
            completed_at=date(2026, 7, 29) and None or None,
        ))
        db.session.rollback()
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=game_pks[2], represented_date=REFERENCE,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            attempt_count=1,
        ))
        db.session.commit()

        plan = planner.plan_game_work(REFERENCE, only_game_pks=[game_pks[0]])

        assert [item.game_pk for item in plan['items']] == [game_pks[0]]


def test_a_requested_completed_game_is_classified_as_explicit_repair(app):
    with app.app_context():
        game_pks = _eligible_window(count=2, first=960300)
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=game_pks[0], represented_date=REFERENCE,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            attempt_count=1,
        ))
        db.session.commit()

        plan = planner.plan_game_work(REFERENCE, only_game_pks=[game_pks[0]])

        assert plan['items'][0].candidate_reason == (
            GameIngestionWorkItem.REASON_EXPLICIT_REPAIR
        )


# ═══════════════ Fail before fetch ══════════════════════════════════════════


@pytest.mark.parametrize('setup,label', [
    ('not_final', 'a requested game that is not final'),
    ('missing_authority', 'a requested game with no schedule rows'),
    ('finality_conflict', 'a requested game whose sides disagree'),
])
def test_an_unplannable_requested_game_fails_the_scope_before_any_fetch(
    app, monkeypatch, setup, label,
):
    with app.app_context():
        good = 960400
        bad = 960401
        _schedule(good)
        if setup == 'not_final':
            for team_id, side in ((147, 'home'), (111, 'away')):
                db.session.add(ScheduledGame(
                    team_id=team_id, game_pk=bad, game_date=REFERENCE,
                    home_away=side, game_type='R', status_code='S',
                    status_state=ScheduledGame.STATE_SCHEDULED,
                ))
        elif setup == 'finality_conflict':
            for team_id, side, state in (
                (147, 'home', ScheduledGame.STATE_FINAL),
                (111, 'away', ScheduledGame.STATE_SCHEDULED),
            ):
                db.session.add(ScheduledGame(
                    team_id=team_id, game_pk=bad, game_date=REFERENCE,
                    home_away=side, game_type='R', status_code='F',
                    status_state=state,
                ))
        _pitcher(7900)
        db.session.commit()
        client = BoxscoreClient({good: boxscore([(7900, 'home', pitching_stats())])})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        before = _fingerprint_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[good, bad],
        )
        after = _fingerprint_tables()

        assert report['status'] == 'scope_mismatch', label
        assert report['execution_scope_exact_match'] is False
        assert bad in report['missing_requested_game_pks']
        assert client.calls == [], 'no MLB request may be made'
        assert before == after, 'no write of any kind'
        assert report['games_fetched'] == 0


def test_a_requested_game_is_never_silently_dropped(app, monkeypatch):
    with app.app_context():
        good = 960500
        _schedule(good)
        _pitcher(7910)
        db.session.commit()
        client = BoxscoreClient({good: boxscore([(7910, 'home', pitching_stats())])})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[good, 999999],
        )

        assert report['status'] == 'scope_mismatch'
        assert report['planned_game_pks'] == [good]
        assert report['missing_requested_game_pks'] == [999999]
        assert client.calls == []


def test_an_unexpected_extra_planned_game_is_caught_before_fetch(
    app, monkeypatch,
):
    """Guards the planner itself, not only its inputs."""
    with app.app_context():
        game_pks = _eligible_window(count=3, first=960600)
        _pitcher(7920)
        db.session.commit()
        client = BoxscoreClient({})
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        real_plan = planner.plan_game_work

        def _leaky_plan(reference_date, **kwargs):
            result = real_plan(reference_date, **kwargs)
            # Simulate a planner defect that admits an unrequested game.
            extra = real_plan(reference_date, only_game_pks=[game_pks[2]])
            result['items'] = list(result['items']) + list(extra['items'])
            return result

        monkeypatch.setattr(planner, 'plan_game_work', _leaky_plan)

        before = _fingerprint_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[game_pks[0]],
        )
        after = _fingerprint_tables()

        assert report['status'] == 'scope_mismatch'
        assert report['unexpected_planned_game_pks'] == [game_pks[2]]
        assert client.calls == []
        assert before == after


def test_duplicate_requested_ids_are_deduplicated_and_reported(app, monkeypatch):
    with app.app_context():
        game_pk = 960700
        _schedule(game_pk)
        _pitcher(7930)
        db.session.commit()
        client = BoxscoreClient({
            game_pk: boxscore([(7930, 'home', pitching_stats())]),
        })
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[game_pk, game_pk, game_pk],
        )

        assert report['requested_game_count'] == 1
        assert report['duplicate_requested_count'] == 2
        assert report['execution_scope_exact_match'] is True
        assert client.calls == [game_pk]


def test_an_empty_exclusive_set_is_rejected(app):
    with app.app_context():
        with pytest.raises(ValueError):
            planner.plan_game_work(REFERENCE, only_game_pks=[])


# ═══════════════ Exclusive shadow is read-only ══════════════════════════════


def test_exclusive_shadow_writes_nothing(app, monkeypatch):
    with app.app_context():
        game_pks = _eligible_window(count=3, first=960800)
        boxscores = _boxscores(game_pks, start_mlb_id=7940)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        before = _fingerprint_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=game_pks[:2],
        )
        db.session.rollback()
        after = _fingerprint_tables()

        assert report['execution_scope_exact_match'] is True
        assert report['games_planned'] == 2
        assert before == after


# ═══════════════ Reviewed-fingerprint write authorization ═══════════════════


def test_an_exclusive_write_without_a_reviewed_fingerprint_is_refused(
    app, monkeypatch,
):
    with app.app_context():
        game_pk = 960900
        _schedule(game_pk)
        _pitcher(7950)
        db.session.commit()
        client = BoxscoreClient({
            game_pk: boxscore([(7950, 'home', pitching_stats())]),
        })
        monkeypatch.setattr(sync_service, 'mlb_client', client)

        before = _fingerprint_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            only_game_pks=[game_pk],
        )
        after = _fingerprint_tables()

        assert report['status'] == 'plan_authorization_required'
        assert before == after
        assert GameLog.query.count() == 0


def test_a_wrong_reviewed_fingerprint_refuses_before_any_mutation(
    app, monkeypatch,
):
    with app.app_context():
        game_pk = 960901
        _schedule(game_pk)
        _pitcher(7951)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({
                game_pk: boxscore([(7951, 'home', pitching_stats())]),
            }),
        )

        before = _fingerprint_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            only_game_pks=[game_pk],
            expected_plan_fingerprint='0' * 64,
        )
        after = _fingerprint_tables()

        assert report['status'] == 'plan_fingerprint_mismatch'
        assert report['expected_plan_fingerprint'] == '0' * 64
        assert report['observed_plan_fingerprint'] != '0' * 64
        assert before == after
        assert GameLog.query.count() == 0


def test_the_reviewed_fingerprint_from_shadow_authorizes_the_write(
    app, monkeypatch,
):
    with app.app_context():
        game_pk = 960902
        _schedule(game_pk)
        _pitcher(7952)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({
                game_pk: boxscore([(7952, 'home', pitching_stats())]),
            }),
        )

        shadow = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[game_pk],
        )
        reviewed = shadow['reconciliation_plan_fingerprint']

        write = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            only_game_pks=[game_pk],
            expected_plan_fingerprint=reviewed,
        )

        assert write['status'] == 'complete'
        assert write['rows_inserted'] == shadow['rows_inserted']
        assert write['rows_updated'] == shadow['rows_updated']
        assert write['rows_unchanged'] == shadow['rows_unchanged']
        assert write['reconciliation_plan_fingerprint'] == reviewed
        assert GameLog.query.filter_by(mlb_game_pk=game_pk).count() == 1


def test_source_drift_between_shadow_and_write_refuses_the_write(
    app, monkeypatch,
):
    with app.app_context():
        game_pk = 960903
        _schedule(game_pk)
        _pitcher(7953)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({
                game_pk: boxscore([(7953, 'home', pitching_stats(earned_runs=1))]),
            }),
        )
        shadow = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[game_pk],
        )
        reviewed = shadow['reconciliation_plan_fingerprint']

        # The official evidence moves between review and application.
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({
                game_pk: boxscore([(7953, 'home', pitching_stats(earned_runs=7))]),
            }),
        )
        before = _fingerprint_tables()
        write = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            only_game_pks=[game_pk],
            expected_plan_fingerprint=reviewed,
        )
        after = _fingerprint_tables()

        assert write['status'] == 'plan_fingerprint_mismatch'
        assert before == after
        assert GameLog.query.count() == 0


def test_exclusive_shadow_and_authorized_write_are_exactly_equal(
    app, monkeypatch,
):
    with app.app_context():
        game_pks = _eligible_window(count=5, first=961000)
        boxscores = _boxscores(game_pks, start_mlb_id=7960)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        shadow = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=game_pks,
        )
        write = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
            only_game_pks=game_pks,
            expected_plan_fingerprint=shadow['reconciliation_plan_fingerprint'],
        )

        assert shadow['planned_game_pks'] == write['planned_game_pks']
        assert shadow['changed_fields_counts'] == write['changed_fields_counts']
        assert shadow['mutation_category_counts'] == (
            write['mutation_category_counts']
        )
        assert shadow['rows_inserted'] == write['rows_inserted']
        assert shadow['rows_updated'] == write['rows_updated']
        assert shadow['rows_unchanged'] == write['rows_unchanged']
        assert shadow['rows_blocked'] == write['rows_blocked']

        replay = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=game_pks,
        )
        assert replay['rows_inserted'] == 0
        assert replay['rows_updated'] == 0
        assert replay['rows_blocked'] == 0
        assert replay['rows_unchanged'] == write['rows_expected']


# ═══════════════ Report contract ════════════════════════════════════════════


REQUIRED_SCOPE_FIELDS = (
    'execution_scope_mode', 'requested_game_pks', 'requested_game_count',
    'duplicate_requested_count', 'planned_game_pks', 'planned_game_count',
    'unexpected_planned_game_pks', 'missing_requested_game_pks',
    'execution_scope_exact_match',
)


def test_every_execution_scope_field_is_reported(app, monkeypatch):
    with app.app_context():
        game_pk = 961100
        _schedule(game_pk)
        _pitcher(7970)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({
                game_pk: boxscore([(7970, 'home', pitching_stats())]),
            }),
        )

        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[game_pk],
        )

        for field in REQUIRED_SCOPE_FIELDS:
            assert field in report, field
        assert report['execution_scope_mode'] == planner.SCOPE_EXCLUSIVE


def test_a_normal_window_run_reports_the_window_scope_mode(app, monkeypatch):
    with app.app_context():
        game_pks = _eligible_window(count=2, first=961200)
        boxscores = _boxscores(game_pks, start_mlb_id=7980)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        )

        assert report['execution_scope_mode'] == planner.SCOPE_WINDOW
        assert report['execution_scope_exact_match'] is True
        assert report['requested_game_pks'] == []


# ═══════════════ CLI contract ═══════════════════════════════════════════════


def _cli_error(argv):
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        'game_driven_ingestion_cli',
        str(__import__('pathlib').Path(__file__).resolve().parent.parent
            / 'scripts' / 'game_driven_ingestion.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(SystemExit) as excinfo:
        module.parse_args(argv)
    return excinfo.value.code


@pytest.mark.parametrize('argv', [
    ['--only-game-pk', '1', '--game-pk', '2'],
    ['--only-game-pk', '1', '--max-games', '5'],
    ['--only-game-pk', '1', '--include-backfill'],
    ['--only-game-pk', '1', '--mode', 'write'],
    ['--expected-plan-fingerprint', 'abc'],
])
def test_the_cli_rejects_scope_claims_it_cannot_honour(argv):
    assert _cli_error(argv) == 2


def test_the_cli_accepts_a_valid_exclusive_write():
    import importlib.util
    import pathlib

    spec = importlib.util.spec_from_file_location(
        'game_driven_ingestion_cli',
        str(pathlib.Path(__file__).resolve().parent.parent
            / 'scripts' / 'game_driven_ingestion.py'),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    args = module.parse_args([
        '--mode', 'write', '--only-game-pk', '1', '--only-game-pk', '2',
        '--expected-plan-fingerprint', 'a' * 64,
    ])

    assert args.only_game_pk == [1, 2]
    assert args.expected_plan_fingerprint == 'a' * 64
    assert args.game_pk is None
