"""Internal review for Consequence Intelligence V1.

This module builds deterministic all-team evidence for consequence review. It
is internal only: no public UI contract, recommendations, predictions, rankings,
probability language, betting language, or tactical guidance.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.bullpen_identity import IDENTITY_LABELS
from services.consequence_intelligence import (
    STATE_NO_CONSEQUENCES,
    build_consequence_intelligence_payload,
)
from services.what_changed_since_yesterday import (
    STATE_NO_MEANINGFUL_CHANGES,
    STATUS_AVAILABLE as CHANGE_STATUS_AVAILABLE,
    build_what_changed_since_yesterday_payload,
)
from services.what_changed_since_yesterday_review import (
    current_data_through_date,
    payload_snapshot_metadata,
    snapshot_record_metadata,
)


CAPABILITY = 'consequence_intelligence_review_v1'
VERSION = '2026-06-19.v1'
DEFAULT_EXPECTED_TEAM_COUNT = 30

TOO_MANY_CONSEQUENCES_THRESHOLD = 4
LOW_CONFIDENCE_VALUES = {'none', 'unknown', 'low'}

RECOMMENDATION_PATTERNS = (
    'recommend',
    'recommendation',
    'should use',
    'should pitch',
    'must use',
    'manager should',
)
PREDICTION_PATTERNS = (
    'predict',
    'prediction',
    'projected',
    'expected to',
    'likely to',
    'forecast',
)
RANKING_PATTERNS = (
    'ranking',
    'ranked',
    'best reliever',
    'best bullpen',
    'worst bullpen',
    'top-ranked',
)
BETTING_PATTERNS = (
    'bet',
    'betting',
    'odds',
    'wager',
)
PROBABILITY_PATTERNS = (
    'probability',
    'probable',
    'percent chance',
    'chance to',
    'likelihood',
)
RELIEVER_SELECTION_PATTERNS = (
    'should use',
    'must use',
    'manager should',
    'which reliever',
    'specific reliever',
    'use the closer',
)
RAW_SCORE_PATTERNS = (
    'raw_score',
    'raw score',
    'score:',
    'score =',
)
GENERIC_CONSEQUENCE_TEXT = {
    'this matters.',
    'the bullpen changed.',
    'the situation changed.',
    'there is a consequence.',
}


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _int(value: Any, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _iso_datetime(value: datetime | None = None) -> str:
    stamp = value or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def _team_sort_key(item: dict[str, Any]):
    return (
        str(item.get('team_abbreviation') or '').lower(),
        str(item.get('team_name') or '').lower(),
        _int(item.get('team_id')),
    )


def _team_key(item: dict[str, Any] | None) -> str | None:
    item = item or {}
    team_id = item.get('team_id') or item.get('teamId')
    if team_id is not None:
        return str(team_id)
    abbr = item.get('team_abbreviation') or item.get('teamAbbreviation') or item.get('team')
    return str(abbr).lower() if abbr else None


def _teams_by_key(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(payload, dict):
        return {}
    by_team = payload.get('by_team_id')
    if isinstance(by_team, dict):
        return {
            str(key): value
            for key, value in by_team.items()
            if isinstance(value, dict)
        }
    teams = payload.get('teams')
    if isinstance(teams, list):
        return {
            str(_team_key(team)): team
            for team in teams
            if isinstance(team, dict) and _team_key(team) is not None
        }
    return {}


def _facts(item: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(item, dict):
        return []
    facts = item.get('supporting_facts')
    return [
        fact
        for fact in (facts if isinstance(facts, list) else [])
        if isinstance(fact, dict)
    ]


def _text(value: Any) -> str:
    return str(value or '').strip()


def _consequence_texts(consequences: list[dict[str, Any]]) -> list[str]:
    texts = []
    for consequence in consequences:
        texts.extend([
            _text(consequence.get('consequence_summary')),
            _text(consequence.get('consequence_context')),
        ])
    return [text for text in texts if text]


def _word_count(value: str | None) -> int:
    return len(re.findall(r'\b\S+\b', value or ''))


def _contains_any(texts: list[str], patterns: tuple[str, ...]) -> bool:
    combined = '\n'.join(texts).lower()
    return any(pattern in combined for pattern in patterns)


def _identity_label_leaked(texts: list[str]) -> bool:
    combined = '\n'.join(texts).lower()
    labels = {str(label).lower() for label in IDENTITY_LABELS.values()}
    labels.update(str(key).lower() for key in IDENTITY_LABELS)
    return any(label and label in combined for label in labels)


def _fact_matches(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left.get('fact_key') == right.get('fact_key')
        and left.get('previous_value') == right.get('previous_value')
        and left.get('current_value') == right.get('current_value')
    )


def _related_change(
    consequence: dict[str, Any] | None,
    changes: list[dict[str, Any]],
) -> dict[str, Any] | None:
    consequence_facts = _facts(consequence)
    if not consequence_facts:
        return None
    for change in changes:
        change_facts = _facts(change)
        if any(
            _fact_matches(consequence_fact, change_fact)
            for consequence_fact in consequence_facts
            for change_fact in change_facts
        ):
            return change
    return None


def _is_generic_consequence(consequence: dict[str, Any]) -> bool:
    summary = _text(consequence.get('consequence_summary'))
    context = _text(consequence.get('consequence_context'))
    normalized_summary = summary.lower()
    normalized_context = context.lower()
    if normalized_summary in GENERIC_CONSEQUENCE_TEXT:
        return True
    if normalized_context in GENERIC_CONSEQUENCE_TEXT:
        return True
    return _word_count(summary) <= 4 and _word_count(context) <= 7


def _initial_review_flags(
    *,
    consequences: list[dict[str, Any]],
    primary_consequence: dict[str, Any] | None,
    meaningful_changes: list[dict[str, Any]],
) -> list[str]:
    flags = []
    texts = _consequence_texts(consequences)

    if not primary_consequence:
        flags.append('no_consequence')
    if len(consequences) > TOO_MANY_CONSEQUENCES_THRESHOLD:
        flags.append('too_many_consequences')
    if primary_consequence and _norm(primary_consequence.get('confidence')) in LOW_CONFIDENCE_VALUES:
        flags.append('low_confidence_primary')
    if primary_consequence and not meaningful_changes:
        flags.append('consequence_without_meaningful_change')
    if any(_is_generic_consequence(consequence) for consequence in consequences):
        flags.append('consequence_too_generic')

    if _contains_any(texts, PREDICTION_PATTERNS):
        flags.append('prediction_language')
    if _contains_any(texts, RECOMMENDATION_PATTERNS):
        flags.append('recommendation_language')
    if _contains_any(texts, RANKING_PATTERNS):
        flags.append('ranking_language')
    if _contains_any(texts, BETTING_PATTERNS):
        flags.append('betting_language')
    if _contains_any(texts, PROBABILITY_PATTERNS):
        flags.append('probability_language')
    if _contains_any(texts, RELIEVER_SELECTION_PATTERNS):
        flags.append('reliever_selection_language')
    if _contains_any(texts, RAW_SCORE_PATTERNS):
        flags.append('raw_score_leak')
    if _identity_label_leaked(texts):
        flags.append('identity_label_leak')

    return flags


def _team_review_item(
    consequence_team: dict[str, Any],
    *,
    what_changed_team: dict[str, Any] | None,
    current_snapshot: dict[str, Any],
    prior_snapshot: dict[str, Any],
) -> dict[str, Any]:
    consequences = list(consequence_team.get('consequences') or [])
    primary = consequences[0] if consequences else None
    meaningful_changes = list((what_changed_team or {}).get('changes') or [])
    related_change = _related_change(primary, meaningful_changes)
    comparison_available = (what_changed_team or {}).get('status') == CHANGE_STATUS_AVAILABLE

    return {
        'team_id': consequence_team.get('team_id'),
        'team_abbreviation': consequence_team.get('team_abbreviation'),
        'team_name': consequence_team.get('team_name'),
        'current_snapshot': current_snapshot,
        'prior_snapshot': prior_snapshot,
        'comparison_available': comparison_available,
        'primary_consequence': primary,
        'primary_consequence_selection_basis': (
            'first_consequence_in_engine_order_not_ranked'
            if primary
            else None
        ),
        'all_consequences': consequences,
        'consequence_type': (primary or {}).get('consequence_type'),
        'consequence_summary': (primary or {}).get('consequence_summary'),
        'consequence_context': (primary or {}).get('consequence_context'),
        'significance': (primary or {}).get('significance'),
        'confidence': (primary or {}).get('confidence') or (
            'medium' if comparison_available else 'none'
        ),
        'supporting_facts': _facts(primary),
        'related_what_changed_item': related_change,
        'all_meaningful_changes': meaningful_changes,
        'what_changed_state': {
            'status': (what_changed_team or {}).get('status'),
            'state': (what_changed_team or {}).get('state'),
            'change_count': (what_changed_team or {}).get('change_count', 0),
            'limitations': list((what_changed_team or {}).get('limitations') or []),
        },
        'consequence_state': {
            'status': consequence_team.get('status'),
            'state': consequence_team.get('state'),
            'consequence_count': consequence_team.get('consequence_count', 0),
            'limitations': list(consequence_team.get('limitations') or []),
        },
        'review_flags': _initial_review_flags(
            consequences=consequences,
            primary_consequence=primary,
            meaningful_changes=meaningful_changes,
        ),
    }


def _repeated_counts(teams: list[dict[str, Any]], field: str) -> dict[str, int]:
    counts = Counter(
        consequence.get(field)
        for team in teams
        for consequence in team.get('all_consequences') or []
        if consequence.get(field)
    )
    return {
        text: count
        for text, count in sorted(counts.items())
        if count > 1
    }


def _apply_repeated_flags(teams: list[dict[str, Any]]) -> tuple[dict[str, int], dict[str, int]]:
    repeated_summaries = _repeated_counts(teams, 'consequence_summary')
    repeated_contexts = _repeated_counts(teams, 'consequence_context')
    for team in teams:
        summaries = {
            consequence.get('consequence_summary')
            for consequence in team.get('all_consequences') or []
        }
        contexts = {
            consequence.get('consequence_context')
            for consequence in team.get('all_consequences') or []
        }
        if summaries.intersection(repeated_summaries):
            team['review_flags'].append('repeated_summary')
        if contexts.intersection(repeated_contexts):
            team['review_flags'].append('repeated_context')
    return repeated_summaries, repeated_contexts


def _distribution_summary(
    teams: list[dict[str, Any]],
    *,
    repeated_summary_counts: dict[str, int],
    repeated_context_counts: dict[str, int],
) -> dict[str, Any]:
    consequence_types = Counter()
    consequence_significance = Counter()
    flags = Counter()

    for team in teams:
        for consequence in team.get('all_consequences') or []:
            consequence_types[consequence.get('consequence_type') or 'unknown'] += 1
            consequence_significance[consequence.get('significance') or 'unknown'] += 1
        for flag in team.get('review_flags') or []:
            flags[flag] += 1

    return {
        'teams_reviewed': len(teams),
        'teams_with_comparison_available': sum(
            1
            for team in teams
            if team.get('comparison_available')
        ),
        'teams_with_primary_consequence': sum(
            1
            for team in teams
            if team.get('primary_consequence')
        ),
        'teams_without_consequence': sum(
            1
            for team in teams
            if not team.get('primary_consequence')
        ),
        'consequence_counts_by_type': {
            key: consequence_types[key]
            for key in sorted(consequence_types)
        },
        'consequence_counts_by_significance': {
            key: consequence_significance[key]
            for key in sorted(consequence_significance)
        },
        'review_flag_counts': {
            flag: flags[flag]
            for flag in sorted(flags)
        },
        'repeated_summary_counts': repeated_summary_counts,
        'repeated_context_counts': repeated_context_counts,
        'teams_for_human_review': [
            {
                'team_id': team.get('team_id'),
                'team_abbreviation': team.get('team_abbreviation'),
                'team_name': team.get('team_name'),
                'primary_consequence_type': team.get('consequence_type'),
                'review_flags': team.get('review_flags') or [],
            }
            for team in teams
            if team.get('review_flags')
        ],
    }


def build_consequence_intelligence_review(
    current_payload: dict[str, Any] | None,
    prior_payload: dict[str, Any] | None,
    *,
    what_changed_payload: dict[str, Any] | None = None,
    consequence_payload: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
    expected_team_count: int = DEFAULT_EXPECTED_TEAM_COUNT,
    current_snapshot_metadata: dict[str, Any] | None = None,
    prior_snapshot_metadata: dict[str, Any] | None = None,
    current_payload_source: str = 'live_dashboard_build',
    prior_payload_source: str = 'ready_dashboard_snapshot_before_current_data_through',
) -> dict[str, Any]:
    """Build a deterministic all-team Consequence Intelligence V1 review artifact."""

    if what_changed_payload is None:
        what_changed_payload = build_what_changed_since_yesterday_payload(
            current_payload,
            prior_payload,
        )
    if consequence_payload is None:
        consequence_payload = build_consequence_intelligence_payload(
            current_payload,
            prior_payload,
            what_changed_payload=what_changed_payload,
        )

    current_snapshot = payload_snapshot_metadata(
        current_payload,
        source=current_payload_source,
        snapshot_metadata=current_snapshot_metadata,
    )
    prior_snapshot = payload_snapshot_metadata(
        prior_payload,
        source=(
            prior_payload_source
            if prior_payload is not None
            else 'missing_prior_dashboard_snapshot'
        ),
        snapshot_metadata=prior_snapshot_metadata,
    )
    what_changed_by_team = _teams_by_key(what_changed_payload)
    teams = sorted(
        (
            _team_review_item(
                team,
                what_changed_team=what_changed_by_team.get(str(_team_key(team))),
                current_snapshot=current_snapshot,
                prior_snapshot=prior_snapshot,
            )
            for team in consequence_payload.get('teams') or []
        ),
        key=_team_sort_key,
    )
    repeated_summaries, repeated_contexts = _apply_repeated_flags(teams)
    summary = _distribution_summary(
        teams,
        repeated_summary_counts=repeated_summaries,
        repeated_context_counts=repeated_contexts,
    )

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'generated_at': _iso_datetime(generated_at),
        'source': 'backend',
        'current_payload_source': current_payload_source,
        'prior_payload_source': prior_snapshot.get('source'),
        'prior_snapshot_source_used': prior_snapshot.get('source'),
        'expected_team_count': expected_team_count,
        'team_count': len(teams),
        'complete_team_count': len(teams) == expected_team_count,
        'ordering_basis': 'team_abbreviation_then_team_name',
        'primary_consequence_selection_basis': 'first_consequence_in_engine_order_not_ranked',
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'comparison': {
            'current_snapshot': current_snapshot,
            'prior_snapshot': prior_snapshot,
            'current_data_through': current_snapshot.get('data_through'),
            'prior_data_through': prior_snapshot.get('data_through'),
            'comparison_available': summary['teams_with_comparison_available'] > 0,
        },
        'what_changed_payload_state': {
            'status': what_changed_payload.get('status'),
            'state': what_changed_payload.get('state'),
            'limitations': list(what_changed_payload.get('limitations') or []),
        },
        'consequence_payload_state': {
            'status': consequence_payload.get('status'),
            'state': consequence_payload.get('state'),
            'limitations': list(consequence_payload.get('limitations') or []),
        },
        'distribution_summary': summary,
        'teams': teams,
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
    'VERSION',
    'build_consequence_intelligence_review',
    'current_data_through_date',
    'snapshot_record_metadata',
    'write_json_report',
]
