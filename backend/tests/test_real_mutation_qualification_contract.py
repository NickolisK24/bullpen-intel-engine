"""The real-mutation qualification contract, executed rather than described.

Every refusal condition in the contract has a test here. The failure matrix is
the point: a gate that is only asserted by reading prose is a gate nobody has
run.

Inverted-assertion note. The no-op contract asserts ABSENCE — every counter
zero, every digest identical. This contract asserts an EXACT PRESENCE: one row,
one field, one value, and absence everywhere else. ``game_log_rows_written`` is
pinned to exactly 1 rather than ``>= 1``, because the reviewed plan named one
row and any other count is a different mutation than the one a human authorized.
"""

import pytest

from services import game_driven_ingestion as lane
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from services import real_mutation_qualification as qualification


GAME_PK = 824969
OTHER_GAME_PK = 824970
PITCHER_MLB_ID = 656240
SHA = 'a' * 40
OTHER_SHA = 'b' * 40
FINGERPRINT = 'f' * 64
OTHER_FINGERPRINT = 'e' * 64
REVIEWED_FIELD = 'earned_runs'
TARGET_DIGEST = 'targetdigest'
STORED_DIGEST = 'storeddigest'


def context(**overrides):
    base = {
        'event_name': 'workflow_dispatch',
        'repository': 'NickolisK24/bullpen-intel-engine',
        'actor': 'NickolisK24',
        'ref': 'refs/heads/main',
        'github_sha': SHA,
        'expected_head_sha': SHA,
        'confirmation': f'QUALIFY_REAL_MUTATION_GAME_{GAME_PK}',
    }
    base.update(overrides)
    return base


def unchanged_row(pitcher_mlb_id=5001, **overrides):
    base = {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': pitcher_mlb_id,
        'action': reconciliation.ACTION_UNCHANGED,
        'changed_fields': [],
        'semantic_changed_fields': [],
        'mutation_categories': [reconciliation.CATEGORY_UNCHANGED],
        'is_statistical_correction': False,
        'pitcher_identity_action': pitcher_identity.ACTION_UNCHANGED,
        'target_fields': [],
        'target_state_digest': '',
        'stored_state_digest': '',
        'difference_classifications': [],
    }
    base.update(overrides)
    return base


def update_row(field=REVIEWED_FIELD, **overrides):
    base = {
        'game_pk': GAME_PK,
        'pitcher_mlb_id': PITCHER_MLB_ID,
        'action': reconciliation.ACTION_UPDATE,
        'changed_fields': [field],
        'semantic_changed_fields': [field],
        'mutation_categories': [
            reconciliation.CATEGORY_STATISTICAL_CORRECTION
        ],
        'is_statistical_correction': True,
        'pitcher_identity_action': pitcher_identity.ACTION_UNCHANGED,
        'target_fields': [field],
        'target_state_digest': TARGET_DIGEST,
        'stored_state_digest': STORED_DIGEST,
        'mutation_digest': 'mutation-1',
        'difference_classifications': [reconciliation.DIFFERENCE_STATISTICAL],
        'affects_published_evidence': True,
    }
    base.update(overrides)
    return base


def effects(**overrides):
    base = {
        'writes_enabled': True,
        'publication_authoritative': False,
        # The canonical lane's real one-correction values.
        'game_log_rows_written': 1,
        'pitcher_rows_written': 0,
        'appearance_team_rows_written': 0,
        'correction_provenance_rows_written': 1,
        'dead_letters_created': 0,
        'work_items_created': 0,
        'work_items_updated': 1,
        'work_items_completed': 1,
        'checkpoints_advanced': 1,
        'commits_performed': 1,
    }
    base.update(overrides)
    return base


def report(*, rows=None, mode=lane.MODE_WRITE, status='complete', **overrides):
    rows = [update_row(), unchanged_row()] if rows is None else rows
    base = {
        'status': status,
        'mode': mode,
        'requested_game_pks': [GAME_PK],
        'planned_game_pks': [GAME_PK],
        'unexpected_planned_game_pks': [],
        'missing_requested_game_pks': [],
        'duplicate_requested_count': 0,
        'execution_scope_mode': 'exclusive',
        'execution_scope_exact_match': True,
        'games_fetched': 2,
        'games_attempted': 1,
        'games_completed': 1,
        'reconciliation_plan_fingerprint': FINGERPRINT,
        'authorized_plan_fingerprint': FINGERPRINT,
        'games': [{
            'game_pk': GAME_PK,
            'source_revision': 'rev-1',
            'rows': rows,
        }],
        'execution_effects': effects(),
    }
    for field in qualification.PROHIBITED_PLAN_COUNTERS:
        base.setdefault(field, 0)
    updates = len([
        entry for entry in rows
        if entry.get('action') == reconciliation.ACTION_UPDATE
    ])
    base.setdefault('rows_updated', updates)
    base.setdefault('statistical_corrections', updates)
    base['rows_unchanged'] = len(rows) - updates
    base.update(overrides)
    return base


