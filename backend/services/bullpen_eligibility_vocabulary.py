"""Shared bullpen eligibility vocabulary and normalization.

Two engines already produce bullpen eligibility payloads: Role Authority V1
(``services/role_authority.py``, the authoritative default) and the legacy
innings heuristic (``services/bullpen_eligibility.py``). They emit different
internal ``role`` / ``status`` vocabularies and a slightly different field set.

This module consolidates that surface area. It defines one shared eligibility
vocabulary, maps each engine's existing output onto it, guarantees a consistent
payload field set, and provides a single fail-closed inclusion test for
bullpen-specific surfaces.

It introduces no new classification policy. The per-engine ``eligible`` boolean
is preserved exactly as produced — only a normalized ``eligibility_type`` label
and a guaranteed set of payload fields are added. The one intentional trust
change is fail-closed handling: a missing or malformed eligibility payload is
treated as ``UNKNOWN_LIMITED`` with ``eligible = False`` instead of being
silently counted toward bullpen depth.
"""

from __future__ import annotations

from typing import Any

from services.bullpen_eligibility import (
    STATUS_BULLPEN_RELEVANT,
    STATUS_CLEAR_STARTER,
    STATUS_INACTIVE,
    STATUS_INACTIVE_BULLPEN_RELEVANT,
    STATUS_NON_PITCHER,
    STATUS_NO_USAGE,
    STATUS_UNCERTAIN,
)
from services.role_authority import (
    ROLE_AMBIGUOUS,
    ROLE_RELIEVER,
    ROLE_STARTER,
    ROLE_UNKNOWN,
)


# ── Shared eligibility vocabulary ────────────────────────────────────────────
ELIGIBILITY_NORMAL_RELIEF = 'normal_relief'
ELIGIBILITY_SWING_BULK_RELIEF = 'swing_bulk_relief'
ELIGIBILITY_STARTER_PROTECTED = 'starter_protected'
ELIGIBILITY_EXCLUDED = 'excluded'
ELIGIBILITY_UNKNOWN_LIMITED = 'unknown_limited'

ELIGIBILITY_TYPES = frozenset({
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_SWING_BULK_RELIEF,
    ELIGIBILITY_STARTER_PROTECTED,
    ELIGIBILITY_EXCLUDED,
    ELIGIBILITY_UNKNOWN_LIMITED,
})

# Eligibility types that count as part of the default bullpen picture. This is a
# descriptive grouping only; the authoritative include/exclude decision remains
# the per-engine ``eligible`` boolean, which this module never overrides.
BULLPEN_PICTURE_TYPES = frozenset({
    ELIGIBILITY_NORMAL_RELIEF,
    ELIGIBILITY_SWING_BULK_RELIEF,
})

# ── Engine/source markers (the "authority/source" field) ─────────────────────
SOURCE_ROLE_AUTHORITY = 'role_authority'
SOURCE_LEGACY_INNINGS = 'innings_heuristic'
SOURCE_FALLBACK = 'fallback'

MISSING_ELIGIBILITY_REASON = (
    'No eligibility payload was attached, so the pitcher is withheld from '
    'default bullpen counts.'
)
MISSING_ELIGIBILITY_LIMITATION = (
    'Eligibility could not be determined; treated as unknown/limited and '
    'excluded from default bullpen counts.'
)


# ── Engine -> vocabulary maps (relabeling only; no logic change) ─────────────
# Role Authority payloads carry a ``role``. Each role has a fixed eligibility
# type; whether it is currently counted is still carried by ``eligible``.
_ROLE_AUTHORITY_TYPE_MAP = {
    ROLE_RELIEVER: ELIGIBILITY_NORMAL_RELIEF,
    ROLE_AMBIGUOUS: ELIGIBILITY_SWING_BULK_RELIEF,
    ROLE_STARTER: ELIGIBILITY_STARTER_PROTECTED,
    ROLE_UNKNOWN: ELIGIBILITY_UNKNOWN_LIMITED,
}

