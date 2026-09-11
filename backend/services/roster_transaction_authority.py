"""SP-05 authoritative roster membership and bounded queue workers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
import hashlib
import logging

from sqlalchemy import text

from models.pitcher import Pitcher
from models.roster_membership import (
    RosterMembershipInterval,
    RosterMembershipMutation,
)
from models.roster_status_snapshot import RosterStatusSnapshot
from services.mlb_api import mlb_client
from services.roster_authority_scope import classify_roster_team, roster_confirmation_routes
from services.roster_status_sync import (
    _snapshot_values,
    _upsert_roster_status_snapshot,
    classify_roster_evidence,
    roster_entry_player_id,
)
from services.source_observations import (
    ObservationCompleteness,
    ObservationOutcome,
    PayloadKind,
    SourceProvider,
    SourceSubjectType,
    build_source_identity,
    canonical_record_collection,
    record_source_fetch_failure,
    record_source_observation,
    stable_json_dumps,
)
from services.sync_control_plane import (
    FailureClass,
    RunStage,
    RunStatus,
    RunType,
    ScopeType,
    SourceDomain,
    TriggerType,
    add_scopes,
    create_run,
    finalize_run,
    mark_stage,
    record_failure,
    record_outcome,
    start_run,
)
from services.sync_jobs import (
    JobScopeType,
    JobType,
    enqueue_job,
    heartbeat_job,
    run_next_job,
)
from services.transaction_ingestion import sync_transactions
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

ROSTER_PAYLOAD_SCHEMA_VERSION = 1
ROSTER_REQUEST_SCHEMA_VERSION = 1
ROSTER_JOB_PAYLOAD_SCHEMA_VERSION = 1
TRANSACTION_JOB_PAYLOAD_SCHEMA_VERSION = 1
AUTHORITY_OFFICIAL_MLB_ROSTER = 'official_mlb_roster_v1'
PRIORITY_CURRENT_ROSTER = 40
PRIORITY_TRANSACTION = 50
PRIORITY_ORGANIZATIONAL_DEPTH = 180


class MembershipType(str, Enum):
    ACTIVE_ROSTER = 'active_roster'
    FORTY_MAN_ROSTER = 'forty_man_roster'
    ORGANIZATION = 'organization'
    MINOR_ASSIGNMENT = 'minor_assignment'
    PUBLIC_INACTIVE = 'public_inactive'
    REHAB_ASSIGNMENT = 'rehab_assignment'


class MembershipMutationType(str, Enum):
    OPENED = 'membership_opened'
    CLOSED = 'membership_closed'
    CORRECTED = 'membership_corrected'


@dataclass(frozen=True)
class RosterObservation:
    roster_type: str
    entries: list
    result: object
    completeness: str
    proof: dict


def _roster_identity(team_id, roster_date, roster_type):
    represented = _date(roster_date)
    return build_source_identity(
        provider=SourceProvider.MLB_STATS_API,
        source_domain=SourceDomain.ROSTER,
        endpoint=f'/teams/{int(team_id)}/roster',
        subject_type=SourceSubjectType.TEAM,
        subject_key=f'{int(team_id)}:{roster_type}',
        request_parameters={
            'teamId': int(team_id),
            'rosterType': roster_type,
            'date': represented.isoformat(),
        },
        request_schema_version=ROSTER_REQUEST_SCHEMA_VERSION,
        baseball_date=represented,
    )


def observe_team_roster(
    team_id,
    roster_date,
    roster_type,
    *,
    client=None,
    sync_run_id=None,
    sync_job_id=None,
    commit=False,
):
    """Fetch one official roster view and record explicit coverage evidence."""
    client = client or mlb_client
    represented = _date(roster_date)
    identity = _roster_identity(team_id, represented, roster_type)
    started_at = utc_now_naive()
    try:
        reader = getattr(type(client), 'get_team_roster_with_completeness', None)
        if callable(reader):
            collection = client.get_team_roster_with_completeness(
                int(team_id), roster_type=roster_type, date=represented.isoformat(),
            )
            entries = list(collection.records or [])
            completeness = collection.completeness
            proof = dict(collection.proof or {})
        else:
            entries = client.get_team_roster(
                int(team_id), roster_type=roster_type, date=represented.isoformat(),
            )
            completeness = (
                ObservationCompleteness.COMPLETE.value
                if isinstance(entries, list)
                else ObservationCompleteness.UNKNOWN.value
            )
            entries = list(entries or []) if isinstance(entries, list) else []
            proof = {'legacy_client_contract': True, 'record_count': len(entries)}
    except Exception as exc:
        record_source_fetch_failure(
            identity=identity,
            error=exc,
            attempt_started_at=started_at,
            http_status=getattr(exc, 'status_code', None),
            sync_run_id=sync_run_id,
            sync_job_id=sync_job_id,
            # No canonical mutation has begun. Persist the failed attempt before
            # re-raising so an outer job rollback cannot erase source evidence.
            commit=True,
        )
        raise

    identity_failures = sum(
        1 for entry in entries
        if not isinstance(entry, dict) or roster_entry_player_id(entry) is None
    )
    try:
        completeness_value = ObservationCompleteness(completeness)
    except ValueError:
        completeness_value = ObservationCompleteness.UNKNOWN
    if identity_failures and completeness_value == ObservationCompleteness.COMPLETE:
        completeness_value = ObservationCompleteness.PARTIAL
    proof.update({
        'identity_failures': identity_failures,
        'authoritative_for_absence': (
            completeness_value == ObservationCompleteness.COMPLETE
        ),
    })
    scope = classify_roster_team(team_id, records=entries)
    proof['roster_authority_scope'] = {**scope, 'represented_roster_type': roster_type}
    proof['authoritative_for_mlb_membership'] = bool(
        scope['mlb_membership_authority']
        and roster_type in ('active', '40Man')
        and completeness_value == ObservationCompleteness.COMPLETE
    )
    result = record_source_observation(
        identity=identity,
        payload={'records': entries, 'completeness_proof': proof},
        fingerprint_payload=canonical_record_collection(entries),
        completeness=completeness_value,
        payload_schema_version=ROSTER_PAYLOAD_SCHEMA_VERSION,
        payload_kind=PayloadKind.NORMALIZED_JSON,
        record_count=len(entries),
        empty_valid=(
            completeness_value == ObservationCompleteness.COMPLETE and not entries
        ),
        attempt_started_at=started_at,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
        commit=commit,
    )
    return RosterObservation(
        roster_type=roster_type,
        entries=entries,
        result=result,
        completeness=completeness_value.value,
        proof=proof,
    )


def reconcile_team_roster(
    team_id,
    roster_date,
    *,
    client=None,
    timestamp=None,
    sync_run_id=None,
    sync_job_id=None,
    commit=True,
    enqueue_downstream=True,
    repair_request_id=None,
):
    """Reconcile one team's active and 40-man pitcher membership atomically."""
    team_id = int(team_id)
    roster_date = _date(roster_date)
    timestamp = timestamp or utc_now_naive()
    # MLB roster endpoints expose no comparable upstream revision. Serialize
    # the two-view acquisition and owner commit for this club, so a response
    # fetched earlier cannot resume after a newer reconciliation commits.
    # Affiliate evidence and unrelated MLB clubs remain independent.
    from services.mlb_club_directory import MLB_TEAM_IDS
    if team_id in MLB_TEAM_IDS:
        _lock_team(team_id)
    views = {
        roster_type: observe_team_roster(
            team_id,
            roster_date,
            roster_type,
            client=client,
            sync_run_id=sync_run_id,
            sync_job_id=sync_job_id,
            commit=False,
        )
        for roster_type in ('active', '40Man')
    }
    complete = all(
        item.completeness == ObservationCompleteness.COMPLETE.value
        for item in views.values()
    )
    authority_scope = classify_roster_team(
        team_id, records=[entry for view in views.values() for entry in view.entries],
    )
    if not complete or not authority_scope['mlb_membership_authority']:
        if commit:
            db.session.commit()
        return {
            **_roster_summary(team_id, roster_date, views, [], [], authoritative=False),
            'authority_scope': authority_scope,
            'evidence_only': complete and not authority_scope['authority_conflict'],
        }

    changed = any(item.result.changed for item in views.values())
    if not changed and repair_request_id is None:
        if commit:
            db.session.commit()
        return _roster_summary(team_id, roster_date, views, [], [], authoritative=True)

    from models.source_observation import SourceObservation, SourceSubject
    from models.compatibility_write_event import CompatibilityWriteEvent
    superseded = any(
        SourceObservation.query.filter(
            SourceObservation.source_subject_id == view.result.observation.source_subject_id,
            SourceObservation.is_authoritative.is_(True),
            SourceObservation.version_number > view.result.observation.version_number,
        ).first() is not None
        for view in views.values()
    )
    superseded = superseded or db.session.query(SourceObservation.id).join(
        SourceSubject, SourceSubject.id == SourceObservation.source_subject_id,
    ).filter(
        SourceSubject.provider == 'mlb_stats_api', SourceSubject.source_domain == 'roster',
        SourceSubject.subject_key.in_((f'{team_id}:active', f'{team_id}:40Man')),
        SourceSubject.baseball_date > roster_date,
        SourceObservation.is_authoritative.is_(True),
    ).first() is not None
    if superseded:
        db.session.add(CompatibilityWriteEvent(
            resource_type='roster', resource_key=f'{team_id}:{roster_date}',
            outcome='stale_suppressed', details_json={
                'source_observation_ids': [view.result.observation.id for view in views.values()],
            },
        ))
        if commit:
            db.session.commit()
        return {**_roster_summary(team_id, roster_date, views, [], [], authoritative=True),
                'write_outcome': 'stale_suppressed'}
    from services.semantic_write_fencing import authorize_roster_projection
    authorize_roster_projection(team_id)
    entries_by_type = {
        MembershipType.ACTIVE_ROSTER.value: _pitcher_entries(views['active'].entries),
        MembershipType.FORTY_MAN_ROSTER.value: _pitcher_entries(views['40Man'].entries),
    }
    observations = {
        MembershipType.ACTIVE_ROSTER.value: views['active'].result.observation,
        MembershipType.FORTY_MAN_ROSTER.value: views['40Man'].result.observation,
    }
    mutations = []
    if repair_request_id is not None:
        from services.roster_authority_correction import correct_roster_authority
        mutations.extend(correct_roster_authority(
            team_id, roster_date, observations=observations,
            entries_by_type=entries_by_type, repair_request_id=repair_request_id,
            sync_run_id=sync_run_id, timestamp=timestamp,
        ))
    affected_pitchers = {}
    for membership_type, incoming_entries in entries_by_type.items():
        observation = observations[membership_type]
        current = (
            RosterMembershipInterval.query
            .filter_by(
                team_id=team_id,
                membership_type=membership_type,
                effective_end_date=None,
                is_current_version=True,
                is_void=False,
            )
            .with_for_update()
            .all()
        )
        current_by_mlb_id = {row.player_mlb_id: row for row in current}
        incoming_ids = set(incoming_entries)
        for mlb_id, interval in current_by_mlb_id.items():
            if mlb_id not in incoming_ids:
                mutations.append(_close_interval(
                    interval,
                    roster_date=roster_date,
                    timestamp=timestamp,
                    observation_id=observation.id,
                    sync_run_id=sync_run_id,
                ))
                affected_pitchers[interval.pitcher_id] = interval.player_mlb_id

        for mlb_id, entry in incoming_entries.items():
            pitcher = _get_or_create_pitcher(mlb_id, entry, team_id, timestamp)
            affected_pitchers.setdefault(pitcher.id, mlb_id)
            if mlb_id in current_by_mlb_id:
                continue
            # Another endpoint's inclusion cannot prove this club's removal.
            # Each complete MLB club view owns only its own membership set.
            interval = RosterMembershipInterval(
                pitcher_id=pitcher.id,
                player_mlb_id=mlb_id,
                team_id=team_id,
                organization_id=team_id,
                membership_type=membership_type,
                effective_start_date=roster_date,
                effective_start_at=None,
                start_precision='date',
                authority_type=AUTHORITY_OFFICIAL_MLB_ROSTER,
                opened_by_observation_id=observation.id,
                created_at=timestamp,
                updated_at=timestamp,
            )
            db.session.add(interval)
            db.session.flush()
            mutations.append(_mutation(
                interval,
                MembershipMutationType.OPENED,
                roster_date,
                observation.id,
                sync_run_id,
                timestamp,
            ))

    _update_current_and_snapshots(
        team_id,
        roster_date,
        entries_by_type,
        observations,
        affected_pitchers,
        timestamp,
        sync_run_id,
    )
    downstream = []
    if mutations and enqueue_downstream:
        for affected_team_id in sorted({row.team_id for row in mutations}):
            team_mutations = [
                row for row in mutations if row.team_id == affected_team_id
            ]
            downstream.append(_enqueue_membership_impact(
                affected_team_id,
                roster_date,
                team_mutations,
                observations,
                sync_run_id=sync_run_id,
                parent_job_id=sync_job_id,
                commit=False,
            ))
    if commit:
        db.session.commit()
    return _roster_summary(
        team_id, roster_date, views, mutations, downstream, authoritative=True,
    )


