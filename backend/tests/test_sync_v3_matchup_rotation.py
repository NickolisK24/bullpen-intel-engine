from copy import deepcopy
from datetime import date, timedelta

import pytest

from services import rotation_support_pressure as rules
from sync_v3.matchup_rotation import matchup_rotation


@pytest.fixture
def week():
    through = date(2024, 8, 7)
    dates = {(through - timedelta(days=n)).isoformat(): dict(reason=None, games=[]) for n in range(7)}
    game = dict(game_pk=123, credited_starter=10, starter_outs=13, relief_outs=14, relief_pitchers=[11, 12],
                shape_reason=None, rotation=dict(kind=rules.KIND_ROTATION_START, short_start=True, starter_outs=13,
                                                bullpen_outs_required=14, total_known_outs=27))
    dates['2024-08-07']['games'].append(game)
    dates['2024-08-01']['games'].append(dict(game, game_pk=122))
    return dict(through=str(through), team=111, dates=dates)


def test_reference_window_excludes_older_start_and_preserves_fractional_pressure(week):
    read = matchup_rotation(week, date(2024, 8, 8), reference_day_unresolved=False)
    assert read['short_starts'] == 1 and read['bullpen_innings'] == 4.7 and read['limitations']


def test_uncertified_game_shape_fails_before_any_legacy_database_lookup(week, monkeypatch):
    def unexpected(*args):
        pytest.fail('Candidate attempted to resolve a shape from the legacy database')
    monkeypatch.setattr(rules, '_verified_shape_for_split', unexpected)
    game = week['dates']['2024-08-07']['games'][0]
    game.update(starter_outs=3, relief_outs=24)
    game['rotation'].update(starter_outs=3, bullpen_outs_required=24)
    assert matchup_rotation(week, date(2024, 8, 8), reference_day_unresolved=False) is None


def test_unreconciled_final_missing_day_and_duplicate_identity_withhold(week):
    day = date(2024, 8, 8)
    assert matchup_rotation(week, day, reference_day_unresolved=True) is None
    assert matchup_rotation(week, day + timedelta(days=1), reference_day_unresolved=False) is None
    missing = deepcopy(week)
    del missing['dates']['2024-08-02']
    assert matchup_rotation(missing, day, reference_day_unresolved=False) is None
    week['dates']['2024-08-06']['games'] = week['dates']['2024-08-07']['games']
    assert matchup_rotation(week, day, reference_day_unresolved=False) is None


def test_official_split_disagreement_withholds_rotation(week):
    week['dates']['2024-08-07']['games'][0]['rotation']['short_start'] = False
    assert matchup_rotation(week, date(2024, 8, 8), reference_day_unresolved=False) is None
