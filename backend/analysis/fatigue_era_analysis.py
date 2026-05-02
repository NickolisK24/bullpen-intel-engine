"""
BaseballOS — Fatigue vs Next-Appearance ERA Analysis
-----------------------------------------------------
Walks 2024-2025 game logs, reconstructs each pitcher's fatigue score going
into every appearance, and measures performance in their NEXT appearance.

The premise being tested: relievers who pitched at HIGH or CRITICAL fatigue
posted a meaningfully worse ERA in their next outing than those at LOW or
MODERATE fatigue.

Run: python -m analysis.fatigue_era_analysis
"""

import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from app import create_app
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.fatigue import calculate_fatigue

SEASONS = [2024, 2025]
TIERS = ['LOW', 'MODERATE', 'HIGH', 'CRITICAL']
RESULTS_PATH = os.path.join(os.path.dirname(__file__), 'fatigue_era_results.json')
WINDOW_DAYS = 14


def ip_to_decimal(ip):
    """
    Convert MLB-style innings (e.g. 1.1 = 1⅓, 1.2 = 1⅔) to a true decimal.
    Pure decimals pass through unchanged. None becomes 0.0.
    """
    if ip is None:
        return 0.0
    whole = int(ip)
    frac = ip - whole
    if abs(frac - 0.1) < 0.01:
        return whole + 1 / 3
    if abs(frac - 0.2) < 0.01:
        return whole + 2 / 3
    return float(ip)


def collect_appearance_pairs(pitcher, logs):
    """
    For each appearance N (except the last), compute the fatigue score the
    pitcher carried into it and pair it with their NEXT appearance's IP/ER.

    `logs` must be ordered by game_date ascending and pre-filtered to drop
    appearances where innings_pitched is null or zero.
    """
    pairs = []
    for i in range(len(logs) - 1):
        current = logs[i]
        nxt = logs[i + 1]

        ref_date = current.game_date
        window_start = ref_date.toordinal() - WINDOW_DAYS

        window_logs = [
            g for g in logs
            if window_start <= g.game_date.toordinal() <= ref_date.toordinal()
        ]
        # calculate_fatigue expects most-recent-first ordering
        window_logs.sort(key=lambda g: g.game_date, reverse=True)

        score = calculate_fatigue(pitcher, window_logs, reference_date=ref_date)

        pairs.append({
            'pitcher_id': pitcher.id,
            'appearance_n_date': ref_date,
            'fatigue_score_before_next': score.raw_score,
            'risk_tier': score.risk_level,
            'next_appearance_ip': ip_to_decimal(nxt.innings_pitched),
            'next_appearance_er': int(nxt.earned_runs or 0),
        })
    return pairs


def aggregate_by_tier(pairs):
    """Group records by risk tier and compute IP/ER/ERA totals."""
    buckets = {tier: {'appearances': 0, 'ip': 0.0, 'er': 0, 'fatigue_sum': 0.0}
               for tier in TIERS}

    for p in pairs:
        tier = p['risk_tier']
        if tier not in buckets:
            continue
        buckets[tier]['appearances'] += 1
        buckets[tier]['ip'] += p['next_appearance_ip']
        buckets[tier]['er'] += p['next_appearance_er']
        buckets[tier]['fatigue_sum'] += p['fatigue_score_before_next']

    out = {}
    for tier, b in buckets.items():
        ip = b['ip']
        er = b['er']
        era = (er * 9 / ip) if ip > 0 else None
        avg_fatigue = (b['fatigue_sum'] / b['appearances']) if b['appearances'] else None
        out[tier] = {
            'appearances': b['appearances'],
            'ip': round(ip, 2),
            'er': er,
            'era': round(era, 2) if era is not None else None,
            'avg_fatigue': round(avg_fatigue, 2) if avg_fatigue is not None else None,
        }
    return out


