"""Frozen TB-09 material changes over one exact trusted snapshot pair."""

from __future__ import annotations

from copy import deepcopy
from typing import Mapping

from services.team_board_snapshot_team_state import compare_exact_team_state
from services.what_changed_comparison_identity import (
    ComparisonIdentityInvalid,
    comparison_identity_from_payload,
    validate_snapshot_pair,
)


CONTRACT = 'team_board_what_changed_v1'
METHOD_VERSION = 'team_board_what_changed_v1'
EVENT_METHOD_VERSION = 'team_board_what_changed_event_v1'
QUIET_COPY = 'No material bullpen changes since the previous trusted update.'
MAX_EVENTS = 5

DOMAIN_ORDER = {
    'team_state': 1,
    'roster': 2,
    'workload_rest': 3,
    'transactions': 4,
    'rotation': 5,
}
PATTERNS = (
    ('back_to_back', 'back-to-back usage'),
    ('three_in_four', '3-in-4 usage'),
    ('four_in_six', '4-in-6 usage'),
    ('high_pitch_outing', 'a qualifying high-pitch outing'),
)


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _team(snapshot, team_id):
    package = _mapping(_mapping(getattr(snapshot, 'payload', None)).get('trusted_team_boards'))
    return _mapping(_mapping(package.get('by_team_id')).get(str(int(team_id))))


def _represented(snapshot):
    value = getattr(snapshot, 'data_through', None)
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _domain(status, reason_code=None, **facts):
    return {'status': status, 'reason_code': reason_code, **facts}


def _event(domain, event_type, *, current, previous, team_id, subject_id=None,
           event_date=None, previous_value=None, current_value=None, facts=None,
           summary=None):
    return {
        'event_type': event_type,
        'domain': domain,
        'team_id': int(team_id),
        'subject_id': subject_id,
        'event_date': event_date,
        'previous_value': previous_value,
        'current_value': current_value,
        'facts': deepcopy(facts or {}),
        'summary': summary,
        'evidence_status': 'complete',
        'current_snapshot_id': current.id,
        'previous_snapshot_id': previous.id,
        'method_version': EVENT_METHOD_VERSION,
    }


def _record_names(team):
    return {
        item['pitcher_id']: item.get('name')
        for item in team.get('records') or ()
        if isinstance(item, Mapping) and type(item.get('pitcher_id')) is int
    }


def _roster_events(previous, current, team_id, previous_team, current_team):
    previous_ids = set(previous_team.get('default_pitcher_ids') or ())
    current_ids = set(current_team.get('default_pitcher_ids') or ())
    previous_names = _record_names(previous_team)
    current_names = _record_names(current_team)
    events = []
    for pitcher_id in sorted(current_ids - previous_ids):
        name = current_names.get(pitcher_id) or f'Pitcher {pitcher_id}'
        events.append(_event(
            'roster', 'active_bullpen_joined', current=current, previous=previous,
            team_id=team_id, subject_id=pitcher_id, current_value='active',
            summary=f'{name} joined the active bullpen.',
            facts={'pitcher_name': name},
        ))
    for pitcher_id in sorted(previous_ids - current_ids):
        name = previous_names.get(pitcher_id) or f'Pitcher {pitcher_id}'
        events.append(_event(
            'roster', 'active_bullpen_left', current=current, previous=previous,
            team_id=team_id, subject_id=pitcher_id, previous_value='active',
            summary=f'{name} left the active bullpen.',
            facts={'pitcher_name': name},
        ))
    return events


def _transaction_events(previous, current, team_id, previous_team, current_team):
    previous_carrier = _mapping(previous_team.get('frozen_roster_transactions'))
    current_carrier = _mapping(current_team.get('frozen_roster_transactions'))
    if current_carrier.get('status') not in {'available', 'partial'}:
        return [], _domain('unavailable', 'current_transaction_evidence_unavailable')
    if previous_carrier.get('status') not in {'available', 'partial'}:
        return [], _domain('unavailable', 'previous_transaction_evidence_unavailable')
    prior_ids = {
        item.get('event_id') for item in previous_carrier.get('events') or ()
        if isinstance(item, Mapping) and item.get('event_id')
    }
    events = []
    for item in current_carrier.get('events') or ():
        if not isinstance(item, Mapping) or not item.get('event_id') or item.get('event_id') in prior_ids:
            continue
        if item.get('evidence_status') != 'complete':
            continue
        name = item.get('player_name') or f"Pitcher {item.get('player_id')}"
        label = item.get('label') or 'Roster transaction recorded'
        events.append(_event(
            'transactions', 'verified_transaction', current=current, previous=previous,
            team_id=team_id, subject_id=item.get('player_id'), event_date=item.get('date'),
            current_value=item.get('direction'), summary=f'{name}: {label}.',
            facts={
                'transaction_id': item.get('event_id'), 'pitcher_name': name,
                'label': label, 'direction': item.get('direction'),
            },
        ))
    status = 'partial' if 'partial' in {previous_carrier.get('status'), current_carrier.get('status')} else 'complete'
    return events, _domain(status, 'transaction_evidence_partial' if status == 'partial' else None)


