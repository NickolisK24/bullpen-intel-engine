"""Daily Primary publication memory guards (incident 2026-09-29).

The Daily Primary 512 MiB cron was killed while assembling and publishing the
Dashboard snapshot. The measured causes were (1) every served-score-cutoff
lookup selecting and parsing the full multi-megabyte snapshot payload, dozens
of times per publication; (2) whole-payload deep copies in What Changed
identity binding and frozen Team Board What Changed attachment inside the
publication transaction; and (3) freed multi-megabyte serialization buffers
staying resident under glibc's dynamic mmap threshold.

RSS is too noisy for CI, so these tests pin the structure that produced the
peak: output parity with the previous implementation, no full-payload read for
the cutoff, shared (not copied) untouched payload domains, a bounded count of
full-payload reads and payload writes per publication, and the production
memory telemetry lines.
"""

from copy import deepcopy
from datetime import timedelta
import importlib
import logging
from types import SimpleNamespace

import pytest
from sqlalchemy import event
from sqlalchemy.exc import OperationalError

from models.dashboard_snapshot import DashboardSnapshot
from services import dashboard_snapshot as dashboard_snapshot_service
from services import process_memory
from services.dashboard_source_cutoff import latest_valid_snapshot_source
from services.team_board_what_changed import attach_frozen_what_changed
from services.what_changed_comparison_identity import (
    bind_comparison_identity,
    build_comparison_identity,
)
from tests.db_config import (
    assert_disposable_test_target,
    create_test_schema,
    drop_test_schema,
    test_database_url as _test_database_url,
)
from utils.db import db
from utils.time import utc_now_naive


# ---------------------------------------------------------------------------
# Served score cutoff: same row, same validity, no payload.
# ---------------------------------------------------------------------------

@pytest.fixture
def snapshot_app(monkeypatch):
    url = _test_database_url()
    assert_disposable_test_target(url, operation='daily publication memory tests')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', url)
    app = importlib.import_module('app').create_app('test')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


def _freshness(data_through, *, complete=True, slate_date=None):
    return {
        'data_through': data_through.isoformat(),
        'availability_reference_date': (data_through + timedelta(days=1)).isoformat(),
        'slate_coverage': {
            'slate_date': (slate_date or data_through).isoformat(),
            'validations_passed': complete,
            'complete_enough_to_publish': complete,
        },
    }


def _add_snapshot(*, data_through, freshness=None, generated_offset_minutes=0,
                  status='ready', is_published=True, payload_version=None,
                  payload_extra=None, error_message=None, row_data_through=None):
    payload = {
        'freshness': freshness if freshness is not None else _freshness(data_through),
        # A large, unrelated domain the cutoff must never need to read.
        'trusted_team_boards': {'by_team_id': {str(i): {'records': list(range(50))} for i in range(30)}},
        **(payload_extra or {}),
    }
    from models.sync_run import SyncRun
    run = SyncRun(
        job_name='daily_sync', started_at=utc_now_naive(), completed_at=utc_now_naive(),
        status='success', stage='published', source='test',
    )
    db.session.add(run)
    db.session.flush()
    snapshot = DashboardSnapshot(
        snapshot_type=dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        sync_run_id=run.id,
        status=status,
        is_published=is_published,
        published_at=utc_now_naive() if is_published else None,
        payload=payload,
        payload_version=(
            payload_version if payload_version is not None
            else dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION
        ),
        data_through=row_data_through or data_through,
        availability_reference_date=data_through + timedelta(days=1),
        snapshot_generated_at=utc_now_naive() + timedelta(minutes=generated_offset_minutes),
        source='test',
        error_message=error_message,
    )
    db.session.add(snapshot)
    db.session.commit()
    return snapshot


def _full_row_cutoff():
    """The pre-incident implementation: load the full ORM row."""
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    return None if snapshot is None else (snapshot.id, snapshot.snapshot_generated_at)


def _projection_cutoff():
    source = latest_valid_snapshot_source()
    return None if source is None else (source.id, source.snapshot_generated_at)


@pytest.fixture
def product_today():
    return dashboard_snapshot_service.product_current_date()


