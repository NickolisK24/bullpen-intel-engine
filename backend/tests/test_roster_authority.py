"""Tests for the Roster Authority foundation (CRC Phase 1).

These prove the foundational guarantees: the authority is pure and deterministic,
its published counts are invariant across UI filters, every count is backed by an
evidence list of the same length, and it reuses the canonical roster classification
rather than inventing its own predicate.
"""

import json
from types import SimpleNamespace

from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.roster_status import classify_roster_status
from services.roster_authority import (
    CANONICAL_POPULATION_FLAGS,
    CAPABILITY,
    FIELD_INVARIANCE,
    build_roster_authority,
)


# ── Record builders (plain dicts mirroring the board record shape) ────────────

def _roster_status(status, *, label, is_active_mlb, is_inactive_context, is_authoritative=True):
    return {
        'status': status,
        'label': label,
        'is_active_mlb': is_active_mlb,
        'is_inactive_context': is_inactive_context,
        'is_authoritative': is_authoritative,
    }


def _active_rs():
    return _roster_status('ACTIVE', label='Active MLB', is_active_mlb=True, is_inactive_context=False)


def _inactive_rs(status='IL_60', label='60-Day IL'):
    return _roster_status(status, label=label, is_active_mlb=False, is_inactive_context=True)


def _unknown_rs():
    return _roster_status(
        'UNKNOWN', label='Roster Unknown',
        is_active_mlb=None, is_inactive_context=False, is_authoritative=False,
    )


def _record(pitcher_id, name, roster_status, availability_status=None):
    return {
        'pitcher_id': pitcher_id,
        'name': name,
        'roster_status': roster_status,
        'availability_status': availability_status,
    }


def _sample_population():
    """A representative team: 8 active arms, 2 off-roster, 1 unknown.

    Active reads: 4 Available, 1 Monitor, 1 Limited, 1 Avoid, 1 Unavailable.
    """
    return [
        _record(1, 'Aaron Available', _active_rs(), STATUS_AVAILABLE),
        _record(2, 'Bart Available', _active_rs(), STATUS_AVAILABLE),
        _record(3, 'Cody Available', _active_rs(), STATUS_AVAILABLE),
        _record(4, 'Drew Available', _active_rs(), STATUS_AVAILABLE),
        _record(5, 'Mason Monitor', _active_rs(), STATUS_MONITOR),
        _record(6, 'Lenny Limited', _active_rs(), STATUS_LIMITED),
        _record(7, 'Avery Avoid', _active_rs(), STATUS_AVOID),
        _record(8, 'Ulysses Unavailable', _active_rs(), STATUS_UNAVAILABLE),
        # Off the active roster — workload read forced to Unavailable by roster status,
        # but these must be counted as roster-inactive, never as workload-unavailable.
        _record(9, 'Ike Injured', _inactive_rs('IL_60', '60-Day IL'), STATUS_UNAVAILABLE),
        _record(10, 'Omar Optioned', _inactive_rs('MINORS', 'Optioned / Minors'), STATUS_UNAVAILABLE),
        # Roster status not yet confirmed.
        _record(11, 'Quincy Question', _unknown_rs(), None),
    ]


# ── Determinism & purity ──────────────────────────────────────────────────────

def test_identical_inputs_produce_identical_objects():
    population = _sample_population()
    first = build_roster_authority(population)
    second = build_roster_authority(population)
    assert first == second


def test_output_is_order_independent():
    population = _sample_population()
    shuffled = list(reversed(population))
    assert build_roster_authority(shuffled) == build_roster_authority(population)


def test_output_is_transport_neutral_json_serializable():
    authority = build_roster_authority(_sample_population(), team={
        'team_id': 147, 'team_name': 'New York Yankees', 'team_abbreviation': 'NYY',
    })
    # Round-trips through JSON unchanged — no sets, ORM objects, or other non-primitives.
    assert json.loads(json.dumps(authority)) == authority
    assert authority['capability'] == CAPABILITY
    assert authority['source'] == 'backend'
    assert authority['invariant'] is True
    assert authority['team'] == {
        'team_id': 147, 'team_name': 'New York Yankees', 'team_abbreviation': 'NYY',
    }


