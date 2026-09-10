"""Tests for the Completed Game Context payload adapter (COIN Phase 3).

The adapter converts raw MLB schedule/boxscore/linescore/play-by-play responses
into the normalized payload the extraction service consumes. It is pure and
fail-closed, so these tests feed raw-MLB-shaped dictionaries and assert the
normalized output (and the conservative degradation when data is ambiguous).
"""

from datetime import date

from services.completed_game_context_payload_adapter import (
    build_completed_game_payload,
)
from services.completed_game_context_service import (
    CONFIDENCE_HIGH,
    extract_completed_game_contexts,
)


def _schedule_game(game_pk=7001, home_score=None, away_score=None):
    home = {'team': {'id': 1, 'name': 'Home Club'}}
    away = {'team': {'id': 2, 'name': 'Away Club'}}
    if home_score is not None:
        home['score'] = home_score
    if away_score is not None:
        away['score'] = away_score
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': '2026-06-20',
        'teams': {'home': home, 'away': away},
    }


def _pitcher(full_name, games_started, innings, pitches):
    stats = {'inningsPitched': innings, 'numberOfPitches': pitches}
    if games_started is not None:
        stats['gamesStarted'] = games_started
    return {'person': {'fullName': full_name}, 'stats': {'pitching': stats}}


def _boxscore():
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club'},
                'pitchers': [11, 12],
                'players': {
                    'ID11': _pitcher('Home Starter', 1, '6.0', '92'),
                    'ID12': _pitcher('Home Reliever', 0, '3.0', '20'),
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club'},
                'pitchers': [21, 22],
                'players': {
                    'ID21': _pitcher('Away Starter', 1, '4.0', '70'),
                    'ID22': _pitcher('Away Reliever', 0, '6.0', '55'),
                },
            },
        },
    }


def _raw_linescore(home_total=3, away_total=1):
    return {
        'innings': [
            {'num': 1, 'home': {'runs': 1}, 'away': {'runs': 0}},
            {'num': 2, 'home': {'runs': 2}, 'away': {'runs': 0}},
            {'num': 7, 'home': {'runs': 0}, 'away': {'runs': 1}},
        ],
        'teams': {'home': {'runs': home_total}, 'away': {'runs': away_total}},
    }


def _raw_play_by_play(plays):
    return {
        'allPlays': [
            {
                'about': {'inning': inning, 'halfInning': half, 'isComplete': True},
                'result': {'awayScore': away, 'homeScore': home},
                'matchup': {'pitcher': {'id': pid}},
            }
            for (inning, half, away, home, pid) in plays
        ]
    }


# ── Boxscore normalization ────────────────────────────────────────────────────

def test_boxscore_only_payload_has_no_linescore_or_plays():
    payload = build_completed_game_payload(
        _schedule_game(), boxscore=_boxscore(), game_date=date(2026, 6, 20)
    )
    assert payload['game_pk'] == 7001
    assert payload['game_date'] == date(2026, 6, 20)
    assert payload['home']['team_id'] == 1
    assert payload['away']['team_name'] == 'Away Club'
    assert 'linescore' not in payload
    assert 'plays' not in payload

    home_pitchers = payload['home']['pitchers']
    assert [p['player_id'] for p in home_pitchers] == [11, 12]
    assert home_pitchers[0] == {
        'player_id': 11,
        'name': 'Home Starter',
        'games_started': 1,
        'innings_pitched_outs': 18,
        'pitches_thrown': 92,
    }


def test_games_started_falls_back_to_first_pitcher_when_missing():
    box = _boxscore()
    # Drop the explicit gamesStarted from both home pitchers.
    for pid in ('ID11', 'ID12'):
        box['teams']['home']['players'][pid]['stats']['pitching'].pop('gamesStarted')
    payload = build_completed_game_payload(_schedule_game(), boxscore=box)
    home_pitchers = payload['home']['pitchers']
    assert home_pitchers[0]['games_started'] == 1   # first used = starter
    assert home_pitchers[1]['games_started'] == 0


# ── Linescore normalization ───────────────────────────────────────────────────

