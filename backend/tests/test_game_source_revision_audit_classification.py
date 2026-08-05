"""Game 824487 source-revision audit — fingerprint, matrix, and classification.

Requirements 35-41 and 95-98, plus the independent classification dimensions.

The single most dangerous thing this audit could do is turn two opaque digests
into a confident story about a baseball field. These tests own the properties
that stop it: the fingerprint is proven deterministic rather than assumed, a
field inside the governed list moves the revision while a field outside it does
not, a digest is never mapped back to a field, a historical value that was
never retained is never presented as a null baseball value, and the six
classification dimensions stay six independent dimensions.
"""

import json
from datetime import date

import pytest

from services import game_appearance_extraction as extraction
from services import game_source_revision_audit as audit


REFERENCE = date(2026, 7, 29)


def _appearance(mlb_id, **overrides):
    record = {
        'game_pk': audit.GAME_PK,
        'game_date': REFERENCE,
        'pitcher_mlb_id': mlb_id,
        'team_id': 147,
        'opponent_team_id': 111,
        'side': 'home',
        'appearance_role': 'relief',
        'games_started': 0,
        'is_starter': False,
        'is_reliever': True,
        'outs_recorded': 3,
        'innings_pitched': 1.0,
        'earned_runs': 0,
        'runs_allowed': 0,
        'hits_allowed': 1,
        'walks': 0,
        'strikeouts': 2,
        'home_runs_allowed': 0,
        'batters_faced': 4,
        'pitches_thrown': 15,
        'source_authority': extraction.SOURCE_AUTHORITY,
    }
    record.update(overrides)
    return record


@pytest.fixture
def appearances():
    return [
        _appearance(7000 + index, outs_recorded=3 + index, strikeouts=index)
        for index in range(12)
    ]


# ── 35-36. Determinism over identical normalized content ────────────────────

def test_repeated_fingerprint_computation_is_stable(appearances):
    result = audit.fingerprint_determinism(appearances)
    assert result['deterministic_in_process'] is True
    assert len(set(result['repeated_fingerprints'])) == 1
    assert result['repeat_count'] == audit.DETERMINISM_REPEATS


def test_input_permutation_does_not_change_the_fingerprint(appearances):
    result = audit.fingerprint_determinism(appearances)
    assert result['permutation_count'] == audit.DETERMINISM_PERMUTATIONS
    assert set(result['permutation_fingerprints']) == set(
        result['repeated_fingerprints']
    )


def test_the_permutations_are_deterministic_and_actually_reorder(appearances):
    """No randomness: the same input yields the same permutations every time."""
    first = audit.deterministic_permutations(appearances)
    second = audit.deterministic_permutations(appearances)
    assert [
        [record['pitcher_mlb_id'] for record in order] for order in first
    ] == [
        [record['pitcher_mlb_id'] for record in order] for order in second
    ]
    original = [record['pitcher_mlb_id'] for record in appearances]
    assert any(
        [record['pitcher_mlb_id'] for record in order] != original
        for order in first
    )


def test_determinism_over_an_empty_set_is_unproven_not_true():
    result = audit.fingerprint_determinism([])
    assert result['deterministic_in_process'] is None
    assert result['evidence_status'] == audit.EVIDENCE_UNPROVEN


def test_the_determinism_check_issues_no_source_request(appearances, monkeypatch):
    from services import mlb_api

    def _explode(*_args, **_kwargs):
        raise AssertionError('the determinism check must not reach the wire')

    monkeypatch.setattr(mlb_api.mlb_client, '_get', _explode, raising=False)
    assert audit.fingerprint_determinism(appearances)[
        'deterministic_in_process'
    ] is True


# ── 37-38. What does and does not move the revision ─────────────────────────

