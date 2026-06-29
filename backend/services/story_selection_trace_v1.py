"""Internal story-selection trace diagnostics.

Read-only helper for explaining why the public story path selected each beat.
It exposes existing selection metadata and source context only; it does not
change selection, writer output, public API payloads, models, or UI.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from services.story_feed import build_canonical_story_feed
from services.story_intelligence_service_v1 import (
    build_story_intelligence_service_v1,
)
from services.story_voice_library_v1 import (
    BEAT_AVAILABILITY_DEPTH,
    BEAT_BRIDGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_TRUST_LANE,
)


CAPABILITY = 'story_selection_trace_v1'
VERSION = '2026-06-29.e1c'

PATH_CANONICAL_DASHBOARD = 'canonical_dashboard_stories'
PATH_STORIES_PAGE = 'stories_page'
PATH_HOME_TODAY = 'home_today_story'
PATH_TEAM_STORY_API = 'team_story_api'
PATH_TEAM_PREVIEWS = 'team_story_previews'
PATH_TODAY_LEAD_STORY = 'today_lead_story_coin'
PATH_FOUR_BEAT_AUDIT = 'four_beat_real_quality_audit'
PATH_DETERMINISTIC_EDITORIAL_CORPUS = 'deterministic_editorial_corpus'

STORY_GENERATION_PATHS = (
    {
        'path': PATH_CANONICAL_DASHBOARD,
        'surface': 'GET /api/bullpen/dashboard -> payload.stories',
        'selection_engine': 'story_intelligence_service_v1',
        'public_contract': 'baseballos_canonical_story_v1',
        'notes': 'Homepage and Stories consume this canonical dashboard feed.',
    },
    {
        'path': PATH_STORIES_PAGE,
        'surface': 'frontend /stories',
        'selection_engine': 'dashboard.stories',
        'public_contract': 'baseballos_canonical_story_v1',
        'notes': 'Frontend renders the canonical backend feed; it does not select beats.',
    },
    {
        'path': PATH_HOME_TODAY,
        'surface': 'frontend Home / Today story modules',
        'selection_engine': 'dashboard.stories',
        'public_contract': 'baseballos_canonical_story_v1',
        'notes': 'Home presentation derives public stories from the dashboard payload.',
    },
    {
        'path': PATH_TEAM_STORY_API,
        'surface': 'GET /api/bullpen/teams/<team_id>/story',
        'selection_engine': 'story_intelligence_service_v1',
        'public_contract': 'story_intelligence_api_v1',
        'notes': 'Team bullpen note path builds one team story directly.',
    },
    {
        'path': PATH_TEAM_PREVIEWS,
        'surface': 'frontend/public/team/<ABBR>/index.html exports',
        'selection_engine': 'dashboard.stories',
        'public_contract': 'team_story_preview',
        'notes': 'Preview pages read the canonical dashboard feed.',
    },
    {
        'path': PATH_TODAY_LEAD_STORY,
        'surface': 'GET /api/bullpen/intelligence/today',
        'selection_engine': 'COIN story package selection',
        'public_contract': 'intelligence_surface_snapshot',
        'notes': 'Separate completed-game lead-story path, not the canonical bullpen feed.',
    },
    {
        'path': PATH_FOUR_BEAT_AUDIT,
        'surface': 'artifacts/four_beat_real_quality_audit_v1.json',
        'selection_engine': 'story_audit_preview_v1',
        'public_contract': 'four_beat_real_quality_audit_v1',
        'notes': 'Generated artifact path for real-context audit review.',
    },
    {
        'path': PATH_DETERMINISTIC_EDITORIAL_CORPUS,
        'surface': 'backend/tests/test_story_editorial_regression_v1.py',
        'selection_engine': 'story_intelligence_service_v1',
        'public_contract': 'baseballos_canonical_story_v1',
        'notes': 'Supplied-context deterministic 30-team regression corpus.',
    },
)

PUBLIC_BEATS = (
    BEAT_ROUTE_CHANGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_SUSTAINABILITY_QUESTION,
    BEAT_AVAILABILITY_DEPTH,
    BEAT_TRUST_LANE,
    BEAT_BRIDGE,
)


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list:
    return value if isinstance(value, list) else []


def _clean(value: Any) -> str:
    return ' '.join(str(value or '').strip().split())


def _name_from_row(row: Any) -> str:
    if isinstance(row, str):
        return _clean(row)
    return _clean(_dict(row).get('name'))


def _names(value: Any) -> list[str]:
    rows = []
    for row in _list(value):
        name = _name_from_row(row)
        if name and name not in rows:
            rows.append(name)
    return rows


def _count(value: Any):
    if isinstance(value, list):
        return len(value)
    return value


def _nested(context: dict, section: str, key: str):
    return _dict(context.get(section)).get(key)


def _story_type_counts(stories: list[dict]) -> dict[str, int]:
    counts = Counter(
        story.get('story_type')
        for story in stories
        if story.get('story_available') is True and story.get('story_type')
    )
    return {
        beat: int(counts.get(beat, 0))
        for beat in PUBLIC_BEATS
    }


def _beat_distribution(stories: list[dict]) -> dict:
    counts = _story_type_counts(stories)
    total = sum(counts.values())
    max_beat, max_count = (None, 0)
    if total:
        max_beat, max_count = max(counts.items(), key=lambda item: (item[1], item[0]))
    route_depth_count = counts.get(BEAT_ROUTE_CHANGE, 0) + counts.get(BEAT_DEPTH_CONSTRAINT, 0)
    return {
        'story_count': total,
        'story_type_counts': counts,
        'distinct_beat_count': sum(1 for count in counts.values() if count > 0),
        'max_beat': max_beat,
        'max_beat_count': max_count,
        'max_beat_share': round(max_count / total, 3) if total else 0.0,
        'route_depth_count': route_depth_count,
        'route_depth_share': round(route_depth_count / total, 3) if total else 0.0,
    }


def _selected_profile(payload: dict) -> dict:
    return _dict(_dict(payload.get('selection_metadata')).get('selected_profile'))


def _candidate_profiles(payload: dict) -> list[dict]:
    return [
        {
            'story_type': profile.get('story_type'),
            'observation_type': profile.get('observation_type'),
            'selection_rank': profile.get('selection_rank'),
            'selection_strength': int(profile.get('selection_strength') or 0),
            'evidence_completeness': int(profile.get('evidence_completeness') or 0),
            'selection_reasons': list(_list(profile.get('selection_reasons'))),
            'selected': profile.get('selected') is True,
        }
        for profile in _list(_dict(payload.get('selection_metadata')).get('candidate_profiles'))
    ]


def _fallback_status(service_payload: dict, canonical_item: dict | None) -> dict:
    service_available = _dict(service_payload).get('story_available') is True
    canonical_available = _dict(canonical_item).get('story_available') is True
    return {
        'fallback_used': not (service_available and canonical_available),
        'service_state': _dict(service_payload).get('state'),
        'neutral_reason': _dict(service_payload).get('neutral_reason'),
        'canonical_suppression_reason': _dict(canonical_item).get('suppression_reason'),
        'limitations': list(_list(_dict(service_payload).get('limitations'))),
    }


def _primary_inputs_for_beat(story_type: str | None, context: dict) -> dict:
    if story_type == BEAT_COVERAGE_PRESSURE:
        return {
            'rotation_avg_ip_7d': _nested(context, 'rotation_context', 'rotation_avg_ip_7d'),
            'rotation_avg_ip_14d': _nested(context, 'rotation_context', 'rotation_avg_ip_14d'),
            'rotation_ip_trend': _nested(context, 'rotation_context', 'rotation_ip_trend'),
            'early_bullpen_entry_rate': _nested(context, 'rotation_context', 'early_bullpen_entry_rate'),
            'bullpen_coverage_ip_7d': _nested(context, 'rotation_context', 'bullpen_coverage_ip_7d'),
        }
    if story_type == BEAT_SUSTAINABILITY_QUESTION:
        return {
            'concentration_band': _nested(context, 'bullpen_concentration_context', 'concentration_band'),
            'top_three_workload_share_10d': _nested(context, 'bullpen_concentration_context', 'top_three_workload_share_10d'),
            'league_top_three_workload_share_10d': _nested(context, 'bullpen_concentration_context', 'league_top_three_workload_share_10d'),
            'practical_close_game_paths_count': _nested(context, 'bullpen_optionality_context', 'practical_close_game_paths_count'),
            'clean_workload_options_count': _count(_nested(context, 'bullpen_optionality_context', 'clean_workload_options')),
            'current_operational_core': _names(_nested(context, 'role_stability_context', 'current_operational_core')),
            'top_three_relievers_10d': _names(_nested(context, 'bullpen_concentration_context', 'top_three_relievers_10d')),
        }
    if story_type == BEAT_DEPTH_CONSTRAINT:
        return {
            'depth_pressure_band': _nested(context, 'injury_context', 'depth_pressure_band'),
            'active_bullpen_arms_count': _nested(context, 'injury_context', 'active_bullpen_arms_count'),
            'inactive_bullpen_arms_count': _nested(context, 'injury_context', 'inactive_bullpen_arms_count'),
            'il_bullpen_arms_count': _nested(context, 'injury_context', 'il_bullpen_arms_count'),
            'non_il_inactive_bullpen_arms_count': _nested(context, 'injury_context', 'non_il_inactive_bullpen_arms_count'),
            'practical_close_game_paths_count': _nested(context, 'bullpen_optionality_context', 'practical_close_game_paths_count'),
        }
    if story_type == BEAT_ROUTE_CHANGE:
        return {
            'stability_band': _nested(context, 'role_stability_context', 'stability_band'),
            'core_retention_count': _nested(context, 'role_stability_context', 'core_retention_count'),
            'core_change_count': _nested(context, 'role_stability_context', 'core_change_count'),
            'current_operational_core': _names(_nested(context, 'role_stability_context', 'current_operational_core')),
            'previous_operational_core': _names(_nested(context, 'role_stability_context', 'previous_operational_core')),
            'new_core_members': _names(_nested(context, 'role_stability_context', 'new_core_members')),
            'departed_core_members': _names(_nested(context, 'role_stability_context', 'departed_core_members')),
        }
    if story_type == BEAT_AVAILABILITY_DEPTH:
        return {
            'optionality_band': _nested(context, 'bullpen_optionality_context', 'optionality_band'),
            'practical_close_game_paths_count': _nested(context, 'bullpen_optionality_context', 'practical_close_game_paths_count'),
            'available_arms_count': _nested(context, 'bullpen_optionality_context', 'available_arms_count'),
            'clean_workload_options_count': _count(_nested(context, 'bullpen_optionality_context', 'clean_workload_options')),
            'stability_band': _nested(context, 'role_stability_context', 'stability_band'),
            'core_retention_count': _nested(context, 'role_stability_context', 'core_retention_count'),
        }
    if story_type == BEAT_TRUST_LANE:
        return {
            'available_arms_count': _nested(context, 'bullpen_optionality_context', 'available_arms_count'),
            'clean_workload_options_count': _count(_nested(context, 'bullpen_optionality_context', 'clean_workload_options')),
            'secondary_options_count': _count(_nested(context, 'bullpen_optionality_context', 'secondary_options')),
            'top_three_workload_share_10d': _nested(context, 'bullpen_concentration_context', 'top_three_workload_share_10d'),
            'concentration_band': _nested(context, 'bullpen_concentration_context', 'concentration_band'),
        }
    if story_type == BEAT_BRIDGE:
        return {
            'early_bullpen_entry_rate': _nested(context, 'rotation_context', 'early_bullpen_entry_rate'),
            'bullpen_coverage_ip_7d': _nested(context, 'rotation_context', 'bullpen_coverage_ip_7d'),
            'monitor_arms_count': _nested(context, 'bullpen_optionality_context', 'monitor_arms_count'),
            'limited_arms_count': _nested(context, 'bullpen_optionality_context', 'limited_arms_count'),
            'clean_workload_options_count': _count(_nested(context, 'bullpen_optionality_context', 'clean_workload_options')),
            'stability_band': _nested(context, 'role_stability_context', 'stability_band'),
            'current_operational_core': _names(_nested(context, 'role_stability_context', 'current_operational_core')),
        }
    return {}


def _team_descriptor(payload: dict) -> dict:
    return {
        'team_id': payload.get('team_id'),
        'team_name': payload.get('team_name'),
        'team_abbreviation': payload.get('team_abbreviation'),
    }


def _trace_row(service_payload: dict, canonical_item: dict | None) -> dict:
    selected = _selected_profile(service_payload)
    story_type = (
        _dict(canonical_item).get('story_type')
        or service_payload.get('story_type')
        or selected.get('story_type')
    )
    return {
        'team': _team_descriptor(service_payload),
        'selected_beat': story_type,
        'selected_observation_type': _dict(service_payload.get('selected_observation')).get('type'),
        'selection_strength': int(selected.get('selection_strength') or 0),
        'evidence_completeness': int(selected.get('evidence_completeness') or 0),
        'selection_reasons': list(_list(selected.get('selection_reasons'))),
        'primary_inputs': _primary_inputs_for_beat(
            story_type,
            _dict(service_payload.get('supporting_context')),
        ),
        'candidate_profiles': _candidate_profiles(service_payload),
        'candidate_count': len(_candidate_profiles(service_payload)),
        'fallback_status': _fallback_status(service_payload, canonical_item),
    }


def build_story_selection_trace(*, team_contexts=None, team_ids=None, as_of_date=None) -> dict:
    """Build an internal public-story selection trace.

    Supplied ``team_contexts`` keep tests and audits deterministic. ``team_ids``
    uses the live Story Intelligence context path, so it should be run only in
    explicit diagnostics where the database state is intended input.
    """
    if team_contexts is not None:
        service = build_story_intelligence_service_v1(
            team_contexts=team_contexts,
            as_of_date=as_of_date,
        )
    else:
        service = build_story_intelligence_service_v1(
            team_ids=team_ids or [],
            as_of_date=as_of_date,
        )

    payloads = [
        payload
        for payload in _list(service.get('teams'))
        if isinstance(payload, dict)
    ]
    payload_by_id = {payload.get('team_id'): payload for payload in payloads}
    descriptors = [_team_descriptor(payload) for payload in payloads]

    def story_builder(team_id, as_of_date=None):
        return payload_by_id.get(team_id)

    feed = build_canonical_story_feed(
        descriptors,
        as_of_date=as_of_date or service.get('as_of_date'),
        story_builder=story_builder,
    )
    canonical_by_id = {
        item.get('team_id'): item
        for item in _list(feed.get('items'))
        if isinstance(item, dict)
    }
    rows = [
        _trace_row(payload, canonical_by_id.get(payload.get('team_id')))
        for payload in payloads
    ]
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source_engine': 'story_intelligence_service_v1',
        'public_contract': 'baseballos_canonical_story_v1',
        'as_of_date': as_of_date or service.get('as_of_date'),
        'team_count': len(payloads),
        'story_count': sum(1 for item in _list(feed.get('items')) if _dict(item).get('story_available') is True),
        'beat_distribution': _beat_distribution(_list(feed.get('items'))),
        'generation_paths': list(STORY_GENERATION_PATHS),
        'multiple_selection_paths_present': True,
        'trace': rows,
        'limitations': [
            'internal_diagnostic_only',
            'does_not_change_story_selection',
            'does_not_change_public_api_output',
            'live_team_ids_depend_on_current_database_state',
        ],
    }


__all__ = [
    'CAPABILITY',
    'PATH_CANONICAL_DASHBOARD',
    'PATH_DETERMINISTIC_EDITORIAL_CORPUS',
    'PATH_FOUR_BEAT_AUDIT',
    'PATH_HOME_TODAY',
    'PATH_STORIES_PAGE',
    'PATH_TEAM_PREVIEWS',
    'PATH_TEAM_STORY_API',
    'PATH_TODAY_LEAD_STORY',
    'PUBLIC_BEATS',
    'STORY_GENERATION_PATHS',
    'VERSION',
    'build_story_selection_trace',
]
