import json
import re

from services.editorial_voice_contract_v1 import contains_editorial_banned_language
from services.what_changed_since_yesterday import (
    REASON_COMPARISON_WITHHELD,
    REASON_PRIOR_SLATE_COVERAGE_MISSING,
    REASON_SNAPSHOTS_NOT_COMPARABLE,
    STATE_CHANGES_DETECTED,
    STATE_INSUFFICIENT_CONTEXT,
    STATE_NO_MEANINGFUL_CHANGES,
)
from services.what_changed_since_yesterday_public import (
    CAPABILITY,
    DEFAULT_PUBLIC_ITEM_LIMIT,
    LANE_MORE_BREATHING_ROOM,
    LANE_OTHER_MEANINGFUL,
    LANE_STRUCTURE_CHANGED,
    LANE_TIGHTER_TODAY,
    _movement_lane,
    _primary_delta,
    build_what_changed_public_payload,
)


def snapshot(
    *,
    team_id=1,
    team_name='Test Team',
    team_abbreviation='TST',
    capacity_state='reduced',
    resource_state='moderate',
    active=7,
    clean=4,
    trusted_group=4,
    coverage_label='Stable Coverage Safety',
    identity_key='flexible_distribution',
    identity_label='Flexible Distribution Bullpen',
):
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_abbreviation,
        'resource_health': {
            'confidence': 'high',
            'capacity_state': capacity_state,
            'resource_health_state': resource_state,
            'bullpen_capacity': {
                'capacity_state': capacity_state,
                'active_reliever_count': active,
                'clean_active_reliever_count': clean,
            },
            'organizational_resource_health': {
                'resource_health_state': resource_state,
            },
        },
        'trust_hierarchy': {
            'anchor_count': 1,
            'leverage_count': 2,
            'trusted_count': 1,
            'depth_count': 1,
            'trusted_group_size': trusted_group,
            'hierarchy_confidence': 'high',
        },
        'coverage_safety': {
            'label': coverage_label,
        },
        'bullpen_identity': {
            'identity_key': identity_key,
            'identity_label': identity_label,
            'confidence': 'medium',
        },
    }


def slate_coverage(
    slate_date,
    *,
    complete=True,
    coverage_known=True,
    validations_passed=True,
):
    return {
        'slate_date': slate_date,
        'coverage_known': coverage_known,
        'games_scheduled': 1,
        'games_final': 1,
        'games_fully_ingested': 1 if complete else 0,
        'games_incomplete': 0 if complete else 1,
        'complete_enough_to_publish': complete,
        'validations_passed': validations_passed,
        'reason_codes': ['slate_complete'] if complete and validations_passed else ['slate_incomplete'],
    }


def payload(
    items,
    *,
    data_through='2026-06-19',
    workload=None,
    include_slate_coverage=False,
):
    freshness = {
        'data_through': data_through,
        'availability_reference_date': data_through,
    }
    if include_slate_coverage:
        freshness['slate_coverage'] = slate_coverage(data_through)
    result = {
        'freshness': freshness,
        'capacity_intelligence': {
            'teams': items,
            'by_team_id': {str(item['team_id']): item for item in items},
        },
    }
    if workload is not None:
        result['what_changed_workload'] = workload
    return result


def build_public(current_items, prior_items=None, *, workload=None, **kwargs):
    return build_what_changed_public_payload(
        payload(current_items, data_through='2026-06-19', workload=workload),
        payload(prior_items, data_through='2026-06-18') if prior_items is not None else None,
        **kwargs,
    )


