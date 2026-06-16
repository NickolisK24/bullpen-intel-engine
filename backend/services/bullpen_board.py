"""
Tonight's Bullpen Board — presentation grouping over existing availability.

This module reshapes already-classified Availability Engine V1 output into the
five decision-support buckets a coach reads before a game:

    Available · Monitor · Limited · Avoid · Unavailable

It performs **no** ranking, **no** selection, **no** recommendation, and
**no** prediction. It only groups existing per-pitcher availability and orders
pitchers alphabetically within each group so that a pitcher's position on the
board never implies preference. Governance flags are surfaced at the API level
(``ranking_applied`` / ``selection_made`` stay ``False``) and are intentionally
not exposed as user-facing copy.
"""

from datetime import datetime, timezone

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.bullpen_stress import build_bullpen_stress
from services.bullpen_visibility import default_visible_contract, summarize_visibility


# Canonical group order: least-restricted to most-restricted. This is a fixed
# presentation order, NOT a ranking of pitchers — pitchers inside each group are
# ordered alphabetically and carry no score-based position.
BOARD_GROUP_ORDER = [
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
]

# Plain baseball language only — no governance/contract jargon on this surface.
GROUP_META = {
    STATUS_AVAILABLE: {
        'label': 'Available',
        'description': 'Workload signals are inside normal ranges in the latest completed data.',
    },
    STATUS_MONITOR: {
        'label': 'Monitor',
        'description': 'Worth a look at recent workload before counting on these arms.',
    },
    STATUS_LIMITED: {
        'label': 'Limited',
        'description': 'Recent workload suggests limited use in the current availability read.',
    },
    STATUS_AVOID: {
        'label': 'Avoid',
        'description': 'Meaningful recent-use load on these arms.',
    },
    STATUS_UNAVAILABLE: {
        'label': 'Unavailable Pitchers',
        'description': 'Not available in the current bullpen planning read.',
    },
}

CAPABILITY = 'tonights_bullpen_board'


# ── Team context (Board V2) ────────────────────────────────────────────────
#
# Deterministic, transparent team-level context derived ONLY from the group
# counts produced above. No scoring, ranking, ordering, or recommendation —
# just a plain-language read of bullpen shape with the numbers that justify it.

# Thresholds, expressed as fractions of the total reliever pool. Centralized so
# the rules stay explainable and tunable without scattering magic numbers.
CONSTRAINED_RESTRICTED_PCT = 0.40   # Avoid+Unavailable at/over this → constrained
MONITOR_DOMINANT_PCT = 0.40         # Monitor at/over this → monitoring
ELEVATED_RESTRICTED_PCT = 0.20      # Avoid+Unavailable at/over this → elevated
ELEVATED_LOW_AVAILABLE_PCT = 0.40   # Available under this → elevated

HEALTH_MANAGEABLE = 'manageable'
HEALTH_MONITORING = 'monitoring'
HEALTH_ELEVATED = 'elevated'
HEALTH_CONSTRAINED = 'constrained'
HEALTH_NO_DATA = 'no_data'

HEALTH_LABELS = {
    HEALTH_MANAGEABLE: 'Bullpen workload appears manageable.',
    HEALTH_MONITORING: 'Several relievers require monitoring.',
    HEALTH_ELEVATED: 'Bullpen workload is elevated.',
    HEALTH_CONSTRAINED: 'Availability is constrained in the current read.',
    HEALTH_NO_DATA: 'No bullpen availability to summarize from the latest completed data.',
}

METHODOLOGY_REASON = 'Availability classifications are workload-based only.'


def _pct(part, total):
    """Whole-number percentage; 0 when there is nothing to divide."""
    if not total:
        return 0
    return round(part / total * 100)


def _monitor_is_dominant(counts):
    """True when Monitor is the single largest group (strict over the rest)."""
    monitor = counts[STATUS_MONITOR]
    if monitor <= 0:
        return False
    others = [counts[status] for status in BOARD_GROUP_ORDER if status != STATUS_MONITOR]
    return all(monitor > other for other in others)


