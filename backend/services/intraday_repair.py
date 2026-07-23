"""Governed intraday repair for current active-bullpen membership.

The mature intraday audit remains the detection authority. This writer accepts
only findings that can be re-proven from MLB numeric identity under the public
writer lock. Conflicting or unresolved evidence is always withheld.
"""

from __future__ import annotations

from datetime import datetime, timezone

from services import intraday_reconcile, sync_metadata
from services.availability_reference_date import product_current_date
from services.sync_publication_proof import build_candidate_publication_proof
from utils.db import db


JOB_INTRADAY_REPAIR = 'intraday_repair'
ROSTER_STATUS_CHANGE_TYPES = frozenset({
    intraday_reconcile.CHANGE_RECALL,
    intraday_reconcile.CHANGE_IL_ACTIVATION,
    intraday_reconcile.CHANGE_REMOVED_FROM_ACTIVE_ROSTER,
    intraday_reconcile.CHANGE_OPTION,
    intraday_reconcile.CHANGE_IL_PLACEMENT,
    intraday_reconcile.CHANGE_DFA,
    intraday_reconcile.CHANGE_ROSTER_ACTIVATION,
    intraday_reconcile.CHANGE_ROSTER_DEACTIVATION,
    intraday_reconcile.CHANGE_ROSTER_STATUS_CHANGE,
})
IDENTITY_CHANGE_TYPES = frozenset({
    intraday_reconcile.CHANGE_TEAM_ASSIGNMENT_CHANGE,
    intraday_reconcile.CHANGE_NEWLY_DISCOVERED_ACTIVE,
})
UNSUPPORTED_CHANGE_TYPES = frozenset({
    intraday_reconcile.CHANGE_CONFLICTING_OFFICIAL_TEAM,
    intraday_reconcile.CHANGE_UNRESOLVED_SOURCE_IDENTITY,
})


def build_roster_repair_scope(audit: dict) -> dict:
    lane = (audit.get('lanes') or {}).get(intraday_reconcile.LANE_ROSTER_ASSIGNMENT) or {}
    differences = list(lane.get('differences') or [])
    if audit.get('status') != intraday_reconcile.STATUS_SUCCESS:
        return _blocked_scope('audit_not_successful', differences)
    if lane.get('verification_status') != intraday_reconcile.LANE_COMPLETE:
        return _blocked_scope('roster_lane_not_complete', differences)

    roster_findings = []
    identity_findings = []
    unsupported = []
    for finding in differences:
        if finding.get('severity') not in (None, intraday_reconcile.SEVERITY_ACTIONABLE):
            unsupported.append(finding)
            continue
        change_type = finding.get('change_type')
        if change_type in ROSTER_STATUS_CHANGE_TYPES and finding.get('stored_pitcher_id') is not None:
            roster_findings.append(finding)
        elif change_type in IDENTITY_CHANGE_TYPES:
            identity_findings.append(finding)
        elif change_type in UNSUPPORTED_CHANGE_TYPES:
            unsupported.append(finding)
        elif finding.get('bullpen_population_effect') != intraday_reconcile.EFFECT_NONE:
            unsupported.append(finding)

    repairable = roster_findings + identity_findings
    payload = {
        'status': 'blocked' if unsupported else ('ready' if repairable else 'no_change'),
        'reason': 'unsupported_public_roster_findings' if unsupported else None,
        'repairable_findings': repairable,
        'roster_status_findings': roster_findings,
        'identity_findings': identity_findings,
        'unsupported_findings': unsupported,
        'affected_team_ids': _affected_team_ids(repairable),
        'affected_pitcher_ids': _stored_pitcher_ids(repairable),
        'affected_pitcher_mlb_ids': _mlb_pitcher_ids(repairable),
    }
    return payload