def test_public_payload_includes_only_frontend_safe_copy_items():
    current = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=5),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=4),
    ]
    prior = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
        snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=4),
    ]

    result = build_public(
        current,
        prior,
        workload={
            'by_team_id': {
                '1': {
                    'workload_added': [
                        {'pitcher_id': 10, 'name': 'Reynaldo Lopez', 'pitches': 28},
                        {'pitcher_id': 11, 'name': 'Dylan Dodd', 'pitches': 24},
                        {'pitcher_id': 12, 'name': 'James Karinchak', 'pitches': 19},
                    ],
                },
            },
        },
    )

    assert result['capability'] == CAPABILITY
    assert result['state'] == STATE_CHANGES_DETECTED
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False
    assert result['comparison']['comparison_available'] is True
    assert result['item_count'] == 1
    assert set(result) == {
        'capability',
        'source',
        'state',
        'ranking_applied',
        'selection_made',
        'prediction_applied',
        'ordering_basis',
        'item_limit',
        'comparison',
        'items',
        'item_count',
        'limitations',
        'reason_codes',
        'summary',
    }
    assert set(result['comparison']) == {
        'current_data_through',
        'previous_data_through',
        'comparison_available',
        'reason_codes',
    }
    assert result['items'] == [
        {
            'key': 'AAA-what-changed',
            'team_id': 1,
            'team_name': 'Alpha Club',
            'team_abbreviation': 'AAA',
            'movement_lane': 'more_breathing_room',
            'movement_label': 'More breathing room',
            'primary_delta': {
                'label': 'Rested relievers',
                'previous': 2,
                'current': 5,
                'net_delta': 3,
            },
            'public_headline': 'The Alpha Club bullpen has more rested arms for a close game.',
            'public_summary': (
                'The Alpha Club bullpen has more close-game room because the rested side gained '
                'three rested arms. That helps bridge the middle innings.'
            ),
            'public_context': (
                'Three relievers took on meaningful workload yesterday because the bullpen still has '
                'more breathing room than before. That gives the staff more ways to cover tonight.'
            ),
            'yesterday_rested_count': 2,
            'today_rested_count': 5,
            'workload_added': [
                {'pitcher_id': 10, 'name': 'Reynaldo Lopez', 'pitches': 28},
                {'pitcher_id': 11, 'name': 'Dylan Dodd', 'pitches': 24},
                {'pitcher_id': 12, 'name': 'James Karinchak', 'pitches': 19},
            ],
        }
    ]


def test_public_payload_uses_plain_baseball_why_it_matters_copy():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
    )
    item = result['items'][0]

    assert item['public_context']
    assert 'breathing room' in item['public_context']
    assert 'tonight' in item['public_context']
    encoded = json.dumps(item).lower()
    for forbidden in (
        'consequence_type',
        'confidence',
        'significance',
        'supporting_facts',
        'raw_score',
        'score',
        'identity_label',
        'identity_key',
        'coverage',
        'cleaner paths',
        'moved from',
        'rested options',
    ):
        assert forbidden not in encoded


def test_public_payload_renders_worsening_movement_as_baseball_consequence():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)],
    )
    item = result['items'][0]
    text = ' '.join([
        item['public_headline'],
        item['public_summary'],
        item['public_context'],
    ]).lower()

    assert 'late-inning cushion' in text
    assert 'middle innings' in text or 'bridge' in text
    assert 'from 5 to 2' not in text
    assert 'fewer rested' not in text


def test_public_payload_does_not_emit_healthier_copy_when_visible_counts_tighten():
    result = build_public(
        [
            snapshot(
                team_name='Boston Red Sox',
                team_abbreviation='BOS',
                clean=2,
                resource_state='moderate',
                capacity_state='thin',
            ),
        ],
        [
            snapshot(
                team_name='Boston Red Sox',
                team_abbreviation='BOS',
                clean=3,
                resource_state='strained',
                capacity_state='thin',
            ),
        ],
        workload={
            'by_team_id': {
                '1': {
                    'workload_added': [
                        {'pitcher_id': 81, 'name': 'Danny Coulombe', 'pitches': 37},
                        {'pitcher_id': 90, 'name': 'Jovani Moran', 'pitches': 25},
                        {'pitcher_id': 91, 'name': 'Justin Slaten', 'pitches': 17},
                    ],
                },
            },
        },
    )
    item = result['items'][0]
    text = ' '.join([
        item['public_headline'],
        item['public_summary'],
        item['public_context'],
    ]).lower()

    assert item['yesterday_rested_count'] == 3
    assert item['today_rested_count'] == 2
    assert item['workload_added'] == [
        {'pitcher_id': 81, 'name': 'Danny Coulombe', 'pitches': 37},
        {'pitcher_id': 90, 'name': 'Jovani Moran', 'pitches': 25},
        {'pitcher_id': 91, 'name': 'Justin Slaten', 'pitches': 17},
    ]
    assert 'healthier' not in text
    assert 'more breathing room' not in text
    assert 'more ways to cover' not in text
    assert 'thinner' in text
    assert 'middle innings' in text
    assert item['public_evidence'] == [
        {
            'label': 'Resource pool',
            'yesterday': 'tight',
            'today': 'less tight',
        },
    ]


