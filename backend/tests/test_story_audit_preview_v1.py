from copy import deepcopy
from datetime import date

import services.story_audit_preview_v1 as audit
from services.story_audit_preview_v1 import (
    CAPABILITY,
    STATE_NEUTRAL,
    STATE_STORY,
    build_story_audit_preview,
)
from services.story_observation_engine import (
    TYPE_CONCENTRATION_PRESSURE,
    TYPE_ROTATION_PRESSURE,
)


def story_payload(**overrides):
    payload = {
        'team_id': 118,
        'team_name': 'Kansas City Royals',
        'team_abbreviation': 'KC',
        'as_of_date': '2026-06-20',
        'state': 'story_available',
        'story_available': True,
        'neutral_reason': None,
        'selected_observation': {
            'type': TYPE_CONCENTRATION_PRESSURE,
            'severity': 'high',
        },
        'written_story': {
            'headline': "Kansas City Royals' bullpen is running through three arms",
            'observation_paragraph': 'The top group has handled 94% of the bullpen workload.',
            'baseline_paragraph': 'The league comparison is 58% for top-three bullpen workload.',
            'cause_paragraph': 'Starter length is down against the two-week mark.',
            'constraint_paragraph': 'If the game shape repeats, the route still runs through the same core.',
        },
        'writer_output': {
            'validation': {
                'passed': True,
                'contains_banned_language': False,
                'contains_robotic_language': False,
                'has_text': True,
            },
        },
        'freshness': {
            'as_of_date': '2026-06-20',
            'data_through': '2026-06-20',
            'data_through_date': '2026-06-20',
            'limitations': [],
        },
        'trust_metadata': {
            'external_generation_used': False,
            'new_metrics_created': False,
            'context_formula_changes': False,
            'availability_changes': False,
            'fatigue_changes': False,
        },
        'limitations': [],
    }
    payload.update(overrides)
    return payload


def neutral_payload(**overrides):
    payload = story_payload()
    payload.update({
        'team_id': 119,
        'team_name': 'Neutral Team',
        'team_abbreviation': 'NT',
        'state': 'neutral',
        'story_available': False,
        'neutral_reason': 'no_story_observations',
        'selected_observation': None,
        'written_story': None,
        'writer_output': None,
        'limitations': ['no_story_observations'],
    })
    payload.update(overrides)
    return payload


def service_payload(teams):
    return {
        'capability': 'story_intelligence_service_v1',
        'as_of_date': '2026-06-20',
        'team_count': len(teams),
        'teams': teams,
        'limitations': ['service_coordinates_existing_deterministic_engines'],
    }


def test_audit_output_includes_multiple_teams_and_clean_neutral_states(monkeypatch):
    teams = [
        story_payload(),
        neutral_payload(),
    ]
    calls = []

    def fake_service(*, team_ids=None, team_contexts=None, as_of_date=None):
        calls.append({
            'team_ids': team_ids,
            'team_contexts': team_contexts,
            'as_of_date': as_of_date,
        })
        return service_payload(teams)

    monkeypatch.setattr(audit, 'build_story_intelligence_service_v1', fake_service)

    result = build_story_audit_preview(team_ids=[118, 119], as_of_date=date(2026, 6, 20))

    assert calls == [{
        'team_ids': [118, 119],
        'team_contexts': None,
        'as_of_date': date(2026, 6, 20),
    }]
    assert result['capability'] == CAPABILITY
    assert result['as_of_date'] == '2026-06-20'
    assert result['team_count'] == 2
    assert result['state_counts'] == {
        STATE_STORY: 1,
        STATE_NEUTRAL: 1,
        'needs_review': 0,
    }
    assert result['story_type_counts'] == {TYPE_CONCENTRATION_PRESSURE: 1}

    story = result['teams'][0]
    assert story['state'] == STATE_STORY
    assert story['story_type'] == TYPE_CONCENTRATION_PRESSURE
    assert story['headline'].startswith('Kansas City Royals')
    assert set(story['sections']) == {
        'headline',
        'observation',
        'baseline',
        'cause',
        'constraint',
    }
    assert story['freshness']['data_through'] == '2026-06-20'
    assert story['trust_metadata']['external_generation_used'] is False

    neutral = result['teams'][1]
    assert neutral['state'] == STATE_NEUTRAL
    assert neutral['story_type'] is None
    assert neutral['headline'] is None
    assert neutral['neutral_reason'] == 'no_story_observations'
    assert neutral['validation_flags']['missing_required_sections'] == []


