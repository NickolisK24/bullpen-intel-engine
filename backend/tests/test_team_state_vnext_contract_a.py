"""Team State vNext — locked Contract A classifier.

These tests pin the calibrated Team State aggregation at the layer that decides
it: ``team_operations.assemble_bullpen_readiness``. They cover the locked
thresholds, the exact precedence, the real-world empirical profiles, the
status-only invariant, monotonicity over N=6..12, the exact share boundaries,
the canonical partition + evidence vector, the method-version boundary, and a
read-only shadow replay against the founder-approved calibration contract.

No database, no Flask app context, no network: the classifier is pure Python and
is exercised directly with in-memory readiness records.
"""

from fractions import Fraction
from itertools import product

import pytest

from services.readiness_population_comparison import (
    CONTRACT_A as CALIBRATION_CONTRACT_A,
    shadow_partition,
    shadow_state,
)
from team_operations import (
    ALLOWED_DECISIVE_RULES,
    TEAM_STATE_CONTRACT_A,
    TEAM_STATE_METHOD_VERSION,
    assemble_bullpen_readiness,
)
from team_operations.contracts import CONTRACT_VERSION


# ── Governed inputs that always clear the trust / data gate ──────────────────

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
TRUST_MEDIUM = {**TRUST_HIGH, 'confidence': 'medium'}
TRUST_LOW = {**TRUST_HIGH, 'confidence': 'low'}
TRUST_UNKNOWN = {**TRUST_HIGH, 'confidence': 'unknown', 'data_state': 'missing'}

FRESHNESS_CURRENT = {
    'freshness_state': 'current',
    'data_through': '2026-08-04',
    'latest_workload_date': '2026-08-04',
    'last_successful_sync': '2026-08-05T00:00:00+00:00',
    'latest_sync_status': 'success',
    'latest_fatigue_calculated_at': '2026-08-05T00:00:00+00:00',
    'generated_at': '2026-08-05T00:00:00+00:00',
    'stale_warning': None,
    'missing_data_warning': None,
    'limitations': [],
}
FRESHNESS_STALE = {**FRESHNESS_CURRENT, 'freshness_state': 'stale'}

TEAM = {'team_id': 42, 'team_name': 'Fixture Club', 'team_abbreviation': 'FIX'}

# Public vocabulary mapping (backend-owned, unchanged by vNext).
PUBLIC = {
    'operationally_stable': 'Fresh',
    'operationally_constrained': 'Stretched',
    'operationally_stressed': 'Vulnerable',
}
# Worse -> better ordering for monotonicity. data_limited is off the axis.
RANK = {'operationally_stressed': 0, 'operationally_constrained': 1, 'operationally_stable': 2}


def _arm(status, *, hand='R', workload='low'):
    """One readiness record. Coverage and handedness are complete so only the
    availability STATUS is in play — the classifier reads nothing else."""
    return {
        'availability_status': status,
        'workload_category': workload,
        'throwing_hand': hand,
        'has_current_workload': True,
        'has_availability': True,
        'active': True,
    }


def _records(clean, moderate, severe, unknown=0, *, workload='low'):
    return tuple(
        [_arm('available', workload=workload) for _ in range(clean)]
        + [_arm('monitor', workload=workload) for _ in range(moderate)]
        + [_arm('avoid', workload=workload) for _ in range(severe)]
        # An ungoverned availability value classifies UNKNOWN while keeping
        # coverage + handedness complete (so it is a pure status-unknown arm).
        + [_arm('nonsense', workload=workload) for _ in range(unknown)]
    )


def _payload(clean, moderate, severe, unknown=0, *, trust=None, freshness=None, workload='low'):
    return assemble_bullpen_readiness(
        team=TEAM,
        pitcher_records=_records(clean, moderate, severe, unknown, workload=workload),
        trust_metadata=trust or TRUST_HIGH,
        freshness=freshness or FRESHNESS_CURRENT,
        generated_at='2026-08-05T00:00:00+00:00',
    )


