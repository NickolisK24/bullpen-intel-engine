"""Production regression for run 30862655470, through the REAL orchestration.

The earlier fixture asserted the finality helper in isolation, which proved
nothing about the order the qualification actually executes in — and the order
was wrong: shadow ran before the work-item check, so a refusal that was already
decided still spent an MLB request and a full canonical planning pass, and the
evidence claimed the planner had run.

These tests drive ``run()`` itself and assert the lane is never called.
"""

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from services import game_driven_ingestion as lane
from services import noop_write_qualification as qualification
from utils.db import db

import scripts.run_game_driven_noop_qualification as runner


GAME_PK = 824488
SHA = 'd' * 40


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


class _Args:
    game_pk = str(GAME_PK)
    expected_head_sha = SHA
    confirmation = f'QUALIFY_NOOP_GAME_{GAME_PK}'
    operator_note = ''
    artifact_dir = ''
    reference_date = '2026-07-29'


@pytest.fixture
def production_context(monkeypatch):
    for key, value in {
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REPOSITORY': 'NickolisK24/bullpen-intel-engine',
        'GITHUB_ACTOR': 'NickolisK24',
        'GITHUB_REF': 'refs/heads/main',
        'GITHUB_SHA': SHA,
        'GITHUB_RUN_ID': '30862655470',
        'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_WORKFLOW': 'Manual Game-Driven No-Op Write Qualification',
    }.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def spy(app, monkeypatch, production_context):
    """Run the real orchestration with the lane and MLB client instrumented."""
    calls = {'lane': 0, 'mlb': 0, 'guard_released': 0}

    def _lane(*args, **kwargs):
        calls['lane'] += 1
        raise AssertionError('the lane must not be called')

    monkeypatch.setattr(lane, 'run_game_driven_ingestion', _lane)
    monkeypatch.setattr(runner, 'build_app', lambda: app)

    class _Guard:
        def release(self):
            calls['guard_released'] += 1

    from services import sync_metadata

    monkeypatch.setattr(
        sync_metadata, 'acquire_sync_writer_guard', lambda **kw: _Guard(),
    )

    from services import sync as sync_service

    class _Client:
        def get_game_boxscore(self, game_pk):
            calls['mlb'] += 1
            raise AssertionError('no MLB request may be made')

    monkeypatch.setattr(sync_service, 'mlb_client', _Client())
    return calls


def _run(tmp_path, spy):
    args = _Args()
    args.artifact_dir = str(tmp_path / 'artifacts')
    return runner.run(args), spy


# ── The regression ──────────────────────────────────────────────────────────


def test_a_missing_work_item_refuses_without_calling_the_lane(spy, tmp_path):
    """No durable work item exists for 824488 in this database."""
    document, calls = _run(tmp_path, spy)

    assert calls['lane'] == 0, 'run_game_driven_ingestion was called'
    assert calls['mlb'] == 0, 'an MLB request was made'

    verdict = document['verdict']
    assert verdict['result'] == qualification.RESULT_FAILED
    assert verdict['failed_reasons'] == [
        qualification.FAILED_TARGET_WORK_ITEM_MISSING
    ]


def test_the_evidence_reports_the_real_execution_order(spy, tmp_path):
    document, _ = _run(tmp_path, spy)
    authority = document['game_authority']

    assert authority['work_item_precondition_checked'] is True
    assert authority['work_item_precondition_passed'] is False
    assert authority['planner_phase_entered'] is False
    assert authority['finality_check_executed'] is False
    assert authority['finality_proven_by_planner'] is None
    assert authority['finality_display'] == 'not executed'


def test_the_planner_is_neither_returned_nor_raised_when_never_entered(
    spy, tmp_path,
):
    document, _ = _run(tmp_path, spy)
    authority = document['game_authority']
    assert authority['planner_returned'] is False
    assert authority['planner_raised'] is False


def test_the_write_phase_is_not_entered(spy, tmp_path):
    document, _ = _run(tmp_path, spy)
    assert document['execution']['write_phase_entered'] is False


def test_the_writer_guard_is_still_acquired_and_released(spy, tmp_path):
    """The refusal happens under the guard, and the guard is released."""
    document, calls = _run(tmp_path, spy)
    execution = document['execution']
    assert execution['writer_guard_acquired'] is True
    assert execution['writer_guard_release_attempted'] is True
    assert execution['writer_guard_released'] is True
    assert calls['guard_released'] == 1


def test_the_refusal_is_failed_not_unproven(spy, tmp_path):
    document, _ = _run(tmp_path, spy)
    assert document['verdict']['exit_code'] == qualification.EXIT_FAILED


def test_the_artifact_carries_the_non_authorization_statement(spy, tmp_path):
    document, _ = _run(tmp_path, spy)
    assert 'does not authorize' in (
        document['verdict']['non_authorization_statement']
    )


def test_no_baseball_effect_is_reported(spy, tmp_path):
    document, _ = _run(tmp_path, spy)
    effects = document['execution']['baseball_data_effects'] or {}
    assert all(value == 0 for value in effects.values())


# ── The precondition genuinely gates the lane ───────────────────────────────


def test_the_work_item_read_precedes_the_lane_call_in_source():
    """Order is a property of the code, not only of this run."""
    import inspect

    source = inspect.getsource(runner.run)
    work_item_at = source.index('read_lane_bookkeeping')
    lane_at = source.index('run_game_driven_ingestion')
    assert work_item_at < lane_at


def test_planner_phase_entered_is_set_immediately_before_the_lane_call():
    import inspect

    source = inspect.getsource(runner.run)
    flag_at = source.index("collected['planner_phase_entered'] = True")
    lane_at = source.index('run_game_driven_ingestion')
    assert flag_at < lane_at
    between = source[flag_at:lane_at]
    # Nothing substantial may sit between the flag and the call.
    assert between.count('\n') <= 6, between