def row_state(*, available=True, reviewed_field=REVIEWED_FIELD,
              value=3, target_digest='row-after', unreviewed='unreviewed-1',
              others='others-1', target_rows=1):
    return {
        'available': available,
        'identity_resolved': True,
        'game_row_count': 2,
        'target_row_count': target_rows,
        'other_row_count': 1,
        'reviewed_field': reviewed_field,
        'reviewed_field_value': value,
        'target_row_digest': target_digest,
        'target_unreviewed_digest': unreviewed,
        'other_rows_digest': others,
    }


def realization(**overrides):
    base = {
        'applicable': True,
        'projected_rows': 2,
        'projected_updates': 1,
        'realized_rows': 1,
        'already_matching_rows': 1,
        'divergent_rows': 0,
        'missing_rows': 0,
        'duplicate_rows': 0,
        'unresolved_rows': 0,
        'prohibited_identity_actions': 0,
        'all_projected_targets_realized': True,
    }
    base.update(overrides)
    return base


def bookkeeping(*, available=True, present=True, status_before='completed',
                status_after='completed', attempts=(1, 2), corrections=(0, 1),
                unrelated='unrelated-1', checkpoints='checkpoints-1',
                extra_after=None):
    before = {
        'status': status_before,
        'attempt_count': attempts[0],
        'correction_count': corrections[0],
        'candidate_reason': 'explicit_repair',
        'rows_reconciled': 8,
    }
    after = {
        'status': status_after,
        'attempt_count': attempts[1],
        'correction_count': corrections[1],
        'candidate_reason': 'explicit_repair',
        'rows_reconciled': 8,
    }
    if extra_after:
        after.update(extra_after)
    return (
        {
            'available': available,
            'target': before if present else None,
            'target_present': present,
            'unrelated_count': 108,
            'unrelated_work_items_digest': unrelated,
            'unrelated_checkpoints_digest': checkpoints,
        },
        {
            'available': available,
            'target': after if present else None,
            'target_present': present,
            'unrelated_count': 108,
            'unrelated_work_items_digest': unrelated,
            'unrelated_checkpoints_digest': checkpoints,
        },
    )


GUARD_OK = {'acquired': True, 'release_attempted': True, 'released': True}


def assess(**overrides):
    before_book, after_book = bookkeeping()
    base = {
        'context': context(),
        'game_pk': GAME_PK,
        'reviewed_fingerprint': FINGERPRINT,
        'shadow_report': report(mode=lane.MODE_SHADOW),
        'write_report': report(),
        'before_state': row_state(value=2, target_digest='row-before'),
        'after_state': row_state(value=3, target_digest='row-after'),
        'realized_digest': TARGET_DIGEST,
        'realization': realization(),
        'bookkeeping_before': before_book,
        'bookkeeping_after': after_book,
        'writer_guard': dict(GUARD_OK),
    }
    base.update(overrides)
    return qualification.assess(**base)


# ── Baseline ────────────────────────────────────────────────────────────────


def test_a_clean_single_field_correction_passes():
    decision = assess()
    assert decision['failed_reasons'] == []
    assert decision['unproven_reasons'] == []
    assert decision['result'] == qualification.RESULT_PASS
    assert decision['exit_code'] == 0


def test_pass_records_the_reviewed_mutation_descriptor():
    decision = assess()
    reviewed = decision['reviewed_mutation']
    assert reviewed['game_pk'] == GAME_PK
    assert reviewed['pitcher_mlb_id'] == PITCHER_MLB_ID
    assert reviewed['field'] == REVIEWED_FIELD
    assert reviewed['target_state_digest'] == TARGET_DIGEST


def test_the_four_terminal_results_have_distinct_exit_codes():
    assert qualification.EXIT_CODES == {
        'PASS': 0, 'FAILED': 1, 'UNPROVEN': 2, 'NO_LONGER_MUTATING': 3,
    }


# ── Authorization ───────────────────────────────────────────────────────────


@pytest.mark.parametrize('overrides,reason', [
    ({'event_name': 'schedule'},
     qualification.FAILED_EVENT_NOT_WORKFLOW_DISPATCH),
    ({'event_name': 'workflow_run'},
     qualification.FAILED_EVENT_NOT_WORKFLOW_DISPATCH),
    ({'repository': 'someone/else'},
     qualification.FAILED_REPOSITORY_NOT_AUTHORIZED),
    ({'actor': 'someone-else'}, qualification.FAILED_ACTOR_NOT_AUTHORIZED),
    ({'actor': 'github-actions[bot]'},
     qualification.FAILED_ACTOR_NOT_AUTHORIZED),
    ({'ref': 'refs/heads/ops/branch'}, qualification.FAILED_REF_NOT_MAIN),
    ({'expected_head_sha': 'short'},
     qualification.FAILED_EXPECTED_SHA_MALFORMED),
    ({'expected_head_sha': OTHER_SHA},
     qualification.FAILED_EXPECTED_SHA_MISMATCH),
    ({'confirmation': 'QUALIFY_REAL_MUTATION_GAME_1'},
     qualification.FAILED_CONFIRMATION_MISMATCH),
    ({'confirmation': f'QUALIFY_NOOP_GAME_{GAME_PK}'},
     qualification.FAILED_CONFIRMATION_MISMATCH),
    ({'confirmation': ''}, qualification.FAILED_CONFIRMATION_MISMATCH),
])
def test_authorization_refusals(overrides, reason):
    failures = qualification.validate_authorization(
        context(**overrides), game_pk=GAME_PK,
    )
    assert reason in failures


