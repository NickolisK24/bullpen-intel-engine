"""Game 824487 checkpoint repair — classification, in-process.

The population expectation, the current-source completeness gate, the field
comparison, the precondition evaluator, and the mutation-scope evaluator are
pure functions over observed evidence. They are exercised here directly, with
one fact moved at a time, so a defect in the judgement shows up as a failing
assertion rather than as a subtly wrong production verdict.

The governing property throughout: absence is never proof. Every function must
distinguish "observed and wrong" from "never observed", and neither may reach a
result that permits a write.
"""

import pytest

from services import game_appearance_extraction as extraction
from services import game_source_revision_audit as audit
from services import game_source_revision_checkpoint_repair as repair


OLD = repair.EXPECTED_EXISTING_SOURCE_REVISION
NEW = repair.INTENDED_SOURCE_REVISION
THIRD = 'c' * 64

ARMS = [770001, 770002, 770003]

# A sentinel, not None: several of these tests need to pass an explicit None —
# "the work item was never read", "the fingerprints were uncomputable" — and a
# helper that treats None as "use the default" would silently test the happy
# path instead of the case the test is named for.
_UNSET = object()


def _work_item(**overrides):
    row = {
        'id': 4242,
        'mlb_game_pk': repair.GAME_PK,
        'represented_date': repair.REPRESENTED_DATE.isoformat(),
        'status': 'completed',
        'source_revision': OLD,
        'rows_expected': 3,
        'rows_reconciled': 3,
        'updated_at': '2026-07-30T04:00:00',
    }
    row.update(overrides)
    return row


def _official_appearance(mlb_id, *, outs=3, innings='1.0', strikeouts=1):
    return {
        'pitcher_mlb_id': mlb_id,
        'side': 'home',
        'team_id': 111,
        'opponent_team_id': 222,
        'appearance_role': 'relief',
        'games_started': 0,
        'outs_recorded': outs,
        'innings_pitched': innings,
        'earned_runs': 0,
        'runs_allowed': 0,
        'hits_allowed': 0,
        'walks': 0,
        'strikeouts': strikeouts,
        'home_runs_allowed': 0,
        'batters_faced': 3,
        'pitches_thrown': 12,
    }


def _stored_appearance(mlb_id, *, outs=3, innings='1.0', strikeouts=1):
    return {
        'pitcher_mlb_id': mlb_id,
        'local_pitcher_id': mlb_id - 700000,
        'team_id': 111,
        'opponent_team_id': 222,
        'appearance_role': 'relief',
        'games_started': 0,
        'outs_recorded': outs,
        'innings_pitched': innings,
        'earned_runs': 0,
        'runs_allowed': 0,
        'hits_allowed': 0,
        'walks': 0,
        'strikeouts': strikeouts,
        'home_runs_allowed': 0,
        'batters_faced': 3,
        'pitches_thrown': 12,
    }


def _official(appearances=None, *, revision=NEW, available=True, **overrides):
    appearances = (
        [_official_appearance(mlb_id) for mlb_id in ARMS]
        if appearances is None else appearances
    )
    payload = {
        'available': available,
        'unavailable_reason': None,
        'appearances': appearances,
        'appearance_count': len(appearances),
        'extraction_yielded_no_appearances': False,
        'current_source_revision': revision,
        'official_pitcher_mlb_ids': sorted(
            record['pitcher_mlb_id'] for record in appearances
        ),
        'plan': _plan(),
    }
    payload.update(overrides)
    return payload


def _stored(appearances=None, **overrides):
    appearances = (
        [_stored_appearance(mlb_id) for mlb_id in ARMS]
        if appearances is None else appearances
    )
    payload = {
        'stored_appearances': appearances,
        'stored_appearance_count': len(appearances),
        'stored_pitcher_mlb_ids': sorted(
            entry['pitcher_mlb_id'] for entry in appearances
        ),
        'duplicate_stored_pitchers': [],
    }
    payload.update(overrides)
    return payload


def _plan(**overrides):
    payload = {
        'available': True,
        'row_count': len(ARMS),
        'action_counts': {'unchanged': len(ARMS)},
        'proposes_insert': False,
        'proposes_update': False,
        'proposes_blocked': False,
        'all_unchanged': True,
        'proposes_mutation': False,
    }
    payload.update(overrides)
    return payload


