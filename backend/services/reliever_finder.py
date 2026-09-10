"""Bounded, intent-driven public read model for Reliever Finder.

This service reuses the existing fatigue, availability, roster, and bullpen-role
authorities.  It changes delivery only: callers must provide search/filter
intent, and the response is a compact paged projection rather than the legacy
league-scale fatigue carrier.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import timedelta
from math import ceil
from threading import RLock
from time import monotonic

from sqlalchemy import or_

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_snapshot import CURRENT_AVAILABILITY_MODE, classify_fatigue_rows
from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services.public_bullpen_copy import public_availability_label
from services.public_fatigue_view import public_availability, public_workload_facts
from utils.db import db


FINDER_CAPABILITY = 'reliever_finder_v1'
FINDER_MIN_QUERY_LENGTH = 2
FINDER_DEFAULT_LIMIT = 25
FINDER_MAX_LIMIT = 50
FINDER_SORTS = frozenset({'name', 'pitches', 'rest'})
FINDER_POPULATION_CACHE_MAX_ENTRIES = 4
FINDER_POPULATION_CACHE_TTL_SECONDS = 20
FINDER_AVAILABILITY_FILTERS = {
    'available': 'Available',
    'monitor': 'On Watch',
    'on watch': 'On Watch',
    'limited': 'Limited',
    'unavailable': 'Unavailable',
}
_population_cache = OrderedDict()
_population_cache_lock = RLock()


def normalize_finder_query(value):
    return ' '.join(str(value or '').strip().split())


def normalize_finder_availability(value):
    text = normalize_finder_query(value).casefold()
    return FINDER_AVAILABILITY_FILTERS.get(text) if text else None


def finder_has_intent(*, query='', team_id=None, availability=None):
    return (
        len(normalize_finder_query(query)) >= FINDER_MIN_QUERY_LENGTH
        or team_id is not None
        or normalize_finder_availability(availability) is not None
    )


def waiting_for_intent_payload():
    return {
        'capability': FINDER_CAPABILITY,
        'status': 'awaiting_intent',
        'data': [],
        'meta': {
            'query_executed': False,
            'min_query_length': FINDER_MIN_QUERY_LENGTH,
            'default_limit': FINDER_DEFAULT_LIMIT,
            'max_limit': FINDER_MAX_LIMIT,
            'sort': 'name',
            'page': 1,
            'limit': FINDER_DEFAULT_LIMIT,
            'total_results': None,
            'total_pages': None,
            'has_more': False,
            'next_page': None,
        },
        'ranking_applied': False,
        'selection_made': False,
    }


def _latest_score_query(*, team_id=None, query='', calculated_at_lte=None):
    score_scope = db.session.query(FatigueScore)
    if calculated_at_lte is not None:
        score_scope = score_scope.filter(FatigueScore.calculated_at <= calculated_at_lte)
    score_scope = score_scope.subquery()

    latest = (
        db.session.query(
            score_scope.c.pitcher_id,
            db.func.max(score_scope.c.calculated_at).label('max_calc'),
        )
        .group_by(score_scope.c.pitcher_id)
        .subquery()
    )
    result = (
        db.session.query(FatigueScore, Pitcher)
        .join(
            latest,
            (FatigueScore.pitcher_id == latest.c.pitcher_id)
            & (FatigueScore.calculated_at == latest.c.max_calc),
        )
        .join(Pitcher, FatigueScore.pitcher_id == Pitcher.id)
    )
    if team_id is not None:
        result = result.filter(Pitcher.team_id == team_id)

    text = normalize_finder_query(query)
    if len(text) >= FINDER_MIN_QUERY_LENGTH:
        pattern = f'%{text}%'
        result = result.filter(or_(
            Pitcher.full_name.ilike(pattern),
            Pitcher.team_name.ilike(pattern),
            Pitcher.team_abbreviation.ilike(pattern),
        ))
    return result


def _fresh_pitcher_ids(rows, *, reference_date):
    pitcher_ids = [pitcher.id for _score, pitcher in rows]
    if not pitcher_ids:
        return set()
    cutoff = reference_date - timedelta(days=ACTIVE_WINDOW_DAYS)
    return {
        row[0]
        for row in (
            db.session.query(GameLog.pitcher_id)
            .filter(GameLog.pitcher_id.in_(pitcher_ids))
            .group_by(GameLog.pitcher_id)
            .having(db.func.max(GameLog.game_date) >= cutoff)
            .all()
        )
    }


def _eligible_rows(rows, *, reference_date):
    rows = list(rows or [])
    contexts = eligible_bullpen_pitcher_contexts(
        [pitcher for _score, pitcher in rows],
        include_stale=True,
        include_inactive_context=False,
        include_unknown_roster=True,
        reference_date=reference_date,
    )
    eligible_ids = {context['pitcher'].id for context in contexts}
    return [row for row in rows if row[1].id in eligible_ids]


def _public_row(record):
    pitcher = record['pitcher']
    workload = public_workload_facts(record['score']) or {}
    availability = public_availability(record['availability']) or {}
    availability = dict(availability)
    availability['availability_public_label'] = public_availability_label(
        availability.get('availability_status')
    )
    return {
        **workload,
        'pitcher': {
            'id': pitcher.id,
            'mlb_id': pitcher.mlb_id,
            'full_name': pitcher.full_name,
            'team_id': pitcher.team_id,
            'team_name': pitcher.team_name,
            'team_abbreviation': pitcher.team_abbreviation,
        },
        'availability': availability,
        'destination': f'/pitcher/{pitcher.id}',
    }


def _sort_rows(rows, sort):
    def name_key(row):
        pitcher = row.get('pitcher') or {}
        return ((pitcher.get('full_name') or '').casefold(), pitcher.get('id') or 0)

    if sort == 'pitches':
        return sorted(
            rows,
            key=lambda row: (
                row.get('pitches_last_7_days') is None,
                -(row.get('pitches_last_7_days') or 0),
                name_key(row),
            ),
        )
    if sort == 'rest':
        return sorted(
            rows,
            key=lambda row: (
                row.get('days_since_last_appearance') is None,
                row.get('days_since_last_appearance') or 0,
                name_key(row),
            ),
        )
    return sorted(rows, key=name_key)


def clear_reliever_finder_population_cache():
    with _population_cache_lock:
        _population_cache.clear()


def _cached_population(cache_key):
    if cache_key is None:
        return None
    now = monotonic()
    with _population_cache_lock:
        cached = _population_cache.get(cache_key)
        if cached is None:
            return None
        expires_at, rows = cached
        if expires_at <= now:
            _population_cache.pop(cache_key, None)
            return None
        _population_cache.move_to_end(cache_key)
        return rows


def _store_population(cache_key, rows):
    if cache_key is None:
        return
    with _population_cache_lock:
        _population_cache[cache_key] = (
            monotonic() + FINDER_POPULATION_CACHE_TTL_SECONDS,
            rows,
        )
        _population_cache.move_to_end(cache_key)
        while len(_population_cache) > FINDER_POPULATION_CACHE_MAX_ENTRIES:
            _population_cache.popitem(last=False)


def _build_public_rows(
    *, query, team_id, include_stale, reference_date, score_cutoff,
):
    candidates = _latest_score_query(
        team_id=team_id,
        query=query,
        calculated_at_lte=score_cutoff,
    ).order_by(Pitcher.full_name, Pitcher.id).all()
    eligible = _eligible_rows(candidates, reference_date=reference_date)
    if not include_stale:
        fresh_ids = _fresh_pitcher_ids(eligible, reference_date=reference_date)
        eligible = [row for row in eligible if row[1].id in fresh_ids]
    records = classify_fatigue_rows(
        eligible,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    return [_public_row(record) for record in records]


def build_reliever_finder_payload(
    *,
    query='',
    team_id=None,
    availability=None,
    include_stale=False,
    sort='name',
    page=1,
    limit=FINDER_DEFAULT_LIMIT,
    reference_date,
    score_cutoff=None,
    source_identity=None,
):
    """Build one bounded Finder page after the route has established intent."""
    public_availability_filter = normalize_finder_availability(availability)
    broad_availability_query = (
        public_availability_filter is not None
        and not normalize_finder_query(query)
        and team_id is None
    )
    cache_key = None
    if broad_availability_query and source_identity is not None:
        cache_key = (
            tuple(source_identity),
            bool(include_stale),
        )
    rows = _cached_population(cache_key)
    if rows is None:
        rows = _build_public_rows(
            query=query,
            team_id=team_id,
            include_stale=include_stale,
            reference_date=reference_date,
            score_cutoff=score_cutoff,
        )
        _store_population(cache_key, rows)
    if public_availability_filter is not None:
        rows = [
            row for row in rows
            if (row.get('availability') or {}).get('availability_public_label')
            == public_availability_filter
        ]
    rows = _sort_rows(rows, sort)

    total_results = len(rows)
    total_pages = max(1, ceil(total_results / limit))
    start = (page - 1) * limit
    data = rows[start:start + limit]
    has_more = start + len(data) < total_results
    return {
        'capability': FINDER_CAPABILITY,
        'status': 'available' if data else 'empty',
        'data': data,
        'meta': {
            'query_executed': True,
            'min_query_length': FINDER_MIN_QUERY_LENGTH,
            'default_limit': FINDER_DEFAULT_LIMIT,
            'max_limit': FINDER_MAX_LIMIT,
            'page': page,
            'limit': limit,
            'total_results': total_results,
            'total_pages': total_pages,
            'has_more': has_more,
            'next_page': page + 1 if has_more else None,
            'sort': sort,
            'filters': {
                'q': normalize_finder_query(query) or None,
                'team_id': team_id,
                'availability': public_availability_filter,
                'include_stale': bool(include_stale),
            },
        },
        'ranking_applied': False,
        'selection_made': False,
    }


__all__ = [
    'FINDER_AVAILABILITY_FILTERS',
    'FINDER_CAPABILITY',
    'FINDER_DEFAULT_LIMIT',
    'FINDER_MAX_LIMIT',
    'FINDER_MIN_QUERY_LENGTH',
    'FINDER_POPULATION_CACHE_MAX_ENTRIES',
    'FINDER_POPULATION_CACHE_TTL_SECONDS',
    'FINDER_SORTS',
    'build_reliever_finder_payload',
    'clear_reliever_finder_population_cache',
    'finder_has_intent',
    'normalize_finder_availability',
    'normalize_finder_query',
    'waiting_for_intent_payload',
]
