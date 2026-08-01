"""The declared source authority for a field the split cannot supply.

A production audit settled a question the two ingestion lanes had been
answering differently by accident: the completed-game box score carries
``balls``; the player game-log split does not carry the key at all. Because a
governed optional statistic is compared only when the source dict supplies it,
the daily correction lane could re-sweep the same appearance forever and never
touch the field. The stored value was uncorrectable, not disputed.

``gamelog_source_authority`` declares the resolution — split primary, box score
as an explicitly approved per-field fallback — and these tests own it. They
prove the *rule*, not the audited row: no production identifier appears in any
assertion about behaviour.

What is deliberately being pinned down here is how narrow the authority is. A
fallback that quietly widened to every optional statistic, or that derived a
value the box score never stated, or that overrode evidence the split did
supply, would each be a much larger claim than the audit supports.
"""

import pytest

from services import gamelog_source_authority as authority


def _boxscore(**overrides):
    """A coherent official pitching line: 19 + 26 == 45."""
    stats = {'balls': 19, 'strikes': 26, 'numberOfPitches': 45}
    stats.update(overrides)
    return stats


def _split(**overrides):
    """The split shape: strikes and pitches, no ``balls`` key."""
    stats = {'strikes': 26, 'numberOfPitches': 45}
    stats.update(overrides)
    return stats


def _resolve(**overrides):
    kwargs = {
        'split_stats': _split(),
        'boxscore_stats': _boxscore(),
        'uncomparable': ['balls'],
        'game_pk': 970001,
        'pitcher_mlb_id': 970100,
    }
    kwargs.update(overrides)
    return authority.resolve_fallback_values(**kwargs)


# ── The approved set is narrow, and stays narrow ────────────────────────────


def test_exactly_one_field_is_approved_for_fallback():
    """Widening this set is a governance decision, not a refactor.

    Each addition needs its own production audit, semantic rule, and
    validation. The test exists so that adding one is a deliberate act.
    """
    assert authority.APPROVED_FALLBACK_FIELDS == ('balls',)


def test_an_unapproved_field_is_never_supplied_by_the_fallback():
    decision = _resolve(uncomparable=['batters_faced', 'games_finished'])
    assert decision['applied_fields'] == []
    assert decision['values'] == {}


def test_an_unapproved_uncomparable_field_is_not_even_a_candidate():
    """Not refused — out of scope. A refusal would imply it was considered."""
    assert authority.approved_uncomparable_fields(
        ['batters_faced', 'balls', 'hold']
    ) == ['balls']


def test_the_declared_contract_names_its_sources_and_its_rule():
    described = authority.describe_authority()
    assert described['authority_contract'] == (
        'player_split_primary_with_boxscore_fallback'
    )
    field = described['fields'][0]
    assert field['primary_source'] == authority.SOURCE_PLAYER_SPLIT
    assert field['fallback_source'] == authority.SOURCE_COMPLETED_GAME_BOXSCORE
    assert field['required_companions'] == ['strikes', 'numberOfPitches']
    assert field['validation_rule'] == 'balls + strikes == numberOfPitches'


# ── Primacy: the fallback never overrides evidence that exists ──────────────


def test_a_split_that_supplies_the_field_refuses_the_fallback():
    decision = _resolve(
        split_stats=_split(balls=21), uncomparable=['balls'],
    )
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == authority.REFUSED_SPLIT_SUPPLIES_FIELD


def test_a_field_the_split_could_compare_is_never_a_candidate():
    """Comparability is the entry condition. An empty uncomparable set means
    the split saw every governed field, so there is nothing to fall back to."""
    decision = _resolve(uncomparable=[])
    assert decision['applied_fields'] == []
    assert decision['refusals'] == {}
    assert decision['source_revision'] is None


def test_an_explicitly_null_split_value_is_treated_as_absence():
    """``balls: null`` is not the split supplying the field.

    The canonical presence rule already treats an explicit null exactly like an
    omission; the fallback must agree, or the two would disagree about what the
    split said.
    """
    decision = _resolve(split_stats=_split(balls=None))
    assert decision['applied_fields'] == ['balls']


# ── Validation: the box score must be coherent before it is trusted ─────────


def test_an_internally_consistent_line_supplies_the_value():
    decision = _resolve()
    assert decision['applied_fields'] == ['balls']
    assert decision['values'] == {'balls': 19}
    assert decision['refusals'] == {}


def test_an_inconsistent_triple_is_refused_rather_than_reconciled():
    """20 + 26 != 45. The line is incoherent, so nothing is written.

    This is the exact shape the audit found stored, and refusing it is the
    point: a fallback that "fixed" the arithmetic would be inventing evidence.
    """
    decision = _resolve(boxscore_stats=_boxscore(balls=20))
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == authority.REFUSED_INCONSISTENT_TRIPLE


