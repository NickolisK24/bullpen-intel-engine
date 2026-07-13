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
