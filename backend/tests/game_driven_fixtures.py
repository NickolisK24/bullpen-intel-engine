"""Shared Foundation 3C fixtures: real box scores driving the real writer.

These helpers deliberately produce official-shaped box-score payloads rather
than hand-built reconciliation results. Both shadow and write then run the
canonical path — one MLB client, one box-score parser, one reconciliation
planner, one writer — so a test cannot accidentally prove parity against a
stand-in that does not exist in production.
"""

from datetime import date, datetime

from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from utils.db import db


REFERENCE = date(2026, 7, 29)
HOME_TEAM = 147
AWAY_TEAM = 111
HOME_NAME = 'Home Club'
AWAY_NAME = 'Away Club'


def schedule_final_game(game_pk, *, game_date=REFERENCE, start_hour=19):
    for team_id, opponent_id, side in (
        (HOME_TEAM, AWAY_TEAM, 'home'),
        (AWAY_TEAM, HOME_TEAM, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id,
            game_pk=game_pk,
            game_date=game_date,
            game_datetime=datetime(
                game_date.year, game_date.month, game_date.day, start_hour, 5,
            ),
            opponent_team_id=opponent_id,
            home_away=side,
            game_type='R',
            status_code='F',
            status_state=ScheduledGame.STATE_FINAL,
        ))


def pitcher(mlb_id, *, team_id=HOME_TEAM, active=True, position='P',
            roster_status='ACTIVE', full_name=None):
    row = Pitcher(
        mlb_id=mlb_id,
        full_name=full_name or f'Arm {mlb_id}',
        team_id=team_id,
        team_abbreviation='HOM' if team_id == HOME_TEAM else 'AWY',
        position=position,
        active=active,
        roster_status=roster_status,
    )
    db.session.add(row)
    return row


def pitching_stats(
    *,
    innings='1.0',
    games_started=0,
    earned_runs=0,
    runs=None,
    hits=1,
    walks=0,
    strikeouts=2,
    home_runs=0,
    strikes=10,
    pitches=15,
    batters_faced=4,
    complete=True,
):
    """One official pitching line.

    ``complete=False`` drops a required correction key, which is what makes an
    existing row's correction unsafe — the governed blocked path.
    """
    stats = {
        'inningsPitched': innings,
        'gamesStarted': games_started,
        'earnedRuns': earned_runs,
        'runs': earned_runs if runs is None else runs,
        'hits': hits,
        'baseOnBalls': walks,
        'strikeOuts': strikeouts,
        'homeRuns': home_runs,
        'strikes': strikes,
        'numberOfPitches': pitches,
        'battersFaced': batters_faced,
    }
    if not complete:
        stats.pop('strikes')
    return stats


def boxscore(lines, *, home_team_id=HOME_TEAM, away_team_id=AWAY_TEAM):
    """Build an official box score from ``[(mlb_id, side, stats), ...]``."""
    sides = {
        'home': {'id': home_team_id, 'name': HOME_NAME, 'abbreviation': 'HOM'},
        'away': {'id': away_team_id, 'name': AWAY_NAME, 'abbreviation': 'AWY'},
    }
    payload = {
        'teams': {
            side: {'team': team, 'pitchers': [], 'players': {}}
            for side, team in sides.items()
        },
    }
    for mlb_id, side, stats in lines:
        payload['teams'][side]['pitchers'].append(mlb_id)
        payload['teams'][side]['players'][f'ID{mlb_id}'] = {
            'person': {'id': mlb_id, 'fullName': f'Arm {mlb_id}'},
            'position': {'abbreviation': 'P', 'code': '1', 'name': 'Pitcher'},
            'stats': {'pitching': stats},
        }
    return payload


def final_game(game_pk, *, game_date=REFERENCE,
               home_team_id=HOME_TEAM, away_team_id=AWAY_TEAM):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': game_date.isoformat(),
        'status': {
            'statusCode': 'F',
            'detailedState': 'Final',
            'abstractGameState': 'Final',
        },
        'teams': {
            'home': {'team': {'id': home_team_id, 'name': HOME_NAME}},
            'away': {'team': {'id': away_team_id, 'name': AWAY_NAME}},
        },
    }


class BoxscoreClient:
    """Stands in for the MLB client only — never for reconciliation."""

    def __init__(self, boxscores_by_game, *, fail_games=()):
        self.boxscores_by_game = dict(boxscores_by_game)
        self.fail_games = set(fail_games)
        self.calls = []

    def get_game_boxscore(self, game_pk):
        self.calls.append(game_pk)
        if game_pk in self.fail_games:
            raise TimeoutError('boxscore fetch failed')
        return self.boxscores_by_game.get(game_pk, {'teams': {}})

    def get_pitcher_game_logs(self, mlb_id, season=None):
        return []
