"""
Conservative synthesis for backend-authored bullpen intelligence layers.

This module does not recalculate capacity, rotation pressure, or stability. It
only summarizes already-authored source reads so downstream surfaces can consume
one environment object without losing the separate source payloads.
"""

from __future__ import annotations

from typing import Any


CAPABILITY = 'bullpen_environment_v1'
LEAGUE_CAPABILITY = 'league_bullpen_environment_v1'
VERSION = '2026-06-18.synthesis'
SOURCE = 'backend'

STATUS_STABLE = 'stable_environment'
STATUS_PRESSURE = 'pressure_with_context'
STATUS_MULTI_SOURCE = 'multi_source_pressure'
STATUS_LIMITED = 'limited_read'

SOURCE_CAPACITY = 'capacity_loss'
SOURCE_ROTATION = 'rotation_support_pressure'
SOURCE_STABILITY = 'bullpen_stability'

FLAG_MODERATE_CHURN = 'moderate_churn'
FLAG_HEAVY_CHURN = 'heavy_churn'
FLAG_TRUST_CAPACITY_LOSS = 'trust_capacity_loss'
FLAG_LIMITED_READ_INPUTS = 'limited_read_inputs'
FLAG_SOURCE_LIMITATIONS = 'source_limitations_present'

CAPACITY_PRESSURE_STATUSES = {'elevated', 'constrained', 'severe'}
ROTATION_PRESSURE_STATUSES = {'moderate_pressure', 'heavy_pressure'}
STABILITY_PRESSURE_STATUSES = {'heavy_churn'}
LIMITED_STATUSES = {'limited_read', 'no_data'}

MATERIAL_CAPACITY_LOSS_PCT = 20
MATERIAL_TRUST_CAPACITY_LOSS_PCT = 20

MISSING_LAYER_LIMITATION = (
    'Bullpen Environment is a Limited Read because one or more source intelligence layers are missing.'
)
LIMITED_LAYER_LIMITATION = (
    'Bullpen Environment is a Limited Read because one or more source intelligence layers are limited or uncertain.'
)

DEFINITIONS = {
    'stable_environment': (
        'No major pressure source is present and the recent bullpen usage group is stable.'
    ),
    'pressure_with_context': (
        'One primary pressure source is present, or a contextual stress flag is present without multiple primary sources.'
    ),
    'multi_source_pressure': (
        'Two or more primary pressure sources are present across capacity, rotation support, and stability reads.'
    ),
    'limited_read': (
        'At least one required source layer is missing, limited, or too uncertain for a full synthesis read.'
    ),
    'primary_pressure_sources': (
        'Source reads contributing direct pressure to the bullpen environment; this is descriptive and does not order teams.'
    ),
    'context_flags': (
        'Supporting context carried alongside pressure sources. Context flags do not order teams or select pitcher usage.'
    ),
}

PRESSURE_LABELS = {
    SOURCE_CAPACITY: 'unavailable capacity',
    SOURCE_ROTATION: 'short-start workload',
    SOURCE_STABILITY: 'heavy churn in the recent usage group',
}

CONTEXT_LABELS = {
    FLAG_MODERATE_CHURN: 'moderate churn in the recent usage group',
    FLAG_HEAVY_CHURN: 'heavy churn in the recent usage group',
    FLAG_TRUST_CAPACITY_LOSS: 'Trust Arm capacity loss',
}