def _evaluate(*, official=_UNSET, stored=_UNSET, work_item=_UNSET,
              plan=_UNSET, database_observed=True,
              before_fingerprints=_UNSET):
    official = _official() if official is _UNSET else official
    stored = _stored() if stored is _UNSET else stored
    work_item = _work_item() if work_item is _UNSET else work_item
    plan = _plan() if plan is _UNSET else plan
    before_fingerprints = (
        {'exact_game_824487': {'game_logs': 'abc'}}
        if before_fingerprints is _UNSET else before_fingerprints
    )
    target = {
        'observed': database_observed,
        'candidate_row_count': 1 if work_item else 0,
        'candidate_row_ids': [work_item['id']] if work_item else [],
        'work_item': work_item,
        'work_item_row_id': work_item['id'] if work_item else None,
    }
    comparison = repair.build_comparison(official=official, stored=stored)
    expectation = repair.population_expectation(
        work_item=work_item,
        stored_appearance_count=stored.get('stored_appearance_count'),
        database_observed=database_observed,
    )
    completeness = repair.source_completeness(
        official=official, comparison=comparison['summary'],
        database_observed=database_observed, expectation=expectation,
    )
    return repair.evaluate_preconditions(
        target=target, official=official, comparison=comparison, plan=plan,
        expectation=expectation, completeness=completeness,
        database_observed=database_observed,
        before_fingerprints=before_fingerprints,
    )


def _state_of(evaluation, identifier):
    for check in evaluation['preconditions']:
        if check['precondition_id'] == identifier:
            return check['state']
    raise AssertionError(f'{identifier} was never evaluated')


# ── Population expectation ──────────────────────────────────────────────────

def test_the_population_size_comes_from_live_state_never_from_a_constant():
    expectation = repair.population_expectation(
        work_item=_work_item(rows_expected=7, rows_reconciled=7),
        stored_appearance_count=7,
    )
    assert expectation['expectation_state'] == repair.POPULATION_VERIFIED
    assert expectation['expected_appearance_count'] == 7
    # The audit's locked constant is deliberately not consulted.
    assert expectation['expected_appearance_count'] != (
        audit.EXPECTED_APPEARANCE_COUNT
    )


def test_a_checkpoint_that_was_never_read_supplies_no_population_size():
    expectation = repair.population_expectation(
        work_item=None, stored_appearance_count=12,
    )
    assert expectation['conclusion_usable'] is False
    assert expectation['expected_appearance_count'] is None
    assert expectation['expectation_state'] == (
        repair.POPULATION_CHECKPOINT_UNAVAILABLE
    )


def test_a_database_that_was_never_opened_supplies_no_population_size():
    expectation = repair.population_expectation(
        work_item=_work_item(), stored_appearance_count=3,
        database_observed=False,
    )
    assert expectation['conclusion_usable'] is False


@pytest.mark.parametrize('overrides,expected', [
    ({'rows_expected': None}, repair.POPULATION_ROWS_EXPECTED_MISSING),
    ({'rows_expected': 0, 'rows_reconciled': 0},
     repair.POPULATION_ROWS_EXPECTED_NOT_POSITIVE),
    ({'rows_reconciled': 2}, repair.POPULATION_RECONCILED_DISAGREES),
])
def test_an_inconsistent_checkpoint_supplies_no_population_size(
    overrides, expected,
):
    expectation = repair.population_expectation(
        work_item=_work_item(**overrides), stored_appearance_count=3,
    )
    assert expectation['expectation_state'] == expected
    assert expectation['conclusion_usable'] is False


def test_storage_disagreeing_with_the_checkpoint_supplies_no_size():
    expectation = repair.population_expectation(
        work_item=_work_item(), stored_appearance_count=2,
    )
    assert expectation['expectation_state'] == (
        repair.POPULATION_STORED_DISAGREES
    )
    assert expectation['conclusion_usable'] is False


def test_a_boolean_row_count_is_not_an_integer_row_count():
    expectation = repair.population_expectation(
        work_item=_work_item(rows_expected=True, rows_reconciled=True),
        stored_appearance_count=1,
    )
    assert expectation['conclusion_usable'] is False


# ── Completeness gate ───────────────────────────────────────────────────────

def _completeness(*, official=_UNSET, stored=_UNSET, work_item=_UNSET,
                  database_observed=True):
    official = _official() if official is _UNSET else official
    stored = _stored() if stored is _UNSET else stored
    work_item = _work_item() if work_item is _UNSET else work_item
    comparison = repair.build_comparison(official=official, stored=stored)
    expectation = repair.population_expectation(
        work_item=work_item,
        stored_appearance_count=stored.get('stored_appearance_count'),
        database_observed=database_observed,
    )
    return repair.source_completeness(
        official=official, comparison=comparison['summary'],
        database_observed=database_observed, expectation=expectation,
    )


