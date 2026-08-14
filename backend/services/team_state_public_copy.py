"""Deterministic, backend-owned canonical copy authority for Team State cards.

Share Cards SC-04B. This is the single authority that turns *governed immutable
facts* into the reader-facing public copy an immutable Team State Share Artifact
carries: public state, headline, why sentence, evidence display labels + receipt
copy, freshness language, trust line, limitation copy, alt text, and a
platform-neutral description.

It is pure and deterministic: identical governed input produces byte-identical
copy. It uses NO AI, calls NO external language service, infers no manager
intent, predicts no usage or outcomes, uses no betting/fantasy framing, makes no
injury claims, and never embellishes beyond the governed evidence. It describes
only evidence already selected into the artifact — it is not a second evidence
selector, state calculator, or trust engine. All public vocabulary comes from
:mod:`services.team_state_public_vocabulary`, and the fail-closed banned-language
guard runs here so bad canonical copy never produces an artifact.

The visible published-time stamp is intentionally NOT baked into the immutable
copy (it is not known at build time and would break determinism/equivalence);
the public page formats ``published_at`` at read time with the shared Eastern
Time formatter. The artifact owns the freshness *language*; the frontend formats
approved timestamps.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Mapping, Optional, Sequence

from services.team_state_public_vocabulary import (
    evidence_display_label,
    find_banned_public_language,
    guard_public_copy,
    public_state_for,
)


PUBLIC_COPY_CONTRACT = 'baseballos.share_card.team_state.public_copy'

_MONTHS = (
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
)
_NUMBER_WORDS = (
    'zero', 'one', 'two', 'three', 'four', 'five',
    'six', 'seven', 'eight', 'nine',
)

# Coarse governed evidence families used for deterministic why-sentence selection.
_FAMILY_WORKLOAD = 'workload'
_FAMILY_AVAILABILITY = 'availability'
_FAMILY_COVERAGE = 'coverage'
_FAMILY_HANDEDNESS = 'handedness'
_FAMILY_FRESHNESS = 'freshness'
_FAMILY_TRUST = 'trust'

# affected_area (internal enum) -> coarse family for why selection.
_AFFECTED_AREA_FAMILY = {
    'workload_pressure': _FAMILY_WORKLOAD,
    'availability_distribution': _FAMILY_AVAILABILITY,
    'coverage_inventory': _FAMILY_COVERAGE,
    'handedness_coverage': _FAMILY_HANDEDNESS,
    'readiness': _FAMILY_FRESHNESS,
    'trust_metadata': _FAMILY_TRUST,
}


def _format_date(value: Any) -> Optional[str]:
    """Deterministic, locale-independent ``Month D, YYYY`` for a date-only value."""
    parsed = _coerce_date(value)
    if parsed is None:
        return None
    return f'{_MONTHS[parsed.month - 1]} {parsed.day}, {parsed.year}'


def _coerce_date(value: Any) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError:
            return None
    return None


def _number_word(count: Any, *, capitalized: bool = False) -> str:
    try:
        n = int(count)
    except (TypeError, ValueError):
        return str(count)
    word = _NUMBER_WORDS[n] if 0 <= n < len(_NUMBER_WORDS) else str(n)
    return word.capitalize() if capitalized else word


def _plural(count: Any, singular: str, plural: str) -> str:
    try:
        return singular if int(count) == 1 else plural
    except (TypeError, ValueError):
        return plural


def _possessive(name: str) -> str:
    """Grammatically correct possessive (team names usually end in ``s``)."""
    name = (name or '').strip() or 'The team'
    return f"{name}'" if name[-1] in ('s', 'S') else f"{name}'s"


# ---------------------------------------------------------------------------
# Team language — sentence grammar only.
#
# This is NOT team identity: it never edits a stored display name, and every
# form is derived from the name it is given. Two defects lived here.
#
# 1. The bare club name was used as a sentence subject ("New York Yankees is
#    missing a few bullpen arms, narrowing its clean options"). Club names take
#    plural agreement, so that sentence disagreed with itself twice.
# 2. Composed fields named the club twice in adjacent clauses ("New York
#    Yankees' bullpen is Fresh. New York Yankees' bullpen has a full set...").
#
# Both are fixed by construction rather than by repairing rendered text: the
# why sentence is written around a possessive SLOT, and the composer decides
# whether that slot takes a first reference or a second one. The possessive
# frame is also number-neutral, so no subject-verb agreement can be got wrong.
# ---------------------------------------------------------------------------

# The second-reference possessive. English gives collective club names plural
# agreement ("the Yankees are"), so the plural possessive pronoun is correct for
# every club name and needs no per-team table.
_SECOND_REFERENCE_POSSESSIVE = 'Their'


def team_possessive(team_name: str) -> str:
    """First-reference possessive with its article: ``the New York Yankees'``.

    The article is what makes the club name read as a noun phrase in running
    prose. Sentence-initial capitalisation is applied by the caller's frame.
    """
    name = (team_name or '').strip()
    if not name:
        return 'The team’s'.replace('’', "'")
    return f'the {_possessive(name)}'


def _sentence_case(text: str) -> str:
    """Capitalise the first character without touching the rest of the string."""
    return f'{text[:1].upper()}{text[1:]}' if text else text


def _family_of(constraint: Mapping) -> Optional[str]:
    affected = constraint.get('affected_area')
    if affected in _AFFECTED_AREA_FAMILY:
        return _AFFECTED_AREA_FAMILY[affected]
    return {
        'workload': _FAMILY_WORKLOAD,
        'availability': _FAMILY_AVAILABILITY,
        'coverage': _FAMILY_COVERAGE,
        'freshness': _FAMILY_FRESHNESS,
        'trust': _FAMILY_TRUST,
    }.get(constraint.get('category'))


# ---------------------------------------------------------------------------
# Evidence receipt copy — reader-facing, faithful to the governed count. Never
# reuses the engine ``message`` and never exposes the internal enum.
# ---------------------------------------------------------------------------

# What each counted family says when its governed count is unusable. Each still
# names the real evidence family; none of them invents a number.
_UNCOUNTED_EVIDENCE_DETAIL = {
    'workload_pressure': 'Relievers are carrying elevated recent workload.',
    'availability_distribution': 'Relievers are limited or unavailable.',
    'coverage_inventory': 'Active bullpen records are missing current data.',
    'handedness_coverage': 'Active relievers are missing throwing-hand data.',
}


def _countable(count) -> Optional[int]:
    """The governed count as a non-negative int, or ``None`` if it is not one.

    A missing or malformed count used to be interpolated straight into public
    copy, which published the literal ``None relievers are limited or
    unavailable.`` The canonical readiness authority only emits positive counts,
    so this is the legacy/stored path talking; either way an unusable count now
    falls back to a countless sentence rather than printing a Python value at a
    reader.
    """
    if isinstance(count, bool) or not isinstance(count, int):
        return None
    return count if count >= 0 else None


def _evidence_detail(affected_area, count) -> str:
    countable = _countable(count)
    if countable is None and affected_area in (
        'workload_pressure',
        'availability_distribution',
        'coverage_inventory',
        'handedness_coverage',
    ):
        return _UNCOUNTED_EVIDENCE_DETAIL[affected_area]
    if affected_area == 'workload_pressure':
        return (
            f'{count} {_plural(count, "reliever is", "relievers are")} carrying '
            'elevated recent workload.'
        )
    if affected_area == 'availability_distribution':
        return (
            f'{count} {_plural(count, "reliever is", "relievers are")} limited or '
            'unavailable.'
        )
    if affected_area == 'coverage_inventory':
        return (
            f'{count} active bullpen {_plural(count, "record is", "records are")} '
            'missing current data.'
        )
    if affected_area == 'handedness_coverage':
        return (
            f'{count} active {_plural(count, "reliever is", "relievers are")} missing '
            'throwing-hand data.'
        )
    if affected_area == 'readiness':
        return 'Recent workload data is not fully current.'
    if affected_area == 'trust_metadata':
        return 'The current read is limited by the available data.'
    if isinstance(count, int) and count > 0:
        return f'{count} bullpen {_plural(count, "record is", "records are")} noted.'
    return 'Additional bullpen context is recorded.'


def build_evidence_receipts(constraints: Sequence[Mapping]) -> list:
    """Reader-facing evidence receipts from governed constraint rows.

    Deterministic and faithful to the governed ``count``; never reuses the engine
    ``message`` and never exposes the internal ``affected_area`` enum. Shared by
    the copy authority (new artifacts) and the public read service (version-aware
    presentation of legacy coded evidence) so there is one owner of the mapping.
    """
    receipts = []
    for constraint in constraints or ():
        if not isinstance(constraint, Mapping):
            continue
        affected = constraint.get('affected_area')
        category = constraint.get('category')
        count = constraint.get('count')
        receipts.append({
            'evidence_id': constraint.get('constraint_id'),
            'kind': category,
            'label': evidence_display_label(affected, category),
            'detail': _evidence_detail(affected, count),
            'severity': constraint.get('severity'),
            'count': count,
        })
    return receipts


# ---------------------------------------------------------------------------
# Why sentence — state-specific, evidence-aware, deterministic. Describes only
# the evidence already present; names a baseball cause; never repeats the state
# label; never predicts.
# ---------------------------------------------------------------------------


def _relievers(count: int) -> str:
    return f'{count} {_plural(count, "reliever", "relievers")}'


def _why_template(public_code: str, families: frozenset, counts: Mapping) -> str:
    """The one why sentence this evidence earns, as a ``{owns}`` template.

    Selection is deterministic and driven only by evidence already governed and
    already present on the artifact: the public state, the coarse constraint
    families, and each family's governed ``count``. It invents no metric, reads
    no new source, and adds no randomness or synonym pool — the sentence changes
    only when the evidence changes.

    A template rather than a finished sentence because the same claim is
    rendered twice on an artifact (as the standalone ``why``, and again inside
    the composed description) and those two renderings must never drift apart.
    One selection, two referring expressions.

    Family precedence is fixed, most bullpen-specific first: arms actually out,
    then arms carrying workload, then incomplete bullpen data, then a limited
    read. Ties cannot occur because the first matching family wins.
    """
    unavailable = counts.get(_FAMILY_AVAILABILITY)
    workload = counts.get(_FAMILY_WORKLOAD)
    data_gap = _FAMILY_COVERAGE in families or _FAMILY_HANDEDNESS in families
    limited_read = _FAMILY_FRESHNESS in families or _FAMILY_TRUST in families

    if public_code == 'vulnerable':
        if unavailable:
            return (
                f'{{owns}} bullpen is down {_relievers(unavailable)}, leaving fewer '
                'clean options available.'
            )
        if workload:
            return (
                f'{{owns}} bullpen has {_relievers(workload)} carrying elevated '
                'recent workload, leaving fewer clean options available.'
            )
        return '{owns} bullpen has fewer clean options available after recent work.'

    if public_code == 'stretched':
        if workload:
            return (
                f'{{owns}} bullpen has {_relievers(workload)} carrying elevated '
                'recent workload, narrowing its clean options.'
            )
        if unavailable:
            return (
                f'{{owns}} bullpen is missing {_relievers(unavailable)}, narrowing '
                'its clean options.'
            )
        return '{owns} clean bullpen options are narrower than usual.'

    # Fresh. Previously one sentence for every Fresh club in the league, no
    # matter what its evidence said. A Fresh read still carries real evidence,
    # and the concessive clause is factual rather than a hedge.
    if unavailable:
        return (
            f'{{owns}} bullpen has a full set of clean options, with '
            f'{_relievers(unavailable)} limited or unavailable.'
        )
    if workload:
        return (
            f'{{owns}} bullpen has a full set of clean options, with '
            f'{_relievers(workload)} carrying elevated recent workload.'
        )
    if data_gap:
        return (
            '{owns} bullpen has a full set of clean options, with some current '
            'bullpen data still incomplete.'
        )
    if limited_read:
        return (
            '{owns} bullpen has a full set of clean options, on a read limited by '
            'the available data.'
        )
    return (
        '{owns} bullpen has a full set of clean options, with no heavy recent '
        'workload.'
    )


# ---------------------------------------------------------------------------
# Trust + limitation copy.
# ---------------------------------------------------------------------------


def _trust_line(confidence: str) -> str:
    if confidence == 'high':
        return 'Verified from the current active bullpen and completed recent appearances.'
    if confidence == 'medium':
        return 'Based on the current active bullpen and its completed recent appearances.'
    return 'Based on the available current bullpen evidence.'


def _partial_coverage_limitation(coverage: Mapping) -> Optional[str]:
    """The founder-approved bounded partial-coverage disclosure, from counts.

    Honest and non-speculative: states record counts only, never implies an
    unresolved pitcher is available, never names a pitcher, never asserts intent.
    """
    try:
        active = int(coverage['active_bullpen_count'])
        usable = int(coverage['usable_record_count'])
        unresolved = int(coverage['unresolved_record_count'])
    except (KeyError, TypeError, ValueError):
        return None
    if unresolved <= 0:
        return None
    unresolved_word = _number_word(unresolved, capitalized=True)
    record = _plural(unresolved, 'record', 'records')
    remain = _plural(unresolved, 'remains', 'remain')
    return (
        f'This read covers {usable} of {active} active bullpen pitchers. '
        f'{unresolved_word} current workload {record} {remain} incomplete.'
    )


def _limitations(coverage: Optional[Mapping], governed_limitations: Sequence) -> list:
    """Reader-facing limitation list; empty when no material limitation exists.

    Prefers the structured active-bullpen coverage disclosure. Any additional
    governed limitation strings are carried through only when they are already
    reader-safe (the banned-language guard is the final arbiter).
    """
    limitations: list = []
    if coverage:
        disclosure = _partial_coverage_limitation(coverage)
        if disclosure:
            limitations.append(disclosure)
    for item in governed_limitations or ():
        text = str(item).strip()
        if not text:
            continue
        # The structured coverage disclosure above supersedes the legacy
        # partial-coverage string; avoid publishing both.
        if 'active bullpen pitchers' in text:
            continue
        # A governed limitation string is legacy engine copy, not copy authored
        # here. Only carry it into the PUBLIC list when it is already reader-safe;
        # the immutable trust.limitations still preserves the original verbatim.
        if find_banned_public_language('limitations', text) is not None:
            continue
        if text not in limitations:
            limitations.append(text)
    return limitations


# ---------------------------------------------------------------------------
# Public builder.
# ---------------------------------------------------------------------------


def build_public_copy(
    *,
    team_name: str,
    team_abbreviation: Optional[str],
    status_code: str,
    confidence: str,
    constraints: Sequence[Mapping],
    limitations: Sequence = (),
    active_bullpen_coverage: Optional[Mapping] = None,
    product_date: Any = None,
) -> dict:
    """Build deterministic public copy for a Team State artifact, or fail closed.

    Fails closed (``UnmappedTeamStateError``) if the internal status has no public
    Team State, and (``PublicCopyGuardError``) if any public field carries banned
    internal language — so no artifact is ever published with leaked engine
    vocabulary. Contains no build-time timestamps; identical governed input
    yields byte-identical copy.
    """
    state = public_state_for(status_code)
    public_code = state['public_code']
    public_label = state['public_label']

    constraints = tuple(constraints or ())
    # Reconcile the public evidence with the confidence. A high/medium read means the
    # canonical active-bullpen coverage authority already deemed the CURRENT active
    # bullpen sufficiently covered, so the coarse whole-``Pitcher.active``
    # coverage_inventory count must not surface as a public "N active bullpen records
    # are missing current data" receipt that contradicts the "verified / based on the
    # current active bullpen" trust line (production Giants/Angels defect). The precise
    # bounded-coverage caveat for a medium read is carried separately by the canonical
    # ``active_bullpen_coverage`` limitation below. A low/unknown read (refused by SC-02)
    # keeps the coarse caveat. Scoped to the public copy authority only — the shared
    # readiness constraint contract and other surfaces are unchanged.
    if confidence in {'high', 'medium'}:
        constraints = tuple(
            c for c in constraints
            if not (isinstance(c, Mapping) and c.get('affected_area') == 'coverage_inventory')
        )
    families = frozenset(
        family for family in (_family_of(c) for c in constraints if isinstance(c, Mapping))
        if family is not None
    )
    # Governed counts per family, already on the constraint rows. Highest count
    # wins within a family so the sentence describes the whole family, and an
    # unusable count is dropped rather than published.
    counts: dict = {}
    for constraint in constraints:
        if not isinstance(constraint, Mapping):
            continue
        family = _family_of(constraint)
        countable = _countable(constraint.get('count'))
        if family is None or not countable:
            continue
        counts[family] = max(counts.get(family, 0), countable)

    evidence = build_evidence_receipts(constraints)
    # One selection, rendered twice: a first reference for the standalone why
    # and a second reference wherever the club has just been named.
    why_template = _why_template(public_code, families, counts)
    owns = team_possessive(team_name)
    why = _sentence_case(why_template.format(owns=owns))
    why_second_reference = why_template.format(owns=_SECOND_REFERENCE_POSSESSIVE)
    headline = f'{team_name} bullpen — {public_label}'
    trust_line = _trust_line(confidence)
    limitation_copy = _limitations(active_bullpen_coverage, limitations)

    date_display = _format_date(product_date)
    freshness_suffix = f' through {date_display}' if date_display else ''
    freshness_line = f'Reflects the current active bullpen{freshness_suffix}.'

    evidence_labels = ', '.join(item['label'] for item in evidence)
    evidence_clause = f' Evidence: {evidence_labels}.' if evidence_labels else ''
    data_through_sentence = f' Data through {date_display}.' if date_display else ''
    # Both composed fields name the club once and then refer back to it, so no
    # artifact repeats the same club-name phrase in adjacent clauses.
    alt_text = (
        f'{team_name} bullpen is {public_label}. {why_second_reference}'
        f'{evidence_clause}{data_through_sentence}'
    )
    snapshot_sentence = (
        f'A published BaseballOS bullpen snapshot, data through {date_display}.'
        if date_display
        else 'A published BaseballOS bullpen snapshot.'
    )
    description = (
        f'{_sentence_case(team_possessive(team_name))} bullpen is {public_label}. '
        f'{why_second_reference} {snapshot_sentence}'
    )

    copy = {
        'contract': PUBLIC_COPY_CONTRACT,
        'state': state,
        'state_label': public_label,
        'headline': headline,
        'why': why,
        'evidence': evidence,
        'freshness_line': freshness_line,
        'trust_line': trust_line,
        'limitations': limitation_copy,
        'alt_text': alt_text,
        'description': description,
    }

    # Fail closed BEFORE the artifact is built: no banned internal language may
    # reach a public field.
    guard_public_copy(copy)
    return copy
