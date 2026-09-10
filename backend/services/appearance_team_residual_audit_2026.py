"""Read-only 2026 residual appearance-team audit (Foundation 2 production completion).

Foundation 1 froze team-at-appearance authority; Foundation 2 ran a governed backfill
that attributed every 2026 legacy row eligible under its selection contract. A residual
population of legacy-NULL 2026 rows remains. This module explains, READ-ONLY, exactly
why each residual row was NOT selected — assigning every row exactly one deterministic,
mutually exclusive primary category, and proving that zero residual rows are actually
eligible under the exact Foundation 2 selection query (the critical defect signal).

It is NOT Foundation 3: it computes no bullpen ERA, relief innings, saves, rankings, or
Team State/Share Card performance field, and it performs NO database write — only
SELECTs, bounded in-memory classification, and a JSON report. Attribution authority is
never inferred from the pitcher's current team.

The Foundation 2 eligibility is not re-approximated here: the parity proof CALLS the
real ``appearance_team_backfill_2026._select_game_keys`` (with its real keyset cursor)
so "eligible" means exactly what the backfill means.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import sqlalchemy as sa

from models.completed_game_context import CompletedGameContext
from models.game_log import GameLog
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority as ata
from services import appearance_team_backfill_2026 as backfill
from utils.db import db


CAPABILITY = 'appearance_team_residual_audit_2026_v1'
EXPECTED_MIGRATION_HEAD = backfill.EXPECTED_MIGRATION_HEAD

DEFAULT_SEASON = 2026
DEFAULT_CAMPAIGN_START = date(2026, 1, 1)
DEFAULT_CAMPAIGN_END = date(2026, 7, 25)
DEFAULT_ROW_DETAIL_LIMIT = 50
DEFAULT_GAME_DETAIL_LIMIT = 50
MAX_DETAIL_LIMIT = 500

# The only game type that feeds the intended MLB regular-season bullpen aggregation.
REGULAR_SEASON_GAME_TYPES = ('R',)
_DISQUALIFIER_STATES = (ScheduledGame.STATE_POSTPONED, ScheduledGame.STATE_SUSPENDED)

# Deterministic, mutually exclusive primary classifications, highest precedence first.
CAT_MISSING_GAME_DATE = 'missing_game_date'
CAT_BEFORE_WINDOW = 'before_campaign_window'
CAT_AFTER_CUTOFF = 'after_campaign_cutoff'
CAT_MISSING_GAME_PK = 'missing_game_pk'
CAT_NO_SCHEDULE_ROWS = 'no_schedule_rows'
CAT_NO_FINAL = 'no_final_schedule_state'
CAT_POSTPONED_SUSPENDED = 'postponed_or_suspended_disqualifier'
CAT_CONTRADICTORY_FINALITY = 'contradictory_finality'
CAT_INCOMPLETE_SIDES = 'incomplete_schedule_sides'
CAT_CONTRADICTORY_AUTHORITY = 'contradictory_schedule_authority'
CAT_EXCEPTIONAL_GAME_TYPE = 'exceptional_game_type'
CAT_ELIGIBLE_NOT_SELECTED = 'eligible_but_not_selected'
CAT_OTHER = 'other_classified_exclusion'
CAT_UNCLASSIFIED = 'unclassified'

PRIMARY_CATEGORIES = (
    CAT_MISSING_GAME_DATE,
    CAT_BEFORE_WINDOW,
    CAT_AFTER_CUTOFF,
    CAT_MISSING_GAME_PK,
    CAT_NO_SCHEDULE_ROWS,
    CAT_NO_FINAL,
    CAT_POSTPONED_SUSPENDED,
    CAT_CONTRADICTORY_FINALITY,
    CAT_INCOMPLETE_SIDES,
    CAT_CONTRADICTORY_AUTHORITY,
    CAT_EXCEPTIONAL_GAME_TYPE,
    CAT_ELIGIBLE_NOT_SELECTED,
    CAT_OTHER,
    CAT_UNCLASSIFIED,
)

# Result contract.
RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {RESULT_PASS: 0, RESULT_FAIL: 1, RESULT_INCONCLUSIVE: 2}


@dataclass(frozen=True)
class _ScheduleFacts:
    states: frozenset
    has_final: bool
    has_disqualifier: bool
    side_status: str          # 'ok' | 'incomplete' | 'contradictory'
    row_count: int


def _clamp_limit(value, default) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < 0:
        return 0
    return min(parsed, MAX_DETAIL_LIMIT)


def _int_or_none(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _side_status(rows) -> str:
    """Classify the canonical two-team-side authority of a game's schedule rows."""
    teams = [(_int_or_none(r.team_id), _int_or_none(r.opponent_team_id), r.home_away)
             for r in rows]
    if any(t is None or o is None or ha not in ('home', 'away') for t, o, ha in teams):
        return 'incomplete'
    distinct_teams = {t for t, _o, _ha in teams}
    if len(distinct_teams) < 2:
        return 'incomplete'
    if len(distinct_teams) > 2 or len(teams) != 2:
        return 'contradictory'
    (t1, o1, ha1), (t2, o2, ha2) = teams
    if {ha1, ha2} != {'home', 'away'}:
        return 'contradictory'
    if o1 != t2 or o2 != t1:
        return 'contradictory'
    return 'ok'