def test_public_payload_exposes_broader_non_rested_evidence_when_copy_uses_it():
    result = build_public(
        [
            snapshot(
                team_name='Milwaukee Brewers',
                team_abbreviation='MIL',
                active=9,
                clean=3,
                resource_state='strained',
                capacity_state='reduced',
            ),
        ],
        [
            snapshot(
                team_name='Milwaukee Brewers',
                team_abbreviation='MIL',
                active=7,
                clean=3,
                resource_state='strained',
                capacity_state='reduced',
            ),
        ],
        workload={
            'by_team_id': {
                '1': {
                    'workload_added': [
                        {'pitcher_id': 738, 'name': 'Craig Yoho', 'pitches': 25},
                    ],
                },
            },
        },
    )
    item = result['items'][0]

    assert item['yesterday_rested_count'] == 3
    assert item['today_rested_count'] == 3
    assert 'more full-game coverage' in item['public_summary']
    assert item['public_evidence'] == [
        {
            'label': 'Full-game routes',
            'yesterday': 7,
            'today': 9,
        },
    ]


def test_public_payload_zero_count_prose_protection_and_banned_scan():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=3)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=0)],
    )
    item = result['items'][0]
    public_text = ' '.join([
        item['public_headline'],
        item['public_summary'],
        item['public_context'],
    ])

    assert not re.search(r'(?<![\w-])0(?![\w-])', public_text)
    assert not contains_editorial_banned_language(public_text)
    assert 'moved from' not in public_text.lower()
    assert 'practical path' not in public_text.lower()


def test_public_payload_preserves_structured_fields_after_voice_migration():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
    )
    item = result['items'][0]

    assert set(item) == {
        'key',
        'team_id',
        'team_name',
        'team_abbreviation',
        'movement_lane',
        'movement_label',
        'primary_delta',
        'public_headline',
        'public_summary',
        'public_context',
        'yesterday_rested_count',
        'today_rested_count',
        'workload_added',
    }
    assert item['yesterday_rested_count'] == 2
    assert item['today_rested_count'] == 5
    assert item['workload_added'] == []


def test_public_payload_sorts_and_limits_workload_added_pitchers():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)],
        workload={
            'by_team_id': {
                '1': {
                    'workload_added': [
                        {'pitcher_id': 10, 'name': 'Third Arm', 'pitches': 19},
                        {'pitcher_id': 11, 'name': 'First Arm', 'pitches': 31},
                        {'pitcher_id': 12, 'name': 'Fourth Arm', 'pitches': 17},
                        {'pitcher_id': 13, 'name': 'Second Arm', 'pitches': 24},
                    ],
                },
            },
        },
    )

    assert result['items'][0]['workload_added'] == [
        {'pitcher_id': 11, 'name': 'First Arm', 'pitches': 31},
        {'pitcher_id': 13, 'name': 'Second Arm', 'pitches': 24},
        {'pitcher_id': 10, 'name': 'Third Arm', 'pitches': 19},
    ]


