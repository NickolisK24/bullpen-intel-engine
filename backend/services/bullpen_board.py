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
        'label': 'Available Tonight',
        'description': 'Workload signals are inside normal ranges.',
    },
    STATUS_MONITOR: {
        'label': 'Monitor',
        'description': 'Worth a look at recent workload before counting on these arms.',
    },
    STATUS_LIMITED: {
        'label': 'Limited',
        'description': 'Recent workload suggests restricted use tonight.',
    },
    STATUS_AVOID: {
        'label': 'Avoid',
        'description': 'Meaningful recent-use load on these arms.',
    },
    STATUS_UNAVAILABLE: {
        'label': 'Unavailable',
        'description': "Should not be counted for tonight's planning.",
    },
}

CAPABILITY = 'tonights_bullpen_board'


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
        return 'Data freshness limits confidence'
    if data_state == 'missing':
        return 'Limited recent workload data'
    if data_state == 'incomplete':
        return 'Some recent workload data is incomplete'

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


def build_card(name, pitcher_id, fatigue_score, availability):
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
        )
        for record in records
    ]
    groups = group_cards(cards)
    grouped_total = sum(group['count'] for group in groups)
    generated = generated_at or datetime.now(timezone.utc).isoformat()

    return {
        'capability': CAPABILITY,
        'team': team,
        'generated_at': generated,
        # API-level governance protections. Never rendered as raw fields.
        'ranking_applied': False,
        'selection_made': False,
        'group_order': list(BOARD_GROUP_ORDER),
        'groups': groups,
        'total_pitchers': grouped_total,
        'ungrouped_pitchers': max(len(cards) - grouped_total, 0),
        'freshness': freshness or {},
        'limitations': list(limitations or []),
    }
