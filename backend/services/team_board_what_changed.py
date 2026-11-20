"""Frozen TB-09 material changes over one exact trusted snapshot pair."""

from __future__ import annotations

from copy import deepcopy
from datetime import timedelta
from typing import Mapping

from services import role_movement
from services import public_team_relief_work as relief
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
    'roles_deployment': 3,
}
PATTERNS = (
    ('back_to_back', 'back-to-back usage'),
    ('three_in_four', '3-in-4 usage'),
    ('four_in_six', '4-in-6 usage'),
    ('recent_multi_inning', 'a recent multi-inning outing'),
    ('high_pitch_outing', 'a qualifying high-pitch outing'),
)


def _mapping(value):
    return value if isinstance(value, Mapping) else {}


def _team(snapshot, team_id):
    package = _mapping(_mapping(getattr(snapshot, 'payload', None)).get('trusted_team_boards'))
    team = _mapping(_mapping(package.get('by_team_id')).get(str(int(team_id))))
    if (package.get('contract') != 'trusted_team_board_publication_v1'
            or package.get('data_through') != _represented(snapshot)
            or _mapping(team.get('team')).get('team_id') != team_id):
        return {}
    return team


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


def _indexed(items):
    records = {}
    for item in items:
        pitcher_id = _mapping(item).get('pitcher_id')
        if type(pitcher_id) is not int or pitcher_id <= 0 or pitcher_id in records:
            return None
        records[pitcher_id] = item
    return records


def _usage_items(snapshot, team):
    from services.public_serving_authority import _frozen_recent_usage_rest_for_view

    carrier = _frozen_recent_usage_rest_for_view(snapshot, team)
    if (not carrier or carrier.get('status') not in {'complete', 'partial'}
            or carrier.get('population_basis') != relief.RECENT_USAGE_REST_POPULATION_BASIS
            or carrier.get('appearance_policy') != relief.RECENT_USAGE_REST_APPEARANCE_POLICY
            or carrier.get('window_policy') != relief.RECENT_USAGE_REST_REFERENCE_DATE_POLICY
            or carrier.get('thresholds') != {
                'multi_inning_minimum_outs': relief.RECENT_USAGE_REST_MULTI_INNING_MIN_OUTS,
                'high_pitch_outing_minimum_pitches': relief.RECENT_USAGE_REST_HIGH_PITCH_MIN_PITCHES,
                'three_in_four_minimum_distinct_days': relief.RECENT_USAGE_REST_THREE_IN_FOUR_MIN_DAYS,
                'four_in_six_minimum_distinct_days': relief.RECENT_USAGE_REST_FOUR_IN_SIX_MIN_DAYS,
            }):
        return None
    active = carrier.get('active_pitchers')
    historical = carrier.get('off_active_historical_contributors')
    if not isinstance(active, list) or not isinstance(historical, list):
        return None
    return _indexed(active + historical)


def _day_work(item, day):
    window = _mapping(_mapping(item.get('windows')).get('yesterday'))
    if (window.get('window_days') != 1 or window.get('through_date') != day
            or window.get('start_date') != day):
        return None
    counts = {}
    for key in ('appearances', 'pitches', 'outs'):
        fact = _mapping(window.get(key))
        if fact.get('status') != 'complete' or type(fact.get('value')) is not int or fact['value'] < 0:
            return None
        counts[key] = fact['value']
    return counts


