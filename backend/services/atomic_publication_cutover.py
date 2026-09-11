"""Governed CR-04 inspection and one-cohort SP-11 publication control."""

from hashlib import sha256
import json

from models.atomic_publication import (
    AtomicPublication,
    AtomicPublicationArtifact,
    AtomicPublicationCurrent,
)
from models.canonical_impact import CanonicalImpactPlan, CanonicalImpactPlanMutation
from models.derived_intelligence import DerivedCohortSnapshot, DerivedIntelligenceCohort
from models.final_game_reconciliation import FinalGameMutation, FinalGameVersion
from models.live_game_delta import LiveGameMutation, ProvisionalPitchingAppearanceState
from models.roster_membership import RosterMembershipInterval, RosterMembershipMutation
from models.source_observation import SourceObservation
from models.sync_job import SyncJob
from services.atomic_publication import (
    ALLOWED_AUTHORITIES,
    PublicationValidationError,
    publication_candidate_specs,
    first_publication_baseline_report,
    run_atomic_publication_worker_once,
    validate_publication_cohort,
)
from services.derived_intelligence import capture_input_manifest, enqueue_publication_candidate
from services.sync_pipeline_certification import collect_operational_health
from services.sync_jobs import JobType
from utils.db import db


ACTIVE_JOB_STATUSES = ('pending', 'running', 'retry_wait')
PREPUBLICATION_IMPACT_BACKLOG_LIMIT = 24


def _pointer_id():
    pointer = db.session.get(AtomicPublicationCurrent, 1)
    return pointer.publication_id if pointer else None


def _manifest_fingerprint(manifest):
    return sha256(json.dumps(
        manifest, sort_keys=True, separators=(',', ':'),
    ).encode('utf-8')).hexdigest()


def _manifest_diff(original, current):
    def keyed(rows):
        return {
            (str(row.get('input_type')), str(row.get('input_key'))): row
            for row in rows
        }

    before = keyed(original)
    after = keyed(current)
    keys = sorted(set(before) | set(after))
    return {
        'added': [after[key] for key in keys if key not in before],
        'removed': [before[key] for key in keys if key not in after],
        'changed': [
            {'before': before[key], 'after': after[key]}
            for key in keys
            if key in before and key in after and before[key] != after[key]
        ],
    }


def _changed_input_details(difference):
    details = []
    for change in difference['changed']:
        after = change['after']
        if after.get('input_type') != 'roster_membership':
            continue
        interval_id = int(str(after['input_version']).split(':', 1)[0])
        interval = db.session.get(RosterMembershipInterval, interval_id)
        if interval is None:
            continue
        mutations = RosterMembershipMutation.query.filter_by(
            interval_id=interval.id,
        ).order_by(RosterMembershipMutation.id).all()
        mutation_ids = [row.id for row in mutations]
        refs = (
            CanonicalImpactPlanMutation.query.filter(
                CanonicalImpactPlanMutation.mutation_family == 'roster_membership',
                CanonicalImpactPlanMutation.source_mutation_id.in_(mutation_ids),
            ).order_by(CanonicalImpactPlanMutation.id).all()
            if mutation_ids else []
        )
        plan_ids = sorted({row.impact_plan_id for row in refs})
        cohorts = (
            DerivedIntelligenceCohort.query.filter(
                DerivedIntelligenceCohort.impact_plan_id.in_(plan_ids),
            ).order_by(DerivedIntelligenceCohort.id).all()
            if plan_ids else []
        )
        observation_ids = sorted({
            value for value in (
                interval.opened_by_observation_id,
                interval.closed_by_observation_id,
                *(row.source_observation_id for row in mutations),
            ) if value is not None
        })
        observations = (
            SourceObservation.query.filter(SourceObservation.id.in_(observation_ids))
            .order_by(SourceObservation.id).all()
            if observation_ids else []
        )
        details.append({
            'input_type': after['input_type'],
            'input_key': after['input_key'],
            'interval': {
                'id': interval.id,
                'team_id': interval.team_id,
                'pitcher_id': interval.pitcher_id,
                'player_mlb_id': interval.player_mlb_id,
                'membership_type': interval.membership_type,
                'effective_start_date': interval.effective_start_date.isoformat(),
                'effective_end_date': (
                    interval.effective_end_date.isoformat()
                    if interval.effective_end_date else None
                ),
                'opened_by_observation_id': interval.opened_by_observation_id,
                'closed_by_observation_id': interval.closed_by_observation_id,
                'is_current_version': interval.is_current_version,
                'updated_at': interval.updated_at.isoformat(),
            },
            'mutations': [{
                'id': row.id,
                'mutation_type': row.mutation_type,
                'baseball_date': row.baseball_date.isoformat(),
                'source_observation_id': row.source_observation_id,
                'sync_run_id': row.sync_run_id,
                'created_at': row.created_at.isoformat(),
            } for row in mutations],
            'source_observations': [{
                'id': row.id,
                'source_subject_id': row.source_subject_id,
                'version_number': row.version_number,
                'outcome': row.outcome,
                'completeness': row.completeness,
                'is_authoritative': row.is_authoritative,
                'sync_run_id': row.sync_run_id,
                'sync_job_id': row.sync_job_id,
                'observed_at': row.observed_at.isoformat(),
                'created_at': row.created_at.isoformat(),
            } for row in observations],
            'impact_plan_ids': plan_ids,
            'cohorts': [{
                'id': row.id,
                'impact_plan_id': row.impact_plan_id,
                'status': row.status,
                'cohort_fingerprint': row.cohort_fingerprint,
                'started_at': row.started_at.isoformat(),
                'completed_at': row.completed_at.isoformat() if row.completed_at else None,
            } for row in cohorts],
        })
    return details