SCENARIOS = {
    'no_snapshot': [],
    'one_valid': [dict(days_ago=1)],
    'latest_valid_of_two': [dict(days_ago=2, offset=0), dict(days_ago=1, offset=5)],
    'latest_incomplete_coverage': [dict(days_ago=2), dict(days_ago=1, offset=5, complete=False)],
    'latest_coverage_date_mismatch': [dict(days_ago=1, slate_days_ago=2)],
    'latest_data_through_mismatch': [dict(days_ago=1, row_days_ago=2)],
    'latest_missing_freshness': [dict(days_ago=1, freshness={})],
    'latest_fail_closed_stale': [dict(days_ago=60)],
    'unpublished_newer_candidate': [dict(days_ago=2), dict(days_ago=1, offset=5, published=False)],
    'pending_withheld_newer': [dict(days_ago=2), dict(days_ago=1, offset=5, status='pending', published=False)],
    'version_mismatch_newer': [dict(days_ago=2), dict(days_ago=1, offset=5, payload_version=-1)],
}


@pytest.mark.parametrize('scenario', sorted(SCENARIOS))
def test_cutoff_projection_selects_the_same_snapshot_as_the_full_row(
    snapshot_app, product_today, scenario,
):
    for spec in SCENARIOS[scenario]:
        data_through = product_today - timedelta(days=spec['days_ago'])
        freshness = spec.get('freshness')
        if freshness is None:
            freshness = _freshness(
                data_through,
                complete=spec.get('complete', True),
                slate_date=(
                    product_today - timedelta(days=spec['slate_days_ago'])
                    if 'slate_days_ago' in spec else None
                ),
            )
        _add_snapshot(
            data_through=data_through,
            freshness=freshness,
            generated_offset_minutes=spec.get('offset', 0),
            status=spec.get('status', 'ready'),
            is_published=spec.get('published', True),
            payload_version=spec.get('payload_version'),
            row_data_through=(
                product_today - timedelta(days=spec['row_days_ago'])
                if 'row_days_ago' in spec else None
            ),
        )
    db.session.expunge_all()
    expected = _full_row_cutoff()
    db.session.expunge_all()
    assert _projection_cutoff() == expected
    if scenario in ('one_valid', 'latest_valid_of_two'):
        assert expected is not None
    if scenario.startswith('latest_') and scenario != 'latest_valid_of_two':
        assert expected is None


def test_cutoff_lookup_never_selects_the_full_payload(snapshot_app, product_today):
    _add_snapshot(data_through=product_today - timedelta(days=1))
    db.session.expunge_all()
    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(' '.join(statement.lower().split()))

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        from api.bullpen import _served_score_cutoff
        cutoff = _served_score_cutoff()
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert cutoff is not None
    snapshot_reads = [sql for sql in statements if 'from dashboard_snapshots' in sql]
    assert len(snapshot_reads) == 1
    assert 'dashboard_snapshots.payload as ' not in snapshot_reads[0]
    assert "->" in snapshot_reads[0] or 'json_extract' in snapshot_reads[0]


def test_cutoff_lookup_keeps_the_database_error_contract(snapshot_app, monkeypatch):
    calls = {'rollback': 0}
    original_rollback = db.session.rollback

    def failing_first(self):
        raise OperationalError('select', {}, Exception('connection lost'))

    def counting_rollback():
        calls['rollback'] += 1
        return original_rollback()

    from sqlalchemy.orm import Query
    monkeypatch.setattr(Query, 'first', failing_first)
    monkeypatch.setattr(db.session, 'rollback', counting_rollback)
    assert latest_valid_snapshot_source() is None
    assert calls['rollback'] == 1


def test_cutoff_lookup_sees_an_unflushed_candidate_like_the_orm_path(
    snapshot_app, product_today,
):
    """Autoflush parity: a candidate published in-session is what both paths see."""
    prior = _add_snapshot(data_through=product_today - timedelta(days=2))
    candidate = _add_snapshot(
        data_through=product_today - timedelta(days=1),
        generated_offset_minutes=5, status='pending', is_published=False,
    )
    candidate.status = 'ready'
    candidate.is_published = True
    prior.is_published = False
    assert _projection_cutoff() == (candidate.id, candidate.snapshot_generated_at)
    assert _full_row_cutoff() == (candidate.id, candidate.snapshot_generated_at)
    db.session.rollback()


