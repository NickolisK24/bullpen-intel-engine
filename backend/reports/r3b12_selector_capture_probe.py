"""Retained B1.2 negative evidence; passing assertions reproduce missing capture.

Run explicitly with pytest against a disposable PostgreSQL database. These are
diagnostics, not selector-completeness certification or production race drills.
"""

from datetime import date, datetime, timedelta
import json
from time import perf_counter

import pytest
from sqlalchemy import event, text

from models.fatigue_score import FatigueScore
from models.derived_intelligence import DerivedCohortSnapshot
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransactionSyncWindow
from models.sync_failure import SyncFailure
from services import derived_intelligence as derived
from services.availability_snapshot import latest_fatigue_rows, _unresolved_workload_fetch_failure_refs
from services.transaction_ingestion import latest_transaction_sync_window
from tests.test_derived_intelligence import (
    app, _plan, _fenced_selector_fixture, _observation, _final_authority, GAME_DATE,
)
from utils.db import db


@pytest.mark.parametrize('family', ['fatigue', 'transaction_window', 'failure'])
def test_unfenced_selector_advances_inside_completion_boundary(app, monkeypatch, family):
    """Actual executor completion; injected domain isolates one real selector."""
    _fenced_selector_fixture(monkeypatch)
    pitcher = Pitcher(id=10, mlb_id=9001, full_name='Selector fixture', team_id=110,
                      team_abbreviation='T', active=True)
    db.session.add(pitcher)
    db.session.commit()
    first_time = datetime(2026, 9, 8, 12)

    def selection():
        if family == 'fatigue':
            return [score.id for score, _ in latest_fatigue_rows(team_id=110)]
        if family == 'transaction_window':
            row = latest_transaction_sync_window()
            return row.id if row else None
        return sorted(_unresolved_workload_fetch_failure_refs([pitcher]))

    def insert(connection, second):
        timestamp = first_time + timedelta(minutes=int(second))
        if family == 'fatigue':
            connection.execute(FatigueScore.__table__.insert().values(
                pitcher_id=10, calculated_at=timestamp, raw_score=10,
            ))
        elif family == 'transaction_window':
            connection.execute(PlayerTransactionSyncWindow.__table__.insert().values(
                source='mlb_stats_api', source_endpoint='/transactions',
                source_query_start_date=GAME_DATE, source_query_end_date=GAME_DATE,
                attempted_at=timestamp, status='success',
            ))
        else:
            connection.execute(SyncFailure.__table__.insert().values(
                job_name='daily_sync', entity_type='pitcher_game_logs',
                entity_ref='9001', created_at=timestamp, resolved=False,
            ))

    if family != 'failure':
        with db.engine.begin() as writer:
            insert(writer, False)
    plan = _plan(domains=('read_models',))
    before = selection()
    context = derived._capture_cohort_context(plan)
    monkeypatch.setattr(derived._DefaultDomainExecutor, '__call__',
                        lambda owner, domain, snapshots: {
                            'team': {'110': {'selected': selection()}},
                        })
    original = derived._persist_snapshots
    observed = {}

    def advance_after_revalidation(cohort, snapshots):
        # The executor already holds B1.1 shared completion locks here.
        with db.engine.begin() as writer:
            assert writer.connection.driver_connection is not db.session.connection().connection.driver_connection
            started = perf_counter()
            insert(writer, True)
        observed['writer_ms'] = (perf_counter() - started) * 1000
        observed['selection'] = selection()
        assert observed['selection'] != before
        # This is the defect, not an assertion of acceptable completion.
        assert derived.cohort_inputs_are_current(cohort, plan)
        original(cohort, snapshots)

    monkeypatch.setattr(derived, '_persist_snapshots', advance_after_revalidation)
    result = derived.execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
    assert result.cohort.status == 'complete'
    assert result.cohort.input_manifest_json[-1]['input_fingerprint'] == context.fingerprint
    artifact = DerivedCohortSnapshot.query.filter_by(cohort_id=result.cohort.id).one()
    assert artifact.payload_json['selected'] == before
    print(json.dumps({'negative_evidence': family, 'captured_selection': before,
                      'new_selection_before_commit': observed['selection'],
                      'cohort_status': result.cohort.status,
                      'unchanged_context_fingerprint': context.fingerprint,
                      'writer_ms': round(observed['writer_ms'], 3)}))


