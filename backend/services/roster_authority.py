"""Roster Authority — the canonical roster-context model (CRC Phase 1 foundation).

Roster Authority is to roster context what the canonical story is to stories: one
deterministic, transport-neutral description of a team's roster reality that every
surface can eventually read from, so no consumer recomputes its own roster truth.

This module is the *foundation only*. It introduces the authority object and a pure
builder over already-classified bullpen records. It does not query the database,
render anything, attach to any payload, or change any existing consumer. Wiring the
authority into the board / story / digest payloads and migrating consumers off their
private counts is deferred to later phases. See
``docs/methodology/ROSTER_AUTHORITY_V1.md`` and the audit at
``docs/methodology/CANONICAL_ROSTER_CONTEXT_AUDIT_AND_DESIGN.md``.

Contract:
  * Pure — output depends only on the records (and optional team / reference_date)
    passed in. No database, no clock, no globals.
  * Deterministic — identical inputs always produce an identical object; input order
    never matters (evidence is sorted by name then pitcher id).
  * Transport-neutral — returns plain JSON-serializable primitives only; no ORM
    objects, no Flask, no rendering concepts.
  * Invariant — every count is computed over the full canonical population, never a
    UI-filtered subset, so no field can change when only a view changes. View-dependent
    display numbers (how many cards a filter renders) are deliberately NOT part of the
    authority; consumers derive those at render time from the evidence lists.

Definitions are reused, never re-invented: per-pitcher roster classification comes from
``services.roster_status.classify_roster_status`` (the ``is_active_mlb`` /
``is_inactive_context`` / ``is_authoritative`` fields), and availability reads use the
canonical ``services.availability`` status constants. This module adds no new predicate
for "on the active roster" or "off the active roster".
"""

from __future__ import annotations

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.roster_status import STATUS_LABELS, STATUS_UNKNOWN


CAPABILITY = 'roster_authority_v1'
VERSION = '2026-06-25.foundation'

# The canonical roster population is defined ONCE, independent of any UI view or
# filter: the full bullpen-eligible set, including off-roster (inactive) arms and
# unknown-status arms. Future database-backed callers (next phase) build it by calling
# ``services.bullpen_population.eligible_bullpen_pitcher_contexts`` with these fixed
# flags and pass the resulting records here. The flags live in one place so the
# population is described once and is never bound to a request or view.
CANONICAL_POPULATION_FLAGS = {
    'include_stale': True,
    'include_inactive_context': True,
}

# Availability reads that mean "usable in some capacity tonight". Unavailable is
# excluded: an active-roster arm read Unavailable is on the roster but should not pitch.
_USABLE_AVAILABILITY = (
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
)

# The per-availability count fields, in canonical reading order.
_AVAILABILITY_FIELDS = (
    ('available_count', STATUS_AVAILABLE),
    ('monitor_count', STATUS_MONITOR),
    ('limited_count', STATUS_LIMITED),
    ('avoid_count', STATUS_AVOID),
    ('unavailable_count', STATUS_UNAVAILABLE),
)

# Every count field the authority publishes, paired with whether it is invariant across
# UI filters/views. The authority publishes only invariant fields; display-only numbers
# (how many cards a filter renders) are derived by consumers and never stored here.
FIELD_INVARIANCE = {
    'bullpen_arms': True,
    'active_bullpen_arms': True,
    'inactive_roster_context_count': True,
    'roster_unknown_count': True,
    'available_count': True,
    'monitor_count': True,
    'limited_count': True,
    'avoid_count': True,
    'unavailable_count': True,
    'availability_unknown_count': True,
}


# ── Canonical roster predicates ───────────────────────────────────────────────
# The single authoritative interpretation of a pitcher's roster bucket, read from the
# per-pitcher classification (services.roster_status.classify_roster_status). Roster
# Authority owns roster truth; engine consumers (capacity, resource health, stability,
# trust hierarchy) call these instead of redefining their own predicate. Each accepts the
# classified ``roster_status`` dict (or None).

def is_on_active_roster(roster_status):
    """True when the pitcher is on the active MLB roster."""
    return (roster_status or {}).get('is_active_mlb') is True


def is_off_active_roster(roster_status):
    """True when the pitcher is off the active roster (IL, optioned, 40-man, DFA, ...).

    ``is_inactive_context`` carries the off-roster fact; ``is_active_mlb is False`` is the
    equivalent signal from the same authoritative classification (a status is inactive
    exactly when it is not active MLB). Both are accepted so this one predicate matches
    every historical consumer byte-for-byte.
    """
    rs = roster_status or {}
    return rs.get('is_inactive_context') is True or rs.get('is_active_mlb') is False


def is_roster_status_unknown(roster_status):
    """True when the pitcher's roster status is not yet confirmed (no authoritative read)."""
    if not roster_status:
        return True
    return roster_status.get('status') == STATUS_UNKNOWN or roster_status.get('is_active_mlb') is None


def _roster_status_of(record):
    value = record.get('roster_status')
    return value if isinstance(value, dict) else {}


def _availability_status_of(record):
    direct = record.get('availability_status')
    if direct:
        return direct
    availability = record.get('availability')
    if isinstance(availability, dict):
        return availability.get('availability_status')
    return None


