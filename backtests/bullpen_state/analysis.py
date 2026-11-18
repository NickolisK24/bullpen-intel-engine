"""Steps 3-4: outcomes per team-game and the state comparison.

Reads output/team_games.csv and output/reliever_days.csv, writes
results/analysis_results.json. Pure computation, no network.

Conventions (fixed before results were viewed):

* Unit of comparison is a team-season ("each team against its own days").
* Every interval is a 95% percentile bootstrap that resamples whole
  team-seasons (2,000 draws, fixed seed), so within-team correlation of games
  is respected.
* Primary sample excludes doubleheader game 2 (its state is a day staler than
  its first pitch); game 2 is reported separately as a sensitivity check.
* Ratio outcomes are pooled (sum of numerators / sum of denominators), never an
  average of per-game ratios, so short bullpen outings do not dominate.
"""

from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from . import config
from .games import load_games

RESULTS_DIR = config.HERE / 'results'
STATES = ('fresh', 'stretched', 'vulnerable')
N_BOOT = 2000
SEED = 20261118
MIN_GAMES_PER_STATE = 5        # a team-season enters a within-team gap only with >= 5 games in both states
MIN_LED_GAMES_PER_STATE = 3    # same, for the blown-lead rate (games led after six)
OPP_SHRINK_GAMES = 20          # opponent offense: shrink season-to-date R/G toward league with 20 phantom games
PASS_RA9_GAP = 0.4
PASS_RATE_RATIO = 0.5

# outcome -> (numerator column, denominator column, scale, label, "higher is worse")
OUTCOMES = {
    'bp_ra9': ('bp_runs_p', 'bp_outs_p', 27.0, 'Bullpen runs per 9 (pitchers only) [primary]', True),
    'bp_ra9_all': ('bp_runs_all', 'bp_outs_all', 27.0, 'Bullpen runs per 9 (incl. position players)', True),
    'blown_lead': ('blown', 'led6', 1.0, 'Blown lead rate (led after 6, lost)', True),
    'ra_7_9': ('ra79', 'has7', 1.0, 'Runs allowed, innings 7-9', True),
    'ra_7_plus': ('ra7p', 'has7', 1.0, 'Team runs allowed, 7th inning on (incl. extras)', True),
    'starter_ip': ('starter_outs_n', 'one', 1 / 3, 'Starter innings', None),
    'bullpen_ip': ('bp_outs_p', 'one', 1 / 3, 'Bullpen innings (pitchers only)', None),
}


# ── Step 3: outcomes ─────────────────────────────────────────────────────────

def _innings(js):
    return [(int(n), 0 if r is None else int(r)) for n, r in json.loads(js)]


def add_outcomes(tg: pd.DataFrame) -> pd.DataFrame:
    tg = tg.copy()
    inn_for = tg.innings_for.map(_innings)
    inn_against = tg.innings_against.map(_innings)
    n_inn = inn_for.map(len)
    for6 = inn_for.map(lambda xs: sum(r for n, r in xs if n <= 6))
    ag6 = inn_against.map(lambda xs: sum(r for n, r in xs if n <= 6))
    tg['has7'] = (n_inn >= 7).astype(int)                    # game reached the 7th
    tg['led6'] = ((for6 > ag6) & (tg.has7 == 1)).astype(int)
    tg['lost'] = (tg.runs_scored < tg.runs_allowed).astype(int)
    tg['blown'] = (tg.led6 & tg.lost).astype(int)
    tg['ra79'] = np.where(tg.has7 == 1, inn_against.map(lambda xs: sum(r for n, r in xs if 7 <= n <= 9)), 0)
    tg['ra7p'] = np.where(tg.has7 == 1, inn_against.map(lambda xs: sum(r for n, r in xs if n >= 7)), 0)
    tg['bp_runs_p'] = tg.bullpen_runs_pitchers
    tg['bp_outs_p'] = tg.bullpen_outs_pitchers
    tg['bp_runs_all'] = tg.bullpen_runs
    tg['bp_outs_all'] = tg.bullpen_outs
    tg['starter_outs_n'] = tg.starter_outs.fillna(0)
    tg['one'] = 1
    tg['cluster'] = tg.team_id.astype(str) + '_' + tg.season.astype(str)
    return tg