def test_linescore_is_flattened_with_totals():
    payload = build_completed_game_payload(
        _schedule_game(), boxscore=_boxscore(), linescore=_raw_linescore()
    )
    ls = payload['linescore']
    assert ls['home_runs'] == 3
    assert ls['away_runs'] == 1
    assert ls['innings'][0] == {'num': 1, 'home': 1, 'away': 0}
    assert ls['innings'][-1] == {'num': 7, 'home': 0, 'away': 1}


def test_linescore_totals_backfill_from_schedule_score():
    raw = _raw_linescore()
    raw['teams'] = {}  # no totals on the linescore itself
    payload = build_completed_game_payload(
        _schedule_game(home_score=5, away_score=2),
        boxscore=_boxscore(),
        linescore=raw,
    )
    assert payload['linescore']['home_runs'] == 5
    assert payload['linescore']['away_runs'] == 2


def test_empty_linescore_is_dropped_not_faked():
    payload = build_completed_game_payload(
        _schedule_game(home_score=5, away_score=2),
        boxscore=_boxscore(),
        linescore={'innings': [], 'teams': {'home': {'runs': 5}, 'away': {'runs': 2}}},
    )
    # A final-score-only entry must not masquerade as inning-level context.
    assert 'linescore' not in payload


# ── Play-by-play normalization ────────────────────────────────────────────────

def test_play_by_play_is_normalized_in_order_with_cumulative_score():
    pbp = _raw_play_by_play([
        (6, 'top', 1, 3, 11),
        (7, 'top', 1, 3, 12),
        (8, 'top', 1, 3, 12),
    ])
    payload = build_completed_game_payload(
        _schedule_game(), boxscore=_boxscore(), play_by_play=pbp
    )
    assert payload['plays'][0] == {
        'inning': 6, 'half': 'top', 'away_score': 1, 'home_score': 3, 'pitcher_id': 11,
    }
    assert [p['pitcher_id'] for p in payload['plays']] == [11, 12, 12]


def test_ambiguous_play_by_play_is_dropped_to_fail_closed():
    pbp = _raw_play_by_play([(6, 'top', 1, 3, 11)])
    # Corrupt the score so the play is ambiguous.
    pbp['allPlays'][0]['result'].pop('homeScore')
    payload = build_completed_game_payload(
        _schedule_game(), boxscore=_boxscore(),
        linescore=_raw_linescore(), play_by_play=pbp,
    )
    assert 'plays' not in payload        # fail closed
    assert 'linescore' in payload        # but still degrade to MEDIUM


def test_non_monotonic_play_scores_are_dropped():
    pbp = _raw_play_by_play([
        (6, 'top', 1, 3, 11),
        (7, 'top', 0, 0, 12),   # score went backwards → ambiguous
    ])
    payload = build_completed_game_payload(
        _schedule_game(), boxscore=_boxscore(), play_by_play=pbp
    )
    assert 'plays' not in payload


def test_incomplete_plays_are_skipped_not_fatal():
    pbp = _raw_play_by_play([(6, 'top', 1, 3, 11), (7, 'top', 1, 3, 12)])
    pbp['allPlays'][1]['about']['isComplete'] = False
    payload = build_completed_game_payload(
        _schedule_game(), boxscore=_boxscore(), play_by_play=pbp
    )
    assert [p['inning'] for p in payload['plays']] == [6]


def test_missing_game_pk_returns_none():
    assert build_completed_game_payload({'teams': {}}, boxscore=_boxscore()) is None
    assert build_completed_game_payload('not a dict') is None


# ── End-to-end: adapter output drives HIGH extraction ─────────────────────────

def test_adapter_output_feeds_high_confidence_extraction():
    pbp = _raw_play_by_play([
        (6, 'top', 1, 3, 11),    # home up 3-1 at starter's last batter
        (7, 'top', 1, 3, 12),    # reliever enters
        (9, 'top', 1, 3, 12),    # final 3-1 home
    ])
    payload = build_completed_game_payload(
        _schedule_game(home_score=3, away_score=1),
        boxscore=_boxscore(), linescore=_raw_linescore(), play_by_play=pbp,
    )
    contexts = extract_completed_game_contexts(payload)
    home = next(c for c in contexts if c['home_away'] == 'home')
    assert home['confidence'] == CONFIDENCE_HIGH
    assert home['bullpen_entry_inning'] == 7
    assert home['lead_when_bullpen_entered'] == 2
    assert home['lead_protected'] is True