def test_audit_uses_default_team_ids_when_no_scope_is_supplied(monkeypatch):
    calls = []

    monkeypatch.setattr(audit, '_default_team_ids', lambda limit=None: [118, 119])

    def fake_service(*, team_ids=None, team_contexts=None, as_of_date=None):
        calls.append(team_ids)
        return service_payload([story_payload(), neutral_payload()])

    monkeypatch.setattr(audit, 'build_story_intelligence_service_v1', fake_service)

    result = build_story_audit_preview(limit=2)

    assert calls == [[118, 119]]
    assert result['team_count'] == 2


def test_audit_passes_supplied_contexts_through_service(monkeypatch):
    contexts = [
        {'team_id': 118, 'team': {'team_name': 'Context Team'}},
        {'team_id': 119, 'team': {'team_name': 'Second Context Team'}},
        {'team_id': 120, 'team': {'team_name': 'Trimmed Context Team'}},
    ]
    calls = []

    def fake_service(*, team_ids=None, team_contexts=None, as_of_date=None):
        calls.append(team_contexts)
        return service_payload([
            story_payload(team_id=118, team_name='Context Team'),
            neutral_payload(team_id=119, team_name='Second Context Team'),
        ])

    monkeypatch.setattr(audit, 'build_story_intelligence_service_v1', fake_service)

    result = build_story_audit_preview(team_contexts=contexts, limit=2)

    assert calls == [contexts[:2]]
    assert result['team_count'] == 2


def test_internal_and_banned_language_flags_work(monkeypatch):
    unsafe = story_payload(
        selected_observation={'type': TYPE_ROTATION_PRESSURE},
        written_story={
            'headline': 'Context indicates this bullpen has a ranking problem',
            'observation_paragraph': 'The observation type is leaking into copy.',
            'baseline_paragraph': 'The comparison point is present.',
            'cause_paragraph': 'The cause is present.',
            'constraint_paragraph': 'The constraint is present.',
        },
        writer_output={
            'validation': {
                'passed': False,
                'contains_banned_language': True,
                'contains_robotic_language': True,
                'has_text': True,
            },
        },
    )
    monkeypatch.setattr(
        audit,
        'build_story_intelligence_service_v1',
        lambda **kwargs: service_payload([unsafe]),
    )

    result = build_story_audit_preview(team_ids=[118])
    flags = result['teams'][0]['validation_flags']

    assert result['state_counts']['needs_review'] == 1
    assert result['story_type_counts'] == {TYPE_ROTATION_PRESSURE: 1}
    assert flags['has_internal_terms'] is True
    assert flags['has_banned_language'] is True
    assert flags['needs_review'] is True


def test_missing_and_awkward_story_sections_are_detected(monkeypatch):
    incomplete = story_payload(
        written_story={
            'headline': 'A valid headline is present',
            'observation_paragraph': 'The observation is present.',
            'baseline_paragraph': None,
            'cause_paragraph': '   ',
            'constraint_paragraph': 'N/A',
        },
    )
    monkeypatch.setattr(
        audit,
        'build_story_intelligence_service_v1',
        lambda **kwargs: service_payload([incomplete]),
    )

    result = build_story_audit_preview(team_ids=[118])
    flags = result['teams'][0]['validation_flags']

    assert flags['missing_required_sections'] == ['baseline', 'cause']
    assert flags['awkward_empty_sections'] == ['cause', 'constraint']
    assert flags['needs_review'] is True


def test_audit_does_not_mutate_service_payload(monkeypatch):
    payload = story_payload()
    original = deepcopy(payload)
    monkeypatch.setattr(
        audit,
        'build_story_intelligence_service_v1',
        lambda **kwargs: service_payload([payload]),
    )

    result = build_story_audit_preview(team_ids=[118])

    assert payload == original
    trust = result['teams'][0]['trust_metadata']
    assert trust['new_metrics_created'] is False
    assert trust['context_formula_changes'] is False
    assert trust['availability_changes'] is False
    assert trust['fatigue_changes'] is False
