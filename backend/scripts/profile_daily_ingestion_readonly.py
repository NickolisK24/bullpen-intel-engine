"""Foundation 3C read-only diagnostic: daily pitcher universe + ingestion profile.

Answers two questions with measurement rather than inference:

  A. WHY IS THE DAILY UNIVERSE ~854 PITCHERS? Reproduces the exact current
     selection (``Pitcher.active == True``) and classifies every selected row
     into mutually exclusive categories using the canonical roster, role and
     appearance authorities already in the repository. The category counts must
     reconcile exactly to the selected total, and criticality must reconcile
     exactly to the same total, or the command exits nonzero.

  B. WHERE DOES THE TIME GO? Runs the real MLB gameLog request and the real
     parsing / window-filtering / existing-row comparison for a bounded,
     deterministic, stratified sample, timing each stage separately.

READ-ONLY, PROVEN THREE WAYS, not asserted:

  1. Every database session is opened with ``SET TRANSACTION READ ONLY`` on
     PostgreSQL, so the database itself rejects a write.
  2. Table row counts and max(id) fingerprints are captured before and after
     and compared; any drift fails the run.
  3. The profile never calls the ingestion writer. It reuses the read-only
     parts of the real path — the same MLB client, the same window filter, the
     same existing-row comparison — and stops before persistence.

The sync writer is never invoked, no SyncRun or dead letter is created, and no
correction is applied.

Exit codes:
    0  OK                — diagnostic complete and every accounting identity holds.
    1  RECONCILIATION    — accounting did not reconcile, or a write was detected.
    2  ERROR             — the diagnostic could not complete.

Only exception CLASS NAMES are reported. Messages are discarded because
database and HTTP errors can carry connection strings and credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Operator diagnostic, not a web worker: never start the background scheduler.
os.environ['AUTO_SYNC'] = 'false'

CAPABILITY = 'foundation_3c_daily_ingestion_readonly_profile_v1'
MODE = 'read_only'
SCHEMA_VERSION = '1.0.0'

RESULT_OK = 'OK'
RESULT_RECONCILIATION = 'RECONCILIATION_FAILED'
RESULT_ERROR = 'ERROR'

EXIT_OK = 0
EXIT_RECONCILIATION = 1
EXIT_ERROR = 2

# ── Import stages ───────────────────────────────────────────────────────────
# A stable name for WHERE an import was attempted. A production import failure
# is otherwise indistinguishable from any other error, and the exception's own
# message cannot be reported: on CPython it embeds the absolute filesystem path
# of the module that failed.
STAGE_BOOTSTRAP = 'bootstrap'
STAGE_APPLICATION_IMPORT = 'application_import'
STAGE_MODEL_IMPORT = 'model_import'
STAGE_SERVICE_IMPORT = 'service_import'
STAGE_PROFILER_IMPORT = 'profiler_import'
STAGE_REPORT_RENDERING = 'report_rendering'

REASON_IMPORT_FAILED = 'import_failed'

# A safe identifier is a dotted Python name and nothing else. Anything that
# fails this — a path, a message fragment, a URL — is dropped rather than
# reported, so a hostile or unusual exception attribute cannot leak.
_SAFE_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*$')


def safe_identifier(value):
    """Return ``value`` only when it is a plain dotted identifier, else None."""
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    if not candidate or len(candidate) > 200:
        return None
    return candidate if _SAFE_IDENTIFIER.match(candidate) else None


class DiagnosticImportError(Exception):
    """An import failure reduced to fields that are safe to publish.

    The originating exception is deliberately NOT retained. ``exc.path`` and
    ``str(exc)`` both carry an absolute filesystem path, and neither may reach
    an artifact.
    """

    def __init__(self, *, stage, target_module, target_symbol, exception_type,
                 module_name, missing_name):
        super().__init__(REASON_IMPORT_FAILED)
        self.stage = stage
        self.target_module = target_module
        self.target_symbol = target_symbol
        self.exception_type = exception_type
        self.module_name = module_name
        self.missing_name = missing_name

    @property
    def import_target(self):
        """What the code path MEANT to import — known, never reconstructed."""
        module = safe_identifier(self.target_module)
        symbol = safe_identifier(self.target_symbol)
        if module and symbol:
            return f'{module}.{symbol}'
        return module or symbol

    def to_payload(self):
        return {
            'capability': CAPABILITY,
            'mode': MODE,
            'schema_version': SCHEMA_VERSION,
            'result': RESULT_ERROR,
            'reason': REASON_IMPORT_FAILED,
            'exception_type': self.exception_type,
            'import_stage': self.stage,
            'module_name': self.module_name,
            'missing_name': self.missing_name,
            'import_target': self.import_target,
            'sanitized': True,
        }


@contextmanager
def importing(stage, target_module, target_symbol=None):
    """Convert an import failure into a publishable, sanitized description.

    The helper already knows the module and symbol it is attempting, so the
    identity comes from the call site rather than from parsing an exception
    message. ``exc.name`` is consulted only as a cross-check and only when it
    passes the identifier guard; ``exc.path`` is never read.
    """
    try:
        yield
    except (ModuleNotFoundError, ImportError) as exc:
        module_name = safe_identifier(getattr(exc, 'name', None))
        if module_name is None:
            module_name = safe_identifier(target_module)
        # CPython 3.11 does not expose the missing symbol on the exception, so
        # the only trustworthy source is what this call site asked for.
        missing_name = (
            safe_identifier(getattr(exc, 'name_from', None))
            or safe_identifier(target_symbol)
        )
        raise DiagnosticImportError(
            stage=stage,
            target_module=target_module,
            target_symbol=target_symbol,
            exception_type=type(exc).__name__,
            module_name=module_name,
            missing_name=missing_name,
        ) from None


DEFAULT_SAMPLE_SIZE = 60
MAX_IDS_PER_CATEGORY = 10
DEFAULT_LOOKBACK_DAYS = 7

# Mutually exclusive universe categories, in reading order.
CAT_ACTIVE_BULLPEN = 'active_bullpen'
CAT_ACTIVE_STARTER = 'active_starter'
CAT_ACTIVE_MIXED_UNKNOWN_ROLE = 'active_roster_mixed_or_unknown_role'
CAT_ACTIVE_NON_PITCHER = 'active_roster_non_pitcher'
CAT_INJURED_LIST = 'injured_list'
CAT_OPTIONED_MINORS = 'optioned_or_minors'
CAT_FORTY_MAN_NOT_ACTIVE = 'forty_man_not_active'
CAT_RESTRICTED_SPECIAL = 'restricted_or_special_list'
CAT_NON_ROSTER_DEPTH = 'non_roster_depth'
CAT_HISTORICAL_ONLY = 'historical_only'
CAT_UNKNOWN_ROSTER_AUTHORITY = 'unknown_roster_authority'
CAT_MISSING_MLB_ID = 'missing_mlb_id'

CATEGORY_ORDER = (
    CAT_ACTIVE_BULLPEN,
    CAT_ACTIVE_STARTER,
    CAT_ACTIVE_MIXED_UNKNOWN_ROLE,
    CAT_ACTIVE_NON_PITCHER,
    CAT_INJURED_LIST,
    CAT_OPTIONED_MINORS,
    CAT_FORTY_MAN_NOT_ACTIVE,
    CAT_RESTRICTED_SPECIAL,
    CAT_NON_ROSTER_DEPTH,
    CAT_HISTORICAL_ONLY,
    CAT_UNKNOWN_ROSTER_AUTHORITY,
    CAT_MISSING_MLB_ID,
)

# Categories sampled for the execution profile, in stratification order.
SAMPLE_STRATA = (
    CAT_ACTIVE_BULLPEN,
    CAT_ACTIVE_STARTER,
    CAT_ACTIVE_MIXED_UNKNOWN_ROLE,
    CAT_OPTIONED_MINORS,
    CAT_INJURED_LIST,
    CAT_HISTORICAL_ONLY,
    CAT_UNKNOWN_ROSTER_AUTHORITY,
)

# Tables whose row count and max(id) must not move.
WRITE_WATCH_TABLES = (
    'game_logs',
    'pitchers',
    'sync_runs',
    'sync_failures',
    'dashboard_snapshots',
    'scheduled_games',
)

# p99 needs enough observations to mean anything.
MIN_SAMPLE_FOR_P99 = 100
MIN_SAMPLE_FOR_P95 = 20
MIN_SAMPLE_FOR_P90 = 10


# ── Percentiles ─────────────────────────────────────────────────────────────
def percentile(values, fraction):
    """Textbook nearest-rank percentile: rank = ceil(fraction * n).

    No interpolation, so every reported value is an observation that actually
    happened, and the result is identical regardless of input order.
    """
    import math

    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    rank = max(1, min(len(ordered), math.ceil(fraction * len(ordered))))
    return ordered[rank - 1]


def distribution(values, *, unit='seconds'):
    """Summary statistics with explicit unsupported-percentile handling."""
    clean = [v for v in values if v is not None]
    count = len(clean)
    if not count:
        return {'count': 0, 'unit': unit, 'unsupported': ['p50', 'p90', 'p95', 'p99']}
    ordered = sorted(clean)
    unsupported = []
    p90 = percentile(ordered, 0.90) if count >= MIN_SAMPLE_FOR_P90 else None
    p95 = percentile(ordered, 0.95) if count >= MIN_SAMPLE_FOR_P95 else None
    p99 = percentile(ordered, 0.99) if count >= MIN_SAMPLE_FOR_P99 else None
    if p90 is None:
        unsupported.append('p90')
    if p95 is None:
        unsupported.append('p95')
    if p99 is None:
        unsupported.append('p99')
    return {
        'count': count,
        'unit': unit,
        'total': round(sum(ordered), 6),
        'min': round(ordered[0], 6),
        'mean': round(sum(ordered) / count, 6),
        'p50': round(percentile(ordered, 0.50), 6),
        'p90': round(p90, 6) if p90 is not None else None,
        'p95': round(p95, 6) if p95 is not None else None,
        'p99': round(p99, 6) if p99 is not None else None,
        'max': round(ordered[-1], 6),
        'unsupported': unsupported,
    }


# ── Deterministic stratified sampling ───────────────────────────────────────
def select_sample(by_category, size):
    """Round-robin across strata, each stratum ordered by mlb_id ascending.

    Deterministic for identical input regardless of database row order: the
    stratum order is fixed, and within a stratum the key is the immutable MLB
    identifier rather than a local row id or query order.
    """
    pools = {
        category: sorted(
            (row for row in by_category.get(category, []) if row['mlb_id'] is not None),
            key=lambda row: row['mlb_id'],
        )
        for category in SAMPLE_STRATA
    }
    chosen, cursor = [], 0
    while len(chosen) < size:
        progressed = False
        for category in SAMPLE_STRATA:
            pool = pools.get(category) or []
            if cursor < len(pool):
                chosen.append(pool[cursor])
                progressed = True
                if len(chosen) >= size:
                    break
        if not progressed:
            break
        cursor += 1
    return chosen


# ── Read-only enforcement ───────────────────────────────────────────────────
def enforce_read_only(session):
    """Make the DATABASE reject writes. Returns the protection actually applied."""
    with importing(STAGE_BOOTSTRAP, 'sqlalchemy', 'text'):
        from sqlalchemy import text
    with importing(STAGE_APPLICATION_IMPORT, 'utils.db', 'db'):
        from utils.db import db

    bind = session.get_bind() if hasattr(session, 'get_bind') else None
    dialect = getattr(getattr(bind, 'dialect', None), 'name', None)
    if not dialect:
        dialect = getattr(db.engine.dialect, 'name', 'unknown')
    if dialect == 'postgresql':
        session.execute(text('SET TRANSACTION READ ONLY'))
        return 'postgresql_read_only_transaction'
    return f'no_engine_level_read_only_available:{dialect}'


def read_only_guard(protection, write_probe, *, require_engine_read_only):
    """The safety decision, isolated so it can be proved without a database.

    Returns ``None`` when it is safe to proceed, or the failure payload that
    must stop the run before any production table is touched.
    """
    if require_engine_read_only and not str(protection).startswith('postgresql'):
        return _fail('read_only_boundary_unprovable', protection)
    # ``write_probe`` is None on the first call, before the probe has run. Only
    # a probe that ACTUALLY RAN and was not refused is a failure.
    if (require_engine_read_only and write_probe is not None
            and not write_probe.get('refused')):
        return _fail('write_probe_not_refused', write_probe)
    return None


def probe_write_refused(session):
    """Actively prove the boundary by attempting a write and expecting refusal.

    Setting a flag is a claim; a refused INSERT is evidence. The probe targets a
    temporary scratch table so it can never touch baseball state even in the
    failure case where the boundary is absent — and if the write SUCCEEDS the
    caller must treat the run as unsafe and stop.
    """
    with importing(STAGE_BOOTSTRAP, 'sqlalchemy', 'text'):
        from sqlalchemy import text

    try:
        session.execute(text(
            'CREATE TEMPORARY TABLE _f3c_write_probe (probe integer)'))
        session.execute(text('INSERT INTO _f3c_write_probe (probe) VALUES (1)'))
    except Exception as exc:
        session.rollback()
        return {'attempted': True, 'refused': True, 'error_class': type(exc).__name__}
    session.rollback()
    return {'attempted': True, 'refused': False, 'error_class': None}


def table_fingerprints(session):
    """Row count and max(id) per watched table. Missing tables report None."""
    with importing(STAGE_BOOTSTRAP, 'sqlalchemy', 'text'):
        from sqlalchemy import text

    fingerprints = {}
    for table in WRITE_WATCH_TABLES:
        try:
            row = session.execute(
                text(f'SELECT COUNT(*) AS n, COALESCE(MAX(id), 0) AS max_id FROM {table}')
            ).one()
            fingerprints[table] = {'rows': int(row[0]), 'max_id': int(row[1])}
        except Exception as exc:
            session.rollback()
            fingerprints[table] = {'rows': None, 'max_id': None,
                                   'error': type(exc).__name__}
    return fingerprints


def fingerprint_drift(before, after):
    drift = []
    for table in WRITE_WATCH_TABLES:
        start, end = before.get(table) or {}, after.get(table) or {}
        if start.get('rows') is None or end.get('rows') is None:
            continue
        if start['rows'] != end['rows'] or start['max_id'] != end['max_id']:
            drift.append({'table': table, 'before': start, 'after': end})
    return drift


# ── Diagnostic A: universe classification ───────────────────────────────────
def classify_universe(session, *, reference_date, lookback_days):
    with importing(STAGE_MODEL_IMPORT, 'models.game_log', 'GameLog'):
        from models.game_log import GameLog
    with importing(STAGE_MODEL_IMPORT, 'models.pitcher', 'Pitcher'):
        from models.pitcher import Pitcher
    with importing(STAGE_SERVICE_IMPORT, 'services.bullpen_eligibility'):
        from services import bullpen_eligibility
    with importing(STAGE_SERVICE_IMPORT, 'services.publication_criticality'):
        from services import publication_criticality
    with importing(STAGE_SERVICE_IMPORT, 'services.role_authority'):
        from services import role_authority
    with importing(STAGE_SERVICE_IMPORT, 'services.roster_authority',
                   'roster_status_category_for_status'):
        from services.roster_authority import (
            ROSTER_STATUS_CATEGORY_ACTIVE,
            ROSTER_STATUS_CATEGORY_FORTY_MAN_NOT_ACTIVE,
            ROSTER_STATUS_CATEGORY_INJURED_LIST,
            ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH,
            ROSTER_STATUS_CATEGORY_OPTIONED_OR_MINORS,
            ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL,
            ROSTER_STATUS_CATEGORY_UNKNOWN,
            roster_status_category_for_status,
        )

    timings = {}
    started = time.monotonic()
    # THE EXACT CURRENT DAILY UNIVERSE QUERY. Reproduced, not replaced.
    pitchers = session.query(Pitcher).filter(Pitcher.active.is_(True)).all()
    timings['universe_query_seconds'] = round(time.monotonic() - started, 6)

    lookback_start = reference_date - timedelta(days=lookback_days)

    started = time.monotonic()
    pitcher_ids = [p.id for p in pitchers]
    recent_logs = defaultdict(list)
    if pitcher_ids:
        rows = (
            session.query(GameLog)
            .filter(GameLog.pitcher_id.in_(pitcher_ids))
            .filter(GameLog.game_date >= lookback_start)
            .filter(GameLog.game_date <= reference_date)
            .all()
        )
        for row in rows:
            recent_logs[row.pitcher_id].append(row)
    timings['recent_appearance_prefetch_seconds'] = round(time.monotonic() - started, 6)

    started = time.monotonic()
    roster_category_to_universe = {
        ROSTER_STATUS_CATEGORY_INJURED_LIST: CAT_INJURED_LIST,
        ROSTER_STATUS_CATEGORY_OPTIONED_OR_MINORS: CAT_OPTIONED_MINORS,
        ROSTER_STATUS_CATEGORY_FORTY_MAN_NOT_ACTIVE: CAT_FORTY_MAN_NOT_ACTIVE,
        ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL: CAT_RESTRICTED_SPECIAL,
        ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH: CAT_NON_ROSTER_DEPTH,
    }

    by_category = defaultdict(list)
    criticality_counts = defaultdict(int)
    duplicate_mlb_ids = defaultdict(int)
    missing_mlb_id_rows = 0

    for pitcher in pitchers:
        mlb_id = getattr(pitcher, 'mlb_id', None)
        if mlb_id is not None:
            duplicate_mlb_ids[mlb_id] += 1

        logs = recent_logs.get(pitcher.id, [])
        has_any_appearance = bool(logs)
        has_relief_appearance = any(
            (getattr(log, 'games_started', None) == 0) for log in logs
        )

        roster_category = roster_status_category_for_status(
            getattr(pitcher, 'roster_status', None))
        criticality = publication_criticality.criticality_for_roster_status(
            getattr(pitcher, 'roster_status', None))
        criticality_counts[criticality] += 1

        position = str(getattr(pitcher, 'position', '') or '').strip().upper()

        # Mutually exclusive assignment, most specific first.
        if mlb_id is None:
            category = CAT_MISSING_MLB_ID
            missing_mlb_id_rows += 1
        elif roster_category == ROSTER_STATUS_CATEGORY_ACTIVE:
            if position and position not in bullpen_eligibility.PITCHING_POSITIONS:
                category = CAT_ACTIVE_NON_PITCHER
            else:
                role = role_authority.classify_role(
                    pitcher, logs, reference_date=reference_date)
                role_name = role.get('role')
                if role_name == role_authority.ROLE_RELIEVER:
                    category = CAT_ACTIVE_BULLPEN
                elif role_name == role_authority.ROLE_STARTER:
                    category = CAT_ACTIVE_STARTER
                elif role_name == role_authority.ROLE_NON_PITCHER:
                    category = CAT_ACTIVE_NON_PITCHER
                else:
                    category = CAT_ACTIVE_MIXED_UNKNOWN_ROLE
        elif roster_category == ROSTER_STATUS_CATEGORY_UNKNOWN:
            category = (CAT_HISTORICAL_ONLY if not has_any_appearance
                        else CAT_UNKNOWN_ROSTER_AUTHORITY)
        else:
            category = roster_category_to_universe.get(
                roster_category, CAT_HISTORICAL_ONLY)

        by_category[category].append({
            'pitcher_id': pitcher.id,
            'mlb_id': mlb_id,
            'team_id': getattr(pitcher, 'team_id', None),
            'position': position or None,
            'roster_status_category': roster_category,
            'criticality': criticality,
            'has_any_appearance_in_lookback': has_any_appearance,
            'has_relief_appearance_in_lookback': has_relief_appearance,
        })
    timings['classification_seconds'] = round(time.monotonic() - started, 6)

    total = len(pitchers)
    categories = []
    for name in CATEGORY_ORDER:
        rows = by_category.get(name, [])
        if not rows:
            categories.append({'category': name, 'count': 0, 'percent': 0.0,
                               'sample_mlb_ids': []})
            continue
        crit = defaultdict(int)
        for row in rows:
            crit[row['criticality']] += 1
        categories.append({
            'category': name,
            'count': len(rows),
            'percent': round(100.0 * len(rows) / total, 2) if total else 0.0,
            'criticality': dict(sorted(crit.items())),
            'source_authority': (
                'roster_authority.roster_status_category_for_status'
                ' + role_authority.classify_role'
                ' + bullpen_eligibility.PITCHING_POSITIONS'
                ' + GameLog appearance lookback'
            ),
            'with_relief_appearance_in_lookback': sum(
                1 for r in rows if r['has_relief_appearance_in_lookback']),
            'with_any_appearance_in_lookback': sum(
                1 for r in rows if r['has_any_appearance_in_lookback']),
            'daily_full_season_gamelog_appears_necessary': (
                name in (CAT_ACTIVE_BULLPEN, CAT_ACTIVE_MIXED_UNKNOWN_ROLE,
                         CAT_UNKNOWN_ROSTER_AUTHORITY)
            ),
            'sample_mlb_ids': [r['mlb_id'] for r in
                               sorted(rows, key=lambda r: (r['mlb_id'] or 0))
                               ][:MAX_IDS_PER_CATEGORY],
        })

    category_total = sum(entry['count'] for entry in categories)
    criticality_total = sum(criticality_counts.values())
    duplicates = {str(k): v for k, v in duplicate_mlb_ids.items() if v > 1}

    return {
        'reference_date': reference_date.isoformat(),
        'lookback_days': lookback_days,
        'selected_total': total,
        'categories': categories,
        'category_total': category_total,
        'criticality_counts': dict(sorted(criticality_counts.items())),
        'criticality_total': criticality_total,
        'anomalies': {
            'duplicate_mlb_ids': duplicates,
            'duplicate_mlb_id_count': len(duplicates),
            'missing_mlb_id_rows': missing_mlb_id_rows,
        },
        'timings': timings,
        'accounting': {
            'category_sum_equals_selected': category_total == total,
            'criticality_sum_equals_selected': criticality_total == total,
        },
    }, by_category


# ── Diagnostic B: bounded execution profile ─────────────────────────────────
def profile_sample(session, sample, *, reference_date, lookback_days, season):
    with importing(STAGE_MODEL_IMPORT, 'models.game_log', 'GameLog'):
        from models.game_log import GameLog
    # The SAME shared client instance services/sync.py uses, so the profile
    # measures the real production request path rather than a second one.
    with importing(STAGE_PROFILER_IMPORT, 'services.mlb_api', 'mlb_client'):
        from services.mlb_api import mlb_client

    client = mlb_client
    cutoff = reference_date - timedelta(days=lookback_days)

    started = time.monotonic()
    pitcher_ids = [row['pitcher_id'] for row in sample]
    existing_by_key = {}
    if pitcher_ids:
        for row in (
            session.query(GameLog)
            .filter(GameLog.pitcher_id.in_(pitcher_ids))
            .filter(GameLog.game_date >= date(season, 1, 1))
            .all()
        ):
            existing_by_key[(row.pitcher_id, row.mlb_game_pk)] = row
    prefetch_seconds = round(time.monotonic() - started, 6)

    observations = []
    api_calls = defaultdict(int)
    for row in sample:
        record = {
            'mlb_id': row['mlb_id'],
            'category': row['category'],
            'criticality': row['criticality'],
            'error': None,
        }
        total_started = time.monotonic()

        request_started = time.monotonic()
        try:
            splits = client.get_pitcher_game_logs(row['mlb_id'], season=season)
            api_calls['people_stats_gamelog'] += 1
        except Exception as exc:
            record['error'] = type(exc).__name__
            record['api_seconds'] = round(time.monotonic() - request_started, 6)
            record['total_seconds'] = round(time.monotonic() - total_started, 6)
            observations.append(record)
            continue
        record['api_seconds'] = round(time.monotonic() - request_started, 6)

        splits = splits or []
        record['splits_returned'] = len(splits)

        parse_started = time.monotonic()
        parsed = []
        for split in splits:
            game = split.get('game') or {}
            parsed.append({
                'game_pk': game.get('gamePk'),
                'date': split.get('date'),
                'stat': split.get('stat') or {},
            })
        record['parse_seconds'] = round(time.monotonic() - parse_started, 6)

        filter_started = time.monotonic()
        in_window = []
        for item in parsed:
            raw_date = item['date']
            if not raw_date or not item['game_pk']:
                continue
            try:
                parsed_date = date.fromisoformat(str(raw_date))
            except ValueError:
                continue
            if cutoff <= parsed_date <= reference_date:
                in_window.append(item)
        record['filter_seconds'] = round(time.monotonic() - filter_started, 6)
        record['splits_in_window'] = len(in_window)
        record['relevant_ratio'] = (
            round(len(in_window) / len(splits), 4) if splits else None)

        compare_started = time.monotonic()
        already_present = 0
        for item in in_window:
            if (row['pitcher_id'], item['game_pk']) in existing_by_key:
                already_present += 1
        record['compare_seconds'] = round(time.monotonic() - compare_started, 6)
        record['in_window_already_stored'] = already_present
        # No material change: every in-window split is already stored locally.
        record['no_change_candidate'] = (
            len(in_window) > 0 and already_present == len(in_window)
        ) or len(in_window) == 0

        record['total_seconds'] = round(time.monotonic() - total_started, 6)
        observations.append(record)

    successful = [o for o in observations if not o['error']]
    no_change = [o for o in successful if o.get('no_change_candidate')]

    by_category = defaultdict(list)
    by_criticality = defaultdict(list)
    for observation in successful:
        by_category[observation['category']].append(observation['total_seconds'])
        by_criticality[observation['criticality']].append(observation['total_seconds'])

    return {
        'season': season,
        'sample_size': len(sample),
        'observed': len(observations),
        'succeeded': len(successful),
        'failed': len(observations) - len(successful),
        'prefetch_seconds': prefetch_seconds,
        'api_calls_by_endpoint_family': dict(sorted(api_calls.items())),
        'stage_distributions': {
            'api_seconds': distribution([o.get('api_seconds') for o in successful]),
            'parse_seconds': distribution([o.get('parse_seconds') for o in successful]),
            'filter_seconds': distribution([o.get('filter_seconds') for o in successful]),
            'compare_seconds': distribution([o.get('compare_seconds') for o in successful]),
            'total_seconds': distribution([o.get('total_seconds') for o in successful]),
        },
        'total_seconds_by_category': {
            name: distribution(values) for name, values in sorted(by_category.items())
        },
        'total_seconds_by_criticality': {
            name: distribution(values) for name, values in sorted(by_criticality.items())
        },
        'response_size': {
            'splits_returned': distribution(
                [o.get('splits_returned') for o in successful], unit='splits'),
            'splits_in_window': distribution(
                [o.get('splits_in_window') for o in successful], unit='splits'),
            'relevant_ratio': distribution(
                [o.get('relevant_ratio') for o in successful], unit='ratio'),
        },
        'unchanged_cost': {
            'no_change_candidates': len(no_change),
            'no_change_share': (
                round(len(no_change) / len(successful), 4) if successful else None),
            'seconds_spent_on_no_change': round(
                sum(o['total_seconds'] for o in no_change), 6),
            'api_calls_spent_on_no_change': len(no_change),
            'note': (
                'A no-change candidate is a sampled pitcher whose every in-window '
                'split is already stored locally. Their requests were still made — '
                'nothing was skipped — so this is the measured cost an incremental '
                'detector could have avoided, not a projection.'
            ),
        },
        'observations': observations,
    }


def _fail(reason, detail=None):
    payload = {
        'capability': CAPABILITY, 'mode': MODE, 'schema_version': SCHEMA_VERSION,
        'result': RESULT_ERROR, 'reason': reason,
    }
    if detail:
        payload['detail'] = detail
    return payload


def _markdown(report):
    if report.get('reason') == REASON_IMPORT_FAILED:
        return '\n'.join([
            '# Foundation 3C — daily ingestion read-only diagnostic',
            '',
            '## Import failure',
            '',
            f"- Result: **{report.get('result')}**",
            f"- Exception type: `{report.get('exception_type')}`",
            f"- Import stage: `{report.get('import_stage')}`",
            f"- Module: `{report.get('module_name')}`",
            f"- Missing symbol: `{report.get('missing_name')}`",
            f"- Import target: `{report.get('import_target')}`",
            f"- Sanitized: **{report.get('sanitized')}**",
            '',
            'No exception message, traceback, or filesystem path is reported.',
        ]) + '\n'

    universe = report.get('universe') or {}
    profile = report.get('profile') or {}
    lines = [
        '# Foundation 3C — daily ingestion read-only diagnostic',
        '',
        f"- Result: **{report.get('result')}**",
        f"- Executed at: {report.get('executed_at')}",
        f"- Reference date: {universe.get('reference_date')}",
        f"- Read-only protection: `{report.get('read_only_protection')}`",
        f"- Write probe refused: **{(report.get('write_probe') or {}).get('refused')}**",
        f"- Production writes detected: **{len(report.get('write_drift') or [])}**",
        '',
        '## Pitcher universe',
        '',
        f"Selected by `Pitcher.active == True`: **{universe.get('selected_total')}**",
        '',
        '| Category | Count | % | Relief appearance in lookback | Any appearance |',
        '|---|---:|---:|---:|---:|',
    ]
    for entry in universe.get('categories') or []:
        lines.append(
            f"| {entry['category']} | {entry['count']} | {entry.get('percent', 0)} | "
            f"{entry.get('with_relief_appearance_in_lookback', 0)} | "
            f"{entry.get('with_any_appearance_in_lookback', 0)} |"
        )
    lines += [
        '',
        f"Criticality: {universe.get('criticality_counts')}",
        f"Category sum == selected: {universe.get('accounting', {}).get('category_sum_equals_selected')}",
        f"Criticality sum == selected: {universe.get('accounting', {}).get('criticality_sum_equals_selected')}",
        '',
        '## Execution profile',
        '',
        f"Sample: {profile.get('sample_size')} pitchers, "
        f"{profile.get('succeeded')} succeeded, {profile.get('failed')} failed",
        '',
        '| Stage | count | mean | p50 | p90 | p95 | max |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for stage, dist in (profile.get('stage_distributions') or {}).items():
        lines.append(
            f"| {stage} | {dist.get('count')} | {dist.get('mean')} | {dist.get('p50')} | "
            f"{dist.get('p90')} | {dist.get('p95')} | {dist.get('max')} |"
        )
    unchanged = profile.get('unchanged_cost') or {}
    lines += [
        '',
        '## Unchanged-pitcher cost',
        '',
        f"- No-change candidates: {unchanged.get('no_change_candidates')} "
        f"({unchanged.get('no_change_share')})",
        f"- Seconds spent on them: {unchanged.get('seconds_spent_on_no_change')}",
        f"- API calls spent on them: {unchanged.get('api_calls_spent_on_no_change')}",
    ]
    return '\n'.join(lines) + '\n'


def run(args):
    with importing(STAGE_APPLICATION_IMPORT, 'app', 'create_app'):
        from app import create_app
    with importing(STAGE_APPLICATION_IMPORT, 'utils.db', 'db'):
        from utils.db import db

    app = create_app()
    with app.app_context():
        session = db.session
        protection = enforce_read_only(session)
        blocked = read_only_guard(
            protection, None, require_engine_read_only=args.require_engine_read_only)
        if blocked is not None:
            return blocked, EXIT_ERROR

        write_probe = probe_write_refused(session)
        blocked = read_only_guard(
            protection, write_probe,
            require_engine_read_only=args.require_engine_read_only)
        if blocked is not None:
            # The boundary did not hold. Stop before touching production.
            return blocked, EXIT_ERROR
        # The probe rolled the transaction back, so re-arm the boundary.
        protection = enforce_read_only(session)

        before = table_fingerprints(session)

        reference_date = (
            date.fromisoformat(args.reference_date) if args.reference_date
            else datetime.now(timezone.utc).date()
        )
        season = args.season or reference_date.year

        universe, by_category = classify_universe(
            session, reference_date=reference_date, lookback_days=args.lookback_days)

        sample = []
        for row in select_sample(by_category, args.sample_size):
            for name, rows in by_category.items():
                if row in rows:
                    sample.append(dict(row, category=name))
                    break

        profile = (
            profile_sample(session, sample, reference_date=reference_date,
                           lookback_days=args.lookback_days, season=season)
            if sample and not args.skip_profile else
            {'sample_size': 0, 'skipped': True}
        )

        after = table_fingerprints(session)
        drift = fingerprint_drift(before, after)
        session.rollback()

        reconciled = (
            universe['accounting']['category_sum_equals_selected']
            and universe['accounting']['criticality_sum_equals_selected']
            and not drift
        )
        report = {
            'capability': CAPABILITY,
            'mode': MODE,
            'schema_version': SCHEMA_VERSION,
            'executed_at': datetime.now(timezone.utc).isoformat(),
            'result': RESULT_OK if reconciled else RESULT_RECONCILIATION,
            'read_only_protection': protection,
            'write_probe': write_probe,
            'table_fingerprints_before': before,
            'table_fingerprints_after': after,
            'write_drift': drift,
            'sample_selection': {
                'method': 'deterministic round-robin across fixed strata, '
                          'each stratum ordered by ascending MLB id',
                'requested_size': args.sample_size,
                'selected_size': len(sample),
                'strata': list(SAMPLE_STRATA),
                'selected_mlb_ids': [row['mlb_id'] for row in sample],
            },
            'universe': universe,
            'profile': profile,
        }
        return report, (EXIT_OK if reconciled else EXIT_RECONCILIATION)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--read-only', action='store_true',
                        help='Required. The command refuses to run without it.')
    parser.add_argument('--reference-date', default=None)
    parser.add_argument('--season', type=int, default=None)
    parser.add_argument('--lookback-days', type=int, default=DEFAULT_LOOKBACK_DAYS)
    parser.add_argument('--sample-size', type=int, default=DEFAULT_SAMPLE_SIZE)
    parser.add_argument('--skip-profile', action='store_true',
                        help='Classification only; makes no MLB request.')
    parser.add_argument('--require-engine-read-only', action='store_true',
                        help='Fail unless the database itself enforces read-only.')
    parser.add_argument('--output', default=None)
    parser.add_argument('--markdown-output', default=None)
    args = parser.parse_args(argv)

    if not args.read_only:
        report = _fail('read_only_flag_required',
                       'Pass --read-only to acknowledge the diagnostic boundary.')
        exit_code = EXIT_ERROR
    else:
        try:
            report, exit_code = run(args)
        except DiagnosticImportError as exc:
            # An import failure names its stage and target so the next repair is
            # exact. Nothing from the original exception is carried across.
            report, exit_code = exc.to_payload(), EXIT_ERROR
        except Exception as exc:
            # Class name only — messages can carry connection strings.
            report, exit_code = _fail('diagnostic_failed', type(exc).__name__), EXIT_ERROR

    rendered = json.dumps(report, indent=2, sort_keys=False, default=str)
    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered)
    if args.markdown_output and (
        report.get('result') != RESULT_ERROR
        or report.get('reason') == REASON_IMPORT_FAILED
    ):
        Path(args.markdown_output).write_text(_markdown(report))
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
