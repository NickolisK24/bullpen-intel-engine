"""Valid team-id directory (Phase D1D).

Team following needs to validate a team_id without inventing a teams table.
The valid set is exactly the teams the public GET /api/bullpen/teams surface is
built from: distinct active pitchers with a team. This keeps the follow API
honest against the same team universe the rest of the product shows.
"""

from models.pitcher import Pitcher
from utils.db import db


def valid_team_ids():
    """Return the set of team ids that currently have active pitchers."""
    rows = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.active == True)
        .filter(Pitcher.team_id.isnot(None))
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
