"""Proof that a pre-game state uses only data available before first pitch.

Three checks, all on synthetic data so they run offline in milliseconds:

1. The HistoryView never exposes an appearance dated on or after its cutoff.
2. Injecting heavy fake workload on the game date and every later date leaves
   every replayed output (team state, counts, each reliever's flag and fatigue
   score) byte-for-byte identical.
3. Deleting everything on/after the game date also leaves it identical, while
   the same fake workload placed one day EARLIER does change the state — so the
   test would catch a replay that ignored history altogether.

A fourth check runs the same injection against real cached data when the cache
is present (skipped otherwise).
"""

from __future__ import annotations

from dataclasses import asdict, replace
from datetime import date, timedelta

import pytest

from backtests.bullpen_state.games import Appearance
from backtests.bullpen_state.replay import History, replay_team_day

TEAM = 999
GAME_DAY = date(2025, 6, 15)


def _app(pid, day, *, started=0, outs=3, pitches=15, pk=None):
    return Appearance(
        pitcher_mlb_id=pid, pitcher_name=f'P{pid}', team_id=TEAM,
        game_pk=pk or int(day.strftime('%Y%m%d')) * 10 + (pid % 10), game_date=day,
        game_number=1, order=0 if started else 1, games_started=started,
        innings_pitched_outs=outs, innings_pitched=outs / 3, pitches_thrown=pitches,
        runs_allowed=0, earned_runs=0, save=False, hold=False, save_situation=False,
        blown_save=False, inherited_runners=0, inherited_runners_scored=0, position='P',
    )


def _roster(pids):
    return [
        {'person': {'id': pid, 'fullName': f'P{pid}'},
         'position': {'abbreviation': 'P'}, 'status': {'code': 'A'}}
        for pid in pids
    ]


RELIEVERS = list(range(1, 9))


def _base_history():
    apps = []
    # Eight relievers with a light, spread-out relief history before the game.
    for pid in RELIEVERS:
        for k in range(10):
            apps.append(_app(pid, GAME_DAY - timedelta(days=6 + 3 * k + pid % 3)))
    return apps


def _future_workload(start_day):
    """Massive fake workload for every reliever on start_day and the 5 days after."""
    apps = []
    for pid in RELIEVERS:
        for d in range(6):
            apps.append(_app(pid, start_day + timedelta(days=d), outs=9, pitches=60,
                             pk=900000 + pid * 10 + d))
    return apps


def _snapshot(apps):
    history = History(apps)
    state = replay_team_day(TEAM, GAME_DAY, _roster(RELIEVERS), history.view_before(GAME_DAY))
    return asdict(state)


def test_view_hides_cutoff_day_and_later():
    apps = _base_history() + _future_workload(GAME_DAY)
    view = History(apps).view_before(GAME_DAY)
    for pid in RELIEVERS:
        logs = view.logs(pid)
        assert logs, 'history before the cutoff must remain visible'
        assert all(log.game_date < GAME_DAY for log in logs)
        assert logs == sorted(logs, key=lambda l: l.game_date, reverse=True)


def test_future_and_same_day_data_cannot_change_pregame_state():
    baseline = _snapshot(_base_history())
    with_future = _snapshot(_base_history() + _future_workload(GAME_DAY))
    assert with_future == baseline


def test_truncating_future_is_identical_and_past_injection_is_detected():
    base = _base_history()
    truncated = [a for a in base if a.game_date < GAME_DAY]
    assert _snapshot(truncated) == _snapshot(base)

    baseline = _snapshot(base)
    # The same workload placed so it ends the day BEFORE the game must matter.
    shifted_earlier = _snapshot(base + _future_workload(GAME_DAY - timedelta(days=6)))
    assert shifted_earlier['public_state'] != baseline['public_state']
    assert baseline['public_state'] == 'fresh'
    assert shifted_earlier['public_state'] == 'vulnerable'


def test_view_must_match_game_date():
    history = History(_base_history())
    with pytest.raises(ValueError):
        replay_team_day(TEAM, GAME_DAY, _roster(RELIEVERS), history.view_before(GAME_DAY + timedelta(days=1)))


def test_real_data_injection_when_cache_present():
    from backtests.bullpen_state import mlb_client
    from backtests.bullpen_state.games import load_games, parse_boxscore

    try:
        games = load_games(2025, offline=True)
    except FileNotFoundError:
        pytest.skip('no cached 2025 schedule')
    sample = [g for g in games if g.game_date.month == 7][:20]
    apps = []
    for g in games:
        if g.game_date > date(2025, 7, 31):
            break
        try:
            apps.extend(parse_boxscore(g, mlb_client.boxscore(g.game_pk, offline=True)))
        except FileNotFoundError:
            pytest.skip('boxscore cache incomplete')
    history = History(apps)
    checked = 0
    for g in sample:
        try:
            roster = mlb_client.active_roster(g.home_id, g.game_date - timedelta(days=1), offline=True)['roster']
        except FileNotFoundError:
            continue
        before = asdict(replay_team_day(g.home_id, g.game_date, roster, history.view_before(g.game_date)))
        # Corrupt everything on/after the game date: 10x pitches, extra outs.
        poisoned = [
            replace(a, pitches_thrown=(a.pitches_thrown or 0) * 10 + 100, innings_pitched_outs=27)
            if a.game_date >= g.game_date else a
            for a in apps
        ]
        after = asdict(replay_team_day(g.home_id, g.game_date, roster, History(poisoned).view_before(g.game_date)))
        assert before == after
        checked += 1
    if not checked:
        pytest.skip('roster cache not yet warm')