@pytest.mark.parametrize('field,value', [
    ('outs_recorded', 99),
    ('earned_runs', 9),
    ('runs_allowed', 9),
    ('hits_allowed', 9),
    ('walks', 9),
    ('strikeouts', 99),
    ('home_runs_allowed', 9),
    ('batters_faced', 99),
    ('pitches_thrown', 999),
    ('games_started', 1),
    ('appearance_role', 'start'),
    ('team_id', 999),
    ('opponent_team_id', 999),
    ('pitcher_mlb_id', 999999),
])
def test_one_changed_fingerprint_field_changes_the_source_revision(
    appearances, field, value,
):
    assert field in extraction.FINGERPRINT_FIELDS
    before = extraction.appearance_set_fingerprint(appearances)
    mutated = [dict(record) for record in appearances]
    mutated[0][field] = value
    assert extraction.appearance_set_fingerprint(mutated) != before


@pytest.mark.parametrize('field,value', [
    ('innings_pitched', 99.0),
    ('side', 'away'),
    ('is_starter', True),
    ('is_reliever', False),
    ('source_authority', 'something_else'),
    ('game_date', date(2020, 1, 1)),
])
def test_fields_outside_the_governed_list_do_not_change_the_revision(
    appearances, field, value,
):
    assert field not in extraction.FINGERPRINT_FIELDS
    before = extraction.appearance_set_fingerprint(appearances)
    mutated = [dict(record) for record in appearances]
    mutated[0][field] = value
    assert extraction.appearance_set_fingerprint(mutated) == before


def test_the_governed_field_list_the_audit_reports_is_the_live_one():
    semantics = audit.source_revision_semantics()
    assert semantics['fingerprint_fields'] == list(
        extraction.FINGERPRINT_FIELDS
    )
    assert semantics['fingerprint_field_count'] == 14
    assert semantics['is_raw_payload_hash'] is False
    assert semantics['digest_is_invertible'] is False


# ── 39. A digest is never mapped back to a field ────────────────────────────

def test_the_audit_never_maps_a_digest_to_a_guessed_field():
    """The two known digests must not appear in any field-level answer."""
    delta = audit.field_delta_answer(
        artifacts={
            'all_required_present': True,
            'prior_row_level_values_retained': False,
        },
        classification={
            'historical_field_identification': audit.FIELD_ID_NOT_RETAINED,
        },
        matrix_summary={'proven_historical_fields': []},
    )
    assert delta['answer'] == audit.DELTA_NOT_RECOVERABLE
    assert delta['digest_was_not_inverted'] is True
    rendered = json.dumps(delta)
    assert audit.PRIOR_SOURCE_REVISION not in rendered
    assert audit.LATER_SOURCE_REVISION not in rendered
    assert not delta['proven_historical_fields']


def test_an_unrecoverable_delta_lists_exactly_what_evidence_was_missing():
    delta = audit.field_delta_answer(
        artifacts={
            'all_required_present': True,
            'prior_row_level_values_retained': False,
        },
        classification={
            'historical_field_identification': audit.FIELD_ID_NOT_RETAINED,
        },
        matrix_summary={},
    )
    assert delta['evidence_required_and_missing'] == list(
        audit.REQUIRED_MISSING_EVIDENCE
    )
    assert delta['evidence_available']


def test_retained_row_level_values_would_identify_the_delta():
    delta = audit.field_delta_answer(
        artifacts={
            'all_required_present': True,
            'prior_row_level_values_retained': True,
        },
        classification={
            'historical_field_identification': audit.FIELD_ID_IDENTIFIED,
        },
        matrix_summary={'proven_historical_fields': ['outs_recorded']},
    )
    assert delta['answer'] == audit.DELTA_IDENTIFIED
    assert delta['evidence_required_and_missing'] == []


# ── 40-41. Missing evidence versus a null baseball value ────────────────────

