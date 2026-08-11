from datetime import date, timedelta

from services.pitcher_public_labels import (
    READ_PUBLIC_LABELS,
    ROLE_KEY_TO_PUBLIC_KEY,
    ROLE_PUBLIC_LABELS,
    build_pitcher_labels,
)
from services.pitcher_role import ROLE_KEYS, classify_usage_role


def availability(status='Available', data_state='fresh', confidence='high'):
    return {
        'availability_status': status,
        'data_state': data_state,
        'confidence': confidence,
    }


def role(role_key, confidence='high', sample_size=4, **extra):
    return {
        'role_key': role_key,
        'confidence': confidence,
        'sample_size': sample_size,
        'evidence': ['4 appearances in the recent window'],
        **extra,
    }


# The one canonical public role vocabulary. Every classifier role key must map
# onto exactly these keys and labels on every public surface.
CANONICAL_ROLE_PIPELINE = [
    ('late_high_leverage', 'trust_arm', 'Trusted Arm'),
    ('setup_bridge', 'bridge_arm', 'Setup Arm'),
    ('middle_relief', 'depth_arm', 'Middle Relief Arm'),
    ('long_multi_inning', 'coverage_arm', 'Coverage Arm'),
    ('low_unclear', 'limited_read', 'Role Unclear'),
    ('insufficient_data', 'limited_read', 'Role Unclear'),
]


def test_role_keys_map_to_backend_public_labels():
    for role_key, expected_key, expected_label in CANONICAL_ROLE_PIPELINE:
        labels = build_pitcher_labels(availability=availability(), role=role(role_key))
        assert labels['role']['key'] == expected_key
        assert labels['role']['label'] == expected_label
        assert labels['role']['source'].startswith('backend:')


def test_middle_relief_does_not_map_to_bridge_arm():
    # Regression guard: middle relief is a distinct baseball role and must not
    # collapse into the setup/bridge slot (the Setup Arm chip).
    assert ROLE_KEY_TO_PUBLIC_KEY['middle_relief'] == 'depth_arm'
    assert ROLE_KEY_TO_PUBLIC_KEY['middle'] == 'depth_arm'

    labels = build_pitcher_labels(availability=availability(), role=role('middle_relief'))
    assert labels['role']['key'] != 'bridge_arm'
    assert labels['role']['label'] != 'Setup Arm'
    assert labels['role']['key'] == 'depth_arm'
    assert labels['role']['label'] == 'Middle Relief Arm'


def test_setup_bridge_still_maps_to_bridge_arm():
    assert ROLE_KEY_TO_PUBLIC_KEY['setup_bridge'] == 'bridge_arm'
    labels = build_pitcher_labels(availability=availability(), role=role('setup_bridge'))
    assert labels['role']['key'] == 'bridge_arm'
    assert labels['role']['label'] == 'Setup Arm'


class _LogStub:
    def __init__(self, days_ago, innings, save=False, hold=False, leverage_index=None,
                 reference_date=date(2026, 6, 20)):
        self.game_date = reference_date - timedelta(days=days_ago)
        self.innings_pitched = innings
        self.innings_pitched_outs = None if innings is None else int(round(innings * 3))
        self.save = save
        self.hold = hold
        self.save_situation = save
        self.leverage_index = leverage_index


def test_every_canonical_public_role_key_is_reachable_from_realistic_usage():
    # Each canonical public role key must be producible by a realistic
    # classifier result flowing through the real pipeline (classify_usage_role
    # -> build_pitcher_labels), so no public slot is dead vocabulary.
    ref = date(2026, 6, 20)
    usage_histories = {
        'trust_arm': [_LogStub(d, 1.0, save=(d == 2), leverage_index=1.6) for d in (2, 5, 9, 13)],
        'bridge_arm': [_LogStub(d, 1.0, hold=(d in (2, 5)), leverage_index=1.2) for d in (2, 5, 9, 13)],
        'depth_arm': [_LogStub(d, 1.0, leverage_index=0.9) for d in (2, 5, 9, 13)],
        'coverage_arm': [_LogStub(d, 2.0, leverage_index=0.7) for d in (2, 7, 12, 18)],
        'limited_read': [_LogStub(3, 1.0, leverage_index=1.0)],
    }

    reached = {}
    for expected_key, logs in usage_histories.items():
        usage_role = classify_usage_role(logs, reference_date=ref)
        labels = build_pitcher_labels(availability=availability(), role=usage_role)
        reached[expected_key] = labels['role']['key']

    assert reached == {key: key for key in ROLE_PUBLIC_LABELS}


