from datetime import datetime, timezone

from sqlalchemy import desc

from models.game_log import GameLog
from models.pitcher import Pitcher
from services.bullpen_population import eligible_bullpen_pitchers
from services.team_board_delta_substrate import (
    CAPABILITY as DELTA_COMPARISON_AUTHORITY,
    COMPARABLE as DELTA_COMPARABLE,
    resolve_latest_team_state_comparison,
)
from utils.db import db


CAPABILITY = 'what_changed_since_last_game'

STATE_CHANGES = 'changes'
STATE_NO_CHANGES = 'no_changes'
STATE_STALE = 'stale'
STATE_NO_BASELINE = 'no_baseline'
STATE_UNAVAILABLE = 'unavailable'

TEAM_STATE_CHANGED = 'changed'
TEAM_STATE_UNCHANGED = 'unchanged'
TEAM_STATE_UNAVAILABLE = 'unavailable'
TEAM_STATE_UNAVAILABLE_LIMITATION = (
    'Team State comparison is unavailable for this publication window.'
)
REST_STATUS_UNAVAILABLE_LIMITATION = (
    'Rest Status comparison is unavailable for this publication window.'
)
ARM_READ_UNAVAILABLE_LIMITATION = (
    'Arm Read comparison is unavailable for this publication window.'
)
ARM_READ_PARTIAL_LIMITATION = (
    'Some Arm Read transitions are withheld because both governed published '
    'reads are not comparable.'
)
PUBLIC_ARM_READ_SEMANTIC_FAMILY = 'public_arm_read'


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
        'team_state_change': None,
        'team_state_comparison': {
            'status': TEAM_STATE_UNAVAILABLE,
            'reason_code': 'current_missing',
            'from_represented_date': None,
            'to_represented_date': None,
            'limitation': TEAM_STATE_UNAVAILABLE_LIMITATION,
        },
        'rest_status_change': None,
        'rest_status_comparison': {
            'status': TEAM_STATE_UNAVAILABLE,
            'reason_code': 'current_missing',
            'from_represented_date': None,
            'to_represented_date': None,
            'limitation': REST_STATUS_UNAVAILABLE_LIMITATION,
        },
        'arm_read_comparison': {
            'status': TEAM_STATE_UNAVAILABLE,
            'reason_code': 'current_missing',
            'from_represented_date': None,
            'to_represented_date': None,
            'previous_delta_snapshot_id': None,
            'current_delta_snapshot_id': None,
            'semantic_family': PUBLIC_ARM_READ_SEMANTIC_FAMILY,
            'comparison_authority': DELTA_COMPARISON_AUTHORITY,
            'method_version': None,
            'public_contract_version': None,
            'withheld_pitcher_count': 0,
            'limitation': ARM_READ_UNAVAILABLE_LIMITATION,
        },
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


def _team_state_lane(team_id, frozen=None):
    frozen = frozen or resolve_latest_team_state_comparison(team_id=team_id)
    window = frozen.get('comparison') or {}
    domain = (frozen.get('domains') or {}).get('team_state') or {}
    status = domain.get('status')
    comparison = {
        'status': TEAM_STATE_UNAVAILABLE,
        'reason_code': domain.get('reason_code') or status,
        'from_represented_date': window.get('from_represented_date'),
        'to_represented_date': window.get('to_represented_date'),
        'limitation': TEAM_STATE_UNAVAILABLE_LIMITATION,
    }
    if status != DELTA_COMPARABLE:
        return comparison, None

    previous = domain.get('previous') or {}
    current = domain.get('current') or {}
    previous_state = previous.get('public_state')
    current_state = current.get('public_state')
    if previous_state == current_state:
        comparison.update({
            'status': TEAM_STATE_UNCHANGED,
            'reason_code': None,
            'limitation': None,
        })
        return comparison, None

    previous_label = previous.get('public_label')
    current_label = current.get('public_label')
    comparison.update({
        'status': TEAM_STATE_CHANGED,
        'reason_code': None,
        'limitation': None,
    })
    return comparison, {
        'type': 'team_state_change',
        'from_state': previous_state,
        'from_label': previous_label,
        'to_state': current_state,
        'to_label': current_label,
        'from_date': window.get('from_represented_date'),
        'to_date': window.get('to_represented_date'),
        'summary': (
            f'Team State changed from {previous_label} to {current_label}.'
        ),
    }


