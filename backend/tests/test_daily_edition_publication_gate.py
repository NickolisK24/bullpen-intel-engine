"""Exhaustive focused tests for the Today Daily Edition semantic gate."""

import pytest

from services.daily_edition_publication_gate import (
    EVENT_CONSEQUENCE_COMPATIBILITY,
    KNOWN_CONSEQUENCES,
    REASON_EVENT_CONSEQUENCE_INCOMPATIBLE,
    REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH,
    REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISSING,
    STATUS_PASS,
    STATUS_WITHHELD,
    event_consequence_is_compatible,
    evaluate_daily_edition_publication,
)


_OPTIONALITY_FOR_CONSEQUENCE = {
    'availability_narrowed': 'thin',
    'late_inning_margin': 'flexible',
}
_CONCENTRATION_FOR_CONSEQUENCE = {
    'workload_concentration': 'concentrated',
}


def _appearance(primary, *, name='Claim Driver', game_pk=9001, team_id=137):
    scoring_event = primary in {'lost_game_shape', 'late_pressure_accumulated'}
    base = {
        'pitcher_mlb_id': 700001,
        'name': name,
        'game_pk': game_pk,
        'appearance_team_id': team_id,
        'innings': 1.0,
        'innings_pitched_outs': 3,
        'pitches_thrown': 14,
        'claim_evidence_role': (
            'claim_scoring_event_pitcher'
            if scoring_event
            else 'claim_supporting_relief_participant'
        ),
    }
    if scoring_event:
        base['claim_event_indexes'] = [71]
    if primary in {'lost_game_shape', 'late_pressure_accumulated'}:
        base['runs_allowed'] = 2
    else:
        base['runs_allowed'] = 0
    return base


def _inspected(primary, consequence, *, appearances=None, priority='HIGH'):
    availability = {}
    workload = {}
    if consequence in _OPTIONALITY_FOR_CONSEQUENCE:
        availability['optionality_band'] = _OPTIONALITY_FOR_CONSEQUENCE[consequence]
    elif consequence in _CONCENTRATION_FOR_CONSEQUENCE:
        workload['concentration_band'] = _CONCENTRATION_FOR_CONSEQUENCE[consequence]
    elif consequence == 'workload_spread':
        # starter-covered reaches its explicit fallback only with no state key.
        availability = {}
        workload = {}
    elif consequence is None:
        priority = 'MEDIUM'

    if appearances is None:
        appearances = [_appearance(primary)]
    return {
        'team_id': 137,
        'game_pk': 9001,
        'package': {
            'team_id': 137,
            'game_pk': 9001,
            'primary_story': primary,
            'story_priority': priority,
            'availability_snapshot': availability,
            'workload_snapshot': workload,
            'evidence_blocks': {'key_relief_appearances': appearances},
        },
    }


@pytest.mark.parametrize(
    ('primary', 'consequence'),
    [
        (primary, consequence)
        for primary in EVENT_CONSEQUENCE_COMPATIBILITY
        for consequence in KNOWN_CONSEQUENCES
    ],
)
def test_every_current_event_consequence_pair_has_an_explicit_decision(
    primary,
    consequence,
):
    expected = consequence in EVENT_CONSEQUENCE_COMPATIBILITY[primary]
    assert event_consequence_is_compatible(primary, consequence) is expected


def test_lost_lead_with_positive_more_routes_consequence_is_withheld_first():
    result = evaluate_daily_edition_publication(
        _inspected('lost_game_shape', 'late_inning_margin', appearances=[])
    )
    assert result['status'] == STATUS_WITHHELD
    assert result['reason'] == REASON_EVENT_CONSEQUENCE_INCOMPATIBLE
    assert result['claim_evidence']['relief_appearances'] == []


def test_compatible_lost_lead_without_damaging_appearance_is_withheld():
    result = evaluate_daily_edition_publication(
        _inspected('lost_game_shape', 'availability_narrowed', appearances=[])
    )
    assert result['status'] == STATUS_WITHHELD
    assert result['reason'] == REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISSING


def test_positive_event_with_named_scoreless_receipt_passes_losslessly():
    appearance = _appearance('protected_game_shape', name='Exact Reliever')
    result = evaluate_daily_edition_publication(
        _inspected('protected_game_shape', 'late_inning_margin', appearances=[appearance])
    )
    assert result['status'] == STATUS_PASS
    assert result['reason'] is None
    assert result['claim_evidence']['relief_appearances'] == [appearance]


def test_wrong_game_or_unlinked_line_cannot_be_published_as_receipt():
    wrong_game = _appearance('lost_game_shape', game_pk=9999)
    result = evaluate_daily_edition_publication(
        _inspected('lost_game_shape', 'availability_narrowed', appearances=[wrong_game])
    )
    assert result['status'] == STATUS_WITHHELD
    assert result['reason'] == REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH

    unlinked = _appearance('lost_game_shape')
    unlinked.pop('claim_event_indexes')
    result = evaluate_daily_edition_publication(
        _inspected('lost_game_shape', 'availability_narrowed', appearances=[unlinked])
    )
    assert result['status'] == STATUS_WITHHELD
    assert result['reason'] == REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH


def test_receipt_and_package_identity_must_exactly_match_inspected_story():
    missing_identity = _appearance('lost_game_shape')
    missing_identity.pop('game_pk')
    missing_identity.pop('appearance_team_id')
    result = evaluate_daily_edition_publication(
        _inspected(
            'lost_game_shape',
            'availability_narrowed',
            appearances=[missing_identity],
        )
    )
    assert result['status'] == STATUS_WITHHELD
    assert result['reason'] == REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH

    package_mismatch = _inspected(
        'lost_game_shape',
        'availability_narrowed',
    )
    package_mismatch['package']['game_pk'] = 9999
    result = evaluate_daily_edition_publication(package_mismatch)
    assert result['status'] == STATUS_WITHHELD
    assert result['reason'] == REASON_RESPONSIBLE_RELIEF_EVIDENCE_MISMATCH


def test_starter_covered_can_publish_without_relief_receipt():
    result = evaluate_daily_edition_publication(
        _inspected('starter_covered_bullpen', 'workload_spread', appearances=[])
    )
    assert result['status'] == STATUS_PASS
    assert result['claim_evidence']['relief_appearances'] == []


def test_medium_story_with_no_rendered_consequence_is_not_direction_checked():
    result = evaluate_daily_edition_publication(
        _inspected('bullpen_overexposed', None)
    )
    assert result['status'] == STATUS_PASS
    assert result['consequence_key'] is None
