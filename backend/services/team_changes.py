from datetime import datetime, time, timedelta, timezone

from sqlalchemy import desc

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import ACTIVE_WINDOW_DAYS, classify_availability
from services.bullpen_board import BOARD_GROUP_ORDER
from services.bullpen_population import eligible_bullpen_pitchers
from utils.db import db


CAPABILITY = 'what_changed_since_last_game'

STATE_CHANGES = 'changes'
STATE_NO_CHANGES = 'no_changes'
STATE_STALE = 'stale'
STATE_NO_BASELINE = 'no_baseline'
STATE_UNAVAILABLE = 'unavailable'

STATUS_ORDER = {status: index for index, status in enumerate(BOARD_GROUP_ORDER)}


def _iso_date(value):
    return value.isoformat() if value else None


def _date_from_iso(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).date()
    except ValueError:
        return None


def _display_date(value):
    if value is None:
        return None
    return f'{value:%b} {value.day}'


def _end_of_day(value):
    return datetime.combine(value, time.max)


def _generated_at():
    return datetime.now(timezone.utc).isoformat()


def _merge_unique(*groups):
    merged = []
    for group in groups:
        for value in group or []:
            if value not in merged:
                merged.append(value)
    return merged


def _team_info(team_id):
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


def _team_short_name(team):
    return team.get('team_abbreviation') or team.get('team_name') or f"Team {team.get('team_id')}"


def _base_payload(team, freshness=None, generated_at=None):
    return {
        'capability': CAPABILITY,
        'team': team,
        'generated_at': generated_at or _generated_at(),
        'ranking_applied': False,
        'selection_made': False,
        'state': STATE_UNAVAILABLE,
        'state_reason_codes': [],
        'comparison': {
            'anchor_game_date': None,
            'current_game_date': None,
            'team_latest_game_date': None,
            'global_latest_game_date': (freshness or {}).get('data_through'),
            'label': None,
            'is_current': bool((freshness or {}).get('is_current') is True),
            'team_data_behind_league': False,
        },
        'pitcher_changes': [],
        'team_summary': None,
        'limitations': [],
        'freshness': freshness or {},
    }


def _freshness_blocker(freshness):
    if not freshness:
        return (
            STATE_STALE,
            ['freshness_metadata_missing'],
            ['Freshness metadata is unavailable; changes cannot be computed reliably.'],
        )

    reason_codes = list(freshness.get('reason_codes') or [])
    limitations = list(freshness.get('limitations') or [])
    if freshness.get('freshness_state') == 'missing' or 'workload_data_missing' in reason_codes:
        return (
            STATE_UNAVAILABLE,
            _merge_unique(reason_codes, ['workload_data_missing']),
            _merge_unique(limitations, ['No completed workload data is available for comparison.']),
        )

    blocking_codes = []

    if freshness.get('sync_authority') != 'sync_runs':
        blocking_codes.append('durable_sync_authority_missing')
        limitations.append('Durable sync metadata is not the freshness authority.')
    if not freshness.get('last_successful_sync'):
        blocking_codes.append('successful_sync_missing')
        limitations.append('No durable successful sync timestamp is available.')
    if 'durable_sync_metadata_unavailable' in reason_codes:
        blocking_codes.append('durable_sync_metadata_unavailable')
        limitations.append('Durable sync metadata is unavailable.')
    if freshness.get('is_current') is not True or freshness.get('freshness_state') != 'current':
        blocking_codes.append('workload_data_not_current')
        limitations.append('Current workload data is not fresh enough to compare safely.')

    if blocking_codes:
        return STATE_STALE, _merge_unique(reason_codes, blocking_codes), _merge_unique(limitations)
    return None, [], []


def _team_game_dates(team_id):
    rows = (
        db.session.query(GameLog.game_date)
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(Pitcher.team_id == team_id)
        .distinct()
        .order_by(desc(GameLog.game_date))
        .limit(2)
        .all()
    )
    return [row[0] for row in rows]


def _comparison_label(team, anchor_date, current_date):
    team_name = _team_short_name(team)
    return (
        f'Compared with {team_name}: '
        f'{_display_date(anchor_date)} -> {_display_date(current_date)}'
    )


def _team_freshness_notes(team, current_date, freshness):
    global_latest = _date_from_iso((freshness or {}).get('data_through'))
    if global_latest is None:
        global_latest = _date_from_iso((freshness or {}).get('latest_workload_date'))
    if global_latest is None or current_date is None or current_date >= global_latest:
        return global_latest, [], []

    team_name = _team_short_name(team)
    limitation = (
        f'{team_name} latest game data is {_display_date(current_date)} while '
        f'league data is current through {_display_date(global_latest)}.'
    )
    return global_latest, ['team_data_behind_league'], [limitation]


