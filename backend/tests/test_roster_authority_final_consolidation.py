"""CRC Phase 8 — final roster-category consolidation.

This is the cleanup that makes Roster Authority the single source of roster truth. The last
two consumers that kept private roster grouping — Resource Health (`INJURED_LIST_STATUSES`)
and the public pitcher labels (`INACTIVE_ROSTER_STATUSES` + a private `_roster_unavailable`
predicate) — now read the authority. These tests prove the private sets are gone, the
consumers bind to the canonical authority functions, Resource Health's injured count equals
the authority's `injured_list` category, the public label reads the canonical off-roster
predicate, and behaviour is unchanged.
"""

from types import SimpleNamespace

import pytest

import services.bullpen_resource_health as health_mod
import services.pitcher_public_labels as labels_mod
from services.bullpen_resource_health import build_bullpen_resource_health
from services.pitcher_public_labels import _roster_unavailable, build_pitcher_labels
from services.roster_authority import (
    build_roster_authority,
    is_off_active_roster,
    roster_status_category,
    roster_status_category_for_status,
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


ALL_STATUSES = [
    STATUS_ACTIVE, STATUS_IL_10, STATUS_IL_15, STATUS_IL_60, STATUS_OPTIONED, STATUS_MINORS,
    STATUS_40_MAN_ONLY, STATUS_RESTRICTED, STATUS_SUSPENDED, STATUS_BEREAVEMENT,
    STATUS_PATERNITY, STATUS_DFA, STATUS_NON_ROSTER, STATUS_UNKNOWN,
]


def _classified(status_code):
    pitcher = SimpleNamespace(
        roster_status=status_code, roster_status_source='mlb_stats_api',
        roster_status_updated_at=None, roster_status_raw_code=None,
        roster_status_raw_description=None, active=(status_code == STATUS_ACTIVE),
    )
    return classify_roster_status(pitcher)


def _availability(status='Available'):
    return {'availability_status': status, 'data_state': 'fresh', 'confidence': 'high'}


def _role():
    return {'role_key': 'setup_bridge', 'confidence': 'high', 'sample_size': 4}


# ── 1. Remaining duplicated category logic has been eliminated ────────────────

def test_no_private_roster_status_sets_remain_in_the_consumers():
    # The last private status sets are gone — Roster Authority owns the grouping now.
    assert not hasattr(health_mod, 'INJURED_LIST_STATUSES'), 'Resource Health still defines INJURED_LIST_STATUSES'
    assert not hasattr(labels_mod, 'INACTIVE_ROSTER_STATUSES'), 'pitcher_public_labels still defines INACTIVE_ROSTER_STATUSES'


def test_consumers_bind_to_the_canonical_authority_functions():
    # Each consumer's roster classification IS the authority's (same object), not a local copy.
    assert health_mod.roster_status_category is roster_status_category
    assert health_mod.is_off_active_roster is is_off_active_roster
    assert labels_mod.is_off_active_roster is is_off_active_roster
    assert labels_mod.roster_status_category_for_status is roster_status_category_for_status


# ── 2. Resource Health consumes Roster Authority categories ───────────────────

def test_resource_health_injured_count_equals_authority_injured_category():
    records = [
        health_record(1),  # active
        health_record(2, roster_status=STATUS_IL_60, active_mlb=False, inactive_context=True),    # injured
        health_record(3, roster_status=STATUS_IL_15, active_mlb=False, inactive_context=True),    # injured
        health_record(4, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),   # off-roster, non-IL
        health_record(5, roster_status=STATUS_40_MAN_ONLY, active_mlb=False, inactive_context=True),
        health_record(6, roster_status=STATUS_RESTRICTED, active_mlb=False, inactive_context=True),
        health_record(7, roster_status=STATUS_DFA, active_mlb=False, inactive_context=True),
        health_record(8, roster_status=STATUS_NON_ROSTER, active_mlb=False, inactive_context=True),
        health_record(9, roster_status=STATUS_UNKNOWN, active_mlb=None),                           # unknown
    ]
    health = build_bullpen_resource_health(records)
    # The authority sees the same records (it reads each record's roster_status dict).
    category_counts = build_roster_authority(records)['category_counts']

    # Injured count IS the injured_list category; the non-IL off-roster count IS the sum of the
    # other off-roster categories. Resource Health no longer decides "which statuses are IL".
    assert health['injured_reliever_count'] == category_counts['injured_list'] == 2
    non_il_off_roster = (
        category_counts['optioned_or_minors']
        + category_counts['forty_man_not_active']
        + category_counts['restricted_or_special_list']
        + category_counts['non_roster_depth']
    )
    assert health['roster_unavailable_reliever_count'] == non_il_off_roster == 5
    assert health['active_reliever_count'] == category_counts['active'] == 1


def test_resource_health_injured_count_unchanged_versus_legacy_il_set():
    # Behaviour parity: the injured count equals what the old {IL_10, IL_15, IL_60} set produced.
    legacy_il = {STATUS_IL_10, STATUS_IL_15, STATUS_IL_60}
    records = [
        health_record(1),
        health_record(2, roster_status=STATUS_IL_10, active_mlb=False, inactive_context=True),
        health_record(3, roster_status=STATUS_IL_60, active_mlb=False, inactive_context=True),
        health_record(4, roster_status=STATUS_OPTIONED, active_mlb=False, inactive_context=True),
    ]
    health = build_bullpen_resource_health(records)
    expected_injured = sum(
        1 for r in records if (r['roster_status'] or {}).get('status') in legacy_il
    )
    assert health['injured_reliever_count'] == expected_injured == 2


# ── 3. pitcher_public_labels consumes the canonical off-roster predicate ──────

@pytest.mark.parametrize('status_code', ALL_STATUSES)
def test_roster_unavailable_equals_canonical_off_roster_for_classified_status(status_code):
    # For a fully classified status, the label's off-roster read is exactly the authority's
    # is_off_active_roster — no private set, no private predicate.
    roster_status = _classified(status_code)
    assert _roster_unavailable(roster_status) == is_off_active_roster(roster_status)


def test_roster_unavailable_handles_bare_status_codes_via_authority_categories():
    # A bare status code (no classification flags) is off-roster when its authority category is
    # neither active nor unknown — preserving the prior status-set behaviour exactly.
    assert _roster_unavailable({'status': STATUS_IL_60}) is True
    assert _roster_unavailable({'status': STATUS_OPTIONED}) is True
    assert _roster_unavailable({'roster_status': STATUS_RESTRICTED}) is True   # nested key honored
    assert _roster_unavailable({'status': STATUS_ACTIVE}) is False
    assert _roster_unavailable({'status': STATUS_UNKNOWN}) is False
    assert _roster_unavailable({}) is False
    assert _roster_unavailable(None) is False


# ── 4. Existing outputs remain unchanged (public label behaviour) ─────────────

def test_public_read_label_unchanged_for_off_roster_and_active():
    off_roster = build_pitcher_labels(
        availability=_availability('Available'), role=_role(), roster_status=_classified(STATUS_IL_60),
    )
    assert off_roster['read']['label'] == 'Unavailable'
    assert off_roster['read']['source'] == 'backend:unavailable_status'

    active = build_pitcher_labels(
        availability=_availability('Available'), role=_role(), roster_status=_classified(STATUS_ACTIVE),
    )
    assert active['read']['label'] == 'Clean Option'

    unknown = build_pitcher_labels(
        availability=_availability('Available'), role=_role(), roster_status=_classified(STATUS_UNKNOWN),
    )
    assert unknown['read']['label'] == 'Clean Option'   # unknown roster status is not "unavailable"