def current_memberships(team_id, membership_type=MembershipType.ACTIVE_ROSTER):
    membership_type = _membership_type(membership_type)
    return (
        RosterMembershipInterval.query
        .filter_by(
            team_id=int(team_id),
            membership_type=membership_type,
            effective_end_date=None,
            is_current_version=True,
            is_void=False,
        )
        .order_by(RosterMembershipInterval.player_mlb_id.asc())
        .all()
    )


def membership_on_date(pitcher_id, membership_date, membership_type=None):
    membership_date = _date(membership_date)
    query = RosterMembershipInterval.query.filter(
        RosterMembershipInterval.pitcher_id == int(pitcher_id),
        RosterMembershipInterval.effective_start_date <= membership_date,
        (
            RosterMembershipInterval.effective_end_date.is_(None)
            | (RosterMembershipInterval.effective_end_date > membership_date)
        ),
        RosterMembershipInterval.is_current_version.is_(True),
        RosterMembershipInterval.is_void.is_(False),
    )
    if membership_type is not None:
        query = query.filter(
            RosterMembershipInterval.membership_type == _membership_type(membership_type)
        )
    return query.order_by(RosterMembershipInterval.membership_type.asc()).all()


def supersede_membership_interval(
    interval_id,
    *,
    source_observation_id,
    correction_reason,
    effective_start_date=None,
    effective_end_date=None,
    team_id=None,
    sync_run_id=None,
    timestamp=None,
    commit=True,
    reopen=False,
    is_void=False,
    organization_id=None,
):
    """Preserve a mistaken interval and install one corrected current version.

    SP-13 owns deciding when this operation is warranted. SP-05 supplies the
    minimum safe primitive so correction never erases the cited prior record.
    """
    timestamp = timestamp or utc_now_naive()
    prior = (
        RosterMembershipInterval.query
        .filter_by(id=int(interval_id))
        .with_for_update()
        .one()
    )
    if not prior.is_current_version:
        raise ValueError('Only the current interval version may be superseded')
    if prior.membership_type in ('active_roster', 'forty_man_roster') and not is_void:
        from models.source_observation import SourceObservation
        from services.roster_authority_correction import observation_scope
        source = db.session.get(SourceObservation, source_observation_id)
        owner, subject, _ = observation_scope(source) if source else (None, None, [])
        expected_type = 'active' if prior.membership_type == 'active_roster' else '40Man'
        if (not source or not source.is_authoritative or source.completeness != 'complete'
                or not owner or not owner['mlb_membership_authority']
                or owner['requested_team_id'] != (int(team_id) if team_id is not None else prior.team_id)
                or (subject.request_parameters or {}).get('rosterType') != expected_type):
            raise ValueError('MLB membership correction requires matching complete MLB club authority')
    prior.is_current_version = False
    prior.updated_at = timestamp
    db.session.flush()
    corrected = RosterMembershipInterval(
        pitcher_id=prior.pitcher_id,
        player_mlb_id=prior.player_mlb_id,
        team_id=int(team_id) if team_id is not None else prior.team_id,
        organization_id=organization_id if organization_id is not None else prior.organization_id,
        membership_type=prior.membership_type,
        effective_start_date=(
            _date(effective_start_date)
            if effective_start_date is not None else prior.effective_start_date
        ),
        effective_start_at=prior.effective_start_at,
        effective_end_date=(
            None if reopen else (
                _date(effective_end_date) if effective_end_date is not None else prior.effective_end_date
            )
        ),
        effective_end_at=None if reopen else prior.effective_end_at,
        start_precision=prior.start_precision,
        end_precision=None if reopen else prior.end_precision,
        authority_type=prior.authority_type,
        opened_by_observation_id=source_observation_id,
        closed_by_observation_id=(
            None if reopen else (
                source_observation_id if effective_end_date is not None else prior.closed_by_observation_id
            )
        ),
        opened_by_transaction_id=prior.opened_by_transaction_id,
        closed_by_transaction_id=prior.closed_by_transaction_id,
        is_current_version=True,
        is_void=is_void,
        supersedes_interval_id=prior.id,
        correction_reason=str(correction_reason),
        created_at=timestamp,
        updated_at=timestamp,
    )
    db.session.add(corrected)
    db.session.flush()
    mutation = _mutation(
        corrected,
        MembershipMutationType.CORRECTED,
        corrected.effective_start_date,
        source_observation_id,
        sync_run_id,
        timestamp,
    )
    if commit:
        db.session.commit()
    return corrected, mutation