def _candidate_report(cohort, *, include_baseline=False, include_revalidation=False):
    plan = db.session.get(CanonicalImpactPlan, cohort.impact_plan_id)
    reason = None
    artifact_count = 0
    try:
        validate_publication_cohort(cohort, plan)
        artifact_count = len(publication_candidate_specs(cohort))
    except PublicationValidationError as exc:
        reason = exc.reason
    publication = AtomicPublication.query.filter_by(cohort_id=cohort.id).one_or_none()
    baseline = (
        first_publication_baseline_report(cohort)
        if include_baseline and _pointer_id() is None else None
    )
    input_manifest = list(cohort.input_manifest_json or ())
    snapshots = DerivedCohortSnapshot.query.filter_by(cohort_id=cohort.id).all()
    snapshot_counts = {}
    for snapshot in snapshots:
        snapshot_counts[snapshot.snapshot_type] = (
            snapshot_counts.get(snapshot.snapshot_type, 0) + 1
        )
    revalidation = None
    if include_revalidation:
        current_manifest = capture_input_manifest(plan) if plan is not None else []
        difference = _manifest_diff(input_manifest, current_manifest)
        revalidation = {
            'captured_input_manifest': input_manifest,
            'captured_input_fingerprint': _manifest_fingerprint(input_manifest),
            # A complete cohort necessarily passed SP-10's completion-time
            # equality check. The immutable captured manifest is therefore the
            # exact completion-time watermark; later publication validation may
            # compare it with a newer authority state.
            'completion_input_manifest': input_manifest if cohort.status == 'complete' else None,
            'completion_input_fingerprint': (
                _manifest_fingerprint(input_manifest)
                if cohort.status == 'complete' else None
            ),
            'current_input_manifest': current_manifest,
            'current_input_fingerprint': _manifest_fingerprint(current_manifest),
            'difference': difference,
            'changed_input_details': _changed_input_details(difference),
        }
    return {
        'cohort_id': cohort.id,
        'cohort_fingerprint': cohort.cohort_fingerprint,
        'cohort_status': cohort.status,
        'authority_class': cohort.authority_class,
        'baseball_date': cohort.baseball_date.isoformat(),
        'impact_plan_id': cohort.impact_plan_id,
        'impact_plan_fingerprint': plan.plan_fingerprint if plan else None,
        'impact_plan_status': plan.status if plan else None,
        'publication_mode': getattr(plan, 'publication_mode', None) if plan else None,
        'affected_game_ids': list(cohort.affected_game_ids_json or ()),
        'affected_team_ids': list(cohort.affected_team_ids_json or ()),
        'affected_pitcher_ids': list(cohort.affected_pitcher_ids_json or ()),
        'completed_domains': list(cohort.completed_domains_json or ()),
        'withheld_domains': list(cohort.withheld_domains_json or ()),
        'source_observation_ids': sorted({
            int(row['source_observation_id'])
            for row in (cohort.input_manifest_json or ())
            if row.get('source_observation_id') is not None
        }),
        'input_manifest': input_manifest,
        'input_manifest_fingerprint': _manifest_fingerprint(input_manifest),
        'input_revalidation': revalidation,
        'candidate_snapshot_count': len(snapshots),
        'candidate_snapshot_counts': snapshot_counts,
        'candidate_artifact_count': artifact_count,
        'first_publication_baseline': baseline,
        'eligible': (
            reason is None and publication is None
            and (baseline is None or baseline['complete'])
        ),
        'ineligible_reason': (
            reason
            or ('already_published' if publication else None)
            or (baseline and baseline['reason'])
        ),
        'publication_id': publication.id if publication else None,
        'completed_at': cohort.completed_at.isoformat() if cohort.completed_at else None,
        'started_at': cohort.started_at.isoformat() if cohort.started_at else None,
        'created_at': cohort.created_at.isoformat() if cohort.created_at else None,
        # The SP-10 schema does not persist a stale timestamp when a completed
        # cohort later fails SP-11 revalidation.
        'stale_at': None,
    }