def run_intraday_roster_repair(
    app,
    *,
    source=sync_metadata.SOURCE_GITHUB_ACTIONS,
    days_back=7,
    audit_runner=None,
    identity_repair=None,
    roster_sync=None,
    recent_log_sync=None,
    fatigue_recalc=None,
    complete_with_snapshot=None,
    tonight_builder=None,
    today_builder=None,
    publication_proof_builder=None,
):
    from services import sync as sync_service
    from services.intraday_identity_repair import apply_intraday_identity_findings
    from services.roster_status_sync import sync_roster_statuses
    from services.tonight_intelligence_snapshot import generate_tonight_snapshot_for_date
    from services.intelligence_surface_snapshot import generate_snapshot_for_date

    audit_runner = audit_runner or intraday_reconcile.run_intraday_audit
    identity_repair = identity_repair or apply_intraday_identity_findings
    roster_sync = roster_sync or sync_roster_statuses
    recent_log_sync = recent_log_sync or sync_service.sync_recent_logs
    fatigue_recalc = fatigue_recalc or sync_service.recalculate_all_fatigue
    complete_with_snapshot = complete_with_snapshot or sync_service.complete_sync_run_with_snapshot
    tonight_builder = tonight_builder or generate_tonight_snapshot_for_date
    today_builder = today_builder or generate_snapshot_for_date
    publication_proof_builder = publication_proof_builder or build_candidate_publication_proof

    started_at = datetime.now(timezone.utc)
    result = {
        'status': sync_metadata.STATUS_FAILED,
        'job_name': JOB_INTRADAY_REPAIR,
        'source': source,
        'started_at': started_at.isoformat(),
        'audit': None,
        'repair_scope': None,
        'identity_repair': None,
        'roster_sync': None,
        'recent_logs': None,
        'fatigue_recalculated': None,
        'dashboard_snapshot_id': None,
        'today_snapshot': None,
        'tonight_snapshot': None,
        'publication_proof': None,
    }

    with app.app_context():
        audit = audit_runner(source=source, lanes=[intraday_reconcile.LANE_ROSTER_ASSIGNMENT])
        result['audit'] = audit
        scope = build_roster_repair_scope(audit)
        result['repair_scope'] = scope
        if scope['status'] == 'no_change':
            result['status'] = sync_metadata.STATUS_SUCCESS
            result['message'] = 'No governed intraday roster changes detected.'
            return result
        if scope['status'] != 'ready':
            result['message'] = 'Intraday roster changes were withheld because not every finding was safe.'
            return result

        writer_guard = None
        sync_run_id = None
        try:
            writer_guard = sync_metadata.acquire_sync_writer_guard(
                job_name=JOB_INTRADAY_REPAIR, source=source)
            sync_run_id = sync_metadata.start_sync_run(
                source=source,
                started_at=started_at.replace(tzinfo=None),
                job_name=JOB_INTRADAY_REPAIR,
            )

            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_TEAM_ASSIGNMENTS)
            identity_result = identity_repair(scope['identity_findings'])
            result['identity_repair'] = identity_result

            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_ROSTER_STATUS)
            roster_result = roster_sync(
                team_ids=scope['affected_team_ids'],
                commit=False,
                sync_run_id=sync_run_id,
                snapshot_date=product_current_date(),
            )
            result['roster_sync'] = roster_result
            if int(roster_result.get('errors') or 0) or int(roster_result.get('records_failed') or 0):
                raise RuntimeError('Targeted intraday roster refresh was incomplete.')
            db.session.commit()

            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_LOG_INGESTION)
            log_result = recent_log_sync(
                days_back=days_back,
                reference_date=product_current_date(),
                sync_run_id=sync_run_id,
                job_name=JOB_INTRADAY_REPAIR,
            )
            result['recent_logs'] = log_result
            if int(log_result.get('errors') or 0) or int(log_result.get('records_failed') or 0):
                raise RuntimeError('Intraday recent-work refresh was incomplete.')

            sync_metadata.set_sync_stage(sync_run_id, sync_metadata.STAGE_FATIGUE_RECALCULATION)
            result['fatigue_recalculated'] = fatigue_recalc(reference_date=product_current_date())

            today = today_builder(product_current_date(), source=JOB_INTRADAY_REPAIR)
            result['today_snapshot'] = _surface_summary(today)
            if (today or {}).get('status') not in ('ok', 'empty', 'generated'):
                raise RuntimeError('Today intelligence rebuild did not complete.')

            tonight = tonight_builder(product_current_date(), source=JOB_INTRADAY_REPAIR)
            result['tonight_snapshot'] = _surface_summary(tonight)
            if (tonight or {}).get('status') not in ('ok', 'empty'):
                raise RuntimeError('Tonight intelligence rebuild did not complete.')

            identity_changes = (
                int((identity_result or {}).get('created') or 0)
                + int((identity_result or {}).get('reassigned') or 0)
            )
            run, snapshot = complete_with_snapshot(
                sync_run_id,
                final_status=sync_metadata.STATUS_SUCCESS,
                records_processed=(
                    int(roster_result.get('pitchers_refreshed') or 0)
                    + int(log_result.get('new_logs_added') or 0)
                    + int(log_result.get('logs_corrected') or 0)
                    + identity_changes
                ),
                records_failed=0,
                new_logs_added=int(log_result.get('new_logs_added') or 0),
                pitchers_updated=int(roster_result.get('pitchers_changed') or 0) + identity_changes,
                errors=0,
                api_calls_made=0,
                retries_used=0,
                source=source,
                started_at=started_at.replace(tzinfo=None),
                snapshot_source=JOB_INTRADAY_REPAIR,
                job_name=JOB_INTRADAY_REPAIR,
            )
            result['dashboard_snapshot_id'] = getattr(snapshot, 'id', None)
            proof = publication_proof_builder(
                result['dashboard_snapshot_id'], candidate_required=True)
            result['publication_proof'] = proof
            if proof.get('verified') is not True:
                raise RuntimeError('Intraday dashboard candidate is not serving.')

            result['status'] = sync_metadata.STATUS_SUCCESS
            result['sync_run_id'] = getattr(run, 'id', sync_run_id)
            result['message'] = 'Intraday roster and identity repair published successfully.'
            return result
        except sync_metadata.SyncWriterConflict as exc:
            db.session.rollback()
            result.update(exc.to_dict())
            result['job_name'] = JOB_INTRADAY_REPAIR
            return result
        except Exception as exc:  # noqa: BLE001
            db.session.rollback()
            result['error'] = str(exc)
            result['message'] = 'Intraday roster repair failed closed.'
            if sync_run_id is not None:
                sync_metadata.finish_sync_run(
                    sync_run_id,
                    status=sync_metadata.STATUS_FAILED,
                    errors=1,
                    error_message=str(exc),
                    source=source,
                    started_at=started_at.replace(tzinfo=None),
                    job_name=JOB_INTRADAY_REPAIR,
                    stage=sync_metadata.STAGE_FAILED,
                )
            return result
        finally:
            if writer_guard is not None:
                writer_guard.release()