def _link_roster_transactions(roster_events, transaction_events):
    """Attach one verified cause to a matching membership delta, without duplicates."""
    remaining = []
    for transaction in transaction_events:
        direction = transaction['facts'].get('direction')
        matching = next((
            event for event in roster_events
            if event.get('subject_id') == transaction.get('subject_id')
            and (
                (event['event_type'] == 'active_bullpen_joined' and direction == 'addition')
                or (event['event_type'] == 'active_bullpen_left' and direction == 'removal')
            )
        ), None)
        if matching is None:
            remaining.append(transaction)
            continue
        label = transaction['facts'].get('label')
        matching['event_date'] = transaction.get('event_date')
        matching['facts']['verified_transaction'] = deepcopy(transaction['facts'])
        if label:
            matching['summary'] = f"{matching['summary']} Verified transaction: {label}."
    return roster_events, remaining


def _usage_items(team):
    carrier = _mapping(team.get('recent_usage_rest'))
    if carrier.get('status') not in {'complete', 'partial'}:
        return None
    items = list(carrier.get('active_pitchers') or ()) + list(
        carrier.get('off_active_historical_contributors') or ()
    )
    return {
        item.get('pitcher_id'): item for item in items
        if isinstance(item, Mapping) and type(item.get('pitcher_id')) is int
    }


def _workload_events(previous, current, team_id, previous_team, current_team):
    before = _usage_items(previous_team)
    after = _usage_items(current_team)
    if before is None or after is None:
        return [], _domain('unavailable', 'usage_rest_evidence_unavailable')
    events = []
    partial = False
    for pitcher_id in sorted(after):
        current_item = after[pitcher_id]
        previous_item = before.get(pitcher_id)
        for key, label in PATTERNS:
            current_fact = _mapping(current_item.get(key))
            previous_fact = _mapping(previous_item.get(key)) if previous_item else {}
            if current_fact.get('status') != 'complete':
                partial = True
                continue
            if current_fact.get('value') is not True:
                continue
            if previous_fact.get('status') != 'complete':
                partial = True
                continue
            if previous_fact.get('value') is True:
                continue
            name = current_item.get('pitcher_name') or f'Pitcher {pitcher_id}'
            events.append(_event(
                'workload_rest', f'{key}_started', current=current, previous=previous,
                team_id=team_id, subject_id=pitcher_id,
                event_date=current_fact.get('most_recent_date'),
                previous_value=False, current_value=True,
                summary=f'{name} now has {label}.',
                facts={'pitcher_name': name, 'pattern': key, **dict(current_fact)},
            ))
    return events, _domain('partial' if partial else 'complete', 'usage_rest_comparison_partial' if partial else None)


def _rotation_events(previous, current, team_id, previous_team, current_team):
    before = _mapping(previous_team.get('frozen_rotation_impact'))
    after = _mapping(current_team.get('frozen_rotation_impact'))
    if before.get('status') not in {'complete', 'partial'} or after.get('status') not in {'complete', 'partial'}:
        return [], _domain('unavailable', 'rotation_evidence_unavailable')
    previous_games = {
        item.get('mlb_game_pk') for item in before.get('starts') or ()
        if isinstance(item, Mapping)
    }
    events = []
    for item in after.get('starts') or ():
        if not isinstance(item, Mapping) or item.get('mlb_game_pk') in previous_games:
            continue
        evidence = _mapping(item.get('short_start_evidence'))
        if item.get('status') != 'complete' or evidence.get('status') != 'complete':
            continue
        if item.get('short_start') is not True:
            continue
        starter = item.get('starter_name') or 'The starter'
        summary = (
            f"{starter} worked {item.get('starter_innings')} innings; "
            f"the bullpen covered {item.get('bullpen_innings')}."
        )
        events.append(_event(
            'rotation', 'new_short_start', current=current, previous=previous,
            team_id=team_id, subject_id=item.get('starter_pitcher_id'),
            event_date=item.get('game_date'), current_value=True, summary=summary,
            facts=deepcopy(dict(item)),
        ))
    status = 'partial' if 'partial' in {before.get('status'), after.get('status')} else 'complete'
    return events, _domain(status, 'rotation_comparison_partial' if status == 'partial' else None)


