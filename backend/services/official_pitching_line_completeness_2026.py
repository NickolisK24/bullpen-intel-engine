"""Official pitching-line completeness diagnostic (2026) — READ ONLY.

The canonical Foundation 3A official validation failed with
``official_mandatory_metric_mismatch``: 30 teams mismatched, 228 mandatory metric
mismatches, and every bounded mismatch had a LOCAL value BELOW the OFFICIAL value. The
local-only audit still passed because its ``complete_team_games`` counts SCHEDULED FINAL
GAMES — it proves a game is final, never that every official pitching line in that game
exists locally. Scheduled-game coverage and pitching-line coverage are different claims.

This diagnostic closes that gap. For every final regular-season game through the as-of
date it enumerates every identity in each official box-score pitching section, identifies
the unique official starter STRICTLY by ``gamesStarted == 1``, treats every other official
pitching identity as a relief appearance, and compares each official line to the local
``GameLog`` ledger on ``(mlb_game_pk, official MLB pitcher id, appearance_team_id)``.

It answers exactly one question: WHICH official pitching lines are absent, extra,
misclassified, misassigned, duplicated, or statistically different locally.

Authority rules (identical to Foundation 1/3A, never weakened here):
    * historical team authority is ``GameLog.appearance_team_id`` — ``Pitcher.team_id``,
      current roster, and current organization are NEVER read;
    * identity matching is by official MLB pitcher id only — a missing identity is never
      inferred from a name;
    * a missing value is never read as zero.

Boundaries: read-only. No INSERT/UPDATE/DELETE, no backfill, no reconciliation write, no
change to the canonical aggregation or to any official-validation threshold or gate. The
repair is deliberately NOT implemented here. Foundation 3B, the public reader, Team State
performance, Share Card performance, and SC-05 all remain blocked.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

import sqlalchemy as sa

from models.game_log import GameLog
from models.pitcher import Pitcher
from services import appearance_team_backfill_2026 as backfill
from services import season_bullpen_aggregation_2026 as aggregation
from services import sync as sync_service
from services.mlb_api import mlb_client
from utils.db import db
from utils.games_started import InvalidGamesStartedValue, parse_games_started
from utils.innings import InvalidInningsNotation, parse_mlb_innings_to_outs


CAPABILITY = 'official_pitching_line_completeness_2026_v1'
DIAGNOSTIC_CONTRACT_VERSION = 'official_pitching_line_completeness_2026.v1'
IDENTITY_MATCH_CONTRACT = 'mlb_game_pk + official_mlb_pitcher_id + appearance_team_id'
STARTER_IDENTITY_CONTRACT = 'official gamesStarted == 1, exactly one per team-game side'
APPEARANCE_TEAM_CONTRACT = backfill.RESOLVER_CONTRACT_VERSION
EXPECTED_MIGRATION_HEAD = backfill.EXPECTED_MIGRATION_HEAD

DEFAULT_SEASON = 2026
DEFAULT_AS_OF_DATE = date(2026, 7, 25)
REGULAR_SEASON_GAME_TYPE = 'R'

DEFAULT_DETAIL_LIMIT = 100
MAX_DETAIL_LIMIT = 500

RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {RESULT_PASS: 0, RESULT_FAIL: 1, RESULT_INCONCLUSIVE: 2}

MODE_READ_ONLY = 'read_only'

ROLE_STARTER = 'starter'
ROLE_RELIEF = 'relief'

# ── Typed classification vocabulary ───────────────────────────────────────────
REASON_EXACT_MATCH = 'exact_match'
REASON_OFFICIAL_LINE_MISSING = 'official_line_missing_local_game_log'
REASON_LOCAL_LINE_EXTRA = 'local_line_not_in_official_pitching_section'
REASON_LOCAL_IDENTITY_MISSING = 'local_pitcher_identity_missing'
REASON_OFFICIAL_IDENTITY_MISSING = 'official_pitcher_identity_missing_from_pitcher_table'
REASON_APPEARANCE_TEAM_MISMATCH = 'appearance_team_mismatch'
REASON_ROLE_MISMATCH = 'starter_relief_classification_mismatch'
REASON_OUTS_MISMATCH = 'innings_outs_mismatch'
REASON_RUNS_MISMATCH = 'runs_mismatch'
REASON_EARNED_RUNS_MISMATCH = 'earned_runs_mismatch'
REASON_HITS_MISMATCH = 'hits_mismatch'
REASON_WALKS_MISMATCH = 'walks_mismatch'
REASON_STRIKEOUTS_MISMATCH = 'strikeouts_mismatch'
REASON_HOME_RUNS_MISMATCH = 'home_runs_mismatch'
REASON_LOCAL_DUPLICATE = 'local_duplicate_line'
REASON_OFFICIAL_STARTER_MISSING = 'official_starter_missing'
REASON_OFFICIAL_STARTER_CONTRADICTORY = 'official_starter_contradictory'
REASON_OFFICIAL_EVIDENCE_UNAVAILABLE = 'official_evidence_unavailable'

# (local GameLog attribute, official box-score stat key, reason code)
STAT_COMPARISONS = (
    ('innings_pitched_outs', 'outs', REASON_OUTS_MISMATCH),
    ('runs_allowed', 'runs', REASON_RUNS_MISMATCH),
    ('earned_runs', 'earned_runs', REASON_EARNED_RUNS_MISMATCH),
    ('hits_allowed', 'hits', REASON_HITS_MISMATCH),
    ('walks', 'walks', REASON_WALKS_MISMATCH),
    ('strikeouts', 'strikeouts', REASON_STRIKEOUTS_MISMATCH),
    ('home_runs_allowed', 'home_runs', REASON_HOME_RUNS_MISMATCH),
)
STAT_KEYS = tuple(key for _attr, key, _reason in STAT_COMPARISONS)
STAT_REASONS = frozenset(reason for _attr, _key, reason in STAT_COMPARISONS)

# A reason in this set is official PROOF of a local ledger defect => FAIL.
FAIL_REASONS = frozenset({
    REASON_OFFICIAL_LINE_MISSING,
    REASON_LOCAL_LINE_EXTRA,
    REASON_LOCAL_IDENTITY_MISSING,
    REASON_OFFICIAL_IDENTITY_MISSING,
    REASON_APPEARANCE_TEAM_MISMATCH,
    REASON_ROLE_MISMATCH,
    REASON_LOCAL_DUPLICATE,
    REASON_OFFICIAL_STARTER_CONTRADICTORY,
}) | STAT_REASONS

# A reason in this set means the official evidence needed for a verdict is incomplete.
INCONCLUSIVE_REASONS = frozenset({
    REASON_OFFICIAL_STARTER_MISSING,
    REASON_OFFICIAL_EVIDENCE_UNAVAILABLE,
})

DETAIL_KEYS = (
    'game_pk',
    'game_date',
    'team_id',
    'team_name',
    'official_pitcher_id',
    'official_pitcher_name',
    'official_role',
    'official_starter_count',
    'official_stats',
    'local_pitcher_id',
    'local_pitcher_mlb_id',
    'local_appearance_team_id',
    'local_games_started',
    'local_stats',
    'reason_codes',
)


# ── Small pure helpers ────────────────────────────────────────────────────────
def _int_or_none(value) -> Optional[int]:
    if isinstance(value, bool) or value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _pos_int(value) -> Optional[int]:
    parsed = _int_or_none(value)
    return parsed if parsed is not None and parsed > 0 else None


def _clamp_limit(value, default) -> int:
    parsed = _int_or_none(value)
    if parsed is None:
        return default
    return max(0, min(parsed, MAX_DETAIL_LIMIT))


def _iso_or_none(value) -> Optional[str]:
    return value.isoformat() if isinstance(value, date) else None


def _official_start_flag(raw_stats) -> Optional[int]:
    """``gamesStarted`` as 0/1, or None when absent or not a legal 0/1 value.

    A missing or illegal value is NEVER read as zero: it simply fails to prove a start,
    which surfaces as ``official_starter_missing`` for the side.
    """
    try:
        return parse_games_started((raw_stats or {}).get('gamesStarted'))
    except InvalidGamesStartedValue:
        return None


def _official_outs(raw_stats) -> Optional[int]:
    value = (raw_stats or {}).get('inningsPitched')
    if value in (None, ''):
        return None
    try:
        return parse_mlb_innings_to_outs(value)
    except InvalidInningsNotation:
        return None


def _official_stats(raw_stats) -> Dict[str, Optional[int]]:
    """The seven compared official stats. An absent stat stays None — never zero."""
    stats = raw_stats or {}
    return {
        'outs': _official_outs(stats),
        'runs': _int_or_none(stats.get('runs')),
        'earned_runs': _int_or_none(stats.get('earnedRuns')),
        'hits': _int_or_none(stats.get('hits')),
        'walks': _int_or_none(stats.get('baseOnBalls')),
        'strikeouts': _int_or_none(stats.get('strikeOuts')),
        'home_runs': _int_or_none(stats.get('homeRuns')),
    }


def _local_stats(log) -> Dict[str, Optional[int]]:
    return {
        'outs': _int_or_none(log.innings_pitched_outs),
        'runs': _int_or_none(log.runs_allowed),
        'earned_runs': _int_or_none(log.earned_runs),
        'hits': _int_or_none(log.hits_allowed),
        'walks': _int_or_none(log.walks),
        'strikeouts': _int_or_none(log.strikeouts),
        'home_runs': _int_or_none(log.home_runs_allowed),
    }


def _empty_stats() -> Dict[str, Optional[int]]:
    return {key: None for key in STAT_KEYS}


def _detail(**values) -> dict:
    detail = {key: None for key in DETAIL_KEYS}
    detail['reason_codes'] = []
    detail.update(values)
    detail['reason_codes'] = sorted(set(detail['reason_codes']))
    return detail


def _detail_sort_key(detail) -> tuple:
    """Deterministic detail order: findings first, then game, team, and identity.

    Findings sort ahead of exact matches so a bounded window always surfaces the defects
    rather than the first game's clean lines. Ordering never changes any count.
    """
    return (
        detail.get('reason_codes') == [REASON_EXACT_MATCH],
        detail.get('game_pk') or 0,
        detail.get('team_id') if detail.get('team_id') is not None else -1,
        detail.get('official_pitcher_id') if detail.get('official_pitcher_id') is not None else -1,
        detail.get('local_pitcher_mlb_id') if detail.get('local_pitcher_mlb_id') is not None else -1,
        detail.get('local_pitcher_id') if detail.get('local_pitcher_id') is not None else -1,
        ','.join(detail.get('reason_codes') or ()),
    )


# ── Official evidence ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _OfficialLine:
    game_pk: int
    game_date: Optional[date]
    side: str
    team_id: int
    team_name: Optional[str]
    pitcher_id: int
    pitcher_name: Optional[str]
    role: str
    stats: dict


@dataclass
class _OfficialSide:
    game_pk: int
    game_date: Optional[date]
    side: str
    team_id: Optional[int]
    team_name: Optional[str]
    lines: List[_OfficialLine] = field(default_factory=list)
    enumerated_line_count: int = 0
    starter_count: int = 0
    starter_status: str = ''          # 'unique' | 'missing' | 'contradictory'
    identities: set = field(default_factory=set)


def _game_team_ids(game) -> set:
    teams = (game or {}).get('teams') or {}
    ids = set()
    for side in ('home', 'away'):
        team_id = _pos_int((((teams.get(side) or {}).get('team')) or {}).get('id'))
        if team_id is not None:
            ids.add(team_id)
    return ids


def _select_official_games(client, *, season, as_of_date, team_id, game_pk):
    """Select final regular-season official games in scope (schedule authority = MLB).

    ``team_id`` narrows GAME SELECTION only: both official sides of every selected game are
    still enumerated and compared, so the side reconciliations stay exact.
    """
    selected: Dict[int, Optional[date]] = {}
    for start, end in aggregation._month_windows(date(season, 1, 1), as_of_date):
        try:
            fetched = client.get_schedule(
                start_date=start.isoformat(), end_date=end.isoformat()) or []
        except Exception:  # noqa: BLE001 — official source unavailable => inconclusive
            return selected, True
        for game in fetched:
            pk = _pos_int((game or {}).get('gamePk'))
            if pk is None or not aggregation._is_official_final_regular(game):
                continue
            if game_pk is not None and pk != game_pk:
                continue
            if team_id is not None and team_id not in _game_team_ids(game):
                continue
            official_date = (game or {}).get('officialDate') or (game or {}).get('gameDate')
            try:
                parsed_date = date.fromisoformat(str(official_date)[:10])
            except (TypeError, ValueError):
                parsed_date = None
            selected[pk] = parsed_date
    return selected, False


def _official_sides(boxscore, *, game_pk, game_date) -> List[_OfficialSide]:
    """Enumerate every identity in both official pitching sections of one box score."""
    lines_by_side: Dict[str, list] = defaultdict(list)
    for raw in sync_service._extract_pitching_lines_from_boxscore(boxscore):
        lines_by_side[raw.get('side')].append(raw)

    sides = []
    for side_key in ('away', 'home'):
        team = ((((boxscore or {}).get('teams') or {}).get(side_key) or {}).get('team')) or {}
        side = _OfficialSide(
            game_pk=game_pk,
            game_date=game_date,
            side=side_key,
            team_id=_pos_int(team.get('id')),
            team_name=team.get('name'),
        )
        raw_lines = lines_by_side.get(side_key) or []
        side.enumerated_line_count = len(raw_lines)
        if side.team_id is None:
            side.starter_status = 'unavailable'
            sides.append(side)
            continue

        parsed = []
        for raw in raw_lines:
            pitcher_id = _pos_int(raw.get('person_id')) or _pos_int(raw.get('player_id'))
            if pitcher_id is None:
                # An official identity without a usable MLB id cannot be compared by
                # identity, and a name is never used to infer one.
                side.starter_status = 'unavailable'
                continue
            raw_stats = raw.get('stats') or {}
            parsed.append((pitcher_id, raw.get('name'), raw_stats))
            side.identities.add(pitcher_id)

        starters = [pid for pid, _name, stats in parsed if _official_start_flag(stats) == 1]
        side.starter_count = len(starters)
        if side.starter_status == 'unavailable':
            sides.append(side)
            continue
        if len(starters) > 1:
            side.starter_status = 'contradictory'
            sides.append(side)
            continue
        if not starters:
            side.starter_status = 'missing'
            sides.append(side)
            continue

        side.starter_status = 'unique'
        starter_pid = starters[0]
        for pitcher_id, name, raw_stats in parsed:
            side.lines.append(_OfficialLine(
                game_pk=game_pk,
                game_date=game_date,
                side=side_key,
                team_id=side.team_id,
                team_name=side.team_name,
                pitcher_id=pitcher_id,
                pitcher_name=name,
                role=ROLE_STARTER if pitcher_id == starter_pid else ROLE_RELIEF,
                stats=_official_stats(raw_stats),
            ))
        side.lines.sort(key=lambda line: (line.role != ROLE_STARTER, line.pitcher_id))
        sides.append(side)
    return sides


# ── Local ledger ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class _LocalLine:
    log: object
    pitcher_row_id: int
    mlb_id: Optional[int]


def _local_lines(session, game_pks) -> List[_LocalLine]:
    """Every local GameLog row for the in-scope games, with its official MLB identity.

    ``Pitcher`` is joined ONLY to resolve ``mlb_id`` (the official identity). ``Pitcher.team_id``
    is never read — historical team authority is ``GameLog.appearance_team_id``.
    """
    if not game_pks:
        return []
    rows = (
        session.query(GameLog, Pitcher.mlb_id)
        .outerjoin(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(GameLog.mlb_game_pk.in_(sorted(game_pks)))
        .order_by(GameLog.mlb_game_pk.asc(), GameLog.pitcher_id.asc(), GameLog.id.asc())
        .all()
    )
    return [_LocalLine(log=log, pitcher_row_id=log.pitcher_id, mlb_id=_pos_int(mlb_id))
            for log, mlb_id in rows]


# ── Comparison ────────────────────────────────────────────────────────────────
@dataclass
class _Counters:
    exact_match: int = 0
    missing_local_line: int = 0
    extra_local_line: int = 0
    official_identity_missing: int = 0
    local_identity_missing: int = 0
    appearance_team_mismatch: int = 0
    role_mismatch: int = 0
    stat_mismatch: int = 0
    duplicate_local_line: int = 0
    defective_matched_lines: int = 0
    # Independently counted populations used by the reconciliations.
    local_in_official_section: int = 0
    game_evidence_unavailable_details: int = 0
    side_level_details: int = 0


def _compare_official_line(line: _OfficialLine, local_matches: List[_LocalLine]) -> dict:
    """Compare one official pitching line to its local counterpart(s)."""
    reasons: List[str] = []
    official_stats = dict(line.stats)

    if not local_matches:
        return _detail(
            game_pk=line.game_pk, game_date=_iso_or_none(line.game_date),
            team_id=line.team_id, team_name=line.team_name,
            official_pitcher_id=line.pitcher_id, official_pitcher_name=line.pitcher_name,
            official_role=line.role, official_stats=official_stats,
            local_stats=_empty_stats(),
            reason_codes=[REASON_OFFICIAL_LINE_MISSING],
        )

    primary = local_matches[0]
    log = primary.log
    if len(local_matches) > 1:
        reasons.append(REASON_LOCAL_DUPLICATE)

    if log.appearance_team_id != line.team_id:
        reasons.append(REASON_APPEARANCE_TEAM_MISMATCH)

    expected_started = 1 if line.role == ROLE_STARTER else 0
    if log.games_started != expected_started:
        # A NULL local games_started proves nothing and is never read as 0.
        reasons.append(REASON_ROLE_MISMATCH)

    local_stats = _local_stats(log)
    for attr, key, reason in STAT_COMPARISONS:
        official_value = official_stats.get(key)
        if official_value is None:
            # Official evidence for this stat is absent; it is never compared against 0.
            reasons.append(REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)
            continue
        if local_stats.get(key) != official_value:
            reasons.append(reason)

    if not reasons:
        reasons.append(REASON_EXACT_MATCH)

    return _detail(
        game_pk=line.game_pk, game_date=_iso_or_none(line.game_date),
        team_id=line.team_id, team_name=line.team_name,
        official_pitcher_id=line.pitcher_id, official_pitcher_name=line.pitcher_name,
        official_role=line.role, official_stats=official_stats,
        local_pitcher_id=primary.pitcher_row_id, local_pitcher_mlb_id=primary.mlb_id,
        local_appearance_team_id=log.appearance_team_id,
        local_games_started=log.games_started, local_stats=local_stats,
        reason_codes=reasons,
    )


def _local_extra_detail(local: _LocalLine, *, game_date, reason) -> dict:
    log = local.log
    return _detail(
        game_pk=log.mlb_game_pk, game_date=_iso_or_none(game_date or log.game_date),
        team_id=log.appearance_team_id,
        local_pitcher_id=local.pitcher_row_id, local_pitcher_mlb_id=local.mlb_id,
        local_appearance_team_id=log.appearance_team_id,
        local_games_started=log.games_started, local_stats=_local_stats(log),
        official_stats=_empty_stats(),
        reason_codes=[reason],
    )


def _team_bucket() -> dict:
    return {
        'official_pitching_lines': 0,
        'local_pitching_lines': 0,
        'exact_match': 0,
        'finding_count': 0,
        'counts_by_reason': {},
    }


# ── Public entry point ────────────────────────────────────────────────────────
def run_diagnostic(
    *,
    season: int = DEFAULT_SEASON,
    as_of_date: date = DEFAULT_AS_OF_DATE,
    game_type: str = REGULAR_SEASON_GAME_TYPE,
    detail_limit: int = DEFAULT_DETAIL_LIMIT,
    team_id: Optional[int] = None,
    game_pk: Optional[int] = None,
    generated_at: Optional[str] = None,
    client=mlb_client,
    session=None,
) -> dict:
    """Diagnose official-vs-local pitching-line completeness. Never writes."""
    if game_type != REGULAR_SEASON_GAME_TYPE:
        raise ValueError('this diagnostic covers regular-season (R) games only')
    session = session or db.session
    detail_limit = _clamp_limit(detail_limit, DEFAULT_DETAIL_LIMIT)
    team_filter = _pos_int(team_id)
    game_filter = _pos_int(game_pk)

    migration_head = _migration_head(session)
    counters = _Counters()
    details: List[dict] = []
    counts_by_reason: Dict[str, int] = defaultdict(int)
    counts_by_team: Dict[int, dict] = {}
    fail_reasons: set = set()
    inconclusive_reasons: set = set()

    def _record(detail, *, team_key=None):
        details.append(detail)
        for reason in detail['reason_codes']:
            counts_by_reason[reason] += 1
            if reason in FAIL_REASONS:
                fail_reasons.add(reason)
            elif reason in INCONCLUSIVE_REASONS:
                inconclusive_reasons.add(reason)
        key = team_key if team_key is not None else detail.get('team_id')
        if key is not None:
            bucket = counts_by_team.setdefault(key, _team_bucket())
            if detail['reason_codes'] == [REASON_EXACT_MATCH]:
                bucket['exact_match'] += 1
            else:
                bucket['finding_count'] += 1
            for reason in detail['reason_codes']:
                bucket['counts_by_reason'][reason] = bucket['counts_by_reason'].get(reason, 0) + 1

    selected_games, schedule_failed = _select_official_games(
        client, season=season, as_of_date=as_of_date, team_id=team_filter, game_pk=game_filter)
    if schedule_failed:
        inconclusive_reasons.add(REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)

    games_selected = len(selected_games)
    games_fetched = 0
    boxscores: Dict[int, dict] = {}
    for pk in sorted(selected_games):
        try:
            boxscores[pk] = client.get_game_boxscore(pk) or {}
        except Exception:  # noqa: BLE001 — bounded official failure => inconclusive
            counters.game_evidence_unavailable_details += 1
            _record(_detail(
                game_pk=pk, game_date=_iso_or_none(selected_games[pk]),
                official_stats=_empty_stats(), local_stats=_empty_stats(),
                reason_codes=[REASON_OFFICIAL_EVIDENCE_UNAVAILABLE]))
            continue
        games_fetched += 1

    # Local rows are only evaluated for games whose official pitching section was fetched:
    # an unfetched game can never prove a local line extra.
    local_lines = _local_lines(session, set(boxscores))
    local_by_game: Dict[int, List[_LocalLine]] = defaultdict(list)
    local_by_identity: Dict[Tuple[int, int], List[_LocalLine]] = defaultdict(list)
    local_starter_lines = local_relief_lines = local_unknown_role_lines = 0
    for local in local_lines:
        local_by_game[local.log.mlb_game_pk].append(local)
        if local.mlb_id is not None:
            local_by_identity[(local.log.mlb_game_pk, local.mlb_id)].append(local)
        if local.log.games_started == 1:
            local_starter_lines += 1
        elif local.log.games_started == 0:
            local_relief_lines += 1
        else:
            local_unknown_role_lines += 1

    official_team_game_sides = 0
    official_sides_with_unique_starter = 0
    official_pitching_lines = 0
    official_starter_lines = 0
    official_relief_lines = 0
    official_lines_excluded_from_comparison = 0
    official_lines_compared = 0
    matched_local_lines = 0
    pitcher_mlb_ids_present: set = set()

    # Enumerate every official pitching section once, then resolve official identities
    # against the Pitcher table in a single bounded lookup.
    sides_by_game: Dict[int, List[_OfficialSide]] = {
        pk: _official_sides(boxscores[pk], game_pk=pk, game_date=selected_games.get(pk))
        for pk in sorted(boxscores)
    }
    all_official_ids = {
        pitcher_id
        for sides in sides_by_game.values()
        for side in sides
        for pitcher_id in side.identities
    }
    if all_official_ids:
        pitcher_mlb_ids_present = {
            row[0] for row in session.query(Pitcher.mlb_id)
            .filter(Pitcher.mlb_id.in_(sorted(all_official_ids))).all()
        }

    for pk in sorted(sides_by_game):
        game_date = selected_games.get(pk)
        sides = sides_by_game[pk]
        official_identities_in_game: set = set()
        for side in sides:
            official_identities_in_game |= side.identities
            official_pitching_lines += side.enumerated_line_count
            if side.team_id is None:
                official_lines_excluded_from_comparison += side.enumerated_line_count
                counters.side_level_details += 1
                _record(_detail(
                    game_pk=pk, game_date=_iso_or_none(game_date),
                    official_stats=_empty_stats(), local_stats=_empty_stats(),
                    reason_codes=[REASON_OFFICIAL_EVIDENCE_UNAVAILABLE]))
                continue

            official_team_game_sides += 1
            bucket = counts_by_team.setdefault(side.team_id, _team_bucket())
            bucket['official_pitching_lines'] += side.enumerated_line_count

            if side.starter_status != 'unique':
                official_lines_excluded_from_comparison += side.enumerated_line_count
                reason = {
                    'contradictory': REASON_OFFICIAL_STARTER_CONTRADICTORY,
                    'missing': REASON_OFFICIAL_STARTER_MISSING,
                }.get(side.starter_status, REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)
                counters.side_level_details += 1
                _record(_detail(
                    game_pk=pk, game_date=_iso_or_none(game_date),
                    team_id=side.team_id, team_name=side.team_name,
                    official_starter_count=side.starter_count,
                    official_stats=_empty_stats(), local_stats=_empty_stats(),
                    reason_codes=[reason]))
                continue

            official_sides_with_unique_starter += 1
            for line in side.lines:
                official_lines_compared += 1
                if line.role == ROLE_STARTER:
                    official_starter_lines += 1
                else:
                    official_relief_lines += 1

                if line.pitcher_id not in pitcher_mlb_ids_present:
                    counters.official_identity_missing += 1
                    counters.missing_local_line += 1
                    _record(_detail(
                        game_pk=pk, game_date=_iso_or_none(game_date),
                        team_id=line.team_id, team_name=line.team_name,
                        official_pitcher_id=line.pitcher_id,
                        official_pitcher_name=line.pitcher_name,
                        official_role=line.role, official_stats=dict(line.stats),
                        local_stats=_empty_stats(),
                        reason_codes=[REASON_OFFICIAL_IDENTITY_MISSING,
                                      REASON_OFFICIAL_LINE_MISSING]))
                    continue

                matches = local_by_identity.get((pk, line.pitcher_id)) or []
                detail = _compare_official_line(line, matches)
                reasons = detail['reason_codes']
                matched_local_lines += len(matches)
                if reasons == [REASON_EXACT_MATCH]:
                    counters.exact_match += 1
                elif REASON_OFFICIAL_LINE_MISSING in reasons:
                    counters.missing_local_line += 1
                else:
                    counters.defective_matched_lines += 1
                    if REASON_LOCAL_DUPLICATE in reasons:
                        counters.duplicate_local_line += 1
                    if REASON_APPEARANCE_TEAM_MISMATCH in reasons:
                        counters.appearance_team_mismatch += 1
                    if REASON_ROLE_MISMATCH in reasons:
                        counters.role_mismatch += 1
                    if any(reason in STAT_REASONS for reason in reasons):
                        counters.stat_mismatch += 1
                _record(detail, team_key=line.team_id)

        # Local direction: a local line whose identity is absent from BOTH official pitching
        # sections of this game is proven extra. Identity enumeration is complete even when a
        # side lacks a unique starter, so extra-line proof does not depend on starter identity.
        for local in local_by_game.get(pk, ()):
            bucket_key = local.log.appearance_team_id
            if bucket_key is not None:
                counts_by_team.setdefault(bucket_key, _team_bucket())['local_pitching_lines'] += 1
            if local.mlb_id is None:
                counters.local_identity_missing += 1
                _record(_local_extra_detail(local, game_date=game_date,
                                            reason=REASON_LOCAL_IDENTITY_MISSING))
            elif local.mlb_id not in official_identities_in_game:
                counters.extra_local_line += 1
                _record(_local_extra_detail(local, game_date=game_date,
                                            reason=REASON_LOCAL_LINE_EXTRA))
            else:
                counters.local_in_official_section += 1

    local_pitching_lines = len(local_lines)
    # Local lines present in an official pitching section but never compared, because their
    # team-game side had no unique official starter.
    local_lines_not_evaluated = counters.local_in_official_section - matched_local_lines

    if games_selected == 0:
        inconclusive_reasons.add(REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)

    reconciliations = {
        'official_games_times_two_equals_team_game_sides':
            official_team_game_sides == games_fetched * 2,
        'every_team_game_side_has_unique_official_starter':
            official_sides_with_unique_starter == official_team_game_sides,
        'official_starter_lines_equal_team_game_sides':
            official_starter_lines == official_team_game_sides,
        'official_starter_plus_relief_equals_pitching_lines':
            official_starter_lines + official_relief_lines == official_pitching_lines,
        'official_compared_lines_partition':
            official_lines_compared == (
                counters.exact_match + counters.missing_local_line
                + counters.defective_matched_lines),
        'official_lines_account_for_uncompared_sides':
            official_pitching_lines == (
                official_lines_compared + official_lines_excluded_from_comparison),
        'local_lines_partition':
            local_pitching_lines == (
                counters.local_in_official_section + counters.extra_local_line
                + counters.local_identity_missing),
        'local_matched_lines_within_official_section':
            matched_local_lines <= counters.local_in_official_section,
        'local_role_lines_partition':
            local_pitching_lines == (
                local_starter_lines + local_relief_lines + local_unknown_role_lines),
        'classification_details_reconcile':
            len(details) == (
                counters.game_evidence_unavailable_details + counters.side_level_details
                + official_lines_compared + counters.extra_local_line
                + counters.local_identity_missing),
        'official_games_fetched_equals_selected': games_fetched == games_selected,
    }
    if migration_head is not None and migration_head != [EXPECTED_MIGRATION_HEAD]:
        fail_reasons.add('migration_head_mismatch')
    if not all(reconciliations.values()) and not fail_reasons and not inconclusive_reasons:
        # A reconciliation can only break when evidence is incomplete or a defect exists; a
        # break with no recorded reason is itself an unexplained gap.
        inconclusive_reasons.add(REASON_OFFICIAL_EVIDENCE_UNAVAILABLE)

    if fail_reasons:
        result = RESULT_FAIL
        decision_reasons = sorted(fail_reasons)
    elif inconclusive_reasons:
        result = RESULT_INCONCLUSIVE
        decision_reasons = sorted(inconclusive_reasons)
    else:
        result = RESULT_PASS
        decision_reasons = ['every_official_pitching_line_has_one_exact_local_counterpart']

    details.sort(key=_detail_sort_key)
    bounded_details = details[:detail_limit]

    return {
        'capability': CAPABILITY,
        'mode': MODE_READ_ONLY,
        'result': result,
        'exit_code': EXIT_BY_RESULT[result],
        'generated_at': generated_at,
        'git_sha': _git_sha(),
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'season': int(season),
        'as_of_date': as_of_date.isoformat(),
        'inputs': {
            'season': int(season),
            'as_of_date': as_of_date.isoformat(),
            'game_type': REGULAR_SEASON_GAME_TYPE,
            'detail_limit': detail_limit,
            'team_id': team_filter,
            'game_pk': game_filter,
        },
        'contracts': {
            'diagnostic_contract_version': DIAGNOSTIC_CONTRACT_VERSION,
            'identity_match_contract': IDENTITY_MATCH_CONTRACT,
            'starter_identity_contract': STARTER_IDENTITY_CONTRACT,
            'appearance_team_contract': APPEARANCE_TEAM_CONTRACT,
            'missing_local_pitcher_identity_count_meaning':
                'official compared lines whose MLB pitcher id has no Pitcher row',
            'reason_vocabulary': sorted(
                {REASON_EXACT_MATCH} | FAIL_REASONS | INCONCLUSIVE_REASONS),
        },
        'official_games_selected': games_selected,
        'official_games_fetched': games_fetched,
        'official_team_game_sides': official_team_game_sides,
        'expected_official_starter_lines': official_team_game_sides,
        'official_sides_with_unique_starter': official_sides_with_unique_starter,
        'official_pitching_lines': official_pitching_lines,
        'official_pitching_lines_compared': official_lines_compared,
        'official_lines_excluded_from_comparison': official_lines_excluded_from_comparison,
        'official_starter_lines': official_starter_lines,
        'official_relief_lines': official_relief_lines,
        'local_pitching_lines': local_pitching_lines,
        'local_starter_lines': local_starter_lines,
        'local_relief_lines': local_relief_lines,
        'local_unknown_role_lines': local_unknown_role_lines,
        'local_lines_matched_to_official': matched_local_lines,
        'local_lines_not_evaluated': local_lines_not_evaluated,
        'exact_match_count': counters.exact_match,
        'missing_local_line_count': counters.missing_local_line,
        'extra_local_line_count': counters.extra_local_line,
        'missing_local_pitcher_identity_count': counters.official_identity_missing,
        'local_pitcher_identity_missing_count': counters.local_identity_missing,
        'appearance_team_mismatch_count': counters.appearance_team_mismatch,
        'role_mismatch_count': counters.role_mismatch,
        'stat_mismatch_count': counters.stat_mismatch,
        'duplicate_local_line_count': counters.duplicate_local_line,
        'counts_by_reason': dict(sorted(counts_by_reason.items())),
        'counts_by_team': {
            str(team): {
                'official_pitching_lines': bucket['official_pitching_lines'],
                'local_pitching_lines': bucket['local_pitching_lines'],
                'exact_match': bucket['exact_match'],
                'finding_count': bucket['finding_count'],
                'counts_by_reason': dict(sorted(bucket['counts_by_reason'].items())),
            }
            for team, bucket in sorted(counts_by_team.items())
        },
        'detail_count': len(details),
        'bounded_detail_count': len(bounded_details),
        'details_truncated': len(details) > len(bounded_details),
        'bounded_details': bounded_details,
        'reconciliations': reconciliations,
        'decision_reasons': decision_reasons,
        'repair_status': 'not_implemented_in_this_branch',
        'foundation_3b_gate': 'blocked',
        'public_reader_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
        'database_writes_performed': False,
    }


def _migration_head(session):
    """Best-effort Alembic head(s) for the report; a create_all test schema has none."""
    try:
        rows = session.execute(
            sa.text('SELECT version_num FROM alembic_version ORDER BY version_num')
        ).fetchall()
        return sorted(str(row[0]) for row in rows)
    except Exception:  # noqa: BLE001 — diagnostic probe only; keep the session usable
        session.rollback()
        return None


def _git_sha():
    import os
    return os.environ.get('GITHUB_SHA')
