"""
Role Authority V1 — deterministic starter / reliever / ambiguous / unknown.

This service answers a single foundational question for bullpen-specific
surfaces: *is this pitcher a bullpen arm, a starter, or can we not say?*

It replaces innings-pitched guessing with the authoritative MLB signal
``gamesStarted`` (captured per appearance on ``GameLog.games_started``), using the
authority hierarchy from the Role Authority V1 design:

    primary    : recency-weighted gamesStarted pattern (starts / known appearances)
    secondary  : save/hold relief confirmation
    supporting : innings length — ONLY as an opener tie-breaker, never primary

It is deterministic, explainable, and confidence-bearing. It never ranks,
selects, predicts, or uses machine learning. Two distinct uncertainty states are
preserved and never collapsed:

    Ambiguous : conflicting evidence exists (swingman, opener, mid-conversion)
    Unknown   : evidence is absent (no start data, no usable logs)

The output is intentionally shaped like ``bullpen_eligibility`` output (an
``eligible`` boolean plus explanation fields) so it is a drop-in for the shared
bullpen population helper, with added ``role`` / ``role_confidence`` fields.
"""

import os

from services.availability_reference_date import product_current_date


# ── Role categories ─────────────────────────────────────────────────────────
ROLE_STARTER = 'Starter'
ROLE_RELIEVER = 'Reliever'
ROLE_AMBIGUOUS = 'Ambiguous'
ROLE_UNKNOWN = 'Unknown'

# ── Confidence levels ───────────────────────────────────────────────────────
CONF_HIGH = 'high'
CONF_MEDIUM = 'medium'
CONF_LOW = 'low'
CONF_NONE = 'none'

# ── Eligibility status codes (mirror the bullpen_eligibility contract) ───────
STATUS_ROLE_RELIEVER = 'role_reliever'
STATUS_ROLE_STARTER = 'role_starter'
STATUS_ROLE_AMBIGUOUS = 'role_ambiguous'
STATUS_ROLE_UNKNOWN = 'role_unknown'

# ── Calibration defaults (tunable; deterministic) ───────────────────────────
STARTER_SHARE = 0.80          # known-start share at/above → Starter
RELIEVER_SHARE = 0.20         # known-start share at/below → Reliever
OPENER_MAX_AVG_START_IP = 2.0  # "starts" this short read as opener, not starter
HIGH_CONFIDENCE_EVIDENCE = 5   # known-start appearances at/above → High eligible
MIN_BINARY_EVIDENCE = 2        # below this, confident binary is capped to Low

AMBIGUOUS_LIMITATION = (
    'Swing/ambiguous role — shown on the bullpen surface with a caveat because '
    'this pitcher both starts and relieves.'
)
UNKNOWN_LIMITATION = (
    'Role not yet established from start data; withheld from default bullpen counts.'
)


def role_authority_enabled():
    """
    Whether role authority drives the live bullpen population.

    Controlled by the ROLE_AUTHORITY_ENABLED environment flag. It defaults to
    OFF so merging this code never silently changes production: the authoritative
    gamesStarted signal must first be captured by sync and backfilled, and the
    read-only diagnostic reviewed, before an operator flips the flag on. Until
    then the legacy innings heuristic remains the live behavior. The role service
    and diagnostic are fully available regardless of the flag.
    """
    raw = os.environ.get('ROLE_AUTHORITY_ENABLED', 'false')
    return str(raw).strip().lower() in ('1', 'true', 'yes', 'on')