def classify_bullpen_health(counts, total):
    """
    Deterministic bullpen-health state from group counts.

    Evaluated in a fixed priority order (first match wins) so the result is
    explainable and stable:

      1. no_data     — no relievers in the freshness window.
      2. constrained — Avoid+Unavailable >= 40% of the pen, or nobody Available.
      3. monitoring  — Monitor >= 40% of the pen, or Monitor is the largest group.
      4. elevated    — Avoid+Unavailable >= 20%, or Available < 40% of the pen.
      5. manageable  — none of the above (healthy availability, light restriction).
    """
    if total == 0:
        return HEALTH_NO_DATA

    available = counts[STATUS_AVAILABLE]
    monitor = counts[STATUS_MONITOR]
    restricted = counts[STATUS_AVOID] + counts[STATUS_UNAVAILABLE]

    if restricted / total >= CONSTRAINED_RESTRICTED_PCT or available == 0:
        return HEALTH_CONSTRAINED
    if monitor / total >= MONITOR_DOMINANT_PCT or _monitor_is_dominant(counts):
        return HEALTH_MONITORING
    if (
        restricted / total >= ELEVATED_RESTRICTED_PCT
        or available / total < ELEVATED_LOW_AVAILABLE_PCT
    ):
        return HEALTH_ELEVATED
    return HEALTH_MANAGEABLE


def _health_reasons(state, counts, total, freshness_note=None):
    """Transparent, count-referencing explanation for a health statement."""
    reasons = []
    if state == HEALTH_NO_DATA:
        reasons.append('No active relievers fall inside the current freshness window.')
        if freshness_note:
            reasons.append(freshness_note)
        return reasons

    available = counts[STATUS_AVAILABLE]
    monitor = counts[STATUS_MONITOR]
    restricted = counts[STATUS_AVOID] + counts[STATUS_UNAVAILABLE]

    reasons.append(f'{available} of {total} relievers are classified Available.')
    if restricted == 0:
        reasons.append('No relievers are marked Avoid or Unavailable.')
    else:
        reasons.append(f'{restricted} of {total} relievers are Avoid or Unavailable.')
    if state in (HEALTH_MONITORING, HEALTH_ELEVATED):
        reasons.append(f'{monitor} of {total} relievers are in the Monitor group.')
    reasons.append(METHODOLOGY_REASON)
    if freshness_note:
        reasons.append(freshness_note)
    return reasons


def build_team_context(groups, freshness=None):
    """
    Team-level bullpen context (Board V2).

    Pure function of the group counts plus the freshness block. Returns
    descriptive metrics, a deterministic health statement with a transparent
    explanation, and an honest confidence read. Contains no scores, rankings,
    orderings, or pitcher-level preferences.
    """
    counts = {status: 0 for status in BOARD_GROUP_ORDER}
    for group in groups:
        status = group.get('status')
        if status in counts:
            counts[status] = int(group.get('count') or 0)

    total = sum(counts.values())
    restricted = counts[STATUS_AVOID] + counts[STATUS_UNAVAILABLE]
    state = classify_bullpen_health(counts, total)

    freshness = freshness or {}
    is_current = freshness.get('is_current', True)
    limitations = []
    freshness_note = None
    if total == 0:
        confidence = 'none'
    elif is_current is False:
        confidence = 'low'
        freshness_note = (
            'Latest workload data is outside the active freshness window, '
            'so this snapshot may not reflect current bullpen planning.'
        )
        limitations.append(freshness_note)
    else:
        confidence = 'high'

    metrics = {
        'total_relievers': total,
        'available': counts[STATUS_AVAILABLE],
        'monitor': counts[STATUS_MONITOR],
        'limited': counts[STATUS_LIMITED],
        'avoid': counts[STATUS_AVOID],
        'unavailable': counts[STATUS_UNAVAILABLE],
        'restricted': restricted,
        'pct_available': _pct(counts[STATUS_AVAILABLE], total),
        'pct_unavailable': _pct(counts[STATUS_UNAVAILABLE], total),
        'pct_restricted': _pct(restricted, total),
    }

    return {
        'metrics': metrics,
        'health': {
            'state': state,
            'label': HEALTH_LABELS[state],
            'reasons': _health_reasons(state, counts, total, freshness_note),
        },
        'confidence': confidence,
        'limitations': limitations,
    }


def short_reason_for(availability):
    """
    A single, plain-language line summarizing why a pitcher sits in its group.

    Reuses the Availability Engine V1 ``reasons`` for non-available statuses and
    synthesizes a positive line for available arms (the engine intentionally
    returns no reasons when nothing is elevated). Freshness states take priority
    so a stale/missing classification reads as a data caveat, not a workload claim.
    """
    availability = availability or {}
    data_state = str(availability.get('data_state') or '').lower()
    status = availability.get('availability_status')
    reasons = availability.get('reasons') or []
    inputs = availability.get('inputs') or {}

    if data_state == 'stale':
        return 'Outside active freshness window'
    if data_state == 'missing':
        return 'No workload record available'
    if data_state == 'incomplete':
        return 'Some recent workload data is incomplete'
    if data_state == 'failed':
        return 'Recent workload fetch failed'

    if status == STATUS_AVAILABLE:
        appearances = inputs.get('appearances_last_5_days')
        pitches = inputs.get('pitches_last_5_days')
        if appearances == 0:
            return 'Minimal recent usage'
        if isinstance(pitches, (int, float)) and pitches <= 20:
            return 'Low recent workload'
        return 'Fresh workload profile'

    if reasons:
        return reasons[0]
    return 'Workload indicators elevated'


