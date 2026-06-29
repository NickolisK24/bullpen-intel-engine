import json
from datetime import datetime, timezone

import services.four_beat_real_quality_audit as real_audit
from services.four_beat_real_quality_audit import (
    BOUNDED_LIVE_PAYLOAD_SOURCE,
    CAPABILITY,
    PUBLIC_BEATS,
    build_bounded_live_four_beat_real_quality_audit,
    build_four_beat_real_quality_audit,
    write_json_report,
)
from services.story_four_beat_interpreter_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
)


OBSERVED_BOUNDED_LIVE_DB_DISTRIBUTION_AFTER_E1E_2026_06_29 = {
    BEAT_AVAILABILITY_DEPTH: 2,
    BEAT_BRIDGE: 0,
    BEAT_COVERAGE_PRESSURE: 7,
    BEAT_DEPTH_CONSTRAINT: 10,
    BEAT_ROUTE_CHANGE: 11,
    BEAT_SUSTAINABILITY_QUESTION: 0,
    BEAT_TRUST_LANE: 0,
}


def team_payload(
    *,
    team_id=118,
    team_name='Kansas City Royals',
    story_type=BEAT_SUSTAINABILITY_QUESTION,
    state='story',
    flags=None,
    eligible_beats=None,
    sustainability_diagnostics=None,
):
    sections = {
        'headline': f"{team_name}' bullpen has a story",
        'observation': 'The current route is visible.',
        'baseline': 'The comparison point is visible.',
        'cause': 'The cause is visible.',
        'constraint': 'If the game shape repeats, the route still has an operational constraint.',
    }
    return {
        'team_id': team_id,
        'team_name': team_name,
        'team_abbreviation': team_name[:3].upper(),
        'state': state,
        'story_type': story_type if state == 'story' else None,
        'headline': sections['headline'] if state == 'story' else None,
        'sections': sections if state == 'story' else {
            key: None for key in sections
        },
        'validation_flags': flags or {
            'has_internal_terms': False,
            'has_banned_language': False,
            'raw_internal_observation_terms': [],
            'has_raw_object_literal': False,
            'raw_object_terms': [],
            'database_diff_terms': [],
            'missing_forward_constraint_clause': False,
            'missing_required_sections': [],
            'awkward_empty_sections': [],
            'awkward_phrasing': [],
            'needs_review': False,
        },
        'eligible_beats': eligible_beats or [],
        'sustainability_diagnostics': sustainability_diagnostics or {
            'candidate_present': False,
            'selected': story_type == BEAT_SUSTAINABILITY_QUESTION and state == 'story',
            'sustainability_evidence_present': False,
            'suppression_reasons': ['no_sustainability_candidate'],
        },
    }


def audit_preview(teams):
    counts = {}
    for team in teams:
        story_type = team.get('story_type')
        if story_type:
            counts[story_type] = counts.get(story_type, 0) + 1
    return {
        'capability': 'story_intelligence_audit_preview_v1',
        'team_count': len(teams),
        'state_counts': {
            'story': sum(1 for team in teams if team.get('state') == 'story'),
            'neutral': sum(1 for team in teams if team.get('state') == 'neutral'),
            'needs_review': sum(
                1
                for team in teams
                if team.get('validation_flags', {}).get('needs_review')
            ),
        },
        'story_type_counts': counts,
        'teams': teams,
    }


def test_four_beat_quality_audit_summarizes_distribution_and_examples():
    flagged = team_payload(
        team_id=1,
        team_name='Flagged Team',
        story_type=BEAT_ROUTE_CHANGE,
        flags={
            'has_internal_terms': False,
            'has_banned_language': False,
            'raw_internal_observation_terms': ['core_transition'],
            'has_raw_object_literal': True,
            'raw_object_terms': ['player_id'],
            'database_diff_terms': ['core changes'],
            'missing_forward_constraint_clause': True,
            'missing_required_sections': [],
            'awkward_empty_sections': [],
            'awkward_phrasing': [],
            'needs_review': True,
        },
    )
    clean = team_payload(
        team_id=2,
        team_name='Clean Team',
        story_type=BEAT_DEPTH_CONSTRAINT,
    )
    neutral = team_payload(
        team_id=3,
        team_name='Neutral Team',
        state='neutral',
    )

    report = build_four_beat_real_quality_audit(
        audit_preview([flagged, clean, neutral]),
        generated_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        expected_team_count=3,
        initial_audit_summary={'team_count': 3},
        initial_findings=['raw object text leaked into depth stories'],
        fixes_applied=['normalized writer name rendering'],
    )

    assert report['capability'] == CAPABILITY
    assert report['complete_team_count'] is True
    assert report['public_story_types_allowed'] == list(PUBLIC_BEATS)
    assert report['calculation_boundaries']['scoring_changes'] is False
    assert report['calculation_boundaries']['context_layer_formula_changes'] is False
    assert report['initial_audit_summary'] == {'team_count': 3}
    assert report['initial_findings'] == ['raw object text leaked into depth stories']
    assert report['fixes_applied'] == ['normalized writer name rendering']

    summary = report['post_fix_summary']
    assert summary['team_count'] == 3
    assert summary['neutral_count'] == 1
    assert summary['needs_review_count'] == 1
    assert summary['beat_distribution'] == [
        {'story_type': BEAT_ROUTE_CHANGE, 'count': 1, 'share_of_story_states': 50.0},
        {'story_type': BEAT_COVERAGE_PRESSURE, 'count': 0, 'share_of_story_states': 0.0},
        {'story_type': BEAT_DEPTH_CONSTRAINT, 'count': 1, 'share_of_story_states': 50.0},
        {'story_type': BEAT_SUSTAINABILITY_QUESTION, 'count': 0, 'share_of_story_states': 0.0},
        {'story_type': BEAT_AVAILABILITY_DEPTH, 'count': 0, 'share_of_story_states': 0.0},
        {'story_type': BEAT_TRUST_LANE, 'count': 0, 'share_of_story_states': 0.0},
        {'story_type': BEAT_BRIDGE, 'count': 0, 'share_of_story_states': 0.0},
    ]
    assert summary['flagged_issue_counts']['team_flag_counts']['has_raw_object_literal'] == 1
    assert summary['flagged_issue_counts']['term_counts']['database_diff_terms'] == {'core changes': 1}
    assert summary['sustainability_summary']['selected_count'] == 0
    assert report['worst_story_outputs'][0]['team_name'] == 'Flagged Team'
    assert report['strongest_story_outputs'][0]['team_name'] == 'Clean Team'


