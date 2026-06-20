"""Observation discovery for backend-authored team stories."""

from __future__ import annotations

from typing import Any


CAPABILITY = 'observation_discovery_engine_v1'
VERSION = '2026-06-19'

MIN_INTERESTING_SCORE = 55.0

OBSERVATION_WORKLOAD_CONCENTRATION = 'workload_concentration'
OBSERVATION_RESOURCE_CONSTRAINT = 'resource_constraint'
OBSERVATION_FLEXIBILITY = 'flexibility'
OBSERVATION_TRUST_SHAPE = 'trust_shape'
OBSERVATION_RUN_PREVENTION_STRESS = 'run_prevention_stress'
OBSERVATION_IDENTITY = 'identity'
OBSERVATION_CHANGE = 'change'

OBSERVATION_TYPE_ORDER = {
    OBSERVATION_WORKLOAD_CONCENTRATION: 0,
    OBSERVATION_RESOURCE_CONSTRAINT: 1,
    OBSERVATION_FLEXIBILITY: 2,
    OBSERVATION_TRUST_SHAPE: 3,
    OBSERVATION_RUN_PREVENTION_STRESS: 4,
    OBSERVATION_IDENTITY: 5,
    OBSERVATION_CHANGE: 6,
}


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _count(value: Any) -> int:
    return int(_number(value, 0))


def _pct(value: Any) -> int:
    return round(_number(value, 0) * 100)


def _decimal(value: Any) -> str:
    value = _number(value, 0)
    if value == int(value):
        return str(int(value))
    return f'{value:.1f}'


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f'{singular}s')


def _join_names(names: list[str], limit: int = 3) -> str:
    cleaned: list[str] = []
    for name in names:
        text = _clean_text(name)
        if text and text not in cleaned:
            cleaned.append(text)
    names = cleaned[:limit]
    if not names:
        return ''
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f'{names[0]} and {names[1]}'
    return f"{', '.join(names[:-1])}, and {names[-1]}"


def _names_from_options(options: Any) -> list[str]:
    if not isinstance(options, list):
        return []
    return [
        _clean_text(item.get('name'))
        for item in options
        if isinstance(item, dict) and _clean_text(item.get('name'))
    ]


def _named_pitchers(inputs: dict[str, Any]) -> list[str]:
    ordered: list[str] = []
    for options in (
        inputs.get('top_workload_options'),
        inputs.get('clean_trust_options'),
        inputs.get('high_risk_arm_options'),
        inputs.get('clean_options'),
    ):
        for name in _names_from_options(options):
            if name not in ordered:
                ordered.append(name)
    return ordered


def _team_name(inputs: dict[str, Any]) -> str:
    team = inputs.get('team') or {}
    return _clean_text(team.get('team_name')) or 'This bullpen'


def _possessive_team(inputs: dict[str, Any]) -> str:
    name = _team_name(inputs)
    return f"{name}'" if name.endswith('s') else f"{name}'s"


def _team_have_verb(inputs: dict[str, Any]) -> str:
    return 'have' if _team_name(inputs).endswith('s') else 'has'


def _candidate(
    *,
    observation_type: str,
    text: str | None,
    score: float,
    score_components: dict[str, float],
    pitcher_names: list[str],
    consequence_category: str,
    consequence_statement: str,
    source_fields: list[str],
) -> dict[str, Any] | None:
    text = _clean_text(text)
    pitcher_names = [name for name in pitcher_names if _clean_text(name)]
    has_name = any(name in text for name in pitcher_names)
    has_number = any(character.isdigit() for character in text)
    writer_test_passed = bool(text and has_name and has_number and score >= MIN_INTERESTING_SCORE)
    if not writer_test_passed:
        return None
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'observation_id': observation_type,
        'observation_type': observation_type,
        'text': text,
        'score': round(score, 2),
        'score_components': {
            key: round(value, 2)
            for key, value in score_components.items()
        },
        'pitcher_names': pitcher_names,
        'consequence_category': consequence_category,
        'consequence_statement': consequence_statement,
        'source_fields': source_fields,
        'editorial_test': {
            'question': "Could a baseball writer reasonably say: That's the thing?",
            'passed': True,
        },
    }


