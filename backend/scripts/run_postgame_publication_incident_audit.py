#!/usr/bin/env python
"""Read-only postgame publication incident audit for run 30873422601.

    python scripts/run_postgame_publication_incident_audit.py \
        --expected-head-sha <40 hex> \
        --confirmation AUDIT_POSTGAME_PUBLICATION_INCIDENT_30873422601 \
        --evidence-dir incident-evidence \
        --artifact-dir ../artifacts/postgame-publication-incident-audit

Manual only, exact scope, read-only. Reconstructs the failed postgame
publication cycle for slate 2026-08-03 and answers eight explicit questions
about it from production evidence plus the run's own uploaded artifacts.

It calls the canonical authorities — schedule finality, the planner, the
appearance ledger, game-ingestion completeness, the snapshot service, the
publication proof — and never reimplements them. Identifying a root cause is
information. It repairs nothing and authorizes nothing.

Exit codes: 0 COMPLETE (root cause identified / no platform defect proven /
incident not reproducible), 1 FAILED, 2 UNPROVEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import postgame_publication_incident_audit as audit  # noqa: E402
from services import noop_write_qualification as qualification  # noqa: E402


SUMMARY_JSON = 'incident-audit-summary.json'
SUMMARY_MARKDOWN = 'incident-audit-summary.md'
METADATA_JSON = 'incident-audit-metadata.json'

REQUIRED_REPOSITORY = qualification.REQUIRED_REPOSITORY
REQUIRED_REF = qualification.REQUIRED_REF
REQUIRED_EVENT_NAME = qualification.REQUIRED_EVENT_NAME
REQUIRED_ACTOR = qualification.REQUIRED_ACTOR


class _AuditHalt(Exception):
    """Stop collecting; the verdict is decided from what was proven."""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only postgame publication incident audit.',
    )
    parser.add_argument('--expected-head-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument(
        '--evidence-dir',
        default='incident-evidence',
        help=(
            'Directory holding the downloaded incident artifacts, one '
            'subdirectory per artifact name.'
        ),
    )
    parser.add_argument(
        '--artifact-dir',
        default='artifacts/postgame-publication-incident-audit',
    )
    parser.add_argument('--operator-note', default='')
    return parser.parse_args(argv)


def event_context(args, environ=None) -> dict:
    env = environ if environ is not None else os.environ
    return {
        'event_name': env.get('GITHUB_EVENT_NAME'),
        'repository': env.get('GITHUB_REPOSITORY'),
        'actor': env.get('GITHUB_ACTOR'),
        'ref': env.get('GITHUB_REF'),
        'github_sha': env.get('GITHUB_SHA'),
        'run_id': env.get('GITHUB_RUN_ID'),
        'run_attempt': env.get('GITHUB_RUN_ATTEMPT'),
        'workflow': env.get('GITHUB_WORKFLOW'),
        'expected_head_sha': args.expected_head_sha,
        'confirmation': args.confirmation,
    }


def validate_authorization(context) -> list[str]:
    """Every gate re-validated here; the workflow's gates are not trusted."""
    failures: list[str] = []
    if str(context.get('event_name') or '') != REQUIRED_EVENT_NAME:
        failures.append('event_not_workflow_dispatch')
    if str(context.get('repository') or '') != REQUIRED_REPOSITORY:
        failures.append('repository_not_authorized')
    if str(context.get('actor') or '') != REQUIRED_ACTOR:
        failures.append('actor_not_authorized')
    if str(context.get('ref') or '') != REQUIRED_REF:
        failures.append('ref_not_main')

    expected = qualification.normalize_sha(context.get('expected_head_sha'))
    actual = qualification.normalize_sha(context.get('github_sha'))
    if not qualification._SHA_PATTERN.match(expected):
        failures.append('expected_head_sha_malformed')
    elif not qualification._SHA_PATTERN.match(actual) or expected != actual:
        failures.append('expected_head_sha_mismatch')

    if str(context.get('confirmation') or '') != audit.CONFIRMATION:
        failures.append('confirmation_mismatch')
    return failures


def build_app():
    import app as app_module

    return app_module.create_app()


# ── Observations ────────────────────────────────────────────────────────────
# Every function here READS. None of them writes, commits, or mutates. Each
# delegates classification to the canonical authority that owns it.

def observe_stored_schedule(game_pk) -> dict:
    """Stored schedule rows for the incident game (Question 2)."""
    from models.scheduled_game import ScheduledGame
    from services import game_finality

    rows = (
        ScheduledGame.query
        .filter(ScheduledGame.game_pk == game_pk)
        .order_by(ScheduledGame.team_id.asc())
        .all()
    )
    stored = [
        {
            'team_id': row.team_id,
            'game_date': _iso(row.game_date),
            'status_code': row.status_code,
            'status_state': row.status_state,
            'game_type': row.game_type,
            'original_product_date': _iso(row.original_product_date),
            'resumed_from_game_pk': row.resumed_from_game_pk,
            'resumed_to_game_pk': row.resumed_to_game_pk,
            'source': row.source,
        }
        for row in rows
    ]
    states = sorted({row.status_state for row in rows})
    return {
        'row_count': len(rows),
        'rows': stored,
        'distinct_status_states': states,
        'rows_agree': len(states) <= 1,
        'stored_status_state': states[0] if len(states) == 1 else None,
        'counts_as_ledger_final': (
            game_finality.FINAL_STATUS_STATE in states
        ),
        'unresolved_resumed_linkage': (
            game_finality.scheduled_rows_have_unresolved_resumed_linkage(rows)
        ),
    }


def observe_official_status(game_pk, stored, budget) -> dict:
    """Live MLB status for the incident game (Questions 1 and 3).

    Bounded by the source-call budget: a refused call is reported as
    unobserved, never as an absent status.
    """
    from services import game_finality
    from services.mlb_api import mlb_client

    slate = audit.INCIDENT_SLATE_DATE.isoformat()
    stored_dates = sorted({
        row['game_date'] for row in stored.get('rows') or []
        if row.get('game_date')
    })

    observation = {
        'slate_date_queried': slate,
        'exact_game_dates_queried': [],
        'game_found_in_source': False,
        'raw_status_code': None,
        'raw_detailed_state': None,
        'raw_abstract_state': None,
        'finality_state': None,
        'finality_reason': None,
        'mapped_status_state': None,
        'boxscore_observed': False,
        'boxscore_usable': None,
        'boxscore_reason': None,
        'source_calls_refused': False,
        'source_error': False,
    }

    game = _fetch_game_from_schedule(
        mlb_client, budget, audit.CALL_KIND_SCHEDULE, slate, slate,
        game_pk, observation,
    )
    for stored_date in stored_dates:
        if game is not None or stored_date == slate:
            continue
        observation['exact_game_dates_queried'].append(stored_date)
        game = _fetch_game_from_schedule(
            mlb_client, budget, audit.CALL_KIND_EXACT_GAME,
            stored_date, stored_date, game_pk, observation,
        )

    if game is None:
        return observation

    observation['game_found_in_source'] = True
    status = game.get('status') or {}
    observation['raw_status_code'] = _safe_text(status.get('statusCode'))
    observation['raw_detailed_state'] = _safe_text(status.get('detailedState'))
    observation['raw_abstract_state'] = _safe_text(
        status.get('abstractGameState')
    )

    # The canonical authority decides. This audit only records what it said.
    decision = game_finality.classify_status(status, game_pk=game_pk)
    observation['finality_state'] = decision.state
    observation['finality_reason'] = decision.reason
    observation['mapped_status_state'] = (
        game_finality.normalize_schedule_status_state(game)
    )
    observation['final_status'] = decision.final_status

    if budget.reserve(audit.CALL_KIND_BOXSCORE):
        try:
            boxscore = mlb_client.get_game_boxscore(game_pk)
        except Exception:  # noqa: BLE001 - never leak the source message
            budget.record_error(audit.CALL_KIND_BOXSCORE)
            observation['source_error'] = True
        else:
            observation['boxscore_observed'] = boxscore is not None
            usability = game_finality.classify_boxscore_usability(boxscore)
            observation['boxscore_usable'] = usability.is_final_and_usable
            observation['boxscore_reason'] = usability.reason
    else:
        observation['source_calls_refused'] = True
    return observation


