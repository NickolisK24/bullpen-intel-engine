"""
Shared sync service.

Consolidates the logic used by the /api/bullpen/sync endpoint and the
APScheduler daily job so both paths hit the same code. Keep this pure:
it only touches the DB and the MLB API — no Flask request objects,
no jsonify — so it can run from any context that has an app_context().
"""

from datetime import date, datetime, timedelta, timezone
import json
import logging
import os
import signal
import threading
import time
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import desc

from utils.db import db
from models.pitcher import Pitcher
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.play_by_play_foundation import PlayByPlayProcessedGame
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
from services import appearance_team_authority
from services import dead_letter
from services import pitcher_season_ledger_coverage
from services import publication_criticality
from services import schedule_authority, schedule_ingestion
from services import sync_jobs
from services import sync_metadata
from services.availability_reference_date import (
    product_availability_reference_date_from_metadata,
    resolve_product_day,
)
from services.completed_game_context_payload_adapter import build_completed_game_payload
from services.completed_game_context_service import (
    extract_completed_game_contexts,
    upsert_completed_game_context,
)
from services import evidence_contract
from services import game_driven_ingestion
from services import game_driven_realization
from services import game_log_reconciliation
from services import gamelog_source_authority
from services import pitcher_identity_reconciliation as pitcher_identity
from services import game_ingestion_completeness
from services.fatigue import calculate_fatigue
from services.game_finality import (
    FINAL_AND_USABLE,
    classify_game_finality,
    has_safe_final_status,
    scheduled_rows_have_unresolved_resumed_linkage,
)
from services.mlb_api import mlb_client
from services.play_by_play_foundation import (
    FINAL_PBP_FETCH_ENTITY_TYPE,
    process_final_play_by_play_foundation,
)
from services.public_roster_readiness import build_public_roster_readiness
from services.roster_evidence import build_run_roster_evidence
from services.roster_status import STATUS_ACTIVE, STATUS_UNKNOWN
from services.roster_status_sync import sync_roster_statuses
from services.team_game_pitching_splits import (
    safe_recompute_team_game_pitching_splits_for_game,
)
from services.team_assignment_sync import sync_team_assignments
from services.transaction_ingestion import sync_transactions
from utils.innings import (
    outs_to_decimal_innings,
    parse_mlb_innings_to_outs,
    validate_innings_outs,
)
from utils.games_started import parse_games_started
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)
PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE = 'pitcher_game_logs'
GAME_LOG_UNRESOLVED_FINALITY_ENTITY_TYPE = 'game_log_unresolved_finality'
DAILY_GAME_LOG_LANE_FAILURE_ENTITY_TYPE = 'daily_game_log_lane'
GAME_LOG_CORRECTION_FAILURE_ENTITY_TYPE = 'game_log_correction_attempt'
PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE = 'pitcher_resolution'
POSTGAME_GAME_FAILURE_ENTITY_TYPE = 'postgame_completed_game'
POSTGAME_CONTEXT_FAILURE_ENTITY_TYPE = 'postgame_completed_game_context'
WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE = 'phase0d_workload_evidence'
COMPOSED_READ_FAILURE_ENTITY_TYPE = 'phase0e_composed_reads'
LEGACY_READ_AUDIT_FAILURE_ENTITY_TYPE = 'phase0e_legacy_read_reconciliation_audit'
STAGE_LEGACY_READ_RECONCILIATION_AUDIT = 'legacy_read_reconciliation_audit'
POSTGAME_EARLY_MORNING_CUTOFF_HOUR = 6
POSTGAME_DEFAULT_LOOKBACK_DAYS = 2
DAILY_SYNC_DEFAULT_INGESTION_BUDGET_SECONDS = 720.0
DAILY_SYNC_DEFAULT_TOTAL_BUDGET_SECONDS = 1080.0
DAILY_SYNC_DEFAULT_FINAL_PHASE_RESERVE_SECONDS = 300.0

# The postgame refresh has never had a runtime budget: its stages are bounded
# by the number of unprocessed completed games, not by wall clock. The
# game-driven lane is different — it plans from the schedule ledger and can
# discover an arbitrarily large correction window — so it is given an explicit
# bounded slice rather than being allowed to run against the postgame command
# timeout. Reaching this budget is a clean, resumable, reported stop; running
# past the command timeout would kill the whole postgame refresh.
POSTGAME_REFRESH_DEFAULT_INGESTION_BUDGET_SECONDS = 600.0
DAILY_GAME_LOG_BUDGET_FAILURE_ENTITY_TYPE = 'daily_game_log_budget'
POSTGAME_SNAPSHOT_DEFAULT_TIMEOUT_SECONDS = 120.0
DAILY_GAME_LOG_CORRECTION_SOURCE = 'daily_game_log'
# Upper bound on box-score fetches the balls fallback may add to one run.
# The natural bound is the number of distinct games in the correction horizon
# (roughly a hundred over seven days), so this never binds in normal operation.
# It exists so a pathological horizon cannot spend the ingestion budget on
# fetches, and reaching it is counted and reported rather than absorbed.
BOXSCORE_FALLBACK_FETCH_CAP = 400
POSTGAME_BOXSCORE_CORRECTION_SOURCE = 'postgame_boxscore'
POSTGAME_PITCHER_RESOLUTION_SOURCE = 'mlb_stats_api:postgame_boxscore_pitching_line'
POSTGAME_PITCHING_LINE_AUTHORITY = 'completed_game_boxscore_pitching_section'
POSTGAME_PITCHER_TEAM_ASSIGNMENT_STATUS = 'ASSIGNED'
POSTGAME_ROSTER_AUTHORITY_PREPARATION_INCOMPLETE = (
    'postgame_roster_authority_preparation_incomplete'
)
OFFICIAL_ROSTER_SYNC_SOURCE_PREFIX = 'mlb_stats_api:roster_sync:'
OFFICIAL_TEAM_ASSIGNMENT_SOURCE_PREFIX = 'mlb_stats_api:team_assignment_sync:'
POSTGAME_MARKER_STATUS_FULLY_PROCESSED = PostgameProcessedGame.STATUS_FULLY_PROCESSED
POSTGAME_MARKER_STATUS_INCOMPLETE = PostgameProcessedGame.STATUS_INCOMPLETE
POSTGAME_MARKER_STATUS_FAILED = PostgameProcessedGame.STATUS_FAILED
POSTGAME_MARKER_RETRY_LIMIT = 3
_OPTIONAL_INPUT_NOT_PROVIDED = object()
_FALSEY_ENV_VALUES = {'0', 'false', 'no', 'off', 'disabled'}

# Correction safety and the correctable-field vocabulary are owned by the
# canonical reconciliation planner so the writer and the read-only projection
# cannot apply different rules. Re-exported under the historical private names
# because governed repair tooling reads them from this module by name.
_REQUIRED_CORRECTION_STAT_KEYS = game_log_reconciliation.REQUIRED_CORRECTION_STAT_KEYS
_OPTIONAL_BOOL_STAT_FIELDS = game_log_reconciliation.OPTIONAL_BOOL_STAT_FIELDS
_OPTIONAL_INT_STAT_FIELDS = game_log_reconciliation.OPTIONAL_INT_STAT_FIELDS

# ── Status file (written by the daily scheduler) ─────────────────────────────
_STATUS_DIR  = Path(__file__).resolve().parent.parent / 'logs'
STATUS_FILE  = _STATUS_DIR / 'sync_status.json'


def _ensure_logs_dir():
    _STATUS_DIR.mkdir(parents=True, exist_ok=True)


def _season_for(ref: date) -> int:
    """MLB seasons run roughly Feb–Nov. Use the calendar year of ref."""
    return ref.year


def postgame_schedule_date(now: datetime | None = None) -> date:
    """
    Resolve the MLB schedule date a postgame refresh should inspect.

    Evening GitHub Actions runs are UTC, while most MLB games complete late in
    the Eastern time window. Before the morning boundary, keep checking the
    prior baseball date so 1-3 AM ET cleanup runs do not accidentally scan the
    next empty slate.
    """
    local = resolve_product_day(now).local_datetime
    if local.hour < POSTGAME_EARLY_MORNING_CUTOFF_HOUR:
        return local.date() - timedelta(days=1)
    return local.date()


def _postgame_lookback_days() -> int:
    """Trailing slate dates a postgame refresh sweeps in addition to its
    primary date. Env-tunable; never negative."""
    raw = os.environ.get('POSTGAME_LOOKBACK_DAYS')
    try:
        value = int(raw) if raw not in (None, '') else POSTGAME_DEFAULT_LOOKBACK_DAYS
    except (TypeError, ValueError):
        value = POSTGAME_DEFAULT_LOOKBACK_DAYS
    return max(0, value)


def postgame_schedule_dates(
    now: datetime | None = None,
    lookback_days: int | None = None,
) -> list[date]:
    """
    Slate dates a postgame refresh sweeps, oldest first.

    A crashed or timed-out overnight run must self-heal: markers make
    re-checking an already-ingested slate nearly free (fully-processed games
    are skipped before any boxscore fetch), so each run re-sweeps the trailing
    dates. Oldest first, so recovery of a missed night lands even if the run
    is cut short.
    """
    if lookback_days is None:
        lookback_days = _postgame_lookback_days()
    primary = postgame_schedule_date(now)
    return [
        primary - timedelta(days=offset)
        for offset in range(lookback_days, -1, -1)
    ]


def is_completed_game(game: dict) -> bool:
    """Return True only for games with safe final status precedence."""
    return has_safe_final_status(game)


# Finality resolution for daily gameLog splits.
#
# The MLB `people/{id}/stats?stats=gameLog` endpoint returns a `game` object
# that does NOT carry a `status` block, so the split alone cannot prove the
# game is final. Treating "no status" as "not final" silently disabled the
# entire daily ingestion/correction lane (every split skipped). Instead we
# resolve finality from the durable schedule ledger (scheduled_games, ingested
# ±10 days daily): final there → ingest; determinately non-final → skip and
# retry on a later run; genuinely unknown → dead-letter, never silently drop.
SPLIT_FINALITY_FINAL = 'final'
SPLIT_FINALITY_NOT_FINAL = 'not_final'
SPLIT_FINALITY_UNKNOWN = 'unknown'


def _split_has_own_status(game_info: dict) -> bool:
    status = (game_info or {}).get('status')
    if not isinstance(status, dict):
        return False
    return any(
        status.get(key) not in (None, '')
        for key in ('statusCode', 'detailedState', 'abstractGameState')
    )


def resolve_scheduled_game_finality(game_pk, finality_cache: dict | None = None) -> str:
    """
    Resolve a game's finality from stored scheduled_games rows.

    Returns SPLIT_FINALITY_FINAL, SPLIT_FINALITY_NOT_FINAL, or
    SPLIT_FINALITY_UNKNOWN. Suspended games and unresolved resumed-game
    linkage fail closed to NOT_FINAL so partial lines are never ingested from
    the daily lane; they retry on later runs once linkage resolves.
    """
    if finality_cache is not None and game_pk in finality_cache:
        return finality_cache[game_pk]

    rows = ScheduledGame.query.filter_by(game_pk=game_pk).all()
    if not rows:
        state = SPLIT_FINALITY_UNKNOWN
    elif scheduled_rows_have_unresolved_resumed_linkage(rows):
        state = SPLIT_FINALITY_NOT_FINAL
    elif any(row.status_state == ScheduledGame.STATE_FINAL for row in rows):
        state = SPLIT_FINALITY_FINAL
    else:
        state = SPLIT_FINALITY_NOT_FINAL

    if finality_cache is not None:
        finality_cache[game_pk] = state
    return state


def completed_games_for_postgame_refresh(schedule_date: date) -> list[dict]:
    games = mlb_client.get_schedule(
        start_date=schedule_date.isoformat(),
        end_date=schedule_date.isoformat(),
    )
    completed = [game for game in (games or []) if is_completed_game(game)]
    seen_game_pks = {_game_pk(game) for game in completed if _game_pk(game)}
    for game in _stored_final_games_for_postgame_refresh(schedule_date):
        game_pk = _game_pk(game)
        if game_pk in seen_game_pks:
            continue
        completed.append(game)
        seen_game_pks.add(game_pk)
    return completed


def _scheduled_side_team(rows, side: str) -> dict:
    for row in rows:
        if row.home_away == side:
            return {'id': row.team_id}

    opposite_side = 'away' if side == 'home' else 'home'
    for row in rows:
        if row.home_away == opposite_side and row.opponent_team_id is not None:
            return {'id': row.opponent_team_id}
    return {}


def _stored_final_games_for_postgame_refresh(schedule_date: date) -> list[dict]:
    rows = (
        ScheduledGame.query
        .filter(ScheduledGame.game_date == schedule_date)
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .order_by(ScheduledGame.game_pk.asc(), ScheduledGame.team_id.asc())
        .all()
    )
    grouped = {}
    for row in rows:
        grouped.setdefault(row.game_pk, []).append(row)

    games = []
    for game_pk, game_rows in grouped.items():
        if scheduled_rows_have_unresolved_resumed_linkage(game_rows):
            continue
        status_code = next((row.status_code for row in game_rows if row.status_code), 'F')
        game_type = next((row.game_type for row in game_rows if row.game_type), 'R')
        games.append({
            'gamePk': game_pk,
            'gameType': game_type,
            'officialDate': schedule_date.isoformat(),
            'status': {
                'statusCode': status_code,
                'detailedState': 'Final',
                'abstractGameState': 'Final',
            },
            'teams': {
                'home': {'team': _scheduled_side_team(game_rows, 'home')},
                'away': {'team': _scheduled_side_team(game_rows, 'away')},
            },
            'source': 'scheduled_games',
        })
    return games


def _game_pk(game: dict):
    return (game or {}).get('gamePk')


def _game_team(game: dict, side: str) -> dict:
    return (((game or {}).get('teams') or {}).get(side) or {}).get('team') or {}


def _game_team_id(game: dict, side: str):
    return _game_team(game, side).get('id')


def _game_team_name(game: dict, side: str):
    return _game_team(game, side).get('name')


def _game_date(game: dict, fallback: date) -> date:
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        return fallback


def _marker_processing_status(marker: PostgameProcessedGame | None) -> str | None:
    if marker is None:
        return None
    return marker.processing_status or POSTGAME_MARKER_STATUS_FULLY_PROCESSED


def _postgame_marker_retryable(marker: PostgameProcessedGame | None) -> bool:
    if marker is None:
        return True
    return (
        _marker_processing_status(marker) == POSTGAME_MARKER_STATUS_INCOMPLETE
        and (marker.attempt_count or 0) < POSTGAME_MARKER_RETRY_LIMIT
    )


def _play_by_play_marker_retryable(marker: PlayByPlayProcessedGame | None) -> bool:
    if marker is None:
        return True
    if marker.processing_status == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED:
        return False
    if marker.processing_status == PlayByPlayProcessedGame.STATUS_FAILED:
        return False
    return (marker.attempt_count or 0) < 3


def _games_requiring_play_by_play_foundation(
    games: list[dict],
    *,
    exclude_game_pks=None,
) -> list[dict]:
    exclude_game_pks = set(exclude_game_pks or ())
    game_pks = [
        pk
        for pk in (_game_pk(game) for game in games)
        if pk and pk not in exclude_game_pks
    ]
    if not game_pks:
        return []
    markers = {
        marker.mlb_game_pk: marker
        for marker in (
            PlayByPlayProcessedGame.query
            .filter(PlayByPlayProcessedGame.mlb_game_pk.in_(game_pks))
            .all()
        )
    }
    postgame_markers = {
        marker.mlb_game_pk: marker
        for marker in (
            PostgameProcessedGame.query
            .filter(PostgameProcessedGame.mlb_game_pk.in_(game_pks))
            .all()
        )
    }
    return [
        game
        for game in games
        if (
            _game_pk(game) not in exclude_game_pks
            and _marker_processing_status(postgame_markers.get(_game_pk(game)))
            == POSTGAME_MARKER_STATUS_FULLY_PROCESSED
            and _play_by_play_marker_retryable(markers.get(_game_pk(game)))
        )
    ]


def _unprocessed_completed_games(games: list[dict]) -> tuple[list[dict], dict]:
    game_pks = [pk for pk in (_game_pk(game) for game in games) if pk]
    if not game_pks:
        return [], {
            'fully_processed': 0,
            'retryable_incomplete': 0,
            'failed': 0,
        }
    markers = {
        marker.mlb_game_pk: marker
        for marker in (
            PostgameProcessedGame.query
            .filter(PostgameProcessedGame.mlb_game_pk.in_(game_pks))
            .all()
        )
    }
    counts = {
        'fully_processed': 0,
        'retryable_incomplete': 0,
        'failed': 0,
    }
    pending = []
    for game in games:
        game_pk = _game_pk(game)
        marker = markers.get(game_pk)
        if marker is None:
            pending.append(game)
            continue

        status = _marker_processing_status(marker)
        if status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED:
            counts['fully_processed'] += 1
        elif _postgame_marker_retryable(marker):
            counts['retryable_incomplete'] += 1
            pending.append(game)
        else:
            counts['failed'] += 1

    return pending, counts


def _int_stat(stats: dict, key: str, default: int = 0) -> int:
    try:
        return int(stats.get(key, default) or default)
    except (TypeError, ValueError):
        return default


def _int_stat_or_none(stats: dict, key: str) -> int | None:
    raw = (stats or {}).get(key)
    if raw is None or raw == '':
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _int_stat_or_none_any(stats: dict, keys: tuple[str, ...]) -> int | None:
    stats = stats or {}
    for key in keys:
        if key in stats:
            return _int_stat_or_none(stats, key)
    return None


def _stat_key_present(stats: dict, keys: tuple[str, ...]) -> bool:
    stats = stats or {}
    return any(key in stats for key in keys)


def _positive_stat(stats: dict, key: str) -> bool:
    return _int_stat(stats, key) > 0


def _correction_source_state(stats: dict) -> tuple[bool, str | None, list[str]]:
    """Whether an official line may authorize a correction (canonical rule)."""
    return game_log_reconciliation.correction_source_state(stats)


def _extract_leverage_index(stats: dict):
    for li_key in ('leverageIndex', 'avgLeverageIndex', 'avgLI'):
        raw_li = (stats or {}).get(li_key)
        if raw_li is not None:
            try:
                return float(raw_li)
            except (TypeError, ValueError):
                return None
    return None


def _game_log_values_from_stats(
    *,
    stats: dict,
    pitcher,
    game_pk: int,
    game_date: date,
    game_type: str,
    opponent: str | None,
    opponent_abbreviation: str | None,
    games_started,
    include_leverage_index: bool = False,
    appearance_team: appearance_team_authority.AppearanceTeamResolution | None = None,
) -> dict:
    innings_pitched_outs = validate_innings_outs(
        parse_mlb_innings_to_outs(stats.get('inningsPitched', '0.0'))
    )
    values = {
        'pitcher_id': pitcher.id,
        'mlb_game_pk': game_pk,
        'game_date': game_date,
        'game_type': game_type,
        'opponent': opponent,
        'opponent_abbreviation': opponent_abbreviation,
        'games_started': games_started,
        'innings_pitched': outs_to_decimal_innings(innings_pitched_outs),
        'innings_pitched_outs': innings_pitched_outs,
        'pitches_thrown': _int_stat_or_none(stats, 'numberOfPitches'),
        'strikes': _int_stat(stats, 'strikes'),
        # Hits and walks are publication-critical WHIP inputs. Preserve an
        # omitted or malformed source value as unknown; zero is authoritative
        # only when the official source explicitly supplies zero.
        'hits_allowed': _int_stat_or_none(stats, 'hits'),
        'runs_allowed': _int_stat(stats, 'runs'),
        'earned_runs': _int_stat(stats, 'earnedRuns'),
        'walks': _int_stat_or_none(stats, 'baseOnBalls'),
        'strikeouts': _int_stat(stats, 'strikeOuts'),
        'home_runs_allowed': _int_stat(stats, 'homeRuns'),
        'batters_faced': _int_stat_or_none_any(stats, ('battersFaced', 'batters_faced')),
        'balls': _int_stat_or_none_any(stats, ('balls',)),
        'games_finished': _int_stat_or_none_any(stats, ('gamesFinished', 'games_finished')),
        'inherited_runners': _int_stat_or_none_any(stats, ('inheritedRunners', 'inherited_runners')),
        'inherited_runners_scored': _int_stat_or_none_any(
            stats,
            ('inheritedRunnersScored', 'inherited_runners_scored'),
        ),
        'save_situation': _positive_stat(stats, 'saveOpportunities'),
        'hold': _positive_stat(stats, 'holds'),
        'blown_save': _positive_stat(stats, 'blownSaves'),
        'win': _positive_stat(stats, 'wins'),
        'loss': _positive_stat(stats, 'losses'),
        'save': _positive_stat(stats, 'saves'),
    }
    if include_leverage_index:
        values['leverage_index'] = _extract_leverage_index(stats)
    if appearance_team is not None:
        # Freeze the team-at-appearance authority onto the row at write time
        # (Foundation 1). Resolved from official game-side evidence, never from the
        # pitcher's mutable current team. An unresolved/conflict appearance is still
        # stored, carrying a fail-closed status and no attributed team.
        values = appearance_team_authority.apply_to_new_log(values, appearance_team)
    return values


def _authoritative_correction_fields(values: dict, stats: dict, *, include_leverage_index: bool) -> list[str]:
    """The exact field set this writer may correct (canonical vocabulary)."""
    return game_log_reconciliation.correctable_fields(
        values, stats, include_leverage_index=include_leverage_index,
    )


def _record_unsafe_correction_attempt(
    *,
    pitcher,
    game_pk,
    reason,
    missing_keys=None,
    stats=None,
    source,
    sync_run_id=None,
    job_name='daily_sync',
):
    dead_letter.record_failure(
        GAME_LOG_CORRECTION_FAILURE_ENTITY_TYPE,
        f'unsafe correction source: {reason}',
        entity_ref=game_pk,
        payload={
            'pitcher_id': pitcher.id,
            'mlb_id': pitcher.mlb_id,
            'game_pk': game_pk,
            'source': source,
            'reason': reason,
            'missing_keys': list(missing_keys or []),
            'stat_keys': sorted((stats or {}).keys()),
        },
        sync_run_id=sync_run_id,
        job_name=job_name,
    )


# ── Dependent-evidence invalidation families ─────────────────────────────────
# The three evidence families a corrected GameLog invalidates. Named constants rather than
# inline strings so a caller can require the exact set rather than trusting a count.
EVIDENCE_FAMILY_WORKLOAD = 'workload'
EVIDENCE_FAMILY_APPEARANCE_CONTEXT = 'appearance_context'
EVIDENCE_FAMILY_INHERITED_TRAFFIC = 'inherited_traffic'
EVIDENCE_FAMILY_ENTRY_BAND_USAGE = 'entry_band_usage'
EVIDENCE_FAMILY_TEAM_RELIEF_COMPOSITION = 'team_relief_composition'
# Every evidence family that depends DIRECTLY on a corrected GameLog — that is, every module
# defining a ``mark_game_log_correction_for_*`` hook that cites ``source_table='game_logs'``.
# None of them is optional during the governed repair. A governed audit proves this tuple
# corresponds to the actual correction hooks rather than to a remembered list.
REQUIRED_EVIDENCE_FAMILIES = (
    EVIDENCE_FAMILY_WORKLOAD,
    EVIDENCE_FAMILY_APPEARANCE_CONTEXT,
    EVIDENCE_FAMILY_INHERITED_TRAFFIC,
    EVIDENCE_FAMILY_ENTRY_BAND_USAGE,
    EVIDENCE_FAMILY_TEAM_RELIEF_COMPOSITION,
)

EVIDENCE_FAMILY_COMPLETED = 'completed'
EVIDENCE_FAMILY_FAILED = 'failed'

# Typed failure reasons. "Zero rows matched" is NOT among them: a marker that ran correctly
# and found nothing to invalidate has completed, and conflating that with an exception would
# fail a repair for the entirely normal case of a corrected line with no dependent evidence.
EVIDENCE_FAILURE_MARKER_RAISED = 'marker_raised'
EVIDENCE_FAILURE_MARKER_ABSENT = 'required_marker_absent'
EVIDENCE_FAILURE_RESULT_MALFORMED = 'marker_result_malformed'
EVIDENCE_FAILURE_FLUSH_FAILED = 'evidence_flush_failed'

_EVIDENCE_MARKERS = (
    (
        EVIDENCE_FAMILY_WORKLOAD,
        'workload',
        'services.workload_recovery_evidence',
        'mark_game_log_correction_for_workload_recovery',
        'WORKLOAD_RULE_IDS',
    ),
    (
        EVIDENCE_FAMILY_APPEARANCE_CONTEXT,
        'appearance',
        'services.appearance_context_evidence',
        'mark_game_log_correction_for_appearance_context',
        'APPEARANCE_RULE_IDS',
    ),
    (
        EVIDENCE_FAMILY_INHERITED_TRAFFIC,
        'inherited traffic',
        'services.inherited_traffic_evidence',
        'mark_game_log_correction_for_inherited_traffic',
        'INHERITED_TRAFFIC_RULE_IDS',
    ),
    (
        EVIDENCE_FAMILY_ENTRY_BAND_USAGE,
        'entry band usage',
        'services.entry_band_usage_evidence',
        'mark_game_log_correction_for_entry_band_usage',
        'ENTRY_BAND_USAGE_RULE_IDS',
    ),
    (
        EVIDENCE_FAMILY_TEAM_RELIEF_COMPOSITION,
        'team relief composition',
        'services.team_relief_composition_evidence',
        'mark_game_log_correction_for_team_relief_composition',
        'TEAM_RELIEF_COMPOSITION_RULE_IDS',
    ),
)

# The source table every GameLog-correction marker cites.
EVIDENCE_SOURCE_TABLE = 'game_logs'
# The bounded batch size the markers already default to; strict mode loops at the same size
# rather than inventing a different one, so exhaustion is the only behavioural difference.
EVIDENCE_BATCH_SIZE = 100
# A deterministic ceiling on strict batches per family. Zero-progress detection already
# catches a stuck marker; this catches a marker that makes one row of progress forever.
STRICT_INVALIDATION_MAX_BATCHES = 1000

EVIDENCE_FAILURE_RESIDUAL_REMAINS = 'residual_current_dependent_evidence_remains'
EVIDENCE_FAILURE_NO_PROGRESS = 'batch_made_no_progress_while_residual_remained'
EVIDENCE_FAILURE_WRONG_SOURCE = 'evidence_id_belongs_to_another_source_row'
EVIDENCE_FAILURE_WRONG_FAMILY = 'evidence_id_belongs_to_another_family'
EVIDENCE_FAILURE_DOUBLE_COUNTED = 'evidence_object_inconsistently_counted'
EVIDENCE_FAILURE_OPERATION_ID = 'governed_operation_id_absent_or_misplaced'
EVIDENCE_FAILURE_SAFETY_LIMIT = 'exhaustive_invalidation_exceeded_safety_limit'
EVIDENCE_FAILURE_RESIDUAL_QUERY = 'residual_dependency_query_unavailable_or_contradictory'
# The backstop. Every registered family reported zero, and yet CURRENT evidence still cites
# this GameLog — which can only mean a direct dependency exists that the registry does not
# know about. Named as a registry gap rather than as a family failure, because no registered
# family failed.
EVIDENCE_FAILURE_UNREGISTERED_FAMILY = (
    'unregistered_direct_game_log_dependent_evidence_family')
UNREGISTERED_FAMILY_SENTINEL = '__unregistered_direct_game_log_dependency__'


class WorkloadEvidenceInvalidationError(Exception):
    """A required dependent-evidence invalidation did not complete under strict mode.

    Carries the per-family evidence gathered so far so a caller can report exactly which
    family failed and why, without re-deriving it from a log line.
    """

    def __init__(self, message, *, families=None, failed_families=None, game_log_id=None):
        super().__init__(message)
        self.families = families or {}
        self.failed_families = failed_families or []
        self.game_log_id = game_log_id


def _normalized_marker_result(result):
    """Validate one marker's return value and normalize it, or raise on a malformed shape.

    A marker that returns something other than a mapping carrying an integer ``marked_count``
    and an iterable ``evidence_ids`` has not told us whether it did its job. Under strict mode
    that is a failure, not a zero.
    """
    if not isinstance(result, dict):
        raise ValueError('marker result is not a mapping')
    if 'marked_count' not in result or 'evidence_ids' not in result:
        raise ValueError('marker result is missing marked_count or evidence_ids')
    raw_count = result.get('marked_count')
    if isinstance(raw_count, bool) or not isinstance(raw_count, int):
        raise ValueError('marked_count is not an integer')
    if raw_count < 0:
        raise ValueError('marked_count is negative')
    evidence_ids = result.get('evidence_ids')
    if evidence_ids is None:
        evidence_ids = []
    if isinstance(evidence_ids, (str, bytes)) or not isinstance(evidence_ids, (list, tuple)):
        raise ValueError('evidence_ids is not a sequence')
    return int(raw_count), list(evidence_ids)


def _notify_workload_evidence_game_log_correction(
    game_log,
    *,
    sync_run_id=None,
    strict=False,
    session=None,
):
    """Mark every dependent-evidence family a corrected GameLog invalidates.

    ``strict=False`` is the DEFAULT and is what ordinary ingestion uses: a marker failure is
    logged and the sweep continues, because a daily sync must not stop ingesting official
    corrections because an evidence table is momentarily unhappy. That trade is right for a
    process that runs again tomorrow.

    ``strict=True`` is for a one-time, atomic, reviewed repair, where it is wrong. There is no
    tomorrow: if the repair commits corrected rows while their dependent workload,
    appearance-context, or inherited-traffic evidence silently kept a stale value, nothing
    will notice and nothing will retry. Under strict mode every required family must complete,
    the pending evidence writes are flushed inside the caller's transaction, and any failure
    raises ``WorkloadEvidenceInvalidationError`` so the caller can roll the whole repair back.

    Completing with ``marked_count: 0`` is a SUCCESS in both modes. A corrected line with no
    dependent evidence is ordinary; only a marker that raised, was absent, returned a
    malformed result, or could not be flushed is a failure.
    """
    game_log_id = getattr(game_log, 'id', None)
    if not strict:
        return _notify_bounded_best_effort(game_log, sync_run_id=sync_run_id,
                                           game_log_id=game_log_id)
    return _notify_strict_exhaustive(game_log, sync_run_id=sync_run_id,
                                     game_log_id=game_log_id, session=session)


def _resolve_marker(module_name, function_name, rule_ids_name):
    module = __import__(module_name, fromlist=[function_name, rule_ids_name])
    marker = getattr(module, function_name, None)
    if marker is None or not callable(marker):
        raise AttributeError(f'{module_name}.{function_name} is not available')
    rule_ids = getattr(module, rule_ids_name, None)
    if not rule_ids:
        raise AttributeError(f'{module_name}.{rule_ids_name} is not available')
    return marker, tuple(rule_ids)


def _notify_bounded_best_effort(game_log, *, sync_run_id, game_log_id):
    """ONE bounded batch per family, warning and continuing on failure. Unchanged."""
    marked_count = 0
    evidence_ids = []
    for _family, label, module_name, function_name, _rules in _EVIDENCE_MARKERS:
        try:
            module = __import__(module_name, fromlist=[function_name])
            marker = getattr(module, function_name, None)
            if marker is None or not callable(marker):
                raise AttributeError(f'{module_name}.{function_name} is not available')
            result = marker(game_log, sync_run_id=sync_run_id)
            family_count, family_ids = _normalized_marker_result(result)
        except Exception as exc:  # noqa: BLE001 - ingestion must not block on evidence
            logger.warning(
                'Could not mark %s evidence for game_log correction id=%s: %s',
                label, game_log_id, exc,
            )
            continue
        marked_count += family_count
        evidence_ids.extend(family_ids)
    return {'marked_count': marked_count, 'evidence_ids': evidence_ids}


def _family_failure(families, family, reason, *, error_type=None, **extra):
    families[family] = dict(
        {'status': EVIDENCE_FAMILY_FAILED, 'reason': reason, 'error_type': error_type,
         'family': family, 'marked_unique_count': 0, 'evidence_ids': [],
         'exhaustive': False},
        **extra)
    return families


