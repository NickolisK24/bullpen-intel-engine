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
                'game_pk': pk, 'series': observed.get('series', {}).get(pk), 'rotation': record, 'shape_reason': shape_reason,
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
    return {'team': team, 'through': through.isoformat(), 'dates': dates, 'windows': windows,
            'series_burden': _series_burden(dates)}


def _series_burden(dates):
    complete, pending, seen = [], [], set()
    for day, daily in sorted(dates.items()):
        games = daily['games']
        seen.update(g['game_pk'] for g in games)
        if daily['reason']:
            pending = []
            continue
        if len(games) > 1:
            order = [(g['series'] or {}).get('game_number') for g in games]
            if any(type(n) is not int or n <= 0 for n in order) or len(set(order)) != len(order):
                pending = []
                continue
            games = sorted(games, key=lambda g: g['series']['game_number'])
        for game in games:
            meta = game['series'] or {}
            number, length = meta.get('number'), meta.get('length')
            if type(number) is not int or type(length) is not int or not 1 <= number <= length:
                pending = []
                continue
            key = meta['home'], meta['away'], length
            if number == 1:
                pending = []
            elif not pending or pending[0][0] != key or len(pending) + 1 != number:
                pending = []
                continue
            pending.append((key, day, game))
            if number == length:
                series_games = [item[2] for item in pending]
                complete.append({'home': key[0], 'away': key[1], 'start': pending[0][1], 'end': day,
                                 'games': [g['game_pk'] for g in series_games],
                                 **{f: _recorded_total(series_games, f) for f in (
                                     'starter_outs', 'relief_outs', 'relief_pitches', 'relief_batters_faced')}})
                pending = []
    qualified = {pk for series in complete for pk in series['games']}
    return {'complete_series': complete, 'games_without_complete_series': sorted(seen - qualified)}