# ---------------------------------------------------------------------------
# Structural sharing: identical values, no whole-payload copies.
# ---------------------------------------------------------------------------

def _reference_bind(payload, current_snapshot, previous_snapshot):
    """The pre-incident implementation, kept verbatim for parity."""
    from services import what_changed_comparison_identity as module
    stored = deepcopy(module._mapping(payload))
    block = module._mapping(stored.get('what_changed_since_yesterday'))
    comparison = module._mapping(block.get('comparison'))
    if comparison.get('comparison_available') is not True:
        return stored
    if (
        previous_snapshot is None
        or comparison.get('previous_snapshot_id') != getattr(previous_snapshot, 'id', None)
        or getattr(previous_snapshot, 'status', None) != module.SNAPSHOT_STATUS_READY
        or getattr(previous_snapshot, 'published_at', None) is None
    ):
        comparison.pop('previous_snapshot_id', None)
        block['comparison'] = comparison
        stored['what_changed_since_yesterday'] = block
        return stored
    try:
        identity = build_comparison_identity(current_snapshot, previous_snapshot)
    except module.ComparisonIdentityInvalid:
        comparison.pop('previous_snapshot_id', None)
        block['comparison'] = comparison
        stored['what_changed_since_yesterday'] = block
        return stored
    if (
        comparison.get('previous_data_through') != identity['previous_data_through']
        or comparison.get('current_data_through') != identity['current_data_through']
    ):
        comparison.pop('previous_snapshot_id', None)
        block['comparison'] = comparison
        stored['what_changed_since_yesterday'] = block
        return stored
    comparison['identity'] = identity
    comparison.pop('previous_snapshot_id', None)
    block['comparison'] = comparison
    stored['what_changed_since_yesterday'] = block
    return stored


def _publication(snapshot_id, data_through):
    from datetime import date, datetime
    return SimpleNamespace(
        id=snapshot_id, sync_run_id=snapshot_id + 100,
        data_through=date.fromisoformat(data_through), payload_version=1,
        snapshot_type='bullpen_dashboard', status='ready', is_published=True,
        published_at=datetime(2026, 9, 22, 12), payload={},
    )


def _bind_payload(comparison):
    return {
        'what_changed_since_yesterday': {'comparison': comparison, 'items': [{'a': 1}]},
        'trusted_team_boards': {'by_team_id': {'108': {'records': [{'pitcher_id': 1}]}}},
        'capacity_intelligence': {'by_team_id': {'108': {'value': [1, 2, 3]}}},
    }


BIND_CASES = {
    'not_available': {'comparison_available': False},
    'missing_previous': {'comparison_available': True, 'previous_snapshot_id': 1},
    'mismatched_previous': {'comparison_available': True, 'previous_snapshot_id': 99},
    'date_mismatch': {
        'comparison_available': True, 'previous_snapshot_id': 1,
        'previous_data_through': '2026-09-01', 'current_data_through': '2026-09-22',
    },
    'bound': {
        'comparison_available': True, 'previous_snapshot_id': 1,
        'previous_data_through': '2026-09-21', 'current_data_through': '2026-09-22',
    },
}


@pytest.mark.parametrize('case', sorted(BIND_CASES))
def test_bind_comparison_identity_matches_the_deep_copy_reference(case):
    previous = _publication(1, '2026-09-21')
    current = _publication(2, '2026-09-22')
    previous_arg = None if case == 'missing_previous' else previous
    payload = _bind_payload(deepcopy(BIND_CASES[case]))
    original = deepcopy(payload)
    expected = _reference_bind(deepcopy(payload), current, previous_arg)

    result = bind_comparison_identity(payload, current, previous_arg)

    assert result == expected
    assert payload == original, 'the candidate payload must not be mutated'
    # Untouched domains are shared, never deep-copied (the OOM guard).
    assert result['trusted_team_boards'] is payload['trusted_team_boards']
    assert result['capacity_intelligence'] is payload['capacity_intelligence']
    assert result is not payload


def _board_snapshot(snapshot_id, represented_date, team_ids=('108', '109')):
    snapshot = _publication(snapshot_id, represented_date)
    snapshot.payload = {
        'trusted_team_boards': {
            'contract': 'trusted_team_board_publication_v1',
            'data_through': represented_date,
            'by_team_id': {
                team_id: {
                    'records': [{'pitcher_id': int(team_id), 'nested': {'x': [1, 2]}}],
                    'frozen_team_state': None,
                }
                for team_id in team_ids
            },
        },
        'capacity_intelligence': {'by_team_id': {'108': {'value': [1, 2, 3]}}},
    }
    return snapshot