def build_frozen_what_changed(previous, current, team_id):
    """Compare only immutable carriers selected by the embedded exact-pair identity."""
    represented = _represented(current)
    identity = comparison_identity_from_payload(getattr(current, 'payload', None))
    base = {
        'contract': CONTRACT,
        'method_version': METHOD_VERSION,
        'team_id': int(team_id),
        'current_snapshot_id': getattr(current, 'id', None),
        'previous_snapshot_id': getattr(previous, 'id', None) if previous else None,
        'current_represented_date': represented,
        'previous_represented_date': _represented(previous) if previous else None,
        'comparison_identity': deepcopy(identity),
        'state': 'unavailable',
        'comparison_status': 'unavailable',
        'events': [],
        'quiet_message': None,
        'domains': {
            'team_state': _domain('unavailable', 'no_prior_trusted_comparison'),
            'roster': _domain('unavailable', 'no_prior_trusted_comparison'),
            'workload_rest': _domain('unavailable', 'no_prior_trusted_comparison'),
            'transactions': _domain('unavailable', 'no_prior_trusted_comparison'),
            'rotation': _domain('unavailable', 'no_prior_trusted_comparison'),
            'roles_deployment': _domain('not_comparable', 'role_movement_not_governed'),
            'performance': _domain('not_comparable', 'performance_materiality_not_governed'),
        },
        'reason_code': 'no_prior_trusted_comparison',
    }
    if previous is None or identity is None:
        return base
    try:
        validate_snapshot_pair(identity, previous, current)
    except ComparisonIdentityInvalid:
        return {**base, 'reason_code': 'comparison_identity_invalid'}

    previous_team = _team(previous, team_id)
    current_team = _team(current, team_id)
    if not previous_team or not current_team:
        return {**base, 'reason_code': 'team_package_missing'}

    state_result = compare_exact_team_state(previous, current, team_id, identity)
    events = []
    domains = dict(base['domains'])
    domains['team_state'] = _domain(
        'complete' if state_result['status'] in {'changed', 'unchanged'} else 'unavailable',
        state_result.get('reason_code'),
        outcome=(
            state_result['status']
            if state_result['status'] in {'changed', 'unchanged'} else None
        ),
    )
    if state_result.get('event'):
        state = state_result['event']
        events.append(_event(
            'team_state', 'team_state_changed', current=current, previous=previous,
            team_id=team_id, previous_value=state['previous_label'],
            current_value=state['current_label'],
            summary=(f"Team State changed from {state['previous_label']} "
                     f"to {state['current_label']}."),
        ))

    roster_events = _roster_events(previous, current, team_id, previous_team, current_team)
    domains['roster'] = _domain('complete')
    transaction_events, domains['transactions'] = _transaction_events(
        previous, current, team_id, previous_team, current_team,
    )
    workload_events, domains['workload_rest'] = _workload_events(
        previous, current, team_id, previous_team, current_team,
    )
    rotation_events, domains['rotation'] = _rotation_events(
        previous, current, team_id, previous_team, current_team,
    )
    roster_events, transaction_events = _link_roster_transactions(
        roster_events, transaction_events,
    )
    events.extend(roster_events)
    events.extend(workload_events)
    events.extend(transaction_events)
    events.extend(rotation_events)
    events.sort(key=lambda item: (
        DOMAIN_ORDER[item['domain']], item.get('event_date') or '',
        item.get('subject_id') or 0, item['event_type'],
    ))
    truncated = len(events) > MAX_EVENTS
    events = events[:MAX_EVENTS]
    partial = truncated or any(
        item['status'] != 'complete' for item in domains.values()
    )
    return {
        **base,
        'state': 'changes' if events else 'quiet',
        'comparison_status': 'partial' if partial else 'complete',
        'events': events,
        'quiet_message': None if events else QUIET_COPY,
        'domains': domains,
        'reason_code': 'event_limit_applied' if truncated else None,
    }


def attach_frozen_what_changed(snapshot, previous_snapshot):
    """Attach all team comparisons to the candidate package by value."""
    payload = deepcopy(dict(snapshot.payload))
    package = deepcopy(dict(_mapping(payload.get('trusted_team_boards'))))
    teams = deepcopy(dict(_mapping(package.get('by_team_id'))))
    for key, team in teams.items():
        team['frozen_what_changed'] = build_frozen_what_changed(
            previous_snapshot, snapshot, int(key),
        )
    package['by_team_id'] = teams
    payload['trusted_team_boards'] = package
    snapshot.payload = payload
