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
VERSION = '2026-06-29.e1g'

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

MISSING_BEAT_REVIEW_TARGETS = (
    BEAT_BRIDGE,
    BEAT_TRUST_LANE,
    BEAT_SUSTAINABILITY_QUESTION,
)

CONTEXT_SIGNAL_ACCURACY_REVIEW_SIGNALS = (
    'stable_late_core_detection',
    'starter_handoff_demand',
    'bridge_thinness',
    'available_arms_counts',
    'flagged_secondary_option_counts',
    'trusted_lane_thinness',
    'concentration_pressure_observations',
    'concentration_band_calculations',
    'optionality_constraint_inputs',
)

CONTEXT_SIGNAL_EXPECTED = 'expected_from_current_data'
CONTEXT_SIGNAL_SUSPICIOUS = 'suspicious_but_explainable'
CONTEXT_SIGNAL_LIKELY_INCORRECT = 'likely_incorrect'
CONTEXT_SIGNAL_UNREACHABLE = 'unreachable_due_to_bug_or_key_mismatch'

CONTEXT_SIGNAL_CLASSIFICATIONS = (
    CONTEXT_SIGNAL_EXPECTED,
    CONTEXT_SIGNAL_SUSPICIOUS,
    CONTEXT_SIGNAL_LIKELY_INCORRECT,
    CONTEXT_SIGNAL_UNREACHABLE,
)

_CLASSIFICATION_SEVERITY = {
    CONTEXT_SIGNAL_EXPECTED: 0,
    CONTEXT_SIGNAL_SUSPICIOUS: 1,
    CONTEXT_SIGNAL_UNREACHABLE: 2,
    CONTEXT_SIGNAL_LIKELY_INCORRECT: 3,
}

_CONTEXT_SIGNAL_BLOCKERS = {
    'stable_late_core_detection': {'late_core_not_settled'},
    'starter_handoff_demand': {'no_starter_handoff_demand'},
    'bridge_thinness': {'bridge_not_thin'},
    'available_arms_counts': {
        'missing_available_count',
        'insufficient_available_arms',
    },
    'flagged_secondary_option_counts': {'insufficient_flagged_secondary_options'},
    'trusted_lane_thinness': {'trusted_lane_not_thin'},
    'concentration_pressure_observations': {'no_concentration_pressure_observation'},
    'concentration_band_calculations': {'insufficient_concentration'},
    'optionality_constraint_inputs': {'insufficient_optionality_constraint'},
}

_CONTEXT_SIGNAL_RAW_KEYS = {
    'stable_late_core_detection': (
        'stability_band',
        'core_retention_count',
        'core_stability_pct',
        'core_change_count',
        'current_core_size',
        'previous_core_size',
    ),
    'starter_handoff_demand': (
        'rotation_context_available',
        'early_bullpen_entry_rate',
        'bullpen_coverage_ip_7d',
    ),
    'bridge_thinness': (
        'optionality_context_available',
        'clean_workload_options_count',
    ),
    'available_arms_counts': (
        'optionality_context_available',
        'available_arms_count',
    ),
    'flagged_secondary_option_counts': (
        'optionality_context_available',
        'secondary_options_count',
    ),
    'trusted_lane_thinness': (
        'optionality_context_available',
        'clean_workload_options_count',
    ),
    'concentration_pressure_observations': (
        'concentration_band',
        'top_three_workload_share_10d',
    ),
    'concentration_band_calculations': (
        'concentration_band',
        'top_three_workload_share_10d',
    ),
    'optionality_constraint_inputs': (
        'optionality_context_available',
        'practical_close_game_paths_count',
        'clean_workload_options_count',
    ),
}


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


def _number(value: Any):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


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


def _profile_for_beat(payload: dict, beat: str) -> dict:
    return next(
        (
            profile
            for profile in _candidate_profiles(payload)
            if profile.get('story_type') == beat
        ),
        {},
    )