def _state(clean, moderate, severe, unknown=0, **kwargs):
    return _payload(clean, moderate, severe, unknown, **kwargs)['readiness']['status_code']


def _evidence(clean, moderate, severe, unknown=0, **kwargs):
    return _payload(clean, moderate, severe, unknown, **kwargs)['team_state_evidence']


# ── 1. Locked thresholds do not drift ────────────────────────────────────────

def test_contract_a_thresholds_match_the_calibration_contract():
    """The runtime thresholds are byte-for-byte the founder-approved calibration
    contract, so neither copy can drift out from under the other."""
    for key in (
        'clean_share_fresh_min',
        'clean_count_fresh_min',
        'severe_count_fresh_max',
        'clean_count_vulnerable_max',
        'severe_share_vulnerable_min',
    ):
        assert TEAM_STATE_CONTRACT_A[key] == CALIBRATION_CONTRACT_A[key]
    assert TEAM_STATE_CONTRACT_A['clean_share_fresh_min'] == (3, 5)
    assert TEAM_STATE_CONTRACT_A['clean_count_fresh_min'] == 5
    assert TEAM_STATE_CONTRACT_A['severe_count_fresh_max'] == 1
    assert TEAM_STATE_CONTRACT_A['clean_count_vulnerable_max'] == 2
    assert TEAM_STATE_CONTRACT_A['severe_share_vulnerable_min'] == (1, 3)
    assert TEAM_STATE_CONTRACT_A['basis'] == 'status_only'


# ── 2. Real-world fixtures (locked empirical profiles) ───────────────────────

# (name, clean, moderate, severe, unknown, expected public state, decisive_rule)
REAL_WORLD_FIXTURES = [
    ('KC',                  7, 4, 0, 0, 'Fresh',      'fresh_coverage'),
    ('TB boundary',         6, 4, 0, 0, 'Fresh',      'fresh_coverage'),
    ('LAD',                 4, 3, 0, 0, 'Stretched',  'residual_stretched'),
    ('HOU',                 3, 4, 0, 0, 'Stretched',  'residual_stretched'),
    ('CWS',                 3, 9, 0, 0, 'Stretched',  'residual_stretched'),
    ('CHC',                 5, 0, 2, 0, 'Stretched',  'residual_stretched'),
    ('TOR',                 0, 8, 1, 0, 'Vulnerable', 'margin_floor'),
    ('LAD deep',            0, 8, 0, 0, 'Vulnerable', 'margin_floor'),
    ('Small-N Fresh',       5, 1, 0, 0, 'Fresh',      'fresh_coverage'),
    ('Small-N floor guard', 4, 2, 0, 0, 'Stretched',  'residual_stretched'),
    ('One-severe strong',   7, 0, 1, 0, 'Fresh',      'fresh_coverage'),
    ('Two-severe strong',   5, 0, 2, 0, 'Stretched',  'residual_stretched'),
    ('ATL divergence',      3, 4, 0, 1, 'Stretched',  'residual_stretched'),
    # Live examples from the same-moment production shadow.
    ('BOS',                 7, 0, 1, 0, 'Fresh',      'fresh_coverage'),
    ('KC shadow',           9, 2, 0, 0, 'Fresh',      'fresh_coverage'),
    ('ATH',                 6, 4, 0, 0, 'Fresh',      'fresh_coverage'),
    ('CIN',                 1, 4, 3, 0, 'Vulnerable', 'margin_floor'),
    # The user-visible profile that exposed the reference-date defect: a Yankees
    # board showing six clean arms and two limited arms published as Stretched.
    # The classifier was never wrong about this shape — it is Fresh, and by a
    # wider margin than the 6/4/0/0 boundary above. What reached it was a
    # bullpen classified one day early. See
    # docs/decisions/2026-08-18-team-state-availability-reference-date.md.
    ('NYY 6 clean 2 limited', 6, 2, 0, 0, 'Fresh', 'fresh_coverage'),
]


