"""Internal real-output quality audit for public four-beat stories.

This module summarizes Story Intelligence audit preview output. It only reads
existing story payloads and validation flags; it does not alter selection,
context, scoring, fatigue, availability, trust, or public UI behavior.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from services.story_four_beat_interpreter_v1 import (
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_ROUTE_CHANGE,
    BEAT_SUSTAINABILITY_QUESTION,
)


CAPABILITY = 'four_beat_real_quality_audit_v1'
VERSION = '2026-06-21.v1'
DEFAULT_EXPECTED_TEAM_COUNT = 30

PUBLIC_BEATS = (
    BEAT_ROUTE_CHANGE,
    BEAT_COVERAGE_PRESSURE,
    BEAT_DEPTH_CONSTRAINT,
    BEAT_SUSTAINABILITY_QUESTION,
)

BOOL_FLAG_KEYS = (
    'has_internal_terms',
    'has_banned_language',
    'has_raw_object_literal',
    'missing_forward_constraint_clause',
    'short_start_cause_omitted',
    'needs_review',
)

LIST_FLAG_KEYS = (
    'raw_internal_observation_terms',
    'database_diff_terms',
    'missing_required_sections',
    'awkward_empty_sections',
    'awkward_phrasing',
)


def _dict(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _clean_text(value):
    return ' '.join(str(value or '').strip().split())


def _iso_datetime(value: datetime | None = None):
    stamp = value or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def _team_sort_key(team):
    return (
        str(team.get('team_name') or team.get('team_abbreviation') or '').lower(),
        int(team.get('team_id') or 0),
    )


def _story_teams(audit_preview):
    return [
        team
        for team in _list(_dict(audit_preview).get('teams'))
        if team.get('state') == 'story'
    ]


def _story_text(team):
    sections = _dict(team.get('sections'))
    return ' '.join(
        _clean_text(sections.get(key))
        for key in ('headline', 'observation', 'baseline', 'cause', 'constraint')
        if sections.get(key)
    )


def _flag_codes(team):
    flags = _dict(team.get('validation_flags'))
    codes = []
    for key in BOOL_FLAG_KEYS:
        if flags.get(key):
            codes.append(key)
    for key in LIST_FLAG_KEYS:
        if _list(flags.get(key)):
            codes.append(key)
    return codes


def _issue_counts(teams):
    counts = Counter()
    term_counts = {
        'raw_internal_observation_terms': Counter(),
        'database_diff_terms': Counter(),
        'awkward_phrasing': Counter(),
    }
    for team in teams:
        flags = _dict(team.get('validation_flags'))
        for key in BOOL_FLAG_KEYS:
            if flags.get(key):
                counts[key] += 1
        for key in LIST_FLAG_KEYS:
            values = _list(flags.get(key))
            if values:
                counts[key] += 1
            if key in term_counts:
                term_counts[key].update(values)

    return {
        'team_flag_counts': {
            key: counts[key]
            for key in sorted(counts)
        },
        'term_counts': {
            key: {
                term: counter[term]
                for term in sorted(counter)
            }
            for key, counter in term_counts.items()
            if counter
        },
    }


def _beat_distribution(audit_preview):
    counts = _dict(_dict(audit_preview).get('story_type_counts'))
    story_total = sum(int(count or 0) for count in counts.values())
    rows = []
    for beat in PUBLIC_BEATS:
        count = int(counts.get(beat) or 0)
        rows.append({
            'story_type': beat,
            'count': count,
            'share_of_story_states': (
                round((count / story_total) * 100, 1)
                if story_total else 0.0
            ),
        })
    return rows


def _unexpected_story_types(audit_preview):
    counts = _dict(_dict(audit_preview).get('story_type_counts'))
    return [
        story_type
        for story_type in sorted(counts)
        if story_type not in PUBLIC_BEATS
    ]


def _example(team, *, review_basis=None):
    return {
        'team_id': team.get('team_id'),
        'team_name': team.get('team_name'),
        'team_abbreviation': team.get('team_abbreviation'),
        'story_type': team.get('story_type'),
        'headline': team.get('headline'),
        'sections': _dict(team.get('sections')),
        'review_flags': _flag_codes(team),
        'review_basis': review_basis,
    }


def _worst_examples(teams, *, limit=5):
    flagged = [
        team
        for team in teams
        if _flag_codes(team)
    ]
    rows = sorted(
        flagged,
        key=lambda team: (-len(_flag_codes(team)), *_team_sort_key(team)),
    )
    if rows:
        return [
            _example(team, review_basis='flagged_quality_issue')
            for team in rows[:limit]
        ]
    rows = sorted(
        teams,
        key=lambda team: (-len(_story_text(team)), *_team_sort_key(team)),
    )
    return [
        _example(team, review_basis='longest_clean_output_no_post_fix_flags')
        for team in rows[:limit]
    ]


def _strongest_examples(teams, *, limit=5):
    clean = [
        team
        for team in teams
        if not _flag_codes(team) and all(_dict(team.get('sections')).values())
    ]
    rows = sorted(clean, key=_team_sort_key)
    return [
        _example(team, review_basis='complete_clean_story')
        for team in rows[:limit]
    ]


def _repetition_summary(teams):
    headline_counts = Counter(_clean_text(team.get('headline')) for team in teams if team.get('headline'))
    story_counts = Counter(_story_text(team) for team in teams if _story_text(team))
    return {
        'repeated_headline_count': sum(1 for team in teams if headline_counts[_clean_text(team.get('headline'))] > 1),
        'repeated_story_text_count': sum(1 for team in teams if story_counts[_story_text(team)] > 1),
        'repeated_headlines': {
            headline: count
            for headline, count in sorted(headline_counts.items())
            if count > 1
        },
    }


def _sustainability_summary(teams):
    reason_counts = Counter()
    evidence_teams = []
    candidate_count = 0
    evidence_present_count = 0
    selected_count = 0
    for team in teams:
        diagnostics = _dict(team.get('sustainability_diagnostics'))
        if diagnostics.get('candidate_present'):
            candidate_count += 1
        if diagnostics.get('sustainability_evidence_present'):
            evidence_present_count += 1
            evidence_teams.append({
                'team_id': team.get('team_id'),
                'team_name': team.get('team_name'),
                'team_abbreviation': team.get('team_abbreviation'),
            })
        if team.get('story_type') == BEAT_SUSTAINABILITY_QUESTION:
            selected_count += 1
        reason_counts.update(_list(diagnostics.get('suppression_reasons')))

    return {
        'candidate_count': candidate_count,
        'evidence_present_count': evidence_present_count,
        'selected_count': selected_count,
        'suppressed_by_reason': {
            reason: reason_counts[reason]
            for reason in sorted(reason_counts)
        },
        'teams_with_sustainability_evidence': evidence_teams,
    }


def _team_selection_audit(teams):
    rows = []
    for team in teams:
        rows.append({
            'team_id': team.get('team_id'),
            'team_name': team.get('team_name'),
            'team_abbreviation': team.get('team_abbreviation'),
            'state': team.get('state'),
            'selected_beat': team.get('story_type'),
            'eligible_beats': list(_list(team.get('eligible_beats'))),
            'sustainability_diagnostics': _dict(team.get('sustainability_diagnostics')),
        })
    return rows


def build_four_beat_real_quality_audit(
    audit_preview,
    *,
    generated_at=None,
    expected_team_count=DEFAULT_EXPECTED_TEAM_COUNT,
    payload_source='story_audit_preview_v1',
    initial_audit_summary=None,
    initial_findings=None,
    fixes_applied=None,
):
    """Build a compact review artifact from Story Intelligence audit preview output."""

    audit_preview = _dict(audit_preview)
    teams = sorted(_list(audit_preview.get('teams')), key=_team_sort_key)
    story_teams = _story_teams(audit_preview)
    state_counts = _dict(audit_preview.get('state_counts'))
    unexpected_types = _unexpected_story_types(audit_preview)
    issue_counts = _issue_counts(story_teams)

    post_fix_summary = {
        'team_count': len(teams),
        'story_count': len(story_teams),
        'neutral_count': int(state_counts.get('neutral') or 0),
        'needs_review_count': int(state_counts.get('needs_review') or 0),
        'beat_distribution': _beat_distribution(audit_preview),
        'unexpected_story_types': unexpected_types,
        'selection_balance_flags': list(_list(audit_preview.get('selection_balance_flags'))),
        'flagged_issue_counts': issue_counts,
        'repetition_summary': _repetition_summary(story_teams),
        'sustainability_summary': _sustainability_summary(teams),
    }

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'generated_at': _iso_datetime(generated_at),
        'source': 'backend',
        'payload_source': payload_source,
        'audit_preview_capability': audit_preview.get('capability'),
        'expected_team_count': expected_team_count,
        'team_count': len(teams),
        'complete_team_count': len(teams) == expected_team_count,
        'public_story_types_allowed': list(PUBLIC_BEATS),
        'unexpected_story_type_count': len(unexpected_types),
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'calculation_boundaries': {
            'scoring_changes': False,
            'fatigue_changes': False,
            'availability_changes': False,
            'trust_changes': False,
            'context_layer_formula_changes': False,
            'prediction_system_added': False,
            'llm_integration_added': False,
        },
        'initial_audit_summary': _dict(initial_audit_summary),
        'initial_findings': list(initial_findings or []),
        'fixes_applied': list(fixes_applied or []),
        'post_fix_summary': post_fix_summary,
        'team_selection_audit': _team_selection_audit(teams),
        'worst_story_outputs': _worst_examples(story_teams),
        'strongest_story_outputs': _strongest_examples(story_teams),
    }


def write_json_report(report: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    return path


__all__ = [
    'CAPABILITY',
    'DEFAULT_EXPECTED_TEAM_COUNT',
    'PUBLIC_BEATS',
    'VERSION',
    'build_four_beat_real_quality_audit',
    'write_json_report',
]