def test_a_complete_and_comparable_source_is_conclusion_eligible():
    result = _completeness()
    assert result['completeness_state'] == repair.SOURCE_COMPLETE
    assert result['conclusion_eligible'] is True


def test_only_complete_and_comparable_is_ever_conclusion_eligible():
    assert repair.CONCLUSION_ELIGIBLE_STATES == {repair.SOURCE_COMPLETE}


def test_a_source_that_was_never_fetched_is_not_eligible():
    result = _completeness(official=_official(
        available=False, unavailable_reason='source_call_failed',
    ))
    assert result['completeness_state'] == repair.SOURCE_UNAVAILABLE
    assert result['conclusion_eligible'] is False


def test_an_empty_official_set_is_missing_evidence_not_a_gameless_game():
    result = _completeness(official=_official(
        [], available=False, extraction_yielded_no_appearances=True,
    ))
    assert result['completeness_state'] == repair.SOURCE_EMPTY
    assert result['conclusion_eligible'] is False


def test_symmetric_truncation_is_refused_even_though_membership_matches():
    """Two truncated sets agree with one another and are still incomplete.

    This package is protected twice over. The live population expectation
    itself notices that storage no longer holds the number of appearances the
    checkpoint recorded, so the pair never even reaches the membership test —
    and membership, which is exactly what a symmetrically truncated pair
    satisfies, would have said yes.
    """
    half = ARMS[:2]
    result = _completeness(
        official=_official([_official_appearance(i) for i in half]),
        stored=_stored([_stored_appearance(i) for i in half]),
        work_item=_work_item(rows_expected=3, rows_reconciled=3),
    )
    assert result['membership_matches'] is True
    assert result['missing_from_storage'] == []
    assert result['extra_in_storage'] == []
    assert result['completeness_state'] == (
        repair.SOURCE_EXPECTATION_UNPROVEN
    )
    assert result['conclusion_eligible'] is False


def test_a_contradicted_count_is_resolved_before_the_duplicate_gate():
    """Ordering proof: count first, then duplicates, then membership.

    A repeated official identity makes the observed COUNT four while the
    unique membership still matches storage's three. Both the count gate and
    the duplicate gate would refuse; the reported state must be the count one,
    because that is the gate a symmetrically truncated pair needs.
    """
    doubled = [_official_appearance(i) for i in ARMS] + [
        _official_appearance(ARMS[0])
    ]
    result = _completeness(
        official=_official(doubled),
        work_item=_work_item(rows_expected=3, rows_reconciled=3),
    )
    assert result['observed_appearance_count'] == 4
    assert result['expected_appearance_count'] == 3
    assert result['duplicate_official_identities'] == [ARMS[0]]
    assert result['completeness_state'] == repair.SOURCE_COUNT_CONTRADICTS
    assert result['conclusion_eligible'] is False


def test_an_unverified_population_size_blocks_before_membership_too():
    result = _completeness(work_item=_work_item(rows_expected=None))
    assert result['completeness_state'] == (
        repair.SOURCE_EXPECTATION_UNPROVEN
    )
    assert result['conclusion_eligible'] is False


def test_a_pitcher_only_in_the_official_set_is_not_eligible():
    result = _completeness(
        stored=_stored([_stored_appearance(i) for i in ARMS[:2]]),
        work_item=_work_item(rows_expected=3, rows_reconciled=3),
    )
    assert result['conclusion_eligible'] is False


def test_a_pitcher_only_in_storage_is_not_eligible():
    result = _completeness(
        official=_official([_official_appearance(i) for i in ARMS[:2]]),
    )
    assert result['conclusion_eligible'] is False


def test_a_duplicated_official_identity_is_ambiguous_not_merely_incomplete():
    """One pitcher has exactly one pitching line per game."""
    doubled = [_official_appearance(i) for i in ARMS] + [
        _official_appearance(ARMS[0])
    ]
    result = _completeness(
        official=_official(doubled),
        work_item=_work_item(rows_expected=4, rows_reconciled=4),
        stored=_stored(
            [_stored_appearance(i) for i in ARMS],
            stored_appearance_count=4,
        ),
    )
    assert result['completeness_state'] == repair.SOURCE_DUPLICATE_OFFICIAL
    assert result['conclusion_eligible'] is False


