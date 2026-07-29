"""Governed 2026 historical team-at-appearance backfill (Foundation 2 of 6).

Foundation 1 froze the represented MLB team onto every NEW pitching appearance at
ingestion (``GameLog.appearance_team_*``) but intentionally left historical rows
NULL. This service attributes those legacy 2026 rows durably, safely, and
auditably — WITHOUT inventing a second resolver or box-score parser.

Contract (every rule below is enforced, not merely intended):

* Target = ``GameLog`` rows whose official ``game_date`` is in ``[start_date,
  end_date]`` AND ``appearance_team_status IS NULL`` AND whose game is FINAL in the
  local ``ScheduledGame`` ledger. Only legacy rows are ever touched; an explicit
  ``unresolved``/``conflict`` is never overwritten (they are not even selected). The
  wall clock is never consulted — the window is the official game date.
* Work is processed by DISTINCT ``mlb_game_pk`` (one box-score call per game at
  most), each game in its own atomic transaction with a per-game commit.
* Resolution is LOCAL-EVIDENCE-FIRST. Tier 1 derives the appearance's opponent from
  local official evidence (``CompletedGameContext``) and resolves it through the
  Foundation 1 schedule authority — no network call. Only appearances Tier 1 cannot
  resolve trigger a single Tier 2 box-score fetch, parsed and resolved through the
  exact Foundation 1 box-score seam. Neither tier ever consults the pitcher's mutable
  current team assignment.
* THE PLAN IS COMPUTED READ-ONLY UP FRONT. Every run first resolves the whole batch
  without writing and produces a deterministic plan + fingerprint. The fingerprint
  binds not only the selected rows but the PROPOSED per-row transition (status, team,
  source, reason) and the official evidence behind it — so if a box score or schedule
  changes between review and apply, the fingerprint changes and apply refuses.
* DRY RUN IS THE DEFAULT: zero writes. APPLY requires the exact confirmation phrase
  AND a matching approved fingerprint (mandatory, not optional); both are checked
  before any write, and a failure returns ``refused`` having mutated nothing.
* FAILURES STOP THE CURSOR. The plan stops at the first game that cannot be resolved,
  and the returned cursor never advances past uncommitted work — the failed game is
  re-selected on the next run. Any failure classifies the run ``fail`` (exit 1); a
  clean batch is ``pass`` (exit 0); an empty/already-complete batch is
  ``inconclusive`` (exit 2).

This module performs NO schema change, computes NO performance metric, and mutates
only the four ``appearance_team_*`` columns of legacy rows it attributes.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date
from typing import List, Optional, Tuple

import sqlalchemy as sa

from models.completed_game_context import CompletedGameContext
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import sync as sync_service
from services.appearance_team_coverage import build_appearance_team_coverage
from services.mlb_api import mlb_client
from utils.db import db


# ── Governance constants ──────────────────────────────────────────────────────
CONFIRMATION_PHRASE = 'RUN_2026_APPEARANCE_TEAM_BACKFILL'
EXPECTED_MIGRATION_HEAD = 'c7b3e5a91d48'

DEFAULT_START_DATE = date(2026, 1, 1)
DEFAULT_END_DATE = date(2026, 12, 31)

DEFAULT_BATCH_SIZE = 200
MAX_BATCH_SIZE = 2000

# Identity of THIS backfill's contract plus the Foundation 1 resolution vocabulary it
# is pinned to. Both are folded into the batch fingerprint so an approved dry-run plan
# is invalidated if either the backfill logic or the underlying resolver contract
# moves — a stale fingerprint can never authorize a changed apply.
BACKFILL_CONTRACT_VERSION = '2026_appearance_team_backfill.v2'
RESOLVER_CONTRACT_VERSION = ':'.join((
    ata.SOURCE_BOXSCORE,
    ata.SOURCE_SCHEDULE,
    ata.STATUS_RESOLVED,
    ata.STATUS_UNRESOLVED,
    ata.STATUS_CONFLICT,
))

# Non-final ledger states that disqualify a game (a postponed or suspended-unreplayed
# game produced no completed appearance to attribute).
_NON_FINAL_STATES = (ScheduledGame.STATE_POSTPONED, ScheduledGame.STATE_SUSPENDED)

# Bound the row/game detail lists carried in the summary so a pathological run can
# never produce an unbounded artifact.
_MAX_GAME_DETAIL = 200
_MAX_ROW_DETAIL = 500
_MAX_FAILED_GAME_DETAIL = 100


# ── Result contract (exit codes) ──────────────────────────────────────────────
RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_REFUSED = 'refused'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {
    RESULT_PASS: 0,
    RESULT_REFUSED: 1,
    RESULT_FAIL: 1,
    RESULT_INCONCLUSIVE: 2,
}


@dataclass(frozen=True)
class RowResolution:
    """One targeted appearance's proposed transition."""

    game_log_id: int
    status: str
    appearance_team_id: Optional[int]
    source: Optional[str]
    reason: Optional[str]


