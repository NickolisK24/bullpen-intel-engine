"""
Pitcher Usage Role Separation V1 — descriptive observed-usage classification.

Given a pitcher's recent game logs, this assigns a deterministic *observed usage
role* (a description of how the pitcher has recently been used) with confidence,
a short reason, evidence, and limitations.

It is descriptive, never advisory. It does NOT recommend, rank, select, or
predict usage; it does not tell anyone who to pitch or where. Role is inferred
only from data in this repo (innings, appearances, recency, and the save/hold/
save-situation/leverage fields when present) — never from reputation or names.

Innings handling: ``innings_pitched`` is treated as a decimal innings count
(1.0 = one inning, 2.0 = two). MLB box-score notation (.1 = ⅓, .2 = ⅔) is a
close approximation under this reading and only ever slightly understates
fractional innings, which keeps the multi-inning rules conservative.
"""

from datetime import date, timedelta

from services.availability import ACTIVE_WINDOW_DAYS


# Recent window used to read usage. Wider than the availability window so role
# has enough appearances to describe a pattern.
ROLE_WINDOW_DAYS = 21

MIN_ROLE_APPEARANCES = 2        # fewer than this → Low Recent Usage / Unclear
SMALL_SAMPLE_APPEARANCES = 3    # fewer than this → confidence capped at medium

ABOVE_ONE_IP = 1.0              # an outing "above 1.0 IP" (evidence)
MULTI_INNING_IP = 1.5           # an outing that counts as multi-inning
LONG_AVG_IP = 1.5               # average recent IP at/above → multi-inning pattern

HIGH_LEVERAGE = 1.5             # avg leverage index at/above → high-leverage
ELEVATED_LEVERAGE = 1.0         # avg leverage index at/above → setup-ish

ROLE_LATE = 'late_high_leverage'
ROLE_SETUP = 'setup_bridge'
ROLE_MIDDLE = 'middle_relief'
ROLE_LONG = 'long_multi_inning'
ROLE_LOW = 'low_unclear'
ROLE_INSUFFICIENT = 'insufficient_data'

# Canonical display order for role summaries.
ROLE_KEYS = [
    ROLE_LATE,
    ROLE_SETUP,
    ROLE_MIDDLE,
    ROLE_LONG,
    ROLE_LOW,
    ROLE_INSUFFICIENT,
]

ROLE_LABELS = {
    ROLE_LATE: 'Late-Inning / High-Leverage Pattern',
    ROLE_SETUP: 'Setup / Bridge Pattern',
    ROLE_MIDDLE: 'Middle Relief Pattern',
    ROLE_LONG: 'Long Relief / Multi-Inning Pattern',
    ROLE_LOW: 'Low Recent Usage / Unclear Pattern',
    ROLE_INSUFFICIENT: 'Insufficient Data',
}

ROLE_SHORT_REASONS = {
    ROLE_LATE: 'Recent usage shows late-inning, high-leverage outings.',
    ROLE_SETUP: 'Recent usage shows setup or bridge outings.',
    ROLE_MIDDLE: 'Recent usage shows regular, shorter outings.',
    ROLE_LONG: 'Recent outings show repeated multi-inning workload.',
    ROLE_LOW: 'Too few recent appearances to establish a usage pattern.',
    ROLE_INSUFFICIENT: 'Not enough recent usage data to classify a role.',
}

# Descriptive caveats that always apply — this is observed usage, not intent.
BASE_LIMITATIONS = [
    'Role is inferred from recent workload patterns only.',
    'Does not include manager intent.',
    'Does not include matchup context.',
]

_CONFIDENCE_LEVELS = ['none', 'low', 'medium', 'high']


def _cap(level, ceiling):
    """Lower a confidence level to at most ``ceiling``."""
    return _CONFIDENCE_LEVELS[min(
        _CONFIDENCE_LEVELS.index(level),
        _CONFIDENCE_LEVELS.index(ceiling),
    )]


def _count(value):
    return f'{value} appearance' if value == 1 else f'{value} appearances'


def _derive(logs, reference_date):
    valid = [log for log in (logs or []) if getattr(log, 'game_date', None) is not None]
    appearances = len(valid)

    ip_values = [getattr(log, 'innings_pitched', None) for log in valid]
    known_ip = [v for v in ip_values if v is not None]
    incomplete = (
        any(v is None for v in ip_values)
        or appearances != len(logs or [])
    )

    total_ip = sum(known_ip)
    avg_ip = (total_ip / len(known_ip)) if known_ip else None
    above_one = sum(1 for v in known_ip if v > ABOVE_ONE_IP)
    multi_inning = sum(1 for v in known_ip if v >= MULTI_INNING_IP)

    saves = sum(1 for log in valid if getattr(log, 'save', False))
    holds = sum(1 for log in valid if getattr(log, 'hold', False))
    save_situations = sum(1 for log in valid if getattr(log, 'save_situation', False))

    li_values = [getattr(log, 'leverage_index', None) for log in valid]
    known_li = [v for v in li_values if v is not None]
    li_present = bool(known_li)
    avg_li = (sum(known_li) / len(known_li)) if known_li else None

    latest = max((log.game_date for log in valid), default=None)
    stale = latest is not None and latest < reference_date - timedelta(days=ACTIVE_WINDOW_DAYS)
    has_role_fields = li_present or saves > 0 or holds > 0 or save_situations > 0

    return {
        'appearances': appearances,
        'avg_ip': avg_ip,
        'above_one': above_one,
        'multi_inning': multi_inning,
        'saves': saves,
        'holds': holds,
        'save_situations': save_situations,
        'li_present': li_present,
        'avg_li': avg_li,
        'incomplete': incomplete,
        'stale': stale,
        'has_role_fields': has_role_fields,
        'latest': latest,
    }