@pytest.mark.parametrize(
    'name,clean,moderate,severe,unknown,public,rule', REAL_WORLD_FIXTURES,
    ids=[row[0] for row in REAL_WORLD_FIXTURES],
)
def test_real_world_fixture_classifies_exactly(name, clean, moderate, severe, unknown, public, rule):
    payload = _payload(clean, moderate, severe, unknown)
    code = payload['readiness']['status_code']
    assert PUBLIC[code] == public, name
    assert payload['team_state_evidence']['decisive_rule'] == rule, name


def test_six_clean_two_limited_is_fresh_with_a_three_quarter_clean_share():
    """The exact Yankees-shaped profile, stated as its own contract.

    Eight active arms, six clean, two moderate, nothing severe or unknown. Clean
    share is 3/4 — comfortably over the 3/5 floor — clean count clears 5, and no
    severe arm exists to cap it. This is Fresh on the fresh-coverage route, and it
    is the shape a reader saw published as Stretched before the availability
    reference date was split from the membership reference date.
    """
    evidence = _evidence(6, 2, 0, 0)
    assert (
        evidence['clean_count'],
        evidence['moderate_count'],
        evidence['severe_count'],
        evidence['unknown_count'],
        evidence['active_pitcher_count'],
    ) == (6, 2, 0, 0, 8)
    assert Fraction(evidence['clean_count'], evidence['active_pitcher_count']) == Fraction(3, 4)
    assert evidence['readiness_status_code'] == 'operationally_stable'
    assert PUBLIC[evidence['readiness_status_code']] == 'Fresh'
    assert evidence['decisive_rule'] == 'fresh_coverage'


def test_atl_divergence_preserves_the_unknown_arm():
    """ATL's one ungoverned arm stays UNKNOWN — never clean, never dropped, and
    the clean axis is unchanged. It is a required real-world fixture."""
    evidence = _evidence(3, 4, 0, 1)
    assert (
        evidence['clean_count'],
        evidence['moderate_count'],
        evidence['severe_count'],
        evidence['unknown_count'],
        evidence['active_pitcher_count'],
    ) == (3, 4, 0, 1, 8)
    assert PUBLIC[evidence['readiness_status_code']] == 'Stretched'


# ── 3. Exact precedence — Vulnerable is evaluated before Fresh ───────────────

def test_margin_floor_is_evaluated_before_fresh():
    # clean == 2 is Vulnerable even with an otherwise strong, all-clean bullpen.
    assert _state(2, 0, 0) == 'operationally_stressed'
    assert _evidence(2, 0, 0)['decisive_rule'] == 'margin_floor'


def test_severity_share_forces_vulnerable_over_fresh_coverage():
    # 5 clean + 3 severe (N=8): clean_share 0.625 and clean_count 5 would pass the
    # Fresh share/count, but severe_share 3/8 >= 1/3 makes it Vulnerable first, and
    # severe_count 3 > 1 disqualifies Fresh anyway.
    assert _state(5, 0, 3) == 'operationally_stressed'
    assert _evidence(5, 0, 3)['decisive_rule'] == 'severity_share'


def test_one_severe_arm_alone_does_not_force_vulnerable():
    # The old worst-arm defect: a single severe arm forced Vulnerable. Not anymore.
    assert _state(7, 0, 1) == 'operationally_stable'


# ── 4. Status-only: no raw-score, no workload-pressure authority ─────────────

def test_workload_category_does_not_change_the_state():
    """Identical availability statuses must yield an identical state regardless of
    the workload_category carried on each record. Team State aggregates the public
    availability status; it never reinterprets a fatigue score."""
    low = _payload(6, 0, 0, workload='low')
    elevated = _payload(6, 0, 0, workload='elevated')
    assert low['readiness']['status_code'] == elevated['readiness']['status_code']
    assert low['readiness']['status_code'] == 'operationally_stable'
    # The workload_pressure block still reports elevated context...
    assert elevated['workload_pressure']['elevated_count'] == 6
    # ...but it did not escalate the Team State.
    assert elevated['team_state_evidence']['decisive_rule'] == 'fresh_coverage'


