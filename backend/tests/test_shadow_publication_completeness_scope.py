"""Shadow observation backlog is not a publication blocker.

A read-only production audit found the exact shape reproduced below: 105
expected final games, 42 with completed work items, and 63 counted as
unresolved final games. All 63 had official-final evidence, final stored
schedule authority, and stored appearance rows. None of them was a baseball
deficit. Their only defect was that the game-driven lane runs in SHADOW mode
and therefore creates no durable work item — and the daily sync folded that
number into publication-critical unresolved work.

That is a scope defect: shadow OBSERVATION incompleteness represented as
PUBLICATION-BLOCKING incompleteness.

These prove the separation is real in both directions. The backlog stays
visible and is not erased, repaired, or backfilled; it contributes zero
publication blockers while the lane is non-authoritative; and every gate that
protects the BASEBALL record — finality, schedule authority, appearance
reconciliation, material corrections — still withholds in shadow exactly as
before.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import game_driven_ingestion
from services import game_ingestion_completeness as completeness
from services import publication_criticality
from services import sync as sync_service
from utils.db import db


REFERENCE = date(2026, 7, 29)

# The audited production shape.
COMPLETED_GAMES = 42
OBSERVATION_ONLY_GAMES = 63
EXPECTED_GAMES = COMPLETED_GAMES + OBSERVATION_ONLY_GAMES  # 105

SHADOW = game_driven_ingestion.MODE_SHADOW
WRITE = game_driven_ingestion.MODE_WRITE
AUTHORITATIVE = game_driven_ingestion.MODE_AUTHORITATIVE
OFF = game_driven_ingestion.MODE_OFF


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


# ── Fixture ────────────────────────────────────────────────────────────────

def _schedule(game_pk, *, game_date=REFERENCE, state=ScheduledGame.STATE_FINAL,
              away_state=None):
    for team_id, opponent, side, side_state in (
        (100, 200, 'home', state),
        (200, 100, 'away', away_state or state),
    ):
        db.session.add(ScheduledGame(
            game_pk=game_pk, team_id=team_id, opponent_team_id=opponent,
            game_date=game_date, home_away=side, status_state=side_state,
            status_code='F', game_type='R',
        ))


def _completed_item(game_pk, *, rows, represented_date=REFERENCE):
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=game_pk, represented_date=represented_date,
        game_date=represented_date,
        status=GameIngestionWorkItem.STATUS_COMPLETED,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        rows_expected=rows, rows_reconciled=rows,
        completed_at=datetime(2026, 7, 29, 6, 0, 0),
    ))


def _appearance_rows(game_pk, count, *, start_mlb_id):
    for offset in range(count):
        mlb_id = start_mlb_id + offset
        pitcher = Pitcher(
            mlb_id=mlb_id, full_name=f'Arm {mlb_id}', team_id=147,
            team_abbreviation='TST', position='P', active=True,
        )
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=game_pk, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3,
        ))


def _seed_audited_shape():
    """105 expected games: 42 with completed work items, 63 with none.

    The absence of a work item for the 63 IS the condition being governed.
    Nothing here fabricates one to make a count go away.
    """
    mlb_id = 90000
    for index in range(COMPLETED_GAMES):
        game_pk = 930000 + index
        _schedule(game_pk)
        _completed_item(game_pk, rows=1)
        _appearance_rows(game_pk, 1, start_mlb_id=mlb_id)
        mlb_id += 1
    for index in range(OBSERVATION_ONLY_GAMES):
        game_pk = 940000 + index
        # Official-final, final stored schedule authority, stored appearance
        # rows — and deliberately no durable work item, because the lane is
        # shadow and has never created one.
        _schedule(game_pk)
        _appearance_rows(game_pk, 1, start_mlb_id=mlb_id)
        mlb_id += 1
    db.session.commit()


def _proof(lane_mode):
    return completeness.build_game_ingestion_completeness(
        REFERENCE, lane_mode=lane_mode,
    )


def _work_item_snapshot():
    return sorted(
        (item.id, item.mlb_game_pk, item.status, item.updated_at)
        for item in GameIngestionWorkItem.query.all()
    )


# ── The audited shape ──────────────────────────────────────────────────────

def test_the_audited_production_shape_is_reproduced(app):
    """105 / 42 / 63, from the real planner against a real database."""
    _seed_audited_shape()
    proof = _proof(SHADOW)

    observation = proof['observation']
    assert observation['expected_final_games'] == EXPECTED_GAMES == 105
    assert observation['completed_work_item_games'] == COMPLETED_GAMES == 42
    assert observation['unresolved_game_count'] == OBSERVATION_ONLY_GAMES == 63


def test_the_audited_backlog_blocks_nothing_in_shadow(app):
    _seed_audited_shape()
    proof = _proof(SHADOW)

    gate = proof['publication_gate']
    assert gate['blocking_unresolved_game_count'] == 0
    assert gate['blocking_terminal_failure_count'] == 0
    assert gate['complete'] is True
    assert proof['publication_complete'] is True
    assert proof['publication_blocking_unresolved_final_games'] == 0
    assert proof['publication_blocking_terminal_failure_games'] == 0


def test_the_observation_view_is_still_incomplete(app):
    """The backlog is not erased. It is reported, and it is not authority."""
    _seed_audited_shape()
    proof = _proof(SHADOW)

    assert proof['observation']['complete'] is False
    assert completeness.REASON_UNRESOLVED_FINAL_GAMES in (
        proof['observation']['reason_codes']
    )
    # And the legacy field still carries the observation count for telemetry.
    assert proof['unresolved_final_games'] == OBSERVATION_ONLY_GAMES


def test_the_status_says_observational_only(app):
    _seed_audited_shape()
    proof = _proof(SHADOW)

    gate = proof['publication_gate']
    assert gate['authority_effect'] == (
        completeness.AUTHORITY_EFFECT_OBSERVATIONAL_ONLY
    )
    assert proof['lane_mode'] == SHADOW
    assert proof['publication_authoritative'] is False
    assert completeness.REASON_LANE_NOT_AUTHORITATIVE in gate['reason_codes']
    assert completeness.REASON_OBSERVATION_UNRESOLVED_GAMES in (
        gate['reason_codes']
    )
    assert gate['observation_only_game_count'] == OBSERVATION_ONLY_GAMES


def test_the_arithmetic_is_not_misleading(app):
    """105 total / 42 completed / 0 unresolved would imply 63 vanished."""
    _seed_audited_shape()
    gate = _proof(SHADOW)['publication_gate']

    # The gate reports its OWN scope, which the shadow lane does not own.
    assert gate['blocking_scope_game_count'] == 0
    assert gate['blocking_completed_game_count'] == 0
    assert gate['blocking_unresolved_game_count'] == 0
    # The 105/42/63 numbers live in the separately named observation view.
    observation = _proof(SHADOW)['observation']
    assert (
        observation['expected_final_games']
        - observation['completed_work_item_games']
    ) == observation['unresolved_game_count']


def test_the_sync_gate_reports_zero_publication_critical_unresolved(app):
    _seed_audited_shape()
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': SHADOW,
            'report': {'best_effort_games_deferred': 0},
            'completeness': _proof(SHADOW),
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )

    assert result['publication_critical_unresolved'] == 0
    assert result['publication_critical_failed'] == 0
    assert result['complete'] is True
    assert result['status'] == (
        publication_criticality.PUBLICATION_CRITICAL_COMPLETE
    )


def test_the_proof_creates_and_mutates_nothing(app):
    """Read-only: no work item is inserted, updated, or committed."""
    _seed_audited_shape()
    before = _work_item_snapshot()
    before_logs = GameLog.query.count()

    for mode in (SHADOW, WRITE, AUTHORITATIVE, OFF):
        _proof(mode)
    completeness.classify_game_ingestion_scope(REFERENCE)
    completeness.unresolved_final_game_membership(REFERENCE)
    completeness.publication_blocking_game_membership(
        REFERENCE, lane_mode=SHADOW,
    )

    db.session.rollback()
    assert _work_item_snapshot() == before
    assert len(before) == COMPLETED_GAMES
    assert GameLog.query.count() == before_logs


# ── Mode matrix ────────────────────────────────────────────────────────────

@pytest.mark.parametrize('mode,effect,blockers', [
    (SHADOW, completeness.AUTHORITY_EFFECT_OBSERVATIONAL_ONLY, 0),
    (WRITE, completeness.AUTHORITY_EFFECT_NON_AUTHORITATIVE_WRITE, 0),
    (AUTHORITATIVE, completeness.AUTHORITY_EFFECT_AUTHORITATIVE,
     OBSERVATION_ONLY_GAMES),
])
def test_the_mode_matrix_over_the_audited_shape(app, mode, effect, blockers):
    _seed_audited_shape()
    proof = _proof(mode)

    # Observation is identical in every mode: the same games, the same count.
    assert proof['observation']['unresolved_game_count'] == (
        OBSERVATION_ONLY_GAMES
    )
    assert proof['publication_gate']['authority_effect'] == effect
    assert proof['publication_gate']['blocking_unresolved_game_count'] == (
        blockers
    )


def test_write_mode_remains_non_authoritative(app):
    _seed_audited_shape()
    proof = _proof(WRITE)

    assert proof['publication_authoritative'] is False
    assert proof['publication_gate']['complete'] is True
    assert proof['publication_gate']['blocking_unresolved_game_count'] == 0
    assert game_driven_ingestion.publication_authoritative(WRITE) is False


def test_authoritative_mode_blocks_on_the_same_backlog(app):
    _seed_audited_shape()
    proof = _proof(AUTHORITATIVE)

    gate = proof['publication_gate']
    assert proof['publication_authoritative'] is True
    assert gate['blocking_unresolved_game_count'] == OBSERVATION_ONLY_GAMES
    assert gate['complete'] is False
    assert proof['publication_complete'] is False
    assert completeness.REASON_UNRESOLVED_FINAL_GAMES in gate['reason_codes']
    # And the arithmetic is coherent in the mode that owns the scope.
    assert gate['blocking_scope_game_count'] == EXPECTED_GAMES
    assert gate['blocking_completed_game_count'] == COMPLETED_GAMES


@pytest.mark.parametrize('mode', [OFF, None, 'not_a_mode', ''])
def test_an_unavailable_or_unknown_mode_cannot_claim_completeness(app, mode):
    _seed_audited_shape()
    proof = completeness.build_game_ingestion_completeness(
        REFERENCE, lane_mode=mode,
    )

    gate = proof['publication_gate']
    assert gate['authority_effect'] == (
        completeness.AUTHORITY_EFFECT_UNAVAILABLE
    )
    assert gate['complete'] is False
    assert proof['publication_complete'] is False
    assert completeness.REASON_LANE_AUTHORITY_UNAVAILABLE in (
        gate['reason_codes']
    )


def test_an_unavailable_mode_fails_closed_through_the_sync_gate(app):
    _seed_audited_shape()
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': OFF,
            'report': {'best_effort_games_deferred': 0},
            'completeness': _proof(OFF),
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )
    assert result['complete'] is False


# ── Real gates still withhold in shadow ────────────────────────────────────

def test_a_finality_conflict_still_withholds_in_shadow(app):
    _seed_audited_shape()
    _schedule(
        950001, state=ScheduledGame.STATE_FINAL,
        away_state=ScheduledGame.STATE_SCHEDULED,
    )
    db.session.commit()

    gate = _proof(SHADOW)['publication_gate']
    assert gate['finality_conflict_count'] >= 1
    assert gate['complete'] is False
    assert completeness.REASON_FINALITY_CONFLICT in gate['reason_codes']


def test_a_schedule_authority_gap_still_withholds_in_shadow(app):
    _seed_audited_shape()
    # Unresolved critical work whose schedule authority has vanished.
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=950002, represented_date=REFERENCE, game_date=REFERENCE,
        status=GameIngestionWorkItem.STATUS_PLANNED,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
    ))
    db.session.commit()

    gate = _proof(SHADOW)['publication_gate']
    assert gate['schedule_authority_missing_count'] >= 1
    assert gate['complete'] is False
    assert completeness.REASON_SCHEDULE_AUTHORITY_MISSING in (
        gate['reason_codes']
    )


def test_an_appearance_row_shortfall_still_withholds_in_shadow(app):
    """A completed game that claims more rows than the ledger holds."""
    _seed_audited_shape()
    _schedule(950003)
    _completed_item(950003, rows=4)
    _appearance_rows(950003, 1, start_mlb_id=95500)
    db.session.commit()

    gate = _proof(SHADOW)['publication_gate']
    assert gate['appearance_rows_expected'] > gate['appearance_rows_reconciled']
    assert gate['complete'] is False
    assert completeness.REASON_APPEARANCE_ROWS_UNRECONCILED in (
        gate['reason_codes']
    )


def test_a_material_correction_conflict_still_withholds_in_shadow(app):
    _seed_audited_shape()
    _schedule(950004)
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=950004, represented_date=REFERENCE, game_date=REFERENCE,
        status=GameIngestionWorkItem.STATUS_PLANNED,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        candidate_reason=GameIngestionWorkItem.REASON_CORRECTED_FINAL,
        error_class='correction_conflict',
    ))
    db.session.commit()

    gate = _proof(SHADOW)['publication_gate']
    assert gate['correction_pending_count'] >= 1
    assert gate['complete'] is False
    assert completeness.REASON_CORRECTION_PENDING in gate['reason_codes']


# ── Work-item state is mode-governed; baseball evidence is not ─────────────

def _retryable_item(game_pk):
    _schedule(game_pk)
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=game_pk, represented_date=REFERENCE, game_date=REFERENCE,
        status=GameIngestionWorkItem.STATUS_PLANNED,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
    ))
    db.session.commit()


def _terminal_item(game_pk):
    _schedule(game_pk)
    db.session.add(GameIngestionWorkItem(
        mlb_game_pk=game_pk, represented_date=REFERENCE, game_date=REFERENCE,
        status=GameIngestionWorkItem.STATUS_TERMINAL_FAILURE,
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
        error_class='boxscore_unavailable',
    ))
    db.session.commit()


def test_retryable_work_in_shadow_is_observed_but_not_blocking(app):
    _seed_audited_shape()
    _retryable_item(950010)

    proof = _proof(SHADOW)
    assert proof['observation']['retryable_work_item_count'] >= 1
    assert completeness.REASON_CRITICAL_FAILURE_UNRESOLVED in (
        proof['observation']['reason_codes']
    )
    gate = proof['publication_gate']
    assert gate['blocking_retryable_work_item_count'] == 0
    assert gate['complete'] is True


def test_terminal_work_in_shadow_is_observed_but_not_blocking(app):
    _seed_audited_shape()
    _terminal_item(950011)

    proof = _proof(SHADOW)
    assert proof['observation']['terminal_work_item_count'] >= 1
    assert completeness.REASON_TERMINAL_CRITICAL_FAILURE in (
        proof['observation']['reason_codes']
    )
    gate = proof['publication_gate']
    assert gate['blocking_terminal_failure_count'] == 0
    assert gate['complete'] is True


def test_retryable_work_in_authoritative_mode_blocks(app):
    _seed_audited_shape()
    _retryable_item(950012)

    gate = _proof(AUTHORITATIVE)['publication_gate']
    assert gate['blocking_retryable_work_item_count'] >= 1
    assert gate['complete'] is False
    assert completeness.REASON_CRITICAL_FAILURE_UNRESOLVED in (
        gate['reason_codes']
    )


def test_terminal_work_in_authoritative_mode_blocks(app):
    _seed_audited_shape()
    _terminal_item(950013)

    gate = _proof(AUTHORITATIVE)['publication_gate']
    assert gate['blocking_terminal_failure_count'] >= 1
    assert gate['complete'] is False
    assert completeness.REASON_TERMINAL_CRITICAL_FAILURE in (
        gate['reason_codes']
    )


# ── One classification, two views ──────────────────────────────────────────

def test_both_views_are_projections_of_one_classification(app):
    """The views may differ in what they COUNT, never in what they SAW."""
    _seed_audited_shape()
    scope = completeness.classify_game_ingestion_scope(REFERENCE)

    observation = completeness.unresolved_final_game_membership(
        REFERENCE, scope=scope,
    )
    shadow_blockers = completeness.publication_blocking_game_membership(
        REFERENCE, scope=scope, lane_mode=SHADOW,
    )
    authoritative_blockers = completeness.publication_blocking_game_membership(
        REFERENCE, scope=scope, lane_mode=AUTHORITATIVE,
    )

    assert observation['game_pks'] == scope['unresolved_game_pks']
    assert shadow_blockers['game_pks'] == []
    # Withheld from the gate, but named, so nothing is silently dropped.
    assert shadow_blockers['observation_only_game_pks'] == (
        observation['game_pks']
    )
    # Under authority the blocker set IS the observation set — same games.
    assert authoritative_blockers['game_pks'] == observation['game_pks']


def test_the_membership_helper_keeps_its_observation_meaning(app):
    """Its meaning must not silently become the blocker set."""
    _seed_audited_shape()
    membership = completeness.unresolved_final_game_membership(REFERENCE)

    assert membership['membership_view'] == 'observation'
    assert len(membership['game_pks']) == OBSERVATION_ONLY_GAMES
    assert len(membership['outstanding_critical_game_pks']) == (
        OBSERVATION_ONLY_GAMES
    )
    assert len(membership['critical_planned_game_pks']) == EXPECTED_GAMES


# ── The sync consumer reads blockers, not observation ──────────────────────

def test_sync_never_folds_observation_backlog_into_critical_counts(app):
    _seed_audited_shape()
    proof = _proof(SHADOW)
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': SHADOW,
            'report': {'best_effort_games_deferred': 0},
            'completeness': proof,
        },
        pull={'pitchers_total': 100, 'budget_exhausted_pitchers': 10},
        non_gamelog_critical_failed=0,
    )

    assert proof['observation']['unresolved_game_count'] == 63
    assert result['publication_critical_unresolved'] == 0
    assert result['publication_critical_total'] == 0
    assert result['publication_critical_completed'] == 0
    # Best-effort accounting is untouched.
    assert result['best_effort_deferred'] == 10


def test_sync_still_folds_baseball_evidence_into_the_gate(app):
    _seed_audited_shape()
    _schedule(
        950020, state=ScheduledGame.STATE_FINAL,
        away_state=ScheduledGame.STATE_SCHEDULED,
    )
    db.session.commit()

    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': SHADOW,
            'report': {'best_effort_games_deferred': 0},
            'completeness': _proof(SHADOW),
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )
    assert result['complete'] is False
    assert result['unknown_criticality'] >= 1


def test_a_non_gamelog_critical_failure_still_blocks_in_shadow(app):
    _seed_audited_shape()
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': SHADOW,
            'report': {'best_effort_games_deferred': 0},
            'completeness': _proof(SHADOW),
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=1,
    )
    assert result['complete'] is False
    assert publication_criticality.REASON_NON_GAMELOG_FAILURE in (
        result['reason_codes']
    )


@pytest.mark.parametrize('completeness_result', [
    {},
    None,
    {'publication_complete': False, 'decision_reasons': ['proof_unavailable']},
    {'unresolved_final_games': 3, 'publication_complete': False},
    {'publication_gate': 'not a mapping'},
    {'publication_gate': {}},
])
def test_a_missing_or_malformed_result_fails_closed(completeness_result):
    """Degrade to the strict legacy reading, never to zero blockers."""
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': SHADOW,
            'report': {'best_effort_games_deferred': 0},
            'completeness': completeness_result,
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )
    assert result['complete'] is False


def test_a_legacy_shaped_result_keeps_its_strict_meaning():
    """An older producer's counts are still read as blocking."""
    result = sync_service._publication_critical_from_game_lane(
        game_lane={
            'mode': AUTHORITATIVE,
            'report': {'best_effort_games_deferred': 0},
            'completeness': {
                'expected_final_games': 15,
                'completed_final_games': 14,
                'unresolved_final_games': 1,
                'terminal_failure_games': 0,
                'finality_conflicts': 0,
                'schedule_authority_missing': 0,
                'publication_complete': False,
                'decision_reasons': ['unresolved_final_games'],
            },
        },
        pull={'pitchers_total': 0, 'budget_exhausted_pitchers': 0},
        non_gamelog_critical_failed=0,
    )
    assert result['complete'] is False
    assert result['publication_critical_unresolved'] == 1