def test_authorization_reports_every_failure_not_only_the_first():
    failures = qualification.validate_authorization(
        context(actor='x', ref='refs/heads/other', repository='a/b'),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_ACTOR_NOT_AUTHORIZED in failures
    assert qualification.FAILED_REF_NOT_MAIN in failures
    assert qualification.FAILED_REPOSITORY_NOT_AUTHORIZED in failures


def test_confirmation_prefix_is_the_real_mutation_one():
    assert qualification.expected_confirmation(GAME_PK) == (
        f'QUALIFY_REAL_MUTATION_GAME_{GAME_PK}'
    )


@pytest.mark.parametrize('raw', [
    '824969,824970', '824969 824970', '824969-824970', '2026-08-19',
    '*', '', '   ', 'all', '-5', '0', '8249.69',
])
def test_malformed_game_scope_is_refused(raw):
    with pytest.raises(qualification.QualificationInputError):
        qualification.parse_game_pk(raw)


@pytest.mark.parametrize('raw', [
    '', 'f' * 63, 'f' * 65, 'g' * 64, 'F' * 63 + 'z', None, '   ',
])
def test_malformed_reviewed_fingerprint_is_refused(raw):
    with pytest.raises(qualification.QualificationInputError) as exc:
        qualification.parse_reviewed_fingerprint(raw)
    assert exc.value.reason == (
        qualification.FAILED_REVIEWED_FINGERPRINT_MALFORMED
    )


def test_reviewed_fingerprint_is_normalised_to_lowercase():
    assert qualification.parse_reviewed_fingerprint(
        ('A' * 64) + ''
    ) == 'a' * 64


# ── Field source authority ──────────────────────────────────────────────────


def test_inherited_runners_is_refused_while_its_authority_is_unresolved():
    """The recorded open question in the runbook, encoded as a gate.

    docs/current/GAME_DRIVEN_DAILY_INGESTION.md carries a live section titled
    "GameLog `inherited_runners` — field authority UNRESOLVED", status
    "unresolved, failed closed". Until that is resolved and recorded, no
    qualification may write the field.
    """
    assert 'inherited_runners' in (
        qualification.UNRESOLVED_SOURCE_AUTHORITY_FIELDS
    )
    assert qualification.field_authority_resolved('inherited_runners') is False
    assert qualification.field_authority_state('inherited_runners') == (
        qualification.FIELD_AUTHORITY_UNRESOLVED
    )


def test_inherited_runners_candidate_is_refused_by_the_plan_contract():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(field='inherited_runners')]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_FIELD_AUTHORITY_UNRESOLVED in (
        candidate['failed_reasons']
    )
    assert candidate['is_valid_candidate'] is False


def test_inherited_runners_candidate_fails_the_whole_qualification():
    decision = assess(
        shadow_report=report(
            mode=lane.MODE_SHADOW,
            rows=[update_row(field='inherited_runners')],
        ),
        write_report=report(rows=[update_row(field='inherited_runners')]),
    )
    assert qualification.FAILED_FIELD_AUTHORITY_UNRESOLVED in (
        decision['failed_reasons']
    )
    assert decision['result'] == qualification.RESULT_FAILED


def test_inherited_runners_scored_is_refused_on_the_same_open_question():
    assert qualification.field_authority_resolved(
        'inherited_runners_scored'
    ) is False


def test_balls_authority_is_resolved_and_eligible():
    """`balls` has a recorded resolution and an approved fallback contract."""
    assert qualification.field_authority_resolved('balls') is True
    described = qualification.describe_field_authority('balls')
    assert described['authority_resolved'] is True
    assert described['approved_fallback_field'] is True


@pytest.mark.parametrize('field', [
    'earned_runs', 'strikeouts', 'hits_allowed', 'walks', 'pitches_thrown',
])
def test_ordinary_statistical_fields_have_resolved_authority(field):
    assert qualification.field_authority_resolved(field) is True


@pytest.mark.parametrize('field', [
    'appearance_team_id', 'games_started', 'game_date',
    'stat_correction_count', 'not_a_field',
])
def test_non_statistical_fields_are_not_eligible(field):
    assert qualification.field_authority_resolved(field) is False
    assert qualification.field_authority_state(field) == (
        qualification.FIELD_AUTHORITY_NOT_GOVERNED
    )