def test_all_moderate_bullpen_is_vulnerable_not_merely_constrained():
    # LAD deep: 8 moderate arms, zero clean -> Vulnerable on the margin floor,
    # independent of any workload interpretation.
    assert _state(0, 8, 0) == 'operationally_stressed'
    assert _evidence(0, 8, 0)['decisive_rule'] == 'margin_floor'


# ── 5. Handedness no longer downgrades the baseball state ────────────────────

def test_partial_handedness_does_not_downgrade_a_fresh_bullpen():
    """A Fresh partition with missing throwing-hand data stays Fresh. Handedness is
    context, not a baseball-state downgrade, and with sufficient trust it does not
    even withhold the read."""
    records = tuple(
        [_arm('available', hand='unknown') for _ in range(3)]
        + [_arm('available', hand='R') for _ in range(3)]
    )
    payload = assemble_bullpen_readiness(
        team=TEAM, pitcher_records=records,
        trust_metadata=TRUST_HIGH, freshness=FRESHNESS_CURRENT,
    )
    assert payload['handedness_coverage']['coverage_state'] == 'partial'
    assert payload['readiness']['status_code'] == 'operationally_stable'
    assert payload['team_state_evidence']['decisive_rule'] == 'fresh_coverage'


# ── 6. Trust / data gate still fails closed ──────────────────────────────────

def test_low_confidence_is_data_limited():
    assert _state(6, 0, 0, trust=TRUST_LOW) == 'data_limited'
    assert _evidence(6, 0, 0, trust=TRUST_LOW)['decisive_rule'] == 'data_limited'


def test_unknown_confidence_is_data_limited():
    assert _state(6, 0, 0, trust=TRUST_UNKNOWN) == 'data_limited'


def test_stale_freshness_is_data_limited():
    assert _state(6, 0, 0, freshness=FRESHNESS_STALE) == 'data_limited'


def test_empty_population_never_produces_a_supported_state():
    """A zero-arm population is a data condition, not a Vulnerable state — the
    margin floor must not manufacture a state for a team with no arms."""
    payload = assemble_bullpen_readiness(
        team=TEAM, pitcher_records=(),
        trust_metadata=TRUST_HIGH, freshness=FRESHNESS_CURRENT,
    )
    assert payload['readiness']['status_code'] == 'data_limited'
    assert payload['team_state_evidence']['decisive_rule'] == 'data_limited'


def test_medium_confidence_still_reaches_a_supported_state():
    assert _state(6, 0, 0, trust=TRUST_MEDIUM) == 'operationally_stable'


# ── 7. Canonical partition + evidence vector ─────────────────────────────────

@pytest.mark.parametrize('clean,moderate,severe,unknown', [
    (7, 4, 0, 0), (3, 4, 0, 1), (0, 8, 1, 0), (5, 0, 2, 0), (1, 4, 3, 0),
])
def test_partition_invariant_holds(clean, moderate, severe, unknown):
    payload = _payload(clean, moderate, severe, unknown)
    evidence = payload['team_state_evidence']
    total = clean + moderate + severe + unknown
    assert (
        evidence['clean_count'] + evidence['moderate_count']
        + evidence['severe_count'] + evidence['unknown_count']
    ) == evidence['active_pitcher_count'] == total
    # The evidence partition equals the availability distribution partition.
    dist = payload['availability_distribution']
    assert evidence['clean_count'] == dist['available']
    assert evidence['moderate_count'] == dist['monitor'] + dist['limited']
    assert evidence['severe_count'] == dist['avoid'] + dist['unavailable']
    assert evidence['unknown_count'] == dist['unknown']


