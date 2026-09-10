"""Postgame shadow: exact-cycle scope, safe diagnostics, and the rollback.

The first automated postgame shadow cycle failed safely. It planned 112 games
and completed 98 before exhausting its 150-second allocation, leaving 14
remaining. The established postgame sync succeeded, publication was verified,
and shadow wrote nothing.

It was not slow. It was looking at the wrong set: the lane was handed a
reference date and no scope, so the canonical planner did what it is built to
do for a DAILY cycle and swept the whole rolling correction horizon — while the
postgame refresh had already resolved the only set that cycle governs.

These tests own the repair: the exact-cycle scope, the diagnostics that would
have named the one discrepancy in the first place, and the temporary rollback.
"""

from datetime import date, datetime
from types import SimpleNamespace

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
from services import game_driven_ingestion
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from services import sync as sync_service
from services import sync_metadata
from utils.db import db


SLATE = date(2026, 6, 20)
PRIOR_SLATE = date(2026, 6, 18)
GAME_PK = 940001


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(
        sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 0,
    )

    def fake_complete(sync_run_id, **kwargs):
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            new_logs_added=kwargs.get('new_logs_added', 0),
            pitchers_updated=kwargs.get('pitchers_updated', 0),
            errors=kwargs.get('errors', 0),
            api_calls_made=kwargs.get('api_calls_made', 0),
            retries_used=kwargs.get('retries_used', 0),
            error_message=kwargs.get('error_message'),
            source=kwargs.get('source', 'test'),
            started_at=kwargs.get('started_at'),
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


# ── Fixtures ────────────────────────────────────────────────────────────────


def _game(game_pk=GAME_PK, slate=SLATE):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': slate.isoformat(),
        'status': {
            'statusCode': 'F', 'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club'}},
            'away': {'team': {'id': 2, 'name': 'Away Club'}},
        },
    }


def _marker(game_pk, *, status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            slate=SLATE):
    marker = PostgameProcessedGame(
        mlb_game_pk=game_pk,
        game_date=slate,
        game_type='R',
        processing_status=status,
        logs_added=2,
        pitchers_touched=2,
    )
    db.session.add(marker)
    db.session.commit()
    return marker


def _scope(games, slates=None):
    slate_by_game_pk = slates or {
        (g['gamePk'] if isinstance(g, dict) else g): SLATE for g in games
    }
    return sync_service._postgame_game_driven_scope(games, slate_by_game_pk)


# ── The defect: scope came from the correction horizon, not the cycle ───────


def test_the_scope_is_the_cycle_completed_games_not_a_date_window(app):
    """The one-line statement of what went wrong in production."""
    with app.app_context():
        for pk in (940001, 940002, 940003):
            _marker(pk)

        scope = _scope([_game(940001), _game(940002), _game(940003)])

        assert scope['scope_source'] == sync_service.POSTGAME_SCOPE_SOURCE
        assert scope['requested_game_pks'] == [940001, 940002, 940003]
        assert scope['cycle_game_count'] == 3


def test_one_completed_game_produces_a_one_game_scope(app):
    with app.app_context():
        _marker(GAME_PK)
        scope = _scope([_game()])
        assert scope['requested_game_pks'] == [GAME_PK]
        assert scope['requested_game_count'] == 1


def test_the_scope_order_is_deterministic(app):
    with app.app_context():
        for pk in (940009, 940002, 940005):
            _marker(pk)
        first = _scope([_game(940009), _game(940002), _game(940005)])
        second = _scope([_game(940002), _game(940005), _game(940009)])
        assert first['requested_game_pks'] == second['requested_game_pks']
        assert first['requested_game_pks'] == [940002, 940005, 940009]


def test_duplicate_game_pks_normalize(app):
    with app.app_context():
        _marker(GAME_PK)
        scope = _scope([_game(), _game(), _game()])
        assert scope['requested_game_pks'] == [GAME_PK]
        assert scope['cycle_game_count'] == 1


def test_a_game_outside_the_cycle_is_simply_not_in_it(app):
    """Scope is what the cycle resolved. Nothing else can enter it."""
    with app.app_context():
        _marker(940001)
        _marker(999999, slate=PRIOR_SLATE)  # governed by some other cycle

        scope = _scope([_game(940001)])

        assert scope['requested_game_pks'] == [940001]
        assert 999999 not in scope['requested_game_pks']


