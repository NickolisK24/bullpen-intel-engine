"""Durable execution ledger for the reviewed official pitching-line repair (2026).

Covers the model's stored-state invariants — a stored row may only ever be ``completed``,
one completed execution per approved fingerprint, and action counts that sum to the recorded
total — plus the migration's chain integrity and reversibility.
"""

from datetime import date, datetime
from pathlib import Path
import re

import pytest
from flask import Flask
from sqlalchemy.exc import IntegrityError

from models.official_pitching_line_repair_execution import (
    OfficialPitchingLineRepairExecution as Ledger,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / 'backend' / 'migrations' / 'versions'
LEDGER_REVISION = 'c7b3e5a91d48'
CURRENT_ALEMBIC_HEAD = 'b9d4e17c3a80'
PRIOR_REVISION = 'a4f1c7e9b3d2'
MIGRATION_PATH = (MIGRATIONS_DIR
                  / f'{LEDGER_REVISION}_add_official_pitching_line_repair_executions.py')

FINGERPRINT = '3ee2ea06492e8161bf7b278228d6f778e24048452366e3c2502ae42e0365216b'


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _row(**overrides):
    values = {
        'capability': 'official_pitching_line_repair_apply_2026_v1',
        'approved_manifest_fingerprint': FINGERPRINT,
        'regenerated_manifest_fingerprint': FINGERPRINT,
        'planner_git_sha': 'b0850719c7ab2c4e9ee232758cd57ba25030364b',
        'apply_git_sha': 'b0850719c7ab2c4e9ee232758cd57ba25030364b',
        'season': 2026,
        'as_of_date': date(2026, 7, 25),
        'accepted_baseline_version': 'v2',
        'amendment_id': 'defect_baseline_amendment_1_brandyn_garcia_hits_allowed',
        'status': Ledger.STATUS_COMPLETED,
        'identity_action_count': 70,
        'insert_action_count': 445,
        'update_action_count': 160,
        'total_action_count': 675,
        'started_at': datetime(2026, 7, 28, 12, 0, 0),
        'completed_at': datetime(2026, 7, 28, 12, 5, 0),
        'committed_at': datetime(2026, 7, 28, 12, 5, 0),
        'execution_summary': {'applied': 675},
        'precondition_summary': {'all_passed': True},
        'verification_summary': {'all_passed': True},
    }
    values.update(overrides)
    return Ledger(**values)


# ═══════════════ Stored-state invariants ════════════════════════════════════
def test_a_completed_execution_row_stores(app):
    db.session.add(_row())
    db.session.commit()
    stored = db.session.query(Ledger).one()
    assert stored.status == 'completed'
    assert stored.total_action_count == 675
    assert stored.to_dict()['approved_manifest_fingerprint'] == FINGERPRINT
    assert stored.to_dict()['as_of_date'] == '2026-07-25'


def test_only_completed_is_a_storable_status(app):
    # A rolled-back or precondition-failed attempt performs no writes, so it has nothing to
    # record. The database refuses any other status rather than trusting writer discipline.
    assert Ledger.STATUSES == ('completed',)
    db.session.add(_row(status='rolled_back'))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.query(Ledger).count() == 0


def test_a_second_completed_execution_for_the_same_fingerprint_is_refused(app):
    db.session.add(_row())
    db.session.commit()
    db.session.add(_row(regenerated_manifest_fingerprint='f' * 64))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.query(Ledger).count() == 1


def test_a_different_approved_fingerprint_is_a_different_execution(app):
    # The uniqueness is per approved fingerprint, not global: this table is not a lock on
    # the capability, it is a lock on one exact approved manifest.
    db.session.add(_row())
    db.session.commit()
    db.session.add(_row(approved_manifest_fingerprint='a' * 64,
                        regenerated_manifest_fingerprint='a' * 64))
    db.session.commit()
    assert db.session.query(Ledger).count() == 2


def test_action_counts_must_sum_to_the_recorded_total(app):
    db.session.add(_row(total_action_count=674))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()
    assert db.session.query(Ledger).count() == 0


def test_negative_action_counts_are_refused(app):
    db.session.add(_row(identity_action_count=-1, total_action_count=604))
    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_the_approved_and_regenerated_fingerprints_are_stored_separately(app):
    # Both values are retained. A reviewer must be able to read what was approved AND what
    # was regenerated, not a single value asserting the two agreed.
    columns = {c.name for c in Ledger.__table__.columns}
    assert 'approved_manifest_fingerprint' in columns
    assert 'regenerated_manifest_fingerprint' in columns
    row = _row()
    assert row.approved_manifest_fingerprint == row.regenerated_manifest_fingerprint


def test_every_governed_ledger_column_exists(app):
    columns = {c.name for c in Ledger.__table__.columns}
    for required in (
        'id', 'capability', 'approved_manifest_fingerprint',
        'regenerated_manifest_fingerprint', 'planner_git_sha', 'apply_git_sha',
        'season', 'as_of_date', 'accepted_baseline_version', 'amendment_id', 'status',
        'identity_action_count', 'insert_action_count', 'update_action_count',
        'total_action_count', 'started_at', 'completed_at', 'committed_at',
        'execution_summary', 'precondition_summary', 'verification_summary',
    ):
        assert required in columns


# ═══════════════ Migration ══════════════════════════════════════════════════
def test_the_ledger_migration_chains_onto_the_prior_head_as_the_single_head():
    text = MIGRATION_PATH.read_text(encoding='utf-8')
    assert f"revision = '{LEDGER_REVISION}'" in text
    assert f"down_revision = '{PRIOR_REVISION}'" in text

    revisions, downs = {}, set()
    for path in MIGRATIONS_DIR.glob('*.py'):
        body = path.read_text(encoding='utf-8')
        rev = re.search(r"^revision = '([^']+)'", body, re.M)
        down = re.search(r"^down_revision = (.+)$", body, re.M)
        if rev:
            revisions[rev.group(1)] = path.name
        if down:
            downs.update(re.findall(r"'([^']+)'", down.group(1)))
    heads = [r for r in revisions if r not in downs]
    # The ledger migration is no longer the tip — the game-driven ingestion
    # work-state checkpoint chains onto it — but chain integrity (exactly one
    # head, and this migration still chaining onto its prior revision) is what
    # this guard exists for, and both still hold.
    assert heads == [CURRENT_ALEMBIC_HEAD]


def test_the_ledger_migration_is_additive_and_reversible():
    text = MIGRATION_PATH.read_text(encoding='utf-8')
    assert "op.create_table(\n        'official_pitching_line_repair_executions'," in text
    assert "op.drop_table('official_pitching_line_repair_executions')" in text
    # Purely additive: it touches no existing table and modifies no existing row.
    assert 'game_logs' not in text
    assert 'pitchers' not in text
    assert 'UPDATE' not in text
    assert 'op.execute' not in text


def test_the_ledger_migration_enforces_the_governed_invariants():
    text = MIGRATION_PATH.read_text(encoding='utf-8')
    assert 'uq_oplr_executions_approved_fingerprint' in text
    assert 'ck_oplr_executions_status_completed' in text
    assert 'ck_oplr_executions_action_counts_reconcile' in text


def test_the_ledger_model_is_registered_with_the_application():
    text = (REPO_ROOT / 'backend' / 'app.py').read_text(encoding='utf-8')
    assert 'from models.official_pitching_line_repair_execution import' in text