def enqueue_roster_reconciliation(
    team_id,
    roster_date,
    *,
    available_at=None,
    priority=PRIORITY_CURRENT_ROSTER,
    sync_run_id=None,
    parent_job_id=None,
    commit=True,
    repair_request_id=None,
):
    roster_date = _date(roster_date)
    return enqueue_job(
        job_type=JobType.FETCH_ROSTER,
        scope_type=JobScopeType.TEAM,
        scope_key=str(int(team_id)),
        product_date=roster_date,
        dedupe_key=(
            f'ROSTER_RECONCILE:{int(team_id)}:{roster_date.isoformat()}:'
            f'contract-v{ROSTER_JOB_PAYLOAD_SCHEMA_VERSION}'
            + (f':repair:{int(repair_request_id)}' if repair_request_id is not None else '')
        ),
        payload={
            'team_id': int(team_id),
            'roster_date': roster_date,
            'trigger': 'authoritative_roster_reconciliation',
            'repair_request_id': repair_request_id,
        },
        payload_schema_version=ROSTER_JOB_PAYLOAD_SCHEMA_VERSION,
        priority=priority,
        available_at=available_at,
        sync_run_id=sync_run_id,
        parent_job_id=parent_job_id,
        commit=commit,
    )


def enqueue_transaction_reconciliation(
    start_date,
    end_date,
    *,
    team_id=None,
    available_at=None,
    priority=PRIORITY_TRANSACTION,
    sync_run_id=None,
    parent_job_id=None,
    commit=True,
):
    start_date = _date(start_date)
    end_date = _date(end_date)
    scope = str(int(team_id)) if team_id is not None else 'league'
    return enqueue_job(
        job_type=JobType.FETCH_TRANSACTIONS,
        scope_type=(JobScopeType.TEAM if team_id is not None else JobScopeType.LEAGUE),
        scope_key=scope,
        product_date=end_date,
        dedupe_key=(
            f'TRANSACTION_RANGE:{start_date.isoformat()}:{end_date.isoformat()}:'
            f'{scope}:request-v{TRANSACTION_JOB_PAYLOAD_SCHEMA_VERSION}'
        ),
        payload={
            'start_date': start_date,
            'end_date': end_date,
            'team_id': int(team_id) if team_id is not None else None,
        },
        payload_schema_version=TRANSACTION_JOB_PAYLOAD_SCHEMA_VERSION,
        priority=priority,
        available_at=available_at,
        sync_run_id=sync_run_id,
        parent_job_id=parent_job_id,
        commit=commit,
    )