def test_public_payload_preserves_card_without_consequence_context_when_absent_or_unsafe():
    current = [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)]
    prior = [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)]
    no_consequence = build_public(
        current,
        prior,
        consequence_payload={
            'teams': [
                {
                    'team_id': 1,
                    'team_name': 'Alpha Club',
                    'team_abbreviation': 'AAA',
                    'status': 'available',
                    'state': 'no_consequences',
                    'consequence_count': 0,
                    'consequences': [],
                }
            ],
        },
    )
    unsafe_consequence = build_public(
        current,
        prior,
        consequence_payload={
            'teams': [
                {
                    'team_id': 1,
                    'team_name': 'Alpha Club',
                    'team_abbreviation': 'AAA',
                    'status': 'available',
                    'state': 'consequences_detected',
                    'consequence_count': 1,
                    'consequences': [
                        {
                            'consequence_type': 'unsafe_test_consequence',
                            'consequence_summary': 'Unsafe test.',
                            'consequence_context': 'The manager should use the closer.',
                            'significance': 'meaningful',
                            'confidence': 'medium',
                            'supporting_facts': [
                                {
                                    'fact_key': 'rested_options',
                                    'previous_value': 2,
                                    'current_value': 5,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )
    flagged_consequence = build_public(
        current,
        prior,
        consequence_payload={
            'teams': [
                {
                    'team_id': 1,
                    'team_name': 'Alpha Club',
                    'team_abbreviation': 'AAA',
                    'status': 'available',
                    'state': 'consequences_detected',
                    'review_flags': ['prediction_language'],
                    'consequence_count': 1,
                    'consequences': [
                        {
                            'consequence_type': 'more_flexibility',
                            'consequence_summary': 'The bullpen has more flexibility than yesterday.',
                            'consequence_context': (
                                'The Alpha Club bullpen is less boxed into one narrow route than it was yesterday.'
                            ),
                            'significance': 'meaningful',
                            'confidence': 'medium',
                            'supporting_facts': [
                                {
                                    'fact_key': 'rested_options',
                                    'previous_value': 2,
                                    'current_value': 5,
                                }
                            ],
                        }
                    ],
                }
            ],
        },
    )

    assert no_consequence['item_count'] == 1
    assert 'breathing room' in no_consequence['items'][0]['public_context']
    assert unsafe_consequence['item_count'] == 1
    assert 'breathing room' in unsafe_consequence['items'][0]['public_context']
    assert flagged_consequence['item_count'] == 1
    assert 'breathing room' in flagged_consequence['items'][0]['public_context']
    assert 'should use' not in json.dumps(unsafe_consequence['items']).lower()


def test_public_payload_skips_no_prior_no_change_and_tiny_flagged_changes():
    no_prior = build_public([snapshot(clean=5)], None)
    no_change = build_public([snapshot(clean=5)], [snapshot(clean=5)])
    tiny_only = build_public(
        [snapshot(capacity_state='reduced', clean=5)],
        [snapshot(capacity_state='thin', clean=4)],
    )

    assert no_prior['items'] == []
    assert no_prior['state'] == STATE_INSUFFICIENT_CONTEXT
    assert no_prior['comparison']['comparison_available'] is False
    assert 'status' not in no_prior
    assert 'state' not in no_prior['comparison']
    assert 'empty_state' not in no_prior
    assert no_change['items'] == []
    assert no_change['state'] == STATE_NO_MEANINGFUL_CHANGES
    assert no_change['comparison'] == {
        'current_data_through': '2026-06-19',
        'previous_data_through': '2026-06-18',
        'comparison_available': True,
        'reason_codes': [],
    }
    assert no_change['item_count'] == 0
    assert 'status' not in no_change
    assert 'state' not in no_change['comparison']
    assert 'empty_state' not in no_change
    assert tiny_only['items'] == []
    assert tiny_only['state'] == STATE_NO_MEANINGFUL_CHANGES


def test_public_payload_withheld_trusted_gate_returns_no_comparison_metadata():
    result = build_what_changed_public_payload(
        payload(
            [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)],
            data_through='2026-06-19',
            include_slate_coverage=True,
        ),
        payload(
            [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
            data_through='2026-06-18',
            include_slate_coverage=False,
        ),
        require_trusted_snapshots=True,
        current_snapshot_metadata={
            'source': 'live_dashboard_build',
            'trusted_current_payload': True,
            'data_through': '2026-06-19',
        },
        prior_snapshot_metadata={
            'source': 'dashboard_snapshot',
            'snapshot_id': 18,
            'status': 'ready',
            'is_published': True,
            'data_through': '2026-06-18',
        },
    )
    encoded = json.dumps(result).lower()

    assert result['state'] == STATE_INSUFFICIENT_CONTEXT
    assert result['comparison']['comparison_available'] is False
    assert result['item_count'] == 0
    assert result['items'] == []
    assert 'status' not in result
    assert 'state' not in result['comparison']
    assert 'empty_state' not in result
    assert result['prediction_applied'] is False
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert REASON_COMPARISON_WITHHELD in result['reason_codes']
    assert REASON_PRIOR_SLATE_COVERAGE_MISSING in result['comparison']['reason_codes']
    assert 'no meaningful bullpen movement' not in encoded
    assert 'no changes' not in encoded


def test_public_payload_enforces_cap_without_ranking_language():
    current = [
        snapshot(
            team_id=idx,
            team_name=f'Team {idx}',
            team_abbreviation=f'T{idx}',
            active=12,
            clean=idx + 4,
        )
        for idx in range(1, 10)
    ]
    prior = [
        snapshot(
            team_id=idx,
            team_name=f'Team {idx}',
            team_abbreviation=f'T{idx}',
            active=12,
            clean=idx,
        )
        for idx in range(1, 10)
    ]

    result = build_public(current, prior, limit=DEFAULT_PUBLIC_ITEM_LIMIT)

    assert len(result['items']) == DEFAULT_PUBLIC_ITEM_LIMIT
    assert [item['team_abbreviation'] for item in result['items']] == [
        'T1',
        'T2',
        'T3',
        'T4',
        'T5',
        'T6',
    ]
    assert result['ordering_basis'] == 'team_abbreviation_then_team_name'


def test_public_payload_skips_items_with_repeated_public_copy_flags():
    current = [
        snapshot(
            team_id=1,
            team_name='Alpha Club',
            team_abbreviation='AAA',
            identity_key='depth_driven',
            identity_label='Depth-Driven Bullpen',
        ),
        snapshot(
            team_id=2,
            team_name='Beta Club',
            team_abbreviation='BBB',
            identity_key='depth_driven',
            identity_label='Depth-Driven Bullpen',
        ),
    ]
    prior = [
        snapshot(
            team_id=1,
            team_name='Alpha Club',
            team_abbreviation='AAA',
            identity_key='flexible_distribution',
            identity_label='Flexible Distribution Bullpen',
        ),
        snapshot(
            team_id=2,
            team_name='Beta Club',
            team_abbreviation='BBB',
            identity_key='flexible_distribution',
            identity_label='Flexible Distribution Bullpen',
        ),
    ]

    result = build_public(current, prior)

    assert result['items'] == []


def test_public_payload_does_not_leak_internal_keys_scores_confidence_or_identity_labels():
    result = build_public(
        [
            snapshot(
                team_name='Alpha Club',
                team_abbreviation='AAA',
                identity_key='resource_strained',
                identity_label='Resource-Strained Bullpen',
            )
        ],
        [
            snapshot(
                team_name='Alpha Club',
                team_abbreviation='AAA',
                identity_key='flexible_distribution',
                identity_label='Flexible Distribution Bullpen',
            )
        ],
    )

    encoded_items = json.dumps(result['items']).lower()
    for forbidden in (
        'change_type',
        'change_direction',
        'consequence_type',
        'confidence',
        'significance',
        'supporting_facts',
        'copy_review_flags',
        'public_copy_generated',
        'identity_label',
        'flexible distribution bullpen',
        'resource-strained bullpen',
        'raw_score',
        'score',
        'recommend',
        'prediction',
        'ranking',
        'best reliever',
    ):
        assert forbidden not in encoded_items


def _trusted_metadata_pair(current_through, prior_through):
    return {
        'current_snapshot_metadata': {
            'source': 'live_dashboard_build',
            'trusted_current_payload': True,
            'data_through': current_through,
        },
        'prior_snapshot_metadata': {
            'source': 'dashboard_snapshot',
            'snapshot_id': 21,
            'status': 'ready',
            'is_published': True,
            'data_through': prior_through,
        },
    }


def test_non_adjacent_views_withhold_then_adjacent_pair_recovers_automatically():
    """
    An off-day gap (non-adjacent data-through dates) is withheld with the
    specific reason code; the very next adjacent pair compares again with no
    manual cleanup — the recovery is purely data-driven.
    """
    current = [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)]
    prior = [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)]

    # League off-day gap: 2026-06-15 -> 2026-06-19 are not adjacent days.
    gapped = build_what_changed_public_payload(
        payload(current, data_through='2026-06-19', include_slate_coverage=True),
        payload(prior, data_through='2026-06-15', include_slate_coverage=True),
        require_trusted_snapshots=True,
        **_trusted_metadata_pair('2026-06-19', '2026-06-15'),
    )
    assert gapped['state'] == STATE_INSUFFICIENT_CONTEXT
    assert gapped['comparison']['comparison_available'] is False
    assert REASON_SNAPSHOTS_NOT_COMPARABLE in gapped['comparison']['reason_codes']
    assert REASON_COMPARISON_WITHHELD in gapped['comparison']['reason_codes']
    assert gapped['items'] == []

    # Next comparable game-day pair: adjacent dates, same trust inputs.
    recovered = build_what_changed_public_payload(
        payload(current, data_through='2026-06-19', include_slate_coverage=True),
        payload(prior, data_through='2026-06-18', include_slate_coverage=True),
        require_trusted_snapshots=True,
        **_trusted_metadata_pair('2026-06-19', '2026-06-18'),
    )
    assert recovered['comparison']['comparison_available'] is True
    assert recovered['comparison']['reason_codes'] == []
    assert recovered['state'] in (STATE_CHANGES_DETECTED, STATE_NO_MEANINGFUL_CHANGES)


def test_public_payload_trusts_rotated_prior_after_repeated_same_date_publish():
    """Production scenario: repeated same-date syncs rotate the prior day's
    snapshot to is_published False, but its durable publication proof keeps the
    public comparison available."""
    current = [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)]
    prior = [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)]

    result = build_what_changed_public_payload(
        payload(current, data_through='2026-06-19', include_slate_coverage=True),
        payload(prior, data_through='2026-06-18', include_slate_coverage=True),
        require_trusted_snapshots=True,
        current_snapshot_metadata={
            'source': 'live_dashboard_build',
            'trusted_current_payload': True,
            'data_through': '2026-06-19',
        },
        prior_snapshot_metadata={
            'source': 'dashboard_snapshot',
            'snapshot_id': 18,
            'status': 'ready',
            # Rotated out of the served slot, but publication is proven.
            'is_published': False,
            'was_published': True,
            'published_at': '2026-06-18T09:15:00',
            'data_through': '2026-06-18',
        },
    )

    assert result['comparison']['comparison_available'] is True
    assert result['comparison']['reason_codes'] == []
    assert result['state'] in (STATE_CHANGES_DETECTED, STATE_NO_MEANINGFUL_CHANGES)


# ---------------------------------------------------------------------------
# Daily-briefing movement lanes, primary deltas, and league summary counts.
# ---------------------------------------------------------------------------

_ALL_LANES = {
    LANE_MORE_BREATHING_ROOM,
    LANE_TIGHTER_TODAY,
    LANE_STRUCTURE_CHANGED,
    LANE_OTHER_MEANINGFUL,
}


def _structure_snapshot(trusted_group, **kwargs):
    # Only the trusted-group size moves, so the trusted-group change is the top
    # change and the team lands in the structure lane.
    return snapshot(
        clean=4,
        active=7,
        resource_state='moderate',
        coverage_label='Stable Coverage Safety',
        trusted_group=trusted_group,
        **kwargs,
    )


def test_every_published_item_carries_exactly_one_valid_movement_lane():
    result = build_public(
        [
            snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=6),
            snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=1),
        ],
        [
            snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
            snapshot(team_id=2, team_name='Beta Club', team_abbreviation='BBB', clean=6),
        ],
    )

    assert result['items']
    for item in result['items']:
        assert item['movement_lane'] in _ALL_LANES
        # Exactly one lane, and the human label matches that single lane.
        assert isinstance(item['movement_lane'], str)
        assert isinstance(item['movement_label'], str)


def test_rested_increase_lands_in_more_breathing_room_lane():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=6)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
    )
    item = result['items'][0]

    assert item['movement_lane'] == LANE_MORE_BREATHING_ROOM
    assert item['movement_label'] == 'More breathing room'


