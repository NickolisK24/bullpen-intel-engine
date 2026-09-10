"""SP-14 operational health, activation safety, and certification evidence."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func

from models.atomic_publication import (
    AtomicPublication, AtomicPublicationArtifact, AtomicPublicationCacheHandoff,
    AtomicPublicationCurrent,
)
from models.canonical_impact import CanonicalImpactPlan
from models.daily_closure import BaseballDateClosure
from models.derived_intelligence import DerivedIntelligenceCohort
from models.final_game_reconciliation import FinalGameVersion
from models.game_observation_state import GameObservationState
from models.repair_request import RepairRequest
from models.scheduled_game import ScheduledGame
from models.source_observation import SourceFetchAttempt
from models.sync_certification import (
    SyncCertificationCheck, SyncCertificationRun, SyncLegacyTransitionState,
)
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.roster_authority_health import roster_authority_coverage
from utils.db import db
from utils.time import utc_now_naive


CERTIFICATION_VERSION = 'sync-pipeline-certification-v1'
CERTIFICATION_SCHEMA_VERSION = 'sync-certification-v1'
EXPECTED_MIGRATION_HEAD = 'c9d4e6f8a1b2'

GATES = {
    'A': 'Schema / Migration',
    'B': 'Queue / Worker',
    'C': 'Source Evidence',
    'D': 'Game Lifecycle',
    'E': 'Roster / Transactions',
    'F': 'Final / Live Authority',
    'G': 'Impact / Derived',
    'H': 'Publication',
    'I': 'Daily Completeness',
    'J': 'Repair / Backfill',
}

CHECK_STATUSES = frozenset({'passing', 'failed', 'blocked', 'warning', 'not_run'})
CRITICAL_NONPASSING = frozenset({'failed', 'blocked', 'not_run'})


@dataclass(frozen=True)
class ActivationControls:
    pipeline_enabled: bool = False
    shadow_mode: bool = False
    publication_enabled: bool = False
    morning_enabled: bool = False
    closure_enabled: bool = False
    legacy_publication_enabled: bool = True
    legacy_schedulers_enabled: bool = True

    @classmethod
    def from_environment(cls, env):
        return cls(
            pipeline_enabled=_bool(env.get('SYNC_PIPELINE_ENABLED'), False),
            shadow_mode=_bool(env.get('SYNC_PIPELINE_SHADOW_MODE'), False),
            publication_enabled=_bool(env.get('SYNC_PIPELINE_PUBLICATION_ENABLED'), False),
            morning_enabled=_bool(env.get('SYNC_PIPELINE_MORNING_ENABLED'), False),
            closure_enabled=_bool(env.get('SYNC_PIPELINE_CLOSURE_ENABLED'), False),
            legacy_publication_enabled=_bool(
                env.get('BASEBALLOS_LEGACY_PUBLICATION_ENABLED'), True,
            ),
            legacy_schedulers_enabled=_bool(
                env.get('BASEBALLOS_LEGACY_SCHEDULERS_ENABLED'), True,
            ),
        )

    @property
    def fingerprint(self):
        return _fingerprint(asdict(self))


def _bool(value, default):
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _fingerprint(value):
    body = json.dumps(value, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(body.encode('utf-8')).hexdigest()


def validate_activation_controls(controls):
    """Return deterministic violations; no production state is changed."""
    violations = []
    child_flags = {
        'SYNC_PIPELINE_SHADOW_MODE': controls.shadow_mode,
        'SYNC_PIPELINE_PUBLICATION_ENABLED': controls.publication_enabled,
        'SYNC_PIPELINE_MORNING_ENABLED': controls.morning_enabled,
        'SYNC_PIPELINE_CLOSURE_ENABLED': controls.closure_enabled,
    }
    if not controls.pipeline_enabled:
        violations.extend(
            f'{name}_requires_SYNC_PIPELINE_ENABLED'
            for name, enabled in child_flags.items() if enabled
        )
    if controls.shadow_mode and controls.publication_enabled:
        violations.append('shadow_mode_cannot_publish')
    if controls.publication_enabled and controls.legacy_publication_enabled:
        violations.append('uncontrolled_duplicate_publication_writers')
    if (
        (controls.morning_enabled or controls.closure_enabled)
        and controls.legacy_schedulers_enabled
        and not controls.shadow_mode
    ):
        violations.append('uncontrolled_duplicate_scheduled_orchestrators')
    return tuple(sorted(violations))


def legacy_responsibility_map():
    """Complete transition map. Every retirement remains evidence-gated."""
    common_rollback = (
        'Disable all SYNC_PIPELINE_* controls; keep new additive evidence; '
        'continue the established daily/postgame/continuous authority.'
    )
    rows = [
        ('schedule_game_state', 'Schedule and game-state discovery',
         'daily sync and continuous game updates', 'SP-04'),
        ('live_game_delta', 'Live bullpen observation',
         'continuous update CU detector', 'SP-08'),
        ('final_game_reconciliation', 'Final game reconciliation',
         'postgame refresh and game-driven ingestion', 'SP-07'),
        ('roster_transactions', 'Roster and transaction authority',
         'daily sync and intraday repair', 'SP-05'),
        ('pregame_context', 'Pregame context',
         'schedule hydration and request-facing context', 'SP-06'),
        ('impact_planning', 'Mutation impact planning',
         'CU impact planner', 'SP-09'),
        ('derived_intelligence', 'Workload, arm read, and Team State derivation',
         'CU and daily incremental services', 'SP-10'),
        ('read_model_rebuild', 'Snapshot and read-model rebuilding',
         'daily/postgame snapshot builders', 'SP-10/SP-11'),
        ('publication', 'Current public publication',
         'legacy dashboard/team publication paths', 'SP-11'),
        ('morning_reconciliation', 'Morning league reconciliation',
         'Render morning primary and GitHub fallback', 'SP-12'),
        ('nightly_closure', 'Nightly historical closure',
         'postgame/daily completeness behavior', 'SP-12'),
        ('repair_backfill', 'Repair and historical backfill',
         'manual intraday and one-off repair tools', 'SP-13'),
        ('request_time_writes', 'Request-time snapshot/cache fills',
         'legacy public request paths', 'SP-11 consumer migration'),
        ('scheduler_authority', 'Production scheduler authority',
         'Render primary plus GitHub scheduled fallback', 'SP-12/SP-14'),
        ('share_artifacts', 'Immutable share artifact generation',
         'legacy publication-linked share services', 'SP-11'),
    ]
    mapped = []
    for key, responsibility, legacy, owner in rows:
        publication_blocker = key in {
            'publication', 'read_model_rebuild', 'request_time_writes', 'share_artifacts',
        }
        natural_blocker = key in {
            'schedule_game_state', 'live_game_delta', 'final_game_reconciliation',
            'roster_transactions', 'morning_reconciliation', 'nightly_closure',
        }
        retirement_type = (
            'DEFER_RETIREMENT' if publication_blocker
            else 'RETAIN_AS_PRIMARY'
        )
        mapped.append({
            'responsibility_key': key,
            'responsibility': responsibility,
            'legacy_owner': legacy,
            'new_owner': owner,
            'current_production_authority': legacy,
            'new_pipeline_readiness': 'blocked' if publication_blocker else 'shadow_required',
            'required_proof': (
                'Publication-bound consumer migration and mixed-generation proof.'
                if publication_blocker else
                'Natural production shadow lineage and recovery evidence.'
                if natural_blocker else
                'Parity, bounded-scope, recovery, and observability evidence.'
            ),
            'retirement_condition': (
                'All relevant SP-14 gates pass and no consumer depends on the legacy write.'
            ),
            'planned_transition_action': (
                'Keep active; shadow the new owner; disable before any later deletion.'
            ),
            'rollback_path': common_rollback,
            'retirement_type': retirement_type,
        })
    return tuple(mapped)


def classify_operational_health(signals):
    blockers = []
    degraded = []
    blocking_fields = {
        'dead_jobs': 'dead_job_present',
        'missing_roster_authority_teams': 'thirty_team_roster_authority_incomplete',
        'unreconciled_final_games': 'unreconciled_final_game',
        'current_publication_missing': 'atomic_current_publication_missing',
        'publication_pointer_inconsistencies': 'publication_pointer_inconsistent',
        'blocked_closures': 'baseball_date_closure_blocked',
        'blocked_repairs': 'repair_request_blocked',
    }
    degraded_fields = {
        'retry_wait_jobs': 'jobs_waiting_to_retry',
        'stale_leases': 'stale_job_lease',
        'failed_source_attempts': 'recent_source_failure',
        'partial_source_attempts': 'recent_source_partial',
        'overdue_game_polls': 'overdue_game_poll',
        'live_games_without_recent_observation': 'live_observation_overdue',
        'pending_impact_plans': 'impact_plan_awaiting_dispatch',
        'running_or_stale_cohorts': 'derived_cohort_not_complete',
        'publication_candidates': 'publication_candidate_waiting',
        'cache_handoff_failures': 'cache_handoff_retrying',
        'active_repairs': 'repair_request_active',
        'continuous_unhealthy_runs': 'continuous_update_required_obligation_unresolved',
    }
    for field, reason in blocking_fields.items():
        if int(signals.get(field) or 0) > 0:
            blockers.append(reason)
    for field, reason in degraded_fields.items():
        if int(signals.get(field) or 0) > 0:
            degraded.append(reason)
    status = 'blocked' if blockers else 'degraded' if degraded else 'healthy'
    return {
        'status': status,
        'blockers': sorted(blockers),
        'degraded_conditions': sorted(degraded),
        'signals': signals,
    }


def collect_operational_health(*, now=None, source_window_hours=24, live_stale_minutes=5):
    """Read-only bounded operational health query over SP-01 through SP-13."""
    now = now or utc_now_naive()
    source_cutoff = now - timedelta(hours=source_window_hours)
    live_cutoff = now - timedelta(minutes=live_stale_minutes)

    queue_counts = dict(
        db.session.query(SyncJob.status, func.count(SyncJob.id)).group_by(SyncJob.status).all()
    )
    final_game_pks = {
        row[0] for row in db.session.query(ScheduledGame.game_pk).filter(
            ScheduledGame.operational_state == 'final',
        ).distinct().all()
    }
    reconciled_game_pks = {
        row[0] for row in db.session.query(FinalGameVersion.game_pk).filter(
            FinalGameVersion.is_current.is_(True),
            FinalGameVersion.core_completeness == 'complete',
        ).all()
    }
    live_game_pks = {
        row[0] for row in db.session.query(ScheduledGame.game_pk).filter(
            ScheduledGame.operational_state == 'live',
        ).distinct().all()
    }
    recently_observed_live = {
        row[0] for row in db.session.query(GameObservationState.mlb_game_pk).filter(
            GameObservationState.source_observed_at >= live_cutoff,
        ).all()
    }

    pointer_inconsistencies = 0
    pointer = db.session.get(AtomicPublicationCurrent, 1)
    current_publication_id = None
    if pointer is not None:
        current_publication_id = pointer.publication_id
        publication = db.session.get(AtomicPublication, pointer.publication_id)
        if publication is None or publication.status != 'published':
            pointer_inconsistencies += 1
        elif AtomicPublicationArtifact.query.filter_by(publication_id=publication.id).count() == 0:
            pointer_inconsistencies += 1

    roster_date = now.replace(tzinfo=timezone.utc).astimezone(
        ZoneInfo('America/New_York')
    ).date()
    roster_authority = roster_authority_coverage(roster_date, now=now)
    roster_team_count = roster_authority['active_roster_coverage_count']
    continuous_runs = SyncRun.query.filter(
        SyncRun.job_name == 'continuous_cycle',
        SyncRun.started_at >= source_cutoff,
    ).all()
    continuous_outcomes = [
        (run.outcome_json or {}).get('observation_outcomes') or {}
        for run in continuous_runs
    ]
    last_shadow_job = SyncJob.query.filter_by(
        job_family='sync_pipeline_shadow',
        status='succeeded',
    ).order_by(SyncJob.completed_at.desc(), SyncJob.id.desc()).first()
    signals = {
        'queue_depth_by_status': queue_counts,
        'pending_jobs': queue_counts.get('pending', 0),
        'running_jobs': queue_counts.get('running', 0),
        'retry_wait_jobs': queue_counts.get('retry_wait', 0),
        'dead_jobs': queue_counts.get('dead', 0),
        'stale_leases': SyncJob.query.filter(
            SyncJob.status == 'running', SyncJob.lease_until < now,
        ).count(),
        'failed_source_attempts': SourceFetchAttempt.query.filter(
            SourceFetchAttempt.started_at >= source_cutoff,
            SourceFetchAttempt.status == 'failed',
        ).count(),
        'partial_source_attempts': SourceFetchAttempt.query.filter(
            SourceFetchAttempt.started_at >= source_cutoff,
            SourceFetchAttempt.status == 'partial',
        ).count(),
        'overdue_game_polls': db.session.query(func.count(func.distinct(ScheduledGame.game_pk))).filter(
            ScheduledGame.operational_state.in_(('scheduled', 'pregame', 'live', 'delayed')),
            ScheduledGame.next_poll_at.isnot(None), ScheduledGame.next_poll_at < now,
        ).scalar() or 0,
        'live_games_without_recent_observation': len(live_game_pks - recently_observed_live),
        'unreconciled_final_games': len(final_game_pks - reconciled_game_pks),
        'roster_authority_team_count': int(roster_team_count),
        'missing_roster_authority_teams': max(0, 30 - int(roster_team_count)),
        'roster_authority': roster_authority,
        'last_recurring_shadow_job_id': last_shadow_job.id if last_shadow_job else None,
        'last_recurring_shadow_completed_at': (
            last_shadow_job.completed_at.isoformat()
            if last_shadow_job and last_shadow_job.completed_at else None
        ),
        'last_shadow_morning_run_id': roster_authority['morning_sync_run_id'],
        'pending_impact_plans': CanonicalImpactPlan.query.filter_by(status='planned').count(),
        'running_or_stale_cohorts': DerivedIntelligenceCohort.query.filter(
            DerivedIntelligenceCohort.status.in_(('running', 'stale', 'failed')),
        ).count(),
        'publication_candidates': AtomicPublication.query.filter(
            AtomicPublication.status.in_(('preparing', 'ready')),
        ).count(),
        'current_publication_id': current_publication_id,
        'current_publication_missing': int(current_publication_id is None),
        'publication_pointer_inconsistencies': pointer_inconsistencies,
        'cache_handoff_failures': AtomicPublicationCacheHandoff.query.filter_by(
            status='retry_wait',
        ).count(),
        'blocked_closures': BaseballDateClosure.query.filter(
            BaseballDateClosure.status.in_(('blocked', 'reopened', 'failed')),
        ).count(),
        'active_repairs': RepairRequest.query.filter(
            RepairRequest.status.in_(('planned', 'running')),
        ).count(),
        'blocked_repairs': RepairRequest.query.filter(
            RepairRequest.status.in_(('blocked', 'failed')),
        ).count(),
        # Warning/no-op counts are intentionally observable but do not degrade
        # health. Only runs with unresolved required work are unhealthy.
        'continuous_warning_observations': sum(
            int(item.get('warnings') or 0) for item in continuous_outcomes
        ),
        'continuous_stale_observations': sum(
            int(item.get('stale') or 0) for item in continuous_outcomes
        ),
        'continuous_duplicate_observations': sum(
            int(item.get('duplicate') or 0) for item in continuous_outcomes
        ),
        'continuous_safe_rejections': sum(
            int(item.get('safe_rejection') or 0) for item in continuous_outcomes
        ),
        'continuous_blocking_ambiguities': sum(
            int(item.get('blocking_ambiguity') or 0) for item in continuous_outcomes
        ),
        'continuous_unhealthy_runs': sum(
            run.status in ('partial', 'failed') for run in continuous_runs
        ),
        'measured_at': now.isoformat(),
    }
    return classify_operational_health(signals)


def certification_checks(*, migration_heads, integration_sha_matches, controls,
                         evidence=None, health=None):
    """Build all ten gates. Missing proof is BLOCKED, never inferred as PASS."""
    evidence = evidence or {}
    health = health or {'status': 'healthy', 'signals': {}}
    checks = []

    migration_ok = list(migration_heads) == [EXPECTED_MIGRATION_HEAD]
    checks.append({
        'gate_key': 'A', 'check_key': 'single_migration_head',
        'status': 'passing' if migration_ok else 'failed', 'critical': True,
        'summary': (
            f'One Alembic head at {EXPECTED_MIGRATION_HEAD}.' if migration_ok
            else f'Expected only {EXPECTED_MIGRATION_HEAD}; got {list(migration_heads)}.'
        ),
        'evidence': {'migration_heads': list(migration_heads)},
    })
    checks.append({
        'gate_key': 'A', 'check_key': 'exact_integration_commit',
        'status': 'passing' if integration_sha_matches else 'failed', 'critical': True,
        'summary': 'Certification checkout matches the requested integration commit.' if integration_sha_matches
                   else 'Certification checkout does not match the requested integration commit.',
        'evidence': {},
    })

    violations = validate_activation_controls(controls)
    checks.append({
        'gate_key': 'B', 'check_key': 'activation_controls_safe',
        'status': 'passing' if not violations else 'failed', 'critical': True,
        'summary': 'Activation controls are fail-closed.' if not violations
                   else 'Unsafe activation control combination.',
        'evidence': {'controls': asdict(controls), 'violations': list(violations)},
    })
    if health.get('status') == 'blocked':
        checks.append({
            'gate_key': 'B', 'check_key': 'operational_health', 'status': 'blocked',
            'critical': True, 'summary': 'Operational health has blocking obligations.',
            'evidence': health,
        })

    for gate_key in GATES:
        supplied = evidence.get(gate_key)
        if supplied:
            for item in supplied if isinstance(supplied, list) else [supplied]:
                status = item.get('status', 'not_run')
                if status not in CHECK_STATUSES:
                    raise ValueError(f'Unsupported certification status {status!r}.')
                checks.append({
                    'gate_key': gate_key,
                    'check_key': item.get('check_key', 'external_evidence'),
                    'status': status,
                    'critical': bool(item.get('critical', True)),
                    'summary': item.get('summary', 'Recorded certification evidence.'),
                    'evidence': item.get('evidence', {}),
                })
        if gate_key != 'A' and not supplied and not any(
            row['gate_key'] == gate_key and row['status'] in CRITICAL_NONPASSING
            for row in checks
        ):
            checks.append({
                'gate_key': gate_key, 'check_key': 'required_proof',
                'status': 'blocked', 'critical': True,
                'summary': f'{GATES[gate_key]} production/shadow proof has not been recorded.',
                'evidence': {},
            })
    return tuple(checks)


def evaluate_certification(checks):
    gate_statuses = {}
    failures = []
    warnings = []
    rank = {'failed': 5, 'blocked': 4, 'not_run': 3, 'warning': 2, 'passing': 1}
    for gate_key in GATES:
        rows = [row for row in checks if row['gate_key'] == gate_key]
        gate_statuses[gate_key] = max(rows, key=lambda row: rank[row['status']])['status']
    for row in checks:
        if row['critical'] and row['status'] in CRITICAL_NONPASSING:
            failures.append(f"Gate {row['gate_key']} {row['check_key']}: {row['summary']}")
        elif row['status'] == 'warning':
            warnings.append(f"Gate {row['gate_key']} {row['check_key']}: {row['summary']}")
    verdict = 'NO-GO' if failures else 'GO'
    return {
        'certification_version': CERTIFICATION_VERSION,
        'verdict': verdict,
        'gate_statuses': gate_statuses,
        'checks': list(checks),
        'failures': failures,
        'warnings': warnings,
    }


def persist_certification_report(report, *, integration_commit_sha, migration_head,
                                 environment, controls, natural_proof=None,
                                 production_identifiers=None, sync_run_id=None):
    """Persist one immutable report; identical evidence reuses the same row."""
    identity = {
        'version': CERTIFICATION_VERSION,
        'sha': integration_commit_sha,
        'migration_head': migration_head,
        'environment': environment,
        'configuration_fingerprint': controls.fingerprint,
        'checks': report['checks'],
    }
    key = _fingerprint(identity)
    existing = SyncCertificationRun.query.filter_by(certification_key=key).first()
    if existing is not None:
        return existing
    now = utc_now_naive()
    row = SyncCertificationRun(
        certification_key=key,
        certification_version=CERTIFICATION_VERSION,
        integration_commit_sha=integration_commit_sha,
        migration_head=migration_head,
        environment=environment,
        configuration_fingerprint=controls.fingerprint,
        status='certified' if report['verdict'] == 'GO' else 'blocked',
        verdict=report['verdict'],
        gate_statuses_json=report['gate_statuses'],
        natural_proof_identifiers_json=natural_proof or {},
        production_identifiers_json=production_identifiers or {},
        failures_json=report['failures'], warnings_json=report['warnings'],
        sync_run_id=sync_run_id, started_at=now, completed_at=now,
    )
    db.session.add(row)
    db.session.flush()
    for item in report['checks']:
        db.session.add(SyncCertificationCheck(
            certification_run_id=row.id,
            gate_key=item['gate_key'], check_key=item['check_key'],
            status=item['status'], critical=item['critical'],
            summary=item['summary'], evidence_json=item.get('evidence') or {},
            measured_at=now,
        ))
    db.session.commit()
    return row


def persist_legacy_responsibility_map(*, evidence=None):
    """Create missing transition rows without rewriting prior decisions."""
    evidence = evidence or {}
    created = []
    for item in legacy_responsibility_map():
        if SyncLegacyTransitionState.query.filter_by(
            responsibility_key=item['responsibility_key'],
        ).first() is not None:
            continue
        row = SyncLegacyTransitionState(
            **item,
            evidence_json=evidence.get(item['responsibility_key'], {}),
        )
        db.session.add(row)
        created.append(row)
    db.session.commit()
    return tuple(created)


__all__ = [
    'ActivationControls', 'CERTIFICATION_VERSION', 'EXPECTED_MIGRATION_HEAD',
    'GATES', 'certification_checks', 'classify_operational_health',
    'collect_operational_health', 'evaluate_certification',
    'legacy_responsibility_map', 'persist_certification_report',
    'persist_legacy_responsibility_map', 'validate_activation_controls',
]
