from collections import defaultdict

from models.pitcher import Pitcher
from services.availability_reference_date import product_current_date
from services.bullpen_population import eligible_bullpen_pitcher_contexts
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_DFA,
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_LABELS,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_OPTIONED,
    STATUS_UNKNOWN,
    classify_roster_status,
)


CAPABILITY = 'injury_il_context_v1'

STATUS_GROUP_INJURED_LIST = 'injured_list'
STATUS_GROUP_INACTIVE_ROSTER = 'inactive_roster'
STATUS_GROUP_ACTIVE = 'active'
STATUS_GROUP_UNKNOWN = 'unknown'

INJURED_LIST_STATUSES = {
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
}

INACTIVE_ROSTER_STATUSES = {
    STATUS_MINORS,
    STATUS_OPTIONED,
    STATUS_DFA,
    STATUS_NON_ROSTER,
    STATUS_40_MAN_ONLY,
}

EXPLANATORY_LIMITATION = (
    'Roster status context is explanatory and does not change workload availability classifications.'
)
UNKNOWN_STATUS_LIMITATION = (
    'Unknown or missing roster status does not count as unavailable.'
)


def status_group_for_roster_status(roster_status):
    status = (roster_status or {}).get('status') or STATUS_UNKNOWN
    if status in INJURED_LIST_STATUSES:
        return STATUS_GROUP_INJURED_LIST
    if status in INACTIVE_ROSTER_STATUSES:
        return STATUS_GROUP_INACTIVE_ROSTER
    if status == STATUS_ACTIVE:
        return STATUS_GROUP_ACTIVE
    return STATUS_GROUP_UNKNOWN


def _pitcher_attr(pitcher, attr, default=None):
    return getattr(pitcher, attr, default)


def _team_key_for(pitcher):
    team_id = _pitcher_attr(pitcher, 'team_id')
    if team_id is not None:
        return str(team_id)
    team_name = _pitcher_attr(pitcher, 'team_name')
    if team_name:
        return f'name:{team_name}'
    return 'unknown'


def _matches_followed_team(pitcher, followed_team_id):
    if followed_team_id in (None, ''):
        return False
    team_id = _pitcher_attr(pitcher, 'team_id')
    if team_id is None:
        return False
    return str(team_id) == str(followed_team_id)


def _pitcher_entry(context, roster_status, status_group):
    pitcher = context.get('pitcher')
    status = roster_status.get('status') or STATUS_UNKNOWN
    return {
        'player_id': _pitcher_attr(pitcher, 'mlb_id') or _pitcher_attr(pitcher, 'id'),
        'name': _pitcher_attr(pitcher, 'full_name'),
        'status': status,
        'status_label': roster_status.get('label') or STATUS_LABELS.get(status, STATUS_LABELS[STATUS_UNKNOWN]),
        'status_group': status_group,
    }


def _empty_team_counts():
    return {
        STATUS_GROUP_INJURED_LIST: 0,
        STATUS_GROUP_INACTIVE_ROSTER: 0,
        STATUS_GROUP_ACTIVE: 0,
        STATUS_GROUP_UNKNOWN: 0,
        'unavailable_pitchers': [],
        'team_id': None,
        'team_name': None,
    }


def build_injury_il_context_from_contexts(contexts, followed_team_id=None):
    """
    Build roster-status context from the already filtered bullpen population.

    The counts explain known roster unavailability around bullpen depth. They do
    not alter workload-based availability, team rankings, or story selection.
    """
    contexts = list(contexts or [])
    league_counts = {
        STATUS_GROUP_INJURED_LIST: 0,
        STATUS_GROUP_INACTIVE_ROSTER: 0,
        STATUS_GROUP_ACTIVE: 0,
        STATUS_GROUP_UNKNOWN: 0,
    }
    team_counts = defaultdict(_empty_team_counts)

    sorted_contexts = sorted(
        contexts,
        key=lambda context: (
            str(_pitcher_attr(context.get('pitcher'), 'team_id', '')),
            str(_pitcher_attr(context.get('pitcher'), 'full_name', '')),
        ),
    )

    for context in sorted_contexts:
        pitcher = context.get('pitcher')
        roster_status = context.get('roster_status') or classify_roster_status(pitcher)
        status_group = status_group_for_roster_status(roster_status)
        league_counts[status_group] += 1

        team_key = _team_key_for(pitcher)
        team = team_counts[team_key]
        team[status_group] += 1
        if team['team_id'] is None:
            team['team_id'] = _pitcher_attr(pitcher, 'team_id')
        if team['team_name'] is None:
            team['team_name'] = _pitcher_attr(pitcher, 'team_name')

        if status_group in {STATUS_GROUP_INJURED_LIST, STATUS_GROUP_INACTIVE_ROSTER}:
            team['unavailable_pitchers'].append(
                _pitcher_entry(context, roster_status, status_group)
            )

    teams_with_multiple_unavailable = sum(
        1
        for team in team_counts.values()
        if team[STATUS_GROUP_INJURED_LIST] + team[STATUS_GROUP_INACTIVE_ROSTER] >= 2
    )

    followed_team = None
    if followed_team_id not in (None, ''):
        for context in sorted_contexts:
            pitcher = context.get('pitcher')
            if not _matches_followed_team(pitcher, followed_team_id):
                continue
            team = team_counts[_team_key_for(pitcher)]
            followed_team = {
                'team_id': team['team_id'],
                'team_name': team['team_name'],
                'injured_list_count': team[STATUS_GROUP_INJURED_LIST],
                'inactive_count': team[STATUS_GROUP_INACTIVE_ROSTER],
                'unavailable_pitchers': team['unavailable_pitchers'],
            }
            break

    return {
        'capability': CAPABILITY,
        'ranking_applied': False,
        'prediction_applied': False,
        'selection_made': False,
        'league': {
            'injured_list_count': league_counts[STATUS_GROUP_INJURED_LIST],
            'inactive_count': league_counts[STATUS_GROUP_INACTIVE_ROSTER],
            'teams_with_multiple_unavailable': teams_with_multiple_unavailable,
            'tracked_pitchers_count': len(sorted_contexts),
        },
        'followed_team': followed_team,
        'limitations': [
            EXPLANATORY_LIMITATION,
            UNKNOWN_STATUS_LIMITATION,
        ],
    }


def build_injury_il_context_payload(
    pitchers=None,
    followed_team_id=None,
    reference_date=None,
    logs_by_pitcher=None,
):
    ref = reference_date or product_current_date()
    pitcher_list = (
        list(pitchers)
        if pitchers is not None
        else (
            Pitcher.query
            .filter(Pitcher.active == True, Pitcher.team_id.isnot(None))
            .order_by(Pitcher.team_id, Pitcher.full_name)
            .all()
        )
    )
    contexts, _ = eligible_bullpen_pitcher_contexts(
        pitcher_list,
        include_stale=True,
        include_inactive_context=True,
        reference_date=ref,
        logs_by_pitcher=logs_by_pitcher,
    )
    return build_injury_il_context_from_contexts(
        contexts,
        followed_team_id=followed_team_id,
    )