def test_missing_prior_row_level_evidence_produces_not_retained():
    row = audit.matrix_row(
        pitcher_mlb_id=7001, side='home', field_name='strikeouts',
        current_official_value=4, current_stored_value=4,
        prior_value=None,
        prior_value_evidence_status=audit.EVIDENCE_NOT_RETAINED,
        later_run_value=None,
        later_value_evidence_status=audit.EVIDENCE_NOT_RETAINED,
    )
    assert row['prior_value'] is None
    assert row['prior_value_evidence_status'] == audit.EVIDENCE_NOT_RETAINED
    assert row['later_value_evidence_status'] == audit.EVIDENCE_NOT_RETAINED


def test_a_null_baseball_value_stays_distinguishable_from_missing_evidence():
    """Both cells read ``None``. Only the status says which is which."""
    legitimately_null = audit.matrix_row(
        pitcher_mlb_id=7001, side='home', field_name='pitches_thrown',
        current_official_value=None, current_stored_value=None,
        prior_value=None,
        prior_value_evidence_status=audit.EVIDENCE_ABSENT,
    )
    never_recorded = audit.matrix_row(
        pitcher_mlb_id=7001, side='home', field_name='pitches_thrown',
        current_official_value=None, current_stored_value=None,
        prior_value=None,
        prior_value_evidence_status=audit.EVIDENCE_NOT_RETAINED,
    )
    assert legitimately_null['prior_value'] is None
    assert never_recorded['prior_value'] is None
    assert legitimately_null['prior_value_evidence_status'] != (
        never_recorded['prior_value_evidence_status']
    )
    # A null official value that equals a null stored value is still a MATCH.
    assert legitimately_null['current_values_match'] is True
    assert legitimately_null['conclusion'] == audit.CONCLUSION_MATCHES


def test_a_matrix_row_is_rejected_when_a_historical_status_is_missing():
    good = audit.matrix_row(
        pitcher_mlb_id=7001, side='home', field_name='walks',
        current_official_value=1, current_stored_value=1,
    )
    bad = dict(good, prior_value_evidence_status=None)
    assert audit.validate_matrix([good])['structurally_valid'] is True
    result = audit.validate_matrix([good, bad])
    assert result['structurally_valid'] is False
    assert result['rows_with_invalid_evidence_status'] == 1
    assert result['every_historical_cell_carries_a_status'] is False


# ── Materiality (79-83) ─────────────────────────────────────────────────────

def test_a_canonical_outs_difference_is_material():
    assert audit.field_materiality('outs_recorded', 18, 17) == (
        audit.MATERIALITY_CANONICAL_OUTS
    )


def test_a_decimal_only_innings_display_difference_is_not_a_correction():
    """Recorded outs are the permanent innings authority.

    A stored float and a freshly derived float can differ in representation
    while describing the same canonical outs. Calling that a baseball
    correction is exactly the defect the reconciliation planner already
    refuses to make, and this audit refuses it too.
    """
    materiality = audit.field_materiality(
        'innings_pitched', 6.0, 5.999999999999999,
    )
    assert materiality == audit.MATERIALITY_DISPLAY_ONLY
    assert materiality != audit.MATERIALITY_CANONICAL_OUTS
    assert materiality != audit.MATERIALITY_STATISTICAL


def test_a_role_difference_is_detected():
    assert audit.field_materiality('appearance_role', 'start', 'relief') == (
        audit.MATERIALITY_ROLE
    )
    assert audit.field_materiality('games_started', 1, 0) == (
        audit.MATERIALITY_ROLE
    )


def test_a_team_or_opponent_difference_is_detected():
    assert audit.field_materiality('team_id', 147, 111) == (
        audit.MATERIALITY_APPEARANCE_TEAM
    )
    assert audit.field_materiality('opponent_team_id', 111, 147) == (
        audit.MATERIALITY_APPEARANCE_TEAM
    )
    assert audit.field_materiality('appearance_team_status', 'resolved', None) \
        == audit.MATERIALITY_APPEARANCE_TEAM


