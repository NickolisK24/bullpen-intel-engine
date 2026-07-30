"""Foundation 3C read-only diagnostic — accounting, determinism, and safety.

The diagnostic exists to produce evidence, so these tests are mostly about the
properties that make its output trustworthy: the accounting must reconcile
exactly, the sample must not depend on database row order, percentiles must
refuse to claim precision the sample cannot support, and the command must
refuse to run at all outside its read-only boundary.
"""

import importlib.util
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import Flask

from models.game_log import GameLog
from models.pitcher import Pitcher
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


BACKEND_DIR = Path(__file__).resolve().parents[1]
SCRIPT_PATH = BACKEND_DIR / 'scripts' / 'profile_daily_ingestion_readonly.py'

_spec = importlib.util.spec_from_file_location('f3c_profile', SCRIPT_PATH)
profile = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(profile)


REFERENCE_DATE = date(2026, 7, 30)

# Canonical roster status CODES, written as literals so this module keeps a
# small model-metadata graph (importing the roster services drags in tables
# whose foreign keys break the fixture's schema teardown on PostgreSQL).
# test_roster_status_literals_match_the_canonical_authority pins them.
ROSTER_ACTIVE = 'ACTIVE'
ROSTER_IL_15 = 'IL_15'
ROSTER_OPTIONED = 'OPTIONED'
TEAM_ID = 147
OTHER_TEAM_ID = 113


@pytest.fixture()
def app():
    application = Flask('test_daily_ingestion_readonly_profile')
    configure_test_database(application)
    db.init_app(application)
    with application.app_context():
        create_test_schema(application)
        # Own id space per test: a shared counter plus a per-test schema
        # lifecycle would otherwise collide on the unique mlb_id.
        _next_mlb_id[0] += 1000
        try:
            yield application
        finally:
            db.session.remove()
            drop_test_schema(application)


_next_mlb_id = [700000]
_next_pk = [800000]


