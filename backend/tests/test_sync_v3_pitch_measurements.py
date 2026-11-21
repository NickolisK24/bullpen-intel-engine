
import pytest

from sync_v3.pitch_measurements import MEASUREMENTS, monthly_pitch_sample, outing_sample


def pitch(code, speed, **measurements):
    return {**dict.fromkeys(MEASUREMENTS), 'pitch_type_code': code, 'start_speed': speed, **measurements}


@pytest.mark.parametrize(('pitches', 'total', 'reason'), [
    ([pitch('FF', 95)], 2, 'pitch_count_unverified'),
    ([pitch('FF', 95)], None, 'pitch_count_unverified'),
    ([pitch(None, 95)], 1, 'pitch_type_sample_unavailable'),
    ([], 0, 'pitch_type_sample_unavailable'),
])
def test_incomplete_outing_withholds_month(pitches, total, reason):
    held = outing_sample(pitches, total)
    assert held['reason'] == reason
    good = outing_sample([pitch('FF', 95)], 1)
    assert monthly_pitch_sample([good, held]) == {'outings': 2, 'verified_outings': 1, 'types': []}


def test_complete_counts_and_separate_measurement_denominators():
    first = outing_sample([pitch('FF', 97.14, extension=7),
                           pitch('SL', None, release_position_x=-1)], 2)
    second = outing_sample([pitch('FF', 95.24, extension=6),
                            pitch('FF', 95.24, extension=6)], 2)
    result = monthly_pitch_sample([first, second])
    ff, sl = result['types']
    assert result['verified_outings'] == 2
    assert (ff['type'], ff['pitches'], ff['mix_percent'], ff['mean_mph']) == ('FF', 3, 75, 95.9)
    assert ff['measurements']['extension'] == {'measured': 3, 'mean': pytest.approx(19 / 3)}
    assert (sl['pitches'], sl['mix_percent'], sl['measured_speeds'], sl['mean_mph']) == (1, 25, 0, None)
    assert sl['measurements']['release_position_x'] == {'measured': 1, 'mean': -1}


def test_invalid_values_only_withhold_the_affected_measurement():
    first = outing_sample([pitch('FF', 95, spin_rate=2000), pitch('FF', float('nan'), spin_rate=-1)], 2)
    ff, = monthly_pitch_sample([first])['types']
    assert ff['pitches'] == 2 and ff['mix_percent'] == 100
    assert ff['mean_mph'] is None and ff['measured_speeds'] == 1
    assert ff['measurements']['spin_rate'] == {'mean': None, 'measured': 1}


def test_chart_uses_only_qualified_months_and_preserves_unknown_velocity():
    from datetime import date
    from services.pitcher_trends import monthly_pitch_characteristics

    outing = outing_sample([pitch('CH', None), pitch('FF', 93)], 2)
    complete = dict(month='2026-09', **monthly_pitch_sample([outing]))
    partial = dict(month='2026-07', **monthly_pitch_sample([outing, outing_sample([], 1)]))
    result = monthly_pitch_characteristics(date(2026, 10, 28), [partial, complete])
    july, september = result['months']
    assert july == dict(month='2026-07', outings=2, verified_outings=1, types=[])
    assert september['types'] == [
        dict(type='CH', pitches=1, mean_mph=None, mix_percent=50.0),
        dict(type='FF', pitches=1, mean_mph=93.0, mix_percent=50.0),
    ]


def test_erceg_game_feed_chart_against_savant_and_preservation_of_frozen_facts():
    import csv
    from copy import deepcopy
    from datetime import date
    from pathlib import Path

    from sync_v3.pitch_measurements import game_pitch_samples, pitch_history_for_display

    with (Path(__file__).parent / 'fixtures/sync_v3/erceg_746272.csv').open() as source:
        rows = list(csv.DictReader(source))
    plays = {}
    for row in rows:
        index = int(row['at_bat_index'])
        play = plays.setdefault(index, dict(
            about=dict(atBatIndex=index, inning=int(row['inning']), halfInning='top', isComplete=True),
            matchup=dict(pitcher=dict(id=668674), batter=dict(id=int(row['batter']))), playEvents=[]))
        coords = {axis + '0': float(row[axis + '0']) for axis in 'xyz'}
        assert all(round(coords[axis + '0'], 2) != float(row['release_pos_' + axis]) for axis in 'xyz')
        assert row['type'] == row['savant_type'] and float(row['start_speed']) == float(row['release_speed'])
        play['playEvents'].append(dict(
            isPitch=True, index=int(row['index']), pitchNumber=int(row['pitch_number']),
            details=dict(type=dict(code=row['type'])),
            pitchData=dict(startSpeed=float(row['start_speed']), extension=float(row['extension']), coordinates=coords)))
    game = dict(gamePk=746272, gameType='R', teams=dict(home=dict(team=dict(id=118)), away=dict(team=dict(id=111))))
    line = dict(team_id=118, pitcher_mlb_id=668674, games_started=0, pitches_thrown=22)
    samples, reason = game_pitch_samples(game, date(2024, 8, 7), [line], list(plays.values()))
    assert reason is None
    month = monthly_pitch_sample([samples[118, 668674]])
    history = {'months': [dict(month='2024-08', **month)]}
    original = deepcopy(history)
    types = pitch_history_for_display(history)['months'][0]['types']
    assert [(t['type'], t['pitches'], t['mean_mph'], t['mix_percent']) for t in types] == [
        ('CH', 8, 91.2, 36.4), ('FF', 7, 98.8, 31.8), ('SI', 3, 99.2, 13.6), ('SL', 4, 86.2, 18.2)]
    for item in types:
        group = [row for row in rows if row['type'] == item['type']]
        for field in ('x0', 'y0', 'z0', 'extension'):
            name = field if field == 'extension' else 'trajectory_' + field
            assert item['measurements'][name] == {
                'measured': len(group), 'mean': pytest.approx(sum(float(row[field]) for row in group) / len(group))}
        assert not any(key.startswith('release_position') for key in item['measurements'])
    assert history == original