def test_canonical_vocabulary_contract():
    # Vocabulary drift guard: the classifier role keys, the public mapping, and
    # the public label wording must stay exactly on the canonical table above.
    assert set(ROLE_KEYS) == {case[0] for case in CANONICAL_ROLE_PIPELINE}
    for role_key, expected_key, expected_label in CANONICAL_ROLE_PIPELINE:
        assert ROLE_KEY_TO_PUBLIC_KEY[role_key] == expected_key
        assert ROLE_PUBLIC_LABELS[expected_key]['label'] == expected_label
    assert {payload['label'] for payload in ROLE_PUBLIC_LABELS.values()} == {
        'Trusted Arm',
        'Setup Arm',
        'Middle Relief Arm',
        'Coverage Arm',
        'Role Unclear',
    }


def test_low_sample_and_weak_confidence_degrade_role_label():
    low_sample = build_pitcher_labels(availability=availability(), role=role('setup_bridge', sample_size=1))
    weak_confidence = build_pitcher_labels(availability=availability(), role=role('setup_bridge', confidence='low'))

    assert low_sample['role']['label'] == 'Role Unclear'
    assert low_sample['role']['source'] == 'backend:low_usage_sample'
    assert weak_confidence['role']['label'] == 'Role Unclear'
    assert weak_confidence['role']['source'] == 'backend:weak_role_confidence'


def test_mixed_starter_reliever_role_stays_limited_unless_coverage_signal_is_clear():
    ambiguous_trust = build_pitcher_labels(
        availability=availability(),
        role=role('late_high_leverage', is_starter=True, is_reliever=True),
        eligibility={'status': 'role_ambiguous'},
    )
    ambiguous_coverage = build_pitcher_labels(
        availability=availability(),
        role=role(
            'long_multi_inning',
            is_starter=True,
            is_reliever=True,
            evidence=['5 appearances with bulk multi inning relief coverage'],
        ),
        eligibility={'status': 'role_ambiguous'},
    )

    assert ambiguous_trust['role']['label'] == 'Role Unclear'
    assert ambiguous_trust['role']['source'] == 'backend:mixed_starter_reliever'
    assert ambiguous_coverage['role']['label'] == 'Coverage Arm'
    assert ambiguous_coverage['role']['source'] == 'backend:mixed_coverage:long_multi_inning'


def test_read_labels_map_from_backend_availability_state():
    cases = [
        ('Available', 'Clean Option', 'clean_option'),
        ('Monitor', 'Watch Arm', 'watch_arm'),
        ('Limited', 'Limited Rest', 'rest_restricted'),
        ('Avoid', 'Limited Rest', 'rest_restricted'),
        ('Unavailable', 'Unavailable', 'unavailable'),
    ]

    for status, expected_label, expected_key in cases:
        labels = build_pitcher_labels(availability=availability(status=status), role=role('setup_bridge'))
        assert labels['read']['label'] == expected_label
        assert labels['read']['key'] == expected_key
        assert labels['read']['source'].startswith('backend:')


def test_non_current_data_and_roster_unavailable_degrade_read_label():
    stale = build_pitcher_labels(
        availability=availability(status='Available', data_state='stale', confidence='low'),
        role=role('setup_bridge'),
    )
    roster_unavailable = build_pitcher_labels(
        availability=availability(status='Available'),
        role=role('setup_bridge'),
        roster_status={'status': 'IL_60', 'is_active_mlb': False, 'is_inactive_context': True},
    )

    assert stale['read']['label'] == 'Limited Read'
    assert stale['read']['source'] == 'backend:limited_data'
    assert roster_unavailable['read']['label'] == 'Unavailable'
    assert roster_unavailable['read']['source'] == 'backend:unavailable_status'


