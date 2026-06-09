"""
Schedule / game-context adapter for bullpen framing.

This is descriptive context only. It frames *when* a bullpen last pitched and
*who* it played so the availability views have a day-of-games anchor. It is NOT
a scoreboard, a matchup engine, or a prediction system, and it never ranks teams
or recommends anything.

The app's durable stored data is MLB game logs, which carry the opponent and
game date but NOT home/away or scheduled time (the MLB gameLog endpoint does not
return them). Those fields are therefore reported as missing rather than
fabricated, and this context is labelled as stored game-log context — never as an
authoritative live schedule. Everything respects the freshness model: a context
is labelled live / historical / stale / unavailable, never silently presented as
current. No live network call is made here.
"""

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_reference_date import product_current_date
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from services.bullpen_board import BOARD_GROUP_ORDER, build_team_context
from utils.db import db


# Stored game logs never carry these — reported honestly as missing.
GAME_LOG_MISSING_FIELDS = ['home_away', 'scheduled_time']
SOURCE_LABEL = 'Stored game-log context'


def _default_reference_date():
    return product_current_date()


def _data_state_for(days_ago):
    """Honest freshness label for how old the stored game is."""
    if days_ago is None:
        return 'unavailable'
    if days_ago == 0:
        return 'live'
    if days_ago <= ACTIVE_WINDOW_DAYS:
        return 'historical'
    return 'stale'


def _team_identity(team_id):
    row = (
        db.session.query(Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation)
        .filter(Pitcher.team_id == team_id)
        .first()
    )
    if row is None:
        return {'team_id': team_id, 'team_name': None, 'team_abbreviation': None}
    return {
        'team_id': row.team_id,
        'team_name': row.team_name,
        'team_abbreviation': row.team_abbreviation,
    }


def _context_confidence(opponent, data_state):
    """Confidence is capped at medium — home/away and time are never available."""
    if data_state == 'unavailable':
        return 'none'
    if opponent is None or data_state == 'stale':
        return 'low'
    return 'medium'


# ── Team game context (stored game-log only) ───────────────────────────────

def build_team_game_context(team_id, reference_date=None):
    """
    Compact game context for one team's most recent stored game on/before today.

    Derived entirely from durable GameLog data — no live schedule call. Supports
    historical fallback: if there is no game today, the latest stored game is
    returned and labelled accordingly. Home/away and scheduled time are not in the
    stored data, so they are reported in ``missing_fields`` rather than fabricated.

    States:
      * 'stored_game_log' — a stored game was found (possibly historical).
      * 'no_game_found'    — the team exists but has no stored game.
      * 'unavailable'      — no team/schedule context is available at all.
    """
    ref = reference_date or _default_reference_date()
    team = _team_identity(team_id)

    latest_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
        .filter(Pitcher.team_id == team_id, GameLog.game_date <= ref)
        .scalar()
    )

    if latest_game_date is None:
        unknown_team = team['team_name'] is None and team['team_abbreviation'] is None
        return {
            'capability': 'team_game_context',
            'team': team,
            'available': False,
            'state': 'unavailable' if unknown_team else 'no_game_found',
            'data_source': 'game_log',
            'data_state': 'unavailable',
            'source_label': SOURCE_LABEL,
            'confidence': 'none',
            'message': (
                'Schedule context unavailable.'
                if unknown_team
                else 'No game found in the stored game log for this date.'
            ),
            'reference_date': ref.isoformat(),
            'game_date': None,
            'opponent': None,
            'opponent_abbreviation': None,
            'home_away': None,
            'scheduled_time': None,
            'game_status': None,
            'is_today': False,
            'days_ago': None,
            'missing_fields': list(GAME_LOG_MISSING_FIELDS),
        }

    log = (
        GameLog.query
        .join(Pitcher, GameLog.pitcher_id == Pitcher.id)
        .filter(Pitcher.team_id == team_id, GameLog.game_date == latest_game_date)
        .order_by(desc(GameLog.mlb_game_pk))
        .first()
    )
    days_ago = (ref - latest_game_date).days
    is_today = days_ago == 0
    data_state = _data_state_for(days_ago)
    opponent = log.opponent if log else None

    missing_fields = list(GAME_LOG_MISSING_FIELDS)
    if opponent is None:
        missing_fields.append('opponent')

    return {
        'capability': 'team_game_context',
        'team': team,
        'available': True,
        'state': 'stored_game_log',
        'data_source': 'game_log',
        # Stored game logs are not a live schedule; label by recency, honestly.
        'data_state': data_state,
        'source_label': SOURCE_LABEL,
        'confidence': _context_confidence(opponent, data_state),
        'message': None,
        'reference_date': ref.isoformat(),
        'game_date': latest_game_date.isoformat(),
        'opponent': opponent,
        'opponent_abbreviation': log.opponent_abbreviation if log else None,
        # Not present in the stored game-log data — reported honestly as unknown.
        'home_away': None,
        'scheduled_time': None,
        'game_status': 'final',
        'is_today': is_today,
        'days_ago': days_ago,
        'missing_fields': missing_fields,
    }