@dataclass(frozen=True)
class GamePlan:
    """A fully-resolved game (read-only) with the evidence behind its transitions."""

    game_date: date
    game_pk: int
    rows: List[RowResolution]
    boxscore_fetched: bool
    schedule_authority: Tuple
    evidence_digest: str


def _clamp_batch_size(value) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return DEFAULT_BATCH_SIZE
    if parsed < 1:
        return 1
    return min(parsed, MAX_BATCH_SIZE)


def _normalize_name(value) -> str:
    return ' '.join(str(value or '').strip().lower().split())


def _int_or_none(value) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _sha256_json(payload) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'), default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


# ── Batch selection (deterministic keyset cursor + finality gate) ─────────────
def _select_game_keys(
    *, start_date, end_date, after_game_date, after_game_pk, batch_size, session,
):
    """Distinct ``(game_date, game_pk)`` of FINAL games with >=1 legacy-NULL target.

    Ordered ``(game_date ASC, game_pk ASC)`` and paginated by a keyset cursor (never
    OFFSET). A game qualifies only when the local ledger shows it FINAL and shows no
    postponed/suspended row for the same game_pk — so a not-yet-final game is never
    targeted (its rows stay NULL until it finalizes), which keeps the cursor monotonic
    and the historical sweep resumable.
    """
    final_exists = (
        session.query(ScheduledGame.id)
        .filter(ScheduledGame.game_pk == GameLog.mlb_game_pk)
        .filter(ScheduledGame.status_state == ScheduledGame.STATE_FINAL)
        .exists()
    )
    non_final_exists = (
        session.query(ScheduledGame.id)
        .filter(ScheduledGame.game_pk == GameLog.mlb_game_pk)
        .filter(ScheduledGame.status_state.in_(_NON_FINAL_STATES))
        .exists()
    )
    query = (
        session.query(GameLog.game_date, GameLog.mlb_game_pk)
        .filter(GameLog.appearance_team_status.is_(None))
        .filter(GameLog.mlb_game_pk.isnot(None))
        .filter(GameLog.game_date >= start_date)
        .filter(GameLog.game_date <= end_date)
        .filter(final_exists)
        .filter(~non_final_exists)
    )
    if after_game_date is not None and after_game_pk is not None:
        query = query.filter(
            sa.or_(
                GameLog.game_date > after_game_date,
                sa.and_(
                    GameLog.game_date == after_game_date,
                    GameLog.mlb_game_pk > after_game_pk,
                ),
            )
        )
    query = (
        query.distinct()
        .order_by(GameLog.game_date.asc(), GameLog.mlb_game_pk.asc())
        .limit(batch_size)
    )
    return query.all()


def _target_rows_for_game(*, game_pk, start_date, end_date, session):
    return (
        session.query(GameLog)
        .filter(GameLog.mlb_game_pk == game_pk)
        .filter(GameLog.appearance_team_status.is_(None))
        .filter(GameLog.game_date >= start_date)
        .filter(GameLog.game_date <= end_date)
        .order_by(GameLog.id.asc())
        .all()
    )


# ── Resolution helpers (Tier 1 local, Tier 2 one box-score call) ──────────────
def _pitcher_mlb_ids(pitcher_ids, *, session):
    """Map internal pitcher id -> MLB id. Never reads the pitcher's current team."""
    ids = {pid for pid in pitcher_ids if pid is not None}
    if not ids:
        return {}
    rows = (
        session.query(Pitcher.id, Pitcher.mlb_id)
        .filter(Pitcher.id.in_(ids))
        .all()
    )
    return {pid: mlb_id for pid, mlb_id in rows}