def execute_roster_job(job, *, client=None, timestamp=None):
    payload = dict(job.details_json or {})
    team_id = int(payload.get('team_id') or job.scope_key)
    roster_date = _date(payload.get('roster_date') or job.product_date)
    run = _start_or_attach_run(job, roster_date, team_ids=[team_id])
    try:
        mark_stage(run, RunStage.ACQUIRE)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token)
        summary = reconcile_team_roster(
            team_id,
            roster_date,
            client=client,
            timestamp=timestamp,
            sync_run_id=run.id,
            sync_job_id=job.id,
            commit=False,
            repair_request_id=payload.get('repair_request_id'),
        )
        heartbeat_job(
            job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
        )
        record_outcome(
            run,
            source_reads=2,
            source_changes=summary['source_changes'],
            canonical_mutations=summary['mutation_count'],
            affected_teams=len(summary['affected_team_ids']),
            affected_pitchers=len(summary['affected_pitcher_ids']),
            downstream_work_created=len(summary['downstream_job_ids']),
            warnings_count=int(not summary['authoritative']),
            outcome=summary,
            commit=False,
        )
        finalize_run(
            run,
            RunStatus.SUCCEEDED if summary['authoritative'] or summary.get('evidence_only') else RunStatus.PARTIAL,
            commit=False,
        )
        db.session.commit()
        return summary
    except Exception as exc:
        _fail_run(run, exc, team_id)
        raise