def _blocked_scope(reason, findings):
    return {
        'status': 'blocked',
        'reason': reason,
        'repairable_findings': [],
        'roster_status_findings': [],
        'identity_findings': [],
        'unsupported_findings': list(findings or []),
        'affected_team_ids': [],
        'affected_pitcher_ids': [],
        'affected_pitcher_mlb_ids': [],
    }


def _affected_team_ids(findings):
    values = set()
    for finding in findings:
        for key in ('stored_team_id', 'observed_official_team_id'):
            value = finding.get(key)
            if isinstance(value, int) and value > 0:
                values.add(value)
    return sorted(values)


def _stored_pitcher_ids(findings):
    return sorted({
        finding.get('stored_pitcher_id')
        for finding in findings
        if isinstance(finding.get('stored_pitcher_id'), int)
    })


def _mlb_pitcher_ids(findings):
    return sorted({
        finding.get('mlb_player_id')
        for finding in findings
        if isinstance(finding.get('mlb_player_id'), int)
    })


def _surface_summary(payload):
    payload = payload or {}
    return {
        'status': payload.get('status'),
        'reference_date': payload.get('reference_date') or payload.get('slate_date'),
        'card_count': payload.get('card_count'),
        'snapshot_id': payload.get('snapshot_id'),
    }
