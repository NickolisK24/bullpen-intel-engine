import requests
from flask import current_app
from datetime import datetime, timedelta

class MLBApiClient:
    """
    Client for the MLB Stats API (statsapi.mlb.com).
    Free, no auth required. Documentation: https://statsapi.mlb.com/docs/
    """

    def __init__(self):
        self.base_url = "https://statsapi.mlb.com/api/v1"
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'BaseballOS/1.0 (Portfolio Analytics Tool)'
        })

    def _get(self, endpoint, params=None):
        """Make a GET request to the MLB API."""
        url = f"{self.base_url}{endpoint}"
        try:
            response = self.session.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"MLB API error [{endpoint}]: {e}")
            return None

    # ─── Teams ───────────────────────────────────────────────

    def get_all_teams(self, sport_id=1):
        """Get all MLB teams. sport_id=1 is MLB."""
        data = self._get('/teams', params={'sportId': sport_id})
        if not data:
            return []
        return data.get('teams', [])

    def get_team_roster(self, team_id, roster_type='pitchers'):
        """
        Get team roster.
        roster_type: 'allRoster', 'pitchers', 'active', '40Man'
        """
        data = self._get(f'/teams/{team_id}/roster', params={
            'rosterType': roster_type
        })
        if not data:
            return []
        return data.get('roster', [])

    # ─── Pitchers ────────────────────────────────────────────

    def get_pitcher_game_logs(self, player_id, season=None):
        """Get game-by-game pitching logs for a player."""
        if not season:
            season = datetime.now().year
        data = self._get(f'/people/{player_id}/stats', params={
            'stats': 'gameLog',
            'group': 'pitching',
            'season': season,
            'sportId': 1
        })
        if not data:
            return []
        stats = data.get('stats', [])
        if stats:
            return stats[0].get('splits', [])
        return []

    def get_player_info(self, player_id):
        """Get detailed player info."""
        data = self._get(f'/people/{player_id}')
        if not data:
            return None
        people = data.get('people', [])
        return people[0] if people else None

    def get_pitching_stats(self, player_id, season=None, stat_type='season'):
        """
        Get aggregate pitching stats.
        stat_type: 'season', 'career', 'lastXGames', 'yearByYear'
        """
        if not season:
            season = datetime.now().year
        data = self._get(f'/people/{player_id}/stats', params={
            'stats': stat_type,
            'group': 'pitching',
            'season': season
        })
        if not data:
            return None
        stats = data.get('stats', [])
        if stats and stats[0].get('splits'):
            return stats[0]['splits'][0].get('stat', {})
        return None

    # ─── Schedule & Games ────────────────────────────────────

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        """Get game schedule."""
        params = {'sportId': 1, 'hydrate': 'team'}
        if start_date:
            params['startDate'] = start_date
        if end_date:
            params['endDate'] = end_date
        if team_id:
            params['teamId'] = team_id

        data = self._get('/schedule', params=params)
        if not data:
            return []
        dates = data.get('dates', [])
        games = []
        for date in dates:
            games.extend(date.get('games', []))
        return games

    def get_recent_schedule(self, days_back=14):
        """Get games from the last N days."""
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')
        return self.get_schedule(start_date=start_date, end_date=end_date)

    def get_game_boxscore(self, game_pk):
        """Get full boxscore for a specific game."""
        data = self._get(f'/game/{game_pk}/boxscore')
        return data

    def get_game_pitching_lines(self, game_pk):
        """Extract pitcher lines from a game boxscore."""
        boxscore = self.get_game_boxscore(game_pk)
        if not boxscore:
            return []

        pitchers = []
        for side in ['home', 'away']:
            team_data = boxscore.get('teams', {}).get(side, {})
            team_info = team_data.get('team', {})
            pitchers_data = team_data.get('pitchers', [])
            player_data = team_data.get('players', {})

            for pitcher_id in pitchers_data:
                key = f'ID{pitcher_id}'
                player = player_data.get(key, {})
                stats = player.get('stats', {}).get('pitching', {})
                if stats:
                    pitchers.append({
                        'player_id': pitcher_id,
                        'name': player.get('person', {}).get('fullName'),
                        'team': team_info.get('name'),
                        'team_id': team_info.get('id'),
                        'stats': stats,
                        'side': side
                    })
        return pitchers

    # ─── Prospects / Minor Leagues ────────────────────────────

    def get_minor_league_teams(self):
        """Get minor league team list."""
        data = self._get('/teams', params={'sportIds': '11,12,13,14,16'})
        if not data:
            return []
        return data.get('teams', [])

    def get_prospect_stats(self, player_id, season=None):
        """Get stats for a prospect (works across levels)."""
        if not season:
            season = datetime.now().year
        data = self._get(f'/people/{player_id}/stats', params={
            'stats': 'yearByYear',
            'sportId': 1,
            'season': season
        })
        if not data:
            return []
        stats = data.get('stats', [])
        if stats:
            return stats[0].get('splits', [])
        return []

    def search_player(self, name):
        """Search for a player by name."""
        data = self._get('/people/search', params={
            'names': name,
            'sportIds': '1,11,12,13,14,16'
        })
        if not data:
            return []
        return data.get('people', [])


# Singleton instance
mlb_client = MLBApiClient()