def _schedule_facts(rows) -> _ScheduleFacts:
    states = frozenset(r.status_state for r in rows)
    return _ScheduleFacts(
        states=states,
        has_final=ScheduledGame.STATE_FINAL in states,
        has_disqualifier=bool(states & set(_DISQUALIFIER_STATES)),
        side_status=_side_status(rows),
        row_count=len(rows),
    )


def _classify_row(row, *, campaign_start, campaign_end, schedule_by_pk, eligible_pks):
    """Assign exactly one primary category. Deterministic precedence, top-down."""
    game_date = row.game_date
    if game_date is None:
        return CAT_MISSING_GAME_DATE
    if game_date < campaign_start:
        return CAT_BEFORE_WINDOW
    if game_date > campaign_end:
        return CAT_AFTER_CUTOFF
    if row.mlb_game_pk is None:
        return CAT_MISSING_GAME_PK

    rows = schedule_by_pk.get(row.mlb_game_pk)
    if not rows:
        return CAT_NO_SCHEDULE_ROWS
    facts = _schedule_facts(rows)
    if not facts.has_final and not facts.has_disqualifier:
        return CAT_NO_FINAL
    if facts.has_disqualifier and not facts.has_final:
        return CAT_POSTPONED_SUSPENDED
    if facts.has_final and facts.has_disqualifier:
        return CAT_CONTRADICTORY_FINALITY

    # has_final and not has_disqualifier -> the game is FINAL-eligible per Foundation 2.
    if facts.side_status == 'incomplete':
        return CAT_INCOMPLETE_SIDES
    if facts.side_status == 'contradictory':
        return CAT_CONTRADICTORY_AUTHORITY
    if row.game_type not in REGULAR_SEASON_GAME_TYPES:
        return CAT_EXCEPTIONAL_GAME_TYPE
    if row.mlb_game_pk in eligible_pks:
        return CAT_ELIGIBLE_NOT_SELECTED
    # Final, clean sides, regular type, yet the exact backfill query did not select the
    # game: a deterministic-but-unexpected exclusion worth surfacing (should be empty).
    return CAT_OTHER


def _all_eligible_game_pks(session, *, campaign_start, campaign_end):
    """The EXACT set of game_pks Foundation 2 would select, via the real selector.

    Paginates ``_select_game_keys`` with its own keyset cursor so no eligible game is
    silently capped. Never re-approximates the eligibility predicate.
    """
    page = 1000
    pks = set()
    after_date, after_pk = None, None
    while True:
        keys = backfill._select_game_keys(
            start_date=campaign_start,
            end_date=campaign_end,
            after_game_date=after_date,
            after_game_pk=after_pk,
            batch_size=page,
            session=session,
        )
        if not keys:
            break
        for game_date, game_pk in keys:
            pks.add(game_pk)
        after_date, after_pk = keys[-1]
        if len(keys) < page:
            break
    return pks


def _residual_rows(session, *, season):
    return (
        session.query(GameLog)
        .filter(GameLog.appearance_team_status.is_(None))
        .filter(sa.extract('year', GameLog.game_date) == season)
        .order_by(GameLog.game_date.asc(), GameLog.id.asc())
        .all()
    )


def _schedule_rows_by_pk(session, game_pks) -> Dict[int, list]:
    by_pk: Dict[int, list] = defaultdict(list)
    if not game_pks:
        return by_pk
    rows = (
        session.query(
            ScheduledGame.game_pk,
            ScheduledGame.team_id,
            ScheduledGame.opponent_team_id,
            ScheduledGame.home_away,
            ScheduledGame.status_state,
        )
        .filter(ScheduledGame.game_pk.in_(game_pks))
        .all()
    )
    for row in rows:
        by_pk[row.game_pk].append(row)
    return by_pk


def _context_game_pks(session, game_pks) -> set:
    if not game_pks:
        return set()
    rows = (
        session.query(CompletedGameContext.game_pk)
        .filter(CompletedGameContext.game_pk.in_(game_pks))
        .distinct()
        .all()
    )
    return {pk for (pk,) in rows}


