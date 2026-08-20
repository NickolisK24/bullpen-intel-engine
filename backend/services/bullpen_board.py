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
from services.pitcher_public_labels import build_pitcher_labels
from services.pitcher_role_authority import author_public_role_read
from services.public_roster_readiness import roster_claims_available
from services.public_bullpen_copy import (
    guard_board_context,
    guard_board_groups,
    guard_team_shape_reads,
    public_availability_label,
)
from services.team_bullpen_shape import build_team_bullpen_shape
from services.bullpen_visibility import default_visible_contract, summarize_visibility
from services.workload_appearance import pitch_count_workload_logs


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

# D-055 Rest Status carrier compatibility. The method version owns the
# governed population, evidence gates, and count definitions. The public
# contract version owns the exact frozen reader-object shape and meaning.
# Phase 1 records these stamps without changing any reader path.
REST_STATUS_METHOD_VERSION = 'd055_rest_status_v1'
REST_STATUS_PUBLIC_CONTRACT_VERSION = 'd055_rest_status_public_v1'

# Plain baseball language only — no governance/contract jargon on this surface.
#
# VOC-001: these are GROUP headings, not pitcher classifications. They used to
# reuse the individual availability labels verbatim ('Available', 'On Watch',
# 'Limited'), so a column heading and a chip on a card inside it read as the
# same claim; and the two restricted groups both headed 'Unavailable' /
# 'Unavailable Pitchers', which told a reader nothing about why they differ.
#
# The two restricted groups differ by WORKLOAD SEVERITY, not by cause. Both
# STATUS_AVOID and STATUS_UNAVAILABLE are produced by the same workload-only
# classifier in services/availability.py — one if/elif chain over pitches
# yesterday, pitches across 3 and 5 days, appearances across 3 and 5 days,
# back-to-back use, and fatigue score. STATUS_UNAVAILABLE is the more
# restrictive tier; STATUS_AVOID is the tier below it.
#
# Roster authority is deliberately NOT named here. It is separate context
# (roster_status on the card, the withhold helpers below, and the read family's
# own roster path), and heading a workload group 'Unavailable — Roster' would
# assert that a fully rostered arm who threw 45 pitches yesterday is off the
# roster. 'Heavy' and 'Severe' name the thresholds actually crossed, imply no
# injury, no manager intent, and no ranking among pitchers.
#
# Engine keys, BOARD_GROUP_ORDER, membership, counts and ordering are unchanged.
GROUP_META = {
    STATUS_AVAILABLE: {
        'label': 'Available Arms',
        'description': 'Recent workload remains inside the normal availability range.',
    },
    STATUS_MONITOR: {
        # Public label, not the engine state. ``Monitor`` is engine vocabulary;
        # ``On Watch`` is the reader form (services/public_bullpen_copy.py).
        'label': 'On-Watch Arms',
        'description': 'Recent workload is worth monitoring before assuming a full workload.',
    },
    STATUS_LIMITED: {
        'label': 'Limited Arms',
        'description': "Recent workload materially narrows the arm's current availability.",
    },
    STATUS_AVOID: {
        # ``Avoid`` is retired reader vocabulary. The engine state key is
        # unchanged; the heading now names the workload threshold crossed.
        'label': 'Unavailable — Heavy Workload',
        'description': (
            'Recent workload crosses the stronger restriction threshold and '
            'keeps these arms out of the available group.'
        ),
    },
    STATUS_UNAVAILABLE: {
        'label': 'Unavailable — Severe Workload',
        'description': (
            'Recent workload crosses the most restrictive workload threshold '
            'in the current availability read.'
        ),
    },
}

CAPABILITY = 'tonights_bullpen_board'


def last_workload_appearance_from_logs(logs):
    """Return the latest positive-pitch workload appearance from raw logs."""
    rows = pitch_count_workload_logs(logs)
    if not rows:
        return None

    latest_date = max(log.game_date for log in rows)
    pitches = sum(
        int(getattr(log, 'pitches_thrown', 0) or 0)
        for log in rows
        if log.game_date == latest_date
    )
    return {
        'game_date': latest_date.isoformat(),
        'pitches': pitches,
    }