def test_a_non_statistical_field_fails_the_candidate_contract():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(field='appearance_team_id')]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_FIELD_NOT_GOVERNED_STATISTICAL in (
        candidate['failed_reasons']
    )


# ── Candidate plan contract ─────────────────────────────────────────────────


def test_exactly_one_update_and_any_unchanged_rows_is_a_valid_candidate():
    candidate = qualification.evaluate_candidate_plan(
        report(), game_pk=GAME_PK,
    )
    assert candidate['is_valid_candidate'] is True
    assert candidate['planned_update_row_count'] == 1
    assert candidate['mutation_present'] is True


def test_two_updated_rows_are_refused():
    rows = [
        update_row(),
        update_row(pitcher_mlb_id=5002),
    ]
    candidate = qualification.evaluate_candidate_plan(
        report(rows=rows, rows_updated=2, statistical_corrections=2),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_MULTI_ROW_MUTATION in (
        candidate['failed_reasons']
    )


def test_two_changed_fields_on_one_row_are_refused():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(
            changed_fields=['earned_runs', 'strikeouts'],
            semantic_changed_fields=['earned_runs', 'strikeouts'],
        )]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_MULTI_FIELD_MUTATION in (
        candidate['failed_reasons']
    )


def test_an_insert_is_refused():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(action=reconciliation.ACTION_INSERT)]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_PROPOSES_INSERT in (
        candidate['failed_reasons']
    )


def test_a_blocked_row_is_refused():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[
            update_row(),
            unchanged_row(action=reconciliation.ACTION_BLOCKED),
        ]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_CONTAINS_BLOCKED_ROW in (
        candidate['failed_reasons']
    )


def test_an_unknown_action_is_refused():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(), unchanged_row(action='invented')]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_UNKNOWN_ACTION in (
        candidate['failed_reasons']
    )


@pytest.mark.parametrize('identity_action', [
    pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
    pitcher_identity.ACTION_BLOCKED,
    # The retired write actions. D-009 removed them from the vocabulary; if one
    # ever reappears on a row it must still refuse rather than read as unknown
    # and pass.
    *pitcher_identity.RETIRED_WRITE_ACTIONS,
])
def test_identity_mutation_is_refused(identity_action):
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(pitcher_identity_action=identity_action)]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PROHIBITED_IDENTITY_ACTION in (
        candidate['failed_reasons']
    )


@pytest.mark.parametrize('category', [
    reconciliation.CATEGORY_APPEARANCE_TEAM_AUTHORITY,
    reconciliation.CATEGORY_ROLE_SIGNAL,
    reconciliation.CATEGORY_GAME_METADATA,
    reconciliation.CATEGORY_PITCHER_IDENTITY,
])
def test_prohibited_mutation_categories_are_refused(category):
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(mutation_categories=[
            reconciliation.CATEGORY_STATISTICAL_CORRECTION, category,
        ])]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PROHIBITED_MUTATION_CATEGORY in (
        candidate['failed_reasons']
    )


def test_the_provenance_category_accompanies_every_real_correction():
    """MEASURED: the planner appends it to every genuine correction.

    Refusing it would refuse every correct run, so it is permitted — while a row
    that is provenance-ONLY is still refused by the test below.
    """
    assert reconciliation.CATEGORY_PROVENANCE_ONLY not in (
        qualification.PROHIBITED_MUTATION_CATEGORIES
    )
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(mutation_categories=[
            reconciliation.CATEGORY_STATISTICAL_CORRECTION,
            reconciliation.CATEGORY_PROVENANCE_ONLY,
        ])]),
        game_pk=GAME_PK,
    )
    assert candidate['is_valid_candidate'] is True


def test_a_provenance_only_row_is_refused():
    """Provenance moved and no published evidence did: nothing to correct."""
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(is_provenance_only=True)]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_IS_PROVENANCE_ONLY in (
        candidate['failed_reasons']
    )


def test_the_provenance_only_plan_counter_must_still_be_zero():
    assert 'provenance_only_updates' in qualification.PROHIBITED_PLAN_COUNTERS


def test_a_row_the_planner_did_not_call_a_statistical_correction_is_refused():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(is_statistical_correction=False)]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_NOT_STATISTICAL_CORRECTION in (
        candidate['failed_reasons']
    )


def test_changed_fields_on_an_unchanged_row_are_counted_prohibited():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(), unchanged_row(changed_fields=['walks'])]),
        game_pk=GAME_PK,
    )
    assert 'changed_fields_on_unchanged_row' in (
        candidate['prohibited_action_counts']
    )


@pytest.mark.parametrize('counter', qualification.PROHIBITED_PLAN_COUNTERS)
def test_every_prohibited_plan_counter_refuses_when_non_zero(counter):
    candidate = qualification.evaluate_candidate_plan(
        report(**{counter: 1}), game_pk=GAME_PK,
    )
    assert qualification.FAILED_PROHIBITED_EFFECT_OBSERVED in (
        candidate['failed_reasons']
    )