def test_mixed_coverage_with_recorded_save_or_hold_events_fails_closed():
    # A clean mixed/coverage profile keeps Coverage Arm; recorded save/hold
    # events on a mixed profile fail closed to Limited Read instead of
    # asserting a concrete role.
    clean = build_pitcher_labels(
        availability=availability(),
        role=role(
            'long_multi_inning',
            role='Long Relief / Multi-Inning Pattern',
            evidence=['6 appearances in the recent window', 'Average recent IP: 2.0'],
        ),
        eligibility={'status': 'role_ambiguous'},
    )
    with_events = build_pitcher_labels(
        availability=availability(),
        role=role(
            'long_multi_inning',
            role='Long Relief / Multi-Inning Pattern',
            evidence=[
                '16 appearances in the recent window',
                'Average recent IP: 1.7',
                '1 save situation finish(es) recorded',
                '1 hold(s) recorded',
            ],
        ),
        eligibility={'status': 'role_ambiguous'},
    )

    assert clean['role']['key'] == 'coverage_arm'
    assert with_events['role']['key'] == 'limited_read'
    assert with_events['role']['source'] == 'backend:mixed_starter_reliever'


# ── VOC-001 public vocabulary contract ──────────────────────────────────────
# The backend owns the reader-facing wording for both pitcher families. These
# pin the exact public sets, so a label can only change by changing this test
# too — which is the point: the wording is a product decision, not an
# implementation detail one file can drift on its own.


def test_public_role_labels_are_exactly_the_canonical_set():
    assert [entry['label'] for entry in ROLE_PUBLIC_LABELS.values()] == [
        'Trusted Arm',
        'Setup Arm',
        'Coverage Arm',
        'Middle Relief Arm',
        'Role Unclear',
    ]


def test_public_read_labels_are_exactly_the_canonical_set():
    assert [entry['label'] for entry in READ_PUBLIC_LABELS.values()] == [
        'Clean Option',
        'Watch Arm',
        'Limited Rest',
        'Unavailable',
        'Limited Read',
    ]


def test_internal_keys_did_not_move_with_the_wording():
    """Only the strings changed. Every engine key is exactly as it was."""
    assert sorted(ROLE_PUBLIC_LABELS) == [
        'bridge_arm', 'coverage_arm', 'depth_arm', 'limited_read', 'trust_arm',
    ]
    assert sorted(READ_PUBLIC_LABELS) == [
        'clean_option', 'limited_read', 'rest_restricted', 'unavailable',
        'watch_arm',
    ]


def test_the_two_families_do_not_share_a_fallback_word():
    """The collision VOC-001 removed.

    Both families key their fallback on ``limited_read``, and both used to
    render it as 'Limited Read'. Two chips on one pitcher card then read
    identically while answering different questions — what kind of arm is this,
    and what does tonight look like for it.
    """
    assert ROLE_PUBLIC_LABELS['limited_read']['label'] == 'Role Unclear'
    assert READ_PUBLIC_LABELS['limited_read']['label'] == 'Limited Read'
    assert (
        ROLE_PUBLIC_LABELS['limited_read']['label']
        != READ_PUBLIC_LABELS['limited_read']['label']
    )


def test_limited_read_is_not_a_public_role_label():
    assert 'Limited Read' not in {
        entry['label'] for entry in ROLE_PUBLIC_LABELS.values()
    }


def test_retired_reader_wording_is_gone_from_both_families():
    published = {
        entry['label']
        for entry in list(ROLE_PUBLIC_LABELS.values()) + list(READ_PUBLIC_LABELS.values())
    }
    for retired in ('Rested', 'Rest-Restricted', 'Trust Arm', 'Bridge Arm', 'Depth Arm'):
        assert retired not in published, retired
