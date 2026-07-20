"""Public payload for What Changed Since Yesterday V1."""

from __future__ import annotations

from typing import Any

from services.editorial_voice_contract_v1 import (
    build_comparison_sentence,
    contains_editorial_banned_language,
    count_to_baseball_language,
)
from services.what_changed_since_yesterday import (
    CHANGE_COVERAGE_SAFETY,
    CHANGE_IDENTITY,
    CHANGE_RESOURCE_HEALTH,
    CHANGE_RESTED_OPTIONS,
    CHANGE_TRUST_STRUCTURE,
    CHANGE_USABLE_DEPTH,
    STATUS_AVAILABLE,
    STATE_CHANGES_DETECTED,
    STATE_INSUFFICIENT_CONTEXT,
    STATE_NO_MEANINGFUL_CHANGES,
    build_what_changed_since_yesterday_payload,
)
from services.what_changed_since_yesterday_copy import (
    COPY_FLAG_REPEATED_HEADLINE,
    COPY_FLAG_REPEATED_SUMMARY,
    build_what_changed_public_copy,
)


CAPABILITY = 'what_changed_since_yesterday_public_v1'
DEFAULT_PUBLIC_ITEM_LIMIT = 6
PUBLIC_WORKLOAD_ADDED_LIMIT = 3
VOICE_SURFACE = 'what_changed_public'
_IMPROVEMENT_DIRECTIONS = {'increased', 'improved', 'expanded'}
_TIGHTENING_DIRECTIONS = {'decreased', 'worsened', 'narrowed'}
_RESOURCE_STATE_LABELS = {
    'strong': 'strong',
    'moderate': 'less tight',
    'strained': 'tight',
    'depleted': 'depleted',
    'unknown': 'unknown',
}

# Descriptive movement lanes for the daily briefing. These describe the
# DIRECTION of a team's meaningful movement so the frontend can group cards
# without re-interpreting bullpen state. They are not rankings — teams stay in
# alphabetical order inside every lane, and no lane implies "best" or "worst".
LANE_MORE_BREATHING_ROOM = 'more_breathing_room'
LANE_TIGHTER_TODAY = 'tighter_today'
LANE_STRUCTURE_CHANGED = 'structure_changed'
LANE_OTHER_MEANINGFUL = 'other_meaningful_changes'

_LANE_LABELS = {
    LANE_MORE_BREATHING_ROOM: 'More breathing room',
    LANE_TIGHTER_TODAY: 'Tighter today',
    LANE_STRUCTURE_CHANGED: 'Structure changed',
    LANE_OTHER_MEANINGFUL: 'Other meaningful change',
}

# Trusted-group and identity movement is a change to the SHAPE of the group,
# not to how much room a team has, so it lands in the structure lane regardless
# of direction. Every other change family is a room-direction change.
_STRUCTURAL_LANE_CHANGE_TYPES = {CHANGE_TRUST_STRUCTURE, CHANGE_IDENTITY}


def _public_top_change(changes: list[dict[str, Any]]) -> dict[str, Any] | None:
    for change in changes:
        copy = build_what_changed_public_copy(
            {},
            top_change=change,
            changes=changes,
        )
        if copy.get('public_copy_generated') and not copy.get('copy_review_flags'):
            return change
    return None


def _team_key(team_change: dict[str, Any]) -> str:
    return str(
        team_change.get('team_abbreviation')
        or team_change.get('team_id')
        or team_change.get('team_name')
        or 'team'
    )


def _team_lookup_key(team_change: dict[str, Any] | None) -> str | None:
    if not isinstance(team_change, dict):
        return None
    team_id = team_change.get('team_id') or team_change.get('teamId')
    if team_id is not None:
        return str(team_id)
    abbr = team_change.get('team_abbreviation') or team_change.get('teamAbbreviation')
    return str(abbr).lower() if abbr else None


