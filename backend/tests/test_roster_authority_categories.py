"""CRC Phase 6 — canonical roster-status categories owned by Roster Authority.

Roster Authority groups the fine-grained roster statuses (IL_60, MINORS, 40_MAN_ONLY, …)
into a small set of baseball-language categories — active, injured_list, optioned_or_minors,
forty_man_not_active, restricted_or_special_list, non_roster_depth, unknown — so no consumer
re-derives "which statuses mean injured" or "which mean optioned". These tests prove:

  * every roster status maps to its canonical category (on real classifier output);
  * each category family (IL, optioned/minors, 40-man, restricted/special, unknown) maps
    exactly as specified;
  * the authority publishes category counts that match their evidence and reconcile with the
    existing roster buckets;
  * the existing counts are untouched (additive only); and
  * the category layer is a strict refinement of the roster predicates the capacity family
    already reads, so capacity-family behavior is unchanged.
"""

import json
from types import SimpleNamespace

import pytest

from services.availability import STATUS_AVAILABLE
from services.bullpen_resource_health import build_bullpen_resource_health
from services.roster_authority import (
    FIELD_INVARIANCE,
    ROSTER_STATUS_CATEGORY_ACTIVE,
    ROSTER_STATUS_CATEGORY_FORTY_MAN_NOT_ACTIVE,
    ROSTER_STATUS_CATEGORY_INJURED_LIST,
    ROSTER_STATUS_CATEGORY_LABELS,
    ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH,
    ROSTER_STATUS_CATEGORY_OPTIONED_OR_MINORS,
    ROSTER_STATUS_CATEGORY_ORDER,
    ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL,
    ROSTER_STATUS_CATEGORY_UNKNOWN,
    build_roster_authority,
    is_off_active_roster,
    is_on_active_roster,
    is_roster_status_unknown,
    roster_status_category,
    roster_status_category_for_status,
    roster_status_category_label,
)
from services.roster_status import (
    STATUS_40_MAN_ONLY,
    STATUS_ACTIVE,
    STATUS_BEREAVEMENT,
    STATUS_DFA,
    STATUS_IL_10,
    STATUS_IL_15,
    STATUS_IL_60,
    STATUS_MINORS,
    STATUS_NON_ROSTER,
    STATUS_OPTIONED,
    STATUS_PATERNITY,
    STATUS_RESTRICTED,
    STATUS_SUSPENDED,
    STATUS_UNKNOWN,
    classify_roster_status,
)
from tests.test_bullpen_resource_health import record as health_record


# The full status → category contract. Built on the canonical status constants so a renamed
# status or category is caught here, and exercised through the REAL classifier below so the
# mapping is proven on the exact dicts the authority sees in production.
EXPECTED_CATEGORY = {
    STATUS_ACTIVE: ROSTER_STATUS_CATEGORY_ACTIVE,
    STATUS_IL_10: ROSTER_STATUS_CATEGORY_INJURED_LIST,
    STATUS_IL_15: ROSTER_STATUS_CATEGORY_INJURED_LIST,
    STATUS_IL_60: ROSTER_STATUS_CATEGORY_INJURED_LIST,
    STATUS_OPTIONED: ROSTER_STATUS_CATEGORY_OPTIONED_OR_MINORS,
    STATUS_MINORS: ROSTER_STATUS_CATEGORY_OPTIONED_OR_MINORS,
    STATUS_40_MAN_ONLY: ROSTER_STATUS_CATEGORY_FORTY_MAN_NOT_ACTIVE,
    STATUS_RESTRICTED: ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL,
    STATUS_SUSPENDED: ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL,
    STATUS_BEREAVEMENT: ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL,
    STATUS_PATERNITY: ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL,
    STATUS_NON_ROSTER: ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH,
    STATUS_DFA: ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH,
    STATUS_UNKNOWN: ROSTER_STATUS_CATEGORY_UNKNOWN,
}


def _classified(status_code):
    """Roster status as the real classifier produces it for a stored status code."""
    pitcher = SimpleNamespace(
        roster_status=status_code, roster_status_source='mlb_stats_api',
        roster_status_updated_at=None, roster_status_raw_code=None,
        roster_status_raw_description=None, active=(status_code == STATUS_ACTIVE),
    )
    return classify_roster_status(pitcher)


def _record(pitcher_id, name, status_code, availability_status=None):
    return {
        'pitcher_id': pitcher_id,
        'name': name,
        'roster_status': _classified(status_code),
        'availability_status': availability_status,
    }


