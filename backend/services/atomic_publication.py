"""SP-11 atomic publication of one completed SP-10 cohort.

The database generation is authoritative. External cache work is deliberately
post-commit and retryable; this module never recomputes baseball intelligence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from hashlib import sha256
import json
from time import perf_counter

from sqlalchemy import text

from models.atomic_publication import (
    AtomicPublication,
    AtomicPublicationArtifact,
    AtomicPublicationCacheHandoff,
    AtomicPublicationCurrent,
)
from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import DerivedCohortSnapshot, DerivedIntelligenceCohort
from models.source_observation import SourceObservation
from models.sync_run import SyncRun
from services.derived_intelligence import capture_input_manifest
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
from utils.db import db
from utils.time import utc_now_naive


PUBLICATION_SCHEMA_VERSION = 'atomic-publication-v1'
PUBLICATION_PAYLOAD_VERSION = 1
CACHE_HANDOFF_PAYLOAD_VERSION = 1
PUBLICATION_PRIORITY = 70
CACHE_HANDOFF_PRIORITY = 80
_PUBLICATION_LOCK_KEY = 711_000_001

STATUS_PREPARING = 'preparing'
STATUS_READY = 'ready'
STATUS_PUBLISHED = 'published'
STATUS_FAILED = 'failed'
STATUS_SUPERSEDED = 'superseded'

ALLOWED_AUTHORITIES = frozenset({
    'final', 'corrected_final', 'roster_authoritative', 'pregame_authoritative',
})

# A candidate snapshot becomes a public artifact only when the domain that owns
# that read family completed in the same cohort. This is intentionally smaller
# than the full Team Board contract; SP-14 will certify legacy-reader retirement.
ARTIFACT_REQUIRED_DOMAIN = {
    'pitcher': 'pitcher_snapshot',
    'team': 'team_snapshot',
    'game': 'game_context',
}


class PublicationValidationError(RuntimeError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


class PublicationStaleError(PublicationValidationError):
    pass


@dataclass(frozen=True)
class PublicationResult:
    publication: AtomicPublication
    created: bool
    pointer_advanced: bool
    cache_handoff: AtomicPublicationCacheHandoff


def _canonical(value):
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items(), key=lambda x: str(x[0]))}
    if isinstance(value, (list, tuple, set)):
        return [_canonical(item) for item in value]
    if isinstance(value, (datetime,)):
        return value.isoformat()
    return value


def _fingerprint(value):
    raw = json.dumps(_canonical(value), sort_keys=True, separators=(',', ':'), ensure_ascii=True)
    return sha256(raw.encode('utf-8')).hexdigest()


def _ms(started):
    return max(0, int(round((perf_counter() - started) * 1000)))


def _acquire_publication_lock():
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:lock_key)'),
            {'lock_key': _PUBLICATION_LOCK_KEY},
        )


def _current_pointer_locked():
    return (
        AtomicPublicationCurrent.query
        .filter_by(singleton_id=1)
        .with_for_update()
        .one_or_none()
    )


def get_current_publication():
    pointer = db.session.get(AtomicPublicationCurrent, 1)
    return db.session.get(AtomicPublication, pointer.publication_id) if pointer else None


def _source_data_through(cohort):
    observation_ids = sorted({
        int(item['source_observation_id'])
        for item in (cohort.input_manifest_json or [])
        if item.get('source_observation_id') is not None
    })
    if observation_ids:
        values = db.session.query(SourceObservation.observed_at).filter(
            SourceObservation.id.in_(observation_ids),
        ).all()
        timestamps = [value[0] for value in values if value[0] is not None]
        if timestamps:
            return max(timestamps)
    return datetime.combine(cohort.baseball_date, time.min)


def validate_publication_cohort(cohort, plan):
    if cohort.status != 'complete':
        raise PublicationValidationError('cohort_not_complete')
    if cohort.authority_class not in ALLOWED_AUTHORITIES:
        raise PublicationValidationError('authority_not_publishable')
    if cohort.withheld_domains_json:
        raise PublicationValidationError('cohort_has_withheld_domains')
    if not cohort.completed_domains_json:
        raise PublicationValidationError('cohort_has_no_completed_domains')
    if plan is None or plan.id != cohort.impact_plan_id:
        raise PublicationValidationError('impact_plan_missing')
    if plan.status == 'superseded':
        raise PublicationStaleError('impact_plan_superseded')
    if capture_input_manifest(plan) != (cohort.input_manifest_json or []):
        raise PublicationStaleError('cohort_input_watermark_drifted')


def publication_candidate_specs(cohort):
    completed = set(cohort.completed_domains_json or ())
    snapshots = DerivedCohortSnapshot.query.filter_by(cohort_id=cohort.id).order_by(
        DerivedCohortSnapshot.entity_type,
        DerivedCohortSnapshot.entity_key,
        DerivedCohortSnapshot.snapshot_type,
    ).all()
    specs = []
    seen = set()
    for snapshot in snapshots:
        required = ARTIFACT_REQUIRED_DOMAIN.get(snapshot.entity_type)
        if required is None or required not in completed:
            continue
        if not isinstance(snapshot.payload_json, dict) or not snapshot.payload_json:
            raise PublicationValidationError('artifact_payload_invalid')
        key = (snapshot.snapshot_type, snapshot.entity_type, snapshot.entity_key)
        if key in seen:
            raise PublicationValidationError('artifact_key_duplicated')
        seen.add(key)
        specs.append({
            'key': key,
            'source_cohort_id': cohort.id,
            'source_snapshot_id': snapshot.id,
            'schema_version': str(snapshot.payload_schema_version),
            'payload_fingerprint': _fingerprint(snapshot.payload_json),
        })
    required_sets = {
        'team': set(map(str, cohort.affected_team_ids_json or ())) if 'team_snapshot' in completed else set(),
        'pitcher': set(map(str, cohort.affected_pitcher_ids_json or ())) if 'pitcher_snapshot' in completed else set(),
        'game': set(map(str, cohort.affected_game_ids_json or ())) if 'game_context' in completed else set(),
    }
    actual = {kind: {spec['key'][2] for spec in specs if spec['key'][1] == kind} for kind in required_sets}
    if any(not required.issubset(actual[kind]) for kind, required in required_sets.items()):
        raise PublicationValidationError('required_candidate_snapshot_missing')
    if not specs:
        raise PublicationValidationError('publication_has_no_artifacts')
    return specs


def _existing_artifacts(publication_id):
    if publication_id is None:
        return []
    return AtomicPublicationArtifact.query.filter_by(publication_id=publication_id).order_by(
        AtomicPublicationArtifact.artifact_type,
        AtomicPublicationArtifact.entity_type,
        AtomicPublicationArtifact.entity_key,
    ).all()


def _manifest_material(cohort, specs, inherited):
    artifacts = [
        {
            'key': spec['key'],
            'source_cohort_id': spec['source_cohort_id'],
            'schema_version': spec['schema_version'],
            'payload_fingerprint': spec['payload_fingerprint'],
        }
        for spec in specs
    ]
    artifacts.extend({
        'key': (row.artifact_type, row.entity_type, row.entity_key),
        'source_cohort_id': row.source_cohort_id,
        'schema_version': row.schema_version,
        'payload_fingerprint': row.payload_fingerprint,
    } for row in inherited)
    artifacts.sort(key=lambda value: value['key'])
    return {
        'schema_version': PUBLICATION_SCHEMA_VERSION,
        'cohort_fingerprint': cohort.cohort_fingerprint,
        'authority_class': cohort.authority_class,
        'input_manifest': cohort.input_manifest_json,
        'method_versions': cohort.method_versions_json,
        'artifacts': artifacts,
    }


def publish_derived_cohort(
    cohort_id,
    *,
    sync_run_id=None,
    lease_fence=None,
    cache_configured=False,
    failure_hook=None,
    commit=True,
):
    """Publish one validated cohort using one serialized pointer transition."""
    started = perf_counter()
    cohort = db.session.get(DerivedIntelligenceCohort, int(cohort_id))
    if cohort is None:
        raise PublicationValidationError('cohort_missing')
    existing = AtomicPublication.query.filter_by(cohort_id=cohort.id).one_or_none()
    if existing is not None and existing.status == STATUS_PUBLISHED:
        pointer = db.session.get(AtomicPublicationCurrent, 1)
        handoff = AtomicPublicationCacheHandoff.query.filter_by(publication_id=existing.id).one()
        return PublicationResult(existing, False, bool(pointer and pointer.publication_id == existing.id), handoff)

    plan = db.session.get(CanonicalImpactPlan, cohort.impact_plan_id)
    validate_publication_cohort(cohort, plan)
    candidate_specs = publication_candidate_specs(cohort)
    if lease_fence:
        lease_fence()

    _acquire_publication_lock()
    pointer = _current_pointer_locked()
    predecessor = db.session.get(AtomicPublication, pointer.publication_id) if pointer else None
    current_artifacts = _existing_artifacts(predecessor.id if predecessor else None)
    candidate_keys = {spec['key'] for spec in candidate_specs}
    for row in current_artifacts:
        key = (row.artifact_type, row.entity_type, row.entity_key)
        if key in candidate_keys and row.source_cohort_id > cohort.id:
            raise PublicationStaleError('candidate_older_than_current_artifact')
    inherited = [
        row for row in current_artifacts
        if (row.artifact_type, row.entity_type, row.entity_key) not in candidate_keys
    ]

    validate_publication_cohort(cohort, plan)
    if lease_fence:
        lease_fence()
    manifest = _manifest_material(cohort, candidate_specs, inherited)
    publication_fingerprint = _fingerprint(manifest)
    existing = AtomicPublication.query.filter_by(
        publication_fingerprint=publication_fingerprint,
    ).one_or_none()
    if existing is not None:
        handoff = AtomicPublicationCacheHandoff.query.filter_by(publication_id=existing.id).one()
        return PublicationResult(existing, False, bool(pointer and pointer.publication_id == existing.id), handoff)

    publication = AtomicPublication(
        publication_fingerprint=publication_fingerprint,
        schema_version=PUBLICATION_SCHEMA_VERSION,
        predecessor_publication_id=predecessor.id if predecessor else None,
        cohort_id=cohort.id,
        impact_plan_id=cohort.impact_plan_id,
        baseball_date=cohort.baseball_date,
        authority_class=cohort.authority_class,
        status=STATUS_PREPARING,
        completeness='complete',
        source_data_through=_source_data_through(cohort),
        affected_game_ids_json=cohort.affected_game_ids_json,
        affected_team_ids_json=cohort.affected_team_ids_json,
        affected_pitcher_ids_json=cohort.affected_pitcher_ids_json,
        completed_domains_json=cohort.completed_domains_json,
        withheld_domains_json=cohort.withheld_domains_json,
        method_versions_json=cohort.method_versions_json,
        input_manifest_fingerprint=_fingerprint(cohort.input_manifest_json or []),
        correlation_id=cohort.correlation_id,
        sync_run_id=sync_run_id or cohort.sync_run_id,
        artifact_created_count=len(candidate_specs),
        artifact_inherited_count=len(inherited),
        preparation_duration_ms=_ms(started),
    )
    db.session.add(publication)
    db.session.flush()
    for spec in candidate_specs:
        artifact_type, entity_type, entity_key = spec['key']
        db.session.add(AtomicPublicationArtifact(
            publication_id=publication.id,
            artifact_type=artifact_type,
            entity_type=entity_type,
            entity_key=entity_key,
            source_cohort_id=spec['source_cohort_id'],
            source_snapshot_id=spec['source_snapshot_id'],
            schema_version=spec['schema_version'],
            payload_fingerprint=spec['payload_fingerprint'],
        ))
    for prior in inherited:
        db.session.add(AtomicPublicationArtifact(
            publication_id=publication.id,
            artifact_type=prior.artifact_type,
            entity_type=prior.entity_type,
            entity_key=prior.entity_key,
            source_cohort_id=prior.source_cohort_id,
            inherited_from_artifact_id=prior.id,
            schema_version=prior.schema_version,
            payload_fingerprint=prior.payload_fingerprint,
        ))
    publication.status = STATUS_READY
    db.session.flush()
    if failure_hook:
        failure_hook('before_pointer_switch', publication)
    validate_publication_cohort(cohort, plan)
    if lease_fence:
        lease_fence()
    switch_started = perf_counter()
    if pointer is None:
        pointer = AtomicPublicationCurrent(singleton_id=1, publication_id=publication.id)
        db.session.add(pointer)
    else:
        pointer.publication_id = publication.id
        pointer.updated_at = utc_now_naive()
    if predecessor is not None:
        predecessor.status = STATUS_SUPERSEDED
    publication.status = STATUS_PUBLISHED
    publication.published_at = utc_now_naive()
    publication.pointer_switch_duration_ms = _ms(switch_started)
    cache_keys = publication_cache_keys(publication.id, candidate_specs, inherited)
    handoff = AtomicPublicationCacheHandoff(
        publication_id=publication.id,
        status='pending' if cache_configured else 'not_configured',
        cache_keys_json=list(cache_keys),
    )
    db.session.add(handoff)
    if cache_configured:
        enqueue_job(
            job_type=JobType.HANDOFF_PUBLICATION_CACHE,
            scope_type=JobScopeType.BASEBALL_DATE,
            scope_key=cohort.baseball_date.isoformat(),
            product_date=cohort.baseball_date,
            dedupe_key=f'HANDOFF_PUBLICATION_CACHE:{publication_fingerprint}',
            priority=CACHE_HANDOFF_PRIORITY,
            sync_run_id=publication.sync_run_id,
            payload_schema_version=CACHE_HANDOFF_PAYLOAD_VERSION,
            payload={'publication_id': publication.id, 'publication_fingerprint': publication_fingerprint},
            commit=False,
        )
    if failure_hook:
        failure_hook('before_commit', publication)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return PublicationResult(publication, True, True, handoff)


def publication_cache_keys(publication_id, candidate_specs=(), inherited=()):
    keys = set()
    for value in candidate_specs:
        artifact_type, entity_type, entity_key = value['key']
        keys.add(f'atomic-publication:{publication_id}:{artifact_type}:{entity_type}:{entity_key}')
    for row in inherited:
        keys.add(f'atomic-publication:{publication_id}:{row.artifact_type}:{row.entity_type}:{row.entity_key}')
    return tuple(sorted(keys))


def resolve_artifact_snapshot(artifact):
    seen = set()
    row = artifact
    while row.source_snapshot_id is None:
        if row.id in seen or row.inherited_from_artifact_id is None:
            raise PublicationValidationError('artifact_lineage_invalid')
        seen.add(row.id)
        row = db.session.get(AtomicPublicationArtifact, row.inherited_from_artifact_id)
        if row is None:
            raise PublicationValidationError('artifact_lineage_missing')
    snapshot = db.session.get(DerivedCohortSnapshot, row.source_snapshot_id)
    if snapshot is None or _fingerprint(snapshot.payload_json) != artifact.payload_fingerprint:
        raise PublicationValidationError('artifact_payload_fingerprint_mismatch')
    return snapshot


def read_current_publication_bundle():
    """Resolve the pointer once, then all artifacts under that generation."""
    publication = get_current_publication()
    if publication is None:
        return None
    try:
        return _read_bundle(publication)
    except PublicationValidationError:
        predecessor = (
            db.session.get(AtomicPublication, publication.predecessor_publication_id)
            if publication.predecessor_publication_id else None
        )
        if predecessor is None:
            raise
        bundle = _read_bundle(predecessor)
        bundle['degraded_from_publication_id'] = publication.id
        bundle['fallback_reason'] = 'current_artifact_unavailable'
        return bundle


def handoff_publication_cache(publication_id, cache_adapter, *, commit=True):
    publication = db.session.get(AtomicPublication, int(publication_id))
    if publication is None or publication.status not in (STATUS_PUBLISHED, STATUS_SUPERSEDED):
        raise PublicationValidationError('publication_not_committed')
    handoff = AtomicPublicationCacheHandoff.query.filter_by(publication_id=publication.id).one()
    handoff.attempt_count += 1
    handoff.updated_at = utc_now_naive()
    try:
        cache_adapter.handoff(
            publication.id,
            read_publication_bundle(publication.id),
            tuple(handoff.cache_keys_json or ()),
        )
    except Exception as exc:
        handoff.status = 'retry_wait'
        handoff.last_error_class = type(exc).__name__
        handoff.last_error = str(exc)[:2000]
        if commit:
            db.session.commit()
        else:
            db.session.flush()
        raise
    handoff.status = 'complete'
    handoff.completed_at = utc_now_naive()
    handoff.last_error_class = None
    handoff.last_error = None
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return handoff


def read_publication_bundle(publication_id):
    publication = db.session.get(AtomicPublication, int(publication_id))
    if publication is None:
        return None
    return _read_bundle(publication)


def _read_bundle(publication):
    artifacts = AtomicPublicationArtifact.query.filter_by(publication_id=publication.id).order_by(
        AtomicPublicationArtifact.artifact_type,
        AtomicPublicationArtifact.entity_type,
        AtomicPublicationArtifact.entity_key,
    ).all()
    return {
        'publication_id': publication.id,
        'publication_fingerprint': publication.publication_fingerprint,
        'published_at': publication.published_at.isoformat() if publication.published_at else None,
        'source_data_through': publication.source_data_through.isoformat(),
        'authority_class': publication.authority_class,
        'method_versions': publication.method_versions_json,
        'artifacts': [{
            'publication_id': publication.id,
            'artifact_type': row.artifact_type,
            'entity_type': row.entity_type,
            'entity_key': row.entity_key,
            'payload_fingerprint': row.payload_fingerprint,
            'payload': resolve_artifact_snapshot(row).payload_json,
        } for row in artifacts],
    }


def execute_publication_job(job, *, cache_adapter=None):
    if job.payload_schema_version != PUBLICATION_PAYLOAD_VERSION:
        raise ValueError('Unsupported publication payload version.')
    cohort = db.session.get(DerivedIntelligenceCohort, int(job.details_json['cohort_id']))
    if cohort is None:
        raise PublicationValidationError('cohort_missing')
    run = _start_run(job, cohort, JobType.PUBLISH_DERIVED_COHORT)
    try:
        mark_stage(run, RunStage.PUBLISH, commit=False)
        fence = lambda: heartbeat_job(
            job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
        )
        result = publish_derived_cohort(
            cohort.id,
            sync_run_id=run.id,
            lease_fence=fence,
            cache_configured=cache_adapter is not None,
            commit=False,
        )
        add_scopes(run, [
            *((ScopeType.GAME, value) for value in cohort.affected_game_ids_json),
            *((ScopeType.TEAM, value) for value in cohort.affected_team_ids_json),
            *((ScopeType.PITCHER, value) for value in cohort.affected_pitcher_ids_json),
        ], commit=False)
        record_outcome(
            run,
            affected_games=len(cohort.affected_game_ids_json or ()),
            affected_teams=len(cohort.affected_team_ids_json or ()),
            affected_pitchers=len(cohort.affected_pitcher_ids_json or ()),
            downstream_work_created=int(result.cache_handoff.status == 'pending'),
            outcome={
                'publication_id': result.publication.id,
                'publication_fingerprint': result.publication.publication_fingerprint,
                'artifacts_created': result.publication.artifact_created_count,
                'artifacts_inherited': result.publication.artifact_inherited_count,
                'cache_handoff_status': result.cache_handoff.status,
            },
            commit=False,
        )
        finalize_run(run, RunStatus.SUCCEEDED, commit=False)
        db.session.commit()
        return {
            'sync_run_id': run.id,
            'publication_id': result.publication.id,
            'pointer_advanced': result.pointer_advanced,
            'cache_handoff_status': result.cache_handoff.status,
        }
    except Exception as exc:
        db.session.rollback()
        record_failure(run.id, exc, failure_class=FailureClass.PUBLICATION, stage=RunStage.PUBLISH, retryable=True, commit=False)
        finalize_run(run.id, RunStatus.FAILED, failed_stage=RunStage.PUBLISH)
        raise


def execute_cache_handoff_job(job, *, cache_adapter):
    if job.payload_schema_version != CACHE_HANDOFF_PAYLOAD_VERSION:
        raise ValueError('Unsupported cache handoff payload version.')
    if cache_adapter is None:
        raise RuntimeError('publication_cache_adapter_unavailable')
    publication_id = int(job.details_json['publication_id'])
    heartbeat_job(
        job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
    )
    handoff = handoff_publication_cache(publication_id, cache_adapter, commit=True)
    heartbeat_job(
        job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
    )
    return {'publication_id': publication_id, 'cache_handoff_status': handoff.status}


def run_atomic_publication_worker_once(worker_id, *, cache_adapter=None, lease_seconds=300):
    handlers = {
        JobType.PUBLISH_DERIVED_COHORT.value: lambda job: execute_publication_job(job, cache_adapter=cache_adapter),
    }
    job_types = [JobType.PUBLISH_DERIVED_COHORT]
    if cache_adapter is not None:
        handlers[JobType.HANDOFF_PUBLICATION_CACHE.value] = lambda job: execute_cache_handoff_job(job, cache_adapter=cache_adapter)
        job_types.append(JobType.HANDOFF_PUBLICATION_CACHE)
    return run_next_job(worker_id, handlers, job_types=job_types, lease_seconds=lease_seconds)


def _start_run(job, cohort, job_type):
    parent = db.session.get(SyncRun, job.sync_run_id) if job.sync_run_id else None
    run = create_run(
        run_type=RunType.PUBLICATION,
        trigger_type=TriggerType.PARENT_RUN,
        source='atomic_publication',
        job_name=job_type.value,
        baseball_date=cohort.baseball_date,
        source_domain=SourceDomain.PUBLICATION,
        parent_sync_run_id=parent.id if parent else None,
        correlation_id=parent.correlation_id if parent else cohort.correlation_id,
        scopes=(),
        commit=False,
    )
    job.sync_run_id = run.id
    db.session.commit()
    return start_run(run)


__all__ = [
    'ALLOWED_AUTHORITIES', 'ARTIFACT_REQUIRED_DOMAIN', 'PUBLICATION_SCHEMA_VERSION',
    'PublicationResult', 'PublicationStaleError', 'PublicationValidationError',
    'execute_publication_job', 'get_current_publication', 'handoff_publication_cache',
    'publication_candidate_specs', 'publish_derived_cohort',
    'read_current_publication_bundle',
    'read_publication_bundle', 'run_atomic_publication_worker_once',
    'validate_publication_cohort',
]