def test_a_duplicated_stored_identity_gets_its_own_state():
    result = _completeness(stored=_stored(
        duplicate_stored_pitchers=[ARMS[0]],
    ))
    assert result['completeness_state'] == repair.SOURCE_DUPLICATE_STORED
    assert result['conclusion_eligible'] is False


def test_a_database_that_was_never_opened_is_not_eligible():
    result = _completeness(database_observed=False)
    assert result['conclusion_eligible'] is False


# ── Field comparison ────────────────────────────────────────────────────────

def test_an_agreeing_comparison_reports_no_governed_difference():
    comparison = repair.build_comparison(
        official=_official(), stored=_stored(),
    )
    summary = comparison['summary']
    assert summary['structurally_valid'] is True
    assert summary['any_governed_field_differs'] is False
    assert summary['every_difference_is_display_only'] is True
    assert summary['membership_matches'] is True


def test_a_display_only_innings_difference_is_not_a_governed_difference():
    """The real production shape: derived innings differ, the digest cannot."""
    official = _official([
        _official_appearance(mlb_id, innings='1.0') for mlb_id in ARMS
    ])
    stored = _stored([
        _stored_appearance(mlb_id, innings='1.00') for mlb_id in ARMS
    ])
    summary = repair.build_comparison(
        official=official, stored=stored,
    )['summary']
    assert summary['differing_rows'], 'the display difference must be visible'
    assert all(
        row['field_name'] == 'innings_pitched'
        for row in summary['differing_rows']
    )
    assert summary['any_governed_field_differs'] is False
    assert summary['every_difference_is_display_only'] is True
    assert 'innings_pitched' not in extraction.FINGERPRINT_FIELDS


def test_a_governed_statistical_difference_is_a_governed_difference():
    official = _official([
        _official_appearance(mlb_id, strikeouts=9) for mlb_id in ARMS
    ])
    summary = repair.build_comparison(
        official=official, stored=_stored(),
    )['summary']
    assert summary['any_governed_field_differs'] is True
    assert summary['every_difference_is_display_only'] is False
    assert any(
        row['field_name'] == 'strikeouts'
        for row in summary['governed_differing_rows']
    )


def test_a_canonical_outs_difference_is_never_called_display_only():
    official = _official([
        _official_appearance(mlb_id, outs=6) for mlb_id in ARMS
    ])
    summary = repair.build_comparison(
        official=official, stored=_stored(),
    )['summary']
    assert summary['every_difference_is_display_only'] is False


def test_the_comparison_makes_no_historical_claim():
    rows = repair.build_comparison(
        official=_official(), stored=_stored(),
    )['rows']
    assert rows
    for row in rows:
        assert row['prior_value_evidence_status'] == audit.EVIDENCE_UNPROVEN
        assert row['later_value_evidence_status'] == audit.EVIDENCE_UNPROVEN


# ── Preconditions ───────────────────────────────────────────────────────────

def test_the_production_shape_satisfies_every_precondition():
    """Complete storage, agreeing source, one display-only difference."""
    official = _official([
        _official_appearance(mlb_id, innings='1.0') for mlb_id in ARMS
    ])
    stored = _stored([
        _stored_appearance(mlb_id, innings='1.00') for mlb_id in ARMS
    ])
    evaluation = _evaluate(official=official, stored=stored)
    assert evaluation['violated'] == [], evaluation['violated']
    assert evaluation['not_observed'] == [], evaluation['not_observed']
    assert evaluation['all_satisfied'] is True


def test_every_governed_precondition_is_evaluated_every_time():
    evaluation = _evaluate()
    covered = {
        check['precondition_id'] for check in evaluation['preconditions']
    }
    assert covered == set(repair.PRECONDITION_IDS)


def test_a_missing_work_item_refuses_rather_than_creating_one():
    """A proven absence is a refusal, never missing evidence.

    Every row-detail precondition is VIOLATED here rather than unobserved:
    the database WAS opened and it positively established that no row exists.
    Reporting those as unobserved would make the run UNPROVEN — "we do not
    know" — about the one thing it knew exactly.
    """
    evaluation = _evaluate(work_item=None)
    # Zero rows must never report ``multiple_candidate_work_items``: the
    # uniqueness requirement is "no more than one", and zero satisfies it.
    assert _state_of(evaluation, repair.PRE_ROW_UNIQUE) == (
        repair.PRECONDITION_SATISFIED
    )
    assert repair.REFUSED_WORK_ITEM_MULTIPLE not in (
        evaluation['refusal_reasons']
    )
    for identifier in (
        repair.PRE_ROW_EXISTS, repair.PRE_ROW_GAME,
        repair.PRE_ROW_REPRESENTED_DATE, repair.PRE_ROW_STATUS,
        repair.PRE_EXISTING_REVISION,
    ):
        assert _state_of(evaluation, identifier) == (
            repair.PRECONDITION_VIOLATED
        ), identifier
    assert evaluation['not_observed'] == []
    assert repair.REFUSED_WORK_ITEM_MISSING in evaluation['refusal_reasons']
    decision = repair.decide(operation='apply', preconditions=evaluation)
    assert decision['result'] == repair.RESULT_REFUSED


