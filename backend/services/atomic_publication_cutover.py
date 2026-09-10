"""Governed CR-04 inspection and one-cohort SP-11 publication control."""

from hashlib import sha256
import json

from models.atomic_publication import (
    AtomicPublication,
    AtomicPublicationArtifact,
    AtomicPublicationCurrent,
)
from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import DerivedIntelligenceCohort
from models.sync_job import SyncJob
from services.atomic_publication import (
    ALLOWED_AUTHORITIES,
    PublicationValidationError,
    publication_candidate_specs,
    first_publication_baseline_report,
    run_atomic_publication_worker_once,
    validate_publication_cohort,
)
from services.derived_intelligence import enqueue_publication_candidate
from services.sync_jobs import JobType
from utils.db import db


ACTIVE_JOB_STATUSES = ('pending', 'running', 'retry_wait')


def _pointer_id():
    pointer = db.session.get(AtomicPublicationCurrent, 1)
    return pointer.publication_id if pointer else None


def _candidate_report(cohort):
    plan = db.session.get(CanonicalImpactPlan, cohort.impact_plan_id)
    reason = None
    artifact_count = 0
    try:
        validate_publication_cohort(cohort, plan)
        artifact_count = len(publication_candidate_specs(cohort))
    except PublicationValidationError as exc:
        reason = exc.reason
    publication = AtomicPublication.query.filter_by(cohort_id=cohort.id).one_or_none()
    baseline = first_publication_baseline_report(cohort) if _pointer_id() is None else None
    input_manifest = list(cohort.input_manifest_json or ())
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
        'input_manifest_fingerprint': sha256(json.dumps(
            input_manifest, sort_keys=True, separators=(',', ':'),
        ).encode('utf-8')).hexdigest(),
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
    }


def inspect_publication_candidates(*, limit=20):
    rows = DerivedIntelligenceCohort.query.filter(
        DerivedIntelligenceCohort.status == 'complete',
        DerivedIntelligenceCohort.authority_class.in_(tuple(ALLOWED_AUTHORITIES)),
    ).order_by(DerivedIntelligenceCohort.id.desc()).limit(max(1, min(limit, 100))).all()
    reports = [_candidate_report(row) for row in rows]
    return {
        'mode': 'read_only',
        'current_publication_id': _pointer_id(),
        'eligible_candidates': [row for row in reports if row['eligible']],
        'reviewed_candidates': reports,
    }


def publish_selected_cohort(cohort_id):
    cohort = db.session.get(DerivedIntelligenceCohort, int(cohort_id))
    if cohort is None:
        raise PublicationValidationError('cohort_missing')
    report = _candidate_report(cohort)
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


__all__ = ['inspect_publication_candidates', 'publish_selected_cohort']
