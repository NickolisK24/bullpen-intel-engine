"""Publication-only TB-08 projection over existing public roster/event authority."""

from copy import deepcopy

from services.public_recent_transactions import CAPABILITY as TRANSACTION_CAPABILITY


CONTRACT = 'team_board_roster_transactions_v1'
STATUS_COMPLETE = 'complete'
STATUS_PARTIAL = 'partial'
STATUS_UNKNOWN = 'unknown'
STATUS_UNAVAILABLE = 'unavailable'


def _current_status(pitcher_id, *, active_ids, roster_by_id):
    if pitcher_id in active_ids:
        return {'status': STATUS_COMPLETE, 'membership': 'active', 'label': 'Active bullpen'}
    roster = roster_by_id.get(pitcher_id)
    if not isinstance(roster, dict):
        return {'status': STATUS_UNAVAILABLE, 'membership': None, 'label': 'Current roster status unavailable'}
    classification = roster.get('roster_status') or {}
    if classification.get('is_active_mlb') is True:
        return {'status': STATUS_COMPLETE, 'membership': 'active_roster', 'label': 'Active roster'}
    if classification.get('is_inactive_context') is True or classification.get('is_active_mlb') is False:
        return {
            'status': STATUS_COMPLETE,
            'membership': 'off_active',
            'label': classification.get('label') or 'Off the active roster',
        }
    return {'status': STATUS_UNKNOWN, 'membership': None, 'label': 'Roster status pending'}


def author_frozen_roster_transactions(
    team_id, *, data_through, transaction_read, records,
    active_pitcher_ids, workload_overview, team_board_package_contract,
):
    """Freeze historical events beside, never in place of, current roster truth.

    Transaction direction describes the dated event. Present membership comes
    only from the already-selected Team Board active group and roster record.
    """
    if not isinstance(transaction_read, dict) or (
        transaction_read.get('capability') != TRANSACTION_CAPABILITY
    ):
        raise ValueError('qualified public transaction read is required')
    if transaction_read.get('status') not in {'available', STATUS_PARTIAL, STATUS_UNAVAILABLE}:
        raise ValueError('qualified public transaction status is required')
    if transaction_read['status'] == STATUS_UNAVAILABLE and transaction_read.get('events'):
        raise ValueError('unavailable transaction evidence cannot publish events')
    active_ids = set(active_pitcher_ids or ())
    roster_by_id = {
        record['pitcher_id']: record
        for record in records or ()
        if isinstance(record, dict) and type(record.get('pitcher_id')) is int
    }
    events = []
    for source in transaction_read.get('events') or ():
        event = deepcopy(source)
        event['current_roster'] = _current_status(
            event.get('player_id'), active_ids=active_ids,
            roster_by_id=roster_by_id,
        )
        events.append(event)

    concentration = (
        workload_overview.get('concentration_7_day')
        if isinstance(workload_overview, dict) else None
    )
    concentration = concentration if isinstance(concentration, dict) else {}
    evidence_status = concentration.get('status') or STATUS_UNAVAILABLE
    off_active = []
    if evidence_status == STATUS_COMPLETE:
        off_active = [
            {
                'pitcher_id': contributor['pitcher_id'],
                'name': contributor['name'],
                'current_roster': _current_status(
                    contributor['pitcher_id'], active_ids=active_ids,
                    roster_by_id=roster_by_id,
                ),
            }
            for contributor in concentration.get('contributors') or ()
            if isinstance(contributor, dict)
            and contributor.get('current_active') is False
            and type(contributor.get('pitcher_id')) is int
        ]

    return {
        'contract': CONTRACT,
        'team_board_package_contract': team_board_package_contract,
        'team_id': team_id,
        'data_through': data_through,
        'population_basis': transaction_read.get('population_basis'),
        'status': transaction_read.get('status'),
        'window_start_date': transaction_read.get('window_start_date'),
        'window_end_date': transaction_read.get('window_end_date'),
        'source_represented_date': transaction_read.get('represented_date'),
        'limitations': deepcopy(transaction_read.get('limitations') or []),
        'events': events,
        'current_group': {
            'population_basis': 'trusted_team_boards.default_pitcher_ids',
            'active_count': len(active_ids),
            'active_pitcher_ids': sorted(active_ids),
        },
        'off_active_recent_contributors': {
            'status': evidence_status,
            'window_days': 7,
            'contributors': off_active,
        },
    }