def _mixed_population():
    """A team spanning every category: 2 active, 2 injured, 2 optioned/minors, 1 40-man,
    2 restricted/special, 2 non-roster depth, 1 unknown (12 arms)."""
    return [
        _record(1, 'Aaron Active', STATUS_ACTIVE, STATUS_AVAILABLE),
        _record(2, 'Bart Active', STATUS_ACTIVE, STATUS_AVAILABLE),
        _record(3, 'Ike Injured', STATUS_IL_60),
        _record(4, 'Ivan Injured', STATUS_IL_15),
        _record(5, 'Omar Optioned', STATUS_OPTIONED),
        _record(6, 'Milo Minors', STATUS_MINORS),
        _record(7, 'Forrest Forty', STATUS_40_MAN_ONLY),
        _record(8, 'Sully Suspended', STATUS_SUSPENDED),
        _record(9, 'Rex Restricted', STATUS_RESTRICTED),
        _record(10, 'Dexter Dfa', STATUS_DFA),
        _record(11, 'Nate Nonroster', STATUS_NON_ROSTER),
        _record(12, 'Quincy Question', STATUS_UNKNOWN),
    ]


# ── 1. Categories assigned correctly (master mapping, on real classifier output) ──

@pytest.mark.parametrize('status_code, expected_category', sorted(EXPECTED_CATEGORY.items()))
def test_every_roster_status_maps_to_its_canonical_category(status_code, expected_category):
    assert roster_status_category(_classified(status_code)) == expected_category


# ── Status-code companion (CRC-7): read by the editorial contexts ─────────────

@pytest.mark.parametrize('status_code, expected_category', sorted(EXPECTED_CATEGORY.items()))
def test_status_code_helper_agrees_with_dict_classifier(status_code, expected_category):
    # roster_status_category_for_status reads the same _CATEGORY_BY_STATUS table, so a bare
    # status code yields the same category the dict classifier gives for that classified status.
    assert roster_status_category_for_status(status_code) == expected_category
    assert roster_status_category_for_status(status_code) == roster_status_category(_classified(status_code))


def test_status_code_helper_handles_active_unknown_and_unmapped_codes():
    # ACTIVE is active; a missing / unrecognized code is unknown (a bare code carries no
    # off-roster signal, so the off-roster table never decides active or unknown here).
    assert roster_status_category_for_status(STATUS_ACTIVE) == ROSTER_STATUS_CATEGORY_ACTIVE
    assert roster_status_category_for_status(STATUS_UNKNOWN) == ROSTER_STATUS_CATEGORY_UNKNOWN
    assert roster_status_category_for_status(None) == ROSTER_STATUS_CATEGORY_UNKNOWN
    assert roster_status_category_for_status('SOME_FUTURE_CODE') == ROSTER_STATUS_CATEGORY_UNKNOWN


def test_category_set_is_exactly_the_published_order():
    # No category exists outside the published order, and the order has no duplicates.
    assert set(EXPECTED_CATEGORY.values()) | {ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH} == set(
        ROSTER_STATUS_CATEGORY_ORDER
    )
    assert len(ROSTER_STATUS_CATEGORY_ORDER) == len(set(ROSTER_STATUS_CATEGORY_ORDER))
    assert ROSTER_STATUS_CATEGORY_ORDER[0] == ROSTER_STATUS_CATEGORY_ACTIVE
    assert ROSTER_STATUS_CATEGORY_ORDER[-1] == ROSTER_STATUS_CATEGORY_UNKNOWN


# ── 2. Injured list (IL_10 / IL_15 / IL_60 → injured_list) ────────────────────

def test_injured_list_statuses_map_to_injured_list_category():
    for status_code in (STATUS_IL_10, STATUS_IL_15, STATUS_IL_60):
        assert roster_status_category(_classified(status_code)) == ROSTER_STATUS_CATEGORY_INJURED_LIST


# ── 3. Optioned / minors ──────────────────────────────────────────────────────

def test_optioned_and_minors_map_to_optioned_or_minors_category():
    for status_code in (STATUS_OPTIONED, STATUS_MINORS):
        assert roster_status_category(_classified(status_code)) == ROSTER_STATUS_CATEGORY_OPTIONED_OR_MINORS


# ── 4. 40-man, not active ─────────────────────────────────────────────────────

def test_forty_man_only_maps_to_forty_man_not_active_category():
    assert roster_status_category(_classified(STATUS_40_MAN_ONLY)) == ROSTER_STATUS_CATEGORY_FORTY_MAN_NOT_ACTIVE