def _prepublication_health():
    health = collect_operational_health()
    signals = health['signals']
    roster = signals['roster_authority']
    required_retry_wait = sum(
        bool(row.get('blocking')) for row in signals['retry_wait_job_details']
    )
    pending_derived = SyncJob.query.filter_by(
        job_name=JobType.PROCESS_DERIVED_INTELLIGENCE.value,
        status='pending',
    ).count()
    checks = {
        'active_roster_30_of_30': roster['active_roster_coverage_count'] == 30,
        'forty_man_30_of_30': roster['forty_man_coverage_count'] == 30,
        'unreconciled_finals_zero': signals['unreconciled_final_games'] == 0,
        'blocking_dead_jobs_zero': signals['blocking_dead_jobs'] == 0,
        'required_retry_wait_jobs_zero': required_retry_wait == 0,
        'stale_leases_zero': signals['stale_leases'] == 0,
        'impact_backlog_bounded': (
            signals['pending_impact_plans'] <= PREPUBLICATION_IMPACT_BACKLOG_LIMIT
        ),
        'atomic_pointer_consistent': signals['publication_pointer_inconsistencies'] == 0,
    }
    return {
        'status': 'pass' if all(checks.values()) else 'fail',
        'checks': checks,
        'active_roster_coverage_count': roster['active_roster_coverage_count'],
        'forty_man_coverage_count': roster['forty_man_coverage_count'],
        'unreconciled_final_games': signals['unreconciled_final_games'],
        'blocking_dead_jobs': signals['blocking_dead_jobs'],
        'required_retry_wait_jobs': required_retry_wait,
        'stale_leases': signals['stale_leases'],
        'pending_impact_plans': signals['pending_impact_plans'],
        'pending_derived_jobs': pending_derived,
        'current_publication_id': signals['current_publication_id'],
        'pointer_writer': 'services.atomic_publication.publish_derived_cohort',
        'measured_at': signals['measured_at'],
    }