def _fetch_game_from_schedule(
    client, budget, kind, start_date, end_date, game_pk, observation,
):
    if not budget.reserve(kind):
        observation['source_calls_refused'] = True
        return None
    try:
        games = client.get_schedule(start_date=start_date, end_date=end_date)
    except Exception:  # noqa: BLE001 - never leak the source message
        budget.record_error(kind)
        observation['source_error'] = True
        return None
    for game in games or ():
        try:
            found = int(game.get('gamePk'))
        except (TypeError, ValueError):
            continue
        if found == int(game_pk):
            return game
    return None


def observe_baseball_state(game_pk) -> dict:
    """Exact stored baseball state for the incident game (Question 5)."""
    from sqlalchemy import func

    from models.completed_game_context import CompletedGameContext
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from models.play_by_play_foundation import GamePlayByPlayEvent
    from models.postgame_processed_game import PostgameProcessedGame
    from models.team_game_pitching_split import TeamGamePitchingSplit
    from utils.db import db

    appearance_rows = (
        db.session.query(func.count(GameLog.id))
        .filter(GameLog.mlb_game_pk == game_pk)
        .scalar()
    )
    pitcher_ids = sorted({
        mlb_id
        for (mlb_id,) in (
            db.session.query(Pitcher.mlb_id)
            .join(GameLog, GameLog.pitcher_id == Pitcher.id)
            .filter(GameLog.mlb_game_pk == game_pk)
            .all()
        )
        if mlb_id is not None
    })
    # D-008: recorded outs are the innings authority. The decimal companion is
    # never inspected here, and a decimal display difference is never a repair.
    recorded_outs = (
        db.session.query(func.sum(GameLog.innings_pitched_outs))
        .filter(GameLog.mlb_game_pk == game_pk)
        .scalar()
    )

    marker = (
        PostgameProcessedGame.query
        .filter(PostgameProcessedGame.mlb_game_pk == game_pk)
        .first()
    )
    work_item = (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.mlb_game_pk == game_pk)
        .first()
    )
    team_splits = (
        db.session.query(func.count(TeamGamePitchingSplit.id))
        .filter(TeamGamePitchingSplit.mlb_game_pk == game_pk)
        .scalar()
    )
    contexts = (
        db.session.query(func.count(CompletedGameContext.id))
        .filter(CompletedGameContext.game_pk == game_pk)
        .scalar()
    )
    play_events = (
        db.session.query(func.count(GamePlayByPlayEvent.id))
        .filter(GamePlayByPlayEvent.mlb_game_pk == game_pk)
        .scalar()
    )

    return {
        'appearance_row_count': int(appearance_rows or 0),
        'distinct_pitcher_mlb_ids': pitcher_ids,
        'recorded_outs_total': (
            int(recorded_outs) if recorded_outs is not None else None
        ),
        'innings_semantics_note': (
            'innings_pitched_outs is the integer semantic authority; the '
            'decimal companion is derived and is never inspected as a '
            'baseball fact here.'
        ),
        'postgame_marker': None if marker is None else {
            'processing_status': marker.processing_status,
            'pitching_lines_seen': int(marker.pitching_lines_seen or 0),
            'logs_added': int(marker.logs_added or 0),
            'pitchers_touched': int(marker.pitchers_touched or 0),
            'pitcher_resolution_failures': int(
                marker.pitcher_resolution_failures or 0
            ),
            'attempt_count': int(marker.attempt_count or 0),
            'incomplete_reason': marker.incomplete_reason,
            'final_state': marker.final_state,
            'game_date': _iso(marker.game_date),
        },
        'work_item': None if work_item is None else {
            'status': work_item.status,
            'criticality': work_item.criticality,
            'candidate_reason': work_item.candidate_reason,
            'finality_state': work_item.finality_state,
            'represented_date': _iso(work_item.represented_date),
            'attempt_count': int(work_item.attempt_count or 0),
            'rows_expected': work_item.rows_expected,
            'rows_reconciled': int(work_item.rows_reconciled or 0),
            'error_class': work_item.error_class,
            'source_revision_present': bool(work_item.source_revision),
        },
        'team_pitching_split_rows': int(team_splits or 0),
        'completed_game_context_rows': int(contexts or 0),
        'play_by_play_event_rows': int(play_events or 0),
    }


def observe_appearance_ledger(game_pk, stored_schedule=None) -> dict:
    """The canonical appearance ledger for the incident slate (Question 4)."""
    from services import appearance_ledger

    ledger = appearance_ledger.build_appearance_ledger(
        end_date=audit.INCIDENT_SLATE_DATE,
    )
    missing = {entry['game_pk'] for entry in ledger['missing_games']}
    deficits = {entry['game_pk'] for entry in ledger['count_deficit_games']}
    incomplete = {
        entry['game_pk'] for entry in ledger['incomplete_marker_games']
    }
    return {
        'gate_enabled': appearance_ledger.ledger_gate_enabled(),
        'window_start': ledger['window_start'],
        'window_end': ledger['window_end'],
        'window_days': ledger['window_days'],
        'expected_games': ledger['expected_games'],
        'represented_games': ledger['represented_games'],
        'expected_appearances': ledger['expected_appearances'],
        'stored_appearances': ledger['stored_appearances'],
        'complete': ledger['complete'],
        'reasons': list(ledger['reasons']),
        'missing_game_count': len(missing),
        'count_deficit_game_count': len(deficits),
        'incomplete_marker_game_count': len(incomplete),
        'deficit_game_pks': sorted(missing | deficits | incomplete),
        # Reported as the two separately derivable facts they are. Membership
        # itself belongs to services.appearance_ledger and is not recomputed
        # here: what this records is (a) that the ledger named the game in a
        # deficit list, and (b) whether the game satisfies the two published
        # membership conditions — a stored `final` row, inside the window.
        'incident_game_in_deficit_set': game_pk in (
            missing | deficits | incomplete
        ),
        'incident_game_has_stored_final_row': bool(
            (stored_schedule or {}).get('counts_as_ledger_final')
        ),
        'incident_game_within_window': _game_within_window(
            stored_schedule, ledger['window_start'], ledger['window_end'],
        ),
        'membership_rule': (
            'services.appearance_ledger counts a game when a stored '
            'scheduled_games row carries status_state=final inside the '
            'trailing window.'
        ),
    }


