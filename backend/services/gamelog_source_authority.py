"""Governed source authority for GameLog fields, declared in one place.

A production read-only audit resolved a question that had been implicit since
the two ingestion lanes were built: **which source owns a governed field when
the two sources do not both supply it?**

The audited appearance found:

* completed-game box score — ``balls: 19``, ``strikes: 26``, ``pitches: 45``
  (internally consistent: 19 + 26 = 45);
* player game-log split — ``balls`` absent, same strikes and pitches;
* stored row — ``balls: 20``, internally inconsistent with the same triple.

The split did not contradict the box score. It had nothing to say. And because
``correctable_fields`` compares an optional statistic only when the source
supplies it, the daily correction lane — which reads the split — could never
correct the field, while the box score could always have supplied it. The value
was uncorrectable, not disputed.

The rule this module declares
-----------------------------
``PLAYER_SPLIT_PRIMARY_WITH_BOXSCORE_FALLBACK``

1. A field the split supplies is reconciled from the split, exactly as before.
   Fallback never overrides evidence that exists.
2. A field the split omits or nulls is reported through ``uncomparable_fields``
   — absence is never treated as agreement.
3. For a field with an **explicitly approved** fallback rule, and only then, the
   completed-game box score may supply it.

Approval is per field and deliberately narrow. Making every optional statistic
box-score-authoritative would be a much larger change than the evidence
supports, so the approved set starts at exactly one member.
"""

from __future__ import annotations

import hashlib
import json


AUTHORITY_CONTRACT = 'player_split_primary_with_boxscore_fallback'
AUTHORITY_VERSION = '1'

SOURCE_PLAYER_SPLIT = 'player_game_log_split'
SOURCE_COMPLETED_GAME_BOXSCORE = 'completed_game_boxscore'

# Provenance label for a correction whose value came from the box score rather
# than from the lane's own source. Recording it as ``daily_game_log`` would name
# the wrong authority for the value that was actually written.
CORRECTION_SOURCE_BOXSCORE_FALLBACK = 'completed_game_boxscore_fallback'

# ── Refusal reasons ─────────────────────────────────────────────────────────
# Every refusal is named. A fallback that silently does nothing is
# indistinguishable from one that was never eligible.
REFUSED_FIELD_NOT_APPROVED = 'field_not_approved_for_fallback'
REFUSED_SPLIT_SUPPLIES_FIELD = 'split_supplies_field'
REFUSED_GAME_NOT_FINAL = 'game_not_final'
REFUSED_BOXSCORE_UNAVAILABLE = 'boxscore_unavailable'
REFUSED_NO_PITCHING_LINE = 'no_boxscore_pitching_line'
REFUSED_FIELD_ABSENT_IN_BOXSCORE = 'field_absent_in_boxscore'
REFUSED_COMPANION_ABSENT = 'required_companion_absent'
REFUSED_INCONSISTENT_TRIPLE = 'boxscore_values_inconsistent'
REFUSED_SOURCE_REVISION_MISSING = 'source_revision_missing'
REFUSED_IDENTITY_AMBIGUOUS = 'pitcher_identity_ambiguous'

APPLIED = 'applied'

# What became of a value the fallback supplied. Distinguished because "the row
# was created with it" and "the row already agreed" are different facts, and
# collapsing them would make a realized correction unprovable.
OUTCOME_CORRECTED = 'corrected_existing_row'
OUTCOME_INSERTED = 'inserted_new_row'
OUTCOME_ALREADY_MATCHING = 'stored_value_already_matched'
OUTCOME_NOT_APPLIED = 'not_applied'


class FieldAuthority:
    """One field's declared source authority.

    ``validate`` is what stops a fallback from becoming a blind copy: the box
    score must be internally coherent before its value is trusted.
    """

    def __init__(
        self, *, field, primary_source, fallback_source, source_key,
        required_companions, semantic_rule, validation_rule, validate,
    ):
        self.field = field
        self.primary_source = primary_source
        self.fallback_source = fallback_source
        self.source_key = source_key
        self.required_companions = tuple(required_companions)
        self.semantic_rule = semantic_rule
        self.validation_rule = validation_rule
        self._validate = validate

    def validate(self, stats) -> str | None:
        """Return a refusal reason, or ``None`` when the evidence is usable."""
        return self._validate(stats or {})

    def describe(self) -> dict:
        return {
            'field': self.field,
            'primary_source': self.primary_source,
            'fallback_source': self.fallback_source,
            'source_key': self.source_key,
            'required_companions': list(self.required_companions),
            'semantic_rule': self.semantic_rule,
            'validation_rule': self.validation_rule,
        }


def _int_or_none(value):
    if value is None or value == '':
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_balls(stats) -> str | None:
    """Official pitch accounting must add up before its balls count is used.

    ``balls + strikes == numberOfPitches`` is a *validation* of the official
    triple, never a derivation: the box score's own ``balls`` is the authority,
    and this only refuses a line whose accounting is incoherent. Deriving the
    value instead would invent evidence the source did not give.
    """
    balls = _int_or_none(stats.get('balls'))
    strikes = _int_or_none(stats.get('strikes'))
    pitches = _int_or_none(stats.get('numberOfPitches'))
    if balls is None:
        return REFUSED_FIELD_ABSENT_IN_BOXSCORE
    if strikes is None or pitches is None:
        return REFUSED_COMPANION_ABSENT
    if balls + strikes != pitches:
        return REFUSED_INCONSISTENT_TRIPLE
    return None