def add_opponent_offense(tg: pd.DataFrame) -> pd.DataFrame:
    """Opponent runs/game from games on strictly earlier dates, shrunk to league."""
    tg = tg.copy()
    tg['gd'] = pd.to_datetime(tg.game_date)
    prior_league = {}
    for season in sorted(tg.season.unique()):
        prev = [g for g in load_games(int(season) - 1, offline=True)] if (config.CACHE_DIR / 'schedule' / f'{int(season) - 1}.json.gz').exists() else []
        runs = [r for g in prev for r in (g.home_runs, g.away_runs) if r is not None]
        prior_league[season] = float(np.mean(runs)) if runs else float(tg[tg.season == season].runs_scored.mean())
    out = np.empty(len(tg))
    for season, sdf in tg.groupby('season'):
        by_date = sdf.groupby('gd').agg(r=('runs_scored', 'sum'), n=('runs_scored', 'size')).sort_index()
        lg_r = by_date.r.cumsum().shift(fill_value=0)
        lg_n = by_date.n.cumsum().shift(fill_value=0)
        lg_mean = ((lg_r + prior_league[season] * 100) / (lg_n + 100))   # league mean to date, seeded by last season
        team = sdf.groupby(['team_id', 'gd']).agg(r=('runs_scored', 'sum'), n=('runs_scored', 'size')).sort_index()
        team['cr'] = team.groupby(level=0).r.cumsum() - team.r
        team['cn'] = team.groupby(level=0).n.cumsum() - team.n
        for idx, row in sdf.iterrows():
            key = (row.opponent_id, row.gd)
            cr, cn = team.loc[key, ['cr', 'cn']]
            lm = lg_mean.loc[row.gd]
            out[tg.index.get_loc(idx)] = (cr + OPP_SHRINK_GAMES * lm) / (cn + OPP_SHRINK_GAMES)
    tg['opp_offense'] = out
    return tg


def mark_openers(tg: pd.DataFrame, rd: pd.DataFrame) -> pd.DataFrame:
    """Opener game: the starting pitcher was in his team's pre-game bullpen read."""
    tg = tg.copy()
    pen = set(zip(rd.game_pk, rd.team_id, rd.pitcher_mlb_id))
    tg['opener'] = [
        int((pk, t, s) in pen) if not pd.isna(s) else 0
        for pk, t, s in zip(tg.game_pk, tg.team_id, tg.starter_mlb_id)
    ]
    return tg


# ── Bootstrap machinery ──────────────────────────────────────────────────────

class ClusterStats:
    """Per (cluster, group) sums so every bootstrap draw is a cheap reindex."""

    def __init__(self, df: pd.DataFrame, group_col: str, groups):
        self.clusters = np.array(sorted(df.cluster.unique()))
        self.groups = list(groups)
        cols = sorted({c for num, den, *_ in OUTCOMES.values() for c in (num, den)})
        g = df.groupby(['cluster', group_col])[cols].sum()
        idx = pd.MultiIndex.from_product([self.clusters, self.groups])
        g = g.reindex(idx, fill_value=0)
        self.sums = {c: g[c].to_numpy().reshape(len(self.clusters), len(self.groups)) for c in cols}
        self.games = df.groupby(['cluster', group_col]).size().reindex(idx, fill_value=0).to_numpy().reshape(len(self.clusters), len(self.groups))

    def gi(self, group):
        return self.groups.index(group)


def _ratio(num, den, scale):
    with np.errstate(divide='ignore', invalid='ignore'):
        return np.where(den > 0, scale * num / den, np.nan)


def pooled_metric(cs: ClusterStats, outcome, group, sample=None):
    num, den, scale, *_ = OUTCOMES[outcome]
    s = slice(None) if sample is None else sample
    j = cs.gi(group)
    n = cs.sums[num][s, j].sum()
    d = cs.sums[den][s, j].sum()
    return float(scale * n / d) if d else float('nan')


