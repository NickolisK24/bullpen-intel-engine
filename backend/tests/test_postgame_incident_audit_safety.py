"""Read-only safety contract for the postgame publication incident audit.

Requirements 41-57.

Transaction state, advisory locks, and scoped content fingerprints are exactly
the behaviour under test, so the fingerprint and transaction requirements run
against real PostgreSQL rather than a substitute. SQLite would not reproduce
``SET TRANSACTION READ ONLY``, advisory locks, or ``string_agg`` row digests,
so it is never used here.
"""

import ast
from datetime import timedelta
from pathlib import Path

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
# Every table the scoped fingerprints touch must be registered, or
# create_test_schema will not build it and the digest will (correctly) refuse.
import models.completed_game_context  # noqa: F401
import models.game_ingestion_work_item  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
import models.team_game_pitching_split  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.scheduled_game import ScheduledGame
from services import postgame_publication_incident_audit as audit
from utils.db import db


SERVICE_PATH = (
    Path(__file__).resolve().parents[1]
    / 'services/postgame_publication_incident_audit.py'
)
RUNNER_PATH = (
    Path(__file__).resolve().parents[1]
    / 'scripts/run_postgame_publication_incident_audit.py'
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


def _is_postgres():
    return db.session.get_bind().dialect.name == 'postgresql'


def _seed_incident_rows():
    """Minimal rows in every scope the fingerprints cover."""
    db.session.add(ScheduledGame(
        team_id=100, game_pk=audit.INCIDENT_GAME_PK,
        game_date=audit.INCIDENT_SLATE_DATE, status_state='final',
        status_code='F', source='test',
    ))
    db.session.add(ScheduledGame(
        team_id=200, game_pk=audit.INCIDENT_GAME_PK,
        game_date=audit.INCIDENT_SLATE_DATE, status_state='final',
        status_code='F', source='test',
    ))
    db.session.add(DashboardSnapshot(
        id=audit.INCIDENT_CANDIDATE_SNAPSHOT_ID,
        snapshot_type='bullpen_dashboard', status='pending',
        is_published=False, payload={}, payload_version=1,
        data_through=audit.INCIDENT_SLATE_DATE,
    ))
    db.session.commit()


def _clean_proof(**overrides):
    proof = {
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        **audit.EXPECTED_PROBE_EVIDENCE,
    }
    proof.update(overrides)
    return proof


def _decide(**overrides):
    kwargs = {
        'questions': [
            {'question_id': key, 'answered': True}
            for key in audit.QUESTION_IDS
        ],
        'findings': [],
        'read_only_proof': _clean_proof(),
        'artifact_ingestion': {
            'missing_required': [], 'unreadable_required': [],
            'digest_mismatches': [], 'all_required_present': True,
            'incident_validation': {'any_mismatch': False},
        },
        'budget_state': audit.SourceCallBudget().state(),
    }
    kwargs.update(overrides)
    return audit.decide(**kwargs)


def _called_names(tree):
    """Every name this module actually CALLS, attribute or bare."""
    names = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute):
            names.add(func.attr)
        elif isinstance(func, ast.Name):
            names.add(func.id)
    return names


def _imported_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
            names.add(node.module or '')
        elif isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
    return names


# ── 41-42 Guard and transaction ─────────────────────────────────────────────

def test_041_the_acquire_only_public_sync_read_lock_is_used():
    source = RUNNER_PATH.read_text(encoding='utf-8')
    assert 'acquire_public_sync_read_lock' in source
    # The writer guard, which touches SyncRun rows, is never used.
    assert 'acquire_sync_writer_guard' not in source


def test_042_a_postgresql_read_only_transaction_is_used(app):
    if not _is_postgres():
        pytest.skip('requires PostgreSQL')
    proof = audit.enforce_read_only(db.session)
    assert proof['protection'] == 'postgresql_read_only_transaction'
    assert proof['dialect'] == 'postgresql'
    db.session.rollback()


# ── 43-46 The bounded write probe ───────────────────────────────────────────

def test_043_the_probe_is_attempted_exactly_once(app):
    if not _is_postgres():
        pytest.skip('requires PostgreSQL')
    proof = audit.enforce_read_only(db.session)
    assert proof['read_only_probe_attempted'] is True
    assert proof['read_only_probe_count'] == 1
    assert proof['read_only_probe_bounded_to_zero_rows'] is True
    assert proof['read_only_probe_refused'] is True
    assert proof['durable_write_attempts'] == 0
    db.session.rollback()