def test_a_statistical_difference_is_detected():
    for field in ('earned_runs', 'strikeouts', 'walks', 'hits_allowed'):
        assert audit.field_materiality(field, 3, 2) == (
            audit.MATERIALITY_STATISTICAL
        )


def test_equal_values_are_never_material():
    for field in extraction.FINGERPRINT_FIELDS:
        assert audit.field_materiality(field, 5, 5) == audit.MATERIALITY_NONE


# ── 95-98. Causality ────────────────────────────────────────────────────────

def _activation(**overrides):
    """A fully-observed activation evidence view, as the parser produces it."""
    view = {
        'unresolved_rows': 0,
        'prohibited_identity_actions': 0,
        'source_revision_match': False,
        'safe_digest_match': True,
        'all_projected_targets_realized': False,
        'observed_fields': list(audit.Q10_FIELDS),
        'missing_fields': [],
        'missing_evidence_paths': [],
        'mismatched_fields': [],
        'all_required_observed': True,
        'state': audit.STATE_VERIFIED,
        'artifact_present': True,
    }
    view.update(overrides)
    if 'missing_fields' in overrides:
        view['all_required_observed'] = not overrides['missing_fields']
        view['observed_fields'] = [
            field for field in audit.Q10_FIELDS
            if field not in overrides['missing_fields']
        ]
    return view


def test_one_source_revision_mismatch_causes_both_observer_invariants():
    result = audit.causality(
        realization_symbol_state=audit.DRIFT_EQUAL,
        later_activation=_activation(),
        drift=False,
    )
    assert result['answer'] == audit.CAUSALITY_SINGLE_CHAIN
    assert result['fully_answered'] is True
    assert result['realization_definition_verified_at_failed_run_sha'] is True
    assert 'source_revision_match' in result['invariant_definition']
    assert result['expectations_supplied_no_value'] is True


def test_an_independent_unresolved_row_failure_is_distinguished():
    result = audit.causality(
        realization_symbol_state=audit.DRIFT_EQUAL,
        later_activation=_activation(unresolved_rows=2),
        drift=False,
    )
    assert result['answer'] == audit.CAUSALITY_INDEPENDENT_UNRESOLVED


def test_an_independent_prohibited_identity_failure_is_distinguished():
    result = audit.causality(
        realization_symbol_state=audit.DRIFT_EQUAL,
        later_activation=_activation(prohibited_identity_actions=1),
        drift=False,
    )
    assert result['answer'] == audit.CAUSALITY_INDEPENDENT_IDENTITY


def test_realization_code_drift_prevents_an_unsupported_causality_claim():
    result = audit.causality(
        realization_symbol_state=audit.DRIFT_CHANGED,
        later_activation=_activation(),
        drift=True,
    )
    assert result['answer'] == audit.CAUSALITY_UNPROVEN_CODE_DRIFT
    assert result['realization_definition_verified_at_failed_run_sha'] is False


def test_an_unreadable_failed_run_sha_makes_causality_unproven():
    result = audit.causality(
        realization_symbol_state=audit.DRIFT_UNAVAILABLE,
        later_activation=_activation(),
        drift=False,
    )
    assert result['answer'] == audit.CAUSALITY_UNPROVEN


def test_absent_invariant_counters_make_causality_unproven():
    result = audit.causality(
        realization_symbol_state=audit.DRIFT_EQUAL,
        later_activation=_activation(
            unresolved_rows=None, prohibited_identity_actions=None,
            missing_fields=[
                'unresolved_rows', 'prohibited_identity_actions',
            ],
        ),
        drift=False,
    )
    assert result['answer'] == audit.CAUSALITY_UNPROVEN


# ── Independent classification dimensions (Q11) ─────────────────────────────