def _current_publication_report():
    publication_id = _pointer_id()
    publication = db.session.get(AtomicPublication, publication_id) if publication_id else None
    if publication is None:
        return None
    cohort = db.session.get(DerivedIntelligenceCohort, publication.cohort_id)
    plan = db.session.get(CanonicalImpactPlan, publication.impact_plan_id)
    refs = list(plan.mutation_refs if plan is not None else ())
    final_mutations = []
    final_version_ids = set()
    for ref in refs:
        if ref.mutation_family not in ('final_appearance', 'final_game_context'):
            continue
        mutation = db.session.get(FinalGameMutation, ref.source_mutation_id)
        if mutation is None:
            continue
        final_version_ids.add(mutation.final_game_version_id)
        final_mutations.append({
            'id': mutation.id,
            'mutation_type': mutation.mutation_type,
            'game_pk': mutation.game_pk,
            'team_id': mutation.team_id,
            'pitcher_id': mutation.pitcher_id,
            'source_observation_id': mutation.source_observation_id,
            'final_game_version_id': mutation.final_game_version_id,
            'old_appearance_version_id': mutation.old_appearance_version_id,
            'new_appearance_version_id': mutation.new_appearance_version_id,
            'created_at': mutation.created_at.isoformat(),
        })
    final_versions = []
    for version_id in sorted(final_version_ids):
        version = db.session.get(FinalGameVersion, version_id)
        if version is not None:
            final_versions.append({
                'id': version.id,
                'game_pk': version.game_pk,
                'version_number': version.version_number,
                'is_current': version.is_current,
                'finality_observation_id': version.finality_observation_id,
                'boxscore_observation_id': version.boxscore_observation_id,
                'play_by_play_observation_id': version.play_by_play_observation_id,
                'observed_at': version.observed_at.isoformat(),
            })
    observation_ids = sorted(set(
        (plan.source_observation_ids_json if plan else ()) or ()
    ) | {
        value for row in final_versions for value in (
            row['finality_observation_id'], row['boxscore_observation_id'],
            row['play_by_play_observation_id'],
        ) if value is not None
    })
    observations = []
    for observation_id in observation_ids:
        observation = db.session.get(SourceObservation, observation_id)
        if observation is not None:
            observations.append({
                'id': observation.id,
                'source_subject_id': observation.source_subject_id,
                'version_number': observation.version_number,
                'outcome': observation.outcome,
                'completeness': observation.completeness,
                'is_authoritative': observation.is_authoritative,
                'sync_run_id': observation.sync_run_id,
                'sync_job_id': observation.sync_job_id,
                'observed_at': observation.observed_at.isoformat(),
            })
    game_ids = list(publication.affected_game_ids_json or ())
    provisional = ProvisionalPitchingAppearanceState.query.filter(
        ProvisionalPitchingAppearanceState.game_pk.in_(game_ids),
    ).order_by(ProvisionalPitchingAppearanceState.id).all() if game_ids else []
    live_mutations = LiveGameMutation.query.filter(
        LiveGameMutation.game_pk.in_(game_ids),
    ).order_by(LiveGameMutation.id).all() if game_ids else []
    artifacts = AtomicPublicationArtifact.query.filter_by(
        publication_id=publication.id,
    ).order_by(AtomicPublicationArtifact.id).all()
    return {
        'publication_id': publication.id,
        'publication_fingerprint': publication.publication_fingerprint,
        'publication_status': publication.status,
        'predecessor_publication_id': publication.predecessor_publication_id,
        'cohort_id': cohort.id if cohort else None,
        'publication_job_id': cohort.publication_job_id if cohort else None,
        'impact_plan_id': plan.id if plan else None,
        'impact_plan_mutation_refs': [{
            'id': ref.id,
            'mutation_family': ref.mutation_family,
            'source_mutation_id': ref.source_mutation_id,
            'source_mutation_type': ref.source_mutation_type,
            'source_observation_id': ref.source_observation_id,
        } for ref in refs],
        'final_game_versions': final_versions,
        'final_game_mutations': final_mutations,
        'source_observations': observations,
        'artifact_ids': [row.id for row in artifacts],
        'artifact_count': len(artifacts),
        'artifact_created_count': publication.artifact_created_count,
        'artifact_inherited_count': publication.artifact_inherited_count,
        'source_data_through': publication.source_data_through.isoformat(),
        'published_at': publication.published_at.isoformat(),
        'provisional_appearances': [{
            'id': row.id,
            'game_pk': row.game_pk,
            'pitcher_id': row.pitcher_id,
            'latest_observation_id': row.latest_observation_id,
            'is_current': row.is_current,
            'superseded_by_final_game_version_id': row.superseded_by_final_game_version_id,
            'superseded_at': row.superseded_at.isoformat() if row.superseded_at else None,
        } for row in provisional],
        'live_mutations': [{
            'id': row.id,
            'game_pk': row.game_pk,
            'pitcher_id': row.pitcher_id,
            'mutation_type': row.mutation_type,
            'source_observation_id': row.source_observation_id,
            'created_at': row.created_at.isoformat(),
        } for row in live_mutations],
    }
