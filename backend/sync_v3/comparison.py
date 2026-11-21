"""Compare canonical official lines to the retained boxscore by game, side and player."""

from collections import Counter
from datetime import timedelta

from psycopg2.extras import Json

from services.game_finality import classify_status
from sync_v3.discovery import calendar_requests
from sync_v3.evidence import replay
from sync_v3.workload import WINDOWS
from sync_v3.pitching_credit import uncredited_pitching_line
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
                stats = team['players'][f'ID{player}']['stats']['pitching']
                if uncredited_pitching_line(stats):
                    continue
                record = records.pop((side, player))
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


def _scheduled_club_games(cur, team, day):
    cur.execute("""SELECT f.id, f.outcome, b.reason FROM candidate.fetches f
                   LEFT JOIN candidate.refusals b ON b.source_id = f.id
                   WHERE f.endpoint = '/schedule' AND f.parameters = %s
                   ORDER BY f.received_at DESC, f.id DESC LIMIT 1""",
                (Json(calendar_requests(day)[0].params()),))
    row = cur.fetchone()
    if row is None or row[1] != 'received' or row[2] is not None:
        raise ValueError(f'Club {team} claims coverage without an accepted schedule on {day}')
    expected = set()
    for entry in replay(cur, row[0]).body['dates']:
        for game in entry['games']:
            if game['gameType'] != 'R' or all(game['teams'][s]['team']['id'] != team for s in ('home', 'away')):
                continue
            status = classify_status(game['status'])
            if status.state in ('cancelled', 'postponed'):
                continue
            if not status.final_status or game['officialDate'] != day.isoformat():
                raise ValueError(f'Club {team} claims a covered day with an unresolved game on {day}')
            expected.add(game['gamePk'])
    return expected


def compare_team_workload(cur, calendar, candidate):
    """Recount each complete club window from retained boxscore player lists."""
    team = candidate['mlb_team_id']
    by_day = {}
    for day, (observed, _) in calendar.items():
        if observed is None:
            continue
        lines = []
        games = set()
        for source in observed['sources']:
            receipt = replay(cur, source)
            if not receipt.request.endpoint.endswith('/boxscore'):
                continue
            for side in receipt.body['teams'].values():
                if side['team']['id'] != team:
                    continue
                game_pk = int(receipt.request.endpoint.split('/')[2])
                if game_pk in games:
                    raise ValueError(f'Duplicate official game {game_pk} for club {team} on {day}')
                games.add(game_pk)
                for index, player in enumerate(side['pitchers']):
                    stats = side['players'][f'ID{player}']['stats']['pitching']
                    if uncredited_pitching_line(stats):
                        continue
                    starts = stats.get('gamesStarted')
                    credited_start = index == 0 if starts in (None, '') else int(starts) == 1
                    if credited_start:
                        continue
                    innings = stats['inningsPitched']
                    if innings is None or not str(innings).strip():
                        raise ValueError('Missing official relief innings in workload comparison')
                    lines.append((player, stats.get('numberOfPitches'), parse_mlb_innings_to_outs(innings),
                                  stats.get('battersFaced')))
        if games != _scheduled_club_games(cur, team, day):
            raise ValueError(f'Official slate and cited boxscores differ for club {team} on {day}')
        by_day[day] = lines

    compared = []
    windows = candidate['facts']['windows']
    if set(windows) != {f'window_{size}' for size in WINDOWS}:
        raise ValueError(f'Incomplete workload window contract for club {team}')
    last = max(calendar)
    for size in WINDOWS:
        key = f'window_{size}'
        window = windows[key]
        first = last - timedelta(days=size - 1)
        if window['start'] != first.isoformat() or window['through'] != last.isoformat():
            raise ValueError(f'Incorrect workload boundaries for club {team} {key}')
        days = [day for day in by_day if first <= day <= last]
        fields = ('appearances', 'pitches', 'outs', 'batters_faced')
        values = [window[field]['value'] for field in fields]
        if len(days) != (last - first).days + 1:
            if any(value is not None for value in values):
                raise ValueError(f'Club {team} {key} claims a total across a coverage gap')
            continue
        lines = [line for day in days for line in by_day[day]]
        pitch_counts = [pitches for _, pitches, _, _ in lines]
        batter_counts = [batters for _, _, _, batters in lines]
        pitches = None if None in pitch_counts else sum(pitch_counts)
        batters = None if None in batter_counts else sum(batter_counts)
        if values != [len(lines), pitches, sum(outs for _, _, outs, _ in lines), batters]:
            raise ValueError(f'Official club workload differs for {team} {key}')
        compared.append(key)
        if key == 'window_7' and pitches is not None:
            totals = Counter()
            for player, count, _, _ in lines:
                totals[player] += count
            expected = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
            concentration = candidate['facts']['concentration_7_day']
            actual = [(item['pitcher_id'], item['pitches']) for item in concentration['contributors']]
            share = sum(count for _, count in expected[:3]) / pitches if pitches else None
            if actual != expected or concentration['top_3_share'] != share:
                raise ValueError(f'Official seven-day workload concentration differs for {team}')
    return compared


def compare_readiness(candidate):
    """Independently reproduce represented arm decisions and the status-only team partition."""
    from services.production_accuracy_reconciliation import _reproduce_arm_status
    from services.publication_truth_certification import contract_a_state

    counts = Counter()
    for player, arm in candidate['arms'].items():
        if arm['read'] is None:
            counts['unknown'] += 1
            continue
        availability = arm['read']['availability']
        status = _reproduce_arm_status(availability['inputs'])
        if availability['data_state'] != 'fresh' or status != availability['availability_status']:
            raise ValueError(f'Unverified represented arm status for {player}')
        counts[status] += 1
    partition = {'active_pitcher_count': len(candidate['arms']), 'clean_count': counts['Available'],
                 'moderate_count': counts['Monitor'] + counts['Limited'],
                 'severe_count': counts['Avoid'] + counts['Unavailable'], 'unknown_count': counts['unknown']}
    if candidate.get('partition') is not None and partition != candidate['partition']:
        raise ValueError('Represented bullpen partition disagrees with arm decisions')
    if candidate['team_state'] is not None:
        code, rule = contract_a_state(partition['clean_count'], partition['severe_count'], partition['active_pitcher_count'])
        if not rule or (code, rule['decisive_rule']) != (candidate['team_state']['public_code'], candidate['rule']):
            raise ValueError('Represented Team State disagrees with independently reproduced rule')
    return {'arm_statuses_compared': len(candidate['arms']) - counts['unknown'],
            'withheld_arms': counts['unknown'], 'team_states_compared': int(candidate['team_state'] is not None)}