def test_multiple_candidate_rows_refuse():
    target = {
        'observed': True, 'candidate_row_count': 2,
        'candidate_row_ids': [1, 2], 'work_item': None,
        'work_item_row_id': None,
    }
    comparison = repair.build_comparison(
        official=_official(), stored=_stored(),
    )
    expectation = repair.population_expectation(
        work_item=None, stored_appearance_count=3,
    )
    evaluation = repair.evaluate_preconditions(
        target=target, official=_official(), comparison=comparison,
        plan=_plan(), expectation=expectation,
        completeness=repair.source_completeness(
            official=_official(), comparison=comparison['summary'],
            database_observed=True, expectation=expectation,
        ),
        database_observed=True, before_fingerprints={'a': {'b': 'c'}},
    )
    assert _state_of(evaluation, repair.PRE_ROW_UNIQUE) == (
        repair.PRECONDITION_VIOLATED
    )
    assert repair.REFUSED_WORK_ITEM_MULTIPLE in evaluation['refusal_reasons']
    # Two rows must never report the row as missing.
    assert _state_of(evaluation, repair.PRE_ROW_EXISTS) == (
        repair.PRECONDITION_SATISFIED
    )
    assert repair.REFUSED_WORK_ITEM_MISSING not in (
        evaluation['refusal_reasons']
    )


def test_an_unexpected_existing_revision_refuses():
    evaluation = _evaluate(work_item=_work_item(source_revision=THIRD))
    assert _state_of(evaluation, repair.PRE_EXISTING_REVISION) == (
        repair.PRECONDITION_VIOLATED
    )
    assert repair.REFUSED_EXISTING_REVISION_UNEXPECTED in (
        evaluation['refusal_reasons']
    )


def test_an_absent_existing_revision_refuses_rather_than_filling_a_blank():
    evaluation = _evaluate(work_item=_work_item(source_revision=None))
    assert _state_of(evaluation, repair.PRE_EXISTING_REVISION) == (
        repair.PRECONDITION_VIOLATED
    )


def test_a_row_already_at_the_intended_value_is_reported_separately():
    evaluation = _evaluate(work_item=_work_item(source_revision=NEW))
    assert evaluation['already_at_intended_revision'] is True
    coverage = repair.precondition_coverage(evaluation)
    assert coverage['already_at_intended_revision'] is True
    assert coverage['blocking_violations'] == [repair.PRE_EXISTING_REVISION]


def test_a_status_that_is_not_completed_refuses():
    evaluation = _evaluate(work_item=_work_item(status='planned'))
    assert _state_of(evaluation, repair.PRE_ROW_STATUS) == (
        repair.PRECONDITION_VIOLATED
    )
    assert repair.REFUSED_STATUS_NOT_COMPLETED in evaluation['refusal_reasons']


def test_a_wrong_game_refuses():
    evaluation = _evaluate(work_item=_work_item(mlb_game_pk=999999))
    assert _state_of(evaluation, repair.PRE_ROW_GAME) == (
        repair.PRECONDITION_VIOLATED
    )


def test_a_wrong_represented_date_refuses():
    evaluation = _evaluate(work_item=_work_item(
        represented_date='2026-07-28',
    ))
    assert _state_of(evaluation, repair.PRE_ROW_REPRESENTED_DATE) == (
        repair.PRECONDITION_VIOLATED
    )


def test_a_current_revision_that_is_not_the_intended_value_refuses():
    evaluation = _evaluate(official=_official(revision=THIRD))
    assert _state_of(evaluation, repair.PRE_CURRENT_REVISION) == (
        repair.PRECONDITION_VIOLATED
    )
    assert repair.REFUSED_CURRENT_REVISION_NOT_INTENDED in (
        evaluation['refusal_reasons']
    )


def test_a_current_revision_matching_the_old_value_still_refuses():
    """Nothing changed upstream, so there is nothing to advance the mark to."""
    evaluation = _evaluate(official=_official(revision=OLD))
    assert _state_of(evaluation, repair.PRE_CURRENT_REVISION) == (
        repair.PRECONDITION_VIOLATED
    )


