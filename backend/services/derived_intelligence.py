"""SP-10 plan-driven, non-publishing derived intelligence cohorts."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from enum import Enum
import hashlib
import json
from types import SimpleNamespace

from sqlalchemy.exc import IntegrityError

from models.canonical_impact import CanonicalImpactPlan
from models.derived_intelligence import (
    DerivedCohortInput,
    DerivedCohortSnapshot,
    DerivedIntelligenceCohort,
    DerivedIntelligenceCohortDomain,
)
from models.final_game_reconciliation import FinalGameVersion, FinalPitchingAppearanceVersion
from models.live_game_delta import ProvisionalPitchingAppearanceState
from models.pregame_context import GamePregameContextVersion
from models.roster_membership import RosterMembershipInterval
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.canonical_impact import AuthorityClass, ImpactDomain
from services.incremental_arm_read_team_state import recompute_arm_reads_team_state
from services.incremental_read_model_rebuild import rebuild_read_model_impact
from services.incremental_workload_rest import recompute_workload_rest_impact
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
from services.team_readiness_coverage import resolve_active_bullpen_membership
from utils.db import db
from utils.time import utc_now_naive


COHORT_SCHEMA_VERSION = 'derived-cohort-v1'
DERIVED_INPUT_PAYLOAD_VERSION = 1
PUBLICATION_PAYLOAD_VERSION = 1
PRIORITY_PUBLICATION_CANDIDATE = 70


class CohortStatus(str, Enum):
    RUNNING = 'running'
    COMPLETE = 'complete'
    PARTIAL = 'partial'
    STALE = 'stale'
    FAILED = 'failed'
    SUPERSEDED = 'superseded'


class DomainStatus(str, Enum):
    REQUESTED = 'requested'
    PREREQUISITE = 'prerequisite'
    SUCCEEDED = 'succeeded'
    WITHHELD = 'withheld'
    FAILED = 'failed'
    SKIPPED = 'skipped'
    STALE = 'stale'


# A prerequisite is included only when its dependent domain is requested.
DOMAIN_DEPENDENCIES = {
    'rest': ('workload',),
    'arm_read': ('workload', 'rest'),
    'concentration': ('workload',),
    'clean_options': ('roster_composition', 'arm_read'),
    'bullpen_churn': ('roster_composition',),
    'role_movement': ('deployment',),
    'team_state': ('roster_composition', 'workload', 'rest', 'arm_read', 'concentration', 'clean_options'),
    'pitcher_snapshot': ('workload', 'rest', 'arm_read'),
    'team_snapshot': ('roster_composition', 'workload', 'rest', 'arm_read', 'team_state'),
    'matchup_context': ('game_context',),
    'read_models': (),
    'what_changed': ('team_snapshot',),
}

DOMAIN_EXECUTION_ORDER = (
    'roster_composition', 'organizational_depth', 'workload', 'workload_current',
    'team_workload_current', 'rest', 'deployment', 'performance',
    'rotation_transfer', 'concentration', 'bullpen_churn', 'arm_read',
    'clean_options', 'team_state', 'role_movement', 'pitcher_snapshot',
    'team_snapshot', 'game_context', 'matchup_context', 'read_models',
    'what_changed',
)

METHOD_VERSIONS = {
    'workload': 'cu04-authoritative-v1',
    'workload_current': 'sp08-provisional-v1',
    'team_workload_current': 'sp08-provisional-v1',
    'rest': 'cu04-authoritative-v1',
    'roster_composition': 'sp05-membership-interval-v1',
    'organizational_depth': 'sp05-membership-interval-v1',
    'bullpen_churn': 'sp05-membership-mutation-v1',
    'deployment': 'existing-deployment-v1',
    'role_movement': 'existing-observed-role-v1',
    'performance': 'era-1.1.0_whip-1.0.0',
    'rotation_transfer': '2026-06-18.phase2',
    'concentration': 'existing-workload-concentration-v1',
    'clean_options': 'existing-arm-read-v1',
    'arm_read': 'existing-arm-read-v1',
    'team_state': 'existing-team-state-v1',
    'pitcher_snapshot': 'derived-candidate-v1',
    'team_snapshot': 'derived-candidate-v1',
    'game_context': 'sp06-context-v1',
    'matchup_context': 'existing-matchup-v1',
    'read_models': 'cu06-publication-artifacts-v2',
    'what_changed': 'what-changed-publication-v1',
}


@dataclass(frozen=True)
class CohortExecutionResult:
    cohort: DerivedIntelligenceCohort | None
    created: bool
    publication_job: SyncJob | None
    zero_work: bool = False


def dependency_closure(requested_domains):
    requested = {str(value.value if isinstance(value, Enum) else value) for value in requested_domains}
    unknown = requested.difference(item.value for item in ImpactDomain)
    if unknown:
        raise ValueError(f'Unknown derived domains: {sorted(unknown)}')
    expanded = set(requested)
    pending = list(requested)
    while pending:
        domain = pending.pop()
        for dependency in DOMAIN_DEPENDENCIES.get(domain, ()):
            if dependency not in expanded:
                expanded.add(dependency)
                pending.append(dependency)
    return tuple(domain for domain in DOMAIN_EXECUTION_ORDER if domain in expanded)


def capture_input_manifest(plan):
    """Capture current version identities without copying source payloads."""
    entries = []
    authority = plan.authority_class
    games = [int(value) for value in plan.affected_game_ids_json or ()]
    teams = [int(value) for value in plan.affected_team_ids_json or ()]
    pitchers = [int(value) for value in plan.affected_pitcher_ids_json or ()]

    if authority in (AuthorityClass.FINAL.value, AuthorityClass.CORRECTED_FINAL.value):
        game_rows = FinalGameVersion.query.filter(
            FinalGameVersion.game_pk.in_(games), FinalGameVersion.is_current.is_(True),
        ).order_by(FinalGameVersion.game_pk).all() if games else []
        for row in game_rows:
            entries.append(_entry('final_game', row.game_pk, row.id, row.fact_fingerprint,
                                  authority, row.boxscore_observation_id))
        query = FinalPitchingAppearanceVersion.query.filter(
            FinalPitchingAppearanceVersion.is_current.is_(True)
        )
        if games:
            query = query.filter(FinalPitchingAppearanceVersion.game_pk.in_(games))
        if pitchers:
            query = query.filter(FinalPitchingAppearanceVersion.pitcher_id.in_(pitchers))
        for row in query.order_by(
            FinalPitchingAppearanceVersion.game_pk,
            FinalPitchingAppearanceVersion.pitcher_id,
        ).all():
            entries.append(_entry(
                'final_appearance', f'{row.game_pk}:{row.pitcher_id}', row.id,
                row.fact_fingerprint, authority, row.boxscore_observation_id,
            ))
    elif authority == AuthorityClass.LIVE.value:
        query = ProvisionalPitchingAppearanceState.query.filter(
            ProvisionalPitchingAppearanceState.is_current.is_(True)
        )
        if games:
            query = query.filter(ProvisionalPitchingAppearanceState.game_pk.in_(games))
        if pitchers:
            query = query.filter(ProvisionalPitchingAppearanceState.pitcher_id.in_(pitchers))
        for row in query.order_by(
            ProvisionalPitchingAppearanceState.game_pk,
            ProvisionalPitchingAppearanceState.pitcher_id,
        ).all():
            entries.append(_entry(
                'live_appearance', f'{row.game_pk}:{row.pitcher_id}', row.id,
                row.fact_fingerprint, authority, row.latest_observation_id,
            ))
    elif authority == AuthorityClass.PREGAME_AUTHORITATIVE.value:
        for game_pk in games:
            row = GamePregameContextVersion.query.filter_by(game_pk=game_pk).order_by(
                GamePregameContextVersion.version_number.desc()
            ).first()
            if row:
                entries.append(_entry('pregame_context', game_pk, row.id,
                                      row.context_fingerprint, authority, row.source_observation_id))

    if authority == AuthorityClass.ROSTER_AUTHORITATIVE.value or any(
        domain in (plan.affected_domains_json or ())
        for domain in ('roster_composition', 'organizational_depth', 'team_state', 'clean_options')
    ):
        query = RosterMembershipInterval.query.filter(
            RosterMembershipInterval.is_current_version.is_(True),
            RosterMembershipInterval.is_void.is_(False),
            RosterMembershipInterval.effective_start_date <= plan.baseball_date,
            db.or_(
                RosterMembershipInterval.effective_end_date.is_(None),
                RosterMembershipInterval.effective_end_date >= plan.baseball_date,
            ),
        )
        if teams:
            query = query.filter(RosterMembershipInterval.team_id.in_(teams))
        elif pitchers:
            query = query.filter(RosterMembershipInterval.pitcher_id.in_(pitchers))
        for row in query.order_by(RosterMembershipInterval.id).all():
            version = f'{row.id}:{row.effective_start_date}:{row.effective_end_date or "open"}'
            entries.append(_entry(
                'roster_membership', f'{row.team_id}:{row.pitcher_id}:{row.membership_type}',
                version, None, AuthorityClass.ROSTER_AUTHORITATIVE.value,
                row.opened_by_observation_id,
            ))

    for observation_id in sorted(set(plan.source_observation_ids_json or ())):
        entries.append(_entry('source_observation', observation_id, observation_id, None,
                              authority, observation_id))
    return sorted(entries, key=lambda item: (item['input_type'], item['input_key'], item['input_version']))


def cohort_fingerprint(plan, manifest, execution_domains, method_versions=None):
    value = {
        'schema_version': COHORT_SCHEMA_VERSION,
        'impact_plan_fingerprint': plan.plan_fingerprint,
        'authority_class': plan.authority_class,
        'inputs': manifest,
        'execution_domains': sorted(execution_domains),
        'method_versions': method_versions or method_version_manifest(execution_domains),
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(',', ':'), default=str).encode('utf-8')
    ).hexdigest()


def method_version_manifest(domains):
    return {domain: METHOD_VERSIONS[domain] for domain in sorted(domains)}


def execute_derived_intelligence_plan(
    plan_id, *, sync_run_id=None, domain_executor=None, before_revalidate=None,
    lease_fence=None, publication_candidate_enabled=True, commit=True,
):
    plan = db.session.get(CanonicalImpactPlan, int(plan_id))
    if plan is None:
        raise ValueError(f'Impact plan {plan_id} does not exist.')
    requested = tuple(sorted(set(plan.affected_domains_json or ())))
    if not requested:
        return CohortExecutionResult(None, False, None, zero_work=True)
    if plan.status == 'superseded':
        return CohortExecutionResult(None, False, None, zero_work=True)

    execution = dependency_closure(requested)
    manifest = capture_input_manifest(plan)
    versions = method_version_manifest(execution)
    overrides = dict(getattr(plan, 'method_versions_override_json', None) or {})
    unknown_overrides = set(overrides).difference(execution)
    if unknown_overrides:
        raise ValueError(f'Method-version overrides are outside the execution domains: {sorted(unknown_overrides)}')
    if any(not str(value).strip() for value in overrides.values()):
        raise ValueError('Method-version overrides must be non-empty strings.')
    versions.update({key: str(value) for key, value in overrides.items()})
    fingerprint = cohort_fingerprint(plan, manifest, execution, versions)
    existing = DerivedIntelligenceCohort.query.filter_by(
        cohort_fingerprint=fingerprint
    ).one_or_none()
    if existing is not None:
        publication = db.session.get(SyncJob, existing.publication_job_id) if existing.publication_job_id else None
        return CohortExecutionResult(existing, False, publication)

    predecessor = _latest_comparable_cohort(plan)
    supersedes = None
    if plan.authority_class in (AuthorityClass.FINAL.value, AuthorityClass.CORRECTED_FINAL.value):
        supersedes = _latest_live_cohort(plan.affected_game_ids_json or ())

    cohort = DerivedIntelligenceCohort(
        impact_plan_id=plan.id, cohort_fingerprint=fingerprint,
        schema_version=COHORT_SCHEMA_VERSION, authority_class=plan.authority_class,
        baseball_date=plan.baseball_date, correlation_id=plan.correlation_id,
        status=CohortStatus.RUNNING.value, requested_domains_json=list(requested),
        execution_domains_json=list(execution), completed_domains_json=[],
        withheld_domains_json=[], affected_game_ids_json=list(plan.affected_game_ids_json or ()),
        affected_team_ids_json=list(plan.affected_team_ids_json or ()),
        affected_pitcher_ids_json=list(plan.affected_pitcher_ids_json or ()),
        input_manifest_json=manifest, method_versions_json=versions,
        predecessor_cohort_id=predecessor.id if predecessor else None,
        supersedes_cohort_id=supersedes.id if supersedes else None,
        sync_run_id=sync_run_id,
    )
    try:
        with db.session.begin_nested():
            db.session.add(cohort)
            db.session.flush()
            _persist_inputs(cohort, manifest)
            for domain in execution:
                db.session.add(DerivedIntelligenceCohortDomain(
                    cohort_id=cohort.id, domain=domain,
                    status=(DomainStatus.REQUESTED.value if domain in requested else DomainStatus.PREREQUISITE.value),
                    prerequisite=domain not in requested, method_version=versions[domain],
                ))
            db.session.flush()
    except IntegrityError:
        cohort = DerivedIntelligenceCohort.query.filter_by(
            cohort_fingerprint=fingerprint
        ).one()
        publication = db.session.get(SyncJob, cohort.publication_job_id) if cohort.publication_job_id else None
        return CohortExecutionResult(cohort, False, publication)

    executor = domain_executor or _DefaultDomainExecutor(plan)
    failed = set()
    completed = []
    withheld = []
    snapshots = {'pitcher': {}, 'team': {}, 'game': {}}
    for domain in execution:
        if lease_fence is not None:
            lease_fence()
        row = DerivedIntelligenceCohortDomain.query.filter_by(
            cohort_id=cohort.id, domain=domain
        ).one()
        blockers = [value for value in DOMAIN_DEPENDENCIES.get(domain, ()) if value in failed]
        row.started_at = utc_now_naive()
        if blockers:
            row.status = DomainStatus.WITHHELD.value
            row.error_class = 'DependencyUnavailable'
            row.error_message = ','.join(sorted(blockers))
            withheld.append(domain)
            failed.add(domain)
        else:
            try:
                result = executor(domain, snapshots)
                row.status = DomainStatus.SUCCEEDED.value
                row.result_summary_json = _result_summary(result)
                completed.append(domain)
                _merge_snapshots(snapshots, result)
            except Exception as exc:
                row.status = DomainStatus.FAILED.value
                row.error_class = type(exc).__name__
                row.error_message = str(exc)[:2000]
                withheld.append(domain)
                failed.add(domain)
        row.completed_at = utc_now_naive()

    if before_revalidate is not None:
        before_revalidate()
        db.session.flush()
    if lease_fence is not None:
        lease_fence()
    db.session.refresh(plan)
    current_manifest = capture_input_manifest(plan)
    if current_manifest != manifest or plan.status == 'superseded':
        cohort.status = CohortStatus.STALE.value
        cohort.completed_domains_json = completed
        cohort.withheld_domains_json = sorted(set(withheld) | set(execution))
        for row in DerivedIntelligenceCohortDomain.query.filter_by(cohort_id=cohort.id).all():
            row.status = DomainStatus.STALE.value
        publication = None
    else:
        _persist_snapshots(cohort, snapshots)
        cohort.completed_domains_json = completed
        cohort.withheld_domains_json = withheld
        cohort.status = (
            CohortStatus.COMPLETE.value if not withheld
            else CohortStatus.PARTIAL.value if completed
            else CohortStatus.FAILED.value
        )
        publication = (
            enqueue_publication_candidate(cohort, plan)
            if (
                publication_candidate_enabled
                and _publication_eligible(cohort)
                and getattr(plan, 'publication_mode', 'current') == 'current'
            )
            else None
        )
        if publication is not None:
            cohort.publication_job_id = publication.id
    cohort.completed_at = utc_now_naive()
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return CohortExecutionResult(cohort, True, publication)


class _DefaultDomainExecutor:
    """Adapter over the proven CU calculators; all outputs remain candidates."""

    def __init__(self, plan):
        self.plan = plan
        self.cache = {}

    def __call__(self, domain, snapshots):
        if self.plan.authority_class == AuthorityClass.LIVE.value:
            return self._live(domain)
        if domain in ('roster_composition', 'organizational_depth', 'bullpen_churn'):
            return self._roster(domain)
        if domain in ('workload', 'rest', 'concentration'):
            return self._workload(domain)
        if domain in ('arm_read', 'clean_options', 'team_state'):
            return self._team_state(domain)
        if self.plan.authority_class == AuthorityClass.PREGAME_AUTHORITATIVE.value and domain in (
            'game_context', 'matchup_context', 'read_models',
        ):
            return self._pregame(domain)
        if domain == 'game_context':
            return self._final_context(domain)
        return self._read_models(domain)

    def _impact(self):
        return SimpleNamespace(
            game_pk=(self.plan.affected_game_ids_json or [None])[0],
            affected_pitcher_ids=tuple(self.plan.affected_pitcher_ids_json or ()),
            affected_team_ids=tuple(self.plan.affected_team_ids_json or ()),
            canonical_mutation_performed=True,
        )

    def _workload_result(self):
        if 'workload_result' not in self.cache:
            self.cache['workload_result'] = recompute_workload_rest_impact(
                self._impact(), data_through=self.plan.baseball_date,
            )
            if self.cache['workload_result'].status != 'complete':
                raise RuntimeError(self.cache['workload_result'].reason_code)
        return self.cache['workload_result']

    def _team_result(self):
        if 'team_result' not in self.cache:
            self.cache['team_result'] = recompute_arm_reads_team_state(self._workload_result())
            if self.cache['team_result'].status != 'complete':
                raise RuntimeError(self.cache['team_result'].reason_code)
        return self.cache['team_result']

    def _read_result(self):
        if 'read_result' not in self.cache:
            self.cache['read_result'] = rebuild_read_model_impact(
                self._team_result(),
                publication_artifact_baseline=self._publication_baseline_required(),
                build_publication_artifacts=True,
                predecessor_cohort_id=(
                    self.cache.get('predecessor_cohort_id')
                    or getattr(_latest_comparable_cohort(self.plan), 'id', None)
                ),
            )
            if self.cache['read_result'].status != 'complete':
                raise RuntimeError(self.cache['read_result'].reason_code)
        return self.cache['read_result']

    def _publication_baseline_required(self):
        """Materialize full reader coverage until one complete generation exists."""
        if 'publication_baseline_required' not in self.cache:
            from services.atomic_publication import get_current_publication
            from services.atomic_publication_reads import publication_reader_coverage

            current = get_current_publication()
            self.cache['publication_baseline_required'] = (
                current is None or not publication_reader_coverage(current.id).get('complete')
            )
        return self.cache['publication_baseline_required']

    def _workload(self, domain):
        result = self._workload_result()
        return {
            'pitcher': {str(k): {domain: v} for k, v in result.pitcher_results.items()},
            'team': {str(k): {domain: v} for k, v in result.team_results.items()},
            'summary': {'pitchers': len(result.pitcher_results), 'teams': len(result.team_results)},
        }

    def _team_state(self, domain):
        result = self._team_result()
        pitcher_values = result.arm_read_results if domain in ('arm_read', 'clean_options') else {}
        team_values = result.team_state_results
        return {
            'pitcher': {str(k): {domain: v} for k, v in pitcher_values.items()},
            'team': {str(k): {domain: v} for k, v in team_values.items()},
            'summary': {'pitchers': len(pitcher_values), 'teams': len(team_values)},
        }

    def _read_models(self, domain):
        result = self._read_result()
        if domain == 'team_snapshot':
            output = {
                'team': {
                    str(k): {domain: v}
                    for k, v in result.team_package_results.items()
                },
                'summary': {'teams': len(result.team_package_results)},
            }
            # Before the first reader-complete publication exists, the read
            # rebuild intentionally materializes a league-wide baseline.  A
            # bounded roster/final plan does not necessarily request the
            # ``read_models`` domain, so retain those already-built immutable
            # publication candidates alongside the team snapshot.  This is a
            # one-time baseline packaging concern; normal post-baseline plans
            # remain bounded by their requested domains.
            if self._publication_baseline_required():
                for team_id, value in result.team_board_v2_results.items():
                    output['team'].setdefault(str(team_id), {}).setdefault(
                        'read_models', {}
                    )['team_board_v2'] = value
                for team_id, value in result.what_changed_results.items():
                    output['team'].setdefault(str(team_id), {})['what_changed'] = value
                output['pitcher'] = {
                    str(pitcher_id): {
                        'read_models': {'pitcher_current': value},
                    }
                    for pitcher_id, value in result.pitcher_current_results.items()
                }
                output['summary'].update({
                    'team_board_v2_artifacts': len(result.team_board_v2_results),
                    'pitcher_current_artifacts': len(result.pitcher_current_results),
                    'what_changed_artifacts': len(result.what_changed_results),
                })
            return output
        if domain == 'read_models':
            baseline = self._publication_baseline_required()
            return {
                'team': {
                    str(k): {
                        domain: {
                            'team_board': result.team_board_results.get(k),
                            'team_board_v2': result.team_board_v2_results.get(k),
                            'league_row': result.league_row_results.get(k),
                        },
                        **(
                            {'what_changed': result.what_changed_results[k]}
                            if baseline and k in result.what_changed_results else {}
                        ),
                    }
                    for k in (
                        set(result.team_board_results)
                        | set(result.team_board_v2_results)
                        | set(result.league_row_results)
                        | (set(result.what_changed_results) if baseline else set())
                    )
                },
                'pitcher': {
                    str(k): {domain: {'pitcher_current': value}}
                    for k, value in result.pitcher_current_results.items()
                },
                'game': {
                    str(k): {domain: {
                        'matchup': result.matchup_results.get(k),
                        'tonight': result.tonight_results.get(k),
                    }}
                    for k in set(result.matchup_results) | set(result.tonight_results)
                },
                'summary': {
                    'teams': len(result.team_board_results),
                    'games': len(result.matchup_results),
                },
            }
        return {
            'team': (
                {
                    str(k): {'what_changed': value}
                    for k, value in result.what_changed_results.items()
                }
                if domain == 'what_changed' else {}
            ),
            'summary': {
                'domain': domain,
                'derived_by': 'cu06_shadow_package',
                'teams': len(result.team_package_results),
            },
        }

    def _roster(self, domain):
        values = {}
        for team_id in self.plan.affected_team_ids_json or ():
            ids, complete = resolve_active_bullpen_membership(team_id, self.plan.baseball_date)
            if not complete:
                raise RuntimeError(f'roster_authority_incomplete:{team_id}')
            values[str(team_id)] = {domain: {'pitcher_ids': sorted(ids), 'authority_complete': True}}
        return {'team': values, 'summary': {'teams': len(values)}}

    def _pregame(self, domain):
        values = {}
        for game_pk in self.plan.affected_game_ids_json or ():
            row = GamePregameContextVersion.query.filter_by(game_pk=game_pk).order_by(
                GamePregameContextVersion.version_number.desc()
            ).first()
            if row is None:
                raise RuntimeError(f'pregame_context_unavailable:{game_pk}')
            values[str(game_pk)] = {domain: {
                'context_version_id': row.id,
                'home_probable_pitcher_id': row.home_probable_pitcher_id,
                'away_probable_pitcher_id': row.away_probable_pitcher_id,
                'scheduled_at': row.scheduled_at.isoformat() if row.scheduled_at else None,
            }}
        return {'game': values, 'summary': {'games': len(values)}}

    def _final_context(self, domain):
        values = {}
        for game_pk in self.plan.affected_game_ids_json or ():
            row = FinalGameVersion.query.filter_by(game_pk=game_pk, is_current=True).one_or_none()
            if row is None:
                raise RuntimeError(f'final_game_context_unavailable:{game_pk}')
            values[str(game_pk)] = {domain: {
                'final_game_version_id': row.id,
                'home_team_id': row.home_team_id, 'away_team_id': row.away_team_id,
                'home_score': row.home_score, 'away_score': row.away_score,
                'innings_played': row.innings_played, 'extra_innings': row.extra_innings,
            }}
        return {'game': values, 'summary': {'games': len(values)}}

    def _live(self, domain):
        if domain not in ('workload_current', 'team_workload_current', 'game_context'):
            raise RuntimeError(f'live_domain_not_authorized:{domain}')
        query = ProvisionalPitchingAppearanceState.query.filter(
            ProvisionalPitchingAppearanceState.is_current.is_(True),
            ProvisionalPitchingAppearanceState.game_pk.in_(self.plan.affected_game_ids_json or [-1]),
        )
        rows = query.order_by(ProvisionalPitchingAppearanceState.pitcher_id).all()
        pitcher = {}
        team = {}
        game = {}
        for row in rows:
            fact = {
                'state_id': row.id, 'pitches': row.pitches_thrown,
                'outs': row.outs_recorded, 'batters_faced': row.batters_faced,
                'outing_status': row.outing_status,
            }
            pitcher[str(row.pitcher_id)] = {domain: fact}
            aggregate = team.setdefault(str(row.team_id_at_appearance), {domain: {'pitches': 0, 'outs': 0, 'pitchers': []}})
            target = aggregate[domain]
            target['pitches'] += row.pitches_thrown or 0
            target['outs'] += row.outs_recorded or 0
            target['pitchers'].append(row.pitcher_id)
            game.setdefault(str(row.game_pk), {domain: {'appearance_state_ids': []}})[domain]['appearance_state_ids'].append(row.id)
        return {'pitcher': pitcher, 'team': team, 'game': game, 'summary': {'appearances': len(rows)}}


def execute_derived_intelligence_job(job, *, publication_candidate_enabled=True):
    if job.payload_schema_version != DERIVED_INPUT_PAYLOAD_VERSION:
        raise ValueError(f'Unsupported derived intelligence payload version: {job.payload_schema_version!r}')
    payload = dict(job.details_json or {})
    plan = db.session.get(CanonicalImpactPlan, int(payload['impact_plan_id']))
    if plan is None:
        raise ValueError(f"Impact plan {payload['impact_plan_id']} does not exist.")
    if payload.get('rules_version') != plan.rules_version:
        raise ValueError('Impact-plan rules version does not match the queued payload.')
    run = _start_run(job, plan)
    try:
        mark_stage(run, RunStage.DERIVE, commit=False)
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False)
        result = execute_derived_intelligence_plan(
            plan.id,
            sync_run_id=run.id,
            publication_candidate_enabled=publication_candidate_enabled,
            lease_fence=lambda: heartbeat_job(
                job.id, worker_id=job.worker_id,
                claim_token=job.claim_token, commit=False,
            ),
            commit=False,
        )
        if result.cohort is not None:
            add_scopes(run, [
                *((ScopeType.GAME, value) for value in result.cohort.affected_game_ids_json),
                *((ScopeType.TEAM, value) for value in result.cohort.affected_team_ids_json),
                *((ScopeType.PITCHER, value) for value in result.cohort.affected_pitcher_ids_json),
            ], commit=False)
        record_outcome(
            run,
            affected_games=len(plan.affected_game_ids_json or ()),
            affected_teams=len(plan.affected_team_ids_json or ()),
            affected_pitchers=len(plan.affected_pitcher_ids_json or ()),
            downstream_work_created=int(result.publication_job is not None and result.created),
            outcome={
                'impact_plan_id': plan.id,
                'cohort_id': result.cohort.id if result.cohort else None,
                'cohort_status': result.cohort.status if result.cohort else 'no_work',
                'completed_domains': result.cohort.completed_domains_json if result.cohort else [],
                'withheld_domains': result.cohort.withheld_domains_json if result.cohort else [],
                'publication_candidate_job_id': result.publication_job.id if result.publication_job else None,
                'publication_mode': getattr(plan, 'publication_mode', 'current'),
                'replay_kind': getattr(plan, 'replay_kind', None),
            },
            commit=False,
        )
        final_status = RunStatus.PARTIAL if result.cohort and result.cohort.status == 'partial' else RunStatus.SUCCEEDED
        finalize_run(run, final_status, commit=False)
        db.session.commit()
        return {
            'sync_run_id': run.id, 'impact_plan_id': plan.id,
            'cohort_id': result.cohort.id if result.cohort else None,
            'cohort_status': result.cohort.status if result.cohort else 'no_work',
            'publication_candidate_job_id': result.publication_job.id if result.publication_job else None,
            'publication_mode': getattr(plan, 'publication_mode', 'current'),
        }
    except Exception as exc:
        db.session.rollback()
        record_failure(run.id, exc, failure_class=FailureClass.DERIVATION,
                       stage=RunStage.DERIVE, retryable=True, commit=False)
        finalize_run(run.id, RunStatus.FAILED, failed_stage=RunStage.DERIVE)
        raise


def run_derived_intelligence_worker_once(worker_id, *, lease_seconds=300):
    return run_next_job(
        worker_id,
        {JobType.PROCESS_DERIVED_INTELLIGENCE.value: execute_derived_intelligence_job},
        job_types=[JobType.PROCESS_DERIVED_INTELLIGENCE],
        lease_seconds=lease_seconds,
    )


def _start_run(job, plan):
    parent = db.session.get(SyncRun, job.sync_run_id) if job.sync_run_id else None
    run = create_run(
        run_type=RunType.INCREMENTAL_INTELLIGENCE,
        trigger_type=TriggerType.PARENT_RUN,
        source='derived_intelligence', job_name=JobType.PROCESS_DERIVED_INTELLIGENCE.value,
        baseball_date=plan.baseball_date, source_domain=SourceDomain.MULTI_DOMAIN,
        parent_sync_run_id=parent.id if parent else None,
        correlation_id=parent.correlation_id if parent else plan.correlation_id,
        scopes=(), commit=False,
    )
    job.sync_run_id = run.id
    db.session.commit()
    return start_run(run)


def _publication_eligible(cohort):
    return (
        cohort.status == CohortStatus.COMPLETE.value
        and cohort.authority_class != AuthorityClass.LIVE.value
        and bool(cohort.completed_domains_json)
    )


def _latest_comparable_cohort(plan):
    target_games = set(plan.affected_game_ids_json or ())
    target_teams = set(plan.affected_team_ids_json or ())
    target_pitchers = set(plan.affected_pitcher_ids_json or ())
    comparable_authorities = (
        (AuthorityClass.FINAL.value, AuthorityClass.CORRECTED_FINAL.value)
        if plan.authority_class in (
            AuthorityClass.FINAL.value, AuthorityClass.CORRECTED_FINAL.value,
        )
        else (plan.authority_class,)
    )
    rows = DerivedIntelligenceCohort.query.filter(
        DerivedIntelligenceCohort.authority_class.in_(comparable_authorities),
        DerivedIntelligenceCohort.status.in_((
            CohortStatus.COMPLETE.value, CohortStatus.PARTIAL.value,
        ))
    ).order_by(DerivedIntelligenceCohort.id.desc()).limit(100).all()
    for row in rows:
        if (
            target_games.intersection(row.affected_game_ids_json or ())
            or target_teams.intersection(row.affected_team_ids_json or ())
            or target_pitchers.intersection(row.affected_pitcher_ids_json or ())
        ):
            return row
    return None


def _latest_live_cohort(game_ids):
    target = set(game_ids)
    if not target:
        return None
    rows = DerivedIntelligenceCohort.query.filter_by(
        authority_class=AuthorityClass.LIVE.value,
    ).order_by(DerivedIntelligenceCohort.id.desc()).limit(100).all()
    return next(
        (row for row in rows if target.intersection(row.affected_game_ids_json or ())),
        None,
    )


def enqueue_publication_candidate(cohort, plan):
    payload = {
        'cohort_id': cohort.id, 'cohort_fingerprint': cohort.cohort_fingerprint,
        'impact_plan_id': plan.id, 'authority_class': cohort.authority_class,
        'baseball_date': cohort.baseball_date.isoformat(),
        'correlation_id': cohort.correlation_id,
        'affected_game_ids': cohort.affected_game_ids_json,
        'affected_team_ids': cohort.affected_team_ids_json,
        'affected_pitcher_ids': cohort.affected_pitcher_ids_json,
        'completed_domains': cohort.completed_domains_json,
        'withheld_domains': cohort.withheld_domains_json,
        'input_manifest': cohort.input_manifest_json,
        'method_versions': cohort.method_versions_json,
        'predecessor_cohort_id': cohort.predecessor_cohort_id,
        'supersedes_cohort_id': cohort.supersedes_cohort_id,
        'cohort_schema_version': cohort.schema_version,
    }
    return enqueue_job(
        job_type=JobType.PUBLISH_DERIVED_COHORT,
        scope_type=(JobScopeType.GAME if len(cohort.affected_game_ids_json) == 1 else JobScopeType.BASEBALL_DATE),
        scope_key=(str(cohort.affected_game_ids_json[0]) if len(cohort.affected_game_ids_json) == 1 else cohort.baseball_date.isoformat()),
        product_date=cohort.baseball_date,
        dedupe_key=f'PUBLISH_DERIVED_COHORT:{cohort.cohort_fingerprint}',
        priority=PRIORITY_PUBLICATION_CANDIDATE,
        sync_run_id=cohort.sync_run_id,
        payload_schema_version=PUBLICATION_PAYLOAD_VERSION,
        payload=payload,
        commit=False,
    )


def _entry(input_type, key, version, fingerprint, authority, observation_id):
    return {
        'input_type': input_type, 'input_key': str(key),
        'input_version': str(version), 'input_fingerprint': fingerprint,
        'authority_class': authority, 'source_observation_id': observation_id,
    }


def _persist_inputs(cohort, manifest):
    for item in manifest:
        db.session.add(DerivedCohortInput(cohort_id=cohort.id, **item))


def _merge_snapshots(target, result):
    if not isinstance(result, dict):
        return
    for entity_type in ('pitcher', 'team', 'game'):
        for key, payload in (result.get(entity_type) or {}).items():
            target[entity_type].setdefault(str(key), {}).update(payload or {})


def _persist_snapshots(cohort, snapshots):
    for entity_type, values in snapshots.items():
        for entity_key, payload in values.items():
            payload = deepcopy(payload)
            specialized = []
            read_models = payload.get('read_models')
            if isinstance(read_models, dict):
                if entity_type == 'team' and isinstance(read_models.get('team_board_v2'), dict):
                    specialized.append((
                        'team_board_v2_publication',
                        {'read_models': {'team_board_v2': read_models.pop('team_board_v2')}},
                    ))
                if entity_type == 'pitcher' and isinstance(read_models.get('pitcher_current'), dict):
                    specialized.append((
                        'pitcher_current_publication',
                        {'read_models': {'pitcher_current': read_models.pop('pitcher_current')}},
                    ))
            if entity_type == 'team' and isinstance(payload.get('what_changed'), dict):
                specialized.append((
                    'what_changed_publication',
                    {'what_changed': payload.pop('what_changed')},
                ))
            db.session.add(DerivedCohortSnapshot(
                cohort_id=cohort.id, entity_type=entity_type,
                entity_key=str(entity_key), snapshot_type=f'{entity_type}_intelligence',
                baseball_date=cohort.baseball_date, authority_class=cohort.authority_class,
                payload_schema_version=1, payload_json=payload,
            ))
            for snapshot_type, specialized_payload in specialized:
                db.session.add(DerivedCohortSnapshot(
                    cohort_id=cohort.id, entity_type=entity_type,
                    entity_key=str(entity_key), snapshot_type=snapshot_type,
                    baseball_date=cohort.baseball_date,
                    authority_class=cohort.authority_class,
                    payload_schema_version=1, payload_json=specialized_payload,
                ))


def _result_summary(result):
    if isinstance(result, dict) and isinstance(result.get('summary'), dict):
        return result['summary']
    return {'produced': result is not None}


__all__ = [
    'COHORT_SCHEMA_VERSION', 'CohortExecutionResult', 'CohortStatus',
    'DOMAIN_DEPENDENCIES', 'DOMAIN_EXECUTION_ORDER', 'DomainStatus',
    'METHOD_VERSIONS', 'capture_input_manifest', 'cohort_fingerprint',
    'dependency_closure', 'execute_derived_intelligence_job',
    'execute_derived_intelligence_plan', 'method_version_manifest',
    'enqueue_publication_candidate', 'run_derived_intelligence_worker_once',
]