def test_four_beat_quality_audit_includes_sustainability_selection_audit():
    depth_team = team_payload(
        team_id=1,
        team_name='Depth Team',
        story_type=BEAT_DEPTH_CONSTRAINT,
        eligible_beats=[
            {
                'story_type': BEAT_DEPTH_CONSTRAINT,
                'selection_strength': 9,
                'selected': True,
                'selection_outcome': 'selected',
            },
            {
                'story_type': BEAT_SUSTAINABILITY_QUESTION,
                'selection_strength': 7,
                'selected': False,
                'selection_outcome': 'not_selected_lower_selection_strength',
            },
        ],
        sustainability_diagnostics={
            'candidate_present': True,
            'selected': False,
            'selection_strength': 7,
            'sustainability_evidence_present': True,
            'top_three_workload_share_10d': 88.0,
            'concentration_band': 'narrow',
            'clean_workload_options_count': 1,
            'practical_close_game_paths_count': 2,
            'repeated_route_core_arms': ['First Arm', 'Second Arm'],
            'optionality_band': 'thin',
            'rotation_pressure': {'rotation_ip_trend': 0.1},
            'has_named_arms': True,
            'has_baseline': True,
            'has_cause': True,
            'has_forward_constraint': True,
            'missing_baseline_or_cause': False,
            'suppression_reasons': ['stronger_depth_constraint'],
        },
    )

    report = build_four_beat_real_quality_audit(
        audit_preview([depth_team]),
        expected_team_count=1,
    )

    summary = report['post_fix_summary']['sustainability_summary']
    assert summary['candidate_count'] == 1
    assert summary['evidence_present_count'] == 1
    assert summary['selected_count'] == 0
    assert summary['suppressed_by_reason'] == {'stronger_depth_constraint': 1}
    assert summary['teams_with_sustainability_evidence'][0]['team_name'] == 'Depth Team'

    team_audit = report['team_selection_audit'][0]
    assert team_audit['selected_beat'] == BEAT_DEPTH_CONSTRAINT
    assert team_audit['eligible_beats'][1]['story_type'] == BEAT_SUSTAINABILITY_QUESTION
    assert team_audit['sustainability_diagnostics']['top_three_workload_share_10d'] == 88.0


def test_four_beat_quality_audit_reports_unexpected_public_story_types(tmp_path):
    report = build_four_beat_real_quality_audit(
        audit_preview([
            team_payload(story_type='depth_pressure'),
        ]),
        expected_team_count=1,
    )

    assert report['unexpected_story_type_count'] == 1
    assert report['post_fix_summary']['unexpected_story_types'] == ['depth_pressure']

    output = write_json_report(report, tmp_path / 'audit.json')
    written = json.loads(output.read_text(encoding='utf-8'))

    assert written['capability'] == CAPABILITY
    assert written['unexpected_story_type_count'] == 1