def test_evidence_vector_is_complete_and_governed():
    evidence = _evidence(7, 4, 0, 0)
    for field in (
        'method_version', 'active_pitcher_count', 'clean_count', 'moderate_count',
        'severe_count', 'unknown_count', 'clean_share', 'moderate_share',
        'severe_share', 'unknown_share', 'decisive_rule', 'decisive_inputs',
        'thresholds_applied', 'trust_state', 'freshness_state', 'material_limitations',
        'evidence_references',
    ):
        assert field in evidence, field
    assert evidence['method_version'] == TEAM_STATE_METHOD_VERSION
    assert evidence['decisive_rule'] in ALLOWED_DECISIVE_RULES
    assert evidence['clean_share'] == pytest.approx(7 / 11)
    assert evidence['trust_state'] == 'high'
    assert evidence['freshness_state'] == 'current'


def test_thresholds_applied_are_the_locked_rationals():
    thresholds = _evidence(6, 4, 0, 0)['thresholds_applied']
    assert thresholds['clean_share_fresh_min'] == [3, 5]
    assert thresholds['clean_count_fresh_min'] == 5
    assert thresholds['severe_count_fresh_max'] == 1
    assert thresholds['clean_count_vulnerable_max'] == 2
    assert thresholds['severe_share_vulnerable_min'] == [1, 3]


def test_decisive_inputs_name_the_rule_that_fired():
    assert _evidence(2, 4, 0)['decisive_inputs']['clean_count'] == 2
    assert _evidence(4, 0, 3)['decisive_inputs']['severe_count'] == 3
    assert _evidence(6, 4, 0)['decisive_inputs']['clean_count'] == 6
    assert _evidence(4, 3, 0)['decisive_inputs']['clean_count'] == 4


def test_unknown_arm_appears_in_material_limitations():
    limitations = {
        item['limitation_id'] for item in _evidence(3, 4, 0, 1)['material_limitations']
    }
    assert 'unknown_arms_present' in limitations


# ── 8. Exact share boundaries (no float ambiguity) ───────────────────────────

def test_clean_share_exactly_three_fifths_qualifies_for_fresh():
    # 6 clean / 10 total = 3/5 exactly, clean_count 6 >= 5, severe 0 -> Fresh.
    assert _state(6, 4, 0) == 'operationally_stable'
    assert Fraction(6, 10) == Fraction(3, 5)


def test_clean_share_just_below_three_fifths_does_not_qualify_for_fresh():
    # 6 clean / 11 total = 6/11 < 3/5, clean_count still 6 -> Stretched, isolating
    # the share boundary at a fixed clean count.
    assert _state(6, 5, 0) == 'operationally_constrained'
    assert Fraction(6, 11) < Fraction(3, 5)


def test_share_alone_is_not_enough_without_the_count_floor():
    # 3 clean / 5 total = 3/5 exactly, but clean_count 3 < 5 -> not Fresh (Stretched).
    assert _state(3, 2, 0) == 'operationally_constrained'


def test_severe_share_exactly_one_third_routes_to_vulnerable():
    # 2 severe / 6 total = 1/3 exactly, clean 4 (> margin floor) -> severity share.
    assert _state(4, 0, 2) == 'operationally_stressed'
    assert _evidence(4, 0, 2)['decisive_rule'] == 'severity_share'
    assert Fraction(2, 6) == Fraction(1, 3)


def test_severe_share_just_below_one_third_does_not_route_to_vulnerable():
    # 2 severe / 7 total < 1/3, clean 5 -> Stretched (severe_count 2 also blocks Fresh).
    assert _state(5, 0, 2) == 'operationally_constrained'
    assert Fraction(2, 7) < Fraction(1, 3)


# ── 9. Monotonicity over N = 6..12 ───────────────────────────────────────────

def _rank_of(clean, moderate, severe, unknown=0):
    code = _state(clean, moderate, severe, unknown)
    assert code in RANK, (clean, moderate, severe, unknown, code)
    return RANK[code]