def test_plan_counters_must_say_exactly_one_correction():
    candidate = qualification.evaluate_candidate_plan(
        report(rows_updated=2), game_pk=GAME_PK,
    )
    assert qualification.FAILED_PLAN_COUNTERS_UNEXPECTED in (
        candidate['failed_reasons']
    )


def test_an_update_for_a_different_game_is_refused():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[update_row(game_pk=OTHER_GAME_PK)]),
        game_pk=GAME_PK,
    )
    assert qualification.FAILED_UNEXPECTED_PLANNED_GAME in (
        candidate['failed_reasons']
    )


# ── NO_LONGER_MUTATING ──────────────────────────────────────────────────────


def test_a_plan_with_no_update_is_not_a_failure():
    candidate = qualification.evaluate_candidate_plan(
        report(rows=[unchanged_row()], rows_updated=0,
               statistical_corrections=0),
        game_pk=GAME_PK,
    )
    assert candidate['mutation_present'] is False
    assert candidate['failed_reasons'] == []


def test_a_plan_with_no_update_resolves_no_longer_mutating():
    clean = report(
        rows=[unchanged_row()], rows_updated=0, statistical_corrections=0,
    )
    decision = assess(
        shadow_report=report(
            mode=lane.MODE_SHADOW, rows=[unchanged_row()],
            rows_updated=0, statistical_corrections=0,
        ),
        write_report=clean,
        realized_digest=None,
        before_state=row_state(),
        after_state=row_state(),
    )
    assert decision['result'] != qualification.RESULT_PASS


def test_decide_precedence_failed_beats_everything():
    decision = qualification.decide({
        'failed_reasons': ['x'],
        'unproven_reasons': ['y'],
        'no_longer_mutating': True,
    })
    assert decision['result'] == qualification.RESULT_FAILED


def test_decide_precedence_unproven_beats_no_longer_mutating():
    decision = qualification.decide({
        'failed_reasons': [],
        'unproven_reasons': ['y'],
        'no_longer_mutating': True,
    })
    assert decision['result'] == qualification.RESULT_UNPROVEN


def test_decide_no_longer_mutating_is_never_pass():
    decision = qualification.decide({
        'failed_reasons': [],
        'unproven_reasons': [],
        'no_longer_mutating': True,
    })
    assert decision['result'] == qualification.RESULT_NO_LONGER_MUTATING
    assert decision['exit_code'] == qualification.EXIT_NO_LONGER_MUTATING
    assert decision['exit_code'] != qualification.EXIT_PASS


def test_decide_pass_requires_positive_absence_of_both_lists():
    decision = qualification.decide({
        'failed_reasons': [], 'unproven_reasons': [],
        'no_longer_mutating': False,
    })
    assert decision['result'] == qualification.RESULT_PASS


# ── Drift ───────────────────────────────────────────────────────────────────


def test_source_revision_change_between_phases_is_refused():
    write = report()
    write['games'][0]['source_revision'] = 'rev-2'
    decision = assess(write_report=write)
    assert qualification.FAILED_SOURCE_REVISION_CHANGED in (
        decision['failed_reasons']
    )
    assert decision['result'] == qualification.RESULT_FAILED


def test_missing_write_phase_source_revision_is_unproven():
    write = report()
    write['games'][0]['source_revision'] = None
    decision = assess(write_report=write)
    assert qualification.UNPROVEN_WRITE_SOURCE_REVISION_MISSING in (
        decision['unproven_reasons']
    )


def test_source_revision_for_the_wrong_game_is_failed():
    write = report()
    write['games'][0]['game_pk'] = OTHER_GAME_PK
    decision = assess(write_report=write)
    assert qualification.FAILED_SOURCE_REVISION_WRONG_GAME in (
        decision['failed_reasons']
    )


def test_plan_fingerprint_mismatch_between_phases_is_refused():
    decision = assess(
        write_report=report(authorized_plan_fingerprint=OTHER_FINGERPRINT),
    )
    assert qualification.FAILED_PLAN_FINGERPRINT_MISMATCH in (
        decision['failed_reasons']
    )


def test_the_lane_fingerprint_mismatch_status_is_mapped():
    decision = assess(
        write_report=report(status=lane.STATUS_PLAN_FINGERPRINT_MISMATCH),
    )
    assert qualification.FAILED_PLAN_FINGERPRINT_MISMATCH in (
        decision['failed_reasons']
    )


def test_a_plan_the_operator_did_not_review_is_refused():
    """The reviewed fingerprint is what a human actually saw."""
    decision = assess(reviewed_fingerprint=OTHER_FINGERPRINT)
    assert qualification.FAILED_REVIEWED_FINGERPRINT_MISMATCH in (
        decision['failed_reasons']
    )
    assert decision['reviewed_plan_fingerprint_match'] is False