# ── 5. Restricted / suspended / special lists ─────────────────────────────────

def test_restricted_suspended_and_special_lists_map_to_restricted_or_special_category():
    for status_code in (STATUS_RESTRICTED, STATUS_SUSPENDED, STATUS_BEREAVEMENT, STATUS_PATERNITY):
        assert roster_status_category(_classified(status_code)) == ROSTER_STATUS_CATEGORY_RESTRICTED_OR_SPECIAL


# ── 6. Unknown / unconfirmed ──────────────────────────────────────────────────

def test_unknown_and_missing_status_map_to_unknown_category():
    assert roster_status_category(_classified(STATUS_UNKNOWN)) == ROSTER_STATUS_CATEGORY_UNKNOWN
    # None / empty / a status dict with no authoritative read all read as unknown.
    for empty in (None, {}, {'status': STATUS_UNKNOWN, 'is_active_mlb': None, 'is_inactive_context': False}):
        assert roster_status_category(empty) == ROSTER_STATUS_CATEGORY_UNKNOWN


def test_non_roster_and_dfa_map_to_non_roster_depth_category():
    for status_code in (STATUS_NON_ROSTER, STATUS_DFA):
        assert roster_status_category(_classified(status_code)) == ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH


def test_unmapped_off_roster_status_falls_back_to_non_roster_depth():
    # An off-roster arm (is_active_mlb False) whose fine status has no explicit mapping is
    # bucketed as non-roster depth — never as active or unknown, so the partition holds.
    odd = {'status': 'SOME_FUTURE_OFF_ROSTER_STATUS', 'is_active_mlb': False, 'is_inactive_context': True}
    assert roster_status_category(odd) == ROSTER_STATUS_CATEGORY_NON_ROSTER_DEPTH


# ── 7. Category counts match their evidence (and the published shape) ──────────

def test_category_counts_match_their_evidence_lengths():
    authority = build_roster_authority(_mixed_population())
    category_counts = authority['category_counts']
    category_evidence = authority['category_evidence']

    # Every published category is present (stable shape), in the canonical order.
    assert list(category_counts.keys()) == list(ROSTER_STATUS_CATEGORY_ORDER)
    assert list(category_evidence.keys()) == list(ROSTER_STATUS_CATEGORY_ORDER)
    # Each count is backed by an evidence list of the same length.
    for category in ROSTER_STATUS_CATEGORY_ORDER:
        assert category_counts[category] == len(category_evidence[category])

    # The mixed population's expected category breakdown.
    assert category_counts == {
        'active': 2,
        'injured_list': 2,
        'optioned_or_minors': 2,
        'forty_man_not_active': 1,
        'restricted_or_special_list': 2,
        'non_roster_depth': 2,
        'unknown': 1,
    }
    # The whole population is partitioned exactly once across the categories.
    assert sum(category_counts.values()) == authority['population']['total_candidates'] == 12


def test_category_evidence_entries_carry_category_fields_and_are_sorted():
    authority = build_roster_authority(_mixed_population())
    injured = authority['category_evidence']['injured_list']
    assert [e['name'] for e in injured] == sorted(e['name'] for e in injured)
    for entry in injured:
        assert entry['roster_status_category'] == 'injured_list'
        assert entry['roster_status_category_label'] == 'Injured list'
        # No engine internals leak into the category evidence the surface reads.
        assert set(entry) == {
            'pitcher_id', 'name', 'roster_status', 'roster_status_label',
            'roster_status_category', 'roster_status_category_label', 'availability', 'reason',
        }


# ── 8. Existing counts unchanged; category aggregates reconcile with them ──────

def test_existing_counts_and_buckets_are_unchanged_by_category_extension():
    authority = build_roster_authority(_mixed_population())
    counts = authority['counts']

    # The pre-existing invariant counts keep exactly their fields and values: the category
    # extension is additive and never perturbs an existing number.
    assert set(counts) == set(FIELD_INVARIANCE)
    assert counts['bullpen_arms'] == 2                       # the two active arms
    assert counts['inactive_roster_context_count'] == 9      # every off-roster arm
    assert counts['roster_unknown_count'] == 1               # the unconfirmed arm
    assert authority['population']['total_candidates'] == 12