def _local_opponent_team_id(opponent_name, pitcher_mlb_id, context_rows):
    """Derive the appearance's opponent team id from LOCAL official evidence.

    Two unambiguous local signals, most authoritative first:
      1. Starter identity — the ``CompletedGameContext`` row whose ``starter_player_id``
         is this pitcher records its own team's opponent directly (no name matching).
      2. Opponent name — the appearance's stored opponent names exactly one side's
         ``opponent_name``; that side's ``opponent_team_id`` is the opponent.
    Any ambiguity (no match, a tie, or missing context) returns None so the caller
    falls through to the authoritative box-score tier. Because the derived id is only a
    proposal that the Foundation 1 schedule authority then re-resolves and fails closed
    on, an ambiguous local signal can never yield a wrong attribution.
    """
    if pitcher_mlb_id is not None:
        for row in context_rows:
            if (
                row.starter_player_id is not None
                and row.starter_player_id == pitcher_mlb_id
                and row.opponent_team_id
            ):
                return row.opponent_team_id
    target = _normalize_name(opponent_name)
    if target:
        opponent_ids = {
            row.opponent_team_id
            for row in context_rows
            if row.opponent_team_id
            and _normalize_name(row.opponent_name) == target
        }
        if len(opponent_ids) == 1:
            return next(iter(opponent_ids))
    return None


def _game_from_boxscore(boxscore, game_pk) -> dict:
    """Minimal game payload the Foundation 1 box-score seam needs (home/away team)."""
    teams = (boxscore or {}).get('teams') or {}
    return {
        'gamePk': game_pk,
        'teams': {
            'home': {'team': ((teams.get('home') or {}).get('team') or {})},
            'away': {'team': ((teams.get('away') or {}).get('team') or {})},
        },
    }


def _unresolved_resolution() -> ata.AppearanceTeamResolution:
    return ata.AppearanceTeamResolution(
        None, ata.STATUS_UNRESOLVED, None, ata.REASON_UNRESOLVED,
    )


def _plan_game(game_pk, game_date, target_rows, *, client, allow_api, session):
    """Resolve every legacy-NULL appearance of one game READ-ONLY into a GamePlan.

    Tier 1 (local, no network) resolves what local evidence unambiguously determines;
    Tier 2 makes a single box-score call for the remainder. Both reuse the Foundation
    1 resolver/parser verbatim. Never consults the pitcher's current team. Raises on an
    evidence/processing failure (box-score fetch/parse/resolver error) so the caller
    can stop the batch at that boundary.
    """
    context_rows = (
        session.query(CompletedGameContext)
        .filter(CompletedGameContext.game_pk == game_pk)
        .all()
    )
    mlb_by_pitcher = _pitcher_mlb_ids((row.pitcher_id for row in target_rows), session=session)
    schedule_rows = session.query(
        ScheduledGame.team_id,
        ScheduledGame.opponent_team_id,
        ScheduledGame.home_away,
    ).filter(ScheduledGame.game_pk == game_pk).all()
    schedule_authority = tuple(sorted(
        (
            (_int_or_none(team_id), _int_or_none(opponent_team_id), home_away or '')
            for team_id, opponent_team_id, home_away in schedule_rows
        ),
        key=lambda item: (item[0] is None, item[0] or 0, item[1] or 0, item[2]),
    ))

    resolutions: dict = {}
    needs_boxscore = []
    for row in target_rows:
        opponent_team_id = _local_opponent_team_id(
            row.opponent, mlb_by_pitcher.get(row.pitcher_id), context_rows,
        )
        if opponent_team_id is not None:
            resolution = ata.resolve_for_write(
                game_pk=game_pk, opponent_team_id=opponent_team_id, session=session,
            )
            if resolution.resolved:
                resolutions[row.id] = resolution
                continue
        needs_boxscore.append(row)

    boxscore_fetched = False
    boxscore_sides = {}
    if needs_boxscore and allow_api:
        boxscore = client.get_game_boxscore(game_pk)
        boxscore_fetched = True
        game = _game_from_boxscore(boxscore, game_pk)
        lines_by_mlb_id = {}
        for line in sync_service._extract_pitching_lines_from_boxscore(boxscore):
            key = line.get('person_id') or line.get('player_id')
            if key is not None:
                boxscore_sides.setdefault(key, (line.get('side'), _int_or_none(line.get('team_id'))))
                lines_by_mlb_id.setdefault(key, line)
        for row in needs_boxscore:
            line = lines_by_mlb_id.get(mlb_by_pitcher.get(row.pitcher_id))
            if line is None:
                resolutions[row.id] = _unresolved_resolution()
            else:
                resolutions[row.id] = sync_service._appearance_team_for_boxscore_line(
                    game, line, game_pk,
                )
    else:
        for row in needs_boxscore:
            resolutions[row.id] = _unresolved_resolution()

    row_resolutions = []
    for row in sorted(target_rows, key=lambda r: r.id):
        res = resolutions[row.id]
        row_resolutions.append(RowResolution(
            game_log_id=row.id,
            status=res.status,
            appearance_team_id=res.team_id if res.resolved else None,
            source=res.source,
            reason=res.reason,
        ))

    evidence_digest = _sha256_json({
        'schedule_authority': [list(item) for item in schedule_authority],
        'boxscore_fetched': boxscore_fetched,
        'boxscore_sides': sorted(
            [key, side, team_id] for key, (side, team_id) in boxscore_sides.items()
        ),
    })
    plan = GamePlan(
        game_date=game_date,
        game_pk=game_pk,
        rows=row_resolutions,
        boxscore_fetched=boxscore_fetched,
        schedule_authority=schedule_authority,
        evidence_digest=evidence_digest,
    )
    return plan