# Legacy innings-heuristic payloads carry a ``status`` and no ``role``.
_LEGACY_STATUS_TYPE_MAP = {
    STATUS_BULLPEN_RELEVANT: ELIGIBILITY_NORMAL_RELIEF,
    STATUS_INACTIVE_BULLPEN_RELEVANT: ELIGIBILITY_NORMAL_RELIEF,
    STATUS_CLEAR_STARTER: ELIGIBILITY_STARTER_PROTECTED,
    STATUS_INACTIVE: ELIGIBILITY_EXCLUDED,
    STATUS_NON_PITCHER: ELIGIBILITY_EXCLUDED,
    STATUS_NO_USAGE: ELIGIBILITY_UNKNOWN_LIMITED,
    STATUS_UNCERTAIN: ELIGIBILITY_UNKNOWN_LIMITED,
}


def _is_payload(payload: Any) -> bool:
    return isinstance(payload, dict)


def eligibility_type_for(payload: Any) -> str:
    """Map an existing engine eligibility payload onto the shared vocabulary.

    Role Authority payloads are matched on ``role``; the legacy engine is matched
    on ``status``. Missing, malformed, or unrecognized payloads map to
    ``UNKNOWN_LIMITED``. This is a pure relabeling and never changes the
    ``eligible`` decision an engine already made.
    """
    if not _is_payload(payload):
        return ELIGIBILITY_UNKNOWN_LIMITED

    role = payload.get('role')
    if role in _ROLE_AUTHORITY_TYPE_MAP:
        return _ROLE_AUTHORITY_TYPE_MAP[role]

    status = payload.get('status')
    if status in _LEGACY_STATUS_TYPE_MAP:
        return _LEGACY_STATUS_TYPE_MAP[status]

    return ELIGIBILITY_UNKNOWN_LIMITED


def _source_for(payload: dict[str, Any]) -> str:
    if payload.get('role') is not None:
        return SOURCE_ROLE_AUTHORITY
    if payload.get('status') is not None:
        return SOURCE_LEGACY_INNINGS
    return SOURCE_FALLBACK


def _fail_closed_payload() -> dict[str, Any]:
    return {
        'eligible': False,
        'eligibility_type': ELIGIBILITY_UNKNOWN_LIMITED,
        'confidence': 'none',
        'reason': MISSING_ELIGIBILITY_REASON,
        'authority': SOURCE_FALLBACK,
        'source': SOURCE_FALLBACK,
        'status': None,
        'role': None,
        'evidence': [],
        'limitations': [MISSING_ELIGIBILITY_LIMITATION],
    }


def normalize_eligibility(payload: Any) -> dict[str, Any]:
    """Return a normalized eligibility payload with the shared field set.

    The returned payload always carries ``eligible``, ``eligibility_type``,
    ``confidence``, ``reason``, ``authority`` and ``source``. All original keys
    are preserved for backward compatibility; only normalized fields are added
    or filled in.

    Missing or malformed payloads fail closed: ``UNKNOWN_LIMITED`` with
    ``eligible = False``. For a well-formed payload the ``eligible`` flag is
    never flipped — it is coerced to ``bool`` exactly as the engine set it.
    """
    if not _is_payload(payload):
        return _fail_closed_payload()

    normalized = dict(payload)
    normalized['eligible'] = bool(payload.get('eligible'))
    normalized['eligibility_type'] = eligibility_type_for(payload)
    normalized['confidence'] = payload.get('confidence') or 'none'
    normalized['reason'] = payload.get('reason') or ''
    source = _source_for(payload)
    normalized['source'] = source
    normalized['authority'] = payload.get('authority') or source
    normalized.setdefault('evidence', [])
    normalized.setdefault('limitations', [])
    return normalized


def record_is_bullpen_eligible(record: Any) -> bool:
    """Fail-closed inclusion test for bullpen-specific surfaces.

    Replaces the duplicated per-service guards that treated a missing
    eligibility payload as included. A record (or context) is bullpen-eligible
    only when it carries an eligibility payload whose ``eligible`` flag is true;
    missing or malformed payloads are excluded.
    """
    if not _is_payload(record):
        return False
    return normalize_eligibility(record.get('eligibility'))['eligible']
