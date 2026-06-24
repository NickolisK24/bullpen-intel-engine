import hmac
import json
import os

from flask import Blueprint, abort, current_app, jsonify, request
from sqlalchemy import desc
from datetime import date, datetime, timedelta, timezone
from time import perf_counter

from api.query_params import (
    QueryParamError,
    parse_enum_param,
    parse_int_param,
    parse_positive_int_param,
    query_param_error_response,
)
from utils.db import db
from models.pitcher import Pitcher
from models.game_log import GameLog
from models.fatigue_score import FatigueScore
from models.sync_run import SyncRun
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services.availability_reference_date import (
    parse_reference_date,
    product_current_date,
)
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    availability_mode_metadata,
    classify_fatigue_rows,
    classify_latest_fatigue_rows,
    latest_fatigue_rows as availability_latest_fatigue_rows,
)
from services.availability_summary import (
    summarize_availability_records,
    summarize_scored_pitcher_inventory,
)
from services.availability_population import (
    CURRENT_AVAILABILITY_SCOPE,
    availability_with_eligibility,
    current_availability_records,
)
from services.bullpen_board import (
    BOARD_GROUP_ORDER,
    build_board_payload,
    build_team_context,
    last_workload_appearance_from_logs,
)
from services.bullpen_capacity import (
    build_league_capacity_payload,
    build_team_bullpen_capacity,
    season_relief_outs_by_pitcher,
)
from services.bullpen_environment import (
    build_league_bullpen_environment_payload,
    build_team_bullpen_environment,
)
from services.bullpen_stability import (
    build_league_bullpen_stability_payload,
    build_team_bullpen_stability,
    recent_bullpen_stability_logs_by_pitcher,
)
from services.rotation_support_pressure import (
    build_league_rotation_support_payload,
    build_team_rotation_support_pressure,
    recent_team_game_logs,
)
from services.bullpen_comparison import build_team_comparison
from services.bullpen_context import (
    BULLPEN_CONTEXT_SAMPLE_CAP,
    CONTEXT_LIMITATIONS as BULLPEN_CONTEXT_LIMITATIONS,
    build_league_sample_bullpen_context,
    build_team_bullpen_context,
    sample_bullpen_context_team_ids,
)
from services.bullpen_population import (
    eligible_bullpen_pitcher_contexts,
    population_diagnostic,
)
from services.bullpen_visibility import build_visibility_contract
from services.game_context import build_landscape, build_team_game_context
from services.injury_il_context import build_injury_il_context_payload
from services.narrative_memory import (
    DEFAULT_WINDOWS as NARRATIVE_MEMORY_WINDOWS,
    build_team_bullpen_recovery_continuity,
    build_team_pitcher_usage_trend_continuity,
    build_team_workload_concentration_continuity,
)
from services.pitcher_role import ROLE_KEYS
from services.pitcher_role_authority import author_role_read_labels, role_logs_by_pitcher
from services.story_intelligence_service_v1 import (
    build_team_story as build_story_intelligence_team_story,
)
from services.story_four_beat_interpreter_v1 import public_beat_for_observation
from services.story_feed import build_canonical_story_feed
from services.bullpen_role_change_detection import (
    build_role_change_detection_payload,
    has_role_change_detection_inputs,
)
from services.what_changed_since_yesterday_public import build_what_changed_public_payload
from services.team_changes import build_team_changes_payload
from services.roster_status import (
    apply_roster_status_to_availability,
    classify_roster_status,
)
from services.roster_status_audit import with_recent_inactive_roster_audit
from services.baseline_distribution import build_baseline_payload
from services.season_era import build_season_era_payload
from services.workload_concentration import (
    WORKLOAD_CONCENTRATION_BASELINE_FAMILY,
    build_workload_concentration_baselines,
    league_relief_workload_by_team,
    summarize_recent_relief_workload,
)
from services.mlb_api import MlbApiFetchError, mlb_client
from services import dashboard_snapshot as dashboard_snapshot_service
from services import sync as sync_service
from services import sync_metadata
from services import board_freshness
from utils.auth import require_admin_token

bullpen_bp = Blueprint('bullpen', __name__)

NARRATIVE_MEMORY_DIAGNOSTIC_SAMPLE_CAP = 5
DASHBOARD_SNAPSHOT_BUILD_TOKEN_ENV = 'DASHBOARD_SNAPSHOT_BUILD_TOKEN'
INTERNAL_TOKEN_HEADER = 'X-Internal-Token'
BULLPEN_LIST_LIMIT_MAX = 750
PITCHER_LOG_DAYS_MAX = 3650
MLB_SEASON_MIN = 1876
MLB_SEASON_MAX = 2100
RISK_LEVELS = {'LOW', 'MODERATE', 'HIGH', 'CRITICAL'}
WHAT_CHANGED_PUBLIC_TEAM_LIMIT = 30
WHAT_CHANGED_MEANINGFUL_WORKLOAD_PITCHES = 15
WHAT_CHANGED_WORKLOAD_ADDED_LIMIT = 3

FATIGUE_ERA_RESULTS_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'analysis',
    'fatigue_era_results.json',
)

def _truthy(value):
    """Parse a query-string boolean tolerantly."""
    if value is None:
        return False
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


def _availability_reference_date_from_freshness(freshness):
    return parse_reference_date((freshness or {}).get('availability_reference_date'))


def _freshness_reference_date(freshness):
    return parse_reference_date((freshness or {}).get('reference_date')) or product_current_date()


def _public_availability_reference_date(freshness=None):
    """
    Availability anchor for public current-availability claims.

    Prefer the durable data-derived date carried by freshness. The fallback is
    a product calendar date, not the host machine's local date.
    """
    return _availability_reference_date_from_freshness(freshness) or product_current_date()


def _active_pitcher_cutoff(days: int = ACTIVE_WINDOW_DAYS, reference_date=None):
    """Calendar-date cutoff for the active/current bullpen list."""
    ref = reference_date or product_current_date()
    return ref - timedelta(days=days)


def _recent_pitcher_ids_subquery(days: int = ACTIVE_WINDOW_DAYS, reference_date=None):
    """
    Subquery returning pitcher_ids whose most recent game_log.game_date falls
    within the last `days` days relative to the product reference date. This intentionally
    treats historical local snapshots as inactive/stale instead of pretending
    old data is current bullpen availability.
    """
    cutoff = _active_pitcher_cutoff(days, reference_date=reference_date)
    return (
        db.session.query(GameLog.pitcher_id.label('pitcher_id'))
        .group_by(GameLog.pitcher_id)
        .having(db.func.max(GameLog.game_date) >= cutoff)
        .subquery()
    )


def _served_score_cutoff():
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is None:
        return None
    return snapshot.snapshot_generated_at


def _latest_fatigue_query(team_id=None, risk_level=None, calculated_at_lte=None):
    """Latest fatigue-score rows with optional user-visible filters applied."""
    score_scope = db.session.query(FatigueScore)
    if calculated_at_lte is not None:
        score_scope = score_scope.filter(FatigueScore.calculated_at <= calculated_at_lte)
    score_scope = score_scope.subquery()

    subq = (
        db.session.query(
            score_scope.c.pitcher_id,
            db.func.max(score_scope.c.calculated_at).label('max_calc')
        )
        .group_by(score_scope.c.pitcher_id)
        .subquery()
    )

    query = (
        db.session.query(FatigueScore, Pitcher)
        .join(subq, (FatigueScore.pitcher_id == subq.c.pitcher_id) &
                    (FatigueScore.calculated_at == subq.c.max_calc))
        .join(Pitcher, FatigueScore.pitcher_id == Pitcher.id)
    )

    if team_id:
        query = query.filter(Pitcher.team_id == team_id)
    if risk_level:
        query = query.filter(FatigueScore.risk_level == risk_level.upper())

    return query


def _fatigue_list_meta(
    filtered_count,
    fresh_filtered_count,
    returned_count,
    include_stale,
    team_id,
    risk_level,
    reference_date=None,
):
    """Trust metadata explaining why a fatigue list may be empty."""
    latest_game_date = db.session.query(db.func.max(GameLog.game_date)).scalar()
    total_game_logs = db.session.query(db.func.count(GameLog.id)).scalar() or 0

    total_scored = (
        db.session.query(db.func.count(db.func.distinct(FatigueScore.pitcher_id)))
        .scalar()
        or 0
    )

    return {
        'include_stale': include_stale,
        'active_window_days': ACTIVE_WINDOW_DAYS,
        'active_cutoff_date': _active_pitcher_cutoff(reference_date=reference_date).isoformat(),
        'availability_reference_date': reference_date.isoformat() if reference_date else None,
        'latest_game_date': latest_game_date.isoformat() if latest_game_date else None,
        'total_game_logs': int(total_game_logs),
        'total_scored_pitchers': int(total_scored),
        'filtered_scored_pitchers': int(filtered_count),
        'fresh_filtered_pitchers': int(fresh_filtered_count),
        'stale_filtered_pitchers': int(max(filtered_count - fresh_filtered_count, 0)),
        'returned_pitchers': int(returned_count),
        'filters': {
            'team_id': team_id,
            'risk_level': risk_level.upper() if risk_level else None,
        },
    }


def _availability_context(pitcher_id, reference_date=None):
    """Fetch the current workload window needed by the availability service."""
    ref = reference_date or product_current_date()
    latest_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )
    window_start = ref - timedelta(days=4)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= ref,
        )
        .order_by(desc(GameLog.game_date))
        .all()
    )
    return logs, latest_game_date


def _availability_for(pitcher_id, score, reference_date=None):
    ref = reference_date or product_current_date()
    logs, latest_game_date = _availability_context(pitcher_id, reference_date=ref)
    return classify_availability(
        score=score,
        game_logs=logs,
        reference_date=ref,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )


# ─── Fatigue Scores ───────────────────────────────────────────────────────────

@bullpen_bp.route('/fatigue', methods=['GET'])
def get_fatigue_scores():
    """
    Get current fatigue scores for all pitchers.
    Optional query params:
      - team_id: filter by team
      - risk_level: LOW | MODERATE | HIGH | CRITICAL
      - limit: max results (default 50)
      - include_stale: when truthy, include pitchers whose most recent
                       appearance is older than 14 days. Default false.
      - with_meta: when truthy, return {data, meta} instead of the legacy array.
    """
    team_id, error = parse_positive_int_param(request.args, 'team_id')
    if error:
        return query_param_error_response(error)
    risk_level, error = parse_enum_param(request.args, 'risk_level', RISK_LEVELS)
    if error:
        return query_param_error_response(error)
    limit, error = parse_positive_int_param(
        request.args,
        'limit',
        default=50,
        maximum=BULLPEN_LIST_LIMIT_MAX,
        clamp_max=True,
    )
    if error:
        return query_param_error_response(error)
    include_stale = _truthy(request.args.get('include_stale'))
    with_meta     = _truthy(request.args.get('with_meta'))
    freshness     = _board_freshness_block()
    reference_date = _public_availability_reference_date(freshness)
    score_cutoff = _served_score_cutoff()

    base_query     = _latest_fatigue_query(
        team_id=team_id,
        risk_level=risk_level,
        calculated_at_lte=score_cutoff,
    )
    filtered_count = base_query.count()
    recent         = _recent_pitcher_ids_subquery(reference_date=reference_date)
    fresh_query    = base_query.join(recent, recent.c.pitcher_id == Pitcher.id)
    fresh_count    = fresh_query.count()
    query          = base_query
    if not include_stale:
        query  = query.join(recent, recent.c.pitcher_id == Pitcher.id)

    query   = query.order_by(desc(FatigueScore.raw_score)).limit(limit)
    results = query.all()

    records = classify_fatigue_rows(
        results,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )

    data = []
    for record in records:
        score = record['score']
        pitcher = record['pitcher']
        data.append({
            **score.to_dict(),
            'pitcher': pitcher.to_dict(),
            'availability': record['availability'],
        })
    if not with_meta:
        return jsonify(data)

    return jsonify({
        'data': data,
        'meta': _fatigue_list_meta(
            filtered_count=filtered_count,
            fresh_filtered_count=fresh_count,
            returned_count=len(data),
            include_stale=include_stale,
            team_id=team_id,
            risk_level=risk_level,
            reference_date=reference_date,
        ),
    })


