"""Round 2: role-weighted state (Test 1) and save prediction (Test 2).

    python -m backtests.bullpen_state.round2 tune      # 2024 only: every variant
    python -m backtests.bullpen_state.round2 evaluate  # 2025+2026, frozen spec only
    python -m backtests.bullpen_state.round2           # both, then the report

Offline only (reads the existing cache and output/reliever_days.csv).

Seal between tuning and evaluation:
* ``tune`` loads appearances from 2023-2024 boxscores only and team-games from
  2024 only. 2025-2026 data is never read.
* ``evaluate`` reads its parameters only from results/round2_frozen_spec.json
  (committed with FROZEN_SPEC.md before evaluation). It refuses to run without
  it, and it never reads the 2024 tuning results.
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import timedelta
from types import SimpleNamespace

import numpy as np
import pandas as pd

from . import analysis, config, mlb_client
from .analysis import N_BOOT, SEED, add_outcomes, bootstrap, outcome_table
from .build_dataset import PITCHER_POSITIONS  # noqa: F401  (documented reuse)
from .games import load_games, parse_boxscore
from .replay import History  # importing replay also puts backend on sys.path

from services.pitcher_role import (  # noqa: E402  production, read-only
    ROLE_INSUFFICIENT, ROLE_LATE, ROLE_LONG, ROLE_LOW, ROLE_MIDDLE, ROLE_SETUP,
    ROLE_WINDOW_DAYS, classify_usage_role,
)
from services.pitcher_role_authority import qualifying_relief_logs  # noqa: E402

RESULTS = analysis.RESULTS_DIR
FROZEN_JSON = RESULTS / 'round2_frozen_spec.json'
TUNE_JSON = RESULTS / 'round2_tuning_2024.json'
EVAL_JSON = RESULTS / 'round2_evaluation.json'
TUNE_SEASON = 2024
EVAL_SEASONS = (2025, 2026)
WINDOW_30 = 30
ROLE_RANK = {ROLE_LATE: 0, ROLE_SETUP: 1, ROLE_MIDDLE: 2, ROLE_LONG: 3, ROLE_LOW: 4, ROLE_INSUFFICIENT: 5}
FIRE_MIN, FIRE_MAX = 0.05, 0.20
T1_PASS_GAP = 0.20
T2_PASS_ACC, T2_PASS_EDGE, T2_MIN_CASES = 0.50, 0.10, 100
NOT_CLEAN = {
    'non_available': {'Monitor', 'Limited', 'Avoid', 'Unavailable'},
    'avoid_unavailable': {'Avoid', 'Unavailable'},
}
TOP3_DEFS = ('role_authority', 'saves_holds_30d')
TIEBREAKS = ('saves_then_holds_30d', 'most_days_rest', 'relief_apps_30d')


# ── Loading (season-scoped) ──────────────────────────────────────────────────

def _load(seasons):
    """Appearances from `seasons` plus the prior season (history), and team-games/flags for `seasons`."""
    seasons = tuple(seasons)
    hist_seasons = sorted({min(seasons) - 1, *seasons})
    games, apps = {}, []
    for s in hist_seasons:
        for g in load_games(s, offline=True):
            games[g.game_pk] = g
            apps.extend(parse_boxscore(g, mlb_client.boxscore(g.game_pk, offline=True)))
    tg = pd.read_csv(config.OUTPUT_DIR / 'team_games.csv')
    tg = tg[tg.season.isin(seasons) & (tg.dh_game2 == 0)].reset_index(drop=True)
    rd = pd.read_csv(config.OUTPUT_DIR / 'reliever_days.csv')
    rd = rd[rd.season.isin(seasons) & (rd.dh_game2 == 0)].reset_index(drop=True)
    assert set(tg.season) <= set(seasons) and set(rd.season) <= set(seasons)
    return games, apps, add_outcomes(tg), rd


def _log(app):
    """Boxscore appearance as the GameLog shape production role code reads."""
    return SimpleNamespace(
        game_date=app.game_date, game_type='R', games_started=app.games_started,
        innings_pitched_outs=app.innings_pitched_outs, innings_pitched=app.innings_pitched,
        pitches_thrown=app.pitches_thrown, save=app.save, hold=app.hold,
        save_situation=app.save_situation, leverage_index=None,
    )


# ── Pre-game arm features ────────────────────────────────────────────────────

def arm_features(history: History, rd: pd.DataFrame) -> pd.DataFrame:
    """Per active-bullpen arm per team-game: role, 30-day saves/holds, flag. Pre-game only."""
    rows = []
    cache = {}
    for r in rd.itertuples(index=False):
        day = pd.Timestamp(r.game_date).date()
        key = (r.pitcher_mlb_id, day)
        if key not in cache:
            logs = history.view_before(day).logs(r.pitcher_mlb_id)   # strictly before game day
            win45 = [_log(a) for a in logs if a.game_date >= day - timedelta(days=ROLE_WINDOW_DAYS)]
            relief, _ex = qualifying_relief_logs(win45)
            role = classify_usage_role(relief, reference_date=day)['role_key']
            win30 = [a for a in logs if a.game_date >= day - timedelta(days=WINDOW_30)]
            sv = sum(1 for a in win30 if a.save)
            hld = sum(1 for a in win30 if a.hold)
            apps30 = sum(1 for a in win30 if (a.games_started or 0) == 0)
            cache[key] = (role, sv, hld, apps30)
        role, sv, hld, apps30 = cache[key]
        rows.append({
            'game_pk': r.game_pk, 'team_id': r.team_id, 'season': r.season, 'game_date': r.game_date,
            'pitcher_mlb_id': r.pitcher_mlb_id, 'flag': r.availability_status,
            'days_rest': r.days_rest if r.days_rest == r.days_rest else 99,
            'usage_role': role, 'role_rank': ROLE_RANK.get(role, 9),
            'sv30': sv, 'hld30': hld, 'svhld30': sv + hld, 'relief_apps30': apps30,
        })
    return pd.DataFrame(rows)


def _top3_key(defn):
    if defn == 'role_authority':
        return lambda a: (a['role_rank'], -a['svhld30'], -a['relief_apps30'], a['pitcher_mlb_id'])
    if defn == 'saves_holds_30d':
        return lambda a: (-a['svhld30'], a['role_rank'], -a['relief_apps30'], a['pitcher_mlb_id'])
    raise ValueError(defn)


def _pick_key(tiebreak):
    """Test 2 ranking: role, then saves+holds 30d, then the tie-break, then id."""
    tb = {
        'saves_then_holds_30d': lambda a: (-a['sv30'], -a['hld30']),
        'most_days_rest': lambda a: (-a['days_rest'],),
        'relief_apps_30d': lambda a: (-a['relief_apps30'],),
    }[tiebreak]
    return lambda a: (a['role_rank'], -a['svhld30'], *tb(a), a['pitcher_mlb_id'])


# ── Test 1 ───────────────────────────────────────────────────────────────────

def test1_flags(tg, feats, defn, n_required, not_clean):
    bad = NOT_CLEAN[not_clean]
    key = _top3_key(defn)
    flag = {}
    for (pk, team), grp in feats.groupby(['game_pk', 'team_id']):
        arms = sorted(grp.to_dict('records'), key=key)[:3]
        flag[(pk, team)] = int(sum(a['flag'] in bad for a in arms) >= n_required)
    out = tg.copy()
    out['t1'] = [flag.get((pk, t), 0) for pk, t in zip(out.game_pk, out.team_id)]
    out['t1_group'] = np.where(out.t1 == 1, 'flagged', 'unflagged')
    return out


def test1_result(df, boot=True):
    tab, _ = outcome_table(df, 't1_group', ('unflagged', 'flagged'), boot=boot)
    gaps = tab['gaps']['flagged_minus_unflagged']
    pick = lambda o: {k: gaps[o].get(k) for k in ('within_team_gap', 'within_team_ci', 'pooled_gap', 'pooled_ci', 'team_seasons_used')}
    return {
        'fire_rate': float(df.t1.mean()),
        'flagged_team_games': int(df.t1.sum()),
        'team_games': int(len(df)),
        'groups': {g: {k: tab['groups'][g][k] for k in ('team_games', 'ra_7_9', 'blown_lead', 'bp_ra9', 'games_led_after_6')} for g in tab['groups']},
        'ra_7_9': pick('ra_7_9'), 'blown_lead': pick('blown_lead'), 'bp_ra9': pick('bp_ra9'),
    }


# ── Test 2 ───────────────────────────────────────────────────────────────────

def save_chances(games, apps, tg):
    """Per team-game: the pitcher handed a 9th-inning-or-later save chance, if any.

    Inning of entry is exact: a team's boxscore lists pitchers in order, so the
    outs recorded before a pitcher entered is the game's out count at entry.
    A save always belongs to the finishing pitcher (so to the 9th or later in a
    game of 9+ innings). A blown save is 9th+ when the pitcher entered with 24+
    outs recorded, or his outing reached the 9th and his team still led when
    its defensive 9th began (so the lead was lost in the 9th or later).
    The recipient is the first pitcher, in appearance order, with either.
    """
    by_gt = defaultdict(list)
    for a in apps:
        by_gt[(a.game_pk, a.team_id)].append(a)
    out, audit = {}, {'save_opportunity_games': 0, 'bs_entered_9th_plus': 0,
                      'bs_straddle_resolved_9th_plus': 0, 'bs_before_9th': 0, 'outs_check_fail': 0}
    want = set(zip(tg.game_pk, tg.team_id))
    for (pk, team), lst in by_gt.items():
        if (pk, team) not in want:
            continue
        g = games[pk]
        if len(g.innings) < 9:
            continue
        lst = sorted(lst, key=lambda a: a.order)
        home = team == g.home_id
        inn = {n: (a_r or 0, h_r or 0) for n, a_r, h_r in g.innings}
        own = lambda n: inn[n][1] if home else inn[n][0]
        opp = lambda n: inn[n][0] if home else inn[n][1]
        own_thru = sum(own(n) for n in range(1, 9 if home else 10) if n in inn)
        opp_thru = sum(opp(n) for n in range(1, 9) if n in inn)
        led_entering_def9 = own_thru > opp_thru
        total_outs = sum(a.innings_pitched_outs for a in lst)
        n_def = len(g.innings)
        if not (3 * (n_def - 1) <= total_outs <= 3 * n_def):
            audit['outs_check_fail'] += 1
        before = 0
        recipient = None
        for a in lst:
            entered, after = before, before + a.innings_pitched_outs
            reached_9th = entered >= 24 or after > 24
            if a.save and recipient is None:
                recipient = a.pitcher_mlb_id
            if a.blown_save and recipient is None:
                if entered >= 24:
                    recipient = a.pitcher_mlb_id
                    audit['bs_entered_9th_plus'] += 1
                elif reached_9th and led_entering_def9:
                    recipient = a.pitcher_mlb_id
                    audit['bs_straddle_resolved_9th_plus'] += 1
                else:
                    audit['bs_before_9th'] += 1
            before = after
        if recipient is not None:
            out[(pk, team)] = recipient
            audit['save_opportunity_games'] += 1
    return out, audit


def closers(feats):
    """Closer per team-game: most saves in the prior 30 days, minimum 3 (ties: holds, then id)."""
    c = feats[feats.sv30 >= 3].sort_values(['sv30', 'hld30', 'pitcher_mlb_id'], ascending=[False, False, True])
    return c.groupby(['game_pk', 'team_id']).head(1).set_index(['game_pk', 'team_id'])


def test2_cases(feats, chances, closer_flags, tiebreak, top_k=1):
    cl = closers(feats)
    key = _pick_key(tiebreak)
    rows = []
    for (pk, team), grp in feats.groupby(['game_pk', 'team_id']):
        if (pk, team) not in cl.index or (pk, team) not in chances:
            continue
        c = cl.loc[(pk, team)]
        if c.flag not in closer_flags:
            continue
        arms = [a for a in grp.to_dict('records') if a['pitcher_mlb_id'] != c.pitcher_mlb_id]
        engine = sorted([a for a in arms if a['flag'] in ('Available', 'Monitor')], key=key)
        naive = sorted(arms, key=key)
        got = chances[(pk, team)]
        rows.append({
            'game_pk': pk, 'team_id': team, 'season': int(c.season),
            'cluster': f'{team}_{int(c.season)}', 'closer_flag': c.flag,
            'recipient_in_bullpen_read': int(any(a['pitcher_mlb_id'] == got for a in arms)),
            'closer_got_chance': int(got == c.pitcher_mlb_id),
            'engine_top1': int(bool(engine) and engine[0]['pitcher_mlb_id'] == got),
            'naive_top1': int(bool(naive) and naive[0]['pitcher_mlb_id'] == got),
            'engine_top2': int(got in [a['pitcher_mlb_id'] for a in engine[:2]]),
            'naive_top2': int(got in [a['pitcher_mlb_id'] for a in naive[:2]]),
        })
    return pd.DataFrame(rows)


def test2_result(cases, k='top1'):
    if cases.empty:
        return {'cases': 0}
    clusters = sorted(cases.cluster.unique())
    idx = {c: np.flatnonzero(cases.cluster.to_numpy() == c) for c in clusters}
    e = cases[f'engine_{k}'].to_numpy()
    n = cases[f'naive_{k}'].to_numpy()

    def stat(fn):
        def inner(draw):
            rows = np.concatenate([idx[clusters[i]] for i in draw])
            return fn(rows)
        return inner
    allr = np.arange(len(cases))
    return {
        'cases': int(len(cases)),
        'by_closer_flag': cases.closer_flag.value_counts().to_dict(),
        'closer_pitched_anyway': int(cases.closer_got_chance.sum()),
        'recipient_in_bullpen_read': int(cases.recipient_in_bullpen_read.sum()),
        'engine_acc': float(e.mean()),
        'engine_ci': bootstrap(stat(lambda r: e[r].mean()), len(clusters)),
        'naive_acc': float(n.mean()),
        'naive_ci': bootstrap(stat(lambda r: n[r].mean()), len(clusters)),
        'edge': float(e.mean() - n.mean()),
        'edge_ci': bootstrap(stat(lambda r: e[r].mean() - n[r].mean()), len(clusters)),
        'team_seasons': len(clusters),
    }


# ── Phases ───────────────────────────────────────────────────────────────────

def _prepare(seasons):
    games, apps, tg, rd = _load(seasons)
    history = History(apps)
    feats = arm_features(history, rd)
    chances, audit = save_chances(games, apps, tg)
    return tg, feats, chances, audit


def tune():
    tg, feats, chances, audit = _prepare((TUNE_SEASON,))
    res = {'season': TUNE_SEASON, 'save_chance_audit': audit, 'test1_variants': [], 'test2_variants': []}
    for defn in TOP3_DEFS:
        for n_req in (1, 2, 3):
            for nc in NOT_CLEAN:
                df = test1_flags(tg, feats, defn, n_req, nc)
                r = test1_result(df)
                r.update({'top3_definition': defn, 'n_not_clean': n_req, 'not_clean': nc,
                          'fire_rate_ok': FIRE_MIN <= r['fire_rate'] <= FIRE_MAX})
                res['test1_variants'].append(r)
                print(f"T1 {defn:16s} N={n_req} {nc:17s} fire={r['fire_rate']:.3f} "
                      f"gap79={r['ra_7_9']['within_team_gap']:+.3f}", flush=True)
    for tb in TIEBREAKS:
        cases = test2_cases(feats, chances, {'Avoid', 'Unavailable'}, tb)
        r = test2_result(cases)
        r['tiebreak'] = tb
        res['test2_variants'].append(r)
        print(f"T2 {tb:22s} cases={r['cases']} engine={r.get('engine_acc', 0):.3f} naive={r.get('naive_acc', 0):.3f}", flush=True)
    # Role-definition audit for Test 2's ranking (descriptive, not a variant).
    res['usage_role_distribution'] = feats.usage_role.value_counts().to_dict()
    TUNE_JSON.write_text(json.dumps(res, indent=2, default=float))
    return res


def evaluate():
    if not FROZEN_JSON.exists():
        sys.exit('round2_frozen_spec.json missing: commit FROZEN_SPEC.md first')
    spec = json.loads(FROZEN_JSON.read_text())
    tg, feats, chances, audit = _prepare(EVAL_SEASONS)
    t1 = spec['test1']
    df = test1_flags(tg, feats, t1['top3_definition'], t1['n_not_clean'], t1['not_clean'])
    r1 = test1_result(df)
    r1['by_season'] = {int(s): test1_result(d) for s, d in df.groupby('season')}
    g = r1['ra_7_9']
    if not (FIRE_MIN <= r1['fire_rate'] <= FIRE_MAX):
        v1 = 'FAIL (fire rate outside 5-20%)'
    else:
        v1 = 'PASS' if g['within_team_gap'] >= T1_PASS_GAP and g['within_team_ci'][0] > 0 else 'FAIL'
    tb = spec['test2']['tiebreak']
    cases = test2_cases(feats, chances, {'Avoid', 'Unavailable'}, tb)
    r2 = test2_result(cases)
    r2['by_season'] = {int(s): test2_result(d) for s, d in cases.groupby('season')} if len(cases) else {}
    if r2['cases'] < T2_MIN_CASES:
        v2 = 'INCONCLUSIVE'
    else:
        v2 = 'PASS' if (r2['engine_acc'] >= T2_PASS_ACC and r2['edge'] >= T2_PASS_EDGE and r2['edge_ci'][0] > 0) else 'FAIL'
    lim = test2_cases(feats, chances, {'Limited', 'Avoid', 'Unavailable'}, tb)
    res = {
        'seasons': list(EVAL_SEASONS), 'frozen_spec': spec, 'save_chance_audit': audit,
        'test1': r1, 'test1_verdict': v1,
        'test2': r2, 'test2_verdict': v2,
        'exploratory': {
            'top2_avoid_unavailable': test2_result(cases, 'top2'),
            'limited_included_top1': test2_result(lim),
            'limited_included_top2': test2_result(lim, 'top2'),
        },
    }
    EVAL_JSON.write_text(json.dumps(res, indent=2, default=float))
    print('T1', v1, r1['fire_rate'], g)
    print('T2', v2, {k: r2.get(k) for k in ('cases', 'engine_acc', 'naive_acc', 'edge', 'edge_ci')})
    return res


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    phase = argv[0] if argv else 'all'
    if phase in ('tune', 'all'):
        tune()
    if phase in ('evaluate', 'all'):
        evaluate()
    if phase in ('report', 'all'):
        from .report_round2 import render
        print(render())


if __name__ == '__main__':
    main()
