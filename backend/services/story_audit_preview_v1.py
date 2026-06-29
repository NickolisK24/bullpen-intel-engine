"""Story Intelligence audit preview V1.

Internal QA helper for inspecting deterministic Story Intelligence output
across teams. This module reads the Story Intelligence Service V1 contract and
adds audit flags only; it does not alter context layers, story selection,
writer output, scoring, public routes, or UI behavior.
"""

from __future__ import annotations

from copy import deepcopy
import re

from models.pitcher import Pitcher
from services.story_four_beat_interpreter_v1 import (
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
)
from services.story_intelligence_service_v1 import (
    build_story_intelligence_service_v1,
)
from services.story_writer_v1 import BANNED_TERMS, ROBOTIC_TERMS
from services.story_voice_library_v1 import DENIED_PUBLIC_PHRASES
from utils.db import db


CAPABILITY = 'story_intelligence_audit_preview_v1'
VERSION = '2026-06-21.v1'
SOURCE = 'backend'

STATE_STORY = 'story'
STATE_NEUTRAL = 'neutral'

SECTION_MAP = {
    'headline': 'headline',
    'observation': 'observation_paragraph',
    'baseline': 'baseline_paragraph',
    'cause': 'cause_paragraph',
    'constraint': 'constraint_paragraph',
}

INTERNAL_TERMS = (
    *ROBOTIC_TERMS,
    'construction frame',
    'construction_frame',
    'selected_observation',
    'writer output',
    'writer_output',
    'trust_metadata',
    'external_generation_used',
    'story_observation_engine',
    'story_construction_engine',
    'story_writer',
)

RAW_INTERNAL_OBSERVATION_TYPES = (
    'rotation_pressure',
    'concentration_pressure',
    'optionality_strength',
    'stable_core',
    'core_transition',
    'depth_pressure',
)

RAW_OBJECT_LITERAL_TERMS = (
    "{'",
    '{"',
    'player_id',
    'status_type',
    'is_on_active_roster',
)

DATABASE_DIFF_TERMS = (
    *DENIED_PUBLIC_PHRASES,
    'core changes',
    'depth picture',
    'forward constraint is',
    'bullpen board',
    'stability rate',
    'active list',
    'available route',
    'outside the active route',
    'per participating reliever',
    'per participating arm',
)

FORWARD_CLAUSE_TERMS = (
    'if ',
    'route points back',
    'fewer ways',
    'late-inning choices',
    'same game shape returns',
    'game shape repeats',
    'workload pattern holds',
)

SHORT_START_CAUSE_TERMS = (
    'shorter starts',
    'starters are not covering',
    'starter length is down',
    'handing the game to the bullpen earlier',
)

COMPETITIVE_SELECTION_STRENGTH = 5
DEFAULT_BOUNDED_LIVE_TEAM_LIMIT = 30

AWKWARD_EMPTY_VALUES = {
    'n/a',
    'na',
    'none',
    'null',
    'not available',
    'unavailable',
}

AWKWARD_PHRASE_PATTERNS = (
    ('sox_possessive', re.compile(r"\b(?:red|white)\s+sox's\b", re.IGNORECASE)),
)

LIMITATIONS = [
    'Internal QA preview only.',
    'Uses Story Intelligence Service V1 output.',
    'Does not change story selection logic.',
    'Does not change context-layer calculations.',
    'Does not change scoring, fatigue, availability, or trust calculations.',
    'Does not create public rankings, predictions, routes, or UI.',
]


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _clean_text(value):
    return ' '.join(str(value or '').strip().split())