@bullpen_bp.route('/fatigue/snapshot', methods=['GET'])
@require_admin_token
def get_latest_workload_snapshot():
    """
    Admin/development-only validation view of the latest known workload window.

    This intentionally does not represent current bullpen availability. It
    anchors each pitcher on their own most recent game log so local historical
    datasets can exercise availability thresholds without changing public
    calendar-based freshness behavior.
    """
    team_id, error = parse_positive_int_param(request.args, 'team_id')
    if error:
        return query_param_error_response(error)
    risk_level, error = parse_enum_param(request.args, 'risk_level', RISK_LEVELS)
    if error:
        return query_param_error_response(error)
    limit, error = parse_positive_int_param(
        request.args,
        'limit',
        default=BULLPEN_LIST_LIMIT_MAX,
        maximum=BULLPEN_LIST_LIMIT_MAX,
        clamp_max=True,
    )
    if error:
        return query_param_error_response(error)

    rows = availability_latest_fatigue_rows(
        team_id=team_id,
        risk_level=risk_level,
        limit=limit,
        order_by_score=True,
    )
    records = classify_latest_fatigue_rows(rows, mode=LATEST_WORKLOAD_SNAPSHOT_MODE)

    data = []
    for record in records:
        score = record['score']
        pitcher = record['pitcher']
        data.append({
            **score.to_dict(),
            'pitcher': pitcher.to_dict(),
            'availability': record['availability'],
            'availability_mode': {
                'mode': LATEST_WORKLOAD_SNAPSHOT_MODE,
                'evaluation_date': record['evaluation_date'].isoformat() if record['evaluation_date'] else None,
                'latest_game_date': record['latest_game_date'].isoformat() if record['latest_game_date'] else None,
                'is_current_availability': False,
            },
        })

    meta = availability_mode_metadata(LATEST_WORKLOAD_SNAPSHOT_MODE, records=records)
    meta.update({
        'total_pitchers': len(records),
        'returned_pitchers': len(data),
        'active_window_days': ACTIVE_WINDOW_DAYS,
        'filters': {
            'team_id': team_id,
            'risk_level': risk_level.upper() if risk_level else None,
        },
    })
    response = jsonify({'data': data, 'meta': meta})
    response.headers['X-BaseballOS-Data-Mode'] = LATEST_WORKLOAD_SNAPSHOT_MODE
    response.headers['X-BaseballOS-Current-Availability'] = 'false'
    return response


@bullpen_bp.route('/fatigue/<int:pitcher_id>', methods=['GET'])
def get_pitcher_fatigue(pitcher_id):
    """Get detailed fatigue profile for a single pitcher."""
    pitcher = db.session.get(Pitcher, pitcher_id)
    if pitcher is None:
        abort(404)

    score_cutoff = _served_score_cutoff()
    latest_query = FatigueScore.query.filter_by(pitcher_id=pitcher_id)
    if score_cutoff is not None:
        latest_query = latest_query.filter(FatigueScore.calculated_at <= score_cutoff)
    latest = latest_query.order_by(desc(FatigueScore.calculated_at)).first()

    freshness = _board_freshness_block()
    reference_date = _public_availability_reference_date(freshness)

    # Anchor recent_logs / fatigue_trend on the pitcher's most recent game
    # so historical (e.g. 2024-2025 seed) data still produces non-empty
    # windows. Fall back to the product reference date if the pitcher has no
    # logs at all.
    last_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )
    anchor = last_game_date if last_game_date else reference_date

    fourteen_days_ago = anchor - timedelta(days=14)
    logs = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.game_date >= fourteen_days_ago)
        .order_by(desc(GameLog.game_date))
        .all()
    )

    thirty_days_ago = anchor - timedelta(days=30)
    history = (
        FatigueScore.query
        .filter(
            FatigueScore.pitcher_id == pitcher_id,
            FatigueScore.calculated_at >= thirty_days_ago
        )
        .order_by(FatigueScore.calculated_at)
    )
    if score_cutoff is not None:
        history = history.filter(FatigueScore.calculated_at <= score_cutoff)
    history = history.all()

    workload_signal = _availability_for(pitcher_id, latest, reference_date=reference_date)
    roster_status = classify_roster_status(pitcher)
    roster_status = with_recent_inactive_roster_audit(roster_status, logs, reference_date)
    availability = apply_roster_status_to_availability(workload_signal, roster_status)

    last_workload_appearance = last_workload_appearance_from_logs(logs)

    return jsonify({
        'pitcher':         pitcher.to_dict(),
        'current_fatigue': latest.to_dict() if latest else None,
        'availability':    availability,
        'workload_signal': workload_signal,
        'roster_status':   roster_status,
        'freshness':       freshness,
        'last_appearance': last_workload_appearance,
        'last_workload_appearance': last_workload_appearance,
        'recent_logs':     [log.to_dict() for log in logs],
        'fatigue_trend':   [s.to_dict() for s in history],
    })


@bullpen_bp.route('/fatigue/recalculate', methods=['POST'])
@require_admin_token
def recalculate_fatigue():
    """
    Trigger fatigue recalculation for all pitchers.

    Delegates to the single canonical recalculation authority
    (services.sync.recalculate_all_fatigue), which scores every pitcher against
    the canonical availability reference date — the latest completed MLB
    workload date + 1 day. This guarantees the recalculate endpoint, the
    scheduled sync, and the GitHub Actions / manual sync all write identical
    fatigue scores for the same game logs, so the league snapshot never changes
    based on which path last ran.
    """
    updated = sync_service.recalculate_all_fatigue()

    # Report the canonical latest scores so the response stays a faithful read
    # of what was just persisted (one entry per scored pitcher).
    rows = _latest_fatigue_query().all()
    results = [
        {
            'pitcher': pitcher.full_name,
            'score':   round(score.raw_score, 1),
            'risk':    score.risk_level,
        }
        for score, pitcher in rows
    ]

    return jsonify({'recalculated': updated, 'results': results})


# ─── Sync (Live Data Refresh) ─────────────────────────────────────────────────

