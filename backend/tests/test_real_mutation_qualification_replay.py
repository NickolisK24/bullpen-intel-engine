"""Replay protection for the real-mutation qualification.

GitHub can re-run a workflow. A re-run against an already-corrected row must
resolve NO_LONGER_MUTATING and must never be presentable as a second
real-mutation proof — not by the service, not by the runner, and not by the
workflow's final gate.

This is the guard that stops one correction from being counted twice.
"""

import pathlib
import re

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion as lane
from services import real_mutation_qualification as qualification
from services import sync as sync_service
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from tests.game_driven_fixtures import (
    BoxscoreClient,
    REFERENCE,
    boxscore,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
from utils.db import db


GAME_PK = 953001
PITCHER_ID = 6801

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / '.github' / 'workflows' / (
    'manual-game-driven-real-mutation-qualification.yml'
)


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


def _install(monkeypatch, strikeouts):
    monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
        GAME_PK: boxscore([
            (PITCHER_ID, 'home', pitching_stats(strikeouts=strikeouts)),
        ]),
    }))


def _stored(field):
    pitcher = Pitcher.query.filter_by(mlb_id=PITCHER_ID).one()
    row = GameLog.query.filter_by(
        mlb_game_pk=GAME_PK, pitcher_id=pitcher.id,
    ).one()
    return getattr(row, field)


def _apply_the_correction(monkeypatch):
    """Seed, revise, and apply exactly one reviewed correction."""
    _schedule(GAME_PK)
    _pitcher(PITCHER_ID)
    _install(monkeypatch, 2)
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()

    _install(monkeypatch, 3)
    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    fingerprint = shadow['reconciliation_plan_fingerprint']
    write = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[GAME_PK],
        expected_plan_fingerprint=fingerprint,
    )
    db.session.expire_all()
    return shadow, write, fingerprint


# ── The replay itself ───────────────────────────────────────────────────────


def test_the_first_run_applies_the_correction(app, monkeypatch):
    _, write, _ = _apply_the_correction(monkeypatch)

    assert write['status'] == 'complete'
    assert write['execution_effects']['game_log_rows_written'] == 1
    assert _stored('strikeouts') == 3


def test_a_replay_plans_no_mutation(app, monkeypatch):
    _apply_the_correction(monkeypatch)

    replay = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(replay, game_pk=GAME_PK)

    assert candidate['planned_row_count'] >= 1
    assert candidate['mutation_present'] is False
    assert candidate['planned_update_row_count'] == 0
    # Not a failure. There is simply nothing left to correct.
    assert candidate['failed_reasons'] == []


def test_a_replay_resolves_no_longer_mutating_not_pass(app, monkeypatch):
    _apply_the_correction(monkeypatch)

    replay = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(replay, game_pk=GAME_PK)

    decision = qualification.decide({
        'failed_reasons': [],
        'unproven_reasons': [],
        'no_longer_mutating': (
            bool(candidate['planned_row_count'])
            and not candidate['mutation_present']
        ),
    })

    assert decision['result'] == qualification.RESULT_NO_LONGER_MUTATING
    assert decision['result'] != qualification.RESULT_PASS
    assert decision['exit_code'] == 3


def test_a_replay_mutates_nothing_further(app, monkeypatch):
    _, _, fingerprint = _apply_the_correction(monkeypatch)
    assert _stored('strikeouts') == 3

    # The old reviewed fingerprint cannot authorize a second write: the plan
    # recomputed from current state is no longer that plan.
    replay_write = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[GAME_PK],
        expected_plan_fingerprint=fingerprint,
    )

    assert replay_write['status'] == lane.STATUS_PLAN_FINGERPRINT_MISMATCH
    assert replay_write['execution_effects']['game_log_rows_written'] == 0
    assert replay_write['execution_effects']['commits_performed'] == 0
    assert _stored('strikeouts') == 3


def test_the_assessment_of_a_replay_is_never_pass(app, monkeypatch):
    _apply_the_correction(monkeypatch)

    replay = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    decision = qualification.assess(
        context={
            'event_name': 'workflow_dispatch',
            'repository': 'NickolisK24/bullpen-intel-engine',
            'actor': 'NickolisK24',
            'ref': 'refs/heads/main',
            'github_sha': 'e' * 40,
            'expected_head_sha': 'e' * 40,
            'confirmation': f'QUALIFY_REAL_MUTATION_GAME_{GAME_PK}',
        },
        game_pk=GAME_PK,
        reviewed_fingerprint=replay['reconciliation_plan_fingerprint'],
        shadow_report=replay,
        write_report=replay,
        before_state=None,
        after_state=None,
        realized_digest=None,
        realization=None,
        bookkeeping_before=None,
        bookkeeping_after=None,
        writer_guard={
            'acquired': True, 'release_attempted': True, 'released': True,
        },
    )

    assert decision['result'] != qualification.RESULT_PASS


def test_the_correction_count_advances_only_once_across_a_replay(
    app, monkeypatch,
):
    _apply_the_correction(monkeypatch)
    after_first = qualification.read_lane_bookkeeping(GAME_PK)
    first_count = after_first['target']['correction_count']

    replay = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[GAME_PK],
        expected_plan_fingerprint=replay['reconciliation_plan_fingerprint'],
    )
    db.session.expire_all()
    after_replay = qualification.read_lane_bookkeeping(GAME_PK)

    assert after_replay['target']['correction_count'] == first_count


# ── The workflow gate refuses to present a replay as success ────────────────


def test_the_workflow_gate_refuses_exit_code_three():
    """A NO_LONGER_MUTATING run must not report a green real-mutation PASS."""
    text = WORKFLOW.read_text(encoding='utf-8')

    assert 'QUALIFICATION_EXIT: ${{ steps.qualification.outputs.exit_code }}' in text
    gate = text.split('Final qualification gate', 1)[1]
    assert '"${QUALIFICATION_EXIT:-1}" = "3"' in gate
    assert 'NO_LONGER_MUTATING' in gate
    # The replay branch exits non-zero before any success line is printed.
    replay_branch = gate.split('"${QUALIFICATION_EXIT:-1}" = "3"', 1)[1]
    replay_branch = replay_branch.split('fi', 1)[0]
    assert 'exit 1' in replay_branch
    # It exits before the success line the gate prints for a real PASS.
    assert 'Manual real-mutation qualification: PASS.' not in replay_branch


def test_the_workflow_gate_defaults_a_missing_exit_code_to_failure():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert 'QUALIFICATION_EXIT:-1' in text


def test_the_service_and_the_workflow_agree_on_the_replay_exit_code():
    text = WORKFLOW.read_text(encoding='utf-8')
    assert qualification.EXIT_NO_LONGER_MUTATING == 3
    assert re.search(r'QUALIFICATION_EXIT:-1\}"\s*=\s*"3"', text)