# A matrix whose MEMBERSHIP is exactly matched. Tests that vary field-level
# differences inherit this so they keep exercising the field-difference path
# rather than tripping the membership gate, and tests that care about
# membership override these keys explicitly.
_MATRIX_BASE = {
    'structurally_valid': True,
    'differing_rows': [],
    'membership_matches': True,
    'missing_from_storage': [],
    'extra_in_storage': [],
    'official_missing_row_count': 0,
    'stored_missing_row_count': 0,
    'official_pitcher_mlb_ids': list(range(7001, 7013)),
    'stored_pitcher_mlb_ids': list(range(7001, 7013)),
}


def _classify(**overrides):
    if 'matrix_summary' in overrides:
        overrides['matrix_summary'] = dict(
            _MATRIX_BASE, **(overrides['matrix_summary'] or {})
        )
    kwargs = {
        'artifacts': {
            'all_required_present': True,
            'identity_all_verified': True,
            'content_all_verified': True,
            'revision_change_proven': True,
            'prior_row_level_values_retained': False,
            'unassociable_historical_candidates': 0,
            'historical_delta': {'delta_identified': False},
        },
        'code_drift': {
            'comparison_complete': True,
            'source_revision_affecting_drift': [],
            'semantic_drift_targets': [],
        },
        'determinism': {
            'deterministic_in_process': True,
            'appearance_count': audit.EXPECTED_APPEARANCE_COUNT,
        },
        'current_revision_state': audit.CURRENT_MATCHES_LATER,
        'matrix_summary': dict(_MATRIX_BASE),
        'plan_observation': {
            'action_counts': {'unchanged': 12}, 'proposes_mutation': False,
        },
        'checkpoint': {
            'exists': True, 'inconsistent': False,
            'matches_current_revision': True,
            'matches_any_observed_revision': True,
        },
        'source_available': True,
    }
    kwargs.update(overrides)
    # Exact-match materiality now REQUIRES a positively resolved current-set
    # completeness verdict. Callers that do not supply one get the fail-closed
    # default, so this helper derives the real one from whatever matrix
    # summary the individual test set up rather than asserting eligibility.
    kwargs.setdefault('source_completeness', audit.current_source_completeness(
        official={
            'available': kwargs['source_available'],
            'appearance_count': len(
                (kwargs['matrix_summary'] or {}).get(
                    'official_pitcher_mlb_ids'
                ) or ()
            ),
        },
        matrix_summary=kwargs['matrix_summary'],
        database_observed=True,
    ))
    return audit.classify(**kwargs)


def test_the_six_dimensions_are_reported_separately():
    result = _classify()
    assert set(result) == {
        'root_condition', 'current_materiality', 'persistence',
        'historical_field_identification', 'checkpoint_state',
        'current_source_completeness',
    }
    assert result['current_source_completeness'] in (
        audit.SOURCE_COMPLETENESS_STATES
    )
    assert result['root_condition'] in audit.ROOT_CONDITIONS
    assert result['current_materiality'] in audit.CURRENT_MATERIALITIES
    assert result['persistence'] in audit.PERSISTENCE_STATES
    assert result['historical_field_identification'] in (
        audit.FIELD_IDENTIFICATIONS
    )
    assert result['checkpoint_state'] in audit.CHECKPOINT_STATES


def test_a_clean_current_state_classifies_as_an_exact_match():
    result = _classify()
    assert result['current_materiality'] == audit.MATERIALITY_EXACT_MATCH
    assert result['persistence'] == audit.PERSISTENCE_MATCHES_LATER
    assert result['checkpoint_state'] == audit.CHECKPOINT_CURRENT
    assert result['historical_field_identification'] == (
        audit.FIELD_ID_NOT_RETAINED
    )


def test_a_nondeterministic_fingerprint_dominates_the_root_condition():
    result = _classify(determinism={'deterministic_in_process': False})
    assert result['root_condition'] == audit.ROOT_FINGERPRINT_NONDETERMINISM