@bullpen_bp.route('/sync', methods=['POST'])
@require_admin_token
def sync_recent_logs():
    """
    Pull the latest game logs from the MLB Stats API for the current season
    and recalculate fatigue scores. Safe to call repeatedly — skips duplicates.

    Optional JSON body:
      { "days_back": 7 }  — how far back to look for new games (default: 7)

    Delegates to services/sync.py so the scheduled daily job and the manual
    POST go through the exact same code path. Durable sync_runs metadata is the
    freshness authority; the status file write is cache-only.
    """
    body      = request.get_json(silent=True) or {}
    days_back = body.get('days_back', 7)
    source    = str(body.get('source') or sync_metadata.SOURCE_MANUAL)[:30]
    started   = datetime.now(timezone.utc)
    sync_run_id = sync_metadata.start_sync_run(
        source=source,
        started_at=started.replace(tzinfo=None),
    )
    # Fresh API metrics so api_calls_made / retries_used reflect only this run.
    mlb_client.metrics.reset()

    try:
        sync_metadata.set_sync_stage(
            sync_run_id,
            sync_metadata.STAGE_TEAM_ASSIGNMENTS,
        )
        team_assignment = sync_service.sync_team_assignments()
        team_assignment_records_failed = sync_service.record_sync_error_details(
            'team_assignment_fetch',
            team_assignment.get('error_details'),
            sync_run_id=sync_run_id,
        )
        sync_metadata.set_sync_stage(
            sync_run_id,
            sync_metadata.STAGE_ROSTER_STATUS,
        )
        roster = sync_service.sync_roster_statuses()
        roster_records_failed = sync_service.record_sync_error_details(
            'roster_status_fetch',
            roster.get('error_details'),
            sync_run_id=sync_run_id,
        )
        sync_metadata.set_sync_stage(
            sync_run_id,
            sync_metadata.STAGE_LOG_INGESTION,
        )
        pull = sync_service.sync_recent_logs(days_back=days_back, sync_run_id=sync_run_id)
    except Exception as e:
        db.session.rollback()
        # Durable first, and self-healing: writes a failed row even if the start
        # row never persisted, so the failure is recorded in sync_runs (not only
        # the cache file).
        api_metrics = mlb_client.metrics.snapshot()
        failed_run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=sync_metadata.STATUS_FAILED,
            errors=1,
            api_calls_made=api_metrics['api_calls'],
            retries_used=api_metrics['retries'],
            error_message=str(e),
            source=source,
            started_at=started.replace(tzinfo=None),
            stage=sync_metadata.STAGE_FAILED,
            failed_stage=(
                db.session.get(SyncRun, sync_run_id).stage
                if sync_run_id and db.session.get(SyncRun, sync_run_id) is not None
                else None
            ),
        )
        # Persist failure status so the dashboard reflects the bad state. The
        # file write is best-effort and never gates the durable row above.
        sync_service.write_status({
            'last_sync':       started.isoformat(),
            'status':          sync_metadata.STATUS_FAILED,
            'pitchers_updated': 0,
            'new_logs_added':  0,
            'errors':          1,
            'message':         str(e),
            'finished_at':     datetime.now(timezone.utc).isoformat(),
        })
        return jsonify({'error': f'Sync failed: {str(e)}'}), 500

    try:
        # Canonical authority: score against the latest completed workload date + 1
        # day — the same reference the scheduled sync and recalculate endpoint use.
        sync_metadata.set_sync_stage(
            sync_run_id,
            sync_metadata.STAGE_FATIGUE_RECALCULATION,
        )
        fatigue_updated = sync_service.recalculate_all_fatigue()
        sync_metadata.set_sync_stage(
            sync_run_id,
            sync_metadata.STAGE_BACKTEST_REFRESH,
        )
        try:
            from services.availability_backtest import refresh_availability_backtest
            backtest = refresh_availability_backtest()
        except Exception as exc:
            db.session.rollback()
            backtest = {'status': 'failed', 'error': str(exc)}
        finished        = datetime.now(timezone.utc)
        # Partial when records were dead-lettered but domains still refreshed.
        records_failed = (
            pull['records_failed']
            + team_assignment_records_failed
            + roster_records_failed
        )
        final_status = (
            sync_metadata.STATUS_PARTIAL if records_failed
            else sync_metadata.STATUS_SUCCESS
        )
        partial_message = (
            f'{records_failed} record(s) dead-lettered; see sync_failures.'
            if records_failed else None
        )
        api_metrics = mlb_client.metrics.snapshot()
        # Durable first (self-healing if the start row never persisted), then the
        # best-effort cache file. The durable row is the source of truth.
        completed_run, snapshot = sync_service.complete_sync_run_with_snapshot(
            sync_run_id,
            final_status=final_status,
            completed_at=finished.replace(tzinfo=None),
            records_processed=pull['new_logs_added'],
            records_failed=records_failed,
            new_logs_added=pull['new_logs_added'],
            pitchers_updated=fatigue_updated,
            errors=pull['errors'] + roster['errors'] + team_assignment['errors'],
            api_calls_made=api_metrics['api_calls'],
            retries_used=api_metrics['retries'],
            error_message=partial_message,
            source=source,
            started_at=started.replace(tzinfo=None),
            snapshot_source='manual_sync',
        )
    except Exception as exc:
        db.session.rollback()
        finished = datetime.now(timezone.utc)
        fatigue_updated = locals().get('fatigue_updated', 0)
        records_failed = (
            pull.get('records_failed', 0)
            + locals().get('team_assignment_records_failed', 0)
            + locals().get('roster_records_failed', 0)
        )
        api_metrics = mlb_client.metrics.snapshot()
        existing_run = db.session.get(SyncRun, sync_run_id) if sync_run_id else None
        if existing_run is None or existing_run.status != sync_metadata.STATUS_FAILED:
            sync_metadata.finish_sync_run(
                sync_run_id,
                status=sync_metadata.STATUS_FAILED,
                completed_at=finished.replace(tzinfo=None),
                records_processed=pull['new_logs_added'],
                records_failed=records_failed,
                new_logs_added=pull['new_logs_added'],
                pitchers_updated=fatigue_updated,
                errors=pull['errors'] + roster['errors'] + team_assignment['errors'] + 1,
                api_calls_made=api_metrics['api_calls'],
                retries_used=api_metrics['retries'],
                error_message=str(exc),
                source=source,
                started_at=started.replace(tzinfo=None),
                stage=sync_metadata.STAGE_FAILED,
                failed_stage=existing_run.stage if existing_run is not None else None,
            )
        sync_service.write_status({
            'last_sync':       started.isoformat(),
            'status':          sync_metadata.STATUS_FAILED,
            'pitchers_updated': fatigue_updated,
            'new_logs_added':  pull['new_logs_added'],
            'records_failed':  records_failed,
            'errors':          pull['errors'] + roster['errors'] + team_assignment['errors'] + 1,
            'message':         str(exc),
            'finished_at':     finished.isoformat(),
        })
        return jsonify({'error': f'Sync failed: {str(exc)}'}), 500
    persisted_run_id = completed_run.id if completed_run is not None else sync_run_id

    # Mirror what the daily APScheduler job writes for local diagnostics. The
    # public freshness endpoint reads durable sync_runs metadata instead.
    sync_service.write_status({
        'last_sync':       started.isoformat(),
        'status':          final_status,
        'pitchers_updated': fatigue_updated,
        'new_logs_added':  pull['new_logs_added'],
        'records_failed':  records_failed,
        'errors':          pull['errors'] + roster['errors'] + team_assignment['errors'],
        'team_assignments_refreshed': team_assignment['pitchers_refreshed'],
        'team_assignments_changed': team_assignment['pitchers_changed'],
        'team_assignments_reassigned': team_assignment['reassigned_count'],
        'team_assignment_no_organization': team_assignment['no_organization_count'],
        'team_assignment_unknown': team_assignment['unknown_count'],
        'roster_statuses_refreshed': roster['pitchers_refreshed'],
        'roster_statuses_changed': roster['pitchers_changed'],
        'roster_status_unknown': roster['unknown_count'],
        'availability_backtest_status': backtest.get('status'),
        'availability_backtest_computed_at': backtest.get('computed_at'),
        'message':         '',
        'finished_at':     finished.isoformat(),
        'dashboard_snapshot_id': snapshot.id if snapshot is not None else None,
    })

    return jsonify({
        'status':               'ok',
        'sync_run_status':      final_status,
        'new_logs_added':       pull['new_logs_added'],
        'records_failed':       records_failed,
        'fatigue_recalculated': fatigue_updated,
        'errors':               pull['errors'] + roster['errors'] + team_assignment['errors'],
        'team_assignments_refreshed': team_assignment['pitchers_refreshed'],
        'team_assignments_changed': team_assignment['pitchers_changed'],
        'team_assignments_reassigned': team_assignment['reassigned_count'],
        'team_assignment_no_organization': team_assignment['no_organization_count'],
        'team_assignment_unknown': team_assignment['unknown_count'],
        'team_assignment_by_status': team_assignment['by_status'],
        'roster_statuses_refreshed': roster['pitchers_refreshed'],
        'roster_statuses_changed': roster['pitchers_changed'],
        'roster_status_unknown': roster['unknown_count'],
        'roster_status_by_status': roster['by_status'],
        'synced_at':            finished.isoformat(),
        'sync_run_id':          persisted_run_id,
        'sync_run_persisted':   persisted_run_id is not None,
        'dashboard_snapshot_id': snapshot.id if snapshot is not None else None,
        'availability_backtest_status': backtest.get('status'),
        'availability_backtest_computed_at': backtest.get('computed_at'),
        'days_back':            days_back,
    })


@bullpen_bp.route('/sync/status', methods=['GET'])
def get_sync_status():
    """
    Return the last sync status, enriched with the actual data snapshot
    (latest game date + game-log count) from the database.

    This lets the dashboard distinguish three real states that the bare status
    file cannot: a successful/failed live sync, a loaded historical snapshot
    (data present but no sync has run — e.g. after `python seed.py`), and a
    genuinely empty system. The snapshot date is real DB data, never a faked
    sync timestamp.

    Authority: durable sync_runs metadata is the source of truth (see
    services/sync_metadata.build_sync_status_payload). backend/logs/sync_status.json
    is cache-only and is not consulted for public freshness reporting.
    """
    try:
        return jsonify(sync_metadata.build_sync_status_payload())
    except Exception:
        # A DB hiccup must never turn the status pill into a hard error.
        return jsonify({
            'status': sync_metadata.STATUS_METADATA_UNAVAILABLE,
            'sync_authority': 'sync_runs',
            'metadata_source': 'none',
            'last_sync': None,
            'last_successful_sync': None,
            'pitchers_updated': 0,
            'new_logs_added': 0,
            'errors': 0,
            'message': 'Freshness metadata unavailable.',
            'finished_at': None,
            'data': {
                'game_logs': None,
                'latest_game_date': None,
                'latest_workload_date': None,
                'latest_fatigue_calculated_at': None,
            },
            'availability_reference_date': None,
            'freshness': {
                'is_current': False,
                'is_stale': False,
                'freshness_state': 'metadata_unavailable',
                'data_age_days': None,
                'reference_date': None,
                'availability_reference_date': None,
                'reason_codes': ['durable_sync_metadata_unavailable'],
                'label': 'Freshness metadata unavailable.',
                'limitations': ['Could not read durable sync metadata.'],
            },
            'sync': None,
            'last_successful_sync_run': None,
        })


# ─── Pitchers ─────────────────────────────────────────────────────────────────

@bullpen_bp.route('/pitchers', methods=['GET'])
def get_pitchers():
    """Get all pitchers, optionally filtered by team."""
    team_id, error = parse_positive_int_param(request.args, 'team_id')
    if error:
        return query_param_error_response(error)
    query    = Pitcher.query.filter_by(active=True)
    if team_id:
        query = query.filter_by(team_id=team_id)
    pitchers = query.order_by(Pitcher.team_name, Pitcher.full_name).all()
    return jsonify([p.to_dict() for p in pitchers])


@bullpen_bp.route('/pitchers/<int:pitcher_id>/logs', methods=['GET'])
def get_pitcher_logs(pitcher_id):
    """Get game logs for a pitcher."""
    days, error = parse_int_param(
        request.args,
        'days',
        default=30,
        minimum=0,
        maximum=PITCHER_LOG_DAYS_MAX,
    )
    if error:
        return query_param_error_response(error)
    since = date.today() - timedelta(days=days)
    logs  = (
        GameLog.query
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.game_date >= since)
        .order_by(desc(GameLog.game_date))
        .all()
    )
    return jsonify([log.to_dict() for log in logs])


# ─── Teams ────────────────────────────────────────────────────────────────────