def _workload_concentration_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    workload = inputs.get('workload') or {}
    top_arms = _count(workload.get('top_arm_count'))
    top_share = _pct(workload.get('top_share'))
    if top_arms <= 0 or top_share < 55:
        return None
    names = _names_from_options(inputs.get('top_workload_options'))
    subject = _join_names(names)
    if not subject:
        return None
    score = 58 + max(top_share - 55, 0) * 0.8 + min(top_arms, 3) * 2
    return _candidate(
        observation_type=OBSERVATION_WORKLOAD_CONCENTRATION,
        text=(
            f'{subject} have handled {top_share}% of '
            f'{_possessive_team(inputs)} recent relief pitches.'
        ),
        score=score,
        score_components={
            'specific_named_pitchers': min(len(names), 3) * 4,
            'workload_share': top_share,
            'unusualness': max(top_share - 55, 0),
        },
        pitcher_names=names,
        consequence_category='heavier_workload_concentration',
        consequence_statement=(
            'That keeps heavier workload concentration in play if the next tight inning '
            f'has to move back through {_join_names(names, limit=2) or "the same group"}.'
        ),
        source_fields=[
            'workload.top_share',
            'workload.top_arm_count',
            'top_workload_options',
        ],
    )


def _resource_constraint_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    availability = inputs.get('availability') or {}
    available = _count(availability.get('available'))
    total = _count(availability.get('total'))
    if total <= 0 or available <= 0:
        return None
    available_share = available / total
    if available > 3 and available_share > 0.35:
        return None
    names = _named_pitchers(inputs)
    subject = _join_names(names)
    if not subject:
        return None
    score = 60 + max(0, 4 - available) * 7 + max(0, 0.35 - available_share) * 60
    return _candidate(
        observation_type=OBSERVATION_RESOURCE_CONSTRAINT,
        text=(
            f'{subject} sit in the current {_team_name(inputs)} bullpen picture while '
            f'only {available} of {total} relievers are available tonight.'
        ),
        score=score,
        score_components={
            'available_count_pressure': max(0, 4 - available) * 7,
            'available_share_pressure': max(0, 0.35 - available_share) * 60,
            'specific_named_pitchers': min(len(names), 3) * 4,
        },
        pitcher_names=names,
        consequence_category='less_coverage_margin',
        consequence_statement=(
            'That leaves less coverage margin if the next close inning has to move beyond '
            f'{_join_names(names, limit=2) or "the first group"}.'
        ),
        source_fields=[
            'availability.available',
            'availability.total',
            'top_workload_options',
            'clean_options',
        ],
    )


def _flexibility_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    workload = inputs.get('workload') or {}
    availability = inputs.get('availability') or {}
    participants = _count(workload.get('participant_count'))
    available = _count(availability.get('available'))
    total = _count(availability.get('total'))
    top_one_share = _pct(workload.get('top_one_share'))
    if participants < 6 or available < 5:
        return None
    names = _named_pitchers(inputs)
    subject = _join_names(names)
    if not subject:
        return None
    score = 56 + max(participants - 5, 0) * 4 + max(available - 4, 0) * 3 + max(30 - top_one_share, 0) * 0.5
    return _candidate(
        observation_type=OBSERVATION_FLEXIBILITY,
        text=(
            f'{_team_name(inputs)} {_team_have_verb(inputs)} spread recent bullpen work across {participants} relievers '
            f'and still has {available} of {total} relievers available, led by {subject}.'
        ),
        score=score,
        score_components={
            'participant_breadth': participants,
            'available_depth': available,
            'top_one_share_inverse': max(30 - top_one_share, 0),
        },
        pitcher_names=names,
        consequence_category='more_stable_bullpen_shape',
        consequence_statement=(
            f'For {_team_name(inputs)}, that creates a more stable bullpen shape because '
            'the staff is not forced back to one narrow group.'
        ),
        source_fields=[
            'workload.participant_count',
            'workload.top_one_share',
            'availability.available',
            'availability.total',
        ],
    )