def _loss_reason(profile: dict, selected: dict) -> str | None:
    profile = _dict(profile)
    if not profile:
        return None
    if profile.get('selected') is True:
        return None
    selected = _dict(selected)
    strength = int(profile.get('selection_strength') or 0)
    selected_strength = int(selected.get('selection_strength') or 0)
    if selected_strength > strength:
        return 'lost_lower_selection_strength'
    if selected_strength == strength:
        return 'lost_tiebreak_or_evidence_completeness'
    return 'lost_after_service_sort'


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


def _source_inputs_for_missing_beat(beat: str, context: dict) -> dict:
    if beat == BEAT_BRIDGE:
        return _primary_inputs_for_beat(BEAT_BRIDGE, context)
    if beat == BEAT_TRUST_LANE:
        return _primary_inputs_for_beat(BEAT_TRUST_LANE, context)
    if beat == BEAT_SUSTAINABILITY_QUESTION:
        return _primary_inputs_for_beat(BEAT_SUSTAINABILITY_QUESTION, context) | {
            'rotation_ip_trend': _nested(context, 'rotation_context', 'rotation_ip_trend'),
            'early_bullpen_entry_rate': _nested(context, 'rotation_context', 'early_bullpen_entry_rate'),
        }
    return {}


def _bridge_blockers(context: dict) -> list[str]:
    rotation = _dict(context.get('rotation_context'))
    optionality = _dict(context.get('bullpen_optionality_context'))
    stability = _dict(context.get('role_stability_context'))
    early_rate = _number(rotation.get('early_bullpen_entry_rate'))
    coverage_ip = _number(rotation.get('bullpen_coverage_ip_7d'))
    monitor = int(_number(optionality.get('monitor_arms_count')) or 0)
    limited = int(_number(optionality.get('limited_arms_count')) or 0)
    clean_count = len(_list(optionality.get('clean_workload_options')))

    blockers = []
    if stability.get('stability_band') != 'stable':
        blockers.append('late_core_not_settled')
    if optionality.get('context_available') is not True:
        blockers.append('optionality_context_unavailable')
    if rotation.get('context_available') is False:
        blockers.append('rotation_context_unavailable')
    if not (
        (early_rate is not None and early_rate >= 35.0)
        or (coverage_ip is not None and coverage_ip >= 3.8)
    ):
        blockers.append('no_starter_handoff_demand')
    if monitor + limited < 2:
        blockers.append('insufficient_volatile_middle')
    if clean_count > 2:
        blockers.append('bridge_not_thin')
    return blockers


def _trust_lane_blockers(context: dict) -> list[str]:
    optionality = _dict(context.get('bullpen_optionality_context'))
    available = _number(optionality.get('available_arms_count'))
    clean_count = len(_list(optionality.get('clean_workload_options')))
    secondary_count = len(_list(optionality.get('secondary_options')))

    blockers = []
    if optionality.get('context_available') is not True:
        blockers.append('optionality_context_unavailable')
    if available is None:
        blockers.append('missing_available_count')
    elif available < 4:
        blockers.append('insufficient_available_arms')
    if clean_count > 2:
        blockers.append('trusted_lane_not_thin')
    if secondary_count < 3:
        blockers.append('insufficient_flagged_secondary_options')
    return blockers


def _sustainability_blockers(context: dict) -> list[str]:
    rotation = _dict(context.get('rotation_context'))
    concentration = _dict(context.get('bullpen_concentration_context'))
    optionality = _dict(context.get('bullpen_optionality_context'))
    stability = _dict(context.get('role_stability_context'))
    band = concentration.get('concentration_band')
    share = _number(concentration.get('top_three_workload_share_10d'))
    paths = _number(optionality.get('practical_close_game_paths_count'))
    clean_count = len(_list(optionality.get('clean_workload_options')))
    trend = _number(rotation.get('rotation_ip_trend'))
    early_rate = _number(rotation.get('early_bullpen_entry_rate'))
    route_arms = (
        _names(stability.get('current_operational_core'))
        or _names(concentration.get('top_three_relievers_10d'))
    )

    blockers = []
    if band not in {'concentrated', 'narrow'}:
        blockers.append('no_concentration_pressure_observation')
    if (
        (trend is not None and trend <= -0.5)
        or (early_rate is not None and early_rate >= 40.0)
    ):
        blockers.append('concentration_mapped_to_coverage_pressure')
    if not (band == 'narrow' or (share is not None and share >= 75.0)):
        blockers.append('insufficient_concentration')
    if not ((paths is not None and paths <= 3) or clean_count <= 1):
        blockers.append('insufficient_optionality_constraint')
    if not route_arms:
        blockers.append('missing_named_arms')
    if not concentration.get('league_top_three_workload_share_10d'):
        blockers.append('missing_baseline')
    if not (
        rotation.get('rotation_ip_trend') is not None
        or paths is not None
        or clean_count is not None
    ):
        blockers.append('missing_cause')
    return blockers