@bullpen_bp.route('/teams', methods=['GET'])
def get_teams():
    """Get all teams that have pitchers in the DB."""
    teams = (
        db.session.query(
            Pitcher.team_id,
            Pitcher.team_name,
            Pitcher.team_abbreviation,
            db.func.count(Pitcher.id).label('pitcher_count')
        )
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
        .group_by(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .order_by(Pitcher.team_name)
        .all()
    )
    return jsonify([
        {
            'team_id':           t.team_id,
            'team_name':         t.team_name,
            'team_abbreviation': t.team_abbreviation,
            'pitcher_count':     t.pitcher_count,
        }
        for t in teams
    ])


def _team_bullpen_rows(team_id, include_stale=False, reference_date=None, calculated_at_lte=None):
    """
    Latest fatigue + availability for a team's active pitchers.

    Single joined query (no N+1). Returns the (pitcher, score) result rows and a
    {pitcher_id: availability} map so the bullpen overview and Tonight's Bullpen
    Board share one availability calculation instead of duplicating it.
    """
    score_scope = db.session.query(FatigueScore)
    if calculated_at_lte is not None:
        score_scope = score_scope.filter(FatigueScore.calculated_at <= calculated_at_lte)
    score_scope = score_scope.subquery()

    subq = (
        db.session.query(
            score_scope.c.pitcher_id,
            db.func.max(score_scope.c.calculated_at).label('max_calc')
        )
        .group_by(score_scope.c.pitcher_id)
        .subquery()
    )

    query = (
        db.session.query(Pitcher, FatigueScore)
        .filter(Pitcher.team_id == team_id, Pitcher.active == True)
        .outerjoin(subq, subq.c.pitcher_id == Pitcher.id)
        .outerjoin(
            FatigueScore,
            (FatigueScore.pitcher_id == subq.c.pitcher_id) &
            (FatigueScore.calculated_at == subq.c.max_calc)
        )
    )

    results = query.order_by(desc(FatigueScore.raw_score)).all()

    availability_rows = [
        (score, pitcher)
        for pitcher, score in results
    ]
    availability_by_pitcher = {
        record['pitcher_id']: record['availability']
        for record in classify_fatigue_rows(
            availability_rows,
            reference_date=reference_date,
            mode=CURRENT_AVAILABILITY_MODE,
        )
    }
    return results, availability_by_pitcher


@bullpen_bp.route('/teams/<int:team_id>/bullpen', methods=['GET'])
def get_team_bullpen(team_id):
    """
    Get full bullpen overview for a team.
    Single joined query — no N+1 issue.

    Optional query params:
      - include_stale: when truthy, include inactive/unavailable roster context
                       beyond default active bullpen options. Default false.
    """
    include_stale = _truthy(request.args.get('include_stale'))
    freshness = _board_freshness_block()
    reference_date = _public_availability_reference_date(freshness)
    results, availability_by_pitcher = _team_bullpen_rows(
        team_id,
        include_stale,
        reference_date=reference_date,
        calculated_at_lte=_served_score_cutoff(),
    )

    return jsonify([
        {
            'pitcher': pitcher.to_dict(),
            'fatigue': score.to_dict() if score else None,
            'availability': availability_by_pitcher.get(pitcher.id),
        }
        for pitcher, score in results
    ])


def _sync_status_freshness_block(status_payload=None):
    return board_freshness.sync_status_freshness_block(status_payload)


def _published_snapshot_overlay(snapshot):
    return board_freshness.published_snapshot_overlay(snapshot)


def _published_snapshot_freshness_block():
    return board_freshness.published_snapshot_freshness_block()


def _board_freshness_block(*, use_published=True):
    return board_freshness.board_freshness_block(use_published=use_published)


def _team_info_lookup(team_id):
    """Best-effort {team_id, team_name, team_abbreviation} even with no pitchers in window."""
    row = (
        db.session.query(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .filter(Pitcher.team_id == team_id)
        .first()
    )
    if row is None:
        return {'team_id': team_id, 'team_name': None, 'team_abbreviation': None}
    return {'team_id': row.team_id, 'team_name': row.team_name, 'team_abbreviation': row.team_abbreviation}


def _capacity_intelligence_for_records(team_info, records, reference_date):
    pitcher_ids = [
        record.get('pitcher_id')
        for record in records or []
        if record.get('pitcher_id') is not None
    ]
    return build_team_bullpen_capacity(
        records,
        team=team_info,
        relief_outs_by_pitcher=season_relief_outs_by_pitcher(
            pitcher_ids,
            reference_date=reference_date,
        ),
    )


def _rotation_support_for_team(team_info, reference_date):
    team_id = (team_info or {}).get('team_id')
    return build_team_rotation_support_pressure(
        recent_team_game_logs(
            team_id,
            reference_date=reference_date,
        ),
        team=team_info,
        reference_date=reference_date,
    )


def _bullpen_stability_for_records(team_info, records, reference_date):
    pitcher_ids = [
        record.get('pitcher_id')
        for record in records or []
        if record.get('pitcher_id') is not None
    ]
    return build_team_bullpen_stability(
        records,
        team=team_info,
        logs_by_pitcher=recent_bullpen_stability_logs_by_pitcher(
            pitcher_ids,
            reference_date=reference_date,
        ),
        reference_date=reference_date,
    )


def _bullpen_environment_for_reads(
    team_info,
    capacity_intelligence,
    rotation_support_pressure,
    bullpen_stability,
):
    return build_team_bullpen_environment(
        team=team_info,
        capacity_intelligence=capacity_intelligence,
        rotation_support_pressure=rotation_support_pressure,
        bullpen_stability=bullpen_stability,
    )


def _dashboard_capacity_payload(reference_date):
    team_ids = [
        row[0]
        for row in (
            db.session.query(Pitcher.team_id)
            .filter(Pitcher.active == True)
            .filter(Pitcher.team_id.isnot(None))
            .distinct()
            .order_by(Pitcher.team_id)
            .all()
        )
    ]
    team_items = []
    for team_id in team_ids:
        context_rows, availability_by_pitcher = _team_bullpen_rows(
            team_id,
            include_stale=True,
            reference_date=reference_date,
            calculated_at_lte=_served_score_cutoff(),
        )
        context_records, _roster_summary = _eligible_records_for_rows(
            context_rows,
            availability_by_pitcher,
            include_stale=True,
            reference_date=reference_date,
        )
        team_info = _team_info_lookup(team_id)
        team_items.append(_capacity_intelligence_for_records(
            team_info,
            context_records,
            reference_date,
        ))
    return build_league_capacity_payload(team_items)


def _dashboard_rotation_support_payload(reference_date):
    team_ids = [
        row[0]
        for row in (
            db.session.query(Pitcher.team_id)
            .filter(Pitcher.active == True)
            .filter(Pitcher.team_id.isnot(None))
            .distinct()
            .order_by(Pitcher.team_id)
            .all()
        )
    ]
    team_items = []
    for team_id in team_ids:
        team_info = _team_info_lookup(team_id)
        team_items.append(_rotation_support_for_team(
            team_info,
            reference_date,
        ))
    return build_league_rotation_support_payload(team_items)


def _dashboard_bullpen_stability_payload(reference_date):
    team_ids = [
        row[0]
        for row in (
            db.session.query(Pitcher.team_id)
            .filter(Pitcher.active == True)
            .filter(Pitcher.team_id.isnot(None))
            .distinct()
            .order_by(Pitcher.team_id)
            .all()
        )
    ]
    team_items = []
    for team_id in team_ids:
        context_rows, availability_by_pitcher = _team_bullpen_rows(
            team_id,
            include_stale=True,
            reference_date=reference_date,
            calculated_at_lte=_served_score_cutoff(),
        )
        context_records, _roster_summary = _eligible_records_for_rows(
            context_rows,
            availability_by_pitcher,
            include_stale=True,
            reference_date=reference_date,
        )
        team_info = _team_info_lookup(team_id)
        team_items.append(_bullpen_stability_for_records(
            team_info,
            context_records,
            reference_date,
        ))
    return build_league_bullpen_stability_payload(team_items)


def _dashboard_bullpen_environment_payload(
    capacity_intelligence,
    rotation_support_pressure,
    bullpen_stability,
):
    team_ids = sorted({
        *(int(team_id) for team_id in (capacity_intelligence.get('by_team_id') or {})),
        *(int(team_id) for team_id in (rotation_support_pressure.get('by_team_id') or {})),
        *(int(team_id) for team_id in (bullpen_stability.get('by_team_id') or {})),
    })
    team_items = []
    for team_id in team_ids:
        capacity = (capacity_intelligence.get('by_team_id') or {}).get(str(team_id)) or {}
        rotation = (rotation_support_pressure.get('by_team_id') or {}).get(str(team_id)) or {}
        stability = (bullpen_stability.get('by_team_id') or {}).get(str(team_id)) or {}
        team_info = _team_info_lookup(team_id)
        team_items.append(_bullpen_environment_for_reads(
            team_info,
            capacity,
            rotation,
            stability,
        ))
    return build_league_bullpen_environment_payload(team_items)


def _latest_comparable_role_change_payload(data_through, immediate_prior_snapshot=None):
    if immediate_prior_snapshot is not None and has_role_change_detection_inputs(
        immediate_prior_snapshot.payload,
    ):
        return immediate_prior_snapshot.payload

    for snapshot in dashboard_snapshot_service.get_recent_dashboard_snapshots_before(
        data_through,
        lookback_days=14,
    ):
        if snapshot is immediate_prior_snapshot:
            continue
        if has_role_change_detection_inputs(snapshot.payload):
            return snapshot.payload
    return None


def _merge_limitations(*groups):
    merged = []
    for group in groups:
        for limitation in group or []:
            if limitation not in merged:
                merged.append(limitation)
    return merged


def _dashboard_payload_data_through(payload):
    freshness = payload.get('freshness') if isinstance(payload, dict) else {}
    freshness = freshness if isinstance(freshness, dict) else {}
    return parse_reference_date(
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
        or freshness.get('availability_reference_date')
        or freshness.get('reference_date')
    )


def _dashboard_what_changed_workload_payload(current_date, prior_date, availability_records):
    """
    Public workload evidence for the homepage What Changed card.

    This does not select relievers or recommend usage. It summarizes observed
    relief workload added between the prior snapshot and the current one.
    """
    base = {
        'capability': 'what_changed_workload_added_v1',
        'source': 'backend',
        'selection_made': False,
        'ranking_applied': False,
        'meaningful_pitch_minimum': WHAT_CHANGED_MEANINGFUL_WORKLOAD_PITCHES,
        'item_limit': WHAT_CHANGED_WORKLOAD_ADDED_LIMIT,
        'current_data_through': current_date.isoformat() if current_date else None,
        'previous_data_through': prior_date.isoformat() if prior_date else None,
        'by_team_id': {},
    }
    if current_date is None or prior_date is None or prior_date >= current_date:
        return base

    eligible_pitchers = {}
    for record in availability_records or []:
        pitcher = record.get('pitcher') if isinstance(record, dict) else None
        if pitcher is None or pitcher.id is None or pitcher.team_id is None:
            continue
        eligible_pitchers[int(pitcher.id)] = {
            'pitcher_id': int(pitcher.id),
            'name': pitcher.full_name,
            'team_id': int(pitcher.team_id),
            'team_name': pitcher.team_name,
            'team_abbreviation': pitcher.team_abbreviation,
            'pitches': 0,
            'innings_outs': 0,
        }
    if not eligible_pitchers:
        return base

    rows = (
        db.session.query(GameLog, Pitcher)
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(GameLog.pitcher_id.in_(list(eligible_pitchers)))
        .filter(GameLog.game_date > prior_date)
        .filter(GameLog.game_date <= current_date)
        .filter(GameLog.game_type == 'R')
        .filter(GameLog.games_started == 0)
        .all()
    )
    for log, pitcher in rows:
        item = eligible_pitchers.get(int(pitcher.id))
        if item is None:
            continue
        item['pitches'] += int(log.pitches_thrown or 0)
        item['innings_outs'] += int(log.innings_pitched_outs or 0)

    by_team = {}
    for item in eligible_pitchers.values():
        if item['pitches'] < WHAT_CHANGED_MEANINGFUL_WORKLOAD_PITCHES:
            continue
        team_key = str(item['team_id'])
        team = by_team.setdefault(team_key, {
            'team_id': item['team_id'],
            'team_name': item['team_name'],
            'team_abbreviation': item['team_abbreviation'],
            'workload_added': [],
        })
        team['workload_added'].append({
            'pitcher_id': item['pitcher_id'],
            'name': item['name'],
            'pitches': item['pitches'],
        })

    for team in by_team.values():
        team['workload_added'] = sorted(
            team['workload_added'],
            key=lambda row: (-int(row.get('pitches') or 0), str(row.get('name') or '').lower()),
        )[:WHAT_CHANGED_WORKLOAD_ADDED_LIMIT]

    base['by_team_id'] = by_team
    return base


def _eligible_records_for_rows(
    rows,
    availability_by_pitcher,
    include_stale=False,
    reference_date=None,
):
    """
    Convert (Pitcher, FatigueScore) rows into board records after applying the
    reusable bullpen eligibility filter.
    """
    ref = reference_date or product_current_date()
    contexts, roster_summary = eligible_bullpen_pitcher_contexts(
        [pitcher for pitcher, _score in rows],
        # Stale workload can still supply board visibility context. Role labels
        # below come from the bounded role authority, not this population helper.
        include_stale=True,
        include_inactive_context=include_stale,
        reference_date=ref,
    )
    contexts_by_pitcher = {
        context['pitcher'].id: context
        for context in contexts
    }
    logs_by_pitcher = role_logs_by_pitcher(
        [pitcher.id for pitcher, _score in rows],
        reference_date=ref,
    )

    records = []
    for pitcher, score in rows:
        context = contexts_by_pitcher.get(pitcher.id)
        if context is None:
            continue

        availability = availability_with_eligibility(
            availability_by_pitcher.get(pitcher.id),
            context['eligibility'],
            context['roster_status'],
        )
        role_record = {
            'pitcher': pitcher,
            'availability': availability,
            'eligibility': context['eligibility'],
            'roster_status': context['roster_status'],
        }
        role, labels = author_role_read_labels(role_record, logs_by_pitcher, ref)
        last_workload_appearance = last_workload_appearance_from_logs(context['logs'])
        records.append({
            'name': pitcher.full_name,
            'pitcher_id': pitcher.id,
            'fatigue_score': score.raw_score if score else None,
            'availability': availability,
            'last_appearance': last_workload_appearance,
            'last_workload_appearance': last_workload_appearance,
            'role': role,
            'pitcher_labels': labels,
            'eligibility': context['eligibility'],
            'roster_status': context['roster_status'],
            'visibility': build_visibility_contract(
                context['eligibility'],
                context['roster_status'],
                context['logs'],
                ref,
            ),
            'pitcher': pitcher,
        })
    return records, roster_summary


def _board_records_from_authority_records(authority_records, reference_date=None):
    """
    Convert governed current-availability records into board presentation rows.

    The board's default availability cards must come from the same scored,
    bullpen-eligible authority as the dashboard. Unscored pitchers are not
    availability-classifiable and are intentionally not adapted here.
    """
    ref = reference_date or product_current_date()
    records = list(authority_records or [])
    pitcher_ids = [
        record['pitcher'].id
        for record in records
        if record.get('pitcher') is not None
    ]
    logs_by_pitcher = role_logs_by_pitcher(
        pitcher_ids,
        reference_date=ref,
    )

    board_records = []
    for record in records:
        pitcher = record.get('pitcher')
        score = record.get('score')
        if pitcher is None or score is None:
            continue
        role, labels = author_role_read_labels(record, logs_by_pitcher, ref)
        last_workload_appearance = last_workload_appearance_from_logs(
            logs_by_pitcher.get(pitcher.id, [])
        )
        board_records.append({
            'name': pitcher.full_name,
            'pitcher_id': pitcher.id,
            'fatigue_score': score.raw_score,
            'availability': record.get('availability'),
            'last_appearance': last_workload_appearance,
            'last_workload_appearance': last_workload_appearance,
            'role': role,
            'pitcher_labels': labels,
            'eligibility': record.get('eligibility'),
            'roster_status': record.get('roster_status'),
            'visibility': record.get('visibility'),
            'pitcher': pitcher,
        })
    return board_records, logs_by_pitcher


def _inactive_context_records(records, authority_pitcher_ids):
    """
    Keep expanded roster-status context without widening availability membership.
    """
    authority_pitcher_ids = set(authority_pitcher_ids or [])
    context = []
    for record in records:
        pitcher_id = record.get('pitcher_id')
        if pitcher_id in authority_pitcher_ids:
            continue
        visibility = record.get('visibility') or {}
        if visibility.get('is_visible_by_default'):
            continue
        if not visibility.get('is_unavailable_roster_status'):
            continue
        if record.get('fatigue_score') is None:
            continue
        context.append(record)
    return context


def _build_team_board(team_id, include_stale=False, freshness=None, reference_date=None):
    """
    Build a Tonight's Bullpen Board payload for one team.

    Shared by the board route and the comparison route so both consume the exact
    same grouped/context output and the same observed-usage-role classification
    (built once here, no duplicate availability or role calculation).
    """
    freshness = freshness or _board_freshness_block()
    ref = reference_date or _public_availability_reference_date(freshness)

    scored_rows = availability_latest_fatigue_rows(
        team_id=team_id,
        calculated_at_lte=_served_score_cutoff(),
    )
    authority_records = current_availability_records(
        scored_rows,
        reference_date=ref,
    )
    records, logs_by_pitcher = _board_records_from_authority_records(
        authority_records,
        reference_date=ref,
    )
    authority_pitcher_ids = {
        record['pitcher_id']
        for record in records
    }

    context_rows, availability_by_pitcher = _team_bullpen_rows(
        team_id,
        include_stale,
        reference_date=ref,
        calculated_at_lte=_served_score_cutoff(),
    )

    team_info = None
    context_records, roster_summary = _eligible_records_for_rows(
        context_rows,
        availability_by_pitcher,
        include_stale=include_stale,
        reference_date=ref,
    )
    capacity_records, _capacity_roster_summary = _eligible_records_for_rows(
        context_rows,
        availability_by_pitcher,
        include_stale=True,
        reference_date=ref,
    )
    if include_stale:
        records.extend(_inactive_context_records(
            context_records,
            authority_pitcher_ids,
        ))

    for record in authority_records:
        pitcher = record.get('pitcher')
        if pitcher is None:
            continue
        if team_info is None:
            team_info = {
                'team_id': pitcher.team_id,
                'team_name': pitcher.team_name,
                'team_abbreviation': pitcher.team_abbreviation,
            }
    for pitcher, _score in context_rows:
        if team_info is None:
            team_info = {
                'team_id': pitcher.team_id,
                'team_name': pitcher.team_name,
                'team_abbreviation': pitcher.team_abbreviation,
            }

    if team_info is None:
        team_info = _team_info_lookup(team_id)

    limitations = _merge_limitations(
        freshness.get('limitations'),
        roster_summary.get('limitations'),
    )
    workload_concentration = summarize_recent_relief_workload(
        logs_by_pitcher,
        ref,
        pitcher_ids=authority_pitcher_ids,
    )
    capacity_intelligence = _capacity_intelligence_for_records(
        team_info,
        capacity_records,
        ref,
    )
    rotation_support_pressure = _rotation_support_for_team(
        team_info,
        ref,
    )
    bullpen_stability = _bullpen_stability_for_records(
        team_info,
        capacity_records,
        ref,
    )
    bullpen_environment = _bullpen_environment_for_reads(
        team_info,
        capacity_intelligence,
        rotation_support_pressure,
        bullpen_stability,
    )
    return build_board_payload(
        team=team_info,
        records=records,
        freshness=freshness,
        limitations=limitations,
        roster_status=roster_summary,
        workload_concentration=workload_concentration,
        capacity_intelligence=capacity_intelligence,
        rotation_support_pressure=rotation_support_pressure,
        bullpen_stability=bullpen_stability,
        bullpen_environment=bullpen_environment,
    )


@bullpen_bp.route('/teams/<int:team_id>/board', methods=['GET'])
def get_team_bullpen_board(team_id):
    """
    Tonight's Bullpen Board — existing availability classifications grouped for a
    coach-facing read of "what does this bullpen look like tonight?".

    Presentation only: no ranking, no selection, no recommendation, no
    prediction. Reuses the same query and Availability Engine V1 output as the
    bullpen overview, groups pitchers by availability status, and orders them
    alphabetically within each group.

    Optional query params:
      - include_stale: include stale workload pitchers and roster-status
                       context. Default false.
    """
    include_stale = _truthy(request.args.get('include_stale'))
    return jsonify(_build_team_board(team_id, include_stale))


@bullpen_bp.route('/teams/<int:team_id>/changes', methods=['GET'])
def get_team_changes(team_id):
    """
    What Changed Since Last Game — small followed-team change surface.

    Compares current team bullpen state to the previous completed game date
    using stored game logs, fatigue-score history, existing availability
    classification, and durable sync freshness. Presentation only: no ranking,
    no selection, no recommendation, and no prediction.
    """
    freshness = _board_freshness_block()
    return jsonify(build_team_changes_payload(team_id, freshness=freshness))


def _story_as_of_date_from_request():
    raw = request.args.get('as_of_date')
    if raw in (None, ''):
        return None, None
    parsed = parse_reference_date(raw)
    if parsed is None:
        return None, QueryParamError(
            'as_of_date',
            'as_of_date must be an ISO date in YYYY-MM-DD format.',
        )
    return parsed, None


def _story_api_payload(service_payload):
    payload = service_payload or {}
    written = payload.get('written_story') or {}
    selected = payload.get('selected_observation') or {}
    frame = payload.get('construction_frame') or {}
    internal_story_type = selected.get('type') or frame.get('observation_type')
    story_type = (
        payload.get('story_type')
        or (payload.get('public_story_beat') or {}).get('story_type')
        or public_beat_for_observation(internal_story_type, frame=frame)
    )
    story_available = bool(payload.get('story_available') is True)
    return {
        'capability': 'story_intelligence_api_v1',
        'contract': 'story_intelligence_api_v1',
        'contract_state': 'available' if story_available else 'neutral',
        'team_id': payload.get('team_id'),
        'team_name': payload.get('team_name'),
        'team_abbreviation': payload.get('team_abbreviation'),
        'as_of_date': payload.get('as_of_date'),
        'state': payload.get('state'),
        'story_available': story_available,
        'neutral_reason': payload.get('neutral_reason'),
        'story_type': story_type,
        'headline': written.get('headline'),
        'observation': written.get('observation_paragraph'),
        'baseline': written.get('baseline_paragraph'),
        'cause': written.get('cause_paragraph'),
        'constraint': written.get('constraint_paragraph'),
        'freshness': payload.get('freshness') or {},
        'trust_metadata': payload.get('trust_metadata') or {},
        'supporting_context': payload.get('supporting_context') or {},
        'selected_observation': selected or None,
        'construction_frame': frame or None,
        'limitations': list(payload.get('limitations') or []),
    }


@bullpen_bp.route('/teams/<int:team_id>/story', methods=['GET'])
def get_team_story(team_id):
    if team_id < 1:
        return query_param_error_response(
            QueryParamError('team_id', 'team_id must be at least 1.')
        )
    as_of_date, error = _story_as_of_date_from_request()
    if error:
        return query_param_error_response(error)
    return jsonify(_story_api_payload(
        build_story_intelligence_team_story(team_id, as_of_date=as_of_date)
    ))


@bullpen_bp.route('/teams/compare', methods=['GET'])
def compare_team_bullpens():
    """
    Team Bullpen Comparison — descriptive side-by-side of two team bullpens.

    Aggregates two existing board payloads (V1 groups + V2 team context) into a
    transparent count comparison answering "which bullpen appears more available
    tonight?". No team ranking, grading, scoring, matchup, or recommendation —
    every observation shows both raw counts.

    Required query params:
      - team_a, team_b: team ids to compare.
    Optional:
      - include_stale: include stale workload pitchers and roster-status context.
    """
    team_a, error = parse_positive_int_param(request.args, 'team_a')
    if error:
        return query_param_error_response(error)
    team_b, error = parse_positive_int_param(request.args, 'team_b')
    if error:
        return query_param_error_response(error)
    if team_a is None or team_b is None:
        return query_param_error_response(
            QueryParamError('team_a', 'team_a and team_b query parameters are required.')
        )

    include_stale = _truthy(request.args.get('include_stale'))
    # One freshness read shared by both boards — it is system-wide, not per-team.
    freshness = _board_freshness_block()
    board_a = _build_team_board(team_a, include_stale, freshness=freshness)
    board_b = _build_team_board(team_b, include_stale, freshness=freshness)

    comparison = build_team_comparison(
        board_a,
        board_b,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )

    return jsonify({
        'capability': 'team_bullpen_comparison',
        'generated_at': comparison['generated_at'],
        'ranking_applied': False,
        'selection_made': False,
        'team_a': board_a,
        'team_b': board_b,
        'comparison': comparison,
    })


# ─── Narrative Memory diagnostic (read-only) ─────────────────────────────────

def _diagnostic_error(message, status_code=400, reason_code='invalid_request'):
    return jsonify({
        'status': 'error',
        'reason_code': reason_code,
        'message': message,
    }), status_code


def _optional_int_arg(name):
    value, error = parse_positive_int_param(request.args, name)
    if error:
        return None, error.message
    return value, None


def _diagnostic_window_days():
    raw = request.args.get('window_days')
    if raw in (None, ''):
        return 10, None
    try:
        days = int(raw)
    except (TypeError, ValueError):
        return None, 'window_days must be one of 7, 10, or 14.'
    if days not in NARRATIVE_MEMORY_WINDOWS:
        return None, 'window_days must be one of 7, 10, or 14.'
    return days, None


def _max_data_through(results):
    dates = [
        result.get('data_through_date')
        for result in results or []
        if result.get('data_through_date')
    ]
    return max(dates) if dates else None


def _canonical_story_team_descriptors(landscape):
    """Ordered team descriptors for the canonical story feed.

    Built from the landscape buckets (constrained, then monitoring, then
    available), de-duplicated in that priority order.
    """
    descriptors = []
    seen = set()

    for key in ('constrained_bullpens', 'monitoring_concentration', 'available_bullpens'):
        for entry in (landscape or {}).get(key) or []:
            team_id = entry.get('team_id')
            if team_id is None or team_id in seen:
                continue
            seen.add(team_id)
            descriptors.append({
                'team_id': team_id,
                'team_name': entry.get('team_name'),
                'team_abbreviation': entry.get('team_abbreviation'),
            })
    return descriptors


def _canonical_league_signal(landscape, availability_records):
    """League-wide availability counts for the canonical feed's league context.

    Counts come from the already-built landscape buckets and the classified
    availability records; no new computation or day-over-day trend is invented.
    """
    landscape = landscape or {}
    team_ids = set()
    for record in availability_records or []:
        pitcher = record['pitcher'] if isinstance(record, dict) and 'pitcher' in record else None
        team_id = getattr(pitcher, 'team_id', None)
        if team_id is not None:
            team_ids.add(team_id)
    return {
        'team_count': len(team_ids),
        'constrained_team_count': len(landscape.get('constrained_bullpens') or []),
        'available_team_count': len(landscape.get('available_bullpens') or []),
        'monitoring_team_count': len(landscape.get('monitoring_concentration') or []),
        'availability_trend': None,
    }


def _canonical_prior_story_items(previous_payload):
    """Prior snapshot's canonical story items, the baseline for continuity.

    Returns an empty list when the prior snapshot predates the canonical feed,
    so continuity falls back to a truthful "no prior story" read.
    """
    stories = (previous_payload or {}).get('stories') or {}
    items = stories.get('items')
    return items if isinstance(items, list) else []


def _canonical_prior_league_context(previous_payload):
    stories = (previous_payload or {}).get('stories') or {}
    context = stories.get('league_context')
    return context if isinstance(context, dict) else None


def _diagnostic_team_exists(team_id):
    return (
        db.session.query(Pitcher.id)
        .filter(Pitcher.team_id == team_id)
        .first()
        is not None
    )


def _diagnostic_team_sample(limit=NARRATIVE_MEMORY_DIAGNOSTIC_SAMPLE_CAP):
    rows = (
        db.session.query(Pitcher.team_id)
        .join(GameLog, GameLog.pitcher_id == Pitcher.id)
        .filter(Pitcher.active == True, Pitcher.team_id.isnot(None))
        .distinct()
        .order_by(Pitcher.team_id)
        .limit(limit)
        .all()
    )
    return [row[0] for row in rows if row[0] is not None]


def _diagnostic_team_results(team_id, window_days):
    team = _team_info_lookup(team_id)
    return [
        {
            'result_type': 'team_workload_concentration',
            'team': team,
            **build_team_workload_concentration_continuity(
                team_id,
                window_days=window_days,
            ),
        },
        {
            'result_type': 'team_workload_easing',
            'team': team,
            **build_team_bullpen_recovery_continuity(
                team_id,
                window_days=window_days,
            ),
        },
    ]


def _diagnostic_pitcher_info(pitcher):
    return {
        'pitcher_id': pitcher.id,
        'pitcher_name': pitcher.full_name,
        'team_id': pitcher.team_id,
        'team_name': pitcher.team_name,
        'team_abbreviation': pitcher.team_abbreviation,
    }


def _diagnostic_payload(mode, window_days, results, limitations=None, extra=None):
    payload = {
        'status': 'ok',
        'capability': 'narrative_memory_v1_diagnostic',
        'mode': mode,
        'window_days': window_days,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'data_through_date': _max_data_through(results),
        'results': results,
        'limitations': _merge_limitations(
            ['Internal diagnostic evidence only; no editorial continuity decision is made.'],
            limitations,
        ),
    }
    if extra:
        payload.update(extra)
    return payload


@bullpen_bp.route('/narrative-memory/diagnostic', methods=['GET'])
def get_narrative_memory_diagnostic():
    """
    Internal/read-only Narrative Memory V1 diagnostic.

    Exposes stored-workload continuity evidence so real team output can be
    reviewed before any product surface consumes it. No stories are persisted,
    selected, ranked, archived, or threaded by this route.

    Optional query params:
      - team_id: return team continuity evidence.
      - pitcher_id: return pitcher usage trend evidence. If team_id is omitted,
                    the pitcher's current team_id anchors observed team games.
      - window_days: 7, 10, or 14. Default 10.
    """
    window_days, window_error = _diagnostic_window_days()
    if window_error:
        return _diagnostic_error(window_error)

    team_id, team_error = _optional_int_arg('team_id')
    if team_error:
        return _diagnostic_error(team_error)
    pitcher_id, pitcher_error = _optional_int_arg('pitcher_id')
    if pitcher_error:
        return _diagnostic_error(pitcher_error)

    if pitcher_id is not None:
        pitcher = db.session.get(Pitcher, pitcher_id)
        if pitcher is None:
            return _diagnostic_error(
                f'pitcher_id {pitcher_id} was not found.',
                status_code=404,
                reason_code='pitcher_not_found',
            )
        anchor_team_id = team_id if team_id is not None else pitcher.team_id
        if anchor_team_id is None:
            return _diagnostic_error(
                'pitcher_id requires a team_id when the pitcher has no current team assignment.',
                status_code=422,
                reason_code='team_assignment_missing',
            )
        if team_id is not None and pitcher.team_id is not None and pitcher.team_id != team_id:
            return _diagnostic_error(
                'pitcher_id is not currently assigned to the requested team_id.',
                status_code=422,
                reason_code='pitcher_team_mismatch',
            )
        if not _diagnostic_team_exists(anchor_team_id):
            return _diagnostic_error(
                f'team_id {anchor_team_id} was not found.',
                status_code=404,
                reason_code='team_not_found',
            )

        result = {
            'result_type': 'pitcher_usage_trend',
            'team': _team_info_lookup(anchor_team_id),
            'pitcher': _diagnostic_pitcher_info(pitcher),
            **build_team_pitcher_usage_trend_continuity(
                anchor_team_id,
                pitcher_id,
                window_days=window_days,
            ),
        }
        return jsonify(_diagnostic_payload(
            mode='pitcher',
            window_days=window_days,
            results=[result],
            limitations=['Pitcher frequency uses observed stored team bullpen games, not a complete schedule.'],
            extra={'team_id': anchor_team_id, 'pitcher_id': pitcher_id},
        ))

    if team_id is not None:
        if not _diagnostic_team_exists(team_id):
            return _diagnostic_error(
                f'team_id {team_id} was not found.',
                status_code=404,
                reason_code='team_not_found',
            )
        results = _diagnostic_team_results(team_id, window_days)
        return jsonify(_diagnostic_payload(
            mode='team',
            window_days=window_days,
            results=results,
            limitations=['Team evidence uses pitchers currently assigned to the team.'],
            extra={'team_id': team_id},
        ))

    sample_team_ids = _diagnostic_team_sample()
    results = []
    for sampled_team_id in sample_team_ids:
        results.extend(_diagnostic_team_results(sampled_team_id, window_days))

    limitations = [
        f'Default league diagnostic is capped at {NARRATIVE_MEMORY_DIAGNOSTIC_SAMPLE_CAP} teams.',
    ]
    if not sample_team_ids:
        limitations.append('No teams with stored workload history were found for the diagnostic sample.')

    return jsonify(_diagnostic_payload(
        mode='league_sample',
        window_days=window_days,
        results=results,
        limitations=limitations,
        extra={
            'sample_cap': NARRATIVE_MEMORY_DIAGNOSTIC_SAMPLE_CAP,
            'sampled_team_ids': sample_team_ids,
        },
    ))


# ─── Bullpen Context diagnostic (read-only foundation) ────────────────────────

def _context_diagnostic_payload(mode, results, limitations=None, extra=None):
    payload = {
        'status': 'ok',
        'capability': 'bullpen_context_engine_v1_diagnostic',
        'mode': mode,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'data_through_date': _max_data_through(results),
        'results': results,
        'limitations': _merge_limitations(
            BULLPEN_CONTEXT_LIMITATIONS,
            ['Internal diagnostic evidence only; no product rendering or story integration is made.'],
            limitations,
        ),
    }
    if extra:
        payload.update(extra)
    return payload


@bullpen_bp.route('/context/diagnostic', methods=['GET'])
def get_bullpen_context_diagnostic():
    """
    Internal/read-only Bullpen Context Engine V1 foundation diagnostic.

    Exposes stored evidence for why a bullpen state might be happening, without
    changing observations, rankings, suppression, story selection, or UI output.

    Optional query params:
      - mode: league_sample (default) or team.
      - team_id: required for team mode.
    """
    team_id, team_error = _optional_int_arg('team_id')
    if team_error:
        return _diagnostic_error(team_error)

    raw_mode = (request.args.get('mode') or '').strip().lower()
    mode = raw_mode or ('team' if team_id is not None else 'league_sample')
    if mode not in ('league_sample', 'team'):
        return _diagnostic_error(
            'mode must be league_sample or team.',
            reason_code='invalid_mode',
        )

    if mode == 'team':
        if team_id is None:
            return _diagnostic_error(
                'team_id is required when mode=team.',
                reason_code='team_id_required',
            )
        if not _diagnostic_team_exists(team_id):
            return _diagnostic_error(
                f'team_id {team_id} was not found.',
                status_code=404,
                reason_code='team_not_found',
            )
        result = build_team_bullpen_context(team_id)
        return jsonify(_context_diagnostic_payload(
            mode='team',
            results=[result],
            limitations=['Team context evidence uses stored GameLog rows for the current team assignment.'],
            extra={'team_id': team_id},
        ))

    if team_id is not None:
        return _diagnostic_error(
            'team_id can only be used when mode=team.',
            reason_code='team_id_mode_mismatch',
        )

    sampled_team_ids = sample_bullpen_context_team_ids(limit=BULLPEN_CONTEXT_SAMPLE_CAP)
    results = build_league_sample_bullpen_context(limit=BULLPEN_CONTEXT_SAMPLE_CAP)
    limitations = [f'Default league diagnostic is capped at {BULLPEN_CONTEXT_SAMPLE_CAP} teams.']
    if not sampled_team_ids:
        limitations.append('No teams with stored game-log context were found for the diagnostic sample.')

    return jsonify(_context_diagnostic_payload(
        mode='league_sample',
        results=results,
        limitations=limitations,
        extra={
            'sample_cap': BULLPEN_CONTEXT_SAMPLE_CAP,
            'sampled_team_ids': sampled_team_ids,
        },
    ))


# ─── Role Authority diagnostic (read-only) ────────────────────────────────────

@bullpen_bp.route('/role-authority/diagnostic', methods=['GET'])
def get_role_authority_diagnostic():
    """
    Read-only comparison of the legacy innings-based bullpen population vs. the
    Role Authority population. Changes no live behavior — it exists so the
    population shift can be audited (additions, removals, role and confidence
    distributions) before/while role authority drives the surfaces.

    Optional query params:
      - team_id: scope to one team (default: all active pitchers).
      - include_stale: widen the usage window and surface Unknown roles.
    """
    team_id, error = parse_positive_int_param(request.args, 'team_id')
    if error:
        return query_param_error_response(error)
    include_stale = _truthy(request.args.get('include_stale'))

    query = Pitcher.query.filter(Pitcher.active == True)
    if team_id is not None:
        query = query.filter(Pitcher.team_id == team_id)
    pitchers = query.order_by(Pitcher.full_name).all()

    diagnostic = population_diagnostic(pitchers, include_stale=include_stale)
    return jsonify({
        'capability': 'role_authority_diagnostic',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'team_id': team_id,
        'include_stale': include_stale,
        **diagnostic,
    })


# ─── Stats & Aggregates ───────────────────────────────────────────────────────

@bullpen_bp.route('/stats/overview', methods=['GET'])
def get_stats_overview():
    """Dashboard overview stats."""
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is not None and isinstance(snapshot.payload, dict):
        overview = (snapshot.payload or {}).get('stats_overview')
        if isinstance(overview, dict):
            return jsonify(dict(overview))

    total_pitchers = Pitcher.query.filter_by(active=True).count()
    total_logs     = GameLog.query.count()
    freshness = _board_freshness_block()
    reference_date = _public_availability_reference_date(freshness)

    latest_rows = availability_latest_fatigue_rows()
    latest_scores = [score for score, _pitcher in latest_rows]
    availability_records = classify_latest_fatigue_rows(
        latest_rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )

    risk_breakdown = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'CRITICAL': 0}
    for score in latest_scores:
        if score.risk_level in risk_breakdown:
            risk_breakdown[score.risk_level] += 1

    avg_fatigue = (
        sum(s.raw_score for s in latest_scores) / len(latest_scores)
        if latest_scores else 0
    )

    inventory_summary = summarize_scored_pitcher_inventory(availability_records)

    return jsonify({
        'total_pitchers':    total_pitchers,
        'total_game_logs':   total_logs,
        'risk_breakdown':    risk_breakdown,
        'avg_fatigue_score': round(float(avg_fatigue), 1),
        'scored_pitchers':   len(latest_scores),
        'scored_pitcher_inventory': inventory_summary,
    })


def build_bullpen_dashboard_payload(*, use_published_freshness=False):
    """
    League-wide bullpen overview for the landing dashboard.

    Reuses existing systems only — Availability Engine V1 (availability summary),
    the V2 Team Context Layer (bullpen health), bullpen eligibility filtering,
    and the usage-role classifier — aggregated across bullpen-eligible scored
    pitchers. Presentation/context only:
    no ranking, selection, recommendation, or prediction.
    """
    freshness = _board_freshness_block(use_published=use_published_freshness)
    reference_date = _public_availability_reference_date(freshness)
    latest_rows = availability_latest_fatigue_rows()
    inventory_records = classify_latest_fatigue_rows(
        latest_rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    availability_records = current_availability_records(
        latest_rows,
        reference_date=reference_date,
    )
    summary = summarize_availability_records(availability_records)
    status_counts = summary.get('statuses') or {}
    groups = [
        {'status': status, 'count': int(status_counts.get(status, 0))}
        for status in BOARD_GROUP_ORDER
    ]

    context = build_team_context(groups, freshness=freshness)

    # Usage-role composition across the same bullpen-eligible scored-pitcher set.
    pitcher_ids = [record['pitcher'].id for record in availability_records]
    logs_by_pitcher = role_logs_by_pitcher(
        pitcher_ids,
        reference_date=reference_date,
    )
    role_counts = {key: 0 for key in ROLE_KEYS}
    for record in availability_records:
        role, _labels = author_role_read_labels(record, logs_by_pitcher, reference_date)
        key = role['role_key']
        role_counts[key] = role_counts.get(key, 0) + 1

    # Tonight's Bullpen Landscape — league orientation, reusing the records we
    # already classified above (no extra availability pass).
    landscape = build_landscape(
        records=availability_records,
        reference_date=reference_date,
        freshness=freshness,
    )
    injury_il_context = build_injury_il_context_payload(
        pitchers=[pitcher for _score, pitcher in latest_rows],
        availability_records=availability_records,
        reference_date=reference_date,
    )
    season_era = build_season_era_payload(
        availability_records,
        reference_date=reference_date,
    )
    capacity_intelligence = _dashboard_capacity_payload(reference_date)
    capacity_by_team = {
        int(team_id): item
        for team_id, item in (capacity_intelligence.get('by_team_id') or {}).items()
    }
    rotation_support_pressure = _dashboard_rotation_support_payload(reference_date)
    rotation_support_by_team = {
        int(team_id): item
        for team_id, item in (rotation_support_pressure.get('by_team_id') or {}).items()
    }
    bullpen_stability = _dashboard_bullpen_stability_payload(reference_date)
    bullpen_stability_by_team = {
        int(team_id): item
        for team_id, item in (bullpen_stability.get('by_team_id') or {}).items()
    }
    bullpen_environment = _dashboard_bullpen_environment_payload(
        capacity_intelligence,
        rotation_support_pressure,
        bullpen_stability,
    )
    bullpen_environment_by_team = {
        int(team_id): item
        for team_id, item in (bullpen_environment.get('by_team_id') or {}).items()
    }
    latest_scores = [score for score, _pitcher in latest_rows]
    risk_breakdown = {'LOW': 0, 'MODERATE': 0, 'HIGH': 0, 'CRITICAL': 0}
    for score in latest_scores:
        if score.risk_level in risk_breakdown:
            risk_breakdown[score.risk_level] += 1
    avg_fatigue = (
        sum(score.raw_score for score in latest_scores) / len(latest_scores)
        if latest_scores else 0
    )
    inventory_summary = summarize_scored_pitcher_inventory(inventory_records)
    stats_overview = {
        'total_pitchers': Pitcher.query.filter_by(active=True).count(),
        'total_game_logs': GameLog.query.count(),
        'risk_breakdown': risk_breakdown,
        'avg_fatigue_score': round(float(avg_fatigue), 1),
        'scored_pitchers': len(latest_scores),
        'scored_pitcher_inventory': inventory_summary,
    }

    # League-wide baseline distributions (Baseline Intelligence infrastructure).
    # Built from the league-wide records and relief logs already in hand; this is
    # backend-only and is not consumed by any UI or story surface yet.
    baseline_team_pitcher_ids = {}
    for record in availability_records:
        record_pitcher = record['pitcher']
        record_team_id = getattr(record_pitcher, 'team_id', None)
        if record_team_id is None:
            continue
        baseline_team_pitcher_ids.setdefault(int(record_team_id), []).append(record_pitcher.id)
    baselines = build_baseline_payload({
        WORKLOAD_CONCENTRATION_BASELINE_FAMILY: build_workload_concentration_baselines(
            league_relief_workload_by_team(
                baseline_team_pitcher_ids, logs_by_pitcher, reference_date,
            )
        ),
    })

    payload = {
        'capability': 'bullpen_dashboard',
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': CURRENT_AVAILABILITY_SCOPE,
        'context': context,
        'roles': {
            'order': list(ROLE_KEYS),
            'counts': role_counts,
            'total': len(pitcher_ids),
        },
        'landscape': landscape,
        'injury_il_context': injury_il_context,
        'capacity_intelligence': capacity_intelligence,
        'rotation_support_pressure': rotation_support_pressure,
        'bullpen_stability': bullpen_stability,
        'bullpen_environment': bullpen_environment,
        'season_era': season_era,
        'freshness': freshness,
        'availability_summary': summary,
        'scored_pitcher_inventory': inventory_summary,
        'stats_overview': stats_overview,
        'baselines': baselines,
    }
    # Prior dashboard snapshot — the comparison baseline for canonical story
    # continuity and the "what changed" surfaces. Fetched once and reused below.
    data_through = parse_reference_date(
        freshness.get('data_through')
        or freshness.get('latest_workload_date')
    )
    previous_snapshot = dashboard_snapshot_service.get_latest_dashboard_snapshot_before(data_through)
    previous_payload = previous_snapshot.payload if previous_snapshot is not None else None
    previous_data_through = _dashboard_payload_data_through(previous_payload)

    # Canonical story feed (additive). Wraps Story Intelligence V1 per team into
    # the forward-facing canonical contract, with continuity keyed to the prior
    # snapshot's canonical stories. Legacy story fields above are untouched.
    payload['stories'] = build_canonical_story_feed(
        _canonical_story_team_descriptors(landscape),
        as_of_date=reference_date,
        story_builder=build_story_intelligence_team_story,
        freshness=freshness,
        league_signal=_canonical_league_signal(landscape, availability_records),
        prior_stories=_canonical_prior_story_items(previous_payload),
        prior_league_context=_canonical_prior_league_context(previous_payload),
    )
    payload['what_changed_workload'] = _dashboard_what_changed_workload_payload(
        data_through,
        previous_data_through,
        availability_records,
    )
    payload['role_change_detection'] = build_role_change_detection_payload(
        payload,
        _latest_comparable_role_change_payload(
            data_through,
            immediate_prior_snapshot=previous_snapshot,
        ),
    )
    changes = build_what_changed_public_payload(
        payload,
        previous_payload,
        limit=WHAT_CHANGED_PUBLIC_TEAM_LIMIT,
    )
    if changes['items']:
        payload['what_changed_since_yesterday'] = changes

    return payload


def _dashboard_payload_with_snapshot_metadata(payload, served_from, snapshot=None):
    result = dict(payload or {})
    if snapshot is not None:
        freshness = dict(result.get('freshness') or {})
        overlay = _published_snapshot_overlay(snapshot)
        if overlay:
            reason_codes = list(freshness.get('reason_codes') or [])
            limitations = list(freshness.get('limitations') or [])
            status = overlay.get('current_sync_status')
            if status == sync_metadata.STATUS_RUNNING:
                code = 'sync_in_progress_serving_previous_published_view'
                message = 'A sync is in progress; this is the last fully published view.'
            else:
                code = 'latest_sync_failed_serving_previous_published_view'
                message = 'The latest sync failed before publish; this is the last fully published view.'
            if code not in reason_codes:
                reason_codes.append(code)
            if message not in limitations:
                limitations.append(message)
            freshness.update(overlay)
            freshness['reason_codes'] = reason_codes
            freshness['limitations'] = limitations
            result['freshness'] = freshness
    snapshot_generated_at = (
        snapshot.snapshot_generated_at.isoformat()
        if snapshot is not None and snapshot.snapshot_generated_at
        else result.get('generated_at')
    )
    result['snapshot'] = {
        'served_from': served_from,
        'snapshot_type': dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
        'snapshot_generated_at': snapshot_generated_at,
        'payload_version': dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION,
    }
    if snapshot is not None:
        result['snapshot'].update({
            'snapshot_id': snapshot.id,
            'sync_run_id': snapshot.sync_run_id,
            'is_published': bool(snapshot.is_published),
            'published_at': snapshot.published_at.isoformat() if snapshot.published_at else None,
            'data_through': snapshot.data_through.isoformat() if snapshot.data_through else None,
            'availability_reference_date': (
                snapshot.availability_reference_date.isoformat()
                if snapshot.availability_reference_date
                else None
            ),
        })
    return result


def _dashboard_live_fallback_enabled():
    if current_app.config.get('TESTING'):
        return True
    app_env = current_app.config.get('APP_ENV', 'development')
    if app_env != 'production':
        return True
    return _truthy(os.environ.get('DASHBOARD_LIVE_FALLBACK_ENABLED'))


def _dashboard_snapshot_unavailable_payload(reason):
    generated_at = datetime.now(timezone.utc).isoformat()
    return {
        'capability': 'bullpen_dashboard',
        'status': 'snapshot_unavailable',
        'reason': reason or 'dashboard_snapshot_unavailable',
        'generated_at': generated_at,
        'ranking_applied': False,
        'selection_made': False,
        'scope': CURRENT_AVAILABILITY_SCOPE,
        'context': {},
        'roles': {
            'order': list(ROLE_KEYS),
            'counts': {},
            'total': 0,
        },
        'landscape': {},
        'what_changed_since_yesterday': {
            'capability': 'what_changed_since_yesterday_public_v1',
            'ranking_applied': False,
            'selection_made': False,
            'prediction_applied': False,
            'ordering_basis': 'team_abbreviation_then_team_name',
            'item_limit': 6,
            'comparison': {
                'current_data_through': None,
                'previous_data_through': None,
                'comparison_available': False,
            },
            'items': [],
            'item_count': 0,
            'limitations': [
                'Dashboard snapshot is unavailable; production live fallback is disabled.',
            ],
        },
        'freshness': {
            'freshness_state': 'snapshot_unavailable',
            'is_current': False,
            'reason_codes': [reason or 'dashboard_snapshot_unavailable'],
            'limitations': [
                'Dashboard snapshot is unavailable; production live fallback is disabled.',
            ],
        },
        'availability_summary': {},
        'snapshot': {
            'served_from': 'snapshot_unavailable',
            'snapshot_type': dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
            'snapshot_generated_at': None,
            'payload_version': dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION,
            'reason': reason or 'dashboard_snapshot_unavailable',
        },
    }


def _dashboard_snapshot_build_token_from_request():
    authorization = request.headers.get('Authorization') or ''
    scheme, separator, token = authorization.partition(' ')
    if separator and scheme.lower() == 'bearer' and token.strip():
        return token.strip()
    return (request.headers.get(INTERNAL_TOKEN_HEADER) or '').strip()


def _dashboard_snapshot_build_token_error():
    expected = (os.environ.get(DASHBOARD_SNAPSHOT_BUILD_TOKEN_ENV) or '').strip()
    if not expected:
        current_app.logger.error(
            'Dashboard snapshot build endpoint disabled: %s is not configured.',
            DASHBOARD_SNAPSHOT_BUILD_TOKEN_ENV,
        )
        return jsonify({
            'status': 'error',
            'reason': 'dashboard_snapshot_build_token_not_configured',
        }), 503

    provided = _dashboard_snapshot_build_token_from_request()
    if not provided:
        return jsonify({
            'status': 'error',
            'reason': 'dashboard_snapshot_build_token_required',
        }), 401

    if not hmac.compare_digest(provided, expected):
        current_app.logger.warning(
            'Dashboard snapshot build rejected: invalid token supplied.'
        )
        return jsonify({
            'status': 'error',
            'reason': 'dashboard_snapshot_build_token_invalid',
        }), 403

    return None


def _dashboard_snapshot_build_response(result):
    snapshot = {
        'served_from': (
            'cache' if result.get('snapshot_served_by_dashboard') else 'pending'
        ),
        'snapshot_type': result.get('snapshot_type'),
        'snapshot_id': result.get('snapshot_id'),
        'sync_run_id': result.get('sync_run_id'),
        'payload_version': result.get('payload_version'),
        'data_through': result.get('data_through'),
        'availability_reference_date': result.get('availability_reference_date'),
        'snapshot_generated_at': result.get('snapshot_generated_at'),
    }
    return {
        'status': 'ok' if result.get('snapshot_served_by_dashboard') else 'pending',
        'snapshot': snapshot,
        'builder': {
            'source': result.get('source'),
            'duration_ms': result.get('duration_ms'),
            'snapshot_served_by_dashboard': result.get('snapshot_served_by_dashboard'),
        },
    }


@bullpen_bp.route('/dashboard/snapshot/build', methods=['POST'])
def build_dashboard_snapshot_endpoint():
    endpoint_started = perf_counter()
    current_app.logger.info('Dashboard snapshot build endpoint received request.')
    token_error = _dashboard_snapshot_build_token_error()
    if token_error is not None:
        status_code = (
            token_error[1]
            if isinstance(token_error, tuple) and len(token_error) > 1
            else None
        )
        current_app.logger.info(
            'Dashboard snapshot build endpoint rejected before build status_code=%s duration_ms=%.2f.',
            status_code,
            round((perf_counter() - endpoint_started) * 1000, 2),
        )
        return token_error

    try:
        result = dashboard_snapshot_service.build_bullpen_dashboard_snapshot_v2(
            source='protected_endpoint',
        )
    except Exception as exc:
        db.session.rollback()
        current_app.logger.exception(
            'Dashboard snapshot build endpoint crashed after %.2f ms.',
            round((perf_counter() - endpoint_started) * 1000, 2),
        )
        return jsonify({
            'status': 'error',
            'reason': 'dashboard_snapshot_build_failed',
        }), 500

    if result.get('status') == 'failed':
        current_app.logger.warning(
            'Dashboard snapshot build endpoint produced non-servable snapshot: %s',
            result,
        )
        return jsonify({
            'status': 'error',
            'reason': result.get('reason') or 'snapshot_not_servable',
            'builder': result,
        }), 500

    status_code = 200 if result.get('snapshot_served_by_dashboard') else 202
    current_app.logger.info(
        'Dashboard snapshot build endpoint completed status=%s snapshot_id=%s http_status=%s duration_ms=%.2f.',
        result.get('status'),
        result.get('snapshot_id'),
        status_code,
        round((perf_counter() - endpoint_started) * 1000, 2),
    )
    return jsonify(_dashboard_snapshot_build_response(result)), status_code


@bullpen_bp.route('/dashboard', methods=['GET'])
def get_bullpen_dashboard():
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is not None:
        return jsonify(_dashboard_payload_with_snapshot_metadata(
            snapshot.payload,
            'cache',
            snapshot=snapshot,
        ))

    if not _dashboard_live_fallback_enabled():
        reason = dashboard_snapshot_service.latest_dashboard_snapshot_unavailable_reason()
        return jsonify(_dashboard_snapshot_unavailable_payload(reason))

    payload = build_bullpen_dashboard_payload()
    return jsonify(_dashboard_payload_with_snapshot_metadata(
        payload,
        'live_fallback',
    ))


@bullpen_bp.route('/landscape', methods=['GET'])
def get_bullpen_landscape():
    """
    Tonight's Bullpen Landscape — league-wide orientation: which bullpens are
    most constrained, most available, and carrying the most monitoring, plus a
    stored games-today anchor. Descriptive and deterministic; no ranking,
    selection, recommendation, or prediction.
    """
    snapshot = dashboard_snapshot_service.get_latest_valid_dashboard_snapshot()
    if snapshot is not None and isinstance(snapshot.payload, dict):
        landscape = (snapshot.payload or {}).get('landscape')
        if isinstance(landscape, dict):
            return jsonify(landscape)

    freshness = _board_freshness_block()
    reference_date = _public_availability_reference_date(freshness)
    records = current_availability_records(
        availability_latest_fatigue_rows(),
        reference_date=reference_date,
    )
    return jsonify(build_landscape(
        records=records,
        reference_date=reference_date,
        freshness=freshness,
    ))


@bullpen_bp.route('/teams/<int:team_id>/game-context', methods=['GET'])
def get_team_game_context(team_id):
    """
    Today's Game Context for one team, derived from stored game logs only (no
    live schedule call). Frames bullpen availability; not a scoreboard, matchup
    engine, or prediction. Home/away and scheduled time are reported as missing
    because the stored game log does not carry them.
    """
    freshness = _board_freshness_block()
    return jsonify(build_team_game_context(
        team_id,
        reference_date=_freshness_reference_date(freshness),
    ))


# ─── Insights ─────────────────────────────────────────────────────────────────

@bullpen_bp.route('/insights/fatigue-era', methods=['GET'])
def get_fatigue_era_insight():
    """
    Return precomputed fatigue → next-appearance ERA analysis.

    Reads backend/analysis/fatigue_era_results.json — generated by
    `python -m analysis.fatigue_era_analysis`. The script is intentionally
    run out-of-band (manually or as a future scheduled job) because it
    walks every reliever's full 2024-2025 history.
    """
    if not os.path.exists(FATIGUE_ERA_RESULTS_PATH):
        return jsonify({
            'status': 'not_generated',
            'message': 'Run the analysis script first',
        })

    try:
        with open(FATIGUE_ERA_RESULTS_PATH, 'r') as fh:
            return jsonify(json.load(fh))
    except (OSError, json.JSONDecodeError) as e:
        return jsonify({
            'status': 'error',
            'message': f'Failed to load analysis results: {str(e)}',
        }), 500


# ─── MLB API Passthrough ──────────────────────────────────────────────────────

@bullpen_bp.route('/mlb/teams', methods=['GET'])
def get_mlb_teams():
    """Proxy: Get all MLB teams from the Stats API."""
    try:
        teams = mlb_client.get_all_teams()
    except MlbApiFetchError as exc:
        return jsonify({
            'error': 'MLB Stats API fetch failed',
            'endpoint': exc.endpoint,
        }), 503
    return jsonify(teams)


@bullpen_bp.route('/mlb/pitcher/<int:player_id>/logs', methods=['GET'])
def get_mlb_pitcher_logs(player_id):
    """Proxy: Get live pitcher game logs from MLB Stats API."""
    season, error = parse_int_param(
        request.args,
        'season',
        minimum=MLB_SEASON_MIN,
        maximum=MLB_SEASON_MAX,
    )
    if error:
        return query_param_error_response(error)
    try:
        logs = mlb_client.get_pitcher_game_logs(player_id, season=season)
    except MlbApiFetchError as exc:
        return jsonify({
            'error': 'MLB Stats API fetch failed',
            'endpoint': exc.endpoint,
        }), 503
    return jsonify(logs)