def test_rested_decrease_lands_in_tighter_today_lane():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=6)],
    )
    item = result['items'][0]

    assert item['movement_lane'] == LANE_TIGHTER_TODAY
    assert item['movement_label'] == 'Tighter today'


def test_trusted_group_movement_lands_in_structure_lane():
    result = build_public(
        [_structure_snapshot(5, team_name='Alpha Club', team_abbreviation='AAA')],
        [_structure_snapshot(2, team_name='Alpha Club', team_abbreviation='AAA')],
    )
    item = result['items'][0]

    assert item['movement_lane'] == LANE_STRUCTURE_CHANGED
    assert item['movement_label'] == 'Structure changed'


def test_movement_lane_fails_closed_to_neutral_for_unknown_direction():
    # A meaningful-but-unclassifiable change must not be forced into a room
    # lane; it falls into the neutral "other" lane instead of being dropped.
    neutral = _movement_lane(
        {'change_type': 'some_future_change', 'change_direction': 'shifted'},
        {'yesterday_rested_count': None, 'today_rested_count': None},
    )
    assert neutral == LANE_OTHER_MEANINGFUL


def test_primary_delta_for_rested_carries_signed_net_delta():
    up = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=6)],
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=2)],
    )['items'][0]['primary_delta']
    down = build_public(
        [snapshot(team_name='Beta Club', team_abbreviation='BBB', clean=2)],
        [snapshot(team_name='Beta Club', team_abbreviation='BBB', clean=6)],
    )['items'][0]['primary_delta']

    assert up == {'label': 'Rested relievers', 'previous': 2, 'current': 6, 'net_delta': 4}
    assert down == {'label': 'Rested relievers', 'previous': 6, 'current': 2, 'net_delta': -4}


