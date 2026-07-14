"""Single role/read label authority for public bullpen surfaces.

This module owns two trust decisions:

1. Which game logs may inform the *observed relief role*: only confirmed
   regular-season relief appearances inside the role window. Starts,
   non-regular-season games, and rows whose start/relief state is unknown are
   excluded and disclosed, never silently assumed to be relief.
2. The one backend-authored public role read per pitcher. The public chip and
   the expanded Usage Role disclosure both consume this read, so a card can
   never chip "Limited Read" while its disclosure asserts a concrete role the
   public authority rejected.

Bullpen-population Role Authority is intentionally untouched: it keeps the
complete start/relief record it needs via ``usage_logs_by_pitcher``.
"""

from services.bullpen_population import usage_logs_by_pitcher
from services.pitcher_public_labels import build_pitcher_labels
from services.pitcher_role import (
    ROLE_LATE,
    ROLE_LONG,
    ROLE_MIDDLE,
    ROLE_SETUP,
    ROLE_WINDOW_DAYS,
    classify_usage_role,
)


# Raw classifier results that assert a concrete bullpen role (as opposed to the
# low/insufficient reads, which are already limited conclusions).
CONCRETE_ROLE_KEYS = frozenset({ROLE_LATE, ROLE_SETUP, ROLE_MIDDLE, ROLE_LONG})

# Public wording for a guarded (rejected) concrete role. Generic by design —
# internal conflict-resolution detail never reaches readers.
GUARDED_PUBLIC_REASON = 'Recent usage does not support one clear bullpen role.'

START_EXCLUDED_LIMITATION = (
    'Starting appearances are excluded from the observed relief role.'
)
NON_REGULAR_SEASON_EXCLUDED_LIMITATION = (
    'Non-regular-season appearances are excluded from the observed relief role.'
)
UNKNOWN_START_EXCLUDED_LIMITATION = (
    'Some recent appearances could not be classified as starts or relief '
    'appearances; the public role uses only appearances with confirmed relief usage.'
)


def _value(obj, key, default=None):
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def role_logs_by_pitcher(pitcher_ids, reference_date=None):
    """Return the bounded role-window logs used by every public role label."""
    return usage_logs_by_pitcher(
        pitcher_ids,
        days=ROLE_WINDOW_DAYS,
        include_stale=False,
        reference_date=reference_date,
    )


def _games_started(log):
    value = getattr(log, 'games_started', None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def qualifying_relief_logs(logs):
    """Split role-window logs into confirmed regular-season relief appearances.

    A log qualifies for the observed relief role only when ALL hold:
    a valid appearance date, ``game_type == 'R'``, and ``games_started == 0``.
    Starts, non-regular-season games, and unknown start states are excluded and
    counted so the exclusion stays auditable. Unknown stays unknown — a row is
    never treated as relief merely because the pitcher reads as a reliever.
    """
    qualifying = []
    exclusions = {
        'starts': 0,
        'unknown_start': 0,
        'non_regular_season': 0,
        'invalid_date': 0,
    }
    for log in logs or []:
        if getattr(log, 'game_date', None) is None:
            exclusions['invalid_date'] += 1
            continue
        game_type = str(getattr(log, 'game_type', '') or '').strip().upper()
        if game_type != 'R':
            exclusions['non_regular_season'] += 1
            continue
        started = _games_started(log)
        if started is None:
            exclusions['unknown_start'] += 1
            continue
        if started != 0:
            exclusions['starts'] += 1
            continue
        qualifying.append(log)
    return qualifying, exclusions


def _count_word(count, noun):
    return f'{count} {noun}' if count == 1 else f'{count} {noun}s'


def _exclusion_evidence(exclusions):
    evidence = []
    if exclusions['starts']:
        evidence.append(
            f"{_count_word(exclusions['starts'], 'starting appearance')} "
            'excluded from the relief-role read'
        )
    if exclusions['non_regular_season']:
        evidence.append(
            f"{_count_word(exclusions['non_regular_season'], 'non-regular-season appearance')} "
            'excluded from the relief-role read'
        )
    if exclusions['unknown_start']:
        evidence.append(
            f"{_count_word(exclusions['unknown_start'], 'appearance')} with unknown start/relief "
            'status excluded from the relief-role read'
        )
    return evidence


def _exclusion_limitations(exclusions):
    limitations = []
    if exclusions['starts']:
        limitations.append(START_EXCLUDED_LIMITATION)
    if exclusions['non_regular_season']:
        limitations.append(NON_REGULAR_SEASON_EXCLUDED_LIMITATION)
    if exclusions['unknown_start'] or exclusions['invalid_date']:
        limitations.append(UNKNOWN_START_EXCLUDED_LIMITATION)
    return limitations


def _merge_unique(existing, additions):
    merged = list(existing or [])
    for item in additions:
        if item not in merged:
            merged.append(item)
    return merged


def author_public_role_read(role, labels):
    """Author the one public role conclusion a pitcher card presents.

    The public label key (already guarded by ``build_pitcher_labels``) is the
    verdict. When it confirms a concrete role, the disclosure headline is the
    matching observed pattern. When the verdict is Limited Read, the headline
    is Limited Read — a rejected concrete classifier result may remain in
    diagnostics, but it is never the public conclusion.
    """
    role = role or {}
    label_payload = dict((labels or {}).get('role') or {})
    public_key = label_payload.get('key') or 'limited_read'
    public_label = label_payload.get('label') or 'Limited Read'
    guarded = public_key == 'limited_read' and role.get('role_key') in CONCRETE_ROLE_KEYS

    if public_key == 'limited_read':
        headline = public_label
        reason = GUARDED_PUBLIC_REASON if guarded else (role.get('short_reason') or GUARDED_PUBLIC_REASON)
        confidence = 'low' if guarded else (role.get('confidence') or 'none')
    else:
        headline = role.get('role') or public_label
        reason = role.get('short_reason')
        confidence = role.get('confidence') or 'none'

    return {
        'kind': 'public_role_read',
        'key': public_key,
        'label': public_label,
        'headline': headline,
        'confidence': confidence,
        'reason': reason,
        'evidence': list(role.get('evidence') or []),
        'limitations': list(role.get('limitations') or []),
        'source': label_payload.get('source') or 'backend',
    }


def author_role_read_labels(record, logs_by_pitcher, reference_date=None):
    """Author observed role, public labels, and the public role read once.

    The observed role is classified from confirmed regular-season relief
    appearances only; excluded rows are disclosed through evidence and
    limitations. Returns ``(role, labels, public_role_read)``.
    """
    pitcher = _value(record, 'pitcher')
    pitcher_id = _value(pitcher, 'id')
    window_logs = (logs_by_pitcher or {}).get(pitcher_id, [])
    relief_logs, exclusions = qualifying_relief_logs(window_logs)

    role = classify_usage_role(relief_logs, reference_date=reference_date)
    role['evidence'] = _merge_unique(role.get('evidence'), _exclusion_evidence(exclusions))
    role['limitations'] = _merge_unique(role.get('limitations'), _exclusion_limitations(exclusions))

    labels = build_pitcher_labels(
        availability=_value(record, 'availability'),
        role=role,
        eligibility=_value(record, 'eligibility'),
        roster_status=_value(record, 'roster_status'),
    )
    return role, labels, author_public_role_read(role, labels)