def _name_of(record):
    name = record.get('name')
    if name:
        return str(name)
    pitcher = record.get('pitcher')
    if isinstance(pitcher, dict):
        return str(pitcher.get('full_name') or pitcher.get('name') or '')
    full_name = getattr(pitcher, 'full_name', None)
    return str(full_name) if full_name else ''


def _reason_for(roster_status, availability_status):
    if roster_status.get('is_active_mlb') is True:
        if availability_status == STATUS_UNAVAILABLE:
            return 'On the active roster; read Unavailable for tonight.'
        return 'On the active roster.'
    if roster_status.get('is_inactive_context') is True:
        label = roster_status.get('label') or STATUS_LABELS.get(
            roster_status.get('status'), STATUS_LABELS[STATUS_UNKNOWN]
        )
        return f'Off the active roster ({label}).'
    return 'Roster status not yet confirmed.'


def _evidence_entry(record):
    roster_status = _roster_status_of(record)
    availability_status = _availability_status_of(record)
    return {
        'pitcher_id': record.get('pitcher_id'),
        'name': _name_of(record),
        'roster_status': roster_status.get('status') or STATUS_UNKNOWN,
        'roster_status_label': roster_status.get('label') or STATUS_LABELS[STATUS_UNKNOWN],
        'availability': availability_status,
        'reason': _reason_for(roster_status, availability_status),
    }


def _evidence(records):
    """Deterministic evidence list — sorted by name then pitcher id, order-independent."""
    return sorted(
        (_evidence_entry(record) for record in records),
        key=lambda entry: (str(entry.get('name') or '').lower(), entry.get('pitcher_id') or 0),
    )


def _iso_date(value):
    if value is None:
        return None
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _team_block(team):
    if not isinstance(team, dict):
        return None
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def build_roster_authority(records, *, team=None, reference_date=None):
    """Build the canonical Roster Authority snapshot from bullpen-eligible records.

    ``records`` is the full canonical roster population for a team — every
    bullpen-eligible pitcher, including off-roster (inactive) and unknown-status arms.
    Each record is a plain dict carrying at least ``pitcher_id``, ``name``, a classified
    ``roster_status`` dict (from ``classify_roster_status``), and an
    ``availability_status`` (or nested ``availability``). Callers must pass the full
    population (see ``CANONICAL_POPULATION_FLAGS``) and never a view-filtered subset —
    the authority's invariance depends on it.

    Returns one deterministic, JSON-serializable object. Every published count is
    invariant across UI filters and is backed by an evidence list of the same length.
    """
    rows = [record for record in (records or []) if isinstance(record, dict)]

    # Each candidate falls in exactly one roster bucket, using the canonical roster
    # predicates above (the same ones the engine consumers call). These three buckets
    # partition the population: on the active roster, off the active roster, or unconfirmed.
    active, inactive, unknown = [], [], []
    for record in rows:
        roster_status = _roster_status_of(record)
        if is_on_active_roster(roster_status):
            active.append(record)
        elif is_off_active_roster(roster_status):
            inactive.append(record)
        else:
            unknown.append(record)

    # Tonight's availability read is a sub-classification of the active roster only. Off-
    # roster and unconfirmed arms are not given a tonight-availability count here; their
    # roster reality is carried by the roster buckets above.
    by_availability = {status: [] for _field, status in _AVAILABILITY_FIELDS}
    availability_unknown = []
    for record in active:
        status = _availability_status_of(record)
        if status in by_availability:
            by_availability[status].append(record)
        else:
            availability_unknown.append(record)

    usable = [
        record
        for status in _USABLE_AVAILABILITY
        for record in by_availability[status]
    ]

    known = active + inactive
    total = len(rows)

    evidence = {
        'bullpen_arms': _evidence(active),
        'active_bullpen_arms': _evidence(usable),
        'inactive_roster_context_count': _evidence(inactive),
        'roster_unknown_count': _evidence(unknown),
        'availability_unknown_count': _evidence(availability_unknown),
    }
    for field, status in _AVAILABILITY_FIELDS:
        evidence[field] = _evidence(by_availability[status])

    counts = {field: len(evidence[field]) for field in FIELD_INVARIANCE}

    limitations = []
    if availability_unknown:
        limitations.append(
            'Some active-roster arms have no current availability read; they count as '
            'bullpen arms but not in the tonight availability breakdown.'
        )
    if unknown:
        limitations.append(
            'Some bullpen candidates have an unconfirmed roster status and are counted '
            'only toward roster status coverage.'
        )

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': 'backend',
        # The entire object is invariant across UI views/filters. View-dependent display
        # numbers (e.g. how many cards a filter renders) are intentionally absent.
        'invariant': True,
        'reference_date': _iso_date(reference_date),
        'team': _team_block(team),
        'population': {
            'total_candidates': total,
            'known_count': len(known),
            'unknown_count': len(unknown),
            'roster_status_coverage': round(len(known) / total, 4) if total else 0.0,
        },
        'counts': counts,
        'evidence': evidence,
        'field_invariance': dict(FIELD_INVARIANCE),
        'limitations': limitations,
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'CANONICAL_POPULATION_FLAGS',
    'FIELD_INVARIANCE',
    'build_roster_authority',
    'is_on_active_roster',
    'is_off_active_roster',
    'is_roster_status_unknown',
]
