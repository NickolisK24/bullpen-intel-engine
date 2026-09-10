"""The bounded probe being ACCEPTED must survive as a definite FAILED result.

If the `UPDATE ... WHERE 1 = 0` proof statement succeeds, the transaction was
never read-only — the most serious thing this audit can observe about itself.

That used to be the least visible outcome: the raise unwound before any probe
detail existed, the runner caught it generically, and a definite violation was
reported as `audit_execution_error` / UNPROVEN. These tests drive the real
runner with a session where the probe is accepted and prove the verdict is
FAILED with the specific reason.
"""

import json

import pytest
from flask import Flask
from sqlalchemy import text

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from services import noop_qualification_candidate_audit as audit
from utils.db import db

import scripts.run_noop_qualification_candidate_audit as runner


SHA = 'e' * 40


@pytest.fixture(scope='module')
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


class _Args:
    expected_head_sha = SHA
    confirmation = audit.CONFIRMATION
    lookback_days = '30'
    candidate_limit = '20'
    eligible_target_count = '5'
    operator_note = ''
    artifact_dir = ''
    reference_date = '2026-07-29'


@pytest.fixture
def authorized(monkeypatch):
    for key, value in {
        'GITHUB_EVENT_NAME': 'workflow_dispatch',
        'GITHUB_REPOSITORY': 'NickolisK24/bullpen-intel-engine',
        'GITHUB_ACTOR': 'NickolisK24',
        'GITHUB_REF': 'refs/heads/main',
        'GITHUB_SHA': SHA,
        'GITHUB_RUN_ID': '1',
        'GITHUB_RUN_ATTEMPT': '1',
        'GITHUB_WORKFLOW': 'Manual No-Op Qualification Candidate Audit',
    }.items():
        monkeypatch.setenv(key, value)


@pytest.fixture
def accepted_probe(app, monkeypatch, authorized):
    """Make the bounded probe succeed, as it would if READ ONLY never applied.

    The SET statement is swallowed, so the probe runs in an ordinary writable
    transaction and is accepted — exactly the condition the contract calls a
    definite violation.
    """
    released = {'count': 0}
    original_execute = db.session.execute

    def _execute(statement, *args, **kwargs):
        rendered = str(getattr(statement, 'text', statement))
        if 'SET TRANSACTION READ ONLY' in rendered:
            return None
        return original_execute(statement, *args, **kwargs)

    monkeypatch.setattr(db.session, 'execute', _execute)
    monkeypatch.setattr(runner, 'build_app', lambda: app)

    class _Guard:
        def release(self):
            released['count'] += 1

    from services import sync_metadata

    monkeypatch.setattr(
        sync_metadata, 'acquire_public_sync_read_lock', lambda **kw: _Guard(),
    )
    return released


def _run(tmp_path):
    args = _Args()
    args.artifact_dir = str(tmp_path / 'artifacts')
    return runner.run(args)


# ── The enforcement primitive ───────────────────────────────────────────────


def test_an_accepted_probe_raises_the_structured_violation(app, monkeypatch):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
        original_execute = db.session.execute

        def _execute(statement, *args, **kwargs):
            rendered = str(getattr(statement, 'text', statement))
            if 'SET TRANSACTION READ ONLY' in rendered:
                return None
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db.session, 'execute', _execute)
        with pytest.raises(audit.ReadOnlyProbeViolation) as excinfo:
            audit.enforce_read_only(db.session)
        db.session.rollback()

        evidence = excinfo.value.evidence
        assert evidence['read_only_probe_attempted'] is True
        assert evidence['read_only_probe_count'] == 1
        assert evidence['read_only_probe_statement_class'] == 'UPDATE'
        assert evidence['read_only_probe_bounded_to_zero_rows'] is True
        assert evidence['read_only_probe_refused'] is False
        assert evidence['durable_write_attempts'] == 0


def test_the_violation_is_a_read_only_not_enforced_subclass():
    assert issubclass(audit.ReadOnlyProbeViolation, audit.ReadOnlyNotEnforced)


def test_the_violation_carries_no_sql_or_exception_text(app, monkeypatch):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
        original_execute = db.session.execute

        def _execute(statement, *args, **kwargs):
            rendered = str(getattr(statement, 'text', statement))
            if 'SET TRANSACTION READ ONLY' in rendered:
                return None
            return original_execute(statement, *args, **kwargs)

        monkeypatch.setattr(db.session, 'execute', _execute)
        with pytest.raises(audit.ReadOnlyProbeViolation) as excinfo:
            audit.enforce_read_only(db.session)
        db.session.rollback()

        encoded = json.dumps(excinfo.value.evidence)
        assert 'WHERE 1 = 0' not in encoded
        assert 'stat_correction_count' not in encoded
        assert 'game_logs' not in encoded


# ── Through the real runner ─────────────────────────────────────────────────


def test_an_accepted_probe_produces_a_definite_failed_verdict(
    app, accepted_probe, tmp_path,
):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
    document = _run(tmp_path)

    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_FAILED
    assert audit.FAILED_PROBE_ACCEPTED in verdict['failed_reasons']
    assert verdict['exit_code'] == 1


def test_the_accepted_probe_is_not_reduced_to_a_generic_error(
    app, accepted_probe, tmp_path,
):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
    verdict = _run(tmp_path)['verdict']
    assert 'audit_execution_error' not in verdict['unproven_reasons']
    assert verdict['result'] != audit.RESULT_UNPROVEN


def test_the_artifact_preserves_the_probe_evidence(
    app, accepted_probe, tmp_path,
):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
    proof = _run(tmp_path)['read_only_proof']

    assert proof['read_only_probe_attempted'] is True
    assert proof['read_only_probe_count'] == 1
    assert proof['read_only_probe_statement_class'] == 'UPDATE'
    assert proof['read_only_probe_bounded_to_zero_rows'] is True
    assert proof['read_only_probe_refused'] is False
    assert proof['durable_write_attempts'] == 0


def test_the_artifact_contains_no_raw_sql(app, accepted_probe, tmp_path):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
    document = _run(tmp_path)
    encoded = json.dumps(document, default=str)
    assert 'WHERE 1 = 0' not in encoded
    assert 'stat_correction_count' not in encoded


def test_the_guard_is_still_released_after_a_probe_violation(
    app, accepted_probe, tmp_path,
):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
    document = _run(tmp_path)
    assert accepted_probe['count'] == 1
    proof = document['read_only_proof']
    assert proof['advisory_guard_acquired'] is True
    assert proof['advisory_guard_release_attempted'] is True
    assert proof['advisory_guard_released'] is True


def test_durable_rows_are_unchanged_after_a_probe_violation(
    app, accepted_probe, tmp_path,
):
    """The probe is bounded to zero rows, so even accepted it changes nothing."""
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
        before = audit.table_fingerprints(db.session)

    _run(tmp_path)

    with app.app_context():
        db.session.rollback()
        after = audit.table_fingerprints(db.session)
    assert audit.fingerprints_match(before, after), (
        audit.changed_tables(before, after)
    )


def test_the_transaction_is_rolled_back_after_a_probe_violation(
    app, accepted_probe, tmp_path,
):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('requires PostgreSQL')
    _run(tmp_path)
    with app.app_context():
        # A usable session proves nothing was left pending.
        assert db.session.execute(text('SELECT 1')).scalar() == 1
        db.session.rollback()