def test_a_matching_reviewed_fingerprint_is_recorded_positively():
    decision = assess()
    assert decision['reviewed_plan_fingerprint_match'] is True


def test_missing_shadow_fingerprint_is_unproven():
    decision = assess(
        shadow_report=report(
            mode=lane.MODE_SHADOW, reconciliation_plan_fingerprint=None,
        ),
    )
    assert qualification.UNPROVEN_PLAN_FINGERPRINT_MISSING in (
        decision['unproven_reasons']
    )


# ── Execution effects ───────────────────────────────────────────────────────


def test_expected_baseball_effects_are_exact_not_at_least_one():
    assert qualification.EXPECTED_BASEBALL_DATA_EFFECTS == {
        'game_log_rows_written': 1,
        'pitcher_rows_written': 0,
        'appearance_team_rows_written': 0,
        # Measured: the correction stamps provenance on the row it corrects.
        'correction_provenance_rows_written': 1,
        'dead_letters_created': 0,
    }


def test_two_game_log_rows_written_is_a_failure():
    decision = assess(
        write_report=report(execution_effects=effects(
            game_log_rows_written=2,
        )),
    )
    assert qualification.FAILED_BASEBALL_EFFECTS_UNEXPECTED in (
        decision['failed_reasons']
    )


def test_zero_game_log_rows_written_is_a_failure():
    decision = assess(
        write_report=report(execution_effects=effects(
            game_log_rows_written=0,
        )),
    )
    assert qualification.FAILED_BASEBALL_EFFECTS_UNEXPECTED in (
        decision['failed_reasons']
    )


@pytest.mark.parametrize('counter,value', [
    ('pitcher_rows_written', 1),
    ('appearance_team_rows_written', 1),
    ('dead_letters_created', 1),
    # Exact on both sides: a second provenance row is as wrong as none.
    ('correction_provenance_rows_written', 2),
    ('correction_provenance_rows_written', 0),
])
def test_any_baseball_effect_outside_the_exact_contract_is_a_failure(
    counter, value,
):
    decision = assess(
        write_report=report(execution_effects=effects(**{counter: value})),
    )
    assert qualification.FAILED_BASEBALL_EFFECTS_UNEXPECTED in (
        decision['failed_reasons']
    )
    assert decision['result'] == qualification.RESULT_FAILED


def test_writes_must_be_enabled():
    decision = assess(
        write_report=report(execution_effects=effects(writes_enabled=False)),
    )
    assert qualification.FAILED_WRITES_NOT_ENABLED in (
        decision['failed_reasons']
    )


def test_publication_authority_is_a_hard_failure():
    decision = assess(
        write_report=report(execution_effects=effects(
            publication_authoritative=True,
        )),
    )
    assert qualification.FAILED_PUBLICATION_AUTHORITATIVE in (
        decision['failed_reasons']
    )


def test_missing_effect_counters_are_unproven():
    decision = assess(write_report=report(execution_effects=None))
    assert qualification.UNPROVEN_EFFECT_COUNTERS_MISSING in (
        decision['unproven_reasons']
    )


def test_an_incomplete_lane_status_is_a_failure():
    decision = assess(write_report=report(status='incomplete'))
    assert qualification.FAILED_LANE_STATUS_NOT_COMPLETE in (
        decision['failed_reasons']
    )


# ── Scope ───────────────────────────────────────────────────────────────────


def test_an_unexpected_planned_game_is_refused():
    decision = assess(
        write_report=report(
            planned_game_pks=[GAME_PK, OTHER_GAME_PK],
            unexpected_planned_game_pks=[OTHER_GAME_PK],
            execution_scope_exact_match=False,
        ),
    )
    assert qualification.FAILED_UNEXPECTED_PLANNED_GAME in (
        decision['failed_reasons']
    )
    assert qualification.FAILED_SCOPE_NOT_EXACT in decision['failed_reasons']


def test_a_missing_requested_game_is_refused():
    decision = assess(
        write_report=report(
            planned_game_pks=[], missing_requested_game_pks=[GAME_PK],
            execution_scope_exact_match=False, games_completed=0,
        ),
    )
    assert qualification.FAILED_MISSING_REQUESTED_GAME in (
        decision['failed_reasons']
    )


def test_a_duplicate_requested_game_is_refused():
    decision = assess(write_report=report(duplicate_requested_count=1))
    assert qualification.FAILED_DUPLICATE_REQUESTED_GAME in (
        decision['failed_reasons']
    )


def test_more_than_one_completed_game_is_refused():
    decision = assess(write_report=report(games_completed=2))
    assert qualification.FAILED_COMPLETED_COUNT_NOT_ONE in (
        decision['failed_reasons']
    )


# ── Integrity ───────────────────────────────────────────────────────────────


def test_the_target_must_reach_the_canonical_value():
    decision = assess(realized_digest='some-other-digest')
    assert qualification.FAILED_TARGET_ROW_NOT_REALIZED in (
        decision['failed_reasons']
    )
    assert decision['integrity']['target_reached_canonical_value'] is False