def _latest_scores(pitcher_ids):
    if not pitcher_ids:
        return {}
    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc'),
        )
        .filter(FatigueScore.pitcher_id.in_(pitcher_ids))
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )
    rows = (
        db.session.query(FatigueScore)
        .join(
            subq,
            (FatigueScore.pitcher_id == subq.c.pitcher_id)
            & (FatigueScore.calculated_at == subq.c.max_calc),
        )
        .all()
    )
    return {score.pitcher_id: score for score in rows}


def _scores_at_or_before(pitcher_ids, anchor_date):
    if not pitcher_ids:
        return {}
    cutoff = _end_of_day(anchor_date)
    subq = (
        db.session.query(
            FatigueScore.pitcher_id,
            db.func.max(FatigueScore.calculated_at).label('max_calc'),
        )
        .filter(
            FatigueScore.pitcher_id.in_(pitcher_ids),
            FatigueScore.calculated_at <= cutoff,
        )
        .group_by(FatigueScore.pitcher_id)
        .subquery()
    )
    rows = (
        db.session.query(FatigueScore)
        .join(
            subq,
            (FatigueScore.pitcher_id == subq.c.pitcher_id)
            & (FatigueScore.calculated_at == subq.c.max_calc),
        )
        .all()
    )
    return {score.pitcher_id: score for score in rows}


def _availability_context(pitcher_id, reference_date):
    latest_game_date = (
        db.session.query(db.func.max(GameLog.game_date))
        .filter(GameLog.pitcher_id == pitcher_id, GameLog.game_date <= reference_date)
        .scalar()
    )
    window_start = reference_date - timedelta(days=4)
    logs = (
        GameLog.query
        .filter(
            GameLog.pitcher_id == pitcher_id,
            GameLog.game_date >= window_start,
            GameLog.game_date <= reference_date,
        )
        .order_by(desc(GameLog.game_date))
        .all()
    )
    return logs, latest_game_date


def _availability_as_of(pitcher_id, score, reference_date):
    logs, latest_game_date = _availability_context(pitcher_id, reference_date)
    return classify_availability(
        score=score,
        game_logs=logs,
        reference_date=reference_date,
        latest_game_date=latest_game_date,
        active_window_days=ACTIVE_WINDOW_DAYS,
    )


def _status_change_summary(name, previous_status, current_status):
    previous_index = STATUS_ORDER.get(previous_status, 0)
    current_index = STATUS_ORDER.get(current_status, 0)
    if current_index < previous_index:
        return f'{name} recovered from {previous_status} to {current_status}.'
    return f'{name} moved from {previous_status} to {current_status}.'


def _status_changes(pitchers, anchor_scores, current_scores, anchor_date, current_date):
    changes = []
    limitations = []
    anchor_statuses = {}
    current_statuses = {}

    for pitcher in pitchers:
        current_score = current_scores.get(pitcher.id)
        anchor_score = anchor_scores.get(pitcher.id)

        if current_score is None:
            limitations.append(
                f'Current workload score missing for {pitcher.full_name}; status change not compared.'
            )
            continue
        if anchor_score is None:
            limitations.append(
                f'Anchor workload score missing for {pitcher.full_name}; status change not compared.'
            )
            continue

        anchor_availability = _availability_as_of(pitcher.id, anchor_score, anchor_date)
        current_availability = _availability_as_of(pitcher.id, current_score, current_date)
        previous_status = anchor_availability.get('availability_status')
        current_status = current_availability.get('availability_status')
        anchor_statuses[pitcher.id] = previous_status
        current_statuses[pitcher.id] = current_status

        if previous_status and current_status and previous_status != current_status:
            changes.append({
                'type': 'status_change',
                'pitcher_id': pitcher.id,
                'pitcher_name': pitcher.full_name,
                'from_status': previous_status,
                'to_status': current_status,
                'summary': _status_change_summary(
                    pitcher.full_name,
                    previous_status,
                    current_status,
                ),
            })

    return changes, anchor_statuses, current_statuses, _merge_unique(limitations)


def _appearance_summary(game_date, pitches):
    weekday = game_date.strftime('%A')
    if pitches is None:
        return f'Pitched {weekday}.'
    return f'Pitched {weekday} - {int(pitches)} pitches.'


