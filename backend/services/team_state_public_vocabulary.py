"""Canonical BaseballOS public vocabulary for Team State Share Artifacts (SC-04B).

The single backend-owned owner of the reader-facing public language used by a
public Team State Share Card and the ``/share/{public_id}`` page:

* the public Team State dictionary (Product Vision Specification, section 2);
* the one canonical internal-readiness-code -> public-state map;
* the reader-facing evidence display-label map for governed evidence families;
* the fail-closed public-copy banned-language guard.

Internal Team Operations status codes and evidence enums remain unchanged and
internal. Nothing here title-cases an internal enum into public prose, and no
snake_case internal token is ever allowed to reach a public field.

Founder vocabulary decision (final, resolves the Workstream A halt):

* The Product Vision public Team State dictionary is authoritative:
  ``Fresh`` / ``Stretched`` / ``Vulnerable``.
* The deterministic mapping is::

      operationally_stable       -> Fresh
      operationally_constrained  -> Stretched
      operationally_stressed     -> Vulnerable

* ``data_limited`` and ``refused`` receive NO public Team State: they are not
  eligible for public publication (SC-02 eligibility already refuses them), and
  building public copy for an unmapped internal state fails closed here.
* No fourth public Team State is introduced; growth of the public dictionary is
  a separate reviewed product decision.
"""

from __future__ import annotations

import re
from typing import Mapping, Optional


# ---------------------------------------------------------------------------
# Public Team State dictionary (Product Vision Specification, section 2).
# ---------------------------------------------------------------------------

PUBLIC_STATE_FRESH = 'fresh'
PUBLIC_STATE_STRETCHED = 'stretched'
PUBLIC_STATE_VULNERABLE = 'vulnerable'

PUBLIC_STATE_LABELS = {
    PUBLIC_STATE_FRESH: 'Fresh',
    PUBLIC_STATE_STRETCHED: 'Stretched',
    PUBLIC_STATE_VULNERABLE: 'Vulnerable',
}

# The one canonical internal-readiness-code -> public-state map (founder final).
# Internal codes are NOT modified; only the publishable subset is mapped.
INTERNAL_TO_PUBLIC_STATE = {
    'operationally_stable': PUBLIC_STATE_FRESH,
    'operationally_constrained': PUBLIC_STATE_STRETCHED,
    'operationally_stressed': PUBLIC_STATE_VULNERABLE,
}
# ``data_limited`` and ``refused`` are deliberately absent -> not publishable.


class UnmappedTeamStateError(Exception):
    """Raised when an internal status has no public Team State (fail closed).

    Building public copy from ``data_limited``/``refused``/an unknown status must
    never invent a public state or title-case an internal enum; it fails closed.
    """


def is_publishable_state(status_code) -> bool:
    """True only for an internal status that maps to a public Team State."""
    return status_code in INTERNAL_TO_PUBLIC_STATE


def public_state_for(status_code) -> dict:
    """Return ``{'public_code', 'public_label'}`` for a publishable status.

    Fails closed with :class:`UnmappedTeamStateError` for ``data_limited``,
    ``refused``, or any unknown status — the copy authority never fabricates a
    public state.
    """
    public_code = INTERNAL_TO_PUBLIC_STATE.get(status_code)
    if public_code is None:
        raise UnmappedTeamStateError(
            f'internal status {status_code!r} has no public Team State; it is not '
            'eligible for public publication'
        )
    return {'public_code': public_code, 'public_label': PUBLIC_STATE_LABELS[public_code]}


# ---------------------------------------------------------------------------
# Evidence display-label map (Workstream E). Keyed on the internal constraint
# identity (``affected_area`` first, ``category`` fallback). The internal enum
# never reaches the reader; an unknown family uses one reviewed generic label.
# ---------------------------------------------------------------------------

# Governed evidence families the Team Operations readiness contract currently
# emits (see team_operations.bullpen_readiness._constraints).
EVIDENCE_DISPLAY_LABELS = {
    # affected_area (internal enum) -> reader-facing label
    'availability_distribution': 'Available bullpen options',
    'workload_pressure': 'Recent bullpen workload',
    'coverage_inventory': 'Active bullpen coverage',
    'handedness_coverage': 'Bullpen handedness',
    'readiness': 'Data freshness',
    'trust_metadata': 'Read confidence',
    # category fallbacks (used when affected_area is absent or unknown)
    'availability': 'Available bullpen options',
    'workload': 'Recent bullpen workload',
    'coverage': 'Active bullpen coverage',
    'freshness': 'Data freshness',
    'trust': 'Read confidence',
}

# One reviewed generic public label for an unrecognized governed evidence family.
# It never exposes the internal enum.
GENERIC_EVIDENCE_LABEL = 'Bullpen evidence'


