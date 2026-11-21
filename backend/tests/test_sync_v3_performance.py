from datetime import date, timedelta

from sync_v3.performance import final_performance_counts, performance_line, performance_windows


THROUGH = date(2024, 8, 7)
STATS = {'hits': 1, 'strikeOuts': 2, 'baseOnBalls': 0, 'battersFaced': 4, 'earnedRuns': 0, 'homeRuns': 0,
         'inheritedRunners': 1, 'inheritedRunnersScored': 0}
FINAL = {'outs_recorded': 3, 'home_runs_allowed': 0, 'earned_runs': 0, 'hits_allowed': 1, 'walks': 0}


def test_missing_earlier_final_withholds_season_but_complete_recent_window_qualifies():
    verified = performance_line(THROUGH - timedelta(days=29), final_performance_counts(FINAL, STATS), STATS)
    missing = performance_line(THROUGH - timedelta(days=30), {}, STATS)
    windows = performance_windows(THROUGH, [missing, verified])
    assert windows['season']['outings'] == 2 and windows['recent']['outings'] == 1
    for metric in windows['season']['metrics'].values():
        assert metric['covered'] == 1 and metric['value'] is None and metric['denominator'] is None
    recent = windows['recent']['metrics']
    assert {k: m['value'] for k, m in recent.items()} == {
        'era': '0.00', 'whip': '1.00', 'k_bb_percent': '50.00', 'inherited': '0 of 1', 'hr9': '0.00'}


def test_conflicting_missing_and_impossible_measurements_are_withheld_independently():
    counts = final_performance_counts(dict(FINAL, home_runs_allowed=None), dict(STATS, inheritedRunnersScored=2))
    line = performance_line(THROUGH, counts, dict(STATS, strikeOuts=3, inheritedRunnersScored=2))
    metrics = performance_windows(THROUGH, [line])['recent']['metrics']
    assert metrics['whip']['value'] == '1.00'
    for k in ('hr9', 'inherited', 'k_bb_percent'):
        assert metrics[k]['covered'] == 0 and metrics[k]['value'] is None
    counts = final_performance_counts(FINAL, dict(STATS, battersFaced=1))
    metrics = performance_windows(THROUGH, [performance_line(THROUGH, counts, {})])['recent']['metrics']
    assert metrics['k_bb_percent']['value'] is None
