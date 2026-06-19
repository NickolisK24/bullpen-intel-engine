"""Internal Bullpen Identity V1 distribution review.

This module builds a deterministic review artifact from existing dashboard
capacity intelligence. It is internal evidence only: no public UI contract,
recommendations, predictions, team ranking, or tactical guidance.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from services.bullpen_coverage_safety import (
    LABEL_LIMITED,
    LABEL_LIMITED_READ,
    LABEL_THIN,
    build_bullpen_coverage_safety_read,
)
from services.bullpen_identity import (
    IDENTITY_FRAGILE_COVERAGE,
    IDENTITY_RESOURCE_STRAINED,
    IDENTITY_UNKNOWN,
    STRUCTURAL_SCOPE_CAVEAT,
    TACTICAL_BOUNDARY_CAVEAT,
    build_bullpen_identity,
)


CAPABILITY = 'bullpen_identity_distribution_review_v1'
VERSION = '2026-06-19.v1'
DEFAULT_EXPECTED_TEAM_COUNT = 30

UNKNOWN_REVIEW_SHARE = 0.20
OVERREPRESENTED_IDENTITY_SHARE = 0.45
THIN_OR_STRAINED_SHARE = 0.40
REPEATED_CAVEAT_SHARE = 0.50


def _get(mapping: dict[str, Any] | None, *keys, default=None):
    current = mapping or {}
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return current if current is not None else default


def _norm(value: Any) -> str:
    return str(value or '').strip().lower()


def _slug(value: Any) -> str | None:
    text = _norm(value)
    if not text:
        return None
    return '_'.join(text.replace('/', ' ').replace('-', ' ').split())


def _int(value: Any, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _iso(value: datetime | None = None) -> str:
    stamp = value or datetime.now(timezone.utc)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc).isoformat()


def _team_sort_key(item: dict[str, Any]):
    return (
        str(item.get('team_name') or item.get('team_abbreviation') or '').lower(),
        _int(item.get('team_id')),
    )


def _capacity_items(dashboard_payload: dict[str, Any]) -> list[dict[str, Any]]:
    capacity = dashboard_payload.get('capacity_intelligence') or {}
    items = list(capacity.get('teams') or [])
    if items:
        return items
    return list((capacity.get('by_team_id') or {}).values())


def _coverage_read(capacity_item: dict[str, Any]) -> dict[str, Any]:
    read = build_bullpen_coverage_safety_read(capacity_item)
    return read if isinstance(read, dict) else {}


def _identity(capacity_item: dict[str, Any]) -> dict[str, Any]:
    existing = capacity_item.get('bullpen_identity')
    if isinstance(existing, dict) and existing:
        return existing
    return build_bullpen_identity(capacity_item)


def _trust_structure_summary(trust_hierarchy: dict[str, Any]) -> str:
    anchor = _int(trust_hierarchy.get('anchor_count'))
    leverage = _int(trust_hierarchy.get('leverage_count'))
    trusted = _int(trust_hierarchy.get('trusted_count'))
    depth = _int(trust_hierarchy.get('depth_count'))
    trusted_group = _int(
        trust_hierarchy.get('trusted_group_size'),
        default=anchor + leverage + trusted,
    )
    confidence = trust_hierarchy.get('hierarchy_confidence') or 'unknown'
    return (
        f'{anchor} anchors, {leverage} leverage arms, {trusted} trusted arms, '
        f'{depth} depth arms, {trusted_group} trusted-group arms; hierarchy confidence {confidence}.'
    )


def _context(capacity_item: dict[str, Any], coverage_read: dict[str, Any]) -> dict[str, Any]:
    resource_health = capacity_item.get('resource_health') or {}
    bullpen_capacity = resource_health.get('bullpen_capacity') or {}
    organizational = resource_health.get('organizational_resource_health') or {}
    trust_hierarchy = capacity_item.get('trust_hierarchy') or {}
    coverage_label = coverage_read.get('label')

    return {
        'capacity_state': (
            bullpen_capacity.get('capacity_state')
            or bullpen_capacity.get('state')
            or resource_health.get('capacity_state')
        ),
        'resource_health_state': (
            organizational.get('resource_health_state')
            or organizational.get('state')
            or resource_health.get('resource_health_state')
        ),
        'coverage_safety': {
            'state': _slug(coverage_label),
            'label': coverage_label,
            'limitations': _list(coverage_read.get('limitations')),
        },
        'trust_structure': {
            'summary': _trust_structure_summary(trust_hierarchy),
            'anchor_count': _int(trust_hierarchy.get('anchor_count')),
            'leverage_count': _int(trust_hierarchy.get('leverage_count')),
            'trusted_count': _int(trust_hierarchy.get('trusted_count')),
            'depth_count': _int(trust_hierarchy.get('depth_count')),
            'unknown_count': _int(trust_hierarchy.get('unknown_count')),
            'trusted_group_size': _int(trust_hierarchy.get('trusted_group_size')),
            'top_trust_bucket_available_count': _int(
                trust_hierarchy.get('top_trust_bucket_available_count')
            ),
            'hierarchy_confidence': trust_hierarchy.get('hierarchy_confidence'),
        },
    }


def _incomplete_context(identity: dict[str, Any], context: dict[str, Any]) -> bool:
    caveat_text = ' '.join(str(item or '').lower() for item in identity.get('caveats') or [])
    return (
        identity.get('identity_key') == IDENTITY_UNKNOWN
        or context.get('capacity_state') in {None, '', 'unknown'}
        or context.get('resource_health_state') in {None, '', 'unknown'}
        or _get(context, 'coverage_safety', 'label') == LABEL_LIMITED_READ
        or any(term in caveat_text for term in ('missing', 'unknown', 'incomplete', 'limited'))
    )


def _team_review_flags(identity: dict[str, Any], context: dict[str, Any]) -> list[str]:
    flags = []
    identity_key = identity.get('identity_key')
    confidence = _norm(identity.get('confidence'))
    coverage_label = _get(context, 'coverage_safety', 'label')
    caveat_count = len(identity.get('caveats') or [])

    if identity_key == IDENTITY_UNKNOWN:
        flags.append('unknown_identity')
    if confidence in {'none', 'low'}:
        flags.append('low_confidence')
    if identity_key in {IDENTITY_FRAGILE_COVERAGE, IDENTITY_RESOURCE_STRAINED}:
        flags.append('thin_or_resource_strained_identity')
    if not coverage_label or coverage_label in {LABEL_LIMITED_READ, LABEL_LIMITED, LABEL_THIN}:
        flags.append('coverage_needs_review')
    if caveat_count > 4:
        flags.append('many_caveats')
    if confidence == 'high' and _incomplete_context(identity, context):
        flags.append('high_confidence_with_incomplete_context')

    return flags


def _team_item(capacity_item: dict[str, Any]) -> dict[str, Any]:
    identity = _identity(capacity_item)
    coverage_read = _coverage_read(capacity_item)
    context = _context(capacity_item, coverage_read)

    return {
        'team_id': capacity_item.get('team_id'),
        'team_name': capacity_item.get('team_name'),
        'team_abbreviation': capacity_item.get('team_abbreviation'),
        'identity_key': identity.get('identity_key'),
        'identity_label': identity.get('identity_label'),
        'identity_summary': identity.get('identity_summary'),
        'supporting_traits': identity.get('supporting_traits') or [],
        'caveats': identity.get('caveats') or [],
        'confidence': identity.get('confidence'),
        'context': context,
        'review_flags': _team_review_flags(identity, context),
    }


def _distribution(teams: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(team.get('identity_label') or 'Unknown / Insufficient Context' for team in teams)
    return {
        label: counts[label]
        for label in sorted(counts)
    }


def _caveat_distribution(teams: list[dict[str, Any]]) -> dict[str, int]:
    caveats = Counter()
    for team in teams:
        for caveat in team.get('caveats') or []:
            if caveat in {STRUCTURAL_SCOPE_CAVEAT, TACTICAL_BOUNDARY_CAVEAT}:
                continue
            caveats[str(caveat)] += 1
    return {
        caveat: caveats[caveat]
        for caveat in sorted(caveats)
    }


def _review_findings(
    teams: list[dict[str, Any]],
    distribution: dict[str, int],
    caveat_distribution: dict[str, int],
) -> dict[str, Any]:
    team_count = len(teams)
    unknown_count = sum(1 for team in teams if team.get('identity_key') == IDENTITY_UNKNOWN)
    thin_or_strained_count = sum(
        1
        for team in teams
        if team.get('identity_key') in {IDENTITY_FRAGILE_COVERAGE, IDENTITY_RESOURCE_STRAINED}
    )
    denominator = max(team_count, 1)

    return {
        'unknown_identity_count': unknown_count,
        'unknown_identity_review_threshold': UNKNOWN_REVIEW_SHARE,
        'unknown_identity_over_threshold': (unknown_count / denominator) > UNKNOWN_REVIEW_SHARE,
        'overrepresented_identity_threshold': OVERREPRESENTED_IDENTITY_SHARE,
        'overrepresented_identity_labels': [
            label
            for label, count in distribution.items()
            if (count / denominator) > OVERREPRESENTED_IDENTITY_SHARE
        ],
        'thin_or_resource_strained_count': thin_or_strained_count,
        'thin_or_resource_strained_review_threshold': THIN_OR_STRAINED_SHARE,
        'thin_or_resource_strained_over_threshold': (
            thin_or_strained_count / denominator
        ) > THIN_OR_STRAINED_SHARE,
        'high_confidence_with_incomplete_context_teams': [
            team['team_abbreviation']
            for team in teams
            if 'high_confidence_with_incomplete_context' in team.get('review_flags', [])
        ],
        'repeated_non_boundary_caveat_threshold': REPEATED_CAVEAT_SHARE,
        'repeated_non_boundary_caveats': [
            caveat
            for caveat, count in caveat_distribution.items()
            if (count / denominator) > REPEATED_CAVEAT_SHARE
        ],
        'teams_for_human_review': [
            {
                'team_id': team.get('team_id'),
                'team_name': team.get('team_name'),
                'team_abbreviation': team.get('team_abbreviation'),
                'identity_label': team.get('identity_label'),
                'review_flags': team.get('review_flags') or [],
            }
            for team in teams
            if team.get('review_flags')
        ],
    }


def build_bullpen_identity_distribution_review(
    dashboard_payload: dict[str, Any],
    *,
    generated_at: datetime | None = None,
    expected_team_count: int = DEFAULT_EXPECTED_TEAM_COUNT,
    payload_source: str = 'live_dashboard_build',
) -> dict[str, Any]:
    """Build a deterministic all-team Bullpen Identity V1 review artifact."""

    teams = sorted(
        (_team_item(item) for item in _capacity_items(dashboard_payload or {})),
        key=_team_sort_key,
    )
    distribution = _distribution(teams)
    caveats = _caveat_distribution(teams)
    findings = _review_findings(teams, distribution, caveats)

    return {
        'capability': CAPABILITY,
        'version': VERSION,
        'generated_at': _iso(generated_at),
        'source': 'backend',
        'payload_source': payload_source,
        'expected_team_count': expected_team_count,
        'team_count': len(teams),
        'complete_team_count': len(teams) == expected_team_count,
        'ordering_basis': 'team_name_then_team_id',
        'ranking_applied': False,
        'selection_made': False,
        'prediction_applied': False,
        'identity_distribution': distribution,
        'non_boundary_caveat_distribution': caveats,
        'review_findings': findings,
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
    'build_bullpen_identity_distribution_review',
    'write_json_report',
]
