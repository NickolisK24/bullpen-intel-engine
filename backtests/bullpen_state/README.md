# Bullpen state backtest

Question: do bullpens the engine flags **Vulnerable** before a game perform
worse in that game than ones flagged **Fresh**?

This folder is self-contained research tooling. It imports production engine
code read-only and changes no production behavior. It is not part of the app,
the nightly pipeline, or CI.

## Run

From the repository root, with the backend requirements installed on Python 3.11
(as in CI) plus `pytest`:

```bash
python -m backtests.bullpen_state.run            # fetch missing data, build dataset, analyze, write report
python -m backtests.bullpen_state.run --offline  # same, from the cache only
```

The first run downloads about 24,000 MLB Stats API responses (schedules,
boxscores, day-before active rosters for 2023–2026) at no more than 4 requests
per second. Every response is cached gzip-compressed under `.cache/` and never
requested again. Row-level outputs go to `output/`. Both `.cache/` and `output/` are git-ignored.
Aggregate results go to `results/`, which is committed:

- `REPORT.md`: the report.
- `analysis_results.json`: every number in the report.
- `dataset_summary.json`: dataset counts.
- `findings.md` and `assumptions.md`: the hand-written prose the report includes.
  They are not regenerated. Re-read them if a rerun's numbers change.

**Source terms.** Every MLB Stats API response points to MLB Advanced Media's
copyright notice (`gdx.mlb.com/components/copyright.txt`). Use here is limited
to internal, non-commercial research. Do not publish or redistribute the cache
or the row-level outputs.

## What it does

1. **Replay** (`replay.py`). For every team and game date, rebuild the pre-game
   Team State the nightly pipeline would have published, using production code:
   role authority → fatigue score → availability → coverage/trust → Contract A.
   Inputs are boxscore appearances dated strictly before the game and the MLB
   active roster as of the previous day.
2. **Dataset** (`build_dataset.py`):
   - `team_games.csv`: one row per team per game, with the pre-game state, its
     evidence counts, team fatigue score (mean reliever score), and the
     same-game raw pitching and linescore facts.
   - `reliever_days.csv`: one row per active-bullpen reliever per team-game,
     with his pre-game availability flag and whether he pitched.
   - `dataset_summary.json`: counts.
3. **Outcomes and analysis** (`analysis.py`). Outcomes per team-game, within-team
   gaps, a fixed-effects regression, and a team-season cluster bootstrap for
   every interval.
4. **Report** (`report.py`). Writes `results/REPORT.md`.
5. **No-lookahead proof** (`tests/test_no_lookahead.py`). Same-day and future
   data, real or synthetic, cannot change any pre-game output.

## Replay assumptions

- **Appearance history.** Taken from boxscores rather than the production
  gameLog rows. The fields are the same.
- **Roster.** Active-bullpen membership uses the MLB active roster for the day
  before the game, which is the slate-day convention production uses. Only
  pitching positions count, so two-way players (`TWP`) are excluded, as in
  production. The production role authority then reads each pitcher's last 10
  appearances.
- **Freshness and completeness.** Source freshness, appearance-ledger
  completeness, and roster authority are treated as current and complete. The
  coverage gate still runs. An arm whose recent logs lack a pitch count still
  counts as unresolved.
- **Doubleheaders.** Both games share one state, computed from data through the
  prior day.
- **Workload scope.** Only regular-season appearances count toward workload.
  Spring training and postseason are excluded.

## Round 2: role-weighted state and save prediction

```bash
python -m backtests.bullpen_state.round2            # tune (2024) + evaluate (2025-26, frozen spec) + report
python -m backtests.bullpen_state.round2 evaluate   # evaluation only; reads results/round2_frozen_spec.json
```

This works offline from the round 1 cache and `output/`, so run round 1 first.

- **Spec.** `FROZEN_SPEC.md` holds the definitions chosen on 2024. It was
  committed before 2025–2026 were evaluated.
- **Tuning.** Reads 2023–2024 data only.
- **Evaluation.** Takes its parameters only from the frozen JSON.
- **Report.** Written to `results/REPORT_ROUND2.md`.
