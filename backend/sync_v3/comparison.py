"""Compare canonical official lines to the retained boxscore by game, side and player."""

from sync_v3.evidence import replay
from utils.innings import parse_mlb_innings_to_outs


SOURCE_FIELDS = {
    'earned_runs':'earnedRuns', 'runs_allowed':'runs', 'hits_allowed':'hits',
    'walks':'baseOnBalls', 'strikeouts':'strikeOuts', 'home_runs_allowed':'homeRuns',
    'batters_faced':'battersFaced', 'pitches_thrown':'numberOfPitches',
}


def compare_finals(cur):
    cur.execute("""SELECT DISTINCT ON (identity) identity,source_id,facts FROM candidate.revisions
                   WHERE domain='final' ORDER BY identity,revision DESC""")
    versions = cur.fetchall()
    appearances = 0
    for game, source_id, facts in versions:
        capture = replay(cur, source_id)
        if capture.request.endpoint != f'/game/{game}/boxscore':
            raise ValueError('Final facts cite a different game')
        records = {(item['side'], item['pitcher_mlb_id']):item for item in facts}
        for side, team in capture.body['teams'].items():
            for player in team['pitchers']:
                record = records.pop((side, player))
                stats = team['players'][f'ID{player}']['stats']['pitching']
                if record['team_id'] != team['team']['id'] or record['game_pk'] != int(game):
                    raise ValueError(f'Identity mismatch for game {game}, pitcher {player}')
                expected = {field:stats.get(src) for field, src in SOURCE_FIELDS.items()}
                expected['outs_recorded'] = parse_mlb_innings_to_outs(stats['inningsPitched'])
                for field, value in expected.items():
                    if record[field] != value:
                        raise ValueError(f'Official {field} mismatch for game {game}, pitcher {player}')
                appearances += 1
        if records:
            raise ValueError(f'Unexpected appearances for {game}')
    return len(versions), appearances
