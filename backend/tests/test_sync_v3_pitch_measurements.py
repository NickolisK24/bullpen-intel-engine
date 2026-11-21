
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
