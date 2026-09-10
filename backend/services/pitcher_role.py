"""
Pitcher Usage Role Separation V1 — descriptive observed-usage classification.

Given a pitcher's recent game logs, this assigns a deterministic *observed usage
role* (a description of how the pitcher has recently been used) with confidence,
a short reason, evidence, and limitations.

It is descriptive, never advisory. It does NOT recommend, rank, select, or
predict usage; it does not tell anyone who to pitch or where. Role is inferred
only from data in this repo (innings, appearances, recency, and the save/hold/
save-situation/leverage fields when present) — never from reputation or names.

Innings handling: ``innings_pitched_outs`` is the lossless source of truth when
present. Decimal ``innings_pitched`` values are display-compatible derived
values and are only a fallback for older in-memory objects.
"""

from datetime import timedelta

from services.availability import ACTIVE_WINDOW_DAYS
from services.availability_reference_date import product_current_date
from utils.innings import log_innings_decimal


# Stability-leaning role window. This is reasoned judgment, not a validated
# threshold: long enough to preserve an established usage role through a quiet
# stretch, still time-bounded so stale history cannot define current trust.
ROLE_WINDOW_DAYS = 45

# Recent-confirmation window. The 45-day window provides stability and
# supporting evidence; a categorical role event (save/hold) or leverage signal
# must be confirmed inside this window to define the CURRENT role, so old role
# events cannot pin the role until they age out of the full window.
ROLE_SIGNAL_RECENCY_DAYS = 21

# Minimum categorical (save/hold) signal strength. A save- or hold-based role
# qualifies only with a sustained, recently confirmed pattern — one isolated
# event never defines the role. Shares are computed over qualifying relief
# appearances. These are deterministic product rules, not validated
# predictions of manager intent.
MIN_CATEGORICAL_ROLE_EVENTS = 2
MIN_CATEGORICAL_ROLE_SHARE = 0.15
MIN_RECENT_CATEGORICAL_ROLE_EVENTS = 1

# Leverage index defines a concrete role only with enough recent coverage —
# one isolated leverage value cannot establish a late/setup role.
MIN_RECENT_LEVERAGE_APPEARANCES = 3

MIN_ROLE_APPEARANCES = 2        # fewer than this → Low Recent Usage / Unclear
SMALL_SAMPLE_APPEARANCES = 3    # fewer than this → confidence capped at medium

ABOVE_ONE_IP = 1.0              # an outing "above 1.0 IP" (evidence)
MULTI_INNING_IP = 1.5           # an outing that counts as multi-inning
LONG_AVG_IP = 1.5               # average recent IP at/above → multi-inning pattern