def _notify_strict_exhaustive(game_log, *, sync_run_id, game_log_id, session):
    """Every family driven to ZERO residual current dependent evidence, or raise.

    The bounded marker is the only thing that writes; this loops it and re-reads the
    authoritative residual population between batches. One successful bounded batch proves
    only that a batch completed — the citation query is limited BEFORE evidence ids are
    deduplicated, so a row with more than ``batch_size`` citations can return fewer unique
    objects than the limit and still leave current evidence behind. Committing a corrected
    GameLog beside evidence that still reads ``current`` is exactly the defect this repair
    exists to remove, so the residual is queried rather than inferred.
    """
    session = session or db.session
    families = {}

    if sync_run_id is None:
        raise WorkloadEvidenceInvalidationError(
            'strict dependent-evidence invalidation requires a governed operation id',
            families={}, failed_families=sorted(REQUIRED_EVIDENCE_FAMILIES),
            game_log_id=game_log_id)

    for family, _label, module_name, function_name, rule_ids_name in _EVIDENCE_MARKERS:
        # ``family`` is deliberately absent: _family_failure takes it positionally and
        # would collide with a duplicate keyword.
        base = {'source_table': EVIDENCE_SOURCE_TABLE,
                'source_pk': str(game_log_id), 'batch_size': EVIDENCE_BATCH_SIZE,
                'batch_count': 0, 'sync_run_id': sync_run_id,
                'initial_current_dependency_count': 0,
                'remaining_current_dependency_count': None}
        try:
            marker, rule_ids = _resolve_marker(module_name, function_name, rule_ids_name)
        except AttributeError as exc:
            _family_failure(families, family, EVIDENCE_FAILURE_MARKER_ABSENT,
                            error_type=type(exc).__name__, **base)
            raise WorkloadEvidenceInvalidationError(
                'a required dependent-evidence marker is unavailable',
                families=families, failed_families=[family],
                game_log_id=game_log_id) from exc

        def _residual():
            return evidence_contract.current_dependent_evidence_ids(
                source_table=EVIDENCE_SOURCE_TABLE, source_pk=game_log_id,
                rule_ids=rule_ids, session=session)

        try:
            remaining_ids = _residual()
        except Exception as exc:  # noqa: BLE001 - an unreadable residual is not a zero
            _family_failure(families, family, EVIDENCE_FAILURE_RESIDUAL_QUERY,
                            error_type=type(exc).__name__, **base)
            raise WorkloadEvidenceInvalidationError(
                'the residual dependency population could not be read',
                families=families, failed_families=[family],
                game_log_id=game_log_id) from exc

        initial_count = len(remaining_ids)
        marked_unique = []
        marked_seen = set()
        batch_count = 0

        while remaining_ids:
            if batch_count >= STRICT_INVALIDATION_MAX_BATCHES:
                _family_failure(families, family, EVIDENCE_FAILURE_SAFETY_LIMIT,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count,
                                       remaining_current_dependency_count=len(remaining_ids)))
                raise WorkloadEvidenceInvalidationError(
                    'exhaustive dependent-evidence invalidation exceeded its safety limit',
                    families=families, failed_families=[family], game_log_id=game_log_id)

            before_count = len(remaining_ids)
            try:
                # sync_run_id is deliberately NOT forwarded to the marker.
                # ``evidence_objects.sync_run_id`` is a FOREIGN KEY into ``sync_runs``, and
                # the governed repair operation id is deliberately not a sync run — no sync
                # run performs this repair. Writing it there violates the constraint on
                # PostgreSQL and would fail the repair on its first marked row. The governed
                # id stays where it belongs: on the corrected GameLog's
                # ``last_stat_correction_sync_run_id`` (a plain integer, no FK), in this
                # result, and in the execution ledger.
                result = marker(game_log, sync_run_id=None,
                                batch_size=EVIDENCE_BATCH_SIZE, rule_ids=rule_ids,
                                session=session)
                batch_count_marked, batch_ids = _normalized_marker_result(result)
            except Exception as exc:  # noqa: BLE001 - classified, never silently dropped
                reason = (EVIDENCE_FAILURE_RESULT_MALFORMED if isinstance(exc, ValueError)
                          else EVIDENCE_FAILURE_MARKER_RAISED)
                _family_failure(families, family, reason, error_type=type(exc).__name__,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count))
                raise WorkloadEvidenceInvalidationError(
                    'a dependent-evidence batch did not complete',
                    families=families, failed_families=[family],
                    game_log_id=game_log_id) from exc

            # Provenance of every returned id, proven against the database rather than
            # taken from the marker's own word.
            split = evidence_contract.evidence_ids_for_source_and_family(
                evidence_ids=batch_ids, source_table=EVIDENCE_SOURCE_TABLE,
                source_pk=game_log_id, rule_ids=rule_ids, session=session)
            if split['wrong_source'] or split['wrong_family']:
                reason = (EVIDENCE_FAILURE_WRONG_SOURCE if split['wrong_source']
                          else EVIDENCE_FAILURE_WRONG_FAMILY)
                _family_failure(families, family, reason,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count,
                                       wrong_source_ids=split['wrong_source'][:20],
                                       wrong_family_ids=split['wrong_family'][:20]))
                raise WorkloadEvidenceInvalidationError(
                    'a dependent-evidence batch returned an id from another source or family',
                    families=families, failed_families=[family], game_log_id=game_log_id)

            repeated = [value for value in batch_ids if value in marked_seen]
            if repeated or batch_count_marked != len(set(batch_ids)):
                _family_failure(families, family, EVIDENCE_FAILURE_DOUBLE_COUNTED,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count,
                                       repeated_ids=sorted(set(repeated))[:20]))
                raise WorkloadEvidenceInvalidationError(
                    'a dependent-evidence object was counted inconsistently',
                    families=families, failed_families=[family], game_log_id=game_log_id)
            for value in batch_ids:
                marked_seen.add(value)
                marked_unique.append(value)

            try:
                session.flush()
            except Exception as exc:  # noqa: BLE001 - the flush is part of the contract
                _family_failure(families, family, EVIDENCE_FAILURE_FLUSH_FAILED,
                                error_type=type(exc).__name__,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count))
                raise WorkloadEvidenceInvalidationError(
                    'dependent-evidence writes could not be flushed',
                    families=families, failed_families=[family],
                    game_log_id=game_log_id) from exc

            # The governed operation id must not have leaked into the foreign-key column.
            stored = evidence_contract.evidence_sync_run_ids(
                evidence_ids=batch_ids, session=session)
            if any(value == sync_run_id for value in stored.values()):
                _family_failure(families, family, EVIDENCE_FAILURE_OPERATION_ID,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count))
                raise WorkloadEvidenceInvalidationError(
                    'the governed operation id was written into a sync-run foreign key',
                    families=families, failed_families=[family], game_log_id=game_log_id)

            batch_count += 1
            try:
                remaining_ids = _residual()
            except Exception as exc:  # noqa: BLE001
                _family_failure(families, family, EVIDENCE_FAILURE_RESIDUAL_QUERY,
                                error_type=type(exc).__name__,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count))
                raise WorkloadEvidenceInvalidationError(
                    'the residual dependency population could not be re-read',
                    families=families, failed_families=[family],
                    game_log_id=game_log_id) from exc

            if len(remaining_ids) >= before_count:
                _family_failure(families, family, EVIDENCE_FAILURE_NO_PROGRESS,
                                **dict(base, batch_count=batch_count,
                                       initial_current_dependency_count=initial_count,
                                       remaining_current_dependency_count=len(remaining_ids)))
                raise WorkloadEvidenceInvalidationError(
                    'a dependent-evidence batch made no progress while residual remained',
                    families=families, failed_families=[family], game_log_id=game_log_id)

        # Final authoritative residual, re-read once more and cross-checked against itself.
        try:
            final_ids = _residual()
            confirm_ids = _residual()
        except Exception as exc:  # noqa: BLE001
            _family_failure(families, family, EVIDENCE_FAILURE_RESIDUAL_QUERY,
                            error_type=type(exc).__name__,
                            **dict(base, batch_count=batch_count,
                                   initial_current_dependency_count=initial_count))
            raise WorkloadEvidenceInvalidationError(
                'the final residual dependency query was unavailable',
                families=families, failed_families=[family],
                game_log_id=game_log_id) from exc
        if final_ids != confirm_ids:
            _family_failure(families, family, EVIDENCE_FAILURE_RESIDUAL_QUERY,
                            **dict(base, batch_count=batch_count,
                                   initial_current_dependency_count=initial_count))
            raise WorkloadEvidenceInvalidationError(
                'the final residual dependency query contradicted itself',
                families=families, failed_families=[family], game_log_id=game_log_id)
        if final_ids:
            _family_failure(families, family, EVIDENCE_FAILURE_RESIDUAL_REMAINS,
                            **dict(base, batch_count=batch_count,
                                   initial_current_dependency_count=initial_count,
                                   remaining_current_dependency_count=len(final_ids)))
            raise WorkloadEvidenceInvalidationError(
                'current dependent evidence remains after exhaustive invalidation',
                families=families, failed_families=[family], game_log_id=game_log_id)

        families[family] = {
            'status': EVIDENCE_FAMILY_COMPLETED,
            'reason': None,
            'family': family,
            'source_table': EVIDENCE_SOURCE_TABLE,
            'source_pk': str(game_log_id),
            'batch_size': EVIDENCE_BATCH_SIZE,
            'batch_count': batch_count,
            'initial_current_dependency_count': initial_count,
            'marked_unique_count': len(marked_seen),
            'marked_count': len(marked_seen),
            'evidence_ids': sorted(marked_seen),
            'remaining_current_dependency_count': 0,
            'exhaustive': True,
            'sync_run_id': sync_run_id,
        }

    missing = [family for family in REQUIRED_EVIDENCE_FAMILIES if family not in families]
    if missing:
        raise WorkloadEvidenceInvalidationError(
            'a required dependent-evidence family was not attempted',
            families=families, failed_families=sorted(missing), game_log_id=game_log_id)

    # ── Final UNSCOPED direct-dependency backstop ────────────────────────────
    # Every registered family reported zero. That is a statement about the families this
    # registry knows about, and the registry is a list someone maintains. This query asks the
    # database the question the registry cannot: does ANY current evidence still cite this
    # corrected GameLog, under any rule id at all?
    #
    # Success is never inferred from the sum of the family results. A future sixth direct
    # GameLog-dependent family added without a registry entry would pass every per-family
    # check and be caught here.
    try:
        unscoped_ids = evidence_contract.current_dependent_evidence_ids(
            source_table=EVIDENCE_SOURCE_TABLE, source_pk=game_log_id, rule_ids=None,
            session=session)
    except Exception as exc:  # noqa: BLE001 - an unreadable backstop is not a zero
        raise WorkloadEvidenceInvalidationError(
            'the final unscoped dependency query was unavailable',
            families=families,
            failed_families=[UNREGISTERED_FAMILY_SENTINEL],
            game_log_id=game_log_id) from exc

    if unscoped_ids:
        residual_rule_ids = evidence_contract.evidence_rule_ids(
            evidence_ids=unscoped_ids, session=session)
        families[UNREGISTERED_FAMILY_SENTINEL] = {
            'status': EVIDENCE_FAMILY_FAILED,
            'reason': EVIDENCE_FAILURE_UNREGISTERED_FAMILY,
            'error_type': None,
            'family': UNREGISTERED_FAMILY_SENTINEL,
            'source_table': EVIDENCE_SOURCE_TABLE,
            'source_pk': str(game_log_id),
            'batch_size': EVIDENCE_BATCH_SIZE,
            'batch_count': 0,
            'initial_current_dependency_count': len(unscoped_ids),
            'marked_unique_count': 0,
            'evidence_ids': sorted(unscoped_ids)[:100],
            'residual_rule_ids': sorted({value for value in residual_rule_ids.values()
                                         if value is not None}),
            'remaining_current_dependency_count': len(unscoped_ids),
            'exhaustive': False,
            'sync_run_id': sync_run_id,
        }
        raise WorkloadEvidenceInvalidationError(
            'current evidence still cites this GameLog under no registered family',
            families=families, failed_families=[UNREGISTERED_FAMILY_SENTINEL],
            game_log_id=game_log_id)

    return {
        'marked_count': sum(item['marked_unique_count'] for item in families.values()),
        'evidence_ids': sorted(
            value for item in families.values() for value in item['evidence_ids']),
        'families': families,
        'all_required_families_completed': True,
        'failed_families': [],
        'exhaustive': True,
        'final_unscoped_current_dependency_count': 0,
        'final_unscoped_residual_rule_ids': [],
        'all_direct_game_log_dependencies_exhausted': True,
        'registered_families': list(REQUIRED_EVIDENCE_FAMILIES),
        'game_log_id': game_log_id,
        'sync_run_id': sync_run_id,
        'session_id': id(session),
        'strict': True,
    }


def direct_game_log_evidence_registry() -> dict:
    """The governed registry, resolved: family -> module, marker name, rule ids.

    Resolving it rather than describing it is the point — an entry naming a marker that does
    not exist, or a rule vocabulary that is empty, is a registry defect and must be visible as
    one rather than as a runtime surprise mid-repair.
    """
    resolved = {}
    for family, label, module_name, function_name, rule_ids_name in _EVIDENCE_MARKERS:
        module = __import__(module_name, fromlist=[function_name, rule_ids_name])
        marker = getattr(module, function_name, None)
        rule_ids = getattr(module, rule_ids_name, None)
        resolved[family] = {
            'family': family,
            'label': label,
            'module': module_name,
            'marker_name': function_name,
            'marker_is_callable': callable(marker),
            'rule_ids_name': rule_ids_name,
            'rule_ids': tuple(rule_ids or ()),
        }
    return resolved


def _upsert_game_log_from_authoritative_values(
    *,
    pitcher,
    game_pk,
    values,
    stats,
    source,
    sync_run_id=None,
    job_name='daily_sync',
    include_leverage_index=False,
    existing=_OPTIONAL_INPUT_NOT_PROVIDED,
    appearance_team=None,
    fallback_source=None,
    fallback_fields=(),
):
    if existing is _OPTIONAL_INPUT_NOT_PROVIDED:
        existing = GameLog.query.filter_by(
            pitcher_id=pitcher.id,
            mlb_game_pk=game_pk,
        ).first()

    # ONE authority decides what happens to this row. The writer applies that
    # decision; the read-only projection reports it. Neither recalculates it,
    # which is what let shadow and write disagree before.
    plan = game_log_reconciliation.plan_row(
        existing=existing,
        values=values,
        stats=stats,
        include_leverage_index=include_leverage_index,
        appearance_team=appearance_team,
        game_pk=game_pk,
        pitcher_mlb_id=getattr(pitcher, 'mlb_id', None),
        local_pitcher_id=getattr(pitcher, 'id', None),
    )

    if plan['action'] == game_log_reconciliation.ACTION_INSERT:
        log = GameLog(**values)
        db.session.add(log)
        return {
            'status': 'inserted',
            'log': log,
            'changed_fields': [],
            'plan': plan,
        }

    if plan['action'] == game_log_reconciliation.ACTION_BLOCKED:
        _record_unsafe_correction_attempt(
            pitcher=pitcher,
            game_pk=game_pk,
            reason=plan['blocked_reason'],
            missing_keys=plan.get('blocked_missing_keys') or [],
            stats=stats,
            source=source,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        return {
            'status': 'unsafe',
            'log': existing,
            'changed_fields': [],
            'reason': plan['blocked_reason'],
            'plan': plan,
        }

    if plan['action'] == game_log_reconciliation.ACTION_UNCHANGED:
        return {
            'status': 'unchanged',
            'log': existing,
            'changed_fields': [],
            'plan': plan,
        }

    # Apply exactly the planned mutation, field by field. Team-at-appearance
    # authority (Foundation 1) is part of the same plan but is a separate
    # category: a stat-only correction never erases team attribution, and an
    # unchanged re-sweep never backfills a legacy row.
    stat_changed_fields = []
    for change in plan['field_changes']:
        field = change['field']
        if change['category'] == (
            game_log_reconciliation.CATEGORY_APPEARANCE_TEAM_AUTHORITY
        ):
            continue
        setattr(existing, field, values[field])
        stat_changed_fields.append(field)

    # Derived companions (D-008: decimal innings) are APPLIED whenever their
    # semantic authority moved, re-derived from the governed values. They are
    # never independently corrected and never counted as changed evidence, but
    # they must be written — the stored-state invariant requires the companion
    # to agree with its authority, and the database enforces it.
    for companion in plan.get('derived_companion_fields') or ():
        if companion in values:
            setattr(existing, companion, values[companion])

    appearance_reason = plan['appearance_team_reason']
    decision = plan.get('appearance_team_decision')
    if decision:
        for field, value in decision['fields'].items():
            setattr(existing, field, value)

    if not plan['provenance_update']:
        db.session.add(existing)
        return {
            'status': 'corrected',
            'log': existing,
            'changed_fields': [],
            'appearance_team_reason': appearance_reason,
            'plan': plan,
        }

    # Provenance names the authority for the values that actually moved. When a
    # correction was only possible because a fallback source supplied a field
    # the lane's own source omits, recording the lane's source would credit an
    # endpoint that never carried the value.
    recorded_source = source
    if fallback_source and any(
        field in set(fallback_fields or ()) for field in stat_changed_fields
    ):
        recorded_source = fallback_source

    existing.stat_correction_count = (existing.stat_correction_count or 0) + 1
    existing.last_stat_correction_at = utc_now_naive()
    existing.last_stat_correction_source = recorded_source
    existing.last_stat_correction_sync_run_id = sync_run_id
    db.session.add(existing)
    _notify_workload_evidence_game_log_correction(
        existing,
        sync_run_id=sync_run_id,
    )
    return {
        'status': 'corrected',
        'log': existing,
        'changed_fields': stat_changed_fields,
        'appearance_team_reason': appearance_reason,
        'plan': plan,
    }


def _positive_external_id(raw):
    if isinstance(raw, bool) or raw in (None, ''):
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _position_value(position):
    if not isinstance(position, dict):
        return position
    return (
        position.get('abbreviation')
        or position.get('code')
        or position.get('type')
        or position.get('name')
    )


def _position_code(position):
    if not isinstance(position, dict):
        return None
    return position.get('code') or position.get('abbreviation')


def _position_name(position):
    if not isinstance(position, dict):
        return None
    return position.get('name') or position.get('type')


def _normalized_position(value):
    raw = _position_value(value)
    return str(raw).strip().upper() if raw not in (None, '') else None


def _pitching_line_record_position(line: dict):
    position = line.get('position')
    return str(position).strip().upper() if position not in (None, '') else None


def _is_pitching_position(position):
    normalized = _normalized_position(position)
    return normalized is None or normalized in {'P', 'PITCHER'}


def _is_authoritative_completed_game_pitching_line(line: dict, game: dict) -> bool:
    return (
        line.get('source') == POSTGAME_PITCHER_RESOLUTION_SOURCE
        and line.get('authority') == POSTGAME_PITCHING_LINE_AUTHORITY
        and is_completed_game(game)
        and bool(line.get('stats'))
    )


def _position_override_from_pitching_line(line: dict, game: dict) -> bool:
    return (
        _is_authoritative_completed_game_pitching_line(line, game)
        and not _is_pitching_position(line.get('position'))
    )


def _team_abbreviation_from(team: dict | None):
    team = team or {}
    return (
        team.get('abbreviation')
        or team.get('teamCode')
        or team.get('fileCode')
    )


def _resolve_pitching_line_team(game: dict, line: dict) -> tuple[dict | None, str | None]:
    side = line.get('side')
    if side not in {'home', 'away'}:
        return None, 'missing_or_invalid_team_side'

    game_team_id = _positive_external_id(_game_team_id(game, side))
    line_team_id = _positive_external_id(line.get('team_id'))
    if game_team_id and line_team_id and game_team_id != line_team_id:
        return None, 'conflicting_team_assignment'

    team_id = line_team_id or game_team_id
    if team_id is None:
        return None, 'missing_team_assignment'

    game_team = _game_team(game, side)
    return {
        'team_id': team_id,
        'team_name': line.get('team') or game_team.get('name'),
        'team_abbreviation': (
            line.get('team_abbreviation')
            or _team_abbreviation_from(game_team)
        ),
    }, None


def _record_pitcher_resolution_failure(
    *,
    line,
    game,
    reason,
    source=POSTGAME_PITCHER_RESOLUTION_SOURCE,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
):
    game_pk = _game_pk(game)
    dead_letter.record_failure(
        PITCHER_RESOLUTION_FAILURE_ENTITY_TYPE,
        f'unresolvable pitcher line: {reason}',
        entity_ref=game_pk,
        payload={
            'game_pk': game_pk,
            'mlb_game_pk': game_pk,
            'source': source,
            'reason': reason,
            'player_id': line.get('player_id'),
            'person_id': line.get('person_id'),
            'name': line.get('name'),
            'side': line.get('side'),
            'team_side': line.get('side'),
            'team_id': line.get('team_id'),
            'team': line.get('team'),
            'position': line.get('position'),
            'position_code': line.get('position_code'),
            'position_name': line.get('position_name'),
            'stat_keys': sorted((line.get('stats') or {}).keys()),
        },
        sync_run_id=sync_run_id,
        job_name=job_name,
    )


def _pitcher_resolution_failure(
    *,
    line,
    game,
    reason,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
    record: bool = True,
) -> dict:
    """The one unresolved-line verdict. ``record=False`` reaches the same
    verdict without dead-lettering, so a read-only projection classifies a line
    exactly as the writer would while writing nothing."""
    if record:
        _record_pitcher_resolution_failure(
            line=line,
            game=game,
            reason=reason,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
    return {
        'status': 'unresolved',
        'pitcher': None,
        'reason': reason,
        'created': False,
        'reactivated': False,
    }


def _source_startswith(value, prefix):
    return bool(value and str(value).startswith(prefix))


def _official_roster_cache_blocks_postgame_active(pitcher):
    source = getattr(pitcher, 'roster_status_source', None)
    if not _source_startswith(source, OFFICIAL_ROSTER_SYNC_SOURCE_PREFIX):
        return False
    return getattr(pitcher, 'roster_status', None) != STATUS_ACTIVE


def _official_assignment_blocks_postgame_current(pitcher, team):
    source = getattr(pitcher, 'team_assignment_source', None)
    if not _source_startswith(source, OFFICIAL_TEAM_ASSIGNMENT_SOURCE_PREFIX):
        return False
    status = getattr(pitcher, 'team_assignment_status', None)
    current_team_id = getattr(pitcher, 'team_id', None)
    return (
        status != POSTGAME_PITCHER_TEAM_ASSIGNMENT_STATUS
        or current_team_id not in (None, team.get('team_id'))
    )


def _appearance_team_context(team: dict) -> dict:
    """Historical team-at-appearance context, for REPORTING only.

    Handed to the identity planner so a plan can state that the appearance team
    differs from the current assignment. It is never applied to the Pitcher row;
    the historical team already lives on the GameLog appearance-team fields.
    """
    team = team or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _identity_resolution(plan, pitcher, *, position_override):
    """Uniform resolution result carrying the canonical identity plan."""
    action = plan.get('action')
    return {
        'status': {
            pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY: 'would_create',
            pitcher_identity.ACTION_BLOCKED: 'blocked',
        }.get(action, 'resolved'),
        'pitcher': pitcher,
        'created': action == pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
        # Retired: completed-game evidence can no longer reactivate anyone.
        'reactivated': False,
        'reason': plan.get('blocked_reason'),
        'position_override_from_pitching_line': position_override,
        'identity_action': action,
        'identity_plan': plan,
        'identity_changed_fields': list(plan.get('changed_fields') or ()),
    }


def resolve_pitcher_for_authoritative_line(
    line: dict,
    game: dict,
    *,
    local_pitchers=None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
    plan_only: bool = False,
):
    """
    Resolve a pitcher from a completed-game pitching line under D-009.

    The box-score pitching line is authority for WHO appeared. It is not
    authority for anything about that person's CURRENT state, so an existing
    Pitcher row is never modified here — not reactivated, not reassigned, not
    renamed, not restatused. Historical/current differences are reported as
    suppressed evidence by the canonical identity planner and refused.

    A missing row may be created minimally, because a new appearance cannot be
    persisted without one. That creation claims no current team, no active
    status, and no official roster status.

    ``plan_only`` reaches the identical verdict while writing nothing. Both
    modes consume the SAME plan, so shadow and write cannot classify a line
    differently.
    """
    player_id = _positive_external_id(line.get('player_id'))
    if player_id is None:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason=pitcher_identity.BLOCKED_MISSING_PLAYER_ID,
            sync_run_id=sync_run_id,
            job_name=job_name,
            record=not plan_only,
        )

    person_id = _positive_external_id(line.get('person_id'))
    if person_id is not None and person_id != player_id:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason=pitcher_identity.BLOCKED_CONFLICTING_IDENTITY,
            sync_run_id=sync_run_id,
            job_name=job_name,
            record=not plan_only,
        )

    team, team_error = _resolve_pitching_line_team(game, line)
    if team_error:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason=team_error,
            sync_run_id=sync_run_id,
            job_name=job_name,
            record=not plan_only,
        )

    line_position = _normalized_position(line.get('position'))
    authoritative_pitching_line = _is_authoritative_completed_game_pitching_line(
        line,
        game,
    )
    position_override = _position_override_from_pitching_line(line, game)
    if (
        line_position is not None
        and line_position not in {'P', 'PITCHER'}
        and not position_override
    ):
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason=pitcher_identity.BLOCKED_NON_PITCHER_POSITION,
            sync_run_id=sync_run_id,
            job_name=job_name,
            record=not plan_only,
        )

    local_pitchers = local_pitchers if local_pitchers is not None else {}
    pitcher = local_pitchers.get(player_id)
    if pitcher is None:
        pitcher = Pitcher.query.filter_by(mlb_id=player_id).first()

    if pitcher is not None:
        existing_position = _normalized_position(pitcher.position)
        if (
            existing_position is not None
            and existing_position not in {'P', 'PITCHER'}
            and not authoritative_pitching_line
        ):
            return _pitcher_resolution_failure(
                line=line,
                game=game,
                reason=pitcher_identity.BLOCKED_LOCAL_RECORD_NOT_PITCHER,
                sync_run_id=sync_run_id,
                job_name=job_name,
                record=not plan_only,
            )

    plan = pitcher_identity.plan_identity(
        existing=pitcher,
        player_mlb_id=player_id,
        line_name=line.get('name'),
        line_position=_pitching_line_record_position(line),
        appearance_team=_appearance_team_context(team),
        position_override=position_override,
    )

    if plan['action'] == pitcher_identity.ACTION_BLOCKED:
        return _pitcher_resolution_failure(
            line=line,
            game=game,
            reason=plan['blocked_reason'],
            sync_run_id=sync_run_id,
            job_name=job_name,
            record=not plan_only,
        )

    if plan['action'] == pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY:
        if plan_only:
            # No local record means no stored appearance row, so the GameLog
            # plan for this line is unambiguously an insert.
            return _identity_resolution(
                plan, None, position_override=position_override,
            )
        # Exactly the planned values and nothing else. Building the row from the
        # plan rather than from the line is what keeps the applied write equal to
        # the reviewed one.
        pitcher = Pitcher(**plan['creation_values'])
        db.session.add(pitcher)
        db.session.flush()
        local_pitchers[player_id] = pitcher
        return _identity_resolution(
            plan, pitcher, position_override=position_override,
        )

    # Existing row: resolved, and untouched. Nothing is added to the session,
    # so an unchanged appearance cannot hide a pitcher write.
    local_pitchers[player_id] = pitcher
    return _identity_resolution(plan, pitcher, position_override=position_override)


def _pitcher_order_by_side(boxscore: dict) -> dict[str, list[int]]:
    teams = (boxscore or {}).get('teams') or {}
    return {
        side: list(((teams.get(side) or {}).get('pitchers') or []))
        for side in ('home', 'away')
    }


def _extract_pitching_lines_from_boxscore(boxscore: dict) -> list[dict]:
    pitchers = []
    for side in ('home', 'away'):
        team_data = ((boxscore or {}).get('teams') or {}).get(side) or {}
        team_info = team_data.get('team') or {}
        player_data = team_data.get('players') or {}
        candidates = [
            (pitcher_id, f'ID{pitcher_id}')
            for pitcher_id in (team_data.get('pitchers') or [])
        ]
        candidate_keys = {key for _pitcher_id, key in candidates}
        for player_key, player in player_data.items():
            stats = ((player.get('stats') or {}).get('pitching') or {})
            if stats and player_key not in candidate_keys:
                person = player.get('person') or {}
                candidates.append((person.get('id'), player_key))

        for pitcher_id, player_key in candidates:
            player = player_data.get(player_key) or {}
            person = player.get('person') or {}
            position = (
                player.get('position')
                or person.get('primaryPosition')
                or {}
            )
            stats = ((player.get('stats') or {}).get('pitching') or {})
            if stats:
                pitchers.append({
                    'player_id': pitcher_id,
                    'person_id': person.get('id'),
                    'name': person.get('fullName'),
                    'team': team_info.get('name'),
                    'team_id': team_info.get('id'),
                    'team_abbreviation': _team_abbreviation_from(team_info),
                    'position': _position_value(position),
                    'position_code': _position_code(position),
                    'position_name': _position_name(position),
                    'source': POSTGAME_PITCHER_RESOLUTION_SOURCE,
                    'authority': POSTGAME_PITCHING_LINE_AUTHORITY,
                    'stats': stats,
                    'side': side,
                })
    return pitchers


def _line_games_started(line: dict, pitcher_order: dict[str, list[int]]) -> int:
    stats = line.get('stats') or {}
    parsed = parse_games_started(stats.get('gamesStarted'))
    if parsed is not None:
        return parsed
    side_pitchers = pitcher_order.get(line.get('side')) or []
    return 1 if side_pitchers and side_pitchers[0] == line.get('player_id') else 0


def _opponent_for_line(game: dict, line: dict, team_abbr_map: dict) -> tuple[str | None, str | None]:
    opponent_side = 'away' if line.get('side') == 'home' else 'home'
    opponent_id = _game_team_id(game, opponent_side)
    return _game_team_name(game, opponent_side), team_abbr_map.get(opponent_id)


class _PlannedPitcher(NamedTuple):
    """Read-only stand-in for a pitcher the writer would create.

    Planning must build the same governed values the writer would, but must not
    create the row. Carrying ``id=None`` is what makes the plan an insert: no
    stored appearance can be keyed to a pitcher that does not exist yet.
    """

    id: int | None
    mlb_id: int | None
    team_id: int | None
    team_abbreviation: str | None


def _unresolved_row_plan(*, game_pk, line, reason) -> dict:
    """Plan entry for a pitching line whose pitcher identity is unresolved.

    Reported identically by the writer and by the read-only projection, so an
    unresolved line can never be classified one way in shadow and another in
    write.
    """
    return {
        'plan_version': game_log_reconciliation.RECONCILIATION_PLAN_VERSION,
        'game_pk': game_pk,
        'pitcher_mlb_id': _positive_external_id(line.get('player_id')),
        'local_pitcher_id': None,
        'natural_key': {'pitcher_id': None, 'mlb_game_pk': game_pk},
        'action': game_log_reconciliation.ACTION_BLOCKED,
        'changed_fields': [],
        'field_changes': [],
        'changed_field_count': 0,
        'mutation_categories': [
            game_log_reconciliation.CATEGORY_PITCHER_IDENTITY,
            game_log_reconciliation.CATEGORY_BLOCKED,
        ],
        'appearance_team_reason': None,
        'provenance_update': False,
        'affects_published_evidence': False,
        'is_statistical_correction': False,
        'is_provenance_only': False,
        'governed_and_safe': False,
        'blocked_reason': 'pitcher_identity_unresolved',
        'unresolved_reason': reason,
        'complete_plan_version': game_log_reconciliation.COMPLETE_PLAN_VERSION,
        'pitcher_identity': pitcher_identity.plan_identity(
            existing=None,
            player_mlb_id=_positive_external_id(line.get('player_id')),
            line_name=line.get('name'),
            blocked_reason=reason,
        ),
        'pitcher_identity_action': pitcher_identity.ACTION_BLOCKED,
        'pitcher_identity_blocked_reason': reason,
        'pitcher_identity_mutation_digest': '',
        'source_authority': None,
    }


