"""CU-08 bounded, fail-closed continuous execution control plane.

The module composes the accepted CU-02 through CU-07 services without changing
their baseball semantics.  It is deliberately scheduler-independent: one call
performs at most one bounded cycle and then returns.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, timezone
from enum import Enum
import json
import logging
import os
import threading
from time import monotonic

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from models.game_observation_state import GameObservationState
from services import change_impact_orchestration as cu03
from services import continuous_game_work
from services import game_change_detection as cu02
from services import game_finality
from services import incremental_arm_read_team_state as cu05
from services import incremental_publication as cu07
from services import incremental_read_model_rebuild as cu06
from services import incremental_workload_rest as cu04
from services import sync_metadata
from services import sync_control_plane
from services import sync_jobs
from services import team_publication_storage
from services.mlb_api import mlb_client
from utils.db import db
from utils.time import utc_now_naive


class ActivationMode(str, Enum):
    OFF = 'off'
    SHADOW_DETECT = 'shadow_detect'
    SHADOW_FULL_CHAIN = 'shadow_full_chain'
    PROOF_PUBLICATION = 'proof_publication'
    LIMITED_LIVE = 'limited_live'
    FULL_LIVE = 'full_live'


CHAIN_MODES = frozenset({
    ActivationMode.SHADOW_FULL_CHAIN,
    ActivationMode.PROOF_PUBLICATION,
    ActivationMode.LIMITED_LIVE,
    ActivationMode.FULL_LIVE,
})
PRODUCTION_MODES = frozenset({ActivationMode.LIMITED_LIVE, ActivationMode.FULL_LIVE})

JOB_CONTINUOUS_CYCLE = 'continuous_cycle'
SOURCE_CONTINUOUS = 'continuous'
CONTINUOUS_LOCK_KEY = 820_260_803
DEFAULT_SOURCE_BUDGET = 32
DEFAULT_MAX_GAMES = 15
DEFAULT_MAX_CANONICAL_ACTIONS = 4
DEFAULT_MAX_COHORTS = 2
DEFAULT_MAX_RUNTIME_SECONDS = 120
DEFAULT_CORE_FAILURE_BREAKER = 3
CANONICAL_WRITE_SOURCE_REQUESTS = 3
AUTOMATIC_PLAN_SOURCE_REQUESTS = 1
REPLAY_JOB_NAME = 'continuous_game_replay'
REPLAY_JOB_FAMILY = 'continuous_replay'
REPLAY_MAX_ATTEMPTS = 2

RESULT_OFF = 'off'
RESULT_COMPLETE = 'complete'
RESULT_PARTIAL = 'partial'
RESULT_SKIPPED = 'skipped'
RESULT_BLOCKED = 'blocked'

_process_cycle_lock = threading.Lock()
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContinuousExecutionConfig:
    mode: ActivationMode = ActivationMode.OFF
    enabled: bool = False
    production_publication_enabled: bool = False
    allowlist_game_pks: tuple[int, ...] = ()
    allowlist_team_ids: tuple[int, ...] = ()
    expected_plan_fingerprints: dict[int, str] = field(default_factory=dict)
    replay_game_pks: tuple[int, ...] = ()
    correction_days: int = 2
    source_request_budget: int = DEFAULT_SOURCE_BUDGET
    max_games: int = DEFAULT_MAX_GAMES
    max_canonical_actions: int = DEFAULT_MAX_CANONICAL_ACTIONS
    max_publication_cohorts: int = DEFAULT_MAX_COHORTS
    max_runtime_seconds: int = DEFAULT_MAX_RUNTIME_SECONDS
    core_failure_breaker: int = DEFAULT_CORE_FAILURE_BREAKER
    full_live_acknowledged: bool = False

    @classmethod
    def from_environment(cls, environ=None):
        env = os.environ if environ is None else environ
        errors = []
        raw_mode = str(env.get('BASEBALLOS_CONTINUOUS_MODE') or 'off').strip().lower()
        try:
            mode = ActivationMode(raw_mode)
        except ValueError:
            mode = ActivationMode.OFF
            errors.append('invalid_mode')
        fingerprints = {}
        raw_fingerprints = env.get('BASEBALLOS_CONTINUOUS_PLAN_FINGERPRINTS')
        if raw_fingerprints:
            try:
                decoded = json.loads(raw_fingerprints)
                fingerprints = {
                    int(key): str(value) for key, value in decoded.items()
                    if str(value).strip()
                }
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                errors.append('invalid_plan_fingerprints')
        values = cls(
            mode=mode,
            enabled=_bool(env.get('BASEBALLOS_CONTINUOUS_ENABLED'), False),
            production_publication_enabled=_bool(
                env.get('BASEBALLOS_CONTINUOUS_PUBLICATION_ENABLED'), False,
            ),
            allowlist_game_pks=_csv_ints(
                env.get('BASEBALLOS_CONTINUOUS_ALLOWLIST_GAME_PKS'), errors,
                'invalid_game_allowlist',
            ),
            allowlist_team_ids=_csv_ints(
                env.get('BASEBALLOS_CONTINUOUS_ALLOWLIST_TEAM_IDS'), errors,
                'invalid_team_allowlist',
            ),
            expected_plan_fingerprints=fingerprints,
            replay_game_pks=_csv_ints(
                env.get('BASEBALLOS_CONTINUOUS_REPLAY_GAME_PKS'), errors,
                'invalid_replay_game_allowlist',
            ),
            correction_days=_integer(
                env, 'BASEBALLOS_CONTINUOUS_CORRECTION_DAYS', 2, errors, minimum=0,
            ),
            source_request_budget=_integer(
                env, 'BASEBALLOS_CONTINUOUS_SOURCE_BUDGET', DEFAULT_SOURCE_BUDGET,
                errors, minimum=1,
            ),
            max_games=_integer(
                env, 'BASEBALLOS_CONTINUOUS_MAX_GAMES', DEFAULT_MAX_GAMES,
                errors, minimum=0,
            ),
            max_canonical_actions=_integer(
                env, 'BASEBALLOS_CONTINUOUS_MAX_CANONICAL_ACTIONS',
                DEFAULT_MAX_CANONICAL_ACTIONS, errors, minimum=0,
            ),
            max_publication_cohorts=_integer(
                env, 'BASEBALLOS_CONTINUOUS_MAX_COHORTS', DEFAULT_MAX_COHORTS,
                errors, minimum=0,
            ),
            max_runtime_seconds=_integer(
                env, 'BASEBALLOS_CONTINUOUS_MAX_RUNTIME_SECONDS',
                DEFAULT_MAX_RUNTIME_SECONDS, errors, minimum=1,
            ),
            core_failure_breaker=_integer(
                env, 'BASEBALLOS_CONTINUOUS_CORE_FAILURE_BREAKER',
                DEFAULT_CORE_FAILURE_BREAKER, errors, minimum=1,
            ),
            full_live_acknowledged=_bool(
                env.get('BASEBALLOS_CONTINUOUS_FULL_LIVE_ACKNOWLEDGED'), False,
            ),
        )
        errors.extend(values.validation_errors())
        return values, tuple(dict.fromkeys(errors))

    def validation_errors(self):
        errors = []
        if self.mode != ActivationMode.OFF and not self.enabled:
            errors.append('continuous_execution_disabled')
        if self.mode == ActivationMode.LIMITED_LIVE and not (
            self.allowlist_game_pks or self.allowlist_team_ids
        ):
            errors.append('limited_live_allowlist_required')
        if self.mode in PRODUCTION_MODES and not self.production_publication_enabled:
            errors.append('production_publication_disabled')
        if self.mode == ActivationMode.FULL_LIVE and not self.full_live_acknowledged:
            errors.append('full_live_acknowledgement_required')
        return tuple(errors)


@dataclass(frozen=True)
class ContinuousCycleResult:
    mode: str
    status: str
    reason_code: str
    started_at: str
    finished_at: str
    represented_time: str
    sync_run_id: int | None = None
    lock_acquired: bool = False
    public_writer_lock_acquired: bool = False
    games_considered: int = 0
    candidate_game_pks: tuple = ()
    finalization_priority_game_pks: tuple = ()
    finalization_candidates_selected: tuple = ()
    pending_finalization_count: int = 0
    final_observations_accepted: int = 0
    durable_work_created: int = 0
    games_checked: int = 0
    unchanged_games: int = 0
    changed_games: int = 0
    rejected_observations: int = 0
    source_failures: int = 0
    canonical_actions: int = 0
    canonical_mutation_games: int = 0
    affected_pitcher_ids: tuple = ()
    affected_team_ids: tuple = ()
    cu04_pitchers_recomputed: int = 0
    cu04_teams_recomputed: int = 0
    cu05_arm_reads_recomputed: int = 0
    cu05_teams_recomputed: int = 0
    cu06_models_rebuilt: int = 0
    publication_candidates: int = 0
    proof_publications: int = 0
    live_publications: int = 0
    cache_handoffs: int = 0
    skipped_by_mode: int = 0
    skipped_by_allowlist: int = 0
    failures: tuple = ()
    source_requests: int = 0
    source_retries: int = 0
    source_budget_exhausted: bool = False
    circuit_breaker_open: bool = False
    timeout_reached: bool = False
    production_authority_affected: bool = False
    publication_target: str = 'none'
    detection_results: tuple = ()
    downstream_results: tuple = ()
    replay_results: tuple = ()
    work_results: tuple = ()
    work_obligations_pending: int = 0
    work_obligations_claimed: int = 0
    work_obligations_completed: int = 0
    work_obligations_failed: int = 0
    shadow_team_packages_created: int = 0
    shadow_team_packages_reused: int = 0
    shadow_team_packages_equivalent: int = 0
    shadow_team_authoring_failures: int = 0
    shadow_authoring_results: tuple = ()
    runtime_ms: float = 0.0

    def to_dict(self):
        value = asdict(self)
        for key in (
            'affected_pitcher_ids', 'affected_team_ids', 'failures',
            'candidate_game_pks', 'finalization_priority_game_pks',
            'finalization_candidates_selected',
            'detection_results', 'downstream_results',
            'replay_results',
            'work_results',
            'shadow_authoring_results',
        ):
            value[key] = list(value[key])
        return value


class ContinuousCycleLock:
    """Nonblocking, session-scoped cycle lock with a process fallback."""

    def __init__(self):
        self.connection = None
        self.process_acquired = False

    def acquire(self):
        if getattr(db.engine.dialect, 'name', '') == 'postgresql':
            self.connection = db.engine.connect()
            try:
                acquired = self.connection.execute(
                    text('SELECT pg_try_advisory_lock(:key)'),
                    {'key': CONTINUOUS_LOCK_KEY},
                ).scalar()
            except SQLAlchemyError:
                self.connection.close()
                self.connection = None
                raise
            if acquired is not True:
                self.connection.close()
                self.connection = None
                return False
            return True
        self.process_acquired = _process_cycle_lock.acquire(blocking=False)
        return self.process_acquired

    def release(self):
        if self.connection is not None:
            try:
                self.connection.execute(
                    text('SELECT pg_advisory_unlock(:key)'),
                    {'key': CONTINUOUS_LOCK_KEY},
                )
            finally:
                self.connection.close()
                self.connection = None
        if self.process_acquired:
            _process_cycle_lock.release()
            self.process_acquired = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.release()
        return False


def run_continuous_cycle(
    mode=None,
    represented_time=None,
    allowlist=None,
    *,
    config=None,
    client=None,
    detector=None,
    orchestrator=None,
    workload_service=None,
    team_state_service=None,
    read_model_service=None,
    proof_publisher=None,
    production_publisher=None,
    production_current_id_provider=None,
    shadow_team_publisher=None,
    cache_adapter=None,
    source_snapshot=None,
    cycle_lock_factory=None,
):
    """Run one bounded cycle; never schedules, sleeps, or loops."""
    started_clock = monotonic()
    started_at = utc_now_naive()
    represented = _represented_time(represented_time)
    if config is None:
        config, config_errors = ContinuousExecutionConfig.from_environment()
    else:
        config_errors = config.validation_errors()
    if mode is not None:
        try:
            raw_mode = mode.value if isinstance(mode, ActivationMode) else str(mode).lower()
            config = replace(config, mode=ActivationMode(raw_mode))
        except ValueError:
            config_errors = tuple(config_errors) + ('invalid_mode',)
        else:
            config_errors = config.validation_errors()
    if allowlist:
        config = replace(
            config,
            allowlist_game_pks=tuple(sorted(set(
                allowlist.get('game_pks', config.allowlist_game_pks)
            ))),
            allowlist_team_ids=tuple(sorted(set(
                allowlist.get('team_ids', config.allowlist_team_ids)
            ))),
        )
        config_errors = config.validation_errors()

    if config.mode == ActivationMode.OFF or not config.enabled:
        reason = 'mode_off' if config.mode == ActivationMode.OFF else 'kill_switch_disabled'
        return _empty_result(
            config, represented, started_at, started_clock,
            status=RESULT_OFF, reason=reason,
            failures=config_errors,
        )
    if config_errors:
        return _empty_result(
            config, represented, started_at, started_clock,
            status=RESULT_BLOCKED, reason='invalid_fail_closed_configuration',
            failures=config_errors,
        )

    lock = (cycle_lock_factory or ContinuousCycleLock)()
    try:
        acquired = lock.acquire()
    except Exception as exc:  # lock state unknown must fail closed
        return _empty_result(
            config, represented, started_at, started_clock,
            status=RESULT_BLOCKED, reason='cycle_lock_unavailable',
            failures=({'scope': 'cycle_lock', 'error': type(exc).__name__},),
        )
    if not acquired:
        return _empty_result(
            config, represented, started_at, started_clock,
            status=RESULT_SKIPPED, reason='cycle_already_running',
        )

    public_guard = None
    sync_run_id = None
    try:
        if config.mode in CHAIN_MODES:
            try:
                public_guard = sync_metadata.acquire_sync_writer_guard(
                    job_name=JOB_CONTINUOUS_CYCLE,
                    source=SOURCE_CONTINUOUS,
                    lock_scope=sync_metadata.LOCK_SCOPE_PUBLIC,
                )
            except sync_metadata.SyncWriterConflict as exc:
                return _empty_result(
                    config, represented, started_at, started_clock,
                    status=RESULT_SKIPPED, reason=exc.reason,
                    failures=(exc.to_dict(),), lock_acquired=True,
                )
            sync_run_id = sync_metadata.start_sync_run(
                source=SOURCE_CONTINUOUS,
                started_at=started_at,
                job_name=JOB_CONTINUOUS_CYCLE,
                run_type=sync_control_plane.RunType.LIVE_GAME,
                trigger_type=sync_control_plane.TriggerType.SOURCE_CHANGE,
                baseball_date=represented.date(),
                source_domain=sync_control_plane.SourceDomain.LIVE_FEED,
                scopes=sync_control_plane.scope_entries(
                    league=True,
                    source_domains=(sync_control_plane.SourceDomain.LIVE_FEED,),
                ),
            )
        try:
            result = _execute_cycle(
                config=config,
                represented=represented,
                started_at=started_at,
                started_clock=started_clock,
                sync_run_id=sync_run_id,
                public_writer_lock_acquired=public_guard is not None,
                client=client or mlb_client,
                detector=detector or cu02.detect_active_slate_changes,
                orchestrator=orchestrator or cu03.orchestrate_game_change,
                workload_service=workload_service or cu04.recompute_workload_rest_impact,
                team_state_service=team_state_service or cu05.recompute_arm_reads_team_state,
                read_model_service=read_model_service or cu06.rebuild_read_model_impact,
                proof_publisher=proof_publisher or cu07.publish_incremental,
                production_publisher=production_publisher,
                production_current_id_provider=production_current_id_provider,
                shadow_team_publisher=(
                    shadow_team_publisher
                    or team_publication_storage.author_continuous_team_publications_shadow
                ),
                cache_adapter=cache_adapter,
                source_snapshot=source_snapshot,
            )
        except Exception as exc:  # cycle-level acquisition/config failure
            db.session.rollback()
            result = _empty_result(
                config, represented, started_at, started_clock,
                status=RESULT_PARTIAL, reason='cycle_execution_failed',
                failures=({'scope': 'cycle', 'error': type(exc).__name__},),
                lock_acquired=True,
            )
            result = replace(
                result,
                sync_run_id=sync_run_id,
                public_writer_lock_acquired=public_guard is not None,
            )
            run = _finish_run(result)
            if result.sync_run_id is None and run is not None:
                result = replace(result, sync_run_id=run.id)
        return result
    finally:
        if public_guard is not None:
            public_guard.release()
        lock.release()


def _execute_cycle(**kwargs):
    config = kwargs['config']
    client = kwargs['client']
    started_clock = kwargs['started_clock']
    before_metrics = _metrics(client)
    attempts_per_source_request = _max_attempts_per_request(client)
    continuous_game_work.ensure_due_correction_rechecks(
        reference_date=kwargs['represented'].date(),
        correction_days=config.correction_days,
        limit=max(config.max_canonical_actions, 1),
        sync_run_id=kwargs['sync_run_id'],
    )
    preexisting_work, invalid_work = _validated_work(
        continuous_game_work.claimable_obligations(
            limit=config.max_canonical_actions,
        )
    )
    pending_source_reserve = max(
        (
            _canonical_source_reserve(config, continuous_game_work.change_for(job))
            for job in preexisting_work
            if continuous_game_work.stage_for(job)
            == continuous_game_work.STAGE_CANONICAL_PENDING
        ),
        default=0,
    ) * attempts_per_source_request
    detection_budget = config.source_request_budget - pending_source_reserve
    max_feed_games = min(
        config.max_games,
        max(
            0,
            (detection_budget - attempts_per_source_request)
            // attempts_per_source_request,
        ),
    )
    detection_deferred_for_source_budget = (
        detection_budget < attempts_per_source_request
    )
    if not detection_deferred_for_source_budget:
        detection_cycle = kwargs['detector'](
            reference_date=kwargs['represented'].date(),
            correction_days=config.correction_days,
            client=client,
            max_games=max_feed_games,
        )
    else:
        # Durable work has already paid the observation edge. Preserve enough
        # worst-case retry budget for CU-01 instead of spending it on another
        # schedule request that cannot make the obligation more authoritative.
        detection_cycle = {
            'candidate_game_pks': [],
            'games_checked': 0,
            'unchanged_games': 0,
            'changed_games': 0,
            'source_failures': 0,
            'requests_expected': 0,
            'results': [],
        }
    detection_results = list(detection_cycle.get('results') or ())
    observation_jobs = continuous_game_work.ensure_obligations(
        detection_results,
        sync_run_id=kwargs['sync_run_id'],
    )
    replay_changes, replay_results = _prepare_governed_replays(
        config, detection_results, sync_run_id=kwargs['sync_run_id'],
    )
    failures = []
    if detection_deferred_for_source_budget:
        failures.append({
            'scope': 'detection',
            'error': (
                'source_budget_reserved_for_durable_work'
                if pending_source_reserve
                else 'source_budget_insufficient_for_detection'
            ),
        })
    source_failures = int(detection_cycle.get('source_failures') or 0)
    checked = int(detection_cycle.get('games_checked') or 0)
    breaker_open = source_failures >= config.core_failure_breaker
    if checked and (source_failures / checked) >= 0.5:
        breaker_open = True
    if breaker_open:
        failures.append({
            'scope': 'cycle', 'error': 'core_source_circuit_breaker_open',
            'source_failures': source_failures,
        })

    counters = {
        'canonical_actions': 0, 'canonical_mutation_games': 0,
        'cu04_pitchers_recomputed': 0, 'cu04_teams_recomputed': 0,
        'cu05_arm_reads_recomputed': 0, 'cu05_teams_recomputed': 0,
        'cu06_models_rebuilt': 0, 'publication_candidates': 0,
        'proof_publications': 0, 'live_publications': 0,
        'cache_handoffs': 0, 'skipped_by_mode': 0,
        'skipped_by_allowlist': 0,
        'work_obligations_claimed': 0,
        'work_obligations_completed': 0,
        'work_obligations_failed': len(invalid_work),
        'shadow_team_packages_created': 0,
        'shadow_team_packages_reused': 0,
        'shadow_team_packages_equivalent': 0,
        'shadow_team_authoring_failures': 0,
    }
    affected_pitchers = set()
    affected_teams = set()
    downstream = []
    production_publication_queue = []
    work_results = list(invalid_work)
    shadow_authoring_results = []
    failures.extend({
        'scope': 'durable_work',
        'game_pk': (item.get('details_json') or {}).get('game_pk'),
        'error': (
            ((item.get('details_json') or {}).get('invalid_work') or {}).get(
                'reason'
            )
            or 'invalid_work_payload'
        ),
    } for item in invalid_work)
    timeout_reached = False
    publication_target = _publication_target(config.mode)

    work_jobs = []
    if config.mode != ActivationMode.SHADOW_DETECT:
        work_jobs, newly_invalid = _validated_work(
            continuous_game_work.claimable_obligations(
                limit=config.max_canonical_actions,
            )
        )
        counters['work_obligations_failed'] += len(newly_invalid)
        work_results.extend(newly_invalid)
        failures.extend({
            'scope': 'durable_work',
            'game_pk': (item.get('details_json') or {}).get('game_pk'),
            'error': (
                ((item.get('details_json') or {}).get('invalid_work') or {}).get(
                    'reason'
                )
                or 'invalid_work_payload'
            ),
        } for item in newly_invalid)
    durable_identities = {
        str((job.details_json or {}).get('observation_fingerprint') or '')
        for job in observation_jobs
    }
    durable_changes = [
        (continuous_game_work.change_for(job), job)
        for job in work_jobs
    ]
    transient_changes = [
        (change, None)
        for change in detection_results
        if (
            config.mode == ActivationMode.SHADOW_DETECT
            or str(change.get('current_observation_identity') or '')
            not in durable_identities
        )
    ]
    pipeline_changes = [
        *durable_changes,
        *transient_changes,
        *((change, None) for change in replay_changes),
    ]
    action_slots_started = 0

    for change, work_job in pipeline_changes:
        replay_result = change.get('_replay_result')
        if config.mode == ActivationMode.SHADOW_DETECT:
            counters['skipped_by_mode'] += int(bool(change.get('changed')))
            continue
        if not change.get('changed'):
            # CU-02 has already classified unchanged/rejected/failed evidence;
            # no later service can turn it into canonical work safely.
            continue
        preclaim_stage = (
            continuous_game_work.stage_for(work_job)
            if work_job is not None
            else continuous_game_work.STAGE_CANONICAL_PENDING
        )
        if preclaim_stage == continuous_game_work.STAGE_CANONICAL_PENDING:
            current_metrics = _metrics(client)
            observed_source_attempts = max(
                0,
                current_metrics['api_calls'] - before_metrics['api_calls'],
            )
            source_requests_used = (
                observed_source_attempts
                if observed_source_attempts
                else int(detection_cycle.get('requests_expected') or 0)
                * attempts_per_source_request
            )
            source_requests_required = (
                _canonical_source_reserve(config, change)
                * attempts_per_source_request
            )
            if source_requests_used + source_requests_required > (
                config.source_request_budget
            ):
                counters['skipped_by_mode'] += 1
                _rotate_unclaimed_work(work_job, 'source_budget_deferred', work_results)
                continue
            if breaker_open:
                counters['skipped_by_mode'] += int(bool(change.get('changed')))
                _rotate_unclaimed_work(
                    work_job, 'source_circuit_breaker_open', work_results,
                )
                continue
        if monotonic() - started_clock >= config.max_runtime_seconds:
            timeout_reached = True
            break
        if action_slots_started >= config.max_canonical_actions:
            counters['skipped_by_mode'] += int(bool(change.get('changed')))
            continue
        if (
            preclaim_stage == continuous_game_work.STAGE_CANONICAL_PENDING
            and config.mode == ActivationMode.LIMITED_LIVE
            and not _change_is_allowlisted(change, config)
        ):
            counters['skipped_by_allowlist'] += int(bool(change.get('changed')))
            _rotate_unclaimed_work(work_job, 'change_not_allowlisted', work_results)
            continue
        if (
            work_job is not None
            and preclaim_stage in {
                continuous_game_work.STAGE_PUBLICATION_PENDING,
                continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
            }
            and config.mode == ActivationMode.SHADOW_FULL_CHAIN
        ):
            counters['skipped_by_mode'] += 1
            _rotate_unclaimed_work(
                work_job, 'publication_disabled_by_mode', work_results,
            )
            continue
        if (
            work_job is not None
            and preclaim_stage == continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
            and config.mode not in {
                ActivationMode.PROOF_PUBLICATION,
                *PRODUCTION_MODES,
            }
        ):
            counters['skipped_by_mode'] += 1
            _rotate_unclaimed_work(
                work_job, 'cache_handoff_disabled_by_mode', work_results,
            )
            continue
        proof_cache_retry = (
            (work_job.details_json or {}).get('proof_publication_receipt')
            if work_job is not None
            and preclaim_stage == continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
            else None
        )
        cache_retry_unavailable = (
            kwargs['cache_adapter'] is None
            if proof_cache_retry is not None
            else kwargs['production_publisher'] is None
        )
        if (
            work_job is not None
            and preclaim_stage == continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
            and cache_retry_unavailable
        ):
            counters['skipped_by_mode'] += 1
            _rotate_unclaimed_work(
                work_job, 'cache_handoff_unavailable', work_results,
            )
            continue
        if (
            work_job is not None
            and preclaim_stage != continuous_game_work.STAGE_CANONICAL_PENDING
            and config.mode == ActivationMode.LIMITED_LIVE
            and not _cohort_is_allowlisted(
                (work_job.details_json or {}).get('canonical_impact') or {},
                config,
            )
        ):
            counters['skipped_by_allowlist'] += 1
            _rotate_unclaimed_work(work_job, 'cohort_not_allowlisted', work_results)
            continue
        if (
            config.mode == ActivationMode.PROOF_PUBLICATION
            and counters['publication_candidates'] >= config.max_publication_cohorts
        ) or (
            config.mode in PRODUCTION_MODES
            and config.max_publication_cohorts < 1
        ):
            counters['skipped_by_mode'] += int(bool(change.get('changed')))
            _rotate_unclaimed_work(work_job, 'publication_cohort_limit', work_results)
            continue

        fingerprint = None
        if preclaim_stage == continuous_game_work.STAGE_CANONICAL_PENDING:
            fingerprint = config.expected_plan_fingerprints.get(
                int(change.get('game_pk') or 0)
            )
            if not fingerprint and config.mode in PRODUCTION_MODES:
                try:
                    if work_job is not None:
                        cu03.persist_accepted_final_schedule_authority(change)
                    fingerprint = cu03.derive_current_plan_fingerprint(
                        change,
                        source_client=client,
                    )
                except Exception as exc:
                    failures.append({
                        'scope': 'plan_authorization',
                        'game_pk': change.get('game_pk'),
                        'error': type(exc).__name__,
                        'work_job_id': getattr(work_job, 'id', None),
                        'stage': preclaim_stage,
                        'reason': 'plan_fingerprint_derivation_failed',
                    })
                    _rotate_unclaimed_work(
                        work_job,
                        'plan_fingerprint_derivation_failed',
                        work_results,
                    )
                    continue
            if work_job is not None and not fingerprint:
                failures.append({
                    'scope': 'plan_authorization',
                    'game_pk': change.get('game_pk'),
                    'error': 'reviewed_plan_fingerprint_unavailable',
                })
                _rotate_unclaimed_work(
                    work_job,
                    'reviewed_plan_fingerprint_unavailable',
                    work_results,
                )
                continue
        if work_job is not None:
            work_job = continuous_game_work.claim(
                work_job,
                sync_run_id=kwargs['sync_run_id'],
                exclusive_cycle_lock_held=True,
            )
            if work_job is None:
                continue
            counters['work_obligations_claimed'] += 1
        action_slots_started += 1

        work_stage = preclaim_stage
        canonical_ran = work_stage == continuous_game_work.STAGE_CANONICAL_PENDING
        stage_started = monotonic()
        if canonical_ran:
            orchestrator_kwargs = {
                'allow_canonical_write': True,
                'expected_plan_fingerprint': fingerprint,
            }
            if replay_result is None:
                orchestrator_kwargs['source_client'] = client
            if work_job is not None:
                orchestrator_kwargs['canonical_completion_callback'] = (
                    _canonical_completion_callback(work_job)
                )
            try:
                impact = kwargs['orchestrator'](change, **orchestrator_kwargs)
            except Exception as exc:  # one game must not poison independent cohorts
                if replay_result is not None:
                    _fail_replay(replay_result, exc)
                if work_job is not None:
                    _record_work_failure(
                        work_job, exc,
                        stage=continuous_game_work.STAGE_CANONICAL_PENDING,
                        counters=counters, results=work_results,
                    )
                failures.append({
                    'scope': 'orchestration', 'game_pk': change.get('game_pk'),
                    'error': type(exc).__name__,
                })
                continue
            impact_dict = _dict(impact)
            if replay_result is not None:
                _settle_replay(replay_result, impact_dict)
            counters['canonical_actions'] += int(
                impact_dict.get('cu01_invocations') or 0
            )
        else:
            impact_dict = dict(
                (work_job.details_json or {}).get('canonical_impact') or {}
            )
            impact = impact_dict
            if not impact_dict:
                error = 'durable_canonical_impact_missing'
                failures.append({
                    'scope': 'canonical_checkpoint',
                    'game_pk': change.get('game_pk'),
                    'error': error,
                })
                _record_work_failure(
                    work_job, error,
                    stage=continuous_game_work.STAGE_CANONICAL_PENDING,
                    counters=counters, results=work_results,
                )
                continue

        game_result = {
            'game_pk': change.get('game_pk'), 'cu03': impact_dict,
            'latency': {
                'canonical_stage_ms': _elapsed_ms(stage_started),
                'canonical_stage_completed_at': utc_now_naive().isoformat(),
            },
        }
        if work_stage == continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING:
            if proof_cache_retry is not None:
                receipt = proof_cache_retry
                try:
                    keys = cu07.retry_cache_handoff(
                        receipt.get('publication_id'),
                        kwargs['cache_adapter'],
                        expected_candidate_id=receipt.get('candidate_id'),
                        expected_payload_version=receipt.get('payload_version'),
                    )
                except Exception as exc:
                    failures.append({
                        'scope': 'proof_publication_cache',
                        'game_pk': change.get('game_pk'),
                        'error': type(exc).__name__,
                    })
                    _record_work_failure(
                        work_job,
                        exc,
                        stage=continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
                        counters=counters,
                        results=work_results,
                    )
                else:
                    counters['cache_handoffs'] += 1
                    completed = continuous_game_work.complete(
                        work_job,
                        outcome='proof_publication_cache_handoff_complete',
                        publication={
                            'new_publication_id': receipt['publication_id'],
                            'candidate_id': receipt['candidate_id'],
                            'committed': True,
                            'cache_handoff_status': 'complete',
                            'cache_keys': list(keys),
                        },
                    )
                    counters['work_obligations_completed'] += 1
                    work_results.append(completed.to_dict())
                downstream.append(game_result)
                continue
            publication_sync_run_id = _positive_int(
                (work_job.details_json or {}).get(
                    'publication_attempt_sync_run_id'
                )
            )
            if publication_sync_run_id is None:
                error = 'publication_receipt_identity_missing'
                failures.append({
                    'scope': 'tonight_refresh',
                    'game_pk': change.get('game_pk'),
                    'error': error,
                })
                _record_work_failure(
                    work_job,
                    error,
                    stage=continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
                    counters=counters,
                    results=work_results,
                )
                downstream.append(game_result)
                continue
            try:
                publication = _publish(
                    kwargs['production_publisher'], {}, change, kwargs,
                    game_result, counters, proof=False,
                    sync_run_id=publication_sync_run_id,
                    require_published_receipt=True,
                )
                if not _publication_satisfied(publication):
                    raise RuntimeError(
                        publication.get('reason_code')
                        or 'publication_cache_handoff_incomplete'
                    )
            except Exception as exc:
                failures.append({
                    'scope': 'tonight_refresh',
                    'game_pk': change.get('game_pk'),
                    'error': type(exc).__name__,
                })
                _record_work_failure(
                    work_job,
                    exc,
                    stage=continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
                    counters=counters,
                    results=work_results,
                )
            else:
                completed = continuous_game_work.complete(
                    work_job,
                    outcome='production_cache_handoff_complete',
                    publication=publication,
                )
                counters['work_obligations_completed'] += 1
                work_results.append(completed.to_dict())
            downstream.append(game_result)
            continue
        if impact_dict.get('orchestration_status') == cu03.STATUS_CANONICAL_FAILED:
            error = impact_dict.get('source_failure_state') or 'canonical_failed'
            failures.append({
                'scope': 'canonical', 'game_pk': change.get('game_pk'),
                'error': error,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, error,
                    stage=continuous_game_work.STAGE_CANONICAL_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        if (
            canonical_ran
            and impact_dict.get('canonical_action_attempted') is not True
            and int(impact_dict.get('cu01_invocations') or 0) == 0
        ):
            if work_job is not None:
                deferred = continuous_game_work.defer(
                    work_job,
                    reason=(
                        impact_dict.get('reason_code')
                        or 'canonical_action_not_attempted'
                    ),
                    stage=continuous_game_work.STAGE_CANONICAL_PENDING,
                )
                work_results.append(deferred.to_dict())
            downstream.append(game_result)
            continue
        if work_job is not None and canonical_ran:
            work_job = db.session.get(sync_jobs.SyncJob, work_job.id)
            if continuous_game_work.stage_for(work_job) == (
                continuous_game_work.STAGE_CANONICAL_PENDING
            ):
                error = 'canonical_checkpoint_missing'
                failures.append({
                    'scope': 'canonical_checkpoint',
                    'game_pk': change.get('game_pk'),
                    'error': error,
                })
                _record_work_failure(
                    work_job,
                    error,
                    stage=continuous_game_work.STAGE_CANONICAL_PENDING,
                    counters=counters,
                    results=work_results,
                )
                downstream.append(game_result)
                continue
            checkpointed_impact = (
                (work_job.details_json or {}).get('canonical_impact') or {}
            )
            if checkpointed_impact.get('canonical_source_revision'):
                impact_dict['canonical_source_revision'] = (
                    checkpointed_impact['canonical_source_revision']
                )
                game_result['cu03'] = impact_dict
        if not impact_dict.get('canonical_mutation_performed'):
            if work_job is not None:
                completed = continuous_game_work.complete(
                    work_job,
                    outcome='canonical_no_op',
                    canonical_impact=impact_dict,
                )
                counters['work_obligations_completed'] += 1
                work_results.append(completed.to_dict())
            downstream.append(game_result)
            continue

        counters['canonical_mutation_games'] += int(canonical_ran)
        affected_pitchers.update(impact_dict.get('affected_pitcher_ids') or ())
        affected_teams.update(impact_dict.get('affected_team_ids') or ())
        if not (
            impact_dict.get('affected_pitcher_ids')
            or impact_dict.get('affected_team_ids')
        ):
            if work_job is not None:
                completed = continuous_game_work.complete(
                    work_job,
                    outcome='canonical_mutation_without_public_impact',
                    canonical_impact=impact_dict,
                )
                counters['work_obligations_completed'] += 1
                work_results.append(completed.to_dict())
            downstream.append(game_result)
            continue
        data_through = (
            work_job.product_date
            if work_job is not None
            else _game_data_through(change.get('game_pk'))
        )
        if data_through is None:
            failures.append({
                'scope': 'represented_date', 'game_pk': change.get('game_pk'),
                'error': 'official_date_missing',
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, 'official_date_missing',
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        try:
            stage_started = monotonic()
            workload = kwargs['workload_service'](impact, data_through=data_through)
        except Exception as exc:
            failures.append({
                'scope': 'cu04', 'game_pk': change.get('game_pk'),
                'error': type(exc).__name__,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, exc,
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        workload_dict = _dict(workload)
        game_result['cu04'] = workload_dict
        game_result['latency']['cu04_stage_ms'] = _elapsed_ms(stage_started)
        counters['cu04_pitchers_recomputed'] += len(
            workload_dict.get('pitchers_recomputed') or ()
        )
        counters['cu04_teams_recomputed'] += len(workload_dict.get('teams_recomputed') or ())
        if work_job is not None and not _trusted_stage_result(workload_dict):
            error = workload_dict.get('reason_code') or 'cu04_incomplete'
            failures.append({
                'scope': 'cu04', 'game_pk': change.get('game_pk'),
                'error': error,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, error,
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        try:
            stage_started = monotonic()
            state = kwargs['team_state_service'](
                workload, source_snapshot=kwargs['source_snapshot'],
            )
        except Exception as exc:
            failures.append({
                'scope': 'cu05', 'game_pk': change.get('game_pk'),
                'error': type(exc).__name__,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, exc,
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        state_dict = _dict(state)
        game_result['cu05'] = state_dict
        game_result['latency']['cu05_stage_ms'] = _elapsed_ms(stage_started)
        counters['cu05_arm_reads_recomputed'] += len(
            state_dict.get('arm_reads_recomputed') or ()
        )
        counters['cu05_teams_recomputed'] += len(state_dict.get('teams_recomputed') or ())
        if work_job is not None and not _trusted_stage_result(state_dict):
            error = state_dict.get('reason_code') or 'cu05_incomplete'
            failures.append({
                'scope': 'cu05', 'game_pk': change.get('game_pk'),
                'error': error,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, error,
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        try:
            stage_started = monotonic()
            read_models = kwargs['read_model_service'](
                state, source_snapshot=kwargs['source_snapshot'],
            )
        except Exception as exc:
            failures.append({
                'scope': 'cu06', 'game_pk': change.get('game_pk'),
                'error': type(exc).__name__,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, exc,
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue
        read_dict = _dict(read_models)
        game_result['cu06'] = read_dict
        game_result['latency'].update({
            'cu06_stage_ms': _elapsed_ms(stage_started),
            'derived_stages_completed_at': utc_now_naive().isoformat(),
        })
        counters['cu06_models_rebuilt'] += sum(len(read_dict.get(key) or ()) for key in (
            'team_boards_rebuilt', 'league_rows_rebuilt', 'matchups_rebuilt',
            'tonight_entries_rebuilt', 'pitcher_models_rebuilt',
        ))
        if (
            work_job is not None
            and not _trusted_stage_result(read_dict, require_rebuild=True)
        ):
            error = read_dict.get('reason_code') or 'cu06_incomplete'
            failures.append({
                'scope': 'cu06', 'game_pk': change.get('game_pk'),
                'error': error,
            })
            if work_job is not None:
                _record_work_failure(
                    work_job, error,
                    stage=continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                    counters=counters, results=work_results,
                )
            downstream.append(game_result)
            continue

        if config.mode in PRODUCTION_MODES and work_job is not None:
            try:
                shadow_result = kwargs['shadow_team_publisher'](
                    change=change,
                    canonical_impact=impact_dict,
                    workload_result=workload_dict,
                    team_state_result=state_dict,
                    read_model_result=read_dict,
                    source_sync_run_id=kwargs['sync_run_id'],
                    work_job_id=work_job.id,
                )
                shadow_result = _dict(shadow_result)
            except Exception as exc:
                db.session.rollback()
                shadow_result = {
                    'event': 'team_publication_shadow',
                    'status': 'failed',
                    'game_pk': change.get('game_pk'),
                    'affected_team_ids': list(
                        impact_dict.get('affected_team_ids') or ()
                    ),
                    'reason': str(exc) or type(exc).__name__,
                    'error_type': type(exc).__name__,
                    'packages_created': 0,
                    'packages_reused': 0,
                    'equivalent': 0,
                    'validation_failures': 1,
                    'equivalence_failures': int(
                        'equivalence' in str(exc).lower()
                    ),
                    'pointers_advanced': 0,
                }
                counters['shadow_team_authoring_failures'] += 1
                logger.warning(json.dumps(shadow_result, sort_keys=True))
            else:
                counters['shadow_team_packages_created'] += int(
                    shadow_result.get('packages_created') or 0
                )
                counters['shadow_team_packages_reused'] += int(
                    shadow_result.get('packages_reused') or 0
                )
                counters['shadow_team_packages_equivalent'] += int(
                    shadow_result.get('equivalent') or 0
                )
                logger.info(json.dumps(shadow_result, sort_keys=True))
            shadow_authoring_results.append(shadow_result)
            game_result['team_publication_shadow'] = shadow_result
            work_job = db.session.get(sync_jobs.SyncJob, work_job.id)
            work_job = continuous_game_work.checkpoint(
                work_job,
                continuous_game_work.STAGE_DOWNSTREAM_PENDING,
                canonical_impact=impact_dict,
                team_publication_shadow=shadow_result,
            )

        if config.mode == ActivationMode.PROOF_PUBLICATION:
            proof_cache_required = (
                kwargs['cache_adapter'] is not None
                or (
                    work_job is not None
                    and (work_job.details_json or {}).get('proof_cache_required')
                    is True
                )
            )
            if work_job is not None:
                work_job = continuous_game_work.checkpoint(
                    work_job,
                    continuous_game_work.STAGE_PUBLICATION_PENDING,
                    canonical_impact=impact_dict,
                    proof_cache_required=proof_cache_required,
                )
            if proof_cache_required and kwargs['cache_adapter'] is None:
                deferred = continuous_game_work.defer(
                    work_job,
                    reason='cache_handoff_unavailable',
                    stage=continuous_game_work.STAGE_PUBLICATION_PENDING,
                    canonical_impact=impact_dict,
                )
                work_results.append(deferred.to_dict())
                downstream.append(game_result)
                continue
            try:
                publication = _publish(
                    kwargs['proof_publisher'], read_models, change, kwargs,
                    game_result, counters, proof=True,
                )
                if not _publication_authority_satisfied(publication):
                    raise RuntimeError(
                        publication.get('reason_code') or 'publication_not_committed'
                    )
                if (
                    work_job is not None
                    and publication.get('reason_code') == 'semantic_no_change'
                    and proof_cache_required
                ):
                    receipt = cu07.recover_committed_publication_receipt(
                        publication.get('candidate_id'),
                        expected_publication_id=publication.get(
                            'previous_publication_id'
                        ),
                        expected_team_ids=publication.get('affected_team_ids') or (),
                        expected_game_ids=publication.get('affected_game_ids') or (),
                    )
                    if receipt is None:
                        raise RuntimeError(
                            'proof_publication_receipt_not_recoverable'
                        )
                    work_job = continuous_game_work.checkpoint(
                        work_job,
                        continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
                        canonical_impact=impact_dict,
                        proof_publication_receipt=receipt,
                        publication=publication,
                    )
                    keys = cu07.retry_cache_handoff(
                        receipt['publication_id'],
                        kwargs['cache_adapter'],
                        expected_candidate_id=receipt['candidate_id'],
                        expected_payload_version=receipt['payload_version'],
                    )
                    publication = {
                        **publication,
                        'new_publication_id': receipt['publication_id'],
                        'committed': True,
                        'cache_handoff_status': 'complete',
                        'cache_keys': list(keys),
                    }
                    game_result['publication'] = publication
                    counters['cache_handoffs'] += 1
                if publication.get('cache_handoff_status') == 'retry_required':
                    if work_job is None:
                        raise RuntimeError('proof_cache_receipt_requires_durable_work')
                    receipt = _proof_publication_receipt(publication)
                    work_job = continuous_game_work.checkpoint(
                        work_job,
                        continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
                        canonical_impact=impact_dict,
                        proof_publication_receipt=receipt,
                        publication=publication,
                    )
                    raise RuntimeError('proof_publication_cache_retry_required')
            except Exception as exc:
                failures.append({
                    'scope': 'proof_publication', 'game_pk': change.get('game_pk'),
                    'error': type(exc).__name__,
                })
                if work_job is not None:
                    _record_work_failure(
                        work_job, exc,
                        stage=(
                            continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
                            if continuous_game_work.stage_for(work_job)
                            == continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
                            else continuous_game_work.STAGE_PUBLICATION_PENDING
                        ),
                        counters=counters, results=work_results,
                    )
            else:
                if work_job is not None:
                    completed = continuous_game_work.complete(
                        work_job,
                        outcome='proof_publication_complete',
                        canonical_impact=impact_dict,
                        publication=publication,
                    )
                    counters['work_obligations_completed'] += 1
                    work_results.append(completed.to_dict())
        elif config.mode in PRODUCTION_MODES:
            if not _cohort_is_allowlisted(impact_dict, config):
                counters['skipped_by_allowlist'] += 1
                game_result['publication'] = {
                    'status': 'skipped', 'reason_code': 'cohort_not_allowlisted',
                }
                if work_job is not None:
                    deferred = continuous_game_work.defer(
                        work_job,
                        reason='cohort_not_allowlisted',
                        stage=continuous_game_work.STAGE_PUBLICATION_PENDING,
                        canonical_impact=impact_dict,
                    )
                    work_results.append(deferred.to_dict())
            else:
                if work_job is not None:
                    work_job = continuous_game_work.checkpoint(
                        work_job,
                        continuous_game_work.STAGE_PUBLICATION_PENDING,
                        canonical_impact=impact_dict,
                        publication_attempt_sync_run_id=(
                            (work_job.details_json or {}).get(
                                'publication_attempt_sync_run_id'
                            )
                            or kwargs['sync_run_id']
                        ),
                    )
                production_publication_queue.append(
                    (read_models, change, game_result, work_job)
                )
                game_result['publication'] = {
                    'status': 'queued',
                    'reason_code': 'cycle_publication_pending',
                }
        else:
            if work_job is not None:
                completed = continuous_game_work.complete(
                    work_job,
                    outcome='bounded_downstream_complete',
                    canonical_impact=impact_dict,
                )
                counters['work_obligations_completed'] += 1
                work_results.append(completed.to_dict())
        if 'publication' in game_result:
            game_result['latency']['publication_stage_completed_at'] = (
                utc_now_naive().isoformat()
            )
        downstream.append(game_result)

    if production_publication_queue:
        read_models, change, game_result, publication_work_job = (
            production_publication_queue[-1]
        )
        blocking_scopes = {'represented_date', 'cu04', 'cu05', 'cu06'}
        blocked = any(item.get('scope') in blocking_scopes for item in failures)
        cycle_publication_committed = False
        publication = None
        publication_attempted = False
        publication_deferral_reason = None
        if config.max_publication_cohorts < 1:
            failures.append({
                'scope': 'publication',
                'error': 'production_publication_disabled_by_cohort_limit',
            })
            game_result['publication'] = {
                'status': 'skipped',
                'reason_code': 'max_publication_cohorts_reached',
            }
            publication_deferral_reason = 'max_publication_cohorts_reached'
        elif blocked:
            failures.append({
                'scope': 'publication',
                'error': 'downstream_recomputation_incomplete',
            })
            game_result['publication'] = {
                'status': 'blocked',
                'reason_code': 'downstream_recomputation_incomplete',
            }
            publication_deferral_reason = 'downstream_recomputation_incomplete'
        elif kwargs['production_publisher'] is None:
            failures.append({
                'scope': 'publication',
                'error': 'production_publisher_unavailable',
            })
            game_result['publication'] = {
                'status': 'blocked',
                'reason_code': 'production_publisher_unavailable',
            }
            publication_deferral_reason = 'production_publisher_unavailable'
        else:
            try:
                publication_attempted = True
                publication_sync_run_id = _publication_batch_sync_run_id(
                    production_publication_queue,
                    current_sync_run_id=kwargs['sync_run_id'],
                )
                for queued_job in (
                    queued_job
                    for _models, _queued_change, _queued_result, queued_job
                    in production_publication_queue
                    if queued_job is not None
                ):
                    if (
                        (queued_job.details_json or {}).get(
                            'publication_attempt_sync_run_id'
                        )
                        != publication_sync_run_id
                    ):
                        continuous_game_work.checkpoint(
                            queued_job,
                            continuous_game_work.STAGE_PUBLICATION_PENDING,
                            publication_attempt_sync_run_id=publication_sync_run_id,
                        )
                publication = _publish(
                    kwargs['production_publisher'], read_models, change, kwargs,
                    game_result, counters, proof=False,
                    sync_run_id=publication_sync_run_id,
                )
                authority_committed = _publication_authority_satisfied(publication)
                cycle_publication_committed = (
                    authority_committed
                    and publication.get('cache_handoff_status') != 'retry_required'
                )
                if not authority_committed:
                    failures.append({
                        'scope': 'live_publication',
                        'game_pk': change.get('game_pk'),
                        'error': (
                            publication.get('reason_code')
                            or 'publication_not_committed'
                        ),
                    })
                elif not cycle_publication_committed:
                    failures.append({
                        'scope': 'tonight_refresh',
                        'game_pk': change.get('game_pk'),
                        'error': 'tonight_refresh_retry_required',
                    })
            except Exception as exc:
                failures.append({
                    'scope': 'live_publication', 'game_pk': change.get('game_pk'),
                    'error': type(exc).__name__,
                })
        queued_jobs = [
            queued_job
            for _models, _queued_change, _queued_result, queued_job
            in production_publication_queue
            if queued_job is not None
        ]
        if cycle_publication_committed:
            for queued_job in queued_jobs:
                completed = continuous_game_work.complete(
                    queued_job,
                    outcome='production_publication_complete',
                    publication=publication,
                )
                counters['work_obligations_completed'] += 1
                work_results.append(completed.to_dict())
        elif publication_attempted:
            error = (
                (publication or {}).get('reason_code')
                if isinstance(publication, dict)
                else None
            ) or 'production_publication_failed'
            for queued_job in queued_jobs:
                authority_committed = _publication_authority_satisfied(
                    publication or {}
                )
                if authority_committed:
                    queued_job = continuous_game_work.checkpoint(
                        queued_job,
                        continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING,
                        publication=publication,
                    )
                _record_work_failure(
                    queued_job, error,
                    stage=(
                        continuous_game_work.STAGE_PUBLICATION_CACHE_PENDING
                        if authority_committed
                        else continuous_game_work.STAGE_PUBLICATION_PENDING
                    ),
                    counters=counters, results=work_results,
                )
        else:
            for queued_job in queued_jobs:
                deferred = continuous_game_work.defer(
                    queued_job,
                    reason=publication_deferral_reason or 'publication_deferred',
                    stage=continuous_game_work.STAGE_PUBLICATION_PENDING,
                )
                work_results.append(deferred.to_dict())
        for (
            _models, _queued_change, queued_result, _queued_job
        ) in production_publication_queue[:-1]:
            if cycle_publication_committed:
                queued_result['publication'] = {
                    'status': 'included',
                    'reason_code': 'included_in_cycle_publication',
                    'published_with_game_pk': change.get('game_pk'),
                }
            else:
                queued_result['publication'] = dict(game_result['publication'])

    after_metrics = _metrics(client)
    source_requests = max(
        int(detection_cycle.get('requests_expected') or 0),
        after_metrics['api_calls'] - before_metrics['api_calls'],
    )
    source_retries = max(0, after_metrics['retries'] - before_metrics['retries'])
    source_budget_exhausted = (
        detection_deferred_for_source_budget
        or source_requests >= config.source_request_budget
    )
    status = RESULT_PARTIAL if failures or timeout_reached else RESULT_COMPLETE
    reason = (
        'cycle_completed_with_failures' if failures
        else 'cycle_runtime_limit_reached' if timeout_reached
        else 'cycle_complete'
    )
    result = ContinuousCycleResult(
        mode=config.mode.value, status=status, reason_code=reason,
        started_at=kwargs['started_at'].isoformat(),
        finished_at=utc_now_naive().isoformat(),
        represented_time=kwargs['represented'].isoformat(),
        sync_run_id=kwargs['sync_run_id'], lock_acquired=True,
        public_writer_lock_acquired=kwargs['public_writer_lock_acquired'],
        games_considered=len(detection_cycle.get('candidate_game_pks') or ()),
        candidate_game_pks=tuple(detection_cycle.get('candidate_game_pks') or ()),
        finalization_priority_game_pks=tuple(
            detection_cycle.get('finalization_priority_game_pks') or ()
        ),
        finalization_candidates_selected=tuple(
            detection_cycle.get('finalization_candidates_selected') or ()
        ),
        pending_finalization_count=int(
            detection_cycle.get('pending_finalization_count') or 0
        ),
        final_observations_accepted=sum(
            bool(item.get('accepted'))
            and item.get('finality_state') in {
                game_finality.FINAL_PENDING_DATA,
                game_finality.FINAL_AND_USABLE,
            }
            for item in detection_results
        ),
        durable_work_created=len(observation_jobs),
        games_checked=checked,
        unchanged_games=int(detection_cycle.get('unchanged_games') or 0),
        changed_games=int(detection_cycle.get('changed_games') or 0),
        rejected_observations=sum(
            item.get('classification') in {
                cu02.STALE_OBSERVATION, cu02.AMBIGUOUS_OBSERVATION,
            } for item in detection_results
        ),
        source_failures=source_failures,
        affected_pitcher_ids=tuple(sorted(affected_pitchers)),
        affected_team_ids=tuple(sorted(affected_teams)),
        failures=tuple(failures), source_requests=source_requests,
        source_retries=source_retries,
        source_budget_exhausted=source_budget_exhausted,
        circuit_breaker_open=breaker_open, timeout_reached=timeout_reached,
        production_authority_affected=counters['live_publications'] > 0,
        publication_target=publication_target,
        detection_results=tuple(detection_results),
        downstream_results=tuple(downstream),
        replay_results=tuple(replay_results),
        work_results=tuple(work_results),
        shadow_authoring_results=tuple(shadow_authoring_results),
        work_obligations_pending=continuous_game_work.unresolved_count(),
        runtime_ms=round((monotonic() - started_clock) * 1000, 3),
        **counters,
    )
    run = _finish_run(result)
    if result.sync_run_id is None and run is not None:
        result = replace(result, sync_run_id=run.id)
    return result


def _publish(
    publisher,
    read_models,
    change,
    kwargs,
    game_result,
    counters,
    *,
    proof,
    sync_run_id=None,
    require_published_receipt=False,
):
    counters['publication_candidates'] += 1
    expected_current_id = None
    if proof:
        current = cu07.get_current_publication()
        expected_current_id = current.id if current is not None else None
    elif kwargs['production_current_id_provider'] is not None:
        expected_current_id = kwargs['production_current_id_provider']()
    correction_recheck = (
        change.get('reason') == continuous_game_work.CORRECTION_RECHECK_REASON
    )
    canonical_impact = game_result.get('cu03') or {}
    publisher_kwargs = {
        'source_identity': (
            canonical_impact.get('canonical_source_revision')
            if correction_recheck else change.get('current_observation_identity')
        ),
        'source_order': _source_order(
            change.get('detected_at')
            if correction_recheck else change.get('source_observed_at')
        ),
        'sync_run_id': (
            kwargs['sync_run_id'] if sync_run_id is None else sync_run_id
        ),
        'expected_current_id': expected_current_id,
        'cache_adapter': kwargs['cache_adapter'],
    }
    if require_published_receipt:
        publisher_kwargs['require_published_receipt'] = True
    result = publisher(read_models, **publisher_kwargs)
    value = _dict(result)
    game_result['publication'] = value
    if value.get('committed'):
        counters['proof_publications' if proof else 'live_publications'] += 1
    if value.get('cache_handoff_status') == 'complete':
        counters['cache_handoffs'] += 1
    return value


def _canonical_completion_callback(work_job):
    """Checkpoint CU-01 impact in the same transaction as canonical rows."""
    def checkpoint(outcome):
        impact = _canonical_impact_from_game_outcome(outcome)
        stage = (
            continuous_game_work.STAGE_DOWNSTREAM_PENDING
            if impact['canonical_mutation_performed']
            else continuous_game_work.STAGE_COMPLETE
        )
        continuous_game_work.checkpoint(
            work_job,
            stage,
            commit=False,
            canonical_impact=impact,
        )

    return checkpoint


def _canonical_impact_from_game_outcome(outcome):
    optional = (outcome.get('optional_source_domains') or {}).get(
        'final_play_by_play'
    ) or {}
    pitch_rows = optional.get('pitch_rows') or {}
    impact = outcome.get('impact') or {}
    mutation_count = sum(int(outcome.get(field) or 0) for field in (
        'inserted', 'updated', 'pitcher_identity_mutations',
    )) + sum(int(pitch_rows.get(field) or 0) for field in (
        'inserted', 'updated', 'superseded',
    ))
    return {
        'game_pk': outcome.get('game_pk'),
        'represented_date': outcome.get('represented_date'),
        'detection_classification': 'durable_observation_work',
        'decision': cu03.INSPECT_POST_FINAL_CORRECTION,
        'orchestration_status': cu03.STATUS_RECONCILED,
        'reason_code': 'cu01_canonical_reconciliation_complete',
        'canonical_action_attempted': True,
        'canonical_ingestion_mode': 'cu01_write_non_authoritative',
        'cu01_invocations': 1,
        'game_log_inserted': int(outcome.get('inserted') or 0),
        'game_log_updated': int(outcome.get('updated') or 0),
        'pitch_inserted': int(pitch_rows.get('inserted') or 0),
        'pitch_updated': int(pitch_rows.get('updated') or 0),
        'pitch_superseded': int(pitch_rows.get('superseded') or 0),
        'canonical_mutation_performed': mutation_count > 0,
        'canonical_source_revision': outcome.get('source_revision'),
        'affected_pitcher_mlb_ids': list(
            impact.get('affected_pitcher_mlb_ids') or ()
        ),
        'affected_pitcher_ids': list(impact.get('affected_pitcher_ids') or ()),
        'affected_team_ids': list(impact.get('affected_team_ids') or ()),
        'optional_pbp_status': optional.get('processing_status') or 'not_requested',
        'publication_affected': False,
        'downstream_recomputation_triggered': False,
    }


def _trusted_stage_result(value, *, require_rebuild=False):
    performed = (
        value.get('rebuild_performed')
        if require_rebuild
        else value.get('recomputation_performed')
    )
    return (
        value.get('status') == 'complete'
        and value.get('parity_status') == 'match'
        and performed is True
        and not value.get('failures')
        and not value.get('parity_mismatches')
    )


def _publication_authority_satisfied(value):
    return bool(value.get('committed')) or value.get('reason_code') in {
        'semantic_no_change',
        'production_snapshot_already_committed',
    }


def _publication_satisfied(value):
    return (
        _publication_authority_satisfied(value)
        and value.get('cache_handoff_status') != 'retry_required'
    )


def _proof_publication_receipt(publication):
    publication_id = _positive_int(publication.get('new_publication_id'))
    candidate_id = publication.get('candidate_id')
    if (
        publication_id is None
        or not isinstance(candidate_id, str)
        or not candidate_id.strip()
    ):
        raise RuntimeError('proof_publication_receipt_invalid')
    return {
        'publication_id': publication_id,
        'candidate_id': candidate_id,
        'snapshot_type': cu07.PROOF_SNAPSHOT_TYPE,
        'payload_version': 1,
    }


def _validated_work(jobs):
    valid = []
    invalid = []
    for job in jobs:
        issue = continuous_game_work.validate_obligation(job)
        if issue is None:
            valid.append(job)
            continue
        quarantined = continuous_game_work.quarantine_invalid(job, issue)
        invalid.append(quarantined.to_dict())
    return valid, invalid


def _publication_batch_sync_run_id(queue, *, current_sync_run_id):
    """Return a receipt identity that proves the entire queued cohort.

    A single failed cohort may reuse its first publication attempt so a durable
    Dashboard receipt can resume only the cache handoff.  Mixed cohorts cannot
    reuse one member's receipt: they receive the current cycle identity before
    publication, proving that every queued game was included together.
    """
    attempt_ids = set()
    for _models, _change, _result, job in queue:
        if job is None:
            return current_sync_run_id
        attempt_id = (job.details_json or {}).get('publication_attempt_sync_run_id')
        if attempt_id is None:
            return current_sync_run_id
        attempt_ids.add(attempt_id)
    if len(attempt_ids) == 1:
        return next(iter(attempt_ids))
    return current_sync_run_id


def _canonical_source_reserve(config, change):
    """Reserve the known endpoint reads before starting one canonical action.

    A reviewed CU-01 write rechecks its boxscore plan, refetches the boxscore
    it applies, and attempts final play-by-play. Production auto-authorization
    adds one shadow boxscore read to derive that reviewed plan identity. MLB
    client's endpoint-level retries remain separately bounded and reported.
    """
    if config.mode not in CHAIN_MODES:
        return 0
    game_pk = int(
        (
            change.get('game_pk')
            if isinstance(change, dict)
            else getattr(change, 'game_pk', None)
        )
        or 0
    )
    if config.expected_plan_fingerprints.get(game_pk):
        return CANONICAL_WRITE_SOURCE_REQUESTS
    if config.mode in PRODUCTION_MODES:
        return CANONICAL_WRITE_SOURCE_REQUESTS + AUTOMATIC_PLAN_SOURCE_REQUESTS
    return 0


def _record_work_failure(job, error, *, stage, counters, results):
    failed = continuous_game_work.fail(job, error, stage=stage)
    counters['work_obligations_failed'] += 1
    results.append(failed.to_dict())


def _rotate_unclaimed_work(job, reason, results):
    if job is None:
        return
    deferred = continuous_game_work.defer_unclaimed(job, reason=reason)
    results.append(deferred.to_dict())


def _prepare_governed_replays(config, detection_results, *, sync_run_id):
    """Claim explicitly requested stored final observations for one-shot replay."""
    changes = []
    results = []
    current_changed = {
        int(item.get('game_pk') or 0)
        for item in detection_results
        if item.get('changed') and item.get('accepted')
    }
    for game_pk in config.replay_game_pks:
        result = {
            'game_pk': game_pk,
            'status': 'requested',
            'reason_code': 'game_replay_requested',
            'outcome': None,
            'events': [],
        }
        results.append(result)
        _record_replay_event(result, 'game_replay_requested')
        refusal = _replay_refusal(config, game_pk, current_changed)
        if refusal:
            result.update(status='refused', reason_code=refusal)
            _record_replay_event(
                result, 'game_replay_refused', reason_code=refusal,
            )
            continue

        row = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one()
        fingerprint = config.expected_plan_fingerprints[game_pk]
        official_date = date.fromisoformat(
            ((row.observation or {}).get('identity') or {})['official_date']
        )
        scope_key = (
            f'game:{game_pk}:obs:{row.observation_fingerprint}:'
            f'plan:{fingerprint}'
        )
        job = _ensure_replay_job(
            scope_key=scope_key, product_date=official_date,
            sync_run_id=sync_run_id,
        )
        claimed = sync_jobs.claim_job(job, sync_run_id=sync_run_id)
        if claimed is None:
            reason = (
                'replay_already_consumed'
                if job.status == sync_jobs.STATUS_SUCCEEDED
                else 'replay_attempts_exhausted'
                if (
                    job.status == sync_jobs.STATUS_FAILED
                    and (job.attempts or 0) >= (job.max_attempts or 0)
                )
                else 'replay_claimed_elsewhere'
            )
            result.update(status='inert', reason_code=reason, checkpoint=job.to_dict())
            _record_replay_event(
                result, 'game_replay_refused', reason_code=reason,
            )
            continue

        result.update(
            status='authorized', reason_code='game_replay_authorized',
            plan_fingerprint=fingerprint, checkpoint=claimed.to_dict(),
        )
        _record_replay_event(
            result, 'game_replay_authorized', plan_fingerprint=fingerprint,
        )
        changes.append({
            'game_pk': game_pk,
            'classification': row.last_classification,
            'changed': True,
            'accepted': True,
            'previous_observation_identity': row.previous_observation_fingerprint,
            'current_observation_identity': row.observation_fingerprint,
            'finality_state': row.finality_state,
            'source_authority': row.source_authority,
            'source_observed_at': (
                row.source_observed_at.isoformat() if row.source_observed_at else None
            ),
            'detected_at': row.accepted_at.isoformat(),
            'differences': dict(row.last_change_summary or {}),
            'reason': 'governed_stored_observation_replay',
            '_replay_result': result,
            '_replay_job_id': claimed.id,
        })
    return changes, results


def _ensure_replay_job(*, scope_key, product_date, sync_run_id):
    job = sync_jobs.SyncJob.query.filter_by(
        job_name=REPLAY_JOB_NAME,
        scope_key=scope_key,
        product_date=product_date,
    ).one_or_none()
    if job is not None:
        return job
    now = utc_now_naive()
    job = sync_jobs.SyncJob(
        job_name=REPLAY_JOB_NAME,
        job_family=REPLAY_JOB_FAMILY,
        lane=sync_jobs.LANE_INTERNAL,
        scope_key=scope_key,
        product_date=product_date,
        status=sync_jobs.STATUS_PENDING,
        attempts=0,
        max_attempts=REPLAY_MAX_ATTEMPTS,
        sync_run_id=sync_run_id,
        created_at=now,
        updated_at=now,
    )
    db.session.add(job)
    db.session.commit()
    return job


def _replay_refusal(config, game_pk, current_changed):
    if config.mode != ActivationMode.SHADOW_FULL_CHAIN:
        return 'replay_requires_shadow_full_chain'
    if config.production_publication_enabled:
        return 'publication_gate_invalid'
    if game_pk not in set(config.allowlist_game_pks):
        return 'game_not_allowlisted'
    fingerprint = config.expected_plan_fingerprints.get(game_pk)
    if not fingerprint:
        return 'missing_fingerprint'
    if len(fingerprint) != 64 or any(char not in '0123456789abcdef' for char in fingerprint.lower()):
        return 'malformed_fingerprint'
    if game_pk in current_changed:
        return 'current_cycle_change_present'
    row = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    if row is None or not row.observation or not row.observation_fingerprint:
        return 'observation_not_accepted'
    if row.last_classification in {
        cu02.STALE_OBSERVATION, cu02.AMBIGUOUS_OBSERVATION,
    }:
        return row.last_classification
    if row.last_classification not in {cu02.FINALIZED, cu02.CORRECTED}:
        return 'observation_not_accepted_final_event'
    if row.finality_state not in {
        cu03.game_finality.FINAL_PENDING_DATA,
        cu03.game_finality.FINAL_AND_USABLE,
    }:
        return 'observation_not_final'
    if row.source_authority != cu02.SOURCE_AUTHORITY:
        return 'weaker_authority'
    identity = (row.observation or {}).get('identity') or {}
    if not identity.get('official_date'):
        return 'observation_official_date_missing'
    return None


def _settle_replay(result, impact):
    job = db.session.get(sync_jobs.SyncJob, result['checkpoint']['id'])
    if impact.get('orchestration_status') == cu03.STATUS_CANONICAL_FAILED:
        _fail_replay(result, impact.get('source_failure_state') or 'canonical_failed')
        return
    if not impact.get('canonical_action_attempted'):
        _fail_replay(result, 'canonical_action_not_attempted')
        return
    outcome = (
        'mutated' if impact.get('canonical_mutation_performed')
        else 'authorized_no_op'
    )
    sync_jobs.complete_job(job, result={
        'status': 'completed', 'outcome': outcome,
        'game_pk': result['game_pk'],
        'plan_fingerprint': result.get('plan_fingerprint'),
        'canonical_mutation_performed': bool(
            impact.get('canonical_mutation_performed')
        ),
        'affected_pitcher_ids': impact.get('affected_pitcher_ids') or [],
        'affected_team_ids': impact.get('affected_team_ids') or [],
    })
    result.update(
        status='consumed', reason_code='game_replay_completed', outcome=outcome,
        checkpoint=job.to_dict(),
    )
    _record_replay_event(result, 'game_replay_completed', outcome=outcome)


def _fail_replay(result, error):
    # A PostgreSQL statement failure aborts the current transaction. Clear that
    # failed unit of work before writing the durable bounded-attempt checkpoint;
    # no canonical success reaches this failure path.
    db.session.rollback()
    job = db.session.get(sync_jobs.SyncJob, result['checkpoint']['id'])
    sync_jobs.fail_job(job, error, result={
        'status': 'failed', 'game_pk': result['game_pk'],
        'reason_code': 'replay_execution_failed',
    })
    result.update(
        status='failed', reason_code='replay_execution_failed',
        outcome=None, checkpoint=job.to_dict(),
    )
    _record_replay_event(
        result, 'game_replay_failed', error=type(error).__name__,
    )


def _record_replay_event(result, event, **fields):
    value = {'event': event, 'game_pk': result['game_pk'], **fields}
    result.setdefault('events', []).append(value)
    _replay_log(event, result['game_pk'], **fields)


def _replay_log(event, game_pk, **fields):
    logger.info(json.dumps({
        'event': event, 'game_pk': game_pk, **fields,
    }, sort_keys=True))


def _finish_run(result):
    return sync_metadata.finish_sync_run(
        result.sync_run_id,
        sync_metadata.STATUS_PARTIAL if result.status == RESULT_PARTIAL else sync_metadata.STATUS_SUCCESS,
        records_processed=result.games_checked,
        records_failed=len(result.failures),
        new_logs_added=result.canonical_mutation_games,
        pitchers_updated=len(result.affected_pitcher_ids),
        errors=len(result.failures),
        api_calls_made=result.source_requests,
        retries_used=result.source_retries,
        source_reads=result.source_requests,
        source_changes=result.changed_games,
        canonical_mutations=result.canonical_mutation_games,
        affected_games=result.changed_games,
        affected_teams=len(result.affected_team_ids),
        affected_pitchers=len(result.affected_pitcher_ids),
        downstream_work_created=result.durable_work_created,
        warnings_count=len(result.failures),
        outcome={
            'unchanged_games': result.unchanged_games,
            'proof_publications': result.proof_publications,
            'live_publications': result.live_publications,
        },
        error_message=json.dumps({
            'mode': result.mode,
            'reason': result.reason_code,
            'proof_publications': result.proof_publications,
            'live_publications': result.live_publications,
            'failures': list(result.failures),
        }, sort_keys=True),
        source=SOURCE_CONTINUOUS,
        job_name=JOB_CONTINUOUS_CYCLE,
        run_type=sync_control_plane.RunType.LIVE_GAME,
        trigger_type=sync_control_plane.TriggerType.SOURCE_CHANGE,
        baseball_date=datetime.fromisoformat(result.represented_time).date(),
        source_domain=sync_control_plane.SourceDomain.LIVE_FEED,
        scopes=sync_control_plane.scope_entries(
            league=True,
            team_ids=result.affected_team_ids,
            pitcher_ids=result.affected_pitcher_ids,
            source_domains=(sync_control_plane.SourceDomain.LIVE_FEED,),
        ),
        stage=(
            sync_metadata.STAGE_PUBLISHED
            if result.live_publications
            else sync_control_plane.RunStage.CONTINUOUS_COMPLETE.value
        ),
    )


def _empty_result(config, represented, started_at, started_clock, *, status, reason,
                  failures=(), lock_acquired=False):
    return ContinuousCycleResult(
        mode=config.mode.value, status=status, reason_code=reason,
        started_at=started_at.isoformat(), finished_at=utc_now_naive().isoformat(),
        represented_time=represented.isoformat(), failures=tuple(failures),
        lock_acquired=lock_acquired,
        publication_target=_publication_target(config.mode),
        runtime_ms=round((monotonic() - started_clock) * 1000, 3),
    )


def _publication_target(mode):
    if mode == ActivationMode.PROOF_PUBLICATION:
        return cu07.PROOF_SNAPSHOT_TYPE
    if mode in PRODUCTION_MODES:
        return 'production_current'
    return 'none'


def _change_is_allowlisted(change, config):
    game_pk = int(change.get('game_pk') or 0)
    if game_pk in set(config.allowlist_game_pks):
        return True
    if not config.allowlist_team_ids:
        return False
    row = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    identity = ((row.observation or {}).get('identity') or {}) if row else {}
    teams = {
        identity.get('home_team_id'), identity.get('away_team_id'),
    } - {None}
    return bool(teams) and teams.issubset(set(config.allowlist_team_ids))


def _cohort_is_allowlisted(impact, config):
    if config.mode == ActivationMode.FULL_LIVE:
        return True
    game_pk = int(impact.get('game_pk') or 0)
    if game_pk in set(config.allowlist_game_pks):
        return True
    teams = set(impact.get('affected_team_ids') or ())
    return bool(teams) and teams.issubset(set(config.allowlist_team_ids))


def _game_data_through(game_pk):
    row = GameObservationState.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    raw = (((row.observation or {}).get('identity') or {}).get('official_date') if row else None)
    try:
        return date.fromisoformat(raw) if raw else None
    except ValueError:
        return None


def _represented_time(value):
    if value is None:
        return datetime.now(timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    elif isinstance(value, datetime):
        parsed = value
    else:
        raise ValueError('represented_time must be an ISO datetime')
    if parsed.tzinfo is None:
        raise ValueError('represented_time must include a timezone')
    return parsed.astimezone(timezone.utc)


def _source_order(value):
    if not value:
        return 0
    try:
        parsed = datetime.fromisoformat(str(value))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.astimezone(timezone.utc).timestamp())
    except (TypeError, ValueError):
        return 0


def _metrics(client):
    metrics = getattr(client, 'metrics', None)
    if metrics is None or not hasattr(metrics, 'snapshot'):
        return {'api_calls': 0, 'retries': 0}
    value = metrics.snapshot()
    return {
        'api_calls': int(value.get('api_calls') or 0),
        'retries': int(value.get('retries') or 0),
    }


def _max_attempts_per_request(client):
    getter = getattr(client, 'max_attempts_per_request', None)
    if not callable(getter):
        return 1
    try:
        return max(1, int(getter()))
    except (TypeError, ValueError):
        return 1


def _positive_int(value):
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _elapsed_ms(started):
    return round((monotonic() - started) * 1000, 3)


def _dict(value):
    if isinstance(value, dict):
        return value
    if hasattr(value, 'to_dict'):
        return value.to_dict()
    return asdict(value)


def _bool(value, default):
    if value is None:
        return default
    return str(value).strip().lower() in {'1', 'true', 'yes', 'on'}


def _csv_ints(value, errors, error_code):
    if not value:
        return ()
    try:
        return tuple(sorted({int(item.strip()) for item in str(value).split(',') if item.strip()}))
    except ValueError:
        errors.append(error_code)
        return ()


def _integer(env, key, default, errors, *, minimum):
    try:
        value = int(env.get(key, default))
    except (TypeError, ValueError):
        errors.append(f'invalid_{key.lower()}')
        return default
    if value < minimum:
        errors.append(f'invalid_{key.lower()}')
        return default
    return value
