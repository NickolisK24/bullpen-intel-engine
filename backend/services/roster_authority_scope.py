"""Official endpoint scope, distinct from a player's affiliate assignment."""

from services.mlb_club_directory import MLB_TEAM_IDS

MLB_MEMBERSHIP_TYPES = ('active_roster', 'forty_man_roster')


def classify_roster_team(team_id, *, records=(), metadata=None):
    """Fail closed; a familiar rosterType never promotes an affiliate to MLB."""
    team_id = int(team_id)
    metadata = metadata or {}
    team = metadata.get(team_id) or {}
    parents = {
        int(row['parentTeamId']) for row in records
        if isinstance(row, dict) and str(row.get('parentTeamId', '')).isdigit()
    }
    parent = team.get('parent_org_id')
    if parent is not None:
        parents.add(int(parent))
    if team_id in MLB_TEAM_IDS:
        conflict = bool(parents - {team_id}) or team.get('sport_id') not in (None, 1)
        return {
            'requested_team_id': team_id, 'team_class': 'mlb_club',
            'mlb_parent_id': team_id, 'authority_conflict': conflict,
            'mlb_membership_authority': not conflict,
        }
    parent = next(iter(parents)) if len(parents) == 1 else None
    return {
        'requested_team_id': team_id,
        'team_class': 'affiliate' if parent in MLB_TEAM_IDS else 'unknown',
        'mlb_parent_id': parent if parent in MLB_TEAM_IDS else None,
        'authority_conflict': len(parents) > 1,
        'mlb_membership_authority': False,
    }


def roster_confirmation_routes(team_ids, *, metadata):
    """Return parent club confirmations and explicit unresolved source scopes."""
    clubs, unresolved = set(), set()
    for team_id in sorted(set(map(int, team_ids))):
        scope = classify_roster_team(team_id, metadata=metadata)
        parent = scope['mlb_parent_id']
        if parent is not None and not scope['authority_conflict']:
            clubs.add(parent)
        else:
            unresolved.add(team_id)
    return sorted(clubs), sorted(unresolved)