def _missing_beat_blockers(beat: str, context: dict) -> list[str]:
    if beat == BEAT_BRIDGE:
        return _bridge_blockers(context)
    if beat == BEAT_TRUST_LANE:
        return _trust_lane_blockers(context)
    if beat == BEAT_SUSTAINABILITY_QUESTION:
        return _sustainability_blockers(context)
    return []


def _missing_beat_team_review(payload: dict, trace_row: dict, beat: str) -> dict:
    context = _dict(payload.get('supporting_context'))
    profile = _profile_for_beat(payload, beat)
    selected = _selected_profile(payload)
    blockers = _missing_beat_blockers(beat, context)
    source_evidence_present = not blockers
    eligible_candidate = bool(profile)
    filtered_reason = (
        'source_evidence_present_but_no_public_candidate'
        if source_evidence_present and not eligible_candidate
        else None
    )
    return {
        'team': _team_descriptor(payload),
        'selected_beat': trace_row.get('selected_beat'),
        'source_evidence_present': source_evidence_present,
        'eligible_candidate': eligible_candidate,
        'candidate_selected': profile.get('selected') is True if profile else False,
        'candidate_score': (
            int(profile.get('selection_strength') or 0)
            if profile else None
        ),
        'candidate_rank': profile.get('selection_rank') if profile else None,
        'selected_score': int(selected.get('selection_strength') or 0),
        'loss_reason': _loss_reason(profile, selected),
        'filtered_reason': filtered_reason,
        'blocker_reasons': blockers,
        'source_inputs': _source_inputs_for_missing_beat(beat, context),
    }


def _missing_beat_evidence_review(payloads: list[dict], trace_rows: list[dict]) -> dict:
    rows_by_id = {
        _dict(row.get('team')).get('team_id'): row
        for row in trace_rows
        if isinstance(row, dict)
    }
    review = {}
    for beat in MISSING_BEAT_REVIEW_TARGETS:
        team_rows = [
            _missing_beat_team_review(
                payload,
                _dict(rows_by_id.get(payload.get('team_id'))),
                beat,
            )
            for payload in payloads
        ]
        blocker_counts = Counter(
            blocker
            for row in team_rows
            for blocker in _list(row.get('blocker_reasons'))
        )
        loss_counts = Counter(
            row.get('loss_reason')
            for row in team_rows
            if row.get('loss_reason')
        )
        filter_counts = Counter(
            row.get('filtered_reason')
            for row in team_rows
            if row.get('filtered_reason')
        )
        scores = [
            int(row.get('candidate_score'))
            for row in team_rows
            if row.get('candidate_score') is not None
        ]
        review[beat] = {
            'candidate_evidence_team_count': sum(
                1 for row in team_rows if row.get('source_evidence_present')
            ),
            'eligible_candidate_team_count': sum(
                1 for row in team_rows if row.get('eligible_candidate')
            ),
            'selected_team_count': sum(
                1 for row in team_rows if row.get('candidate_selected')
            ),
            'lost_selection_team_count': sum(
                1 for row in team_rows if row.get('loss_reason')
            ),
            'filtered_candidate_team_count': sum(
                1 for row in team_rows if row.get('filtered_reason')
            ),
            'top_candidate_score': max(scores) if scores else None,
            'lost_selection_reason_counts': {
                reason: loss_counts[reason]
                for reason in sorted(loss_counts)
            },
            'filtered_reason_counts': {
                reason: filter_counts[reason]
                for reason in sorted(filter_counts)
            },
            'source_blocker_reason_counts': {
                reason: blocker_counts[reason]
                for reason in sorted(blocker_counts)
            },
            'teams': team_rows,
        }
    return review