def _reference_attach(snapshot, previous_snapshot):
    """The pre-incident implementation, kept verbatim for parity."""
    from services import team_board_what_changed as module
    payload = deepcopy(dict(snapshot.payload))
    package = deepcopy(dict(module._mapping(payload.get('trusted_team_boards'))))
    teams = deepcopy(dict(module._mapping(package.get('by_team_id'))))
    for key, team in teams.items():
        team['frozen_what_changed'] = module.build_frozen_what_changed(
            previous_snapshot, snapshot, int(key),
        )
    package['by_team_id'] = teams
    payload['trusted_team_boards'] = package
    return payload


@pytest.mark.parametrize('with_previous', [True, False])
def test_attach_frozen_what_changed_matches_the_deep_copy_reference(with_previous):
    previous = _board_snapshot(1, '2026-09-21') if with_previous else None
    current = _board_snapshot(2, '2026-09-22')
    if previous is not None:
        current.payload['what_changed_since_yesterday'] = {
            'comparison': {'identity': build_comparison_identity(current, previous)},
        }
    previous_original = deepcopy(previous.payload) if previous is not None else None
    before = current.payload
    before_copy = deepcopy(before)
    expected = _reference_attach(SimpleNamespace(**vars(current)), previous)

    attach_frozen_what_changed(current, previous)

    assert current.payload == expected
    assert before == before_copy, 'the replaced payload must not be mutated'
    if previous is not None:
        assert previous.payload == previous_original
    # Untouched domains and per-team evidence are shared, not deep-copied.
    assert current.payload is not before
    assert current.payload['capacity_intelligence'] is before['capacity_intelligence']
    new_team = current.payload['trusted_team_boards']['by_team_id']['108']
    old_team = before['trusted_team_boards']['by_team_id']['108']
    assert new_team is not old_team
    assert new_team['records'] is old_team['records']
    assert 'frozen_what_changed' not in old_team


def test_attach_keeps_the_malformed_team_entry_failure():
    current = _board_snapshot(2, '2026-09-22')
    current.payload['trusted_team_boards']['by_team_id']['110'] = None
    with pytest.raises(TypeError):
        attach_frozen_what_changed(current, None)


# ---------------------------------------------------------------------------
# Process memory policy and telemetry.
# ---------------------------------------------------------------------------

@pytest.fixture
def fresh_allocator_state(monkeypatch):
    monkeypatch.setattr(
        process_memory, '_allocator_state',
        {'configured': False, 'threshold_bytes': None, 'reason': None},
    )


def test_allocator_policy_is_applied_once_on_glibc(fresh_allocator_state, monkeypatch):
    monkeypatch.delenv(process_memory.MMAP_THRESHOLD_ENV, raising=False)
    calls = []

    class FakeMallopt:
        argtypes = None
        restype = None

        def __call__(self, param, value):
            calls.append((param, value))
            return 1

    fake = SimpleNamespace(mallopt=FakeMallopt())
    monkeypatch.setattr(process_memory.ctypes.util, 'find_library', lambda _name: 'libc.so.6')
    monkeypatch.setattr(process_memory.ctypes, 'CDLL', lambda _name: fake)
    first = process_memory.configure_allocator_for_large_buffers()
    second = process_memory.configure_allocator_for_large_buffers()
    assert first['threshold_bytes'] == process_memory.DEFAULT_MMAP_THRESHOLD_BYTES
    assert first['reason'] is None
    assert second == first
    assert calls == [(-3, process_memory.DEFAULT_MMAP_THRESHOLD_BYTES)]


@pytest.mark.parametrize('value', ['off', '0', 'false'])
def test_allocator_policy_can_be_disabled(fresh_allocator_state, monkeypatch, value):
    monkeypatch.setenv(process_memory.MMAP_THRESHOLD_ENV, value)
    monkeypatch.setattr(
        process_memory.ctypes, 'CDLL',
        lambda _name: pytest.fail('mallopt must not be called when disabled'),
    )
    result = process_memory.configure_allocator_for_large_buffers()
    assert result['threshold_bytes'] is None
    assert result['reason'] == 'disabled_by_environment'