def _game_within_window(stored_schedule, window_start, window_end):
    """True when any stored schedule row's date falls inside the window."""
    dates = [
        row.get('game_date') for row in (stored_schedule or {}).get('rows') or ()
        if row.get('game_date')
    ]
    if not dates:
        return None
    return any(window_start <= value <= window_end for value in dates)


def observe_completeness(game_pk) -> dict:
    """Canonical planner + completeness proof (Questions 4 and 7)."""
    from models.game_ingestion_work_item import GameIngestionWorkItem
    from services import game_ingestion_completeness, game_ingestion_planner

    plan = game_ingestion_planner.plan_game_work(audit.INCIDENT_SLATE_DATE)
    completeness = game_ingestion_completeness.build_game_ingestion_completeness(
        audit.INCIDENT_SLATE_DATE, plan=plan,
    )

    excluded_reason_for_game = None
    for reason, game_pks in (plan.get('excluded_game_pks') or {}).items():
        if game_pk in set(game_pks or ()):
            excluded_reason_for_game = reason
            break

    attribution = _attribute_unresolved_games(plan, completeness)

    return {
        'plan': {
            'reference_date': plan['reference_date'],
            'window_start': plan['window_start'],
            'games_discovered': plan['games_discovered'],
            'games_planned': plan['games_planned'],
            'excluded_counts': dict(plan['excluded_counts']),
            'finality_conflicts': list(plan['finality_conflicts']),
            'schedule_authority_missing': list(
                plan['schedule_authority_missing']
            ),
            'incident_game_planned': game_pk in set(plan['planned_game_pks']),
            'incident_game_exclusion_reason': excluded_reason_for_game,
        },
        'completeness': {
            'represented_date': completeness['represented_date'],
            'window_start': completeness['window_start'],
            'horizon_days': completeness['horizon_days'],
            'expected_final_games': completeness['expected_final_games'],
            'completed_final_games': completeness['completed_final_games'],
            'unresolved_final_games': completeness['unresolved_final_games'],
            'terminal_failure_games': completeness['terminal_failure_games'],
            'correction_pending_games': completeness['correction_pending_games'],
            'critical_appearance_rows_expected': completeness[
                'critical_appearance_rows_expected'
            ],
            'critical_appearance_rows_reconciled': completeness[
                'critical_appearance_rows_reconciled'
            ],
            'publication_complete': completeness['publication_complete'],
            'decision_reasons': list(completeness['decision_reasons']),
        },
        'unresolved_attribution': attribution,
        'work_item_status_vocabulary': list(
            GameIngestionWorkItem.UNRESOLVED_STATUSES
        ),
    }


def _attribute_unresolved_games(plan, completeness) -> dict:
    """Classify each game the canonical completeness proof left unresolved.

    The COUNT belongs to ``services.game_ingestion_completeness``. This only
    attributes the games behind it, then checks its own reconstruction against
    that authority's number. A reconstruction that does not match is reported
    as not reconciled — it never overrides the authority.
    """
    from models.game_ingestion_work_item import GameIngestionWorkItem

    horizon = int(completeness['horizon_days'])
    from datetime import timedelta

    window_start = audit.INCIDENT_SLATE_DATE - timedelta(days=horizon)
    work_items = (
        GameIngestionWorkItem.query
        .filter(GameIngestionWorkItem.represented_date >= window_start)
        .filter(GameIngestionWorkItem.represented_date
                <= audit.INCIDENT_SLATE_DATE)
        .all()
    )
    by_game = {item.mlb_game_pk: item for item in work_items}

    critical_planned = {
        item.game_pk for item in (plan.get('items') or [])
        if item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
        and item.candidate_reason != GameIngestionWorkItem.REASON_CORRECTED_FINAL
    }
    unresolved_items = {
        item.mlb_game_pk for item in work_items
        if item.status in GameIngestionWorkItem.UNRESOLVED_STATUSES
        and item.criticality != GameIngestionWorkItem.CRITICALITY_BEST_EFFORT
    }
    schedule_missing = set(plan.get('schedule_authority_missing') or ())

    game_pks = sorted(critical_planned | unresolved_items)
    classified: list[dict] = []
    counts: dict[str, int] = {}
    for game_pk in game_pks:
        item = by_game.get(game_pk)
        if game_pk in schedule_missing:
            bucket = audit.UNRESOLVED_SCHEDULE_AUTHORITY_MISSING
        elif item is None:
            bucket = audit.UNRESOLVED_PLANNED_NEVER_ATTEMPTED
        elif (item.error_class or '') == 'correction_conflict':
            bucket = audit.UNRESOLVED_CORRECTION_CONFLICT
        elif item.status == GameIngestionWorkItem.STATUS_TERMINAL_FAILURE:
            bucket = audit.UNRESOLVED_TERMINAL_FAILURE
        elif item.status == GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE:
            bucket = audit.UNRESOLVED_RETRYABLE_FAILURE
        elif item.status == GameIngestionWorkItem.STATUS_IN_PROGRESS:
            bucket = audit.UNRESOLVED_IN_PROGRESS
        elif item.status == GameIngestionWorkItem.STATUS_PLANNED:
            bucket = audit.UNRESOLVED_PLANNED_NEVER_ATTEMPTED
        else:
            bucket = audit.UNRESOLVED_UNATTRIBUTED
        counts[bucket] = counts.get(bucket, 0) + 1
        classified.append({
            'game_pk': game_pk,
            'classification': bucket,
            'work_item_status': None if item is None else item.status,
            'attempt_count': None if item is None else int(
                item.attempt_count or 0
            ),
            'error_class': None if item is None else item.error_class,
        })

    authority_count = int(completeness['unresolved_final_games'])
    return {
        'attributed_game_count': len(classified),
        'authority_unresolved_final_games': authority_count,
        'reconciles_with_authority': len(classified) == authority_count,
        'classification_counts': counts,
        'unattributed_count': counts.get(audit.UNRESOLVED_UNATTRIBUTED, 0),
        'games': classified[:audit.MAX_REPORTED_UNRESOLVED_GAMES],
        'games_truncated': (
            len(classified) > audit.MAX_REPORTED_UNRESOLVED_GAMES
        ),
        'incident_reported_count': (
            audit.INCIDENT_REPORTED_UNRESOLVED_FINAL_GAMES
        ),
    }