def test_the_value_is_never_derived_from_its_companions():
    """A line carrying strikes and pitches but no balls supplies nothing.

    ``45 - 26`` would be a derivation. The box score's own ``balls`` is the
    authority; the sum only validates it.
    """
    stats = {'strikes': 26, 'numberOfPitches': 45}
    decision = _resolve(boxscore_stats=stats)
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == (
        authority.REFUSED_FIELD_ABSENT_IN_BOXSCORE
    )


def test_a_missing_companion_is_refused_because_nothing_can_validate():
    decision = _resolve(boxscore_stats={'balls': 19, 'strikes': 26})
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == authority.REFUSED_COMPANION_ABSENT


def test_a_zero_value_is_supplied_rather_than_read_as_missing():
    """0 + 0 == 0 is a real, coherent line — a pitcher who threw only strikes."""
    decision = _resolve(
        boxscore_stats={'balls': 0, 'strikes': 12, 'numberOfPitches': 12},
    )
    assert decision['applied_fields'] == ['balls']
    assert decision['values'] == {'balls': 0}


def test_a_non_numeric_value_cannot_validate_and_is_refused():
    decision = _resolve(boxscore_stats=_boxscore(balls='nineteen'))
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == (
        authority.REFUSED_FIELD_ABSENT_IN_BOXSCORE
    )


# ── Availability and identity ───────────────────────────────────────────────


def test_a_game_that_is_not_final_refuses_before_consulting_the_box_score():
    decision = _resolve(game_final=False)
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == authority.REFUSED_GAME_NOT_FINAL


def test_an_unreachable_box_score_is_distinguished_from_a_missing_line():
    """Two different facts, two different names.

    "We could not read the source" and "the source has no line for this
    pitcher" would otherwise collapse into one silent non-event.
    """
    unreachable = _resolve(
        boxscore_stats=None,
        unavailable_reason=authority.REFUSED_BOXSCORE_UNAVAILABLE,
    )
    missing = _resolve(boxscore_stats=None)
    assert unreachable['refusals']['balls'] == (
        authority.REFUSED_BOXSCORE_UNAVAILABLE
    )
    assert missing['refusals']['balls'] == authority.REFUSED_NO_PITCHING_LINE


def test_the_pitchers_own_line_is_selected_by_either_identifier():
    lines = [
        {'player_id': 970199, 'stats': {'balls': 3}},
        {'person_id': 970100, 'stats': _boxscore()},
    ]
    stats, refusal = authority.select_boxscore_line(lines, 970100)
    assert refusal is None
    assert stats == _boxscore()


def test_two_lines_claiming_one_pitcher_refuse_rather_than_choose():
    """Ambiguous identity is not a tie to break.

    If the recipient of the correction is not established, writing either line
    would be a guess about whose appearance this is.
    """
    lines = [
        {'player_id': 970100, 'stats': _boxscore()},
        {'person_id': 970100, 'stats': _boxscore(balls=4, strikes=4,
                                                 numberOfPitches=8)},
    ]
    stats, refusal = authority.select_boxscore_line(lines, 970100)
    assert stats is None
    assert refusal == authority.REFUSED_IDENTITY_AMBIGUOUS


def test_an_unidentified_pitcher_cannot_select_a_line():
    assert authority.select_boxscore_line([{'player_id': 1, 'stats': {}}], None) == (
        None, authority.REFUSED_IDENTITY_AMBIGUOUS,
    )


def test_a_box_score_with_no_line_for_this_pitcher_is_named_as_such():
    assert authority.select_boxscore_line([], 970100) == (
        None, authority.REFUSED_NO_PITCHING_LINE,
    )


# ── Source revision: a value whose evidence cannot be named is refused ──────


def test_an_applied_value_always_carries_the_evidence_that_produced_it():
    decision = _resolve()
    assert decision['source_revision']
    assert decision['source_revision'] == authority.fallback_evidence_revision(
        game_pk=970001, pitcher_mlb_id=970100, stats=_boxscore(),
    )


def test_an_unpinnable_appearance_refuses_rather_than_writing_unauditable_data():
    decision = _resolve(game_pk=None)
    assert decision['applied_fields'] == []
    assert decision['refusals']['balls'] == (
        authority.REFUSED_SOURCE_REVISION_MISSING
    )


def test_a_revised_box_score_produces_a_different_revision():
    first = authority.fallback_evidence_revision(
        game_pk=970001, pitcher_mlb_id=970100, stats=_boxscore(),
    )
    revised = authority.fallback_evidence_revision(
        game_pk=970001, pitcher_mlb_id=970100,
        stats=_boxscore(balls=18, numberOfPitches=44),
    )
    assert first != revised


def test_the_revision_is_stable_across_calls():
    args = {'game_pk': 970001, 'pitcher_mlb_id': 970100, 'stats': _boxscore()}
    assert (
        authority.fallback_evidence_revision(**args)
        == authority.fallback_evidence_revision(**args)
    )


# ── Purity: deciding is not writing ─────────────────────────────────────────


def test_resolving_never_mutates_either_source_payload():
    split = _split()
    box = _boxscore()
    _resolve(split_stats=split, boxscore_stats=box)
    assert split == _split()
    assert box == _boxscore()


