"""Regular-season schedule evidence for in-season publication fixtures.

Production's rolling schedule window (``schedule_authority``) always stores the
next days' games during the season. Club competition status (WP-0.1) reads a
stored regular-season game on or after the reference date as positive evidence
that the regular season continues, so a fixture that models an in-season
publication with only completed games needs one such game.

The game is between two non-MLB ids, so it never lands on a tested club's
slate, roster, or schedule.
"""

from datetime import timedelta

LEAGUE_AHEAD_GAME_PK = 8990001
LEAGUE_AHEAD_TEAM_IDS = (990001, 990002)


def add_league_regular_season_game_ahead(anchor_date, *, days_ahead=10):
    """Store one scheduled regular-season game ``days_ahead`` after ``anchor_date``."""
    from models.scheduled_game import ScheduledGame
    from utils.db import db

    exists = (
        db.session.query(ScheduledGame.id)
        .filter(ScheduledGame.game_pk == LEAGUE_AHEAD_GAME_PK)
        .first()
    )
    if exists is not None:
        return
    home, away = LEAGUE_AHEAD_TEAM_IDS
    game_date = anchor_date + timedelta(days=days_ahead)
    db.session.add_all([
        ScheduledGame(
            game_type='R', team_id=team_id, game_pk=LEAGUE_AHEAD_GAME_PK,
            game_date=game_date, status_state='scheduled', home_away=side,
            opponent_team_id=opponent,
        )
        for team_id, opponent, side in ((home, away, 'home'), (away, home, 'away'))
    ])
    db.session.flush()