def attribute_player_mismatches(ledger_report, ledger_observation) -> dict:
    """Attribute every reported player mismatch individually (Question 6).

    Each entry gets exactly one classification. A mismatch this audit cannot
    place is ``unattributed`` — which leaves the question unanswered rather
    than quietly reporting a clean attribution.
    """
    from models.game_log import GameLog
    from models.pitcher import Pitcher
    from utils.db import db

    report = ledger_report if isinstance(ledger_report, dict) else {}
    entries = list(report.get('player_mismatches') or [])
    deficit_games = set(ledger_observation.get('deficit_game_pks') or ())
    report_games = set(
        (report.get('missing_game_pks') or [])
        + (report.get('count_deficit_game_pks') or [])
        + (report.get('incomplete_marker_game_pks') or [])
    )
    candidate_games = sorted(report_games or deficit_games)

    attributed: list[dict] = []
    counts: dict[str, int] = {}
    for entry in entries:
        player_id = entry.get('player_id')
        pitcher = (
            Pitcher.query.filter_by(mlb_id=player_id).first()
            if player_id is not None else None
        )
        stored_games: list[int] = []
        if pitcher is not None and candidate_games:
            stored_games = sorted({
                game_pk
                for (game_pk,) in (
                    db.session.query(GameLog.mlb_game_pk)
                    .filter(GameLog.pitcher_id == pitcher.id)
                    .filter(GameLog.mlb_game_pk.in_(candidate_games))
                    .all()
                )
                if game_pk is not None
            })

        if pitcher is None:
            bucket = audit.MISMATCH_PITCHER_IDENTITY_UNTRACKED
        elif stored_games:
            bucket = audit.MISMATCH_APPEARANCE_ROW_NOW_PRESENT
        elif not candidate_games:
            bucket = audit.MISMATCH_GAME_NOT_IN_LEDGER_WINDOW
        elif deficit_games:
            bucket = audit.MISMATCH_NO_APPEARANCE_ROW
        else:
            # The report named deficit games that the current ledger window no
            # longer contains, so the mismatch is placed but no longer inside
            # the gate's scope.
            bucket = audit.MISMATCH_GAME_NOT_IN_LEDGER_WINDOW
        counts[bucket] = counts.get(bucket, 0) + 1
        attributed.append({
            'player_id': player_id,
            'latest_stored_appearance': entry.get('latest_stored_appearance'),
            'pitcher_tracked': pitcher is not None,
            'classification': bucket,
            'candidate_games_checked': len(candidate_games),
            'games_with_stored_appearance': stored_games,
        })

    return {
        'reported_mismatch_count': len(entries),
        'incident_reported_mismatch_count': (
            audit.INCIDENT_REPORTED_PLAYER_MISMATCHES
        ),
        'attributed_count': len(attributed),
        'unattributed_count': counts.get(audit.MISMATCH_UNATTRIBUTED, 0),
        'classification_counts': counts,
        'candidate_games_checked': candidate_games,
        'mismatches': attributed,
        'all_attributed': (
            bool(attributed)
            and counts.get(audit.MISMATCH_UNATTRIBUTED, 0) == 0
        ),
        'player_names_withheld': True,
    }


def observe_snapshot_gate(sync_summary) -> dict:
    """Snapshot 344 / 343 / sync run 596 (Question 8)."""
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from services import dashboard_snapshot as snapshot_service
    from utils.db import db

    candidate = db.session.get(
        DashboardSnapshot, audit.INCIDENT_CANDIDATE_SNAPSHOT_ID
    )
    prior = db.session.get(
        DashboardSnapshot, audit.INCIDENT_SERVING_SNAPSHOT_ID
    )
    served = snapshot_service.get_latest_valid_dashboard_snapshot()
    sync_run = db.session.get(SyncRun, audit.INCIDENT_SYNC_RUN_ID)

    artifact_proof = (
        (sync_summary or {}).get('publication_proof')
        if isinstance(sync_summary, dict) else None
    )
    artifact_proof = artifact_proof if isinstance(artifact_proof, dict) else {}

    return {
        'candidate_snapshot': _snapshot_view(candidate, snapshot_service),
        'prior_snapshot': _snapshot_view(prior, snapshot_service),
        'currently_served_snapshot_id': getattr(served, 'id', None),
        'sync_run': None if sync_run is None else {
            'id': sync_run.id,
            'job_name': getattr(sync_run, 'job_name', None),
            'status': getattr(sync_run, 'status', None),
            'stage': getattr(sync_run, 'stage', None),
            'published_dashboard_snapshot_id': getattr(
                sync_run, 'published_dashboard_snapshot_id', None
            ),
        },
        'publication_proof_from_incident_artifact': {
            'status': artifact_proof.get('status'),
            'verified': artifact_proof.get('verified'),
            'league_publication_status': artifact_proof.get(
                'league_publication_status'
            ),
            'candidate_required': artifact_proof.get('candidate_required'),
            'candidate_snapshot_id': artifact_proof.get(
                'candidate_snapshot_id'
            ),
            'served_snapshot_id': artifact_proof.get('served_snapshot_id'),
            'reason_codes': list(artifact_proof.get('reason_codes') or ()),
        },
        'gate_owner': (
            'services.dashboard_snapshot.publish_dashboard_snapshot decides '
            'publication; services.sync_publication_proof decides whether the '
            "run's candidate is serving. Neither is reimplemented here."
        ),
    }


def _snapshot_view(snapshot, snapshot_service) -> dict | None:
    if snapshot is None:
        return None
    return {
        'id': snapshot.id,
        'status': snapshot.status,
        'is_published': bool(getattr(snapshot, 'is_published', False)),
        'published_at': _iso(getattr(snapshot, 'published_at', None)),
        'data_through': _iso(getattr(snapshot, 'data_through', None)),
        'sync_run_id': getattr(snapshot, 'sync_run_id', None),
        'error_message': getattr(snapshot, 'error_message', None),
        'unavailable_reason': snapshot_service.snapshot_unavailable_reason(
            snapshot
        ),
    }


def observe_unresolved_sync_failures() -> dict:
    """Observed dead-letter backlog. Reported, never asserted as zero."""
    from sqlalchemy import func

    from models.sync_failure import SyncFailure
    from utils.db import db

    try:
        total = (
            db.session.query(func.count(SyncFailure.id))
            .filter(SyncFailure.resolved.is_(False))
            .scalar()
        )
    except Exception:  # noqa: BLE001 - an unobserved backlog is not zero
        return {'observed': False, 'unresolved_sync_failures': None}
    return {
        'observed': True,
        'unresolved_sync_failures': int(total or 0),
        'note': (
            'Observed count at audit time. This audit never asserts the '
            'dead-letter backlog is zero and resolves nothing.'
        ),
    }


# ── Questions ───────────────────────────────────────────────────────────────