def within_team_gap(cs: ClusterStats, outcome, a, b, sample=None):
    """Mean over eligible team-seasons of metric(b) - metric(a)."""
    num, den, scale, *_ = OUTCOMES[outcome]
    s = np.arange(len(cs.clusters)) if sample is None else sample
    ia, ib = cs.gi(a), cs.gi(b)
    min_den = MIN_LED_GAMES_PER_STATE if den == 'led6' else None
    ga, gb = cs.games[s, ia], cs.games[s, ib]
    da, db = cs.sums[den][s, ia], cs.sums[den][s, ib]
    ok = (ga >= MIN_GAMES_PER_STATE) & (gb >= MIN_GAMES_PER_STATE) & (da > 0) & (db > 0)
    if min_den:
        ok &= (da >= min_den) & (db >= min_den)
    if not ok.any():
        return float('nan'), 0
    ma = scale * cs.sums[num][s, ia][ok] / da[ok]
    mb = scale * cs.sums[num][s, ib][ok] / db[ok]
    return float(np.mean(mb - ma)), int(ok.sum())


def bootstrap(fn, n_clusters, n_boot=N_BOOT, seed=SEED):
    rng = np.random.default_rng(seed)
    vals = []
    for _ in range(n_boot):
        draw = rng.integers(0, n_clusters, n_clusters)
        v = fn(draw)
        if v is not None and not np.isnan(v):
            vals.append(v)
    if not vals:
        return [None, None]
    lo, hi = np.percentile(vals, [2.5, 97.5])
    return [float(lo), float(hi)]


def outcome_table(df: pd.DataFrame, group_col: str, groups, boot=True):
    """Pooled metric per group, plus within-team and pooled gaps vs the first group."""
    cs = ClusterStats(df, group_col, groups)
    nc = len(cs.clusters)
    table = {'groups': {}, 'gaps': {}}
    for g in groups:
        sub = df[df[group_col] == g]
        table['groups'][str(g)] = {
            'team_games': int(len(sub)),
            'games_led_after_6': int(sub.led6.sum()),
            'bullpen_outs': int(sub.bp_outs_p.sum()),
            **{o: pooled_metric(cs, o, g) for o in OUTCOMES},
        }
    base = groups[0]
    for g in groups[1:]:
        for o in OUTCOMES:
            wt, n_teams = within_team_gap(cs, o, base, g)
            pooled = table['groups'][str(g)][o] - table['groups'][str(base)][o]
            entry = {'within_team_gap': wt, 'team_seasons_used': n_teams, 'pooled_gap': pooled}
            if boot:
                entry['within_team_ci'] = bootstrap(lambda s: within_team_gap(cs, o, base, g, s)[0], nc)
                entry['pooled_ci'] = bootstrap(lambda s: pooled_metric(cs, o, g, s) - pooled_metric(cs, o, base, s), nc)
            table['gaps'][f'{g}_minus_{base}'] = table['gaps'].get(f'{g}_minus_{base}', {})
            table['gaps'][f'{g}_minus_{base}'][o] = entry
    return table, cs


def ordering(table, outcome):
    vals = [table['groups'][s][outcome] for s in STATES]
    return {
        'values': vals,
        'fresh_lt_stretched_lt_vulnerable': bool(vals[0] < vals[1] < vals[2]),
    }


# ── Regression ───────────────────────────────────────────────────────────────

def _design(df):
    y = 27.0 * df.bp_runs_p.to_numpy() / df.bp_outs_p.to_numpy()
    w = df.bp_outs_p.to_numpy().astype(float)
    parts = [
        (df.public_state == 'stretched').astype(float).to_numpy()[:, None],
        (df.public_state == 'vulnerable').astype(float).to_numpy()[:, None],
        (df.opp_offense - df.opp_offense.mean()).to_numpy()[:, None],
        (df.home_away == 'home').astype(float).to_numpy()[:, None],
        pd.get_dummies(df.cluster, drop_first=False).to_numpy(float),      # team-season fixed effects (absorb intercept)
        pd.get_dummies(df.venue_id.astype(str), drop_first=True).to_numpy(float),  # ballpark
    ]
    return y, w, np.hstack(parts)


def _wls(y, w, X):
    sw = np.sqrt(w)
    beta, *_ = np.linalg.lstsq(X * sw[:, None], y * sw, rcond=None)
    return beta[:4]