def test_primary_delta_for_structure_change_has_no_net_delta():
    item = build_public(
        [_structure_snapshot(5, team_name='Alpha Club', team_abbreviation='AAA')],
        [_structure_snapshot(2, team_name='Alpha Club', team_abbreviation='AAA')],
    )['items'][0]
    delta = item['primary_delta']

    assert delta is not None
    assert delta['net_delta'] is None
    assert delta['previous'] is not None and delta['current'] is not None


def test_primary_delta_omits_net_when_one_side_unknown():
    # Directly exercise the fail-closed guard: a missing side yields no delta.
    assert _primary_delta(
        {'change_type': 'rested_options_changed'},
        {'yesterday_rested_count': 3, 'today_rested_count': None},
        None,
        use_count_aligned=False,
    ) is None


def test_summary_counts_use_full_population_before_display_limit():
    current = [
        snapshot(team_id=i, team_name=f'Team {i}', team_abbreviation=f'T{i}', clean=6)
        for i in range(1, 9)
    ]
    prior = [
        snapshot(team_id=i, team_name=f'Team {i}', team_abbreviation=f'T{i}', clean=1)
        for i in range(1, 9)
    ]

    result = build_public(current, prior, limit=3)

    # Only three cards are shown, but the league count reflects all eight.
    assert result['item_count'] == 3
    assert result['summary']['more_breathing_room_count'] == 8
    assert result['summary']['meaningful_change_count'] == 8


