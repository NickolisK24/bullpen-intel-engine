"""SP-07 authoritative final-game reconciliation over existing canonical writers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
import hashlib
import logging

from sqlalchemy import text

from models.final_game_reconciliation import (
    FinalGameMutation,
    FinalGameVersion,
    FinalPitchingAppearanceVersion,
)
from models.game_log import GameLog
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.pitcher import Pitcher
from models.play_by_play_foundation import PlayByPlayProcessedGame
from models.sync_run import SyncRun
from services import game_appearance_extraction as extraction
from services import sync as sync_service
from services.game_finality import FINAL_AND_USABLE, classify_game_finality
from services.play_by_play_foundation import process_final_play_by_play_foundation
from services.source_observations import (
    ObservationCompleteness,
    PayloadKind,
    SourceProvider,
    SourceSubjectType,
    build_source_identity,
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
from utils.db import db
from utils.time import utc_now_naive


logger = logging.getLogger(__name__)

FINAL_PAYLOAD_SCHEMA_VERSION = 1
FINAL_FACT_FINGERPRINT_VERSION = 'final-game-facts-v1'
FINAL_JOB_PAYLOAD_SCHEMA_VERSION = 1
PRIORITY_CANONICAL_IMPACT = 40


class FinalMutationType(str, Enum):
    FINAL_GAME_INGESTED = 'final_game_ingested'
    STARTER_APPEARANCE_ADDED = 'starter_appearance_added'
    RELIEVER_APPEARANCE_ADDED = 'reliever_appearance_added'
    PITCHING_LINE_CORRECTED = 'pitching_line_corrected'
    APPEARANCE_CONTEXT_CORRECTED = 'appearance_context_corrected'
    FINAL_PLAY_BY_PLAY_CORRECTED = 'final_play_by_play_corrected'
    FINAL_GAME_CONTEXT_CORRECTED = 'final_game_context_corrected'


@dataclass(frozen=True)
class FinalSourceBundle:
    game: dict
    boxscore: dict
    play_by_play: dict | None
    finality_observation: object
    boxscore_observation: object
    play_by_play_observation: object | None
    play_by_play_completeness: str
    play_by_play_changed: bool = False
    source_reads: int = 3
    source_change_count: int = 0


@dataclass(frozen=True)
class FinalReconciliationResult:
    game_version: FinalGameVersion
    appearance_versions: tuple[FinalPitchingAppearanceVersion, ...]
    mutations: tuple[FinalGameMutation, ...]
    created: bool
    affected_team_ids: tuple[int, ...]
    affected_pitcher_ids: tuple[int, ...]
    affected_pitcher_mlb_ids: tuple[int, ...]
    removed_game_log_ids: tuple[int, ...]
    pbp_result: dict


def finality_source_identity(game_pk, baseball_date):
    return build_source_identity(
        provider=SourceProvider.MLB_STATS_API,
        source_domain=SourceDomain.SCHEDULE,
        endpoint='/schedule',
        subject_type=SourceSubjectType.GAME,
        subject_key=f'game:{int(game_pk)}:finality',
        request_parameters={
            'sportId': 1,
            'gamePk': int(game_pk),
            'hydrate': 'team',
        },
        baseball_date=_date(baseball_date),
    )


def boxscore_source_identity(game_pk, baseball_date):
    return build_source_identity(
        provider=SourceProvider.MLB_STATS_API,
        source_domain=SourceDomain.BOXSCORE,
        endpoint=f'/game/{int(game_pk)}/boxscore',
        subject_type=SourceSubjectType.GAME,
        subject_key=f'game:{int(game_pk)}:final-boxscore',
        request_parameters={'gamePk': int(game_pk), 'final': True},
        baseball_date=_date(baseball_date),
    )


def play_by_play_source_identity(game_pk, baseball_date):
    return build_source_identity(
        provider=SourceProvider.MLB_STATS_API,
        source_domain=SourceDomain.PLAY_BY_PLAY,
        endpoint=f'/game/{int(game_pk)}/playByPlay',
        subject_type=SourceSubjectType.GAME,
        subject_key=f'game:{int(game_pk)}:final-play-by-play',
        request_parameters={'gamePk': int(game_pk), 'final': True},
        baseball_date=_date(baseball_date),
    )


def acquire_final_game_sources(
    game_pk,
    baseball_date,
    *,
    client=None,
    sync_run_id=None,
    sync_job_id=None,
):
    """Fetch and durably record finality, boxscore, and optional final PBP."""
    client = client or sync_service.mlb_client
    game_pk = _positive_int(game_pk)
    baseball_date = _date(baseball_date)
    correction = FinalGameVersion.query.filter_by(game_pk=game_pk).first() is not None

    finality_identity = finality_source_identity(game_pk, baseball_date)
    started = utc_now_naive()
    try:
        games = list(client.get_schedule(game_pk=game_pk, hydrate='team') or [])
    except Exception as exc:
        _record_fetch_failure(
            finality_identity, exc, started, sync_run_id, sync_job_id,
        )
        raise
    matching = [game for game in games if _int((game or {}).get('gamePk')) == game_pk]
    finality_completeness = (
        ObservationCompleteness.COMPLETE if len(matching) == 1
        else ObservationCompleteness.UNKNOWN
    )
    finality_result = record_source_observation(
        identity=finality_identity,
        payload=games,
        completeness=finality_completeness,
        payload_schema_version=FINAL_PAYLOAD_SCHEMA_VERSION,
        payload_kind=PayloadKind.RAW_JSON,
        record_count=len(matching),
        correction=correction,
        attempt_started_at=started,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
    )
    if len(matching) != 1:
        raise ValueError('authoritative finality response did not contain exactly one game')
    game = matching[0]

    boxscore_identity = boxscore_source_identity(game_pk, baseball_date)
    started = utc_now_naive()
    try:
        boxscore = client.get_game_boxscore(game_pk)
    except Exception as exc:
        _record_fetch_failure(boxscore_identity, exc, started, sync_run_id, sync_job_id)
        raise
    lines = sync_service._extract_pitching_lines_from_boxscore(boxscore)
    boxscore_complete = _boxscore_complete(game, boxscore, lines)
    boxscore_result = record_source_observation(
        identity=boxscore_identity,
        payload=boxscore,
        completeness=(
            ObservationCompleteness.COMPLETE if boxscore_complete
            else ObservationCompleteness.PARTIAL
        ),
        payload_schema_version=FINAL_PAYLOAD_SCHEMA_VERSION,
        payload_kind=PayloadKind.RAW_JSON,
        record_count=len(lines),
        correction=correction,
        attempt_started_at=started,
        sync_run_id=sync_run_id,
        sync_job_id=sync_job_id,
    )
    if not boxscore_complete:
        raise ValueError('final boxscore is incomplete for core appearance authority')

    pbp_identity = play_by_play_source_identity(game_pk, baseball_date)
    started = utc_now_naive()
    play_by_play = None
    pbp_observation = None
    pbp_source_result = None
    pbp_completeness = ObservationCompleteness.FAILED.value
    try:
        play_by_play = client.get_game_play_by_play(game_pk)
        all_plays = (play_by_play or {}).get('allPlays')
        pbp_complete = _pbp_complete(all_plays, lines)
        pbp_completeness = (
            ObservationCompleteness.COMPLETE.value if pbp_complete
            else ObservationCompleteness.PARTIAL.value
        )
        pbp_source_result = record_source_observation(
            identity=pbp_identity,
            payload=play_by_play,
            completeness=pbp_completeness,
            payload_schema_version=FINAL_PAYLOAD_SCHEMA_VERSION,
            payload_kind=PayloadKind.RAW_JSON,
            record_count=len(all_plays) if isinstance(all_plays, list) else 0,
            correction=correction,
            attempt_started_at=started,
            sync_run_id=sync_run_id,
            sync_job_id=sync_job_id,
        )
        pbp_observation = pbp_source_result.observation
    except Exception as exc:  # optional source; core remains eligible
        _record_fetch_failure(pbp_identity, exc, started, sync_run_id, sync_job_id)

    return FinalSourceBundle(
        game=game,
        boxscore=boxscore,
        play_by_play=play_by_play,
        finality_observation=finality_result.observation,
        boxscore_observation=boxscore_result.observation,
        play_by_play_observation=pbp_observation,
        play_by_play_completeness=pbp_completeness,
        play_by_play_changed=bool(
            pbp_source_result is not None and pbp_source_result.changed
        ),
        source_change_count=sum(bool(result.changed) for result in (
            finality_result,
            boxscore_result,
            pbp_source_result,
        ) if result is not None),
    )


def reconcile_final_game(bundle, *, sync_run_id=None, commit=True, fail_after_core=False):
    """Reconcile one complete final boxscore and optional PBP as one core transaction."""
    if bundle.boxscore_observation.completeness != 'complete':
        raise ValueError('complete boxscore observation required')
    game_pk = _positive_int(bundle.game.get('gamePk'))
    baseball_date = _date(bundle.game.get('officialDate'))
    finality = classify_game_finality(
        bundle.game, boxscore=bundle.boxscore, require_boxscore=True,
    )
    if finality.state != FINAL_AND_USABLE:
        raise ValueError(f'game {game_pk} is not authoritative Final: {finality.reason}')

    _lock_game(game_pk)
    lines = sync_service._extract_pitching_lines_from_boxscore(bundle.boxscore)
    order = sync_service._pitcher_order_by_side(bundle.boxscore)
    appearances = extraction.extract_game_appearances(
        game=bundle.game,
        pitching_lines=lines,
        pitcher_order=order,
        game_date=baseball_date,
    )
    contexts = (
        _appearance_contexts(bundle.game, bundle.play_by_play)
        if bundle.play_by_play_completeness == 'complete' else {}
    )
    projections = _appearance_projections(appearances, contexts)
    game_projection = _game_projection(bundle.game, bundle.boxscore, bundle.play_by_play)
    game_fingerprint = _fingerprint({
        'version': FINAL_FACT_FINGERPRINT_VERSION,
        'game': game_projection,
        'appearances': projections,
    })

    latest_game = (
        FinalGameVersion.query.filter_by(game_pk=game_pk, is_current=True)
        .with_for_update().one_or_none()
    )
    current_appearances = {
        row.pitcher_mlb_id: row
        for row in FinalPitchingAppearanceVersion.query.filter_by(
            game_pk=game_pk, is_current=True,
        ).with_for_update().all()
    }
    legacy_work = GameIngestionWorkItem.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    bootstrap_without_mutation = bool(
        latest_game is None
        and legacy_work is not None
        and legacy_work.status == GameIngestionWorkItem.STATUS_COMPLETED
        and legacy_work.source_revision == extraction.appearance_set_fingerprint(appearances)
        and legacy_work.rows_reconciled == len(appearances)
    )
    same_final_facts = bool(
        latest_game is not None and latest_game.fact_fingerprint == game_fingerprint
    )
    if same_final_facts and not bundle.play_by_play_changed:
        return _unchanged_result(latest_game, game_pk)

    if not same_final_facts:
        core = sync_service.process_completed_game_for_postgame_refresh(
            bundle.game,
            schedule_date=baseball_date,
            sync_run_id=sync_run_id,
            force=True,
            boxscore=bundle.boxscore,
        )
        if (
            core.get('processing_status') != 'fully_processed'
            or core.get('pitcher_resolution_failures')
            or core.get('correction_attempts_failed')
            or core.get('pitching_lines_seen') != len(appearances)
        ):
            raise ValueError('existing canonical GameLog writer did not fully reconcile core')

    pbp_result = _process_final_pbp(bundle, baseball_date, sync_run_id)
    pbp_only_correction = bool(
        same_final_facts
        and pbp_result.get('corrected')
        and not pbp_result.get('observation_rejected')
    )
    if same_final_facts and not pbp_only_correction:
        return _unchanged_result(latest_game, game_pk, pbp_result=pbp_result)
    effective_pbp_completeness = bundle.play_by_play_completeness
    if (
        effective_pbp_completeness == ObservationCompleteness.COMPLETE.value
        and pbp_result.get('processing_status')
        != PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
    ):
        effective_pbp_completeness = ObservationCompleteness.PARTIAL.value

    pitchers = {
        row.mlb_id: row
        for row in Pitcher.query.filter(
            Pitcher.mlb_id.in_([item['pitcher_mlb_id'] for item in projections])
        ).all()
    }
    logs = {
        (row.pitcher_id, row.mlb_game_pk): row
        for row in GameLog.query.filter_by(mlb_game_pk=game_pk).all()
    }
    if set(pitchers) != {item['pitcher_mlb_id'] for item in projections}:
        raise ValueError('canonical pitcher resolution incomplete after core reconciliation')

    now = utc_now_naive()
    if latest_game is not None:
        latest_game.is_current = False
        latest_game.superseded_at = now
    game_version = FinalGameVersion(
        game_pk=game_pk,
        version_number=(latest_game.version_number + 1) if latest_game else 1,
        predecessor_version_id=latest_game.id if latest_game else None,
        baseball_date=baseball_date,
        game_type=game_projection['game_type'],
        home_team_id=game_projection['home_team_id'],
        away_team_id=game_projection['away_team_id'],
        home_score=game_projection['home_score'],
        away_score=game_projection['away_score'],
        innings_played=game_projection['innings_played'],
        extra_innings=game_projection['extra_innings'],
        game_number=game_projection['game_number'],
        doubleheader=game_projection['doubleheader'],
        fact_fingerprint=game_fingerprint,
        fingerprint_version=FINAL_FACT_FINGERPRINT_VERSION,
        core_completeness='complete',
        pbp_completeness=effective_pbp_completeness,
        finality_observation_id=bundle.finality_observation.id,
        boxscore_observation_id=bundle.boxscore_observation.id,
        play_by_play_observation_id=(
            bundle.play_by_play_observation.id
            if bundle.play_by_play_observation is not None else None
        ),
        sync_run_id=sync_run_id,
        observed_at=bundle.boxscore_observation.observed_at,
    )
    db.session.add(game_version)
    db.session.flush()

    created_versions = []
    mutations = []
    affected_teams = set()
    affected_pitchers = set()
    affected_mlb_ids = set()
    source_ids = {
        'boxscore': bundle.boxscore_observation.id,
        'pbp': (
            bundle.play_by_play_observation.id
            if bundle.play_by_play_observation is not None else None
        ),
    }
    for projection in projections:
        pitcher = pitchers[projection['pitcher_mlb_id']]
        log = logs.get((pitcher.id, game_pk))
        if log is None or log.appearance_team_status != GameLog.APPEARANCE_TEAM_RESOLVED:
            raise ValueError('core GameLog projection lacks resolved team-at-appearance')
        prior = current_appearances.pop(projection['pitcher_mlb_id'], None)
        fact_fingerprint = _fingerprint(projection)
        if prior is not None and prior.fact_fingerprint == fact_fingerprint:
            continue
        if prior is not None:
            prior.is_current = False
            prior.superseded_at = now
        version = _new_appearance_version(
            game_version,
            log,
            pitcher,
            projection,
            prior,
            source_ids,
            sync_run_id,
        )
        db.session.add(version)
        db.session.flush()
        created_versions.append(version)
        if not bootstrap_without_mutation:
            mutation_type = _appearance_mutation_type(prior, projection)
            mutation = _new_mutation(
                mutation_type,
                game_version,
                source_observation_id=bundle.boxscore_observation.id,
                team_id=projection['team_id_at_appearance'],
                pitcher=pitcher,
                old_appearance=prior,
                new_appearance=version,
                sync_run_id=sync_run_id,
                details={'changed_fields': _changed_fields(prior, projection)},
            )
            db.session.add(mutation)
            mutations.append(mutation)
            affected_teams.add(projection['team_id_at_appearance'])
            affected_pitchers.add(pitcher.id)
            affected_mlb_ids.add(pitcher.mlb_id)

    removed_log_ids = []
    for pitcher_mlb_id, prior in current_appearances.items():
        prior.is_current = False
        prior.superseded_at = now
        mutation = _new_mutation(
            FinalMutationType.PITCHING_LINE_CORRECTED.value,
            game_version,
            source_observation_id=bundle.boxscore_observation.id,
            team_id=prior.team_id_at_appearance,
            pitcher=db.session.get(Pitcher, prior.pitcher_id),
            old_appearance=prior,
            new_appearance=None,
            sync_run_id=sync_run_id,
            details={'removed_from_complete_official_appearance_set': True},
        )
        db.session.add(mutation)
        mutations.append(mutation)
        affected_teams.add(prior.team_id_at_appearance)
        affected_pitchers.add(prior.pitcher_id)
        affected_mlb_ids.add(pitcher_mlb_id)
        stale_log = db.session.get(GameLog, prior.game_log_id)
        if stale_log is not None:
            removed_log_ids.append(stale_log.id)
            db.session.delete(stale_log)

    if pbp_only_correction:
        pbp_pitcher_ids = set(
            (pbp_result.get('pitch_rows') or {}).get('affected_pitcher_mlb_ids') or []
        )
        pbp_team_ids = set(
            (pbp_result.get('pitch_rows') or {}).get('affected_team_ids') or []
        )
        affected_mlb_ids.update(pbp_pitcher_ids)
        affected_teams.update(pbp_team_ids)
        for pitcher in Pitcher.query.filter(Pitcher.mlb_id.in_(pbp_pitcher_ids or [-1])):
            affected_pitchers.add(pitcher.id)
        if not affected_teams:
            affected_teams.update((game_projection['home_team_id'], game_projection['away_team_id']))
        pbp_mutation = _new_mutation(
            FinalMutationType.FINAL_PLAY_BY_PLAY_CORRECTED.value,
            game_version,
            source_observation_id=bundle.play_by_play_observation.id,
            sync_run_id=sync_run_id,
            details={
                'affected_pitcher_mlb_ids': sorted(pbp_pitcher_ids),
                'affected_team_ids': sorted(pbp_team_ids),
                'previous_final_game_version_id': latest_game.id,
            },
        )
        db.session.add(pbp_mutation)
        mutations.append(pbp_mutation)

    if latest_game is None and not bootstrap_without_mutation:
        game_mutation = _new_mutation(
            FinalMutationType.FINAL_GAME_INGESTED.value,
            game_version,
            source_observation_id=bundle.boxscore_observation.id,
            sync_run_id=sync_run_id,
            details={'appearance_count': len(projections)},
        )
        db.session.add(game_mutation)
        mutations.insert(0, game_mutation)
    elif latest_game is not None and _game_context_changed(latest_game, game_projection):
        game_mutation = _new_mutation(
            FinalMutationType.FINAL_GAME_CONTEXT_CORRECTED.value,
            game_version,
            source_observation_id=bundle.boxscore_observation.id,
            sync_run_id=sync_run_id,
            details={'previous_final_game_version_id': latest_game.id},
        )
        db.session.add(game_mutation)
        mutations.append(game_mutation)
        affected_teams.update((game_projection['home_team_id'], game_projection['away_team_id']))

    if fail_after_core:
        raise RuntimeError('simulated failure during canonical final reconciliation')
    db.session.flush()
    if commit:
        db.session.commit()
    return FinalReconciliationResult(
        game_version=game_version,
        appearance_versions=tuple(created_versions),
        mutations=tuple(mutations),
        created=True,
        affected_team_ids=tuple(sorted(affected_teams)),
        affected_pitcher_ids=tuple(sorted(affected_pitchers)),
        affected_pitcher_mlb_ids=tuple(sorted(affected_mlb_ids)),
        removed_game_log_ids=tuple(sorted(removed_log_ids)),
        pbp_result=pbp_result,
    )


def execute_final_game_job(job, *, acquirer=acquire_final_game_sources):
    """Execute one claimed SP-04 final handoff; SP-02 settles the job lease."""
    payload = dict(job.details_json or {})
    game_pk = _positive_int(payload.get('game_pk') or job.scope_key)
    baseball_date = _date(payload.get('baseball_date') or job.product_date)
    run = _start_final_run(job, game_pk, baseball_date)
    failure_stage = RunStage.ACQUIRE
    try:
        mark_stage(run, failure_stage)
        bundle = acquirer(
            game_pk,
            baseball_date,
            sync_run_id=run.id,
            sync_job_id=job.id,
        )
        heartbeat_job(job.id, worker_id=job.worker_id, claim_token=job.claim_token)
        failure_stage = RunStage.CANONICALIZE
        mark_stage(run, failure_stage)
        result = reconcile_final_game(bundle, sync_run_id=run.id, commit=False)
        downstream = None
        if result.mutations:
            downstream = enqueue_job(
                job_type=JobType.PROCESS_CANONICAL_IMPACT,
                scope_type=JobScopeType.GAME,
                scope_key=str(game_pk),
                product_date=baseball_date,
                dedupe_key=f'CANONICAL_IMPACT:final-game:{game_pk}:v{result.game_version.version_number}',
                priority=PRIORITY_CANONICAL_IMPACT,
                sync_run_id=run.id,
                parent_job_id=job.id,
                payload_schema_version=FINAL_JOB_PAYLOAD_SCHEMA_VERSION,
                payload={
                    'game_pk': game_pk,
                    'baseball_date': baseball_date,
                    'final_game_version_id': result.game_version.id,
                    'mutation_ids': [row.id for row in result.mutations],
                    'source_observation_id': bundle.boxscore_observation.id,
                },
                commit=False,
            )
        add_scopes(run, [
            *((ScopeType.TEAM, value) for value in result.affected_team_ids),
            *((ScopeType.PITCHER, value) for value in result.affected_pitcher_ids),
        ], commit=False)
        optional_complete = bool(
            bundle.play_by_play_completeness == 'complete'
            and result.pbp_result.get('processing_status')
            == PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED
        )
        record_outcome(
            run,
            source_reads=bundle.source_reads,
            source_changes=bundle.source_change_count,
            canonical_mutations=len(result.mutations),
            affected_games=int(bool(result.mutations)),
            affected_teams=len(result.affected_team_ids),
            affected_pitchers=len(result.affected_pitcher_ids),
            downstream_work_created=int(downstream is not None),
            warnings_count=int(not optional_complete),
            outcome={
                'game_pk': game_pk,
                'final_game_version_id': result.game_version.id,
                'boxscore_observation_id': bundle.boxscore_observation.id,
                'play_by_play_observation_id': (
                    bundle.play_by_play_observation.id
                    if bundle.play_by_play_observation is not None else None
                ),
                'pbp_completeness': (
                    'complete' if optional_complete
                    else result.game_version.pbp_completeness
                ),
                'mutation_ids': [row.id for row in result.mutations],
                'affected_team_ids': list(result.affected_team_ids),
                'affected_pitcher_ids': list(result.affected_pitcher_ids),
                'downstream_job_id': downstream.id if downstream else None,
            },
            commit=False,
        )
        finalize_run(
            run,
            RunStatus.SUCCEEDED if optional_complete else RunStatus.PARTIAL,
            commit=False,
        )
        heartbeat_job(
            job.id, worker_id=job.worker_id, claim_token=job.claim_token, commit=False,
        )
        db.session.commit()
        return {
            'sync_run_id': run.id,
            'game_pk': game_pk,
            'final_game_version_id': result.game_version.id,
            'mutation_ids': [row.id for row in result.mutations],
            'downstream_job_id': downstream.id if downstream else None,
            'partial': not optional_complete,
        }
    except Exception as exc:
        db.session.rollback()
        record_failure(
            run.id,
            exc,
            failure_class=(
                FailureClass.SOURCE if failure_stage == RunStage.ACQUIRE
                else FailureClass.CANONICALIZATION
            ),
            stage=failure_stage,
            source_domain=SourceDomain.BOXSCORE,
            entity_type='game',
            entity_ref=game_pk,
            retryable=True,
            commit=False,
        )
        finalize_run(run.id, RunStatus.FAILED, failed_stage=failure_stage, commit=False)
        db.session.commit()
        raise


def run_next_final_game_job(worker_id, *, acquirer=acquire_final_game_sources, lease_seconds=300):
    return run_next_job(
        worker_id,
        {
            JobType.RECONCILE_FINAL_GAME.value: lambda job: execute_final_game_job(
                job, acquirer=acquirer,
            ),
        },
        job_types=[JobType.RECONCILE_FINAL_GAME],
        lease_seconds=lease_seconds,
    )


def current_final_game_version(game_pk):
    return FinalGameVersion.query.filter_by(game_pk=int(game_pk), is_current=True).one_or_none()


def current_final_appearances(game_pk):
    return (
        FinalPitchingAppearanceVersion.query
        .filter_by(game_pk=int(game_pk), is_current=True)
        .order_by(
            FinalPitchingAppearanceVersion.team_id_at_appearance,
            FinalPitchingAppearanceVersion.appearance_order,
            FinalPitchingAppearanceVersion.pitcher_mlb_id,
        ).all()
    )


def _appearance_projections(appearances, contexts):
    values = []
    for appearance in appearances:
        context = contexts.get(appearance['pitcher_mlb_id']) or {}
        values.append({
            'pitcher_mlb_id': appearance['pitcher_mlb_id'],
            'team_id_at_appearance': appearance['team_id'],
            'opponent_team_id': appearance['opponent_team_id'],
            'side': appearance['side'],
            'appearance_role': 'starter' if appearance['is_starter'] else 'reliever',
            'appearance_order': 0 if appearance['is_starter'] else context.get('appearance_order'),
            'outs_recorded': appearance['outs_recorded'],
            'pitches_thrown': appearance['pitches_thrown'],
            'strikes': appearance['strikes'],
            'balls': appearance['balls'],
            'batters_faced': appearance['batters_faced'],
            'hits_allowed': appearance['hits_allowed'],
            'runs_allowed': appearance['runs_allowed'],
            'earned_runs': appearance['earned_runs'],
            'walks': appearance['walks'],
            'strikeouts': appearance['strikeouts'],
            'home_runs_allowed': appearance['home_runs_allowed'],
            'hit_batters': appearance['hit_batters'],
            'wild_pitches': appearance['wild_pitches'],
            'balks': appearance.get('balks'),
            'games_finished': appearance['games_finished'],
            'inherited_runners': appearance['inherited_runners'],
            'inherited_runners_scored': appearance['inherited_runners_scored'],
            'save_situation': appearance['save_situation'],
            'hold': appearance['hold'],
            'blown_save': appearance['blown_save'],
            'win': appearance['win'],
            'loss': appearance['loss'],
            'save': appearance['save'],
            'entry_inning': context.get('entry_inning'),
            'entry_half': context.get('entry_half'),
            'entry_outs': context.get('entry_outs'),
            'entry_home_score': context.get('entry_home_score'),
            'entry_away_score': context.get('entry_away_score'),
            'entry_base_state': None,
            'inherited_runners_context': appearance['inherited_runners'],
            'exit_inning': context.get('exit_inning'),
            'exit_half': context.get('exit_half'),
            'exit_outs': context.get('exit_outs'),
            'exit_home_score': context.get('exit_home_score'),
            'exit_away_score': context.get('exit_away_score'),
            'context_completeness': 'partial' if context else 'unknown',
        })
    return sorted(values, key=lambda item: (item['side'], item['appearance_order'] is None, item['appearance_order'] or 0, item['pitcher_mlb_id']))


def _appearance_contexts(game, play_by_play):
    all_plays = (play_by_play or {}).get('allPlays')
    if not isinstance(all_plays, list) or not all_plays:
        return {}
    teams = game.get('teams') or {}
    team_ids = {
        'home': _int((((teams.get('home') or {}).get('team')) or {}).get('id')),
        'away': _int((((teams.get('away') or {}).get('team')) or {}).get('id')),
    }
    groups = {}
    previous = None
    for index, play in enumerate(all_plays):
        about = play.get('about') or {}
        matchup = play.get('matchup') or {}
        result = play.get('result') or {}
        pitcher_id = _int((matchup.get('pitcher') or {}).get('id'))
        inning = _int(about.get('inning'))
        half = str(about.get('halfInning') or '').lower() or None
        if pitcher_id is None or inning is None or half not in {'top', 'bottom'}:
            previous = play
            continue
        side = 'home' if half == 'top' else 'away'
        entry = groups.setdefault(pitcher_id, {
            'team_id': team_ids[side],
            'first_index': index,
            'entry_inning': inning,
            'entry_half': half,
            'entry_outs': _entry_outs(previous, inning, half),
            'entry_home_score': _prior_score(previous, 'homeScore'),
            'entry_away_score': _prior_score(previous, 'awayScore'),
        })
        entry.update({
            'exit_inning': inning,
            'exit_half': half,
            'exit_outs': _int(about.get('outs')),
            'exit_home_score': _int(result.get('homeScore')),
            'exit_away_score': _int(result.get('awayScore')),
        })
        previous = play
    by_team = {}
    for pitcher_id, context in groups.items():
        by_team.setdefault(context['team_id'], []).append((context['first_index'], pitcher_id))
    for entries in by_team.values():
        for order, (_index, pitcher_id) in enumerate(sorted(entries)):
            groups[pitcher_id]['appearance_order'] = order
    return groups


def _entry_outs(previous, inning, half):
    if not isinstance(previous, dict):
        return 0
    prior_about = previous.get('about') or {}
    if _int(prior_about.get('inning')) != inning or str(prior_about.get('halfInning') or '').lower() != half:
        return 0
    return _int((previous.get('about') or {}).get('outs'))


def _prior_score(previous, key):
    if not isinstance(previous, dict):
        return 0
    return _int((previous.get('result') or {}).get(key))


def _game_projection(game, boxscore, play_by_play):
    teams = game.get('teams') or {}
    home = teams.get('home') or {}
    away = teams.get('away') or {}
    innings = [
        _int((play.get('about') or {}).get('inning'))
        for play in ((play_by_play or {}).get('allPlays') or [])
    ]
    innings = [value for value in innings if value is not None]
    innings_played = max(innings) if innings else _team_innings(boxscore)
    return {
        'game_type': game.get('gameType'),
        'home_team_id': _positive_int((home.get('team') or {}).get('id')),
        'away_team_id': _positive_int((away.get('team') or {}).get('id')),
        'home_score': _int(home.get('score')),
        'away_score': _int(away.get('score')),
        'innings_played': innings_played,
        'extra_innings': innings_played > 9 if innings_played is not None else None,
        'game_number': _int(game.get('gameNumber')),
        'doubleheader': game.get('doubleHeader'),
    }


def _team_innings(boxscore):
    values = []
    for side in ('home', 'away'):
        raw = (((((boxscore or {}).get('teams') or {}).get(side) or {}).get('teamStats') or {}).get('pitching') or {}).get('inningsPitched')
        try:
            values.append((int(str(raw).split('.')[0]) if raw not in (None, '') else None))
        except (TypeError, ValueError):
            pass
    values = [value for value in values if value is not None]
    return max(values) if values else None


def _new_appearance_version(game_version, log, pitcher, projection, prior, source_ids, sync_run_id):
    values = dict(projection)
    return FinalPitchingAppearanceVersion(
        final_game_version_id=game_version.id,
        game_log_id=log.id,
        game_pk=game_version.game_pk,
        baseball_date=game_version.baseball_date,
        pitcher_id=pitcher.id,
        version_number=(prior.version_number + 1) if prior else 1,
        predecessor_version_id=prior.id if prior else None,
        fact_fingerprint=_fingerprint(projection),
        fingerprint_version=FINAL_FACT_FINGERPRINT_VERSION,
        boxscore_observation_id=source_ids['boxscore'],
        play_by_play_observation_id=source_ids['pbp'],
        sync_run_id=sync_run_id,
        **values,
    )


def _new_mutation(
    mutation_type,
    game_version,
    *,
    source_observation_id,
    team_id=None,
    pitcher=None,
    old_appearance=None,
    new_appearance=None,
    sync_run_id=None,
    details=None,
):
    identity = new_appearance.id if new_appearance is not None else f'removed-{old_appearance.id}' if old_appearance is not None else 'game'
    return FinalGameMutation(
        mutation_key=f'{game_version.game_pk}:v{game_version.version_number}:{mutation_type}:{identity}',
        mutation_type=mutation_type,
        final_game_version_id=game_version.id,
        old_appearance_version_id=old_appearance.id if old_appearance else None,
        new_appearance_version_id=new_appearance.id if new_appearance else None,
        game_pk=game_version.game_pk,
        baseball_date=game_version.baseball_date,
        team_id=team_id,
        pitcher_id=pitcher.id if pitcher else None,
        pitcher_mlb_id=pitcher.mlb_id if pitcher else None,
        source_observation_id=source_observation_id,
        sync_run_id=sync_run_id,
        details_json=details,
    )


def _appearance_mutation_type(prior, projection):
    if prior is None:
        return (
            FinalMutationType.STARTER_APPEARANCE_ADDED.value
            if projection['appearance_role'] == 'starter'
            else FinalMutationType.RELIEVER_APPEARANCE_ADDED.value
        )
    context_fields = {
        'appearance_order', 'entry_inning', 'entry_half', 'entry_outs',
        'entry_home_score', 'entry_away_score', 'entry_base_state',
        'inherited_runners_context', 'exit_inning', 'exit_half', 'exit_outs',
        'exit_home_score', 'exit_away_score', 'context_completeness',
    }
    changed = set(_changed_fields(prior, projection))
    return (
        FinalMutationType.APPEARANCE_CONTEXT_CORRECTED.value
        if changed and changed <= context_fields
        else FinalMutationType.PITCHING_LINE_CORRECTED.value
    )


def _changed_fields(prior, projection):
    if prior is None:
        return sorted(projection)
    return sorted(
        key for key, value in projection.items() if getattr(prior, key) != value
    )


def _game_context_changed(prior, projection):
    return any(getattr(prior, key) != value for key, value in projection.items())


def _boxscore_complete(game, boxscore, lines):
    if classify_game_finality(game, boxscore=boxscore, require_boxscore=True).state != FINAL_AND_USABLE:
        return False
    sides = {line.get('side') for line in lines if line.get('stats')}
    return bool(lines) and sides == {'home', 'away'}


def _pbp_complete(all_plays, lines):
    """Require nonempty PBP with every official boxscore pitcher represented."""
    if not isinstance(all_plays, list) or not all_plays:
        return False
    expected = {_int(line.get('player_id')) for line in lines}
    expected.discard(None)
    observed = {
        _int((((play or {}).get('matchup') or {}).get('pitcher') or {}).get('id'))
        for play in all_plays
    }
    observed.discard(None)
    return bool(expected) and expected <= observed


def _process_final_pbp(bundle, baseball_date, sync_run_id):
    authoritative = bool(
        bundle.play_by_play_completeness == ObservationCompleteness.COMPLETE.value
        and bundle.play_by_play is not None
    )
    return process_final_play_by_play_foundation(
        bundle.game,
        boxscore=bundle.boxscore,
        play_by_play=bundle.play_by_play if authoritative else None,
        play_by_play_error=(
            None if authoritative
            else RuntimeError('final play-by-play unavailable or incomplete')
        ),
        game_date=baseball_date,
        sync_run_id=sync_run_id,
        job_name=JobType.RECONCILE_FINAL_GAME.value,
        observation_sequence=(
            bundle.play_by_play_observation.version_number
            if bundle.play_by_play_observation is not None else None
        ),
    )


def _unchanged_result(latest_game, game_pk, *, pbp_result=None):
    result = pbp_result or {'processing_status': _pbp_marker_status(game_pk)}
    return FinalReconciliationResult(
        latest_game, (), (), False, (), (), (), (),
        {**result, 'unchanged': True},
    )


def _pbp_marker_status(game_pk):
    marker = PlayByPlayProcessedGame.query.filter_by(mlb_game_pk=game_pk).one_or_none()
    return marker.processing_status if marker else None


def _record_fetch_failure(identity, exc, started, sync_run_id, sync_job_id):
    try:
        record_source_fetch_failure(
            identity=identity,
            error=exc,
            attempt_started_at=started,
            http_status=getattr(exc, 'status_code', None),
            sync_run_id=sync_run_id,
            sync_job_id=sync_job_id,
        )
    except Exception:
        logger.exception('Could not persist failed final-game source attempt')


def _lock_game(game_pk):
    if db.session.get_bind().dialect.name == 'postgresql':
        db.session.execute(
            text('SELECT pg_advisory_xact_lock(:key)'),
            {'key': 507000000000 + int(game_pk)},
        )


def _start_final_run(job, game_pk, baseball_date):
    parent_id = job.sync_run_id
    current = db.session.get(SyncRun, parent_id) if parent_id is not None else None
    if current is not None and current.run_type == RunType.FINAL_GAME_RECONCILIATION.value and current.status not in {'success', 'partial', 'failed', 'cancelled'}:
        return start_run(current)
    run = create_run(
        run_type=RunType.FINAL_GAME_RECONCILIATION,
        trigger_type=TriggerType.GAME_FINAL,
        source='final_game_reconciliation',
        job_name=JobType.RECONCILE_FINAL_GAME.value,
        baseball_date=baseball_date,
        source_domain=SourceDomain.BOXSCORE,
        parent_sync_run_id=parent_id,
        scopes=[(ScopeType.GAME, game_pk)],
        commit=False,
    )
    job.sync_run_id = run.id
    db.session.commit()
    return start_run(run)


def _fingerprint(value):
    return hashlib.sha256(stable_json_dumps(value).encode('utf-8')).hexdigest()


def _date(value):
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _positive_int(value):
    parsed = _int(value)
    if parsed is None or parsed <= 0:
        raise ValueError('positive integer required')
    return parsed
