"""Normalized story facts for backend-authored team stories."""

from __future__ import annotations

from typing import Any

from services.story_observation_discovery import discover_story_observations
from services.story_observation_voice import build_observation_voice
from services.story_identity_integration import build_story_identity_integration
from services.story_context_integration import build_story_context_integration


CAPABILITY = 'story_fact_layer_v1'
VERSION = '2026-06-18'
EVIDENCE_CAPABILITY = 'story_evidence_framework_v1'
EVIDENCE_VERSION = '2026-06-19'

BEAT_SIGNAL = 'signal'
BEAT_EVIDENCE = 'evidence'
BEAT_CONTEXT = 'context'
BEAT_MECHANISM = 'mechanism'
BEAT_IMPLICATION = 'implication'

RULE_STRESS_TRANSFER = 'stress_transfer'
RULE_PRESSURE_DISTRIBUTION = 'pressure_distribution'
RULE_SUSTAINABILITY_QUESTION = 'sustainability_question'
RULE_HIDDEN_CAPACITY_LOSS = 'hidden_capacity_loss'

LEAD_FATIGUE_LOAD = 'fatigue_load'
LEAD_TRUST_LANE_ABSENCE = 'trust_lane_absence'
LEAD_TRUST_LANE_SHALLOW = 'trust_lane_shallow'
LEAD_WORKLOAD_HIGH = 'workload_high'
LEAD_WORKLOAD_LIGHT = 'workload_light'
LEAD_AVAILABILITY_THIN = 'availability_thin'
LEAD_AVAILABILITY_DEEP = 'availability_deep'
LEAD_DEEP_INTACT = 'deep_intact'
LEAD_CONCENTRATION_SHAPE = 'concentration_shape'
LEAD_PARTICIPATION_NARROW = 'participation_narrow'
LEAD_PARTICIPATION_BROAD = 'participation_broad'
LEAD_ERA_ELITE = 'era_elite'
LEAD_ERA_ORDINARY = 'era_ordinary'
LEAD_TRUST_LANE_DEPTH = 'trust_lane_depth'

DISCLOSURE_LIMITED_BULLPEN_PICTURE = (
    'With part of the bullpen picture less clear, the read should stay focused '
    'on usage patterns rather than assuming the full roster picture.'
)