def test_clock_fallback_can_advance_without_context_identity(app, monkeypatch):
    from services import public_pitcher_current
    _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    context = derived._capture_cohort_context(plan)
    before = context.fingerprint
    monkeypatch.setattr(public_pitcher_current, 'product_current_date', lambda: date(2026, 9, 8))
    first = public_pitcher_current._reference_date({})
    monkeypatch.setattr(public_pitcher_current, 'product_current_date', lambda: date(2026, 9, 9))
    second = public_pitcher_current._reference_date({})
    assert first != second
    assert derived._capture_cohort_context(plan).fingerprint == before
    print('Negative clock evidence: fallback changed September 8 -> September 9; context unchanged')


def test_current_final_can_advance_after_final_validation(app, monkeypatch):
    """Real game-context domain, persisted versions, separate R2 game writer."""
    from models.final_game_reconciliation import FinalGameVersion
    from services.semantic_write_fencing import GAME_LOCK_NAMESPACE
    observation = _observation('canonical-selector')
    first, _, pitcher = _final_authority(observation, version=1)
    db.session.commit()
    first_id = first.id
    values = {column.name: getattr(first, column.name)
              for column in FinalGameVersion.__table__.columns if column.name != 'id'}
    values.update(version_number=2, predecessor_version_id=first_id, is_current=False,
                  fact_fingerprint='corrected-selector'.ljust(64, '0'))
    with db.engine.begin() as writer:
        second_id = writer.execute(FinalGameVersion.__table__.insert().values(**values)
                                   .returning(FinalGameVersion.id)).scalar_one()
    plan = _plan(domains=('game_context',), pitchers=(pitcher.id,))
    original = derived._persist_snapshots

    def advance_after_revalidation(cohort, snapshots):
        assert snapshots['game']['777123']['game_context']['final_game_version_id'] == first_id
        with db.engine.begin() as writer:
            writer.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                           {'key': GAME_LOCK_NAMESPACE + 777123})
            writer.execute(FinalGameVersion.__table__.update()
                           .where(FinalGameVersion.id == first_id).values(is_current=False))
            writer.execute(FinalGameVersion.__table__.update()
                           .where(FinalGameVersion.id == second_id).values(is_current=True))
        original(cohort, snapshots)

    monkeypatch.setattr(derived, '_persist_snapshots', advance_after_revalidation)
    result = derived.execute_derived_intelligence_plan(plan.id, publication_candidate_enabled=False)
    assert result.cohort.status == 'complete'
    assert not derived.cohort_inputs_are_current(result.cohort, plan)
    entry = next(row for row in result.cohort.input_manifest_json if row['input_type'] == 'final_game')
    assert str(entry['input_version']) == str(first_id)
    print(json.dumps({'negative_evidence': 'canonical_final', 'captured_version': first_id,
                      'current_version_before_commit': second_id,
                      'cohort_status': result.cohort.status, 'currentness_after_commit': False}))


def test_current_context_capture_cost_is_not_v2_proof(app, monkeypatch):
    _fenced_selector_fixture(monkeypatch)
    plan = _plan(domains=('read_models',))
    statements = []
    def record(*args):
        statements.append(1)
    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        started = perf_counter()
        context = derived._capture_cohort_context(plan)
        elapsed = (perf_counter() - started) * 1000
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    from services.selector_generation_fencing import captured_resources
    print(json.dumps({'fixture': 'one requested team, sparse baseline, v1 only',
                      'capture_sql': len(statements), 'capture_ms': round(elapsed, 3),
                      'context_bytes': len(json.dumps(context.manifest_value(), sort_keys=True).encode()),
                      'fence_resources': len(captured_resources(context, plan.authority_class))}))