def regression(df: pd.DataFrame, n_boot=N_BOOT):
    df = df[df.bp_outs_p > 0].reset_index(drop=True)
    y, w, X = _design(df)
    coef = _wls(y, w, X)
    clusters = df.cluster.to_numpy()
    uniq = np.unique(clusters)
    rows_by = {c: np.flatnonzero(clusters == c) for c in uniq}
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(n_boot):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([rows_by[uniq[k]] for k in pick])
        # Rebuild FE columns for the draw so a repeated team-season shares one effect.
        sub = df.iloc[idx]
        yb, wb, Xb = _design(sub)
        draws.append(_wls(yb, wb, Xb))
    draws = np.array(draws)
    names = ['stretched_vs_fresh', 'vulnerable_vs_fresh', 'opp_offense_per_run', 'home']
    return {
        'n_games': int(len(df)),
        'dropped_zero_bullpen_out_games': None,
        'coefficients': {
            n: {'estimate': float(coef[i]), 'ci': [float(np.percentile(draws[:, i], 2.5)), float(np.percentile(draws[:, i], 97.5))]}
            for i, n in enumerate(names)
        },
        'spec': 'WLS of game bullpen R/9 (pitchers only) on state dummies (fresh = baseline), '
                'team-season fixed effects, ballpark fixed effects, opponent season-to-date R/G '
                '(prior dates only, shrunk), home indicator; weights = bullpen outs; '
                'team-season cluster bootstrap.',
    }


# ── Availability ─────────────────────────────────────────────────────────────

FLAGS = ('Available', 'Monitor', 'Limited', 'Avoid', 'Unavailable')


def availability(rd: pd.DataFrame):
    rd = rd.copy()
    rd['cluster'] = rd.team_id.astype(str) + '_' + rd.season.astype(str)
    rd['flag'] = rd.availability_status
    clusters = np.array(sorted(rd.cluster.unique()))
    groups = list(FLAGS) + ['Avoid+Unavailable']
    rd2 = pd.concat([rd, rd[rd.flag.isin(['Avoid', 'Unavailable'])].assign(flag='Avoid+Unavailable')])
    g = rd2.groupby(['cluster', 'flag']).agg(n=('pitched', 'size'), p=('pitched', 'sum'))
    idx = pd.MultiIndex.from_product([clusters, groups])
    g = g.reindex(idx, fill_value=0)
    N = g.n.to_numpy().reshape(len(clusters), len(groups))
    P = g.p.to_numpy().reshape(len(clusters), len(groups))

    def rate(j, s=slice(None)):
        n = N[s, j].sum()
        return P[s, j].sum() / n if n else np.nan

    out = {'flags': {}}
    for j, f in enumerate(groups):
        out['flags'][f] = {
            'reliever_days': int(N[:, j].sum()),
            'pitched': int(P[:, j].sum()),
            'same_day_pitch_rate': float(rate(j)),
            'rate_ci': bootstrap(lambda s, j=j: rate(j, s), len(clusters)),
        }
    ja = groups.index('Available')
    for f in ('Unavailable', 'Avoid+Unavailable'):
        jf = groups.index(f)
        ratio = rate(jf) / rate(ja)
        out[f'{f}_to_Available_ratio'] = {
            'ratio': float(ratio),
            'ci': bootstrap(lambda s, jf=jf: rate(jf, s) / rate(ja, s), len(clusters)),
            'did_not_pitch_share': float(1 - rate(jf)),
        }
    return out


# ── Orchestration ────────────────────────────────────────────────────────────

