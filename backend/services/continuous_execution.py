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
from services import game_change_detection as cu02
from services import incremental_arm_read_team_state as cu05
from services import incremental_publication as cu07
from services import incremental_read_model_rebuild as cu06
from services import incremental_workload_rest as cu04
from services import sync_metadata
from services import sync_jobs
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
    runtime_ms: float = 0.0

    def to_dict(self):
        value = asdict(self)
        for key in (
            'affected_pitcher_ids', 'affected_team_ids', 'failures',
            'detection_results', 'downstream_results',
            'replay_results',
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
                cache_adapter=cache_adapter,
                source_snapshot=source_snapshot,
            )
        except Exception as exc:  # cycle-level acquisition/config failure
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
    max_feed_games = min(
        config.max_games,
        max(0, config.source_request_budget - 1),
    )
    detection_cycle = kwargs['detector'](
        reference_date=kwargs['represented'].date(),
        correction_days=config.correction_days,
        client=client,
        max_games=max_feed_games,
    )
    detection_results = list(detection_cycle.get('results') or ())
    replay_changes, replay_results = _prepare_governed_replays(
        config, detection_results, sync_run_id=kwargs['sync_run_id'],
    )
    failures = []
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
    }
    affected_pitchers = set()
    affected_teams = set()
    downstream = []
    timeout_reached = False
    publication_target = _publication_target(config.mode)

    for change in [*detection_results, *replay_changes]:
        replay_result = change.get('_replay_result')
        if config.mode == ActivationMode.SHADOW_DETECT:
            counters['skipped_by_mode'] += int(bool(change.get('changed')))
            continue
        if not change.get('changed'):
            # CU-02 has already classified unchanged/rejected/failed evidence;
            # no later service can turn it into canonical work safely.
            continue
        current_metrics = _metrics(client)
        if (
            current_metrics['api_calls'] - before_metrics['api_calls']
            >= config.source_request_budget
        ):
            counters['skipped_by_mode'] += 1
            continue
        if breaker_open:
            counters['skipped_by_mode'] += int(bool(change.get('changed')))
            continue
        if monotonic() - started_clock >= config.max_runtime_seconds:
            timeout_reached = True
            break
        if counters['canonical_actions'] >= config.max_canonical_actions:
            counters['skipped_by_mode'] += int(bool(change.get('changed')))
            continue
        if config.mode == ActivationMode.LIMITED_LIVE and not _change_is_allowlisted(
            change, config,
        ):
            counters['skipped_by_allowlist'] += int(bool(change.get('changed')))
            continue

        fingerprint = config.expected_plan_fingerprints.get(int(change.get('game_pk') or 0))
        stage_started = monotonic()
        try:
            impact = kwargs['orchestrator'](
                change,
                allow_canonical_write=True,
                expected_plan_fingerprint=fingerprint,
            )
        except Exception as exc:  # one game must not poison independent cohorts
            if replay_result is not None:
                _fail_replay(replay_result, exc)
            failures.append({
                'scope': 'orchestration', 'game_pk': change.get('game_pk'),
                'error': type(exc).__name__,
            })
            continue
        impact_dict = _dict(impact)
        if replay_result is not None:
            _settle_replay(replay_result, impact_dict)
        counters['canonical_actions'] += int(impact_dict.get('cu01_invocations') or 0)
        game_result = {
            'game_pk': change.get('game_pk'), 'cu03': impact_dict,
            'latency': {
                'canonical_stage_ms': _elapsed_ms(stage_started),
                'canonical_stage_completed_at': utc_now_naive().isoformat(),
            },
        }
        if impact_dict.get('orchestration_status') == cu03.STATUS_CANONICAL_FAILED:
            failures.append({
                'scope': 'canonical', 'game_pk': change.get('game_pk'),
                'error': impact_dict.get('source_failure_state') or 'canonical_failed',
            })
        if not impact_dict.get('canonical_mutation_performed'):
            downstream.append(game_result)
            continue

        counters['canonical_mutation_games'] += 1
        affected_pitchers.update(impact_dict.get('affected_pitcher_ids') or ())
        affected_teams.update(impact_dict.get('affected_team_ids') or ())
        data_through = _game_data_through(change.get('game_pk'))
        if data_through is None:
            failures.append({
                'scope': 'represented_date', 'game_pk': change.get('game_pk'),
                'error': 'official_date_missing',
            })
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
            downstream.append(game_result)
            continue
        workload_dict = _dict(workload)
        game_result['cu04'] = workload_dict
        game_result['latency']['cu04_stage_ms'] = _elapsed_ms(stage_started)
        counters['cu04_pitchers_recomputed'] += len(
            workload_dict.get('pitchers_recomputed') or ()
        )
        counters['cu04_teams_recomputed'] += len(workload_dict.get('teams_recomputed') or ())
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
            downstream.append(game_result)
            continue
        state_dict = _dict(state)
        game_result['cu05'] = state_dict
        game_result['latency']['cu05_stage_ms'] = _elapsed_ms(stage_started)
        counters['cu05_arm_reads_recomputed'] += len(
            state_dict.get('arm_reads_recomputed') or ()
        )
        counters['cu05_teams_recomputed'] += len(state_dict.get('teams_recomputed') or ())
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

        if config.mode == ActivationMode.PROOF_PUBLICATION:
            if counters['publication_candidates'] >= config.max_publication_cohorts:
                game_result['publication'] = {
                    'status': 'skipped', 'reason_code': 'max_publication_cohorts_reached',
                }
            else:
                try:
                    _publish(
                        kwargs['proof_publisher'], read_models, change, kwargs,
                        game_result, counters, proof=True,
                    )
                except Exception as exc:
                    failures.append({
                        'scope': 'proof_publication', 'game_pk': change.get('game_pk'),
                        'error': type(exc).__name__,
                    })
        elif config.mode in PRODUCTION_MODES:
            if counters['publication_candidates'] >= config.max_publication_cohorts:
                game_result['publication'] = {
                    'status': 'skipped', 'reason_code': 'max_publication_cohorts_reached',
                }
            elif not _cohort_is_allowlisted(impact_dict, config):
                counters['skipped_by_allowlist'] += 1
                game_result['publication'] = {
                    'status': 'skipped', 'reason_code': 'cohort_not_allowlisted',
                }
            elif kwargs['production_publisher'] is None:
                failures.append({
                    'scope': 'publication', 'game_pk': change.get('game_pk'),
                    'error': 'production_publisher_unavailable',
                })
                game_result['publication'] = {
                    'status': 'blocked', 'reason_code': 'production_publisher_unavailable',
                }
            else:
                try:
                    _publish(
                        kwargs['production_publisher'], read_models, change, kwargs,
                        game_result, counters, proof=False,
                    )
                except Exception as exc:
                    failures.append({
                        'scope': 'live_publication', 'game_pk': change.get('game_pk'),
                        'error': type(exc).__name__,
                    })
        if 'publication' in game_result:
            game_result['latency']['publication_stage_completed_at'] = (
                utc_now_naive().isoformat()
            )
        downstream.append(game_result)

    after_metrics = _metrics(client)
    source_requests = max(
        int(detection_cycle.get('requests_expected') or 0),
        after_metrics['api_calls'] - before_metrics['api_calls'],
    )
    source_retries = max(0, after_metrics['retries'] - before_metrics['retries'])
    source_budget_exhausted = source_requests >= config.source_request_budget
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
        runtime_ms=round((monotonic() - started_clock) * 1000, 3),
        **counters,
    )
    run = _finish_run(result)
    if result.sync_run_id is None and run is not None:
        result = replace(result, sync_run_id=run.id)
    return result