HIGH_LEVERAGE = 1.5             # recent avg leverage index at/above → high-leverage
ELEVATED_LEVERAGE = 1.0         # recent avg leverage index at/above → setup-ish

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
    recent_cutoff = reference_date - timedelta(days=ROLE_SIGNAL_RECENCY_DAYS)

    ip_values = [log_innings_decimal(log) for log in valid]
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
    recent_saves = sum(
        1 for log in valid
        if getattr(log, 'save', False) and log.game_date >= recent_cutoff
    )
    recent_holds = sum(
        1 for log in valid
        if getattr(log, 'hold', False) and log.game_date >= recent_cutoff
    )
    save_share = (saves / appearances) if appearances else 0.0
    hold_share = (holds / appearances) if appearances else 0.0

    li_values = [getattr(log, 'leverage_index', None) for log in valid]
    known_li = [v for v in li_values if v is not None]
    li_present = bool(known_li)
    avg_li = (sum(known_li) / len(known_li)) if known_li else None
    recent_li = [
        value for log in valid
        if (value := getattr(log, 'leverage_index', None)) is not None
        and log.game_date >= recent_cutoff
    ]
    recent_li_count = len(recent_li)
    recent_avg_li = (sum(recent_li) / recent_li_count) if recent_li else None

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
        'recent_saves': recent_saves,
        'recent_holds': recent_holds,
        'save_share': save_share,
        'hold_share': hold_share,
        'li_present': li_present,
        'avg_li': avg_li,
        'recent_li_count': recent_li_count,
        'recent_avg_li': recent_avg_li,
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
        evidence.append(f"Save share: {d['save_share']:.0%} of qualifying relief appearances")
        if d['recent_saves']:
            evidence.append(f'At least one save occurred in the latest {ROLE_SIGNAL_RECENCY_DAYS} days')
        else:
            evidence.append(
                f'Older save evidence remains in the {ROLE_WINDOW_DAYS}-day window but is '
                f'outside the {ROLE_SIGNAL_RECENCY_DAYS}-day confirmation window'
            )
    if d['holds']:
        evidence.append(f"{d['holds']} hold(s) recorded")
        evidence.append(f"Hold share: {d['hold_share']:.0%} of qualifying relief appearances")
        if d['recent_holds']:
            evidence.append(f'At least one hold occurred in the latest {ROLE_SIGNAL_RECENCY_DAYS} days')
        else:
            evidence.append(
                f'Older hold evidence remains in the {ROLE_WINDOW_DAYS}-day window but is '
                f'outside the {ROLE_SIGNAL_RECENCY_DAYS}-day confirmation window'
            )
    if d['save_situations'] and not d['saves']:
        evidence.append(f"{d['save_situations']} save-situation appearance(s)")
    if d['li_present']:
        evidence.append(f"Average leverage index: {d['avg_li']:.2f}")
    if d['recent_li_count']:
        evidence.append(
            f"Recent leverage index was available for {d['recent_li_count']} appearance(s)"
        )
        evidence.append(f"Average recent leverage index: {d['recent_avg_li']:.2f}")
    return evidence


def _result(role_key, confidence, evidence, limitations, short_reason=None):
    return {
        'role_key': role_key,
        'role': ROLE_LABELS[role_key],
        'confidence': confidence,
        'short_reason': short_reason or ROLE_SHORT_REASONS[role_key],
        'evidence': evidence,
        'limitations': limitations,
    }


def _categorical_pattern(events, share, recent_events):
    """Whether save/hold events form a sustained, recently confirmed pattern."""
    return (
        events >= MIN_CATEGORICAL_ROLE_EVENTS
        and share >= MIN_CATEGORICAL_ROLE_SHARE
        and recent_events >= MIN_RECENT_CATEGORICAL_ROLE_EVENTS
    )


def _categorical_role(d):
    """Resolve the categorical (save/hold) role candidate.

    Save and hold patterns are COMPARED — the larger sustained pattern wins,
    with recent event counts as the tie-breaker. Returns (role_key, tied):
    role_key is None when categorical evidence establishes no late/setup role;
    tied is True when both patterns qualify and remain even after tie-breaks.
    """
    late_ok = _categorical_pattern(d['saves'], d['save_share'], d['recent_saves'])
    setup_ok = _categorical_pattern(d['holds'], d['hold_share'], d['recent_holds'])

    if late_ok and setup_ok:
        if d['saves'] > d['holds']:
            return ROLE_LATE, False
        if d['holds'] > d['saves']:
            return ROLE_SETUP, False
        if d['recent_saves'] > d['recent_holds']:
            return ROLE_LATE, False
        if d['recent_holds'] > d['recent_saves']:
            return ROLE_SETUP, False
        return None, True
    if late_ok:
        return ROLE_LATE, False
    if setup_ok:
        return ROLE_SETUP, False
    return None, False


def _leverage_role(d):
    """Resolve the recent-leverage role candidate.

    Leverage defines a concrete role only with sufficient recent coverage;
    a recent average below the setup threshold establishes nothing.
    """
    if d['recent_li_count'] < MIN_RECENT_LEVERAGE_APPEARANCES:
        return None
    if d['recent_avg_li'] >= HIGH_LEVERAGE:
        return ROLE_LATE
    if d['recent_avg_li'] >= ELEVATED_LEVERAGE:
        return ROLE_SETUP
    return None


