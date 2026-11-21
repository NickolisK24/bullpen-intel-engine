from copy import deepcopy
from datetime import date, timedelta

import pytest

from services import rotation_support_pressure as rules
from sync_v3.matchup_rotation import matchup_rotation
from tests.test_rotation_support_split_window import app as legacy_split_app


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


def test_pinned_nonrotation_games_match_persisted_legacy_splits(week, legacy_split_app):
    from tests import test_rotation_support_split_window as legacy
    from models.team_game_pitching_split import TeamGamePitchingSplit as Split

    day = legacy.REF
    fixture_day = date.fromisoformat(week['through'])
    week['through'] = str(day - timedelta(days=1))
    week['team'] = legacy.TEAM_A
    week['dates'] = {str(day - timedelta(days=1) + (date.fromisoformat(key) - fixture_day)): value
                     for key, value in week['dates'].items()}
    pin = {}
    with legacy_split_app.app_context():
        p1 = legacy._pitcher('Starter', 10, legacy.TEAM_A)
        p2 = legacy._pitcher('Bulk follower', 11, legacy.TEAM_A)
        legacy._scheduled_game(123, 1)
        legacy._split(123, 1, starter_pitcher=p1, starter_outs=13, bullpen_outs=14)
        for pk, ago, starter_outs, relief_outs in [(124, 2, 3, 24), (125, 3, None, 27)]:
            represented = legacy._scheduled_game(pk, ago)
            starter_status = Split.STARTER_KNOWN if starter_outs is not None else Split.STARTER_UNKNOWN
            legacy._split(pk, ago, starter_pitcher=p1 if starter_outs is not None else None,
                          starter_status=starter_status, starter_outs=starter_outs, bullpen_outs=relief_outs, total_outs=27)
            pitchers = [(p1, 1, starter_outs), (p2, 0, relief_outs)] if starter_outs is not None else [(p2, 0, relief_outs)]
            lines = []
            for pitcher, started, outs in pitchers:
                legacy._game_log(pitcher, pk, ago, outs=outs, games_started=started)
                lines.append(dict(game_pk=pk, game_date=str(represented), team_id=week['team'],
                                  pitcher_mlb_id=pitcher.mlb_id, games_started=started, outs_recorded=outs))
            record, reason = rules._classify_team_game([dict(line, innings_pitched_outs=line['outs_recorded']) for line in lines])
            week['dates'][str(represented)]['games'].append(dict(
                game_pk=pk, credited_starter=10 if starter_outs is not None else None, starter_outs=starter_outs,
                relief_outs=relief_outs, relief_pitchers=[11], shape_reason=reason, rotation=record))
            pin[pk] = lines
        legacy.db.session.commit()
        expected = legacy._payload()
    assert expected['games_analyzed'] == expected['opener_bulk_games'] == expected['bullpen_games'] == 1
    value = matchup_rotation(week, day, reference_day_unresolved=False, pinned_lines=pin)
    assert value == dict(window_days=7, short_starts=expected['short_start_count'],
                         bullpen_innings=expected['bullpen_innings_required'], limitations=expected['limitations'])
    for corrupt in ({}, {**pin, 124: pin[125]}, {**pin, 125: pin[125] * 2}):
        assert matchup_rotation(week, day, reference_day_unresolved=False, pinned_lines=corrupt) is None
