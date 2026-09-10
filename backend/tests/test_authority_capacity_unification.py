"""CRC Phase 5 — the Capacity family consumes Roster Authority.

Bullpen Capacity, Resource Health, Bullpen Stability, and the Trust Hierarchy (a capacity
sub-component) previously each defined their own ``_is_roster_unavailable`` predicate
(and resource health an ``_is_roster_unknown``, trust hierarchy an ``_is_active_mlb``).
Those duplicate roster predicates are removed; the family now reads the single canonical
roster predicates from ``services.roster_authority``. These tests prove the predicates are
centralized (no local copies remain), that each consumer imports the canonical predicate,
and that roster state is classified through it with results unchanged.
"""

import services.bullpen_capacity as capacity_mod
import services.bullpen_resource_health as health_mod
import services.bullpen_stability as stability_mod
import services.bullpen_trust_hierarchy as trust_mod
from services.bullpen_capacity import build_team_bullpen_capacity
from services.bullpen_resource_health import build_bullpen_resource_health
from services.roster_authority import (
    is_off_active_roster,
    is_on_active_roster,
    is_roster_status_unknown,
)
from services.roster_status import STATUS_IL_60, STATUS_MINORS
from tests.test_bullpen_resource_health import record as health_record


# ── Canonical predicates own roster truth ─────────────────────────────────────

def test_canonical_predicates_partition_roster_state():
    active = {'status': 'ACTIVE', 'is_active_mlb': True, 'is_inactive_context': False}
    off = {'status': 'MINORS', 'is_active_mlb': False, 'is_inactive_context': True}
    unknown = {'status': 'UNKNOWN', 'is_active_mlb': None, 'is_inactive_context': False}

    assert is_on_active_roster(active)
    assert not is_off_active_roster(active)
    assert not is_roster_status_unknown(active)

    assert is_off_active_roster(off)
    assert not is_on_active_roster(off)
    assert not is_roster_status_unknown(off)

    assert is_roster_status_unknown(unknown)
    assert not is_on_active_roster(unknown)
    assert not is_off_active_roster(unknown)

    # None / empty roster status is unknown and neither on nor off the active roster.
    for empty in (None, {}):
        assert is_roster_status_unknown(empty)
        assert not is_on_active_roster(empty)
        assert not is_off_active_roster(empty)


# ── Duplicate roster predicates eliminated in the capacity family ─────────────

def test_capacity_family_no_longer_defines_local_roster_predicates():
    for module in (capacity_mod, health_mod, stability_mod, trust_mod):
        assert not hasattr(module, '_is_roster_unavailable'), (
            f'{module.__name__} still defines its own _is_roster_unavailable'
        )
    assert not hasattr(health_mod, '_is_roster_unknown')
    assert not hasattr(trust_mod, '_is_active_mlb')


def test_capacity_family_reads_the_canonical_predicates():
    # Each consumer's bound predicate IS the one Roster Authority owns (same object).
    assert capacity_mod.is_off_active_roster is is_off_active_roster
    assert stability_mod.is_off_active_roster is is_off_active_roster
    assert health_mod.is_off_active_roster is is_off_active_roster
    assert health_mod.is_roster_status_unknown is is_roster_status_unknown
    assert trust_mod.is_off_active_roster is is_off_active_roster
    assert trust_mod.is_on_active_roster is is_on_active_roster


# ── Consumers classify roster state through the authority (results stable) ─────

def test_resource_health_classifies_roster_state_via_authority():
    records = [
        health_record(1),  # active MLB, Available
        health_record(2, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),  # off the roster
        health_record(3, roster_status=STATUS_IL_60, active_mlb=False, inactive_context=True),   # injured (IL)
        health_record(4, roster_status='UNKNOWN', active_mlb=None),                               # roster unknown
    ]
    payload = build_bullpen_resource_health(records)

    # The off-roster (non-IL) arm is the one is_off_active_roster flags as roster-unavailable.
    assert payload['roster_unavailable_reliever_count'] == 1
    assert payload['injured_reliever_count'] == 1
    assert payload['unknown_reliever_count'] >= 1
    assert payload['active_reliever_count'] == 1


def test_capacity_counts_off_roster_arms_via_authority():
    records = [
        health_record(1),  # active
        health_record(2, roster_status=STATUS_MINORS, active_mlb=False, inactive_context=True),  # off the roster
        health_record(3, roster_status=STATUS_IL_60, active_mlb=False, inactive_context=True),   # off the roster (IL)
    ]
    loss = build_team_bullpen_capacity(records)['capacity_loss']

    # Both off-roster arms (everything is_off_active_roster flags) count as inactive-roster
    # unavailable capacity; the active arm does not.
    assert loss['inactive_roster_unavailable_pitcher_count'] == 2
