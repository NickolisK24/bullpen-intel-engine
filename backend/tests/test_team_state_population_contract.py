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

These tests pin the population contract at the layer that decides it: which
records reach the readiness distributions. That contract — the canonical active
bullpen resolved by ``resolve_active_bullpen_membership`` — is unchanged by the
Team State vNext (Contract A) recalibration. The classification thresholds
themselves DID change with vNext (the worst-arm-wins escalation is gone), so the
status expectations below reflect Contract A; the population intent each fixture
demonstrates is identical.
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
    """Thin-but-not-severe clean coverage is Stretched under Contract A.

    Four clean arms out of seven: above the Vulnerable margin floor (clean > 2)
    and below the Fresh clean floor (clean < 5), with no severe share. The
    residual Stretched rule is what fires.
    """
    bullpen = [arm('available', 'low') for _ in range(4)]
    bullpen += [arm('monitor', 'moderate'), arm('limited', 'moderate'), arm('monitor', 'moderate')]

    payload = readiness_for(bullpen)

    assert payload['readiness']['status_code'] == 'operationally_constrained'
    assert payload['team_state_evidence']['decisive_rule'] == 'residual_stretched'
    # No severe inventory: the Stretched rule fired on clean coverage alone.
    assert payload['availability_distribution']['unavailable'] == 0
    assert payload['availability_distribution']['avoid'] == 0


# ── FIXTURE 3 — Vulnerable ───────────────────────────────────────────────────

def test_a_genuine_active_bullpen_stress_trigger_is_operationally_stressed():
    """A true severe share in the canonical bullpen drives Vulnerable.

    Under Contract A a single severe arm does NOT force Vulnerable; a severe SHARE
    at or above one third does. Four clean and three severe (3/7 severe) trips the
    severity-share route.
    """
    bullpen = [arm('available', 'low') for _ in range(4)]
    bullpen += [arm('avoid', 'elevated') for _ in range(3)]

    payload = readiness_for(bullpen)

    assert payload['readiness']['status_code'] == 'operationally_stressed'
    assert payload['team_state_evidence']['decisive_rule'] == 'severity_share'
    assert payload['availability_distribution']['avoid'] == 3


# ── FIXTURE 4 — Off-active records must not contaminate state ────────────────

def test_off_active_records_distort_a_rested_team_state():
    """The production defect, reproduced at the layer that caused it.

    This is the mechanism behind Detroit publishing a stressed state while showing
    a rested and available bullpen: the team's own bullpen is untouched, and extra
    records that are not part of it distort the state. Under Contract A one severe
    arm no longer flips a strong bullpen, but off-active severe arms still push the
    severe share past the Vulnerable route — which is exactly why the canonical
    population must exclude them.
    """
    bullpen = [arm('available', 'low') for _ in range(8)]
    starters_and_injured = [arm('unavailable', 'elevated') for _ in range(4)]

    assert status_of(bullpen) == 'operationally_stable'
    # 8 clean + 4 severe = 4/12 severe share (>= 1/3) -> Vulnerable if counted.
    assert status_of(bullpen + starters_and_injured) == 'operationally_stressed'


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
    """Three teams, three expected states, resolved back to back (Contract A)."""
    fresh = [arm('available', 'low') for _ in range(8)]
    stretched = [arm('available', 'low') for _ in range(4)] + [
        arm('monitor', 'moderate') for _ in range(3)
    ]
    vulnerable = [arm('available', 'low') for _ in range(4)] + [
        arm('avoid', 'elevated') for _ in range(3)
    ]

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


# ── The public mapping is untouched; the classification is Contract A ────────

@pytest.mark.parametrize('records,expected', [
    # A strong clean bullpen is Fresh.
    ([arm('available', 'low') for _ in range(6)], 'operationally_stable'),
    # Thin clean coverage with no severe share is Stretched.
    ([arm('available', 'low') for _ in range(4)]
     + [arm('monitor', 'moderate') for _ in range(3)], 'operationally_constrained'),
    # A severe share at or above one third is Vulnerable.
    ([arm('available', 'low') for _ in range(4)]
     + [arm('avoid', 'elevated') for _ in range(3)], 'operationally_stressed'),
    # Two or fewer clean arms is Vulnerable on the margin floor alone.
    ([arm('available', 'low') for _ in range(2)]
     + [arm('monitor', 'moderate') for _ in range(4)], 'operationally_stressed'),
])
def test_the_status_rule_is_contract_a(records, expected):
    """The status is decided by the Contract A partition of the same population."""
    assert status_of(records) == expected
