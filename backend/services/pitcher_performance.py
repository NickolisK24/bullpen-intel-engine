"""Individual descriptive rates for explicitly bounded, recorded relief samples."""
from collections import Counter
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from models.game_log import GameLog
from services.team_performance_evidence import DOMAINS, compare, completed_game_receipts, count


def _rate(numerator, denominator, multiplier=1):
    if not denominator:
        return None
    return str((Decimal(numerator * multiplier) / denominator).quantize(
        Decimal('0.01'), rounding=ROUND_HALF_UP))


def _window(start, through, lines):
    selected = [(row, official) for row, official in lines if start <= row.game_date <= through]
    totals = Counter()
    covered = Counter()
    for row, official in selected:
        outs = count(row.innings_pitched_outs)
        if outs is not None and count(row.hits_allowed) is not None and count(row.walks) is not None:
            totals['baserunners'] += row.hits_allowed + row.walks
            covered['whip'] += 1
        if outs is not None:
            totals['outs'] += outs
        earned = official.get('earned_runs')
        if outs is not None and earned is not None:
            totals['earned_runs'] += earned
            covered['era'] += 1
        for key, fields in (
            ('hr9', ('home_runs_allowed',)),
            ('k_bb_percent', ('strikeouts', 'walks', 'batters_faced')),
            ('inherited', ('inherited_runners', 'inherited_runners_scored')),
        ):
            if all(f in official for f in fields) and (key != 'hr9' or outs is not None):
                covered[key] += 1
                totals.update({f: official[f] for f in fields})

    appearances = len(selected)
    values = {
        'era': _rate(totals['earned_runs'], totals['outs'], 27),
        'whip': _rate(totals['baserunners'], totals['outs'], 3),
        'hr9': _rate(totals['home_runs_allowed'], totals['outs'], 27),
        'k_bb_percent': _rate(totals['strikeouts'] - totals['walks'], totals['batters_faced'], 100),
        'inherited': f"{totals['inherited_runners_scored']} of {totals['inherited_runners']}",
    }
    denominators = {
        'era': (totals['outs'], 'outs'), 'whip': (totals['outs'], 'outs'),
        'hr9': (totals['outs'], 'outs'), 'k_bb_percent': (totals['batters_faced'], 'batters faced'),
        'inherited': (totals['inherited_runners'], 'inherited runners'),
    }
    metrics = {}
    for key, value in values.items():
        complete = bool(appearances and covered[key] == appearances)
        denominator, unit = denominators[key]
        metrics[key] = {
            'covered': covered[key], 'value': value if complete else None,
            'denominator': denominator if complete else None, 'unit': unit,
        }
    return {'start': start.isoformat(), 'through': through.isoformat(), 'outings': appearances,
            'metrics': metrics}


def pitcher_performance(pitcher, through):
    if through is None:
        return None
    start = through.replace(month=1, day=1)
    rows = GameLog.query.filter(GameLog.pitcher_id == pitcher.id, GameLog.game_type == 'R',
                                GameLog.games_started == 0, GameLog.game_date.between(start, through)).all()
    receipts = completed_game_receipts(rows)
    lines = []
    for row in rows:
        official = {}
        receipt = receipts.get(row.mlb_game_pk)
        if receipt and row.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED:
            checked = compare([row], {pitcher.id: pitcher.mlb_id}, {row.mlb_game_pk: receipt}, row.appearance_team_id)
            if checked.lines:
                for domain, fields in DOMAINS.items():
                    if checked.verified[domain]:
                        official.update({f: checked.totals[f] for f in fields})
                earned = count(receipt['lines'][str(pitcher.mlb_id)].get('earned_runs'))
                if earned is not None and earned == row.earned_runs:
                    official['earned_runs'] = earned
        lines.append((row, official))
    return {'method_version': 'recorded_pitcher_relief_v1', 'season': _window(start, through, lines),
            'recent': _window(max(start, through - timedelta(days=29)), through, lines)}