def test_summary_lane_counts_split_direction_and_structure():
    current = [
        snapshot(team_id=1, team_name='Up Club', team_abbreviation='UPC', clean=6),
        snapshot(team_id=2, team_name='Down Club', team_abbreviation='DNC', clean=1),
        _structure_snapshot(5, team_id=3, team_name='Shape Club', team_abbreviation='SHC'),
    ]
    prior = [
        snapshot(team_id=1, team_name='Up Club', team_abbreviation='UPC', clean=2),
        snapshot(team_id=2, team_name='Down Club', team_abbreviation='DNC', clean=6),
        _structure_snapshot(2, team_id=3, team_name='Shape Club', team_abbreviation='SHC'),
    ]

    summary = build_public(current, prior)['summary']

    assert summary['more_breathing_room_count'] == 1
    assert summary['tighter_today_count'] == 1
    assert summary['structure_changed_count'] == 1
    assert summary['meaningful_change_count'] == 3


def test_summary_reports_proven_steady_teams_when_population_complete():
    current = [
        snapshot(team_id=1, team_name='Moved Club', team_abbreviation='MVC', clean=6),
        snapshot(team_id=2, team_name='Steady Club', team_abbreviation='STC', clean=4),
    ]
    prior = [
        snapshot(team_id=1, team_name='Moved Club', team_abbreviation='MVC', clean=2),
        snapshot(team_id=2, team_name='Steady Club', team_abbreviation='STC', clean=4),
    ]

    summary = build_public(current, prior)['summary']

    assert summary['counts_complete'] is True
    assert summary['steady_count'] == 1
    assert summary['steady_teams'] == [
        {'team_id': 2, 'team_name': 'Steady Club', 'team_abbreviation': 'STC'},
    ]


