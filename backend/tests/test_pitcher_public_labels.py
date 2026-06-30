from services.pitcher_public_labels import build_pitcher_labels


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


def test_role_keys_map_to_backend_public_labels():
    cases = [
        ('late_high_leverage', 'Trust Arm', 'trust_arm'),
        ('setup_bridge', 'Bridge Arm', 'bridge_arm'),
        ('long_multi_inning', 'Coverage Arm', 'coverage_arm'),
        ('depth', 'Depth Arm', 'depth_arm'),
        ('insufficient_data', 'Limited Read', 'limited_read'),
    ]

    for role_key, expected_label, expected_key in cases:
        labels = build_pitcher_labels(availability=availability(), role=role(role_key))
        assert labels['role']['label'] == expected_label
        assert labels['role']['key'] == expected_key
        assert labels['role']['source'].startswith('backend:')


def test_low_sample_and_weak_confidence_degrade_role_label():
    low_sample = build_pitcher_labels(availability=availability(), role=role('setup_bridge', sample_size=1))
    weak_confidence = build_pitcher_labels(availability=availability(), role=role('setup_bridge', confidence='low'))

    assert low_sample['role']['label'] == 'Limited Read'
    assert low_sample['role']['source'] == 'backend:low_usage_sample'
    assert weak_confidence['role']['label'] == 'Limited Read'
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

    assert ambiguous_trust['role']['label'] == 'Limited Read'
    assert ambiguous_trust['role']['source'] == 'backend:mixed_starter_reliever'
    assert ambiguous_coverage['role']['label'] == 'Coverage Arm'
    assert ambiguous_coverage['role']['source'] == 'backend:mixed_coverage:long_multi_inning'


def test_read_labels_map_from_backend_availability_state():
    cases = [
        ('Available', 'Rested', 'clean_option'),
        ('Monitor', 'Watch Arm', 'watch_arm'),
        ('Limited', 'Rest-Restricted', 'rest_restricted'),
        ('Avoid', 'Rest-Restricted', 'rest_restricted'),
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