def last_appearance_from_logs(logs):
    """Backward-compatible alias for workload appearance summaries."""
    return last_workload_appearance_from_logs(logs)


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
    HEALTH_MONITORING: 'Several relievers need a workload check.',
    HEALTH_ELEVATED: 'Bullpen workload is elevated.',
    HEALTH_CONSTRAINED: 'The bullpen is short on rested arms right now.',
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

    reasons.append(
        f'{_reliever_count_phrase(available).capitalize()} {_reliever_verb(available)} '
        'available from the latest completed workload data.'
    )
    if restricted == 0:
        reasons.append('No relievers are marked Unavailable.')
    else:
        reasons.append(
            f'{_reliever_count_phrase(restricted).capitalize()} {_reliever_verb(restricted)} '
            'Unavailable.'
        )
    # The On Watch count is authored whenever there is one, not only when the
    # board entered the monitoring/elevated branch.
    #
    # It used to be branch-gated, which left a calm board with exactly two
    # authored candidates: the available-count sentence and, when nothing was
    # restricted, the fixed 'No relievers are marked Unavailable.' Downstream
    # consumers that rank candidates correctly demote the generic available-count
    # sentence, so the constant won by default — 14 of 30 generated team previews
    # shipped that one sentence, including seven Vulnerable teams whose only
    # published evidence read as the opposite of their state. The selector was
    # working; it had nothing discriminating to select.
    #
    # Purely additive: every case that authored this sentence before still does.
    if monitor > 0 or state in (HEALTH_MONITORING, HEALTH_ELEVATED):
        reasons.append(
            f'{_reliever_count_phrase(monitor).capitalize()} {_reliever_verb(monitor)} '
            'in the On Watch group.'
        )
    reasons.append(METHODOLOGY_REASON)
    if freshness_note:
        reasons.append(freshness_note)
    return reasons


def _count_word(value):
    words = {
        0: 'no',
        1: 'one',
        2: 'two',
        3: 'three',
        4: 'four',
        5: 'five',
        6: 'six',
        7: 'seven',
        8: 'eight',
        9: 'nine',
        10: 'ten',
        11: 'eleven',
        12: 'twelve',
        13: 'thirteen',
        14: 'fourteen',
        15: 'fifteen',
        16: 'sixteen',
        17: 'seventeen',
        18: 'eighteen',
        19: 'nineteen',
        20: 'twenty',
    }
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 'unknown'
    return words.get(count, 'more than twenty')


def _reliever_count_phrase(value):
    try:
        count = int(value)
    except (TypeError, ValueError):
        return 'unknown relievers'
    return f'{_count_word(count)} reliever{"" if count == 1 else "s"}'


def _reliever_verb(value):
    try:
        return 'is' if int(value) == 1 else 'are'
    except (TypeError, ValueError):
        return 'are'


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
            'so this bullpen read may not reflect current bullpen planning.'
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

    # Publication boundary for the Why and its evidence: guarded here so no
    # caller can publish this block without the public prose being checked.
    return guard_board_context({
        'metrics': metrics,
        'health': {
            'state': state,
            'label': HEALTH_LABELS[state],
            'reasons': _health_reasons(state, counts, total, freshness_note),
        },
        'confidence': confidence,
        'limitations': limitations,
    })


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


REST_STATUS_NO_ELIGIBLE_ARMS = 'no_eligible_arms'
REST_STATUS_BOARD_CONTEXT_UNAVAILABLE = 'board_context_unavailable'
REST_STATUS_ROSTER_CONTEXT_UNAVAILABLE = 'roster_context_unavailable'
REST_STATUS_WORKLOAD_EVIDENCE_INCOMPLETE = 'workload_evidence_incomplete'


def _board_workload_facts(workload_facts, availability):
    """Project only D-055's already-public facts, preserving nulls exactly."""
    facts = workload_facts if isinstance(workload_facts, dict) else {}
    inputs = (availability or {}).get('inputs') or {}
    back_to_back = inputs.get('back_to_back')
    if type(back_to_back) is not bool:
        back_to_back = None
    return {
        'days_since_last_appearance': facts.get('days_since_last_appearance'),
        'appearances_last_7': facts.get('appearances_last_7'),
        'pitches_last_7_days': facts.get('pitches_last_7_days'),
        'back_to_back': back_to_back,
    }


