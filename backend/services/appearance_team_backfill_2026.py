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
  most), each game in its own atomic transaction with a per-game commit (apply) or
  per-game rollback (failure), so a single bad game can never corrupt a batch.
* Resolution is LOCAL-EVIDENCE-FIRST. Tier 1 derives the appearance's opponent from
  local official evidence (``CompletedGameContext``) and resolves it through the
  Foundation 1 schedule authority — no network call. Only appearances Tier 1 cannot
  resolve trigger a single Tier 2 box-score fetch, parsed and resolved through the
  exact Foundation 1 box-score seam. Neither tier ever consults the pitcher's
  mutable current team assignment.
* DRY RUN IS THE DEFAULT: zero writes, a deterministic JSON report, and a batch
  fingerprint over the ordered work set. APPLY requires the exact confirmation phrase
  and, optionally, a matching approved fingerprint — checked BEFORE any write.
* The deterministic cursor is keyset ``(game_date ASC, game_pk ASC)`` — never OFFSET
  — so a large sweep resumes across runs without re-doing or skipping work.

This module performs NO schema change, computes NO performance metric, and mutates
only the four ``appearance_team_*`` columns of legacy rows it attributes.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from typing import Optional

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
# The one phrase that authorizes writes. The CLI and the workflow both require it.
CONFIRMATION_PHRASE = 'RUN_2026_APPEARANCE_TEAM_BACKFILL'

# The backfill campaign window defaults to the full 2026 calendar year so every 2026
# game_date is covered; the caller may narrow it.
DEFAULT_START_DATE = date(2026, 1, 1)
DEFAULT_END_DATE = date(2026, 12, 31)

DEFAULT_BATCH_SIZE = 200
MAX_BATCH_SIZE = 2000

# Identity of THIS backfill's contract plus the Foundation 1 resolution vocabulary it
# is pinned to. Both are folded into the batch fingerprint so an approved dry-run plan
# is invalidated if either the backfill logic or the underlying resolver contract
# moves — a stale fingerprint can never authorize a changed apply.
BACKFILL_CONTRACT_VERSION = '2026_appearance_team_backfill.v1'
RESOLVER_CONTRACT_VERSION = ':'.join((
    ata.SOURCE_BOXSCORE,
    ata.SOURCE_SCHEDULE,
    ata.STATUS_RESOLVED,
    ata.STATUS_UNRESOLVED,
    ata.STATUS_CONFLICT,
))

# Non-final ledger states that disqualify a game from attribution (a game that was
# postponed or suspended-unreplayed produced no completed appearance to attribute).
_NON_FINAL_STATES = (ScheduledGame.STATE_POSTPONED, ScheduledGame.STATE_SUSPENDED)

# Bound the failed-game detail list carried in the summary so a pathological run can
# never produce an unbounded artifact.
_MAX_FAILED_GAME_DETAIL = 100


# ── Result contract ───────────────────────────────────────────────────────────
RESULT_COMPLETED = 'completed'
RESULT_COMPLETED_WITH_FAILURES = 'completed_with_failures'
RESULT_REFUSED = 'refused'
RESULT_FAILED = 'failed'


@dataclass(frozen=True)
class _GamePlan:
    """One distinct game selected for the batch (used for the fingerprint)."""

    game_date: date
    game_pk: int
    game_log_ids: tuple


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