def _ingest_boxscore_pitching_line(
    pitcher,
    line: dict,
    game: dict,
    *,
    game_date: date,
    team_abbr_map: dict,
    pitcher_order: dict[str, list[int]],
    sync_run_id=None,
    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
    plan_only: bool = False,
    identity_plan=None,
    pitcher_mlb_id=None,
) -> dict:
    game_pk = _game_pk(game)
    if not game_pk:
        return {'status': 'skipped', 'reason': 'missing_game_pk'}

    stats = line.get('stats') or {}
    opponent, opponent_abbreviation = _opponent_for_line(game, line, team_abbr_map)
    # Team-at-appearance authority: the official box-score pitching side (already
    # validated for game-side/line conflicts by _resolve_pitching_line_team) is the
    # authoritative source; cross-check against the schedule ledger's opponent side.
    appearance_team = _appearance_team_for_boxscore_line(game, line, game_pk)
    values = _game_log_values_from_stats(
        stats=stats,
        pitcher=pitcher,
        game_pk=game_pk,
        game_date=game_date,
        game_type=(game or {}).get('gameType', 'R'),
        opponent=opponent,
        opponent_abbreviation=opponent_abbreviation,
        games_started=_line_games_started(line, pitcher_order),
        include_leverage_index=True,
        appearance_team=appearance_team,
    )
    if plan_only:
        # The identical decision, taken by the identical planner, with nothing
        # written. A pitcher that does not exist locally owns no appearance row.
        existing = (
            GameLog.query.filter_by(
                pitcher_id=pitcher.id, mlb_game_pk=game_pk,
            ).first()
            if pitcher is not None else None
        )
        plan = game_log_reconciliation.plan_row(
            existing=existing,
            values=values,
            stats=stats,
            include_leverage_index=True,
            appearance_team=appearance_team,
            game_pk=game_pk,
            pitcher_mlb_id=(
                pitcher_mlb_id if pitcher_mlb_id is not None
                else getattr(pitcher, 'mlb_id', None)
            ),
            local_pitcher_id=getattr(pitcher, 'id', None),
            identity_plan=identity_plan,
        )
        return {
            'status': _STATUS_BY_PLAN_ACTION[plan['action']],
            'log': existing,
            'changed_fields': list(plan['changed_fields']),
            'reason': plan['blocked_reason'],
            'plan': plan,
        }

    result = _upsert_game_log_from_authoritative_values(
        pitcher=pitcher,
        game_pk=game_pk,
        values=values,
        stats=stats,
        source=POSTGAME_BOXSCORE_CORRECTION_SOURCE,
        sync_run_id=sync_run_id,
        job_name=job_name,
        include_leverage_index=True,
        appearance_team=appearance_team,
    )
    plan = result.get('plan')
    if plan is not None:
        # Every field the complete fingerprint reads, not just the label.
        # The writer builds its plan without the identity half and patches it on
        # here, so anything omitted at this point is missing from the write's
        # fingerprint while shadow carries it — which is precisely how a
        # reviewed authorization and the applied write drift apart.
        plan['pitcher_identity'] = identity_plan or {}
        plan['pitcher_identity_action'] = (identity_plan or {}).get('action')
        plan['pitcher_identity_blocked_reason'] = (
            (identity_plan or {}).get('blocked_reason')
        )
        plan['pitcher_identity_mutation_digest'] = (
            (identity_plan or {}).get('mutation_digest') or ''
        )
        plan['complete_plan_version'] = (
            game_log_reconciliation.COMPLETE_PLAN_VERSION
        )
        # The category means "this run would write a Pitcher row", so it is
        # attached only to a genuine identity mutation.
        if pitcher_identity.is_mutation(identity_plan) and (
            game_log_reconciliation.CATEGORY_PITCHER_IDENTITY
            not in plan['mutation_categories']
        ):
            plan['mutation_categories'] = [
                category for category in game_log_reconciliation.CATEGORIES
                if category in set(
                    plan['mutation_categories']
                    + [game_log_reconciliation.CATEGORY_PITCHER_IDENTITY]
                )
            ]
    return result


_STATUS_BY_PLAN_ACTION = {
    game_log_reconciliation.ACTION_INSERT: 'inserted',
    game_log_reconciliation.ACTION_UPDATE: 'corrected',
    game_log_reconciliation.ACTION_UNCHANGED: 'unchanged',
    game_log_reconciliation.ACTION_BLOCKED: 'unsafe',
}


def _appearance_team_for_boxscore_line(game: dict, line: dict, game_pk):
    """Resolve the team-at-appearance for a box-score pitching line (Foundation 1).

    The box-score side is authoritative; the schedule ledger's opponent side is a
    cross-check that fails closed to ``conflict`` on a definite disagreement. Returns
    an ``unresolved`` resolution if the official side cannot be determined — never a
    guess and never the pitcher's current team.
    """
    team, _team_error = _resolve_pitching_line_team(game, line)
    boxscore_team_id = team['team_id'] if team else None
    opposite_side = 'away' if line.get('side') == 'home' else 'home'
    opponent_team_id = _positive_external_id(_game_team_id(game, opposite_side))
    return appearance_team_authority.resolve_for_write(
        boxscore_team_id=boxscore_team_id,
        game_pk=game_pk,
        opponent_team_id=opponent_team_id,
    )


def _postgame_incomplete_reason(
    *,
    pitching_lines_seen: int,
    pitcher_resolution_failures: int,
    correction_attempts_failed: int,
) -> str | None:
    if pitching_lines_seen <= 0:
        return 'empty_pitching_data'
    if pitcher_resolution_failures:
        return 'pitcher_resolution_failures'
    if correction_attempts_failed:
        return 'unsafe_correction_attempts'
    return None


def _postgame_processing_status_for_attempt(reason: str | None, attempt_count: int) -> str:
    if reason is None:
        return POSTGAME_MARKER_STATUS_FULLY_PROCESSED
    if attempt_count >= POSTGAME_MARKER_RETRY_LIMIT:
        return POSTGAME_MARKER_STATUS_FAILED
    return POSTGAME_MARKER_STATUS_INCOMPLETE


def _record_postgame_retry_exhausted_failure(
    *,
    marker: PostgameProcessedGame,
    game: dict,
    reason: str,
    pitching_lines_seen: int,
    pitcher_resolution_failures: int,
    correction_attempts_failed: int,
    sync_run_id=None,
):
    dead_letter.record_failure(
        POSTGAME_GAME_FAILURE_ENTITY_TYPE,
        f'postgame processing retry limit reached: {reason}',
        entity_ref=marker.mlb_game_pk,
        payload={
            'game_pk': marker.mlb_game_pk,
            'schedule_game_status': game.get('status') if isinstance(game, dict) else None,
            'attempt_count': marker.attempt_count,
            'retry_limit': POSTGAME_MARKER_RETRY_LIMIT,
            'processing_status': marker.processing_status,
            'incomplete_reason': reason,
            'pitching_lines_seen': pitching_lines_seen,
            'pitcher_resolution_failures': pitcher_resolution_failures,
            'correction_attempts_failed': correction_attempts_failed,
        },
        sync_run_id=sync_run_id,
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
    )


def _upsert_postgame_processed_marker(
    *,
    existing_marker: PostgameProcessedGame | None,
    game: dict,
    game_date: date,
    logs_added: int,
    pitchers_touched: int,
    pitching_lines_seen: int,
    pitcher_resolution_failures: int,
    correction_attempts_failed: int,
    sync_run_id=None,
    correction_recheck: bool = False,
) -> tuple[PostgameProcessedGame, bool]:
    attempted_at = utc_now_naive()
    previous_status = _marker_processing_status(existing_marker)
    prior_attempts = (existing_marker.attempt_count if existing_marker else 0) or 0
    # A governed correction re-check of an ALREADY fully-processed game is not a
    # retry. Counting it would burn the retry budget a genuine future failure
    # needs — after a week inside the correction horizon every game would sit at
    # the retry limit and the next real incomplete read would go straight to
    # `failed`.
    already_complete_recheck = (
        correction_recheck
        and previous_status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED
    )
    attempt_count = max(
        prior_attempts if already_complete_recheck else prior_attempts + 1, 1
    )
    incomplete_reason = _postgame_incomplete_reason(
        pitching_lines_seen=pitching_lines_seen,
        pitcher_resolution_failures=pitcher_resolution_failures,
        correction_attempts_failed=correction_attempts_failed,
    )
    processing_status = _postgame_processing_status_for_attempt(
        incomplete_reason,
        attempt_count,
    )
    if already_complete_recheck and incomplete_reason is not None:
        # The game was already PROVEN complete from its official box score. A
        # correction re-check that comes back degraded is evidence about the
        # re-read, not evidence that the proven ledger is now wrong — so the
        # marker the appearance-ledger publication gate reads is not demoted by
        # a transient source blip. The caller that requested the re-check still
        # fails its own work item closed on the same shortfall, so the trust
        # signal is preserved in the lane that owns it.
        incomplete_reason = existing_marker.incomplete_reason
        processing_status = POSTGAME_MARKER_STATUS_FULLY_PROCESSED
        pitching_lines_seen = existing_marker.pitching_lines_seen or 0
        pitcher_resolution_failures = (
            existing_marker.pitcher_resolution_failures or 0
        )
        correction_attempts_failed = existing_marker.correction_attempts_failed or 0
        logs_added = existing_marker.logs_added or 0

    marker = existing_marker or PostgameProcessedGame(mlb_game_pk=_game_pk(game))
    marker.game_date = game_date
    marker.game_type = (game or {}).get('gameType')
    marker.home_team_id = _game_team_id(game, 'home')
    marker.away_team_id = _game_team_id(game, 'away')
    marker.final_state = ((game or {}).get('status') or {}).get('detailedState')
    marker.logs_added = logs_added
    marker.pitchers_touched = pitchers_touched
    marker.sync_run_id = sync_run_id
    marker.processing_status = processing_status
    marker.attempt_count = attempt_count
    marker.last_attempted_at = attempted_at
    marker.incomplete_reason = incomplete_reason
    marker.pitching_lines_seen = pitching_lines_seen
    marker.pitcher_resolution_failures = pitcher_resolution_failures
    marker.correction_attempts_failed = correction_attempts_failed

    if processing_status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED:
        marker.processed_at = attempted_at
        marker.failed_at = None
    elif processing_status == POSTGAME_MARKER_STATUS_FAILED:
        marker.processed_at = None
        marker.failed_at = marker.failed_at or attempted_at
    else:
        marker.processed_at = None
        marker.failed_at = None

    db.session.add(marker)
    retry_exhausted = (
        processing_status == POSTGAME_MARKER_STATUS_FAILED
        and previous_status != POSTGAME_MARKER_STATUS_FAILED
        and incomplete_reason is not None
    )
    if retry_exhausted:
        _record_postgame_retry_exhausted_failure(
            marker=marker,
            game=game,
            reason=incomplete_reason,
            pitching_lines_seen=pitching_lines_seen,
            pitcher_resolution_failures=pitcher_resolution_failures,
            correction_attempts_failed=correction_attempts_failed,
            sync_run_id=sync_run_id,
        )
    return marker, retry_exhausted


def process_completed_game_for_postgame_refresh(
    game: dict,
    *,
    schedule_date: date,
    sync_run_id=None,
    force: bool = False,
    plan_only: bool = False,
    boxscore=None,
) -> dict:
    """Fetch one final game once and reconcile its pitching lines idempotently.

    ``force`` bypasses ONLY the fully-processed / retry-limit short-circuit, so
    a caller that owns its own completion contract — the Foundation 3C
    game-driven lane, which re-examines recent final games inside a bounded
    correction horizon — can re-read a game whose official line may have been
    corrected. Every write below stays idempotent and governed: the same
    unique key, the same correction-safety checks, the same marker.

    ``plan_only`` runs this same path and returns the canonical reconciliation
    plan WITHOUT writing: no GameLog is inserted or corrected, no pitcher is
    created or reconciled, no marker is upserted, no failure is dead-lettered.
    It is the read-only projection's only entry point, so shadow and write are
    the same code reaching the same verdict rather than two implementations
    that can drift. ``plan_only`` implies ``force``: a projection reports what
    would happen to the game it was asked about, never a marker short-circuit.
    """
    force = force or plan_only
    game_pk = _game_pk(game)
    if not game_pk:
        return {
            'game_pk': None,
            'logs_added': 0,
            'logs_corrected': 0,
            'correction_attempts_failed': 0,
            'pitcher_resolution_failures': 0,
            'pitchers_created': 0,
            'pitchers_reactivated': 0,
            'position_overrides_from_pitching_line': 0,
            'pitchers_touched': 0,
            'pitching_lines_seen': 0,
            'processing_status': None,
            'incomplete_reason': 'missing_game_pk',
            'attempt_count': 0,
            'retry_exhausted': False,
            'skipped': True,
            'reason': 'missing_game_pk',
        }

    existing_marker = PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).first()
    if (
        not force
        and existing_marker is not None
        and not _postgame_marker_retryable(existing_marker)
    ):
        processing_status = _marker_processing_status(existing_marker)
        return {
            'game_pk': game_pk,
            'logs_added': 0,
            'logs_corrected': 0,
            'correction_attempts_failed': 0,
            'pitcher_resolution_failures': 0,
            'pitchers_created': 0,
            'pitchers_reactivated': 0,
            'position_overrides_from_pitching_line': 0,
            'pitchers_touched': 0,
            'pitching_lines_seen': existing_marker.pitching_lines_seen or 0,
            'processing_status': processing_status,
            'incomplete_reason': existing_marker.incomplete_reason,
            'attempt_count': existing_marker.attempt_count or 0,
            'retry_exhausted': False,
            'skipped': True,
            'reason': (
                'already_processed'
                if processing_status == POSTGAME_MARKER_STATUS_FULLY_PROCESSED
                else 'retry_limit_reached'
            ),
        }

    # A caller that already fetched this game's official evidence may supply it,
    # so a reviewed plan and its application read the SAME box score and one run
    # makes one request per game.
    if boxscore is None:
        boxscore = mlb_client.get_game_boxscore(game_pk)
    finality = classify_game_finality(game, boxscore=boxscore, require_boxscore=True)
    pitching_lines = _extract_pitching_lines_from_boxscore(boxscore)
    pitcher_order = _pitcher_order_by_side(boxscore)
    player_ids = sorted({
        player_id
        for player_id in (
            _positive_external_id(line.get('player_id'))
            for line in pitching_lines
        )
        if player_id is not None
    })
    local_pitchers = {
        pitcher.mlb_id: pitcher
        for pitcher in (
            Pitcher.query
            .filter(Pitcher.mlb_id.in_(player_ids or [-1]))
            .all()
        )
    }
    team_abbr_map = dict(
        db.session.query(Pitcher.team_id, Pitcher.team_abbreviation)
        .filter(Pitcher.team_abbreviation.isnot(None))
        .distinct()
        .all()
    )
    game_date = _game_date(game, schedule_date)
    logs_added = 0
    logs_corrected = 0
    correction_attempts_failed = 0
    pitcher_resolution_failures = 0
    pitchers_created = 0
    pitchers_reactivated = 0
    position_overrides_from_pitching_line = 0
    touched_pitcher_ids = set()
    if finality.state != FINAL_AND_USABLE:
        logger.info(
            'Postgame finality pending for game_pk=%s state=%s reason=%s',
            game_pk,
            finality.state,
            finality.reason,
        )

    reconciliation_plan = []
    for line in pitching_lines:
        resolution = resolve_pitcher_for_authoritative_line(
            line,
            game,
            local_pitchers=local_pitchers,
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            plan_only=plan_only,
        )
        pitcher = resolution['pitcher']
        if pitcher is None and resolution['status'] == 'would_create':
            # Planning only: stand in for the pitcher the writer would create,
            # so the row plan is built from the same governed values. It owns no
            # local id, so it can own no existing appearance row.
            pitcher = _PlannedPitcher(
                id=None,
                mlb_id=_positive_external_id(line.get('player_id')),
                team_id=None,
                team_abbreviation=None,
            )
        if pitcher is None and resolution['status'] != 'would_create':
            pitcher_resolution_failures += 1
            reconciliation_plan.append(_unresolved_row_plan(
                game_pk=game_pk, line=line, reason=resolution.get('reason'),
            ))
            continue
        if resolution['created']:
            pitchers_created += 1
        if resolution['reactivated']:
            pitchers_reactivated += 1
        if resolution.get('position_override_from_pitching_line'):
            position_overrides_from_pitching_line += 1
        if pitcher is not None and pitcher.team_id and pitcher.team_abbreviation:
            team_abbr_map[pitcher.team_id] = pitcher.team_abbreviation
        result = _ingest_boxscore_pitching_line(
            pitcher,
            line,
            game,
            game_date=game_date,
            team_abbr_map=team_abbr_map,
            pitcher_order=pitcher_order,
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            plan_only=plan_only,
            identity_plan=resolution.get('identity_plan'),
            pitcher_mlb_id=_positive_external_id(line.get('player_id')),
        )
        plan = result.get('plan')
        if plan is not None:
            reconciliation_plan.append(plan)
        if result['status'] == 'inserted':
            logs_added += 1
            if pitcher is not None:
                touched_pitcher_ids.add(pitcher.id)
        elif result['status'] == 'corrected':
            logs_corrected += 1
            if pitcher is not None:
                touched_pitcher_ids.add(pitcher.id)
        elif result['status'] == 'unsafe':
            correction_attempts_failed += 1

    if plan_only:
        # Read-only: no marker, no flush, nothing added to the session.
        return {
            'game_pk': game_pk,
            'logs_added': logs_added,
            'logs_corrected': logs_corrected,
            'correction_attempts_failed': correction_attempts_failed,
            'pitcher_resolution_failures': pitcher_resolution_failures,
            'pitchers_created': pitchers_created,
            'pitchers_reactivated': pitchers_reactivated,
            'position_overrides_from_pitching_line':
                position_overrides_from_pitching_line,
            'pitchers_touched': len(touched_pitcher_ids),
            'pitching_lines_seen': len(pitching_lines),
            'processing_status': None,
            'incomplete_reason': _postgame_incomplete_reason(
                pitching_lines_seen=len(pitching_lines),
                pitcher_resolution_failures=pitcher_resolution_failures,
                correction_attempts_failed=correction_attempts_failed,
            ),
            'attempt_count': (existing_marker.attempt_count or 0)
                if existing_marker else 0,
            'retry_exhausted': False,
            'skipped': False,
            'reason': None,
            'plan_only': True,
            'reconciliation_plan': reconciliation_plan,
            'reconciliation_summary': game_log_reconciliation.summarize(
                reconciliation_plan
            ),
            'boxscore': boxscore,
        }

    marker, retry_exhausted = _upsert_postgame_processed_marker(
        existing_marker=existing_marker,
        game=game,
        game_date=game_date,
        logs_added=logs_added,
        pitchers_touched=len(touched_pitcher_ids),
        pitching_lines_seen=len(pitching_lines),
        pitcher_resolution_failures=pitcher_resolution_failures,
        correction_attempts_failed=correction_attempts_failed,
        sync_run_id=sync_run_id,
        correction_recheck=force,
    )
    db.session.flush()

    return {
        'game_pk': game_pk,
        'logs_added': logs_added,
        'logs_corrected': logs_corrected,
        'correction_attempts_failed': correction_attempts_failed,
        'pitcher_resolution_failures': pitcher_resolution_failures,
        'pitchers_created': pitchers_created,
        'pitchers_reactivated': pitchers_reactivated,
        'position_overrides_from_pitching_line': position_overrides_from_pitching_line,
        'pitchers_touched': len(touched_pitcher_ids),
        'pitching_lines_seen': len(pitching_lines),
        'processing_status': marker.processing_status,
        'incomplete_reason': marker.incomplete_reason,
        'attempt_count': marker.attempt_count or 0,
        'retry_exhausted': retry_exhausted,
        'skipped': False,
        'reason': None,
        'plan_only': False,
        'reconciliation_plan': reconciliation_plan,
        'reconciliation_summary': game_log_reconciliation.summarize(
            reconciliation_plan
        ),
        # Passed back so completed-game context can reuse the boxscore that was
        # already fetched, without a second API call. Not persisted.
        'boxscore': boxscore,
    }


def generate_completed_game_context(
    game: dict,
    *,
    boxscore: dict | None,
    game_date: date,
    linescore=_OPTIONAL_INPUT_NOT_PROVIDED,
    play_by_play=_OPTIONAL_INPUT_NOT_PROVIDED,
) -> dict:
    """Derive and upsert per-team Completed Game Context for one completed game.

    Consumes linescore and play-by-play transiently (raw responses are never
    stored), normalizes them with the boxscore into the service payload, and
    upserts one derived row per team keyed by (team_id, game_pk). Adds rows to
    the current session but does not commit — the caller owns the transaction.

    Network failures for the optional context endpoints degrade gracefully:
    a missing linescore/play-by-play simply lowers confidence rather than
    failing the game.
    """
    game_pk = _game_pk(game)
    if game_pk:
        optional_inputs = _fetch_completed_game_optional_inputs(
            game_pk,
            fetch_linescore=linescore is _OPTIONAL_INPUT_NOT_PROVIDED,
            fetch_play_by_play=play_by_play is _OPTIONAL_INPUT_NOT_PROVIDED,
        )
        if linescore is _OPTIONAL_INPUT_NOT_PROVIDED:
            linescore = optional_inputs['linescore']
        if play_by_play is _OPTIONAL_INPUT_NOT_PROVIDED:
            play_by_play = optional_inputs['play_by_play']
    else:
        if linescore is _OPTIONAL_INPUT_NOT_PROVIDED:
            linescore = None
        if play_by_play is _OPTIONAL_INPUT_NOT_PROVIDED:
            play_by_play = None

    payload = build_completed_game_payload(
        game,
        boxscore=boxscore,
        linescore=linescore,
        play_by_play=play_by_play,
        game_date=game_date,
    )
    if not payload:
        return {'contexts_upserted': 0, 'confidences': [], 'reason': 'no_payload'}

    contexts = extract_completed_game_contexts(payload)
    for context in contexts:
        upsert_completed_game_context(context)
    return {
        'contexts_upserted': len(contexts),
        'confidences': [c.get('confidence') for c in contexts],
        'reason': None,
    }


def _fetch_completed_game_optional_inputs(
    game_pk,
    *,
    fetch_linescore=True,
    fetch_play_by_play=True,
):
    linescore = None
    play_by_play = None
    play_by_play_error = None
    if not game_pk:
        return {
            'linescore': None,
            'play_by_play': None,
            'play_by_play_error': None,
        }
    if fetch_linescore:
        try:
            linescore = mlb_client.get_game_linescore(game_pk)
        except Exception as exc:  # noqa: BLE001 - optional input, degrade not fail
            logger.warning('Linescore fetch failed for game_pk=%s: %s', game_pk, exc)
    if fetch_play_by_play:
        try:
            play_by_play = mlb_client.get_game_play_by_play(game_pk)
        except Exception as exc:  # noqa: BLE001 - optional input, degrade not fail
            play_by_play_error = exc
            logger.warning('Play-by-play fetch failed for game_pk=%s: %s', game_pk, exc)
    return {
        'linescore': linescore,
        'play_by_play': play_by_play,
        'play_by_play_error': play_by_play_error,
    }