def build_questions(observations) -> list[dict]:
    """Turn observations into eight explicit, individually answerable records."""
    stored = observations.get('stored_schedule') or {}
    official = observations.get('official_status') or {}
    baseball = observations.get('baseball_state') or {}
    ledger = observations.get('appearance_ledger') or {}
    completeness = observations.get('completeness') or {}
    mismatches = observations.get('player_mismatches') or {}
    snapshot = observations.get('snapshot_gate') or {}

    questions: list[dict] = []

    questions.append(_question(
        audit.QUESTION_OFFICIAL_STATUS,
        answered=bool(official.get('game_found_in_source')),
        answer=(
            f"MLB reports status_code={official.get('raw_status_code')!r}, "
            f"detailed_state={official.get('raw_detailed_state')!r}; the "
            f"canonical finality authority classifies it "
            f"{official.get('finality_state')!r} "
            f"(reason {official.get('finality_reason')!r})."
            if official.get('game_found_in_source')
            else 'The official record was not observed within the source-call '
                 'budget, so the official status is unproven.'
        ),
        evidence={
            'source': official,
            'authority': 'services.game_finality.classify_status',
        },
        unproven_reason=(
            None if official.get('game_found_in_source')
            else 'official_record_not_observed'
        ),
    ))

    questions.append(_question(
        audit.QUESTION_STORED_SCHEDULE_STATE,
        answered=int(stored.get('row_count') or 0) > 0,
        answer=(
            f"{stored.get('row_count')} stored schedule row(s) carry "
            f"status_state(s) {stored.get('distinct_status_states')}; the rows "
            f"{'agree' if stored.get('rows_agree') else 'DISAGREE'}."
        ),
        evidence={'stored_schedule': stored},
        unproven_reason=(
            None if int(stored.get('row_count') or 0) > 0
            else 'no_stored_schedule_rows'
        ),
    ))

    preflight_answered = official.get('mapped_status_state') is not None
    questions.append(_question(
        audit.QUESTION_PREFLIGHT_PRODUCED_OTHER,
        answered=preflight_answered,
        answer=(
            f"The preflight stores whatever "
            f"game_finality.normalize_schedule_status_state returns. For the "
            f"observed status that is "
            f"{official.get('mapped_status_state')!r}, because "
            f"classify_status resolved {official.get('finality_reason')!r}. "
            f"'other' is the state the authority uses for cancelled, "
            f"live/in-progress, abstract-final-without-final-status, and "
            f"unknown status."
            if preflight_answered
            else 'The live status was not observed, so the mapping that '
                 'produced "other" cannot be reproduced.'
        ),
        evidence={
            'mapped_status_state': official.get('mapped_status_state'),
            'finality_reason': official.get('finality_reason'),
            'stored_status_states': stored.get('distinct_status_states'),
            'authority': (
                'services.game_finality.normalize_schedule_status_state'
            ),
        },
        unproven_reason=(
            None if preflight_answered else 'live_status_not_observed'
        ),
    ))

    ledger_answered = bool(ledger)
    questions.append(_question(
        audit.QUESTION_LEDGER_COUNTED_COMPLETED,
        answered=ledger_answered,
        answer=(
            'The appearance ledger counts a game from the STORED schedule '
            'ledger: any scheduled_games row with status_state=final inside '
            'the trailing window is an expected completed game. The planner '
            'instead requires every row of the game to agree on final. Those '
            'two membership rules are not the same test, so a game can be '
            'inside ledger membership and outside planning scope at the same '
            'time. Stored states observed for the incident game: '
            f"{stored.get('distinct_status_states')}; ledger reasons: "
            f"{ledger.get('reasons')}."
            if ledger_answered
            else 'The appearance ledger could not be computed.'
        ),
        evidence={
            'appearance_ledger': ledger,
            'planner': (completeness.get('plan') or {}),
            'authority': 'services.appearance_ledger.build_appearance_ledger',
        },
        unproven_reason=(
            None if ledger_answered else 'appearance_ledger_unavailable'
        ),
    ))

    questions.append(_question(
        audit.QUESTION_EXACT_BASEBALL_STATE,
        answered=bool(baseball),
        answer=(
            f"{baseball.get('appearance_row_count')} appearance row(s), "
            f"{len(baseball.get('distinct_pitcher_mlb_ids') or ())} distinct "
            f"pitcher identities, "
            f"{baseball.get('team_pitching_split_rows')} team split row(s), "
            f"{baseball.get('completed_game_context_rows')} completed-game "
            f"context row(s), "
            f"{baseball.get('play_by_play_event_rows')} play-by-play row(s); "
            f"postgame marker "
            f"{(baseball.get('postgame_marker') or {}).get('processing_status')}"
            f", work item "
            f"{(baseball.get('work_item') or {}).get('status')}."
            if baseball else 'Stored baseball state could not be read.'
        ),
        evidence={'baseball_state': baseball},
        unproven_reason=None if baseball else 'baseball_state_unavailable',
    ))

    questions.append(_question(
        audit.QUESTION_PLAYER_MISMATCH_ATTRIBUTION,
        answered=bool(mismatches.get('all_attributed')),
        answer=(
            f"{mismatches.get('attributed_count')} of "
            f"{mismatches.get('reported_mismatch_count')} reported mismatches "
            f"attributed individually: "
            f"{mismatches.get('classification_counts')}."
            if mismatches.get('all_attributed')
            else 'At least one reported mismatch could not be attributed '
                 'individually, so the attribution is incomplete.'
        ),
        evidence={'player_mismatches': mismatches},
        unproven_reason=(
            None if mismatches.get('all_attributed')
            else 'player_mismatch_attribution_incomplete'
        ),
    ))

    attribution = completeness.get('unresolved_attribution') or {}
    questions.append(_question(
        audit.QUESTION_UNRESOLVED_GAME_CLASSIFICATION,
        answered=bool(
            attribution.get('reconciles_with_authority')
            and attribution.get('unattributed_count') == 0
        ),
        answer=(
            f"{attribution.get('attributed_game_count')} unresolved final "
            f"game(s) classified as "
            f"{attribution.get('classification_counts')}, reconciling with "
            f"the completeness authority's count of "
            f"{attribution.get('authority_unresolved_final_games')}."
            if attribution.get('reconciles_with_authority')
            and attribution.get('unattributed_count') == 0
            else 'The per-game reconstruction did not reconcile with the '
                 "completeness authority's count, or left games "
                 'unattributed, so the classification is incomplete.'
        ),
        evidence={
            'unresolved_attribution': attribution,
            'completeness': completeness.get('completeness'),
            'authority': (
                'services.game_ingestion_completeness.'
                'build_game_ingestion_completeness'
            ),
        },
        unproven_reason=(
            None if attribution.get('reconciles_with_authority')
            and attribution.get('unattributed_count') == 0
            else 'unresolved_game_classification_incomplete'
        ),
    ))

    candidate = snapshot.get('candidate_snapshot')
    questions.append(_question(
        audit.QUESTION_SNAPSHOT_GATE,
        answered=bool(snapshot),
        answer=(
            f"Snapshot {audit.INCIDENT_CANDIDATE_SNAPSHOT_ID} is "
            f"{(candidate or {}).get('status')} "
            f"(published={(candidate or {}).get('is_published')}, "
            f"reason={(candidate or {}).get('unavailable_reason')!r}); the "
            f"snapshot currently selected for serving is "
            f"{snapshot.get('currently_served_snapshot_id')}. The incident "
            f"artifact's publication proof recorded "
            f"{(snapshot.get('publication_proof_from_incident_artifact') or {}).get('reason_codes')}."
            if snapshot else 'The snapshot gate state could not be read.'
        ),
        evidence={'snapshot_gate': snapshot},
        unproven_reason=None if snapshot else 'snapshot_state_unavailable',
    ))

    return questions