def test_an_unrelated_prior_corrected_final_game_is_excluded(app):
    """The 7-day fan-out class, stated as a test."""
    with app.app_context():
        _marker(940001)
        for pk in range(950000, 950111):  # a horizon's worth of older games
            _marker(pk, slate=PRIOR_SLATE)

        scope = _scope([_game(940001)])

        assert scope['requested_game_count'] == 1
        assert scope['requested_game_pks'] == [940001]


# ── Cycle accounting: only what the writer actually finished ────────────────


def test_an_already_complete_cycle_game_is_in_scope(app):
    with app.app_context():
        _marker(GAME_PK)
        scope = _scope([_game()])
        assert scope['requested_game_pks'] == [GAME_PK]


def test_a_retryable_incomplete_game_is_excluded_with_a_named_reason(app):
    """The writer has not finished it, so zero projection is not expected."""
    with app.app_context():
        _marker(GAME_PK, status=PostgameProcessedGame.STATUS_INCOMPLETE)
        scope = _scope([_game()])

        assert scope['requested_game_pks'] == []
        assert scope['excluded_game_pks'] == [{
            'game_pk': GAME_PK,
            'reason': sync_service.POSTGAME_SCOPE_EXCLUDED_INCOMPLETE,
        }]


def test_a_game_with_no_marker_is_excluded_with_a_named_reason(app):
    with app.app_context():
        scope = _scope([_game()])
        assert scope['requested_game_pks'] == []
        assert scope['excluded_game_pks'][0]['reason'] == (
            sync_service.POSTGAME_SCOPE_EXCLUDED_UNPROCESSED
        )


def test_every_excluded_game_carries_a_reason(app):
    with app.app_context():
        _marker(940001)
        _marker(940002, status=PostgameProcessedGame.STATUS_INCOMPLETE)

        scope = _scope([_game(940001), _game(940002), _game(940003)])

        assert scope['requested_game_pks'] == [940001]
        reasons = {entry['game_pk']: entry['reason']
                   for entry in scope['excluded_game_pks']}
        assert set(reasons) == {940002, 940003}
        assert all(reason for reason in reasons.values())


def test_the_excluded_reason_counts_reconcile(app):
    with app.app_context():
        _marker(940001)
        _marker(940002, status=PostgameProcessedGame.STATUS_INCOMPLETE)

        scope = _scope([_game(940001), _game(940002), _game(940003)])

        assert sum(scope['excluded_reason_counts'].values()) == len(
            scope['excluded_game_pks']
        )
        assert (
            scope['requested_game_count'] + len(scope['excluded_game_pks'])
            == scope['cycle_game_count']
        )


def test_an_empty_cycle_produces_an_empty_scope(app):
    with app.app_context():
        scope = _scope([])
        assert scope['requested_game_pks'] == []
        assert scope['cycle_game_count'] == 0


def test_the_scope_records_the_cycle_slate_dates(app):
    with app.app_context():
        _marker(940001)
        _marker(940002, slate=PRIOR_SLATE)
        scope = sync_service._postgame_game_driven_scope(
            [_game(940001), _game(940002, PRIOR_SLATE)],
            {940001: SLATE, 940002: PRIOR_SLATE},
        )
        assert scope['slate_dates'] == [
            PRIOR_SLATE.isoformat(), SLATE.isoformat(),
        ]


# ── The scope reaches the lane as exclusive scope ───────────────────────────


def test_the_lane_receives_the_exact_scope_not_a_date_window(app, monkeypatch):
    calls = []

    def spy(reference_date, **kwargs):
        calls.append(kwargs)
        return {
            'status': 'complete', 'games': [], 'games_planned': 0,
            'elapsed_seconds': 1.0, 'remaining_budget_seconds': 1.0,
            'execution_effects': game_driven_ingestion._empty_execution_effects(
                'shadow'
            ),
        }

    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion', spy,
    )
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    status = {}
    with app.app_context():
        sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget={'ingestion_budget_seconds': 600.0,
                            'stage_budget_cap_seconds': 600.0},
            sync_run_id=None,
            status=status,
            stage_timings={},
            run_logger=sync_service.logger,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            write_modes_supported=False,
            only_game_pks=[940001, 940002],
            scope_summary={'scope_source': 'test'},
        )

    assert calls[0]['only_game_pks'] == [940001, 940002]