def run():
    tg = pd.read_csv(config.OUTPUT_DIR / 'team_games.csv')
    rd = pd.read_csv(config.OUTPUT_DIR / 'reliever_days.csv')
    tg = add_outcomes(tg)
    tg = add_opponent_offense(tg)
    tg = mark_openers(tg, rd)
    primary = tg[tg.dh_game2 == 0]
    dh2 = tg[tg.dh_game2 == 1]

    res = {'generated_from': {'team_games': int(len(tg)), 'reliever_days': int(len(rd))}}
    res['sample'] = {
        'primary_team_games': int(len(primary)),
        'dh_game2_team_games': int(len(dh2)),
        'state_counts_primary': primary.public_state.value_counts().reindex(list(STATES) + ['data_limited'], fill_value=0).to_dict(),
        'state_counts_all': tg.public_state.value_counts().reindex(list(STATES) + ['data_limited'], fill_value=0).to_dict(),
        'state_counts_by_season': {int(s): d.public_state.value_counts().reindex(STATES, fill_value=0).to_dict() for s, d in tg.groupby('season')},
        'zero_bullpen_out_games_primary': int((primary.bp_outs_p == 0).sum()),
        'position_player_pitching_team_games': int((tg.pp_outs > 0).sum() + ((tg.pp_runs > 0) & (tg.pp_outs == 0)).sum()),
        'position_player_runs': int(tg.pp_runs.sum()),
        'opener_team_games_primary': primary.groupby('public_state').opener.sum().reindex(STATES, fill_value=0).to_dict(),
        'team_seasons': int(tg.cluster.nunique()),
    }

    main_tab, _ = outcome_table(primary, 'public_state', STATES)
    res['primary'] = main_tab
    vs_stretched, _ = outcome_table(primary[primary.public_state != 'fresh'], 'public_state', ('stretched', 'vulnerable'))
    res['vulnerable_minus_stretched'] = vs_stretched['gaps']['vulnerable_minus_stretched']
    res['ordering'] = {o: ordering(main_tab, o) for o in OUTCOMES}
    res['regression'] = regression(primary)
    res['regression']['dropped_zero_bullpen_out_games'] = res['sample']['zero_bullpen_out_games_primary']

    res['by_season'] = {}
    for s, d in primary.groupby('season'):
        t, _ = outcome_table(d, 'public_state', STATES)
        res['by_season'][int(s)] = {
            'groups': {k: {'team_games': v['team_games'], 'bp_ra9': v['bp_ra9']} for k, v in t['groups'].items()},
            'vulnerable_minus_fresh_bp_ra9': t['gaps']['vulnerable_minus_fresh']['bp_ra9'],
        }

    t, _ = outcome_table(dh2, 'public_state', STATES)
    res['dh_game2'] = t
    t, _ = outcome_table(primary[primary.opener == 0], 'public_state', STATES)
    res['excluding_openers'] = {'groups': {k: {'team_games': v['team_games'], 'bp_ra9': v['bp_ra9']} for k, v in t['groups'].items()},
                                'vulnerable_minus_fresh_bp_ra9': t['gaps']['vulnerable_minus_fresh']['bp_ra9']}

    res['availability_primary'] = availability(rd[rd.dh_game2 == 0])
    res['availability_dh_game2'] = availability(rd[rd.dh_game2 == 1])

    # Exploratory (not part of pass/fail)
    prim = primary.copy()
    prim['clean_bucket'] = prim.clean_count.clip(upper=5).map(lambda c: '5+' if c >= 5 else str(int(c)))
    buckets = [b for b in ('0', '1', '2', '3', '4', '5+') if (prim.clean_bucket == b).any()]
    t, _ = outcome_table(prim, 'clean_bucket', buckets, boot=True)
    res['exploratory_clean_arms'] = t
    vul = primary[primary.public_state == 'vulnerable']
    t, _ = outcome_table(vul, 'decisive_rule', ('margin_floor', 'severity_share'), boot=True)
    res['exploratory_vulnerable_rules'] = t

    gap = main_tab['gaps']['vulnerable_minus_fresh']['bp_ra9']
    ratio = res['availability_primary']['Unavailable_to_Available_ratio']
    res['pass'] = {
        'ra9_bar': {
            'rule': f'within-team vulnerable - fresh bullpen R/9 >= {PASS_RA9_GAP} and 95% CI excludes 0',
            'gap': gap['within_team_gap'], 'ci': gap['within_team_ci'],
            'passed': bool(gap['within_team_gap'] >= PASS_RA9_GAP and gap['within_team_ci'][0] > 0),
        },
        'availability_bar': {
            'rule': f'Unavailable same-day pitch rate <= {PASS_RATE_RATIO} x Available rate and 95% CI of the ratio excludes 1',
            'ratio': ratio['ratio'], 'ci': ratio['ci'],
            'unavailable_flags': res['availability_primary']['flags']['Unavailable']['reliever_days'],
            'passed': bool(ratio['ratio'] <= PASS_RATE_RATIO and ratio['ci'][1] < 1),
        },
    }
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESULTS_DIR / 'analysis_results.json', 'w') as fh:
        json.dump(res, fh, indent=2, default=float)
    return res


if __name__ == '__main__':
    run()
