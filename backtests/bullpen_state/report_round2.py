"""Render results/REPORT_ROUND2.md from the round 2 tuning and evaluation JSON.

Numbers come from round2_tuning_2024.json and round2_evaluation.json. The
summary prose is hand-written in results/findings_round2.md and included
verbatim.
"""

from __future__ import annotations

import json

from .analysis import RESULTS_DIR
from .round2 import EVAL_JSON, TUNE_JSON

DEF_LABEL = {'role_authority': 'Role authority', 'saves_holds_30d': 'Saves + holds (30d)'}
NC_LABEL = {'non_available': 'not Available', 'avoid_unavailable': 'Avoid/Unavailable'}


def _ci(c, d=3, pct=False):
    if not c or c[0] is None:
        return '—'
    if pct:
        return f'[{c[0]:.1%}, {c[1]:.1%}]'
    return f'[{c[0]:+.{d}f}, {c[1]:+.{d}f}]'


def _g(x, d=3):
    return '—' if x is None or x != x else f'{x:+.{d}f}'


def _t1_rows(variants, frozen=None):
    rows = ['| Top-3 definition | N of 3 | "Not clean" | Fire rate | In 5–20%? | Innings 7–9 runs gap | 95% CI | Blown-lead gap | 95% CI | Bullpen R/9 gap | 95% CI |',
            '|---|---:|---|---:|:---:|---:|---:|---:|---:|---:|---:|']
    for v in variants:
        mark = ' **← frozen**' if frozen and (v['top3_definition'], v['n_not_clean'], v['not_clean']) == frozen else ''
        rows.append(
            f"| {DEF_LABEL[v['top3_definition']]}{mark} | {v['n_not_clean']} | {NC_LABEL[v['not_clean']]} | "
            f"{v['fire_rate']:.1%} | {'yes' if v['fire_rate_ok'] else 'no'} | "
            f"{_g(v['ra_7_9']['within_team_gap'])} | {_ci(v['ra_7_9']['within_team_ci'])} | "
            f"{_g(v['blown_lead']['within_team_gap'])} | {_ci(v['blown_lead']['within_team_ci'])} | "
            f"{_g(v['bp_ra9']['within_team_gap'], 2)} | {_ci(v['bp_ra9']['within_team_ci'], 2)} |")
    return '\n'.join(rows)


def _t2_row(label, r):
    if not r.get('cases'):
        return f'| {label} | 0 | — | — | — | — | — | — |'
    return (f"| {label} | {r['cases']} | {r['engine_acc']:.1%} | {_ci(r['engine_ci'], pct=True)} | "
            f"{r['naive_acc']:.1%} | {_ci(r['naive_ci'], pct=True)} | {r['edge'] * 100:+.1f} pts | "
            f"[{r['edge_ci'][0] * 100:+.1f}, {r['edge_ci'][1] * 100:+.1f}] |")


T2_HEAD = ('| Sample | Cases | Engine | 95% CI | Naive | 95% CI | Engine − naive | 95% CI |\n'
           '|---|---:|---:|---:|---:|---:|---:|---:|')