def test_reference_date_is_passed_through_not_derived_from_clock():
    # Purity: no clock. None stays None; a provided date is echoed verbatim.
    assert build_roster_authority([])['reference_date'] is None
    assert build_roster_authority([], reference_date='2026-06-08')['reference_date'] == '2026-06-08'


# ── Invariance (counts do not depend on any UI view/filter) ───────────────────

def test_counts_are_invariant_to_ui_only_record_fields():
    """Adding view/display fields to records must not change any count or evidence.

    This is the core invariance guarantee: the authority describes roster reality, so a
    UI concern (which cards a filter would render) can never move a number.
    """
    population = _sample_population()
    baseline = build_roster_authority(population)

    decorated = [
        {**record, 'visible': index % 2 == 0, 'view_mode': 'unavailable_only', 'card_shown': False}
        for index, record in enumerate(population)
    ]
    assert build_roster_authority(decorated) == baseline


def test_partition_covers_every_candidate_exactly_once():
    authority = build_roster_authority(_sample_population())
    counts = authority['counts']
    total = authority['population']['total_candidates']
    assert total == 11
    assert (
        counts['bullpen_arms']
        + counts['inactive_roster_context_count']
        + counts['roster_unknown_count']
        == total
    )


def test_roster_bucket_counts():
    authority = build_roster_authority(_sample_population())
    counts = authority['counts']
    assert counts['bullpen_arms'] == 8
    assert counts['inactive_roster_context_count'] == 2
    assert counts['roster_unknown_count'] == 1


def test_availability_breakdown_sums_to_bullpen_arms():
    authority = build_roster_authority(_sample_population())
    counts = authority['counts']
    breakdown = (
        counts['available_count']
        + counts['monitor_count']
        + counts['limited_count']
        + counts['avoid_count']
        + counts['unavailable_count']
        + counts['availability_unknown_count']
    )
    assert breakdown == counts['bullpen_arms']
    assert counts['available_count'] == 4
    assert counts['monitor_count'] == 1
    assert counts['limited_count'] == 1
    assert counts['avoid_count'] == 1
    assert counts['unavailable_count'] == 1
    assert counts['availability_unknown_count'] == 0


def test_active_bullpen_arms_excludes_unavailable_and_unread():
    authority = build_roster_authority(_sample_population())
    counts = authority['counts']
    # Usable = Available + Monitor + Limited + Avoid (not Unavailable, not unread).
    assert counts['active_bullpen_arms'] == 7
    assert counts['active_bullpen_arms'] == (
        counts['available_count']
        + counts['monitor_count']
        + counts['limited_count']
        + counts['avoid_count']
    )


def test_off_roster_unavailable_read_is_not_workload_unavailable():
    """An off-roster arm whose read is Unavailable counts as roster-inactive only.

    This is the canonical-drift fix: workload Unavailable and roster Off-the-roster are
    two different facts and must never be conflated in one count.
    """
    authority = build_roster_authority(_sample_population())
    counts = authority['counts']
    # Two off-roster arms carry an Unavailable read, but unavailable_count is 1 (only the
    # active-roster arm read Unavailable for workload reasons).
    assert counts['unavailable_count'] == 1
    assert counts['inactive_roster_context_count'] == 2
    inactive_ids = {entry['pitcher_id'] for entry in authority['evidence']['inactive_roster_context_count']}
    unavailable_ids = {entry['pitcher_id'] for entry in authority['evidence']['unavailable_count']}
    assert inactive_ids == {9, 10}
    assert unavailable_ids == {8}
    assert inactive_ids.isdisjoint(unavailable_ids)


# ── Evidence backs every count ────────────────────────────────────────────────

def test_every_count_has_an_evidence_list_of_equal_length():
    authority = build_roster_authority(_sample_population())
    for field, count in authority['counts'].items():
        assert field in authority['evidence'], f'missing evidence for {field}'
        assert len(authority['evidence'][field]) == count, f'evidence mismatch for {field}'