def _safe_generate_completed_game_context(
    game: dict,
    *,
    boxscore: dict | None,
    schedule_date: date,
    linescore=None,
    play_by_play=None,
    sync_run_id=None,
    status: dict,
    run_logger,
) -> None:
    """Run completed-game context generation without ever breaking the refresh.

    Fail-closed wrapper: commits the derived rows on success; on any failure it
    rolls back only the context work (the game logs are already committed),
    records a dead-letter entry, and lets the refresh continue.
    """
    game_pk = _game_pk(game)
    try:
        result = generate_completed_game_context(
            game,
            boxscore=boxscore,
            game_date=_game_date(game, schedule_date),
            linescore=linescore,
            play_by_play=play_by_play,
        )
        db.session.commit()
        status['completed_game_contexts_upserted'] += result['contexts_upserted']
        if result['contexts_upserted']:
            run_logger.info(
                'Completed-game context for game %s: %s row(s) %s.',
                game_pk,
                result['contexts_upserted'],
                '/'.join(result['confidences']) or 'none',
            )
    except Exception as exc:  # noqa: BLE001 — context is best-effort, never fatal
        db.session.rollback()
        status['completed_game_context_errors'] += 1
        dead_letter.record_failure(
            POSTGAME_CONTEXT_FAILURE_ENTITY_TYPE,
            exc,
            entity_ref=game_pk,
            payload={
                'game_pk': game_pk,
                'schedule_date': schedule_date.isoformat(),
            },
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        db.session.commit()
        run_logger.warning(
            'Completed-game context failed for game_pk=%s: %s', game_pk, exc
        )


def _safe_process_final_play_by_play_foundation(
    game: dict,
    *,
    boxscore: dict | None,
    schedule_date: date,
    play_by_play: dict | None,
    play_by_play_error=None,
    sync_run_id=None,
    run_logger,
) -> None:
    """Run final PBP foundation storage without changing postgame outcome."""
    game_pk = _game_pk(game)
    try:
        result = process_final_play_by_play_foundation(
            game,
            boxscore=boxscore,
            play_by_play=play_by_play,
            play_by_play_error=play_by_play_error,
            game_date=_game_date(game, schedule_date),
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        db.session.commit()
        if result.get('skipped'):
            run_logger.info(
                'Final play-by-play foundation skipped for game %s: %s.',
                game_pk,
                result.get('reason'),
            )
            return
        run_logger.info(
            'Final play-by-play foundation for game %s: status=%s reason=%s '
            'events=%s mismatches=%s unresolved_pitchers=%s.',
            game_pk,
            result.get('processing_status'),
            result.get('reason'),
            result.get('events_stored'),
            result.get('reconciliation_mismatch_count'),
            result.get('unresolved_pitcher_count'),
        )
    except Exception as exc:  # noqa: BLE001 - optional foundation, fail-soft
        db.session.rollback()
        dead_letter.record_failure(
            FINAL_PBP_FETCH_ENTITY_TYPE,
            exc,
            entity_ref=game_pk,
            payload={
                'game_pk': game_pk,
                'schedule_date': schedule_date.isoformat(),
            },
            sync_run_id=sync_run_id,
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        db.session.commit()
        run_logger.warning(
            'Final play-by-play foundation failed for game_pk=%s: %s',
            game_pk,
            exc,
        )


def _safe_recompute_team_game_pitching_splits(
    game: dict,
    *,
    schedule_date: date,
    sync_run_id=None,
    run_logger,
) -> None:
    """Run derived split/calendar storage after committed GameLog writes."""
    game_pk = _game_pk(game)
    result = safe_recompute_team_game_pitching_splits_for_game(
        game_pk,
        game=game,
        game_date=_game_date(game, schedule_date),
        sync_run_id=sync_run_id,
        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
    )
    db.session.commit()
    if result.get('status') == 'skipped':
        run_logger.info(
            'Team-game pitching split recompute skipped for game %s: %s.',
            game_pk,
            result.get('reason'),
        )
        return
    if result.get('status') == 'failed':
        run_logger.warning(
            'Team-game pitching split recompute failed for game %s: %s.',
            game_pk,
            result.get('reason'),
        )
        return
    run_logger.info(
        'Team-game pitching split recompute for game %s: inserted=%s '
        'corrected=%s unchanged=%s reasons=%s.',
        game_pk,
        result.get('rows_inserted'),
        result.get('rows_corrected'),
        result.get('rows_unchanged'),
        ','.join(result.get('reason_codes') or []) or 'none',
    )


def _postgame_snapshot_refresh_enabled() -> bool:
    """Whether the postgame refresh rebuilds the homepage lead-story cache.

    On by default. Set POSTGAME_REFRESH_SNAPSHOT to a falsey value to skip the
    in-refresh rebuild — an operational lever for the case where this optional
    tail is the slow/hanging step. Skipping it never affects correctness: the
    completed-game data is already committed, the homepage endpoint falls back to
    live generation, and the daily warm still refreshes the cache.
    """
    raw = os.environ.get('POSTGAME_REFRESH_SNAPSHOT')
    if raw is None:
        return True
    return raw.strip().lower() not in {'0', 'false', 'no', 'off', ''}


class _PostgameSnapshotTimeout(TimeoutError):
    """Raised when the optional postgame snapshot tail exceeds its time budget."""


def _postgame_snapshot_timeout_seconds() -> float | None:
    raw = os.environ.get('POSTGAME_REFRESH_SNAPSHOT_TIMEOUT_SECONDS')
    if raw is None:
        return POSTGAME_SNAPSHOT_DEFAULT_TIMEOUT_SECONDS

    value = raw.strip().lower()
    if value in {'0', 'false', 'no', 'off', ''}:
        return None

    try:
        seconds = float(value)
    except ValueError:
        return POSTGAME_SNAPSHOT_DEFAULT_TIMEOUT_SECONDS

    return seconds if seconds > 0 else None


def _snapshot_timeout_supported() -> bool:
    return (
        threading.current_thread() is threading.main_thread()
        and hasattr(signal, 'SIGALRM')
        and hasattr(signal, 'setitimer')
        and hasattr(signal, 'ITIMER_REAL')
    )


def _run_intelligence_surface_snapshot_with_timeout(
    schedule_date,
    *,
    timeout_seconds,
    run_logger,
):
    from services.intelligence_surface_snapshot import generate_snapshot_for_date

    if timeout_seconds is None:
        return generate_snapshot_for_date(
            schedule_date,
            source='postgame_refresh',
            step_logger=run_logger,
        )

    if not _snapshot_timeout_supported():
        run_logger.warning(
            'Intelligence surface snapshot timeout unavailable on this runtime; '
            'continuing without a hard bound (timeout_seconds=%s).',
            timeout_seconds,
        )
        return generate_snapshot_for_date(
            schedule_date,
            source='postgame_refresh',
            step_logger=run_logger,
        )

    previous_handler = signal.getsignal(signal.SIGALRM)

    def _raise_timeout(_signum, _frame):
        raise _PostgameSnapshotTimeout(
            f'Intelligence surface snapshot exceeded {timeout_seconds:g}s')

    signal.signal(signal.SIGALRM, _raise_timeout)
    signal.setitimer(signal.ITIMER_REAL, timeout_seconds)
    try:
        return generate_snapshot_for_date(
            schedule_date,
            source='postgame_refresh',
            step_logger=run_logger,
        )
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)


def _safe_generate_intelligence_surface_snapshot(schedule_date, *, status, run_logger):
    """Refresh the Intelligence Surface snapshot for a slate without ever
    breaking the refresh.

    Fail-soft wrapper around the homepage cache: rebuilds the stored
    GET /api/bullpen/intelligence/today response from the completed-game contexts
    just derived for ``schedule_date``. The completed-game contexts are already
    committed, so a snapshot failure here costs only a stale homepage cache (the
    endpoint falls back to live generation) and never undoes context work or
    fails the postgame refresh.

    This is the most expensive optional tail of the refresh (it rebuilds the
    lead-story for every team with a completed-game context). It logs a start
    line and an elapsed_ms so a slow build is visible in the job log instead of
    appearing as a silent gap. It can be skipped via POSTGAME_REFRESH_SNAPSHOT
    and bounded via POSTGAME_REFRESH_SNAPSHOT_TIMEOUT_SECONDS.
    """
    if not _postgame_snapshot_refresh_enabled():
        status['intelligence_snapshot'] = 'skipped_by_config'
        run_logger.info(
            'Intelligence surface snapshot skipped for %s '
            '(POSTGAME_REFRESH_SNAPSHOT disabled); homepage uses live fallback.',
            schedule_date,
        )
        return

    timeout_seconds = _postgame_snapshot_timeout_seconds()
    started = time.perf_counter()
    status.pop('intelligence_snapshot_error', None)
    run_logger.info(
        'Intelligence surface snapshot refresh starting for %s '
        '(timeout_seconds=%s).',
        schedule_date,
        timeout_seconds if timeout_seconds is not None else 'disabled',
    )
    try:
        response = _run_intelligence_surface_snapshot_with_timeout(
            schedule_date,
            timeout_seconds=timeout_seconds,
            run_logger=run_logger,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        status['intelligence_snapshot'] = response.get('status') or 'generated'
        run_logger.info(
            'Intelligence surface snapshot refresh completed for %s: status=%s, '
            'publishable=%s, elapsed_ms=%s.',
            schedule_date,
            response.get('status'),
            response.get('publishable_candidates'),
            elapsed_ms,
        )
    except _PostgameSnapshotTimeout as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        db.session.rollback()
        status['intelligence_snapshot'] = 'timed_out'
        status['intelligence_snapshot_error'] = str(exc)
        run_logger.warning(
            'Intelligence surface snapshot refresh timed out for '
            'schedule_date=%s after %ss (elapsed_ms=%s); postgame refresh will '
            'continue.',
            schedule_date,
            timeout_seconds,
            elapsed_ms,
        )
    except Exception as exc:  # noqa: BLE001 — snapshot is best-effort, never fatal
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        db.session.rollback()
        status['intelligence_snapshot'] = 'failed'
        status['intelligence_snapshot_error'] = str(exc)
        run_logger.warning(
            'Intelligence surface snapshot refresh failed for schedule_date=%s '
            '(elapsed_ms=%s); postgame refresh will continue: %s',
            schedule_date, elapsed_ms, exc,
        )


def _env_seconds(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    try:
        value = float(raw) if raw not in (None, '') else default
    except (TypeError, ValueError):
        value = default
    if value is None:
        return None
    return value if value > 0 else None


def _daily_sync_ingestion_budget_seconds() -> float | None:
    """Maximum soft wall-clock budget for the gameLog ingestion stage."""
    return _env_seconds(
        'DAILY_SYNC_INGESTION_BUDGET_SECONDS',
        DAILY_SYNC_DEFAULT_INGESTION_BUDGET_SECONDS,
    )


def _daily_sync_total_budget_seconds() -> float | None:
    """Total Python-process budget for the public daily sync command.

    This is deliberately shorter than the workflow command timeout so the
    process can finish metadata, release the writer guard, and exit cleanly.
    """
    return _env_seconds(
        'DAILY_SYNC_TOTAL_BUDGET_SECONDS',
        DAILY_SYNC_DEFAULT_TOTAL_BUDGET_SECONDS,
    )


def _daily_sync_final_phase_reserve_seconds() -> float:
    return (
        _env_seconds(
            'DAILY_SYNC_FINAL_PHASE_RESERVE_SECONDS',
            DAILY_SYNC_DEFAULT_FINAL_PHASE_RESERVE_SECONDS,
        )
        or 0.0
    )


def _postgame_refresh_ingestion_budget_seconds() -> float | None:
    """Bounded soft budget for the postgame game-driven appearance lane."""
    return _env_seconds(
        'POSTGAME_REFRESH_INGESTION_BUDGET_SECONDS',
        POSTGAME_REFRESH_DEFAULT_INGESTION_BUDGET_SECONDS,
    )


def _postgame_refresh_runtime_budget() -> dict:
    """Runtime budget the postgame game-driven lane runs inside.

    The postgame refresh has no total-process budget to divide, so this reports
    the lane's own cap honestly rather than inventing a reserve it does not
    have. The shape matches the daily budget so one lane implementation reads
    both without a second code path.
    """
    ingestion_budget = _postgame_refresh_ingestion_budget_seconds()
    return {
        'total_budget_seconds': None,
        'stage_budget_cap_seconds': ingestion_budget,
        'final_phase_reserve_seconds': None,
        'elapsed_before_ingestion_seconds': None,
        'remaining_total_seconds': None,
        'ingestion_budget_seconds': ingestion_budget,
    }


def _sync_schedule_finality_preflight_enabled() -> bool:
    raw = (
        os.environ.get('SYNC_SCHEDULE_FINALITY_PREFLIGHT')
        or os.environ.get('DAILY_SYNC_SCHEDULE_FINALITY_PREFLIGHT')
    )
    if raw is not None:
        return raw.strip().lower() not in _FALSEY_ENV_VALUES
    return os.environ.get('APP_ENV') == 'production'


# Refusal reason for a writing mode requested on a cycle that has no
# conflict-prevention mechanism against its own legacy writer.
GAME_DRIVEN_WRITE_MODE_UNSUPPORTED = 'write_mode_unsupported_for_cycle'


def _game_driven_lane_budget_share() -> float:
    """Share of the ingestion budget the game-driven lane may consume.

    While the lane is not yet publication-authoritative it must not starve the
    loop that IS still authoritative, so it runs inside a bounded slice (25% by
    default) — enough to gather Stage B/C production evidence, never enough to
    endanger the current publication path. Once the lane is authoritative it is
    the critical lane and may use the whole ingestion budget; whatever it does
    not use falls through to the demoted best-effort loop.
    """
    raw = os.environ.get('GAME_DRIVEN_INGESTION_BUDGET_SHARE')
    try:
        share = float(str(raw).strip()) if raw not in (None, '') else 0.25
    except (TypeError, ValueError):
        share = 0.25
    return min(max(share, 0.0), 1.0)


def _game_driven_lane_time_budget(ingestion_budget_seconds, mode) -> float | None:
    if ingestion_budget_seconds is None:
        return None
    if game_driven_ingestion.publication_authoritative(mode):
        return float(ingestion_budget_seconds)
    return float(ingestion_budget_seconds) * _game_driven_lane_budget_share()


def _run_game_driven_ingestion_stage(
    *,
    reference_date: date,
    runtime_budget: dict,
    sync_run_id,
    status: dict,
    stage_timings: dict,
    run_logger,
    job_name: str = sync_metadata.JOB_DAILY_SYNC,
    write_modes_supported: bool = True,
    only_game_pks=None,
    scope_summary: dict | None = None,
) -> dict:
    """Run the Foundation 3C game-driven appearance lane, if it is enabled.

    Returns the lane result plus the ingestion budget that remains for the
    (demoted) full-season pitcher loop. A failure inside the lane can never
    abort the sync: it is caught, classified, and surfaced — and in
    authoritative mode it fails the publication gate closed.

    ``write_modes_supported`` is the two-writer guard. A cycle may only run
    this lane in a writing mode when that cycle also has an explicit
    conflict-prevention mechanism against its own legacy writer. The daily sync
    has one (``skip_game_pks``); the postgame refresh does not, so it passes
    ``False`` and a writing mode is refused there rather than silently letting
    two writers touch the same canonical rows.
    """
    mode = game_driven_ingestion.ingestion_mode()
    ingestion_budget = runtime_budget.get('ingestion_budget_seconds')
    result = {
        'mode': mode,
        'report': None,
        'completeness': None,
        'authoritative': game_driven_ingestion.publication_authoritative(mode),
        'remaining_ingestion_budget_seconds': ingestion_budget,
        'completed_game_pks': (),
        'error_class': None,
        'refused_reason': None,
        # OPS-002: the lane's own consumption, reported separately from its
        # allocation. A lane that never ran consumed nothing; a lane that ran
        # consumed its measured wall clock even if it then raised.
        'lane_allocated_budget_seconds': 0.0,
        'lane_elapsed_seconds': 0.0,
    }
    if mode == game_driven_ingestion.MODE_OFF:
        status['game_driven_ingestion'] = {'status': 'disabled', 'mode': mode}
        return result

    if not write_modes_supported and game_driven_ingestion.writes_enabled(mode):
        # Refuse BEFORE planning, so a writing mode reaches neither MLB nor the
        # database on a cycle that cannot prevent writer conflict. The lane is
        # forced non-authoritative here too: a refused lane must never be able
        # to take over the publication gate it never ran.
        result['authoritative'] = False
        result['refused_reason'] = GAME_DRIVEN_WRITE_MODE_UNSUPPORTED
        status['game_driven_ingestion'] = {
            'status': 'refused',
            'mode': mode,
            'reason': GAME_DRIVEN_WRITE_MODE_UNSUPPORTED,
            'job_name': job_name,
        }
        run_logger.error(
            'Game-driven ingestion lane refused (mode=%s, job=%s, reason=%s): '
            'this cycle has no conflict-prevention mechanism against its own '
            'legacy writer, so a writing mode is not runnable here.',
            mode, job_name, GAME_DRIVEN_WRITE_MODE_UNSUPPORTED,
        )
        return result

    lane_budget = _game_driven_lane_time_budget(ingestion_budget, mode)
    result['lane_allocated_budget_seconds'] = lane_budget
    stage_started = time.monotonic()
    try:
        report = game_driven_ingestion.run_game_driven_ingestion(
            reference_date,
            mode=mode,
            time_budget_seconds=lane_budget,
            sync_run_id=sync_run_id,
            job_name=job_name,
            only_game_pks=only_game_pks,
        )
    except Exception as exc:  # noqa: BLE001 - the sync must not die here
        # OPS-002: a lane that raises has still spent wall clock, and that time
        # is gone from the shared ingestion pool. Charging it here stops the
        # legacy GameLog writer from being told it has time the run no longer
        # has. Measure BEFORE the rollback so recovery work is not counted as
        # lane time.
        failed_elapsed = max(time.monotonic() - stage_started, 0.0)
        db.session.rollback()
        error_class = type(exc).__name__
        result['error_class'] = error_class
        result['lane_elapsed_seconds'] = failed_elapsed
        if ingestion_budget is not None:
            result['remaining_ingestion_budget_seconds'] = max(
                float(ingestion_budget) - failed_elapsed, 0.0
            )
        status['game_driven_ingestion'] = {
            'status': 'failed',
            'mode': mode,
            'job_name': job_name,
            'error_class': error_class,
            'allocated_budget_seconds': lane_budget,
            'elapsed_seconds': round(failed_elapsed, 3),
        }
        # No exception text: it can carry paths and payload fragments. The
        # failure stays fail-soft: it is recorded and charged, and it does not
        # abort public-sync or by itself fail publication. A genuine GameLog
        # deficit remains publication-blocking exactly as before.
        run_logger.error(
            'Game-driven ingestion lane failed (mode=%s, class=%s) after %.3fs; '
            'that time is charged against the shared ingestion pool.',
            mode, error_class, failed_elapsed,
        )
        stage_timings['game_driven_ingestion'] = round(failed_elapsed, 1)
        return result

    elapsed = max(time.monotonic() - stage_started, 0.0)
    result['lane_elapsed_seconds'] = elapsed
    stage_timings['game_driven_ingestion'] = round(elapsed, 1)
    stage_timings['game_driven_fetch'] = report.get('fetch_seconds')
    stage_timings['game_driven_extraction'] = report.get('extraction_seconds')
    stage_timings['game_driven_persistence'] = report.get('persistence_seconds')
    result['report'] = report
    result['completed_game_pks'] = tuple(
        entry['game_pk'] for entry in report.get('games') or []
        if entry.get('status') in (
            GameIngestionWorkItem.STATUS_COMPLETED, 'completed_with_correction',
        )
    )
    if ingestion_budget is not None:
        result['remaining_ingestion_budget_seconds'] = max(
            float(ingestion_budget) - elapsed, 0.0
        )

    try:
        # The mode is passed explicitly: this lane has just RUN under `mode`,
        # so re-reading the environment inside the proof could describe a
        # different authority from the one that produced the evidence.
        completeness = game_ingestion_completeness.build_game_ingestion_completeness(
            reference_date, lane_mode=mode,
        )
    except Exception as exc:  # noqa: BLE001 - proof failure must fail closed
        db.session.rollback()
        completeness = {
            'represented_date': reference_date.isoformat(),
            'lane_mode': mode,
            'publication_complete': False,
            'decision_reasons': ['completeness_proof_unavailable'],
            'error_class': type(exc).__name__,
        }
    result['completeness'] = completeness

    status['game_driven_ingestion'] = {
        'status': report.get('status'),
        'mode': mode,
        'job_name': job_name,
        'writes_enabled': game_driven_ingestion.writes_enabled(mode),
        'publication_authoritative': game_driven_ingestion.publication_authoritative(
            mode
        ),
        # The cap and the allocation are different numbers and were reported
        # ambiguously on the first production cycle: a 600s cap with a 150s
        # allocation read as "600 seconds available". Both are named now, with
        # the share that relates them.
        'configured_stage_cap_seconds': runtime_budget.get(
            'stage_budget_cap_seconds'
        ),
        'lane_budget_share': (
            1.0 if game_driven_ingestion.publication_authoritative(mode)
            else _game_driven_lane_budget_share()
        ),
        'effective_allocated_budget_seconds': lane_budget,
        # Retained under its original name so an existing reader does not
        # break; it is the effective allocation, never the cap.
        'allocated_budget_seconds': lane_budget,
        'elapsed_seconds': report.get('elapsed_seconds'),
        'remaining_headroom_seconds': report.get('remaining_budget_seconds'),
        'remaining_budget_seconds': report.get('remaining_budget_seconds'),
        # The cycle's own scope summary, and the planner's independent verdict
        # on it. Both are needed: the first says what this cycle asked for, the
        # second says what the planner actually produced from that request.
        # A validator that only saw the request could not catch the planner
        # returning something else.
        'execution_scope': {
            **dict(scope_summary or {}),
            'execution_scope_mode': report.get('execution_scope_mode'),
            'planner_requested_game_pks': report.get('requested_game_pks'),
            'planner_requested_game_count': report.get('requested_game_count'),
            'duplicate_requested_count': report.get('duplicate_requested_count'),
            'planned_game_pks': report.get('planned_game_pks'),
            'planned_game_count': report.get('planned_game_count'),
            'missing_requested_game_pks': report.get(
                'missing_requested_game_pks'
            ),
            'unexpected_planned_game_pks': report.get(
                'unexpected_planned_game_pks'
            ),
            'execution_scope_exact_match': report.get(
                'execution_scope_exact_match'
            ),
        },
        'games_discovered': report.get('games_discovered'),
        'games_planned': report.get('games_planned'),
        'games_attempted': report.get('games_attempted'),
        'games_fetched': report.get('games_fetched'),
        'games_completed': report.get('games_completed'),
        'games_failed': report.get('games_failed'),
        'games_remaining': report.get('games_remaining'),
        'critical_games_remaining': report.get('critical_games_unresolved'),
        'best_effort_games_deferred': report.get('best_effort_games_deferred'),
        'newly_final_count': report.get('newly_final_count'),
        'corrected_final_count': report.get('corrected_final_count'),
        'retry_count': report.get('retry_count'),
        'schedule_authority_missing': report.get('schedule_authority_missing'),
        'finality_conflicts': report.get('finality_conflicts'),
        'rows_expected': report.get('rows_expected'),
        'rows_inserted': report.get('rows_inserted'),
        'rows_updated': report.get('rows_updated'),
        'rows_unchanged': report.get('rows_unchanged'),
        'rows_blocked': report.get('rows_blocked'),
        # Every mutation target, so the lane can never report "no mutations"
        # while one target is unaccounted for.
        'pitcher_identity_mutations': report.get('pitcher_identity_mutations'),
        'pitcher_identity_creations': report.get('pitcher_identity_creations'),
        'pitcher_identity_reactivations': report.get(
            'pitcher_identity_reactivations'
        ),
        'pitcher_identity_metadata_updates': report.get(
            'pitcher_identity_metadata_updates'
        ),
        'pitcher_identity_blocked': report.get('pitcher_identity_blocked'),
        'appearance_team_mutations': report.get('appearance_team_mutations'),
        'complete_mutation_count': report.get('complete_mutation_count'),
        'canonical_outs_corrections': report.get('canonical_outs_corrections'),
        'statistical_corrections': report.get('statistical_corrections'),
        'provenance_only_updates': report.get('provenance_only_updates'),
        'derived_companion_fields_applied': report.get(
            'derived_companion_fields_applied'
        ),
        'derived_companion_differences_ignored': report.get(
            'derived_companion_differences_ignored'
        ),
        'corrections_applied': report.get('corrections_applied'),
        'budget_stop_triggered': report.get('budget_stop_triggered'),
        'failure_classes': report.get('failure_classes'),
        # Evidence identity only. A fingerprint recorded here has never been,
        # and can never become, authorization for a write.
        'reconciliation_plan_fingerprint': report.get(
            'reconciliation_plan_fingerprint'
        ),
        'complete_reconciliation_fingerprint': report.get(
            'complete_reconciliation_fingerprint'
        ),
        'reconciliation_plan_version': report.get('reconciliation_plan_version'),
        'parity_contract_version': report.get('parity_contract_version'),
        'innings_semantics_version': report.get('innings_semantics_version'),
        'complete_plan_version': report.get('complete_plan_version'),
        'identity_plan_version': report.get('identity_plan_version'),
        'planner_seconds': report.get('planner_seconds'),
        'fetch_seconds': report.get('fetch_seconds'),
        'extraction_seconds': report.get('extraction_seconds'),
        'persistence_seconds': report.get('persistence_seconds'),
        'checkpoint_seconds': report.get('checkpoint_seconds'),
        'elapsed_seconds': report.get('elapsed_seconds'),
    }
    # What the lane ACTUALLY did to the database, counted at the write sites
    # themselves rather than derived from the mode name. Everything else in
    # this object counts what the plan WOULD do; these are different numbers
    # and must never be conflated. A projected insert is not a write.
    status['game_driven_ingestion']['execution_effects'] = dict(
        report.get('execution_effects') or {}
    )
    # ── Safe difference diagnostics ─────────────────────────────────────────
    # The first postgame cycle reported "1 projected statistical update" and
    # nothing about WHICH row, so the discrepancy could not be investigated
    # from the artifact at all. Every non-unchanged projected row is now named
    # — by identifiers, canonical field names, classification, and digests.
    #
    # Field NAMES and digests only. The values behind them never appear, so a
    # reviewer learns that a row differs and in what way without the artifact
    # carrying baseball data or anything else it should not.
    status['game_driven_ingestion']['projected_differences'] = [
        {
            'game_pk': row.get('game_pk'),
            'pitcher_mlb_id': row.get('pitcher_mlb_id'),
            'action': row.get('action'),
            'changed_fields': list(row.get('changed_fields') or ()),
            'difference_classifications': list(
                row.get('difference_classifications') or ()
            ),
            # What this lane could not evaluate. A field named here was never
            # compared, which is a different fact from being found equal — and
            # it is the fact that explains a difference one lane sees and
            # another never can.
            'uncomparable_fields': list(row.get('uncomparable_fields') or ()),
            'blocked_reason': row.get('blocked_reason'),
            'pitcher_identity_action': row.get('pitcher_identity_action'),
            'source_revision': game.get('source_revision'),
            'reconciliation_plan_fingerprint': game.get(
                'reconciliation_plan_fingerprint'
            ),
            'target_state_digest': row.get('target_state_digest'),
            'stored_state_digest': row.get('stored_state_digest'),
        }
        for game in report.get('games') or ()
        for row in (game.get('rows') or ())
        if row.get('action') != game_log_reconciliation.ACTION_UNCHANGED
    ]
    # Per-game evidence, in the canonical processing order the run used. Row
    # detail stays out: the realization proof already summarizes it, and a
    # durable artifact should carry the evidence a reviewer needs rather than
    # every row the planner considered.
    status['game_driven_ingestion']['games'] = [
        {
            'game_pk': entry.get('game_pk'),
            'represented_date': entry.get('represented_date'),
            'candidate_reason': entry.get('candidate_reason'),
            'criticality': entry.get('criticality'),
            'status': entry.get('status'),
            'source_revision': entry.get('source_revision'),
            'appearances_extracted': entry.get('appearances_extracted'),
            'inserted': entry.get('inserted'),
            'updated': entry.get('updated'),
            'unchanged': entry.get('unchanged'),
            'blocked': entry.get('blocked'),
            'reconciliation_plan_fingerprint': entry.get(
                'reconciliation_plan_fingerprint'
            ),
            'error_class': entry.get('error_class'),
        }
        for entry in report.get('games') or ()
    ]
    status['game_ingestion_completeness'] = completeness
    run_logger.info(
        'Game-driven ingestion lane (mode=%s): planned=%s fetched=%s '
        'completed=%s failed=%s remaining=%s critical_remaining=%s '
        'inserted=%s updated=%s unchanged=%s corrections=%s '
        'budget_stop=%s publication_complete=%s elapsed_s=%s.',
        mode,
        report.get('games_planned'),
        report.get('games_fetched'),
        report.get('games_completed'),
        report.get('games_failed'),
        report.get('games_remaining'),
        report.get('critical_games_unresolved'),
        report.get('rows_inserted'),
        report.get('rows_updated'),
        report.get('rows_unchanged'),
        report.get('corrections_applied'),
        report.get('budget_stop_triggered'),
        completeness.get('publication_complete'),
        report.get('elapsed_seconds'),
    )
    return result


# ── Postgame exact-cycle scope ──────────────────────────────────────────────
# The first automated postgame shadow cycle planned 112 games and completed 98
# before exhausting its allocation. It was not slow: it was looking at the
# wrong set. The lane was given a reference date and no scope, so the canonical
# planner did what it is supposed to do for a DAILY cycle — sweep the whole
# rolling correction horizon — while the postgame refresh had already resolved
# the only set that cycle governs.
#
# The scope below is that set. It is derived from state the cycle already
# holds, so it costs no MLB request and no second planning pass, and it is
# handed to the lane through the exclusive-scope mechanism Foundation 3C
# already built, which fails before any fetch if the plan is not the exact
# requested set.

POSTGAME_SCOPE_SOURCE = 'postgame_cycle_completed_games'

# Why a governed game of this cycle is, or is not, eligible for post-writer
# convergence verification. A game the writer has not finished cannot be
# expected to project zero, and excluding it silently would be the same class
# of defect as the fan-out this replaces.
POSTGAME_SCOPE_INCLUDED = 'fully_processed_after_writer'
POSTGAME_SCOPE_EXCLUDED_INCOMPLETE = 'incomplete_after_writer'
POSTGAME_SCOPE_EXCLUDED_FAILED = 'failed_marker'
POSTGAME_SCOPE_EXCLUDED_UNPROCESSED = 'no_processing_marker'


def _postgame_game_driven_scope(completed_games, slate_by_game_pk) -> dict:
    """Resolve the exact game set this postgame cycle may verify.

    Read AFTER the cycle's writer has run, because eligibility depends on what
    that writer actually finished. Deterministic and de-duplicated: the same
    cycle state always yields the same ordered scope.
    """
    ordered_pks = []
    seen = set()
    for game in completed_games or ():
        game_pk = _game_pk(game)
        if game_pk is None or game_pk in seen:
            continue
        seen.add(game_pk)
        ordered_pks.append(game_pk)

    scope = {
        'scope_source': POSTGAME_SCOPE_SOURCE,
        'cycle_game_count': len(ordered_pks),
        'requested_game_pks': [],
        'requested_game_count': 0,
        'excluded_game_pks': [],
        'excluded_reason_counts': {},
        'slate_dates': sorted({
            slate.isoformat()
            for slate in (slate_by_game_pk or {}).values()
            if slate is not None
        }),
    }
    if not ordered_pks:
        return scope

    markers = {
        marker.mlb_game_pk: marker
        for marker in (
            PostgameProcessedGame.query
            .filter(PostgameProcessedGame.mlb_game_pk.in_(ordered_pks))
            .all()
        )
    }

    requested = []
    excluded = []
    for game_pk in ordered_pks:
        marker = markers.get(game_pk)
        if marker is None:
            reason = POSTGAME_SCOPE_EXCLUDED_UNPROCESSED
        elif _marker_processing_status(marker) == POSTGAME_MARKER_STATUS_FULLY_PROCESSED:
            reason = POSTGAME_SCOPE_INCLUDED
        elif _postgame_marker_retryable(marker):
            reason = POSTGAME_SCOPE_EXCLUDED_INCOMPLETE
        else:
            reason = POSTGAME_SCOPE_EXCLUDED_FAILED

        if reason == POSTGAME_SCOPE_INCLUDED:
            requested.append(game_pk)
        else:
            excluded.append({'game_pk': game_pk, 'reason': reason})
            scope['excluded_reason_counts'][reason] = (
                scope['excluded_reason_counts'].get(reason, 0) + 1
            )

    scope['requested_game_pks'] = sorted(requested)
    scope['requested_game_count'] = len(requested)
    scope['excluded_game_pks'] = sorted(
        excluded, key=lambda entry: entry['game_pk']
    )
    scope['excluded_reason_counts'] = dict(
        sorted(scope['excluded_reason_counts'].items())
    )
    return scope


def _attach_daily_realization(*, game_lane, status, stage_timings, run_logger) -> None:
    """Attach the daily realization proof, after the legacy writer has run.

    Read-only and fail-closed. A proof that cannot be built is reported as
    unavailable — which fails the activation gate — rather than being omitted,
    because a missing proof and a passing proof must never look alike.

    This never affects the daily sync's own outcome. It is activation evidence.
    """
    lane = status.get('game_driven_ingestion')
    if not isinstance(lane, dict) or lane.get('status') in (None, 'disabled'):
        return
    if game_lane.get('report') is None:
        lane['realization'] = {
            'applicable': False,
            'cycle_kind': game_driven_realization.CYCLE_DAILY,
            'available': False,
            'reason': 'no_game_driven_report',
            'all_projected_targets_realized': False,
        }
        return

    started = time.monotonic()
    try:
        realization = game_driven_realization.build_daily_realization(
            game_lane['report']
        )
        realization['available'] = True
    except Exception as exc:  # noqa: BLE001 - evidence must fail closed, not raise
        db.session.rollback()
        realization = {
            'applicable': True,
            'cycle_kind': game_driven_realization.CYCLE_DAILY,
            'available': False,
            'reason': 'realization_proof_unavailable',
            'error_class': type(exc).__name__,
            'all_projected_targets_realized': False,
        }
        # No exception text: it can carry paths and payload fragments.
        run_logger.error(
            'Daily game-driven realization proof unavailable (class=%s).',
            type(exc).__name__,
        )
    stage_timings['game_driven_realization'] = round(
        time.monotonic() - started, 3
    )
    lane['realization'] = realization
    run_logger.info(
        'Daily game-driven realization: applicable=%s projected_rows=%s '
        'realized=%s already_matching=%s missing=%s divergent=%s duplicate=%s '
        'unresolved=%s prohibited_identity=%s all_realized=%s.',
        realization.get('applicable'),
        realization.get('projected_rows'),
        realization.get('realized_rows'),
        realization.get('already_matching_rows'),
        realization.get('missing_rows'),
        realization.get('divergent_rows'),
        realization.get('duplicate_rows'),
        realization.get('unresolved_rows'),
        realization.get('prohibited_identity_actions'),
        realization.get('all_projected_targets_realized'),
    )


def _game_lane_publication_gate(completeness) -> dict:
    """The blocker view of a completeness result, whatever shape it arrives in.

    The canonical proof carries an explicit ``publication_gate``. Anything
    else — an older producer, a truncated payload, the fail-closed stub built
    when the proof itself raised — is read STRICTLY: every legacy count is
    treated as blocking, which is the behaviour that existed before the
    observation/blocker split. Degrading to the conservative reading means a
    malformed result can only over-withhold, never under-withhold.
    """
    if isinstance(completeness, dict):
        gate = completeness.get('publication_gate')
        if isinstance(gate, dict) and 'complete' in gate:
            return gate

    completeness = completeness if isinstance(completeness, dict) else {}
    return {
        'authority_effect': (
            game_ingestion_completeness.AUTHORITY_EFFECT_UNAVAILABLE
            if not completeness
            else game_ingestion_completeness.AUTHORITY_EFFECT_AUTHORITATIVE
        ),
        'complete': bool(completeness.get('publication_complete', False)),
        'blocking_scope_game_count': int(
            completeness.get('expected_final_games') or 0
        ),
        'blocking_completed_game_count': int(
            completeness.get('completed_final_games') or 0
        ),
        'blocking_unresolved_game_count': int(
            completeness.get('unresolved_final_games') or 0
        ),
        'blocking_terminal_failure_count': int(
            completeness.get('terminal_failure_games') or 0
        ),
        'finality_conflict_count': int(
            completeness.get('finality_conflicts') or 0
        ),
        'schedule_authority_missing_count': int(
            completeness.get('schedule_authority_missing') or 0
        ),
        'reason_codes': list(completeness.get('decision_reasons') or []),
        'schema': 'legacy_strict_fallback',
    }


def _publication_critical_from_game_lane(
    *, game_lane: dict, pull: dict, non_gamelog_critical_failed: int,
) -> dict:
    """Assemble publication-critical completeness from the game-level proof.

    The canonical completeness helper is reused unchanged — this only changes
    WHAT is counted as critical. Critical work is now governed GAMES; the
    demoted pitcher loop contributes best-effort accounting only. Every
    fail-closed rule (unknown fails closed, non-game-log lane failures are
    critical, an unavailable authority is never ``complete``) is preserved.
    """
    report = game_lane.get('report') or {}
    completeness = game_lane.get('completeness') or {}
    authority_available = bool(game_lane.get('report')) and bool(completeness)

    gate = _game_lane_publication_gate(completeness)

    # ONLY the publication-blocker view reaches the publication-critical
    # result. Shadow observation backlog, non-authoritative missing work
    # items, and non-authoritative retryable or terminal work are telemetry
    # about the lane's own rollout and are deliberately not folded in here —
    # they remain visible on the game-driven status block.
    critical_total = int(gate.get('blocking_scope_game_count') or 0)
    critical_completed = int(gate.get('blocking_completed_game_count') or 0)
    critical_unresolved = int(gate.get('blocking_unresolved_game_count') or 0)
    critical_failed = int(gate.get('blocking_terminal_failure_count') or 0)
    # Unknown required authority still fails closed in every mode.
    unknown = (
        int(gate.get('finality_conflict_count') or 0)
        + int(gate.get('schedule_authority_missing_count') or 0)
    )

    reason_codes = list(gate.get('reason_codes') or [])
    if not gate.get('complete', False) and not (
        critical_unresolved or critical_failed or unknown
    ):
        # The proof says withhold for a reason not expressible as a count
        # (for example an appearance-row reconciliation shortfall, a material
        # correction conflict, or an unavailable lane authority). Fail closed
        # by carrying it as unresolved critical work rather than losing it.
        critical_unresolved = max(critical_unresolved, 1)

    best_effort_total = int(pull.get('pitchers_total') or 0)
    best_effort_deferred = (
        int(pull.get('budget_exhausted_pitchers') or 0)
        + int(report.get('best_effort_games_deferred') or 0)
    )

    return publication_criticality.build_publication_critical_result(
        critical_total=critical_total,
        critical_completed=critical_completed,
        critical_failed=critical_failed,
        critical_unresolved=critical_unresolved,
        unknown_criticality=unknown,
        best_effort_total=best_effort_total,
        best_effort_completed=max(best_effort_total - best_effort_deferred, 0),
        best_effort_deferred=best_effort_deferred,
        non_gamelog_critical_failed=int(non_gamelog_critical_failed),
        authority_available=authority_available,
        reason_codes=reason_codes,
    )


def _publication_critical_from_legacy_pull(
    *, pull: dict, non_gamelog_critical_failed: int,
) -> dict:
    """Assemble the legacy lane's fail-closed completeness by item scope.

    New producers expose non-budget failures split by criticality. The fallback
    to the historical aggregate is intentionally strict so an older or malformed
    producer can only over-withhold, never silently reclassify a failure.
    """
    split_failure_keys = (
        'critical_non_budget_failed',
        'unknown_non_budget_failed',
        'best_effort_non_budget_failed',
    )
    has_scoped_failures = all(key in pull for key in split_failure_keys)
    critical_unresolved = int(
        pull.get('critical_non_budget_failed', 0)
        if has_scoped_failures else pull.get('gamelog_non_budget_failed', 0)
    )
    unknown_unresolved = int(
        pull.get('unknown_non_budget_failed', 0) if has_scoped_failures else 0
    )
    best_effort_unresolved = int(
        pull.get('best_effort_non_budget_failed', 0) if has_scoped_failures else 0
    )
    critical_budget = int(pull.get('critical_budget_exhausted', 0))
    unknown_budget = int(pull.get('unknown_budget_exhausted', 0))
    best_effort_budget = int(pull.get('best_effort_budget_exhausted', 0))
    critical_total = int(pull.get('publication_critical_total', 0))
    best_effort_total = int(pull.get('best_effort_total', 0))

    return publication_criticality.build_publication_critical_result(
        critical_total=critical_total,
        critical_completed=max(
            critical_total
            - critical_budget
            - unknown_budget
            - critical_unresolved
            - unknown_unresolved,
            0,
        ),
        critical_failed=critical_budget,
        critical_unresolved=critical_unresolved,
        unknown_criticality=unknown_budget + unknown_unresolved,
        best_effort_total=best_effort_total,
        best_effort_completed=max(
            best_effort_total - best_effort_budget - best_effort_unresolved,
            0,
        ),
        best_effort_deferred=best_effort_budget + best_effort_unresolved,
        non_gamelog_critical_failed=non_gamelog_critical_failed,
        authority_available=pull.get('criticality_authority_available', True),
    )


def _daily_sync_runtime_budget(run_started_monotonic: float) -> dict:
    stage_budget = _daily_sync_ingestion_budget_seconds()
    total_budget = _daily_sync_total_budget_seconds()
    final_phase_reserve = _daily_sync_final_phase_reserve_seconds()
    elapsed_before_ingestion = max(time.monotonic() - run_started_monotonic, 0.0)
    remaining_total = (
        None
        if total_budget is None
        else max(total_budget - elapsed_before_ingestion, 0.0)
    )
    budget_after_reserve = (
        None
        if remaining_total is None
        else max(remaining_total - final_phase_reserve, 0.0)
    )
    if budget_after_reserve is None:
        ingestion_budget = stage_budget
    elif stage_budget is None:
        ingestion_budget = budget_after_reserve
    else:
        ingestion_budget = min(stage_budget, budget_after_reserve)

    return {
        'total_budget_seconds': total_budget,
        'stage_budget_cap_seconds': stage_budget,
        'final_phase_reserve_seconds': final_phase_reserve,
        'elapsed_before_ingestion_seconds': round(elapsed_before_ingestion, 1),
        'remaining_total_seconds': (
            round(remaining_total, 1) if remaining_total is not None else None
        ),
        'budget_after_reserve_seconds': (
            round(budget_after_reserve, 1)
            if budget_after_reserve is not None
            else None
        ),
        'ingestion_budget_seconds': (
            round(ingestion_budget, 1) if ingestion_budget is not None else None
        ),
    }


def _daily_ingestion_budget_breakdown(runtime_budget: dict, game_lane: dict) -> dict:
    """The five distinct runtime quantities, reported separately (OPS-002).

    The August 6 incident was misread for a full revision because one field,
    ``ingestion_budget_seconds``, was doing the work of three different
    numbers. It is a COMBINED pool shared by the game-driven lane and the
    legacy GameLog writer — never a GameLog-only allowance — and the number
    that actually decides whether publication-critical work completes (the pool
    minus what the lane really consumed) appeared nowhere at top level.

    Every existing field is preserved untouched; this is additive evidence.
    """
    pool = runtime_budget.get('ingestion_budget_seconds')
    allocation = game_lane.get('lane_allocated_budget_seconds')
    elapsed = game_lane.get('lane_elapsed_seconds')
    remaining = game_lane.get('remaining_ingestion_budget_seconds')

    def _seconds(value):
        # Fail closed to null rather than guessing: an unmeasurable quantity
        # must read as unavailable, never as a confident zero.
        if value is None:
            return None
        try:
            return round(float(value), 3)
        except (TypeError, ValueError):
            return None

    return {
        # Configured stage ceiling. Not necessarily reachable, and never a
        # promise of time to any one lane.
        'configured_ingestion_cap_seconds': _seconds(
            runtime_budget.get('stage_budget_cap_seconds')
        ),
        # The result of _daily_sync_runtime_budget, computed BEFORE the lane
        # runs. Compatibility-equivalent to ingestion_budget_seconds.
        'combined_ingestion_pool_seconds': _seconds(pool),
        # The lane's configured share of the pool: 25% in shadow, 0 when the
        # lane is off or refused, the whole pool only under a separately
        # approved authoritative mode.
        'shadow_lane_configured_allocation_seconds': _seconds(allocation),
        # What the lane actually consumed, including a lane that raised.
        'shadow_lane_actual_elapsed_seconds': _seconds(elapsed),
        # Pool minus actual lane elapsed: the exact value handed to
        # sync_recent_logs, never negative.
        'legacy_gamelog_budget_seconds': _seconds(remaining),
    }


def _refresh_daily_schedule_finality_window(
    reference_date: date,
    days_back: int,
    *,
    source: str = 'daily_finality_preflight',
) -> dict:
    start_date = reference_date - timedelta(days=max(int(days_back or 0), 0))
    started = time.perf_counter()
    try:
        summary = schedule_ingestion.ingest_schedule(
            start_date,
            reference_date,
            source=source,
        )
    except Exception as exc:  # noqa: BLE001 - daily sync can continue fail-closed
        db.session.rollback()
        return {
            'status': 'failed',
            'source': source,
            'start_date': start_date.isoformat(),
            'end_date': reference_date.isoformat(),
            'summary': {'errors': 1},
            'error': str(exc),
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
        }
    return {
        'status': 'ok' if int((summary or {}).get('errors') or 0) == 0 else 'partial',
        'source': source,
        'start_date': start_date.isoformat(),
        'end_date': reference_date.isoformat(),
        'summary': summary,
        'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
    }


def _refresh_daily_slate_schedule_window(reference_date: date) -> dict:
    """Refresh the WP42 yesterday-through-+3 schedule authority window."""
    started = time.perf_counter()
    try:
        result = schedule_authority.ingest_rolling_window(
            reference_date,
            source='daily_slate_schedule',
        )
    except Exception as exc:  # noqa: BLE001 - sync continues with stale authority
        db.session.rollback()
        start_date, end_date = schedule_authority.rolling_window(reference_date)
        return {
            'status': 'failed',
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'summary': {'errors': 1},
            'error': str(exc),
            'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
        }
    result['elapsed_ms'] = round((time.perf_counter() - started) * 1000, 1)
    return result


def _refresh_postgame_schedule_finality(
    schedule_dates,
    *,
    source: str = 'postgame_finality_preflight',
) -> dict:
    started = time.perf_counter()
    results = []
    for slate_date in schedule_dates or []:
        try:
            results.append(
                schedule_ingestion.refresh_non_final_games_for_slate(
                    slate_date,
                    source=source,
                )
            )
        except Exception as exc:  # noqa: BLE001 - postgame can continue fail-closed
            db.session.rollback()
            results.append({
                'status': 'failed',
                'reason': 'finality_preflight_failed',
                'slate_date': (
                    slate_date.isoformat()
                    if hasattr(slate_date, 'isoformat')
                    else str(slate_date)
                ),
                'candidate_game_pks': [],
                'summary': {'errors': 1},
                'error': str(exc),
            })
    refreshed = [item for item in results if item.get('status') == 'refreshed']
    errors = [
        item
        for item in results
        if item.get('summary', {}).get('errors')
    ]
    return {
        'status': 'ok' if not errors else 'partial',
        'source': source,
        'slates_checked': len(results),
        'slates_refreshed': len(refreshed),
        'candidate_game_count': sum(
            len(item.get('candidate_game_pks') or [])
            for item in results
        ),
        'results': results,
        'elapsed_ms': round((time.perf_counter() - started) * 1000, 1),
    }


def sync_recent_logs(
    days_back: int = 7,
    reference_date: date | None = None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
    time_budget_seconds=_OPTIONAL_INPUT_NOT_PROVIDED,
    skip_game_pks=(),
    best_effort_only=False,
):
    """
    Pull recent game logs from the MLB Stats API for every active pitcher,
    insert missing logs, and correct existing logs when MLB revises an
    authoritative stat line.

    Foundation 3C status: this full-season-per-pitcher loop is NO LONGER the
    daily publication-critical path once the game-driven lane is authoritative.
    It is retained as the governed repair mechanism it always was good at —
    historical backfill, off-roster arms, IL/optioned reconciliation, operator
    replays — and the caller says so explicitly:

    * ``best_effort_only`` reports every item as best-effort, so a shortfall in
      this lane defers repair work and can never withhold the public snapshot;
    * ``skip_game_pks`` is the explicit conflict-prevention mechanism: games the
      authoritative game lane already reconciled in this run are not rewritten
      here, so two writers never touch the same canonical rows.

    Partial-failure semantics: a single pitcher whose fetch fails, or a single
    malformed game-log record, is dead-lettered (recorded in sync_failures with
    enough payload to retry) and skipped — it never aborts the rest of the
    batch. ``records_failed`` counts dead-lettered entities so the caller can
    mark the run 'partial'.

    Returns a dict suitable for API response / log line:
        {
          'new_logs_added':       int,
          'logs_corrected':       int,
          'pitchers_touched':     int,
          'errors':               int,
          'records_failed':       int,
          'correction_attempts_failed': int,
          'days_back':            int,
          'season':               int,
          'cutoff':               'YYYY-MM-DD',
        }
    """
    product_day = resolve_product_day(datetime.now(timezone.utc))
    timezone_limitations = ()
    if reference_date is None:
        reference_date = product_day.calendar_date
        timezone_limitations = product_day.limitations
    cutoff         = reference_date - timedelta(days=days_back)
    season         = _season_for(reference_date)
    season_opening = date(season, 1, 1)

    # Build a team_id -> abbreviation map from existing pitcher rows.
    # MLB's gameLog endpoint returns the opponent's id and name but NOT the
    # abbreviation, so we resolve it ourselves. Falls back to None if a team
    # somehow isn't represented in the pitchers table.
    team_abbr_map = dict(
        db.session.query(Pitcher.team_id, Pitcher.team_abbreviation)
        .filter(Pitcher.team_abbreviation.isnot(None))
        .distinct()
        .all()
    )

    if time_budget_seconds is _OPTIONAL_INPUT_NOT_PROVIDED:
        time_budget_seconds = _daily_sync_ingestion_budget_seconds()

    pitchers        = Pitcher.query.filter_by(active=True).all()
    # Publication-critical-first ordering (founder publication-critical contract):
    # process current active-MLB-roster pitching candidates — a safe superset of
    # the active bullpen and the records required by the public trusted snapshot
    # — before best-effort/historical corrections, so a runtime-budget shortfall
    # can only DEFER best-effort work and never starve publication-critical rows.
    # Criticality is read from each pitcher's already-synced canonical roster-status
    # code (in-memory, zero extra queries — it must not add pre-ingestion cost that
    # would worsen the very starvation this fixes). Unknown criticality is ordered
    # with critical and fails closed.
    # The canonical roster-status criticality classifier is NOT deleted: it
    # still orders this lane so its own repair work runs in a sensible order.
    # What changed is what it MEANS. Once the game-driven lane is authoritative,
    # publication completeness is driven by relevant game coverage, and every
    # item here is best-effort regardless of roster code.
    _criticality_by_id = {
        p.id: (
            publication_criticality.CRITICALITY_BEST_EFFORT if best_effort_only
            else publication_criticality.criticality_for_player(
                p.roster_status, p.position,
            )
        )
        for p in pitchers
    }
    skip_game_pks = {
        pk for pk in (_positive_external_id(value) for value in (skip_game_pks or ()))
        if pk is not None
    }
    splits_skipped_already_reconciled = 0
    pitchers = sorted(
        pitchers,
        key=lambda p: (
            1 if _criticality_by_id.get(p.id) == publication_criticality.CRITICALITY_BEST_EFFORT
            else 0,
            p.id or 0,
        ),
    )
    _critical_total = sum(
        1 for c in _criticality_by_id.values()
        if c != publication_criticality.CRITICALITY_BEST_EFFORT
    )
    _best_effort_total = len(pitchers) - _critical_total
    critical_budget_exhausted = 0
    unknown_budget_exhausted = 0
    best_effort_budget_exhausted = 0
    new_logs        = 0
    corrected_logs  = 0
    unchanged_logs  = 0
    errors          = 0
    records_failed  = 0
    correction_attempts_failed = 0
    unresolved_finality = 0
    pitchers_touched = 0
    splits_seen     = 0
    skip_counts     = {'missing_key': 0, 'not_completed': 0, 'before_cutoff': 0}
    affected_game_pks = set()
    # One finality resolution per game_pk per run, shared across pitchers.
    finality_cache = {}
    # One boxscore fetch per game_pk, shared by the leverage-index backfill and
    # the governed box-score fallback — never one fetch per log, and never two
    # fetches for the same game because two features wanted it.
    pitching_lines_cache = {}
    # Accounting for the fields the split cannot supply and the box score can.
    fallback_ledger = gamelog_source_authority.FallbackLedger()
    # One SELECT for every current-season row, instead of one SELECT per split
    # per pitcher. The same prefetch feeds both upserts and ledger coverage.
    existing_rows = (
        GameLog.query
        .filter(
            GameLog.game_date >= season_opening,
            GameLog.game_date <= reference_date,
        )
        .all()
    )
    existing_by_key = {
        (row.pitcher_id, row.mlb_game_pk): row
        for row in existing_rows
    }
    existing_rows_by_pitcher = {}
    for row in existing_rows:
        existing_rows_by_pitcher.setdefault(row.pitcher_id, []).append(row)
    # One SELECT for outstanding fetch failures; per-pitcher resolution
    # UPDATEs run only for pitchers that actually have one to resolve.
    unresolved_fetch_refs = {
        ref
        for (ref,) in (
            db.session.query(SyncFailure.entity_ref)
            .filter(SyncFailure.entity_type == PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE)
            .filter(SyncFailure.resolved.is_(False))
            .all()
        )
    }
    fetch_seconds = 0.0
    ingestion_started = time.monotonic()
    budget_exhausted_pitchers = 0
    ledger_coverage_records = 0
    ledger_coverage_complete = 0
    ledger_coverage_incomplete = 0
    non_budget_failed_by_criticality = {
        publication_criticality.CRITICALITY_PUBLICATION_CRITICAL: 0,
        publication_criticality.CRITICALITY_UNKNOWN: 0,
        publication_criticality.CRITICALITY_BEST_EFFORT: 0,
    }

    def _count_non_budget_failure(criticality):
        # A malformed classifier result must never become best-effort.
        key = (
            criticality
            if criticality in non_budget_failed_by_criticality
            else publication_criticality.CRITICALITY_UNKNOWN
        )
        non_budget_failed_by_criticality[key] += 1

    for index, pitcher in enumerate(pitchers):
        if (
            time_budget_seconds is not None
            and time.monotonic() - ingestion_started >= time_budget_seconds
        ):
            # Finish cleanly as partial instead of dying to the hard workflow
            # timeout mid-transaction. Remaining pitchers are dead-lettered in
            # one batch so the shortfall is visible, counted, and retried by
            # the next run — never silently absorbed.
            remaining = pitchers[index:]
            budget_exhausted_pitchers = len(remaining)
            records_failed += budget_exhausted_pitchers
            # Classify the deferred remainder. Because publication-critical
            # pitchers were ordered first, the tail is normally best-effort — but
            # we classify explicitly and fail closed on unknown, so the
            # publication gate can distinguish a best-effort-only shortfall from a
            # publication-critical one.
            critical_remaining_mlb_ids = []
            for _p in remaining:
                _crit = _criticality_by_id.get(_p.id)
                if _crit == publication_criticality.CRITICALITY_PUBLICATION_CRITICAL:
                    critical_budget_exhausted += 1
                    if len(critical_remaining_mlb_ids) < 200:
                        critical_remaining_mlb_ids.append(_p.mlb_id)
                elif _crit == publication_criticality.CRITICALITY_UNKNOWN:
                    unknown_budget_exhausted += 1
                    if len(critical_remaining_mlb_ids) < 200:
                        critical_remaining_mlb_ids.append(_p.mlb_id)
                else:
                    best_effort_budget_exhausted += 1
            logger.error(
                'Daily gameLog ingestion exceeded its %.0fs budget after %s of '
                '%s pitcher(s); dead-lettering the remaining %s '
                '(publication_critical=%s unknown=%s best_effort=%s) and finishing '
                'partial.',
                time_budget_seconds,
                index,
                len(pitchers),
                budget_exhausted_pitchers,
                critical_budget_exhausted,
                unknown_budget_exhausted,
                best_effort_budget_exhausted,
            )
            dead_letter.record_failure(
                DAILY_GAME_LOG_BUDGET_FAILURE_ENTITY_TYPE,
                'daily gameLog ingestion time budget exhausted',
                entity_ref=reference_date.isoformat(),
                payload={
                    'reference_date': reference_date.isoformat(),
                    'budget_seconds': time_budget_seconds,
                    'pitchers_total': len(pitchers),
                    'pitchers_processed': index,
                    'pitchers_remaining': budget_exhausted_pitchers,
                    'publication_critical_remaining': critical_budget_exhausted,
                    'unknown_criticality_remaining': unknown_budget_exhausted,
                    'best_effort_remaining': best_effort_budget_exhausted,
                    'remaining_mlb_ids': [p.mlb_id for p in remaining[:200]],
                    'publication_critical_remaining_mlb_ids': critical_remaining_mlb_ids,
                },
                sync_run_id=sync_run_id,
                job_name=job_name,
            )
            break

        fetch_started = time.monotonic()
        try:
            splits = mlb_client.get_pitcher_game_logs(pitcher.mlb_id, season=season)
        except Exception as e:
            # A per-pitcher fetch failure is dead-lettered with enough payload
            # to retry, then skipped — the rest of the league still syncs.
            fetch_seconds += time.monotonic() - fetch_started
            logger.warning('MLB fetch failed for %s (mlb_id=%s): %s',
                           pitcher.full_name, pitcher.mlb_id, e)
            errors += 1
            records_failed += 1
            _count_non_budget_failure(_criticality_by_id.get(pitcher.id))
            dead_letter.record_failure(
                PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE,
                e,
                entity_ref=pitcher.mlb_id,
                payload={
                    'pitcher_id': pitcher.id,
                    'mlb_id': pitcher.mlb_id,
                    'season': season,
                    'days_back': days_back,
                },
                sync_run_id=sync_run_id,
                job_name=job_name,
            )
            continue
        fetch_seconds += time.monotonic() - fetch_started

        if str(pitcher.mlb_id) in unresolved_fetch_refs:
            dead_letter.resolve_entity_failures(
                PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE,
                pitcher.mlb_id,
                job_name=job_name,
            )
            unresolved_fetch_refs.discard(str(pitcher.mlb_id))

        touched_this_pitcher = False
        coverage_target_game_pks = set()

        for split in splits or []:
            game_info     = split.get('game', {})
            game_pk       = game_info.get('gamePk')
            game_date_str = split.get('date')
            splits_seen  += 1

            if not game_pk or not game_date_str:
                skip_counts['missing_key'] += 1
                continue

            if _positive_external_id(game_pk) in skip_game_pks:
                # Conflict prevention: the authoritative game lane already
                # reconciled this game from its official box score in this same
                # run. Rewriting it here would be a second writer on the same
                # canonical rows.
                splits_skipped_already_reconciled += 1
                coverage_target_game_pks.add(_positive_external_id(game_pk))
                continue

            # Process one record in isolation: a single poisoned record is
            # dead-lettered and skipped rather than aborting this pitcher or the
            # whole batch.
            try:
                result = _ingest_game_log_split(
                    pitcher,
                    split,
                    cutoff,
                    team_abbr_map,
                    finality_cache=finality_cache,
                    existing_by_key=existing_by_key,
                    pitching_lines_cache=pitching_lines_cache,
                    sync_run_id=sync_run_id,
                    job_name=job_name,
                    fallback_ledger=fallback_ledger,
                )
            except Exception as e:
                logger.warning(
                    'Malformed game-log record for %s (mlb_id=%s, game_pk=%s): %s',
                    pitcher.full_name, pitcher.mlb_id, game_pk, e,
                )
                records_failed += 1
                _count_non_budget_failure(_criticality_by_id.get(pitcher.id))
                dead_letter.record_failure(
                    'game_log_record',
                    e,
                    entity_ref=game_pk,
                    payload={
                        'pitcher_id': pitcher.id,
                        'mlb_id': pitcher.mlb_id,
                        'game_pk': game_pk,
                        'game_date': game_date_str,
                        'season': season,
                    },
                    sync_run_id=sync_run_id,
                    job_name=job_name,
                )
                continue

            if result['status'] == 'inserted':
                new_logs += 1
                touched_this_pitcher = True
                positive_game_pk = _positive_external_id(game_pk)
                affected_game_pks.add(positive_game_pk)
                coverage_target_game_pks.add(positive_game_pk)
                log = result.get('log')
                if log is not None:
                    existing_rows_by_pitcher.setdefault(pitcher.id, []).append(log)
            elif result['status'] == 'corrected':
                corrected_logs += 1
                touched_this_pitcher = True
                positive_game_pk = _positive_external_id(game_pk)
                affected_game_pks.add(positive_game_pk)
                coverage_target_game_pks.add(positive_game_pk)
            elif result['status'] == 'unchanged':
                unchanged_logs += 1
                positive_game_pk = _positive_external_id(game_pk)
                coverage_target_game_pks.add(positive_game_pk)
            elif result['status'] == 'unsafe':
                records_failed += 1
                correction_attempts_failed += 1
                _count_non_budget_failure(_criticality_by_id.get(pitcher.id))
            elif result['status'] == 'unresolved_finality':
                # Already dead-lettered inside the split ingester. Counted as a
                # failed record so the run surfaces as partial — an appearance
                # we could not prove final must never disappear silently.
                records_failed += 1
                unresolved_finality += 1
                _count_non_budget_failure(_criticality_by_id.get(pitcher.id))
            elif result['status'] == 'skipped':
                reason = result.get('reason')
                if reason in skip_counts:
                    skip_counts[reason] += 1

        if touched_this_pitcher:
            pitchers_touched += 1

        coverage_target_game_pks.discard(None)
        if coverage_target_game_pks:
            coverage = pitcher_season_ledger_coverage.reconcile_pitcher_season_coverage(
                pitcher,
                splits,
                season=season,
                through_date=reference_date,
                sync_run_id=sync_run_id,
                finality_cache=finality_cache,
                stored_rows=existing_rows_by_pitcher.get(pitcher.id, ()),
                target_game_pks=coverage_target_game_pks,
            )
            ledger_coverage_records += coverage['coverage_records_upserted']
            ledger_coverage_complete += coverage['coverage_records_complete']
            ledger_coverage_incomplete += coverage['coverage_records_incomplete']

    # Lane-health canary: if the window contained ingestable splits and every
    # single one was dropped at the finality gate (never reached the upsert),
    # the daily lane is not merely quiet — it is dead (the exact failure mode
    # that hid the July 4 hole). Unsafe correction attempts do NOT trip the
    # canary: they reach the upsert and are already dead-lettered per record.
    ingestable_splits = (
        splits_seen
        - skip_counts['missing_key']
        - skip_counts['before_cutoff']
        # A split the authoritative game lane already reconciled was never this
        # lane's to ingest, so it must not make the canary read the lane as dead.
        - splits_skipped_already_reconciled
    )
    ingested_splits = new_logs + corrected_logs + unchanged_logs
    dropped_at_finality = skip_counts['not_completed'] + unresolved_finality
    if budget_exhausted_pitchers:
        # Budget exhaustion already dead-lettered and counted the shortfall;
        # the canary would misread a truncated run as a dead lane.
        lane_health = 'budget_exhausted'
    elif (
        ingestable_splits > 0
        and ingested_splits == 0
        and dropped_at_finality >= ingestable_splits
    ):
        lane_health = 'all_window_splits_dropped'
        records_failed += 1
        _count_non_budget_failure(
            publication_criticality.CRITICALITY_PUBLICATION_CRITICAL
        )
        logger.error(
            'Daily gameLog lane ingested nothing: %s split(s) in window, all '
            'dropped (not_completed=%s unresolved_finality=%s unsafe=%s). '
            'Treating the run as partial.',
            ingestable_splits,
            skip_counts['not_completed'],
            unresolved_finality,
            correction_attempts_failed,
        )
        dead_letter.record_failure(
            DAILY_GAME_LOG_LANE_FAILURE_ENTITY_TYPE,
            'daily gameLog lane dropped every in-window split',
            entity_ref=reference_date.isoformat(),
            payload={
                'reference_date': reference_date.isoformat(),
                'cutoff': cutoff.isoformat(),
                'splits_seen': splits_seen,
                'ingestable_splits': ingestable_splits,
                'skip_counts': dict(skip_counts),
                'unresolved_finality': unresolved_finality,
                'correction_attempts_failed': correction_attempts_failed,
            },
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
    elif ingestable_splits == 0:
        lane_health = 'no_window_splits'
    else:
        lane_health = 'ok'

    db.session.commit()
    for game_pk in sorted(game_pk for game_pk in affected_game_pks if game_pk is not None):
        safe_recompute_team_game_pitching_splits_for_game(
            game_pk,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.commit()

    elapsed_seconds = time.monotonic() - ingestion_started
    result = {
        'new_logs_added':    new_logs,
        'logs_corrected':    corrected_logs,
        'logs_unchanged':    unchanged_logs,
        'pitchers_touched':  pitchers_touched,
        'pitchers_total':    len(pitchers),
        'errors':            errors,
        'records_failed':    records_failed,
        'correction_attempts_failed': correction_attempts_failed,
        'unresolved_finality': unresolved_finality,
        'splits_seen':       splits_seen,
        'splits_skipped':    dict(skip_counts),
        'splits_skipped_already_reconciled': splits_skipped_already_reconciled,
        'best_effort_only':  bool(best_effort_only),
        'ledger_coverage_records': ledger_coverage_records,
        'ledger_coverage_complete': ledger_coverage_complete,
        'ledger_coverage_incomplete': ledger_coverage_incomplete,
        'lane_health':       lane_health,
        'budget_exhausted_pitchers': budget_exhausted_pitchers,
        # Publication-critical accounting (founder publication-critical contract).
        # Non-budget item failures retain the affected player's criticality;
        # lane-wide failures remain publication-critical. The historical total
        # stays exposed for compatibility, while the scoped counters drive the
        # completeness result in _complete_sync_phase.
        'publication_critical_total': _critical_total,
        'best_effort_total': _best_effort_total,
        'critical_budget_exhausted': critical_budget_exhausted,
        'unknown_budget_exhausted': unknown_budget_exhausted,
        'best_effort_budget_exhausted': best_effort_budget_exhausted,
        'gamelog_non_budget_failed': max(records_failed - budget_exhausted_pitchers, 0),
        'critical_non_budget_failed': non_budget_failed_by_criticality[
            publication_criticality.CRITICALITY_PUBLICATION_CRITICAL
        ],
        'unknown_non_budget_failed': non_budget_failed_by_criticality[
            publication_criticality.CRITICALITY_UNKNOWN
        ],
        'best_effort_non_budget_failed': non_budget_failed_by_criticality[
            publication_criticality.CRITICALITY_BEST_EFFORT
        ],
        # The criticality classifier reads each pitcher's synced roster-status code
        # in-memory, so it is always available; individual unresolved roster codes
        # are counted as unknown-criticality (which fails closed) rather than as an
        # unavailable authority.
        'criticality_authority_available': True,
        'time_budget_seconds': time_budget_seconds,
        'elapsed_seconds':   round(elapsed_seconds, 1),
        'fetch_seconds':     round(fetch_seconds, 1),
        'process_seconds':   round(elapsed_seconds - fetch_seconds, 1),
        'days_back':         days_back,
        'season':            season,
        'reference_date':    reference_date.isoformat(),
        'cutoff':            cutoff.isoformat(),
        # Always present, zeros included: an absent key would read as "the
        # fallback is not instrumented", which is a different claim from
        # "nothing was eligible".
        **fallback_ledger.summary(),
    }
    if timezone_limitations:
        result['limitations'] = list(timezone_limitations)
    return result


def _apply_boxscore_fallback(
    *, pitcher, game_pk, stat, values, pitching_lines_cache, ledger,
):
    """Supply approved fields the split omits, from the completed-game box score.

    Returns ``(stats, decision)``. The returned stats are the split's own stats
    when nothing was applied — the same object, so the split stays reportable as
    what the split actually said.

    The fetch is the reason this function owns the cache: at most one box-score
    read per game per run, shared with the leverage-index backfill, and only
    when an approved field is genuinely uncomparable. A row whose split already
    carries every approved field costs nothing.
    """
    empty = {'applied_fields': [], 'values': {}, 'refusals': {},
             'source_revision': None}
    if ledger is None:
        return stat, empty

    uncomparable = game_log_reconciliation.uncomparable_fields(values, stat)
    candidates = gamelog_source_authority.approved_uncomparable_fields(uncomparable)
    if not candidates:
        return stat, empty

    ledger.eligible_rows += 1
    positive_game_pk = _positive_external_id(game_pk)
    unavailable_reason = None
    pitching_lines = []

    if pitching_lines_cache is not None and game_pk in pitching_lines_cache:
        pitching_lines = pitching_lines_cache[game_pk] or []
    elif ledger.fetches >= BOXSCORE_FALLBACK_FETCH_CAP:
        ledger.fetch_cap_reached += 1
        unavailable_reason = gamelog_source_authority.REFUSED_BOXSCORE_UNAVAILABLE
    else:
        ledger.fetches += 1
        try:
            pitching_lines = mlb_client.get_game_pitching_lines(game_pk) or []
        except Exception as e:
            logger.warning(
                'Boxscore fallback fetch failed for game_pk=%s: %s', game_pk, e,
            )
            ledger.fetch_failures += 1
            unavailable_reason = (
                gamelog_source_authority.REFUSED_BOXSCORE_UNAVAILABLE
            )
        else:
            if pitching_lines_cache is not None:
                pitching_lines_cache[game_pk] = pitching_lines

    boxscore_stats = None
    if unavailable_reason is None:
        boxscore_stats, refusal = gamelog_source_authority.select_boxscore_line(
            pitching_lines, pitcher.mlb_id,
        )
        if refusal is not None:
            unavailable_reason = refusal

    decision = gamelog_source_authority.resolve_fallback_values(
        split_stats=stat,
        boxscore_stats=boxscore_stats,
        uncomparable=uncomparable,
        game_pk=positive_game_pk,
        pitcher_mlb_id=pitcher.mlb_id,
        game_final=True,
        unavailable_reason=unavailable_reason,
    )
    ledger.note_refusals(decision['refusals'])
    if not decision['applied_fields']:
        ledger.refused_rows += 1
        return stat, decision

    ledger.applied_rows += 1
    return gamelog_source_authority.enriched_stats(stat, decision), decision


def _record_boxscore_fallback_outcome(
    *, ledger, fallback, result, game_pk, pitcher,
):
    """Name the authority behind a fallback-supplied value that was written."""
    if ledger is None or not fallback['applied_fields']:
        return
    plan = result.get('plan') or {}
    changed = set(plan.get('changed_fields') or ())
    if result.get('status') == 'inserted':
        # The new row carries the fallback value from the moment it exists;
        # inserts report no changed fields, so this is not "already matching".
        outcome = gamelog_source_authority.OUTCOME_INSERTED
        ledger.inserted_rows += 1
    elif changed & set(fallback['applied_fields']):
        outcome = gamelog_source_authority.OUTCOME_CORRECTED
        ledger.corrected_rows += 1
    else:
        outcome = gamelog_source_authority.OUTCOME_ALREADY_MATCHING
        ledger.unchanged_rows += 1
    ledger.record_application(
        game_pk=_positive_external_id(game_pk),
        pitcher_mlb_id=getattr(pitcher, 'mlb_id', None),
        fields=fallback['applied_fields'],
        classifications=plan.get('difference_classifications') or (),
        source_revision=fallback['source_revision'],
        plan_fingerprint=game_log_reconciliation.plan_fingerprint([plan]),
        target_state_digest=plan.get('target_state_digest'),
        outcome=outcome,
    )


def _ingest_game_log_split(
    pitcher,
    split,
    cutoff,
    team_abbr_map,
    *,
    finality_cache=None,
    existing_by_key=None,
    pitching_lines_cache=None,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
    correction_source=DAILY_GAME_LOG_CORRECTION_SOURCE,
    fallback_ledger=None,
):
    """
    Insert or correct a single game-log split for a pitcher.

    Returns a result dict with status inserted, corrected, unchanged, unsafe,
    unresolved_finality, or skipped. Skipped covers before-cutoff,
    determinately non-final games, and malformed-but-empty keys.
    Raises on a genuinely poisoned record so the caller can dead-letter it.

    ``existing_by_key`` is an optional prefetched {(pitcher_id, game_pk): row}
    map covering the sync window. A hit skips the per-split SELECT (the
    dominant cost against a remote database); a miss still falls back to a
    real query before inserting, so correctness is unchanged.
    ``pitching_lines_cache`` dedupes the leverage-index boxscore fetch per
    game_pk (one game produces many inserted lines). The same cache serves the
    box-score fallback below, so a game is fetched at most once per run for
    both purposes.

    ``fallback_ledger`` enables the governed box-score fallback: a field the
    split does not carry at all (see ``gamelog_source_authority``) is supplied
    from the completed-game box score, fed through the same canonical values
    builder and the same planner, and written by the same writer. Omit it and
    the split remains the only source, exactly as before.
    """
    game_info     = split.get('game', {})
    stat          = split.get('stat', {})
    game_pk       = game_info.get('gamePk')
    game_date_str = split.get('date')
    game_type     = game_info.get('gameType', 'R')

    if not game_pk or not game_date_str:
        return {'status': 'skipped', 'reason': 'missing_key'}

    game_date = datetime.strptime(game_date_str, '%Y-%m-%d').date()

    # Cutoff before finality: gameLog returns the whole season, so the window
    # check must run first to keep schedule-ledger lookups bounded.
    if game_date < cutoff:
        return {'status': 'skipped', 'reason': 'before_cutoff'}

    if _split_has_own_status(game_info):
        # The split carries an explicit status (fixtures, hydrated responses):
        # trust it — it is the closest authority for this game.
        if not is_completed_game(game_info):
            return {'status': 'skipped', 'reason': 'not_completed'}
    else:
        # Statusless split (the production shape of the gameLog endpoint):
        # resolve finality from the scheduled_games ledger instead of
        # silently dropping the appearance.
        finality = resolve_scheduled_game_finality(game_pk, finality_cache)
        if finality == SPLIT_FINALITY_NOT_FINAL:
            return {'status': 'skipped', 'reason': 'not_completed'}
        if finality == SPLIT_FINALITY_UNKNOWN:
            dead_letter.record_failure(
                GAME_LOG_UNRESOLVED_FINALITY_ENTITY_TYPE,
                'statusless gameLog split with no scheduled_games coverage',
                entity_ref=game_pk,
                payload={
                    'pitcher_id': pitcher.id,
                    'mlb_id': pitcher.mlb_id,
                    'game_pk': game_pk,
                    'game_date': game_date_str,
                    'game_type': game_type,
                },
                sync_run_id=sync_run_id,
                job_name=job_name,
            )
            return {'status': 'unresolved_finality', 'reason': 'unresolved_finality'}

    opponent = split.get('opponent', {})
    # Team-at-appearance authority: the per-pitcher gameLog payload carries only the
    # opponent, not the pitcher's own side, so resolve the represented team from the
    # official schedule ledger (the side that faces this opponent). Never the
    # pitcher's current team.
    appearance_team = appearance_team_authority.resolve_for_write(
        game_pk=game_pk,
        opponent_team_id=opponent.get('id'),
    )
    values = _game_log_values_from_stats(
        stats=stat,
        pitcher=pitcher,
        game_pk=game_pk,
        game_date=game_date,
        game_type=game_type,
        opponent=opponent.get('name'),
        opponent_abbreviation=team_abbr_map.get(opponent.get('id')),
        games_started=parse_games_started(stat.get('gamesStarted')),
        appearance_team=appearance_team,
    )
    # Governed box-score fallback. The split is still primary: this only runs
    # for fields the split does not carry at all, and only for fields with an
    # explicitly approved fallback rule. The enriched stats then flow through
    # the same values builder and the same planner — there is no second
    # comparator and no direct assignment to the row.
    stat, fallback = _apply_boxscore_fallback(
        pitcher=pitcher,
        game_pk=game_pk,
        stat=stat,
        values=values,
        pitching_lines_cache=pitching_lines_cache,
        ledger=fallback_ledger,
    )
    if fallback['applied_fields']:
        values = _game_log_values_from_stats(
            stats=stat,
            pitcher=pitcher,
            game_pk=game_pk,
            game_date=game_date,
            game_type=game_type,
            opponent=opponent.get('name'),
            opponent_abbreviation=team_abbr_map.get(opponent.get('id')),
            games_started=parse_games_started(stat.get('gamesStarted')),
            appearance_team=appearance_team,
        )

    row_key = (pitcher.id, _positive_external_id(game_pk))
    preloaded = (
        existing_by_key.get(row_key)
        if existing_by_key is not None and row_key[1] is not None
        else None
    )
    result = _upsert_game_log_from_authoritative_values(
        pitcher=pitcher,
        game_pk=game_pk,
        values=values,
        stats=stat,
        source=correction_source,
        sync_run_id=sync_run_id,
        job_name=job_name,
        appearance_team=appearance_team,
        fallback_source=gamelog_source_authority.CORRECTION_SOURCE_BOXSCORE_FALLBACK,
        fallback_fields=fallback['applied_fields'],
        # A map hit avoids the per-split SELECT; a miss keeps the real query
        # so a row stored under an out-of-window date is never double-inserted.
        **({'existing': preloaded} if preloaded is not None else {}),
    )
    _record_boxscore_fallback_outcome(
        ledger=fallback_ledger,
        fallback=fallback,
        result=result,
        game_pk=game_pk,
        pitcher=pitcher,
    )

    # Backfill leverage index from the boxscore. A failed call or a missing LI
    # field just leaves the column as None — never crash the sync.
    if result['status'] != 'inserted':
        return result
    log = result['log']
    if existing_by_key is not None and row_key[1] is not None:
        existing_by_key[row_key] = log

    if pitching_lines_cache is not None and game_pk in pitching_lines_cache:
        pitching_lines = pitching_lines_cache[game_pk]
    else:
        try:
            pitching_lines = mlb_client.get_game_pitching_lines(game_pk)
        except Exception as e:
            logger.warning('Boxscore fetch failed for game_pk=%s: %s', game_pk, e)
            pitching_lines = []
        if pitching_lines_cache is not None:
            pitching_lines_cache[game_pk] = pitching_lines

    for line in pitching_lines or []:
        if line.get('player_id') == pitcher.mlb_id:
            stats_block = line.get('stats') or {}
            for li_key in ('leverageIndex', 'avgLeverageIndex', 'avgLI'):
                raw_li = stats_block.get(li_key)
                if raw_li is not None:
                    try:
                        log.leverage_index = float(raw_li)
                    except (TypeError, ValueError):
                        pass
                    break
            break

    return result


def recalculate_all_fatigue(reference_date: date | None = None):
    """
    Recalculate fatigue scores for every active pitcher against a SINGLE
    canonical availability reference date — the latest completed MLB workload
    date + 1 day ("tonight's availability"), resolved by
    ``sync_metadata.canonical_fatigue_reference_date``.

    This is the one production authority. The scheduled APScheduler sync, the
    GitHub Actions / manual sync endpoint, and the recalculate endpoint all flow
    through here, so the same game logs always yield the same fatigue scores no
    matter which path last ran. It replaces the previous split where the daily
    job scored each pitcher at their own last game date while the sync endpoint
    scored against the host's runtime "today" — a divergence that let one
    database tell two different league-wide stories.

    Pass ``reference_date`` only to pin the anchor explicitly (e.g. in tests);
    production callers leave it None so the canonical date is derived from
    durable workload metadata. Returns the count of pitchers updated.
    """
    ref = sync_metadata.canonical_fatigue_reference_date(reference_date)
    if ref is None:
        # No workload data at all → nothing to anchor against.
        return 0

    window_start = ref - timedelta(days=14)
    pitchers = Pitcher.query.filter_by(active=True).all()
    failed_fetch_refs = {
        row[0]
        for row in (
            db.session.query(SyncFailure.entity_ref)
            .filter(SyncFailure.entity_type == PITCHER_GAME_LOG_FAILURE_ENTITY_TYPE)
            .filter(SyncFailure.resolved.is_(False))
            .all()
        )
    }
    updated  = 0

    for pitcher in pitchers:
        if str(pitcher.mlb_id) in failed_fetch_refs:
            continue
        logs = (
            GameLog.query
            .filter(
                GameLog.pitcher_id == pitcher.id,
                GameLog.game_date  >= window_start,
                GameLog.game_date  <= ref,
            )
            .order_by(desc(GameLog.game_date))
            .all()
        )
        if not logs:
            continue

        score = calculate_fatigue(pitcher, logs, reference_date=ref)
        db.session.add(score)
        updated += 1

    db.session.commit()
    return updated


def record_sync_error_details(
    entity_type,
    error_details,
    sync_run_id=None,
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    """Persist fetch-domain error details from sub-syncs as dead letters."""
    count = 0
    for detail in error_details or []:
        payload = dict(detail)
        entity_ref = (
            payload.get('pitcher_mlb_id')
            or payload.get('team_id')
            or payload.get('source')
        )
        failure = dead_letter.record_failure(
            entity_type,
            payload.get('error') or 'MLB API fetch failed',
            entity_ref=entity_ref,
            payload=payload,
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        if failure is not None:
            count += 1
    return count


def phase0d_evidence_build_enabled():
    value = os.environ.get('PHASE0D_EVIDENCE_BUILD', 'true')
    return str(value).strip().lower() not in _FALSEY_ENV_VALUES


def phase0e_read_build_enabled():
    value = os.environ.get('PHASE0E_READ_BUILD', 'true')
    return str(value).strip().lower() not in _FALSEY_ENV_VALUES


def phase0e_reconciliation_audit_enabled():
    value = os.environ.get('PHASE0E_RECONCILIATION_AUDIT', 'true')
    return str(value).strip().lower() not in _FALSEY_ENV_VALUES


def _safe_build_workload_recovery_evidence_stage(
    product_dates,
    *,
    sync_run_id=None,
    source='sync',
    job_name=sync_metadata.JOB_DAILY_SYNC,
    run_logger=None,
):
    logger_to_use = run_logger or logger
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    if not dates:
        return {'status': 'skipped', 'reason': 'no_product_dates', 'dates': []}
    if not phase0d_evidence_build_enabled():
        logger_to_use.info(
            'Phase 0D workload evidence build skipped: PHASE0D_EVIDENCE_BUILD disabled.'
        )
        return {'status': 'skipped', 'reason': 'disabled', 'dates': [d.isoformat() for d in dates]}

    started = time.perf_counter()
    try:
        from services.appearance_context_evidence import (
            build_appearance_context_evidence,
            rebuild_marked_appearance_context_evidence,
        )
        from services.inherited_traffic_evidence import (
            build_inherited_traffic_evidence,
            rebuild_marked_inherited_traffic_evidence,
        )
        from services.starter_exposure_evidence import (
            build_starter_exposure_evidence,
            rebuild_marked_starter_exposure_evidence,
        )
        from services.roster_depth_evidence import (
            build_roster_depth_evidence,
            rebuild_marked_roster_depth_evidence,
        )
        from services.entry_band_usage_evidence import (
            build_entry_band_usage_evidence,
            rebuild_marked_entry_band_usage_evidence,
        )
        from services.team_relief_composition_evidence import (
            build_team_relief_composition_evidence,
            rebuild_marked_team_relief_composition_evidence,
        )
        from services.workload_recovery_evidence import (
            build_workload_recovery_evidence,
            rebuild_marked_workload_recovery_evidence,
        )

        dates_label = ','.join(day.isoformat() for day in dates)

        def run_evidence_step(step_name, action):
            step_started = time.perf_counter()
            logger_to_use.info(
                'Phase 0D evidence step starting: step=%s dates=%s.',
                step_name,
                dates_label,
            )
            try:
                result = action()
            except Exception:
                elapsed_ms = round((time.perf_counter() - step_started) * 1000, 1)
                logger_to_use.warning(
                    'Phase 0D evidence step failed: step=%s dates=%s elapsed_ms=%s.',
                    step_name,
                    dates_label,
                    elapsed_ms,
                )
                raise
            elapsed_ms = round((time.perf_counter() - step_started) * 1000, 1)
            logger_to_use.info(
                'Phase 0D evidence step completed: step=%s status=%s '
                'objects_built=%s objects_rebuilt=%s dates_rebuilt=%s elapsed_ms=%s.',
                step_name,
                result.get('status'),
                result.get('objects_built', 0),
                result.get('objects_rebuilt', 0),
                ','.join(result.get('dates_rebuilt') or []),
                elapsed_ms,
            )
            return result

        def build_for_dates(step_name, builder):
            return [
                run_evidence_step(
                    f'{step_name}:{product_date.isoformat()}',
                    lambda product_date=product_date: builder(
                        product_date,
                        sync_run_id=sync_run_id,
                        source=source,
                    ),
                )
                for product_date in dates
            ]

        sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_WORKLOAD_EVIDENCE)
        rebuild = run_evidence_step(
            'workload_recovery_rebuild',
            lambda: rebuild_marked_workload_recovery_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        appearance_rebuild = run_evidence_step(
            'appearance_context_rebuild',
            lambda: rebuild_marked_appearance_context_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        inherited_rebuild = run_evidence_step(
            'inherited_traffic_rebuild',
            lambda: rebuild_marked_inherited_traffic_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        starter_exposure_rebuild = run_evidence_step(
            'starter_exposure_rebuild',
            lambda: rebuild_marked_starter_exposure_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        roster_depth_rebuild = run_evidence_step(
            'roster_depth_rebuild',
            lambda: rebuild_marked_roster_depth_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        entry_band_usage_rebuild = run_evidence_step(
            'entry_band_usage_rebuild',
            lambda: rebuild_marked_entry_band_usage_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        team_relief_composition_rebuild = run_evidence_step(
            'team_relief_composition_rebuild',
            lambda: rebuild_marked_team_relief_composition_evidence(
                sync_run_id=sync_run_id,
                source=source,
            ),
        )
        builds = build_for_dates('workload_recovery_build', build_workload_recovery_evidence)
        appearance_builds = build_for_dates('appearance_context_build', build_appearance_context_evidence)
        inherited_builds = build_for_dates('inherited_traffic_build', build_inherited_traffic_evidence)
        starter_exposure_builds = build_for_dates('starter_exposure_build', build_starter_exposure_evidence)
        roster_depth_builds = build_for_dates('roster_depth_build', build_roster_depth_evidence)
        entry_band_usage_builds = build_for_dates('entry_band_usage_build', build_entry_band_usage_evidence)
        team_relief_composition_builds = build_for_dates(
            'team_relief_composition_build',
            build_team_relief_composition_evidence,
        )
        db.session.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.info(
            'Phase 0D evidence stage complete: dates=%s workload_rebuilt=%s '
            'appearance_rebuilt=%s inherited_rebuilt=%s starter_exposure_rebuilt=%s '
            'roster_depth_rebuilt=%s entry_band_usage_rebuilt=%s '
            'team_relief_composition_rebuilt=%s '
            'workload_objects_built=%s appearance_objects_built=%s '
            'inherited_objects_built=%s starter_exposure_objects_built=%s '
            'roster_depth_objects_built=%s entry_band_usage_objects_built=%s '
            'team_relief_composition_objects_built=%s '
            'elapsed_ms=%s.',
            ','.join(day.isoformat() for day in dates),
            rebuild.get('objects_rebuilt', 0),
            appearance_rebuild.get('objects_rebuilt', 0),
            inherited_rebuild.get('objects_rebuilt', 0),
            starter_exposure_rebuild.get('objects_rebuilt', 0),
            roster_depth_rebuild.get('objects_rebuilt', 0),
            entry_band_usage_rebuild.get('objects_rebuilt', 0),
            team_relief_composition_rebuild.get('objects_rebuilt', 0),
            sum(item.get('objects_built', 0) for item in builds),
            sum(item.get('objects_built', 0) for item in appearance_builds),
            sum(item.get('objects_built', 0) for item in inherited_builds),
            sum(item.get('objects_built', 0) for item in starter_exposure_builds),
            sum(item.get('objects_built', 0) for item in roster_depth_builds),
            sum(item.get('objects_built', 0) for item in entry_band_usage_builds),
            sum(item.get('objects_built', 0) for item in team_relief_composition_builds),
            elapsed_ms,
        )
        return {
            'status': 'built',
            'dates': [d.isoformat() for d in dates],
            'rebuild': rebuild,
            'builds': builds,
            'appearance_rebuild': appearance_rebuild,
            'appearance_builds': appearance_builds,
            'inherited_rebuild': inherited_rebuild,
            'inherited_builds': inherited_builds,
            'starter_exposure_rebuild': starter_exposure_rebuild,
            'starter_exposure_builds': starter_exposure_builds,
            'roster_depth_rebuild': roster_depth_rebuild,
            'roster_depth_builds': roster_depth_builds,
            'entry_band_usage_rebuild': entry_band_usage_rebuild,
            'entry_band_usage_builds': entry_band_usage_builds,
            'team_relief_composition_rebuild': team_relief_composition_rebuild,
            'team_relief_composition_builds': team_relief_composition_builds,
            'elapsed_ms': elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001 - optional evidence stage is fail-soft
        db.session.rollback()
        dead_letter.record_failure(
            WORKLOAD_EVIDENCE_FAILURE_ENTITY_TYPE,
            exc,
            entity_ref=','.join(day.isoformat() for day in dates),
            payload={
                'product_dates': [day.isoformat() for day in dates],
                'source': source,
                'stage': sync_metadata.STAGE_WORKLOAD_EVIDENCE,
            },
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.warning(
            'Phase 0D workload evidence stage failed after %sms; sync will continue: %s',
            elapsed_ms,
            exc,
        )
        return {
            'status': 'failed',
            'dates': [d.isoformat() for d in dates],
            'error': str(exc),
            'elapsed_ms': elapsed_ms,
        }


def _safe_build_composed_reads_stage(
    product_dates,
    *,
    sync_run_id=None,
    source='sync',
    job_name=sync_metadata.JOB_DAILY_SYNC,
    run_logger=None,
):
    logger_to_use = run_logger or logger
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    if not dates:
        return {'status': 'skipped', 'reason': 'no_product_dates', 'dates': []}
    if not phase0e_read_build_enabled():
        logger_to_use.info(
            'Phase 0E composed read build skipped: PHASE0E_READ_BUILD disabled.'
        )
        return {'status': 'skipped', 'reason': 'disabled', 'dates': [d.isoformat() for d in dates]}

    started = time.perf_counter()
    sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_COMPOSED_READS)
    try:
        from services.reliever_daily_read import (
            build_reliever_daily_reads,
            rebuild_marked_reliever_daily_reads,
        )
        reliever_started = time.perf_counter()
        reliever_rebuild = rebuild_marked_reliever_daily_reads(
            sync_run_id=sync_run_id,
            source=source,
        )
        reliever_builds = [
            build_reliever_daily_reads(
                product_date,
                sync_run_id=sync_run_id,
                source=source,
            )
            for product_date in dates
        ]
        db.session.commit()
        reliever_elapsed_ms = round((time.perf_counter() - reliever_started) * 1000, 1)
        logger_to_use.info(
            'Phase 0E reliever read stage complete: dates=%s reads_rebuilt=%s '
            'reads_built=%s elapsed_ms=%s.',
            ','.join(day.isoformat() for day in dates),
            reliever_rebuild.get('reads_rebuilt', 0),
            sum(item.get('reads_built', 0) for item in reliever_builds),
            reliever_elapsed_ms,
        )
        reliever_result = {
            'status': 'built',
            'dates': [d.isoformat() for d in dates],
            'rebuild': reliever_rebuild,
            'builds': reliever_builds,
            'elapsed_ms': reliever_elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001 - optional read stage is fail-soft
        db.session.rollback()
        _record_composed_read_failure(
            exc,
            dates=dates,
            source=source,
            read_type='reliever_daily_read',
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.warning(
            'Phase 0E reliever read stage failed after %sms; sync will continue: %s',
            elapsed_ms,
            exc,
        )
        return {
            'status': 'failed',
            'dates': [d.isoformat() for d in dates],
            'error': str(exc),
            'elapsed_ms': elapsed_ms,
            'reliever': {'status': 'failed', 'error': str(exc)},
            'team': {'status': 'skipped', 'reason': 'reliever_failed'},
        }

    try:
        from services.team_daily_read import (
            build_team_daily_reads,
            rebuild_marked_team_daily_reads,
        )
        team_started = time.perf_counter()
        team_rebuild = rebuild_marked_team_daily_reads(
            sync_run_id=sync_run_id,
            source=source,
        )
        team_builds = [
            build_team_daily_reads(
                product_date,
                sync_run_id=sync_run_id,
                source=source,
            )
            for product_date in dates
        ]
        db.session.commit()
        team_elapsed_ms = round((time.perf_counter() - team_started) * 1000, 1)
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.info(
            'Phase 0E team read stage complete: dates=%s reads_rebuilt=%s '
            'reads_built=%s elapsed_ms=%s.',
            ','.join(day.isoformat() for day in dates),
            team_rebuild.get('reads_rebuilt', 0),
            sum(item.get('reads_built', 0) for item in team_builds),
            team_elapsed_ms,
        )
        return {
            'status': 'built',
            'dates': [d.isoformat() for d in dates],
            'reliever': reliever_result,
            'team': {
                'status': 'built',
                'dates': [d.isoformat() for d in dates],
                'rebuild': team_rebuild,
                'builds': team_builds,
                'elapsed_ms': team_elapsed_ms,
            },
            'elapsed_ms': elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001 - team read stage is fail-soft
        db.session.rollback()
        _record_composed_read_failure(
            exc,
            dates=dates,
            source=source,
            read_type='team_daily_read',
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.warning(
            'Phase 0E team read stage failed after %sms; reliever reads remain committed: %s',
            elapsed_ms,
            exc,
        )
        return {
            'status': 'partial',
            'dates': [d.isoformat() for d in dates],
            'reliever': reliever_result,
            'team': {'status': 'failed', 'error': str(exc)},
            'elapsed_ms': elapsed_ms,
        }


def _record_composed_read_failure(
    exc,
    *,
    dates,
    source,
    read_type,
    sync_run_id,
    job_name,
):
    dead_letter.record_failure(
        COMPOSED_READ_FAILURE_ENTITY_TYPE,
        exc,
        entity_ref=','.join(day.isoformat() for day in dates),
        payload={
            'product_dates': [day.isoformat() for day in dates],
            'source': source,
            'stage': sync_metadata.STAGE_COMPOSED_READS,
            'read_type': read_type,
        },
        sync_run_id=sync_run_id,
        job_name=job_name,
    )


def _safe_run_legacy_read_reconciliation_audit_stage(
    product_dates,
    *,
    sync_run_id=None,
    source='sync',
    job_name=sync_metadata.JOB_DAILY_SYNC,
    run_logger=None,
):
    logger_to_use = run_logger or logger
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    if not dates:
        return {'status': 'skipped', 'reason': 'no_product_dates', 'dates': []}
    if not phase0e_reconciliation_audit_enabled():
        logger_to_use.info(
            'Phase 0E reconciliation audit skipped: '
            'PHASE0E_RECONCILIATION_AUDIT disabled.'
        )
        return {'status': 'skipped', 'reason': 'disabled', 'dates': [d.isoformat() for d in dates]}

    started = time.perf_counter()
    sync_metadata.set_sync_stage(sync_run_id, STAGE_LEGACY_READ_RECONCILIATION_AUDIT)
    try:
        from services.legacy_read_reconciliation import run_reconciliation_audit
        results = [
            run_reconciliation_audit(
                product_date,
                sync_run_id=sync_run_id,
                source=source,
                force_skip_reads_missing=not phase0e_read_build_enabled(),
            )
            for product_date in dates
        ]
        db.session.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.info(
            'Phase 0E reconciliation audit complete: dates=%s elapsed_ms=%s.',
            ','.join(day.isoformat() for day in dates),
            elapsed_ms,
        )
        return {
            'status': 'completed',
            'dates': [d.isoformat() for d in dates],
            'results': results,
            'elapsed_ms': elapsed_ms,
        }
    except Exception as exc:  # noqa: BLE001 - audit stage is fail-soft
        db.session.rollback()
        dead_letter.record_failure(
            LEGACY_READ_AUDIT_FAILURE_ENTITY_TYPE,
            exc,
            entity_ref=','.join(day.isoformat() for day in dates),
            payload={
                'product_dates': [day.isoformat() for day in dates],
                'source': source,
                'stage': STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
            },
            sync_run_id=sync_run_id,
            job_name=job_name,
        )
        db.session.commit()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        logger_to_use.warning(
            'Phase 0E reconciliation audit failed after %sms; sync will continue: %s',
            elapsed_ms,
            exc,
        )
        return {
            'status': 'failed',
            'dates': [d.isoformat() for d in dates],
            'error': str(exc),
            'elapsed_ms': elapsed_ms,
        }


def _daily_sync_phase_status(result):
    if isinstance(result, dict):
        status = result.get('status') or result.get('reason') or 'completed'
        snapshot_id = result.get('snapshot_id')
        if snapshot_id is not None:
            return f'{status};snapshot_id={snapshot_id}'
        return str(status)
    return 'completed'


def _run_logged_daily_sync_phase(run_logger, timings, phase_name, operation):
    started = time.perf_counter()
    run_logger.info(
        'Daily sync post-fatigue phase starting: phase=%s.',
        phase_name,
    )
    try:
        result = operation()
    except Exception as exc:
        elapsed_seconds = round(time.perf_counter() - started, 3)
        timings.append({
            'phase': phase_name,
            'status': 'failed',
            'elapsed_seconds': elapsed_seconds,
        })
        run_logger.warning(
            'Daily sync post-fatigue phase failed: phase=%s '
            'elapsed_seconds=%s error=%s',
            phase_name,
            elapsed_seconds,
            exc,
        )
        raise

    elapsed_seconds = round(time.perf_counter() - started, 3)
    status = _daily_sync_phase_status(result)
    timings.append({
        'phase': phase_name,
        'status': status,
        'elapsed_seconds': elapsed_seconds,
    })
    run_logger.info(
        'Daily sync post-fatigue phase completed: phase=%s status=%s '
        'elapsed_seconds=%s.',
        phase_name,
        status,
        elapsed_seconds,
    )
    return result


def _run_post_publish_internal_daily_sync_phase(
    run_logger,
    timings,
    phase_name,
    operation,
):
    try:
        return _run_logged_daily_sync_phase(
            run_logger,
            timings,
            phase_name,
            operation,
        )
    except Exception as exc:  # noqa: BLE001 - internal enrichment is post-publish
        run_logger.warning(
            'Daily sync post-publish internal phase failed after public '
            'snapshot publish: phase=%s error=%s',
            phase_name,
            exc,
        )
        return {'status': 'failed', 'error': str(exc)}


def _run_post_publish_internal_postgame_phase(run_logger, phase_name, operation):
    started = time.perf_counter()
    run_logger.info(
        'Postgame post-publish internal phase starting: phase=%s.',
        phase_name,
    )
    try:
        result = operation()
    except Exception as exc:  # noqa: BLE001 - internal enrichment is post-publish
        db.session.rollback()
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        run_logger.warning(
            'Postgame post-publish internal phase failed after public snapshot '
            'publish: phase=%s elapsed_ms=%s error=%s',
            phase_name,
            elapsed_ms,
            exc,
        )
        return {'status': 'failed', 'error': str(exc), 'elapsed_ms': elapsed_ms}

    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    status = _daily_sync_phase_status(result)
    run_logger.info(
        'Postgame post-publish internal phase completed: phase=%s status=%s '
        'elapsed_ms=%s.',
        phase_name,
        status,
        elapsed_ms,
    )
    return result


def _restore_completed_sync_publish_stage(sync_run_id, *, run_logger=None):
    if not sync_run_id:
        return None
    try:
        run = db.session.get(SyncRun, sync_run_id)
        if run is None or run.completed_at is None:
            return run
        if run.stage == sync_metadata.STAGE_PUBLISHED:
            return run
        run.stage = sync_metadata.STAGE_PUBLISHED
        db.session.commit()
        if run_logger is not None:
            run_logger.info(
                'Restored completed sync stage after post-publish internal '
                'phases: sync_run_id=%s.',
                sync_run_id,
            )
        return run
    except Exception as exc:  # noqa: BLE001 - diagnostics must not undo publish
        db.session.rollback()
        if run_logger is not None:
            run_logger.warning(
                'Could not restore completed sync published stage: '
                'sync_run_id=%s error=%s',
                sync_run_id,
                exc,
            )
        return None


def _refresh_availability_backtest_phase(sync_run_id, status, run_logger):
    try:
        from services.availability_backtest import refresh_availability_backtest
        backtest = refresh_availability_backtest()
        if status is not None:
            status['availability_backtest_status'] = backtest.get('status')
            status['availability_backtest_computed_at'] = backtest.get('computed_at')
        run_logger.info(
            'Refreshed availability backtest (%s)',
            backtest.get('computed_at') or backtest.get('status'),
        )
        result = {'status': backtest.get('status') or 'completed'}
    except Exception as exc:
        db.session.rollback()
        if status is not None:
            status['availability_backtest_status'] = 'failed'
            status['availability_backtest_error'] = str(exc)
        run_logger.warning('Availability backtest refresh failed: %s', exc)
        result = {'status': 'failed', 'error': str(exc)}
    sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_BACKTEST_REFRESH)
    return result


def _run_logged_internal_enrichment_phase(
    run_logger,
    timings,
    phase_name,
    operation,
):
    started = time.perf_counter()
    run_logger.info('Internal enrichment phase starting: phase=%s.', phase_name)
    try:
        result = operation()
    except Exception as exc:
        elapsed_seconds = round(time.perf_counter() - started, 3)
        timings.append({
            'phase': phase_name,
            'status': 'failed',
            'elapsed_seconds': elapsed_seconds,
        })
        run_logger.warning(
            'Internal enrichment phase failed: phase=%s elapsed_seconds=%s '
            'error=%s',
            phase_name,
            elapsed_seconds,
            exc,
        )
        raise

    elapsed_seconds = round(time.perf_counter() - started, 3)
    status = _daily_sync_phase_status(result)
    timings.append({
        'phase': phase_name,
        'status': status,
        'elapsed_seconds': elapsed_seconds,
    })
    run_logger.info(
        'Internal enrichment phase completed: phase=%s status=%s '
        'elapsed_seconds=%s.',
        phase_name,
        status,
        elapsed_seconds,
    )
    return result


def _internal_phase_failed(result):
    if isinstance(result, dict):
        return result.get('status') == 'failed'
    return False


def _aggregate_internal_checkpoint_results(phase_name, jobs, results):
    if not jobs:
        return {
            'status': 'skipped',
            'reason': 'no_jobs_planned',
            'jobs': [],
        }
    failed = [result for result in results if _internal_phase_failed(result)]
    if failed:
        status = sync_metadata.STATUS_FAILED
    elif all(
        isinstance(result, dict) and result.get('status') == sync_jobs.STATUS_SKIPPED
        for result in results
    ):
        status = sync_jobs.STATUS_SKIPPED
    elif any(
        isinstance(result, dict) and result.get('status') == sync_metadata.STATUS_PARTIAL
        for result in results
    ):
        status = sync_metadata.STATUS_PARTIAL
    else:
        status = 'completed'
    return {
        'status': status,
        'phase': phase_name,
        'dates': [
            job.product_date.isoformat()
            for job in jobs
            if job.product_date is not None
        ],
        'jobs': results,
    }


def _run_checkpointed_internal_enrichment_phase(
    *,
    run_logger,
    timings,
    phase_name,
    jobs,
    sync_run_id,
    operation_for_job,
):
    results = []
    for job in jobs:
        job_phase_name = f'{phase_name}:{job.product_date.isoformat()}'
        results.append(
            _run_logged_internal_enrichment_phase(
                run_logger,
                timings,
                job_phase_name,
                lambda job=job: sync_jobs.run_checkpointed_job(
                    job,
                    lambda job=job: operation_for_job(job),
                    sync_run_id=sync_run_id,
                    reclaim_abandoned=True,
                    run_logger=run_logger,
                ),
            )
        )
    return _aggregate_internal_checkpoint_results(phase_name, jobs, results)


def _run_internal_enrichment_phases(
    product_dates,
    *,
    sync_run_id,
    source,
    job_name,
    run_logger,
    include_backtest,
    status=None,
):
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    if not dates:
        return {
            'status': 'skipped',
            'reason': 'no_product_dates',
            'product_dates': [],
            'phase_results': {},
        }

    timings = []
    phase_results = {}
    planned_jobs = sync_jobs.plan_internal_enrichment_jobs(
        dates,
        include_backtest=include_backtest,
        sync_run_id=sync_run_id,
        run_logger=run_logger,
    )
    sync_jobs.reclaim_running_jobs(
        planned_jobs,
        reason='internal enrichment lock acquired',
        reclaim_abandoned=True,
        run_logger=run_logger,
    )
    checkpoint_jobs = sync_jobs.jobs_by_name(planned_jobs)
    checkpoint_summary = sync_jobs.summary_for_product_dates(dates)
    run_logger.info(
        'Internal enrichment checkpoint summary after planning: '
        'dates=%s total=%s succeeded=%s pending=%s running=%s failed=%s skipped=%s.',
        ','.join(day.isoformat() for day in dates),
        checkpoint_summary['total'],
        checkpoint_summary['succeeded'],
        checkpoint_summary['pending'],
        checkpoint_summary['running'],
        checkpoint_summary['failed'],
        checkpoint_summary['skipped'],
    )

    phase_results[sync_metadata.STAGE_WORKLOAD_EVIDENCE] = (
        _run_checkpointed_internal_enrichment_phase(
            run_logger=run_logger,
            timings=timings,
            phase_name=sync_metadata.STAGE_WORKLOAD_EVIDENCE,
            jobs=checkpoint_jobs.get(sync_metadata.STAGE_WORKLOAD_EVIDENCE, []),
            sync_run_id=sync_run_id,
            operation_for_job=lambda checkpoint_job: _safe_build_workload_recovery_evidence_stage(
                [checkpoint_job.product_date],
                sync_run_id=sync_run_id,
                source=source,
                job_name=job_name,
                run_logger=run_logger,
            ),
        )
    )
    phase_results[sync_metadata.STAGE_COMPOSED_READS] = (
        _run_checkpointed_internal_enrichment_phase(
            run_logger=run_logger,
            timings=timings,
            phase_name=sync_metadata.STAGE_COMPOSED_READS,
            jobs=checkpoint_jobs.get(sync_metadata.STAGE_COMPOSED_READS, []),
            sync_run_id=sync_run_id,
            operation_for_job=lambda checkpoint_job: _safe_build_composed_reads_stage(
                [checkpoint_job.product_date],
                sync_run_id=sync_run_id,
                source=source,
                job_name=job_name,
                run_logger=run_logger,
            ),
        )
    )
    phase_results[STAGE_LEGACY_READ_RECONCILIATION_AUDIT] = (
        _run_checkpointed_internal_enrichment_phase(
            run_logger=run_logger,
            timings=timings,
            phase_name=STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
            jobs=checkpoint_jobs.get(STAGE_LEGACY_READ_RECONCILIATION_AUDIT, []),
            sync_run_id=sync_run_id,
            operation_for_job=lambda checkpoint_job: _safe_run_legacy_read_reconciliation_audit_stage(
                [checkpoint_job.product_date],
                sync_run_id=sync_run_id,
                source=source,
                job_name=job_name,
                run_logger=run_logger,
            ),
        )
    )
    if include_backtest:
        phase_results[sync_metadata.STAGE_BACKTEST_REFRESH] = (
            _run_checkpointed_internal_enrichment_phase(
                run_logger=run_logger,
                timings=timings,
                phase_name=sync_metadata.STAGE_BACKTEST_REFRESH,
                jobs=checkpoint_jobs.get(sync_metadata.STAGE_BACKTEST_REFRESH, []),
                sync_run_id=sync_run_id,
                operation_for_job=lambda _checkpoint_job: _refresh_availability_backtest_phase(
                    sync_run_id,
                    status,
                    run_logger,
                ),
            )
        )

    failed_phases = [
        phase_name
        for phase_name, result in phase_results.items()
        if _internal_phase_failed(result)
    ]
    return {
        'status': (
            sync_metadata.STATUS_FAILED if failed_phases
            else sync_metadata.STATUS_SUCCESS
        ),
        'product_dates': [day.isoformat() for day in dates],
        'phase_results': phase_results,
        'failed_phases': failed_phases,
        'phase_timings': timings,
        'checkpoint_summary': sync_jobs.summary_for_product_dates(dates),
    }


def _log_daily_sync_phase_summary(run_logger, timings):
    if not timings:
        return
    summary = ', '.join(
        f"{item['phase']}={item['status']}:{item['elapsed_seconds']}s"
        for item in timings
    )
    run_logger.info(
        'Daily sync post-fatigue phase duration summary: %s.',
        summary,
    )


def complete_sync_run_with_snapshot(
    sync_run_id,
    *,
    final_status,
    publication_critical_complete=None,
    completed_at=None,
    records_processed=0,
    records_failed=0,
    new_logs_added=0,
    pitchers_updated=0,
    errors=0,
    api_calls_made=0,
    retries_used=0,
    error_message=None,
    source=sync_metadata.SOURCE_MANUAL,
    started_at=None,
    snapshot_source='sync_completion',
    job_name=sync_metadata.JOB_DAILY_SYNC,
):
    from services import dashboard_snapshot as dashboard_snapshot_service

    completed_at = completed_at or datetime.now(timezone.utc).replace(tzinfo=None)
    try:
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=final_status,
            completed_at=completed_at,
            records_processed=records_processed,
            records_failed=records_failed,
            new_logs_added=new_logs_added,
            pitchers_updated=pitchers_updated,
            errors=errors,
            api_calls_made=api_calls_made,
            retries_used=retries_used,
            error_message=error_message,
            source=source,
            started_at=started_at,
            job_name=job_name,
            stage=sync_metadata.STAGE_DASHBOARD_SNAPSHOT,
            commit=False,
            rollback_before=False,
        )
        snapshot = dashboard_snapshot_service.build_bullpen_dashboard_snapshot(
            sync_run_id=run.id if run is not None else sync_run_id,
            source=snapshot_source,
            publish=True,
            commit=False,
            raise_errors=True,
            publication_critical_complete=publication_critical_complete,
        )
        if run is not None:
            run.stage = sync_metadata.STAGE_PUBLISHED
            run.published_dashboard_snapshot_id = snapshot.id
        db.session.commit()
        # SC-03B-04: this path publishes with commit=False and owns the commit, so
        # the post-publication generation hook must be invoked here (once, after the
        # publication has durably committed). Reuses the one canonical completion
        # function; never raises, so a generation problem never affects the sync.
        dashboard_snapshot_service.run_post_commit_snapshot_publication(snapshot)
        return run, snapshot
    except Exception as exc:
        db.session.rollback()
        sync_metadata.finish_sync_run(
            sync_run_id,
            status=sync_metadata.STATUS_FAILED,
            completed_at=completed_at,
            records_processed=records_processed,
            records_failed=records_failed,
            new_logs_added=new_logs_added,
            pitchers_updated=pitchers_updated,
            errors=(errors or 0) + 1,
            api_calls_made=api_calls_made,
            retries_used=retries_used,
            error_message=str(exc),
            source=source,
            started_at=started_at,
            job_name=job_name,
            stage=sync_metadata.STAGE_FAILED,
            failed_stage=sync_metadata.STAGE_DASHBOARD_SNAPSHOT,
        )
        raise


def _prepare_canonical_public_roster_authority(
    reference_date,
    *,
    sync_run_id,
    job_name,
):
    """Prepare and qualify the canonical roster state one publication will freeze.

    Daily and postgame both use the same official roster-evidence pass for team
    assignment and roster status. The caller owns lane-specific acquisition and
    decides whether an unqualified result may continue to publication.
    """
    started = time.monotonic()
    assignment_started = time.monotonic()
    run_roster_evidence = build_run_roster_evidence()
    team_assignment = sync_team_assignments(evidence=run_roster_evidence)
    assignment_elapsed = round(time.monotonic() - assignment_started, 1)
    sync_metadata.set_sync_stage(
        sync_run_id,
        sync_metadata.STAGE_TEAM_ASSIGNMENTS,
    )
    team_assignment_records_failed = record_sync_error_details(
        'team_assignment_fetch',
        team_assignment.get('error_details'),
        sync_run_id=sync_run_id,
        job_name=job_name,
    )

    roster_started = time.monotonic()
    roster = sync_roster_statuses(
        sync_run_id=sync_run_id,
        snapshot_date=reference_date,
        evidence=run_roster_evidence,
    )
    roster_elapsed = round(time.monotonic() - roster_started, 1)
    sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_ROSTER_STATUS)

    readiness = build_public_roster_readiness(
        reference_date=reference_date,
        scope='league',
    )
    coverage = readiness.get('coverage') or {}
    exact_reference_date = (
        reference_date is not None
        and coverage.get('snapshot_date') == reference_date.isoformat()
    )
    assignment_errors = int(team_assignment.get('errors') or 0)
    roster_errors = int(roster.get('errors') or 0)
    roster_records_failed = int(roster.get('records_failed') or 0)
    roster_conflicts = int(roster.get('snapshot_conflicts') or 0)
    qualified = bool(
        exact_reference_date
        and readiness.get('claims_available') is True
        and readiness.get('counts_withheld') is False
        and coverage.get('complete') is True
        and int(coverage.get('teams_missing_count') or 0) == 0
        and assignment_errors == 0
        and roster_errors == 0
        and roster_records_failed == 0
        and roster_conflicts == 0
    )

    reason_codes = list(readiness.get('reason_codes') or [])
    if not exact_reference_date:
        reason_codes.append('roster_snapshot_reference_date_mismatch')
    if assignment_errors:
        reason_codes.append('team_assignment_preparation_incomplete')
    if roster_errors or roster_records_failed:
        reason_codes.append('roster_status_preparation_incomplete')
    if roster_conflicts:
        reason_codes.append('roster_snapshot_conflict')

    return {
        'status': 'qualified' if qualified else 'unqualified',
        'qualified': qualified,
        'reference_date': (
            reference_date.isoformat() if reference_date is not None else None
        ),
        'reason_codes': list(dict.fromkeys(reason_codes)),
        'records_failed': (
            team_assignment_records_failed + roster_records_failed
        ),
        'errors': assignment_errors + roster_errors,
        'team_assignment': team_assignment,
        'roster_status': roster,
        'readiness': readiness,
        'roster_evidence': run_roster_evidence.summary(),
        'stage_timings': {
            'team_assignments': assignment_elapsed,
            'roster_statuses': roster_elapsed,
            'total': round(time.monotonic() - started, 1),
        },
    }


def _safe_run_progressive_team_publication(game_pks, *, sync_run_id, status, run_logger):
    """Progressive per-team Team State publication for the games that fully completed
    this postgame pass. Fail-soft: gated by the Share Artifact autogeneration flag and
    fully exception-isolated so it can never break the postgame sync, and it never
    touches the league dashboard snapshot. Returns a JSON-safe accounting or None.
    """
    if not game_pks:
        return None
    try:
        from flask import current_app
        if not current_app.config.get('SHARE_ARTIFACT_AUTOGENERATION_ENABLED', False):
            run_logger.info(
                'Progressive team publication skipped for %s completed game(s): '
                'autogeneration disabled.',
                len(game_pks),
            )
            return None
    except Exception:
        return None

    from services.team_progressive_publication import publish_team_state_for_final_game

    events = []
    totals = {'games': 0, 'attempted': 0, 'accounted': 0, 'generated': 0,
              'reused': 0, 'refused': 0, 'failed': 0}
    for game_pk in game_pks:
        try:
            result = publish_team_state_for_final_game(
                game_pk, sync_run_id=sync_run_id, actor='postgame_progressive',
            )
            db.session.commit()
            events.append(result.to_dict())
            totals['games'] += 1
            totals['attempted'] += result.attempted
            totals['accounted'] += result.accounted
            totals['generated'] += result.generated
            totals['reused'] += result.reused
            totals['refused'] += result.refused
            totals['failed'] += result.failed
        except Exception as exc:  # noqa: BLE001 - progressive publication is fail-soft
            try:
                db.session.rollback()
            except Exception:
                pass
            run_logger.warning(
                'Progressive team publication failed for game_pk=%s: %s', game_pk, exc,
            )
    run_logger.info(
        'Progressive team publication complete: games=%s attempted=%s generated=%s '
        'reused=%s refused=%s failed=%s.',
        totals['games'], totals['attempted'], totals['generated'],
        totals['reused'], totals['refused'], totals['failed'],
    )
    return {'totals': totals, 'events': events}


def run_postgame_refresh(
    app,
    schedule_date: date | None = None,
    source: str = sync_metadata.SOURCE_GITHUB_ACTIONS,
    include_internal_enrichment: bool = True,
):
    """
    Lightweight completed-game refresh.

    This job sweeps the primary MLB schedule date plus a trailing lookback
    window (oldest first), finds completed games not yet marked as processed,
    fetches only those games' boxscores, and ingests pitching lines for
    tracked active pitchers. Fully-processed markers make re-sweeping old
    slates nearly free, and the lookback means a crashed overnight run
    self-heals on the next pass instead of leaving a permanent hole. An
    explicit ``schedule_date`` restricts the sweep to exactly that date
    (manual replays). It leaves the full morning sync path intact and performs
    only the canonical roster-authority preparation required for a replacement
    public snapshot; it does not perform a full-league game-log sweep.
    """
    _ensure_logs_dir()
    log_file = _STATUS_DIR / 'postgame_refresh.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s  %(levelname)-7s  %(message)s'
    ))
    run_logger = logging.getLogger('baseballos.postgame_refresh')
    if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(log_file)
               for h in run_logger.handlers):
        run_logger.addHandler(file_handler)
    run_logger.setLevel(logging.INFO)

    started_at = datetime.now(timezone.utc)
    if schedule_date is not None:
        schedule_dates = [schedule_date]
    else:
        schedule_dates = postgame_schedule_dates(started_at)
        schedule_date = schedule_dates[-1]
    sync_run_id = None
    active_stage = None
    writer_guard = None
    status = {
        'last_sync': started_at.isoformat(),
        'status': sync_metadata.STATUS_SUCCESS,
        'job_name': sync_metadata.JOB_POSTGAME_REFRESH,
        'schedule_date': schedule_date.isoformat(),
        'schedule_dates': [slate.isoformat() for slate in schedule_dates],
        'completed_games_found': 0,
        'newly_completed_games': 0,
        'games_already_processed': 0,
        'games_retryable_incomplete': 0,
        'games_failed_markers': 0,
        'games_processed': 0,
        'games_incomplete': 0,
        'games_skipped': 0,
        'new_logs_added': 0,
        'logs_corrected': 0,
        'pitchers_touched': 0,
        'pitchers_updated': 0,
        'errors': 0,
        'records_failed': 0,
        'correction_attempts_failed': 0,
        'pitcher_resolution_failures': 0,
        'postgame_retry_exhausted': 0,
        'pitchers_created': 0,
        'pitchers_reactivated': 0,
        'completed_game_contexts_upserted': 0,
        'completed_game_context_errors': 0,
        'public_state_preparation': None,
        'publication_withheld_reason': None,
        'dashboard_snapshot_id': None,
        'intelligence_snapshot': 'skipped',
        'message': '',
    }
    run_logger.info(
        '── Postgame refresh starting (schedule_dates=%s) ──',
        ','.join(slate.isoformat() for slate in schedule_dates),
    )
    refresh_started = time.perf_counter()

    try:
        with app.app_context():
            writer_guard = sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                source=source,
            )
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
                job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            )
            mlb_client.metrics.reset()
            stage_timings = {}
            status['stage_timings'] = stage_timings
            schedule_finality_records_failed = 0
            if _sync_schedule_finality_preflight_enabled():
                active_stage = sync_metadata.STAGE_SCHEDULE_FINALITY_PREFLIGHT
                preflight_started = time.monotonic()
                preflight = _refresh_postgame_schedule_finality(schedule_dates)
                stage_timings['schedule_finality_preflight'] = round(
                    time.monotonic() - preflight_started,
                    1,
                )
                status['schedule_finality_preflight'] = preflight
                schedule_finality_records_failed = sum(
                    int((item.get('summary') or {}).get('errors') or 0)
                    for item in preflight.get('results') or []
                )
                sync_metadata.set_sync_stage(
                    sync_run_id,
                    sync_metadata.STAGE_SCHEDULE_FINALITY_PREFLIGHT,
                )
                run_logger.info(
                    'Postgame schedule finality preflight completed: '
                    'status=%s slates_checked=%s slates_refreshed=%s '
                    'candidate_games=%s elapsed_ms=%s.',
                    preflight.get('status'),
                    preflight.get('slates_checked'),
                    preflight.get('slates_refreshed'),
                    preflight.get('candidate_game_count'),
                    preflight.get('elapsed_ms'),
                )
            else:
                status['schedule_finality_preflight'] = {
                    'status': 'skipped',
                    'reason': 'disabled',
                }
            status['records_failed'] += schedule_finality_records_failed
            status['errors'] += schedule_finality_records_failed
            active_stage = sync_metadata.STAGE_LOG_INGESTION

            completed_games = []
            slate_by_game_pk = {}
            for slate_date in schedule_dates:
                for game in completed_games_for_postgame_refresh(slate_date):
                    game_pk = _game_pk(game)
                    if game_pk in slate_by_game_pk:
                        continue
                    slate_by_game_pk[game_pk] = slate_date
                    completed_games.append(game)
            unprocessed_games, marker_counts = _unprocessed_completed_games(completed_games)
            status['completed_games_found'] = len(completed_games)
            status['newly_completed_games'] = len(unprocessed_games)
            status['games_already_processed'] = marker_counts['fully_processed']
            status['games_retryable_incomplete'] = marker_counts['retryable_incomplete']
            status['games_failed_markers'] = marker_counts['failed']
            run_logger.info(
                'Found %s completed game(s) across %s slate date(s); '
                '%s fully processed, %s retryable incomplete, %s failed, '
                '%s pending.',
                len(completed_games),
                len(schedule_dates),
                marker_counts['fully_processed'],
                marker_counts['retryable_incomplete'],
                marker_counts['failed'],
                len(unprocessed_games),
            )

            pbp_foundation_attempted_game_pks = set()
            changed_slate_dates = set()
            # Games that reached full box-score/ledger completion this pass. Each is a
            # candidate for progressive per-team Team State publication (team-scoped;
            # it does NOT wait for the whole league slate to be final).
            progressive_final_game_pks = set()
            for game in unprocessed_games:
                game_pk = _game_pk(game)
                game_slate_date = slate_by_game_pk.get(game_pk, schedule_date)
                game_started = time.perf_counter()
                outcome = 'processed'
                try:
                    result = process_completed_game_for_postgame_refresh(
                        game,
                        schedule_date=game_slate_date,
                        sync_run_id=sync_run_id,
                    )
                    db.session.commit()
                    if result.get('skipped'):
                        status['games_skipped'] += 1
                        outcome = 'skipped'
                        continue
                    fully_processed = (
                        result['processing_status']
                        == POSTGAME_MARKER_STATUS_FULLY_PROCESSED
                    )
                    if fully_processed:
                        status['games_processed'] += 1
                        progressive_final_game_pks.add(game_pk)
                    else:
                        status['games_incomplete'] += 1
                        if result['processing_status'] == POSTGAME_MARKER_STATUS_FAILED:
                            status['games_failed_markers'] += 1
                        outcome = result['processing_status']
                    if result['logs_added'] or result['logs_corrected']:
                        changed_slate_dates.add(game_slate_date)
                    status['new_logs_added'] += result['logs_added']
                    status['logs_corrected'] += result['logs_corrected']
                    status['correction_attempts_failed'] += result['correction_attempts_failed']
                    status['pitcher_resolution_failures'] += result['pitcher_resolution_failures']
                    if result['retry_exhausted']:
                        status['postgame_retry_exhausted'] += 1
                    status['pitchers_created'] += result['pitchers_created']
                    status['pitchers_reactivated'] += result['pitchers_reactivated']
                    game_failure_count = (
                        result['correction_attempts_failed']
                        + result['pitcher_resolution_failures']
                    )
                    if fully_processed:
                        status['records_failed'] += game_failure_count
                    else:
                        status['records_failed'] += max(1, game_failure_count)
                    status['pitchers_touched'] += result['pitchers_touched']
                    run_logger.info(
                        'Postgame attempt for game %s: status=%s reason=%s '
                        'attempt=%s lines=%s; %s inserted, %s corrected, '
                        '%s unsafe correction(s), %s pitcher resolution failure(s), '
                        '%s pitcher(s).',
                        game_pk,
                        result['processing_status'],
                        result['incomplete_reason'],
                        result['attempt_count'],
                        result['pitching_lines_seen'],
                        result['logs_added'],
                        result['logs_corrected'],
                        result['correction_attempts_failed'],
                        result['pitcher_resolution_failures'],
                        result['pitchers_touched'],
                    )
                    _safe_recompute_team_game_pitching_splits(
                        game,
                        schedule_date=game_slate_date,
                        sync_run_id=sync_run_id,
                        run_logger=run_logger,
                    )
                    optional_inputs = _fetch_completed_game_optional_inputs(game_pk)
                    _safe_process_final_play_by_play_foundation(
                        game,
                        boxscore=result.get('boxscore'),
                        schedule_date=game_slate_date,
                        play_by_play=optional_inputs['play_by_play'],
                        play_by_play_error=optional_inputs['play_by_play_error'],
                        sync_run_id=sync_run_id,
                        run_logger=run_logger,
                    )
                    pbp_foundation_attempted_game_pks.add(game_pk)
                    # Derive completed-game context in its own transaction so a
                    # context failure can never undo the committed game logs.
                    _safe_generate_completed_game_context(
                        game,
                        boxscore=result.get('boxscore'),
                        schedule_date=game_slate_date,
                        linescore=optional_inputs['linescore'],
                        play_by_play=optional_inputs['play_by_play'],
                        sync_run_id=sync_run_id,
                        status=status,
                        run_logger=run_logger,
                    )
                except Exception as exc:
                    outcome = 'failed'
                    db.session.rollback()
                    status['errors'] += 1
                    status['records_failed'] += 1
                    dead_letter.record_failure(
                        POSTGAME_GAME_FAILURE_ENTITY_TYPE,
                        exc,
                        entity_ref=game_pk,
                        payload={
                            'game_pk': game_pk,
                            'schedule_date': game_slate_date.isoformat(),
                            'status': game.get('status') if isinstance(game, dict) else None,
                        },
                        sync_run_id=sync_run_id,
                        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    )
                    db.session.commit()
                    run_logger.warning('Postgame processing failed for game_pk=%s: %s', game_pk, exc)
                finally:
                    run_logger.info(
                        'postgame_refresh game_done game_pk=%s outcome=%s elapsed_ms=%s',
                        game_pk,
                        outcome,
                        round((time.perf_counter() - game_started) * 1000, 1),
                    )

            for game in _games_requiring_play_by_play_foundation(
                completed_games,
                exclude_game_pks=pbp_foundation_attempted_game_pks,
            ):
                game_pk = _game_pk(game)
                game_slate_date = slate_by_game_pk.get(game_pk, schedule_date)
                try:
                    boxscore = mlb_client.get_game_boxscore(game_pk)
                    optional_inputs = _fetch_completed_game_optional_inputs(game_pk)
                    _safe_process_final_play_by_play_foundation(
                        game,
                        boxscore=boxscore,
                        schedule_date=game_slate_date,
                        play_by_play=optional_inputs['play_by_play'],
                        play_by_play_error=optional_inputs['play_by_play_error'],
                        sync_run_id=sync_run_id,
                        run_logger=run_logger,
                    )
                    pbp_foundation_attempted_game_pks.add(game_pk)
                except Exception as exc:  # noqa: BLE001 - optional retry, fail-soft
                    db.session.rollback()
                    dead_letter.record_failure(
                        FINAL_PBP_FETCH_ENTITY_TYPE,
                        exc,
                        entity_ref=game_pk,
                        payload={
                            'game_pk': game_pk,
                            'schedule_date': game_slate_date.isoformat(),
                            'phase': 'play_by_play_retry',
                        },
                        sync_run_id=sync_run_id,
                        job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    )
                    db.session.commit()
                    run_logger.warning(
                        'Final play-by-play retry failed for game_pk=%s: %s',
                        game_pk,
                        exc,
                    )

            # Progressive per-team publication runs AFTER fatigue recalculation
            # commits (see below), so each team's Team State is generated only once its
            # required workload/readiness evidence for the completed game is current and
            # committed. The newly-completed game_pks collected above are handed off to
            # that later, post-readiness point.

            run_logger.info(
                'Postgame ingestion complete for %s: processed=%s skipped=%s '
                'incomplete=%s failed=%s contexts=%s logs_added=%s logs_corrected=%s '
                'pitchers_created=%s pitchers_reactivated=%s.',
                ','.join(slate.isoformat() for slate in schedule_dates),
                status['games_processed'],
                status['games_skipped'],
                status['games_incomplete'],
                status['records_failed'],
                status['completed_game_contexts_upserted'],
                status['new_logs_added'],
                status['logs_corrected'],
                status['pitchers_created'],
                status['pitchers_reactivated'],
            )

            # ── Game-driven appearance lane ─────────────────────────────────
            # The postgame cycle's single integration point: the same service
            # call the daily sync makes, on the same canonical planner and
            # writer, exactly once per cycle. It is not a second ingestion
            # command and it is not a second comparator.
            #
            # It runs AFTER the legacy sweep, not before it. The sweep is this
            # cycle's writer, and it commits per game; a lane placed ahead of
            # it would project every one of those rows as an insert it is about
            # to perform anyway, which is noise, not evidence. Reading after
            # the writer asks the question worth asking overnight: given what
            # the current path just wrote, what would the game-driven lane do?
            # (The daily sync's ordering is different for a real reason — there
            # the lane is the one that becomes authoritative and the pitcher
            # loop is demoted behind it.)
            #
            # write_modes_supported=False is the two-writer guard. The postgame
            # sweep has no skip_game_pks equivalent, so nothing could stop it
            # and a writing game-driven lane from touching the same canonical
            # rows. Until that mechanism exists a writing mode is refused here,
            # before any MLB request and before any write.
            postgame_runtime_budget = _postgame_refresh_runtime_budget()
            status['runtime_budget'] = postgame_runtime_budget
            # Exactly this cycle's governed, fully-written games — not the
            # planner's rolling correction horizon. Resolved from state the
            # cycle already holds, so it costs no MLB request and no second
            # planning pass, and handed over through the exclusive-scope
            # mechanism that refuses before any fetch if the plan is not the
            # exact requested set.
            postgame_scope = _postgame_game_driven_scope(
                completed_games, slate_by_game_pk,
            )
            status['game_driven_scope'] = postgame_scope
            game_lane = _run_game_driven_ingestion_stage(
                reference_date=schedule_date,
                runtime_budget=postgame_runtime_budget,
                sync_run_id=sync_run_id,
                status=status,
                stage_timings=stage_timings,
                run_logger=run_logger,
                job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                write_modes_supported=False,
                only_game_pks=postgame_scope['requested_game_pks'],
                scope_summary=postgame_scope,
            )
            # Recorded, never consulted. The postgame publication gate is
            # unchanged and stays with the established authority; this lane is
            # observation only until its own reviewed activation.
            status['game_driven_lane_authoritative'] = bool(
                game_lane['authoritative']
            )

            changed_log_count = status['new_logs_added'] + status['logs_corrected']
            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_LOG_INGESTION)
            if changed_log_count > 0:
                active_stage = sync_metadata.STAGE_FATIGUE_RECALCULATION
                fatigue_started = time.perf_counter()
                run_logger.info(
                    'Fatigue recalculation starting after postgame ingestion.'
                )
                pitchers_updated = recalculate_all_fatigue()
                sync_metadata.set_sync_stage(
                    sync_run_id,
                    sync_metadata.STAGE_FATIGUE_RECALCULATION,
                )
                status['pitchers_updated'] = pitchers_updated
                run_logger.info(
                    'Fatigue recalculation complete: pitchers_updated=%s '
                    'elapsed_ms=%s.',
                    pitchers_updated,
                    round((time.perf_counter() - fatigue_started) * 1000, 1),
                )

                candidate_metadata = sync_metadata.collect_data_metadata()
                candidate_reference_date = (
                    product_availability_reference_date_from_metadata(
                        candidate_metadata
                    )
                )
                candidate_data_through = (
                    candidate_reference_date - timedelta(days=1)
                    if candidate_reference_date is not None
                    else None
                )
                status['candidate_data_through'] = (
                    candidate_data_through.isoformat()
                    if candidate_data_through is not None
                    else None
                )
                status['candidate_availability_reference_date'] = (
                    candidate_reference_date.isoformat()
                    if candidate_reference_date is not None
                    else None
                )
                if candidate_reference_date is None:
                    public_state_preparation = {
                        'status': 'unqualified',
                        'qualified': False,
                        'reference_date': None,
                        'reason_codes': [
                            'availability_reference_date_unavailable'
                        ],
                        'records_failed': 0,
                        'errors': 0,
                    }
                else:
                    active_stage = sync_metadata.STAGE_TEAM_ASSIGNMENTS
                    try:
                        public_state_preparation = (
                            _prepare_canonical_public_roster_authority(
                                candidate_reference_date,
                                sync_run_id=sync_run_id,
                                job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                            )
                        )
                    except Exception as exc:
                        status['public_state_preparation'] = {
                            'status': 'failed',
                            'qualified': False,
                            'reference_date': candidate_reference_date.isoformat(),
                            'reason_codes': [
                                POSTGAME_ROSTER_AUTHORITY_PREPARATION_INCOMPLETE
                            ],
                            'error': str(exc),
                        }
                        status['publication_withheld_reason'] = (
                            POSTGAME_ROSTER_AUTHORITY_PREPARATION_INCOMPLETE
                        )
                        raise RuntimeError(
                            POSTGAME_ROSTER_AUTHORITY_PREPARATION_INCOMPLETE
                        ) from exc
                    active_stage = sync_metadata.STAGE_ROSTER_STATUS

                status['public_state_preparation'] = public_state_preparation
                status['records_failed'] += int(
                    public_state_preparation.get('records_failed') or 0
                )
                status['errors'] += int(
                    public_state_preparation.get('errors') or 0
                )
                run_logger.info(
                    'Postgame public roster authority preparation completed: '
                    'data_through=%s availability_reference_date=%s '
                    'status=%s reasons=%s.',
                    status['candidate_data_through'],
                    status['candidate_availability_reference_date'],
                    public_state_preparation.get('status'),
                    ','.join(public_state_preparation.get('reason_codes') or [])
                    or 'none',
                )
            else:
                run_logger.info(
                    'Fatigue recalculation skipped: no postgame logs changed.'
                )

            # Progressive per-team publication: each game that reached full completion
            # this pass may publish its two teams' Team State artifacts independently,
            # WITHOUT waiting for the whole league slate to be final. It runs HERE —
            # after fatigue recalculation has recalculated and COMMITTED the completed
            # game's workload evidence — so the canonical Team Operations readiness the
            # generation path reads is current and visible (fatigue rows updated,
            # committed, in this session). It reuses the canonical single-team path and
            # is fully fail-closed and idempotent; a failure here never breaks the
            # postgame sync and never publishes or mutates the league dashboard
            # snapshot. If fatigue recalculation itself raised, control never reaches
            # here (the run fails closed) and no team is published on partial evidence.
            progressive_result = _safe_run_progressive_team_publication(
                sorted(progressive_final_game_pks),
                sync_run_id=sync_run_id,
                status=status,
                run_logger=run_logger,
            )
            if progressive_result is not None:
                status['progressive_team_publication'] = progressive_result

            if (
                changed_log_count > 0
                and not (status.get('public_state_preparation') or {}).get(
                    'qualified'
                )
            ):
                status['status'] = sync_metadata.STATUS_PARTIAL
                status['publication_withheld_reason'] = (
                    POSTGAME_ROSTER_AUTHORITY_PREPARATION_INCOMPLETE
                )
                status['message'] = (
                    'Postgame workload was refreshed, but the replacement '
                    'Dashboard snapshot was withheld because exact-date public '
                    'roster authority was not qualified.'
                )
            elif status['records_failed']:
                status['status'] = (
                    sync_metadata.STATUS_FAILED
                    if status['games_processed'] == 0 and status['newly_completed_games'] > 0
                    else sync_metadata.STATUS_PARTIAL
                )
                status['message'] = (
                    f"{status['records_failed']} postgame record(s) incomplete or failed."
                )
            elif changed_log_count > 0:
                status['message'] = 'Updated after completed games.'
            elif status['newly_completed_games'] == 0:
                status['message'] = 'No newly completed games to process.'
            else:
                status['message'] = 'Completed games were checked; no tracked pitcher workload changed.'

            api_metrics = mlb_client.metrics.snapshot()
            if (
                changed_log_count > 0
                and (status.get('public_state_preparation') or {}).get(
                    'qualified'
                ) is True
            ):
                active_stage = sync_metadata.STAGE_DASHBOARD_SNAPSHOT
                completed_run, snapshot = complete_sync_run_with_snapshot(
                    sync_run_id,
                    final_status=status['status'],
                    records_processed=changed_log_count,
                    records_failed=status['records_failed'],
                    new_logs_added=status['new_logs_added'],
                    pitchers_updated=status['pitchers_updated'],
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=status['message'] or None,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    snapshot_source='postgame_refresh',
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                )
                status['dashboard_snapshot_id'] = snapshot.id

                # Refresh the Intelligence Surface homepage cache from the freshly
                # derived contexts before internal-only enrichment. Best-effort:
                # it never blocks or fails the refresh.
                if status['completed_game_contexts_upserted'] > 0:
                    _safe_generate_intelligence_surface_snapshot(
                        schedule_date, status=status, run_logger=run_logger)

                if include_internal_enrichment:
                    enrichment_slate_dates = (
                        sorted(changed_slate_dates) or [schedule_date]
                    )
                    active_stage = sync_metadata.STAGE_WORKLOAD_EVIDENCE
                    _run_post_publish_internal_postgame_phase(
                        run_logger,
                        sync_metadata.STAGE_WORKLOAD_EVIDENCE,
                        lambda: _safe_build_workload_recovery_evidence_stage(
                            enrichment_slate_dates,
                            sync_run_id=sync_run_id,
                            source='postgame_refresh',
                            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                            run_logger=run_logger,
                        ),
                    )
                    active_stage = sync_metadata.STAGE_COMPOSED_READS
                    _run_post_publish_internal_postgame_phase(
                        run_logger,
                        sync_metadata.STAGE_COMPOSED_READS,
                        lambda: _safe_build_composed_reads_stage(
                            enrichment_slate_dates,
                            sync_run_id=sync_run_id,
                            source='postgame_refresh',
                            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                            run_logger=run_logger,
                        ),
                    )
                    active_stage = STAGE_LEGACY_READ_RECONCILIATION_AUDIT
                    _run_post_publish_internal_postgame_phase(
                        run_logger,
                        STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
                        lambda: _safe_run_legacy_read_reconciliation_audit_stage(
                            enrichment_slate_dates,
                            sync_run_id=sync_run_id,
                            source='postgame_refresh',
                            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                            run_logger=run_logger,
                        ),
                    )
                    _restore_completed_sync_publish_stage(
                        sync_run_id,
                        run_logger=run_logger,
                    )
                else:
                    status['internal_enrichment'] = 'skipped_public_only'
            elif changed_log_count > 0:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=status['status'],
                    records_processed=changed_log_count,
                    records_failed=status['records_failed'],
                    new_logs_added=status['new_logs_added'],
                    pitchers_updated=status['pitchers_updated'],
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=status['message'],
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    stage=sync_metadata.STAGE_ROSTER_STATUS,
                )
            else:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=status['status'],
                    records_processed=0,
                    records_failed=status['records_failed'],
                    new_logs_added=0,
                    pitchers_updated=0,
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=status['message'] or None,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    stage=(
                        sync_metadata.STAGE_FAILED
                        if status['status'] == sync_metadata.STATUS_FAILED
                        else sync_metadata.STAGE_LOG_INGESTION
                    ),
                )
    except sync_metadata.SyncWriterConflict as conflict:
        status.update(sync_metadata.sync_writer_conflict_payload(conflict))
        status['job_name'] = sync_metadata.JOB_POSTGAME_REFRESH
        run_logger.warning('Postgame refresh blocked: %s', conflict.reason)
    except Exception as e:
        status['status'] = sync_metadata.STATUS_FAILED
        status['message'] = str(e)
        status['errors'] = max(1, status.get('errors', 0))
        run_logger.exception('Postgame refresh failed: %s', e)
        try:
            api_metrics = mlb_client.metrics.snapshot()
        except Exception:
            api_metrics = {'api_calls': 0, 'retries': 0}
        with app.app_context():
            existing_run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
            if existing_run is None or existing_run.status != sync_metadata.STATUS_FAILED:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    errors=status['errors'],
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=str(e),
                    job_name=sync_metadata.JOB_POSTGAME_REFRESH,
                    stage=sync_metadata.STAGE_FAILED,
                    failed_stage=active_stage or (
                        existing_run.stage if existing_run is not None else None
                    ),
                )

    if writer_guard is not None:
        writer_guard.release()

    status['finished_at'] = datetime.now(timezone.utc).isoformat()
    status['elapsed_ms'] = round((time.perf_counter() - refresh_started) * 1000, 1)
    write_status(status)
    run_logger.info(
        'postgame_refresh completed status=%s games_found=%s already_processed=%s '
        'processed=%s skipped=%s failed=%s logs_corrected=%s contexts=%s '
        'snapshot=%s elapsed_ms=%s',
        status['status'],
        status['completed_games_found'],
        status['games_already_processed'],
        status['games_processed'],
        status['games_skipped'],
        status['records_failed'],
        status['logs_corrected'],
        status['completed_game_contexts_upserted'],
        status['intelligence_snapshot'],
        status['elapsed_ms'],
    )
    run_logger.info('── Postgame refresh finished: %s ──', status['status'])
    run_logger.removeHandler(file_handler)
    file_handler.close()
    return status


def run_daily_sync(
    app,
    days_back: int = 7,
    source: str = sync_metadata.SOURCE_SCHEDULED,
    include_internal_enrichment: bool = True,
):
    """
    Full daily refresh — pulls new logs, recalculates fatigue using each
    pitcher's last game date, and records durable sync_runs metadata for
    /api/bullpen/sync/status.

    Safe to call repeatedly. Gracefully handles the offseason (when MLB
    returns no recent games) by writing a status of 'no_games' instead
    of raising.

    Meant to run inside an app context — we push one here if needed.
    """
    _ensure_logs_dir()
    log_file = _STATUS_DIR / 'daily_sync.log'

    # File-based logger so the schedule leaves an audit trail even if the
    # process is headless (APScheduler background thread).
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s  %(levelname)-7s  %(message)s'
    ))
    run_logger = logging.getLogger('baseballos.daily_sync')
    # Avoid stacking handlers across repeated runs.
    if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(log_file)
               for h in run_logger.handlers):
        run_logger.addHandler(file_handler)
    run_logger.setLevel(logging.INFO)

    started_at = datetime.now(timezone.utc)
    sync_started = time.monotonic()
    product_day = resolve_product_day(started_at)
    sync_run_id = None
    active_stage = None
    writer_guard = None
    post_fatigue_phase_timings = []
    post_fatigue_instrumentation_started = False
    run_logger.info('── Daily sync starting (days_back=%s) ──', days_back)

    status = {
        'last_sync':        started_at.isoformat(),
        'status':           sync_metadata.STATUS_SUCCESS,
        'pitchers_updated': 0,
        'new_logs_added':   0,
        'logs_corrected':   0,
        'errors':           0,
        'message':          '',
    }
    if product_day.limitations:
        status['limitations'] = list(product_day.limitations)

    try:
        with app.app_context():
            writer_guard = sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_DAILY_SYNC,
                source=source,
            )
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
            )
            # Fresh API metrics for this run so api_calls_made / retries_used
            # reflect only this sync's activity.
            mlb_client.metrics.reset()
            stage_timings = {}
            status['stage_timings'] = stage_timings
            stage_started = time.monotonic()
            active_stage = sync_metadata.STAGE_TEAM_ASSIGNMENTS
            # One run-scoped pass over the official roster feeds. Team
            # assignment reads it first, roster status reuses the same fresh
            # evidence below instead of fetching every roster view a second
            # time. Nothing is fetched until a consumer asks for it, and a
            # failed view stays a failure for both consumers.
            roster_preparation = _prepare_canonical_public_roster_authority(
                product_day.calendar_date,
                sync_run_id=sync_run_id,
                job_name=sync_metadata.JOB_DAILY_SYNC,
            )
            team_assignment = roster_preparation['team_assignment']
            roster = roster_preparation['roster_status']
            run_roster_evidence_summary = roster_preparation['roster_evidence']
            team_assignment_records_failed = (
                roster_preparation['records_failed']
                - int(roster.get('records_failed') or 0)
            )
            roster_records_failed = int(roster.get('records_failed') or 0)
            stage_timings['team_assignments'] = roster_preparation[
                'stage_timings'
            ]['team_assignments']
            stage_timings['roster_statuses'] = roster_preparation[
                'stage_timings'
            ]['roster_statuses']
            run_logger.info(
                'Refreshed team assignment for %s pitchers (%s changed, %s reassigned, %s no org, %s unknown, %s errors)',
                team_assignment['pitchers_refreshed'],
                team_assignment['pitchers_changed'],
                team_assignment['reassigned_count'],
                team_assignment['no_organization_count'],
                team_assignment['unknown_count'],
                team_assignment['errors'],
            )
            active_stage = sync_metadata.STAGE_ROSTER_STATUS
            run_logger.info(
                'Refreshed roster status for %s pitchers (%s changed, %s created, '
                '%s corrected, %s unchanged, %s unknown, %s errors)',
                roster['pitchers_refreshed'],
                roster['pitchers_changed'],
                roster.get('snapshots_created', 0),
                roster.get('snapshots_corrected', 0),
                roster.get('snapshots_unchanged', 0),
                roster['unknown_count'],
                roster['errors'],
            )
            run_logger.info(
                'Roster evidence: %s teams x %s roster types = %s roster requests '
                '(%s fetch failures) reused by %s',
                run_roster_evidence_summary['teams_fetched'],
                len(run_roster_evidence_summary['roster_types_fetched']),
                run_roster_evidence_summary['roster_requests'],
                run_roster_evidence_summary['fetch_failures'],
                ', '.join(run_roster_evidence_summary['consumers']) or 'no consumers',
            )
            active_stage = sync_metadata.STAGE_TRANSACTIONS
            stage_started = time.monotonic()
            transactions = sync_transactions(
                sync_run_id=sync_run_id,
                end_date=product_day.calendar_date,
            )
            stage_timings['transactions'] = round(time.monotonic() - stage_started, 1)
            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_TRANSACTIONS)
            transaction_records_failed = transactions.get('records_failed', 0)
            run_logger.info(
                'Refreshed player transactions for %s row(s) '
                '(%s stored, %s unknown types, %s errors)',
                transactions['records_fetched'],
                transactions['records_stored'],
                transactions['unknown_type_count'],
                transactions['errors'],
            )
            schedule_finality_records_failed = 0
            slate_schedule_records_failed = 0
            if _sync_schedule_finality_preflight_enabled():
                active_stage = sync_metadata.STAGE_SCHEDULE_FINALITY_PREFLIGHT
                stage_started = time.monotonic()
                finality_preflight = _refresh_daily_schedule_finality_window(
                    product_day.calendar_date,
                    days_back,
                )
                stage_timings['schedule_finality_preflight'] = round(
                    time.monotonic() - stage_started,
                    1,
                )
                status['schedule_finality_preflight'] = finality_preflight
                schedule_finality_records_failed = int(
                    (finality_preflight.get('summary') or {}).get('errors') or 0
                )
                sync_metadata.set_sync_stage(
                    sync_run_id,
                    sync_metadata.STAGE_SCHEDULE_FINALITY_PREFLIGHT,
                )
                run_logger.info(
                    'Daily schedule finality preflight completed: status=%s '
                    'window=%s..%s games_seen=%s rows_created=%s '
                    'rows_updated=%s errors=%s elapsed_ms=%s.',
                    finality_preflight.get('status'),
                    finality_preflight.get('start_date'),
                    finality_preflight.get('end_date'),
                    (finality_preflight.get('summary') or {}).get('games_seen'),
                    (finality_preflight.get('summary') or {}).get('rows_created'),
                    (finality_preflight.get('summary') or {}).get('rows_updated'),
                    (finality_preflight.get('summary') or {}).get('errors'),
                    finality_preflight.get('elapsed_ms'),
                )
                slate_schedule = _refresh_daily_slate_schedule_window(
                    product_day.calendar_date
                )
                status['slate_schedule_refresh'] = slate_schedule
                slate_schedule_records_failed = int(
                    (slate_schedule.get('summary') or {}).get('errors') or 0
                )
                run_logger.info(
                    'Daily slate schedule refresh completed: status=%s '
                    'window=%s..%s games_seen=%s slate_created=%s '
                    'slate_updated=%s errors=%s elapsed_ms=%s.',
                    slate_schedule.get('status'),
                    slate_schedule.get('start_date'),
                    slate_schedule.get('end_date'),
                    (slate_schedule.get('summary') or {}).get('games_seen'),
                    (slate_schedule.get('summary') or {}).get('slate_games_created'),
                    (slate_schedule.get('summary') or {}).get('slate_games_updated'),
                    (slate_schedule.get('summary') or {}).get('errors'),
                    slate_schedule.get('elapsed_ms'),
                )
            else:
                status['schedule_finality_preflight'] = {
                    'status': 'skipped',
                    'reason': 'disabled',
                }
                status['slate_schedule_refresh'] = {
                    'status': 'skipped',
                    'reason': 'disabled',
                }
            active_stage = sync_metadata.STAGE_LOG_INGESTION
            runtime_budget = _daily_sync_runtime_budget(sync_started)
            status['runtime_budget'] = runtime_budget
            run_logger.info(
                'Daily sync runtime budget: total=%s stage_cap=%s reserve=%s '
                'elapsed_before_ingestion=%s remaining_total=%s '
                'derived_ingestion_budget=%s.',
                runtime_budget.get('total_budget_seconds'),
                runtime_budget.get('stage_budget_cap_seconds'),
                runtime_budget.get('final_phase_reserve_seconds'),
                runtime_budget.get('elapsed_before_ingestion_seconds'),
                runtime_budget.get('remaining_total_seconds'),
                runtime_budget.get('ingestion_budget_seconds'),
            )
            # Foundation 3C: the publication-critical appearance lane is
            # game-driven. It runs FIRST and, once authoritative, owns the
            # critical budget; the full-season pitcher loop below is demoted to
            # governed best-effort repair inside whatever budget remains.
            game_lane = _run_game_driven_ingestion_stage(
                reference_date=product_day.calendar_date,
                runtime_budget=runtime_budget,
                sync_run_id=sync_run_id,
                status=status,
                stage_timings=stage_timings,
                run_logger=run_logger,
            )
            game_lane_authoritative = bool(game_lane['authoritative'])

            # OPS-002: name the five quantities separately, immediately before
            # the legacy writer starts. The last one is what actually decides
            # whether publication-critical work can complete, and it had no
            # operator-facing field until now.
            ingestion_budget_breakdown = _daily_ingestion_budget_breakdown(
                runtime_budget, game_lane,
            )
            status['ingestion_budget_breakdown'] = ingestion_budget_breakdown
            run_logger.info(
                'Daily ingestion budget breakdown: configured_cap=%s '
                'combined_pool=%s shadow_mode=%s shadow_allocation=%s '
                'shadow_elapsed=%s legacy_gamelog_budget=%s.',
                ingestion_budget_breakdown['configured_ingestion_cap_seconds'],
                ingestion_budget_breakdown['combined_ingestion_pool_seconds'],
                game_lane.get('mode'),
                ingestion_budget_breakdown[
                    'shadow_lane_configured_allocation_seconds'
                ],
                ingestion_budget_breakdown['shadow_lane_actual_elapsed_seconds'],
                ingestion_budget_breakdown['legacy_gamelog_budget_seconds'],
            )

            stage_started = time.monotonic()
            pull = sync_recent_logs(
                days_back=days_back,
                reference_date=product_day.calendar_date,
                sync_run_id=sync_run_id,
                time_budget_seconds=game_lane['remaining_ingestion_budget_seconds'],
                # Explicit conflict prevention: never let the demoted loop
                # re-write a game the authoritative lane already reconciled in
                # this run. Two writers never touch the same canonical rows.
                skip_game_pks=(
                    game_lane['completed_game_pks'] if game_lane_authoritative else ()
                ),
                best_effort_only=game_lane_authoritative,
            )
            stage_timings['log_ingestion'] = round(time.monotonic() - stage_started, 1)
            stage_timings['log_ingestion_fetch'] = pull.get('fetch_seconds')
            stage_timings['log_ingestion_process'] = pull.get('process_seconds')
            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_LOG_INGESTION)
            logs_corrected = pull.get('logs_corrected', 0)
            correction_attempts_failed = pull.get('correction_attempts_failed', 0)
            run_logger.info(
                'Pulled %s new logs, corrected %s logs, %s unchanged '
                '(touched %s of %s pitchers, %s errors, %s dead-lettered, '
                'splits_seen=%s skipped=%s unresolved_finality=%s '
                'lane_health=%s elapsed_s=%s fetch_s=%s process_s=%s '
                'budget_exhausted_pitchers=%s)',
                pull['new_logs_added'], logs_corrected,
                pull.get('logs_unchanged', 0),
                pull['pitchers_touched'],
                pull.get('pitchers_total', 0),
                pull['errors'],
                pull['records_failed'],
                pull.get('splits_seen', 0),
                pull.get('splits_skipped', {}),
                pull.get('unresolved_finality', 0),
                pull.get('lane_health', 'unknown'),
                pull.get('elapsed_seconds'),
                pull.get('fetch_seconds'),
                pull.get('process_seconds'),
                pull.get('budget_exhausted_pitchers', 0),
            )
            # ── Daily realization proof ─────────────────────────────────────
            # The game-driven lane ran BEFORE this writer, so its projection
            # legitimately contains inserts and updates. Those are projected
            # reconciliation actions, never shadow writes. Now that the writer
            # has finished, ask the only question that means anything here: did
            # it actually put the canonical rows into the projected state?
            #
            # Read-only, no MLB call, no second planning pass — it consumes the
            # plan the lane already produced.
            _attach_daily_realization(
                game_lane=game_lane,
                status=status,
                stage_timings=stage_timings,
                run_logger=run_logger,
            )

            records_failed = (
                pull['records_failed']
                + team_assignment_records_failed
                + roster_records_failed
                + transaction_records_failed
                + schedule_finality_records_failed
                + slate_schedule_records_failed
            )
            status['new_logs_added'] = pull['new_logs_added']
            status['logs_corrected'] = logs_corrected
            status['logs_unchanged'] = pull.get('logs_unchanged', 0)
            status['records_failed'] = records_failed
            status['correction_attempts_failed'] = correction_attempts_failed
            status['unresolved_finality'] = pull.get('unresolved_finality', 0)
            status['splits_seen'] = pull.get('splits_seen', 0)
            status['splits_skipped'] = pull.get('splits_skipped', {})
            status['game_log_lane_health'] = pull.get('lane_health', 'unknown')
            status['budget_exhausted_pitchers'] = pull.get('budget_exhausted_pitchers', 0)
            # Governed box-score fallback accounting. Surfaced on every run, so
            # "the fallback wrote nothing today" and "the fallback is not
            # reported" can never look the same in an artifact.
            for _key, _zero in gamelog_source_authority.empty_summary().items():
                status[_key] = pull.get(_key, _zero)
            run_logger.info(
                'Box-score fallback: eligible=%s applied=%s corrected=%s '
                'inserted=%s already_matching=%s refused=%s fetches=%s '
                'refusals=%s',
                status['boxscore_fallback_eligible_rows'],
                status['boxscore_fallback_applied_rows'],
                status['boxscore_fallback_corrected_rows'],
                status['boxscore_fallback_inserted_rows'],
                status['boxscore_fallback_unchanged_rows'],
                status['boxscore_fallback_refused_rows'],
                status['boxscore_fallback_fetches'],
                status['boxscore_fallback_refusal_reasons'],
            )
            status['errors'] = (
                pull['errors']
                + roster['errors']
                + team_assignment['errors']
                + transactions['errors']
                + schedule_finality_records_failed
                + slate_schedule_records_failed
            )
            status['team_assignments_refreshed'] = team_assignment['pitchers_refreshed']
            status['team_assignments_changed'] = team_assignment['pitchers_changed']
            status['team_assignments_reassigned'] = team_assignment['reassigned_count']
            status['team_assignment_no_organization'] = team_assignment['no_organization_count']
            status['team_assignment_unknown'] = team_assignment['unknown_count']
            status['roster_statuses_refreshed'] = roster['pitchers_refreshed']
            status['roster_statuses_changed'] = roster['pitchers_changed']
            status['roster_status_unknown'] = roster['unknown_count']

            if pull['new_logs_added'] == 0 and pull['pitchers_touched'] == 0:
                # Nothing to score against that's new — treat as offseason if
                # we also have no recent logs anywhere in the DB window.
                recent_cutoff = product_day.calendar_date - timedelta(days=days_back)
                recent_any = GameLog.query.filter(
                    GameLog.game_date >= recent_cutoff
                ).first()
                if recent_any is None:
                    status['message'] = 'No games found — offseason skip.'
                    run_logger.info('No games found — offseason skip.')

            active_stage = sync_metadata.STAGE_FATIGUE_RECALCULATION
            stage_started = time.monotonic()
            pitchers_updated = recalculate_all_fatigue()
            stage_timings['fatigue'] = round(time.monotonic() - stage_started, 1)
            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_FATIGUE_RECALCULATION)
            status['pitchers_updated'] = pitchers_updated
            run_logger.info('Recalculated fatigue for %s pitchers', pitchers_updated)
            api_summary = mlb_client.metrics.snapshot()
            status['api_calls_by_endpoint'] = api_summary.get('by_endpoint', {})
            run_logger.info(
                'Daily sync stage timings (s): %s; API calls: %s total, %s retries, by endpoint: %s',
                stage_timings,
                api_summary.get('api_calls'),
                api_summary.get('retries'),
                api_summary.get('by_endpoint'),
            )
            post_fatigue_instrumentation_started = True

            def _complete_sync_phase():
                # Partial when records were dead-lettered but the run still
                # refreshed its domains; otherwise success.
                final_status = (
                    sync_metadata.STATUS_PARTIAL if records_failed
                    else sync_metadata.STATUS_SUCCESS
                )
                status['status'] = final_status
                if records_failed and not status['message']:
                    status['message'] = (
                        f'{records_failed} record(s) dead-lettered; see sync_failures.'
                    )
                # Publication-critical completeness (founder publication-critical
                # contract). Non-game-log lane failures are treated as
                # publication-critical (fail closed). The overall SyncRun status may
                # stay PARTIAL while the public candidate publishes — but ONLY when
                # every publication-critical requirement is complete; a critical or
                # unknown-criticality failure still withholds. The finality,
                # appearance-ledger, freshness, and provenance gates are unchanged.
                non_gamelog_records_failed = max(
                    records_failed - pull.get('records_failed', 0), 0
                )
                if game_lane_authoritative:
                    # Foundation 3C: publication-critical completeness is
                    # game-level. The demoted full-season pitcher loop
                    # contributes ONLY best-effort accounting, so its shortfall
                    # defers repair work instead of withholding the snapshot —
                    # and the game-level proof withholds on its own terms.
                    publication_critical = (
                        _publication_critical_from_game_lane(
                            game_lane=game_lane,
                            pull=pull,
                            non_gamelog_critical_failed=non_gamelog_records_failed,
                        )
                    )
                else:
                    publication_critical = (
                        _publication_critical_from_legacy_pull(
                            pull=pull,
                            non_gamelog_critical_failed=(
                                non_gamelog_records_failed
                            ),
                        )
                    )
                status['publication_critical'] = publication_critical
                api_metrics = mlb_client.metrics.snapshot()
                changed_log_count = pull['new_logs_added'] + logs_corrected
                completed_run, snapshot = complete_sync_run_with_snapshot(
                    sync_run_id,
                    publication_critical_complete=publication_critical['complete'],
                    final_status=final_status,
                    records_processed=changed_log_count,
                    records_failed=records_failed,
                    new_logs_added=pull['new_logs_added'],
                    pitchers_updated=pitchers_updated,
                    errors=(
                        pull['errors']
                        + roster['errors']
                        + team_assignment['errors']
                        + transactions['errors']
                        + schedule_finality_records_failed
                        + slate_schedule_records_failed
                    ),
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=status['message'] or None,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    snapshot_source='scheduled_sync',
                )
                status['dashboard_snapshot_id'] = snapshot.id
                return {'status': final_status, 'snapshot_id': snapshot.id}

            active_stage = sync_metadata.STAGE_DASHBOARD_SNAPSHOT
            _run_logged_daily_sync_phase(
                run_logger,
                post_fatigue_phase_timings,
                'sync_completion_snapshot_publish',
                _complete_sync_phase,
            )

            if include_internal_enrichment:
                active_stage = sync_metadata.STAGE_WORKLOAD_EVIDENCE
                _run_post_publish_internal_daily_sync_phase(
                    run_logger,
                    post_fatigue_phase_timings,
                    sync_metadata.STAGE_WORKLOAD_EVIDENCE,
                    lambda: _safe_build_workload_recovery_evidence_stage(
                        [product_day.calendar_date],
                        sync_run_id=sync_run_id,
                        source='scheduled_sync',
                        job_name=sync_metadata.JOB_DAILY_SYNC,
                        run_logger=run_logger,
                    ),
                )
                active_stage = sync_metadata.STAGE_COMPOSED_READS
                _run_post_publish_internal_daily_sync_phase(
                    run_logger,
                    post_fatigue_phase_timings,
                    sync_metadata.STAGE_COMPOSED_READS,
                    lambda: _safe_build_composed_reads_stage(
                        [product_day.calendar_date],
                        sync_run_id=sync_run_id,
                        source='scheduled_sync',
                        job_name=sync_metadata.JOB_DAILY_SYNC,
                        run_logger=run_logger,
                    ),
                )
                active_stage = STAGE_LEGACY_READ_RECONCILIATION_AUDIT
                _run_post_publish_internal_daily_sync_phase(
                    run_logger,
                    post_fatigue_phase_timings,
                    STAGE_LEGACY_READ_RECONCILIATION_AUDIT,
                    lambda: _safe_run_legacy_read_reconciliation_audit_stage(
                        [product_day.calendar_date],
                        sync_run_id=sync_run_id,
                        source='scheduled_sync',
                        job_name=sync_metadata.JOB_DAILY_SYNC,
                        run_logger=run_logger,
                    ),
                )
                active_stage = sync_metadata.STAGE_BACKTEST_REFRESH
                _run_post_publish_internal_daily_sync_phase(
                    run_logger,
                    post_fatigue_phase_timings,
                    sync_metadata.STAGE_BACKTEST_REFRESH,
                    lambda: _refresh_availability_backtest_phase(
                        sync_run_id,
                        status,
                        run_logger,
                    ),
                )
                _restore_completed_sync_publish_stage(
                    sync_run_id,
                    run_logger=run_logger,
                )
            else:
                status['internal_enrichment'] = 'skipped_public_only'
    except sync_metadata.SyncWriterConflict as conflict:
        status.update(sync_metadata.sync_writer_conflict_payload(conflict))
        run_logger.warning('Daily sync blocked: %s', conflict.reason)
    except Exception as e:
        status['status']  = sync_metadata.STATUS_FAILED
        status['message'] = str(e)
        run_logger.exception('Daily sync failed: %s', e)
        # Snapshot whatever API activity occurred before the crash so a failed
        # run still records its retry pressure.
        try:
            api_metrics = mlb_client.metrics.snapshot()
        except Exception:
            api_metrics = {'api_calls': 0, 'retries': 0}
        with app.app_context():
            existing_run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
            if existing_run is None or existing_run.status != sync_metadata.STATUS_FAILED:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    errors=1,
                    api_calls_made=api_metrics['api_calls'],
                    retries_used=api_metrics['retries'],
                    error_message=str(e),
                    stage=sync_metadata.STAGE_FAILED,
                    failed_stage=active_stage or (
                        existing_run.stage if existing_run is not None else None
                    ),
                )

    if writer_guard is not None:
        if post_fatigue_instrumentation_started:
            _run_logged_daily_sync_phase(
                run_logger,
                post_fatigue_phase_timings,
                'writer_guard_release',
                lambda: (writer_guard.release() or {'status': 'released'}),
            )
        else:
            writer_guard.release()
    elif post_fatigue_instrumentation_started:
        run_logger.info(
            'Daily sync post-fatigue phase skipped: phase=writer_guard_release '
            'status=no_guard.'
        )

    status['finished_at'] = datetime.now(timezone.utc).isoformat()

    if post_fatigue_instrumentation_started:
        _run_logged_daily_sync_phase(
            run_logger,
            post_fatigue_phase_timings,
            'local_status_write',
            lambda: (write_status(status) or {'status': 'written'}),
        )
        _log_daily_sync_phase_summary(run_logger, post_fatigue_phase_timings)
    else:
        write_status(status)

    run_logger.info('── Daily sync finished: %s ──', status['status'])
    # Detach the handler so it doesn't leak on the next run.
    if post_fatigue_instrumentation_started:
        _run_logged_daily_sync_phase(
            run_logger,
            post_fatigue_phase_timings,
            'logger_cleanup',
            lambda: (
                run_logger.removeHandler(file_handler),
                file_handler.close(),
                {'status': 'closed'},
            )[-1],
        )
    else:
        run_logger.removeHandler(file_handler)
        file_handler.close()

    return status


