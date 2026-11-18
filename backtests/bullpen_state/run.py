"""One command to (re)run the bullpen-state backtest.

    python -m backtests.bullpen_state.run              # fetch (cached) + dataset + analysis + report
    python -m backtests.bullpen_state.run --offline    # cache only, no network

Run from the repository root with the backend requirements installed (Python 3.11,
as in CI). The no-lookahead tests run first; a failure stops the run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import config


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--seasons', type=int, nargs='*', default=list(config.EVAL_SEASONS))
    ap.add_argument('--offline', action='store_true', help='use the cache only; never call the API')
    ap.add_argument('--skip-tests', action='store_true')
    args = ap.parse_args(argv)
    seasons = tuple(args.seasons)
    history = tuple(s for s in config.HISTORY_SEASONS if s < min(seasons))

    if not args.skip_tests:
        rc = subprocess.call([sys.executable, '-m', 'pytest', '-q', str(config.HERE / 'tests')],
                             cwd=str(config.REPO_ROOT))
        if rc != 0:
            print('no-lookahead tests failed; stopping', file=sys.stderr)
            return rc

    if not args.offline:
        from .fetch import fetch_all
        if fetch_all(seasons, history):
            print('some requests failed; rerun to retry (cached responses are kept)', file=sys.stderr)
            return 1

    from .build_dataset import build
    build(seasons, history, offline=True)
    print(f'dataset written to {config.OUTPUT_DIR}')

    from .analysis import run as analyze
    from .report import render
    analyze()
    print(f'report written to {render()}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
