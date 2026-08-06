"""Team State population contract (UX-001 production correction).

Production validation of #590 found every supported team collapsing to
Vulnerable across materially different Dashboard lanes — Detroit published
Vulnerable while showing eight rested and available arms.

The label migration was correct. The population was not: readiness
distributions were built from every pitcher on the team carrying a fatigue
score (``Pitcher.active``), while the trust metadata that authorizes the read
was built from the canonical current active bullpen. A starter who worked
yesterday, or an injured-list arm still flagged active, classifies Avoid or
Unavailable — and ``_readiness_status_code`` returns ``operationally_stressed``
when either the unavailable count or the elevated workload count is nonzero.
Every club has such an arm on any given day, so every club collapsed.

These tests pin the population contract at the layer that decides it. They do
not change any threshold, status meaning, or public mapping — a genuine active
bullpen record still drives state exactly as it did.
"""

import pytest

from services.team_readiness_coverage import (
    resolve_active_bullpen_membership,
    select_active_bullpen_records,
)
from team_operations import assemble_bullpen_readiness


TEAM = {'team_id': 116, 'team_name': 'Detroit Tigers', 'team_abbreviation': 'DET'}

TRUST_HIGH = {
    'confidence': 'high',
    'confidence_reasons': ['complete_active_bullpen_coverage'],
    'data_state': 'fresh',
    'source_evidence_state': 'represented',
    'governance_state': 'internal_uncertified',
    'generated_at': '2026-08-05T00:00:00+00:00',
    'limitations': [],
    'explanations': [],
    'refusal_reasons': [],
    'trust_validation_errors': [],
    'ranking_applied': False,
    'selection_made': False,
}

TRUST_UNKNOWN = {**TRUST_HIGH, 'confidence': 'unknown', 'data_state': 'missing'}

FRESHNESS_CURRENT = {
    'freshness_state': 'current',
    'data_through': '2026-08-04',
    'latest_workload_date': '2026-08-04',
    'last_successful_sync': '2026-08-05T00:00:00+00:00',
    'sync_status': 'success',
    'is_current': True,
    'is_stale': False,
    'generated_at': '2026-08-05T00:00:00+00:00',
    'limitations': [],
    'latest_fatigue_calculated_at': '2026-08-05T00:00:00+00:00',
    'latest_sync_status': 'success',
    'missing_data_warning': False,
    'stale_warning': False,
}


def arm(availability_status, workload_category):
    """One readiness record, exactly as ``_readiness_record`` shapes it."""
    return {
        'availability_status': availability_status,
        'workload_category': workload_category,
        'throwing_hand': 'R',
        'has_current_workload': True,
        'has_availability': True,
        'active': True,
    }


def readiness_for(records, *, trust=None):
    return assemble_bullpen_readiness(
        team=TEAM,
        pitcher_records=tuple(records),
        trust_metadata=trust or TRUST_HIGH,
        freshness=FRESHNESS_CURRENT,
        generated_at='2026-08-05T00:00:00+00:00',
    )


def status_of(records, *, trust=None):
    return readiness_for(records, trust=trust)['readiness']['status_code']


class FakePitcher:
    def __init__(self, pitcher_id):
        self.id = pitcher_id


def classified(pitcher_id):
    return {'pitcher': FakePitcher(pitcher_id)}


# ── FIXTURE 1 — Fresh ────────────────────────────────────────────────────────

def test_a_complete_rested_active_bullpen_is_operationally_stable():
    bullpen = [arm('available', 'low') for _ in range(8)]

    payload = readiness_for(bullpen)

    assert payload['readiness']['status_code'] == 'operationally_stable'
    assert payload['availability_distribution']['available'] == 8
    assert payload['availability_distribution']['unavailable'] == 0
    assert payload['workload_pressure']['elevated_count'] == 0


# ── FIXTURE 2 — Stretched ────────────────────────────────────────────────────

def test_a_monitored_active_bullpen_is_operationally_constrained():
    bullpen = [arm('available', 'low') for _ in range(6)]
    bullpen += [arm('monitor', 'moderate'), arm('limited', 'moderate')]

    payload = readiness_for(bullpen)

    assert payload['readiness']['status_code'] == 'operationally_constrained'
    # No stressed trigger: the constrained rule is what fired.
    assert payload['availability_distribution']['unavailable'] == 0
    assert payload['workload_pressure']['elevated_count'] == 0


# ── FIXTURE 3 — Vulnerable ───────────────────────────────────────────────────

def test_a_genuine_active_bullpen_stress_trigger_is_operationally_stressed():
    """A true canonical member still drives Vulnerable. The rule is unchanged."""
    bullpen = [arm('available', 'low') for _ in range(6)]
    bullpen += [arm('limited', 'moderate'), arm('unavailable', 'elevated')]

    payload = readiness_for(bullpen)

    assert payload['readiness']['status_code'] == 'operationally_stressed'
    assert payload['availability_distribution']['unavailable'] == 1
    assert payload['workload_pressure']['elevated_count'] == 1