# The approved fallback set. Exactly one member, by evidence.
#
# Adding a field here authorizes the daily correction lane to write it from box
# score evidence, so each addition needs its own production audit, its own
# semantic rule, and its own validation — not merely the observation that the
# split omits it.
BOXSCORE_FALLBACK_AUTHORITY = {
    'balls': FieldAuthority(
        field='balls',
        primary_source=SOURCE_PLAYER_SPLIT,
        fallback_source=SOURCE_COMPLETED_GAME_BOXSCORE,
        source_key='balls',
        required_companions=('strikes', 'numberOfPitches'),
        semantic_rule=(
            'Total non-strike pitches thrown in this appearance, taken '
            'directly from the completed-game box score. The player game-log '
            'split does not expose the statistic, so the split can never '
            'correct it.'
        ),
        validation_rule='balls + strikes == numberOfPitches',
        validate=_validate_balls,
    ),
}

APPROVED_FALLBACK_FIELDS = tuple(sorted(BOXSCORE_FALLBACK_AUTHORITY))


def is_approved_fallback_field(field) -> bool:
    return field in BOXSCORE_FALLBACK_AUTHORITY


def authority_for(field) -> FieldAuthority | None:
    return BOXSCORE_FALLBACK_AUTHORITY.get(field)


def approved_uncomparable_fields(uncomparable) -> list[str]:
    """The approved fallback fields among those a source could not compare."""
    return [
        field for field in sorted(set(uncomparable or ()))
        if is_approved_fallback_field(field)
    ]


def describe_authority() -> dict:
    """The whole contract, for artifacts and review."""
    return {
        'authority_contract': AUTHORITY_CONTRACT,
        'authority_version': AUTHORITY_VERSION,
        'approved_fallback_fields': list(APPROVED_FALLBACK_FIELDS),
        'fields': [
            BOXSCORE_FALLBACK_AUTHORITY[field].describe()
            for field in APPROVED_FALLBACK_FIELDS
        ],
    }


def select_boxscore_line(pitching_lines, pitcher_mlb_id):
    """The one box-score pitching line belonging to this pitcher.

    Returns ``(stats, refusal_reason)``. Two lines claiming the same pitcher in
    one game is not a tie to break — it means the identity that would receive
    the correction is not established, so the fallback refuses rather than
    picking one.
    """
    if pitcher_mlb_id is None:
        return None, REFUSED_IDENTITY_AMBIGUOUS
    matches = [
        line for line in (pitching_lines or ())
        if pitcher_mlb_id in (line.get('player_id'), line.get('person_id'))
    ]
    if not matches:
        return None, REFUSED_NO_PITCHING_LINE
    if len(matches) > 1:
        return None, REFUSED_IDENTITY_AMBIGUOUS
    return matches[0].get('stats') or {}, None