def test_evidence_entries_are_inspectable_and_sorted():
    authority = build_roster_authority(_sample_population())
    bullpen = authority['evidence']['bullpen_arms']
    # Sorted deterministically by name then pitcher id.
    assert [entry['name'] for entry in bullpen] == sorted(entry['name'] for entry in bullpen)
    sample = authority['evidence']['inactive_roster_context_count'][0]
    assert set(sample) == {
        'pitcher_id', 'name', 'roster_status', 'roster_status_label',
        'roster_status_category', 'roster_status_category_label', 'availability', 'reason',
    }
    assert sample['reason']  # plain-language, non-empty
    # The first off-roster arm is the 60-day IL pitcher, grouped under the injured-list category.
    assert sample['roster_status_category'] == 'injured_list'
    assert sample['roster_status_category_label'] == 'Injured list'


# ── Coverage & unknown ────────────────────────────────────────────────────────

def test_roster_status_coverage_and_unknown():
    authority = build_roster_authority(_sample_population())
    population = authority['population']
    assert population['total_candidates'] == 11
    assert population['known_count'] == 10
    assert population['unknown_count'] == 1
    assert population['roster_status_coverage'] == round(10 / 11, 4)
    assert authority['counts']['roster_unknown_count'] == population['unknown_count']


def test_empty_population_is_safe():
    authority = build_roster_authority([])
    assert authority['population'] == {
        'total_candidates': 0,
        'known_count': 0,
        'unknown_count': 0,
        'roster_status_coverage': 0.0,
    }
    assert all(value == 0 for value in authority['counts'].values())
    assert all(authority['evidence'][field] == [] for field in authority['counts'])
    assert json.loads(json.dumps(authority)) == authority


def test_none_and_non_dict_records_are_ignored():
    authority = build_roster_authority([None, 'nope', 42, _record(1, 'Real Arm', _active_rs(), STATUS_AVAILABLE)])
    assert authority['population']['total_candidates'] == 1
    assert authority['counts']['bullpen_arms'] == 1


# ── Reuse of the canonical classifier (no parallel definition) ────────────────

def test_consumes_real_classify_roster_status_output():
    """Records classified by the real roster classifier bucket correctly.

    Proves the authority reads the canonical is_active_mlb / is_inactive_context /
    is_authoritative fields rather than re-deriving roster status.
    """
    active_pitcher = SimpleNamespace(
        roster_status='ACTIVE', roster_status_source='mlb_stats_api',
        roster_status_updated_at=None, roster_status_raw_code=None,
        roster_status_raw_description=None, active=True,
    )
    inactive_pitcher = SimpleNamespace(
        roster_status='IL_60', roster_status_source='mlb_stats_api',
        roster_status_updated_at=None, roster_status_raw_code=None,
        roster_status_raw_description=None, active=False,
    )
    records = [
        _record(1, 'Real Active', classify_roster_status(active_pitcher), STATUS_AVAILABLE),
        _record(2, 'Real Inactive', classify_roster_status(inactive_pitcher), STATUS_UNAVAILABLE),
        _record(3, 'Real Unknown', classify_roster_status(None), None),
    ]
    counts = build_roster_authority(records)['counts']
    assert counts['bullpen_arms'] == 1
    assert counts['inactive_roster_context_count'] == 1
    assert counts['roster_unknown_count'] == 1


def test_canonical_population_flags_are_fixed_and_view_independent():
    # The population is defined once with fixed flags; it is never bound to a request.
    assert CANONICAL_POPULATION_FLAGS == {'include_stale': True, 'include_inactive_context': True}


def test_all_published_fields_are_documented_invariant():
    authority = build_roster_authority(_sample_population())
    # Every count the authority publishes is declared invariant; the object carries the
    # contract so consumers can rely on it without re-reading the docs.
    assert set(authority['counts']) == set(FIELD_INVARIANCE)
    assert authority['field_invariance'] == FIELD_INVARIANCE
    assert all(value is True for value in FIELD_INVARIANCE.values())
