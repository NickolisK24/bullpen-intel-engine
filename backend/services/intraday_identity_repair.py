"""Governed creation and organization repair for intraday roster findings."""

from __future__ import annotations

from models.pitcher import Pitcher
from services.mlb_api import mlb_client
from services.roster_status import STATUS_UNKNOWN
from services.team_assignment_sync import TEAM_ASSIGNMENT_ASSIGNED
from utils.db import db
from utils.time import utc_now_naive

PITCHER_CODES = frozenset({'1', 'Y'})
PITCHER_ABBRS = frozenset({'P', 'TWP'})
SOURCE = 'mlb_stats_api:intraday_identity_repair'
NEWLY_DISCOVERED_ACTIVE = 'newly_discovered_active'


class IntradayIdentityRepairError(RuntimeError):
    pass


def apply_intraday_identity_findings(findings, *, client=None, timestamp=None):
    """Apply only identity findings re-proven from MLB numeric-id authority.

    New players require a pitcher/two-way role and use the audited active-roster
    observation as their current-team bootstrap authority. The MLB people
    endpoint is still used to prove numeric identity and role, but its
    ``currentTeam`` field may lag the active roster during same-day moves.
    Existing team changes continue to require a matching ``currentTeam``.
    Names are display evidence only and are never used for matching.
    """
    client = client or mlb_client
    timestamp = timestamp or utc_now_naive()
    teams = _team_map(client)
    created = 0
    reassigned = 0
    unchanged = 0
    applied = []

    for finding in findings or []:
        mlb_id = _positive_int(finding.get('mlb_player_id'))
        team_id = _positive_int(finding.get('observed_official_team_id'))
        if mlb_id is None or team_id is None:
            raise IntradayIdentityRepairError('Identity finding lacks MLB player or team authority.')

        info = client.get_player_info(mlb_id) or {}
        if _positive_int(info.get('id')) not in (None, mlb_id):
            raise IntradayIdentityRepairError(f'MLB identity mismatch for player {mlb_id}.')

        pitcher = Pitcher.query.filter_by(mlb_id=mlb_id).one_or_none()
        is_newly_discovered = (
            pitcher is None
            and finding.get('change_type') == NEWLY_DISCOVERED_ACTIVE
        )
        current_team = info.get('currentTeam') or {}
        if not is_newly_discovered and _positive_int(current_team.get('id')) != team_id:
            raise IntradayIdentityRepairError(
                f'Current-team authority changed for player {mlb_id}; expected {team_id}.'
            )

        if pitcher is None:
            if not _is_pitcher_or_two_way(info):
                raise IntradayIdentityRepairError(
                    f'Player {mlb_id} is not proven as a pitcher or two-way player.'
                )
            if team_id not in teams:
                raise IntradayIdentityRepairError(
                    f'Audited team authority {team_id} is not an active MLB team.'
                )
            name = str(info.get('fullName') or finding.get('source_player_name') or '').strip()
            if not name:
                raise IntradayIdentityRepairError(f'Player {mlb_id} has no authoritative display name.')
            pitcher = Pitcher(
                mlb_id=mlb_id,
                full_name=name[:100],
                position=_position_abbreviation(info) or 'P',
                active=True,
                roster_status=STATUS_UNKNOWN,
                roster_status_source=SOURCE,
                roster_status_updated_at=timestamp,
            )
            db.session.add(pitcher)
            created += 1
            action = 'created'
        else:
            action = 'unchanged'

        team = teams.get(team_id) or current_team
        before = (
            pitcher.team_id,
            pitcher.team_name,
            pitcher.team_abbreviation,
            pitcher.active,
            pitcher.team_assignment_status,
        )
        pitcher.team_id = team_id
        pitcher.team_name = team.get('name') or pitcher.team_name
        pitcher.team_abbreviation = team.get('abbreviation') or pitcher.team_abbreviation
        pitcher.active = True
        pitcher.team_assignment_status = TEAM_ASSIGNMENT_ASSIGNED
        pitcher.team_assignment_source = SOURCE
        pitcher.team_assignment_updated_at = timestamp
        after = (
            pitcher.team_id,
            pitcher.team_name,
            pitcher.team_abbreviation,
            pitcher.active,
            pitcher.team_assignment_status,
        )
        if action != 'created' and before != after:
            reassigned += 1
            action = 'reassigned'
        elif action != 'created':
            unchanged += 1
        applied.append({'mlb_id': mlb_id, 'team_id': team_id, 'action': action})

    db.session.flush()
    return {
        'source': SOURCE,
        'created': created,
        'reassigned': reassigned,
        'unchanged': unchanged,
        'applied': applied,
    }


def _team_map(client):
    return {
        team.get('id'): team
        for team in (client.get_all_teams() or [])
        if _positive_int(team.get('id')) is not None
    }


def _is_pitcher_or_two_way(info):
    position = (info or {}).get('primaryPosition') or {}
    return (
        str(position.get('code') or '').upper() in PITCHER_CODES
        or str(position.get('abbreviation') or '').upper() in PITCHER_ABBRS
    )


def _position_abbreviation(info):
    position = (info or {}).get('primaryPosition') or {}
    value = position.get('abbreviation') or position.get('code')
    return str(value)[:10] if value else None


def _positive_int(value):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None
