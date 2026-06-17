"""Bullpen stress presentation mapping over existing team context.

This module does not classify bullpen health. It only turns the existing
``build_team_context`` output into user-facing stress copy and stable reason
codes for rendering.
"""


STATE_META = {
    'manageable': {
        'label': 'Manageable',
        'summary': 'Overall bullpen availability is manageable.',
        'reason_code': 'bullpen_shape_manageable',
        'tone': 'manageable',
    },
    'monitoring': {
        'label': 'Monitoring',
        'summary': 'Overall bullpen availability needs monitoring.',
        'reason_code': 'monitor_group_pressure',
        'tone': 'monitoring',
    },
    'elevated': {
        'label': 'Elevated',
        'summary': 'Overall bullpen availability is tighter than usual.',
        'reason_code': 'workload_pressure_elevated',
        'tone': 'elevated',
    },
    'constrained': {
        'label': 'Constrained',
        'summary': 'Overall bullpen availability is constrained.',
        'reason_code': 'bullpen_options_constrained',
        'tone': 'constrained',
    },
    'no_data': {
        'label': 'No Read',
        'summary': 'Not enough current bullpen data to assess overall availability.',
        'reason_code': 'no_current_bullpen_data',
        'tone': 'muted',
    },
}

FRESHNESS_LIMITED_SUMMARY = 'Overall availability read is limited by data freshness.'
METHODOLOGY_CODE = 'workload_based_availability_context'
FRESHNESS_LIMITED_CODE = 'freshness_limited'


def _as_list(value):
    return list(value) if isinstance(value, (list, tuple)) else []


def _is_stale_context(team_context):
    confidence = (team_context or {}).get('confidence')
    if confidence == 'low':
        return True

    text = ' '.join(
        str(item).lower()
        for item in (
            _as_list((team_context or {}).get('limitations'))
            + _as_list(((team_context or {}).get('health') or {}).get('reasons'))
        )
    )
    return 'freshness' in text or 'outside the active freshness window' in text


def build_bullpen_stress(team_context):
    """Map existing team context into the MVP bullpen stress presentation block."""
    context = team_context or {}
    health = context.get('health') or {}
    state = health.get('state') or 'no_data'
    meta = STATE_META.get(state, STATE_META['no_data'])
    confidence = context.get('confidence') or 'none'
    reasons = _as_list(health.get('reasons'))
    limitations = _as_list(context.get('limitations'))
    is_stale = _is_stale_context(context)
    is_no_read = state == 'no_data' or confidence in ('none', None)

    label = meta['label']
    summary = meta['summary']
    tone = meta['tone']
    reason_codes = [meta['reason_code'], METHODOLOGY_CODE]

    if is_stale and state != 'no_data':
        label = 'No Read'
        summary = FRESHNESS_LIMITED_SUMMARY
        tone = 'muted'
        reason_codes.append(FRESHNESS_LIMITED_CODE)

    if is_no_read and state == 'no_data':
        tone = 'muted'

    return {
        'state': state,
        'label': label,
        'summary': summary,
        'reasons': reasons,
        'reason_codes': reason_codes,
        'confidence': confidence,
        'is_stale': bool(is_stale),
        'limitations': limitations,
        'tone': tone,
        'source': 'team_context.health',
    }