def _context_signal_raw_values(context: dict) -> dict:
    rotation = _dict(context.get('rotation_context'))
    optionality = _dict(context.get('bullpen_optionality_context'))
    stability = _dict(context.get('role_stability_context'))
    concentration = _dict(context.get('bullpen_concentration_context'))
    return {
        'rotation_context_available': rotation.get('context_available'),
        'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
        'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        'optionality_context_available': optionality.get('context_available'),
        'available_arms_count': optionality.get('available_arms_count'),
        'monitor_arms_count': optionality.get('monitor_arms_count'),
        'limited_arms_count': optionality.get('limited_arms_count'),
        'clean_workload_options_count': len(
            _list(optionality.get('clean_workload_options'))
        ),
        'secondary_options_count': len(_list(optionality.get('secondary_options'))),
        'practical_close_game_paths_count': optionality.get(
            'practical_close_game_paths_count'
        ),
        'optionality_band': optionality.get('optionality_band'),
        'stability_context_available': stability.get('context_available'),
        'stability_band': stability.get('stability_band'),
        'core_retention_count': stability.get('core_retention_count'),
        'core_stability_pct': stability.get('core_stability_pct'),
        'core_change_count': stability.get('core_change_count'),
        'current_core_size': stability.get('current_core_size'),
        'previous_core_size': stability.get('previous_core_size'),
        'concentration_context_available': concentration.get('context_available'),
        'concentration_band': concentration.get('concentration_band'),
        'top_three_workload_share_10d': concentration.get(
            'top_three_workload_share_10d'
        ),
        'league_top_three_workload_share_10d': concentration.get(
            'league_top_three_workload_share_10d'
        ),
        'qualifying_reliever_count_10d': concentration.get(
            'qualifying_reliever_count_10d'
        ),
    }


def _expected_concentration_band(share):
    share = _number(share)
    if share is None:
        return 'insufficient_data'
    if share < 55.0:
        return 'balanced'
    if share <= 65.0:
        return 'normal'
    if share <= 80.0:
        return 'concentrated'
    return 'narrow'


def _has_blocker(blockers_by_beat: dict, reason: str) -> bool:
    return any(
        reason in _list(reasons)
        for reasons in _dict(blockers_by_beat).values()
    )