def test_category_counts_reconcile_with_roster_buckets():
    authority = build_roster_authority(_mixed_population())
    counts = authority['counts']
    category_counts = authority['category_counts']

    # active ↔ bullpen_arms, unknown ↔ roster_unknown_count, and the off-roster categories
    # sum to inactive_roster_context_count — the categories are a refinement, not a new
    # source of truth.
    assert category_counts['active'] == counts['bullpen_arms']
    assert category_counts['unknown'] == counts['roster_unknown_count']
    off_roster = sum(
        category_counts[c] for c in (
            'injured_list', 'optioned_or_minors', 'forty_man_not_active',
            'restricted_or_special_list', 'non_roster_depth',
        )
    )
    assert off_roster == counts['inactive_roster_context_count']


# ── 9. Determinism / transport-neutrality of the category aggregates ──────────

def test_category_aggregates_are_deterministic_and_json_serializable():
    population = _mixed_population()
    first = build_roster_authority(population)
    second = build_roster_authority(list(reversed(population)))
    assert first['category_counts'] == second['category_counts']
    assert first['category_evidence'] == second['category_evidence']
    assert json.loads(json.dumps(first['category_counts'])) == first['category_counts']
    assert json.loads(json.dumps(first['category_evidence'])) == first['category_evidence']


def test_empty_population_publishes_every_category_at_zero():
    authority = build_roster_authority([])
    assert authority['category_counts'] == {c: 0 for c in ROSTER_STATUS_CATEGORY_ORDER}
    assert authority['category_evidence'] == {c: [] for c in ROSTER_STATUS_CATEGORY_ORDER}


# ── Labels are baseball language, owned here, never internal field names ───────

def test_category_labels_are_baseball_language_for_every_category():
    for category in ROSTER_STATUS_CATEGORY_ORDER:
        label = roster_status_category_label(category)
        assert label == ROSTER_STATUS_CATEGORY_LABELS[category]
        assert label and label != category          # a human label, not the internal key
        assert '_' not in label                      # never an internal field name


def test_category_label_falls_back_to_pending_for_unknown_key():
    assert roster_status_category_label('not_a_category') == ROSTER_STATUS_CATEGORY_LABELS[
        ROSTER_STATUS_CATEGORY_UNKNOWN
    ]


# ── 10. Categories are a strict refinement of the capacity-family predicates ───

def test_categories_are_strict_refinement_of_roster_predicates():
    """active ⟺ on the active roster; unknown ⟺ unconfirmed; everything else ⟺ off-roster.

    The capacity family classifies roster state through is_on_active_roster /
    is_off_active_roster / is_roster_status_unknown. Because the category of every status
    agrees with those predicates, adding categories cannot change a capacity-family count.
    """
    for status_code in EXPECTED_CATEGORY:
        rs = _classified(status_code)
        category = roster_status_category(rs)
        if category == ROSTER_STATUS_CATEGORY_ACTIVE:
            assert is_on_active_roster(rs)
            assert not is_off_active_roster(rs) and not is_roster_status_unknown(rs)
        elif category == ROSTER_STATUS_CATEGORY_UNKNOWN:
            assert is_roster_status_unknown(rs)
            assert not is_on_active_roster(rs) and not is_off_active_roster(rs)
        else:
            assert is_off_active_roster(rs)
            assert not is_on_active_roster(rs) and not is_roster_status_unknown(rs)


def test_capacity_family_behavior_unchanged_and_categories_align():
    records = [
        health_record(1),                                                                       # active, Available
        health_record(2, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),  # off the roster
        health_record(3, roster_status=STATUS_IL_60, active_mlb=False, inactive_context=True),   # injured (IL)
        health_record(4, roster_status='UNKNOWN', active_mlb=None),                              # roster unknown
    ]
    health = build_bullpen_resource_health(records)

    # Resource health's existing roster counts are unchanged by the category extension.
    assert health['roster_unavailable_reliever_count'] == 1   # the optioned arm (off-roster, non-IL)
    assert health['injured_reliever_count'] == 1              # the IL_60 arm
    assert health['unknown_reliever_count'] >= 1
    assert health['active_reliever_count'] == 1

    # Over the SAME population, the categories mirror that partition: injured_list aligns with
    # resource health's injured count and active with its active count. This is exactly what
    # lets CRC-7 replace the private INJURED_LIST_STATUSES set with the injured_list category
    # without moving a number.
    category_counts = build_roster_authority(records)['category_counts']
    assert category_counts['injured_list'] == health['injured_reliever_count']
    assert category_counts['active'] == health['active_reliever_count']
    assert category_counts['optioned_or_minors'] == health['roster_unavailable_reliever_count']
    assert category_counts['unknown'] >= 1