def _unavailable_rest_status(reason_code):
    return {
        'available': False,
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'summary': None,
        'reason_code': reason_code,
    }


def is_valid_rest_status_carrier(value):
    """Return whether ``value`` is one complete governed D-055 public object."""
    if not isinstance(value, dict):
        return False

    expected_fields = {
        'available',
        'active_arm_count',
        'rested_arm_count',
        'worked_yesterday_count',
        'back_to_back_count',
        'summary',
        'reason_code',
    }
    if set(value) != expected_fields:
        return False

    count_fields = (
        'active_arm_count',
        'rested_arm_count',
        'worked_yesterday_count',
        'back_to_back_count',
    )
    if value.get('available') is True:
        return (
            all(type(value.get(field)) is int and value[field] >= 0 for field in count_fields)
            and isinstance(value.get('summary'), str)
            and bool(value['summary'].strip())
            and value.get('reason_code') is None
        )
    if value.get('available') is False:
        return (
            all(value.get(field) is None for field in count_fields)
            and value.get('summary') is None
            and isinstance(value.get('reason_code'), str)
            and bool(value['reason_code'].strip())
        )
    return False


def _arm_word(count):
    return 'arm' if count == 1 else 'arms'


def build_rest_status(cards, *, counts_withheld=False, board_context_unavailable=False):
    """Author the D-055 Rest Status from represented active Team Board cards.

    ``days_since_last_appearance >= 2`` means at least one full calendar day
    elapsed between the last appearance and the board availability date;
    ``== 1`` means the pitcher worked yesterday. ``back_to_back`` is reused as
    the existing governed availability boolean and is not recalculated here.
    """
    if board_context_unavailable:
        return _unavailable_rest_status(REST_STATUS_BOARD_CONTEXT_UNAVAILABLE)
    if counts_withheld:
        return _unavailable_rest_status(REST_STATUS_ROSTER_CONTEXT_UNAVAILABLE)

    active_cards = [
        card for card in list(cards or [])
        if (card.get('visibility') or {}).get('is_visible_by_default', True)
    ]
    if not active_cards:
        return _unavailable_rest_status(REST_STATUS_NO_ELIGIBLE_ARMS)

    for card in active_cards:
        facts = card.get('workload_facts') or {}
        days_since = facts.get('days_since_last_appearance')
        back_to_back = facts.get('back_to_back')
        if (
            card.get('data_state') != 'fresh'
            or type(days_since) is not int
            or days_since < 0
            or type(back_to_back) is not bool
        ):
            return _unavailable_rest_status(
                REST_STATUS_WORKLOAD_EVIDENCE_INCOMPLETE
            )

    active_count = len(active_cards)
    rested_count = sum(
        card['workload_facts']['days_since_last_appearance'] >= 2
        for card in active_cards
    )
    worked_yesterday_count = sum(
        card['workload_facts']['days_since_last_appearance'] == 1
        for card in active_cards
    )
    back_to_back_count = sum(
        card['workload_facts']['back_to_back'] is True
        for card in active_cards
    )
    summary = (
        f'{rested_count} of {active_count} active bullpen {_arm_word(active_count)} '
        f'{"has" if rested_count == 1 else "have"} at least one full day of rest; '
        f'{worked_yesterday_count} {_arm_word(worked_yesterday_count)} worked yesterday '
        f'and {back_to_back_count} {_arm_word(back_to_back_count)} worked back-to-back.'
    )
    return {
        'available': True,
        'active_arm_count': active_count,
        'rested_arm_count': rested_count,
        'worked_yesterday_count': worked_yesterday_count,
        'back_to_back_count': back_to_back_count,
        'summary': summary,
        'reason_code': None,
    }


def _board_cards(records):
    return [
        build_card(
            name=record.get('name'),
            pitcher_id=record.get('pitcher_id'),
            fatigue_score=record.get('fatigue_score'),
            availability=record.get('availability'),
            role=record.get('role'),
            eligibility=record.get('eligibility'),
            roster_status=record.get('roster_status'),
            visibility=record.get('visibility'),
            pitcher_labels=record.get('pitcher_labels'),
            public_role_read=record.get('public_role_read'),
            last_appearance=record.get('last_appearance'),
            last_workload_appearance=record.get('last_workload_appearance'),
            workload_facts=record.get('workload_facts'),
        )
        for record in records
    ]