def _all_partitions(n):
    for clean in range(n + 1):
        for moderate in range(n - clean + 1):
            severe = n - clean - moderate
            yield clean, moderate, severe


def test_monotonicity_over_realistic_bullpen_sizes():
    """Exhaustive over every clean/moderate/severe partition of N=6..12.

    Improving an arm (severe -> moderate -> clean) can never worsen the state, and
    degrading an arm (clean -> moderate -> severe) can never improve it.
    """
    for n in range(6, 13):
        ranks = {
            (c, m, s): _rank_of(c, m, s) for c, m, s in _all_partitions(n)
        }
        for (c, m, s), rank in ranks.items():
            # Severe -> Moderate cannot worsen.
            if s > 0:
                assert ranks[(c, m + 1, s - 1)] >= rank, (n, c, m, s, 'sev->mod')
            # Moderate -> Clean cannot worsen.
            if m > 0:
                assert ranks[(c + 1, m - 1, s)] >= rank, (n, c, m, s, 'mod->clean')
            # Severe -> Clean cannot worsen.
            if s > 0:
                assert ranks[(c + 1, m, s - 1)] >= rank, (n, c, m, s, 'sev->clean')


def test_adding_clean_coverage_cannot_worsen_state():
    for n in range(6, 12):
        for c, m, s in _all_partitions(n):
            assert _rank_of(c + 1, m, s) >= _rank_of(c, m, s), (n, c, m, s)


def test_removing_a_severe_arm_cannot_worsen_state():
    for n in range(6, 13):
        for c, m, s in _all_partitions(n):
            if s > 0:
                # Removing a severe arm (N shrinks by one) cannot make it worse.
                assert _rank_of(c, m, s - 1) >= _rank_of(c, m, s), (n, c, m, s)


def test_unknown_arms_never_improve_the_state_by_implicit_zero():
    """An UNKNOWN arm is a real member of the population; it must never be treated
    as clean. Replacing a clean arm with an unknown one cannot improve the state."""
    for c, m, s in [(6, 2, 0), (5, 3, 0), (4, 2, 0), (3, 3, 0)]:
        if c > 0:
            with_unknown = _rank_of(c - 1, m, s, 1)
            baseline = _rank_of(c, m, s, 0)
            assert with_unknown <= baseline, (c, m, s)


# ── 10. Determinism ──────────────────────────────────────────────────────────

def test_classification_is_deterministic():
    first = _payload(3, 4, 0, 1)
    second = _payload(3, 4, 0, 1)
    assert first == second


# ── 11. Method-version boundary on the readiness payload ─────────────────────

def test_readiness_payload_stamps_the_vnext_contract_version():
    payload = _payload(7, 4, 0, 0)
    assert payload['contract_version'] == 'v3_phase_5'
    assert payload['contract_version'] == CONTRACT_VERSION
    assert payload['team_state_evidence']['method_version'] == 'v3_phase_5'


def test_refused_payload_still_records_the_method_version():
    payload = assemble_bullpen_readiness(
        team=TEAM, pitcher_records=_records(6, 0, 0),
        trust_metadata=None, freshness=FRESHNESS_CURRENT,
    )
    assert payload['contract_state'] == 'refused'
    evidence = payload['team_state_evidence']
    assert evidence['method_version'] == TEAM_STATE_METHOD_VERSION
    assert evidence['decisive_rule'] == 'data_limited'
    # No fabricated zero-arm partition on a refused read.
    assert evidence['active_pitcher_count'] is None
    assert evidence['clean_count'] is None


# ── 12. Shadow replay against the founder-approved calibration contract ──────

def test_runtime_classifier_matches_offline_contract_a_shadow():
    """Read-only shadow replay: for every locked empirical profile the runtime
    classifier's public state equals the offline Contract A shadow computed by the
    calibration module. One method, one threshold interpretation, two code paths
    that must agree exactly."""
    for name, clean, moderate, severe, unknown, public, _rule in REAL_WORLD_FIXTURES:
        statuses = (
            ['Available'] * clean
            + ['Monitor'] * moderate
            + ['Avoid'] * severe
            + [None] * unknown
        )
        offline = shadow_state(shadow_partition(statuses))
        assert offline == public, name
        runtime = PUBLIC[_state(clean, moderate, severe, unknown)]
        assert runtime == offline, name