def _pitcher(name, *, roster_status=ROSTER_ACTIVE, position='P', active=True,
             team_id=TEAM_ID, mlb_id=None):
    if mlb_id is None:
        _next_mlb_id[0] += 1
        mlb_id = _next_mlb_id[0]
    row = Pitcher(
        mlb_id=mlb_id, full_name=name, team_id=team_id,
        team_name='New York Yankees', team_abbreviation='NYY',
        active=active, roster_status=roster_status, position=position,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _relief(arm, *, appearances=6, outs_each=3, games_started=0,
            end=REFERENCE_DATE - timedelta(days=1)):
    for index in range(appearances):
        _next_pk[0] += 1
        db.session.add(GameLog(
            pitcher_id=arm.id, mlb_game_pk=_next_pk[0],
            game_date=end - timedelta(days=index),
            game_type='R', opponent='Boston Red Sox', opponent_abbreviation='BOS',
            games_started=games_started, innings_pitched=outs_each / 3,
            innings_pitched_outs=outs_each, earned_runs=0, runs_allowed=0,
            pitches_thrown=15, appearance_team_id=TEAM_ID,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
            appearance_team_source='boxscore_side',
            appearance_team_reason='appearance_team_resolved_boxscore',
        ))


# ── Vocabulary ─────────────────────────────────────────────────────────────
def test_roster_status_literals_match_the_canonical_authority():
    """Imported here only, so the module graph stays small."""
    from services import roster_authority

    assert ROSTER_ACTIVE == roster_authority.STATUS_ACTIVE
    assert ROSTER_IL_15 == roster_authority.STATUS_IL_15
    assert ROSTER_OPTIONED == roster_authority.STATUS_OPTIONED


# ── Percentile aggregation ─────────────────────────────────────────────────
def test_percentile_is_nearest_rank_and_deterministic():
    values = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    # rank = ceil(fraction * n); every result is an observation that happened.
    assert profile.percentile(values, 0.50) == 5
    assert profile.percentile(values, 0.90) == 9
    assert profile.percentile(values, 0.95) == 10
    assert profile.percentile(values, 1.0) == 10
    # Order of the input never changes the answer.
    assert profile.percentile(list(reversed(values)), 0.50) == 5
    assert profile.percentile([7], 0.99) == 7


def test_percentiles_are_marked_unsupported_below_their_sample_floor():
    small = profile.distribution([0.1, 0.2, 0.3])
    assert small['count'] == 3
    assert small['p50'] is not None
    assert small['p90'] is None and 'p90' in small['unsupported']
    assert small['p95'] is None and 'p95' in small['unsupported']
    assert small['p99'] is None and 'p99' in small['unsupported']


def test_p90_and_p95_appear_once_the_sample_supports_them():
    medium = profile.distribution([float(n) for n in range(1, 31)])
    assert medium['p90'] is not None
    assert medium['p95'] is not None
    # 30 observations still cannot support a p99.
    assert medium['p99'] is None and 'p99' in medium['unsupported']


def test_empty_distribution_claims_nothing():
    empty = profile.distribution([])
    assert empty['count'] == 0
    assert set(empty['unsupported']) == {'p50', 'p90', 'p95', 'p99'}


# ── Deterministic sampling ─────────────────────────────────────────────────
def _rows(category, mlb_ids):
    return [{'pitcher_id': i, 'mlb_id': mlb_id, 'category': category}
            for i, mlb_id in enumerate(mlb_ids, start=1)]


def test_sampling_is_deterministic_regardless_of_input_order():
    forward = {
        profile.CAT_ACTIVE_BULLPEN: _rows('a', [5, 1, 3]),
        profile.CAT_ACTIVE_STARTER: _rows('b', [9, 7]),
    }
    reversed_input = {
        profile.CAT_ACTIVE_STARTER: _rows('b', [7, 9]),
        profile.CAT_ACTIVE_BULLPEN: _rows('a', [3, 5, 1]),
    }
    first = [row['mlb_id'] for row in profile.select_sample(forward, 5)]
    second = [row['mlb_id'] for row in profile.select_sample(reversed_input, 5)]
    assert first == second


def test_sampling_round_robins_across_strata_before_deepening():
    pools = {
        profile.CAT_ACTIVE_BULLPEN: _rows('a', [1, 2, 3]),
        profile.CAT_ACTIVE_STARTER: _rows('b', [10, 11]),
    }
    chosen = [row['mlb_id'] for row in profile.select_sample(pools, 4)]
    # One from each stratum before a second from either.
    assert chosen[:2] == [1, 10]
    assert chosen[2:] == [2, 11]


def test_sampling_is_bounded_and_terminates_when_pools_run_dry():
    pools = {profile.CAT_ACTIVE_BULLPEN: _rows('a', [1, 2])}
    assert len(profile.select_sample(pools, 50)) == 2
    assert profile.select_sample({}, 10) == []


def test_sampling_never_selects_a_row_without_an_mlb_id():
    pools = {profile.CAT_ACTIVE_BULLPEN: [
        {'pitcher_id': 1, 'mlb_id': None},
        {'pitcher_id': 2, 'mlb_id': 42},
    ]}
    chosen = profile.select_sample(pools, 5)
    assert [row['mlb_id'] for row in chosen] == [42]


# ── Classification accounting ──────────────────────────────────────────────
def test_categories_are_mutually_exclusive_and_reconcile(app):
    reliever = _pitcher('Active Reliever')
    _relief(reliever, appearances=8)
    starter = _pitcher('Active Starter')
    _relief(starter, appearances=6, outs_each=18, games_started=1)
    _pitcher('Injured Arm', roster_status=ROSTER_IL_15)
    _pitcher('Optioned Arm', roster_status=ROSTER_OPTIONED)
    _pitcher('Unknown Arm', roster_status=None)
    _pitcher('Position Player', position='SS')
    db.session.commit()

    universe, by_category = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)

    assert universe['selected_total'] == 6
    assert universe['category_total'] == universe['selected_total']
    assert universe['criticality_total'] == universe['selected_total']
    assert universe['accounting']['category_sum_equals_selected'] is True
    assert universe['accounting']['criticality_sum_equals_selected'] is True

    # No pitcher may appear in two categories.
    seen = []
    for rows in by_category.values():
        seen.extend(row['pitcher_id'] for row in rows)
    assert len(seen) == len(set(seen)) == 6