def _number(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _name_from_row(row):
    if isinstance(row, str):
        return _clean_text(row)
    return _clean_text(_dict(row).get('name'))


def _names_from(value):
    names = []
    for row in _list(value):
        name = _name_from_row(row)
        if name and name not in names:
            names.append(name)
    return names


def _count_or_none(value):
    if isinstance(value, list):
        return len(value)
    return value


def _iso(value):
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _text_has_any(text, terms):
    lower = _clean_text(text).lower()
    return any(term in lower for term in terms)


def _matched_terms(text, terms):
    lower = _clean_text(text).lower()
    return [
        term
        for term in terms
        if term in lower
    ]


def _default_team_ids(limit=None):
    query = (
        db.session.query(Pitcher.team_id)
        .filter(Pitcher.team_id.isnot(None))
        .distinct()
        .order_by(Pitcher.team_id)
    )
    if limit is not None:
        query = query.limit(limit)
    return [row[0] for row in query.all() if row[0] is not None]


def _limited(values, limit=None):
    rows = list(_list(values))
    if limit is None:
        return rows
    try:
        limit = int(limit)
    except (TypeError, ValueError):
        return rows
    if limit < 1:
        return []
    return rows[:limit]


def _sections(service_payload):
    written = _dict(_dict(service_payload).get('written_story'))
    return {
        public_key: _clean_text(written.get(writer_key)) or None
        for public_key, writer_key in SECTION_MAP.items()
    }


def _visible_text(sections):
    return ' '.join(value for value in _dict(sections).values() if value)


def _missing_required_sections(sections, *, story_available):
    if not story_available:
        return []
    return [
        key
        for key, value in _dict(sections).items()
        if not _clean_text(value)
    ]


def _awkward_empty_sections(service_payload, sections, *, story_available):
    if not story_available:
        return []
    written = _dict(_dict(service_payload).get('written_story'))
    awkward = []
    for public_key, writer_key in SECTION_MAP.items():
        raw_value = written.get(writer_key)
        cleaned = _clean_text(raw_value)
        if isinstance(raw_value, str) and not cleaned:
            awkward.append(public_key)
            continue
        if cleaned.lower() in AWKWARD_EMPTY_VALUES:
            awkward.append(public_key)
    return awkward


def _awkward_phrasing(text):
    cleaned = _clean_text(text)
    return [
        code
        for code, pattern in AWKWARD_PHRASE_PATTERNS
        if pattern.search(cleaned)
    ]


def _constraint_has_forward_clause(sections):
    constraint = _clean_text(_dict(sections).get('constraint'))
    if not constraint:
        return False
    lower = constraint.lower()
    if lower.startswith('if '):
        return True
    return any(term in lower for term in FORWARD_CLAUSE_TERMS)


def _selection_metadata(service_payload):
    return _dict(_dict(service_payload).get('selection_metadata'))


def _candidate_profiles_from_team(team):
    metadata = _dict(team.get('selection_metadata'))
    return _list(metadata.get('candidate_profiles'))


def _selected_profile_from_payload(service_payload):
    return _dict(_selection_metadata(service_payload).get('selected_profile'))


def _selection_outcome(profile, selected_profile):
    profile = _dict(profile)
    selected_profile = _dict(selected_profile)
    if profile.get('selected') is True:
        return 'selected'
    strength = int(profile.get('selection_strength') or 0)
    selected_strength = int(selected_profile.get('selection_strength') or 0)
    if strength <= 0:
        return 'not_selected_no_competitive_evidence'
    if selected_strength > strength:
        return 'not_selected_lower_selection_strength'
    if selected_strength == strength:
        return 'not_selected_tiebreak_or_evidence_completeness'
    return 'not_selected_after_service_sort'


def _eligible_beats(service_payload):
    selected = _selected_profile_from_payload(service_payload)
    rows = []
    for profile in _candidate_profiles_from_team(service_payload):
        profile = _dict(profile)
        rows.append({
            'story_type': profile.get('story_type'),
            'observation_type': profile.get('observation_type'),
            'severity': profile.get('severity'),
            'selection_rank': profile.get('selection_rank'),
            'selection_strength': int(profile.get('selection_strength') or 0),
            'evidence_completeness': int(profile.get('evidence_completeness') or 0),
            'selection_reasons': list(_list(profile.get('selection_reasons'))),
            'selected': profile.get('selected') is True,
            'selection_outcome': _selection_outcome(profile, selected),
        })
    return rows


def _sustainability_profile(service_payload):
    candidates = [
        _dict(profile)
        for profile in _candidate_profiles_from_team(service_payload)
        if _dict(profile).get('story_type') == BEAT_SUSTAINABILITY_QUESTION
    ]
    if not candidates:
        return {}
    return sorted(
        candidates,
        key=lambda profile: (
            int(profile.get('selection_rank') or 999),
            -int(profile.get('selection_strength') or 0),
        ),
    )[0]


def _append_unique(rows, value):
    if value and value not in rows:
        rows.append(value)


def _context_sustainability_evidence(service_payload):
    context = _dict(_dict(service_payload).get('supporting_context'))
    concentration = _dict(context.get('bullpen_concentration_context'))
    optionality = _dict(context.get('bullpen_optionality_context'))
    stability = _dict(context.get('role_stability_context'))
    rotation = _dict(context.get('rotation_context'))

    share = concentration.get('top_three_workload_share_10d')
    band = concentration.get('concentration_band')
    clean_count = _count_or_none(optionality.get('clean_workload_options'))
    paths = optionality.get('practical_close_game_paths_count')
    route_arms = (
        _names_from(stability.get('current_operational_core'))
        or _names_from(concentration.get('top_three_relievers_10d'))
    )
    share_number = _number(share)
    paths_number = _number(paths)
    clean_number = _number(clean_count)
    concentration_elevated = (
        band == 'narrow'
        or (share_number is not None and share_number >= 75.0)
    )
    optionality_limited = (
        (paths_number is not None and paths_number <= 3)
        or (clean_number is not None and clean_number <= 1)
    )
    has_baseline = bool(concentration.get('league_top_three_workload_share_10d'))
    has_cause = (
        rotation.get('rotation_ip_trend') is not None
        or paths is not None
        or clean_count is not None
    )
    has_named_arms = bool(route_arms)
    has_forward_constraint = bool(route_arms)

    suppression_reasons = []
    if not concentration_elevated:
        suppression_reasons.append('insufficient_concentration')
    if not optionality_limited:
        suppression_reasons.append('insufficient_optionality_constraint')
    if not has_named_arms:
        suppression_reasons.append('missing_named_arms')
    if not has_forward_constraint:
        suppression_reasons.append('missing_forward_route_names')
    if not has_baseline:
        suppression_reasons.append('missing_baseline')
    if not has_cause:
        suppression_reasons.append('missing_cause')

    evidence_present = (
        concentration_elevated
        and optionality_limited
        and has_named_arms
        and has_forward_constraint
    )
    return {
        'sustainability_evidence_present': evidence_present,
        'top_three_workload_share_10d': share,
        'concentration_band': band,
        'clean_workload_options_count': clean_count,
        'practical_close_game_paths_count': paths,
        'repeated_route_core_arms': route_arms,
        'optionality_band': optionality.get('optionality_band'),
        'rotation_pressure': {
            'rotation_avg_ip_7d': rotation.get('rotation_avg_ip_7d'),
            'rotation_avg_ip_14d': rotation.get('rotation_avg_ip_14d'),
            'rotation_ip_trend': rotation.get('rotation_ip_trend'),
            'early_bullpen_entry_rate': rotation.get('early_bullpen_entry_rate'),
            'bullpen_coverage_ip_7d': rotation.get('bullpen_coverage_ip_7d'),
        },
        'has_named_arms': has_named_arms,
        'has_baseline': has_baseline,
        'has_cause': has_cause,
        'has_forward_constraint': has_forward_constraint,
        'suppression_reasons': suppression_reasons,
        'source': 'supporting_context',
    }


def _sustainability_suppression_reasons(profile, service_payload, evidence=None):
    profile = _dict(profile)
    evidence = _dict(evidence) or _dict(profile.get('sustainability_evidence'))
    reasons = list(_list(evidence.get('suppression_reasons')))
    if not profile:
        _append_unique(reasons, 'no_sustainability_candidate')
        return reasons

    selected_beat = _dict(service_payload).get('story_type')
    selected = _selected_profile_from_payload(service_payload)
    if selected_beat == BEAT_SUSTAINABILITY_QUESTION or profile.get('selected') is True:
        return reasons

    selected_strength = int(selected.get('selection_strength') or 0)
    strength = int(profile.get('selection_strength') or 0)
    if selected_strength >= strength:
        if selected_beat == BEAT_DEPTH_CONSTRAINT:
            _append_unique(reasons, 'stronger_depth_constraint')
        elif selected_beat == BEAT_ROUTE_CHANGE:
            _append_unique(reasons, 'stronger_route_change')
        elif selected_beat == BEAT_COVERAGE_PRESSURE:
            _append_unique(reasons, 'stronger_coverage_pressure')
        else:
            _append_unique(reasons, 'stronger_selected_beat')
    return reasons


def _sustainability_diagnostics(service_payload):
    payload = _dict(service_payload)
    profile = _sustainability_profile(payload)
    evidence = _dict(profile.get('sustainability_evidence')) or _context_sustainability_evidence(payload)
    rotation_pressure = _dict(evidence.get('rotation_pressure'))
    return {
        'candidate_present': bool(profile),
        'selected': payload.get('story_type') == BEAT_SUSTAINABILITY_QUESTION,
        'selection_strength': (
            int(profile.get('selection_strength') or 0)
            if profile else 0
        ),
        'selection_reasons': list(_list(profile.get('selection_reasons'))),
        'selection_outcome': (
            _selection_outcome(profile, _selected_profile_from_payload(payload))
            if profile else 'not_selected_no_candidate'
        ),
        'sustainability_evidence_present': bool(
            evidence.get('sustainability_evidence_present')
        ),
        'top_three_workload_share_10d': evidence.get('top_three_workload_share_10d'),
        'concentration_band': evidence.get('concentration_band'),
        'clean_workload_options_count': evidence.get('clean_workload_options_count'),
        'practical_close_game_paths_count': evidence.get('practical_close_game_paths_count'),
        'repeated_route_core_arms': list(_list(evidence.get('repeated_route_core_arms'))),
        'optionality_band': evidence.get('optionality_band'),
        'rotation_pressure': rotation_pressure,
        'has_named_arms': bool(evidence.get('has_named_arms')),
        'has_baseline': bool(evidence.get('has_baseline')),
        'has_cause': bool(evidence.get('has_cause')),
        'has_forward_constraint': bool(evidence.get('has_forward_constraint')),
        'missing_baseline_or_cause': bool(
            'missing_baseline' in _list(evidence.get('suppression_reasons'))
            or 'missing_cause' in _list(evidence.get('suppression_reasons'))
        ),
        'suppression_reasons': _sustainability_suppression_reasons(
            profile,
            payload,
            evidence=evidence,
        ),
    }


def _short_start_cause_omitted(service_payload, sections):
    payload = _dict(service_payload)
    if payload.get('story_type') != BEAT_COVERAGE_PRESSURE:
        return False
    selected = _dict(_selection_metadata(payload).get('selected_profile'))
    if int(selected.get('selection_strength') or 0) <= 0:
        return False
    cause = _clean_text(_dict(sections).get('cause')).lower()
    return not any(term in cause for term in SHORT_START_CAUSE_TERMS)


def _validation_flags(service_payload, sections, *, story_available):
    text = _visible_text(sections)
    writer_validation = _dict(_dict(service_payload).get('writer_output')).get('validation')
    writer_validation = _dict(writer_validation)
    missing = _missing_required_sections(sections, story_available=story_available)
    awkward = _awkward_empty_sections(
        service_payload,
        sections,
        story_available=story_available,
    )
    awkward_phrasing = _awkward_phrasing(text) if story_available else []
    has_banned = bool(writer_validation.get('contains_banned_language')) or _text_has_any(
        text,
        BANNED_TERMS,
    )
    has_internal = bool(writer_validation.get('contains_robotic_language')) or _text_has_any(
        text,
        INTERNAL_TERMS,
    )
    raw_internal_terms = _matched_terms(text, RAW_INTERNAL_OBSERVATION_TYPES)
    raw_object_terms = _matched_terms(text, RAW_OBJECT_LITERAL_TERMS)
    database_diff_terms = _matched_terms(text, DATABASE_DIFF_TERMS)
    missing_forward_clause = (
        story_available
        and 'constraint' not in missing
        and not _constraint_has_forward_clause(sections)
    )
    short_start_cause_omitted = (
        story_available
        and _short_start_cause_omitted(service_payload, sections)
    )
    return {
        'has_internal_terms': has_internal,
        'has_banned_language': has_banned,
        'raw_internal_observation_terms': raw_internal_terms,
        'has_raw_object_literal': bool(raw_object_terms),
        'raw_object_terms': raw_object_terms,
        'database_diff_terms': database_diff_terms,
        'missing_forward_constraint_clause': missing_forward_clause,
        'short_start_cause_omitted': short_start_cause_omitted,
        'missing_required_sections': missing,
        'awkward_empty_sections': awkward,
        'awkward_phrasing': awkward_phrasing,
        'needs_review': bool(
            has_internal
            or has_banned
            or raw_internal_terms
            or raw_object_terms
            or database_diff_terms
            or missing_forward_clause
            or short_start_cause_omitted
            or missing
            or awkward
            or awkward_phrasing
        ),
    }


def _preview_team(service_payload):
    payload = _dict(service_payload)
    story_available = bool(payload.get('story_available'))
    sections = _sections(payload) if story_available else {
        key: None for key in SECTION_MAP
    }
    flags = _validation_flags(payload, sections, story_available=story_available)
    return {
        'team_id': payload.get('team_id'),
        'team_name': payload.get('team_name'),
        'team_abbreviation': payload.get('team_abbreviation'),
        'state': STATE_STORY if story_available else STATE_NEUTRAL,
        'service_state': payload.get('state'),
        'story_available': story_available,
        'story_type': payload.get('story_type') if story_available else None,
        'headline': sections.get('headline'),
        'sections': sections,
        'freshness': deepcopy(_dict(payload.get('freshness'))),
        'trust_metadata': deepcopy(_dict(payload.get('trust_metadata'))),
        'selection_metadata': deepcopy(_dict(payload.get('selection_metadata'))),
        'eligible_beats': _eligible_beats(payload),
        'sustainability_diagnostics': _sustainability_diagnostics(payload),
        'neutral_reason': payload.get('neutral_reason') if not story_available else None,
        'validation_flags': flags,
        'limitations': list(_list(payload.get('limitations'))),
    }


def _state_counts(teams):
    return {
        STATE_STORY: sum(1 for team in teams if team.get('state') == STATE_STORY),
        STATE_NEUTRAL: sum(1 for team in teams if team.get('state') == STATE_NEUTRAL),
        'needs_review': sum(
            1
            for team in teams
            if _dict(team.get('validation_flags')).get('needs_review')
        ),
    }


def _story_type_counts(teams):
    counts = {}
    for team in teams:
        story_type = team.get('story_type')
        if not story_type:
            continue
        counts[story_type] = counts.get(story_type, 0) + 1
    return counts


def _story_type_distribution(story_type_counts):
    total = sum(story_type_counts.values())
    if not total:
        return []
    return [
        {
            'story_type': story_type,
            'count': count,
            'share_of_story_states': round((count / total) * 100, 1),
        }
        for story_type, count in sorted(
            story_type_counts.items(),
            key=lambda item: (-item[1], item[0]),
        )
    ]


def _strong_candidate_count(teams, story_type):
    return sum(
        1
        for team in teams
        if any(
            _dict(profile).get('story_type') == story_type
            and int(_dict(profile).get('selection_strength') or 0) >= COMPETITIVE_SELECTION_STRENGTH
            and (
                story_type != BEAT_SUSTAINABILITY_QUESTION
                or _dict(_dict(profile).get('sustainability_evidence')).get(
                    'sustainability_evidence_present'
                ) is True
            )
            for profile in _candidate_profiles_from_team(team)
        )
    )


def _selection_balance_flags(teams, story_type_counts):
    flags = []
    coverage_candidates = _strong_candidate_count(teams, BEAT_COVERAGE_PRESSURE)
    sustainability_candidates = _strong_candidate_count(teams, BEAT_SUSTAINABILITY_QUESTION)
    if coverage_candidates > 0 and not story_type_counts.get(BEAT_COVERAGE_PRESSURE):
        flags.append({
            'code': 'coverage_evidence_present_but_never_selected',
            'candidate_team_count': coverage_candidates,
        })
    if sustainability_candidates > 0 and not story_type_counts.get(BEAT_SUSTAINABILITY_QUESTION):
        flags.append({
            'code': 'sustainability_evidence_present_but_never_selected',
            'candidate_team_count': sustainability_candidates,
        })
    return flags


def _audit_preview_from_service_payload(service_payload, *, as_of_date=None):
    service_payload = _dict(service_payload)
    teams = [
        _preview_team(team)
        for team in _list(service_payload.get('teams'))
    ]
    story_type_counts = _story_type_counts(teams)
    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'source': SOURCE,
        'as_of_date': _iso(as_of_date) or service_payload.get('as_of_date'),
        'team_count': len(teams),
        'state_counts': _state_counts(teams),
        'story_type_counts': story_type_counts,
        'story_type_distribution': _story_type_distribution(story_type_counts),
        'selection_balance_flags': _selection_balance_flags(teams, story_type_counts),
        'teams': teams,
        'limitations': [*LIMITATIONS, *_list(service_payload.get('limitations'))],
    }