def _question(question_id, *, answered, answer, evidence, unproven_reason):
    return {
        'question_id': question_id,
        'question': audit.QUESTION_TEXT[question_id],
        'answered': bool(answered),
        'answer': answer,
        'evidence': evidence,
        'unproven_reason': unproven_reason,
    }


# ── Classification ──────────────────────────────────────────────────────────

def classify(observations) -> list[str]:
    """Name every condition the canonical authorities actually reported."""
    stored = observations.get('stored_schedule') or {}
    official = observations.get('official_status') or {}
    baseball = observations.get('baseball_state') or {}
    ledger = observations.get('appearance_ledger') or {}
    completeness = observations.get('completeness') or {}
    snapshot = observations.get('snapshot_gate') or {}

    found: list[str] = []

    if stored.get('row_count') and not stored.get('rows_agree'):
        found.append(audit.CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT)
    if (completeness.get('plan') or {}).get('finality_conflicts'):
        found.append(audit.CLASSIFICATION_SCHEDULE_ROW_FINALITY_CONFLICT)

    mapped = official.get('mapped_status_state')
    stored_state = stored.get('stored_status_state')
    if (
        official.get('game_found_in_source')
        and mapped is not None
        and stored_state is not None
        and mapped != stored_state
    ):
        found.append(
            audit.CLASSIFICATION_STORED_SCHEDULE_STATE_DIVERGES_FROM_SOURCE
        )

    # The defect the incident named: ledger membership counts the game while
    # the planner cannot plan it, so no lane can ever close the deficit.
    plan = completeness.get('plan') or {}
    if stored.get('counts_as_ledger_final') and not plan.get(
        'incident_game_planned'
    ):
        found.append(
            audit.CLASSIFICATION_LEDGER_MEMBERSHIP_DIVERGES_FROM_PLANNER
        )
    if mapped == 'other' and stored.get('counts_as_ledger_final'):
        found.append(
            audit.CLASSIFICATION_FINALITY_AUTHORITY_MAPS_GAME_OUT_OF_SCOPE
        )

    marker = baseball.get('postgame_marker')
    if stored.get('counts_as_ledger_final'):
        if marker is None:
            found.append(audit.CLASSIFICATION_POSTGAME_MARKER_MISSING)
        elif marker.get('processing_status') != 'fully_processed':
            found.append(audit.CLASSIFICATION_POSTGAME_MARKER_INCOMPLETE)
        if int(baseball.get('appearance_row_count') or 0) == 0:
            found.append(
                audit.CLASSIFICATION_APPEARANCE_ROWS_MISSING_FOR_FINAL_GAME
            )

    attribution = completeness.get('unresolved_attribution') or {}
    if int(attribution.get('authority_unresolved_final_games') or 0) > 0:
        found.append(audit.CLASSIFICATION_WORK_ITEM_BACKLOG_UNRESOLVED)

    candidate = snapshot.get('candidate_snapshot') or {}
    reason = candidate.get('error_message') or candidate.get(
        'unavailable_reason'
    )
    if reason and 'appearance_ledger' in str(reason):
        found.append(
            audit.CLASSIFICATION_SNAPSHOT_WITHHELD_BY_APPEARANCE_LEDGER_GATE
        )
    elif reason and 'slate_coverage' in str(reason):
        found.append(audit.CLASSIFICATION_SNAPSHOT_WITHHELD_BY_SLATE_COVERAGE)

    artifact_proof = snapshot.get(
        'publication_proof_from_incident_artifact'
    ) or {}
    served = snapshot.get('currently_served_snapshot_id')
    if artifact_proof.get('verified') is False or (
        candidate and served is not None
        and served != audit.INCIDENT_CANDIDATE_SNAPSHOT_ID
    ):
        found.append(
            audit.CLASSIFICATION_PUBLICATION_PROOF_CANDIDATE_NOT_SERVING
        )

    return found


# ── Orchestration ───────────────────────────────────────────────────────────

def run(args) -> dict:
    context = event_context(args)
    note = qualification.sanitize_note(args.operator_note)
    budget = audit.SourceCallBudget()

    failures = validate_authorization(context)
    if failures:
        return build_document(
            context=context, note=note, observations={}, questions=[],
            read_only={}, artifact_ingestion={}, budget_state=budget.state(),
            decision=_refuse(failed=failures),
        )

    ingestion = audit.ingest_incident_artifacts(args.evidence_dir)
    shadow = (ingestion.get('artifacts') or {}).get(audit.ARTIFACT_SHADOW) or {}
    ledger_artifact = (
        (ingestion.get('artifacts') or {}).get(audit.ARTIFACT_LEDGER_AUDIT)
        or {}
    )

    identity_failures = audit.validate_incident_scope(
        run_id=audit.INCIDENT_RUN_ID,
        cycle=audit.INCIDENT_CYCLE,
        slate_date=audit.INCIDENT_SLATE_DATE,
    )

    flask_app = build_app()

    from services import sync_metadata
    from utils.db import db

    observations: dict = {}
    collected: dict = {}
    with flask_app.app_context():
        guard_state = {
            'guard_acquired': False,
            'guard_release_attempted': False,
            'guard_released': False,
        }
        guard = None
        try:
            # Acquire-only guard: it takes the public sync advisory lock and
            # never creates, reclaims, or updates a SyncRun row.
            guard = sync_metadata.acquire_public_sync_read_lock(
                source=sync_metadata.SOURCE_GITHUB_ACTIONS,
            )
            guard_state['guard_acquired'] = guard is not None
        except Exception:  # noqa: BLE001 - a contended lock is UNPROVEN
            guard = None

        try:
            if not guard_state['guard_acquired']:
                raise _AuditHalt()

            try:
                read_only = audit.enforce_read_only(db.session)
            except audit.ReadOnlyProbeViolation as violation:
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = violation.evidence
                raise _AuditHalt()
            collected['read_only_enabled'] = True
            collected['read_only_detail'] = read_only

            before = audit.table_fingerprints(db.session)
            collected['before_fingerprints'] = before
            if before is None:
                raise _AuditHalt()

            game_pk = audit.INCIDENT_GAME_PK
            observations['stored_schedule'] = observe_stored_schedule(game_pk)
            observations['official_status'] = observe_official_status(
                game_pk, observations['stored_schedule'], budget,
            )
            observations['baseball_state'] = observe_baseball_state(game_pk)
            observations['appearance_ledger'] = observe_appearance_ledger(
                game_pk, observations['stored_schedule'],
            )
            observations['completeness'] = observe_completeness(game_pk)
            observations['player_mismatches'] = attribute_player_mismatches(
                ledger_artifact.get('ledger_report'),
                observations['appearance_ledger'],
            )
            observations['snapshot_gate'] = observe_snapshot_gate(
                shadow.get('sync_summary')
            )
            observations['dead_letter_backlog'] = (
                observe_unresolved_sync_failures()
            )

            collected['after_fingerprints'] = audit.table_fingerprints(
                db.session
            )
        except _AuditHalt:
            pass
        except Exception:  # noqa: BLE001 - never leak exception text
            collected['audit_error'] = True
        finally:
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            if guard is not None:
                guard_state['guard_release_attempted'] = True
                try:
                    guard.release()
                    guard_state['guard_released'] = True
                except Exception:  # noqa: BLE001
                    guard_state['guard_released'] = False

    read_only_proof = _read_only_proof(collected, guard_state)
    questions = build_questions(observations) if observations else []
    classifications = classify(observations) if observations else []

    extra_unproven = []
    if collected.get('audit_error'):
        extra_unproven.append(audit.UNPROVEN_AUDIT_EXECUTION_ERROR)

    decision = audit.decide(
        questions=questions,
        classifications=classifications,
        read_only_proof=read_only_proof,
        artifact_ingestion=ingestion,
        budget_state=budget.state(),
        identity_failures=identity_failures,
        extra_unproven=extra_unproven,
    )

    return build_document(
        context=context, note=note, observations=observations,
        questions=questions, read_only=read_only_proof,
        artifact_ingestion=ingestion, budget_state=budget.state(),
        decision=decision,
    )