def test_every_declared_category_is_reported_even_when_empty(app):
    _pitcher('Only Arm')
    db.session.commit()

    universe, _ = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    reported = [entry['category'] for entry in universe['categories']]
    assert reported == list(profile.CATEGORY_ORDER)


def test_inactive_pitchers_are_not_selected(app):
    _pitcher('Active Arm')
    _pitcher('Inactive Arm', active=False)
    db.session.commit()

    universe, _ = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    assert universe['selected_total'] == 1


def test_roster_state_is_not_inferred_from_active_roster_absence(app):
    """An optioned arm is optioned because the roster authority says so."""
    optioned = _pitcher('Optioned Arm', roster_status=ROSTER_OPTIONED)
    _relief(optioned, appearances=6)
    db.session.commit()

    _, by_category = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    ids = {row['pitcher_id'] for row in by_category[profile.CAT_OPTIONED_MINORS]}
    assert optioned.id in ids
    assert not by_category.get(profile.CAT_HISTORICAL_ONLY)


def test_recent_appearance_flags_are_reported_per_pitcher(app):
    worked = _pitcher('Worked Recently')
    _relief(worked, appearances=4)
    idle = _pitcher('No Recent Work')
    db.session.commit()

    _, by_category = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    rows = {row['pitcher_id']: row for group in by_category.values() for row in group}
    assert rows[worked.id]['has_relief_appearance_in_lookback'] is True
    assert rows[worked.id]['has_any_appearance_in_lookback'] is True
    assert rows[idle.id]['has_relief_appearance_in_lookback'] is False


def test_bounded_id_samples_never_exceed_their_limit(app):
    for index in range(profile.MAX_IDS_PER_CATEGORY + 8):
        arm = _pitcher(f'Bullpen Arm {index}')
        _relief(arm, appearances=6)
    db.session.commit()

    universe, _ = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    for entry in universe['categories']:
        assert len(entry['sample_mlb_ids']) <= profile.MAX_IDS_PER_CATEGORY


def test_duplicate_and_missing_identities_are_foreclosed_by_the_schema(app):
    """Persistence already guarantees both; the counters are defence in depth.

    ``pitchers.mlb_id`` is NOT NULL and UNIQUE, so neither a duplicate nor a
    missing MLB identity can exist as a row — which is itself a finding: the
    "duplicate identity" condition the audit asks about cannot occur at the row
    level in this schema. The diagnostic still counts both so a future schema
    relaxation cannot silently break the accounting.

    The guarantee is asserted against the schema rather than by attempting the
    write, because a deliberately failed INSERT poisons the session transaction
    and would tear down the fixture's schema teardown with it.
    """
    column = Pitcher.__table__.columns['mlb_id']
    assert column.unique is True
    assert column.nullable is False

    _pitcher('Only Arm')
    db.session.commit()

    universe, _ = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    assert universe['anomalies']['duplicate_mlb_id_count'] == 0
    assert universe['anomalies']['missing_mlb_id_rows'] == 0
    assert universe['category_total'] == universe['selected_total'] == 1


# ── Read-only boundary ─────────────────────────────────────────────────────
def test_the_command_refuses_to_run_without_the_read_only_flag(capsys):
    exit_code = profile.main([])
    assert exit_code == profile.EXIT_ERROR
    payload = capsys.readouterr().out
    assert 'read_only_flag_required' in payload


