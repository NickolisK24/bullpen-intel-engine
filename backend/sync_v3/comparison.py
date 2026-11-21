"""Compare canonical official lines to the retained boxscore by game, side and player."""

from collections import Counter
from datetime import date

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


def compare_team_workload(cur, calendar, candidate):
    """Recount each complete club window from retained boxscore player lists."""
    team = candidate['mlb_team_id']
    by_day = {}
    for day, (observed, _) in calendar.items():
        if observed is None:
            continue
        lines = []
        for source in observed['sources']:
            receipt = replay(cur, source)
            if not receipt.request.endpoint.endswith('/boxscore'):
                continue
            for side in receipt.body['teams'].values():
                if side['team']['id'] != team:
                    continue
                for index, player in enumerate(side['pitchers']):
                    stats = side['players'][f'ID{player}']['stats']['pitching']
                    starts = stats.get('gamesStarted')
                    credited_start = index == 0 if starts in (None, '') else int(starts) == 1
                    if credited_start:
                        continue
                    innings = stats['inningsPitched']
                    if innings is None or not str(innings).strip():
                        raise ValueError('Missing official relief innings in workload comparison')
                    lines.append((player, stats.get('numberOfPitches'), parse_mlb_innings_to_outs(innings)))
        by_day[day] = lines

    compared = []
    for key, window in candidate['facts']['windows'].items():
        first, last = date.fromisoformat(window['start']), date.fromisoformat(window['through'])
        days = [day for day in by_day if first <= day <= last]
        fields = ('appearances', 'pitches', 'outs')
        values = [window[field]['value'] for field in fields]
        if len(days) != (last - first).days + 1:
            if any(value is not None for value in values):
                raise ValueError(f'Club {team} {key} claims a total across a coverage gap')
            continue
        lines = [line for day in days for line in by_day[day]]
        pitches = None if any(count is None for _, count, _ in lines) else sum(count for _, count, _ in lines)
        if values != [len(lines), pitches, sum(outs for _, _, outs in lines)]:
            raise ValueError(f'Official club workload differs for {team} {key}')
        compared.append(key)
        if key == 'window_7' and pitches is not None:
            totals = Counter()
            for player, count, _ in lines:
                totals[player] += count
            expected = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
            concentration = candidate['facts']['concentration_7_day']
            actual = [(item['pitcher_id'], item['pitches']) for item in concentration['contributors']]
            share = sum(count for _, count in expected[:3]) / pitches if pitches else None
            if actual != expected or concentration['top_3_share'] != share:
                raise ValueError(f'Official seven-day workload concentration differs for {team}')
    return compared