def execute_transaction_job(job, *, client=None, timestamp=None):
    payload = dict(job.details_json or {})
    start_date = _date(payload.get('start_date'))
    end_date = _date(payload.get('end_date') or job.product_date)
    run = _start_or_attach_run(job, end_date, team_ids=())
    try:
        mark_stage(run, RunStage.ACQUIRE)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token)
        summary = sync_transactions(
            start_date=start_date,
            end_date=end_date,
            client=client,
            timestamp=timestamp,
            sync_run_id=run.id,
            sync_job_id=job.id,
            team_id=payload.get('team_id'),
            commit=False,
        )
        if any(
            detail.get('reason') == 'fetch_failed'
            for detail in summary.get('error_details', [])
        ):
            # Preserve SP-03/domain failure evidence, then let SP-02 apply its
            # bounded job retry policy rather than settling a source outage.
            db.session.commit()
            raise RuntimeError('Official transaction acquisition failed')
        affected_teams = sorted({
            int(value) for value in summary.get('affected_team_ids', []) if value is not None
        })
        metadata = {}
        if any(not classify_roster_team(value)['mlb_membership_authority'] for value in affected_teams):
            try:
                metadata = (client or mlb_client).get_team_metadata(end_date.year) or {}
            except Exception:
                logger.warning('Roster confirmation parent metadata unavailable; retaining unresolved team scopes')
        confirmation_teams, unresolved_teams = roster_confirmation_routes(affected_teams, metadata=metadata)
        summary['roster_confirmation_team_ids'] = confirmation_teams
        summary['unresolved_roster_team_ids'] = unresolved_teams
        roster_jobs = []
        revalidation_job = None
        if summary.get('records_stale_suppressed'):
            from datetime import timedelta
            revision_key = hashlib.sha256(stable_json_dumps(
                summary['suppressed_event_versions']
            ).encode('utf-8')).hexdigest()
            revalidation_job = enqueue_job(
                job_type=JobType.FETCH_TRANSACTIONS, scope_type=JobScopeType.SOURCE_DOMAIN,
                scope_key='transactions', product_date=end_date,
                dedupe_key=f'TRANSACTION_REVALIDATE:{start_date}:{end_date}:{revision_key}',
                priority=PRIORITY_TRANSACTION, sync_run_id=run.id, parent_job_id=job.id,
                available_at=utc_now_naive() + timedelta(seconds=30),
                payload={**payload, 'reason': 'authority_changed_during_acquisition'},
                commit=False,
            )
        summary['revalidation_job_id'] = revalidation_job.id if revalidation_job else None
        if summary.get('records_created', 0) or summary.get('records_corrected', 0):
            for team_id in confirmation_teams:
                roster_jobs.append(enqueue_roster_reconciliation(
                    team_id,
                    end_date,
                    priority=PRIORITY_CURRENT_ROSTER,
                    sync_run_id=run.id,
                    parent_job_id=job.id,
                    commit=False,
                ))
        status = RunStatus.PARTIAL if summary.get('errors') or unresolved_teams else RunStatus.SUCCEEDED
        record_outcome(
            run,
            source_reads=1,
            source_changes=int(bool(summary.get('source_observation_changed'))),
            canonical_mutations=(
                summary.get('records_created', 0) + summary.get('records_corrected', 0)
            ),
            affected_teams=len(affected_teams),
            affected_pitchers=len(summary.get('affected_player_mlb_ids', [])),
            downstream_work_created=len(roster_jobs) + int(revalidation_job is not None),
            warnings_count=summary.get('errors', 0),
            outcome={**summary, 'downstream_roster_job_ids': [row.id for row in roster_jobs]},
            commit=False,
        )
        finalize_run(run, status, commit=False)
        heartbeat_job(
            job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
        )
        db.session.commit()
        return {**summary, 'downstream_roster_job_ids': [row.id for row in roster_jobs]}
    except Exception as exc:
        _fail_run(run, exc, None)
        raise