def test_engine_level_read_only_is_required_when_demanded():
    """On an engine that cannot enforce it, the run stops before touching data."""
    blocked = profile.read_only_guard(
        'no_engine_level_read_only_available:sqlite', None,
        require_engine_read_only=True)
    assert blocked is not None
    assert blocked['reason'] == 'read_only_boundary_unprovable'


def test_a_write_that_is_not_refused_stops_the_run():
    blocked = profile.read_only_guard(
        'postgresql_read_only_transaction',
        {'attempted': True, 'refused': False, 'error_class': None},
        require_engine_read_only=True)
    assert blocked is not None
    assert blocked['reason'] == 'write_probe_not_refused'


def test_a_refused_write_on_a_read_only_engine_is_allowed_to_proceed():
    assert profile.read_only_guard(
        'postgresql_read_only_transaction',
        {'attempted': True, 'refused': True, 'error_class': 'InternalError'},
        require_engine_read_only=True) is None


def test_table_drift_fails_the_run():
    before = {'game_logs': {'rows': 10, 'max_id': 5}}
    unchanged = profile.fingerprint_drift(before, {'game_logs': {'rows': 10, 'max_id': 5}})
    assert unchanged == []
    grew = profile.fingerprint_drift(before, {'game_logs': {'rows': 11, 'max_id': 6}})
    assert len(grew) == 1 and grew[0]['table'] == 'game_logs'


def test_unreadable_table_is_not_mistaken_for_drift():
    before = {'game_logs': {'rows': None, 'max_id': None, 'error': 'ProgrammingError'}}
    after = {'game_logs': {'rows': None, 'max_id': None, 'error': 'ProgrammingError'}}
    assert profile.fingerprint_drift(before, after) == []


# ── Output schema and redaction ────────────────────────────────────────────
def test_failure_payload_carries_no_exception_message():
    payload = profile._fail('diagnostic_failed', 'OperationalError')
    assert payload['result'] == profile.RESULT_ERROR
    assert payload['detail'] == 'OperationalError'
    # A class name only — never a message that could carry a connection string.
    assert 'postgresql://' not in str(payload)
    assert 'password' not in str(payload).lower()


def test_markdown_summary_renders_without_leaking_structure(app):
    _pitcher('Markdown Arm')
    db.session.commit()
    universe, _ = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    rendered = profile._markdown({
        'result': profile.RESULT_OK,
        'executed_at': '2026-07-30T00:00:00+00:00',
        'read_only_protection': 'postgresql_read_only_transaction',
        'write_probe': {'refused': True},
        'write_drift': [],
        'universe': universe,
        'profile': {'sample_size': 0, 'succeeded': 0, 'failed': 0,
                    'stage_distributions': {}, 'unchanged_cost': {}},
    })
    assert '# Foundation 3C' in rendered
    assert 'Write probe refused: **True**' in rendered
    assert 'postgresql://' not in rendered


def test_report_schema_declares_its_version_and_mode(app):
    _pitcher('Schema Arm')
    db.session.commit()
    universe, _ = profile.classify_universe(
        db.session, reference_date=REFERENCE_DATE, lookback_days=7)
    assert set(universe) >= {
        'reference_date', 'lookback_days', 'selected_total', 'categories',
        'category_total', 'criticality_counts', 'criticality_total',
        'anomalies', 'timings', 'accounting',
    }
    assert profile.SCHEMA_VERSION and profile.MODE == 'read_only'


def test_the_diagnostic_never_imports_the_sync_writer():
    source = SCRIPT_PATH.read_text(encoding='utf-8')
    for forbidden in ('sync_recent_logs', 'services.sync', 'dead_letter',
                      'record_failure', 'complete_sync_run'):
        assert forbidden not in source, forbidden


def test_the_guard_does_not_fail_before_the_probe_has_run():
    """None means "not yet probed", which is not the same as "not refused"."""
    assert profile.read_only_guard(
        'postgresql_read_only_transaction', None,
        require_engine_read_only=True) is None