def test_enrichment_returns_a_new_mapping_and_leaves_the_split_intact():
    split = _split()
    decision = _resolve(split_stats=split)
    enriched = authority.enriched_stats(split, decision)
    assert enriched == {'strikes': 26, 'numberOfPitches': 45, 'balls': 19}
    assert 'balls' not in split


def test_enrichment_with_nothing_applied_returns_the_split_unchanged():
    decision = _resolve(boxscore_stats=None)
    assert authority.enriched_stats(_split(), decision) == _split()


def test_enrichment_adds_only_the_approved_field():
    decision = _resolve()
    enriched = authority.enriched_stats(_split(), decision)
    assert set(enriched) - set(_split()) == {'balls'}


# ── Ledger accounting ───────────────────────────────────────────────────────


def test_a_run_that_never_used_the_fallback_still_reports_it():
    """Zeros, not absence. A missing key reads as "not instrumented"."""
    summary = authority.empty_summary()
    assert summary['boxscore_fallback_eligible_rows'] == 0
    assert summary['boxscore_fallback_applied_rows'] == 0
    assert summary['boxscore_fallback_authority'] == authority.AUTHORITY_CONTRACT


def test_every_refusal_is_counted_under_its_own_name():
    ledger = authority.FallbackLedger()
    ledger.note_refusals({'balls': authority.REFUSED_INCONSISTENT_TRIPLE})
    ledger.note_refusals({'balls': authority.REFUSED_INCONSISTENT_TRIPLE})
    ledger.note_refusals({'balls': authority.REFUSED_NO_PITCHING_LINE})
    assert ledger.summary()['boxscore_fallback_refusal_reasons'] == {
        authority.REFUSED_INCONSISTENT_TRIPLE: 2,
        authority.REFUSED_NO_PITCHING_LINE: 1,
    }


def test_an_applied_value_records_the_authority_behind_it():
    ledger = authority.FallbackLedger()
    ledger.record_application(
        game_pk=970001, pitcher_mlb_id=970100, fields=['balls'],
        classifications=['statistical_correction'], source_revision='rev',
        plan_fingerprint='fp', target_state_digest='digest',
        outcome=authority.OUTCOME_CORRECTED,
    )
    record = ledger.summary()['boxscore_fallback_records'][0]
    assert record['correction_source'] == (
        authority.CORRECTION_SOURCE_BOXSCORE_FALLBACK
    )
    assert record['source_authority'] == authority.AUTHORITY_CONTRACT
    assert record['source_revision'] == 'rev'
    assert record['plan_fingerprint'] == 'fp'
    assert record['applied_target_state_digest'] == 'digest'
    assert record['outcome'] == authority.OUTCOME_CORRECTED


def test_the_record_list_is_bounded_and_says_what_it_dropped():
    ledger = authority.FallbackLedger()
    for index in range(authority.FallbackLedger.MAX_RECORDS + 7):
        ledger.record_application(
            game_pk=970000 + index, pitcher_mlb_id=970100, fields=['balls'],
            classifications=(), source_revision='rev', plan_fingerprint='fp',
            target_state_digest='digest', outcome=authority.OUTCOME_CORRECTED,
        )
    summary = ledger.summary()
    assert len(summary['boxscore_fallback_records']) == (
        authority.FallbackLedger.MAX_RECORDS
    )
    assert summary['boxscore_fallback_records_truncated'] == 7


@pytest.mark.parametrize('reason', [
    authority.REFUSED_FIELD_NOT_APPROVED,
    authority.REFUSED_SPLIT_SUPPLIES_FIELD,
    authority.REFUSED_GAME_NOT_FINAL,
    authority.REFUSED_BOXSCORE_UNAVAILABLE,
    authority.REFUSED_NO_PITCHING_LINE,
    authority.REFUSED_FIELD_ABSENT_IN_BOXSCORE,
    authority.REFUSED_COMPANION_ABSENT,
    authority.REFUSED_INCONSISTENT_TRIPLE,
    authority.REFUSED_SOURCE_REVISION_MISSING,
    authority.REFUSED_IDENTITY_AMBIGUOUS,
])
def test_every_refusal_reason_is_a_distinct_named_string(reason):
    assert isinstance(reason, str) and reason


def test_no_two_refusal_reasons_share_a_name():
    reasons = [
        authority.REFUSED_FIELD_NOT_APPROVED,
        authority.REFUSED_SPLIT_SUPPLIES_FIELD,
        authority.REFUSED_GAME_NOT_FINAL,
        authority.REFUSED_BOXSCORE_UNAVAILABLE,
        authority.REFUSED_NO_PITCHING_LINE,
        authority.REFUSED_FIELD_ABSENT_IN_BOXSCORE,
        authority.REFUSED_COMPANION_ABSENT,
        authority.REFUSED_INCONSISTENT_TRIPLE,
        authority.REFUSED_SOURCE_REVISION_MISSING,
        authority.REFUSED_IDENTITY_AMBIGUOUS,
    ]
    assert len(set(reasons)) == len(reasons)