def _plan_batch(game_keys, *, start_date, end_date, client, allow_api, session):
    """Resolve the batch READ-ONLY in cursor order, stopping at the first failure.

    Returns (plan_games, boundary_failure, api_calls). ``plan_games`` is the
    committable prefix; ``boundary_failure`` (if any) is the first game that could not
    be resolved — everything at and after it is deliberately left for a later run so
    the cursor never advances past uncommitted work.
    """
    plan_games = []
    boundary_failure = None
    api_calls = 0
    with session.no_autoflush:
        for game_date, game_pk in game_keys:
            target_rows = _target_rows_for_game(
                game_pk=game_pk, start_date=start_date, end_date=end_date, session=session,
            )
            if not target_rows:
                continue
            try:
                plan = _plan_game(
                    game_pk, game_date, target_rows,
                    client=client, allow_api=allow_api, session=session,
                )
            except Exception as exc:  # noqa: BLE001 — a game failure is a stop boundary
                boundary_failure = {'game_pk': game_pk, 'error_type': type(exc).__name__}
                break
            if plan.boxscore_fetched:
                api_calls += 1
            plan_games.append(plan)
    return plan_games, boundary_failure, api_calls


def _plan_fingerprint(plan_games, *, start_date, end_date, after_game_date, after_game_pk):
    """SHA-256 over the ordered resolution PLAN — targets AND proposed transitions.

    Binds the resolver/backfill contract versions, the window, the cursor, and for
    each game its evidence digest plus every targeted row's proposed status, team,
    source, and reason. So a changed official attribution (a moved box-score side, a
    changed schedule authority) alters the fingerprint even when the selected row IDs
    are identical, and apply refuses until a fresh dry run is approved. Excludes
    secrets, database URL, raw payloads, timestamps, and unstable ordering.
    """
    canonical = {
        'backfill_contract_version': BACKFILL_CONTRACT_VERSION,
        'resolver_contract_version': RESOLVER_CONTRACT_VERSION,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'after_game_date': after_game_date.isoformat() if after_game_date else None,
        'after_game_pk': after_game_pk,
        'games': [
            {
                'game_pk': plan.game_pk,
                'game_date': plan.game_date.isoformat(),
                'boxscore_fetched': plan.boxscore_fetched,
                'schedule_authority': [list(item) for item in plan.schedule_authority],
                'evidence_digest': plan.evidence_digest,
                'rows': [
                    {
                        'game_log_id': row.game_log_id,
                        'status': row.status,
                        'appearance_team_id': row.appearance_team_id,
                        'source': row.source,
                        'reason': row.reason,
                    }
                    for row in plan.rows
                ],
            }
            for plan in plan_games
        ],
    }
    return _sha256_json(canonical)