def build_comparison(tiers):
    """
    Compare MODERATE (rested baseline) against HIGH+CRITICAL combined
    (elevated fatigue). LOW is excluded because pitchers who have a 'next
    appearance' almost never score LOW by definition — that tier requires
    5+ days of rest, which means they haven't pitched recently enough to
    be in the analysis window.
    """
    moderate = tiers.get('MODERATE', {})
    high = tiers.get('HIGH', {})
    critical = tiers.get('CRITICAL', {})

    baseline_apps = moderate.get('appearances', 0)
    baseline_ip = moderate.get('ip', 0)
    baseline_er = moderate.get('er', 0)
    baseline_era = moderate.get('era')

    elevated_apps = high.get('appearances', 0) + critical.get('appearances', 0)
    elevated_ip = high.get('ip', 0) + critical.get('ip', 0)
    elevated_er = high.get('er', 0) + critical.get('er', 0)
    elevated_era = (elevated_er * 9 / elevated_ip) if elevated_ip > 0 else None

    if baseline_apps < 100 or elevated_apps < 100 or baseline_era is None or elevated_era is None:
        return {
            'baseline_tier': 'MODERATE',
            'baseline_era': baseline_era,
            'baseline_apps': baseline_apps,
            'elevated_era': round(elevated_era, 2) if elevated_era is not None else None,
            'elevated_apps': elevated_apps,
            'pct_difference': None,
            'headline': ('Insufficient sample to compare rested vs elevated '
                         'fatigue ERAs across the 2024-2025 seasons.'),
        }

    pct_diff = ((elevated_era - baseline_era) / baseline_era) * 100
    headline = (f'Pitchers throwing at HIGH or CRITICAL fatigue posted a '
                f'{elevated_era:.2f} ERA in their next outing — '
                f'{abs(pct_diff):.0f}% {"worse" if pct_diff >= 0 else "better"} '
                f'than the {baseline_era:.2f} ERA they posted when rested.')

    return {
        'baseline_tier': 'MODERATE',
        'baseline_era': round(baseline_era, 2),
        'baseline_apps': baseline_apps,
        'elevated_era': round(elevated_era, 2),
        'elevated_apps': elevated_apps,
        'pct_difference': round(pct_diff),
        'headline': headline,
    }


def print_table(tiers, total):
    print()
    print(f'  Total appearances analyzed: {total}')
    print()
    print('  Tier      | Apps  | IP       | ER   | ERA   | Avg Fatigue')
    print('  ----------+-------+----------+------+-------+------------')
    for tier in TIERS:
        d = tiers[tier]
        era = f'{d["era"]:.2f}' if d['era'] is not None else '  n/a'
        af = f'{d["avg_fatigue"]:.1f}' if d['avg_fatigue'] is not None else ' n/a'
        print(f'  {tier:<9} | {d["appearances"]:>5} | {d["ip"]:>8.2f} | '
              f'{d["er"]:>4} | {era:>5} | {af:>10}')
    print()


def run():
    pitchers = Pitcher.query.filter_by(active=True).all()
    print(f'Analyzing fatigue → next-appearance ERA for {len(pitchers)} pitchers '
          f'across seasons {SEASONS}...')

    all_pairs = []
    for i, pitcher in enumerate(pitchers):
        if i % 50 == 0 and i > 0:
            print(f'  → {i}/{len(pitchers)}')

        logs = (
            GameLog.query
            .filter(GameLog.pitcher_id == pitcher.id)
            .order_by(GameLog.game_date.asc())
            .all()
        )

        # Filter: only 2024-2025 logs with real innings pitched.
        logs = [
            g for g in logs
            if g.game_date.year in SEASONS
            and g.innings_pitched is not None
            and g.innings_pitched > 0
        ]

        if len(logs) < 2:
            continue

        all_pairs.extend(collect_appearance_pairs(pitcher, logs))

    tiers = aggregate_by_tier(all_pairs)
    comparison = build_comparison(tiers)

    payload = {
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'seasons': SEASONS,
        'total_appearances_analyzed': len(all_pairs),
        'tiers': tiers,
        'comparison': comparison,
        'headline': comparison['headline'],
    }

    with open(RESULTS_PATH, 'w') as fh:
        json.dump(payload, fh, indent=2)

    print_table(tiers, len(all_pairs))
    print(f'  Headline: {comparison["headline"]}')
    print(f'  Wrote {RESULTS_PATH}')


if __name__ == '__main__':
    app = create_app()
    with app.app_context():
        run()