def test_revision_affecting_code_drift_classifies_as_a_code_path_change():
    result = _classify(code_drift={
        'comparison_complete': True,
        'source_revision_affecting_drift': ['extraction.FINGERPRINT_FIELDS'],
        'semantic_drift_targets': ['extraction.FINGERPRINT_FIELDS'],
    })
    assert result['root_condition'] == audit.ROOT_CODE_PATH_CHANGED
    assert result['historical_field_identification'] == audit.FIELD_ID_NARROWED


def test_an_incomplete_code_comparison_leaves_the_root_condition_unproven():
    result = _classify(code_drift={
        'comparison_complete': False,
        'source_revision_affecting_drift': [],
        'semantic_drift_targets': [],
    })
    assert result['root_condition'] == audit.ROOT_UNPROVEN
    assert result['historical_field_identification'] == (
        audit.FIELD_ID_NOT_RETAINED
    )


def test_a_checkpoint_holding_no_observed_revision_is_inconsistent_evidence():
    result = _classify(checkpoint={
        'exists': True, 'inconsistent': False,
        'matches_current_revision': False,
        'matches_any_observed_revision': False,
    })
    assert result['root_condition'] == (
        audit.ROOT_ARTIFACT_CHECKPOINT_INCONSISTENCY
    )
    assert result['checkpoint_state'] == audit.CHECKPOINT_STALE


def test_a_missing_checkpoint_is_reported_as_missing():
    result = _classify(checkpoint={
        'exists': False, 'inconsistent': False,
        'matches_current_revision': None,
        'matches_any_observed_revision': None,
    })
    assert result['checkpoint_state'] == audit.CHECKPOINT_MISSING


def test_an_inconsistent_checkpoint_is_reported_as_inconsistent():
    result = _classify(checkpoint={
        'exists': True, 'inconsistent': True,
        'matches_current_revision': True,
        'matches_any_observed_revision': True,
    })
    assert result['checkpoint_state'] == audit.CHECKPOINT_INCONSISTENT


def test_an_unreadable_checkpoint_is_unproven_not_missing():
    result = _classify(checkpoint={
        'exists': None, 'inconsistent': False,
        'matches_current_revision': None,
        'matches_any_observed_revision': None,
    })
    assert result['checkpoint_state'] == audit.CHECKPOINT_UNPROVEN


@pytest.mark.parametrize('state,expected', [
    (audit.CURRENT_MATCHES_LATER, audit.PERSISTENCE_MATCHES_LATER),
    (audit.CURRENT_MATCHES_PRIOR, audit.PERSISTENCE_REVERTED),
    (audit.CURRENT_MATCHES_NEITHER, audit.PERSISTENCE_CHANGED_AGAIN),
    (audit.CURRENT_SOURCE_UNAVAILABLE, audit.PERSISTENCE_UNAVAILABLE),
])
def test_persistence_follows_the_current_revision_state(state, expected):
    result = _classify(
        current_revision_state=state,
        source_available=state != audit.CURRENT_SOURCE_UNAVAILABLE,
    )
    assert result['persistence'] == expected


def test_an_unavailable_current_source_is_never_an_exact_match():
    result = _classify(
        source_available=False,
        current_revision_state=audit.CURRENT_SOURCE_UNAVAILABLE,
    )
    assert result['current_materiality'] == audit.MATERIALITY_SOURCE_UNAVAILABLE
    assert result['root_condition'] == audit.ROOT_UNPROVEN


def test_a_plan_proposing_a_mutation_is_material_to_the_writer_target():
    result = _classify(plan_observation={
        'action_counts': {'update': 1, 'unchanged': 11},
        'proposes_mutation': True,
    })
    assert result['current_materiality'] == audit.MATERIALITY_MATERIAL


def test_display_only_differences_alone_are_not_material():
    result = _classify(matrix_summary={
        'structurally_valid': True,
        'differing_rows': [{
            'pitcher_mlb_id': 7001, 'field_name': 'innings_pitched',
            'materiality': audit.MATERIALITY_DISPLAY_ONLY,
        }],
    })
    assert result['current_materiality'] == audit.MATERIALITY_NON_MATERIAL


