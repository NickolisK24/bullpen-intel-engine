"""Rotation pressure and official relief work on covered regular-season baseball dates."""

from collections import defaultdict
from datetime import timedelta

from services.rotation_support_pressure import _classify_team_game, build_team_rotation_support_pressure


def _recorded_total(lines, field):
    counts = [row[field] for row in lines]
    return sum(counts) if all(type(n) is int and n >= 0 for n in counts) else None


def club_rotation(calendar, team, through):
    dates = {}
    logs = []
    for offset in reversed(range(14)):
        day = through - timedelta(days=offset)
        observed, reason = calendar.get(day, (None, 'missing_complete_schedule'))
        daily = {'reason': reason, 'games': [], 'sources': observed['sources'] if observed else []}
        dates[day.isoformat()] = daily
        if observed is None:
            continue
        by_game = defaultdict(list)
        for line in observed['official_lines']:
            if line['team_id'] == team:
                by_game[line['game_pk']].append(dict(line, mlb_game_pk=line['game_pk'],
                                                     game_type='R', innings_pitched_outs=line['outs_recorded']))
        for pk, lines in sorted(by_game.items()):
            record, shape_reason = _classify_team_game(lines)
            starts = [r for r in lines if r['games_started'] == 1]
            relief = [r for r in lines if r['games_started'] == 0]
            starter = starts[0] if len(starts) == 1 else None
            daily['games'].append({
                'game_pk': pk, 'rotation': record, 'shape_reason': shape_reason,
                'credited_starter': starter['pitcher_mlb_id'] if starter else None,
                'starter_outs': starter['outs_recorded'] if starter else None,
                'starter_pitches': starter['pitches_thrown'] if starter else None,
                'starter_batters_faced': starter['batters_faced'] if starter else None,
                'relief_pitchers': [r['pitcher_mlb_id'] for r in relief],
                'relief_outs': _recorded_total(relief, 'outs_recorded'),
                'relief_pitches': _recorded_total(relief, 'pitches_thrown'),
                'relief_batters_faced': _recorded_total(relief, 'batters_faced'),
            })
            logs.extend(lines)

    windows = {}
    for days in (7, 14):
        start = (through - timedelta(days=days - 1)).isoformat()
        gaps = {day: daily['reason'] for day, daily in dates.items() if day >= start and daily['reason']}
        window = {'start': start, 'gaps': gaps, 'pressure': None}
        windows[str(days)] = window
        if gaps:
            continue
        pressure = build_team_rotation_support_pressure(logs, team={'team_id': team}, reference_date=through,
                                                        window_days=days)
        window['pressure'] = {key: pressure[key] for key in (
            'status', 'games_in_window', 'games_analyzed', 'games_excluded', 'excluded_game_reasons',
            'starter_outs', 'short_start_count', 'bullpen_outs_required', 'opener_bulk_games',
            'bulk_follower_outs', 'bullpen_games', 'bullpen_game_outs', 'game_shape_distribution',
        )}
    return {'team': team, 'through': through.isoformat(), 'dates': dates, 'windows': windows}