def test_a_governed_field_difference_refuses_because_this_is_not_a_data_repair(
):
    official = _official([
        _official_appearance(mlb_id, strikeouts=9) for mlb_id in ARMS
    ])
    evaluation = _evaluate(official=official)
    assert _state_of(evaluation, repair.PRE_NO_GOVERNED_DIFFERENCE) == (
        repair.PRECONDITION_VIOLATED
    )
    assert repair.REFUSED_GOVERNED_FIELD_DIFFERS in (
        evaluation['refusal_reasons']
    )


def test_a_canonical_plan_proposing_a_mutation_refuses():
    evaluation = _evaluate(plan=_plan(
        action_counts={'unchanged': 2, 'update': 1},
        proposes_update=True, all_unchanged=False, proposes_mutation=True,
    ))
    assert _state_of(evaluation, repair.PRE_CANONICAL_PLAN_CLEAN) == (
        repair.PRECONDITION_VIOLATED
    )
    assert repair.REFUSED_CANONICAL_PLAN_PROPOSES_MUTATION in (
        evaluation['refusal_reasons']
    )


def test_an_unavailable_canonical_plan_is_unproven_never_refused():
    evaluation = _evaluate(plan={'available': False, 'reason': 'x'})
    assert _state_of(evaluation, repair.PRE_CANONICAL_PLAN_CLEAN) == (
        repair.PRECONDITION_NOT_OBSERVED
    )
    assert repair.UNPROVEN_CANONICAL_PLAN_UNAVAILABLE in (
        evaluation['unproven_reasons']
    )


def test_an_empty_canonical_plan_is_not_a_clean_canonical_plan():
    evaluation = _evaluate(plan=_plan(row_count=0, action_counts={}))
    assert _state_of(evaluation, repair.PRE_CANONICAL_PLAN_CLEAN) == (
        repair.PRECONDITION_VIOLATED
    )


def test_a_database_that_was_never_opened_makes_row_facts_unobserved():
    evaluation = _evaluate(database_observed=False)
    for identifier in (
        repair.PRE_ROW_EXISTS, repair.PRE_ROW_UNIQUE, repair.PRE_ROW_GAME,
        repair.PRE_EXISTING_REVISION, repair.PRE_ROW_STATUS,
    ):
        assert _state_of(evaluation, identifier) == (
            repair.PRECONDITION_NOT_OBSERVED
        )
    assert repair.UNPROVEN_DATABASE_EVIDENCE_UNAVAILABLE in (
        evaluation['unproven_reasons']
    )
    assert repair.UNPROVEN_PRECONDITION_NOT_OBSERVED in (
        evaluation['unproven_reasons']
    )


def test_a_source_that_failed_to_fetch_is_unobserved_never_refused():
    """Knowing WHY evidence is missing does not make it present."""
    evaluation = _evaluate(official={
        'available': False, 'unavailable_reason': 'source_call_failed',
        'appearances': [], 'appearance_count': 0,
        'extraction_yielded_no_appearances': False,
        'current_source_revision': None, 'plan': None,
    })
    for identifier in (
        repair.PRE_SOURCE_OBSERVED, repair.PRE_SOURCE_COMPLETE,
        repair.PRE_CURRENT_REVISION,
    ):
        assert _state_of(evaluation, identifier) == (
            repair.PRECONDITION_NOT_OBSERVED
        ), identifier
    assert repair.REFUSED_SOURCE_NOT_CONCLUSION_ELIGIBLE not in (
        evaluation['refusal_reasons']
    )
    decision = repair.decide(operation='apply', preconditions=evaluation)
    assert decision['result'] == repair.RESULT_UNPROVEN


def test_an_empty_official_set_is_unobserved_evidence_not_a_gameless_game():
    evaluation = _evaluate(official={
        'available': False, 'unavailable_reason': 'empty',
        'appearances': [], 'appearance_count': 0,
        'extraction_yielded_no_appearances': True,
        'current_source_revision': None, 'plan': None,
    })
    assert _state_of(evaluation, repair.PRE_SOURCE_OBSERVED) == (
        repair.PRECONDITION_NOT_OBSERVED
    )
    assert repair.decide(
        operation='apply', preconditions=evaluation,
    )['result'] == repair.RESULT_UNPROVEN