def run_residual_audit(
    *,
    season: int = DEFAULT_SEASON,
    campaign_start_date: date = DEFAULT_CAMPAIGN_START,
    campaign_end_date: date = DEFAULT_CAMPAIGN_END,
    row_detail_limit: int = DEFAULT_ROW_DETAIL_LIMIT,
    game_detail_limit: int = DEFAULT_GAME_DETAIL_LIMIT,
    generated_at: Optional[str] = None,
    session=None,
) -> dict:
    """Classify every ``season`` legacy-NULL appearance and return a bounded report.

    Read-only: only SELECTs and in-memory classification. Never mutates a row.
    """
    session = session or db.session
    row_detail_limit = _clamp_limit(row_detail_limit, DEFAULT_ROW_DETAIL_LIMIT)
    game_detail_limit = _clamp_limit(game_detail_limit, DEFAULT_GAME_DETAIL_LIMIT)
    if campaign_end_date < campaign_start_date:
        raise ValueError('campaign_end_date must not be before campaign_start_date')

    migration_head = backfill._migration_head(session)
    coverage = backfill._coverage_snapshot(session, season=season)

    residual = _residual_rows(session, season=season)
    game_pks = {row.mlb_game_pk for row in residual if row.mlb_game_pk is not None}
    schedule_by_pk = _schedule_rows_by_pk(session, game_pks)
    context_pks = _context_game_pks(session, game_pks)
    eligible_pks = _all_eligible_game_pks(
        session, campaign_start=campaign_start_date, campaign_end=campaign_end_date,
    )

    category_of: Dict[int, str] = {}
    category_rows = defaultdict(int)
    category_games = defaultdict(set)
    for row in residual:
        category = _classify_row(
            row,
            campaign_start=campaign_start_date,
            campaign_end=campaign_end_date,
            schedule_by_pk=schedule_by_pk,
            eligible_pks=eligible_pks,
        )
        category_of[row.id] = category
        category_rows[category] += 1
        if row.mlb_game_pk is not None:
            category_games[category].add(row.mlb_game_pk)

    total_rows = len(residual)
    distinct_games = len(game_pks)
    exact_backfill_eligible_rows = sum(
        1 for row in residual if row.mlb_game_pk in eligible_pks
    )
    unclassified_rows = category_rows.get(CAT_UNCLASSIFIED, 0)

    # Population buckets.
    inside_window = sum(
        1 for r in residual
        if r.game_date is not None and campaign_start_date <= r.game_date <= campaign_end_date
    )
    before_window = sum(
        1 for r in residual if r.game_date is not None and r.game_date < campaign_start_date
    )
    after_cutoff = sum(
        1 for r in residual if r.game_date is not None and r.game_date > campaign_end_date
    )
    missing_date = sum(1 for r in residual if r.game_date is None)

    category_totals_reconcile = (
        sum(category_rows.values()) == total_rows
        and exact_backfill_eligible_rows == sum(
            category_rows.get(cat, 0)
            for cat in (CAT_INCOMPLETE_SIDES, CAT_CONTRADICTORY_AUTHORITY,
                        CAT_EXCEPTIONAL_GAME_TYPE, CAT_ELIGIBLE_NOT_SELECTED, CAT_OTHER)
        )
    )

    # Secondary diagnostic dimensions (deterministic ordering).
    by_month = _counter(
        (row.game_date.strftime('%Y-%m') if row.game_date else 'unknown') for row in residual
    )
    by_game_type = _counter(row.game_type or 'unknown' for row in residual)
    by_finality = _counter(
        _finality_label(row, schedule_by_pk) for row in residual
    )

    schedule_coverage = _schedule_coverage(residual, schedule_by_pk)
    context_coverage = {
        'rows_with_completed_game_context': sum(
            1 for r in residual if r.mlb_game_pk in context_pks),
        'rows_without_completed_game_context': sum(
            1 for r in residual if r.mlb_game_pk not in context_pks),
        'games_with_completed_game_context': len(context_pks & game_pks),
    }
    aggregation = _aggregation_relevance(residual, category_of, campaign_end_date)

    row_samples = _row_samples(
        residual, category_of, schedule_by_pk, context_pks, limit=row_detail_limit)
    game_samples = _game_samples(
        residual, category_of, schedule_by_pk, limit=game_detail_limit)

    result, reasons = _classify_result(
        total_rows=total_rows,
        exact_eligible=exact_backfill_eligible_rows,
        reconcile=category_totals_reconcile,
        invalid=coverage['invalid_stored_states'],
        unclassified=unclassified_rows,
        migration_head=migration_head,
    )
    f2_status = 'production_complete' if result == RESULT_PASS else (
        'incomplete' if result == RESULT_FAIL else 'inconclusive')
    f3_gate = _foundation_3_gate(result, aggregation, exact_backfill_eligible_rows,
                                 unclassified_rows)

    return {
        'capability': CAPABILITY,
        'mode': 'read_only',
        'result': result,
        'exit_code': EXIT_BY_RESULT[result],
        'generated_at': generated_at,
        'git_sha': _git_sha(),
        'migration_head': migration_head,
        'expected_migration_head': EXPECTED_MIGRATION_HEAD,
        'inputs': {
            'season': int(season),
            'campaign_start_date': campaign_start_date.isoformat(),
            'campaign_end_date': campaign_end_date.isoformat(),
            'row_detail_limit': row_detail_limit,
            'game_detail_limit': game_detail_limit,
        },
        'coverage': coverage,
        'residual_population': {
            'total_rows': total_rows,
            'distinct_games': distinct_games,
            'inside_campaign_window': inside_window,
            'before_campaign_window': before_window,
            'after_campaign_cutoff': after_cutoff,
            'missing_game_date': missing_date,
        },
        'primary_categories': {
            cat: {
                'row_count': category_rows.get(cat, 0),
                'game_count': len(category_games.get(cat, set())),
                'percentage': round(100.0 * category_rows.get(cat, 0) / total_rows, 4)
                if total_rows else 0.0,
            }
            for cat in PRIMARY_CATEGORIES
        },
        'category_totals_reconcile': category_totals_reconcile,
        'exact_backfill_eligible_rows': exact_backfill_eligible_rows,
        'unclassified_rows': unclassified_rows,
        'by_month': by_month,
        'by_game_type': by_game_type,
        'by_finality_state': by_finality,
        'schedule_coverage': schedule_coverage,
        'context_coverage': context_coverage,
        'bullpen_aggregation_relevance': aggregation,
        'bounded_row_samples': row_samples,
        'bounded_game_samples': game_samples,
        'samples_truncated': (len(row_samples) < total_rows)
        or (len(game_samples) < distinct_games),
        'decision_reasons': reasons,
        'foundation_2_status': f2_status,
        'foundation_3_gate': f3_gate,
        'database_writes_performed': False,
    }