def test_the_daily_cycle_still_plans_its_correction_horizon(app, monkeypatch):
    """Exclusive scope is a postgame repair, not a global narrowing."""
    calls = []

    def spy(reference_date, **kwargs):
        calls.append(kwargs)
        return {
            'status': 'complete', 'games': [], 'games_planned': 0,
            'elapsed_seconds': 1.0, 'remaining_budget_seconds': 1.0,
            'execution_effects': game_driven_ingestion._empty_execution_effects(
                'shadow'
            ),
        }

    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion', spy,
    )
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget={'ingestion_budget_seconds': 600.0},
            sync_run_id=None,
            status={},
            stage_timings={},
            run_logger=sync_service.logger,
        )

    assert calls[0]['only_game_pks'] is None


def test_the_scope_costs_no_extra_mlb_request():
    """It is derived from state the cycle already holds."""
    import inspect

    source = inspect.getsource(sync_service._postgame_game_driven_scope)
    for forbidden in ('mlb_client', 'get_schedule', 'get_game_boxscore',
                      'plan_game_work', 'requests.'):
        assert forbidden not in source


def test_the_scope_runs_no_second_planning_pass():
    import inspect

    source = inspect.getsource(sync_service._postgame_game_driven_scope)
    assert 'planner' not in source
    assert 'run_game_driven_ingestion' not in source


def test_the_scope_is_resolved_after_the_writer(app):
    """Eligibility depends on what the writer finished, so order matters."""
    import pathlib

    text = pathlib.Path(sync_service.__file__).read_text(encoding='utf-8')
    writer_at = text.index('for game in unprocessed_games:')
    scope_at = text.index('postgame_scope = _postgame_game_driven_scope(')
    assert writer_at < scope_at


# ── Safe difference diagnostics ─────────────────────────────────────────────


def _pitcher(mlb_id):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'Arm {mlb_id}', team_id=1,
        team_abbreviation='HME', position='P', active=True,
        roster_status='ACTIVE',
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _values(*, outs=3, earned_runs=0, strikeouts=1, **overrides):
    values = {
        'mlb_game_pk': GAME_PK,
        'game_date': SLATE,
        'game_type': 'R',
        'innings_pitched_outs': outs,
        'innings_pitched': round(outs / 3.0, 10),
        'pitches_thrown': 14,
        'strikes': 9,
        'earned_runs': earned_runs,
        'runs_allowed': earned_runs,
        'hits_allowed': 0,
        'walks': 0,
        'strikeouts': strikeouts,
        'home_runs_allowed': 0,
        'games_started': 0,
    }
    values.update(overrides)
    return values


def _stats(**overrides):
    stats = {
        'inningsPitched': '1.0', 'strikes': 9, 'hits': 0, 'runs': 0,
        'earnedRuns': 0, 'baseOnBalls': 0, 'strikeOuts': 1, 'homeRuns': 0,
    }
    stats.update(overrides)
    return stats


def _stored(pitcher, **overrides):
    row = GameLog(pitcher_id=pitcher.id, **_values(**overrides))
    db.session.add(row)
    db.session.commit()
    return row


def _plan(existing, values, stats, pitcher):
    return reconciliation.plan_row(
        existing=existing, values=values, stats=stats, game_pk=GAME_PK,
        pitcher_mlb_id=pitcher.mlb_id, local_pitcher_id=pitcher.id,
        identity_plan={'action': pitcher_identity.ACTION_UNCHANGED},
    )


