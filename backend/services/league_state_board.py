"""Public league Team State board read model.

The product league board needs one row per club.  The existing landscape is a
small orientation sample, so it cannot be expanded into a 30-club state board
without inventing state in the browser.  This adapter only joins three
backend-owned facts: team identity, the governed public Team State block, and
already-classified current availability counts.
"""

from collections import Counter


GROUP_ORDER = ('fresh', 'stretched', 'vulnerable', 'withheld')
AVAILABILITY_ORDER = ('Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable')


def _availability_counts(records):
    counts = {}
    for record in records or []:
        pitcher = record.get('pitcher') if isinstance(record, dict) else None
        team_id = getattr(pitcher, 'team_id', None)
        if team_id is None:
            continue
        status = (record.get('availability') or {}).get('availability_status')
        if status not in AVAILABILITY_ORDER:
            continue
        counts.setdefault(int(team_id), Counter())[status] += 1
    return counts


def _group_key(team_state):
    if not isinstance(team_state, dict) or team_state.get('available') is not True:
        return 'withheld'
    state = str(team_state.get('public_state') or '').strip().lower()
    return state if state in GROUP_ORDER[:-1] else 'withheld'


def build_league_state_board(*, teams, records, team_state_for_team, freshness=None):
    """Build a deterministic, non-ranking league board.

    ``team_state_for_team`` is injected so the service remains easy to test and
    so the API can use the single canonical Team State authority.  Unavailable,
    malformed, or unsupported state blocks are grouped as publication-level
    ``withheld`` reads, never as a fourth Team State.
    """
    availability_by_team = _availability_counts(records)
    groups = {key: [] for key in GROUP_ORDER}

    ordered_teams = sorted(
        teams or [],
        key=lambda team: (
            str((team or {}).get('team_abbreviation') or ''),
            str((team or {}).get('team_name') or ''),
            int((team or {}).get('team_id') or 0),
        ),
    )
    seen = set()
    for team in ordered_teams:
        team_id = team.get('team_id') if isinstance(team, dict) else None
        if team_id is None or int(team_id) in seen:
            continue
        team_id = int(team_id)
        seen.add(team_id)
        team_state = team_state_for_team(team_id)
        key = _group_key(team_state)
        counts = availability_by_team.get(team_id, Counter())
        groups[key].append({
            'team_id': team_id,
            'team_name': team.get('team_name'),
            'team_abbreviation': team.get('team_abbreviation'),
            'team_state': team_state,
            'arm_read_counts': {
                status: int(counts.get(status, 0))
                for status in AVAILABILITY_ORDER
            },
            'active_read_count': int(sum(counts.values())),
            'clean_option_count': int(counts.get('Available', 0)),
        })

    return {
        'capability': 'league_team_state_board_v1',
        'contract': 'league_team_state_board_v1',
        'ranking_applied': False,
        'selection_made': False,
        'group_order': list(GROUP_ORDER),
        'teams_expected': len(seen),
        'teams_in_current_state': sum(len(groups[key]) for key in GROUP_ORDER[:-1]),
        'teams_withheld': len(groups['withheld']),
        'groups': [
            {
                'key': key,
                'label': key.upper(),
                'count': len(groups[key]),
                'teams': groups[key],
            }
            for key in GROUP_ORDER
        ],
        'freshness': freshness or {},
    }