def _trust_shape_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    clean_trust_names = _names_from_options(inputs.get('clean_trust_options'))
    names = clean_trust_names or _named_pitchers(inputs)
    subject = _join_names(names)
    if not subject:
        return None
    clean_trust_count = len(clean_trust_names)
    clean_option_count = len(inputs.get('clean_options') or [])
    if clean_option_count <= 0:
        return None
    if clean_trust_count >= 2:
        score = 57 + clean_trust_count * 5
        text = (
            f'{subject} give {_team_name(inputs)} {clean_trust_count} clean trusted '
            f'late-inning options among {clean_option_count} usable relievers.'
        )
        category = 'more_stable_bullpen_shape'
        consequence = (
            f'For {_team_name(inputs)}, that creates a more stable bullpen shape because '
            'the late innings have more than one way to land.'
        )
    else:
        score = 58 + max(0, 2 - clean_trust_count) * 7
        text = (
            f'{subject} are carrying the named part of {_possessive_team(inputs)} relief read '
            f'while only {clean_trust_count} clean trusted late-inning option is available.'
        )
        category = 'reduced_flexibility'
        consequence = (
            'That reduces flexibility if the game needs one more clean inning before '
            f'the late plan reaches {_join_names(names, limit=2) or "the trusted group"}.'
        )
    return _candidate(
        observation_type=OBSERVATION_TRUST_SHAPE,
        text=text,
        score=score,
        score_components={
            'clean_trust_count': clean_trust_count,
            'clean_option_count': clean_option_count,
            'specific_named_pitchers': min(len(names), 3) * 4,
        },
        pitcher_names=names,
        consequence_category=category,
        consequence_statement=consequence,
        source_fields=[
            'clean_trust_options',
            'clean_options',
        ],
    )


def _run_prevention_stress_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    season_era = inputs.get('season_era') or {}
    workload = inputs.get('workload') or {}
    era = season_era.get('era')
    if not isinstance(era, (int, float)) or not season_era.get('strong_results'):
        return None
    participants = _count(workload.get('participant_count'))
    per_arm = _decimal(workload.get('per_arm_pitches'))
    names = _named_pitchers(inputs)
    subject = _join_names(names)
    if not subject or participants <= 0:
        return None
    high_risk = _count(inputs.get('high_risk_arms'))
    score = 57 + max(0, 30 - _number(era, 0) * 6) + high_risk * 5 + _number(workload.get('per_arm_pitches')) * 0.3
    return _candidate(
        observation_type=OBSERVATION_RUN_PREVENTION_STRESS,
        text=(
            f'{subject} remain central to {_possessive_team(inputs)} bullpen with a {era:.2f} season ERA, '
            f'but recent usage is {per_arm} pitches per participating reliever.'
        ),
        score=score,
        score_components={
            'season_era_strength': max(0, 30 - _number(era, 0) * 6),
            'per_arm_workload': _number(workload.get('per_arm_pitches')),
            'high_risk_arms': high_risk * 5,
        },
        pitcher_names=names,
        consequence_category='heavier_workload_concentration',
        consequence_statement=(
            'That keeps heavier workload concentration in play if the next tight inning '
            f'has to move back through {_join_names(names, limit=2) or "the same group"}.'
        ),
        source_fields=[
            'season_era.era',
            'season_era.strong_results',
            'workload.per_arm_pitches',
            'high_risk_arm_options',
        ],
    )


def _identity_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    capacity = inputs.get('capacity_intelligence') or {}
    identity = capacity.get('bullpen_identity') if isinstance(capacity, dict) else None
    if not isinstance(identity, dict):
        return None
    summary = _clean_text(identity.get('identity_summary'))
    if not summary:
        return None
    names = _named_pitchers(inputs)
    subject = _join_names(names)
    if not subject:
        return None
    clean_option_count = len(inputs.get('clean_options') or [])
    score = 56 + clean_option_count * 2 + min(len(names), 3) * 4
    return _candidate(
        observation_type=OBSERVATION_IDENTITY,
        text=(
            f'{subject} sit at the front of {_possessive_team(inputs)} bullpen identity, '
            f'with {clean_option_count} usable relievers behind a {summary.lower()}.'
        ),
        score=score,
        score_components={
            'identity_context_present': 12,
            'clean_option_count': clean_option_count,
            'specific_named_pitchers': min(len(names), 3) * 4,
        },
        pitcher_names=names,
        consequence_category='reduced_flexibility',
        consequence_statement=(
            'That reduces flexibility if the game moves away from the relievers who best match '
            f'{_possessive_team(inputs)} current identity.'
        ),
        source_fields=[
            'capacity_intelligence.bullpen_identity',
            'clean_options',
        ],
    )