def test_summary_withholds_steady_count_and_never_counts_uncompared_team_as_steady():
    # Beta has no prior counterpart -> comparison unavailable for it. It must
    # not be counted as steady, and the incomplete population withholds the
    # steady count entirely.
    current = [
        snapshot(team_id=1, team_name='Moved Club', team_abbreviation='MVC', clean=6),
        snapshot(team_id=2, team_name='Orphan Club', team_abbreviation='ORC', clean=4),
    ]
    prior = [
        snapshot(team_id=1, team_name='Moved Club', team_abbreviation='MVC', clean=2),
    ]

    summary = build_public(current, prior)['summary']

    assert summary['counts_complete'] is False
    assert 'steady_count' not in summary
    assert 'steady_teams' not in summary
    assert summary['meaningful_change_count'] == 1


def test_summary_absent_when_comparison_unavailable():
    result = build_public(
        [snapshot(team_name='Alpha Club', team_abbreviation='AAA', clean=5)],
        None,
    )

    assert result['state'] == STATE_INSUFFICIENT_CONTEXT
    assert 'summary' not in result


def test_items_stay_alphabetical_and_are_not_ranked_by_delta_magnitude():
    # Bravo has the larger delta but must not jump ahead of Alpha.
    current = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=4),
        snapshot(team_id=2, team_name='Bravo Club', team_abbreviation='BBB', clean=8),
    ]
    prior = [
        snapshot(team_id=1, team_name='Alpha Club', team_abbreviation='AAA', clean=2),
        snapshot(team_id=2, team_name='Bravo Club', team_abbreviation='BBB', clean=1),
    ]

    result = build_public(current, prior)

    assert [item['team_abbreviation'] for item in result['items']] == ['AAA', 'BBB']
    assert result['ranking_applied'] is False
    assert result['selection_made'] is False
    assert result['prediction_applied'] is False


def test_movement_lane_labels_pass_the_editorial_banned_language_scan():
    for label in ('More breathing room', 'Tighter today', 'Structure changed', 'Other meaningful change'):
        assert not contains_editorial_banned_language(label)


def test_summary_and_lane_fields_do_not_leak_internal_terminology():
    result = build_public(
        [_structure_snapshot(5, team_name='Alpha Club', team_abbreviation='AAA')],
        [_structure_snapshot(2, team_name='Alpha Club', team_abbreviation='AAA')],
    )
    encoded = json.dumps({'summary': result.get('summary'), 'items': result['items']}).lower()
    for forbidden in (
        'change_type',
        'change_direction',
        'confidence',
        'significance',
        'supporting_facts',
        'raw_score',
        'score',
        'coverage',
        'rested options',
        'ranking',
        'prediction',
        'identity_label',
    ):
        assert forbidden not in encoded