def test_a_source_that_was_never_fetched_makes_source_facts_unobserved():
    evaluation = _evaluate(official={
        'available': False, 'unavailable_reason': None, 'appearances': [],
        'appearance_count': 0, 'extraction_yielded_no_appearances': False,
        'current_source_revision': None, 'plan': None,
    })
    assert _state_of(evaluation, repair.PRE_SOURCE_OBSERVED) == (
        repair.PRECONDITION_NOT_OBSERVED
    )
    assert _state_of(evaluation, repair.PRE_CURRENT_REVISION) == (
        repair.PRECONDITION_NOT_OBSERVED
    )


def test_uncomputable_scope_fingerprints_are_unobserved_never_satisfied():
    evaluation = _evaluate(before_fingerprints=None)
    assert _state_of(evaluation, repair.PRE_SCOPE_FINGERPRINTS) == (
        repair.PRECONDITION_NOT_OBSERVED
    )


# ── Mutation-scope evaluation ───────────────────────────────────────────────

CLEAN_GUARD = {
    'no_object_was_created': True,
    'no_object_was_deleted': True,
    'exactly_the_expected_objects_mutated': True,
    'only_the_target_type_mutated': True,
    'only_governed_attributes_changed': True,
}

CLEAN_STATEMENTS = {
    'exactly_one_target_update': True,
    'no_other_write_statement': True,
    'target_table_affected_rows': 1,
    'target_table_rowcount_observed': True,
}


def _mutation(**overrides):
    before = {'id': 1, 'source_revision': OLD, 'updated_at': 'A',
              'status': 'completed', 'rows_expected': 3}
    after = dict(before, source_revision=NEW, updated_at='B')
    payload = {
        'before_snapshot': before,
        'after_snapshot': after,
        'guard_checks': dict(CLEAN_GUARD),
        'affected_row_count': 1,
        'changed_tables': [[audit.SCOPE_EXACT_GAME, repair.TARGET_TABLE]],
        'out_of_scope_before': {'digest': 'x', 'row_count': 40},
        'out_of_scope_after': {'digest': 'x', 'row_count': 40},
        'statements': dict(CLEAN_STATEMENTS),
    }
    payload.update(overrides)
    return repair.evaluate_mutation(**payload)


def test_the_permitted_delta_is_exactly_the_column_plus_the_timestamp():
    result = _mutation()
    assert result['observed_changed_columns'] == [
        'source_revision', 'updated_at',
    ]
    assert result['changed_columns_are_exactly_permitted'] is True
    assert result['governed_changed_columns'] == ['source_revision']
    assert result['automatic_bookkeeping_changed_columns'] == ['updated_at']
    assert result['unpermitted_changed_columns'] == []
    assert result['mutation_within_scope'] is True
    assert result['failed_reasons'] == []


def test_the_updated_at_side_effect_is_disclosed_not_hidden():
    result = _mutation()
    assert 'onupdate' in result['updated_at_disclosure']
    assert 'automatic bookkeeping' in result['updated_at_disclosure']


def test_any_third_changed_column_is_a_contract_violation():
    before = {'id': 1, 'source_revision': OLD, 'updated_at': 'A',
              'status': 'completed'}
    after = dict(before, source_revision=NEW, updated_at='B',
                 status='superseded')
    result = _mutation(before_snapshot=before, after_snapshot=after)
    assert result['unpermitted_changed_columns'] == ['status']
    assert repair.FAILED_MUTATION_SCOPE_EXCEEDED in result['failed_reasons']


def test_a_post_state_that_is_not_the_intended_value_is_a_violation():
    before = {'id': 1, 'source_revision': OLD, 'updated_at': 'A'}
    after = dict(before, source_revision=THIRD, updated_at='B')
    result = _mutation(before_snapshot=before, after_snapshot=after)
    assert repair.FAILED_POST_STATE_NOT_INTENDED in result['failed_reasons']


@pytest.mark.parametrize('count', [0, 2, 12, None])
def test_affecting_anything_other_than_one_row_is_a_violation(count):
    result = _mutation(
        affected_row_count=count,
        statements=dict(CLEAN_STATEMENTS, target_table_affected_rows=count),
    )
    assert repair.FAILED_AFFECTED_ROW_COUNT_NOT_ONE in result['failed_reasons']


def test_a_created_object_is_a_violation():
    result = _mutation(guard_checks=dict(
        CLEAN_GUARD, no_object_was_created=False,
    ))
    assert repair.FAILED_UNEXPECTED_ROW_CREATED in result['failed_reasons']