def test_allocator_policy_never_raises_without_mallopt(fresh_allocator_state, monkeypatch):
    monkeypatch.delenv(process_memory.MMAP_THRESHOLD_ENV, raising=False)
    monkeypatch.setattr(process_memory.ctypes.util, 'find_library', lambda _name: None)
    result = process_memory.configure_allocator_for_large_buffers()
    assert result['threshold_bytes'] is None
    assert result['reason'] == 'mallopt_unavailable'


def test_memory_checkpoint_is_one_concise_line(caplog):
    with caplog.at_level(logging.INFO, logger=process_memory.logger.name):
        process_memory.log_memory_checkpoint('publication_before', sync_run_id=7, skipped=None)
    lines = [record.getMessage() for record in caplog.records]
    assert len(lines) == 1
    assert lines[0].startswith('daily_sync memory checkpoint phase=publication_before rss_mb=')
    assert 'peak_rss_mb=' in lines[0]
    assert lines[0].endswith(' sync_run_id=7')


def test_memory_checkpoint_never_raises(monkeypatch):
    monkeypatch.setattr(process_memory, 'rss_mb', lambda: 1 / 0)
    process_memory.log_memory_checkpoint('daily_final')


def test_rss_readers_report_this_process():
    rss = process_memory.rss_mb()
    peak = process_memory.peak_rss_mb()
    if rss is None:
        pytest.skip('/proc is unavailable on this platform')
    assert rss > 0
    assert peak >= rss - 1


def test_due_sync_entrypoint_configures_the_allocator_before_the_app():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'scripts' / 'run_due_sync.py').read_text()
    configure = source.index('configure_allocator_for_large_buffers()')
    app_import = source.index('from app import app')
    assert configure < app_import


# ---------------------------------------------------------------------------
# End-to-end structural guard: the real Daily completion path, small fixture.
# ---------------------------------------------------------------------------

SMALL_SHAPE = {
    'starters_per_team': 2,
    'relievers_per_team': 3,
    'depth_per_team': 1,
    'season_days': 12,
    'seasons': 1,
}


def test_daily_publication_reads_and_writes_the_payload_a_bounded_number_of_times(
    monkeypatch, tmp_path,
):
    from scripts.daily_publication_memory_harness import configure_harness_app, run_harness
    from services import sync as sync_service

    url = _test_database_url()
    assert_disposable_test_target(url, operation='daily publication memory guard')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', url)
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = configure_harness_app(importlib.import_module('app').create_app('test'))
    with app.app_context():
        create_test_schema(app)
        try:
            results = run_harness(app, shape=SMALL_SHAPE)
        finally:
            db.session.remove()
            drop_test_schema(app)

    for label in ('prior', 'measured'):
        run = results[label]
        assert run['published'] is True, label
        assert run['status'] == 'ready', label
        assert run['parity']['team_board_teams'] == 30
        assert run['parity']['artifact_count'] == 30
        assert run['parity']['proof_present'] is True
        assert run['parity']['tonight_v1_digest'] is not None
        # Every served-score-cutoff lookup still happens (same authority,
        # same row), but none of them may select the payload column: before
        # the fix each one parsed the full Dashboard payload.
        assert run['source_snapshot_lookups'] >= 30
        # Exactly the INSERT and the one pre-trust UPDATE write the payload.
        assert run['dashboard_payload_writes'] == 2, run['dashboard_payload_writes']
        # Remaining full-row reads are the post-commit artifact batch refresh
        # and the small per-team sidecars (two per team) plus a handful of
        # comparison lookups: O(teams), never O(teams x cutoff lookups).
        assert run['full_payload_selects'] <= 2 * 30 + 10, run['full_payload_selects']

    telemetry = results['memory_telemetry']
    phases = [line.split('phase=', 1)[1].split()[0] for line in telemetry]
    for phase in (
        'publication_before', 'dashboard_payload_after', 'team_boards_after',
        'publication_committed', 'post_publication_hooks_after', 'artifact_gate_after',
    ):
        assert phase in phases, phase
    assert all('rss_mb=' in line and 'peak_rss_mb=' in line for line in telemetry)
