"""Single-lock intraday schedule and completed-game repair orchestration."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timezone

from services import intraday_reconcile, sync_metadata
from services.availability_reference_date import product_current_date
from services.game_finality import has_safe_final_status
from services.intraday_schedule_repair import (
    apply_intraday_schedule_findings,
    build_schedule_repair_scope,
)
from services.mlb_api import mlb_client
from services.sync_publication_proof import build_candidate_publication_proof
from utils.db import db


JOB_INTRADAY_COMPLETED_GAME_REPAIR = 'intraday_completed_game_repair'


class IntradayCompletedGameRepairError(RuntimeError):
    pass


def run_intraday_completed_game_repair(
    app,
    *,
    source=sync_metadata.SOURCE_GITHUB_ACTIONS,
    audit_runner=None,
    schedule_writer=None,
    completed_game_processor=None,
    fatigue_recalc=None,
    complete_with_snapshot=None,
    tonight_builder=None,
    today_builder=None,
    publication_proof_builder=None,
    client=None,
):
    """Repair proven schedule deltas and newly-final games under one writer lock."""
    from services import sync as sync_service
    from services.intelligence_surface_snapshot import generate_snapshot_for_date
    from services.tonight_intelligence_snapshot import generate_tonight_snapshot_for_date

    audit_runner = audit_runner or intraday_reconcile.run_intraday_audit
    schedule_writer = schedule_writer or apply_intraday_schedule_findings
    completed_game_processor = (
        completed_game_processor or sync_service.process_completed_game_for_postgame_refresh
    )
    fatigue_recalc = fatigue_recalc or sync_service.recalculate_all_fatigue
    complete_with_snapshot = complete_with_snapshot or sync_service.complete_sync_run_with_snapshot
    tonight_builder = tonight_builder or generate_tonight_snapshot_for_date
    today_builder = today_builder or generate_snapshot_for_date
    publication_proof_builder = publication_proof_builder or build_candidate_publication_proof
    client = client or mlb_client

    started_at = datetime.now(timezone.utc)
    result = {
        'status': sync_metadata.STATUS_FAILED,
        'job_name': JOB_INTRADAY_COMPLETED_GAME_REPAIR,
        'source': source,
        'started_at': started_at.isoformat(),
        'audit': None,
        'repair_scope': None,
        'schedule_repair': None,
        'completed_games': [],
        'new_logs_added': 0,
        'logs_corrected': 0,
        'pitchers_touched': 0,
        'fatigue_recalculated': None,
        'today_snapshot': None,
        'tonight_snapshot': None,
        'dashboard_snapshot_id': None,
        'publication_proof': None,
    }

    with app.app_context():
        audit = audit_runner(
            source=source,
            lanes=[intraday_reconcile.LANE_SCHEDULE_FINALITY],
        )
        result['audit'] = audit
        scope = build_schedule_repair_scope(audit)
        result['repair_scope'] = scope

        if scope['status'] == 'no_change':
            result['status'] = sync_metadata.STATUS_SUCCESS
            result['message'] = 'No governed intraday schedule changes detected.'
            return result
        if scope['status'] != 'ready':
            result['message'] = (
                'Intraday schedule changes were withheld because not every finding was safe.'
            )
            return result

        writer_guard = None
        sync_run_id = None
        try:
            writer_guard = sync_metadata.acquire_sync_writer_guard(
                job_name=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
                source=source,
            )
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
                job_name=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
            )

            sync_metadata.set_sync_stage(
                sync_run_id,
                sync_metadata.STAGE_SCHEDULE_FINALITY_PREFLIGHT,
            )
            schedule_result = schedule_writer(scope['repairable_findings'])
            result['schedule_repair'] = schedule_result
            db.session.commit()

            completed_games = _fetch_exact_completed_games(scope, client=client)
            if set(completed_games) != set(scope['completed_game_pks']):
                raise IntradayCompletedGameRepairError(
                    'Not every audited newly-final game remained safely final at write time.'
                )

            if completed_games:
                sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_LOG_INGESTION)
            for game_pk in sorted(completed_games):
                processed = completed_game_processor(
                    completed_games[game_pk],
                    schedule_date=_game_date(completed_games[game_pk]),
                    sync_run_id=sync_run_id,
                ) or {}
                result['completed_games'].append(_public_completed_game_summary(processed))
                _require_complete_processing(game_pk, processed)
                result['new_logs_added'] += int(processed.get('logs_added') or 0)
                result['logs_corrected'] += int(processed.get('logs_corrected') or 0)
                result['pitchers_touched'] += int(processed.get('pitchers_touched') or 0)
                db.session.commit()

            changed_workload = result['new_logs_added'] + result['logs_corrected'] > 0
            if completed_games:
                sync_metadata.set_sync_stage(
                    sync_run_id,
                    sync_metadata.STAGE_FATIGUE_RECALCULATION,
                )
                result['fatigue_recalculated'] = fatigue_recalc(
                    reference_date=product_current_date()
                )

            today = today_builder(
                product_current_date(),
                source=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
            )
            result['today_snapshot'] = _surface_summary(today)
            if (today or {}).get('status') not in ('ok', 'empty', 'generated'):
                raise IntradayCompletedGameRepairError(
                    'Today intelligence rebuild did not complete.'
                )

            tonight = tonight_builder(
                product_current_date(),
                source=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
            )
            result['tonight_snapshot'] = _surface_summary(tonight)
            if (tonight or {}).get('status') not in ('ok', 'empty'):
                raise IntradayCompletedGameRepairError(
                    'Tonight intelligence rebuild did not complete.'
                )

            run, snapshot = complete_with_snapshot(
                sync_run_id,
                final_status=sync_metadata.STATUS_SUCCESS,
                records_processed=(
                    int((schedule_result or {}).get('games_selected') or 0)
                    + result['new_logs_added']
                    + result['logs_corrected']
                ),
                records_failed=0,
                new_logs_added=result['new_logs_added'],
                pitchers_updated=result['pitchers_touched'],
                errors=0,
                api_calls_made=0,
                retries_used=0,
                source=source,
                started_at=started_at.replace(tzinfo=None),
                snapshot_source=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
                job_name=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
            )
            result['dashboard_snapshot_id'] = getattr(snapshot, 'id', None)
            proof = publication_proof_builder(
                result['dashboard_snapshot_id'],
                candidate_required=changed_workload or bool(scope['repairable_findings']),
            )
            result['publication_proof'] = proof
            if proof.get('verified') is not True:
                raise IntradayCompletedGameRepairError(
                    'Intraday completed-game dashboard candidate is not serving.'
                )

            result['status'] = sync_metadata.STATUS_SUCCESS
            result['sync_run_id'] = getattr(run, 'id', sync_run_id)
            result['message'] = (
                'Intraday schedule and completed-game repair published successfully.'
            )
            return result
        except sync_metadata.SyncWriterConflict as exc:
            db.session.rollback()
            result.update(exc.to_dict())
            result['job_name'] = JOB_INTRADAY_COMPLETED_GAME_REPAIR
            return result
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            result['error'] = str(exc)
            result['message'] = 'Intraday completed-game repair failed closed.'
            if sync_run_id is not None:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    errors=1,
                    error_message=str(exc),
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    job_name=JOB_INTRADAY_COMPLETED_GAME_REPAIR,
                    stage=sync_metadata.STAGE_FAILED,
                )
            return result
        finally:
            if writer_guard is not None:
                writer_guard.release()


def _require_complete_processing(game_pk, processed):
    if processed.get('skipped') and processed.get('reason') != 'already_processed':
        raise IntradayCompletedGameRepairError(
            f'Completed game {game_pk} was not safely processed.'
        )
    if processed.get('processing_status') not in (None, 'fully_processed'):
        raise IntradayCompletedGameRepairError(
            f'Completed game {game_pk} did not reach fully processed state.'
        )
    if int(processed.get('pitcher_resolution_failures') or 0):
        raise IntradayCompletedGameRepairError(
            f'Completed game {game_pk} had unresolved pitchers.'
        )
    if int(processed.get('correction_attempts_failed') or 0):
        raise IntradayCompletedGameRepairError(
            f'Completed game {game_pk} had failed corrections.'
        )


def _fetch_exact_completed_games(scope, *, client):
    required = set(scope.get('completed_game_pks') or [])
    if not required:
        return {}

    by_pk = defaultdict(list)
    for slate_date in scope.get('slate_dates') or []:
        for game in client.get_schedule(start_date=slate_date, end_date=slate_date) or []:
            game_pk = _positive_int((game or {}).get('gamePk'))
            if game_pk in required:
                by_pk[game_pk].append(game)

    selected = {}
    for game_pk in sorted(required):
        candidates = by_pk.get(game_pk) or []
        if not candidates:
            raise IntradayCompletedGameRepairError(
                f'Official schedule no longer contains completed game {game_pk}.'
            )
        if len({_game_signature(game) for game in candidates}) != 1:
            raise IntradayCompletedGameRepairError(
                f'Official schedule has conflicting completed-game rows for {game_pk}.'
            )
        game = candidates[0]
        if not has_safe_final_status(game):
            raise IntradayCompletedGameRepairError(
                f'Official schedule no longer proves game {game_pk} final.'
            )
        selected[game_pk] = game
    return selected


def _game_signature(game):
    status = (game or {}).get('status') or {}
    teams = (game or {}).get('teams') or {}
    return (
        _positive_int((game or {}).get('gamePk')),
        str((game or {}).get('officialDate') or '')[:10],
        _positive_int((((teams.get('home') or {}).get('team') or {}).get('id'))),
        _positive_int((((teams.get('away') or {}).get('team') or {}).get('id'))),
        str(status.get('statusCode') or ''),
        str(status.get('detailedState') or ''),
        str(status.get('abstractGameState') or ''),
    )


def _game_date(game):
    raw = (game or {}).get('officialDate') or str((game or {}).get('gameDate') or '')[:10]
    try:
        return date.fromisoformat(str(raw)[:10])
    except (TypeError, ValueError) as exc:
        raise IntradayCompletedGameRepairError(
            'Completed game lacks a valid official date.'
        ) from exc


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _surface_summary(payload):
    payload = payload or {}
    return {
        'status': payload.get('status'),
        'reference_date': payload.get('reference_date') or payload.get('slate_date'),
        'card_count': payload.get('card_count'),
        'snapshot_id': payload.get('snapshot_id'),
    }


def _public_completed_game_summary(payload):
    payload = payload or {}
    return {
        'game_pk': payload.get('game_pk'),
        'logs_added': int(payload.get('logs_added') or 0),
        'logs_corrected': int(payload.get('logs_corrected') or 0),
        'pitchers_touched': int(payload.get('pitchers_touched') or 0),
        'processing_status': payload.get('processing_status'),
        'incomplete_reason': payload.get('incomplete_reason'),
        'skipped': bool(payload.get('skipped')),
        'reason': payload.get('reason'),
    }