def _games_started(log):
    value = getattr(log, 'games_started', None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _innings(log):
    value = getattr(log, 'innings_pitched', None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _has_relief_context(logs):
    return any(
        bool(getattr(log, 'save', False))
        or bool(getattr(log, 'hold', False))
        or bool(getattr(log, 'save_situation', False))
        for log in logs
    )


def _result(role, confidence, status, eligible, reason, evidence, limitations=None):
    return {
        'eligible': eligible,
        'status': status,
        'confidence': confidence,
        'reason': reason,
        'evidence': list(evidence or []),
        'limitations': list(limitations or []),
        'role': role,
        'role_confidence': confidence,
        'authority': 'games_started',
    }


def classify_role(pitcher, logs, reference_date=None):
    """
    Classify a pitcher's role from recent game logs.

    Args:
        pitcher: a Pitcher-like object (unused fields tolerated).
        logs: recent GameLog-like rows (the caller controls the window).
        reference_date: product current date (default).

    Returns:
        An eligibility-shaped dict that also carries ``role`` and
        ``role_confidence``. Deterministic for identical inputs.
    """
    _ = reference_date or product_current_date()
    logs = list(logs or [])
    appearances = len(logs)

    # No usable evidence at all → Unknown (evidence absent, not conflicting).
    if appearances == 0:
        return _result(
            ROLE_UNKNOWN, CONF_NONE, STATUS_ROLE_UNKNOWN, False,
            'No recent appearances on record to establish a role.',
            ['0 recent appearances.'],
            limitations=[UNKNOWN_LIMITATION],
        )

    start_flags = [_games_started(log) for log in logs]
    covered = [flag for flag in start_flags if flag is not None]
    coverage = len(covered)
    starts = sum(1 for flag in covered if flag and flag > 0)
    relief_context = _has_relief_context(logs)

    start_ips = [
        ip for log, flag in zip(logs, start_flags)
        if flag and flag > 0 and (ip := _innings(log)) is not None
    ]
    avg_start_ip = (sum(start_ips) / len(start_ips)) if start_ips else None

    evidence = [f'{appearances} recent appearance(s).']

    # Start signal absent → cannot assert a start-based role.
    if coverage == 0:
        if relief_context:
            return _result(
                ROLE_RELIEVER, CONF_LOW, STATUS_ROLE_RELIEVER, True,
                'Relief usage (save/hold) is present but start data is unavailable; '
                'treated as a reliever.',
                evidence + ['No known start flags; save/hold relief context present.'],
            )
        return _result(
            ROLE_UNKNOWN, CONF_NONE, STATUS_ROLE_UNKNOWN, False,
            'No start data is available to establish a role.',
            evidence + ['No known start flags on recent appearances.'],
            limitations=[UNKNOWN_LIMITATION],
        )

    start_share = starts / coverage
    evidence.append(f'{starts} of {coverage} appearances with known start data were starts.')
    if relief_context:
        evidence.append('Save/hold relief context present.')

    decisive = start_share >= STARTER_SHARE or start_share <= RELIEVER_SHARE
    if coverage >= HIGH_CONFIDENCE_EVIDENCE and decisive:
        binary_conf = CONF_HIGH
    elif coverage >= MIN_BINARY_EVIDENCE:
        binary_conf = CONF_MEDIUM
    else:
        binary_conf = CONF_LOW

    # Starter — high known-start share.
    if start_share >= STARTER_SHARE:
        # Opener tie-breaker: "starts" this short are opener usage, not rotation.
        if avg_start_ip is not None and avg_start_ip <= OPENER_MAX_AVG_START_IP:
            evidence.append(f'Average start length {avg_start_ip:.1f} IP suggests an opener role.')
            return _result(
                ROLE_AMBIGUOUS, CONF_LOW if coverage < MIN_BINARY_EVIDENCE else CONF_MEDIUM,
                STATUS_ROLE_AMBIGUOUS, True,
                'Credited starts are very short, consistent with an opener role.',
                evidence,
                limitations=[AMBIGUOUS_LIMITATION],
            )
        return _result(
            ROLE_STARTER, binary_conf, STATUS_ROLE_STARTER, False,
            f'{starts} of {coverage} recent appearances were starts.',
            evidence,
        )

    # Reliever — very low known-start share.
    if start_share <= RELIEVER_SHARE:
        conf = binary_conf
        if relief_context and conf == CONF_MEDIUM:
            conf = CONF_HIGH
        return _result(
            ROLE_RELIEVER, conf, STATUS_ROLE_RELIEVER, True,
            'Recent usage is primarily relief; few or no starts.',
            evidence,
        )

    # Ambiguous — genuinely mixed start/relief usage (swingman).
    if coverage >= HIGH_CONFIDENCE_EVIDENCE:
        conf = CONF_HIGH
    elif coverage >= 3:
        conf = CONF_MEDIUM
    else:
        conf = CONF_LOW
    return _result(
        ROLE_AMBIGUOUS, conf, STATUS_ROLE_AMBIGUOUS, True,
        f'Mixed starting and relief usage ({starts} of {coverage} appearances were starts).',
        evidence,
        limitations=[AMBIGUOUS_LIMITATION],
    )