# ── Batch selection (deterministic keyset cursor + finality gate) ─────────────
def _select_game_keys(
    *, start_date, end_date, after_game_date, after_game_pk, batch_size, session,
):
    """Distinct ``(game_date, game_pk)`` of FINAL games with >=1 legacy-NULL target.

    Ordered ``(game_date ASC, game_pk ASC)`` and paginated by a keyset cursor (never
    OFFSET). A game qualifies only when the local ledger shows it FINAL and shows no
    postponed/suspended row for the same game_pk — so a not-yet-final game is simply
    never targeted (its rows stay NULL until it finalizes), which keeps the cursor
    monotonic and the historical sweep resumable.
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


# ── Resolution (Tier 1 local, Tier 2 one box-score call) ──────────────────────
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
    falls through to the authoritative box-score tier. Because the derived id is only
    a proposal that the Foundation 1 schedule authority then re-resolves and fails
    closed on, an ambiguous local signal can never yield a wrong attribution.
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


def _resolve_game(game_pk, target_rows, *, client, allow_api, session):
    """Resolve every legacy-NULL appearance of one game. Returns (pairs, api_called).

    Tier 1 (local, no network) resolves what local evidence unambiguously determines;
    Tier 2 makes a single box-score call for the remainder. Both reuse the Foundation
    1 resolver/parser verbatim. Never consults the pitcher's current team.
    """
    context_rows = (
        session.query(CompletedGameContext)
        .filter(CompletedGameContext.game_pk == game_pk)
        .all()
    )
    mlb_by_pitcher = _pitcher_mlb_ids((row.pitcher_id for row in target_rows), session=session)

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

    api_called = False
    if needs_boxscore and allow_api:
        boxscore = client.get_game_boxscore(game_pk)
        api_called = True
        game = _game_from_boxscore(boxscore, game_pk)
        lines_by_mlb_id = {}
        for line in sync_service._extract_pitching_lines_from_boxscore(boxscore):
            key = line.get('person_id') or line.get('player_id')
            if key is not None and key not in lines_by_mlb_id:
                lines_by_mlb_id[key] = line
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

    return [(row, resolutions[row.id]) for row in target_rows], api_called


def _apply_resolution(row, resolution) -> None:
    """Freeze a resolution onto a legacy row, honoring the stored-state invariant.

    Only NULL-status rows reach here; the guard makes overwriting an explicit
    ``unresolved``/``conflict`` impossible even under a concurrent attribution.
    """
    if row.appearance_team_status is not None:
        return
    fields = resolution.to_write_fields()
    row.appearance_team_id = fields['appearance_team_id']
    row.appearance_team_source = fields['appearance_team_source']
    row.appearance_team_status = fields['appearance_team_status']
    row.appearance_team_reason = fields['appearance_team_reason']


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


# ── Fingerprint ───────────────────────────────────────────────────────────────
def _batch_fingerprint(*, plans, start_date, end_date, after_game_date, after_game_pk):
    canonical = {
        'backfill_contract_version': BACKFILL_CONTRACT_VERSION,
        'resolver_contract_version': RESOLVER_CONTRACT_VERSION,
        'start_date': start_date.isoformat(),
        'end_date': end_date.isoformat(),
        'after_game_date': after_game_date.isoformat() if after_game_date else None,
        'after_game_pk': after_game_pk,
        'games': [
            {
                'game_date': plan.game_date.isoformat(),
                'game_pk': plan.game_pk,
                'game_log_ids': list(plan.game_log_ids),
            }
            for plan in plans
        ],
    }
    serialized = json.dumps(
        canonical, sort_keys=True, separators=(',', ':'), default=str,
    )
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()


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

    Dry run by default (zero writes). Apply requires ``apply=True`` AND the exact
    confirmation phrase; if ``expected_fingerprint`` is supplied it must equal the
    computed batch fingerprint. Both gates are checked BEFORE any write; a failed gate
    returns a ``refused`` summary having mutated nothing.
    """
    session = session or db.session
    batch_size = _clamp_batch_size(batch_size)
    if end_date < start_date:
        raise ValueError('end_date must not be before start_date')

    coverage_before = _coverage_snapshot(session, season=season)

    # 1) Select the batch and build the fingerprint plan from lightweight keys.
    game_keys = _select_game_keys(
        start_date=start_date,
        end_date=end_date,
        after_game_date=after_game_date,
        after_game_pk=after_game_pk,
        batch_size=batch_size,
        session=session,
    )
    plans = []
    for game_date, game_pk in game_keys:
        row_ids = [
            row.id
            for row in _target_rows_for_game(
                game_pk=game_pk, start_date=start_date, end_date=end_date, session=session,
            )
        ]
        if not row_ids:
            continue
        plans.append(_GamePlan(game_date, game_pk, tuple(sorted(row_ids))))

    fingerprint = _batch_fingerprint(
        plans=plans,
        start_date=start_date,
        end_date=end_date,
        after_game_date=after_game_date,
        after_game_pk=after_game_pk,
    )
    next_cursor = (
        {
            'after_game_date': plans[-1].game_date.isoformat(),
            'after_game_pk': plans[-1].game_pk,
        }
        if plans
        else None
    )
    exhausted = len(game_keys) < batch_size

    base_summary = {
        'capability': 'appearance_team_backfill_2026_v1',
        'mode': 'apply' if apply else 'dry_run',
        'backfill_contract_version': BACKFILL_CONTRACT_VERSION,
        'resolver_contract_version': RESOLVER_CONTRACT_VERSION,
        'season': int(season),
        'window': {'start_date': start_date.isoformat(), 'end_date': end_date.isoformat()},
        'cursor': {
            'after_game_date': after_game_date.isoformat() if after_game_date else None,
            'after_game_pk': after_game_pk,
        },
        'batch_size': batch_size,
        'games_selected': len(plans),
        'appearances_targeted': sum(len(plan.game_log_ids) for plan in plans),
        'batch_fingerprint': fingerprint,
        'next_cursor': next_cursor,
        'exhausted': exhausted,
        'database_writes_performed': False,
        'coverage_before': coverage_before,
    }

    # 2) Apply gates — checked before any mutation.
    if apply and confirmation != CONFIRMATION_PHRASE:
        return {
            **base_summary,
            'result': RESULT_REFUSED,
            'refused_reason': 'confirmation_phrase_required',
            'coverage_after': coverage_before,
        }
    if apply and expected_fingerprint is not None and expected_fingerprint != fingerprint:
        return {
            **base_summary,
            'result': RESULT_REFUSED,
            'refused_reason': 'fingerprint_mismatch',
            'expected_fingerprint': expected_fingerprint,
            'coverage_after': coverage_before,
        }

    # 3) Process each game in its own transaction.
    counts = {
        'games_processed': 0,
        'games_committed': 0,
        'games_failed': 0,
        'api_calls': 0,
        'appearances_resolved': 0,
        'appearances_unresolved': 0,
        'appearances_conflict': 0,
        'resolved_via_schedule': 0,
        'resolved_via_boxscore': 0,
        'fetch_failures': 0,
    }
    failed_games = []
    for plan in plans:
        target_rows = _target_rows_for_game(
            game_pk=plan.game_pk, start_date=start_date, end_date=end_date, session=session,
        )
        if not target_rows:
            continue
        try:
            pairs, api_called = _resolve_game(
                plan.game_pk, target_rows, client=client, allow_api=allow_api, session=session,
            )
        except Exception as exc:  # noqa: BLE001 — a single game must not abort the batch
            session.rollback()
            counts['games_failed'] += 1
            counts['fetch_failures'] += 1
            if len(failed_games) < _MAX_FAILED_GAME_DETAIL:
                failed_games.append(
                    {'game_pk': plan.game_pk, 'error_type': type(exc).__name__}
                )
            continue

        counts['games_processed'] += 1
        if api_called:
            counts['api_calls'] += 1
        for row, resolution in pairs:
            if resolution.status == ata.STATUS_RESOLVED and resolution.team_id is not None:
                counts['appearances_resolved'] += 1
                if resolution.source == ata.SOURCE_SCHEDULE:
                    counts['resolved_via_schedule'] += 1
                elif resolution.source == ata.SOURCE_BOXSCORE:
                    counts['resolved_via_boxscore'] += 1
            elif resolution.status == ata.STATUS_CONFLICT:
                counts['appearances_conflict'] += 1
            else:
                counts['appearances_unresolved'] += 1
            if apply:
                _apply_resolution(row, resolution)

        if apply:
            try:
                session.commit()
                counts['games_committed'] += 1
            except Exception as exc:  # noqa: BLE001 — isolate a bad per-game commit
                session.rollback()
                counts['games_failed'] += 1
                counts['games_processed'] -= 1
                if len(failed_games) < _MAX_FAILED_GAME_DETAIL:
                    failed_games.append(
                        {'game_pk': plan.game_pk, 'error_type': type(exc).__name__}
                    )

    if not apply:
        session.rollback()

    coverage_after = _coverage_snapshot(session, season=season)

    if coverage_after['invalid_stored_states'] > 0:
        result = RESULT_FAILED
    elif counts['games_failed'] > 0 or counts['fetch_failures'] > 0:
        result = RESULT_COMPLETED_WITH_FAILURES
    else:
        result = RESULT_COMPLETED

    return {
        **base_summary,
        'result': result,
        'database_writes_performed': bool(apply and counts['games_committed'] > 0),
        **counts,
        'failed_games': failed_games,
        'failed_game_count': len(failed_games),
        'coverage_after': coverage_after,
    }
