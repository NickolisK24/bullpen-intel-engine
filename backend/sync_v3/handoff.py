"""Observed handedness and starter transition on a previously reconciled play sequence."""

from collections import Counter, defaultdict

from services.completed_game_context_payload_adapter import _normalize_play_by_play
from services.completed_game_context_service import _derive_from_plays


def _side(matchup, field):
    value = matchup.get(field)
    code = value.get('code') if isinstance(value, dict) else None
    return code if code in ('L', 'R') else '?'


def game_handoffs(game, lines, plays):
    normalized = _normalize_play_by_play({'allPlays': plays})
    output = {}
    for side, half in [('home', 'top'), ('away', 'bottom')]:
        team = game['teams'][side]['team']['id']
        staff = [r for r in lines if r['team_id'] == team]
        starter, = (r for r in staff if r['games_started'] == 1)
        pid = starter['pitcher_mlb_id']
        defending = [p for p in plays if p['about']['halfInning'] == half]
        splits = defaultdict(Counter)
        ids = []
        for play in defending:
            matchup = play['matchup']
            arm = matchup['pitcher']['id']
            ids.append(arm)
            splits[arm][_side(matchup, 'pitchHand') + '/' + _side(matchup, 'batSide')] += 1
        result = {'starter': pid, 'matchup_sides_by_pitcher': dict(splits), 'last_starter_pa': None,
                  'first_relief_pa': None, 'reason': None}
        output[team] = result
        last = max((i for i, arm in enumerate(ids) if arm == pid), default=-1)
        if last < 0 or any(arm != pid for arm in ids[:last]) or not normalized:
            result['reason'] = 'starter_sequence_unresolved'
            continue
        scores = _derive_from_plays(normalized, side == 'home', pid, set(ids))
        inning, runs_for, runs_against = scores['starter_exit']
        final_play = defending[last]
        outs = (final_play.get('count') or {}).get('outs')
        expected = starter['outs_recorded'] - 3 * (inning - 1)
        result['last_starter_pa'] = {
            'at_bat_index': final_play['about']['atBatIndex'], 'inning': inning,
            'runs_for': runs_for, 'runs_against': runs_against,
            'outs_after': outs if type(outs) is int and 0 <= outs <= 3 and outs == expected else None,
        }
        if scores['bullpen_entry'] is not None:
            inning, runs_for, runs_against = scores['bullpen_entry']
            first = defending[last + 1]
            result['first_relief_pa'] = {
                'pitcher': ids[last + 1], 'at_bat_index': first['about']['atBatIndex'],
                'inning': inning, 'runs_for_before': runs_for, 'runs_against_before': runs_against,
                'entry_bases': None, 'entry_bases_reason': 'base_state_unavailable',
            }
    return output