def run_internal_enrichment(
    app,
    product_dates=None,
    *,
    source: str = sync_metadata.SOURCE_GITHUB_ACTIONS,
    include_backtest: bool = True,
):
    """
    Run internal-only evidence/read/audit enrichment outside the public sync lane.

    This entrypoint intentionally does not publish dashboard snapshots or update
    public freshness state. It records its own sync_runs row under the internal
    job name and uses the internal writer lock scope so it cannot block public
    daily/postgame publication.
    """
    _ensure_logs_dir()
    log_file = _STATUS_DIR / 'internal_enrichment.log'
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s  %(levelname)-7s  %(message)s'
    ))
    run_logger = logging.getLogger('baseballos.internal_enrichment')
    if not any(isinstance(h, logging.FileHandler) and getattr(h, 'baseFilename', None) == str(log_file)
               for h in run_logger.handlers):
        run_logger.addHandler(file_handler)
    run_logger.setLevel(logging.INFO)

    started_at = datetime.now(timezone.utc)
    dates = sorted({_date for _date in product_dates or [] if _date is not None})
    if not dates:
        dates = [resolve_product_day(started_at).calendar_date]
    sync_run_id = None
    writer_guard = None
    active_stage = None
    enrichment_started = time.perf_counter()
    status = {
        'last_sync': started_at.isoformat(),
        'status': sync_metadata.STATUS_SUCCESS,
        'job_name': sync_metadata.JOB_INTERNAL_ENRICHMENT,
        'product_dates': [day.isoformat() for day in dates],
        'include_backtest': include_backtest,
        'phase_results': {},
        'failed_phases': [],
        'checkpoint_summary': {},
        'message': '',
        'errors': 0,
    }
    run_logger.info(
        '── Internal enrichment starting (dates=%s include_backtest=%s) ──',
        ','.join(status['product_dates']),
        include_backtest,
    )

    try:
        with app.app_context():
            writer_guard = sync_metadata.acquire_sync_writer_guard(
                job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
                source=source,
                lock_scope=sync_metadata.LOCK_SCOPE_INTERNAL,
            )
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
                job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
            )
            active_stage = sync_metadata.STAGE_WORKLOAD_EVIDENCE
            phase_result = _run_internal_enrichment_phases(
                dates,
                sync_run_id=sync_run_id,
                source=source,
                job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
                run_logger=run_logger,
                include_backtest=include_backtest,
                status=status,
            )
            status.update({
                'status': phase_result['status'],
                'phase_results': phase_result['phase_results'],
                'failed_phases': phase_result['failed_phases'],
                'phase_timings': phase_result['phase_timings'],
                'checkpoint_summary': phase_result.get('checkpoint_summary', {}),
            })
            status['errors'] = len(status['failed_phases'])
            if status['failed_phases']:
                status['message'] = (
                    'Internal enrichment failed phase(s): '
                    + ','.join(status['failed_phases'])
                )
                active_stage = status['failed_phases'][0]
            else:
                status['message'] = 'Internal enrichment completed.'
                active_stage = sync_metadata.STAGE_BACKTEST_REFRESH if include_backtest else STAGE_LEGACY_READ_RECONCILIATION_AUDIT
            sync_metadata.finish_sync_run(
                sync_run_id,
                status=status['status'],
                records_processed=len(status['phase_results']),
                records_failed=len(status['failed_phases']),
                errors=status['errors'],
                error_message=status['message'] or None,
                source=source,
                started_at=started_at.replace(tzinfo=None),
                job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
                stage=(
                    sync_metadata.STAGE_FAILED
                    if status['status'] == sync_metadata.STATUS_FAILED
                    else active_stage
                ),
                failed_stage=(
                    active_stage
                    if status['status'] == sync_metadata.STATUS_FAILED
                    else None
                ),
            )
    except sync_metadata.SyncWriterConflict as conflict:
        status.update(sync_metadata.sync_writer_conflict_payload(conflict))
        status['job_name'] = sync_metadata.JOB_INTERNAL_ENRICHMENT
        run_logger.warning('Internal enrichment blocked: %s', conflict.reason)
    except Exception as exc:
        status['status'] = sync_metadata.STATUS_FAILED
        status['message'] = str(exc)
        status['errors'] = max(1, status.get('errors', 0))
        run_logger.exception('Internal enrichment failed: %s', exc)
        with app.app_context():
            existing_run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
            if existing_run is None or existing_run.status != sync_metadata.STATUS_FAILED:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    errors=status['errors'],
                    error_message=str(exc),
                    job_name=sync_metadata.JOB_INTERNAL_ENRICHMENT,
                    stage=sync_metadata.STAGE_FAILED,
                    failed_stage=active_stage,
                )

    if writer_guard is not None:
        writer_guard.release()

    status['finished_at'] = datetime.now(timezone.utc).isoformat()
    status['elapsed_ms'] = round((time.perf_counter() - enrichment_started) * 1000, 1)
    run_logger.info(
        'internal_enrichment completed status=%s dates=%s failed_phases=%s '
        'elapsed_ms=%s',
        status['status'],
        ','.join(status['product_dates']),
        ','.join(status.get('failed_phases') or []),
        status['elapsed_ms'],
    )
    run_logger.info('── Internal enrichment finished: %s ──', status['status'])
    run_logger.removeHandler(file_handler)
    file_handler.close()
    return status


def write_status(status: dict) -> None:
    """
    Persist a diagnostic sync status dict to STATUS_FILE.

    Public freshness reporting reads durable sync_runs metadata instead of this
    local cache file.
    """
    # Best-effort cache only. This file must NEVER gate the durable sync_runs
    # write — a read-only filesystem (mkdir/open failure) here is non-fatal and
    # is swallowed so it can never break or precede the durable record.
    try:
        _ensure_logs_dir()
        with open(STATUS_FILE, 'w', encoding='utf-8') as fh:
            json.dump(status, fh, indent=2)
    except OSError as e:
        # Non-fatal — sync itself succeeded, we just couldn't persist the cache.
        logging.getLogger('baseballos.sync').warning(
            'Could not write status file: %s', e
        )

def read_status():
    """Return the most recent sync status, or a sentinel if none exists."""
    if not STATUS_FILE.exists():
        return {
            'last_sync':        None,
            'pitchers_updated': 0,
            'status':           'never',
            'message':          'No sync has run yet.',
        }
    try:
        with open(STATUS_FILE, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        return {
            'last_sync':        None,
            'pitchers_updated': 0,
            'status':           'error',
            'message':          f'Could not read status file: {e}',
        }