# ── Write (apply only) ────────────────────────────────────────────────────────
def _apply_plan_game(plan, session):
    """Freeze one game's planned transitions and commit atomically.

    Each row is reloaded and revalidated immediately before write: a row that is no
    longer legacy-NULL (a concurrent completion) or has been deleted is safely skipped
    rather than overwritten. Only the four appearance_team_* fields change; statistics
    and every other model are untouched. Returns (rows_written, rows_skipped).
    """
    written = 0
    skipped = 0
    for row_plan in plan.rows:
        row = session.get(GameLog, row_plan.game_log_id)
        if row is None or row.appearance_team_status is not None:
            skipped += 1
            continue
        row.appearance_team_id = row_plan.appearance_team_id
        row.appearance_team_source = row_plan.source
        row.appearance_team_status = row_plan.status
        row.appearance_team_reason = row_plan.reason
        written += 1
    session.commit()
    return written, skipped


# ── Audit helpers (read-only) ─────────────────────────────────────────────────
def _invalid_stored_state_count(session) -> int:
    """Rows violating the Foundation 1 status<->team_id invariant (must stay 0)."""
    valid_statuses = (ata.STATUS_RESOLVED, ata.STATUS_UNRESOLVED, ata.STATUS_CONFLICT)
    query = session.query(sa.func.count(GameLog.id)).filter(
        sa.or_(
            sa.and_(
                GameLog.appearance_team_status == ata.STATUS_RESOLVED,
                GameLog.appearance_team_id.is_(None),
            ),
            sa.and_(
                GameLog.appearance_team_status.in_(
                    (ata.STATUS_UNRESOLVED, ata.STATUS_CONFLICT)
                ),
                GameLog.appearance_team_id.isnot(None),
            ),
            sa.and_(
                GameLog.appearance_team_status.is_(None),
                GameLog.appearance_team_id.isnot(None),
            ),
            sa.and_(
                GameLog.appearance_team_status.isnot(None),
                ~GameLog.appearance_team_status.in_(valid_statuses),
            ),
        )
    )
    return int(query.scalar() or 0)


def _season_null_legacy(coverage, season) -> Optional[int]:
    bucket = (coverage.get('by_season') or {}).get(season)
    if bucket is None:
        return None
    return int(bucket.get('null_legacy', 0))


def _coverage_snapshot(session, *, season) -> dict:
    coverage = build_appearance_team_coverage(session=session)
    return {
        'total_game_logs': coverage['total_game_logs'],
        'resolved': coverage['resolved'],
        'unresolved': coverage['unresolved'],
        'conflict': coverage['conflict'],
        'null_legacy': coverage['null_legacy'],
        'season_null_legacy': _season_null_legacy(coverage, season),
        'invalid_stored_states': _invalid_stored_state_count(session),
    }


def _migration_head(session):
    """Best-effort current Alembic head(s) for the report.

    This is a diagnostic probe, not part of the resolution/write flow. On a schema
    without an ``alembic_version`` table (a ``create_all`` test schema) the read
    fails; on PostgreSQL a failed statement ABORTS the surrounding transaction, so
    the probe immediately rolls back to leave the session usable. The probe runs
    before any coverage read or write, so clearing the (read-only) transaction here
    is always safe and never poisons a later query.
    """
    try:
        rows = session.execute(
            sa.text('SELECT version_num FROM alembic_version ORDER BY version_num')
        ).fetchall()
        return sorted(str(row[0]) for row in rows)
    except Exception:  # noqa: BLE001 — a diagnostic probe never fails the run
        # A failed statement leaves a PostgreSQL transaction aborted; roll back so
        # every subsequent query (coverage audit, selection, per-game write) runs on
        # a clean transaction.
        session.rollback()
        return None