def _counter(values) -> dict:
    counts = defaultdict(int)
    for value in values:
        counts[value] += 1
    return {key: counts[key] for key in sorted(counts)}


def _finality_label(row, schedule_by_pk) -> str:
    if row.mlb_game_pk is None:
        return 'no_game_pk'
    rows = schedule_by_pk.get(row.mlb_game_pk)
    if not rows:
        return 'no_schedule_rows'
    facts = _schedule_facts(rows)
    if facts.has_final and facts.has_disqualifier:
        return 'final_and_disqualifier'
    if facts.has_final:
        return 'final'
    if facts.has_disqualifier:
        return 'postponed_or_suspended'
    return 'no_final'


def _schedule_coverage(residual, schedule_by_pk) -> dict:
    game_pks = {r.mlb_game_pk for r in residual if r.mlb_game_pk is not None}
    rows_with = sum(1 for r in residual
                    if r.mlb_game_pk is not None and schedule_by_pk.get(r.mlb_game_pk))
    with_final = with_postponed = with_suspended = 0
    with_contradictory = with_incomplete = without_final = 0
    for pk in game_pks:
        rows = schedule_by_pk.get(pk)
        if not rows:
            continue
        facts = _schedule_facts(rows)
        if facts.has_final:
            with_final += 1
        else:
            without_final += 1
        if ScheduledGame.STATE_POSTPONED in facts.states:
            with_postponed += 1
        if ScheduledGame.STATE_SUSPENDED in facts.states:
            with_suspended += 1
        if facts.has_final and facts.has_disqualifier:
            with_contradictory += 1
        if facts.side_status == 'incomplete':
            with_incomplete += 1
    return {
        'rows_with_schedule': rows_with,
        'rows_without_schedule': len(residual) - rows_with,
        'games_with_final': with_final,
        'games_without_final': without_final,
        'games_with_postponed': with_postponed,
        'games_with_suspended': with_suspended,
        'games_with_contradictory_states': with_contradictory,
        'games_with_incomplete_sides': with_incomplete,
        'games_with_contradictory_authority': sum(
            1 for pk in game_pks
            if schedule_by_pk.get(pk) and _side_status(schedule_by_pk[pk]) == 'contradictory'
        ),
    }