def test_a_deleted_object_is_a_violation():
    result = _mutation(guard_checks=dict(
        CLEAN_GUARD, no_object_was_deleted=False,
    ))
    assert repair.FAILED_UNEXPECTED_ROW_DELETED in result['failed_reasons']


def test_mutating_a_second_work_item_is_a_violation():
    result = _mutation(guard_checks=dict(
        CLEAN_GUARD, exactly_the_expected_objects_mutated=False,
    ))
    assert repair.FAILED_OTHER_WORK_ITEM_MUTATED in result['failed_reasons']


def test_a_second_governed_table_moving_is_a_violation():
    result = _mutation(changed_tables=[
        [audit.SCOPE_EXACT_GAME, repair.TARGET_TABLE],
        [audit.SCOPE_EXACT_GAME, 'game_logs'],
    ])
    assert repair.FAILED_UNPERMITTED_SCOPE_CHANGED in result['failed_reasons']
    assert result['unexpected_changed_fingerprint_tables'] == [
        [audit.SCOPE_EXACT_GAME, 'game_logs'],
    ]


def test_a_target_table_that_did_not_move_after_an_apply_is_a_violation():
    """A repair that reported itself without moving the row is not a repair."""
    result = _mutation(changed_tables=[
        [audit.SCOPE_PITCHER_IDENTITY, 'pitchers'],
    ])
    assert repair.FAILED_TARGET_TABLE_UNCHANGED_AFTER_APPLY in (
        result['failed_reasons']
    )


def test_no_table_moving_at_all_after_a_commit_is_a_violation():
    """An empty CHANGED list is a computed observation, and it is wrong."""
    result = _mutation(changed_tables=[])
    assert result['changed_fingerprint_tables_observed'] is True
    assert repair.FAILED_TARGET_TABLE_UNCHANGED_AFTER_APPLY in (
        result['failed_reasons']
    )


def test_an_uncomputable_table_comparison_is_unproven_never_a_violation():
    """None is missing evidence, not an observation that nothing moved."""
    result = _mutation(changed_tables=None)
    assert result['changed_fingerprint_tables_observed'] is False
    assert repair.UNPROVEN_FINGERPRINT_UNAVAILABLE in (
        result['unproven_reasons']
    )
    assert repair.FAILED_TARGET_TABLE_UNCHANGED_AFTER_APPLY not in (
        result['failed_reasons']
    )
    assert result['mutation_within_scope'] is False


def test_another_games_checkpoint_moving_is_a_violation():
    result = _mutation(out_of_scope_after={'digest': 'y', 'row_count': 40})
    assert repair.FAILED_OUT_OF_SCOPE_TABLE_CHANGED in (
        result['failed_reasons']
    )


def test_an_uncomputable_out_of_scope_digest_is_unproven_never_a_pass():
    result = _mutation(out_of_scope_after=None)
    assert repair.UNPROVEN_OUT_OF_SCOPE_FINGERPRINT_UNAVAILABLE in (
        result['unproven_reasons']
    )
    assert result['mutation_within_scope'] is False


def test_a_second_write_statement_is_a_violation_even_with_a_clean_guard():
    """The database is asked what it was told, not only the session."""
    result = _mutation(statements=dict(
        CLEAN_STATEMENTS, no_other_write_statement=False,
    ))
    assert repair.FAILED_MUTATION_SCOPE_EXCEEDED in result['failed_reasons']


def test_two_updates_to_the_target_table_are_a_violation():
    result = _mutation(statements=dict(
        CLEAN_STATEMENTS, exactly_one_target_update=False,
    ))
    assert repair.FAILED_AFFECTED_ROW_COUNT_NOT_ONE in result['failed_reasons']


# ── changed_fingerprint_tables ──────────────────────────────────────────────

def test_changed_tables_names_the_table_not_only_the_scope():
    before = {'s': {'a': '1', 'b': '2'}}
    after = {'s': {'a': '1', 'b': '3'}}
    assert repair.changed_fingerprint_tables(before, after) == [['s', 'b']]


def test_identical_fingerprints_report_no_change():
    digests = {'s': {'a': '1'}}
    assert repair.changed_fingerprint_tables(digests, dict(digests)) == []


def test_a_missing_fingerprint_side_reports_nothing_rather_than_guessing():
    assert repair.changed_fingerprint_tables(None, {'s': {'a': '1'}}) == []


def test_changed_columns_is_symmetric_and_covers_added_keys():
    assert repair.changed_columns({'a': 1}, {'a': 1, 'b': 2}) == ['b']
    assert repair.changed_columns({'a': 1, 'b': 2}, {'a': 1}) == ['b']