# ── Public entry point ────────────────────────────────────────────────────────
def run_backfill(
    *,
    start_date: date = DEFAULT_START_DATE,
    end_date: date = DEFAULT_END_DATE,
    batch_size: int = DEFAULT_BATCH_SIZE,
    after_game_date: Optional[date] = None,
    after_game_pk: Optional[int] = None,
    apply: bool = False,
    confirmation: Optional[str] = None,
    expected_fingerprint: Optional[str] = None,
    allow_api: bool = True,
    season: int = 2026,
    client=mlb_client,
    session=None,
) -> dict:
    """Run one governed backfill batch and return a deterministic summary.

    Dry run by default (zero writes). Apply requires ``apply=True``, the exact
    confirmation phrase, AND a matching ``expected_fingerprint`` (mandatory) — all
    checked BEFORE any write. Failures stop the cursor at the last successful game.
    """
    session = session or db.session
    batch_size = _clamp_batch_size(batch_size)
    if end_date < start_date:
        raise ValueError('end_date must not be before start_date')

    # Diagnostic probe FIRST (it self-recovers on failure) so every read/write below
    # runs on a clean transaction.
    migration_head = _migration_head(session)
    coverage_before = _coverage_snapshot(session, season=season)

    # 1) Plan the whole batch READ-ONLY, stopping at the first failure.
    game_keys = _select_game_keys(
        start_date=start_date,
        end_date=end_date,
        after_game_date=after_game_date,
        after_game_pk=after_game_pk,
        batch_size=batch_size,
        session=session,
    )
    plan_games, boundary_failure, api_calls = _plan_batch(
        game_keys,
        start_date=start_date,
        end_date=end_date,
        client=client,
        allow_api=allow_api,
        session=session,
    )
    fingerprint = _plan_fingerprint(
        plan_games,
        start_date=start_date,
        end_date=end_date,
        after_game_date=after_game_date,
        after_game_pk=after_game_pk,
    )

    proposed = {'resolved': 0, 'unresolved': 0, 'conflict': 0,
                'via_schedule': 0, 'via_boxscore': 0}
    non_resolved = []
    for plan in plan_games:
        for row in plan.rows:
            if row.status == ata.STATUS_RESOLVED and row.appearance_team_id is not None:
                proposed['resolved'] += 1
                if row.source == ata.SOURCE_SCHEDULE:
                    proposed['via_schedule'] += 1
                elif row.source == ata.SOURCE_BOXSCORE:
                    proposed['via_boxscore'] += 1
            elif row.status == ata.STATUS_CONFLICT:
                proposed['conflict'] += 1
                if len(non_resolved) < _MAX_ROW_DETAIL:
                    non_resolved.append({'game_log_id': row.game_log_id,
                                         'game_pk': plan.game_pk, 'status': row.status})
            else:
                proposed['unresolved'] += 1
                if len(non_resolved) < _MAX_ROW_DETAIL:
                    non_resolved.append({'game_log_id': row.game_log_id,
                                         'game_pk': plan.game_pk, 'status': row.status})

    appearances_targeted = sum(len(plan.rows) for plan in plan_games)
    counts_reconcile = appearances_targeted == (
        proposed['resolved'] + proposed['unresolved'] + proposed['conflict']
    )
    has_more = boundary_failure is not None or len(game_keys) >= batch_size
    failed_games = []
    if boundary_failure is not None:
        failed_games.append({**boundary_failure, 'phase': 'resolve'})

    inputs = {
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'season': int(season),
        'batch_size': batch_size,
        'allow_api': bool(allow_api),
        'after_game_date': after_game_date.isoformat() if after_game_date else None,
        'after_game_pk': after_game_pk,
    }
    games_preview = [
        {
            'game_pk': plan.game_pk,
            'game_date': plan.game_date.isoformat(),
            'boxscore_fetched': plan.boxscore_fetched,
            'rows': [
                {'game_log_id': row.game_log_id, 'status': row.status,
                 'appearance_team_id': row.appearance_team_id,
                 'source': row.source, 'reason': row.reason}
                for row in plan.rows
            ],
        }
        for plan in plan_games[:_MAX_GAME_DETAIL]
    ]

    base_summary = {
        'capability': 'appearance_team_backfill_2026_v2',
        'mode': 'apply' if apply else 'dry_run',
        'backfill_contract_version': BACKFILL_CONTRACT_VERSION,
        'resolver_contract_version': RESOLVER_CONTRACT_VERSION,
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'git_sha': os.environ.get('GITHUB_SHA'),
        'inputs': inputs,
        'season': int(season),
        'batch_fingerprint': fingerprint,
        'games_selected': len(game_keys),
        'games_planned': len(plan_games),
        'appearances_targeted': appearances_targeted,
        'proposed_resolved': proposed['resolved'],
        'proposed_unresolved': proposed['unresolved'],
        'proposed_conflict': proposed['conflict'],
        'resolved_via_schedule': proposed['via_schedule'],
        'resolved_via_boxscore': proposed['via_boxscore'],
        'api_calls': api_calls,
        'counts_reconcile': counts_reconcile,
        'games_preview': games_preview,
        'games_preview_truncated': len(plan_games) > _MAX_GAME_DETAIL,
        'non_resolved': non_resolved,
        'non_resolved_truncated': (proposed['unresolved'] + proposed['conflict']) > len(non_resolved),
        'coverage_before': coverage_before,
        'database_writes_performed': False,
    }

    def _finish(*, result, reasons, next_cursor, extra=None):
        coverage_after = _coverage_snapshot(session, season=season)
        summary = {
            **base_summary,
            'result': result,
            'exit_code': EXIT_BY_RESULT[result],
            'decision_reasons': reasons,
            'next_cursor': next_cursor,
            'has_more': has_more,
            'exhausted': not has_more,
            'failed_games': failed_games[:_MAX_FAILED_GAME_DETAIL],
            'failed_game_count': len(failed_games),
            'coverage_after': coverage_after,
        }
        if extra:
            summary.update(extra)
        return summary

    input_cursor = {
        'after_game_date': after_game_date.isoformat() if after_game_date else None,
        'after_game_pk': after_game_pk,
    }

    def _cursor_at(plan):
        return {'after_game_date': plan.game_date.isoformat(), 'after_game_pk': plan.game_pk}

    # 2) Apply gates — MANDATORY, checked before any mutation.
    if apply:
        if confirmation != CONFIRMATION_PHRASE:
            return _finish(result=RESULT_REFUSED,
                           reasons=['confirmation_phrase_required'],
                           next_cursor=input_cursor)
        if not expected_fingerprint:
            return _finish(result=RESULT_REFUSED,
                           reasons=['approved_fingerprint_required'],
                           next_cursor=input_cursor)
        if expected_fingerprint != fingerprint:
            return _finish(result=RESULT_REFUSED,
                           reasons=['fingerprint_mismatch'],
                           next_cursor=input_cursor,
                           extra={'expected_fingerprint': expected_fingerprint})

    # 3) Empty batch → inconclusive (nothing to do).
    if not plan_games and boundary_failure is None:
        return _finish(result=RESULT_INCONCLUSIVE, reasons=['no_target_rows'],
                       next_cursor=input_cursor)

    # 4) Write phase (apply only). Per-game commit; stop and fail on a commit error.
    writes = {'games_committed': 0, 'rows_written': 0, 'rows_skipped_concurrent': 0}
    commit_failure = None
    last_committed = None
    if apply:
        for plan in plan_games:
            try:
                written, skipped = _apply_plan_game(plan, session)
            except Exception as exc:  # noqa: BLE001 — isolate + stop on a commit error
                session.rollback()
                commit_failure = {'game_pk': plan.game_pk, 'error_type': type(exc).__name__,
                                  'phase': 'commit'}
                failed_games.append(commit_failure)
                break
            writes['games_committed'] += 1
            writes['rows_written'] += written
            writes['rows_skipped_concurrent'] += skipped
            last_committed = plan
    else:
        session.rollback()  # belt-and-braces: dry run mutates nothing

    # 5) Next cursor = last SUCCESSFULLY processed game (never past uncommitted work).
    if apply:
        last_ok = last_committed
    else:
        last_ok = plan_games[-1] if plan_games else None
    next_cursor = _cursor_at(last_ok) if last_ok is not None else input_cursor

    # 6) Classify.
    invalid_after = _invalid_stored_state_count(session)
    writes_performed = apply and writes['games_committed'] > 0
    if invalid_after > 0:
        result, reasons = RESULT_FAIL, ['invalid_stored_states']
    elif commit_failure is not None:
        result, reasons = RESULT_FAIL, ['game_commit_failure']
    elif boundary_failure is not None:
        result, reasons = RESULT_FAIL, ['game_resolution_failure']
    elif apply and writes['rows_written'] == 0 and writes['rows_skipped_concurrent'] > 0:
        result, reasons = RESULT_INCONCLUSIVE, ['all_targets_already_complete']
    else:
        result, reasons = RESULT_PASS, ['batch_committed' if apply else 'clean_plan']

    return _finish(
        result=result,
        reasons=reasons,
        next_cursor=next_cursor,
        extra={'database_writes_performed': writes_performed, **writes},
    )