def test_044_an_accepted_probe_is_failed():
    decision = _decide(
        read_only_proof=_clean_proof(read_only_probe_refused=False)
    )
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_READ_ONLY_PROBE_ACCEPTED in decision['failed_reasons']


def test_045_missing_probe_evidence_is_unproven():
    decision = _decide(read_only_proof={
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
    })
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_PROBE_EVIDENCE_MISSING in (
        decision['unproven_reasons']
    )


def test_046_a_definite_violation_outranks_missing_evidence():
    """An accepted probe reported alongside missing fields is still FAILED."""
    decision = _decide(read_only_proof={
        'advisory_guard_acquired': True,
        'transaction_read_only_enabled': True,
        'fingerprints_match': True,
        'read_only_probe_refused': False,
    })
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_READ_ONLY_PROBE_ACCEPTED in decision['failed_reasons']
    assert audit.UNPROVEN_PROBE_EVIDENCE_MISSING in (
        decision['unproven_reasons']
    )


# ── 47-48 Rollback and guard release ────────────────────────────────────────

def test_047_rollback_happens_on_every_exit_path():
    tree = ast.parse(RUNNER_PATH.read_text(encoding='utf-8'))
    run_function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'run'
    )
    tries = [
        node for node in ast.walk(run_function)
        if isinstance(node, ast.Try) and node.finalbody
    ]
    assert tries, 'the audit must roll back from a finally block'
    finally_source = ''.join(
        ast.dump(statement) for node in tries for statement in node.finalbody
    )
    assert 'rollback' in finally_source


def test_048_guard_release_is_proven():
    tree = ast.parse(RUNNER_PATH.read_text(encoding='utf-8'))
    run_function = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == 'run'
    )
    finally_source = ''.join(
        ast.dump(statement)
        for node in ast.walk(run_function)
        if isinstance(node, ast.Try) and node.finalbody
        for statement in node.finalbody
    )
    for marker in (
        'guard_release_attempted', 'guard_released', 'release',
    ):
        assert marker in finally_source


# ── 49-53 Scoped fingerprints against real PostgreSQL ───────────────────────

@pytest.mark.parametrize('scope,mutate', [
    (audit.SCOPE_EXACT_GAME, 'exact_game'),
    (audit.SCOPE_SLATE, 'slate'),
    (audit.SCOPE_SNAPSHOTS, 'snapshot'),
    (audit.SCOPE_LEDGER_WINDOW, 'ledger_window'),
])
def test_049_050_051_052_fingerprint_movement_is_failed(app, scope, mutate):
    """Requirements 49-52: movement in any required scope is FAILED.

    Row COUNT is deliberately held constant: the digest covers full row
    content, so an in-place edit must still be detected.
    """
    if not _is_postgres():
        pytest.skip('requires PostgreSQL')
    _seed_incident_rows()

    before = audit.scoped_fingerprints(db.session)
    assert before is not None

    if mutate == 'snapshot':
        snapshot = db.session.get(
            DashboardSnapshot, audit.INCIDENT_CANDIDATE_SNAPSHOT_ID
        )
        snapshot.status = 'ready'
    elif mutate == 'ledger_window':
        row = ScheduledGame.query.filter_by(team_id=200).first()
        row.game_date = audit.INCIDENT_SLATE_DATE - timedelta(days=2)
    else:
        row = ScheduledGame.query.filter_by(team_id=100).first()
        row.status_code = 'O'
    db.session.commit()

    after = audit.scoped_fingerprints(db.session)
    assert audit.fingerprint_scopes_match(before, after) is False
    assert scope in audit.changed_fingerprint_scopes(before, after)

    decision = _decide(read_only_proof=_clean_proof(fingerprints_match=False))
    assert decision['result'] == audit.RESULT_FAILED
    assert audit.FAILED_FINGERPRINTS_CHANGED in decision['failed_reasons']


