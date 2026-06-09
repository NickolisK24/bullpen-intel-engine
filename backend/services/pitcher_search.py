"""
Database-backed pitcher name search for trust-first discovery surfaces.

Search reads BaseballOS pitcher, team-assignment, roster-status, fatigue, and
game-log records only. It does not refresh or enrich data during the request.
"""

from datetime import timedelta
import unicodedata

from sqlalchemy import desc

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS, STATUS_UNAVAILABLE, classify_availability
from services.availability_reference_date import product_current_date
from services.roster_status import classify_roster_status, apply_roster_status_to_availability
from utils.db import db


DEFAULT_SEARCH_LIMIT = 10
MAX_SEARCH_LIMIT = 25
MIN_SEARCH_QUERY_LENGTH = 2

TEAM_ASSIGNMENT_ASSIGNED = 'ASSIGNED'
TEAM_ASSIGNMENT_NO_ORGANIZATION = 'NO_ORGANIZATION'
TEAM_ASSIGNMENT_UNKNOWN = 'UNKNOWN'

UNRESOLVED_TEAM_ASSIGNMENT_LIMITATION = (
    'Unavailable due to unresolved team assignment; no current organization is available for bullpen planning.'
)


def _normalize_search_text(value):
    normalized = unicodedata.normalize('NFKD', str(value or ''))
    ascii_folded = ''.join(
        char for char in normalized
        if not unicodedata.combining(char)
    )
    return ' '.join(ascii_folded.casefold().strip().split())


def _last_name(normalized_name):
    parts = normalized_name.split()
    return parts[-1] if parts else ''


def _match_rank(player_name, query):
    normalized_name = _normalize_search_text(player_name)
    normalized_last_name = _last_name(normalized_name)

    if not normalized_name:
        return None
    if normalized_name == query:
        return 0
    if normalized_name.startswith(query) or normalized_last_name.startswith(query):
        return 1
    if query in normalized_name or query in normalized_last_name:
        return 2
    return None


def _coerce_limit(limit):
    try:
        parsed = int(limit)
    except (TypeError, ValueError):
        parsed = DEFAULT_SEARCH_LIMIT
    return max(1, min(parsed, MAX_SEARCH_LIMIT))


def _latest_fatigue_score(pitcher_id):
    return (
        FatigueScore.query
        .filter_by(pitcher_id=pitcher_id)
        .order_by(desc(FatigueScore.calculated_at))
        .first()
    )


def _availability_context(pitcher_id, reference_date=None):
    ref = reference_date or product_current_date()
    latest_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id)
        .scalar()
    )
    window_start = ref - timedelta(days=4)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= ref,
        )
        .order_by(desc(GameLog.game_date))
        .all()
    )
    return logs, latest_game_date


def _final_availability_for(pitcher, score, reference_date=None):
    logs, latest_game_date = _availability_context(
        pitcher.id,
        reference_date=reference_date,
    )
    workload_signal = classify_availability(
        score=score,
        game_logs=logs,
        reference_date=reference_date or product_current_date(),
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )
    roster_status = classify_roster_status(pitcher)
    final_availability = apply_roster_status_to_availability(workload_signal, roster_status)
    return _apply_team_assignment_to_availability(final_availability, pitcher)


def _team_assignment_status(pitcher):
    return (getattr(pitcher, 'team_assignment_status', None) or '').upper()


def _has_authoritative_team_assignment(pitcher):
    return _team_assignment_status(pitcher) == TEAM_ASSIGNMENT_ASSIGNED


def _apply_team_assignment_to_availability(availability, pitcher):
    if _has_authoritative_team_assignment(pitcher):
        return availability

    merged = dict(availability or {})
    reasons = list(merged.get('reasons') or [])
    limitations = list(merged.get('limitations') or [])
    assignment_status = _team_assignment_status(pitcher)

    label = {
        TEAM_ASSIGNMENT_NO_ORGANIZATION: 'No organization',
        TEAM_ASSIGNMENT_UNKNOWN: 'Team assignment unknown',
    }.get(assignment_status, 'Team assignment unavailable')
    reason = f'Team assignment: {label}.'

    if reason not in reasons:
        reasons.insert(0, reason)
    if UNRESOLVED_TEAM_ASSIGNMENT_LIMITATION not in limitations:
        limitations.append(UNRESOLVED_TEAM_ASSIGNMENT_LIMITATION)

    merged['availability_status'] = STATUS_UNAVAILABLE
    merged['confidence'] = 'low'
    merged['reasons'] = reasons
    merged['limitations'] = limitations
    return merged


def _safe_team_fields(pitcher):
    if not _has_authoritative_team_assignment(pitcher):
        return {
            'team_id': None,
            'team_name': None,
        }

    return {
        'team_id': pitcher.team_id if pitcher.team_id is not None else None,
        'team_name': pitcher.team_name or None,
    }


def _serialize_pitcher_search_result(pitcher, reference_date=None):
    latest_score = _latest_fatigue_score(pitcher.id)
    availability = _final_availability_for(
        pitcher,
        latest_score,
        reference_date=reference_date,
    )
    roster_status = availability.get('roster_status') or classify_roster_status(pitcher)
    team = _safe_team_fields(pitcher)

    return {
        'player_id': pitcher.id,
        'player_name': pitcher.full_name,
        'team_id': team['team_id'],
        'team_name': team['team_name'],
        'position': pitcher.position or None,
        'roster_status': roster_status.get('status') or 'UNKNOWN',
        'availability': availability.get('availability_status') or 'Monitor',
    }


def search_pitchers_by_name(raw_query, limit=DEFAULT_SEARCH_LIMIT, reference_date=None):
    query = str(raw_query or '').strip()
    normalized_query = _normalize_search_text(query)
    safe_limit = _coerce_limit(limit)

    if len(normalized_query) < MIN_SEARCH_QUERY_LENGTH:
        return {
            'query': query,
            'min_query_length': MIN_SEARCH_QUERY_LENGTH,
            'results': [],
        }

    matches = []
    for pitcher in Pitcher.query.order_by(Pitcher.full_name, Pitcher.id).all():
        rank = _match_rank(pitcher.full_name, normalized_query)
        if rank is None:
            continue
        matches.append((rank, _normalize_search_text(pitcher.full_name), pitcher.id, pitcher))

    matches.sort(key=lambda item: (item[0], item[1], item[2]))

    return {
        'query': query,
        'min_query_length': MIN_SEARCH_QUERY_LENGTH,
        'results': [
            _serialize_pitcher_search_result(pitcher, reference_date=reference_date)
            for _, _, _, pitcher in matches[:safe_limit]
        ],
    }
