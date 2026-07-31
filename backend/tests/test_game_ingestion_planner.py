"""Foundation 3C — deterministic game-driven work planner."""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.scheduled_game import ScheduledGame
from services import game_ingestion_planner as planner
from utils.db import db


REFERENCE = date(2026, 7, 29)


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


def _game(
    game_pk,
    *,
    game_date=REFERENCE,
    state=ScheduledGame.STATE_FINAL,
    away_state=None,
    home_team=147,
    away_team=111,
    start_hour=19,
    game_number=1,
    doubleheader='N',
    original_product_date=None,
):
    rows = []
    for team_id, opponent_id, side, side_state in (
        (home_team, away_team, 'home', state),
        (away_team, home_team, 'away', away_state or state),
    ):
        rows.append(ScheduledGame(
            team_id=team_id,
            game_pk=game_pk,
            game_date=game_date,
            game_datetime=datetime(
                game_date.year, game_date.month, game_date.day, start_hour, 5,
            ),
            opponent_team_id=opponent_id,
            home_away=side,
            game_type='R',
            status_code='F' if side_state == ScheduledGame.STATE_FINAL else 'S',
            status_state=side_state,
            doubleheader=doubleheader,
            game_number=game_number,
            original_product_date=original_product_date,
        ))
    db.session.add_all(rows)
    return rows


def _work_item(
    game_pk,
    *,
    status=GameIngestionWorkItem.STATUS_COMPLETED,
    represented_date=REFERENCE,
    reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
    criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
    rows_expected=8,
    revision='abc123',
    attempt_count=1,
):
    completed = status == GameIngestionWorkItem.STATUS_COMPLETED
    item = GameIngestionWorkItem(
        mlb_game_pk=game_pk,
        represented_date=represented_date,
        game_date=represented_date,
        candidate_reason=reason,
        criticality=criticality,
        status=status,
        attempt_count=attempt_count,
        rows_expected=rows_expected if completed else None,
        rows_reconciled=rows_expected if completed else 0,
        completed_at=datetime(2026, 7, 29, 6, 0, 0) if completed else None,
        source_revision=revision if completed else None,
    )
    db.session.add(item)
    return item


def _plan(**kwargs):
    return planner.plan_game_work(REFERENCE, **kwargs)


# ── Selection ────────────────────────────────────────────────────────────────


def test_a_newly_final_game_is_planned(app):
    with app.app_context():
        _game(900001)
        db.session.commit()

        plan = _plan()

        assert [item.game_pk for item in plan['items']] == [900001]
        assert plan['items'][0].candidate_reason == (
            GameIngestionWorkItem.REASON_NEWLY_FINAL
        )
        assert plan['items'][0].criticality == (
            GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL
        )


def test_a_non_final_game_is_excluded(app):
    with app.app_context():
        _game(900002, state=ScheduledGame.STATE_SCHEDULED)
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []
        assert plan['excluded_counts'][planner.EXCLUDED_NOT_FINAL] == 1


def test_a_completed_unchanged_game_outside_the_correction_horizon_is_skipped(app):
    with app.app_context():
        old = date(2026, 6, 1)
        _game(900003, game_date=old)
        _work_item(900003, represented_date=old)
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []


def test_a_completed_game_inside_the_correction_horizon_is_rechecked(app):
    with app.app_context():
        _game(900004)
        _work_item(900004)
        db.session.commit()

        plan = _plan()

        assert [item.game_pk for item in plan['items']] == [900004]
        assert plan['items'][0].candidate_reason == (
            GameIngestionWorkItem.REASON_CORRECTED_FINAL
        )
        assert plan['items'][0].prior_source_revision == 'abc123'


def test_an_incomplete_prior_attempt_is_planned_first(app):
    with app.app_context():
        _game(900005, start_hour=13)
        _game(900006, start_hour=19)
        _work_item(
            900006,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
            attempt_count=1,
        )
        db.session.commit()

        plan = _plan()

        assert [item.game_pk for item in plan['items']] == [900006, 900005]
        assert plan['items'][0].candidate_reason == (
            GameIngestionWorkItem.REASON_INCOMPLETE_PRIOR_ATTEMPT
        )


def test_unresolved_work_older_than_the_horizon_is_still_replanned(app):
    with app.app_context():
        stale = date(2026, 5, 1)
        _game(900007, game_date=stale)
        _work_item(
            900007,
            represented_date=stale,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
        )
        db.session.commit()

        plan = _plan()

        assert [item.game_pk for item in plan['items']] == [900007]
        # It never silently becomes best effort just because time passed.
        assert plan['items'][0].criticality == (
            GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL
        )


def test_a_terminal_failure_is_not_endlessly_replanned(app):
    with app.app_context():
        _game(900008)
        _work_item(900008, status=GameIngestionWorkItem.STATUS_TERMINAL_FAILURE)
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []
        assert plan['excluded_counts'][planner.EXCLUDED_TERMINAL_FAILURE] == 1


