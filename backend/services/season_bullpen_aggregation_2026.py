"""Canonical 2026 season bullpen aggregation + independent official-MLB validation.

Foundation 3A. This is the SINGLE canonical backend authority for team-level season
bullpen performance. It aggregates completed regular-season RELIEF appearances using the
historical team authority ``GameLog.appearance_team_id`` (Foundation 1) — never
``Pitcher.team_id``, current roster, current organization, current role, or current
bullpen assignment.

It is a pure, deterministic, READ-ONLY read model over canonical stored data:
    official appearance-team authority (GameLog.appearance_team_id, resolved only)
    + official start signal (GameLog.games_started == 0 => relief)
    + integer outs (GameLog.innings_pitched_outs)
    + canonical finality (game_finality.classify_status + ScheduledGame STATE_FINAL)
    => per-team bullpen workload + performance totals, reconciled team<->league.

An optional INDEPENDENT validator re-derives relief totals directly from official MLB
box scores (official starter excluded, all other pitchers summed as relief) and compares
them EXACTLY to the local aggregation. No public metric ships until that validation
matches every mandatory team and league total in production.

Boundaries (Foundation 3A): no migration, no persistence, no rankings, no public reader,
no public API/frontend change, no Team State / Share Card change, no predictions. Public
exposure remains blocked here.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Optional, Tuple

from models.game_log import GameLog
from models.scheduled_game import ScheduledGame
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import appearance_team_backfill_2026 as backfill
from services.game_finality import classify_status, FINAL_STATUS_STATE
from services.mlb_api import mlb_client
from utils.db import db
from utils.games_started import games_started_state, START, UNKNOWN
from utils.innings import parse_mlb_innings_to_outs


CAPABILITY = 'canonical_season_bullpen_aggregation_2026_v1'
AGGREGATION_CONTRACT_VERSION = 'canonical_season_bullpen_aggregation_2026.v1'
RELIEF_CLASSIFICATION_CONTRACT = 'games_started==0 (official gamesStarted); starter=1; null=unknown'
APPEARANCE_TEAM_CONTRACT = backfill.RESOLVER_CONTRACT_VERSION
FINALITY_CONTRACT = 'game_finality.classify_status:final + ScheduledGame.STATE_FINAL'
EXPECTED_MIGRATION_HEAD = backfill.EXPECTED_MIGRATION_HEAD

DEFAULT_SEASON = 2026
DEFAULT_AS_OF_DATE = date(2026, 7, 25)
REGULAR_SEASON_GAME_TYPE = 'R'
_FINAL = ScheduledGame.STATE_FINAL

DEFAULT_TEAM_DETAIL_LIMIT = 40
DEFAULT_MISMATCH_DETAIL_LIMIT = 60
MAX_DETAIL_LIMIT = 200

RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {RESULT_PASS: 0, RESULT_FAIL: 1, RESULT_INCONCLUSIVE: 2}

# The metric-support matrix (from the Foundation 3A source investigation). Every proposed
# metric is classified against repository evidence; nothing is invented to fill it.
METRIC_SUPPORT = {
    'final_regular_season_games': 'supported',
    'team_games_with_relief_usage': 'supported',
    'relief_appearances': 'supported',
    'unique_relievers': 'supported',
    'bullpen_outs': 'supported_with_validation',
    'bullpen_innings_display': 'supported_with_validation',
    'runs_allowed': 'supported_with_validation',
    'earned_runs': 'supported_with_validation',
    'hits_allowed': 'supported_with_validation',
    'walks': 'supported_with_validation',
    'strikeouts': 'supported_with_validation',
    'home_runs_allowed': 'supported_with_validation',
    'bullpen_era': 'supported_with_validation',
    # Optional, source-backed:
    'batters_faced': 'supported_with_validation',  # official battersFaced, NULL-aware
    'saves': 'supported',                          # official 'saves' flag projection
    'blown_saves': 'supported',                    # official 'blownSaves' flag projection
    'holds': 'supported',                          # official 'holds' flag projection
    # Unsupported (no clean/complete official per-appearance source):
    'hit_batters': 'blocked_by_missing_source',
    'inherited_runners': 'unsupported',
    'inherited_runners_scored': 'unsupported',
}

# The mandatory counting metrics compared EXACTLY against the independent validator. ERA is
# validated through its components (earned_runs + bullpen_outs), never by a rounded value.
MANDATORY_COUNTING_METRICS = (
    'relief_appearances',
    'bullpen_outs',
    'runs_allowed',
    'earned_runs',
    'hits_allowed',
    'walks',
    'strikeouts',
    'home_runs_allowed',
)
INHERITED_RUNNER_REASON = 'inherited_runner_evidence_not_available'
HIT_BATTERS_REASON = 'hit_batters_source_not_stored'

TRUST_COMPLETE = 'complete'
TRUST_PARTIAL = 'partial'
TRUST_UNAVAILABLE = 'unavailable'


# ── Pure metric helpers ───────────────────────────────────────────────────────
def _innings_display(outs: int) -> str:
    """Baseball innings notation from integer outs (never sums decimal innings)."""
    whole, remainder = divmod(int(outs), 3)
    return f'{whole}.{remainder}'


def _era_components(earned_runs: int, outs: int) -> dict:
    """Exact ERA components. ERA = earned_runs * 27 / outs; unavailable when outs == 0."""
    numerator = int(earned_runs) * 27
    denominator = int(outs)
    if denominator <= 0:
        return {
            'exact_numerator': numerator,
            'exact_denominator': denominator,
            'era': None,
            'reason_code': 'era_denominator_zero',
        }
    era = (Decimal(numerator) / Decimal(denominator)).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP)
    return {
        'exact_numerator': numerator,
        'exact_denominator': denominator,
        'era': str(era),
        'reason_code': None,
    }


def _clamp_limit(value, default):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(0, min(parsed, MAX_DETAIL_LIMIT))


def _pos_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


# ── Canonical schedule authority (final regular-season games) ─────────────────
@dataclass(frozen=True)
class _FinalGame:
    game_pk: int
    team_ids: frozenset
    game_date: date


# Canonical schedule-authority classes for a game_pk in scope.
SCHED_FINAL_R = 'final_r'          # all rows final AND 'R' — the only aggregatable class
SCHED_NON_FINAL = 'non_final'      # uniform but not final-R (scheduled/postponed/suspended/non-R)
SCHED_CONTRADICTORY = 'contradictory'  # the game's rows disagree on finality or type
# A game_pk absent from the class map has NO ScheduledGame authority => missing (blocking).


def _schedule_authority(session, *, season, as_of_date):
    """Classify every scope game_pk's canonical schedule authority.

    Returns (final_games, sched_class). ``final_games`` maps a final regular-season game_pk to
    its ``_FinalGame`` (both team ids). ``sched_class`` maps every game_pk that HAS ScheduledGame
    rows to exactly one of final_r / non_final / contradictory. A game_pk with NO rows is absent
    from ``sched_class`` — that absence is the MISSING-authority case, which blocks a PASS
    (missing evidence is never a harmless exclusion). Doubleheaders stay distinct by game_pk.
    """
    season_start = date(season, 1, 1)
    rows = (
        session.query(
            ScheduledGame.game_pk, ScheduledGame.team_id,
            ScheduledGame.status_state, ScheduledGame.game_type, ScheduledGame.game_date,
        )
        .filter(ScheduledGame.game_date >= season_start)
        .filter(ScheduledGame.game_date <= as_of_date)
        .all()
    )
    by_pk: Dict[int, list] = defaultdict(list)
    for game_pk, team_id, status_state, game_type, game_date in rows:
        by_pk[game_pk].append((team_id, status_state, game_type, game_date))
    final_games: Dict[int, _FinalGame] = {}
    sched_class: Dict[int, str] = {}
    for game_pk, sides in by_pk.items():
        states = {s[1] for s in sides}
        types = {s[2] for s in sides}
        if len(states) > 1 or len(types) > 1:
            # The two sides disagree on finality or game type — contradictory authority.
            sched_class[game_pk] = SCHED_CONTRADICTORY
            continue
        if states == {_FINAL} and types == {REGULAR_SEASON_GAME_TYPE}:
            team_ids = frozenset(s[0] for s in sides if s[0] is not None)
            game_date = min(s[3] for s in sides if s[3] is not None)
            final_games[game_pk] = _FinalGame(game_pk, team_ids, game_date)
            sched_class[game_pk] = SCHED_FINAL_R
        else:
            sched_class[game_pk] = SCHED_NON_FINAL
    return final_games, sched_class


def _scope_rows(session, *, season, as_of_date):
    """Every candidate GameLog row in scope: regular season, in season, on/before as_of."""
    season_start = date(season, 1, 1)
    season_end = date(season, 12, 31)
    return (
        session.query(GameLog)
        .filter(GameLog.game_type == REGULAR_SEASON_GAME_TYPE)
        .filter(GameLog.game_date >= season_start)
        .filter(GameLog.game_date <= season_end)
        .filter(GameLog.game_date <= as_of_date)
        .order_by(GameLog.mlb_game_pk.asc(), GameLog.pitcher_id.asc())
        .all()
    )


def _splits_by_team_game(session, *, season, as_of_date) -> Dict[Tuple[int, int], TeamGamePitchingSplit]:
    season_start = date(season, 1, 1)
    rows = (
        session.query(TeamGamePitchingSplit)
        .filter(TeamGamePitchingSplit.game_type == REGULAR_SEASON_GAME_TYPE)
        .filter(TeamGamePitchingSplit.game_date >= season_start)
        .filter(TeamGamePitchingSplit.game_date <= as_of_date)
        .all()
    )
    return {(r.team_id, r.mlb_game_pk): r for r in rows}


# ── Row classification (inclusion / exclusion / blocking) ─────────────────────
@dataclass
class _RowDecision:
    disposition: str          # 'included_relief' | 'excluded_starter' | 'excluded'
    reason_code: str          # '' for a clean included row
    blocking: str = ''        # '' | 'fail' | 'inconclusive'


def _classify_row(log, final_games, sched_class, seen_keys) -> _RowDecision:
    """Classify one in-scope GameLog row deterministically."""
    game_pk = log.mlb_game_pk
    if game_pk is None:
        return _RowDecision('excluded', 'game_pk_missing')

    key = (log.pitcher_id, game_pk)
    if key in seen_keys:
        # DB unique (pitcher_id, game_pk) makes this unreachable in stored data; still a
        # fail-closed integrity guard.
        return _RowDecision('excluded', 'duplicate_appearance', blocking='fail')
    seen_keys.add(key)

    cls = sched_class.get(game_pk)
    if cls is None:
        # In scope but NO canonical ScheduledGame authority. A canonical season aggregation
        # must never silently omit an in-scope appearance for want of schedule authority, so
        # this is a BLOCKING evidence gap (inconclusive), not a harmless exclusion.
        return _RowDecision('excluded', 'schedule_authority_missing', blocking='inconclusive')
    if cls == SCHED_CONTRADICTORY:
        return _RowDecision('excluded', 'contradictory_game_authority', blocking='fail')
    if cls == SCHED_NON_FINAL:
        # A legitimately non-final / postponed / suspended-without-final / non-R game. Its
        # appearances never contribute, and this is deliberately distinct from missing
        # authority so the two cannot be confused.
        return _RowDecision('excluded', 'game_not_final')

    final_game = final_games[game_pk]
    status = log.appearance_team_status
    if status is None:
        return _RowDecision('excluded', 'legacy_null_appearance', blocking='fail')
    if status == GameLog.APPEARANCE_TEAM_UNRESOLVED:
        return _RowDecision('excluded', 'appearance_team_not_resolved', blocking='fail')
    if status == GameLog.APPEARANCE_TEAM_CONFLICT:
        return _RowDecision('excluded', 'contradictory_game_authority', blocking='fail')
    if status != GameLog.APPEARANCE_TEAM_RESOLVED or log.appearance_team_id is None:
        return _RowDecision('excluded', 'appearance_team_missing', blocking='fail')

    if log.appearance_team_id not in final_game.team_ids:
        # The represented team is not one of the two teams that played this game — a
        # cross-team leakage / starter-contamination class integrity failure.
        return _RowDecision('excluded', 'appearance_team_not_in_game', blocking='fail')

    outs = log.innings_pitched_outs
    if outs is None or int(outs) < 0:
        return _RowDecision('excluded', 'innings_outs_invalid', blocking='fail')

    state = games_started_state(log.games_started)
    if state == UNKNOWN:
        # Cannot prove starter vs relief for a completed regular-season game.
        return _RowDecision('excluded', 'starter_identity_unknown', blocking='inconclusive')
    if state == START:
        return _RowDecision('excluded_starter', 'starter_excluded')
    return _RowDecision('included_relief', '')


# ── Team aggregation ──────────────────────────────────────────────────────────
@dataclass
class _TeamAccumulator:
    team_id: int
    relief_appearances: int = 0
    bullpen_outs: int = 0
    runs_allowed: int = 0
    earned_runs: int = 0
    hits_allowed: int = 0
    walks: int = 0
    strikeouts: int = 0
    home_runs_allowed: int = 0
    saves: int = 0
    blown_saves: int = 0
    holds: int = 0
    batters_faced_sum: int = 0
    batters_faced_missing: int = 0
    relievers: set = field(default_factory=set)
    relief_game_pks: set = field(default_factory=set)
    game_outs: dict = field(default_factory=dict)


def _accumulate_team(acc: _TeamAccumulator, log):
    acc.relief_appearances += 1
    acc.bullpen_outs += int(log.innings_pitched_outs)
    acc.runs_allowed += int(log.runs_allowed or 0)
    acc.earned_runs += int(log.earned_runs or 0)
    acc.hits_allowed += int(log.hits_allowed or 0)
    acc.walks += int(log.walks or 0)
    acc.strikeouts += int(log.strikeouts or 0)
    acc.home_runs_allowed += int(log.home_runs_allowed or 0)
    acc.saves += 1 if log.save else 0
    acc.blown_saves += 1 if log.blown_save else 0
    acc.holds += 1 if log.hold else 0
    if log.batters_faced is None:
        acc.batters_faced_missing += 1
    else:
        acc.batters_faced_sum += int(log.batters_faced)
    acc.relievers.add(log.pitcher_id)
    acc.relief_game_pks.add(log.mlb_game_pk)
    acc.game_outs[log.mlb_game_pk] = acc.game_outs.get(log.mlb_game_pk, 0) + int(log.innings_pitched_outs)


def _team_final_game_counts(final_games) -> Dict[int, set]:
    per_team: Dict[int, set] = defaultdict(set)
    for game in final_games.values():
        for team_id in game.team_ids:
            per_team[team_id].add(game.game_pk)
    return per_team


def _optional_metric(support, value, reason_code=None):
    return {'support_status': support, 'value': value, 'reason_code': reason_code}


def _build_team_result(acc: _TeamAccumulator, *, final_game_pks, splits, team_name, team_abbr,
                       season, as_of_date):
    era = _era_components(acc.earned_runs, acc.bullpen_outs)

    # Canonical (appearance-team-correct) reconciliation: the team's relief outs summed at the
    # GAME grain must equal the same outs summed at the TEAM grain. This is the ONLY
    # reconciliation that governs trust — it never leaks current-team data.
    canonical_game_grain = sum(acc.game_outs.values())
    canonical_team_grain = acc.bullpen_outs
    canonical_outs_match = (canonical_game_grain == canonical_team_grain)

    # team_game_pitching_splits.bullpen_outs_recorded is grouped by CURRENT Pitcher.team_id
    # (documented Foundation-0 leakage), so it is a NON-GOVERNING diagnostic only: it never
    # marks a team partial/unavailable, never gates a PASS, and never changes a gate. A
    # divergence or a missing split cannot alter canonical trust.
    split_observed = None
    for game_pk in sorted(acc.relief_game_pks):
        row = splits.get((acc.team_id, game_pk))
        if row is not None and row.bullpen_outs_recorded is not None:
            split_observed = (split_observed or 0) + int(row.bullpen_outs_recorded)

    reasons = []
    if acc.relief_appearances == 0:
        trust = TRUST_UNAVAILABLE
        reasons.append('no_relief_appearances')
    elif not canonical_outs_match:
        trust = TRUST_PARTIAL
        reasons.append('canonical_outs_mismatch')
    else:
        trust = TRUST_COMPLETE

    batters_faced_metric = (
        _optional_metric('unsupported', None, 'batters_faced_incomplete')
        if acc.batters_faced_missing > 0
        else _optional_metric('supported', acc.batters_faced_sum)
    )

    return {
        'team': {'mlb_id': acc.team_id, 'name': team_name, 'abbreviation': team_abbr},
        'scope': {
            'season': int(season),
            'as_of_date': as_of_date.isoformat(),
            'game_type': REGULAR_SEASON_GAME_TYPE,
            'data_through_date': as_of_date.isoformat(),
        },
        'coverage': {
            'eligible_team_games': len(final_game_pks),
            'complete_team_games': len(final_game_pks),
            'excluded_team_games': 0,
            'relief_rows_included': acc.relief_appearances,
            'unique_relievers': len(acc.relievers),
            'team_games_with_relief_usage': len(acc.relief_game_pks),
        },
        'workload': {
            'bullpen_outs': acc.bullpen_outs,
            'bullpen_innings_display': _innings_display(acc.bullpen_outs),
            'relief_appearances': acc.relief_appearances,
        },
        'performance': {
            'runs_allowed': acc.runs_allowed,
            'earned_runs': acc.earned_runs,
            'hits_allowed': acc.hits_allowed,
            'walks': acc.walks,
            'strikeouts': acc.strikeouts,
            'home_runs_allowed': acc.home_runs_allowed,
            'bullpen_era': era['era'],
            'bullpen_era_numerator': era['exact_numerator'],
            'bullpen_era_denominator': era['exact_denominator'],
            'bullpen_era_reason_code': era['reason_code'],
        },
        'optional_metrics': {
            'batters_faced': batters_faced_metric,
            'saves': _optional_metric('supported', acc.saves),
            'blown_saves': _optional_metric('supported', acc.blown_saves),
            'holds': _optional_metric('supported', acc.holds),
            'hit_batters': _optional_metric('blocked_by_missing_source', None, HIT_BATTERS_REASON),
            'inherited_runners': _optional_metric('unsupported', None, INHERITED_RUNNER_REASON),
            'inherited_runners_scored': _optional_metric('unsupported', None, INHERITED_RUNNER_REASON),
        },
        'trust': {
            'status': trust,
            'reason_codes': sorted(set(reasons)),
            'source_contract_version': APPEARANCE_TEAM_CONTRACT,
            'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION,
        },
        'reconciliation': {
            'canonical_game_grain_bullpen_outs': canonical_game_grain,
            'canonical_team_grain_bullpen_outs': canonical_team_grain,
            'canonical_outs_match': canonical_outs_match,
            'current_team_split_diagnostic': {
                'support_status': 'unsupported',
                'reason_code': 'current_team_leakage',
                'observed_value': split_observed,
            },
        },
    }


# ── Local aggregation ─────────────────────────────────────────────────────────
def _aggregate_local(session, *, season, as_of_date, team_names=None):
    team_names = team_names or {}
    final_games, sched_class = _schedule_authority(session, season=season, as_of_date=as_of_date)
    scope = _scope_rows(session, season=season, as_of_date=as_of_date)
    splits = _splits_by_team_game(session, season=season, as_of_date=as_of_date)

    seen_keys: set = set()
    accumulators: Dict[int, _TeamAccumulator] = {}
    game_relief_outs: Dict[int, int] = defaultdict(int)
    excluded_by_reason: Dict[str, int] = defaultdict(int)
    fail_reasons: set = set()
    inconclusive_reasons: set = set()
    counts = {
        'source_rows': len(scope),
        'included_relief_rows': 0,
        'excluded_rows': 0,
        'starter_rows_excluded': 0,
        'duplicate_rows': 0,
        'unresolved_rows': 0,
        'conflict_rows': 0,
        'legacy_null_rows': 0,
        'invalid_state_rows': 0,
        'missing_starter_identity_games': 0,
        'schedule_authority_missing_rows': 0,
        'schedule_authority_missing_games': 0,
    }
    missing_starter_games: set = set()
    schedule_missing_games: set = set()

    for log in scope:
        decision = _classify_row(log, final_games, sched_class, seen_keys)
        if decision.blocking == 'fail':
            fail_reasons.add(decision.reason_code)
        elif decision.blocking == 'inconclusive':
            inconclusive_reasons.add(decision.reason_code)

        if decision.reason_code == 'duplicate_appearance':
            counts['duplicate_rows'] += 1
        if decision.reason_code == 'appearance_team_not_resolved':
            counts['unresolved_rows'] += 1
        if decision.reason_code == 'contradictory_game_authority':
            counts['conflict_rows'] += 1
        if decision.reason_code == 'legacy_null_appearance':
            counts['legacy_null_rows'] += 1
        if decision.reason_code in ('innings_outs_invalid', 'appearance_team_not_in_game',
                                    'appearance_team_missing'):
            counts['invalid_state_rows'] += 1
        if decision.reason_code == 'starter_identity_unknown':
            missing_starter_games.add(log.mlb_game_pk)
        if decision.reason_code == 'schedule_authority_missing':
            counts['schedule_authority_missing_rows'] += 1
            schedule_missing_games.add(log.mlb_game_pk)

        if decision.disposition == 'included_relief':
            counts['included_relief_rows'] += 1
            acc = accumulators.setdefault(log.appearance_team_id, _TeamAccumulator(log.appearance_team_id))
            _accumulate_team(acc, log)
            game_relief_outs[log.mlb_game_pk] += int(log.innings_pitched_outs)
        elif decision.disposition == 'excluded_starter':
            counts['starter_rows_excluded'] += 1
        else:
            counts['excluded_rows'] += 1
            excluded_by_reason[decision.reason_code] += 1

    counts['missing_starter_identity_games'] = len(missing_starter_games)
    counts['schedule_authority_missing_games'] = len(schedule_missing_games)

    team_final_games = _team_final_game_counts(final_games)
    expected_team_ids = sorted(team_final_games)

    teams = []
    for team_id in sorted(set(expected_team_ids) | set(accumulators)):
        acc = accumulators.get(team_id) or _TeamAccumulator(team_id)
        name, abbr = (team_names.get(team_id) or (None, None))
        teams.append(_build_team_result(
            acc, final_game_pks=team_final_games.get(team_id, set()),
            splits=splits, team_name=name, team_abbr=abbr,
            season=season, as_of_date=as_of_date))

    return {
        'final_games': final_games,
        'accumulators': accumulators,
        'game_relief_outs': dict(game_relief_outs),
        'expected_team_ids': expected_team_ids,
        'teams': teams,
        'counts': counts,
        'excluded_by_reason': dict(sorted(excluded_by_reason.items())),
        'fail_reasons': fail_reasons,
        'inconclusive_reasons': inconclusive_reasons,
    }


def _league_totals(accumulators) -> dict:
    total = {m: 0 for m in ('relief_appearances', 'bullpen_outs', 'runs_allowed',
                            'earned_runs', 'hits_allowed', 'walks', 'strikeouts',
                            'home_runs_allowed')}
    for acc in accumulators.values():
        total['relief_appearances'] += acc.relief_appearances
        total['bullpen_outs'] += acc.bullpen_outs
        total['runs_allowed'] += acc.runs_allowed
        total['earned_runs'] += acc.earned_runs
        total['hits_allowed'] += acc.hits_allowed
        total['walks'] += acc.walks
        total['strikeouts'] += acc.strikeouts
        total['home_runs_allowed'] += acc.home_runs_allowed
    return total


# ── Independent official-MLB validator ────────────────────────────────────────
def _ip_stat_to_outs(stats) -> int:
    return parse_mlb_innings_to_outs((stats or {}).get('inningsPitched', '0.0'))


def _int_box_stat(stats, key) -> int:
    try:
        return int((stats or {}).get(key) or 0)
    except (TypeError, ValueError):
        return 0


STARTER_UNIQUE = 'unique'
STARTER_MISSING = 'missing'
STARTER_CONTRADICTORY = 'contradictory'


def _official_starter(side) -> Tuple[str, Optional[int]]:
    """Identify one box-score side's official starter STRICTLY by gamesStarted == 1.

    Returns (status, pid): 'unique' with the starter pid when EXACTLY one pitching line marks
    the start; 'missing' when zero do; 'contradictory' when more than one does. Pitcher-array
    position is NEVER used — order is not authoritative starter evidence, and there is no
    first-pitcher / appearance-order / innings / role / current-team fallback.
    """
    players = (side or {}).get('players') or {}
    ordered = [pid for pid in ((side or {}).get('pitchers') or []) if pid is not None]
    starters = []
    for pid in ordered:
        stats = ((players.get(f'ID{pid}') or {}).get('stats') or {}).get('pitching') or {}
        if games_started_state(stats.get('gamesStarted')) == START:
            starters.append(int(pid))
    if len(starters) == 1:
        return STARTER_UNIQUE, starters[0]
    if len(starters) == 0:
        return STARTER_MISSING, None
    return STARTER_CONTRADICTORY, None


def _official_relief_for_side(side) -> Optional[dict]:
    """Independently sum a side's RELIEF pitching from the official box score.

    Official starter evidence is evaluated BEFORE any relief total is accepted: a side without
    a unique gamesStarted==1 starter yields no relief totals, only its starter_status.
    """
    team = (side or {}).get('team') or {}
    team_id = team.get('id')
    if team_id is None:
        return None
    players = (side or {}).get('players') or {}
    ordered = [pid for pid in ((side or {}).get('pitchers') or []) if pid is not None]
    if not ordered:
        return None
    starter_status, starter_pid = _official_starter(side)
    base = {'team_id': int(team_id), 'team_name': team.get('name'),
            'starter_status': starter_status}
    if starter_status != STARTER_UNIQUE:
        # No trustworthy starter => no relief totals accepted for this team-game.
        return base
    totals = {**base, 'relief_appearances': 0, 'bullpen_outs': 0, 'runs_allowed': 0,
              'earned_runs': 0, 'hits_allowed': 0, 'walks': 0, 'strikeouts': 0,
              'home_runs_allowed': 0}
    for pid in ordered:
        if int(pid) == starter_pid:
            continue
        stats = ((players.get(f'ID{pid}') or {}).get('stats') or {}).get('pitching') or {}
        totals['relief_appearances'] += 1
        totals['bullpen_outs'] += _ip_stat_to_outs(stats)
        totals['runs_allowed'] += _int_box_stat(stats, 'runs')
        totals['earned_runs'] += _int_box_stat(stats, 'earnedRuns')
        totals['hits_allowed'] += _int_box_stat(stats, 'hits')
        totals['walks'] += _int_box_stat(stats, 'baseOnBalls')
        totals['strikeouts'] += _int_box_stat(stats, 'strikeOuts')
        totals['home_runs_allowed'] += _int_box_stat(stats, 'homeRuns')
    return totals


def _official_validation(client, *, season, as_of_date, accumulators, expected_team_ids,
                         mismatch_limit):
    """Fetch official evidence and compare relief totals to the local aggregation."""
    api_calls = 0
    official = {tid: {'team_id': tid, 'team_name': None, 'relief_appearances': 0,
                      'bullpen_outs': 0, 'runs_allowed': 0, 'earned_runs': 0,
                      'hits_allowed': 0, 'walks': 0, 'strikeouts': 0, 'home_runs_allowed': 0,
                      'games': 0}
                for tid in expected_team_ids}
    team_names: Dict[int, tuple] = {}
    games_selected = 0
    games_fetched = 0
    fetch_failed = False
    games_missing_unique_starter = 0
    games_with_multiple_starters = 0
    incomplete_teams: set = set()

    # Official schedule, month-chunked so payloads stay bounded and cached per range.
    windows = _month_windows(date(season, 1, 1), as_of_date)
    schedule_games = {}
    for start, end in windows:
        try:
            fetched = client.get_schedule(start_date=start.isoformat(), end_date=end.isoformat()) or []
        except Exception:  # noqa: BLE001 — source unavailable => inconclusive
            return {'enabled': True, 'fetch_failed': True, 'api_calls': api_calls,
                    'games_selected': games_selected, 'games_fetched': games_fetched,
                    'official': official, 'team_names': team_names, 'mismatches': [],
                    'teams_matched': 0, 'teams_mismatched': 0, 'mandatory_mismatch': 0,
                    'games_missing_unique_starter': games_missing_unique_starter,
                    'games_with_multiple_starters': games_with_multiple_starters}
        api_calls += 1
        for game in fetched:
            game_pk = _pos_int((game or {}).get('gamePk'))
            if game_pk is not None and _is_official_final_regular(game):
                schedule_games[game_pk] = game

    boxscore_cache: Dict[int, dict] = {}
    for game_pk in sorted(schedule_games):
        games_selected += 1
        if game_pk not in boxscore_cache:
            try:
                boxscore_cache[game_pk] = client.get_game_boxscore(game_pk)
            except Exception:  # noqa: BLE001 — bounded official failure => inconclusive
                fetch_failed = True
                break
            api_calls += 1
        games_fetched += 1
        boxscore = boxscore_cache[game_pk] or {}
        # Home and away starter evidence is evaluated INDEPENDENTLY per side.
        for side_key in ('home', 'away'):
            relief = _official_relief_for_side((boxscore.get('teams') or {}).get(side_key))
            if relief is None:
                continue
            tid = relief['team_id']
            status = relief.get('starter_status')
            if status == STARTER_CONTRADICTORY:
                games_with_multiple_starters += 1
                incomplete_teams.add(tid)
                continue
            if status == STARTER_MISSING:
                games_missing_unique_starter += 1
                incomplete_teams.add(tid)
                continue
            bucket = official.setdefault(
                tid, {'team_id': tid, 'team_name': None, 'relief_appearances': 0,
                      'bullpen_outs': 0, 'runs_allowed': 0, 'earned_runs': 0,
                      'hits_allowed': 0, 'walks': 0, 'strikeouts': 0,
                      'home_runs_allowed': 0, 'games': 0})
            bucket['games'] += 1
            if relief.get('team_name'):
                team_names[tid] = (relief['team_name'], None)
            for metric in ('relief_appearances', 'bullpen_outs', 'runs_allowed', 'earned_runs',
                           'hits_allowed', 'walks', 'strikeouts', 'home_runs_allowed'):
                bucket[metric] += relief[metric]

    mismatches = []
    teams_matched = 0
    teams_mismatched = 0
    mandatory_mismatch = 0
    for tid in sorted(set(expected_team_ids) | set(accumulators) | set(official)):
        if tid in incomplete_teams:
            # Evidence for this team is incomplete (a game lacked a unique official starter);
            # it can never be declared a mismatch — it drives INCONCLUSIVE, not FAIL.
            continue
        acc = accumulators.get(tid) or _TeamAccumulator(tid)
        off = official.get(tid)
        local_vals = {
            'relief_appearances': acc.relief_appearances, 'bullpen_outs': acc.bullpen_outs,
            'runs_allowed': acc.runs_allowed, 'earned_runs': acc.earned_runs,
            'hits_allowed': acc.hits_allowed, 'walks': acc.walks,
            'strikeouts': acc.strikeouts, 'home_runs_allowed': acc.home_runs_allowed,
        }
        team_mismatched = False
        for metric in MANDATORY_COUNTING_METRICS:
            official_val = None if off is None else off[metric]
            if official_val is None or official_val != local_vals[metric]:
                team_mismatched = True
                mandatory_mismatch += 1
                if len(mismatches) < mismatch_limit:
                    mismatches.append({
                        'team_id': tid, 'metric': metric,
                        'local_value': local_vals[metric], 'official_value': official_val,
                        'difference': (None if official_val is None
                                       else local_vals[metric] - official_val),
                        'safe_reason_code': ('official_evidence_unavailable'
                                             if official_val is None else 'metric_value_mismatch'),
                    })
        if team_mismatched:
            teams_mismatched += 1
        else:
            teams_matched += 1

    return {
        'enabled': True,
        'fetch_failed': fetch_failed,
        'api_calls': api_calls,
        'games_selected': games_selected,
        'games_fetched': games_fetched,
        'official': official,
        'team_names': team_names,
        'teams_matched': teams_matched,
        'teams_mismatched': teams_mismatched,
        'mandatory_mismatch': mandatory_mismatch,
        'mismatches': mismatches,
        'games_missing_unique_starter': games_missing_unique_starter,
        'games_with_multiple_starters': games_with_multiple_starters,
        'incomplete_teams': sorted(incomplete_teams),
    }


def _is_official_final_regular(game) -> bool:
    if (game or {}).get('gameType') != REGULAR_SEASON_GAME_TYPE:
        return False
    return classify_status((game or {}).get('status') or {}).status_state == FINAL_STATUS_STATE


def _month_windows(start: date, end: date):
    """Month-sized [start, end] windows so official schedule payloads stay bounded."""
    windows = []
    cursor = start
    while cursor <= end:
        if cursor.month == 12:
            next_month_first = date(cursor.year + 1, 1, 1)
        else:
            next_month_first = date(cursor.year, cursor.month + 1, 1)
        month_end = next_month_first - timedelta(days=1)
        windows.append((cursor, min(month_end, end)))
        cursor = next_month_first
    return windows


# ── Public entry point ────────────────────────────────────────────────────────
def run_aggregation(
    *,
    season: int = DEFAULT_SEASON,
    as_of_date: date = DEFAULT_AS_OF_DATE,
    game_type: str = REGULAR_SEASON_GAME_TYPE,
    include_official_validation: bool = False,
    team_detail_limit: int = DEFAULT_TEAM_DETAIL_LIMIT,
    mismatch_detail_limit: int = DEFAULT_MISMATCH_DETAIL_LIMIT,
    generated_at: Optional[str] = None,
    client=mlb_client,
    session=None,
) -> dict:
    """Canonical season bullpen aggregation (read-only), optionally validated vs official MLB."""
    session = session or db.session
    team_detail_limit = _clamp_limit(team_detail_limit, DEFAULT_TEAM_DETAIL_LIMIT)
    mismatch_detail_limit = _clamp_limit(mismatch_detail_limit, DEFAULT_MISMATCH_DETAIL_LIMIT)
    if game_type != REGULAR_SEASON_GAME_TYPE:
        raise ValueError('Foundation 3A aggregates regular-season (R) only')

    migration_head = backfill._migration_head(session)
    invalid_states = backfill._invalid_stored_state_count(session)

    local = _aggregate_local(session, season=season, as_of_date=as_of_date)
    accumulators = local['accumulators']
    expected_team_ids = local['expected_team_ids']
    counts = local['counts']

    # Local result precedence: FAIL (critical) > INCONCLUSIVE (uncertainty) > PASS.
    fail_reasons = set(local['fail_reasons'])
    inconclusive_reasons = set(local['inconclusive_reasons'])
    if migration_head is not None and migration_head != [EXPECTED_MIGRATION_HEAD]:
        fail_reasons.add('migration_head_mismatch')
    if invalid_states > 0:
        fail_reasons.add('invalid_stored_states')
    league_totals = _league_totals(accumulators)
    team_totals_reconcile = all(
        sum(getattr(acc, m) for acc in accumulators.values()) == league_totals[m]
        for m in league_totals
    )
    # Genuine second-order cross-check: relief outs summed at the GAME grain must equal the
    # relief outs summed at the TEAM grain (the league total). A divergence means an included
    # appearance was double-counted or mis-grouped.
    game_outs_total = sum(local['game_relief_outs'].values())
    game_totals_reconcile = (game_outs_total == league_totals['bullpen_outs'])
    if not team_totals_reconcile or not game_totals_reconcile:
        fail_reasons.add('totals_do_not_reconcile')
    if not expected_team_ids and counts['included_relief_rows'] == 0:
        inconclusive_reasons.add('team_population_unavailable')

    if fail_reasons:
        local_result = RESULT_FAIL
        local_decision = sorted(fail_reasons)
    elif inconclusive_reasons:
        local_result = RESULT_INCONCLUSIVE
        local_decision = sorted(inconclusive_reasons)
    else:
        local_result = RESULT_PASS
        local_decision = ['local_aggregation_reconciled']

    # Official validation only runs on a clean local base and only when requested.
    validation = {'enabled': include_official_validation, 'games_selected': 0,
                  'games_fetched': 0, 'api_calls': 0, 'teams_validated': 0,
                  'teams_matched': 0, 'teams_mismatched': 0, 'mandatory_metric_mismatches': 0,
                  'optional_metric_mismatches': 0, 'unavailable_evidence_count': 0,
                  'official_games_missing_unique_starter': 0,
                  'official_games_with_multiple_starters': 0}
    bounded_mismatches = []
    team_names = {}
    result = local_result
    decision_reasons = list(local_decision)

    if include_official_validation and local_result == RESULT_PASS:
        raw = _official_validation(
            client, season=season, as_of_date=as_of_date, accumulators=accumulators,
            expected_team_ids=expected_team_ids, mismatch_limit=mismatch_detail_limit)
        team_names = raw['team_names']
        bounded_mismatches = raw['mismatches']
        covered = {tid for tid, off in raw['official'].items() if off['games'] > 0}
        incomplete = set(raw.get('incomplete_teams') or [])
        uncovered = [tid for tid in expected_team_ids if tid not in covered]
        multi_starter = raw['games_with_multiple_starters']
        missing_starter = raw['games_missing_unique_starter']
        validation.update({
            'games_selected': raw['games_selected'], 'games_fetched': raw['games_fetched'],
            'api_calls': raw['api_calls'], 'teams_validated': len(covered),
            'teams_matched': raw['teams_matched'], 'teams_mismatched': raw['teams_mismatched'],
            'mandatory_metric_mismatches': raw['mandatory_mismatch'],
            'optional_metric_mismatches': 0,
            'official_games_missing_unique_starter': missing_starter,
            'official_games_with_multiple_starters': multi_starter,
            'unavailable_evidence_count': (
                len(uncovered) + len(incomplete) + (1 if raw['fetch_failed'] else 0)),
        })
        # Official precedence: (1) contradictory official evidence (multiple gamesStarted==1)
        # is a hard FAIL; (2) incomplete evidence — a fetch failure or a game lacking a unique
        # official starter — is INCONCLUSIVE and can never be replaced by a later mismatch
        # verdict; (3) a genuine mandatory metric mismatch on complete-evidence teams is FAIL;
        # (4) uncovered expected teams are INCONCLUSIVE; else PASS.
        if multi_starter > 0:
            result = RESULT_FAIL
            decision_reasons = ['official_starter_identity_contradictory']
        elif raw['fetch_failed']:
            result = RESULT_INCONCLUSIVE
            decision_reasons = ['official_evidence_unavailable']
        elif missing_starter > 0:
            result = RESULT_INCONCLUSIVE
            decision_reasons = ['official_starter_identity_missing']
        elif raw['mandatory_mismatch'] > 0:
            result = RESULT_FAIL
            decision_reasons = ['official_mandatory_metric_mismatch']
        elif uncovered:
            result = RESULT_INCONCLUSIVE
            decision_reasons = ['official_evidence_unavailable']
        else:
            result = RESULT_PASS
            decision_reasons = ['official_validation_matched']

    # Rebuild team results with official names when validation supplied them.
    if team_names:
        local = _aggregate_local(session, season=season, as_of_date=as_of_date,
                                 team_names=team_names)

    teams_out = local['teams']
    teams_complete = sum(1 for t in teams_out if t['trust']['status'] == TRUST_COMPLETE)
    teams_partial = sum(1 for t in teams_out if t['trust']['status'] == TRUST_PARTIAL)
    teams_unavailable = sum(1 for t in teams_out if t['trust']['status'] == TRUST_UNAVAILABLE)

    foundation_3_status, public_reader_gate, share_card_gate = _gates(
        result, include_official_validation)

    payload = {
        'capability': CAPABILITY,
        'mode': 'official_validation' if include_official_validation else 'local_only',
        'result': result,
        'exit_code': EXIT_BY_RESULT[result],
        'generated_at': generated_at,
        'git_sha': _git_sha(),
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'inputs': {
            'season': int(season),
            'as_of_date': as_of_date.isoformat(),
            'game_type': REGULAR_SEASON_GAME_TYPE,
            'include_official_validation': bool(include_official_validation),
            'team_detail_limit': team_detail_limit,
            'mismatch_detail_limit': mismatch_detail_limit,
        },
        'contracts': {
            'aggregation_contract_version': AGGREGATION_CONTRACT_VERSION,
            'relief_classification_contract': RELIEF_CLASSIFICATION_CONTRACT,
            'appearance_team_contract': APPEARANCE_TEAM_CONTRACT,
            'finality_contract': FINALITY_CONTRACT,
            'metric_support': METRIC_SUPPORT,
        },
        'local_aggregation': {
            'team_count': len(teams_out),
            'teams_complete': teams_complete,
            'teams_partial': teams_partial,
            'teams_unavailable': teams_unavailable,
            'league_totals': league_totals,
            'teams': teams_out[:team_detail_limit],
        },
        'coverage': {
            'source_rows': counts['source_rows'],
            'included_relief_rows': counts['included_relief_rows'],
            'excluded_rows': counts['excluded_rows'],
            'starter_rows_excluded': counts['starter_rows_excluded'],
            'duplicate_rows': counts['duplicate_rows'],
            'unresolved_rows': counts['unresolved_rows'],
            'conflict_rows': counts['conflict_rows'],
            'legacy_null_rows': counts['legacy_null_rows'],
            'invalid_state_rows': counts['invalid_state_rows'],
            'missing_starter_identity_games': counts['missing_starter_identity_games'],
            'schedule_authority_missing_rows': counts['schedule_authority_missing_rows'],
            'schedule_authority_missing_games': counts['schedule_authority_missing_games'],
            'official_games_missing_unique_starter': validation['official_games_missing_unique_starter'],
            'official_games_with_multiple_starters': validation['official_games_with_multiple_starters'],
            'outs_reconciliation_failures': 0 if game_totals_reconcile else 1,
            'excluded_by_reason': local['excluded_by_reason'],
        },
        'official_validation': validation,
        'bounded_mismatches': bounded_mismatches[:mismatch_detail_limit],
        'reconciliations': {
            'canonical_game_grain_bullpen_outs': game_outs_total,
            'canonical_team_grain_bullpen_outs': league_totals['bullpen_outs'],
            'canonical_outs_match': game_totals_reconcile,
            'team_totals_reconcile': team_totals_reconcile,
            'league_totals_reconcile': team_totals_reconcile,
            'bullpen_outs_reconcile': game_totals_reconcile,
            'all_mandatory_metrics_match': (
                include_official_validation and result == RESULT_PASS
                and validation['teams_mismatched'] == 0),
            'expected_team_count': len(expected_team_ids),
            'teams_returned': len(teams_out),
            'duplicate_appearance_count': counts['duplicate_rows'],
            'excluded_row_count': counts['excluded_rows'],
        },
        'decision_reasons': decision_reasons,
        'foundation_3_status': foundation_3_status,
        'public_reader_gate': public_reader_gate,
        'share_card_performance_gate': share_card_gate,
        'database_writes_performed': False,
    }
    return payload


def _gates(result, official_mode):
    if result != RESULT_PASS:
        status = 'aggregation_failed' if result == RESULT_FAIL else 'aggregation_inconclusive'
        return status, 'blocked', 'blocked'
    if official_mode:
        return 'validated_ready_for_reader_review', 'ready_for_review', 'blocked'
    return 'aggregation_ready_for_validation', 'blocked', 'blocked'


def _git_sha():
    import os
    return os.environ.get('GITHUB_SHA')
