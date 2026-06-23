"""Game Shape integration into Rotation Support Pressure (Phase C3K).

Opener/bulk and bullpen games no longer distort starter depth, short-start rate,
or rotation-driven bullpen burden; they are tracked separately as transparency.
Genuine normal and short starts are unchanged, and the downstream Bullpen
Environment read no longer calls an opener-heavy sample "short-start workload".
"""

from datetime import date, timedelta

from services.bullpen_environment import SOURCE_ROTATION, build_team_bullpen_environment
from services.rotation_support_pressure import (
    INCOMPLETE_GAME_DATA_LIMITATION,
    OPENER_BULK_LIMITATION,
    STATUS_HEAVY,
    STATUS_LIMITED,
    build_team_rotation_support_pressure,
)
from utils.innings import outs_to_decimal_innings


REF = date(2026, 6, 18)
TEAM = {'team_id': 1, 'team_name': 'Test Team', 'team_abbreviation': 'TST'}


def _log(game_pk, days_ago, outs, games_started, seq=0):
    return {
        'pitcher_id': game_pk * 100 + (games_started or 0) * 10 + seq,
        'mlb_game_pk': game_pk,
        'game_date': REF - timedelta(days=days_ago),
        'game_type': 'R',
        'games_started': games_started,
        'innings_pitched_outs': outs,
        'innings_pitched': outs_to_decimal_innings(outs),
    }


def _start_game(game_pk, days_ago, starter_outs, relief_outs):
    return [_log(game_pk, days_ago, starter_outs, 1), _log(game_pk, days_ago, relief_outs, 0)]


def _opener_bulk_game(game_pk, days_ago, opener_outs=3, bulk_outs=21):
    return [_log(game_pk, days_ago, opener_outs, 1), _log(game_pk, days_ago, bulk_outs, 0)]


def _bullpen_game(game_pk, days_ago):
    return [
        _log(game_pk, days_ago, 12, 0, seq=1),
        _log(game_pk, days_ago, 9, 0, seq=2),
        _log(game_pk, days_ago, 6, 0, seq=3),
    ]


def _pressure(logs):
    return build_team_rotation_support_pressure(logs, team=TEAM, reference_date=REF)


# ── Opener/bulk no longer distorts starter depth or short-start rate ─────────

def test_opener_bulk_does_not_depress_starter_average():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_opener_bulk_game(4, 4),
    ])

    # The average reflects the three genuine rotation starts (6.0 IP), not the opener.
    assert result['games_analyzed'] == 3
    assert result['starter_avg_innings'] == 6.0
    assert result['opener_bulk_games'] == 1


def test_opener_bulk_does_not_inflate_short_start_rate():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_opener_bulk_game(4, 4),
    ])

    assert result['short_start_count'] == 0
    assert result['short_start_rate'] == 0.0


def test_opener_bulk_innings_are_separated_and_still_visible():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_opener_bulk_game(4, 4, opener_outs=3, bulk_outs=21),
    ])

    # Bulk-follower innings are not rotation-driven bullpen pressure ...
    assert result['bullpen_outs_required'] == 27  # 3 rotation games x 9 relief outs
    # ... but remain visible as transparency.
    assert result['bulk_follower_outs'] == 21
    assert result['bulk_follower_innings'] == 7.0


# ── Genuine rotation reads are unchanged ─────────────────────────────────────

def test_genuine_short_start_still_counts_as_short_start():
    # A 4-inning start (12 outs) is a short start, not an opener (opener <= 6 outs).
    result = _pressure([
        *_start_game(1, 1, 12, 15),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
    ])

    assert result['games_analyzed'] == 3
    assert result['short_start_count'] == 1
    assert result['opener_bulk_games'] == 0


def test_normal_start_read_is_unchanged():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_start_game(4, 4, 18, 9),
    ])

    assert result['games_analyzed'] == 4
    assert result['starter_avg_innings'] == 6.0
    assert result['short_start_rate'] == 0.0
    assert result['bullpen_outs_required'] == 36
    assert result['opener_bulk_games'] == 0
    assert result['bullpen_games'] == 0


# ── Bullpen games tracked separately, not as missing data ────────────────────

def test_bullpen_game_is_tracked_separately():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_bullpen_game(4, 4),
    ])

    assert result['games_in_window'] == 4
    assert result['games_analyzed'] == 3
    assert result['bullpen_games'] == 1
    assert result['bullpen_game_outs'] == 27
    assert result['game_shape_distribution'].get('bullpen_game') == 1


def test_bullpen_game_does_not_count_as_incomplete_data():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_bullpen_game(4, 4),
    ])

    assert result['games_excluded'] == 0
    assert 'no_starter' not in result['excluded_game_reasons']
    assert INCOMPLETE_GAME_DATA_LIMITATION not in result['limitations']


# ── Downstream Bullpen Environment read ──────────────────────────────────────

def test_bullpen_environment_no_longer_labels_opener_sample_short_start_workload():
    # Three genuine 6-inning starts plus three opener/bulk games. Pre-Game-Shape,
    # the openers read as short starts and pushed rotation_support_pressure to
    # heavy_pressure, which the environment surfaced as "short-start workload".
    rotation = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
        *_opener_bulk_game(4, 4),
        *_opener_bulk_game(5, 5),
        *_opener_bulk_game(6, 6),
    ])

    assert rotation['status'] != STATUS_HEAVY
    assert rotation['short_start_rate'] == 0.0
    assert rotation['opener_bulk_games'] == 3

    environment = build_team_bullpen_environment(
        team=TEAM,
        capacity_intelligence={'capacity_loss': {'status': 'clear', 'unavailable_capacity_pct': 0}},
        rotation_support_pressure=rotation,
        bullpen_stability={'status': 'stable', 'new_or_reintroduced_arm_count': 0},
    )

    assert SOURCE_ROTATION not in environment['primary_pressure_sources']
    assert environment['supporting_reads']['rotation_short_start_rate'] == 0.0


# ── Payload compatibility and determinism ────────────────────────────────────

def test_payload_remains_backward_compatible_and_additive():
    result = _pressure([
        *_start_game(1, 1, 18, 9),
        *_start_game(2, 2, 18, 9),
        *_start_game(3, 3, 18, 9),
    ])

    for key in (
        'status', 'window_days', 'games_in_window', 'games_analyzed', 'games_excluded',
        'starter_outs', 'starter_avg_innings', 'bullpen_outs_required',
        'short_start_count', 'short_start_rate', 'definitions', 'thresholds',
        'methodology_notes', 'source_limitations', 'summary', 'limitations',
    ):
        assert key in result

    for key in ('opener_bulk_games', 'bullpen_games', 'bulk_follower_outs', 'game_shape_distribution'):
        assert key in result

    assert OPENER_BULK_LIMITATION in result['source_limitations']


def test_rotation_support_output_is_deterministic():
    logs = [
        *_start_game(1, 1, 18, 9),
        *_opener_bulk_game(2, 2),
        *_bullpen_game(3, 3),
    ]

    assert _pressure(logs) == _pressure(logs)