def test_a_changed_unreviewed_field_on_the_target_row_is_a_failure():
    decision = assess(
        after_state=row_state(unreviewed='unreviewed-2'),
    )
    assert qualification.FAILED_TARGET_ROW_UNREVIEWED_FIELD_CHANGED in (
        decision['failed_reasons']
    )


def test_a_changed_other_row_in_the_same_game_is_a_failure():
    decision = assess(after_state=row_state(others='others-2'))
    assert qualification.FAILED_OTHER_ROWS_CHANGED in (
        decision['failed_reasons']
    )
    assert decision['integrity']['other_rows_unchanged'] is False


def test_an_unmoved_target_row_is_a_failure():
    """A real-mutation PASS requires the row to have actually changed."""
    decision = assess(after_state=row_state(target_digest='row-before'))
    assert qualification.FAILED_TARGET_ROW_UNCHANGED_AFTER_WRITE in (
        decision['failed_reasons']
    )


def test_an_absent_target_row_is_a_failure():
    decision = assess(after_state=row_state(target_rows=0))
    assert qualification.FAILED_TARGET_ROW_ABSENT in decision['failed_reasons']


def test_a_duplicated_target_row_is_a_failure():
    decision = assess(before_state=row_state(target_rows=2))
    assert qualification.FAILED_TARGET_ROW_DUPLICATE in (
        decision['failed_reasons']
    )


def test_an_unavailable_pre_readback_is_unproven():
    decision = assess(before_state={'available': False})
    assert qualification.UNPROVEN_PRE_READBACK_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_an_unavailable_post_readback_is_unproven():
    decision = assess(after_state={'available': False})
    assert qualification.UNPROVEN_POST_READBACK_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_a_missing_realized_digest_is_unproven():
    decision = assess(realized_digest=None)
    assert qualification.UNPROVEN_POST_READBACK_UNAVAILABLE in (
        decision['unproven_reasons']
    )


# ── Realization ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize('field', [
    'missing_rows', 'divergent_rows', 'duplicate_rows', 'unresolved_rows',
])
def test_any_unresolved_realization_counter_is_a_failure(field):
    decision = assess(realization=realization(**{field: 1}))
    assert qualification.FAILED_REALIZATION_UNRESOLVED in (
        decision['failed_reasons']
    )


def test_a_prohibited_identity_action_in_realization_is_a_failure():
    decision = assess(
        realization=realization(prohibited_identity_actions=1),
    )
    assert qualification.FAILED_PROHIBITED_IDENTITY_ACTION in (
        decision['failed_reasons']
    )


def test_realization_must_positively_report_all_targets_realized():
    decision = assess(
        realization=realization(all_projected_targets_realized=False),
    )
    assert qualification.FAILED_REALIZATION_UNRESOLVED in (
        decision['failed_reasons']
    )


def test_unavailable_realization_is_unproven():
    decision = assess(realization=None)
    assert qualification.UNPROVEN_REALIZATION_UNAVAILABLE in (
        decision['unproven_reasons']
    )


# ── Lane bookkeeping ────────────────────────────────────────────────────────


def test_the_expected_ledger_delta_is_pinned_exactly():
    assert qualification.EXPECTED_LANE_BOOKKEEPING_DELTA == {
        'work_items_created': 0,
        'work_items_updated': 1,
        'work_items_completed': 1,
        'checkpoints_advanced': 1,
        'commits_performed': 1,
    }


def test_correction_count_must_advance_by_exactly_one():
    assert qualification.EXPECTED_CORRECTION_COUNT_DELTA == 1
    before, after = bookkeeping(corrections=(0, 0))
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_CORRECTION_COUNT_DELTA_UNEXPECTED in (
        decision['failed_reasons']
    )


def test_correction_count_advancing_twice_is_refused():
    before, after = bookkeeping(corrections=(0, 2))
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_CORRECTION_COUNT_DELTA_UNEXPECTED in (
        decision['failed_reasons']
    )


def test_correction_count_is_permitted_to_change_unlike_the_noop_contract():
    """The no-op contract requires it to hold; this one requires it to move."""
    from services import noop_write_qualification as noop

    assert 'correction_count' in (
        noop.BOOKKEEPING_REQUIRED_UNCHANGED_FIELDS
    )
    assert 'correction_count' in (
        qualification.BOOKKEEPING_ALLOWED_CHANGED_FIELDS
    )
    assert 'correction_count' not in (
        qualification.BOOKKEEPING_REQUIRED_UNCHANGED_FIELDS
    )


def test_a_work_item_field_outside_the_permitted_set_is_refused():
    before, after = bookkeeping(extra_after={'criticality': 'best_effort'})
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_UNEXPECTED_WORK_ITEM_FIELD_CHANGE in (
        decision['failed_reasons']
    )


def test_a_missing_work_item_is_refused():
    before, after = bookkeeping(present=False)
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_TARGET_WORK_ITEM_MISSING in (
        decision['failed_reasons']
    )


