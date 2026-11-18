"""Step 6: render results/REPORT.md from analysis_results.json.

Every number in the report comes from results/analysis_results.json and
results/dataset_summary.json. The interpretation (findings and ranked
refinements) is hand-written in results/findings.md and included verbatim, so a
rerun refreshes the numbers but not the prose. If you rerun on different
data, re-read the findings against the new tables.
"""

from __future__ import annotations

import json
import shutil

from . import config
from .analysis import OUTCOMES, RESULTS_DIR, STATES

STATE_LABEL = {'fresh': 'Fresh', 'stretched': 'Stretched', 'vulnerable': 'Vulnerable'}
FMT = {'bp_ra9': 2, 'bp_ra9_all': 2, 'blown_lead': 3, 'ra_7_9': 2, 'ra_7_plus': 2, 'starter_ip': 2, 'bullpen_ip': 2}


def _n(x, d=2):
    return '—' if x is None or x != x else f'{x:+.{d}f}' if d < 0 else f'{x:.{d}f}'


def _g(x, d):
    return '—' if x is None or x != x else f'{x:+.{d}f}'


def _ci(c, d):
    if not c or c[0] is None:
        return '—'
    return f'[{c[0]:+.{d}f}, {c[1]:+.{d}f}]'


def _outcome_rows(table, groups, label=lambda g: g):
    head = '| Outcome | ' + ' | '.join(label(g) for g in groups) + ' |'
    sep = '|---|' + '---:|' * len(groups)
    rows = [head, sep]
    rows.append('| Team-games | ' + ' | '.join(f"{table['groups'][g]['team_games']:,}" for g in groups) + ' |')
    rows.append('| Games led after 6 | ' + ' | '.join(f"{table['groups'][g]['games_led_after_6']:,}" for g in groups) + ' |')
    for o, (_n1, _d, _s, lab, _w) in OUTCOMES.items():
        rows.append(f'| {lab} | ' + ' | '.join(_n(table['groups'][g][o], FMT[o]) for g in groups) + ' |')
    return '\n'.join(rows)


def _gap_rows(gaps, key, title):
    rows = [f'| Outcome ({title}) | Within-team gap | 95% CI | Pooled gap | 95% CI | Team-seasons |',
            '|---|---:|---:|---:|---:|---:|']
    for o, (_n1, _d, _s, lab, _w) in OUTCOMES.items():
        e = gaps[key][o] if key else gaps[o]
        d = FMT[o]
        rows.append(f"| {lab} | {_g(e['within_team_gap'], d)} | {_ci(e.get('within_team_ci'), d)} | "
                    f"{_g(e['pooled_gap'], d)} | {_ci(e.get('pooled_ci'), d)} | {e['team_seasons_used']} |")
    return '\n'.join(rows)