def _read_only_proof(collected, guard_state) -> dict:
    detail = collected.get('read_only_detail') or {}
    before = collected.get('before_fingerprints')
    after = collected.get('after_fingerprints')
    return {
        'advisory_guard_acquired': guard_state['guard_acquired'],
        'advisory_guard_release_attempted': guard_state[
            'guard_release_attempted'
        ],
        'advisory_guard_released': guard_state['guard_released'],
        'transaction_read_only_enabled': bool(
            collected.get('read_only_enabled')
        ),
        'fingerprint_tables': list(audit.FINGERPRINT_TABLES),
        'before_fingerprints': before,
        'after_fingerprints': after,
        'fingerprints_match': audit.fingerprints_match(before, after),
        'changed_tables': audit.changed_tables(before, after),
        # One bounded, refused proof statement is attempted. Zero durable
        # writes are attempted. Different facts, different fields.
        **audit.probe_evidence(detail),
        'durable_rows_created': 0,
        'durable_rows_updated': 0,
        'durable_rows_deleted': 0,
        'commits_performed_by_audit': 0,
    }


def _refuse(*, failed=(), unproven=()) -> dict:
    result = (
        audit.RESULT_FAILED if failed
        else audit.RESULT_UNPROVEN
    )
    return {
        'result': result,
        'exit_code': audit.EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)) or (
            [] if failed else [audit.UNPROVEN_AUDIT_EXECUTION_ERROR]
        ),
        'unanswered_question_ids': list(audit.QUESTION_IDS),
        'questions_answered': 0,
        'questions_total': len(audit.QUESTION_IDS),
        'classifications': [],
        'primary_classification': None,
        'platform_defect_classifications': [],
        'platform_defect_proven': False,
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }


def build_document(*, context, note, observations, questions, read_only,
                   artifact_ingestion, budget_state, decision) -> dict:
    proof = read_only or {}
    ingestion = artifact_ingestion or {}
    artifacts = ingestion.get('artifacts') or {}
    return {
        'identity': {
            'schema_version': audit.SCHEMA_VERSION,
            'audit_type': audit.AUDIT_TYPE,
            'repository': context.get('repository'),
            'workflow_name': context.get('workflow'),
            'workflow_run_id': context.get('run_id'),
            'workflow_run_attempt': context.get('run_attempt'),
            'commit_sha': qualification.normalize_sha(
                context.get('github_sha')
            ),
            'ref': context.get('ref'),
            'actor': context.get('actor'),
            'event_name': context.get('event_name'),
            'executed_at': datetime.now(timezone.utc).isoformat(),
        },
        'incident': audit.incident_identity(),
        'request': {
            'confirmation_valid': 'confirmation_mismatch' not in (
                decision['failed_reasons']
            ),
            'expected_head_sha_valid': not (
                {'expected_head_sha_malformed', 'expected_head_sha_mismatch'}
                & set(decision['failed_reasons'])
            ),
            'operator_note': note,
        },
        'evidence_artifacts': {
            'expectations': ingestion.get('expectations'),
            'missing_required': ingestion.get('missing_required') or [],
            'unreadable_required': ingestion.get('unreadable_required') or [],
            'missing_optional': ingestion.get('missing_optional') or [],
            'all_required_present': ingestion.get('all_required_present'),
            'per_artifact': {
                name: {
                    'required': entry.get('required'),
                    'present': entry.get('present'),
                    'readable': entry.get('readable'),
                    'files': entry.get('files'),
                    'parse_error': entry.get('parse_error'),
                }
                for name, entry in artifacts.items()
            },
            'ledger_report': (
                (artifacts.get(audit.ARTIFACT_LEDGER_AUDIT) or {})
                .get('ledger_report')
            ),
        },
        'source_call_budget': budget_state,
        'read_only_proof': proof,
        'observations': observations,
        'questions': questions,
        'root_cause': {
            'classifications': decision['classifications'],
            'primary_classification': decision['primary_classification'],
            'platform_defect_classifications': decision[
                'platform_defect_classifications'
            ],
            'platform_defect_proven': decision['platform_defect_proven'],
            'classification_vocabulary': list(audit.CLASSIFICATION_PRECEDENCE),
        },
        'verdict': {
            'result': decision['result'],
            'exit_code': decision['exit_code'],
            'failed_reasons': decision['failed_reasons'],
            'unproven_reasons': decision['unproven_reasons'],
            'unanswered_question_ids': decision['unanswered_question_ids'],
            'questions_answered': decision['questions_answered'],
            'questions_total': decision['questions_total'],
            'explanation': audit.explanation(decision),
            'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
        },
    }