def _publish(publisher, read_models, change, kwargs, game_result, counters, *, proof):
    counters['publication_candidates'] += 1
    expected_current_id = None
    if proof:
        current = cu07.get_current_publication()
        expected_current_id = current.id if current is not None else None
    elif kwargs['production_current_id_provider'] is not None:
        expected_current_id = kwargs['production_current_id_provider']()
    result = publisher(
        read_models,
        source_identity=change.get('current_observation_identity'),
        source_order=_source_order(change.get('source_observed_at')),
        sync_run_id=kwargs['sync_run_id'],
        expected_current_id=expected_current_id,
        cache_adapter=kwargs['cache_adapter'],
    )
    value = _dict(result)
    game_result['publication'] = value
    if value.get('committed'):
        counters['proof_publications' if proof else 'live_publications'] += 1
    if value.get('cache_handoff_status') == 'complete':
        counters['cache_handoffs'] += 1


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
        error_message=json.dumps({
            'mode': result.mode,
            'reason': result.reason_code,
            'proof_publications': result.proof_publications,
            'live_publications': result.live_publications,
            'failures': list(result.failures),
        }, sort_keys=True),
        source=SOURCE_CONTINUOUS,
        job_name=JOB_CONTINUOUS_CYCLE,
        stage=(sync_metadata.STAGE_PUBLISHED if result.live_publications else 'continuous_complete'),
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