def test_bounded_live_quality_audit_emits_trace_and_diversity_guardrails(monkeypatch):
    distribution = {
        BEAT_AVAILABILITY_DEPTH: 4,
        BEAT_BRIDGE: 4,
        BEAT_COVERAGE_PRESSURE: 5,
        BEAT_DEPTH_CONSTRAINT: 4,
        BEAT_ROUTE_CHANGE: 4,
        BEAT_SUSTAINABILITY_QUESTION: 5,
        BEAT_TRUST_LANE: 4,
    }
    teams = []
    team_id = 100
    for beat, count in distribution.items():
        for _ in range(count):
            team_id += 1
            teams.append(team_payload(
                team_id=team_id,
                team_name=f'Team {team_id}',
                story_type=beat,
                eligible_beats=[{
                    'story_type': beat,
                    'selection_strength': 7,
                    'selection_reasons': ['bounded_live_evidence'],
                    'selected': True,
                }],
            ))

    preview = audit_preview(teams)
    service_payload = {
        'capability': 'story_intelligence_service_v1',
        'as_of_date': '2026-06-29',
        'teams': [],
    }
    canonical_trace = {
        'beat_distribution': {
            'story_count': 30,
            'story_type_counts': distribution,
            'distinct_beat_count': 7,
            'max_beat': BEAT_SUSTAINABILITY_QUESTION,
            'max_beat_count': 5,
            'max_beat_share': 0.167,
            'route_depth_count': 8,
            'route_depth_share': 0.267,
        },
        'missing_beat_evidence_review': {
            BEAT_BRIDGE: {
                'candidate_evidence_team_count': 4,
                'eligible_candidate_team_count': 4,
                'top_candidate_score': 6,
                'selected_team_count': 4,
            },
            BEAT_TRUST_LANE: {
                'candidate_evidence_team_count': 4,
                'eligible_candidate_team_count': 4,
                'top_candidate_score': 7,
                'selected_team_count': 4,
            },
            BEAT_SUSTAINABILITY_QUESTION: {
                'candidate_evidence_team_count': 5,
                'eligible_candidate_team_count': 5,
                'top_candidate_score': 8,
                'selected_team_count': 5,
            },
        },
        'trace': [
            {
                'team': {
                    'team_id': team['team_id'],
                    'team_name': team['team_name'],
                    'team_abbreviation': team['team_abbreviation'],
                },
                'selected_beat': team['story_type'],
                'selection_reasons': ['bounded_live_evidence'],
                'primary_inputs': {'selection_strength': 7},
                'fallback_status': {'fallback_used': False},
            }
            for team in teams
        ],
    }

    monkeypatch.setattr(
        real_audit,
        'build_bounded_live_story_audit_preview',
        lambda **kwargs: {
            'mode': 'bounded_live_current_stored_data',
            'limit': 30,
            'team_ids': [team['team_id'] for team in teams],
            'service_payload': service_payload,
            'audit_preview': preview,
            'limitations': [
                'uses_current_stored_data_only',
                'does_not_start_sync',
                'does_not_change_story_selection',
            ],
        },
    )
    monkeypatch.setattr(
        real_audit,
        'build_story_selection_trace_from_service_payload',
        lambda payload, as_of_date=None: canonical_trace,
    )

    report = build_bounded_live_four_beat_real_quality_audit(
        generated_at=datetime(2026, 6, 29, tzinfo=timezone.utc),
    )

    assert report['payload_source'] == BOUNDED_LIVE_PAYLOAD_SOURCE
    assert report['complete_team_count'] is True
    assert report['unexpected_story_type_count'] == 0

    diagnostic = report['bounded_live_diagnostic']
    assert diagnostic['team_count'] == 30
    assert diagnostic['current_stored_data_only'] is True
    assert diagnostic['sync_like_behavior_started'] is False
    assert diagnostic['audit_preview_story_type_counts'] == distribution
    assert diagnostic['canonical_trace_story_type_counts'] == distribution
    assert diagnostic['matches_canonical_public_trace'] is True
    assert diagnostic['prior_collapse_reproduced'] is False
    assert diagnostic['missing_beat_evidence_review'][BEAT_BRIDGE]['selected_team_count'] == 4
    assert diagnostic['missing_beat_evidence_review'][BEAT_TRUST_LANE]['top_candidate_score'] == 7
    assert diagnostic['beat_distribution']['distinct_beat_count'] == 7
    assert diagnostic['beat_distribution']['route_depth_share'] <= 0.80
    assert len(diagnostic['team_trace']) == 30
    assert diagnostic['team_trace'][0]['headline']
    assert diagnostic['team_trace'][0]['opening']
    assert diagnostic['team_trace'][0]['fallback_status']['fallback_used'] is False
    assert diagnostic['team_trace'][0]['selection_reasons'] == ['bounded_live_evidence']


def test_document_observed_bounded_live_db_after_e1e_meets_diversity_targets():
    counts = OBSERVED_BOUNDED_LIVE_DB_DISTRIBUTION_AFTER_E1E_2026_06_29
    story_count = sum(counts.values())
    max_count = max(counts.values())
    route_depth_count = counts[BEAT_ROUTE_CHANGE] + counts[BEAT_DEPTH_CONSTRAINT]

    assert story_count == 30
    assert sum(1 for count in counts.values() if count > 0) >= 3
    assert max_count / story_count < 0.70
    assert route_depth_count / story_count <= 0.80
    assert counts[BEAT_DEPTH_CONSTRAINT] < 25