def _evidence(d):
    evidence = [_count(d['appearances']) + ' in the recent window']
    if d['avg_ip'] is not None:
        evidence.append(f"Average recent IP: {d['avg_ip']:.1f}")
    if d['above_one']:
        evidence.append(f"{d['above_one']} of {d['appearances']} outings above 1.0 IP")
    if d['saves']:
        evidence.append(f"{d['saves']} save situation finish(es) recorded")
    if d['holds']:
        evidence.append(f"{d['holds']} hold(s) recorded")
    if d['save_situations'] and not d['saves']:
        evidence.append(f"{d['save_situations']} save-situation appearance(s)")
    if d['li_present']:
        evidence.append(f"Average leverage index: {d['avg_li']:.2f}")
    return evidence


def _result(role_key, confidence, evidence, limitations):
    return {
        'role_key': role_key,
        'role': ROLE_LABELS[role_key],
        'confidence': confidence,
        'short_reason': ROLE_SHORT_REASONS[role_key],
        'evidence': evidence,
        'limitations': limitations,
    }


def classify_usage_role(logs, reference_date=None):
    """
    Classify observed usage role from recent game logs.

    Args:
        logs: recent GameLog-like objects (caller windows them). May be empty.
        reference_date: date the window is anchored on. Defaults to today.

    Returns:
        Dict with role_key, role label, confidence, short_reason, evidence,
        and limitations. Safe to embed in an API response.
    """
    ref = reference_date or date.today()
    d = _derive(logs, ref)
    evidence = _evidence(d)

    # 1. Insufficient data — nothing usable to read.
    if d['appearances'] == 0 or d['avg_ip'] is None:
        return _result(
            ROLE_INSUFFICIENT,
            'none',
            evidence,
            BASE_LIMITATIONS + ['No usable recent appearances with innings data.'],
        )

    # 2. Low recent usage / unclear — too few appearances to describe a pattern.
    if d['appearances'] < MIN_ROLE_APPEARANCES:
        limitations = list(BASE_LIMITATIONS)
        limitations.append('Based on too few recent appearances to establish a pattern.')
        if d['stale']:
            limitations.append('Latest usage data is outside the active freshness window.')
        return _result(ROLE_LOW, 'low', evidence, limitations)

    # 3-6. Determine pattern in a fixed priority order. Save/hold/leverage
    # evidence (a defined late/setup usage) outranks innings length; the
    # multi-inning rule then catches long relievers who lack that evidence.
    is_late = d['saves'] >= 1 or (d['li_present'] and d['avg_li'] >= HIGH_LEVERAGE)
    is_setup = d['holds'] >= 1 or (d['li_present'] and d['avg_li'] >= ELEVATED_LEVERAGE)
    is_long = (
        d['avg_ip'] >= LONG_AVG_IP
        or (d['multi_inning'] >= 2 and d['multi_inning'] / d['appearances'] >= 0.5)
    )

    if is_late:
        role_key = ROLE_LATE
    elif is_setup:
        role_key = ROLE_SETUP
    elif is_long:
        role_key = ROLE_LONG
    else:
        role_key = ROLE_MIDDLE

    # Confidence: start high, degrade for small sample / incomplete / stale /
    # missing supporting fields.
    confidence = 'high'
    limitations = list(BASE_LIMITATIONS)

    if d['appearances'] < SMALL_SAMPLE_APPEARANCES:
        confidence = _cap(confidence, 'medium')
        limitations.append('Based on a small number of recent appearances.')
    if d['incomplete']:
        confidence = _cap(confidence, 'medium')
        limitations.append('Some recent outings were missing innings data.')
    if d['stale']:
        confidence = _cap(confidence, 'low')
        limitations.append('Latest usage data is outside the active freshness window.')
    if role_key in (ROLE_LATE, ROLE_SETUP) and not d['li_present']:
        # Late/setup was read from save/hold flags only — no leverage context.
        confidence = _cap(confidence, 'medium')
        limitations.append('Leverage-index data was not available; role uses save/hold flags only.')
    if not d['has_role_fields']:
        limitations.append(
            'Save, hold, and leverage data were not available; role is based on '
            'innings and appearance counts only.'
        )

    return _result(role_key, confidence, evidence, limitations)
