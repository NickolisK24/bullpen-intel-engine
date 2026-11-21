"""Outing pitch samples from reconciled official game and tracking evidence."""

from collections import defaultdict
from decimal import Decimal
from math import isfinite
from statistics import fmean

from services.pitcher_trends import pitch_type_summary
from services.play_by_play_foundation import _normalize_pitch_events


MEASUREMENTS = ('spin_rate', 'extension', 'release_position_x', 'release_position_y',
                'release_position_z', 'break_horizontal', 'break_vertical_induced')


def outing_sample(pitches, official_total):
    result = {'official_pitches': official_total, 'tracked_pitches': len(pitches),
              'reason': None, 'types': []}
    if type(official_total) is not int or len(pitches) != official_total:
        result['reason'] = 'pitch_count_unverified'
        return result
    if not pitches or any(not pitch['pitch_type_code'] for pitch in pitches):
        result['reason'] = 'pitch_type_sample_unavailable'
        return result
    by_type = defaultdict(list)
    for pitch in pitches:
        by_type[pitch['pitch_type_code']].append(pitch)
    for code, group in sorted(by_type.items()):
        speeds = [p['start_speed'] for p in group]
        known = [v for v in speeds if v is not None and isfinite(v) and v > 0]
        speed_sum = sum((Decimal(str(v)) for v in known), Decimal(0))
        item = pitch_type_summary(code, len(group), len(pitches), len(known), speed_sum)
        item.update(measured_speeds=len(known), speed_sum_mph=str(speed_sum), measurements={})
        result['types'].append(item)
        for field in MEASUREMENTS:
            known = [p[field] for p in group if p[field] is not None and isfinite(p[field])]
            if field in ('spin_rate', 'extension'):
                known = [v for v in known if v > 0]
            item['measurements'][field] = {'measured': len(known),
                                           'mean': fmean(known) if len(known) == len(group) else None}
    return result


def game_pitch_samples(game, day, lines, plays):
    """Called after date, final, game-side identities and full plays are validated."""
    ids = {line['pitcher_mlb_id']: line['pitcher_mlb_id'] for line in lines}
    try:
        normalized = _normalize_pitch_events(
            plays, game_pk=game['gamePk'], game_date=day, game_type=game['gameType'],
            home_team_id=game['teams']['home']['team']['id'], away_team_id=game['teams']['away']['team']['id'],
            sync_run_id=None, local_pitcher_ids=ids,
        )
    except (AttributeError, TypeError, ValueError):
        return {}, 'malformed_pitch_tracking'
    if normalized['status'] != 'ok':
        return {}, normalized['reason']
    if normalized['unresolved_pitcher_count']:
        return {}, 'unresolved_pitcher_identity'
    by_arm = defaultdict(list)
    for pitch in normalized['pitches']:
        by_arm[pitch['fielding_team_id'], pitch['pitcher_mlb_id']].append(pitch)
    return {(row['team_id'], row['pitcher_mlb_id']): outing_sample(
                by_arm[row['team_id'], row['pitcher_mlb_id']], row['pitches_thrown'])
            for row in lines if row['games_started'] == 0}, None


def monthly_pitch_sample(outings):
    """Combine complete outing counts and unrounded measurements before display rounding."""
    verified = [sample for sample in outings if sample.get('reason') is None]
    result = {'outings': len(outings), 'verified_outings': len(verified), 'types': []}
    if len(verified) != len(outings):
        return result
    by_type = defaultdict(list)
    for outing in outings:
        for item in outing['types']:
            by_type[item['type']].append(item)
    total = sum(s['official_pitches'] for s in outings)
    for code, items in sorted(by_type.items()):
        count = sum(i['pitches'] for i in items)
        measured = sum(i['measured_speeds'] for i in items)
        speed_sum = sum((Decimal(i['speed_sum_mph']) for i in items), Decimal(0))
        row = pitch_type_summary(code, count, total, measured, speed_sum)
        row.update(measured_speeds=measured, measurements={})
        for field in MEASUREMENTS:
            samples = [i['measurements'][field] for i in items]
            known = sum(s['measured'] for s in samples)
            row['measurements'][field] = {'measured': known, 'mean': (
                sum(s['mean'] * s['measured'] for s in samples) / count if known == count else None)}
        result['types'].append(row)
    return result
