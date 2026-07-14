"""Backend-authored public labels for pitcher role and workload reads."""

import re

from services.roster_authority import (
    ROSTER_STATUS_CATEGORY_ACTIVE,
    ROSTER_STATUS_CATEGORY_UNKNOWN,
    is_off_active_roster,
    roster_status_category_for_status,
)


# One canonical public role vocabulary. These labels are the authority for
# every public surface; the frontend renders them verbatim and must never
# reinterpret one role key as another baseball role.
ROLE_PUBLIC_LABELS = {
    'trust_arm': {
        'kind': 'role',
        'key': 'trust_arm',
        'label': 'Trusted Arm',
        'source': 'backend',
    },
    'bridge_arm': {
        'kind': 'role',
        'key': 'bridge_arm',
        'label': 'Setup Arm',
        'source': 'backend',
    },
    'coverage_arm': {
        'kind': 'role',
        'key': 'coverage_arm',
        'label': 'Coverage Arm',
        'source': 'backend',
    },
    'depth_arm': {
        'kind': 'role',
        'key': 'depth_arm',
        'label': 'Middle Relief Arm',
        'source': 'backend',
    },
    'limited_read': {
        'kind': 'role',
        'key': 'limited_read',
        'label': 'Limited Read',
        'source': 'backend',
    },
}

READ_PUBLIC_LABELS = {
    'clean_option': {
        'kind': 'read',
        'key': 'clean_option',
        'label': 'Rested',
        'source': 'backend',
    },
    'watch_arm': {
        'kind': 'read',
        'key': 'watch_arm',
        'label': 'Watch Arm',
        'source': 'backend',
    },
    'rest_restricted': {
        'kind': 'read',
        'key': 'rest_restricted',
        'label': 'Rest-Restricted',
        'source': 'backend',
    },
    'unavailable': {
        'kind': 'read',
        'key': 'unavailable',
        'label': 'Unavailable',
        'source': 'backend',
    },
    'limited_read': {
        'kind': 'read',
        'key': 'limited_read',
        'label': 'Limited Read',
        'source': 'backend',
    },
}

# Canonical usage-role -> public-role mapping. middle_relief is a distinct
# baseball role and must never collapse into the setup/bridge slot.
ROLE_KEY_TO_PUBLIC_KEY = {
    'late_high_leverage': 'trust_arm',
    'high_leverage': 'trust_arm',
    'closer': 'trust_arm',
    'leverage': 'trust_arm',
    'setup_bridge': 'bridge_arm',
    'setup': 'bridge_arm',
    'bridge': 'bridge_arm',
    'middle_relief': 'depth_arm',
    'middle': 'depth_arm',
    'long_multi_inning': 'coverage_arm',
    'long_relief': 'coverage_arm',
    'multi_inning': 'coverage_arm',
    'bulk': 'coverage_arm',
    'coverage': 'coverage_arm',
    'depth': 'depth_arm',
    'depth_arm': 'depth_arm',
    'lower_leverage': 'depth_arm',
    'low_leverage': 'depth_arm',
    'mop_up': 'depth_arm',
    'low_unclear': 'limited_read',
    'insufficient_data': 'limited_read',
}

# Public role composition buckets for league-wide role summaries. These are
# the final public conclusions pitcher cards present, so dashboard counts can
# never disagree with the chips (a guarded pitcher counts as limited_read).
PUBLIC_ROLE_COMPOSITION_KEYS = (
    'trust_arm',
    'bridge_arm',
    'depth_arm',
    'coverage_arm',
    'limited_read',
)

COVERAGE_ROLE_KEYS = {
    'long_multi_inning',
    'long_relief',
    'multi_inning',
    'bulk',
    'coverage',
}

FRESH_DATA_STATES = {'fresh', 'current', 'ok'}
LIMITED_DATA_STATES = {'stale', 'missing', 'incomplete', 'failed', 'historical', 'unknown'}


def _label(payload, catalog):
    key = payload.get('key', 'limited_read')
    base = dict(catalog.get(key, catalog['limited_read']))
    base.update(payload)
    return base


def _normalize_token(value):
    return ''.join(
        char.lower() if char.isalnum() else '_'
        for char in str(value or '').strip()
    ).strip('_')


def _normalize_text(*values):
    parts = []
    for value in values:
        if isinstance(value, (list, tuple)):
            parts.extend(str(item or '') for item in value)
        else:
            parts.append(str(value or ''))
    return ' '.join(parts).lower()


def _role_key(role):
    role = role or {}
    return _normalize_token(
        role.get('role_key')
        or role.get('key')
        or role.get('role_type')
    )


def _role_sample_size(role):
    role = role or {}
    for key in (
        'sample_size',
        'usage_sample_size',
        'appearance_count',
        'appearances',
        'recent_appearances',
        'recent_outings',
        'relief_appearances',
    ):
        value = role.get(key)
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str) and value.strip().isdigit():
            return int(value)
        if isinstance(value, (list, tuple)):
            return len(value)

    evidence_text = _normalize_text(role.get('evidence'), role.get('reasons'), role.get('short_reason'))
    match = re.search(r'\b(\d+)\s+(?:appearance|appearances|outing|outings)\b', evidence_text)
    if match:
        return int(match.group(1))
    return None


def _weak_role_confidence(role):
    confidence = _normalize_token(
        (role or {}).get('confidence')
        or (role or {}).get('role_confidence')
        or (role or {}).get('usage_confidence')
    )
    return confidence in {'low', 'none', 'unknown'}


