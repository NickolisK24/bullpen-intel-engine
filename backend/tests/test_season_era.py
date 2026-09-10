from types import SimpleNamespace

from services.season_era import era_components, era_from_components, era_line


def _log(outs, earned_runs, *, games_started=0):
    return SimpleNamespace(
        innings_pitched_outs=outs,
        earned_runs=earned_runs,
        games_started=games_started,
    )


def test_pitcher_season_era_uses_outs_denominator():
    line = era_line([
        _log(1, 1, games_started=0),
        _log(2, 0, games_started=1),
    ])

    assert line['innings_outs'] == 3
    assert line['earned_runs'] == 1
    assert line['innings'] == 1.0
    assert line['era'] == 9.0
    assert era_from_components(1, 1) == 27.0
    assert era_from_components(1, 0) is None


def test_bullpen_season_era_is_relief_only_and_weighted_by_innings():
    logs = [
        _log(9, 0, games_started=0),   # Pitcher A: 3.0 IP, 0 ERA
        _log(3, 3, games_started=0),   # Pitcher B: 1.0 IP, 27 ERA
        _log(18, 6, games_started=1),  # A start by the same current bullpen
    ]

    relief_components = era_components(logs, relief_only=True)
    relief_line = era_line(logs, relief_only=True)

    assert relief_components['appearances'] == 2
    assert relief_components['earned_runs'] == 3
    assert relief_components['innings_outs'] == 12
    assert relief_line['era'] == 6.75


def test_unknown_start_split_is_excluded_from_relief_only_bullpen_era():
    line = era_line([
        _log(3, 1, games_started=None),
        _log(3, 0, games_started=0),
    ], relief_only=True)

    assert line['appearances'] == 1
    assert line['earned_runs'] == 0
    assert line['innings_outs'] == 3
    assert line['era'] == 0.0
