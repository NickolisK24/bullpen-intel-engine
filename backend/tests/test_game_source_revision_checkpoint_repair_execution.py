"""Game 824487 checkpoint repair — driven against real PostgreSQL.

Transactions, advisory locks, row locks, content fingerprints, statement
accounting, and the single-column UPDATE ARE the behaviour under test, so they
run against a live database rather than a simulation. The canonical path is
real too: the real planner, the real box-score parser, the real appearance
extractor, the real reconciliation planner, and the real game-driven lane
writing the checkpoint these tests then repair. Only the MLB client is stood in
for — and it is stood in for behind the package's own counting guard.

The two governed revisions are monkeypatched, never parameterized. Production
has no way to supply a different value: the constants are reviewed literals
with no input, no argument, and no environment variable that can reach them.
A test that needs different digests reaches into the module, which is exactly
the kind of access production does not have.
"""

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import text

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

# Imported so ``create_all`` builds every table the scoped fingerprints cover.
# A scope whose table is absent makes the whole fingerprint uncomputable, which
# is UNPROVEN — correct in production, and useless as a test bed.
import models.completed_game_context  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.prospect  # noqa: F401
import models.sync_failure  # noqa: F401
import models.team_game_pitching_split  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from scripts import run_game_source_revision_audit as audit_runner
from scripts import run_game_source_revision_checkpoint_repair as runner
from services import game_source_revision_audit as audit
from services import game_source_revision_checkpoint_repair as repair
from services import game_driven_ingestion as lane
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


GAME_PK = repair.GAME_PK
HOME_ARMS = [790001, 790002, 790003, 790004, 790005, 790006]
AWAY_ARMS = [790011, 790012, 790013, 790014, 790015, 790016]
ALL_ARMS = HOME_ARMS + AWAY_ARMS

OLD_REVISION = 'b' * 64
SHA = 'f' * 40