@pytest.mark.parametrize('status', ['pending', 'failed', 'in_progress'])
def test_a_work_item_not_completed_before_is_refused(status):
    before, after = bookkeeping(status_before=status)
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_WORK_ITEM_STATUS_UNEXPECTED in (
        decision['failed_reasons']
    )


def test_the_required_before_status_is_completed():
    assert qualification.REQUIRED_WORK_ITEM_STATUS_BEFORE == 'completed'
    assert qualification.REQUIRED_WORK_ITEM_STATUS_AFTER == 'completed'


def test_attempt_count_must_advance_by_exactly_one():
    before, after = bookkeeping(attempts=(1, 3))
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_ATTEMPT_COUNT_DELTA_UNEXPECTED in (
        decision['failed_reasons']
    )


def test_an_unrelated_work_item_change_is_refused():
    before, after = bookkeeping()
    after['unrelated_work_items_digest'] = 'moved'
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_UNRELATED_WORK_ITEM_CHANGED in (
        decision['failed_reasons']
    )


def test_an_unrelated_checkpoint_change_is_refused():
    before, after = bookkeeping()
    after['unrelated_checkpoints_digest'] = 'moved'
    decision = assess(bookkeeping_before=before, bookkeeping_after=after)
    assert qualification.FAILED_UNRELATED_CHECKPOINT_CHANGED in (
        decision['failed_reasons']
    )


def test_an_unexpected_work_item_creation_is_refused():
    decision = assess(
        write_report=report(execution_effects=effects(work_items_created=1)),
    )
    assert qualification.FAILED_UNEXPECTED_WORK_ITEM_CREATION in (
        decision['failed_reasons']
    )


def test_a_checkpoint_delta_mismatch_is_refused():
    decision = assess(
        write_report=report(execution_effects=effects(
            checkpoints_advanced=2,
        )),
    )
    assert qualification.FAILED_CHECKPOINT_DELTA_MISMATCH in (
        decision['failed_reasons']
    )


def test_a_commit_count_mismatch_is_refused():
    decision = assess(
        write_report=report(execution_effects=effects(commits_performed=2)),
    )
    assert qualification.FAILED_COMMIT_COUNT_MISMATCH in (
        decision['failed_reasons']
    )


def test_unavailable_bookkeeping_readback_is_unproven():
    decision = assess(bookkeeping_before=None, bookkeeping_after=None)
    assert qualification.UNPROVEN_BOOKKEEPING_READBACK_UNAVAILABLE in (
        decision['unproven_reasons']
    )


# ── Writer guard ────────────────────────────────────────────────────────────


def test_an_unacquired_writer_guard_is_unproven():
    decision = assess(writer_guard={
        'acquired': False, 'release_attempted': False, 'released': False,
    })
    assert qualification.UNPROVEN_WRITER_GUARD_UNAVAILABLE in (
        decision['unproven_reasons']
    )


def test_an_unreleased_writer_guard_is_unproven():
    decision = assess(writer_guard={
        'acquired': True, 'release_attempted': True, 'released': False,
    })
    assert qualification.UNPROVEN_WRITER_GUARD_RELEASE_UNPROVEN in (
        decision['unproven_reasons']
    )


def test_a_released_guard_is_recorded_positively():
    decision = assess()
    assert decision['writer_guard'] == {
        'acquired': True, 'release_attempted': True, 'released': True,
    }


# ── Artifact safety ─────────────────────────────────────────────────────────


def test_forbidden_artifact_content_is_a_failure():
    decision = assess(artifact_scan={'available': True, 'safe': False})
    assert qualification.FAILED_ARTIFACT_FORBIDDEN_CONTENT in (
        decision['failed_reasons']
    )


def test_an_unavailable_artifact_scan_is_unproven():
    decision = assess(artifact_scan={'available': False})
    assert qualification.UNPROVEN_ARTIFACT_SCAN_UNAVAILABLE in (
        decision['unproven_reasons']
    )


# ── Non-authorization ───────────────────────────────────────────────────────


def test_the_non_authorization_statement_names_every_withheld_authority():
    statement = qualification.NON_AUTHORIZATION_STATEMENT.lower()
    for phrase in (
        'scheduled writes', 'automated', 'authoritative publication',
        'backfill', 'multiple-game', 'identity mutation',
    ):
        assert phrase in statement


def test_every_decision_carries_the_non_authorization_statement():
    for evidence in (
        {'failed_reasons': ['x'], 'unproven_reasons': []},
        {'failed_reasons': [], 'unproven_reasons': ['y']},
        {'failed_reasons': [], 'unproven_reasons': [],
         'no_longer_mutating': True},
        {'failed_reasons': [], 'unproven_reasons': []},
    ):
        decision = qualification.decide(evidence)
        assert decision['non_authorization_statement'] == (
            qualification.NON_AUTHORIZATION_STATEMENT
        )