def test_a_canonical_outs_difference_makes_the_mismatch_material():
    result = _classify(matrix_summary={
        'structurally_valid': True,
        'differing_rows': [{
            'pitcher_mlb_id': 7001, 'field_name': 'outs_recorded',
            'materiality': audit.MATERIALITY_CANONICAL_OUTS,
        }],
    })
    assert result['current_materiality'] == audit.MATERIALITY_MATERIAL


def test_an_unproven_artifact_set_cannot_prove_a_root_condition():
    result = _classify(artifacts={
        'all_required_present': False,
        'identity_all_verified': False,
        'content_all_verified': False,
        'revision_change_proven': False,
        'prior_row_level_values_retained': False,
        'unassociable_historical_candidates': 0,
        'historical_delta': {'delta_identified': False},
    })
    assert result['root_condition'] == audit.ROOT_UNPROVEN
    assert result['historical_field_identification'] == audit.FIELD_ID_UNPROVEN


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER-A — exact-match materiality requires exact membership
#
# An empty ``differing_rows`` list is a statement about the rows that were
# COMPARABLE. On its own it can never establish that the current official
# target matches storage.
# ══════════════════════════════════════════════════════════════════════════

def _membership(*, official, stored, count=None, available=True,
                database_observed=True, structurally_valid=True):
    official_ids, stored_ids = list(official), list(stored)
    matrix_summary = {
        'structurally_valid': structurally_valid,
        'differing_rows': [],
        'official_pitcher_mlb_ids': official_ids,
        'stored_pitcher_mlb_ids': stored_ids,
        'membership_matches': set(official_ids) == set(stored_ids),
        'missing_from_storage': sorted(set(official_ids) - set(stored_ids)),
        'extra_in_storage': sorted(set(stored_ids) - set(official_ids)),
        'official_missing_row_count': len(
            set(stored_ids) - set(official_ids)
        ),
        'stored_missing_row_count': len(set(official_ids) - set(stored_ids)),
    }
    completeness = audit.current_source_completeness(
        official={
            'available': available,
            'appearance_count': (
                len(official_ids) if count is None else count
            ),
        },
        matrix_summary=matrix_summary, database_observed=database_observed,
    )
    return matrix_summary, completeness


def _classify_membership(**kwargs):
    matrix_summary, completeness = _membership(**kwargs)
    return _classify(
        matrix_summary=matrix_summary, source_completeness=completeness,
        source_available=kwargs.get('available', True),
    )


ALL_TWELVE = list(range(7001, 7013))


def test_exact_membership_with_no_field_difference_is_an_exact_match():
    result = _classify_membership(official=ALL_TWELVE, stored=ALL_TWELVE)
    assert result['current_materiality'] == audit.MATERIALITY_EXACT_MATCH
    assert result['current_source_completeness'] == audit.SOURCE_COMPLETE


def test_an_empty_official_set_is_unproven_not_an_exact_match():
    result = _classify_membership(official=[], stored=ALL_TWELVE, count=0)
    assert result['current_materiality'] == audit.MATERIALITY_UNPROVEN
    assert result['current_source_completeness'] == audit.SOURCE_EMPTY


def test_a_partial_official_set_is_unproven_not_an_exact_match():
    result = _classify_membership(official=ALL_TWELVE[:6], stored=ALL_TWELVE)
    assert result['current_materiality'] == audit.MATERIALITY_UNPROVEN
    assert result['current_source_completeness'] == (
        audit.SOURCE_STORED_ONLY_MEMBERS
    )


def test_an_official_pitcher_missing_from_storage_is_material():
    result = _classify_membership(
        official=ALL_TWELVE, stored=ALL_TWELVE[:-1],
    )
    assert result['current_materiality'] == audit.MATERIALITY_MATERIAL
    assert result['current_source_completeness'] == (
        audit.SOURCE_OFFICIAL_ONLY_MEMBERS
    )