def build_card(
    name,
    pitcher_id,
    fatigue_score,
    availability,
    role=None,
    eligibility=None,
    roster_status=None,
    visibility=None,
):
    """Build a single display card from existing availability output."""
    availability = availability or {}
    score = None
    if fatigue_score is not None:
        try:
            score = round(float(fatigue_score), 1)
        except (TypeError, ValueError):
            score = None

    return {
        'pitcher_id': pitcher_id,
        'name': name,
        'availability_status': availability.get('availability_status'),
        'fatigue_score': score,
        'confidence': availability.get('confidence'),
        'short_reason': short_reason_for(availability),
        'data_state': availability.get('data_state'),
        'reasons': list(availability.get('reasons') or []),
        'limitations': list(availability.get('limitations') or []),
        # Observed usage role (descriptive). May be None if not classified.
        'role': role,
        # Bullpen roster eligibility is descriptive and explains why a pitcher
        # is present on this bullpen-specific surface.
        'eligibility': eligibility,
        # Roster status is separate from workload freshness and role inference.
        'roster_status': roster_status,
        # Visibility is the explicit board/story trust contract. Default board
        # payload tests pass already-visible records, so a safe visible default
        # preserves the pure grouping API.
        'visibility': visibility or default_visible_contract(),
    }


def group_cards(cards):
    """
    Group cards into the five named buckets in canonical order.

    Within each group, pitchers are sorted alphabetically by name (ties broken by
    pitcher id only for stability). This ordering is explicitly NOT by score,
    fatigue, or any preference signal — position must never read as a ranking.
    """
    buckets = {status: [] for status in BOARD_GROUP_ORDER}
    for card in cards:
        status = card.get('availability_status')
        if status in buckets:
            buckets[status].append(card)
        # Cards with an unknown/None status are intentionally excluded from the
        # five named groups; the payload reconciles them via ungrouped_pitchers.

    groups = []
    for status in BOARD_GROUP_ORDER:
        ordered = sorted(
            buckets[status],
            key=lambda card: (str(card.get('name') or '').lower(), card.get('pitcher_id') or 0),
        )
        meta = GROUP_META[status]
        groups.append({
            'status': status,
            'label': meta['label'],
            'description': meta['description'],
            'count': len(ordered),
            'pitchers': ordered,
        })
    return groups


def build_board_payload(
    team,
    records,
    freshness=None,
    limitations=None,
    roster_status=None,
    generated_at=None,
):
    """
    Assemble the full Tonight's Bullpen Board payload.

    Args:
        team: {team_id, team_name, team_abbreviation} dict.
        records: iterable of {name, pitcher_id, fatigue_score, availability}.
        freshness: pre-built freshness/trust block (data-through, sync state).
        limitations: top-level trust limitations to surface.
        generated_at: ISO timestamp override (tests pass a fixed value).

    Returns:
        Dict safe to ``jsonify``. ``ranking_applied`` / ``selection_made`` are
        hard-coded ``False`` — this surface is presentation only.
    """
    cards = [
        build_card(
            name=record.get('name'),
            pitcher_id=record.get('pitcher_id'),
            fatigue_score=record.get('fatigue_score'),
            availability=record.get('availability'),
            role=record.get('role'),
            eligibility=record.get('eligibility'),
            roster_status=record.get('roster_status'),
            visibility=record.get('visibility'),
        )
        for record in records
    ]
    groups = group_cards(cards)
    grouped_total = sum(group['count'] for group in groups)
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    context = build_team_context(groups, freshness=freshness)
    stress = build_bullpen_stress(context)
    visibility = summarize_visibility(cards)

    return {
        'capability': CAPABILITY,
        'team': team,
        'generated_at': generated,
        # API-level governance protections. Never rendered as raw fields.
        'ranking_applied': False,
        'selection_made': False,
        'group_order': list(BOARD_GROUP_ORDER),
        'context': context,
        'stress': stress,
        'visibility': visibility,
        'groups': groups,
        'total_pitchers': grouped_total,
        'ungrouped_pitchers': max(len(cards) - grouped_total, 0),
        'freshness': freshness or {},
        'roster_status': roster_status or {},
        'limitations': list(limitations or []),
    }