def test_a_projected_update_names_its_changed_field(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        plan = _plan(
            stored, _values(earned_runs=2), _stats(earnedRuns=2, runs=2), pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert row['game_pk'] == GAME_PK
        assert row['pitcher_mlb_id'] == 8001
        assert row['action'] == reconciliation.ACTION_UPDATE
        assert 'earned_runs' in row['changed_fields']


def test_a_projected_update_classifies_the_difference(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        plan = _plan(
            stored, _values(earned_runs=2), _stats(earnedRuns=2, runs=2), pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert reconciliation.DIFFERENCE_STATISTICAL in (
            row['difference_classifications']
        )


def test_an_outs_difference_is_classified_as_a_canonical_outs_correction(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, outs=3)
        plan = _plan(
            stored, _values(outs=6), _stats(inningsPitched='2.0'), pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert reconciliation.DIFFERENCE_CANONICAL_OUTS in (
            row['difference_classifications']
        )


def test_an_insert_is_classified_as_a_missing_appearance_row(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        plan = _plan(None, _values(), _stats(), pitcher)
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert reconciliation.DIFFERENCE_INSERT in (
            row['difference_classifications']
        )


def test_every_classification_is_in_the_closed_vocabulary(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0, outs=3)
        plan = _plan(
            stored, _values(earned_runs=2, outs=6),
            _stats(earnedRuns=2, runs=2, inningsPitched='2.0'), pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        for name in row['difference_classifications']:
            assert name in reconciliation.DIFFERENCE_CLASSIFICATIONS


def test_the_diagnostic_carries_both_digests(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        plan = _plan(
            stored, _values(earned_runs=2), _stats(earnedRuns=2, runs=2), pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert row['target_state_digest']
        assert row['stored_state_digest']
        assert row['target_state_digest'] != row['stored_state_digest'], (
            'a real difference must produce different digests'
        )


def test_an_unchanged_row_has_matching_empty_digests(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher)
        plan = _plan(stored, _values(), _stats(), pitcher)
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert row['action'] == reconciliation.ACTION_UNCHANGED
        assert row['target_state_digest'] == row['stored_state_digest']


def test_the_diagnostic_contains_no_values(app):
    """Field names and digests travel. The values behind them never do."""
    import json

    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0, strikeouts=1)
        plan = _plan(
            stored,
            _values(earned_runs=7, strikeouts=13),
            _stats(earnedRuns=7, runs=7, strikeOuts=13),
            pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]
        body = json.dumps(row, sort_keys=True, default=str)

        assert 'earned_runs' in body          # the name is reported
        assert '"before"' not in body
        assert '"after"' not in body
        assert '"field_changes"' not in body
        for forbidden in (
            'postgresql://', 'password=', 'Authorization:', 'ADMIN_API_TOKEN',
            'SECRET_KEY', 'DATABASE_URL', 'Traceback', '/home/',
        ):
            assert forbidden not in body


def test_the_diagnostic_is_deterministic(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        args = (stored, _values(earned_runs=2), _stats(earnedRuns=2, runs=2), pitcher)
        first = game_driven_ingestion._safe_row_entries([_plan(*args)])
        second = game_driven_ingestion._safe_row_entries([_plan(*args)])
        assert first == second


def test_the_diagnostic_uses_the_canonical_plan_not_a_second_comparator():
    import inspect

    source = inspect.getsource(reconciliation.difference_classifications)
    # It reads the plan's own categories and field sets; it never re-compares
    # a stored row against source values.
    assert 'getattr(' not in source
    assert 'query' not in source


def test_the_classification_reads_only_the_plans_own_decision(app):
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        plan = _plan(
            stored, _values(earned_runs=2), _stats(earnedRuns=2, runs=2), pitcher,
        )
        # Same plan, no database at all.
        assert reconciliation.difference_classifications(plan) == (
            plan['difference_classifications']
        )


# ── The production discrepancy class (game 824488) ──────────────────────────


def test_a_statistical_field_left_different_by_the_writer_is_projected(app):
    """The class of discrepancy the first production cycle reported.

    One appearance in a newly-final game, one statistical field differing, no
    outs difference, no decimal difference, no appearance-team or identity
    action. This reproduces that shape without depending on production, and
    without naming the game in production logic.
    """
    with app.app_context():
        pitcher = _pitcher(8488)
        stored = _stored(pitcher, earned_runs=1)

        plan = _plan(
            stored, _values(earned_runs=3), _stats(earnedRuns=3, runs=3), pitcher,
        )
        summary = reconciliation.summarize([plan])

        assert summary['rows_updated'] == 1
        assert summary['rows_inserted'] == 0
        assert summary['rows_blocked'] == 0
        assert summary['statistical_corrections'] == 1
        assert summary['canonical_outs_corrections'] == 0
        assert summary['appearance_team_mutations'] == 0
        assert summary['pitcher_identity_mutations'] == 0
        assert summary['provenance_only_updates'] == 0
        assert summary['complete_mutation_count'] == 1


def test_that_class_is_now_identifiable_from_the_artifact(app):
    """The artifact from the failed cycle could not name the row. This can."""
    with app.app_context():
        pitcher = _pitcher(8488)
        stored = _stored(pitcher, earned_runs=1)
        plan = _plan(
            stored, _values(earned_runs=3), _stats(earnedRuns=3, runs=3), pitcher,
        )
        row = game_driven_ingestion._safe_row_entries([plan])[0]

        assert row['pitcher_mlb_id'] == 8488
        assert row['changed_fields']
        assert row['difference_classifications'] == [
            reconciliation.DIFFERENCE_STATISTICAL
        ]


def test_a_decimal_only_difference_is_not_a_statistical_correction(app):
    """D-008 preserved: representation drift is never a correction."""
    with app.app_context():
        pitcher = _pitcher(8489)
        stored = _stored(pitcher, outs=3)
        stored.innings_pitched = 0.9999999999
        db.session.commit()

        plan = _plan(stored, _values(outs=3), _stats(), pitcher)

        assert plan['action'] == reconciliation.ACTION_UNCHANGED
        assert plan['derived_companion_differences_ignored'] == ['innings_pitched']


def test_the_repair_hardcodes_no_production_game_or_pitcher():
    """No one-off exception for the game that exposed the class."""
    import pathlib

    for module in (
        sync_service.__file__,
        reconciliation.__file__,
        game_driven_ingestion.__file__,
    ):
        text = pathlib.Path(module).read_text(encoding='utf-8')
        assert '824488' not in text


# ── Budget reporting ────────────────────────────────────────────────────────


def test_the_cap_and_the_allocation_are_reported_separately(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion',
        lambda reference_date, **kwargs: {
            'status': 'complete', 'games': [], 'games_planned': 0,
            'elapsed_seconds': 1.0, 'remaining_budget_seconds': 149.0,
            'execution_effects': game_driven_ingestion._empty_execution_effects(
                'shadow'
            ),
        },
    )
    status = {}
    with app.app_context():
        sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget=sync_service._postgame_refresh_runtime_budget(),
            sync_run_id=None,
            status=status,
            stage_timings={},
            run_logger=sync_service.logger,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            write_modes_supported=False,
            only_game_pks=[],
            scope_summary={'scope_source': 'test'},
        )

    lane = status['game_driven_ingestion']
    assert lane['configured_stage_cap_seconds'] == 600.0
    assert lane['effective_allocated_budget_seconds'] == 150.0
    assert lane['lane_budget_share'] == 0.25
    assert lane['remaining_headroom_seconds'] == 149.0


def test_the_cap_is_never_presented_as_the_available_budget(app, monkeypatch):
    """600 with 150 allocated read as '600 available' on the first cycle."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion',
        lambda reference_date, **kwargs: {
            'status': 'complete', 'games': [], 'games_planned': 0,
            'elapsed_seconds': 1.0, 'remaining_budget_seconds': 149.0,
            'execution_effects': game_driven_ingestion._empty_execution_effects(
                'shadow'
            ),
        },
    )
    status = {}
    with app.app_context():
        sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget=sync_service._postgame_refresh_runtime_budget(),
            sync_run_id=None,
            status=status,
            stage_timings={},
            run_logger=sync_service.logger,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            write_modes_supported=False,
            only_game_pks=[],
            scope_summary={},
        )

    lane = status['game_driven_ingestion']
    assert lane['allocated_budget_seconds'] == (
        lane['effective_allocated_budget_seconds']
    )
    assert lane['allocated_budget_seconds'] != lane['configured_stage_cap_seconds']


def test_the_postgame_cap_was_not_raised_to_mask_the_scope_defect():
    assert sync_service.POSTGAME_REFRESH_DEFAULT_INGESTION_BUDGET_SECONDS == 600.0


def test_the_lane_budget_share_was_not_raised():
    assert sync_service._game_driven_lane_budget_share() == 0.25


# ── Zero-write behaviour is unchanged ───────────────────────────────────────


def test_the_scoped_postgame_lane_still_writes_nothing(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        pitcher = _pitcher(8001)
        _stored(pitcher)
        _marker(GAME_PK)
        for team_id, opponent_id, side in ((1, 2, 'home'), (2, 1, 'away')):
            db.session.add(ScheduledGame(
                team_id=team_id, game_pk=GAME_PK, game_date=SLATE,
                game_datetime=datetime(2026, 6, 20, 19, 5),
                opponent_team_id=opponent_id, home_away=side, game_type='R',
                status_code='F', status_state=ScheduledGame.STATE_FINAL,
            ))
        db.session.commit()
        before = GameLog.query.count(), GameIngestionWorkItem.query.count()

        scope = _scope([_game()])
        status = {}
        result = sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget=sync_service._postgame_refresh_runtime_budget(),
            sync_run_id=None,
            status=status,
            stage_timings={},
            run_logger=sync_service.logger,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            write_modes_supported=False,
            only_game_pks=scope['requested_game_pks'],
            scope_summary=scope,
        )

        assert (GameLog.query.count(), GameIngestionWorkItem.query.count()) == before
        assert result['refused_reason'] is None
        effects = status['game_driven_ingestion']['execution_effects']
        assert all(
            effects[field] == 0 for field in (
                'game_log_rows_written', 'work_items_created',
                'checkpoints_advanced', 'dead_letters_created',
                'commits_performed',
            )
        )


def test_the_scope_summary_reaches_the_report(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion',
        lambda reference_date, **kwargs: {
            'status': 'complete', 'games': [], 'games_planned': 0,
            'elapsed_seconds': 1.0, 'remaining_budget_seconds': 149.0,
            'execution_effects': game_driven_ingestion._empty_execution_effects(
                'shadow'
            ),
        },
    )
    status = {}
    with app.app_context():
        sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget=sync_service._postgame_refresh_runtime_budget(),
            sync_run_id=None,
            status=status,
            stage_timings={},
            run_logger=sync_service.logger,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            write_modes_supported=False,
            only_game_pks=[940001],
            scope_summary={
                'scope_source': sync_service.POSTGAME_SCOPE_SOURCE,
                'requested_game_pks': [940001],
                'requested_game_count': 1,
            },
        )

    scope = status['game_driven_ingestion']['execution_scope']
    assert scope['scope_source'] == sync_service.POSTGAME_SCOPE_SOURCE
    assert scope['requested_game_pks'] == [940001]


# ── The diagnostic surface, end to end through the stage ────────────────────
# This path had no coverage when it was written, and an undefined module alias
# in it survived a full green suite. It is exercised for real here.


def _stage_with_report(monkeypatch, rows, *, game_extra=None):
    report_game = {'game_pk': GAME_PK, 'rows': rows}
    report_game.update(game_extra or {})
    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion',
        lambda reference_date, **kwargs: {
            'status': 'complete', 'games_planned': 1,
            'elapsed_seconds': 1.0, 'remaining_budget_seconds': 149.0,
            'execution_effects': (
                game_driven_ingestion._empty_execution_effects('shadow')
            ),
            'games': [report_game],
        },
    )
    status = {}
    sync_service._run_game_driven_ingestion_stage(
        reference_date=SLATE,
        runtime_budget=sync_service._postgame_refresh_runtime_budget(),
        sync_run_id=None,
        status=status,
        stage_timings={},
        run_logger=sync_service.logger,
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        write_modes_supported=False,
        only_game_pks=[GAME_PK],
        scope_summary={'scope_source': sync_service.POSTGAME_SCOPE_SOURCE},
    )
    return status


def test_the_stage_publishes_projected_differences(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        plan = _plan(
            stored, _values(earned_runs=2), _stats(earnedRuns=2, runs=2), pitcher,
        )
        rows = game_driven_ingestion._safe_row_entries([plan])

        status = _stage_with_report(monkeypatch, rows, game_extra={
            'source_revision': 'rev-abc',
            'reconciliation_plan_fingerprint': 'f' * 64,
        })

        differences = status['game_driven_ingestion']['projected_differences']
        assert len(differences) == 1
        entry = differences[0]
        assert entry['game_pk'] == GAME_PK
        assert entry['pitcher_mlb_id'] == 8001
        assert entry['action'] == reconciliation.ACTION_UPDATE
        assert 'earned_runs' in entry['changed_fields']
        assert entry['difference_classifications'] == [
            reconciliation.DIFFERENCE_STATISTICAL
        ]
        assert entry['source_revision'] == 'rev-abc'
        assert entry['reconciliation_plan_fingerprint'] == 'f' * 64
        assert entry['target_state_digest'] != entry['stored_state_digest']


def test_unchanged_rows_do_not_appear_in_the_diagnostic(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher)
        plan = _plan(stored, _values(), _stats(), pitcher)
        rows = game_driven_ingestion._safe_row_entries([plan])

        status = _stage_with_report(monkeypatch, rows)

        assert status['game_driven_ingestion']['projected_differences'] == []


def test_the_published_diagnostic_carries_no_values(app, monkeypatch):
    import json

    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        pitcher = _pitcher(8001)
        stored = _stored(pitcher, earned_runs=0)
        plan = _plan(
            stored, _values(earned_runs=9), _stats(earnedRuns=9, runs=9), pitcher,
        )
        rows = game_driven_ingestion._safe_row_entries([plan])

        status = _stage_with_report(monkeypatch, rows)

        body = json.dumps(
            status['game_driven_ingestion']['projected_differences'],
            sort_keys=True, default=str,
        )
        assert 'earned_runs' in body
        assert '"before"' not in body
        assert '"after"' not in body
        for forbidden in (
            'postgresql://', 'password=', 'Authorization:', 'ADMIN_API_TOKEN',
            'SECRET_KEY', 'DATABASE_URL', 'Traceback', '/home/',
        ):
            assert forbidden not in body