def test_membership_differing_in_both_directions_is_unproven():
    result = _classify_membership(
        official=ALL_TWELVE, stored=ALL_TWELVE[1:] + [7099],
    )
    assert result['current_materiality'] == audit.MATERIALITY_UNPROVEN
    assert result['current_source_completeness'] == (
        audit.SOURCE_BOTH_DIRECTIONS
    )


def test_no_membership_deficit_can_ever_reach_exact_match():
    """The whole point: differing_rows == [] is not proof of set equality."""
    for official, stored, count in (
        ([], ALL_TWELVE, 0),
        (ALL_TWELVE[:6], ALL_TWELVE, None),
        (ALL_TWELVE, ALL_TWELVE[:-1], None),
        (ALL_TWELVE, ALL_TWELVE[1:] + [7099], None),
        ([], [], 0),
    ):
        result = _classify_membership(
            official=official, stored=stored, count=count,
        )
        assert result['current_materiality'] != (
            audit.MATERIALITY_EXACT_MATCH
        ), f'{official!r} vs {stored!r} reached exact match'


def test_an_unobserved_database_cannot_reach_exact_match():
    result = _classify_membership(
        official=ALL_TWELVE, stored=ALL_TWELVE, database_observed=False,
    )
    assert result['current_materiality'] == audit.MATERIALITY_UNPROVEN


def test_a_classifier_given_no_completeness_verdict_fails_closed():
    """Callers that never resolved completeness get UNPROVEN, not a match."""
    result = _classify(source_completeness=None)
    assert result['current_materiality'] != audit.MATERIALITY_EXACT_MATCH


# ── HIGH-B — determinism is structurally load-bearing ───────────────────────

def test_unobserved_determinism_makes_the_root_condition_unproven():
    result = _classify(determinism={'deterministic_in_process': None})
    assert result['root_condition'] == audit.ROOT_UNPROVEN


def test_nondeterminism_still_reports_the_fingerprint_root_condition():
    result = _classify(determinism={
        'deterministic_in_process': False, 'appearance_count': 12,
    })
    assert result['root_condition'] == audit.ROOT_FINGERPRINT_NONDETERMINISM


def test_unobserved_determinism_cannot_reach_exact_match():
    matrix_summary, completeness = _membership(
        official=ALL_TWELVE, stored=ALL_TWELVE,
    )
    result = _classify(
        matrix_summary=matrix_summary, source_completeness=completeness,
        determinism={'deterministic_in_process': None},
    )
    assert result['current_materiality'] != audit.MATERIALITY_EXACT_MATCH


# ── Q12 must not read as agreement while membership is open ────────────────

def test_an_unresolved_membership_never_recommends_continued_observation():
    for official, stored, count in (
        ([], ALL_TWELVE, 0),
        (ALL_TWELVE[:6], ALL_TWELVE, None),
        (ALL_TWELVE, ALL_TWELVE[:-1], None),
    ):
        classification = _classify_membership(
            official=official, stored=stored, count=count,
        )
        supported = audit.operational_consequence(
            classification,
        )['supported_by_evidence']
        assert audit.CONSEQUENCE_CONTINUED_OBSERVATION not in supported
        assert audit.CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW in supported


def test_a_resolved_exact_match_still_recommends_continued_observation():
    classification = _classify_membership(
        official=ALL_TWELVE, stored=ALL_TWELVE,
    )
    supported = audit.operational_consequence(
        classification,
    )['supported_by_evidence']
    assert audit.CONSEQUENCE_CONTINUED_OBSERVATION in supported
    assert audit.CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW not in supported


def test_the_new_consequence_is_in_the_declared_vocabulary():
    assert audit.CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW in audit.CONSEQUENCES