def run_next_roster_transaction_job(worker_id, *, client=None, timestamp=None):
    return run_next_job(
        worker_id,
        {
            JobType.FETCH_ROSTER.value: lambda job: execute_roster_job(
                job, client=client, timestamp=timestamp,
            ),
            JobType.FETCH_TRANSACTIONS.value: lambda job: execute_transaction_job(
                job, client=client, timestamp=timestamp,
            ),
        },
        job_types=[JobType.FETCH_ROSTER, JobType.FETCH_TRANSACTIONS],
    )


def _pitcher_entries(entries):
    result = {}
    for entry in entries or ():
        if not isinstance(entry, dict) or not _is_pitcher_entry(entry):
            continue
        mlb_id = roster_entry_player_id(entry)
        if mlb_id is not None:
            result[int(mlb_id)] = entry
    return result


def _is_pitcher_entry(entry):
    person = entry.get('person') or {}
    position = entry.get('position') or person.get('primaryPosition') or {}
    abbreviation = str(position.get('abbreviation') or '').upper()
    position_type = str(position.get('type') or '').lower()
    return abbreviation in {'P', 'TWP'} or position_type in {'pitcher', 'two-way player'}


def _get_or_create_pitcher(mlb_id, entry, team_id, timestamp):
    pitcher = Pitcher.query.filter_by(mlb_id=mlb_id).one_or_none()
    person = entry.get('person') or {}
    position = entry.get('position') or person.get('primaryPosition') or {}
    if pitcher is None:
        pitcher = Pitcher(
            mlb_id=mlb_id,
            full_name=str(person.get('fullName') or f'MLB Player {mlb_id}'),
            team_id=team_id,
            position=str(position.get('abbreviation') or 'P')[:10],
            active=True,
            created_at=timestamp,
            updated_at=timestamp,
        )
        db.session.add(pitcher)
        db.session.flush()
    return pitcher


def _close_interval(
    interval, *, roster_date, timestamp, observation_id, sync_run_id,
):
    interval.effective_end_date = max(roster_date, interval.effective_start_date)
    interval.effective_end_at = None
    interval.end_precision = 'date'
    interval.closed_by_observation_id = observation_id
    interval.updated_at = timestamp
    return _mutation(
        interval,
        MembershipMutationType.CLOSED,
        roster_date,
        observation_id,
        sync_run_id,
        timestamp,
    )