def test_shadow_partition_matches_runtime_partition():
    for _name, clean, moderate, severe, unknown, _public, _rule in REAL_WORLD_FIXTURES:
        statuses = (
            ['Available'] * clean + ['Monitor'] * moderate
            + ['Avoid'] * severe + [None] * unknown
        )
        offline = shadow_partition(statuses)
        evidence = _evidence(clean, moderate, severe, unknown)
        assert offline['clean_count'] == evidence['clean_count']
        assert offline['moderate_count'] == evidence['moderate_count']
        assert offline['severe_count'] == evidence['severe_count']
        assert offline['unknown_count'] == evidence['unknown_count']


# ── 13. Historical immutability — the artifact surface is left untouched ──────

def _eligible_source():
    from datetime import date, datetime
    from services.team_state_source import TeamStateSnapshotAuthority, TeamStateSource
    authority = TeamStateSnapshotAuthority(
        snapshot_id=1, sync_run_id=1, data_through=date(2026, 8, 4),
        published_at=datetime(2026, 8, 5, 0, 0, 0), unavailable_reason=None,
    )
    readiness = assemble_bullpen_readiness(
        team={'team_id': 42, 'team_name': 'Fixture Club', 'team_abbreviation': 'FIX'},
        pitcher_records=_records(6, 0, 0),
        trust_metadata=TRUST_HIGH,
        freshness={**FRESHNESS_CURRENT, 'data_through': '2026-08-04'},
        generated_at='2026-08-05T00:00:00+00:00',
    )
    return TeamStateSource(team_id=42, team_valid=True, snapshot=authority, readiness=readiness)


def test_render_version_registry_is_untouched_by_vnext():
    """The immutable Share Artifact builder is a frozen surface and stays frozen:
    the method-version boundary lives on the readiness payload, not the artifact.
    LATEST is unchanged, so every historical artifact is byte-for-byte unaffected —
    nothing is migrated, rewritten, or backfilled."""
    from services.team_state_payload import (
        TEAM_STATE_LATEST, TEAM_STATE_V1, TEAM_STATE_V1_1, TEAM_STATE_V1_2,
        team_state_payload_registry,
    )
    versions = team_state_payload_registry.versions()
    for legacy in (TEAM_STATE_V1, TEAM_STATE_V1_1, TEAM_STATE_V1_2):
        assert legacy in versions
    assert TEAM_STATE_LATEST == TEAM_STATE_V1_2


def test_artifact_documents_do_not_carry_the_vnext_method_blocks():
    """The vNext method version and evidence vector live on the readiness payload.
    The immutable artifact document is deliberately unchanged, so a built document
    carries no new method block — historical artifacts retain their exact shape."""
    from services.team_state_eligibility import evaluate_team_state_eligibility
    from services.team_state_payload import (
        TEAM_STATE_V1, TEAM_STATE_V1_1, team_state_payload_registry,
    )
    source = _eligible_source()
    for version in (TEAM_STATE_V1, TEAM_STATE_V1_1):
        eligibility = evaluate_team_state_eligibility(source, payload_version=version)
        assert eligibility.eligible, eligibility.blocking_conditions
        document = team_state_payload_registry.get(version).builder(source, eligibility)['document']
        assert document['payload_version'] == version
        assert 'team_state_method' not in document
        assert 'team_state_evidence' not in document


def test_legacy_document_build_is_deterministic():
    from services.team_state_eligibility import evaluate_team_state_eligibility
    from services.team_state_payload import TEAM_STATE_V1, team_state_payload_registry
    source = _eligible_source()
    eligibility = evaluate_team_state_eligibility(source, payload_version=TEAM_STATE_V1)
    contract = team_state_payload_registry.get(TEAM_STATE_V1)
    first = contract.builder(source, eligibility)['document']
    second = contract.builder(source, eligibility)['document']
    assert first == second