def evidence_display_label(affected_area, category=None) -> str:
    """Deterministic reader-facing label for a governed evidence family.

    Prefers the specific ``affected_area`` mapping, falls back to ``category``,
    and finally to one reviewed generic label — never the raw internal enum.
    """
    for key in (affected_area, category):
        if key is not None and key in EVIDENCE_DISPLAY_LABELS:
            return EVIDENCE_DISPLAY_LABELS[key]
    return GENERIC_EVIDENCE_LABEL


# ---------------------------------------------------------------------------
# Public-copy banned-language guard (Workstream F). Fails closed BEFORE
# publication; the copy authority runs it, so bad canonical copy never produces
# an artifact (it is not merely sanitized at render time).
# ---------------------------------------------------------------------------

# Multi-word internal phrasings that must not appear in public copy. Matched
# case-insensitively as substrings (a phrase is unambiguous in a way a single
# ordinary baseball word is not).
_BANNED_PHRASES = (
    'team-level readiness',
    'team-level bullpen readiness',
    'operational inventory',
    'constrained inventory',
    'coverage inventory',
    'elevated team-level',
    'model output',
    'engine says',
    'system says',
    'system determined',
    'based on our analysis',
    'actionable insight',
    'leverage opportunity',
)

# Single internal/telemetry words banned on a word boundary so ordinary baseball
# language is never over-banned. (``leverage`` and ``edge`` are legitimate
# baseball words and are NOT banned as bare words — only in the phrases above.)
_BANNED_WORDS = (
    'payload',
    'algorithm',
    'actionable',
    'optimization',
    'optimized',
    'telemetry',
)

# Any snake_case internal token (two+ segments joined by underscores) is treated
# as a leaked enum and rejected outright.
_SNAKE_CASE_RE = re.compile(r'[a-z0-9]+_[a-z0-9_]+')
_WORD_RES = {word: re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE) for word in _BANNED_WORDS}


class PublicCopyGuardError(Exception):
    """Typed fail-closed refusal for a banned term in a public copy field.

    The copy authority raises this BEFORE an artifact is built, so no artifact is
    ever published carrying internal engine vocabulary in a public field.
    """

    def __init__(self, field: str, term: str, value: str):
        self.field = field
        self.term = term
        self.value = value
        super().__init__(
            f'public copy field {field!r} contains banned public language '
            f'{term!r}: {value!r}'
        )


def _iter_strings(field: str, value):
    """Yield ``(field, string)`` pairs from a str / list / mapping public field."""
    if value is None:
        return
    if isinstance(value, str):
        yield field, value
    elif isinstance(value, Mapping):
        for key, item in value.items():
            yield from _iter_strings(f'{field}.{key}', item)
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            yield from _iter_strings(f'{field}[{index}]', item)


def find_banned_public_language(field: str, value) -> Optional[tuple]:
    """Return ``(field, term)`` for the first banned term found, or ``None``.

    Checks banned phrases (substring), banned words (word boundary), and any
    leaked snake_case internal token. Deterministic; order is stable.
    """
    for field_path, text in _iter_strings(field, value):
        lowered = text.lower()
        for phrase in _BANNED_PHRASES:
            if phrase in lowered:
                return field_path, phrase
        for word, pattern in _WORD_RES.items():
            if pattern.search(text):
                return field_path, word
        snake = _SNAKE_CASE_RE.search(lowered)
        if snake:
            return field_path, snake.group(0)
    return None


# The plain-string public copy fields the guard protects (Workstream F).
GUARDED_PUBLIC_COPY_FIELDS = (
    'state_label',
    'headline',
    'why',
    'freshness_line',
    'trust_line',
    'limitations',
    'alt_text',
    'description',
)

# The reader-facing sub-fields of each evidence receipt that the guard protects.
# Internal identifiers (``evidence_id``, ``kind``) are intentionally excluded:
# they are legitimately snake_case internal keys and never reach the reader.
GUARDED_EVIDENCE_FIELDS = ('label', 'detail')


def _raise_if_banned(field: str, value) -> None:
    hit = find_banned_public_language(field, value)
    if hit is not None:
        field_path, term = hit
        offending = next(
            (text for path, text in _iter_strings(field, value) if path == field_path),
            '',
        )
        raise PublicCopyGuardError(field_path, term, offending)


def guard_public_copy(copy: Mapping) -> None:
    """Fail closed if any guarded public copy field contains banned language.

    Raises :class:`PublicCopyGuardError` on the first violation. Only the
    reader-facing public fields are checked; internal codes, evidence ids, and
    logs may keep technical vocabulary.
    """
    for field in GUARDED_PUBLIC_COPY_FIELDS:
        if field in copy:
            _raise_if_banned(field, copy[field])

    # Evidence receipts: only the reader-facing label + detail are public copy.
    for index, item in enumerate(copy.get('evidence') or ()):
        if not isinstance(item, Mapping):
            continue
        for sub in GUARDED_EVIDENCE_FIELDS:
            if sub in item:
                _raise_if_banned(f'evidence[{index}].{sub}', item[sub])