def inspect_publication_candidates(*, limit=20):
    rows = DerivedIntelligenceCohort.query.filter(
        DerivedIntelligenceCohort.status == 'complete',
        DerivedIntelligenceCohort.authority_class.in_(tuple(ALLOWED_AUTHORITIES)),
    ).order_by(DerivedIntelligenceCohort.id.desc()).limit(max(1, min(limit, 100))).all()
    reports = [_candidate_report(row) for row in rows]
    if _pointer_id() is None:
        for index, report in enumerate(reports):
            if report['ineligible_reason'] is not None:
                continue
            reports[index] = _candidate_report(rows[index], include_baseline=True)
            if reports[index]['eligible']:
                break
    return {
        'mode': 'read_only',
        'current_publication_id': _pointer_id(),
        'current_publication': _current_publication_report(),
        'prepublication_health': _prepublication_health(),
        'eligible_candidates': [row for row in reports if row['eligible']],
        'reviewed_candidates': reports,
    }


def inspect_publication_cohort(cohort_id):
    """Read one cohort with row-level current-authority watermark comparison."""
    cohort = db.session.get(DerivedIntelligenceCohort, int(cohort_id))
    if cohort is None:
        raise PublicationValidationError('cohort_missing')
    return {
        'mode': 'read_only',
        'current_publication_id': _pointer_id(),
        'cohort': _candidate_report(cohort, include_revalidation=True),
    }


def publish_selected_cohort(cohort_id):
    cohort = db.session.get(DerivedIntelligenceCohort, int(cohort_id))
    if cohort is None:
        raise PublicationValidationError('cohort_missing')
    report = _candidate_report(cohort, include_baseline=True)
    if not report['eligible'] and report['ineligible_reason'] != 'already_published':
        raise PublicationValidationError(report['ineligible_reason'])

    active = SyncJob.query.filter(
        SyncJob.job_name == JobType.PUBLISH_DERIVED_COHORT.value,
        SyncJob.status.in_(ACTIVE_JOB_STATUSES),
    ).all()
    if any(int((row.details_json or {}).get('cohort_id', -1)) != cohort.id for row in active):
        raise PublicationValidationError('unrelated_active_publication_job')

    pointer_before = _pointer_id()
    plan = db.session.get(CanonicalImpactPlan, cohort.impact_plan_id)
    publication_job = enqueue_publication_candidate(cohort, plan)
    publication_job.details_json = {
        **(publication_job.details_json or {}),
        'bootstrap_first_publication': pointer_before is None,
    }
    cohort.publication_job_id = publication_job.id
    db.session.commit()
    settled = run_atomic_publication_worker_once('cr04-controlled-publication')
    publication = AtomicPublication.query.filter_by(cohort_id=cohort.id).one_or_none()
    if settled is None or publication is None or publication.status != 'published':
        raise PublicationValidationError('selected_cohort_not_published')
    artifacts = AtomicPublicationArtifact.query.filter_by(
        publication_id=publication.id,
    ).order_by(AtomicPublicationArtifact.id).all()
    return {
        'mode': 'controlled_publication',
        'candidate': report,
        'publication_job_id': publication_job.id,
        'publication_job_status': settled.status,
        'publication_sync_run_id': settled.result_json.get('sync_run_id'),
        'publication_id': publication.id,
        'publication_fingerprint': publication.publication_fingerprint,
        'predecessor_publication_id': publication.predecessor_publication_id,
        'artifact_ids': [row.id for row in artifacts],
        'artifact_count': len(artifacts),
        'artifact_created_count': publication.artifact_created_count,
        'artifact_inherited_count': publication.artifact_inherited_count,
        'first_publication_baseline': report.get('first_publication_baseline'),
        'pointer_before': pointer_before,
        'pointer_after': _pointer_id(),
        'published_at': publication.published_at.isoformat(),
        'source_data_through': publication.source_data_through.isoformat(),
    }


__all__ = [
    'inspect_publication_candidates', 'inspect_publication_cohort',
    'publish_selected_cohort',
]