def _classify_context_signal(
    signal: str,
    raw: dict,
    blockers_by_beat: dict,
) -> str:
    if signal == 'stable_late_core_detection':
        band = raw.get('stability_band')
        pct = _number(raw.get('core_stability_pct'))
        change_count = _number(raw.get('core_change_count'))
        retention = _number(raw.get('core_retention_count'))
        current_size = _number(raw.get('current_core_size'))
        late_core_blocked = _has_blocker(blockers_by_beat, 'late_core_not_settled')
        if band is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if band == 'stable':
            if late_core_blocked or (pct is not None and pct < 100.0) or change_count:
                return CONTEXT_SIGNAL_LIKELY_INCORRECT
            return CONTEXT_SIGNAL_EXPECTED
        if not late_core_blocked:
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        if (
            pct is not None
            and pct >= 100.0
            and change_count == 0
            and retention is not None
            and current_size is not None
            and retention >= current_size
        ):
            return CONTEXT_SIGNAL_SUSPICIOUS
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'starter_handoff_demand':
        early_rate = _number(raw.get('early_bullpen_entry_rate'))
        coverage_ip = _number(raw.get('bullpen_coverage_ip_7d'))
        no_demand = _has_blocker(blockers_by_beat, 'no_starter_handoff_demand')
        demand_present = (
            (early_rate is not None and early_rate >= 35.0)
            or (coverage_ip is not None and coverage_ip >= 3.8)
        )
        if early_rate is None and coverage_ip is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if no_demand == demand_present:
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'bridge_thinness':
        clean_count = _number(raw.get('clean_workload_options_count'))
        not_thin = _has_blocker(blockers_by_beat, 'bridge_not_thin')
        if clean_count is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if not_thin != (clean_count > 2):
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'available_arms_counts':
        available = _number(raw.get('available_arms_count'))
        if available is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if _has_blocker(blockers_by_beat, 'missing_available_count'):
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        if _has_blocker(blockers_by_beat, 'insufficient_available_arms') != (
            available < 4
        ):
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'flagged_secondary_option_counts':
        secondary = _number(raw.get('secondary_options_count'))
        if secondary is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if _has_blocker(
            blockers_by_beat,
            'insufficient_flagged_secondary_options',
        ) != (secondary < 3):
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'trusted_lane_thinness':
        clean_count = _number(raw.get('clean_workload_options_count'))
        not_thin = _has_blocker(blockers_by_beat, 'trusted_lane_not_thin')
        if clean_count is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if not_thin != (clean_count > 2):
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'concentration_pressure_observations':
        band = raw.get('concentration_band')
        no_pressure = _has_blocker(
            blockers_by_beat,
            'no_concentration_pressure_observation',
        )
        pressure_observed = band in {'concentrated', 'narrow'}
        if band is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if no_pressure == pressure_observed:
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'concentration_band_calculations':
        band = raw.get('concentration_band')
        share = _number(raw.get('top_three_workload_share_10d'))
        if band is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        if band != _expected_concentration_band(share):
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    if signal == 'optionality_constraint_inputs':
        paths = _number(raw.get('practical_close_game_paths_count'))
        clean_count = _number(raw.get('clean_workload_options_count'))
        insufficient = _has_blocker(
            blockers_by_beat,
            'insufficient_optionality_constraint',
        )
        if paths is None or clean_count is None:
            return CONTEXT_SIGNAL_UNREACHABLE
        constraint_present = paths <= 3 or clean_count <= 1
        if insufficient == constraint_present:
            return CONTEXT_SIGNAL_LIKELY_INCORRECT
        return CONTEXT_SIGNAL_EXPECTED

    return CONTEXT_SIGNAL_SUSPICIOUS


def _context_signal_team_review(payload: dict, trace_row: dict) -> dict:
    context = _dict(payload.get('supporting_context'))
    blockers_by_beat = {
        BEAT_BRIDGE: _bridge_blockers(context),
        BEAT_TRUST_LANE: _trust_lane_blockers(context),
        BEAT_SUSTAINABILITY_QUESTION: _sustainability_blockers(context),
    }
    raw = _context_signal_raw_values(context)
    classifications = {
        signal: _classify_context_signal(signal, raw, blockers_by_beat)
        for signal in CONTEXT_SIGNAL_ACCURACY_REVIEW_SIGNALS
    }
    return {
        'team': _team_descriptor(payload),
        'selected_beat': trace_row.get('selected_beat'),
        'raw_values': raw,
        'blockers_by_missing_beat': blockers_by_beat,
        'signal_classifications': classifications,
    }


def _value_key(value: Any) -> str:
    if value is None:
        return 'null'
    if value is True:
        return 'true'
    if value is False:
        return 'false'
    return str(value)


def _raw_value_counts(rows: list[dict], raw_keys: tuple[str, ...]) -> dict:
    counts = {}
    for key in raw_keys:
        counter = Counter(
            _value_key(_dict(row.get('raw_values')).get(key))
            for row in rows
        )
        counts[key] = {
            value: int(counter[value])
            for value in sorted(counter)
        }
    return counts


def _numeric_range(rows: list[dict], raw_keys: tuple[str, ...]) -> dict:
    ranges = {}
    for key in raw_keys:
        values = [
            _number(_dict(row.get('raw_values')).get(key))
            for row in rows
        ]
        values = [value for value in values if value is not None]
        if values:
            ranges[key] = {
                'min': min(values),
                'max': max(values),
            }
    return ranges