def _rest_status_lane(frozen):
    window = frozen.get('comparison') or {}
    domain = (frozen.get('domains') or {}).get('rest_status') or {}
    status = domain.get('status')
    comparison = {
        'status': TEAM_STATE_UNAVAILABLE,
        'reason_code': domain.get('reason_code') or status,
        'from_represented_date': window.get('from_represented_date'),
        'to_represented_date': window.get('to_represented_date'),
        'limitation': REST_STATUS_UNAVAILABLE_LIMITATION,
    }
    if status != DELTA_COMPARABLE:
        return comparison, None

    previous = domain.get('previous') or {}
    current = domain.get('current') or {}
    previous_count = previous.get('rested_arm_count')
    current_count = current.get('rested_arm_count')
    if previous_count == current_count:
        comparison.update({
            'status': TEAM_STATE_UNCHANGED,
            'reason_code': None,
            'limitation': None,
        })
        return comparison, None

    comparison.update({
        'status': TEAM_STATE_CHANGED,
        'reason_code': None,
        'limitation': None,
    })
    return comparison, {
        'type': 'rest_status_change',
        'field': 'rested_arm_count',
        'label': 'Rested Options',
        'from_value': previous_count,
        'to_value': current_count,
        'from_date': window.get('from_represented_date'),
        'to_date': window.get('to_represented_date'),
        'transition': f'{previous_count} → {current_count}',
        'summary': (
            f'Rested options moved from {previous_count} to {current_count}.'
        ),
    }


def _arm_read_endpoint(record):
    public_read = (record or {}).get('public_read') or {}
    key = public_read.get('key')
    label = public_read.get('label')
    if not isinstance(key, str) or not key or not isinstance(label, str) or not label:
        return None
    return {'key': key, 'label': label}


def _arm_read_lane(frozen):
    window = frozen.get('comparison') or {}
    domain = (frozen.get('domains') or {}).get('arm_read') or {}
    status = domain.get('status')
    comparison = {
        'status': TEAM_STATE_UNAVAILABLE,
        'reason_code': domain.get('reason_code') or status,
        'from_represented_date': window.get('from_represented_date'),
        'to_represented_date': window.get('to_represented_date'),
        'previous_delta_snapshot_id': window.get('previous_delta_snapshot_id'),
        'current_delta_snapshot_id': window.get('current_delta_snapshot_id'),
        'semantic_family': PUBLIC_ARM_READ_SEMANTIC_FAMILY,
        'comparison_authority': DELTA_COMPARISON_AUTHORITY,
        'method_version': domain.get('method_version'),
        'public_contract_version': domain.get('public_contract_version'),
        'withheld_pitcher_count': 0,
        'limitation': ARM_READ_UNAVAILABLE_LIMITATION,
    }
    if status != DELTA_COMPARABLE:
        return comparison, []

    arm_comparisons = domain.get('arm_comparisons')
    movement_candidates = domain.get('movement_candidates')
    if not isinstance(arm_comparisons, list) or not isinstance(
        movement_candidates, list
    ):
        comparison['reason_code'] = 'value_missing'
        return comparison, []

    withheld = [
        arm for arm in arm_comparisons
        if not isinstance(arm, dict) or arm.get('comparable') is not True
    ]
    changes = []
    invalid_candidates = 0
    for movement in movement_candidates:
        movement = movement if isinstance(movement, dict) else {}
        previous = movement.get('previous') or {}
        current = movement.get('current') or {}
        from_read = _arm_read_endpoint(previous)
        to_read = _arm_read_endpoint(current)
        pitcher_id = movement.get('pitcher_id')
        pitcher_name = current.get('pitcher_name')
        if (
            from_read is None
            or to_read is None
            or pitcher_id is None
            or not isinstance(pitcher_name, str)
            or not pitcher_name.strip()
        ):
            invalid_candidates += 1
            continue
        pitcher_name = pitcher_name.strip()
        changes.append({
            'type': 'arm_read_change',
            'semantic_family': PUBLIC_ARM_READ_SEMANTIC_FAMILY,
            'pitcher_id': pitcher_id,
            'pitcher_name': pitcher_name,
            'from_read': from_read,
            'to_read': to_read,
            'from_date': window.get('from_represented_date'),
            'to_date': window.get('to_represented_date'),
            'summary': (
                f'{pitcher_name} moved from {from_read["label"]} '
                f'to {to_read["label"]}.'
            ),
        })

    withheld_count = len(withheld) + invalid_candidates
    comparison['withheld_pitcher_count'] = withheld_count
    if withheld_count:
        comparison.update({
            'status': 'partial',
            'reason_code': next((
                arm.get('reason_code')
                for arm in withheld
                if isinstance(arm, dict) and arm.get('reason_code')
            ), 'value_missing'),
            'limitation': ARM_READ_PARTIAL_LIMITATION,
        })
    else:
        comparison.update({
            'status': TEAM_STATE_CHANGED if changes else TEAM_STATE_UNCHANGED,
            'reason_code': None,
            'limitation': None,
        })
    return comparison, changes


