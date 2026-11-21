"""Individual descriptive performance from qualified final lines and a reconciled relief sample."""

from datetime import timedelta
from types import SimpleNamespace

from services.pitcher_performance import _window
from services.team_performance_evidence import DOMAINS, FIELDS, consistent_domain_counts, count


SOURCE_FIELDS = {**FIELDS, 'earned_runs': 'earnedRuns', 'hits_allowed': 'hits'}


def final_performance_counts(line, official):
    """Only carry counts explicitly supported by the player's official pitching line."""
    result = {'outs': count(line['outs_recorded'])}
    for name, key in SOURCE_FIELDS.items():
        recorded = count(official.get(key))
        canonical = line.get(name)
        if name in ('home_runs_allowed', 'earned_runs', 'hits_allowed', 'walks') and count(canonical) is None:
            recorded = None
        elif canonical is not None and count(canonical) != recorded:
            recorded = None
        result[name] = recorded
    return result


def performance_line(day, final, log):
    """Preserve the expected outing even when its final or one measurement is missing."""
    agreed, conflicts = {}, {}
    for name, key in SOURCE_FIELDS.items():
        value = final.get(name)
        if value is not None and (log.get(key) is None or count(log[key]) == value):
            agreed[name] = value
        elif value is not None and count(log.get(key)) is not None:
            conflicts[name] = {'boxscore': value, 'game_log': log[key]}
    row = SimpleNamespace(game_date=day, source_conflicts=conflicts, innings_pitched_outs=final.get('outs'),
                          walks=agreed.get('walks'), hits_allowed=agreed.get('hits_allowed'))
    official = {}
    if 'earned_runs' in agreed:
        official['earned_runs'] = agreed['earned_runs']
    for domain, fields in DOMAINS.items():
        if not consistent_domain_counts(domain, agreed):
            continue
        official.update({f: agreed[f] for f in fields})
    return row, official


def performance_windows(through, lines):
    start = through.replace(month=1, day=1)
    return {'method_version': 'recorded_pitcher_relief_v1',
            'recent': _window(max(start, through - timedelta(days=29)), through, lines),
            'season': _window(start, through, lines)}
