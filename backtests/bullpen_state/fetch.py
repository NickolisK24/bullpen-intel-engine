"""Warm the source cache: schedules, boxscores, and day-before active rosters.

    python -m backtests.bullpen_state.fetch            # all configured seasons

Idempotent. Cached responses are never refetched, so an interrupted run resumes.
"""

from __future__ import annotations

import argparse
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import timedelta

from . import config, mlb_client
from .games import load_games


def _run(tasks, label):
    done = failed = 0
    with ThreadPoolExecutor(config.WORKER_THREADS) as pool:
        futures = [pool.submit(fn, *args) for fn, *args in tasks]
        for fut in as_completed(futures):
            try:
                fut.result()
                done += 1
            except Exception as exc:  # keep going; report at the end
                failed += 1
                print(f'  [{label}] failed: {exc}', file=sys.stderr)
            if (done + failed) % 500 == 0:
                print(f'  [{label}] {done + failed}/{len(futures)} '
                      f'(network={mlb_client.stats["network"]})', flush=True)
    print(f'[{label}] done={done} failed={failed}', flush=True)
    return failed


def roster_requests(games):
    """(team_id, day-before) for every team-date that has a game.

    The replay asks for the active roster as of the day BEFORE the game, the
    same slate-day convention production uses for active-bullpen membership.
    """
    keys = set()
    for g in games:
        prev = g.game_date - timedelta(days=1)
        keys.add((g.home_id, prev))
        keys.add((g.away_id, prev))
    return sorted(keys)


def fetch_all(eval_seasons=config.EVAL_SEASONS, history_seasons=config.HISTORY_SEASONS):
    failures = 0
    all_seasons = sorted(set(history_seasons) | set(eval_seasons))
    games_by_season = {}
    for season in all_seasons:
        games_by_season[season] = load_games(season)
        print(f'[schedule] {season}: {len(games_by_season[season])} final regular-season games', flush=True)

    for season in all_seasons:
        tasks = [(mlb_client.boxscore, g.game_pk) for g in games_by_season[season]]
        failures += _run(tasks, f'boxscore {season}')

    for season in eval_seasons:
        tasks = [(mlb_client.active_roster, t, d) for t, d in roster_requests(games_by_season[season])]
        failures += _run(tasks, f'roster {season}')
    print(f'network requests this run: {mlb_client.stats["network"]}, cache hits: {mlb_client.stats["cache"]}')
    return failures


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--seasons', type=int, nargs='*', default=list(config.EVAL_SEASONS))
    args = ap.parse_args(argv)
    history = tuple(s for s in config.HISTORY_SEASONS if s < min(args.seasons))
    return 1 if fetch_all(tuple(args.seasons), history) else 0


if __name__ == '__main__':
    raise SystemExit(main())
