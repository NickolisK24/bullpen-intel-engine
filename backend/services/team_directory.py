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
