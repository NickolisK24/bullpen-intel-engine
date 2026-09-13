"""Valid team-id directory (Phase D1D).

Team following needs to validate a team_id without inventing a teams table.
The valid set is active MLB clubs represented by stored active pitchers.
Affiliate assignments can coexist in the pitcher table, but cannot expand the
MLB publication or following universe. Missing MLB clubs remain missing so the
publication completeness gate can reject an incomplete directory.
"""

from models.pitcher import Pitcher
from services.mlb_club_directory import MLB_TEAM_IDS
from utils.db import db


def valid_team_ids():
    """Return MLB club ids that currently have active pitchers."""
    rows = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
        .filter(Pitcher.team_id.in_(MLB_TEAM_IDS))
        .distinct()
        .all()
    )
    return {int(row[0]) for row in rows if row[0] is not None}


def is_valid_team_id(team_id):
    """True when ``team_id`` is a real, currently-active MLB team in the data."""
    try:
        candidate = int(team_id)
    except (TypeError, ValueError):
        return False
    return candidate in valid_team_ids()


def valid_team_directory():
    """Canonical teams as ``{team_id: {team_id, team_name, team_abbreviation}}``.

    Same active-pitcher universe as ``valid_team_ids`` — one team authority, not a
    second registry — enriched with the display name/abbreviation for operator
    surfaces. First non-null name/abbreviation seen for a team wins (a team's
    pitchers carry a consistent name), so the mapping is deterministic.
    """
    rows = (
        db.session.query(
            Pitcher.team_id, Pitcher.team_name, Pitcher.team_abbreviation
        )
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
        .filter(Pitcher.team_id.in_(MLB_TEAM_IDS))
        .order_by(Pitcher.team_id.asc(), Pitcher.id.asc())
        .all()
    )
    directory = {}
    for team_id, team_name, team_abbreviation in rows:
        if team_id is None:
            continue
        tid = int(team_id)
        entry = directory.get(tid)
        if entry is None:
            directory[tid] = {
                'team_id': tid,
                'team_name': team_name,
                'team_abbreviation': team_abbreviation,
            }
            continue
        if not entry['team_name'] and team_name:
            entry['team_name'] = team_name
        if not entry['team_abbreviation'] and team_abbreviation:
            entry['team_abbreviation'] = team_abbreviation
    return directory