def _aggregation_relevance(residual, category_of, campaign_end) -> dict:
    """Whether a residual row is a completed regular-season appearance an aggregation
    through the cutoff would need attributed. Only FINAL, in-window, regular-season
    residuals count as relevant; everything else is not relevant (or uncertain)."""
    relevant = not_relevant = uncertain = 0
    relevant_cats = {CAT_ELIGIBLE_NOT_SELECTED, CAT_CONTRADICTORY_FINALITY,
                     CAT_INCOMPLETE_SIDES, CAT_CONTRADICTORY_AUTHORITY, CAT_OTHER}
    for row in residual:
        cat = category_of[row.id]
        if cat == CAT_UNCLASSIFIED:
            uncertain += 1
        elif (cat in relevant_cats and row.game_date is not None
              and row.game_date <= campaign_end and row.game_type in REGULAR_SEASON_GAME_TYPES):
            relevant += 1
        else:
            not_relevant += 1
    return {
        'rows_relevant_through_campaign_cutoff': relevant,
        'rows_not_relevant_through_campaign_cutoff': not_relevant,
        'rows_relevance_uncertain': uncertain,
    }


def _row_samples(residual, category_of, schedule_by_pk, context_pks, *, limit) -> list:
    samples = []
    for row in residual[:limit]:
        rows = schedule_by_pk.get(row.mlb_game_pk) if row.mlb_game_pk is not None else None
        samples.append({
            'game_log_id': row.id,
            'game_pk': row.mlb_game_pk,
            'game_date': row.game_date.isoformat() if row.game_date else None,
            'game_type': row.game_type,
            'category': category_of[row.id],
            'safe_reason_code': category_of[row.id],
            'schedule_row_count': len(rows) if rows else 0,
            'schedule_states': sorted({r.status_state for r in rows}) if rows else [],
            'completed_context_present': row.mlb_game_pk in context_pks,
        })
    return samples


def _game_samples(residual, category_of, schedule_by_pk, *, limit) -> list:
    per_game_rows = defaultdict(list)
    for row in residual:
        if row.mlb_game_pk is not None:
            per_game_rows[row.mlb_game_pk].append(row)
    ordered_pks = sorted(
        per_game_rows,
        key=lambda pk: (min(r.game_date for r in per_game_rows[pk] if r.game_date) or date.min, pk),
    )
    samples = []
    for pk in ordered_pks[:limit]:
        rows = per_game_rows[pk]
        sched = schedule_by_pk.get(pk) or []
        first = rows[0]
        samples.append({
            'game_pk': pk,
            'game_date': first.game_date.isoformat() if first.game_date else None,
            'category': category_of[first.id],
            'residual_row_count': len(rows),
            'schedule_row_count': len(sched),
            'schedule_states': sorted({r.status_state for r in sched}) if sched else [],
            'team_side_summary': _side_status(sched) if sched else 'no_schedule_rows',
        })
    return samples


def _classify_result(*, total_rows, exact_eligible, reconcile, invalid, unclassified,
                     migration_head):
    reasons = []
    if exact_eligible > 0:
        reasons.append('backfill_eligible_rows_remain')
    if not reconcile:
        reasons.append('category_totals_do_not_reconcile')
    if invalid > 0:
        reasons.append('invalid_stored_states')
    if migration_head is not None and migration_head != [EXPECTED_MIGRATION_HEAD]:
        reasons.append('migration_head_mismatch')
    # Result precedence: (1) critical FAIL, (2) clean empty-population PASS,
    # (3) non-empty fully classified PASS, (4) genuine uncertainty INCONCLUSIVE.
    if reasons:
        return RESULT_FAIL, reasons
    # A clean zero-row residual population is the successful terminal state for
    # Foundation 2: every critical invariant above is already satisfied (exact-eligible,
    # reconciliation, invalid-state, migration-head), there is nothing left to classify,
    # and an empty population cannot carry unclassified rows. season_null_legacy is the
    # same season legacy-NULL count as total_rows, so it is necessarily 0 here.
    if total_rows == 0:
        return RESULT_PASS, ['no_residual_rows']
    if unclassified > 0:
        return RESULT_INCONCLUSIVE, ['unclassified_rows_remain']
    return RESULT_PASS, ['all_residual_rows_classified']


def _foundation_3_gate(result, aggregation, exact_eligible, unclassified) -> str:
    if (result != RESULT_PASS or exact_eligible > 0 or unclassified > 0
            or aggregation['rows_relevant_through_campaign_cutoff'] > 0
            or aggregation['rows_relevance_uncertain'] > 0):
        return 'blocked'
    return 'ready_for_review'


def _git_sha():
    import os
    return os.environ.get('GITHUB_SHA')
