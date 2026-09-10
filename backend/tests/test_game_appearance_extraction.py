"""Foundation 3C — canonical game -> appearance extraction."""

from datetime import date

import pytest

from services import game_appearance_extraction as extraction
from services.game_appearance_extraction import AppearanceExtractionError


GAME_DATE = date(2026, 7, 29)


def _game(game_pk=790001, home_id=147, away_id=111):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': GAME_DATE.isoformat(),
        'teams': {
            'home': {'team': {'id': home_id}},
            'away': {'team': {'id': away_id}},
        },
    }


def _line(player_id, side, *, innings='1.0', games_started=0, team_id=147, **stats):
    payload = {
        'inningsPitched': innings,
        'earnedRuns': 0,
        'runs': 0,
        'hits': 0,
        'baseOnBalls': 0,
        'strikeOuts': 1,
        'homeRuns': 0,
        'battersFaced': 3,
        'numberOfPitches': 12,
    }
    payload.update(stats)
    if games_started is not None:
        payload['gamesStarted'] = games_started
    return {
        'player_id': player_id,
        'person_id': player_id,
        'name': f'Pitcher {player_id}',
        'team_id': team_id,
        'side': side,
        'stats': payload,
    }


def _extract(lines, *, order=None, game=None):
    return extraction.extract_game_appearances(
        game=game or _game(),
        pitching_lines=lines,
        pitcher_order=order or {'home': [], 'away': []},
        game_date=GAME_DATE,
    )


def test_starter_is_identified_from_the_official_per_game_signal():
    records = _extract([
        _line(101, 'home', innings='6.0', games_started=1),
        _line(102, 'home', innings='1.1', games_started=0),
    ])

    by_id = {record['pitcher_mlb_id']: record for record in records}
    assert by_id[101]['appearance_role'] == extraction.APPEARANCE_ROLE_START
    assert by_id[101]['is_starter'] is True
    assert by_id[102]['appearance_role'] == extraction.APPEARANCE_ROLE_RELIEF
    assert by_id[102]['is_reliever'] is True


def test_relievers_are_identified_regardless_of_season_or_roster_role():
    # Nothing in this payload says anything about season role; role is decided
    # by the per-game signal alone.
    records = _extract([
        _line(201, 'away', innings='5.0', games_started=1, team_id=111),
        _line(202, 'away', innings='2.0', games_started=0, team_id=111),
        _line(203, 'away', innings='2.0', games_started=0, team_id=111),
    ])

    assert extraction.relief_appearance_count(records) == 2
    assert extraction.starter_identity(records)['away'] == 201


def test_opener_records_a_start_and_the_bulk_arm_records_relief():
    # An opener is officially credited with the start; the bulk arm behind them
    # is relief. The governed signal is followed, never overridden.
    records = _extract([
        _line(301, 'home', innings='1.0', games_started=1),
        _line(302, 'home', innings='5.0', games_started=0),
    ])

    by_id = {record['pitcher_mlb_id']: record for record in records}
    assert by_id[301]['is_starter'] is True
    assert by_id[301]['outs_recorded'] == 3
    assert by_id[302]['is_reliever'] is True
    assert by_id[302]['outs_recorded'] == 15


def test_missing_games_started_falls_back_to_the_first_listed_pitcher():
    records = _extract(
        [
            _line(401, 'home', innings='6.0', games_started=None),
            _line(402, 'home', innings='1.0', games_started=None),
        ],
        order={'home': [401, 402], 'away': []},
    )

    by_id = {record['pitcher_mlb_id']: record for record in records}
    assert by_id[401]['is_starter'] is True
    assert by_id[402]['is_reliever'] is True


def test_every_pitching_line_in_the_game_is_extracted():
    records = _extract([
        _line(501, 'home', games_started=1),
        _line(502, 'home'),
        _line(503, 'home'),
        _line(504, 'away', games_started=1, team_id=111),
        _line(505, 'away', team_id=111),
    ])

    assert len(records) == 5
    assert {record['pitcher_mlb_id'] for record in records} == {
        501, 502, 503, 504, 505,
    }


def test_zero_out_appearance_is_extracted_not_dropped():
    records = _extract([_line(601, 'home', innings='0.0')])

    assert len(records) == 1
    assert records[0]['outs_recorded'] == 0
    assert records[0]['innings_pitched'] == 0.0


def test_mlb_innings_notation_is_read_as_outs_not_tenths():
    records = _extract([_line(701, 'home', innings='2.1')])

    assert records[0]['outs_recorded'] == 7


def test_duplicate_pitching_line_for_one_pitcher_is_rejected():
    with pytest.raises(AppearanceExtractionError) as excinfo:
        _extract([_line(801, 'home'), _line(801, 'home', innings='2.0')])

    assert excinfo.value.error_class == 'payload_invalid'


def test_unidentifiable_pitcher_fails_closed():
    line = _line(0, 'home')
    line['player_id'] = None
    line['person_id'] = None

    with pytest.raises(AppearanceExtractionError) as excinfo:
        _extract([line])

    assert excinfo.value.error_class == 'starter_identity_unresolved'


def test_unparsable_innings_fails_closed():
    with pytest.raises(AppearanceExtractionError) as excinfo:
        _extract([_line(901, 'home', innings='not-an-inning')])

    assert excinfo.value.error_class == 'payload_invalid'


def test_missing_game_identifier_fails_closed():
    with pytest.raises(AppearanceExtractionError):
        extraction.extract_game_appearances(
            game={'teams': {}},
            pitching_lines=[_line(1001, 'home')],
            pitcher_order={},
            game_date=GAME_DATE,
        )


def test_extraction_order_is_deterministic_regardless_of_payload_order():
    lines = [
        _line(1103, 'home'),
        _line(1101, 'home', games_started=1),
        _line(1102, 'away', team_id=111),
    ]
    first = _extract(lines)
    second = _extract(list(reversed(lines)))

    assert [record['pitcher_mlb_id'] for record in first] == [
        record['pitcher_mlb_id'] for record in second
    ]


def test_lines_without_pitching_stats_are_not_appearances():
    line = _line(1201, 'home')
    line['stats'] = {}

    assert _extract([line, _line(1202, 'home')]) != []
    assert len(_extract([line, _line(1202, 'home')])) == 1


def test_opponent_and_team_come_from_the_game_side_not_the_pitcher():
    records = _extract([_line(1301, 'away', team_id=111)])

    assert records[0]['team_id'] == 111
    assert records[0]['opponent_team_id'] == 147


class TestSourceRevision:
    def test_identical_appearance_sets_fingerprint_identically(self):
        lines = [_line(1401, 'home', games_started=1), _line(1402, 'home')]

        assert (
            extraction.appearance_set_fingerprint(_extract(lines))
            == extraction.appearance_set_fingerprint(_extract(list(reversed(lines))))
        )

    def test_a_corrected_stat_line_changes_the_fingerprint(self):
        before = _extract([_line(1501, 'home', earnedRuns=1)])
        after = _extract([_line(1501, 'home', earnedRuns=2)])

        assert (
            extraction.appearance_set_fingerprint(before)
            != extraction.appearance_set_fingerprint(after)
        )

    def test_cosmetic_payload_change_does_not_look_like_a_correction(self):
        base = _line(1601, 'home')
        renamed = dict(base)
        renamed['name'] = 'Someone Else'

        assert (
            extraction.appearance_set_fingerprint(_extract([base]))
            == extraction.appearance_set_fingerprint(_extract([renamed]))
        )