def build_story_audit_preview(*, team_ids=None, team_contexts=None, as_of_date=None, limit=None):
    """
    Build an internal Story Intelligence QA preview.

    If team_contexts are supplied, they are passed through the service directly.
    If team_ids are supplied, those ids are evaluated in deterministic team-id
    order. If neither is supplied, all known DB team ids are evaluated, with an
    optional limit for lightweight review runs.
    """
    if team_contexts is not None:
        selected_contexts = _limited(team_contexts, limit=limit)
        service_payload = build_story_intelligence_service_v1(
            team_contexts=selected_contexts,
            as_of_date=as_of_date,
        )
    else:
        selected_ids = _limited(
            team_ids if team_ids is not None else _default_team_ids(limit=limit),
            limit=limit if team_ids is not None else None,
        )
        service_payload = build_story_intelligence_service_v1(
            team_ids=selected_ids,
            as_of_date=as_of_date,
        )

    return _audit_preview_from_service_payload(service_payload, as_of_date=as_of_date)


def build_bounded_live_story_audit_preview(
    *,
    team_ids=None,
    as_of_date=None,
    limit=DEFAULT_BOUNDED_LIVE_TEAM_LIMIT,
):
    """Build the current stored-data audit preview with an explicit team cap."""

    selected_ids = _limited(
        team_ids if team_ids is not None else _default_team_ids(limit=limit),
        limit=limit,
    )
    service_payload = build_story_intelligence_service_v1(
        team_ids=selected_ids,
        as_of_date=as_of_date,
    )
    return {
        'mode': 'bounded_live_current_stored_data',
        'limit': int(limit or 0),
        'team_ids': selected_ids,
        'service_payload': service_payload,
        'audit_preview': _audit_preview_from_service_payload(
            service_payload,
            as_of_date=as_of_date,
        ),
        'limitations': [
            'uses_current_stored_data_only',
            'caps_team_scope_before_story_generation',
            'does_not_start_sync',
            'does_not_change_story_selection',
        ],
    }


__all__ = [
    'CAPABILITY',
    'INTERNAL_TERMS',
    'DATABASE_DIFF_TERMS',
    'RAW_INTERNAL_OBSERVATION_TYPES',
    'RAW_OBJECT_LITERAL_TERMS',
    'SECTION_MAP',
    'STATE_NEUTRAL',
    'STATE_STORY',
    'VERSION',
    'build_bounded_live_story_audit_preview',
    'build_story_audit_preview',
]