def render():
    tune = json.loads(TUNE_JSON.read_text())
    ev = json.loads(EVAL_JSON.read_text())
    spec = ev['frozen_spec']
    frozen = (spec['test1']['top3_definition'], spec['test1']['n_not_clean'], spec['test1']['not_clean'])
    t1, t2 = ev['test1'], ev['test2']
    L = []
    w = L.append
    w('# Bullpen backtest, round 2: role-weighted state and save prediction\n')
    w('Tuned on 2024 only. Evaluated once on 2025 and 2026 combined, with the definitions frozen in '
      '`FROZEN_SPEC.md`, which was committed before evaluation. No new data requests. Same methods as round 1: '
      'within-team gaps, a team-season bootstrap with 2,000 draws, doubleheader game 2 excluded, and position '
      'players excluded from bullpen runs per 9.\n')

    w('## Verdicts\n')
    g = t1['ra_7_9']
    w('| Test | Bar | Result | Verdict |')
    w('|---|---|---|---|')
    w(f"| 1. Role-weighted state | Innings 7–9 runs, flagged − unflagged (within-team) ≥ +0.20, CI excludes 0; fires on 5–20% | "
      f"{g['within_team_gap']:+.3f} {_ci(g['within_team_ci'])}; fires {t1['fire_rate']:.1%} | **{ev['test1_verdict']}** |")
    w(f"| 2. Save prediction | Engine top-1 ≥ 50% and ≥ 10 pts over naive, CI excludes 0; needs ≥ 100 cases | "
      f"{t2['cases']} cases; engine {t2['engine_acc']:.1%}, naive {t2['naive_acc']:.1%}, "
      f"edge {t2['edge'] * 100:+.1f} pts | **{ev['test2_verdict']}** |\n")

    w((RESULTS_DIR / 'findings_round2.md').read_text())

    w('\n## Frozen definitions\n')
    w('Summary (full text in `FROZEN_SPEC.md`):\n')
    w('- **Test 1.**')
    w('  - Top 3 late-inning arms: ranked by saves + holds over the prior 30 days, then production usage role, '
      'then relief appearances.')
    w('  - Flag: at least 1 of those 3 is flagged Avoid or Unavailable.')
    w('- **Test 2.**')
    w('  - Closer: most saves over the prior 30 days, minimum 3.')
    w('  - Case: the closer is flagged Avoid/Unavailable and the team had a 9th-inning-or-later save chance.')
    w('  - Engine pick: among Available/Monitor arms, rank by usage role, then saves + holds (30d), '
      'then saves, then holds.')
    w('  - Naive pick: the same ranking with flags ignored and the closer excluded.\n')

    w('## Test 1: role-weighted state\n')
    w('### Every 2024 variant (tuning season)\n')
    w('All gaps are within-team: flagged days minus the same team-season\'s unflagged days.\n')
    w(_t1_rows(tune['test1_variants'], frozen))
    w('\nWhen a variant fires on almost no team-games, no team-season has 5 flagged games, so the gap is blank.\n')
    w('### Evaluation: 2025 + 2026 (frozen variant)\n')
    w(f"Flag fired on {t1['flagged_team_games']:,} of {t1['team_games']:,} team-games ({t1['fire_rate']:.1%}).\n")
    w('| Outcome | Unflagged | Flagged | Within-team gap | 95% CI | Pooled gap | 95% CI | Team-seasons |')
    w('|---|---:|---:|---:|---:|---:|---:|---:|')
    lab = {'ra_7_9': 'Runs allowed, innings 7–9 [primary]', 'blown_lead': 'Blown-lead rate', 'bp_ra9': 'Bullpen runs per 9 (pitchers only)'}
    for o in ('ra_7_9', 'blown_lead', 'bp_ra9'):
        e = t1[o]
        d = 2 if o == 'bp_ra9' else 3
        w(f"| {lab[o]} | {t1['groups']['unflagged'][o]:.3f} | {t1['groups']['flagged'][o]:.3f} | "
          f"{_g(e['within_team_gap'], d)} | {_ci(e['within_team_ci'], d)} | {_g(e['pooled_gap'], d)} | "
          f"{_ci(e['pooled_ci'], d)} | {e['team_seasons_used']} |")
    w('\n**By season (within-team gaps):**\n')
    w('| Season | Fire rate | Innings 7–9 runs | 95% CI | Blown lead | 95% CI | Bullpen R/9 | 95% CI |')
    w('|---|---:|---:|---:|---:|---:|---:|---:|')
    for s, d in t1['by_season'].items():
        w(f"| {s} | {d['fire_rate']:.1%} | {_g(d['ra_7_9']['within_team_gap'])} | {_ci(d['ra_7_9']['within_team_ci'])} | "
          f"{_g(d['blown_lead']['within_team_gap'])} | {_ci(d['blown_lead']['within_team_ci'])} | "
          f"{_g(d['bp_ra9']['within_team_gap'], 2)} | {_ci(d['bp_ra9']['within_team_ci'], 2)} |")

    w('\n## Test 2: save prediction\n')
    w('### Every 2024 tie-break variant (tuning season)\n')
    w(T2_HEAD)
    for v in tune['test2_variants']:
        mark = ' **← frozen**' if v['tiebreak'] == spec['test2']['tiebreak'] else ''
        w(_t2_row(f"{v['tiebreak']}{mark}", v))
    w('\n### Evaluation: 2025 + 2026 (frozen ranking, top-1)\n')
    w(T2_HEAD)
    w(_t2_row('2025 + 2026', t2))
    for s, d in t2.get('by_season', {}).items():
        w(_t2_row(f'{s} only', d))
    w(f"\n**Case counts:**\n")
    w(f"- {t2['cases']} cases across {t2['team_seasons']} team-seasons.")
    w(f"- Closer flagged: {', '.join(f'{k} {v}' for k, v in t2['by_closer_flag'].items())}.")
    w(f"- The flagged closer took the save chance himself in {t2['closer_pitched_anyway']} cases.")
    w(f"- In {t2['cases'] - t2['recipient_in_bullpen_read'] - t2['closer_pitched_anyway']} more cases, the save "
      'chance went to another arm outside the pre-game bullpen read.')
    w(f"- No pick could be right in either situation. Those {t2['cases'] - t2['recipient_in_bullpen_read']} cases "
      'count as misses for the engine and the naive pick alike.\n')
    a = ev['save_chance_audit']
    w(f"**Save-chance derivation (2025 + 2026):** {a['save_opportunity_games']:,} team-games had a 9th-inning-or-later save chance.")
    w(f"- Blown saves counted: {a['bs_entered_9th_plus']} where the pitcher entered with 24+ outs, and "
      f"{a['bs_straddle_resolved_9th_plus']} that needed the 'still led entering the 9th' rule.")
    w(f"- Blown saves excluded as before the 9th: {a['bs_before_9th']}.")
    w(f"- Team-games of 9+ innings where pitcher outs failed to reconcile with the line score: {a['outs_check_fail']}.\n")
    w('### Exploratory (not part of pass/fail)\n')
    ex = ev['exploratory']
    w(T2_HEAD)
    w(_t2_row('Top-2, Avoid/Unavailable closers', ex['top2_avoid_unavailable']))
    w(_t2_row('Top-1, Limited closers included', ex['limited_included_top1']))
    w(_t2_row('Top-2, Limited closers included', ex['limited_included_top2']))
    lim = ex['limited_included_top1']
    w(f"\nWith Limited closers included, the closer took the save chance himself in {lim['closer_pitched_anyway']} "
      f"of {lim['cases']} cases ({lim['closer_pitched_anyway'] / lim['cases']:.0%}).\n")
    out = RESULTS_DIR / 'REPORT_ROUND2.md'
    out.write_text('\n'.join(L) + '\n')
    return out


if __name__ == '__main__':
    print(render())
