"""Shared wording rules for Availability Engine explanations.

Reason text is product-facing decision-support copy. Keep this vocabulary
centralized so API responses, reports, and tests use the same trust language.
"""

CATEGORY_FATIGUE = 'fatigue'
CATEGORY_PITCH_COUNT = 'pitch_count'
CATEGORY_APPEARANCE_FREQUENCY = 'appearance_frequency'
CATEGORY_REST = 'rest'
CATEGORY_DATA_STATE = 'data_state'
CATEGORY_FALLBACK = 'fallback'
CATEGORY_LIMITATION = 'limitation'
CATEGORY_UNKNOWN = 'unknown'

CATEGORY_ORDER = [
    CATEGORY_PITCH_COUNT,
    CATEGORY_APPEARANCE_FREQUENCY,
    CATEGORY_REST,
    CATEGORY_FATIGUE,
    CATEGORY_DATA_STATE,
    CATEGORY_LIMITATION,
    CATEGORY_FALLBACK,
    CATEGORY_UNKNOWN,
]

BASE_LIMITATIONS = [
    'No injury data available',
    'No team-reported availability data available',
]

MISSING_WORKLOAD_REASON = 'Missing workload history or fatigue score'
INCOMPLETE_WORKLOAD_REASON = 'Incomplete workload inputs'
MISSING_WORKLOAD_LIMITATION = 'Availability confidence is low because workload inputs are missing'
INCOMPLETE_WORKLOAD_LIMITATION = 'Some game-log workload fields are incomplete'
STALE_WORKLOAD_LIMITATION = 'Stale workload data must not be treated as current availability'
WORKLOAD_FALLBACK_REASON = 'Availability restriction rule matched without a displayable workload input'


REASON_CATALOG = [
    {
        'category': CATEGORY_PITCH_COUNT,
        'rule': 'Yesterday pitch volume',
        'template': '{n} pitches yesterday',
        'example': '42 pitches yesterday',
    },
    {
        'category': CATEGORY_PITCH_COUNT,
        'rule': 'Three-day pitch volume',
        'template': '{n} pitches in 3 days',
        'example': '54 pitches in 3 days',
    },
    {
        'category': CATEGORY_PITCH_COUNT,
        'rule': 'Five-day pitch volume',
        'template': '{n} pitches in 5 days',
        'example': '75 pitches in 5 days',
    },
    {
        'category': CATEGORY_APPEARANCE_FREQUENCY,
        'rule': 'Three-day appearance compression',
        'template': '{n} appearances in 3 days',
        'example': '2 appearances in 3 days',
    },
    {
        'category': CATEGORY_APPEARANCE_FREQUENCY,
        'rule': 'Four-day appearance compression',
        'template': '3 appearances in 4 days',
        'example': '3 appearances in 4 days',
    },
    {
        'category': CATEGORY_APPEARANCE_FREQUENCY,
        'rule': 'Five-day appearance compression',
        'template': '{n} appearances in 5 days',
        'example': '4 appearances in 5 days',
    },
    {
        'category': CATEGORY_APPEARANCE_FREQUENCY,
        'rule': 'Back-to-back appearances',
        'template': 'Back-to-back appearances',
        'example': 'Back-to-back appearances',
    },
    {
        'category': CATEGORY_REST,
        'rule': 'No rest',
        'template': 'No rest since last appearance',
        'example': 'No rest since last appearance',
    },
    {
        'category': CATEGORY_REST,
        'rule': 'One rest day',
        'template': 'Only 1 day of rest',
        'example': 'Only 1 day of rest',
    },
    {
        'category': CATEGORY_FATIGUE,
        'rule': 'Fatigue score',
        'template': 'Fatigue score is {score}',
        'example': 'Fatigue score is 55.3',
    },
    {
        'category': CATEGORY_DATA_STATE,
        'rule': 'Missing workload data',
        'template': MISSING_WORKLOAD_REASON,
        'example': MISSING_WORKLOAD_REASON,
    },
    {
        'category': CATEGORY_DATA_STATE,
        'rule': 'Incomplete workload data',
        'template': INCOMPLETE_WORKLOAD_REASON,
        'example': INCOMPLETE_WORKLOAD_REASON,
    },
    {
        'category': CATEGORY_DATA_STATE,
        'rule': 'Stale workload data',
        'template': 'Latest workload data is outside the {days}-day freshness window',
        'example': 'Latest workload data is outside the 14-day freshness window',
    },
    {
        'category': CATEGORY_FALLBACK,
        'rule': 'Unmapped restriction',
        'template': WORKLOAD_FALLBACK_REASON,
        'example': WORKLOAD_FALLBACK_REASON,
    },
]


def _pluralize(count, singular, plural=None):
    return singular if count == 1 else (plural or f'{singular}s')


def _format_number(value):
    rounded = round(float(value), 1)
    return f'{rounded:.1f}'.rstrip('0').rstrip('.')


def pitch_count_reason(count, window_label):
    noun = _pluralize(count, 'pitch', 'pitches')
    if window_label == 'yesterday':
        return f'{count} {noun} yesterday'
    return f'{count} {noun} in {window_label}'


def appearance_frequency_reason(count, window_label):
    noun = _pluralize(count, 'appearance')
    return f'{count} {noun} in {window_label}'


def back_to_back_reason():
    return 'Back-to-back appearances'


def rest_reason(days):
    if days is None:
        return 'Rest days are unknown'
    if days <= 0:
        return 'No rest since last appearance'
    if days == 1:
        return 'Only 1 day of rest'
    return f'{days} days of rest'


def fatigue_score_reason(score):
    return f'Fatigue score is {_format_number(score)}'


def stale_workload_reason(active_window_days):
    return f'Latest workload data is outside the {active_window_days}-day freshness window'


def reason_catalog():
    return [dict(item) for item in REASON_CATALOG]


def categorize_reason(reason):
    text = (reason or '').lower()
    if not text:
        return CATEGORY_UNKNOWN
    if 'freshness window' in text or text.startswith('missing workload') or text.startswith('incomplete workload'):
        return CATEGORY_DATA_STATE
    if 'pitch' in text:
        return CATEGORY_PITCH_COUNT
    if 'appearance' in text or 'back-to-back' in text:
        return CATEGORY_APPEARANCE_FREQUENCY
    if 'rest' in text:
        return CATEGORY_REST
    if 'fatigue score' in text:
        return CATEGORY_FATIGUE
    if 'restriction rule' in text:
        return CATEGORY_FALLBACK
    return CATEGORY_UNKNOWN


def categorize_limitation(limitation):
    text = (limitation or '').lower()
    if not text:
        return CATEGORY_UNKNOWN
    if text in {item.lower() for item in BASE_LIMITATIONS}:
        return CATEGORY_LIMITATION
    if 'stale' in text or 'missing' in text or 'incomplete' in text:
        return CATEGORY_DATA_STATE
    return CATEGORY_LIMITATION