def _clean_text(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _sentence(value: Any) -> str | None:
    text = _clean_text(value)
    if not text:
        return None
    if text[-1] not in '.!?':
        text = f'{text}.'
    return text


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
    number = _number(value, 0)
    if number == int(number):
        return str(int(number))
    return f'{number:.1f}'


def _plural(count: int, singular: str, plural: str | None = None) -> str:
    return singular if count == 1 else (plural or f'{singular}s')


def _join_names(names: list[str], limit: int = 2) -> str:
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


def _named_pitchers(inputs: dict[str, Any], rule_key: str | None = None) -> list[str]:
    ordered: list[str] = []
    option_sets = []
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        option_sets.append(inputs.get('high_risk_arm_options'))
    option_sets.extend([
        inputs.get('top_workload_options'),
        inputs.get('clean_trust_options'),
        inputs.get('high_risk_arm_options'),
        inputs.get('clean_options'),
    ])
    for options in option_sets:
        for name in _names_from_options(options):
            if name not in ordered:
                ordered.append(name)
    return ordered


def _beat_by_key(beats: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    return next((beat for beat in beats if beat.get('key') == key), None)


def _beat_text(beats: list[dict[str, Any]], key: str) -> str | None:
    beat = _beat_by_key(beats, key)
    return _sentence((beat or {}).get('text'))


def _context_items(beats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    context = _beat_by_key(beats, BEAT_CONTEXT) or {}
    items = context.get('items') or []
    return [item for item in items if isinstance(item, dict)]


def _context_text(items: list[dict[str, Any]], source: str) -> str | None:
    matches = [_sentence(item.get('text')) for item in items if item.get('source') == source]
    matches = [item for item in matches if item]
    if not matches:
        return None
    return ' '.join(matches)


def _team_identity(inputs: dict[str, Any]) -> dict[str, Any]:
    team = inputs.get('team') or {}
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
    }


def _supporting_context(rule_key: str, inputs: dict[str, Any]) -> str | None:
    workload = inputs.get('workload') or {}
    availability = inputs.get('availability') or {}
    season_era = inputs.get('season_era') or {}
    available = _count(availability.get('available'))
    total = _count(availability.get('total'))
    participants = _count(workload.get('participant_count'))
    top_arms = _count(workload.get('top_arm_count'))
    top_share = _pct(workload.get('top_share'))
    per_arm = _decimal(workload.get('per_arm_pitches'))
    high_risk = _count(inputs.get('high_risk_arms'))
    era = season_era.get('era')
    era_text = f' at a {era:.2f} ERA' if isinstance(era, (int, float)) else ''

    if rule_key == RULE_STRESS_TRANSFER:
        if total > 0 and top_arms > 0:
            return (
                f'The recent workload has clustered around the top {top_arms} '
                f'{_plural(top_arms, "reliever")}, who have handled {top_share}% '
                f'of relief pitches in the window, while {available} of {total} '
                'bullpen arms are available.'
            )
        return 'The current read is built around recent relief usage and the available bullpen layer.'

    if rule_key == RULE_PRESSURE_DISTRIBUTION:
        if participants > 0:
            return (
                f'Recent relief work has been spread across {participants} '
                f'{_plural(participants, "reliever")}, averaging {per_arm} '
                'pitches per participating arm.'
            )
        return 'Recent relief usage has not centered on one narrow group.'

    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        load = (
            f'recent usage is averaging {per_arm} pitches per participating reliever'
            if participants > 0 else 'recent usage is doing more of the explaining'
        )
        heavier_flag = (
            ' At least one arm is already carrying a heavier workload flag.'
            if high_risk > 0 else ''
        )
        return f'The season run prevention has been strong{era_text}, but {load}.{heavier_flag}'

    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        if total > 0:
            return (
                f'The run prevention line has stayed solid{era_text}, but only '
                f'{available} of {total} bullpen arms are available in the current read.'
            )
        return f'The run prevention line has stayed solid{era_text}, but the usable layer is less clear.'

    return _beat_text([], BEAT_EVIDENCE)


def _pressure_source(rule_key: str, lead: dict[str, Any] | None) -> str | None:
    dimension = (lead or {}).get('dimension')
    if dimension == LEAD_FATIGUE_LOAD:
        return 'The pressure source is recent workload landing on arms that are already carrying a heavier usage flag.'
    if dimension in {LEAD_TRUST_LANE_ABSENCE, LEAD_TRUST_LANE_SHALLOW, LEAD_TRUST_LANE_DEPTH, LEAD_DEEP_INTACT}:
        return 'The pressure source is the trusted late-inning layer, where the usable group and the preferred group do not fully line up.'
    if dimension in {LEAD_WORKLOAD_HIGH, LEAD_CONCENTRATION_SHAPE, LEAD_PARTICIPATION_NARROW}:
        return 'The pressure source is recent work being concentrated around a smaller set of relievers.'
    if dimension in {LEAD_WORKLOAD_LIGHT, LEAD_PARTICIPATION_BROAD}:
        return 'The shape comes from recent work being spread across more of the bullpen.'
    if dimension == LEAD_AVAILABILITY_THIN:
        return 'The pressure source is a thinner usable layer behind the late-inning plan.'
    if dimension == LEAD_AVAILABILITY_DEEP:
        return 'The shape comes from a deeper usable layer behind the late-inning plan.'
    if dimension in {LEAD_ERA_ELITE, LEAD_ERA_ORDINARY}:
        return 'The season run-prevention line is part of the read, but it is not the whole bullpen picture.'

    if rule_key == RULE_STRESS_TRANSFER:
        return 'The pressure source is workload concentration meeting a smaller usable group.'
    if rule_key == RULE_PRESSURE_DISTRIBUTION:
        return 'The shape comes from workload distribution rather than one narrow lane.'
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        return 'The tension is between strong results and the size of the recent workload ask.'
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        return 'The pressure source is usable depth behind a solid run-prevention line.'
    return None


def _workload_pattern(inputs: dict[str, Any]) -> str | None:
    workload = inputs.get('workload') or {}
    total_pitches = _count(workload.get('total_pitches'))
    participants = _count(workload.get('participant_count'))
    top_arms = _count(workload.get('top_arm_count'))
    top_share = _pct(workload.get('top_share'))
    per_arm = _decimal(workload.get('per_arm_pitches'))

    if total_pitches <= 0 or participants <= 0:
        return 'The recent workload sample is too thin to carry a bigger usage read.'
    if top_share >= 60 and top_arms > 0:
        return (
            f'The workload pattern is narrow: the top {top_arms} '
            f'{_plural(top_arms, "reliever")} have taken {top_share}% of the recent relief work.'
        )
    if participants >= 6:
        return (
            f'The workload pattern is broad: {participants} relievers have shared the work '
            f'at {per_arm} pitches per participating arm.'
        )
    return (
        f'The workload pattern sits between those poles, with {participants} relievers '
        f'sharing {total_pitches} recent relief pitches.'
    )


def _watch_question(rule_key: str, lead: dict[str, Any] | None) -> str:
    dimension = (lead or {}).get('dimension')
    if dimension in {LEAD_WORKLOAD_LIGHT, LEAD_PARTICIPATION_BROAD, LEAD_AVAILABILITY_DEEP}:
        return 'The next useful read is whether that broad, usable shape still holds after the next completed game.'
    if dimension in {LEAD_TRUST_LANE_ABSENCE, LEAD_TRUST_LANE_SHALLOW, LEAD_TRUST_LANE_DEPTH, LEAD_DEEP_INTACT}:
        return 'The thing to watch next is whether the late-inning work can move through more than the same trusted lane.'
    if dimension == LEAD_FATIGUE_LOAD:
        return 'The thing to watch next is whether the heaviest recent workload starts to ease.'

    if rule_key == RULE_PRESSURE_DISTRIBUTION:
        return 'The next useful read is whether the work stays spread across the group.'
    if rule_key == RULE_SUSTAINABILITY_QUESTION:
        return 'The thing to watch next is whether the same relievers remain at the center of the workload.'
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS:
        return 'The next useful read is whether one more bullpen-heavy game exposes the thin usable layer behind the results.'
    return 'The thing to watch next is whether the recent usage pattern changes after the next completed game.'


def _evidence_statement(rule_key: str, inputs: dict[str, Any], lead: dict[str, Any] | None) -> str | None:
    workload = inputs.get('workload') or {}
    availability = inputs.get('availability') or {}
    season_era = inputs.get('season_era') or {}
    team = _team_identity(inputs)
    team_name = _clean_text(team.get('team_name'))
    pitcher_names = _named_pitchers(inputs, rule_key)
    subject = _join_names(pitcher_names)
    if not subject:
        return None
    verb = 'is' if len(pitcher_names[:2]) == 1 else 'are'
    top_arms = _count(workload.get('top_arm_count'))
    top_share = _pct(workload.get('top_share'))
    participants = _count(workload.get('participant_count'))
    per_arm = _decimal(workload.get('per_arm_pitches'))
    available = _count(availability.get('available'))
    total = _count(availability.get('total'))
    era = season_era.get('era')
    era_text = f' behind a {era:.2f} season ERA' if isinstance(era, (int, float)) else ''
    dimension = (lead or {}).get('dimension')

    if top_share >= 60 and top_arms > 0:
        return (
            f'{subject} {verb} part of the top {top_arms} {team_name} relievers '
            f'who have handled {top_share}% of recent relief pitches.'
        )
    if participants >= 6:
        return (
            f'{subject} {verb} part of a {participants}-reliever {team_name} workload spread '
            f'averaging {per_arm} pitches per participating arm.'
        )
    if total > 0 and dimension in {LEAD_AVAILABILITY_THIN, LEAD_AVAILABILITY_DEEP}:
        return (
            f'{subject} {verb} in the current {team_name} bullpen mix while '
            f'{available} of {total} relievers are available.'
        )
    if rule_key in {RULE_SUSTAINABILITY_QUESTION, RULE_HIDDEN_CAPACITY_LOSS} and era_text:
        if participants > 0:
            return (
                f'{subject} {verb} in the current {team_name} relief mix{era_text}, '
                f'with recent usage at {per_arm} pitches per participating reliever.'
            )
        return (
            f'{subject} {verb} in the current {team_name} relief mix{era_text}, '
            f'with {available} of {total} relievers available.'
        )
    if total > 0:
        return (
            f'{subject} {verb} in the current {team_name} bullpen mix while '
            f'{available} of {total} relievers are available.'
        )
    return None


def _consequence_category(rule_key: str, lead: dict[str, Any] | None) -> str:
    dimension = (lead or {}).get('dimension')
    if rule_key == RULE_PRESSURE_DISTRIBUTION or dimension in {
        LEAD_WORKLOAD_LIGHT,
        LEAD_PARTICIPATION_BROAD,
        LEAD_AVAILABILITY_DEEP,
        LEAD_DEEP_INTACT,
    }:
        return 'more_stable_bullpen_shape'
    if rule_key == RULE_SUSTAINABILITY_QUESTION or dimension in {
        LEAD_FATIGUE_LOAD,
        LEAD_WORKLOAD_HIGH,
        LEAD_CONCENTRATION_SHAPE,
        LEAD_PARTICIPATION_NARROW,
    }:
        return 'heavier_workload_concentration'
    if rule_key == RULE_HIDDEN_CAPACITY_LOSS or dimension in {
        LEAD_AVAILABILITY_THIN,
        LEAD_TRUST_LANE_ABSENCE,
        LEAD_TRUST_LANE_SHALLOW,
    }:
        return 'reduced_flexibility'
    return 'less_coverage_margin'


def _consequence_statement(rule_key: str, inputs: dict[str, Any], lead: dict[str, Any] | None) -> str:
    category = _consequence_category(rule_key, lead)
    team = _team_identity(inputs)
    team_name = _clean_text(team.get('team_name'))
    names = _join_names(_named_pitchers(inputs, rule_key))
    if category == 'more_stable_bullpen_shape':
        return (
            f'For {team_name}, that creates a more stable bullpen shape because the staff is not forced '
            'back to one narrow group.'
        )
    if category == 'heavier_workload_concentration':
        return (
            'That keeps heavier workload concentration in play if the next tight inning '
            f'has to move back through {names or "the same group"}.'
        )
    if category == 'reduced_flexibility':
        return (
            'That reduces flexibility if the game needs one more clean inning before '
            f'the late plan reaches {names or "the trusted group"}.'
        )
    return (
        'That leaves less coverage margin if the next close inning has to move beyond '
        f'{names or "the first group"}.'
    )


def _disclosure(inputs: dict[str, Any], context_items: list[dict[str, Any]]) -> str | None:
    if any(item.get('source_limitations_present') or item.get('disclosure_limitations') for item in context_items):
        return DISCLOSURE_LIMITED_BULLPEN_PICTURE
    availability = inputs.get('availability') or {}
    if _count(availability.get('total')) <= 0:
        return DISCLOSURE_LIMITED_BULLPEN_PICTURE
    return None


def build_story_facts(
    rule_key: str,
    inputs: dict[str, Any],
    beats: list[dict[str, Any]],
    lead: dict[str, Any] | None = None,
    selected_observation_override: dict[str, Any] | None = None,
    observation_differentiation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Adapt four-beat story inputs into normalized baseball story facts."""

    context_items = _context_items(beats)
    disclosure = _disclosure(inputs, context_items)
    bullpen_context = build_story_context_integration(rule_key, inputs, lead=lead)
    capacity_intelligence = inputs.get('capacity_intelligence') or {}
    bullpen_identity = (
        capacity_intelligence.get('bullpen_identity')
        if isinstance(capacity_intelligence, dict)
        else None
    ) or {}
    observation_discovery = discover_story_observations(
        rule_key,
        inputs,
        lead=lead,
        selected_observation_override=selected_observation_override,
        observation_differentiation=observation_differentiation,
    )
    selected_observation = observation_discovery.get('selected_observation') or {}
    evidence_statement = selected_observation.get('text') or _evidence_statement(rule_key, inputs, lead)
    consequence_category = (
        selected_observation.get('consequence_category')
        or _consequence_category(rule_key, lead)
    )
    consequence_statement = (
        selected_observation.get('consequence_statement')
        or _consequence_statement(rule_key, inputs, lead)
    )
    named_pitchers = selected_observation.get('pitcher_names') or _named_pitchers(inputs, rule_key)
    observation_voice = build_observation_voice({
        'team': _team_identity(inputs),
        'rule_key': rule_key,
        'lead_dimension': (lead or {}).get('dimension'),
        'selected_observation': selected_observation,
        'named_pitchers': named_pitchers,
        'evidence_statement': evidence_statement,
        'consequence_statement': consequence_statement,
        'consequence_category': consequence_category,
    })
    facts = {
        'capability': CAPABILITY,
        'version': VERSION,
        'evidence_capability': EVIDENCE_CAPABILITY,
        'evidence_version': EVIDENCE_VERSION,
        'team': _team_identity(inputs),
        'observation_discovery': observation_discovery,
        'observation_differentiation': observation_discovery.get('observation_differentiation') or {},
        'selected_observation': selected_observation,
        'observation_voice': observation_voice,
        'named_pitchers': named_pitchers,
        'evidence_statement': evidence_statement,
        'consequence_category': consequence_category,
        'consequence_statement': consequence_statement,
        'primary_observation': _beat_text(beats, BEAT_SIGNAL),
        'supporting_context': _supporting_context(rule_key, inputs),
        'pressure_source': _pressure_source(rule_key, lead),
        'workload_pattern': _workload_pattern(inputs),
        'capacity_context': _context_text(context_items, 'capacity_loss'),
        'rotation_context': _context_text(context_items, 'rotation_support_pressure'),
        'stability_context': _context_text(context_items, 'bullpen_stability'),
        'environment_context': _context_text(context_items, 'bullpen_environment'),
        'bullpen_context': bullpen_context.get('text'),
        'bullpen_context_integration': bullpen_context,
        'bullpen_identity': bullpen_identity,
        'identity_context': bullpen_identity.get('identity_summary') if bullpen_identity else None,
        'watch_question': _watch_question(rule_key, lead),
        'confidence': 'limited' if disclosure else 'supported',
        'disclosure': disclosure,
    }
    story_identity = build_story_identity_integration(facts)
    facts['identity_story_context'] = story_identity.get('text')
    facts['story_identity_integration'] = story_identity
    return facts


__all__ = [
    'CAPABILITY',
    'VERSION',
    'DISCLOSURE_LIMITED_BULLPEN_PICTURE',
    'build_story_facts',
]