def _workload_events(previous, current, team_id, previous_team, current_team):
    before = _usage_items(previous, previous_team)
    after = _usage_items(current, current_team)
    prior_reference = getattr(previous, 'availability_reference_date', None)
    reference = getattr(current, 'availability_reference_date', None)
    if (before is None or after is None or not prior_reference or not reference
            or reference - prior_reference != timedelta(days=1)):
        return [], _domain('unavailable', 'usage_rest_evidence_unavailable')
    events = []
    partial = before.keys() != after.keys()
    for pitcher_id in sorted(before.keys() & after.keys()):
        name = after[pitcher_id].get('pitcher_name')
        if not isinstance(name, str) or not name.strip():
            partial = True
            continue
        # Describe actual dated work. A rolling-window decline alone cannot
        # establish that a pitcher appeared or rested on the represented day.
        prior_work = _day_work(before[pitcher_id], _represented(previous))
        work = _day_work(after[pitcher_id], _represented(current))
        if work is None or prior_work is None:
            partial = True
        elif work['appearances']:
            events.append(_event(
                'workload_rest', 'relief_work_recorded', current=current, previous=previous,
                team_id=team_id, subject_id=pitcher_id, event_date=_represented(current),
                previous_value=prior_work, current_value=work,
                summary=(f"{name} recorded {work['appearances']} relief "
                         f"{'appearance' if work['appearances'] == 1 else 'appearances'} "
                         f"({work['pitches']} pitches, {work['outs']} outs)."),
                facts={'pitcher_name': name},
            ))
        for key, label in PATTERNS:
            current_fact = _mapping(after[pitcher_id].get(key))
            previous_fact = _mapping(before[pitcher_id].get(key))
            if any(f.get('status') != 'complete' or type(f.get('value')) is not bool
                   for f in (current_fact, previous_fact)):
                partial = True
                continue
            value = current_fact['value']
            if previous_fact['value'] == value:
                continue
            events.append(_event(
                'workload_rest', f"{key}_{'started' if value else 'ended'}",
                current=current, previous=previous, team_id=team_id, subject_id=pitcher_id,
                event_date=(reference - timedelta(days=1)).isoformat(), previous_value=not value, current_value=value,
                summary=(f'{name} now has {label}.' if value else
                         f'{name} no longer shows {label} in the usage window.'),
                facts={'pitcher_name': name, 'pattern': key, **dict(current_fact)},
            ))
    return events, _domain('partial' if partial else 'complete', 'usage_rest_comparison_partial' if partial else None)


def _movement_items(snapshot, team, team_id):
    from services.public_serving_authority import _frozen_roles_deployment_for_view

    carrier = _frozen_roles_deployment_for_view(snapshot, team, team_id)
    movement = _mapping(_mapping(carrier).get('role_movement'))
    if (movement.get('status') not in {'complete', 'partial'}
            or movement.get('contract') != role_movement.CONTRACT
            or movement.get('method_version') != role_movement.METHOD_VERSION
            or movement.get('data_through') != _represented(snapshot)
            or movement.get('population_basis') != relief.DEPLOYMENT_PROFILE_POPULATION_BASIS
            or movement.get('game_types') != sorted(role_movement.GAME_TYPES)
            or not isinstance(movement.get('profiles'), list)):
        return None
    return _indexed(movement['profiles'])


def _movement_read(item, anchor):
    if item.get('status') != 'complete':
        return None
    recent, prior = (_mapping(item.get(k)) for k in ('recent_window', 'prior_window'))
    bounds = role_movement.window_bounds(anchor)
    for window, start, end in ((recent, *bounds[:2]), (prior, *bounds[2:])):
        if (window.get('start_date') != start.isoformat() or window.get('through_date') != end.isoformat()
                or window.get('window_days') != role_movement.WINDOW_DAYS):
            return None
        for known, observed in (('known_entry_appearances', 'eighth_or_later_appearances'),
                                ('known_leverage_appearances', 'high_leverage_appearances')):
            counts = [window.get(k) for k in (observed, known, 'appearances')]
            if not all(type(n) is int for n in counts) or not 0 <= counts[0] <= counts[1] <= counts[2]:
                return None
    verified = role_movement.classify_observed_role_movement(recent=recent, prior=prior)
    if verified['status'] != 'complete' or any(item.get(k) != v for k, v in verified.items()):
        return None
    return verified