# ── League-wide bullpen landscape ──────────────────────────────────────────

def _team_buckets(records):
    """Group classified availability records by team into status counts."""
    buckets = {}
    for record in records:
        pitcher = record.get('pitcher')
        if pitcher is None:
            continue
        bucket = buckets.setdefault(pitcher.team_id, {
            'team_id': pitcher.team_id,
            'team_name': pitcher.team_name,
            'team_abbreviation': pitcher.team_abbreviation,
            'counts': {status: 0 for status in BOARD_GROUP_ORDER},
        })
        status = (record.get('availability') or {}).get('availability_status')
        if status in bucket['counts']:
            bucket['counts'][status] += 1
    return buckets


def _landscape_entry(bucket):
    counts = bucket['counts']
    groups = [{'status': status, 'count': counts[status]} for status in BOARD_GROUP_ORDER]
    context = build_team_context(groups)
    metrics = context['metrics']
    return {
        'team_id': bucket['team_id'],
        'team_name': bucket['team_name'],
        'team_abbreviation': bucket['team_abbreviation'],
        'total_relievers': metrics['total_relievers'],
        'available': metrics['available'],
        'monitor': metrics['monitor'],
        'restricted': metrics['restricted'],
        'pct_available': metrics['pct_available'],
        'pct_restricted': metrics['pct_restricted'],
        'health_state': context['health']['state'],
        'health_label': context['health']['label'],
    }


def _games_block(reference_date=None):
    ref = reference_date or _default_reference_date()
    latest_game_date = db.session.query(db.func.max(GameLog.game_date)).scalar()
    if latest_game_date is None:
        return {
            'available': False,
            'data_state': 'unavailable',
            'message': 'Schedule context unavailable.',
            'today_count': 0,
            'as_of_date': None,
            'as_of_count': 0,
            'is_today': False,
        }

    def _distinct_games_on(day):
        return int(
            db.session.query(db.func.count(db.func.distinct(GameLog.mlb_game_pk)))
            .filter(GameLog.game_date == day)
            .scalar()
            or 0
        )

    days_ago = (ref - latest_game_date).days
    return {
        'available': True,
        'data_state': _data_state_for(days_ago),
        'message': None,
        'today_count': _distinct_games_on(ref),
        # The most recent slate present in the stored data (historical anchor).
        'as_of_date': latest_game_date.isoformat(),
        'as_of_count': _distinct_games_on(latest_game_date),
        'is_today': days_ago == 0,
    }


def _landscape_notes(games):
    # Disclaimers are worded to avoid advisory vocabulary entirely (no
    # best/worst/advice/forecast language), so the surface stays descriptive.
    notes = [
        'Descriptive groupings of bullpen situations only — this is bullpen context, not a league ranking or a game forecast.',
        'Sorted deterministically by count, then percentage, then team name.',
    ]
    state = (games or {}).get('data_state')
    if state == 'unavailable':
        notes.append('Schedule context unavailable; bullpen situations reflect the latest workload data only.')
    elif state in ('historical', 'stale'):
        notes.append('Game context is from the latest stored game log, not a live schedule.')
    return notes


def build_landscape(records=None, reference_date=None, freshness=None, top_n=3):
    """
    League-wide bullpen landscape: which bullpens are most constrained, most
    available, and carrying the most monitoring, plus a stored games anchor.

    Sorting is descriptive and deterministic (by count, then percentage, then
    team name) — it surfaces *situations*, not a ranking or recommendation, and
    never uses best / worst / advantage language. ``records`` may be supplied by
    the caller to avoid re-classifying; otherwise they are computed here.
    """
    ref = reference_date or _default_reference_date()
    if records is None:
        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(),
            reference_date=ref,
            mode=CURRENT_AVAILABILITY_MODE,
        )

    buckets = _team_buckets(records)
    entries = [
        entry for entry in (_landscape_entry(bucket) for bucket in buckets.values())
        if entry['total_relievers'] > 0
    ]

    constrained_bullpens = [
        entry for entry in sorted(
            entries,
            key=lambda e: (-e['restricted'], -e['pct_restricted'], e['team_name'] or ''),
        )
        if entry['restricted'] > 0
    ][:top_n]

    available_bullpens = sorted(
        entries,
        key=lambda e: (-e['available'], -e['pct_available'], e['team_name'] or ''),
    )[:top_n]

    monitoring_concentration = [
        entry for entry in sorted(
            entries,
            key=lambda e: (-e['monitor'], e['team_name'] or ''),
        )
        if entry['monitor'] > 0
    ][:top_n]

    games = _games_block(ref)

    return {
        'capability': 'tonights_bullpen_landscape',
        'ranking_applied': False,
        'selection_made': False,
        'reference_date': ref.isoformat(),
        'teams_evaluated': len(entries),
        'games': games,
        'constrained_bullpens': constrained_bullpens,
        'available_bullpens': available_bullpens,
        'monitoring_concentration': monitoring_concentration,
        'freshness': freshness or {},
        'notes': _landscape_notes(games),
    }