def _signal_blocker_counts(rows: list[dict], signal: str) -> dict:
    target_blockers = _CONTEXT_SIGNAL_BLOCKERS[signal]
    counter = Counter()
    for row in rows:
        for blockers in _dict(row.get('blockers_by_missing_beat')).values():
            for blocker in _list(blockers):
                if blocker in target_blockers:
                    counter[blocker] += 1
    return {
        blocker: int(counter[blocker])
        for blocker in sorted(counter)
    }


def _worst_classification(classifications: Counter) -> str:
    if not classifications:
        return CONTEXT_SIGNAL_EXPECTED
    return max(
        classifications,
        key=lambda classification: (
            _CLASSIFICATION_SEVERITY.get(classification, 0),
            classification,
        ),
    )


def _context_signal_rows_for_signal(rows: list[dict], signal: str) -> list[dict]:
    raw_keys = _CONTEXT_SIGNAL_RAW_KEYS[signal]
    target_blockers = _CONTEXT_SIGNAL_BLOCKERS[signal]
    signal_rows = []
    for row in rows:
        blockers = sorted({
            blocker
            for blockers_for_beat in _dict(row.get('blockers_by_missing_beat')).values()
            for blocker in _list(blockers_for_beat)
            if blocker in target_blockers
        })
        raw_values = _dict(row.get('raw_values'))
        signal_rows.append({
            'team': row.get('team'),
            'selected_beat': row.get('selected_beat'),
            'classification': _dict(row.get('signal_classifications')).get(signal),
            'blocker_reasons': blockers,
            'raw_values': {
                key: raw_values.get(key)
                for key in raw_keys
            },
        })
    return signal_rows


def _context_signal_accuracy_review(
    payloads: list[dict],
    trace_rows: list[dict],
) -> dict:
    rows_by_id = {
        _dict(row.get('team')).get('team_id'): row
        for row in trace_rows
        if isinstance(row, dict)
    }
    rows = [
        _context_signal_team_review(
            payload,
            _dict(rows_by_id.get(payload.get('team_id'))),
        )
        for payload in payloads
    ]
    review = {}
    for signal in CONTEXT_SIGNAL_ACCURACY_REVIEW_SIGNALS:
        raw_keys = _CONTEXT_SIGNAL_RAW_KEYS[signal]
        classifications = Counter(
            _dict(row.get('signal_classifications')).get(signal)
            for row in rows
        )
        review[signal] = {
            'classification': _worst_classification(classifications),
            'team_count': len(rows),
            'classification_counts': {
                classification: int(classifications.get(classification, 0))
                for classification in CONTEXT_SIGNAL_CLASSIFICATIONS
                if classifications.get(classification, 0)
            },
            'blocker_reason_counts': _signal_blocker_counts(rows, signal),
            'raw_value_counts': _raw_value_counts(rows, raw_keys),
            'numeric_ranges': _numeric_range(rows, raw_keys),
            'teams': _context_signal_rows_for_signal(rows, signal),
        }
    return review


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


def build_story_selection_trace_from_service_payload(
    service_payload: dict,
    *,
    as_of_date=None,
) -> dict:
    """Build a canonical selection trace from an existing service payload."""

    service = _dict(service_payload)
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
        'missing_beat_evidence_review': _missing_beat_evidence_review(payloads, rows),
        'context_signal_accuracy_review': _context_signal_accuracy_review(
            payloads,
            rows,
        ),
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
    return build_story_selection_trace_from_service_payload(
        service,
        as_of_date=as_of_date,
    )


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
    'CONTEXT_SIGNAL_ACCURACY_REVIEW_SIGNALS',
    'CONTEXT_SIGNAL_CLASSIFICATIONS',
    'MISSING_BEAT_REVIEW_TARGETS',
    'STORY_GENERATION_PATHS',
    'VERSION',
    'build_story_selection_trace',
    'build_story_selection_trace_from_service_payload',
]