# ── 14. Cross-version: What Changed never compares Team State ─────────────────

def _capacity_snapshot(*, team_state_label):
    """A minimal capacity-intelligence payload with a (deliberately ignored)
    public Team State block attached to the team item."""
    return {
        'capacity_intelligence': {
            'teams': [{
                'team_id': 42,
                'team_name': 'Fixture Club',
                'team_abbreviation': 'FIX',
                # The Team State block a surface would attach — What Changed must
                # never read it.
                'team_state': {'public_label': team_state_label},
                'resource_health': {
                    'resource_health_state': 'strong',
                    'confidence': 'high',
                    'bullpen_capacity': {
                        'capacity_state': 'healthy',
                        'clean_active_reliever_count': 6,
                        'active_reliever_count': 8,
                    },
                },
                'trust_hierarchy': {
                    'anchor_count': 2, 'leverage_count': 2, 'trusted_count': 2,
                    'hierarchy_confidence': 'high',
                },
                'bullpen_identity': {'identity_key': 'balanced', 'identity_label': 'Balanced'},
            }],
        },
        'freshness': {'data_through': '2026-08-04'},
    }


def test_what_changed_does_not_treat_team_state_as_a_change():
    """The version boundary cannot surface as a false baseball transition: What
    Changed compares capacity intelligence, not the Team State classification. Two
    snapshots with identical capacity but different Team State labels report no
    change, and no change carries Team State vocabulary."""
    from services.what_changed_since_yesterday import (
        STATE_NO_MEANINGFUL_CHANGES,
        build_what_changed_since_yesterday_payload,
    )
    current = _capacity_snapshot(team_state_label='Fresh')
    prior = _capacity_snapshot(team_state_label='Vulnerable')

    payload = build_what_changed_since_yesterday_payload(
        current, prior,
        current_snapshot_metadata={'data_through': '2026-08-04', 'is_published': True},
        prior_snapshot_metadata={'data_through': '2026-08-03', 'published_at': 'x'},
    )

    assert payload['change_count'] == 0
    assert payload['state'] == STATE_NO_MEANINGFUL_CHANGES
    serialized = str(payload)
    for public_label in ('Fresh', 'Stretched', 'Vulnerable'):
        assert public_label not in serialized


# ── 15. Why compatibility — the explanation cannot contradict the state ──────

@pytest.mark.parametrize('clean,moderate,severe,unknown', [
    (7, 4, 0, 0), (7, 0, 1, 0), (4, 3, 0, 0), (0, 8, 1, 0), (3, 4, 0, 1),
])
def test_readiness_explanation_state_never_contradicts_the_classifier(
    clean, moderate, severe, unknown,
):
    """The known historical defect — Stretched text asserting 'one reliever
    Unavailable' while the classifier forced Vulnerable — is structurally
    impossible now: the explanation reads the exact status the classifier
    published, from the same population and the same evidence vector."""
    from explanations import serialize_readiness_explanation

    payload = _payload(clean, moderate, severe, unknown)
    status_code = payload['readiness']['status_code']
    explanation = serialize_readiness_explanation(
        payload, scope='readiness_state', generated_at='2026-08-05T00:05:00Z',
    )
    assert explanation['state_explained'] == status_code


def test_one_severe_arm_is_visible_as_context_without_forcing_vulnerable():
    """The one-severe strong-coverage profile is Fresh, and the severe arm is
    carried as honest evidence (severe_count == 1) — visible context, not a forced
    Vulnerable state. That is the exact contradiction the recalibration removes."""
    payload = _payload(7, 0, 1)
    assert payload['readiness']['status_code'] == 'operationally_stable'
    assert payload['team_state_evidence']['severe_count'] == 1
