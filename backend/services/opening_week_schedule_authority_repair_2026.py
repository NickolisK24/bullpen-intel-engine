"""Governed repair of the 2026 opening-week schedule-authority gap.

Root cause (traced, not assumed): ``GameLog`` rows are populated per-pitcher from the
MLB per-season gameLog feed, independent of the schedule ledger. The schedule/ledger
ingestion default ``start_date`` is ``2026-03-30``, so opening-week games
2026-03-25..2026-03-29 (strictly before it) were never ingested into
``scheduled_games`` — leaving 47 completed regular-season games / 418 pitching
appearances with ``appearance_team_status IS NULL`` classified ``no_schedule_rows`` by
the merged residual audit, because ``resolve_from_schedule`` reads ``ScheduledGame``
only and finds none.

This repair restores the MISSING canonical schedule authority for exactly those 47
games from official MLB evidence, then lets the EXISTING Foundation 1/2 resolver and
backfill attribute the appearances. It never assigns ``appearance_team_id`` and never
touches ``GameLog``: authority order is
    official MLB game evidence → canonical ScheduledGame authority
    → existing Foundation 1/2 resolver → governed backfill → residual audit.

It reuses the canonical writer (``schedule_ingestion.ingest_games`` → ``_upsert_row``,
both team sides + the sibling ``SlateGame``) exactly as the ``intraday_schedule_repair``
precedent does — no parallel row shape — wrapped in the Foundation 2 governance scaffold
(dry-run default, mandatory confirmation + approved fingerprint, per-game transaction,
stop-at-first-failure, fail-closed refusals). ``CompletedGameContext`` is deliberately
NOT written here: the resolver does not read it, and schedule ingestion never generates
it — it remains the separate existing postgame/backfill path.

No migration; no performance metric; no Foundation 3.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

from models.game_log import GameLog
from models.scheduled_game import ScheduledGame
from services import appearance_team_backfill_2026 as backfill
from services import schedule_ingestion
from services.game_finality import classify_status
from services.mlb_api import mlb_client
from utils.db import db


CAPABILITY = 'opening_week_schedule_authority_repair_2026_v1'
CONFIRMATION_PHRASE = 'RUN_2026_OPENING_WEEK_SCHEDULE_REPAIR'
REPAIR_CONTRACT_VERSION = 'opening_week_schedule_authority_repair_2026.v1'
REPAIR_SOURCE = 'opening_week_schedule_repair_2026'
EXPECTED_MIGRATION_HEAD = backfill.EXPECTED_MIGRATION_HEAD

DEFAULT_SEASON = 2026
DEFAULT_CAMPAIGN_START = date(2026, 3, 25)
DEFAULT_CAMPAIGN_END = date(2026, 3, 29)
EXPECTED_GAME_COUNT = 47
EXPECTED_RESIDUAL_ROW_COUNT = 418

# The only game type this repair reconstructs (regular season). A non-'R' game fails
# closed rather than being silently reconstructed.
SUPPORTED_GAME_TYPES = ('R',)
_FINAL_STATE = ScheduledGame.STATE_FINAL

# The exact approved target set from the merged production residual audit
# (result=pass, 418 rows / 47 games, all no_schedule_rows, 2026-03-25..29). Ordered by
# (game_date, game_pk) for deterministic planning and fingerprinting. The repair NEVER
# broadens beyond this allowlist.
TARGET_GAMES = (
    (date(2026, 3, 25), 823244),
    (date(2026, 3, 26), 823081), (date(2026, 3, 26), 823163), (date(2026, 3, 26), 823325),
    (date(2026, 3, 26), 823486), (date(2026, 3, 26), 823649), (date(2026, 3, 26), 823812),
    (date(2026, 3, 26), 823974), (date(2026, 3, 26), 824218), (date(2026, 3, 26), 824541),
    (date(2026, 3, 26), 824704), (date(2026, 3, 26), 824865),
    (date(2026, 3, 27), 822839), (date(2026, 3, 27), 823162), (date(2026, 3, 27), 823243),
    (date(2026, 3, 27), 823324), (date(2026, 3, 27), 823893), (date(2026, 3, 27), 823971),
    (date(2026, 3, 27), 824216), (date(2026, 3, 27), 824946),
    (date(2026, 3, 28), 822838), (date(2026, 3, 28), 823082), (date(2026, 3, 28), 823161),
    (date(2026, 3, 28), 823241), (date(2026, 3, 28), 823323), (date(2026, 3, 28), 823488),
    (date(2026, 3, 28), 823651), (date(2026, 3, 28), 823811), (date(2026, 3, 28), 823892),
    (date(2026, 3, 28), 823973), (date(2026, 3, 28), 824213), (date(2026, 3, 28), 824540),
    (date(2026, 3, 28), 824701), (date(2026, 3, 28), 824862), (date(2026, 3, 28), 824945),
    (date(2026, 3, 29), 822837), (date(2026, 3, 29), 823079), (date(2026, 3, 29), 823160),
    (date(2026, 3, 29), 823487), (date(2026, 3, 29), 823647), (date(2026, 3, 29), 823810),
    (date(2026, 3, 29), 823891), (date(2026, 3, 29), 824215), (date(2026, 3, 29), 824538),
    (date(2026, 3, 29), 824700), (date(2026, 3, 29), 824864), (date(2026, 3, 29), 824944),
)
TARGET_GAME_PKS = frozenset(pk for _d, pk in TARGET_GAMES)
_TARGET_DATE_BY_PK = {pk: d for d, pk in TARGET_GAMES}

RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_REFUSED = 'refused'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {RESULT_PASS: 0, RESULT_REFUSED: 1, RESULT_FAIL: 1, RESULT_INCONCLUSIVE: 2}

_MAX_PREVIEW = 60


@dataclass(frozen=True)
class _GamePlan:
    game_pk: int
    game_date: str
    game_type: Optional[str]
    final_status_code: Optional[str]
    status_state: str
    home_team_id: Optional[int]
    away_team_id: Optional[int]
    doubleheader: Optional[str]
    game_number: Optional[int]
    planned_rows: tuple
    context_action: str
    reason_code: str


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _norm_abbr(value):
    return str(value or '').strip().upper()


# ── Production preconditions (read-only) ──────────────────────────────────────
def _residual_snapshot(session):
    """The current legacy-NULL population for the target game_pks."""
    rows = (
        session.query(GameLog.mlb_game_pk, GameLog.opponent_abbreviation)
        .filter(GameLog.appearance_team_status.is_(None))
        .filter(GameLog.mlb_game_pk.in_(TARGET_GAME_PKS))
        .all()
    )
    by_game = defaultdict(list)
    for game_pk, opp_abbr in rows:
        by_game[game_pk].append(opp_abbr)
    return by_game


def _games_with_existing_schedule(session):
    rows = (
        session.query(ScheduledGame.game_pk)
        .filter(ScheduledGame.game_pk.in_(TARGET_GAME_PKS))
        .distinct()
        .all()
    )
    return {pk for (pk,) in rows}


# ── Official MLB evidence (fetched once per date, cached) ─────────────────────
def _fetch_official_games(client):
    """Fetch schedule authority for each target date once; index target games by pk.

    Returns (games_by_pk, api_calls, fetch_failed). games_by_pk maps game_pk -> list of
    official game dicts (a list so duplicate/conflicting source rows are detectable).
    """
    games_by_pk: Dict[int, list] = defaultdict(list)
    api_calls = 0
    dates = sorted({d for d, _pk in TARGET_GAMES})
    for game_date in dates:
        try:
            games = client.get_schedule(
                start_date=game_date.isoformat(), end_date=game_date.isoformat(),
            ) or []
        except Exception:  # noqa: BLE001 — source unavailable is inconclusive, not fail
            return games_by_pk, api_calls, True
        api_calls += 1
        for game in games:
            pk = _positive_int((game or {}).get('gamePk'))
            if pk in TARGET_GAME_PKS:
                games_by_pk[pk].append(game)
    return games_by_pk, api_calls, False


def _team_abbr(side):
    team = ((side or {}).get('team') or {})
    return _norm_abbr(team.get('abbreviation') or team.get('teamCode') or team.get('fileCode'))


def _plan_game(game_pk, official_games, residual_opponents):
    """Validate one target game's official evidence and plan its canonical rows.

    Deterministic single reason_code; empty string means clean/plannable. Reuses the
    canonical mapper ``schedule_ingestion._parse_game`` and finality ``classify_status``.
    """
    approved_date = _TARGET_DATE_BY_PK[game_pk]
    if not official_games:
        return _fail_plan(game_pk, approved_date, 'official_evidence_missing')
    # Duplicate source rows are acceptable only if they agree on identity.
    signatures = {
        (
            _positive_int((g or {}).get('gamePk')),
            str((g or {}).get('officialDate') or (g or {}).get('gameDate') or '')[:10],
            _positive_int((((g or {}).get('teams') or {}).get('home') or {}).get('team', {}).get('id')),
            _positive_int((((g or {}).get('teams') or {}).get('away') or {}).get('team', {}).get('id')),
        )
        for g in official_games
    }
    if len(signatures) > 1:
        return _fail_plan(game_pk, approved_date, 'duplicate_conflicting_source')

    game = official_games[0]
    parsed = schedule_ingestion._parse_game(game)
    if parsed is None:
        return _fail_plan(game_pk, approved_date, 'unparseable_official_game')
    if parsed['game_date'] != approved_date:
        return _fail_plan(game_pk, approved_date, 'game_date_mismatch')
    if parsed['game_type'] not in SUPPORTED_GAME_TYPES:
        return _fail_plan(game_pk, approved_date, 'unsupported_game_type')

    status_state = classify_status((game or {}).get('status') or {}).status_state
    if status_state != _FINAL_STATE:
        return _fail_plan(game_pk, approved_date, 'non_final_game', status_state=status_state)

    home_id = _positive_int(parsed['home_team_id'])
    away_id = _positive_int(parsed['away_team_id'])
    if home_id is None:
        return _fail_plan(game_pk, approved_date, 'missing_home_team')
    if away_id is None:
        return _fail_plan(game_pk, approved_date, 'missing_away_team')

    # Contradiction check (opponent text is only a check, never the repair authority):
    # every residual appearance's stored opponent must name one of the two official
    # teams when both abbreviations are available.
    teams = (game or {}).get('teams') or {}
    team_abbrs = {a for a in (_team_abbr(teams.get('home')), _team_abbr(teams.get('away'))) if a}
    if len(team_abbrs) == 2:
        for opp_abbr in residual_opponents:
            normalized = _norm_abbr(opp_abbr)
            if normalized and normalized not in team_abbrs:
                return _fail_plan(game_pk, approved_date, 'contradictory_opponent_evidence')

    planned_rows = (
        {'team_id': home_id, 'opponent_team_id': away_id, 'home_away': 'home'},
        {'team_id': away_id, 'opponent_team_id': home_id, 'home_away': 'away'},
    )
    return _GamePlan(
        game_pk=game_pk,
        game_date=approved_date.isoformat(),
        game_type=parsed['game_type'],
        final_status_code=parsed['status_code'],
        status_state=status_state,
        home_team_id=home_id,
        away_team_id=away_id,
        doubleheader=parsed['doubleheader'],
        game_number=parsed['game_number'],
        planned_rows=planned_rows,
        context_action='skipped_not_required',
        reason_code='',
    )


def _fail_plan(game_pk, approved_date, reason_code, *, status_state='') -> _GamePlan:
    return _GamePlan(
        game_pk=game_pk, game_date=approved_date.isoformat(), game_type=None,
        final_status_code=None, status_state=status_state, home_team_id=None,
        away_team_id=None, doubleheader=None, game_number=None, planned_rows=(),
        context_action='none', reason_code=reason_code,
    )


# ── Fingerprint ───────────────────────────────────────────────────────────────
def _game_fingerprint_entry(plan: _GamePlan) -> dict:
    return {
        'game_pk': plan.game_pk,
        'official_date': plan.game_date,
        'game_type': plan.game_type,
        'final_status_code': plan.final_status_code,
        'status_state': plan.status_state,
        'home_team_id': plan.home_team_id,
        'away_team_id': plan.away_team_id,
        'doubleheader': plan.doubleheader,
        'game_number': plan.game_number,
        'planned_rows': [dict(row) for row in plan.planned_rows],
        'context_action': plan.context_action,
    }


def _repair_fingerprint(*, plans, season, campaign_start, campaign_end,
                        expected_game_count, expected_residual_row_count, migration_head):
    canonical = {
        'repair_contract_version': REPAIR_CONTRACT_VERSION,
        'resolver_contract_version': backfill.RESOLVER_CONTRACT_VERSION,
        'season': int(season),
        'campaign_start_date': campaign_start.isoformat(),
        'campaign_end_date': campaign_end.isoformat(),
        'expected_game_count': int(expected_game_count),
        'expected_residual_row_count': int(expected_residual_row_count),
        'target_game_pks': [pk for _d, pk in TARGET_GAMES],
        'migration_head': migration_head,
        'games': [_game_fingerprint_entry(plan) for plan in plans],
    }
    return backfill._sha256_json(canonical)


# ── Persistence (apply only) — reuse the canonical ingester ───────────────────
def _apply_game(game_pk, official_games, ingester, session):
    """Persist one game's canonical schedule rows via the existing ingester.

    Delegates to schedule_ingestion.ingest_games (both ScheduledGame sides + the sibling
    SlateGame) with commit=False, then commits this game's transaction. Never writes
    GameLog. Returns rows_created for the game; raises on ingester error.
    """
    summary = ingester([official_games[0]], source=REPAIR_SOURCE, commit=False)
    if int((summary or {}).get('errors') or 0) > 0:
        session.rollback()
        raise RuntimeError('schedule_ingestion_reported_errors')
    session.commit()
    return int((summary or {}).get('rows_created') or 0)


# ── Public entry point ────────────────────────────────────────────────────────
def run_repair(
    *,
    season: int = DEFAULT_SEASON,
    campaign_start_date: date = DEFAULT_CAMPAIGN_START,
    campaign_end_date: date = DEFAULT_CAMPAIGN_END,
    expected_game_count: int = EXPECTED_GAME_COUNT,
    expected_residual_row_count: int = EXPECTED_RESIDUAL_ROW_COUNT,
    apply: bool = False,
    confirmation: Optional[str] = None,
    expected_fingerprint: Optional[str] = None,
    generated_at: Optional[str] = None,
    client=mlb_client,
    ingester=None,
    session=None,
) -> dict:
    """Plan (dry run) or perform (apply) the opening-week schedule-authority repair."""
    session = session or db.session
    ingester = ingester or schedule_ingestion.ingest_games
    if campaign_end_date < campaign_start_date:
        raise ValueError('campaign_end_date must not be before campaign_start_date')

    migration_head = backfill._migration_head(session)
    invalid_before = backfill._invalid_stored_state_count(session)

    residual_by_game = _residual_snapshot(session)
    residual_games = set(residual_by_game)
    residual_rows = sum(len(v) for v in residual_by_game.values())
    existing_schedule_games = _games_with_existing_schedule(session)

    official_by_pk, api_calls, fetch_failed = _fetch_official_games(client)

    plans = [
        _plan_game(pk, official_by_pk.get(pk, []), residual_by_game.get(pk, []))
        for _d, pk in TARGET_GAMES
    ]

    fingerprint = _repair_fingerprint(
        plans=plans, season=season, campaign_start=campaign_start_date,
        campaign_end=campaign_end_date, expected_game_count=expected_game_count,
        expected_residual_row_count=expected_residual_row_count, migration_head=migration_head,
    )

    reasons = []
    if migration_head is not None and migration_head != [EXPECTED_MIGRATION_HEAD]:
        reasons.append('migration_head_mismatch')
    if invalid_before > 0:
        reasons.append('invalid_stored_states')
    if residual_games != TARGET_GAME_PKS:
        reasons.append('residual_game_set_mismatch')
    if residual_rows != expected_residual_row_count:
        reasons.append('residual_row_count_mismatch')
    if len(residual_games) != expected_game_count:
        reasons.append('residual_game_count_mismatch')
    if existing_schedule_games:
        reasons.append('target_game_already_has_schedule')
    plan_reason_codes = sorted({p.reason_code for p in plans if p.reason_code})
    reasons.extend(plan_reason_codes)

    official = {
        'games_fetched': sum(1 for _d, pk in TARGET_GAMES if official_by_pk.get(pk)),
        'api_calls': api_calls,
        'final_games': sum(1 for p in plans if p.status_state == _FINAL_STATE),
        'non_final_games': sum(1 for p in plans if p.reason_code == 'non_final_game'),
        'regular_season_games': sum(1 for p in plans if p.game_type in SUPPORTED_GAME_TYPES),
        'unsupported_game_types': sum(1 for p in plans if p.reason_code == 'unsupported_game_type'),
        'missing_home_team': sum(1 for p in plans if p.reason_code == 'missing_home_team'),
        'missing_away_team': sum(1 for p in plans if p.reason_code == 'missing_away_team'),
        'contradictory_games': sum(1 for p in plans if p.reason_code == 'contradictory_opponent_evidence'),
        'duplicate_conflicting_games': sum(1 for p in plans if p.reason_code == 'duplicate_conflicting_source'),
        'missing_evidence_games': sum(1 for p in plans if p.reason_code == 'official_evidence_missing'),
    }
    clean_plans = [p for p in plans if not p.reason_code]
    planned_schedule_rows = sum(len(p.planned_rows) for p in clean_plans)

    base = {
        'capability': CAPABILITY,
        'mode': 'apply' if apply else 'dry_run',
        'repair_contract_version': REPAIR_CONTRACT_VERSION,
        'generated_at': generated_at,
        'git_sha': _git_sha(),
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'inputs': {
            'season': int(season),
            'campaign_start_date': campaign_start_date.isoformat(),
            'campaign_end_date': campaign_end_date.isoformat(),
            'expected_game_count': int(expected_game_count),
            'expected_residual_row_count': int(expected_residual_row_count),
        },
        'target_games': {
            'count': len(TARGET_GAMES),
            'ordered_game_pks': [pk for _d, pk in TARGET_GAMES],
        },
        'production_preconditions': {
            'residual_rows': residual_rows,
            'residual_games': len(residual_games),
            'invalid_stored_states': invalid_before,
            'games_already_with_schedule': len(existing_schedule_games),
            'games_with_conflicting_schedule': len(existing_schedule_games),
        },
        'official_evidence': official,
        'planned_schedule_rows': {
            'row_count': planned_schedule_rows,
            'game_count': len(clean_plans),
        },
        'planned_completed_context': {
            'create_count': 0,
            'refresh_count': 0,
            'skipped_count': len(TARGET_GAMES),
        },
        'bounded_game_preview': [
            {
                'game_pk': p.game_pk,
                'game_date': p.game_date,
                'game_type': p.game_type,
                'final_status': p.status_state,
                'home_team_id': p.home_team_id,
                'away_team_id': p.away_team_id,
                'planned_schedule_row_count': len(p.planned_rows),
                'planned_context_action': p.context_action,
                'safe_reason_code': p.reason_code or 'plannable',
            }
            for p in plans[:_MAX_PREVIEW]
        ],
        'fingerprint': fingerprint,
        'database_writes_performed': False,
    }

    def _finish(result, decision_reasons, next_step, extra=None):
        payload = {
            **base,
            'result': result,
            'exit_code': EXIT_BY_RESULT[result],
            'decision_reasons': decision_reasons,
            'next_step': next_step,
        }
        if extra:
            payload.update(extra)
        return payload

    # 1) Empty / already-repaired population, or a temporarily unavailable source.
    if residual_rows == 0 and not existing_schedule_games:
        return _finish(RESULT_INCONCLUSIVE, ['no_residual_population'], 'none')
    if fetch_failed:
        return _finish(RESULT_INCONCLUSIVE, ['official_source_unavailable'], 'retry_when_source_available')

    # 2) Any refusal reason fails the run (dry run or apply) with no write.
    if reasons:
        return _finish(RESULT_FAIL, sorted(set(reasons)), 'resolve_blocking_conditions')

    # 3) Apply gates — mandatory, checked before any write.
    if apply:
        if confirmation != CONFIRMATION_PHRASE:
            return _finish(RESULT_REFUSED, ['confirmation_phrase_required'], 'supply_confirmation')
        if not expected_fingerprint:
            return _finish(RESULT_REFUSED, ['approved_fingerprint_required'], 'supply_approved_fingerprint')
        if expected_fingerprint != fingerprint:
            return _finish(RESULT_REFUSED, ['fingerprint_mismatch'], 'rerun_dry_run',
                           extra={'expected_fingerprint': expected_fingerprint})

    # 4) Dry run: clean, no writes.
    if not apply:
        return _finish(RESULT_PASS, ['schedule_authority_repair_ready'],
                       'run_apply_then_foundation_2_backfill')

    # 5) Apply: per-game canonical ingest, per-game commit, stop at first failure.
    writes = {'games_committed': 0, 'schedule_rows_written': 0, 'failed_game_count': 0}
    failed_games = []
    for _d, pk in TARGET_GAMES:
        try:
            created = _apply_game(pk, official_by_pk.get(pk, []), ingester, session)
        except Exception as exc:  # noqa: BLE001 — isolate + stop on first failure
            session.rollback()
            writes['failed_game_count'] += 1
            failed_games.append({'game_pk': pk, 'error_type': type(exc).__name__})
            break
        writes['games_committed'] += 1
        writes['schedule_rows_written'] += created

    invalid_after = backfill._invalid_stored_state_count(session)
    writes_performed = writes['games_committed'] > 0
    if invalid_after > 0:
        result, decision = RESULT_FAIL, ['invalid_stored_states_after_apply']
    elif writes['failed_game_count'] > 0:
        result, decision = RESULT_FAIL, ['game_apply_failure']
    else:
        result, decision = RESULT_PASS, ['schedule_authority_repaired']
    return _finish(
        result, decision, 'run_foundation_2_backfill_dry_run',
        extra={'database_writes_performed': writes_performed, **writes,
               'failed_games': failed_games, 'invalid_stored_states_after': invalid_after},
    )


def _git_sha():
    import os
    return os.environ.get('GITHUB_SHA')