def _mutation(
    interval, mutation_type, roster_date, observation_id, sync_run_id, timestamp,
):
    row = RosterMembershipMutation(
        interval_id=interval.id,
        pitcher_id=interval.pitcher_id,
        player_mlb_id=interval.player_mlb_id,
        team_id=interval.team_id,
        membership_type=interval.membership_type,
        mutation_type=mutation_type.value,
        baseball_date=roster_date,
        precision='date',
        source_observation_id=observation_id,
        sync_run_id=sync_run_id,
        created_at=timestamp,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _update_current_and_snapshots(
    team_id,
    roster_date,
    entries_by_type,
    observations,
    affected_pitchers,
    timestamp,
    sync_run_id,
):
    active = entries_by_type[MembershipType.ACTIVE_ROSTER.value]
    forty = entries_by_type[MembershipType.FORTY_MAN_ROSTER.value]
    all_ids = set(active) | set(forty) | set(affected_pitchers.values())
    pitchers = {
        row.mlb_id: row
        for row in Pitcher.query.filter(Pitcher.mlb_id.in_(all_ids or [-1]))
        .order_by(Pitcher.id).populate_existing().with_for_update().all()
    }
    for mlb_id in sorted(all_ids):
        pitcher = pitchers.get(mlb_id)
        if pitcher is None:
            continue
        projection_fields = (
            'team_id', 'team_name', 'team_abbreviation', 'active',
            'team_assignment_status', 'team_assignment_source', 'roster_status',
            'roster_status_source', 'roster_status_raw_code', 'roster_status_raw_description',
        )
        before_projection = {field: getattr(pitcher, field) for field in projection_fields}
        roster_types = set()
        entries = {}
        if mlb_id in active:
            roster_types.add('active')
            entries['active'] = active[mlb_id]
        if mlb_id in forty:
            roster_types.add('40Man')
            entries['40Man'] = forty[mlb_id]
        # Both source views are complete at this point, so an empty set is
        # explicit negative evidence (False/False), not unknown evidence.
        evidence = {
            'player_id': mlb_id,
            'roster_types': roster_types,
            'raw_statuses': [],
            'entries': entries,
        }
        classification = classify_roster_evidence(evidence)
        values = _snapshot_values(
            pitcher=pitcher,
            team_id=team_id,
            snapshot_date=roster_date,
            classification=classification,
            evidence=evidence,
            timestamp=timestamp,
            sync_run_id=sync_run_id,
            active_roster_observation_id=observations[MembershipType.ACTIVE_ROSTER.value].id,
            forty_man_roster_observation_id=observations[MembershipType.FORTY_MAN_ROSTER.value].id,
        )
        snapshot, _action, _failed = _upsert_roster_status_snapshot(
            values,
            sync_run_id=sync_run_id,
            timestamp=timestamp,
        )
        if snapshot is not None:
            # Historical evidence may update its dated snapshot, but cannot
            # replace the current projection established by a later MLB view.
            newer = RosterStatusSnapshot.query.filter(
                RosterStatusSnapshot.pitcher_id == pitcher.id,
                RosterStatusSnapshot.snapshot_date > roster_date,
                RosterStatusSnapshot.active_roster_observation_id.isnot(None),
                RosterStatusSnapshot.forty_man_roster_observation_id.isnot(None),
            ).first()
            if newer is not None:
                continue
            if roster_types:
                from services.mlb_club_directory import MLB_CLUBS
                club = next(club for club in MLB_CLUBS if club.team_id == team_id)
                pitcher.team_id = team_id
                pitcher.team_name = club.team_name
                pitcher.team_abbreviation = club.abbreviation
                pitcher.active = True
                pitcher.team_assignment_status = 'assigned'
                pitcher.team_assignment_source = AUTHORITY_OFFICIAL_MLB_ROSTER
                pitcher.team_assignment_updated_at = timestamp
                pitcher.updated_at = timestamp
            pitcher.roster_status = snapshot.roster_status
            pitcher.roster_status_source = snapshot.source
            pitcher.roster_status_raw_code = snapshot.roster_status_raw_code
            pitcher.roster_status_raw_description = snapshot.roster_status_raw_description
            pitcher.roster_status_updated_at = timestamp
            after_projection = {field: getattr(pitcher, field) for field in projection_fields}
            if before_projection != after_projection:
                from models.compatibility_write_event import CompatibilityWriteEvent
                db.session.add(CompatibilityWriteEvent(
                    resource_type='pitcher_projection', resource_key=str(pitcher.id),
                    outcome='applied', details_json={
                        'team_id': team_id, 'roster_date': roster_date.isoformat(),
                        'previous_team_id': before_projection['team_id'],
                        'source_observation_ids': [row.id for row in observations.values()],
                        'changed_fields': sorted(field for field in projection_fields
                                                 if before_projection[field] != after_projection[field]),
                    },
                ))


def _enqueue_membership_impact(
    team_id,
    roster_date,
    mutations,
    observations,
    *,
    sync_run_id,
    parent_job_id,
    commit,
):
    mutation_ids = sorted(row.id for row in mutations)
    pitcher_ids = sorted({row.pitcher_id for row in mutations})
    observation_ids = sorted({row.id for row in observations.values()})
    mutation_fingerprint = hashlib.sha256(
        ','.join(map(str, mutation_ids)).encode('ascii')
    ).hexdigest()
    return enqueue_job(
        job_type=JobType.PROCESS_CANONICAL_IMPACT,
        scope_type=JobScopeType.TEAM,
        scope_key=str(team_id),
        product_date=roster_date,
        dedupe_key=(
            f'ROSTER_IMPACT:{team_id}:{roster_date.isoformat()}:'
            f'observations:{"-".join(map(str, observation_ids))}'
            f':mutations:{mutation_fingerprint}'
        ),
        priority=PRIORITY_CURRENT_ROSTER,
        sync_run_id=sync_run_id,
        parent_job_id=parent_job_id,
        payload_schema_version=1,
        payload={
            'mutation_family': 'roster_membership',
            'authority_class': 'roster_authoritative',
            'team_id': team_id,
            'pitcher_ids': pitcher_ids,
            'source_observation_ids': observation_ids,
            'membership_mutation_ids': mutation_ids,
            'baseball_date': roster_date,
            'trigger': 'roster_membership_changed',
        },
        commit=commit,
    )


def _roster_summary(team_id, roster_date, views, mutations, downstream, *, authoritative):
    affected_pitchers = sorted({row.pitcher_id for row in mutations})
    affected_teams = sorted({row.team_id for row in mutations})
    return {
        'team_id': team_id,
        'roster_date': roster_date.isoformat(),
        'authority_scope': classify_roster_team(
            team_id, records=[entry for view in views.values() for entry in view.entries],
        ),
        'authoritative': authoritative,
        'source_changes': sum(int(item.result.changed) for item in views.values()),
        'source_observation_ids': {
            key: value.result.observation.id if value.result.observation else None
            for key, value in views.items()
        },
        'completeness': {key: value.completeness for key, value in views.items()},
        'mutation_count': len(mutations),
        'membership_mutation_ids': [row.id for row in mutations],
        'affected_pitcher_ids': affected_pitchers,
        'affected_team_ids': affected_teams,
        'downstream_job_ids': [row.id for row in downstream],
    }


def _start_or_attach_run(job, baseball_date, *, team_ids):
    if job.sync_run_id is None:
        run = create_run(
            run_type=RunType.ROSTER_TRANSACTIONS,
            trigger_type=TriggerType.RECONCILIATION,
            source='sp05_roster_authority',
            job_name=job.job_name,
            baseball_date=baseball_date,
            source_domain=(
                SourceDomain.ROSTER
                if job.job_name == JobType.FETCH_ROSTER.value
                else SourceDomain.TRANSACTIONS
            ),
            scopes=[(ScopeType.TEAM, value) for value in team_ids],
            commit=False,
        )
        job.sync_run_id = run.id
        db.session.commit()
    else:
        run = start_run(job.sync_run_id)
    return start_run(run)


def _fail_run(run, error, team_id):
    db.session.rollback()
    record_failure(
        run.id,
        error,
        failure_class=FailureClass.SOURCE,
        stage=RunStage.ACQUIRE,
        source_domain=SourceDomain.ROSTER if team_id is not None else SourceDomain.TRANSACTIONS,
        entity_type='team' if team_id is not None else 'transaction_range',
        entity_ref=team_id,
        retryable=True,
        commit=False,
    )
    finalize_run(run.id, RunStatus.FAILED, failed_stage=RunStage.ACQUIRE, commit=False)
    db.session.commit()


def _lock_team(team_id):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:lock_key)'),
            {'lock_key': 505000000 + int(team_id)},
        )


def _membership_type(value):
    raw = value.value if isinstance(value, MembershipType) else str(value)
    return MembershipType(raw).value


def _date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


__all__ = [
    'MembershipMutationType',
    'MembershipType',
    'current_memberships',
    'enqueue_roster_reconciliation',
    'enqueue_transaction_reconciliation',
    'execute_roster_job',
    'execute_transaction_job',
    'membership_on_date',
    'observe_team_roster',
    'reconcile_team_roster',
    'run_next_roster_transaction_job',
    'supersede_membership_interval',
]