def render_markdown(document) -> str:
    identity = document['identity']
    incident = document['incident']
    verdict = document['verdict']
    proof = document['read_only_proof']
    budget = document['source_call_budget']
    evidence = document['evidence_artifacts']
    root_cause = document['root_cause']

    lines = [
        '# Postgame publication incident audit',
        '',
        f"**Result: {verdict['result']}**",
        '',
        verdict['explanation'],
        '',
        '## Incident',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| incident run | {incident['workflow_run_id']} |",
        f"| incident head | `{incident['head_sha']}` |",
        f"| cycle | {incident['cycle']} |",
        f"| slate | {incident['slate_date']} |",
        f"| game | {incident['game_pk']} |",
        f"| candidate snapshot | {incident['candidate_snapshot_id']} |",
        f"| serving snapshot | {incident['serving_snapshot_id']} |",
        f"| sync run | {incident['sync_run_id']} |",
        '',
        '## Audit identity',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| audit type | `{identity['audit_type']}` |",
        f"| schema version | {identity['schema_version']} |",
        f"| run | {identity.get('workflow_run_id')} "
        f"(attempt {identity.get('workflow_run_attempt')}) |",
        f"| commit | `{identity.get('commit_sha')}` |",
        f"| actor | {identity.get('actor')} |",
        f"| executed at | {identity.get('executed_at')} |",
        '',
        '## Read-only proof',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| advisory guard acquired | {proof.get('advisory_guard_acquired')} |",
        f"| release attempted | "
        f"{proof.get('advisory_guard_release_attempted')} |",
        f"| release confirmed | {proof.get('advisory_guard_released')} |",
        f"| transaction read-only | "
        f"{proof.get('transaction_read_only_enabled')} |",
        f"| fingerprints match | {proof.get('fingerprints_match')} |",
        f"| changed tables | {proof.get('changed_tables')} |",
        '',
        '### Write accounting',
        '',
        'The audit issues exactly one bounded proof statement, expected to be '
        'refused and rolled back. It attempts zero durable writes. Those are '
        'different facts and are reported as different rows.',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| read-only probe attempted | "
        f"{proof.get('read_only_probe_attempted')} |",
        f"| read-only probe count | {proof.get('read_only_probe_count')} |",
        f"| read-only probe statement class | "
        f"`{proof.get('read_only_probe_statement_class')}` |",
        f"| read-only probe bounded to zero rows | "
        f"{proof.get('read_only_probe_bounded_to_zero_rows')} |",
        f"| read-only probe refused | "
        f"{proof.get('read_only_probe_refused')} |",
        f"| durable write attempts | {proof.get('durable_write_attempts')} |",
        f"| durable rows created | {proof.get('durable_rows_created')} |",
        f"| durable rows updated | {proof.get('durable_rows_updated')} |",
        f"| durable rows deleted | {proof.get('durable_rows_deleted')} |",
        f"| commits performed by audit | "
        f"{proof.get('commits_performed_by_audit')} |",
        '',
        '## Evidence artifacts',
        '',
        '| artifact | required | present | readable | parse error |',
        '| :--- | :--- | :--- | :--- | :--- |',
    ]
    for name, entry in sorted((evidence.get('per_artifact') or {}).items()):
        lines.append(
            f"| `{name}` | {entry.get('required')} | {entry.get('present')} "
            f"| {entry.get('readable')} | {entry.get('parse_error')} |"
        )
    if evidence.get('missing_optional'):
        lines += [
            '',
            'Optional artifacts absent (reported, not inferred away): '
            f"{evidence['missing_optional']}.",
        ]

    lines += [
        '',
        '## MLB source-call budget',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| limits | {budget.get('limits')} |",
        f"| total limit | {budget.get('total_limit')} |",
        f"| calls spent | {budget.get('calls_spent')} |",
        f"| total spent | {budget.get('total_spent')} |",
        f"| calls refused by budget | "
        f"{budget.get('calls_refused_by_budget')} |",
        f"| source errors | {budget.get('total_source_errors')} |",
        f"| budget exhausted | {budget.get('budget_exhausted')} |",
        '',
        '## Questions',
        '',
        '| # | question | answered |',
        '| ---: | :--- | :--- |',
    ]
    for position, question in enumerate(document['questions'], start=1):
        lines.append(
            f"| {position} | {question['question']} | {question['answered']} |"
        )
    for question in document['questions']:
        lines += [
            '',
            f"### {question['question']}",
            '',
            question['answer'] or '',
        ]
        if question.get('unproven_reason'):
            lines.append('')
            lines.append(f"Unproven: `{question['unproven_reason']}`")

    lines += [
        '',
        '## Root cause',
        '',
        f"- primary: `{root_cause.get('primary_classification')}`",
        f"- all classifications: {root_cause.get('classifications')}",
        f"- platform defect classifications: "
        f"{root_cause.get('platform_defect_classifications')}",
        f"- platform defect proven: {root_cause.get('platform_defect_proven')}",
        '',
    ]

    if verdict['failed_reasons']:
        lines += ['## Failed reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['failed_reasons']]
        lines.append('')
    if verdict['unproven_reasons']:
        lines += ['## Unproven reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['unproven_reasons']]
        lines.append('')

    lines += ['---', '', verdict['non_authorization_statement'], '']
    return '\n'.join(lines)


def write_artifacts(document, artifact_dir) -> dict:
    target = Path(artifact_dir)
    target.mkdir(parents=True, exist_ok=True)

    (target / SUMMARY_JSON).write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    (target / SUMMARY_MARKDOWN).write_text(
        render_markdown(document), encoding='utf-8',
    )
    metadata = {
        'schema_version': audit.SCHEMA_VERSION,
        'audit_type': audit.AUDIT_TYPE,
        'incident_run_id': audit.INCIDENT_RUN_ID,
        'incident_head_sha': audit.INCIDENT_HEAD_SHA,
        'result': document['verdict']['result'],
        'exit_code': document['verdict']['exit_code'],
        'questions_answered': document['verdict']['questions_answered'],
        'questions_total': document['verdict']['questions_total'],
        'primary_classification': document['root_cause'][
            'primary_classification'
        ],
        'platform_defect_proven': document['root_cause'][
            'platform_defect_proven'
        ],
        'commit_sha': document['identity'].get('commit_sha'),
        'workflow_run_id': document['identity'].get('workflow_run_id'),
        'summary_filename': SUMMARY_JSON,
        'markdown_filename': SUMMARY_MARKDOWN,
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }
    (target / METADATA_JSON).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )
    return metadata


def _iso(value):
    if value is None:
        return None
    return value.isoformat() if hasattr(value, 'isoformat') else str(value)


def _safe_text(value, *, limit=60):
    if value is None:
        return None
    return str(value).strip()[:limit]


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        document = run(args)
    except Exception:  # noqa: BLE001 - never leak exception text
        document = build_document(
            context=event_context(args),
            note=qualification.sanitize_note(args.operator_note),
            observations={}, questions=[], read_only={},
            artifact_ingestion={},
            budget_state=audit.SourceCallBudget().state(),
            decision=_refuse(unproven=[audit.UNPROVEN_AUDIT_EXECUTION_ERROR]),
        )

    try:
        write_artifacts(document, args.artifact_dir)
    except Exception:  # noqa: BLE001 - an unwritable artifact is UNPROVEN
        document['verdict']['unproven_reasons'] = sorted(set(
            list(document['verdict']['unproven_reasons'])
            + [audit.UNPROVEN_ARTIFACT_CONSTRUCTION_FAILED]
        ))
        document['verdict']['result'] = audit.RESULT_UNPROVEN
        document['verdict']['exit_code'] = audit.EXIT_CODES[
            audit.RESULT_UNPROVEN
        ]

    print(json.dumps(document, indent=2, sort_keys=True, default=str))
    return int(document['verdict']['exit_code'])


if __name__ == '__main__':
    os.environ.setdefault('AUTO_SYNC', 'false')
    raise SystemExit(main())