def test_053_a_missing_fingerprint_is_unproven():
    assert audit.fingerprint_scopes_match(None, {}) is None
    decision = _decide(read_only_proof=_clean_proof(fingerprints_match=None))
    assert decision['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_FINGERPRINTS_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_fingerprints_are_stable_when_nothing_changes(app):
    if not _is_postgres():
        pytest.skip('requires PostgreSQL')
    _seed_incident_rows()
    before = audit.scoped_fingerprints(db.session)
    after = audit.scoped_fingerprints(db.session)
    assert audit.fingerprint_scopes_match(before, after) is True
    assert audit.changed_fingerprint_scopes(before, after) == []


def test_every_declared_scope_is_computed(app):
    if not _is_postgres():
        pytest.skip('requires PostgreSQL')
    _seed_incident_rows()
    digests = audit.scoped_fingerprints(
        db.session, unresolved_game_pks=[audit.INCIDENT_GAME_PK],
    )
    assert set(digests) == set(audit.FINGERPRINT_SCOPE_NAMES)


# ── 54-57 No mutation surface in the diagnostic service ─────────────────────

FORBIDDEN_CALL_NAMES = (
    'add', 'delete', 'commit', 'flush', 'merge', 'bulk_save_objects',
    'bulk_insert_mappings', 'bulk_update_mappings', 'add_all',
)


def test_054_the_service_contains_no_direct_mutation_api():
    tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in (
            FORBIDDEN_CALL_NAMES
        ):
            # `session.execute` is allowed; `session.add`/`commit` are not.
            offenders.append(func.attr)
    assert offenders == []

    source = SERVICE_PATH.read_text(encoding='utf-8')
    for marker in (
        'session.add', 'session.delete', 'session.commit', 'session.flush',
        'db.session.add', 'db.session.commit',
    ):
        assert marker not in source


def test_054b_only_one_sql_mutation_verb_exists_and_it_is_the_shared_probe():
    """The bounded probe lives in the SHARED helper, not duplicated here."""
    source = SERVICE_PATH.read_text(encoding='utf-8')
    for verb in ('INSERT ', 'DELETE ', 'UPDATE '):
        assert verb not in source.upper().replace(
            "'UPDATE'", ''
        ), f'{verb} must not appear in the diagnostic service'
    # It is imported from the PR #605 helper rather than reimplemented.
    assert 'enforce_read_only' in source
    assert 'from services.noop_qualification_candidate_audit import' in source


def test_055_no_write_capable_mode_is_reachable():
    for path in (SERVICE_PATH, RUNNER_PATH):
        source = path.read_text(encoding='utf-8')
        for marker in (
            'MODE_WRITE', 'MODE_AUTHORITATIVE', "mode='write'",
            'mode="write"', 'run_game_driven_ingestion',
        ):
            assert marker not in source, f'{marker} in {path.name}'


def test_056_no_backfill_call_is_reachable():
    for path in (SERVICE_PATH, RUNNER_PATH):
        source = path.read_text(encoding='utf-8')
        for marker in (
            'include_backfill=True', 'REASON_BACKFILL', 'run_backfill',
            'backfill(',
        ):
            assert marker not in source, f'{marker} in {path.name}'


PUBLICATION_CALLS = (
    'publish_dashboard_snapshot', 'store_dashboard_snapshot',
    'mark_dashboard_snapshot_failed', 'run_post_commit_snapshot_publication',
    'reset_failed_postgame_markers',
    'reset_fully_processed_markers_without_appearance_rows',
)


def test_057_no_snapshot_publication_call_is_reachable():
    """Matched against CALLS and IMPORTS, not prose. Both files name these
    authorities in documentation to say they are NOT reimplemented here, and a
    sentence naming a function does not make it reachable."""
    for path in (SERVICE_PATH, RUNNER_PATH):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        reachable = _called_names(tree) | _imported_names(tree)
        for marker in PUBLICATION_CALLS:
            assert marker not in reachable, f'{marker} reachable in {path.name}'


def test_the_service_never_imports_a_writer():
    """Import graph, not prose: the module docstring names the reconciliation
    service precisely to say it is not owned here."""
    tree = ast.parse(SERVICE_PATH.read_text(encoding='utf-8'))
    imported = _imported_names(tree)
    for marker in (
        'services.sync', 'services.game_driven_realization',
        'services.game_log_reconciliation', 'services.game_driven_ingestion',
    ):
        assert marker not in imported