def _apply_terminal_state(payload, state, reason_codes, limitations):
    team_state_change = payload.get('team_state_change')
    rest_status_change = payload.get('rest_status_change')
    arm_read_change = any(
        change.get('type') == 'arm_read_change'
        for change in payload.get('pitcher_changes') or []
        if isinstance(change, dict)
    )
    if team_state_change or rest_status_change or arm_read_change:
        payload.update({
            'state': STATE_CHANGES,
            'state_reason_codes': _merge_unique(
                ['meaningful_changes_detected'],
                ['team_state_change_detected'] if team_state_change else [],
                ['rest_status_change_detected'] if rest_status_change else [],
                ['arm_read_change_detected'] if arm_read_change else [],
                reason_codes,
            ),
            'limitations': limitations,
        })
    else:
        payload.update({
            'state': state,
            'state_reason_codes': reason_codes,
            'limitations': limitations,
        })
    return payload


def build_team_changes_payload(team_id, freshness=None, generated_at=None):
    """
    Build the team-scoped "What Changed Since Last Game" payload.

    Team State, Rested Options, and Arm Read movement come only from comparable
    trusted publication sidecars. New appearances use existing game logs and
    durable freshness metadata. This service does not rank, select, recommend,
    predict, or modify the Availability Engine.
    """
    team = _team_info(team_id)
    payload = _base_payload(team, freshness=freshness, generated_at=generated_at)
    frozen = resolve_latest_team_state_comparison(team_id=team_id)
    team_state_comparison, team_state_change = _team_state_lane(
        team_id, frozen=frozen,
    )
    rest_status_comparison, rest_status_change = _rest_status_lane(frozen)
    arm_read_comparison, arm_read_changes = _arm_read_lane(frozen)
    payload.update({
        'team_state_comparison': team_state_comparison,
        'team_state_change': team_state_change,
        'rest_status_comparison': rest_status_comparison,
        'rest_status_change': rest_status_change,
        'arm_read_comparison': arm_read_comparison,
        'pitcher_changes': arm_read_changes,
    })

    # Resolve the team's data-derived game dates up front and publish the current
    # game reference date before any freshness gate can short-circuit. The board,
    # pitcher detail, and bullpen endpoints all expose this data-derived date
    # regardless of wall-clock staleness, so the changes surface must advertise the
    # same date for every availability-related endpoint to agree. Freshness gating
    # below still governs whether *deltas* are computed — not whether the basic
    # current game date is known. Governed Arm Read movement above remains
    # bound to the frozen publication comparison and never uses these live
    # game-date availability inputs.
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
        return _apply_terminal_state(
            payload, blocker_state, blocker_codes, blocker_limitations,
        )

    if not dates:
        return _apply_terminal_state(
            payload,
            STATE_UNAVAILABLE,
            ['team_game_logs_missing'],
            ['No completed game logs are available for this team.'],
        )

    if len(dates) < 2:
        return _apply_terminal_state(
            payload,
            STATE_NO_BASELINE,
            _merge_unique(
                ['previous_team_game_missing'],
                team_reason_codes,
            ),
            _merge_unique(
                ['No earlier completed game is available for comparison.'],
                team_limitations,
            ),
        )

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
    appearance_changes = _appearance_changes(team_id, anchor_date, current_date, pitcher_ids)
    # Suppress team-level summary counts until they can be guaranteed to match
    # the current board / Follow My Team population for the same data date.
    team_summary = None

    pitcher_changes = arm_read_changes + appearance_changes
    payload.update({
        'pitcher_changes': pitcher_changes,
        'team_summary': team_summary,
        'limitations': _merge_unique(
            freshness.get('limitations') if freshness else [],
            team_limitations,
        ),
    })

    if pitcher_changes or team_summary or team_state_change or rest_status_change:
        payload['state'] = STATE_CHANGES
        payload['state_reason_codes'] = _merge_unique(
            ['meaningful_changes_detected'],
            ['team_state_change_detected'] if team_state_change else [],
            ['rest_status_change_detected'] if rest_status_change else [],
            ['arm_read_change_detected'] if arm_read_changes else [],
            team_reason_codes,
        )
    else:
        payload['state'] = STATE_NO_CHANGES
        payload['state_reason_codes'] = _merge_unique(
            ['no_meaningful_changes_detected'],
            team_reason_codes,
        )

    return payload