def author_rest_status(records, *, freshness=None, roster_authority=None):
    """Author D-055 once from the existing governed publication inputs."""
    cards = _board_cards(list(records or []))
    return build_rest_status(
        cards,
        counts_withheld=_roster_counts_withheld(roster_authority),
        board_context_unavailable=bool(
            (freshness or {}).get('fail_closed') is True
            or (freshness or {}).get('degradation_state') == 'unavailable'
            or (freshness or {}).get('freshness_state') == 'metadata_unavailable'
        ),
    )


def build_card(
    name,
    pitcher_id,
    fatigue_score,
    availability,
    role=None,
    eligibility=None,
    roster_status=None,
    visibility=None,
    pitcher_labels=None,
    public_role_read=None,
    last_appearance=None,
    last_workload_appearance=None,
    workload_facts=None,
):
    """Build a single display card from existing availability output.

    ``fatigue_score`` is accepted because the availability read behind the card
    is derived from it, but it is deliberately NOT part of the card. The board
    is a de-scored public surface: it publishes the availability status, the
    authored role/read labels, the short reason, and the last appearance —
    never the internal 0-100 composite (SEC-001).
    """
    availability = availability or {}

    workload_appearance = (
        last_workload_appearance
        if last_workload_appearance is not None
        else last_appearance
    )

    authored_labels = pitcher_labels or build_pitcher_labels(
        availability=availability,
        role=role,
        eligibility=eligibility,
        roster_status=roster_status,
    )

    return {
        'pitcher_id': pitcher_id,
        'name': name,
        # Engine state, kept for internal consumers and existing contracts.
        'availability_status': availability.get('availability_status'),
        # The reader-facing form of that state, decided by the backend public
        # vocabulary authority. The frontend renders this and owns no mapping.
        'availability_public_label': public_availability_label(
            availability.get('availability_status')
        ),
        'confidence': availability.get('confidence'),
        'short_reason': short_reason_for(availability),
        'last_appearance': workload_appearance,
        'last_workload_appearance': workload_appearance,
        'workload_facts': _board_workload_facts(workload_facts, availability),
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
        # Public role/read chips are authored on the backend so frontend
        # consumers render them without re-deriving classification.
        'pitcher_labels': authored_labels,
        # The one backend-authored public role conclusion. It owns both the
        # role chip and the expanded Usage Role headline, so the disclosure
        # can never assert a concrete role the public authority rejected.
        # None when no observed-role classification exists for the card.
        'public_role_read': public_role_read or (
            author_public_role_read(role, authored_labels) if role is not None else None
        ),
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


def _roster_counts_withheld(roster_authority):
    readiness = (roster_authority or {}).get('readiness') or {}
    return readiness.get('counts_withheld') is True or (
        readiness and not roster_claims_available(readiness)
    )


def _withhold_group_counts(groups):
    return [
        {
            **group,
            'count': None,
            'count_withheld': True,
            'description': (
                'Recent workload evidence is available; current usable depth is '
                'withheld until roster status is verified.'
            ),
        }
        for group in groups
    ]


def _withhold_team_shape(team_shape, roster_authority):
    readiness = (roster_authority or {}).get('readiness') or {}
    result = dict(team_shape or {})
    limitations = list(result.get('limitations') or [])
    for item in readiness.get('reader_limitations') or []:
        if item not in limitations:
            limitations.append(item)
    result.update({
        'current_roster_claims_available': False,
        'counts_withheld': True,
        'reads': [],
        # build_team_bullpen_shape returns the camelCase 'byKey'; clearing only
        # 'by_key' left the withheld reads readable on the served payload, and
        # the reader surfaces resolve byKey first.
        'byKey': {},
        'by_key': {},
        'limitations': limitations,
    })
    return result


def _withhold_team_context(context, roster_authority):
    readiness = (roster_authority or {}).get('readiness') or {}
    limitations = list((context or {}).get('limitations') or [])
    for item in readiness.get('reader_limitations') or []:
        if item not in limitations:
            limitations.append(item)
    return {
        'metrics': {
            'total_relievers': None,
            'available': None,
            'monitor': None,
            'limited': None,
            'avoid': None,
            'unavailable': None,
            'restricted': None,
            'pct_available': None,
            'pct_unavailable': None,
            'pct_restricted': None,
        },
        'health': {
            'state': 'no_data',
            'label': 'Roster status unverified',
            'reasons': list(readiness.get('reader_limitations') or []),
        },
        'confidence': 'low',
        'limitations': limitations,
        'current_roster_claims_available': False,
        'counts_withheld': True,
    }


def _withhold_bullpen_stress(stress, roster_authority):
    readiness = (roster_authority or {}).get('readiness') or {}
    return {
        **(stress or {}),
        'state': 'no_data',
        'label': 'Roster status unverified',
        'summary': (
            'Recent workload evidence is available, but current usable bullpen '
            'depth is withheld until roster status is verified.'
        ),
        'confidence': 'low',
        'reason_codes': list(readiness.get('reason_codes') or []),
        'limitations': list(readiness.get('reader_limitations') or []),
        'tone': 'muted',
        'current_roster_claims_available': False,
        'counts_withheld': True,
    }


def build_board_payload(
    team,
    records,
    freshness=None,
    limitations=None,
    roster_authority=None,
    generated_at=None,
    workload_concentration=None,
    capacity_intelligence=None,
    rotation_support_pressure=None,
    bullpen_stability=None,
    bullpen_environment=None,
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
    records = list(records or [])
    cards = _board_cards(records)
    # The internal composite stays on this side of the boundary: the authored
    # team-shape reads are derived from it, the published payload never is.
    fatigue_by_pitcher = {
        record.get('pitcher_id'): record.get('fatigue_score')
        for record in records
        if record.get('pitcher_id') is not None
    }
    groups = group_cards(cards)
    counts_withheld = _roster_counts_withheld(roster_authority)
    board_context_unavailable = bool(
        (freshness or {}).get('fail_closed') is True
        or (freshness or {}).get('degradation_state') == 'unavailable'
        or (freshness or {}).get('freshness_state') == 'metadata_unavailable'
    )
    rest_status = build_rest_status(
        cards,
        counts_withheld=counts_withheld,
        board_context_unavailable=board_context_unavailable,
    )
    grouped_total = None if counts_withheld else sum(group['count'] for group in groups)
    generated = generated_at or datetime.now(timezone.utc).isoformat()
    context = build_team_context(groups, freshness=freshness)
    stress = build_bullpen_stress(context)
    team_shape = build_team_bullpen_shape(
        groups,
        context=context,
        workload_concentration=workload_concentration,
        capacity_intelligence=capacity_intelligence,
        bullpen_environment=bullpen_environment,
        fatigue_by_pitcher=fatigue_by_pitcher,
    )
    visibility = summarize_visibility(cards)
    if counts_withheld:
        groups = _withhold_group_counts(groups)
        context = _withhold_team_context(context, roster_authority)
        stress = _withhold_bullpen_stress(stress, roster_authority)
        team_shape = _withhold_team_shape(team_shape, roster_authority)

    # Publication boundary for the board payload: the reader-facing group labels
    # and the authored team-shape reads are guarded before anything is returned,
    # so unsafe public prose is refused rather than partially published.
    guard_board_groups(groups)
    guard_team_shape_reads(team_shape)

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
        'team_shape': team_shape,
        'capacity_intelligence': capacity_intelligence or {},
        'rotation_support_pressure': rotation_support_pressure or {},
        'bullpen_stability': bullpen_stability or {},
        'bullpen_environment': bullpen_environment or {},
        'visibility': visibility,
        'rest_status': rest_status,
        'groups': groups,
        'total_pitchers': grouped_total,
        'ungrouped_pitchers': None if counts_withheld else max(len(cards) - grouped_total, 0),
        'freshness': freshness or {},
        # Roster Authority is the single source of roster truth (CRC). The legacy
        # roster_status board summary was retired in CRC-10; this is the only
        # roster-context payload, and it is invariant across board views.
        'roster_authority': roster_authority or {},
        'limitations': list(limitations or []),
    }