def render():
    res = json.load(open(RESULTS_DIR / 'analysis_results.json'))
    shutil.copy(config.OUTPUT_DIR / 'dataset_summary.json', RESULTS_DIR / 'dataset_summary.json')
    ds = json.load(open(RESULTS_DIR / 'dataset_summary.json'))
    findings = (RESULTS_DIR / 'findings.md').read_text() if (RESULTS_DIR / 'findings.md').exists() else '_findings.md missing_'
    s = res['sample']
    p = res['pass']
    av = res['availability_primary']
    L = []
    w = L.append

    w('# Bullpen state backtest: does "Vulnerable" mean worse bullpen results?\n')
    w('Seasons 2024, 2025 and 2026, all regular-season games. Every pre-game state is a '
      'day-by-day replay of the current production engine, unchanged and untuned. '
      'Internal research only (MLB Stats API terms).\n')

    w('## Pass / fail (bars fixed before results)\n')
    w('| Bar | Result | Estimate | 95% CI | Verdict |')
    w('|---|---|---:|---:|---|')
    r9 = p['ra9_bar']
    w(f"| Vulnerable bullpens allow **≥ 0.4 more runs per 9** than Fresh (within-team), CI excludes 0 | "
      f"Vulnerable − Fresh | {r9['gap']:+.2f} | {_ci(r9['ci'], 2)} | **{'PASS' if r9['passed'] else 'FAIL'}** |")
    ab = p['availability_bar']
    w(f"| Unavailable relievers pitch at **≤ half** the Available rate, CI excludes equal rates | "
      f"Unavailable ÷ Available pitch rate | {ab['ratio']:.4f} | [{ab['ci'][0]:.4f}, {ab['ci'][1]:.4f}] | "
      f"**{'PASS' if ab['passed'] else 'FAIL'}** |")
    w(f"\nUnavailable flags in the primary sample: **{ab['unavailable_flags']:,}**.\n")

    w(findings)

    w('\n## Sample\n')
    w('| Season | Team-games | Fresh | Stretched | Vulnerable | Withheld | Reliever-days | Missing pitch counts scored as 0 |')
    w('|---|---:|---:|---:|---:|---:|---:|---:|')
    for season, d in ds['seasons'].items():
        c = d['team_games_by_state']
        w(f"| {season} | {d['team_games']:,} | {c.get('fresh', 0):,} | {c.get('stretched', 0):,} | "
          f"{c.get('vulnerable', 0):,} | {c.get('data_limited', 0):,} | {d['reliever_days']:,} | "
          f"{d['reliever_days_pitch_count_unknown_scored_as_zero']:,} |")
    tot = s['state_counts_all']
    w(f"| **All** | {sum(tot.values()):,} | {tot['fresh']:,} | {tot['stretched']:,} | {tot['vulnerable']:,} | "
      f"{tot['data_limited']:,} | {sum(d['reliever_days'] for d in ds['seasons'].values()):,} | "
      f"{sum(d['reliever_days_pitch_count_unknown_scored_as_zero'] for d in ds['seasons'].values()):,} |")
    w(f"\nPrimary sample: {s['primary_team_games']:,} team-games, excluding {s['dh_game2_team_games']} "
      f"doubleheader game-2 team-games (reported separately below). {s['team_seasons']} team-seasons. "
      f"{s['zero_bullpen_out_games_primary']} primary team-games had zero bullpen outs; they drop out of the "
      'runs-per-9 regression but stay in pooled ratios.\n')

    w('## Outcomes by Team State (primary sample)\n')
    w(_outcome_rows(res['primary'], STATES, lambda g: STATE_LABEL[g]))
    w('\n**Ordering check (Fresh < Stretched < Vulnerable, pooled values):**\n')
    for o, v in res['ordering'].items():
        vals = ', '.join(f'{STATE_LABEL[s]} {x:.{FMT[o] + 1}f}' for s, x in zip(STATES, v['values']))
        w(f"- {OUTCOMES[o][3]}: {vals} → {'ordered' if v['fresh_lt_stretched_lt_vulnerable'] else '**not ordered**'}")
    w('\nFor starter and bullpen innings, the order shows direction only. Neither is a "worse" outcome.\n')

    w('## Gaps with 95% bootstrap intervals\n')
    w('A within-team gap is each team-season\'s own Vulnerable (or Stretched) days minus its own Fresh days, '
      'averaged with equal weight across team-seasons that have at least 5 games in both states. '
      'Blown leads require at least 3 led-after-six games in both states. The pooled gap compares all '
      'team-games together. Intervals resample whole team-seasons, with 2,000 draws.\n')
    w('### Vulnerable − Fresh\n')
    w(_gap_rows(res['primary']['gaps'], 'vulnerable_minus_fresh', 'V − F'))
    w('\n### Stretched − Fresh\n')
    w(_gap_rows(res['primary']['gaps'], 'stretched_minus_fresh', 'S − F'))
    w('\n### Vulnerable − Stretched\n')
    w(_gap_rows(res['vulnerable_minus_stretched'], None, 'V − S'))

    w('\n## Regression: bullpen runs per 9 (pitchers only)\n')
    reg = res['regression']
    w(reg['spec'] + f" n = {reg['n_games']:,} team-games.\n")
    w('| Term | Estimate | 95% CI |')
    w('|---|---:|---:|')
    names = {'stretched_vs_fresh': 'Stretched vs Fresh', 'vulnerable_vs_fresh': 'Vulnerable vs Fresh',
             'opp_offense_per_run': 'Opponent offense (per 1 R/G)', 'home': 'Home'}
    for k, v in reg['coefficients'].items():
        w(f"| {names[k]} | {v['estimate']:+.3f} | {_ci(v['ci'], 3)} |")

    w('\n## Reliever availability: same-day pitch rate by pre-game flag\n')
    w('| Flag | Reliever-days | Pitched | Same-day pitch rate | 95% CI | Did not pitch |')
    w('|---|---:|---:|---:|---:|---:|')
    for f, v in av['flags'].items():
        w(f"| {f} | {v['reliever_days']:,} | {v['pitched']:,} | {v['same_day_pitch_rate']:.3f} | "
          f"[{v['rate_ci'][0]:.3f}, {v['rate_ci'][1]:.3f}] | {1 - v['same_day_pitch_rate']:.3f} |")
    for k in ('Unavailable_to_Available_ratio', 'Avoid+Unavailable_to_Available_ratio'):
        v = av[k]
        w(f"\n- **{k.replace('_to_', ' ÷ ').replace('_ratio', '')} pitch-rate ratio:** {v['ratio']:.4f} "
          f"(95% CI {v['ci'][0]:.4f} to {v['ci'][1]:.4f}). Share flagged that did not pitch: {v['did_not_pitch_share']:.3%}.")

    w('\n## Sensitivity checks\n')
    w('### By season (bullpen runs per 9, pitchers only)\n')
    w('| Season | Fresh | Stretched | Vulnerable | V − F within-team | 95% CI |')
    w('|---|---:|---:|---:|---:|---:|')
    for season, d in res['by_season'].items():
        g = d['groups']
        e = d['vulnerable_minus_fresh_bp_ra9']
        w(f"| {season} | {g['fresh']['bp_ra9']:.2f} (n={g['fresh']['team_games']:,}) | "
          f"{g['stretched']['bp_ra9']:.2f} (n={g['stretched']['team_games']:,}) | "
          f"{g['vulnerable']['bp_ra9']:.2f} (n={g['vulnerable']['team_games']:,}) | "
          f"{e['within_team_gap']:+.2f} | {_ci(e['within_team_ci'], 2)} |")
    w('\n### Excluding opener games\n')
    eo = res['excluding_openers']
    oc = s['opener_team_games_primary']
    w(f"An opener game is one where the starting pitcher was in his team's pre-game bullpen population "
      f"(known at first pitch). Opener team-games: Fresh {oc['fresh']}, Stretched {oc['stretched']}, "
      f"Vulnerable {oc['vulnerable']}. Without them, bullpen runs per 9 are "
      f"Fresh {eo['groups']['fresh']['bp_ra9']:.2f}, Stretched {eo['groups']['stretched']['bp_ra9']:.2f}, "
      f"Vulnerable {eo['groups']['vulnerable']['bp_ra9']:.2f}. The within-team V − F gap is "
      f"{eo['vulnerable_minus_fresh_bp_ra9']['within_team_gap']:+.2f} "
      f"{_ci(eo['vulnerable_minus_fresh_bp_ra9']['within_team_ci'], 2)}.\n")
    w('### Doubleheader game 2 (state computed before game 1)\n')
    w(_outcome_rows(res['dh_game2'], STATES, lambda g: STATE_LABEL[g]))
    w('\nNo team-season has 5 game-2s in two states, so only pooled gaps exist. '
      f"Vulnerable − Fresh pooled bullpen R/9: {_g(res['dh_game2']['gaps']['vulnerable_minus_fresh']['bp_ra9']['pooled_gap'], 2)} "
      f"{_ci(res['dh_game2']['gaps']['vulnerable_minus_fresh']['bp_ra9']['pooled_ci'], 2)}.")
    d2 = res['availability_dh_game2']['flags']
    w('\nGame-2 same-day pitch rates: ' + ', '.join(
        f"{f} {v['same_day_pitch_rate']:.3f} (n={v['reliever_days']})" for f, v in d2.items()) + '.\n')

    w('## Exploratory (not part of pass/fail)\n')
    w('### Every outcome by number of clean (Available) arms\n')
    ex = res['exploratory_clean_arms']
    groups = list(ex['groups'])
    w(_outcome_rows(ex, groups, lambda g: f'{g} clean'))
    w('\nBullpen runs per 9 gaps vs 0 clean arms:\n')
    w('| Clean arms | Within-team gap vs 0 | 95% CI | Pooled gap vs 0 | 95% CI |')
    w('|---|---:|---:|---:|---:|')
    for g in groups[1:]:
        e = ex['gaps'][f'{g}_minus_0']['bp_ra9']
        w(f"| {g} | {_g(e['within_team_gap'], 2)} | {_ci(e['within_team_ci'], 2)} | {_g(e['pooled_gap'], 2)} | {_ci(e['pooled_ci'], 2)} |")
    w('\n### Vulnerable by rule: "a third or more severe" vs "2 or fewer clean arms"\n')
    vr = res['exploratory_vulnerable_rules']
    w(_outcome_rows(vr, ['margin_floor', 'severity_share'],
                    lambda g: {'margin_floor': '≤ 2 clean arms', 'severity_share': '≥ ⅓ severe'}[g]))
    e = vr['gaps']['severity_share_minus_margin_floor']['bp_ra9']
    w(f"\nPooled bullpen R/9, severe-share minus clean-floor: {_g(e['pooled_gap'], 2)} {_ci(e['pooled_ci'], 2)}. "
      'The severe-share group is too small for a within-team comparison.\n')

    w('## Data notes and assumptions\n')
    w((RESULTS_DIR / 'assumptions.md').read_text())

    out = RESULTS_DIR / 'REPORT.md'
    out.write_text('\n'.join(L) + '\n')
    return out


if __name__ == '__main__':
    print(render())