def _appearance_changes(team_id, anchor_date, current_date, pitcher_ids):
    if not pitcher_ids:
        return []

    rows = (
        db.session.query(GameLog, Pitcher)
        .join(Pitcher, Pitcher.id == GameLog.pitcher_id)
        .filter(
            Pitcher.team_id == team_id,
            Pitcher.id.in_(pitcher_ids),
            GameLog.game_date > anchor_date,
            GameLog.game_date <= current_date,
        )
        .order_by(GameLog.game_date.desc(), Pitcher.full_name)
        .all()
    )

    changes = []
    for log, pitcher in rows:
        changes.append({
            'type': 'appearance',
            'pitcher_id': pitcher.id,
            'pitcher_name': pitcher.full_name,
            'game_date': _iso_date(log.game_date),
            'pitches': log.pitches_thrown,
            'summary': _appearance_summary(log.game_date, log.pitches_thrown),
        })
    return changes


def build_team_changes_payload(team_id, freshness=None, generated_at=None):
    """
    Build the team-scoped "What Changed Since Last Game" payload.

    This reads existing game logs, fatigue history, and durable freshness
    metadata only. It does not rank, select, recommend, predict, or modify the
    Availability Engine.
    """
    team = _team_info(team_id)
    payload = _base_payload(team, freshness=freshness, generated_at=generated_at)

    # Resolve the team's data-derived game dates up front and publish the current
    # game reference date before any freshness gate can short-circuit. The board,
    # pitcher detail, and bullpen endpoints all expose this data-derived date
    # regardless of wall-clock staleness, so the changes surface must advertise the
    # same date for every availability-related endpoint to agree. Freshness gating
    # below still governs whether *deltas* are computed — not whether the basic
    # current game date is known.
    dates = _team_game_dates(team_id)
    current_date = dates[0] if dates else None
    global_latest_date, team_reason_codes, team_limitations = _team_freshness_notes(
        team,
        current_date,
        freshness,
    )
    if current_date is not None:
        payload['comparison'].update({
            'current_game_date': _iso_date(current_date),
            'team_latest_game_date': _iso_date(current_date),
            'global_latest_game_date': _iso_date(global_latest_date),
            'team_data_behind_league': bool(team_reason_codes),
        })

    blocker_state, blocker_codes, blocker_limitations = _freshness_blocker(freshness)
    if blocker_state:
        payload.update({
            'state': blocker_state,
            'state_reason_codes': blocker_codes,
            'limitations': blocker_limitations,
        })
        return payload

    if not dates:
        payload.update({
            'state': STATE_UNAVAILABLE,
            'state_reason_codes': ['team_game_logs_missing'],
            'limitations': ['No completed game logs are available for this team.'],
        })
        return payload

    if len(dates) < 2:
        payload.update({
            'state': STATE_NO_BASELINE,
            'state_reason_codes': _merge_unique(
                ['previous_team_game_missing'],
                team_reason_codes,
            ),
            'limitations': _merge_unique(
                ['No earlier completed game is available for comparison.'],
                team_limitations,
            ),
        })
        return payload

    anchor_date = dates[1]
    payload['comparison'].update({
        'anchor_game_date': _iso_date(anchor_date),
        'label': _comparison_label(team, anchor_date, current_date),
    })

    pitchers = eligible_bullpen_pitchers(
        team_id,
        include_stale=False,
        reference_date=current_date,
    )
    pitcher_ids = [pitcher.id for pitcher in pitchers]
    current_scores = _latest_scores(pitcher_ids)
    anchor_scores = _scores_at_or_before(pitcher_ids, anchor_date)

    status_changes, _anchor_statuses, _current_statuses, coverage_limitations = _status_changes(
        pitchers,
        anchor_scores,
        current_scores,
        anchor_date,
        current_date,
    )
    appearance_changes = _appearance_changes(team_id, anchor_date, current_date, pitcher_ids)
    # Suppress team-level summary counts until they can be guaranteed to match
    # the current board / Follow My Team population for the same data date.
    team_summary = None

    pitcher_changes = status_changes + appearance_changes
    payload.update({
        'pitcher_changes': pitcher_changes,
        'team_summary': team_summary,
        'limitations': _merge_unique(
            freshness.get('limitations') if freshness else [],
            coverage_limitations,
            team_limitations,
        ),
    })

    if pitcher_changes or team_summary:
        payload['state'] = STATE_CHANGES
        payload['state_reason_codes'] = _merge_unique(
            ['meaningful_changes_detected'],
            team_reason_codes,
        )
    else:
        payload['state'] = STATE_NO_CHANGES
        payload['state_reason_codes'] = _merge_unique(
            ['no_meaningful_changes_detected'],
            team_reason_codes,
        )

    return payload