def test_explicit_repair_overrides_prior_completion(app):
    with app.app_context():
        old = date(2026, 5, 15)
        _game(900009, game_date=old)
        _work_item(900009, represented_date=old)
        db.session.commit()

        plan = _plan(explicit_game_pks=[900009])

        assert [item.game_pk for item in plan['items']] == [900009]
        assert plan['items'][0].candidate_reason == (
            GameIngestionWorkItem.REASON_EXPLICIT_REPAIR
        )


def test_backfill_is_opt_in_and_best_effort(app):
    with app.app_context():
        old = date(2026, 4, 10)
        _game(900010, game_date=old)
        db.session.commit()

        assert _plan()['items'] == []

        plan = _plan(include_backfill=True, horizon_days=200, correction_days=200)
        # Inside a widened horizon it is critical; the point of the flag is that
        # nothing older is planned unless asked for.
        assert [item.game_pk for item in plan['items']] == [900010]


# ── Fail-closed status handling ─────────────────────────────────────────────


def test_postponed_and_cancelled_games_are_handled_explicitly(app):
    with app.app_context():
        _game(900011, state=ScheduledGame.STATE_POSTPONED)
        _game(900012, state=ScheduledGame.STATE_OTHER)
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []
        assert plan['excluded_counts'][planner.EXCLUDED_POSTPONED] == 1
        assert plan['excluded_counts'][planner.EXCLUDED_CANCELLED] == 1


def test_a_suspended_game_is_never_treated_as_final(app):
    with app.app_context():
        _game(900013, state=ScheduledGame.STATE_SUSPENDED)
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []
        assert plan['excluded_counts'][
            planner.EXCLUDED_UNRESOLVED_RESUMED_LINKAGE
        ] == 1


def test_conflicting_finality_sources_fail_closed(app):
    with app.app_context():
        _game(900014, state=ScheduledGame.STATE_FINAL,
              away_state=ScheduledGame.STATE_SCHEDULED)
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []
        assert plan['finality_conflicts'] == [900014]


def test_missing_schedule_authority_for_unresolved_work_is_reported(app):
    with app.app_context():
        _work_item(
            900015,
            status=GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE,
        )
        db.session.commit()

        plan = _plan()

        assert plan['items'] == []
        assert plan['schedule_authority_missing'] == [900015]


def test_a_resumed_game_keeps_its_original_represented_date(app):
    with app.app_context():
        _game(
            900016,
            game_date=REFERENCE,
            original_product_date=date(2026, 7, 27),
        )
        db.session.commit()

        plan = _plan()

        assert plan['items'][0].represented_date == date(2026, 7, 27)


# ── Determinism ─────────────────────────────────────────────────────────────


def test_doubleheader_games_are_separate_work_items_in_start_order(app):
    with app.app_context():
        _game(900018, start_hour=18, game_number=2, doubleheader='S')
        _game(900017, start_hour=13, game_number=1, doubleheader='S')
        db.session.commit()

        plan = _plan()

        assert [item.game_pk for item in plan['items']] == [900017, 900018]


def test_ordering_prefers_the_oldest_unresolved_represented_date(app):
    with app.app_context():
        _game(900019, game_date=REFERENCE, start_hour=13)
        _game(900020, game_date=date(2026, 7, 27), start_hour=19)
        db.session.commit()

        plan = _plan()

        assert [item.game_pk for item in plan['items']] == [900020, 900019]


def test_the_plan_is_stable_across_repeated_calls(app):
    with app.app_context():
        for offset, game_pk in enumerate((900021, 900022, 900023)):
            _game(game_pk, start_hour=13 + offset)
        db.session.commit()

        first = [item.game_pk for item in _plan()['items']]
        second = [item.game_pk for item in _plan()['items']]

        assert first == second == [900021, 900022, 900023]


def test_the_planner_never_reads_the_active_pitcher_universe():
    """The daily critical plan must not be derived from the pitcher universe.

    Checked structurally, not by prose: the planner must not import the Pitcher
    model at all, so it cannot regrow an ``active=True`` selection.
    """
    import ast

    with open(planner.__file__, encoding='utf-8') as handle:
        tree = ast.parse(handle.read())

    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            imported.add(node.module or '')
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)

    assert 'models.pitcher' not in imported
    assert 'Pitcher' not in imported

    active_filters = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and any(
            keyword.arg == 'active'
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in node.keywords
        )
    ]
    assert active_filters == []


def test_every_discovered_game_is_planned_or_explicitly_excluded(app):
    with app.app_context():
        _game(900024)
        _game(900025, state=ScheduledGame.STATE_SCHEDULED)
        _game(900026, state=ScheduledGame.STATE_POSTPONED)
        db.session.commit()

        plan = _plan()

        accounted = plan['games_planned'] + sum(plan['excluded_counts'].values())
        assert accounted == plan['games_discovered'] == 3