# ── FIXTURE 4 — Off-active records must not contaminate state ────────────────

def test_one_non_bullpen_record_flips_a_rested_team_to_stressed():
    """The production defect, reproduced at the layer that caused it.

    This is the mechanism behind Detroit publishing Vulnerable while showing
    eight rested and available arms: the team's own bullpen is untouched, and a
    single extra record that is not part of it decides the state.
    """
    bullpen = [arm('available', 'low') for _ in range(8)]
    starter_who_worked_yesterday = arm('unavailable', 'elevated')

    assert status_of(bullpen) == 'operationally_stable'
    assert status_of(bullpen + [starter_who_worked_yesterday]) == 'operationally_stressed'


def test_selecting_the_canonical_population_removes_the_contamination():
    """The correction: only canonical members reach the distributions."""
    members = frozenset({1, 2, 3, 4, 5, 6, 7, 8})
    records = [classified(pitcher_id) for pitcher_id in sorted(members)]
    # Starters, injured-list arms, and off-active depth all carry fatigue scores
    # and all reach the resolver's row set.
    records += [classified(91), classified(92), classified(93)]

    selected = select_active_bullpen_records(records, members)

    assert len(selected) == 8
    assert {record['pitcher'].id for record in selected} == members


def test_off_active_arms_are_excluded_while_the_bullpen_stays_fresh():
    """End-to-end shape of FIXTURE 4: contaminating records are dropped first."""
    members = frozenset(range(1, 9))
    classified_records = [classified(pitcher_id) for pitcher_id in sorted(members)]
    classified_records.append(classified(99))  # injured-list arm, still flagged active

    by_pitcher = {pitcher_id: arm('available', 'low') for pitcher_id in members}
    by_pitcher[99] = arm('unavailable', 'elevated')

    selected = select_active_bullpen_records(classified_records, members)
    readiness_records = [by_pitcher[record['pitcher'].id] for record in selected]

    assert 99 not in {record['pitcher'].id for record in selected}
    assert status_of(readiness_records) == 'operationally_stable'


# ── FIXTURE 5 — Authority incomplete fails closed ────────────────────────────

def test_membership_fails_closed_without_a_team_id():
    ids, complete = resolve_active_bullpen_membership(None, None)

    assert ids == frozenset()
    assert complete is False


def test_an_incomplete_authority_selects_nothing_and_stays_data_limited():
    """No authority means no population, and unknown trust refuses first."""
    records = [classified(1), classified(2)]

    assert select_active_bullpen_records(records, frozenset()) == ()
    # The status resolver consults trust before any distribution, so an
    # unauthorized read never reaches a supported state.
    assert status_of([], trust=TRUST_UNKNOWN) == 'data_limited'


def test_an_empty_population_never_produces_a_supported_state():
    payload = readiness_for([], trust=TRUST_UNKNOWN)

    assert payload['readiness']['status_code'] == 'data_limited'
    assert payload['coverage_inventory']['coverage_state'] == 'missing'


# ── FIXTURE 6 — Sequential teams do not leak ─────────────────────────────────

def test_sequential_teams_resolve_independent_states():
    """Three teams, three expected states, resolved back to back."""
    fresh = [arm('available', 'low') for _ in range(8)]
    stretched = [arm('available', 'low') for _ in range(7)] + [arm('monitor', 'moderate')]
    vulnerable = [arm('available', 'low') for _ in range(7)] + [arm('unavailable', 'elevated')]

    results = [status_of(records) for records in (fresh, stretched, vulnerable, fresh)]

    assert results == [
        'operationally_stable',
        'operationally_constrained',
        'operationally_stressed',
        # The fourth call repeats the first: no prior team's result survives.
        'operationally_stable',
    ]


def test_selection_does_not_mutate_its_inputs():
    members = frozenset({1, 2})
    records = [classified(1), classified(2), classified(3)]

    first = select_active_bullpen_records(records, members)
    second = select_active_bullpen_records(records, members)

    assert len(records) == 3, 'selection must not consume or mutate the record list'
    assert [r['pitcher'].id for r in first] == [r['pitcher'].id for r in second]


def test_selection_tolerates_records_without_a_resolvable_pitcher():
    members = frozenset({1})

    selected = select_active_bullpen_records(
        [classified(1), {'pitcher': None}, {}], members,
    )

    assert [record['pitcher'].id for record in selected] == [1]


# ── The thresholds and the mapping are untouched ─────────────────────────────

@pytest.mark.parametrize('records,expected', [
    ([arm('available', 'low')], 'operationally_stable'),
    ([arm('monitor', 'moderate')], 'operationally_constrained'),
    ([arm('limited', 'moderate')], 'operationally_constrained'),
    ([arm('avoid', 'elevated')], 'operationally_stressed'),
    ([arm('unavailable', 'elevated')], 'operationally_stressed'),
])
def test_the_status_rule_itself_is_unchanged(records, expected):
    """Same inputs, same status. Only which records are inputs changed."""
    assert status_of(records) == expected