def _change_observation(inputs: dict[str, Any]) -> dict[str, Any] | None:
    stability = inputs.get('bullpen_stability') or {}
    changed = _count(stability.get('new_or_reintroduced_arm_count'))
    if changed <= 0:
        return None
    names = _named_pitchers(inputs)
    subject = _join_names(names)
    if not subject:
        return None
    score = 55 + changed * 6 + min(len(names), 3) * 4
    return _candidate(
        observation_type=OBSERVATION_CHANGE,
        text=(
            f'{_team_name(inputs)} has {changed} recently reintroduced {_plural(changed, "reliever")}, '
            f'but {subject} still anchor the current usage read.'
        ),
        score=score,
        score_components={
            'new_or_reintroduced_arm_count': changed * 6,
            'specific_named_pitchers': min(len(names), 3) * 4,
        },
        pitcher_names=names,
        consequence_category='more_stable_bullpen_shape',
        consequence_statement=(
            f'For {_team_name(inputs)}, that creates a more stable bullpen shape if those returned arms '
            'can keep the night from collapsing back to one narrow group.'
        ),
        source_fields=[
            'bullpen_stability.new_or_reintroduced_arm_count',
            'top_workload_options',
        ],
    )


def generate_observation_candidates(
    rule_key: str,
    inputs: dict[str, Any],
    lead: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Generate observation candidates before narrative text is rendered."""

    del rule_key, lead
    candidates = [
        factory(inputs)
        for factory in (
            _workload_concentration_observation,
            _resource_constraint_observation,
            _flexibility_observation,
            _trust_shape_observation,
            _run_prevention_stress_observation,
            _identity_observation,
            _change_observation,
        )
    ]
    return [candidate for candidate in candidates if candidate]


def rank_observation_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rank observations by interest, specificity, and deterministic type order."""

    ranked = sorted(
        candidates or [],
        key=lambda item: (
            -_number(item.get('score')),
            OBSERVATION_TYPE_ORDER.get(item.get('observation_type'), 999),
            item.get('text') or '',
        ),
    )
    return [
        {
            **candidate,
            'rank': index,
        }
        for index, candidate in enumerate(ranked, start=1)
    ]


def discover_story_observations(
    rule_key: str,
    inputs: dict[str, Any],
    lead: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return ranked observation candidates and the selected story observation."""

    candidates = rank_observation_candidates(
        generate_observation_candidates(rule_key, inputs, lead=lead)
    )
    selected = candidates[0] if candidates else None
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'generated_before_story_generation': True,
        'candidate_count': len(candidates),
        'ranking_applied': True,
        'selection_made': bool(selected),
        'selected_observation': selected,
        'candidates': candidates,
    }


def story_template_dependency_audit() -> dict[str, Any]:
    """Describe fixed structures still present and how V1 routes around them."""

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'status': 'template_dependency_reduced',
        'fixed_structure_surfaces': [
            'four_beat_story_rule_eligibility',
            'legacy_beat_skeletons',
            'narrative_middle_and_closing_phrase_pools',
            'story_evidence_framework_phrase_diversity_gate',
        ],
        'reduction_strategy': [
            'generate_observation_candidates_before_rendering',
            'rank_candidates_by_specificity_and_unusualness',
            'open_public_narrative_with_selected_observation',
            'fail_closed_when_story_text_does_not_reference_the_selected_observation',
        ],
    }


__all__ = [
    'CAPABILITY',
    'VERSION',
    'discover_story_observations',
    'generate_observation_candidates',
    'rank_observation_candidates',
    'story_template_dependency_audit',
]