def _facts(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    facts = item.get('supporting_facts')
    return [
        fact
        for fact in (facts if isinstance(facts, list) else [])
        if isinstance(fact, dict)
    ]


def _int_value(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _rested_counts(
    team_change: dict[str, Any],
    top_change: dict[str, Any],
) -> dict[str, int | None]:
    counts = team_change.get('rested_counts')
    counts = counts if isinstance(counts, dict) else {}
    yesterday = _int_value(counts.get('yesterday_rested_count'))
    today = _int_value(counts.get('today_rested_count'))
    if yesterday is not None and today is not None:
        return {
            'yesterday_rested_count': yesterday,
            'today_rested_count': today,
        }

    for fact in _facts(top_change):
        if fact.get('fact_key') != 'rested_options':
            continue
        return {
            'yesterday_rested_count': _int_value(fact.get('previous_value')),
            'today_rested_count': _int_value(fact.get('current_value')),
        }
    return {
        'yesterday_rested_count': yesterday,
        'today_rested_count': today,
    }


def _workload_by_team(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    workload = payload.get('what_changed_workload') if isinstance(payload, dict) else {}
    by_team = workload.get('by_team_id') if isinstance(workload, dict) else {}
    return {
        str(key): value
        for key, value in (by_team if isinstance(by_team, dict) else {}).items()
        if isinstance(value, dict)
    }


def _public_workload_added(workload_team: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    source = (workload_team or {}).get('workload_added')
    for item in source if isinstance(source, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or item.get('pitcher_name') or '').strip()
        pitches = _int_value(item.get('pitches'))
        if not name or pitches is None:
            continue
        row = {
            'pitcher_id': item.get('pitcher_id'),
            'name': name,
            'pitches': pitches,
        }
        innings = item.get('innings')
        if innings is not None:
            row['innings'] = innings
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (-int(row.get('pitches') or 0), str(row.get('name') or '').lower()),
    )[:PUBLIC_WORKLOAD_ADDED_LIMIT]


def _direction_family(direction: Any) -> str | None:
    normalized = str(direction or '').strip().lower()
    if normalized in _IMPROVEMENT_DIRECTIONS:
        return 'improving'
    if normalized in _TIGHTENING_DIRECTIONS:
        return 'tightening'
    return None


def _rested_direction_family(counts: dict[str, int | None]) -> str | None:
    yesterday = counts.get('yesterday_rested_count')
    today = counts.get('today_rested_count')
    if yesterday is None or today is None or yesterday == today:
        return None
    return 'improving' if today > yesterday else 'tightening'


def _copy_contradicts_visible_counts(
    top_change: dict[str, Any],
    counts: dict[str, int | None],
) -> bool:
    top_direction = _direction_family(top_change.get('change_direction'))
    rested_direction = _rested_direction_family(counts)
    return bool(
        top_direction
        and rested_direction
        and top_direction != rested_direction
    )


def _public_value(value: Any) -> str | int | None:
    if value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).replace(' Coverage Safety', '').replace('_', ' ').strip()
    return text.lower() if text else None


def _resource_value(value: Any) -> str | None:
    normalized = str(value or '').strip().lower()
    return _RESOURCE_STATE_LABELS.get(normalized) or _public_value(value)


def _primary_public_evidence(top_change: dict[str, Any]) -> dict[str, Any] | None:
    change_type = top_change.get('change_type')
    if change_type == CHANGE_RESTED_OPTIONS:
        return None

    facts = _facts(top_change)
    fact = facts[0] if facts else {}
    previous = fact.get('previous_value')
    current = fact.get('current_value')
    if previous is None or current is None:
        return None

    labels = {
        CHANGE_USABLE_DEPTH: 'Full-game routes',
        CHANGE_RESOURCE_HEALTH: 'Resource pool',
        CHANGE_COVERAGE_SAFETY: 'Game-stretch margin',
        CHANGE_TRUST_STRUCTURE: 'Late-inning support arms',
    }
    label = labels.get(change_type)
    if not label:
        return None

    if change_type == CHANGE_RESOURCE_HEALTH:
        previous = _resource_value(previous)
        current = _resource_value(current)
    else:
        previous = _public_value(previous)
        current = _public_value(current)
    if previous is None or current is None:
        return None

    return {
        'label': label,
        'yesterday': previous,
        'today': current,
    }


def _movement_lane(
    top_change: dict[str, Any] | None,
    counts: dict[str, int | None],
) -> str:
    """Classify a team's meaningful movement into one descriptive lane.

    Trusted-group / identity movement is structural. Everything else is a
    room-direction change, and the visible rested-count delta (the card's
    numeric anchor) is preferred so a card's lane always matches what the
    reader sees; the change direction is only a fallback when counts are
    unknown. Unknown direction fails closed into the neutral lane rather than
    forcing a team into a room lane.
    """
    change_type = (top_change or {}).get('change_type')
    if change_type in _STRUCTURAL_LANE_CHANGE_TYPES:
        return LANE_STRUCTURE_CHANGED
    family = _rested_direction_family(counts) or _direction_family(
        (top_change or {}).get('change_direction')
    )
    if family == 'improving':
        return LANE_MORE_BREATHING_ROOM
    if family == 'tightening':
        return LANE_TIGHTER_TODAY
    return LANE_OTHER_MEANINGFUL


def _primary_delta(
    top_change: dict[str, Any] | None,
    counts: dict[str, int | None],
    primary_evidence: dict[str, Any] | None,
    *,
    use_count_aligned: bool,
) -> dict[str, Any] | None:
    """The single numeric or structural movement the card leads with.

    Rested-option movement (the common anchor) carries a signed ``net_delta``;
    structural movement carries a ``previous -> current`` label pair with no
    net number. ``net_delta`` is emitted only when both sides are known so the
    frontend never renders a plus/minus against an unknown value.
    """
    yesterday = counts.get('yesterday_rested_count')
    today = counts.get('today_rested_count')
    rested = None
    if isinstance(yesterday, int) and isinstance(today, int):
        rested = {
            'label': 'Rested relievers',
            'previous': yesterday,
            'current': today,
            'net_delta': today - yesterday,
        }
    change_type = (top_change or {}).get('change_type')
    if use_count_aligned or change_type == CHANGE_RESTED_OPTIONS:
        return rested
    if primary_evidence:
        return {
            'label': primary_evidence.get('label'),
            'previous': primary_evidence.get('yesterday'),
            'current': primary_evidence.get('today'),
            'net_delta': None,
        }
    return rested


def _safe_public_copy(text: str, fallback: str) -> str:
    """Fail closed if future public context trips the shared banned scan."""
    return fallback if contains_editorial_banned_language(text) else text


def _prose_count(count: int | None, singular: str, plural: str | None = None) -> str:
    phrase = count_to_baseball_language(count, singular, plural)
    return phrase or f'a few {plural or singular}'


def _public_sentence(
    *,
    subject: str,
    reason: str,
    consequence: str,
    stable_parts: tuple[Any, ...],
) -> str:
    sentence = build_comparison_sentence(
        subject=subject,
        reason=reason,
        consequence=consequence,
        stable_parts=(VOICE_SURFACE, *stable_parts),
    )
    fallback = build_comparison_sentence(
        subject='The bullpen movement stays descriptive',
        reason='the public read needs a baseball consequence',
        consequence='That keeps the note tied to the game shape',
        stable_parts=(VOICE_SURFACE, 'fallback'),
    )
    return _safe_public_copy(sentence, fallback)


def _public_headline(team_name: str, counts: dict[str, int | None]) -> str:
    yesterday = counts.get('yesterday_rested_count')
    today = counts.get('today_rested_count')
    if yesterday is not None and today is not None:
        if today < yesterday:
            return f'{team_name} has a thinner late-inning cushion today.'
        if today > yesterday:
            return f'{team_name} has more bullpen breathing room today.'
    return f'{team_name} bullpen route is steady today.'


def _public_summary(team_name: str, counts: dict[str, int | None]) -> str:
    yesterday = counts.get('yesterday_rested_count')
    today = counts.get('today_rested_count')
    if yesterday is None or today is None:
        return f'{team_name} has a bullpen change in the current comparison.'
    if today < yesterday:
        lost = _prose_count(yesterday - today, 'rested arm', 'rested arms')
        return _public_sentence(
            subject=f'{team_name} has a thinner late-inning cushion',
            reason=f'the bullpen lost {lost}',
            consequence='That puts more weight on the middle innings',
            stable_parts=(team_name, 'summary', 'down', yesterday, today),
        )
    if today > yesterday:
        gained = _prose_count(today - yesterday, 'rested arm', 'rested arms')
        return _public_sentence(
            subject=f'{team_name} has more breathing room than yesterday',
            reason=f'the bullpen gained {gained}',
            consequence='That creates more ways through a close game',
            stable_parts=(team_name, 'summary', 'up', yesterday, today),
        )
    return f'{team_name} still has a steady bullpen route today.'


def _public_why_it_matters(
    team_name: str,
    counts: dict[str, int | None],
    workload_added: list[dict[str, Any]],
) -> str:
    yesterday = counts.get('yesterday_rested_count')
    today = counts.get('today_rested_count')
    workload_count = len(workload_added)
    if workload_count > 0 and yesterday is not None and today is not None:
        relievers = _prose_count(workload_count, 'reliever', 'relievers')
        relievers_subject = relievers[:1].upper() + relievers[1:]
        if today < yesterday:
            return _public_sentence(
                subject=f'{relievers_subject} carried meaningful workload yesterday',
                reason='the late-inning cushion is thinner tonight',
                consequence='That makes the middle innings matter more',
                stable_parts=(team_name, 'context', 'workload_down', workload_count, yesterday, today),
            )
        if today > yesterday:
            return _public_sentence(
                subject=f'{relievers_subject} took on meaningful workload yesterday',
                reason='the bullpen still has more breathing room than before',
                consequence='That gives the staff more ways to cover tonight',
                stable_parts=(team_name, 'context', 'workload_up', workload_count, yesterday, today),
            )
        return _public_sentence(
            subject=f'{relievers_subject} took on meaningful workload yesterday',
            reason='the clean group held steady overall',
            consequence='That shifts the watch to the arms who did not pitch',
            stable_parts=(team_name, 'context', 'workload_flat', workload_count, today),
        )
    if yesterday is not None and today is not None:
        if today < yesterday:
            return _public_sentence(
                subject='The late-inning cushion is thinner than yesterday',
                reason='the bullpen has less room',
                consequence='That makes the middle innings matter more',
                stable_parts=(team_name, 'context', 'down', yesterday, today),
            )
        if today > yesterday:
            return _public_sentence(
                subject='The bullpen has more breathing room than yesterday',
                reason='the bullpen has more room',
                consequence='That creates more ways through a close game tonight',
                stable_parts=(team_name, 'context', 'up', yesterday, today),
            )
    return 'No meaningful bullpen movement stands out for this club in the current comparison.'


def _public_item(
    team_change: dict[str, Any],
    *,
    workload_team: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    if team_change.get('status') != STATUS_AVAILABLE:
        return None
    changes = list(team_change.get('changes') or [])
    top_change = _public_top_change(changes)
    if not top_change:
        return None

    copy = build_what_changed_public_copy(
        team_change,
        top_change=top_change,
        changes=changes,
    )
    if not copy.get('public_copy_generated') or copy.get('copy_review_flags'):
        return None
    team_name = str(team_change.get('team_name') or 'This club').strip()
    counts = _rested_counts(team_change, top_change)
    workload_added = _public_workload_added(workload_team)
    use_count_aligned_copy = _copy_contradicts_visible_counts(top_change, counts)
    primary_evidence = _primary_public_evidence(top_change)
    lane = _movement_lane(top_change, counts)

    item = {
        'key': f'{_team_key(team_change)}-what-changed',
        'team_id': team_change.get('team_id'),
        'team_name': team_change.get('team_name'),
        'team_abbreviation': team_change.get('team_abbreviation'),
        'movement_lane': lane,
        'movement_label': _LANE_LABELS[lane],
        'primary_delta': _primary_delta(
            top_change,
            counts,
            primary_evidence,
            use_count_aligned=use_count_aligned_copy,
        ),
        'public_headline': (
            _public_headline(team_name, counts)
            if use_count_aligned_copy
            else copy.get('public_headline') or _public_headline(team_name, counts)
        ),
        'public_summary': (
            _public_summary(team_name, counts)
            if use_count_aligned_copy
            else copy.get('public_summary') or _public_summary(team_name, counts)
        ),
        'public_context': _public_why_it_matters(team_name, counts, workload_added),
        'yesterday_rested_count': counts.get('yesterday_rested_count'),
        'today_rested_count': counts.get('today_rested_count'),
        'workload_added': workload_added,
        '_copy_headline': copy.get('public_headline'),
        '_copy_summary': copy.get('public_summary'),
        '_copy_review_flags': list(copy.get('copy_review_flags') or []),
    }
    if primary_evidence:
        item['public_evidence'] = [primary_evidence]
    return item


def _repeated_values(items: list[dict[str, Any]], field: str) -> set[str]:
    counts: dict[str, int] = {}
    for item in items:
        value = item.get(field)
        if not value:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return {
        value
        for value, count in counts.items()
        if count > 1
    }


def _without_private_fields(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in item.items()
        if not key.startswith('_')
    }


def _movement_summary(changes: dict[str, Any]) -> dict[str, Any] | None:
    """League-level movement counts derived from the COMPLETE comparison.

    Counts are taken from every compared team before any public-card display
    limit, so the league orientation stays honest even if some cards are
    withheld. A team is counted as steady only when it was actually compared
    and cleared no meaningful movement — never inferred from a missing or
    withheld team. ``steady_count`` (and the steady team list) are emitted only
    when the whole population was comparable (``counts_complete``); otherwise
    only the proven movement counts are exposed. Returns ``None`` when no
    trusted comparison exists.
    """
    if changes.get('status') != STATUS_AVAILABLE:
        return None

    lane_counts = {lane: 0 for lane in _LANE_LABELS}
    steady_teams = []
    counts_complete = True
    for team in changes.get('teams') or []:
        if team.get('status') != STATUS_AVAILABLE:
            # A team we could not compare cannot be called steady, and its
            # absence makes the league steady count unprovable.
            counts_complete = False
            continue
        team_changes = team.get('changes') or []
        if team_changes:
            representative = _public_top_change(team_changes) or team_changes[0]
            lane = _movement_lane(
                representative,
                _rested_counts(team, representative),
            )
            lane_counts[lane] += 1
        else:
            steady_teams.append(team)

    summary = {
        'meaningful_change_count': sum(lane_counts.values()),
        'more_breathing_room_count': lane_counts[LANE_MORE_BREATHING_ROOM],
        'tighter_today_count': lane_counts[LANE_TIGHTER_TODAY],
        'structure_changed_count': lane_counts[LANE_STRUCTURE_CHANGED],
        'other_meaningful_change_count': lane_counts[LANE_OTHER_MEANINGFUL],
        'counts_complete': counts_complete,
    }
    if counts_complete:
        summary['steady_count'] = len(steady_teams)
        summary['steady_teams'] = [
            {
                'team_id': team.get('team_id'),
                'team_name': team.get('team_name'),
                'team_abbreviation': team.get('team_abbreviation'),
            }
            for team in sorted(
                steady_teams,
                key=lambda team: (
                    str(team.get('team_abbreviation') or ''),
                    str(team.get('team_name') or ''),
                ),
            )
        ]
    return summary


def _public_state(changes: dict[str, Any], items: list[dict[str, Any]]) -> str:
    if changes.get('status') != STATUS_AVAILABLE:
        return STATE_INSUFFICIENT_CONTEXT
    if items:
        return STATE_CHANGES_DETECTED
    return STATE_NO_MEANINGFUL_CHANGES


def build_what_changed_public_payload(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None,
    *,
    limit: int = DEFAULT_PUBLIC_ITEM_LIMIT,
    consequence_payload: dict[str, Any] | None = None,
    require_trusted_snapshots: bool = False,
    current_snapshot_metadata: dict[str, Any] | None = None,
    prior_snapshot_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a frontend-safe What Changed Since Yesterday V1 payload."""

    changes = build_what_changed_since_yesterday_payload(
        current_payload,
        prior_payload,
        require_trusted_snapshots=require_trusted_snapshots,
        current_snapshot_metadata=current_snapshot_metadata,
        prior_snapshot_metadata=prior_snapshot_metadata,
    )
    # ``consequence_payload`` is retained for compatibility with older tests and
    # callers. This public surface now explains the change from concrete rested
    # counts and observed workload instead of consequence prose.
    workload_by_team = _workload_by_team(current_payload)
    candidate_items = []
    for team_change in changes.get('teams') or []:
        item = _public_item(
            team_change,
            workload_team=workload_by_team.get(str(_team_lookup_key(team_change))),
        )
        if item is None:
            continue
        candidate_items.append(item)

    repeated_headlines = _repeated_values(candidate_items, '_copy_headline')
    repeated_summaries = _repeated_values(candidate_items, '_copy_summary')
    items = []
    for item in candidate_items:
        flags = list(item.get('_copy_review_flags') or [])
        if item.get('_copy_headline') in repeated_headlines:
            flags.append(COPY_FLAG_REPEATED_HEADLINE)
        if item.get('_copy_summary') in repeated_summaries:
            flags.append(COPY_FLAG_REPEATED_SUMMARY)
        if flags:
            continue
        items.append(_without_private_fields(item))
        if len(items) >= limit:
            break

    state = _public_state(changes, items)
    summary = _movement_summary(changes)
    payload = {
        'capability': CAPABILITY,
        'source': 'backend',
        'state': state,
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'ordering_basis': 'team_abbreviation_then_team_name',
        'item_limit': limit,
        'comparison': {
            'current_data_through': changes.get('reference_date'),
            'previous_data_through': changes.get('prior_date'),
            'comparison_available': changes.get('status') == STATUS_AVAILABLE,
            'reason_codes': list(changes.get('reason_codes') or []),
        },
        'items': items,
        'item_count': len(items),
        'limitations': list(changes.get('limitations') or []),
        'reason_codes': list(changes.get('reason_codes') or []),
    }
    # League-level orientation, derived from the complete comparison before any
    # display limit. Omitted entirely when no trusted comparison exists.
    if summary is not None:
        payload['summary'] = summary
    return payload


__all__ = [
    'CAPABILITY',
    'DEFAULT_PUBLIC_ITEM_LIMIT',
    'LANE_MORE_BREATHING_ROOM',
    'LANE_OTHER_MEANINGFUL',
    'LANE_STRUCTURE_CHANGED',
    'LANE_TIGHTER_TODAY',
    'build_what_changed_public_payload',
]