def _deployment_events(previous, current, team_id, previous_team, current_team):
    before = _movement_items(previous, previous_team, team_id)
    after = _movement_items(current, current_team, team_id)
    if not before or not after:
        return [], _domain('not_comparable', 'role_movement_evidence_unavailable')
    names = _record_names(current_team)
    events = []
    partial = before.keys() != after.keys()
    for pitcher_id in sorted(before.keys() & after.keys()):
        old = _movement_read(before[pitcher_id], previous.data_through)
        new = _movement_read(after[pitcher_id], current.data_through)
        name = names.get(pitcher_id)
        if (not old or not new or not isinstance(name, str) or not name.strip()
                or old['season_phase'] != new['season_phase']
                or [s['status'] for s in old['signals']] != [s['status'] for s in new['signals']]):
            partial = True
            continue
        if old['movement'] == new['movement']:
            continue
        label = new['public_label'] or 'Recent deployment returned to a stable pattern.'
        events.append(_event(
            'roles_deployment', 'observed_deployment_changed', current=current, previous=previous,
            team_id=team_id, subject_id=pitcher_id, event_date=_represented(current),
            previous_value=old['movement'], current_value=new['movement'],
            summary=f'{name}: {label}', facts={'pitcher_name': name, 'method_version': new['method_version'],
                'prior_window': after[pitcher_id]['prior_window'], 'recent_window': after[pitcher_id]['recent_window']},
        ))
    return events, _domain('partial' if partial else 'complete', 'role_movement_comparison_partial' if partial else None)


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


def _compare(previous, current, team_id):
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
            'roles_deployment': _domain('not_comparable', 'no_prior_trusted_comparison'),
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
    deployment, domains['roles_deployment'] = _deployment_events(previous, current, team_id, previous_team, current_team)
    events.extend(deployment)
    events.sort(key=lambda item: (
        item['event_type'] == 'relief_work_recorded', DOMAIN_ORDER[item['domain']], item.get('event_date') or '',
        item.get('subject_id') or 0, item['event_type'],
    ))
    partial = any(
        item['status'] != 'complete' for item in domains.values()
    )
    return {
        **base,
        'state': 'changes' if events else 'quiet',
        'comparison_status': 'partial' if partial else 'complete',
        'events': events,
        'quiet_message': None if events else QUIET_COPY,
        'domains': domains,
        'reason_code': None,
    }


def _board_summary(comparison):
    if len(comparison['events']) <= MAX_EVENTS:
        return comparison
    return {**comparison, 'events': comparison['events'][:MAX_EVENTS],
            'comparison_status': 'partial', 'reason_code': 'event_limit_applied'}


def build_frozen_what_changed(previous, current, team_id):
    return _board_summary(_compare(previous, current, team_id))


ARM_HISTORY_CONTRACT = 'published_named_arm_changes_v1'
ARM_DOMAINS = ('workload_rest', 'roles_deployment')


def attach_frozen_what_changed(snapshot, previous_snapshot):
    """Attach all team comparisons to the candidate package by value.

    Only the payload, package, team map and team entries need new containers
    for the Board summary and named-arm History receipt. Every
    other domain is shared with the candidate's current payload, which is
    replaced below and never mutated. Deep-copying the whole multi-megabyte
    payload (and the package and team map again) held three full copies at
    once inside the publication transaction, the largest single contributor to
    the Daily Primary memory peak. The resulting value is unchanged.
    """
    payload = dict(snapshot.payload)
    package = dict(_mapping(payload.get('trusted_team_boards')))
    teams = {
        key: dict(team) if isinstance(team, Mapping) else deepcopy(team)
        for key, team in _mapping(package.get('by_team_id')).items()
    }
    for key, team in teams.items():
        comparison = _compare(previous_snapshot, snapshot, int(key))
        team['frozen_what_changed'] = _board_summary(comparison)
        if comparison['state'] != 'unavailable':
            team['frozen_arm_changes'] = {
                'contract': ARM_HISTORY_CONTRACT, 'team_id': int(key),
                'comparison_identity': comparison['comparison_identity'],
                'domains': {k: comparison['domains'][k] for k in ARM_DOMAINS},
                'events': [e for e in comparison['events'] if e['domain'] in ARM_DOMAINS],
            }
    package['by_team_id'] = teams
    payload['trusted_team_boards'] = package
    snapshot.payload = payload