postgres_only = pytest.mark.skipif(
    not __import__('os').environ.get('TEST_DATABASE_URL', '').startswith(
        'postgresql'
    ),
    reason='requires PostgreSQL',
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


def _lines(*, home_outs=None, away_outs=None, strikeouts=None):
    """Twelve official lines: one start and five relievers per side."""
    home_outs = home_outs or [18, 3, 3, 3, 3, 3]
    away_outs = away_outs or [15, 3, 3, 6, 3, 3]
    entries = []
    for arms, side, outs_by_arm in (
        (HOME_ARMS, 'home', home_outs), (AWAY_ARMS, 'away', away_outs),
    ):
        for index, (mlb_id, outs) in enumerate(zip(arms, outs_by_arm)):
            entries.append((mlb_id, side, pitching_stats(
                innings=f'{outs // 3}.{outs % 3}',
                games_started=1 if index == 0 else 0,
                strikeouts=(index + 1) if strikeouts is None else strikeouts,
                pitches=15 + index,
                batters_faced=4 + index,
            )))
    return entries


def _seed(monkeypatch, *, lines=None):
    """Seed game 824487 and complete its work item through the real lane."""
    _schedule(GAME_PK, game_date=REFERENCE)
    for mlb_id in HOME_ARMS:
        _pitcher(mlb_id, team_id=HOME_TEAM)
    for mlb_id in AWAY_ARMS:
        _pitcher(mlb_id, team_id=AWAY_TEAM)
    payload = boxscore(lines or _lines())
    client = BoxscoreClient({GAME_PK: payload})
    monkeypatch.setattr(sync_service, 'mlb_client', client)
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()
    return payload


def _work_item():
    return GameIngestionWorkItem.query.filter_by(mlb_game_pk=GAME_PK).one()


def _observed_plan_fingerprint():
    """The plan fingerprint the seeded game actually produces.

    Read through the SAME canonical path the package uses, so the literal the
    tests pin is a real observation of this fixture rather than a number
    copied from production into a test that could then never fail.
    """
    observed = audit_runner.observe_current_source(None)
    db.session.rollback()
    return (observed.get('plan') or {}).get('reconciliation_plan_fingerprint')


def _install(monkeypatch, app, *, current_revision, existing_revision,
             plan_fingerprint=None):
    """Point the package's locked literals at this fixture's values."""
    monkeypatch.setattr(
        repair, 'INTENDED_SOURCE_REVISION', current_revision,
    )
    monkeypatch.setattr(
        repair, 'EXPECTED_EXISTING_SOURCE_REVISION', existing_revision,
    )
    if plan_fingerprint is not None:
        monkeypatch.setattr(
            repair, 'EXPECTED_PLAN_FINGERPRINT', plan_fingerprint,
        )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    for key, value in (
        ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
        ('GITHUB_REPOSITORY', repair.REQUIRED_REPOSITORY),
        ('GITHUB_ACTOR', repair.REQUIRED_ACTOR),
        ('GITHUB_REF', repair.REQUIRED_REF),
        ('GITHUB_SHA', SHA),
        ('GITHUB_RUN_ID', '1'),
        ('GITHUB_RUN_ATTEMPT', '1'),
        ('GITHUB_WORKFLOW', 'test'),
    ):
        monkeypatch.setenv(key, value)


def _args(operation='verify', **overrides):
    payload = {
        'operation': operation,
        'expected_main_sha': SHA,
        'confirmation': repair.CONFIRMATIONS.get(operation, ''),
        'operator_note': '',
        'artifact_dir': 'unused',
    }
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _prepare(monkeypatch, app, *, existing=OLD_REVISION, lines=None):
    """Seed, then set the checkpoint to the 'old' value this run repairs."""
    _seed(monkeypatch, lines=lines)
    item = _work_item()
    current = item.source_revision
    assert current, 'the lane must have recorded a source revision'
    db.session.execute(text(
        'UPDATE game_ingestion_work_items SET source_revision = :old '
        'WHERE mlb_game_pk = :pk'
    ), {'old': existing, 'pk': GAME_PK})
    db.session.commit()
    db.session.expire_all()
    _install(
        monkeypatch, app,
        current_revision=current, existing_revision=existing,
        plan_fingerprint=_observed_plan_fingerprint(),
    )
    return current


def _run(operation='verify', **overrides):
    return runner.run(_args(operation, **overrides))


# ── Seed sanity: the bed is real ────────────────────────────────────────────

@postgres_only
def test_the_lane_really_writes_a_completed_checkpoint(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        item = _work_item()
        assert item.status == GameIngestionWorkItem.STATUS_COMPLETED
        assert item.rows_expected == 12
        assert item.rows_reconciled == 12
        assert item.source_revision
        assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 12


# ── Verify: read-only under every outcome ───────────────────────────────────

@postgres_only
def test_verify_reports_the_repair_required_and_safe_without_writing(
    app, monkeypatch,
):
    with app.app_context():
        current = _prepare(monkeypatch, app)
        before = _work_item().updated_at
        document = _run('verify')

        verdict = document['verdict']
        assert verdict['result'] == repair.RESULT_VERIFIED_REQUIRED_AND_SAFE
        assert verdict['exit_code'] == 0
        assert verdict['mutation_performed'] is False
        assert verdict['preconditions_all_satisfied'] is True

        db.session.expire_all()
        item = _work_item()
        assert item.source_revision == OLD_REVISION
        assert item.updated_at == before
        assert item.source_revision != current


@postgres_only
def test_verify_proves_read_only_and_a_refused_probe(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('verify')
        proof = document['read_only_proof']
        assert proof['read_only_transaction_enabled'] is True
        assert proof['read_only_probe_refused'] is True
        assert proof['durable_write_attempts'] == 0
        assert proof['probe_validation']['probe_evidence_valid'] is True


@postgres_only
def test_verify_acquires_and_provably_releases_the_public_sync_lock(
    app, monkeypatch,
):
    from services import sync_metadata

    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('verify')
        lock = document['advisory_lock']
        assert lock['guard_acquired'] is True
        assert lock['guard_released'] is True
        assert lock['lifecycle_complete'] is True
        # Releasing makes it acquirable again. That IS the release proof.
        again = sync_metadata.acquire_public_sync_read_lock(
            source=sync_metadata.SOURCE_MANUAL,
        )
        assert again is not None
        again.release()


@postgres_only
def test_verify_creates_no_sync_run_row(app, monkeypatch):
    from models.sync_run import SyncRun

    with app.app_context():
        _prepare(monkeypatch, app)
        before = SyncRun.query.count()
        _run('verify')
        db.session.expire_all()
        assert SyncRun.query.count() == before


@postgres_only
def test_verify_moves_no_governed_scope_fingerprint(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('verify')
        assert document['fingerprints']['changed_during_read_phase'] == []


@postgres_only
def test_verify_spends_exactly_one_bounded_box_score_call(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('verify')
        calls = document['source_call_report']
        assert calls['total_calls_issued'] == 1
        assert calls['duplicate_boxscore_requests'] == 0
        assert calls['hidden_call_detected'] is False
        assert calls['reported_equals_actual'] is True


# ── Apply: the one permitted change ─────────────────────────────────────────

@postgres_only
def test_apply_changes_exactly_the_one_column_on_the_one_row(
    app, monkeypatch,
):
    with app.app_context():
        current = _prepare(monkeypatch, app)
        document = _run('apply')

        verdict = document['verdict']
        assert verdict['result'] == repair.RESULT_APPLIED, verdict
        assert verdict['exit_code'] == 0
        assert verdict['mutation_performed'] is True

        db.session.expire_all()
        item = _work_item()
        assert item.source_revision == current
        assert GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).count() == 1


@postgres_only
def test_apply_reports_the_changed_columns_as_exactly_the_permitted_pair(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('apply')
        scope = document['mutation_ledger']['scope_evaluation']
        assert scope['observed_changed_columns'] == [
            'source_revision', 'updated_at',
        ]
        assert scope['changed_columns_are_exactly_permitted'] is True
        assert scope['unpermitted_changed_columns'] == []
        assert scope['governed_changed_columns'] == ['source_revision']
        assert scope['automatic_bookkeeping_changed_columns'] == ['updated_at']
        assert scope['mutation_within_scope'] is True


@postgres_only
def test_apply_really_advances_the_bookkeeping_timestamp(app, monkeypatch):
    """The disclosure is checked against the database, not a comment."""
    with app.app_context():
        _prepare(monkeypatch, app)
        before = _work_item().updated_at
        _run('apply')
        db.session.expire_all()
        assert _work_item().updated_at > before


@postgres_only
def test_apply_issues_exactly_one_write_statement_affecting_one_row(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('apply')
        statements = document['mutation_ledger']['statement_report']
        assert statements['exactly_one_target_update'] is True
        assert statements['no_other_write_statement'] is True
        assert statements['target_table_affected_rows'] == 1
        assert document['mutation_ledger']['affected_row_count'] == 1


@postgres_only
def test_apply_creates_nothing_and_deletes_nothing(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('apply')
        guard = document['mutation_ledger']['guard_observations']
        assert guard['created_object_count'] == 0
        assert guard['deleted_object_count'] == 0
        assert guard['mutated_types'] == ['GameIngestionWorkItem']
        assert guard['mutated_attributes'] == ['source_revision']


@postgres_only
def test_apply_moves_only_the_target_table_and_no_other_governed_scope(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run('apply')
        scope = document['mutation_ledger']['scope_evaluation']
        assert scope['changed_fingerprint_tables'] == [
            [audit.SCOPE_EXACT_GAME, repair.TARGET_TABLE],
        ]
        assert scope['unexpected_changed_fingerprint_tables'] == []
        assert scope['out_of_scope_unchanged'] is True


@postgres_only
def test_apply_leaves_every_canonical_appearance_row_untouched(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        before = {
            row.id: (
                row.strikeouts, row.earned_runs, row.innings_pitched_outs,
                row.appearance_team_id, row.stat_correction_count,
                row.last_stat_correction_at,
            )
            for row in GameLog.query.filter_by(mlb_game_pk=GAME_PK).all()
        }
        _run('apply')
        db.session.expire_all()
        after = {
            row.id: (
                row.strikeouts, row.earned_runs, row.innings_pitched_outs,
                row.appearance_team_id, row.stat_correction_count,
                row.last_stat_correction_at,
            )
            for row in GameLog.query.filter_by(mlb_game_pk=GAME_PK).all()
        }
        assert after == before


@postgres_only
def test_apply_leaves_another_games_checkpoint_untouched(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        other = GameIngestionWorkItem(
            mlb_game_pk=999001, represented_date=REFERENCE,
            game_date=REFERENCE, status=GameIngestionWorkItem.STATUS_PLANNED,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
            source_revision=OLD_REVISION,
        )
        db.session.add(other)
        db.session.commit()
        other_id = other.id
        before = other.updated_at

        _run('apply')

        db.session.expire_all()
        neighbour = db.session.get(GameIngestionWorkItem, other_id)
        assert neighbour.source_revision == OLD_REVISION
        assert neighbour.updated_at == before


@postgres_only
def test_apply_is_idempotent_a_second_run_reports_not_required(
    app, monkeypatch,
):
    with app.app_context():
        current = _prepare(monkeypatch, app)
        assert _run('apply')['verdict']['result'] == repair.RESULT_APPLIED
        db.session.expire_all()
        stamped = _work_item().updated_at

        second = _run('apply')
        assert second['verdict']['result'] == repair.RESULT_NOT_REQUIRED
        assert second['verdict']['exit_code'] == 0
        assert second['verdict']['mutation_performed'] is False

        db.session.expire_all()
        item = _work_item()
        assert item.source_revision == current
        # A no-op run does not restamp the bookkeeping timestamp either.
        assert item.updated_at == stamped


@postgres_only
def test_a_verify_run_after_an_apply_reports_not_required(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        _run('apply')
        document = _run('verify')
        assert document['verdict']['result'] == repair.RESULT_NOT_REQUIRED


# ── Refusals: every one of them writes nothing ──────────────────────────────

def _assert_untouched(before_revision, before_updated_at):
    db.session.expire_all()
    item = _work_item()
    assert item.source_revision == before_revision
    assert item.updated_at == before_updated_at


@postgres_only
def test_apply_refuses_when_the_existing_value_is_not_the_expected_one(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app, existing='d' * 64)
        monkeypatch.setattr(
            repair, 'EXPECTED_EXISTING_SOURCE_REVISION', OLD_REVISION,
        )
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert document['verdict']['exit_code'] == 2
        assert repair.REFUSED_EXISTING_REVISION_UNEXPECTED in (
            document['verdict']['refusal_reasons']
        )
        assert document['mutation_ledger']['apply_attempted'] is False
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_work_item_is_missing(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        db.session.execute(text(
            'DELETE FROM game_ingestion_work_items WHERE mlb_game_pk = :pk'
        ), {'pk': GAME_PK})
        db.session.commit()

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_WORK_ITEM_MISSING in (
            document['verdict']['refusal_reasons']
        )
        # The prohibition that matters most: it did not create one.
        assert GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).count() == 0
        assert document['mutation_ledger']['apply_attempted'] is False


@postgres_only
def test_apply_refuses_when_the_checkpoint_is_not_completed(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        db.session.execute(text(
            'UPDATE game_ingestion_work_items SET status = :status, '
            'completed_at = NULL, rows_reconciled = 0 '
            'WHERE mlb_game_pk = :pk'
        ), {'status': GameIngestionWorkItem.STATUS_PLANNED, 'pk': GAME_PK})
        db.session.commit()
        db.session.expire_all()
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_STATUS_NOT_COMPLETED in (
            document['verdict']['refusal_reasons']
        )
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_today_source_produces_a_different_digest(
    app, monkeypatch,
):
    """The intended value is recomputed from the source, never assumed."""
    with app.app_context():
        _prepare(monkeypatch, app)
        monkeypatch.setattr(repair, 'INTENDED_SOURCE_REVISION', 'e' * 64)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_CURRENT_REVISION_NOT_INTENDED in (
            document['verdict']['refusal_reasons']
        )
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_a_governed_field_differs_from_storage(
    app, monkeypatch,
):
    """A data defect is a DATA repair. This package is not one."""
    with app.app_context():
        _prepare(monkeypatch, app)
        db.session.execute(text(
            'UPDATE game_logs SET strikeouts = strikeouts + 5 '
            'WHERE mlb_game_pk = :pk'
        ), {'pk': GAME_PK})
        db.session.commit()
        db.session.expire_all()
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        reasons = document['verdict']['refusal_reasons']
        assert repair.REFUSED_GOVERNED_FIELD_DIFFERS in reasons
        assert repair.REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION in reasons
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_canonical_storage_is_missing_an_appearance(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        victim = GameLog.query.filter_by(mlb_game_pk=GAME_PK).first()
        db.session.execute(text('DELETE FROM game_logs WHERE id = :id'),
                           {'id': victim.id})
        db.session.commit()
        db.session.expire_all()
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] in (
            repair.RESULT_REFUSED, repair.RESULT_UNPROVEN,
        )
        assert document['verdict']['mutation_performed'] is False
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_source_cannot_be_fetched(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({}, fail_games=(GAME_PK,)),
        )
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_UNPROVEN
        assert document['verdict']['mutation_performed'] is False
        assert repair.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE in (
            document['verdict']['unproven_reasons']
        )
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_represented_date_does_not_match(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        db.session.execute(text(
            "UPDATE game_ingestion_work_items "
            "SET represented_date = DATE '2026-07-28' WHERE mlb_game_pk = :pk"
        ), {'pk': GAME_PK})
        db.session.commit()
        db.session.expire_all()
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_REPRESENTED_DATE_MISMATCH in (
            document['verdict']['refusal_reasons']
        )
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_checkpoint_row_counts_disagree(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        # The completion CHECK constraint forbids an inconsistent COMPLETED
        # row, so the population expectation is broken the only way the schema
        # permits: by removing the recorded expectation from a resolved row.
        db.session.execute(text(
            'UPDATE game_ingestion_work_items SET status = :status, '
            'rows_expected = NULL WHERE mlb_game_pk = :pk'
        ), {'status': GameIngestionWorkItem.STATUS_SUPERSEDED, 'pk': GAME_PK})
        db.session.commit()
        db.session.expire_all()
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        reasons = document['verdict']['refusal_reasons']
        assert repair.REFUSED_POPULATION_EXPECTATION_UNVERIFIED in reasons
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_plan_fingerprint_changed(app, monkeypatch):
    """Clean action counts do not rescue a plan whose fingerprint moved."""
    with app.app_context():
        _prepare(monkeypatch, app)
        monkeypatch.setattr(repair, 'EXPECTED_PLAN_FINGERPRINT', 'f' * 64)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_PLAN_FINGERPRINT_CHANGED in (
            document['verdict']['refusal_reasons']
        )
        # The canonical plan itself is still clean — only the fingerprint
        # gate refused.
        assert document['canonical_plan']['proposes_mutation'] is False
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_game_no_longer_has_twelve_appearances(
    app, monkeypatch,
):
    with app.app_context():
        eleven = _lines()[:11]
        _prepare(monkeypatch, app, lines=eleven)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] in (
            repair.RESULT_REFUSED, repair.RESULT_UNPROVEN,
        )
        assert document['verdict']['mutation_performed'] is False
        assert repair.REFUSED_APPEARANCE_COUNT_UNEXPECTED in (
            document['verdict']['refusal_reasons']
        )
        _assert_untouched(*before)


@postgres_only
def test_apply_refuses_when_the_target_row_carries_an_error_class(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        db.session.execute(text(
            'UPDATE game_ingestion_work_items SET error_class = :cls '
            'WHERE mlb_game_pk = :pk'
        ), {'cls': 'appearance_extraction_failed', 'pk': GAME_PK})
        db.session.commit()
        db.session.expire_all()
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_TARGET_ERROR_STATE in (
            document['verdict']['refusal_reasons']
        )
        _assert_untouched(*before)


@postgres_only
def test_apply_records_the_pre_and_post_commit_verification(app, monkeypatch):
    """The commit is conditioned on the in-transaction value."""
    with app.app_context():
        current = _prepare(monkeypatch, app)
        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_APPLIED
        ledger = document['mutation_ledger']
        transaction = ledger['transaction_state']
        assert transaction['in_transaction_value_is_intended'] is True
        assert transaction['post_commit_transaction_read_only'] is True
        assert ledger['post_commit_value_is_intended'] is True
        assert ledger['post_commit_row_count'] == 1
        assert ledger['commits_performed'] == 1
        assert ledger['observed_value_after'] == current
        assert ledger['mutation_timestamp']


# ── Authorization ───────────────────────────────────────────────────────────

@postgres_only
def test_a_verify_confirmation_can_never_start_an_apply_run(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run(
            'apply', confirmation=repair.CONFIRMATIONS['verify'],
        )
        assert document['verdict']['result'] == repair.RESULT_FAILED
        assert repair.FAILED_CONFIRMATION_MISMATCH in (
            document['verdict']['failed_reasons']
        )
        assert document['verdict']['mutation_performed'] is False
        _assert_untouched(*before)


@postgres_only
def test_an_apply_confirmation_does_not_satisfy_a_verify_run(app, monkeypatch):
    with app.app_context():
        _prepare(monkeypatch, app)
        document = _run(
            'verify', confirmation=repair.CONFIRMATIONS['apply'],
        )
        assert document['verdict']['result'] == repair.RESULT_FAILED


@postgres_only
def test_an_unknown_operation_never_opens_a_database_session(
    app, monkeypatch,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply-everything', confirmation='whatever')
        assert document['verdict']['result'] == repair.RESULT_FAILED
        assert repair.FAILED_OPERATION_UNKNOWN in (
            document['verdict']['failed_reasons']
        )
        assert document['read_only_proof'] == {}
        _assert_untouched(*before)


@postgres_only
@pytest.mark.parametrize('key,value', [
    ('GITHUB_EVENT_NAME', 'schedule'),
    ('GITHUB_REPOSITORY', 'someone-else/fork'),
    ('GITHUB_ACTOR', 'someone-else'),
    ('GITHUB_REF', 'refs/heads/feature'),
    ('GITHUB_SHA', 'a' * 40),
])
def test_an_unauthorized_context_refuses_before_any_observation(
    app, monkeypatch, key, value,
):
    with app.app_context():
        _prepare(monkeypatch, app)
        monkeypatch.setenv(key, value)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_FAILED
        assert document['verdict']['mutation_performed'] is False
        assert document['read_only_proof'] == {}
        _assert_untouched(*before)


SCANNER = Path(__file__).resolve().parents[1] / (
    'scripts/scan_forbidden_artifact_content.py'
)


def _scan(directory):
    return subprocess.run(
        [sys.executable, str(SCANNER), '--directory', str(directory)],
        capture_output=True, text=True, check=False,
    )


@postgres_only
def test_real_verify_and_apply_artifacts_pass_the_repository_scanner(
    app, monkeypatch, tmp_path,
):
    """The pre-upload gate, run against artifacts a real run produced.

    Not a hand-built document: these come from the full runner, through the
    real lane, the real planner, and the real reconciler, in both operations.
    """
    with app.app_context():
        _prepare(monkeypatch, app)

        verify_dir = tmp_path / 'verify'
        code = runner.main([
            '--operation', 'verify',
            '--expected-main-sha', SHA,
            '--confirmation', repair.CONFIRMATIONS['verify'],
            '--artifact-dir', str(verify_dir),
        ])
        assert code == 0
        assert _scan(verify_dir).returncode == 0

        apply_dir = tmp_path / 'apply'
        code = runner.main([
            '--operation', 'apply',
            '--expected-main-sha', SHA,
            '--confirmation', repair.CONFIRMATIONS['apply'],
            '--artifact-dir', str(apply_dir),
        ])
        assert code == 0
        assert _scan(apply_dir).returncode == 0

        for directory, expected in (
            (verify_dir, repair.RESULT_VERIFIED_REQUIRED_AND_SAFE),
            (apply_dir, repair.RESULT_APPLIED),
        ):
            payload = json.loads(
                (directory / runner.SUMMARY_JSON).read_text(encoding='utf-8')
            )
            assert payload['verdict']['result'] == expected
            assert sorted(path.name for path in directory.iterdir()) == (
                sorted(runner.ARTIFACT_FILES)
            )

        # The verify artifact proposes; only the apply artifact executes.
        verify_ledger = json.loads(
            (verify_dir / runner.MUTATION_LEDGER_JSON).read_text(
                encoding='utf-8'
            )
        )
        apply_ledger = json.loads(
            (apply_dir / runner.MUTATION_LEDGER_JSON).read_text(
                encoding='utf-8'
            )
        )
        assert verify_ledger['apply_attempted'] is False
        assert verify_ledger['committed'] is None
        assert verify_ledger['mutation_performed'] is False
        assert apply_ledger['apply_attempted'] is True
        assert apply_ledger['committed'] is True
        assert apply_ledger['mutation_performed'] is True
        assert apply_ledger['commits_performed'] == 1


# ── Concurrency ─────────────────────────────────────────────────────────────

@postgres_only
def test_a_contended_public_sync_lock_stops_the_run_without_waiting(
    app, monkeypatch,
):
    from services import sync_metadata

    with app.app_context():
        _prepare(monkeypatch, app)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        held = sync_metadata.acquire_public_sync_read_lock(
            source=sync_metadata.SOURCE_MANUAL,
        )
        try:
            document = _run('apply')
        finally:
            held.release()

        assert document['verdict']['result'] == repair.RESULT_UNPROVEN
        assert repair.UNPROVEN_ADVISORY_LOCK_UNAVAILABLE in (
            document['verdict']['unproven_reasons']
        )
        assert document['verdict']['mutation_performed'] is False
        assert document['halt_stage'] == 'advisory_lock'
        _assert_untouched(*before)


@postgres_only
def test_a_row_that_moved_between_observation_and_lock_is_refused(
    app, monkeypatch,
):
    """Observation and the write transaction are not one instant."""
    with app.app_context():
        current = _prepare(monkeypatch, app)
        real_apply = runner.apply_repair

        def _moving_apply(*, target_row_id, observed_snapshot):
            # Simulate a concurrent writer landing between the two phases by
            # presenting a snapshot the locked row no longer matches.
            stale = dict(observed_snapshot or {}, correction_count=99)
            return real_apply(
                target_row_id=target_row_id, observed_snapshot=stale,
            )

        monkeypatch.setattr(runner, 'apply_repair', _moving_apply)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_REFUSED
        assert repair.REFUSED_CONCURRENT_MODIFICATION in (
            document['verdict']['refusal_reasons']
        )
        ledger = document['mutation_ledger']
        assert ledger['revalidated_under_lock'] is False
        assert ledger['committed'] is None
        _assert_untouched(*before)
        assert _work_item().source_revision != current


@postgres_only
def test_a_scope_guard_violation_rolls_back_rather_than_committing(
    app, monkeypatch,
):
    """A violation seen before COMMIT is undone, not committed and reported."""
    with app.app_context():
        _prepare(monkeypatch, app)
        item = _work_item()
        before = (item.source_revision, item.updated_at)

        real_checks = repair.MutationScopeGuard.checks
        monkeypatch.setattr(
            repair.MutationScopeGuard, 'checks',
            lambda self, **kwargs: dict(
                real_checks(self, **kwargs), no_object_was_created=False,
            ),
        )

        document = _run('apply')
        assert document['verdict']['result'] == repair.RESULT_FAILED
        assert repair.FAILED_MUTATION_SCOPE_EXCEEDED in (
            document['verdict']['failed_reasons']
        )
        assert document['verdict']['mutation_performed'] is False
        _assert_untouched(*before)


# ── Statement and snapshot helpers, against the real schema ─────────────────

@postgres_only
def test_the_row_snapshot_covers_every_mapped_column(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        snapshot = repair.row_snapshot(_work_item())
        columns = {
            column.key
            for column in GameIngestionWorkItem.__table__.columns
        }
        assert set(snapshot) == columns
        assert 'updated_at' in snapshot and 'id' in snapshot


@postgres_only
def test_the_out_of_scope_digest_excludes_the_target_game(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        first = repair.out_of_scope_fingerprint(db.session)
        assert first is not None
        assert first['table'] == repair.TARGET_TABLE

        db.session.execute(text(
            'UPDATE game_ingestion_work_items SET source_revision = :rev '
            'WHERE mlb_game_pk = :pk'
        ), {'rev': OLD_REVISION, 'pk': GAME_PK})
        db.session.commit()
        # Moving the target game must not move the complement digest.
        assert repair.out_of_scope_fingerprint(db.session) == first

        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=999002, represented_date=REFERENCE,
            status=GameIngestionWorkItem.STATUS_PLANNED,
            candidate_reason=GameIngestionWorkItem.REASON_NEWLY_FINAL,
            criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        ))
        db.session.commit()
        assert repair.out_of_scope_fingerprint(db.session) != first


@postgres_only
def test_the_statement_watch_sees_a_raw_write_no_orm_guard_would(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        watch = repair.StatementWatch(db.engine).attach()
        try:
            db.session.execute(text(
                'UPDATE game_ingestion_work_items SET source_revision = :rev '
                'WHERE mlb_game_pk = :pk'
            ), {'rev': OLD_REVISION, 'pk': GAME_PK})
            db.session.rollback()
        finally:
            watch.detach()
        report = watch.as_dict()
        assert report['target_table_update_count'] == 1
        assert report['target_table_affected_rows'] == 1
        assert report['exactly_one_target_update'] is True
        # Statement TEXT never crosses into the report.
        assert 'source_revision = :rev' not in json.dumps(report)


@postgres_only
def test_the_statement_watch_flags_a_second_table_being_written(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        watch = repair.StatementWatch(db.engine).attach()
        try:
            db.session.execute(text(
                'UPDATE game_logs SET strikeouts = strikeouts '
                'WHERE mlb_game_pk = :pk'
            ), {'pk': GAME_PK})
            db.session.rollback()
        finally:
            watch.detach()
        report = watch.as_dict()
        assert report['no_other_write_statement'] is False
        assert report['other_write_statement_classes'] == ['UPDATE']