def _get(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _number(value, default=0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _dedupe(items):
    result = []
    for item in items or []:
        if item is None:
            continue
        if item not in result:
            result.append(item)
    return result


def _team_identity(team, *sources):
    identity = {
        'team_id': None,
        'team_name': None,
        'team_abbreviation': None,
    }
    if isinstance(team, dict):
        identity.update({
            'team_id': team.get('team_id'),
            'team_name': team.get('team_name'),
            'team_abbreviation': team.get('team_abbreviation'),
        })
    for source in sources:
        if not isinstance(source, dict):
            continue
        for key in identity:
            if identity[key] is None and source.get(key) is not None:
                identity[key] = source.get(key)
    return identity


def _status_of(layer, *path):
    if not path and isinstance(layer, dict):
        return str(layer.get('status') or '')
    return str(_get(layer, *path, default='') or '')


def _is_missing_layer(layer, required_path=None):
    if not isinstance(layer, dict) or not layer:
        return True
    if required_path:
        return not isinstance(_get(layer, *required_path), dict)
    return False


def _has_limited_or_unknown_signal(layer):
    if not isinstance(layer, dict):
        return False
    statuses = [
        str(layer.get('status') or ''),
        str(_get(layer, 'capacity_loss', 'status', default='') or ''),
    ]
    if any(status in LIMITED_STATUSES for status in statuses):
        return True
    unknown_capacity_pct = _number(
        _get(layer, 'capacity_loss', 'unknown_limited_read_capacity_pct', default=0)
    )
    return unknown_capacity_pct > 0


def _source_limitations(*layers):
    values = []
    for layer in layers:
        if isinstance(layer, dict):
            values.extend(layer.get('source_limitations') or [])
    return _dedupe(values)


def _limitations(capacity_intelligence, rotation_support_pressure, bullpen_stability, missing_layers, limited_layers):
    values = []
    if missing_layers:
        values.append(MISSING_LAYER_LIMITATION)
    if limited_layers:
        values.append(LIMITED_LAYER_LIMITATION)

    capacity_loss = _get(capacity_intelligence, 'capacity_loss', default={}) or {}
    trust_loss = _get(capacity_intelligence, 'trust_capacity_loss', default={}) or {}
    for layer in (capacity_loss, trust_loss, rotation_support_pressure, bullpen_stability):
        if isinstance(layer, dict):
            values.extend(layer.get('limitations') or [])
    return _dedupe(values)


def _capacity_is_pressure(capacity_loss):
    status = str((capacity_loss or {}).get('status') or '')
    unavailable_pct = _number((capacity_loss or {}).get('unavailable_capacity_pct'))
    return (
        status in CAPACITY_PRESSURE_STATUSES
        or unavailable_pct >= MATERIAL_CAPACITY_LOSS_PCT
    )


def _trust_capacity_flag(trust_capacity_loss):
    status = str((trust_capacity_loss or {}).get('status') or '')
    unavailable_pct = _number((trust_capacity_loss or {}).get('trust_capacity_unavailable_pct'))
    return (
        status in CAPACITY_PRESSURE_STATUSES
        or unavailable_pct >= MATERIAL_TRUST_CAPACITY_LOSS_PCT
    )


def _summary(status, primary_sources, context_flags):
    pressure_labels = [PRESSURE_LABELS.get(source, source) for source in primary_sources]
    material_context = [
        CONTEXT_LABELS[flag]
        for flag in context_flags
        if flag in CONTEXT_LABELS
    ]

    if status == STATUS_LIMITED:
        return 'Bullpen Environment is a Limited Read because one or more source reads are missing or limited.'
    if status == STATUS_STABLE:
        return 'The bullpen environment reads stable across capacity, rotation support, and recent usage group.'

    if len(pressure_labels) >= 2:
        pressure_text = ', '.join(pressure_labels[:-1]) + f' and {pressure_labels[-1]}'
        if material_context:
            return (
                f'The bullpen environment shows pressure from {pressure_text}, '
                f'with {material_context[0]}.'
            )
        return f'The bullpen environment shows pressure from {pressure_text}.'

    if pressure_labels:
        if material_context:
            return (
                f'The bullpen environment shows pressure from {pressure_labels[0]}, '
                f'with {material_context[0]}.'
            )
        return f'The bullpen environment shows pressure from {pressure_labels[0]}.'

    if material_context:
        return f'The bullpen environment has contextual pressure from {material_context[0]}.'
    return 'The bullpen environment has contextual pressure without a primary source read.'


def build_team_bullpen_environment(
    *,
    capacity_intelligence=None,
    rotation_support_pressure=None,
    bullpen_stability=None,
    team=None,
):
    """Build a conservative synthesis object from existing bullpen reads."""
    capacity_loss = _get(capacity_intelligence, 'capacity_loss', default={}) or {}
    trust_capacity_loss = _get(capacity_intelligence, 'trust_capacity_loss', default={}) or {}

    missing_layers = []
    if _is_missing_layer(capacity_intelligence, ('capacity_loss',)):
        missing_layers.append(SOURCE_CAPACITY)
    if _is_missing_layer(rotation_support_pressure):
        missing_layers.append(SOURCE_ROTATION)
    if _is_missing_layer(bullpen_stability):
        missing_layers.append(SOURCE_STABILITY)

    limited_layers = []
    for key, layer in (
        (SOURCE_CAPACITY, capacity_intelligence),
        (SOURCE_ROTATION, rotation_support_pressure),
        (SOURCE_STABILITY, bullpen_stability),
    ):
        if key not in missing_layers and _has_limited_or_unknown_signal(layer):
            limited_layers.append(key)

    primary_sources = []
    if (
        SOURCE_CAPACITY not in missing_layers
        and SOURCE_CAPACITY not in limited_layers
        and _capacity_is_pressure(capacity_loss)
    ):
        primary_sources.append(SOURCE_CAPACITY)
    if (
        SOURCE_ROTATION not in missing_layers
        and SOURCE_ROTATION not in limited_layers
        and _status_of(rotation_support_pressure) in ROTATION_PRESSURE_STATUSES
    ):
        primary_sources.append(SOURCE_ROTATION)
    if (
        SOURCE_STABILITY not in missing_layers
        and SOURCE_STABILITY not in limited_layers
        and _status_of(bullpen_stability) in STABILITY_PRESSURE_STATUSES
    ):
        primary_sources.append(SOURCE_STABILITY)

    source_limitations = _source_limitations(
        capacity_intelligence,
        rotation_support_pressure,
        bullpen_stability,
    )
    context_flags = []
    stability_status = _status_of(bullpen_stability)
    if stability_status == 'moderate_churn':
        context_flags.append(FLAG_MODERATE_CHURN)
    elif stability_status == 'heavy_churn':
        context_flags.append(FLAG_HEAVY_CHURN)
    if _trust_capacity_flag(trust_capacity_loss):
        context_flags.append(FLAG_TRUST_CAPACITY_LOSS)
    if missing_layers or limited_layers:
        context_flags.append(FLAG_LIMITED_READ_INPUTS)
    if source_limitations:
        context_flags.append(FLAG_SOURCE_LIMITATIONS)
    context_flags = _dedupe(context_flags)

    if missing_layers or limited_layers:
        status = STATUS_LIMITED
    elif len(primary_sources) >= 2:
        status = STATUS_MULTI_SOURCE
    elif primary_sources or any(flag in context_flags for flag in (
        FLAG_MODERATE_CHURN,
        FLAG_HEAVY_CHURN,
        FLAG_TRUST_CAPACITY_LOSS,
    )):
        status = STATUS_PRESSURE
    else:
        status = STATUS_STABLE

    identity = _team_identity(
        team,
        capacity_intelligence,
        rotation_support_pressure,
        bullpen_stability,
    )
    limitations = _limitations(
        capacity_intelligence,
        rotation_support_pressure,
        bullpen_stability,
        missing_layers,
        limited_layers,
    )

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'team': identity.get('team_abbreviation'),
        **identity,
        'status': status,
        'primary_pressure_sources': primary_sources,
        'context_flags': context_flags,
        'summary': _summary(status, primary_sources, context_flags),
        'supporting_reads': {
            'capacity_loss_status': capacity_loss.get('status'),
            'capacity_unavailable_pct': capacity_loss.get('unavailable_capacity_pct'),
            'trust_capacity_loss_status': trust_capacity_loss.get('status'),
            'trust_capacity_unavailable_pct': trust_capacity_loss.get('trust_capacity_unavailable_pct'),
            'rotation_support_status': (rotation_support_pressure or {}).get('status'),
            'rotation_short_start_rate': (rotation_support_pressure or {}).get('short_start_rate'),
            'bullpen_stability_status': (bullpen_stability or {}).get('status'),
            'new_or_reintroduced_arm_count': (bullpen_stability or {}).get('new_or_reintroduced_arm_count'),
        },
        'source_capabilities': {
            'capacity_intelligence': (capacity_intelligence or {}).get('capability'),
            'rotation_support_pressure': (rotation_support_pressure or {}).get('capability'),
            'bullpen_stability': (bullpen_stability or {}).get('capability'),
        },
        'missing_layers': missing_layers,
        'limited_layers': limited_layers,
        'definitions': dict(DEFINITIONS),
        'source_limitations': source_limitations,
        'limitations': limitations,
    }


def build_league_bullpen_environment_payload(team_items):
    teams = list(team_items or [])
    return {
        'capability': LEAGUE_CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'teams_evaluated': len(teams),
        'teams': teams,
        'by_team_id': {
            str(item.get('team_id')): item
            for item in teams
            if item.get('team_id') is not None
        },
    }


__all__ = [
    'CAPABILITY',
    'LEAGUE_CAPABILITY',
    'STATUS_LIMITED',
    'STATUS_MULTI_SOURCE',
    'STATUS_PRESSURE',
    'STATUS_STABLE',
    'VERSION',
    'build_league_bullpen_environment_payload',
    'build_team_bullpen_environment',
]