# ── No authority transfer ──────────────────────────────────────────────────

def test_the_mode_authority_itself_is_unchanged():
    assert game_driven_ingestion.publication_authoritative(SHADOW) is False
    assert game_driven_ingestion.publication_authoritative(WRITE) is False
    assert game_driven_ingestion.publication_authoritative(AUTHORITATIVE) is (
        True
    )
    assert game_driven_ingestion.writes_enabled(SHADOW) is False
    assert game_driven_ingestion.writes_enabled(WRITE) is True


def test_the_completeness_proof_never_enables_a_write_path():
    """This module reads. It has no write verb at all."""
    import ast
    import inspect

    source = inspect.getsource(completeness)
    tree = ast.parse(source)
    called = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = node.func
            if isinstance(target, ast.Attribute):
                called.add(target.attr)
            elif isinstance(target, ast.Name):
                called.add(target.id)

    for forbidden in ('add', 'commit', 'flush', 'delete', 'merge', 'execute'):
        assert forbidden not in called, forbidden
    assert 'GameIngestionWorkItem(' not in source


def test_this_package_adds_no_dispatch_backfill_or_publication_path():
    import inspect

    source = inspect.getsource(completeness)
    for forbidden in (
        'run_game_driven_ingestion', 'include_backfill', 'workflow_dispatch',
        'store_dashboard_snapshot', 'publish_dashboard_snapshot',
        'reset_checkpoint',
    ):
        assert forbidden not in source, forbidden


def test_the_authority_effect_vocabulary_is_closed(app):
    _seed_audited_shape()
    for mode in (SHADOW, WRITE, AUTHORITATIVE, OFF, 'nonsense', None):
        proof = completeness.build_game_ingestion_completeness(
            REFERENCE, lane_mode=mode,
        )
        assert proof['publication_gate']['authority_effect'] in (
            completeness.AUTHORITY_EFFECTS
        )


def test_a_non_blocking_reason_never_appears_without_zero_blockers(app):
    """The observation reason must not ride into a blocking field."""
    _seed_audited_shape()
    for mode in (SHADOW, WRITE, AUTHORITATIVE):
        gate = _proof(mode)['publication_gate']
        if completeness.REASON_OBSERVATION_UNRESOLVED_GAMES in (
            gate['reason_codes']
        ):
            assert gate['blocking_unresolved_game_count'] == 0
            assert gate['blocking_terminal_failure_count'] == 0