def fallback_evidence_revision(*, game_pk, pitcher_mlb_id, stats):
    """Deterministic identity of the box-score evidence a fallback used.

    Covers the appearance and the exact triple that was validated, so a later
    reviewer can tell whether a recorded correction rests on the evidence they
    are looking at or on a since-revised line. Returns ``None`` when the
    appearance cannot be pinned — a value whose evidence cannot be named is not
    auditable, and the caller refuses it.
    """
    if game_pk is None or pitcher_mlb_id is None or not stats:
        return None
    payload = {
        'game_pk': str(game_pk),
        'pitcher_mlb_id': str(pitcher_mlb_id),
        'stats': {
            key: _int_or_none(stats.get(key))
            for key in ('balls', 'strikes', 'numberOfPitches')
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(encoded.encode('utf-8')).hexdigest()[:32]


def resolve_fallback_values(
    *, split_stats, boxscore_stats, uncomparable,
    game_pk=None, pitcher_mlb_id=None, game_final=True, unavailable_reason=None,
):
    """Decide which approved fields the box score may supply for this line.

    Pure: it reads two source shapes and returns a decision. It performs no
    fetch, touches no database, and never mutates a row — the caller feeds the
    result back through the canonical values builder and ``plan_row`` so the
    normal planner remains the only comparator.

    ``unavailable_reason`` lets the caller — which owns the fetch — report *why*
    there is no box score to consult, so an unreachable source and a source that
    genuinely lacks the field never collapse into one outcome.
    """
    decision = {
        'authority_contract': AUTHORITY_CONTRACT,
        'authority_version': AUTHORITY_VERSION,
        'applied_fields': [],
        'values': {},
        'refusals': {},
        'source_revision': None,
    }
    candidates = approved_uncomparable_fields(uncomparable)
    if not candidates:
        return decision

    revision = fallback_evidence_revision(
        game_pk=game_pk, pitcher_mlb_id=pitcher_mlb_id, stats=boxscore_stats,
    )
    decision['source_revision'] = revision

    for field in candidates:
        authority = BOXSCORE_FALLBACK_AUTHORITY[field]

        # Evidence that exists is never overridden by a fallback.
        supplied = (split_stats or {}).get(authority.source_key)
        if supplied not in (None, ''):
            decision['refusals'][field] = REFUSED_SPLIT_SUPPLIES_FIELD
            continue

        if not game_final:
            decision['refusals'][field] = REFUSED_GAME_NOT_FINAL
            continue

        if unavailable_reason is not None:
            decision['refusals'][field] = unavailable_reason
            continue

        if not boxscore_stats:
            decision['refusals'][field] = REFUSED_NO_PITCHING_LINE
            continue

        refusal = authority.validate(boxscore_stats)
        if refusal is not None:
            decision['refusals'][field] = refusal
            continue

        if revision is None:
            decision['refusals'][field] = REFUSED_SOURCE_REVISION_MISSING
            continue

        decision['values'][authority.source_key] = _int_or_none(
            boxscore_stats.get(authority.source_key)
        )
        decision['applied_fields'].append(field)

    decision['applied_fields'] = sorted(decision['applied_fields'])
    decision['refusals'] = dict(sorted(decision['refusals'].items()))
    return decision


class FallbackLedger:
    """Run-scoped accounting for what the fallback did, tried, and refused.

    A fallback that is invisible in the run summary is indistinguishable from
    one that never ran, so every eligible row lands in exactly one bucket and
    every refusal is counted under its own name. Pure accumulation: it holds no
    session, opens no transaction, and decides nothing.
    """

    # Bounded so a bad day cannot turn the summary into a payload dump. The
    # count of what was dropped is reported, never silently absorbed.
    MAX_RECORDS = 100

    def __init__(self):
        self.eligible_rows = 0
        self.fetches = 0
        self.fetch_failures = 0
        self.applied_rows = 0
        self.corrected_rows = 0
        self.inserted_rows = 0
        self.refused_rows = 0
        self.unchanged_rows = 0
        self.fetch_cap_reached = 0
        self.refusal_reasons: dict[str, int] = {}
        self.records: list[dict] = []
        self.records_truncated = 0

    def note_refusals(self, refusals):
        for reason in (refusals or {}).values():
            self.refusal_reasons[reason] = self.refusal_reasons.get(reason, 0) + 1

    def record_application(
        self, *, game_pk, pitcher_mlb_id, fields, classifications,
        source_revision, plan_fingerprint, target_state_digest, outcome,
    ):
        """Name the authority behind one applied fallback value.

        Recorded whether or not the row ultimately changed: "the box score
        supplied it and it already agreed" is evidence too.
        """
        if len(self.records) >= self.MAX_RECORDS:
            self.records_truncated += 1
            return
        self.records.append({
            'game_pk': game_pk,
            'pitcher_mlb_id': pitcher_mlb_id,
            'fields': sorted(fields or ()),
            'difference_classifications': sorted(classifications or ()),
            'source_authority': AUTHORITY_CONTRACT,
            'source_authority_version': AUTHORITY_VERSION,
            'correction_source': CORRECTION_SOURCE_BOXSCORE_FALLBACK,
            'source_revision': source_revision,
            'plan_fingerprint': plan_fingerprint,
            'applied_target_state_digest': target_state_digest,
            'outcome': outcome,
        })

    def summary(self) -> dict:
        return {
            'boxscore_fallback_authority': AUTHORITY_CONTRACT,
            'boxscore_fallback_authority_version': AUTHORITY_VERSION,
            'boxscore_fallback_approved_fields': list(APPROVED_FALLBACK_FIELDS),
            'boxscore_fallback_eligible_rows': self.eligible_rows,
            'boxscore_fallback_fetches': self.fetches,
            'boxscore_fallback_fetch_failures': self.fetch_failures,
            'boxscore_fallback_applied_rows': self.applied_rows,
            'boxscore_fallback_corrected_rows': self.corrected_rows,
            'boxscore_fallback_inserted_rows': self.inserted_rows,
            'boxscore_fallback_unchanged_rows': self.unchanged_rows,
            'boxscore_fallback_refused_rows': self.refused_rows,
            'boxscore_fallback_fetch_cap_reached': self.fetch_cap_reached,
            'boxscore_fallback_refusal_reasons': dict(
                sorted(self.refusal_reasons.items())
            ),
            'boxscore_fallback_records': list(self.records),
            'boxscore_fallback_records_truncated': self.records_truncated,
        }


def empty_summary() -> dict:
    """The shape a run reports when the fallback never ran.

    Present with zeros rather than absent: a missing key reads as "the field is
    not instrumented", which is a different claim from "nothing was eligible".
    """
    return FallbackLedger().summary()


def enriched_stats(split_stats, decision):
    """The split's stats plus the values the fallback authorized, and nothing else.

    Returned as a new dict: the caller's source payload is never mutated, so the
    split remains reportable as what the split actually said.
    """
    values = (decision or {}).get('values') or {}
    if not values:
        return split_stats
    return {**(split_stats or {}), **values}