def classify_usage_role(logs, reference_date=None):
    """
    Classify observed usage role from recent game logs.

    Args:
        logs: recent GameLog-like objects (caller windows them). May be empty.
        reference_date: date the window is anchored on. Defaults to the product
            calendar date.

    Returns:
        Dict with role_key, role label, confidence, short_reason, evidence,
        and limitations. Safe to embed in an API response.
    """
    ref = reference_date or product_current_date()
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

    # 3. Sustained categorical (save/hold) and recent-leverage candidates are
    # derived independently, then reconciled. A save- or hold-based role needs
    # a sustained, recently confirmed pattern — one isolated event (or one
    # save-situation appearance without a save) never defines the role.
    categorical_role, categorical_tied = _categorical_role(d)
    leverage_role = _leverage_role(d)

    # Threshold-failure disclosure: isolated events stay visible but are
    # explicitly reported as not meeting the sustained-pattern rules.
    if d['saves'] and not (categorical_role == ROLE_LATE or categorical_tied):
        evidence.append(
            f"{d['saves']} save(s) in {d['appearances']} qualifying relief appearances did "
            'not meet the sustained late-inning threshold'
        )
    if d['holds'] and not (categorical_role == ROLE_SETUP or categorical_tied):
        evidence.append(
            f"{d['holds']} hold(s) in {d['appearances']} qualifying relief appearances did not "
            'meet the sustained setup threshold'
        )

    # 4. Conflict handling fails closed. Tied sustained save/hold patterns can
    # be decided by qualifying recent leverage evidence; otherwise — and when
    # leverage and categorical evidence point to different roles — the honest
    # answer is that no single usage pattern is established.
    conflict_reason = None
    if categorical_tied:
        if leverage_role is not None:
            role_key = leverage_role
            evidence.append(
                'Save and hold usage are equally sustained; recent leverage evidence '
                'determined the role'
            )
        else:
            conflict_reason = (
                'Recent save and hold usage are equally sustained; no single usage '
                'pattern is established.'
            )
    elif (
        categorical_role is not None
        and leverage_role is not None
        and categorical_role != leverage_role
    ):
        conflict_reason = (
            'Recent leverage evidence and recorded save/hold usage point to different '
            'roles; no single usage pattern is established.'
        )

    if conflict_reason:
        limitations = list(BASE_LIMITATIONS)
        limitations.append(conflict_reason)
        if categorical_tied:
            limitations.append(
                'Save and hold patterns both met the sustained-usage rules with no '
                'decisive recent leverage evidence.'
            )
        else:
            limitations.append(
                'Recorded save/hold usage and recent leverage evidence each met their '
                'own thresholds but disagree on the role.'
            )
        if d['stale']:
            limitations.append('Latest usage data is outside the active freshness window.')
        return _result(ROLE_LOW, 'low', evidence, limitations, short_reason=conflict_reason)

    if not categorical_tied:
        # 5. Reconciled concrete role, then the innings fallbacks. A sustained
        # late/setup pattern still outranks innings length; isolated save/hold
        # evidence that failed the thresholds no longer blocks a long-relief read.
        role_key = categorical_role or leverage_role
    is_long = (
        d['avg_ip'] >= LONG_AVG_IP
        or (d['multi_inning'] >= 2 and d['multi_inning'] / d['appearances'] >= 0.5)
    )
    if role_key is None:
        role_key = ROLE_LONG if is_long else ROLE_MIDDLE

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
    if role_key in (ROLE_LATE, ROLE_SETUP) and leverage_role != role_key:
        # Late/setup rests on save/hold frequency without confirming recent
        # leverage coverage — capped at medium.
        if not d['li_present']:
            confidence = _cap(confidence, 'medium')
            limitations.append('Leverage-index data was not available; role uses save/hold flags only.')
        elif d['recent_li_count'] < MIN_RECENT_LEVERAGE_APPEARANCES:
            confidence = _cap(confidence, 'medium')
            limitations.append(
                'Recent leverage-index coverage was too limited to confirm the role; '
                'the role relies on recorded save/hold usage.'
            )
    if not d['has_role_fields']:
        limitations.append(
            'Save, hold, and leverage data were not available; role is based on '
            'innings and appearance counts only.'
        )

    return _result(role_key, confidence, evidence, limitations)
