"""Bounded reconciliation of a withheld Dashboard publication (WP-3, first layer).

A publication gate that withholds a candidate is correct. Some withholdings,
though, have a local, deterministic cause that the pipeline can repair itself
instead of waiting for an operator. This module decides whether a withheld
outcome is one of them, and performs that repair once.

Classification reads only the withheld outcome's persisted gate evidence
(``services.publication_outcome.gate_evidence``):

* REPAIRABLE, class ``final_game_reingest``: every blocking game is a game MLB
  already lists as final whose canonical ingestion is incomplete. The
  blockers are a missing/incomplete/failed postgame marker, a final game with
  no appearance rows, or fewer rows than the ingest saw. The repair re-fetches
  exactly those games from the official schedule. It requires each one to
  still be safely final, and re-runs the canonical completed-game processor
  for each, idempotently.
* NOT REPAIRABLE, withheld unchanged:
  - a game that is not final (live or scheduled; stale finality is already
    refreshed during the candidate build, so a non-final game here is
    genuinely unfinished);
  - a suspended game, or one with unresolved resumed linkage;
  - a withhold caused by the run's publication-critical failures
    (``partial_sync``) rather than by a game;
  - any authority other than slate coverage or the appearance ledger;
  - more blocking games than ``MAX_REPAIR_GAMES``.

A slate that also has a non-repairable game is not repaired at all: it could
not complete in this attempt, and repairing part of it changes nothing that
gates publication.

The caller runs at most one repair per publication attempt and rebuilds the
candidate at most once. Every evaluation, attempted or not, is recorded in
``publication_outcome.recovery_result``. Nothing here changes a gate.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

from utils.db import db


REPAIR_FINAL_GAME_REINGEST = 'final_game_reingest'

MAX_REPAIR_GAMES = 16

REPAIRABLE_BLOCKERS = frozenset({
    'final_marker_missing',
    'final_marker_incomplete',
    'final_marker_failed',
    'final_game_without_appearance_rows',
    'appearance_rows_below_ingested_lines',
    'final_game_marker_incomplete',
})

REPAIRABLE_AUTHORITIES = frozenset({'slate_coverage', 'appearance_ledger'})

STOP_AUTHORITY_NOT_REPAIRABLE = 'authority_not_repairable'
STOP_PUBLICATION_CRITICAL_INCOMPLETE = 'publication_critical_incomplete'
STOP_NON_REPAIRABLE_GAMES = 'non_repairable_games'
STOP_NO_REPAIRABLE_ENTITIES = 'no_repairable_entities'
STOP_SCOPE_EXCEEDS_BOUND = 'repair_scope_exceeds_bound'
STOP_REPAIR_FAILED = 'repair_failed'
STOP_STILL_WITHHELD = 'still_withheld_after_repair'

RESULT_REPAIRED = 'repaired'
RESULT_PARTIAL = 'repair_incomplete'
RESULT_FAILED = 'repair_failed'


def plan_repair(outcome) -> dict:
    """Classify a withheld outcome. Pure: reads only the persisted evidence."""
    outcome = outcome or {}
    authority = outcome.get('failed_authority')
    evidence = outcome.get('gate_evidence') or {}
    games = list(evidence.get('games') or [])
    base = {'evaluated': True, 'failed_authority': authority}
    if authority not in REPAIRABLE_AUTHORITIES:
        return {**base, 'repairable': False,
                'stop_reason': f'{STOP_AUTHORITY_NOT_REPAIRABLE}:{authority}'}
    if outcome.get('publication_critical_complete') is False:
        # The rebuilt candidate would still be withheld as partial_sync: the
        # run's own publication-critical failures are not a game to repair.
        return {**base, 'repairable': False,
                'stop_reason': STOP_PUBLICATION_CRITICAL_INCOMPLETE}
    non_repairable = [
        game for game in games if game.get('blocker') not in REPAIRABLE_BLOCKERS
    ]
    if non_repairable:
        return {**base, 'repairable': False, 'stop_reason': STOP_NON_REPAIRABLE_GAMES,
                'affected_entities': _entities(non_repairable)}
    if not games:
        stop = (
            STOP_PUBLICATION_CRITICAL_INCOMPLETE
            if outcome.get('publication_critical_complete') is False
            or 'partial_sync' in (evidence.get('reason_codes') or [])
            else STOP_NO_REPAIRABLE_ENTITIES
        )
        return {**base, 'repairable': False, 'stop_reason': stop}
    if len(games) > MAX_REPAIR_GAMES:
        return {**base, 'repairable': False, 'stop_reason': STOP_SCOPE_EXCEEDS_BOUND,
                'affected_entities': _entities(games[:MAX_REPAIR_GAMES])}
    return {**base, 'repairable': True, 'repair_class': REPAIR_FINAL_GAME_REINGEST,
            'affected_entities': _entities(games)}


def _entities(games):
    return [
        {'game_pk': game.get('game_pk'), 'game_date': game.get('game_date'),
         'blocker': game.get('blocker')}
        for game in games
    ]


def _date(value):
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def reingest_final_games(plan, *, sync_run_id=None, client=None, processor=None,
                         fatigue_recalc=None) -> dict:
    """Re-run canonical ingestion once for exactly the planned final games."""
    from services import sync as sync_service
    from services.game_finality import has_safe_final_status
    from services.mlb_api import mlb_client

    client = client or mlb_client
    processor = processor or sync_service.process_completed_game_for_postgame_refresh
    fatigue_recalc = fatigue_recalc or sync_service.recalculate_all_fatigue

    by_date = defaultdict(set)
    for entity in plan.get('affected_entities') or ():
        game_date = _date(entity.get('game_date'))
        if game_date is not None and entity.get('game_pk') is not None:
            by_date[game_date].add(int(entity['game_pk']))

    actions = []
    workload_changed = False
    for game_date in sorted(by_date):
        wanted = by_date[game_date]
        official = {}
        for game in client.get_schedule(
            start_date=game_date.isoformat(), end_date=game_date.isoformat(),
        ) or []:
            try:
                game_pk = int((game or {}).get('gamePk'))
            except (TypeError, ValueError):
                continue
            if game_pk in wanted:
                official.setdefault(game_pk, game)
        for game_pk in sorted(wanted):
            game = official.get(game_pk)
            if game is None:
                actions.append({'game_pk': game_pk, 'result': 'not_in_official_schedule'})
                continue
            if not has_safe_final_status(game):
                actions.append({'game_pk': game_pk, 'result': 'not_safely_final'})
                continue
            processed = processor(
                game, schedule_date=game_date, sync_run_id=sync_run_id, force=True,
            ) or {}
            db.session.commit()
            added = int(processed.get('logs_added') or 0)
            corrected = int(processed.get('logs_corrected') or 0)
            workload_changed = workload_changed or bool(added or corrected)
            actions.append({
                'game_pk': game_pk,
                'result': 'reingested',
                'processing_status': processed.get('processing_status'),
                'logs_added': added,
                'logs_corrected': corrected,
                'pitcher_resolution_failures': int(
                    processed.get('pitcher_resolution_failures') or 0
                ),
            })
    if workload_changed:
        fatigue_recalc()
    complete = all(
        action.get('result') == 'reingested'
        and action.get('processing_status') in (None, 'fully_processed')
        and not action.get('pitcher_resolution_failures')
        for action in actions
    ) and bool(actions)
    return {
        'actions': actions,
        'workload_changed': workload_changed,
        'result': RESULT_REPAIRED if complete else RESULT_PARTIAL,
    }


class Reconciler:
    """One bounded repair per publication attempt."""

    def __init__(self, *, repair=None):
        self._repair = repair or reingest_final_games

    def plan(self, outcome):
        return plan_repair(outcome)

    def repair(self, plan, *, sync_run_id=None):
        try:
            return self._repair(plan, sync_run_id=sync_run_id)
        except Exception as exc:  # noqa: BLE001 - a failed repair leaves the withhold
            try:
                db.session.rollback()
            except Exception:
                pass
            return {'actions': [], 'result': RESULT_FAILED,
                    'error': type(exc).__name__}


def default_reconciler():
    return Reconciler()
