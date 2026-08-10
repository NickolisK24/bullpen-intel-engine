"""Backend-owned public copy authority for the bullpen State -> Why -> Evidence path.

Companion to :mod:`services.team_state_public_vocabulary`, which owns the public
Team State dictionary. This module owns the other two public-language decisions
the live bullpen reads depend on:

1. **Public availability vocabulary.** The availability engine's internal states
   (``Available`` / ``Monitor`` / ``Limited`` / ``Avoid`` / ``Unavailable``) are
   engine vocabulary. ``Monitor`` and ``Avoid`` are NOT reader vocabulary — the
   public forms are ``On Watch`` and ``Unavailable``. Before FE-001 that mapping
   lived in the browser (``frontend/src/components/bullpen/availabilityView.js``),
   which made the presentation layer the semantic owner of a BaseballOS public
   claim. It lives here now; the frontend renders what this module decides.

2. **The public prose guard.** The Why sentence, its evidence reasons, and the
   limitation lines are meaning-bearing public copy. They are authored from
   static constants and counts, never from user input, so a banned term in a
   guarded field is a code defect and is treated as one: the guard raises before
   the payload is published rather than letting the browser quietly repair it.

Nothing here changes which availability state a pitcher is in, which bullpen
health state is chosen, any threshold, or any count. It decides only what those
already-decided states are *called* in public and refuses prose that leaks
engine vocabulary.

Scope note: the guard runs over PUBLIC PROSE FIELDS ONLY. Internal structured
keys (``pct_restricted``, ``restrictedTrustArms``, the ``constrained`` health
code) are engine data, are never read as sentences, and are deliberately not
subject to the prose ban list.
"""

from __future__ import annotations

import re
from typing import Mapping

from services.team_state_public_vocabulary import PublicCopyGuardError


# ---------------------------------------------------------------------------
# Public availability vocabulary (backend-owned as of FE-001 / #591).
# ---------------------------------------------------------------------------

# Internal availability state -> the reader-facing label. ``Available``,
# ``Limited`` and ``Unavailable`` are already reader-safe and map to themselves;
# ``Monitor`` and ``Avoid`` are engine-only vocabulary with distinct public forms.
PUBLIC_AVAILABILITY_LABELS = {
    'Available': 'Available',
    'Monitor': 'On Watch',
    'Limited': 'Limited',
    'Avoid': 'Unavailable',
    'Unavailable': 'Unavailable',
}

# The complete approved public availability vocabulary. A fourth public status is
# a reviewed product decision, not an implementation detail.
PUBLIC_AVAILABILITY_STATUSES = ('Available', 'On Watch', 'Limited', 'Unavailable')


def public_availability_label(status):
    """Public label for an internal availability state, or ``None``.

    Fails closed: an unrecognised internal state yields no public label rather
    than a title-cased guess at one.
    """
    if not isinstance(status, str):
        return None
    return PUBLIC_AVAILABILITY_LABELS.get(status.strip())


# ---------------------------------------------------------------------------
# Public prose guard.
# ---------------------------------------------------------------------------

# Engine vocabulary that must never reach a reader inside a public sentence.
# Word-boundary matched so ordinary baseball language is never over-banned.
_BANNED_PROSE_WORDS = (
    'avoid',
    'monitor',
    'snapshot',
    'restricted',
    'constrained',
)

_BANNED_PROSE_PHRASES = (
    'recommendation engine',
    'baseline distribution',
    'governance layer',
    'model output',
    'engine says',
    'deterministic',
)

# ``Rest-Restricted`` is an already-governed public pitcher-read label owned by
# services/pitcher_public_labels.py. It is not part of the FE-001 State -> Why ->
# Evidence contract, so the bare-word ``restricted`` ban must not fire on it.
# Retiring or renaming that label is tracked separately from #591.
_ALLOWED_PROSE_TOKENS = ('rest-restricted',)

_WORD_PATTERNS = {
    word: re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
    for word in _BANNED_PROSE_WORDS
}
_PHRASE_PATTERNS = {
    phrase: re.compile(rf'\b{re.escape(phrase)}\b', re.IGNORECASE)
    for phrase in _BANNED_PROSE_PHRASES
}


def _mask_allowed_tokens(text):
    masked = text
    for token in _ALLOWED_PROSE_TOKENS:
        masked = re.sub(re.escape(token), ' ', masked, flags=re.IGNORECASE)
    return masked


def _iter_prose(field, value):
    """Yield ``(field_path, text)`` for every string inside a public prose field."""
    if value is None:
        return
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_prose(f'{field}.{key}', item)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_prose(f'{field}[{index}]', item)


def find_banned_public_prose(field, value):
    """Return ``(field_path, term)`` for the first banned term, or ``None``.

    Deterministic: phrases are checked before bare words, and both in declaration
    order, so the same input always reports the same term.
    """
    for field_path, text in _iter_prose(field, value):
        candidate = _mask_allowed_tokens(text)
        for phrase, pattern in _PHRASE_PATTERNS.items():
            if pattern.search(candidate):
                return field_path, phrase
        for word, pattern in _WORD_PATTERNS.items():
            if pattern.search(candidate):
                return field_path, word
    return None


def guard_public_prose(field, value):
    """Raise :class:`PublicCopyGuardError` if a public prose field leaks vocabulary.

    Fail-closed by design and shared with the Team State copy authority so a copy
    guard failure is one typed refusal across the platform. Every guarded string
    on this path is authored from static constants and counts, so a violation is
    a code defect that CI catches — never a data-driven runtime surprise.
    """
    found = find_banned_public_prose(field, value)
    if found is not None:
        field_path, term = found
        raise PublicCopyGuardError(field_path, term, str(value)[:200])
    return value


# The public prose fields of a board / dashboard context block.
GUARDED_CONTEXT_PROSE_FIELDS = ('label', 'reasons')


def guard_board_context(context):
    """Guard the public prose a board or dashboard ``context`` block publishes.

    Covers the Why (``health.label``), its evidence reasons (``health.reasons``)
    and the trust limitations. Structured metrics and the internal health code
    are untouched.
    """
    if not isinstance(context, Mapping):
        return context

    health = context.get('health')
    if isinstance(health, Mapping):
        for field in GUARDED_CONTEXT_PROSE_FIELDS:
            guard_public_prose(f'context.health.{field}', health.get(field))
    guard_public_prose('context.limitations', context.get('limitations'))
    return context


def guard_team_shape_reads(team_shape):
    """Guard the backend-authored public copy on every team-shape read."""
    if not isinstance(team_shape, Mapping):
        return team_shape

    reads = team_shape.get('reads')
    if isinstance(reads, (list, tuple)):
        for index, read in enumerate(reads):
            if not isinstance(read, Mapping):
                continue
            key = read.get('key') or index
            for field in ('label', 'summary', 'explanation', 'reasons'):
                guard_public_prose(f'team_shape.{key}.{field}', read.get(field))
    return team_shape


def guard_board_groups(groups):
    """Guard the public group labels and descriptions the board publishes."""
    if not isinstance(groups, (list, tuple)):
        return groups
    for group in groups:
        if not isinstance(group, Mapping):
            continue
        status = group.get('status') or 'group'
        guard_public_prose(f'groups.{status}.label', group.get('label'))
        guard_public_prose(f'groups.{status}.description', group.get('description'))
    return groups