def _has_coverage_usage_signal(role):
    text = _normalize_text(
        (role or {}).get('role_key'),
        (role or {}).get('role'),
        (role or {}).get('short_reason'),
        (role or {}).get('reason'),
        (role or {}).get('evidence'),
        (role or {}).get('reasons'),
    )
    return any(term in text for term in ('long relief', 'multi inning', 'multi innings', 'bulk', 'coverage'))


def _has_save_or_hold_events(role):
    """Whether the observed-role evidence records any save or hold events.

    Keyed to the classifier's stable evidence phrasing ('N save situation
    finish(es) recorded' / 'N hold(s) recorded'), which is emitted exactly when
    the corresponding event count is nonzero.
    """
    text = _normalize_text((role or {}).get('evidence'))
    return 'save situation finish' in text or 'hold(s) recorded' in text


def _is_mixed_starter_reliever(role, eligibility):
    role = role or {}
    eligibility = eligibility or {}
    if role.get('is_starter') is True and role.get('is_reliever') is True:
        return True
    if role.get('starter_reliever_mixed') is True or role.get('mixed_starter_reliever') is True:
        return True
    if eligibility.get('status') == 'role_ambiguous':
        return True

    text = _normalize_text(
        role.get('role_key'),
        role.get('role'),
        role.get('short_reason'),
        role.get('reason'),
        eligibility.get('status'),
        eligibility.get('reason'),
    )
    has_starter = 'starter' in text or 'starting' in text
    has_relief = 'relief' in text or 'reliever' in text or 'bullpen' in text
    ambiguous = 'ambiguous' in text or 'mixed' in text or 'swing' in text
    return has_starter and has_relief and ambiguous


def _roster_unavailable(roster_status):
    """True when the pitcher is off the active roster — read from Roster Authority.

    Roster Authority owns "off the active roster": ``is_off_active_roster`` decides a
    classified status, and ``roster_status_category_for_status`` decides a bare status code
    (a status with no classification flags is off-roster when its category is neither the
    active roster nor unknown). This label keeps no private roster set or predicate.
    """
    roster_status = roster_status or {}
    if is_off_active_roster(roster_status):
        return True
    status = roster_status.get('status') or roster_status.get('roster_status')
    return roster_status_category_for_status(status) not in (
        ROSTER_STATUS_CATEGORY_ACTIVE,
        ROSTER_STATUS_CATEGORY_UNKNOWN,
    )


def _role_label(role, eligibility=None):
    role = role or {}
    key = _role_key(role)
    sample_size = _role_sample_size(role)
    if sample_size is not None and sample_size < 2:
        return _label({'key': 'limited_read', 'source': 'backend:low_usage_sample'}, ROLE_PUBLIC_LABELS)
    if _weak_role_confidence(role):
        return _label({'key': 'limited_read', 'source': 'backend:weak_role_confidence'}, ROLE_PUBLIC_LABELS)
    if _is_mixed_starter_reliever(role, eligibility):
        # A mixed starter/reliever keeps a Coverage Arm read only when the
        # relief evidence is cleanly multi-inning. Recorded save/hold events on
        # a mixed profile make the public read genuinely murkier, so the label
        # fails closed to Limited Read instead of asserting a concrete role.
        if key in COVERAGE_ROLE_KEYS and _has_coverage_usage_signal(role) and not _has_save_or_hold_events(role):
            return _label({'key': 'coverage_arm', 'source': f'backend:mixed_coverage:{key}'}, ROLE_PUBLIC_LABELS)
        return _label({'key': 'limited_read', 'source': 'backend:mixed_starter_reliever'}, ROLE_PUBLIC_LABELS)
    return _label(
        {'key': ROLE_KEY_TO_PUBLIC_KEY.get(key, 'limited_read'), 'source': f'backend:role_key:{key or "missing"}'},
        ROLE_PUBLIC_LABELS,
    )


def _has_enough_read_data(availability, status):
    availability = availability or {}
    data_state = _normalize_token(availability.get('data_state'))
    if data_state in LIMITED_DATA_STATES:
        return False
    if data_state and data_state not in FRESH_DATA_STATES:
        return False
    if not data_state:
        return False
    confidence = _normalize_token(availability.get('confidence'))
    return confidence not in {'none', 'unknown'}


def _read_label(availability, roster_status=None):
    availability = availability or {}
    status = _normalize_token(availability.get('availability_status'))
    if status == 'unavailable' or _roster_unavailable(roster_status):
        return _label({'key': 'unavailable', 'source': 'backend:unavailable_status'}, READ_PUBLIC_LABELS)
    if not _has_enough_read_data(availability, status):
        return _label({'key': 'limited_read', 'source': 'backend:limited_data'}, READ_PUBLIC_LABELS)
    if status == 'available':
        return _label({'key': 'clean_option', 'source': 'backend:availability_status'}, READ_PUBLIC_LABELS)
    if status == 'monitor':
        return _label({'key': 'watch_arm', 'source': 'backend:availability_status'}, READ_PUBLIC_LABELS)
    if status in {'limited', 'avoid'}:
        return _label({'key': 'rest_restricted', 'source': 'backend:availability_status'}, READ_PUBLIC_LABELS)
    return _label({'key': 'limited_read', 'source': 'backend:unknown_availability'}, READ_PUBLIC_LABELS)


def build_pitcher_labels(availability=None, role=None, eligibility=None, roster_status=None):
    """Return backend-authored public label chips for a pitcher card."""
    return {
        'role': _role_label(role, eligibility=eligibility),
        'read': _read_label(availability, roster_status=roster_status),
    }
