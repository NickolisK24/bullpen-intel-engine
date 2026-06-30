"""Read-only editorial corpus for pitcher/team context explanation surfaces.

E2D-1 is an audit/export phase. This module reads current stored data through
the existing explanation, board, label, and readiness paths, then formats a
Markdown artifact for editorial review. It does not sync, mutate snapshots,
change thresholds, or migrate copy.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import json
from typing import Any, Iterable, Mapping

from services.editorial_voice_contract_v1 import find_editorial_violations
from utils.time import utc_now_naive


ARTIFACT_PATH = 'artifacts/context_explanation_editorial_review_E2D1.md'
REVIEW_LABEL = 'E2D-1 Context Explanation Corpus'

PITCHER_AVAILABILITY_STATUSES = (
    'Available',
    'Monitor',
    'Limited',
    'Avoid',
    'Unavailable',
)

BOARD_GROUP_STATUSES = (
    'Available',
    'Monitor',
    'Limited',
    'Avoid',
    'Unavailable',
)

TEAM_READINESS_STATUSES = (
    'operationally_stable',
    'operationally_constrained',
    'operationally_stressed',
    'data_limited',
    'refused',
)

TEAM_READINESS_SCOPES = (
    'readiness_state',
    'workload_state',
    'coverage_state',
    'freshness_state',
    'trust_state',
)

RETIRED_PUBLIC_PHRASES = (
    'clean option',
    'clean options',
    'clean arms',
    'short list of clean arms',
    'clean way',
    'clean ways',
    'usable group',
    'usable depth',
    'in good shape',
    'availability distributions',
    'practical path',
    'practical paths',
    '0 trusted',
)

INVENTORIED_SURFACES = (
    {
        'surface': 'Pitcher Context modal/detail route',
        'source_path': 'api.bullpen.get_pitcher_fatigue',
        'helpers': (
            'services.availability.classify_availability',
            'services.availability_explanations',
            'services.roster_status',
        ),
    },
    {
        'surface': 'Pitcher V4 availability explanation',
        'source_path': 'api.explanations._availability_explanation_payload',
        'helpers': (
            'explanations.availability.serialize_availability_explanation',
            'services.availability.classify_availability',
        ),
    },
    {
        'surface': 'Pitcher public role/read labels',
        'source_path': 'services.pitcher_public_labels.build_pitcher_labels',
        'helpers': (
            'services.pitcher_public_labels._role_label',
            'services.pitcher_public_labels._read_label',
        ),
    },
    {
        'surface': 'Team bullpen board context',
        'source_path': 'api.bullpen._build_team_board',
        'helpers': (
            'services.bullpen_board.build_board_payload',
            'services.bullpen_board.build_team_context',
        ),
    },
    {
        'surface': 'Team bullpen shape explanations',
        'source_path': 'services.team_bullpen_shape.build_team_bullpen_shape',
        'helpers': (
            'services.team_bullpen_shape._trust_availability',
            'services.team_bullpen_shape._clean_options',
            'services.team_bullpen_shape._bullpen_pressure',
            'services.team_bullpen_shape._workload_concentration',
            'services.team_bullpen_shape._depth_safety',
        ),
    },
    {
        'surface': 'Team Operations readiness V4 explanation',
        'source_path': 'api.explanations._team_readiness_payload_from_request',
        'helpers': (
            'team_operations.assemble_bullpen_readiness',
            'explanations.readiness.serialize_readiness_explanation',
        ),
    },
)


def build_context_explanation_editorial_review(
    *,
    app=None,
    generated_at=None,
    artifact_path: str | Path | None = None,
    review_label: str | None = None,
    seed_examples: Iterable[Mapping[str, Any]] | None = None,
    seed_missing_categories: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a deterministic review payload from current stored data."""

    def _run() -> dict[str, Any]:
        if seed_examples is not None:
            examples = [_with_scans(dict(example)) for example in seed_examples]
            missing = dict(seed_missing_categories or {})
            data_notes = ['seeded examples supplied by test/integrity path']
            team_ids: list[int] = []
        else:
            examples, missing, data_notes, team_ids = _collect_current_examples(app)

        scans = _scan_examples(examples)
        summary = _surface_summary(examples)
        coverage = _coverage_summary(examples, missing)

        return {
            'artifact': str(artifact_path or ARTIFACT_PATH),
            'review_label': review_label or REVIEW_LABEL,
            'generated_at': _isoformat(generated_at or utc_now_naive()),
            'source_mode': 'current stored DB data only; exporter starts no sync',
            'generation_path_used': [
                'services.context_explanation_editorial_review.build_context_explanation_editorial_review',
                'api.bullpen.get_pitcher_fatigue',
                'api.explanations._availability_explanation_payload',
                'services.pitcher_public_labels.build_pitcher_labels',
                'api.bullpen._build_team_board',
                'services.team_bullpen_shape.build_team_bullpen_shape',
                'api.explanations._team_readiness_payload_from_request',
                'explanations.readiness.serialize_readiness_explanation',
            ],
            'inventoried_surfaces': list(INVENTORIED_SURFACES),
            'team_ids_reviewed': team_ids,
            'example_count': len(examples),
            'surface_summary': summary,
            'coverage_summary': coverage,
            'missing_categories': missing,
            'data_notes': data_notes,
            'banned_language_scan': scans['banned_language_scan'],
            'retired_phrase_scan': scans['retired_phrase_scan'],
            'fallback_summary': _fallback_summary(examples),
            'examples': examples,
        }

    if app is not None:
        with app.app_context():
            return _run()
    return _run()


def write_context_explanation_editorial_review(
    report: Mapping[str, Any],
    path: str | Path,
) -> Path:
    """Write the Markdown review artifact and return its path."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        render_context_explanation_editorial_review_markdown(report),
        encoding='utf-8',
    )
    return output


def render_context_explanation_editorial_review_markdown(
    report: Mapping[str, Any],
) -> str:
    """Render a Markdown corpus with exact public explanation strings."""

    label = report.get('review_label') or REVIEW_LABEL
    lines: list[str] = [
        f'# Context Explanation Editorial Review Corpus - {label}',
        '',
        'Read-only export of current Pitcher Context and Team Context '
        'explanation copy before E2 Editorial Voice migration.',
        '',
        '## Export Metadata',
        '',
        _json_block(_metadata(report)),
        '',
        '## Inventoried Context Surfaces',
        '',
        _json_block(report.get('inventoried_surfaces') or []),
        '',
        '## Coverage And Missing Categories',
        '',
        _json_block(report.get('coverage_summary') or {}),
        '',
        '## Editorial Banned-Language Scan',
        '',
        _scan_status_line(report.get('banned_language_scan'), 'banned language'),
        '',
        '## Retired Phrase Scan',
        '',
        _scan_status_line(report.get('retired_phrase_scan'), 'retired phrase'),
        '',
        '## Fallbacks Found',
        '',
        _json_block(report.get('fallback_summary') or {}),
        '',
        '## Surface Summary',
        '',
        _json_block(report.get('surface_summary') or {}),
        '',
        '## Context Explanation Examples',
        '',
    ]

    examples = list(report.get('examples') or [])
    if not examples:
        lines.extend(['No context explanation examples rendered from current stored data.', ''])
    for index, example in enumerate(examples, start=1):
        lines.extend(_example_lines(index, example))

    return '\n'.join(lines).rstrip() + '\n'


def _collect_current_examples(app) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], list[int]]:
    from sqlalchemy import distinct

    from api.bullpen import _build_team_board
    from api.explanations import (
        _availability_explanation_payload,
        _team_readiness_payload_from_request,
    )
    from explanations import serialize_readiness_explanation
    from models.fatigue_score import FatigueScore
    from models.pitcher import Pitcher
    from services.pitcher_public_labels import build_pitcher_labels
    from utils.db import db

    examples: list[dict[str, Any]] = []
    notes: list[str] = []

    team_ids = [
        team_id for (team_id,) in (
            db.session.query(distinct(Pitcher.team_id))
            .filter(Pitcher.team_id.isnot(None))
            .order_by(Pitcher.team_id.asc())
            .all()
        )
    ]

    pitchers = (
        db.session.query(Pitcher)
        .join(FatigueScore, FatigueScore.pitcher_id == Pitcher.id)
        .distinct()
        .order_by(Pitcher.team_id.asc(), Pitcher.full_name.asc(), Pitcher.id.asc())
        .all()
    )

    availability_seen: set[str] = set()
    detail_seen: set[str] = set()
    label_seen: set[str] = set()
    availability_errors: list[dict[str, Any]] = []
    client = app.test_client() if app is not None else None

    for pitcher in pitchers:
        try:
            explanation = _availability_explanation_payload(pitcher.id)
        except Exception as exc:  # noqa: BLE001 - artifact records read gaps
            availability_errors.append({
                'pitcher_id': pitcher.id,
                'pitcher': pitcher.full_name,
                'error': _error_summary(exc),
            })
            continue

        status = str(explanation.get('state_explained') or 'unknown')
        if status not in availability_seen:
            availability_seen.add(status)
            examples.append(_availability_explanation_example(pitcher, explanation))

        detail_payload = None
        if client is not None and status not in detail_seen:
            detail_payload = _pitcher_detail_payload(client, pitcher.id)
            if detail_payload:
                detail_seen.add(status)
                examples.append(_pitcher_detail_example(pitcher, detail_payload))

        if detail_payload is None and client is not None:
            detail_payload = _pitcher_detail_payload(client, pitcher.id)

        if detail_payload:
            labels = build_pitcher_labels(
                availability=detail_payload.get('availability'),
                role=None,
                roster_status=detail_payload.get('roster_status'),
            )
            label_key = _label_key(labels)
            if label_key not in label_seen:
                label_seen.add(label_key)
                examples.append(_pitcher_label_example(pitcher, detail_payload, labels))

        if _pitcher_collection_complete(availability_seen, detail_seen, label_seen):
            break

    board_status_counts: Counter[str] = Counter()
    board_totals: dict[int, int] = {}
    shape_label_counts: Counter[str] = Counter()
    board_examples_added = 0
    for team_id in team_ids:
        try:
            board = _build_team_board(team_id, include_stale=False)
        except Exception as exc:  # noqa: BLE001 - artifact records read gaps
            examples.append(_error_example(
                surface_name='Team bullpen board context',
                team=f'Team {team_id}',
                source_path='api.bullpen._build_team_board',
                error=_error_summary(exc),
            ))
            continue

        board_totals[int(team_id)] = int(board.get('total_pitchers') or 0)
        for group in board.get('groups') or []:
            board_status_counts[str(group.get('status') or 'unknown')] += int(group.get('count') or 0)
        for read in (board.get('team_shape') or {}).get('reads') or []:
            shape_label_counts[str(read.get('label') or 'unknown')] += 1

        if board_examples_added < 3:
            board_examples_added += 1
            examples.append(_team_board_example(board))
            examples.append(_team_shape_example(board))

    readiness_seen: set[str] = set()
    readiness_errors: list[dict[str, Any]] = []
    for team_id in team_ids:
        if app is None:
            break
        try:
            with app.test_request_context(f'/api/explanations/team-readiness?team_id={team_id}'):
                readiness_payload = _team_readiness_payload_from_request()
        except Exception as exc:  # noqa: BLE001 - artifact records read gaps
            readiness_errors.append({'team_id': team_id, 'error': _error_summary(exc)})
            continue

        status = str((readiness_payload.get('readiness') or {}).get('status_code') or 'unknown')
        if status in readiness_seen:
            continue
        readiness_seen.add(status)
        for scope in TEAM_READINESS_SCOPES:
            explanation = serialize_readiness_explanation(
                readiness_payload,
                scope=scope,
                generated_at=readiness_payload.get('generated_at'),
            )
            examples.append(_readiness_explanation_example(readiness_payload, explanation, scope))

    missing = {
        'pitcher_availability_statuses': [
            status for status in PITCHER_AVAILABILITY_STATUSES
            if status not in availability_seen
        ],
        'pitcher_context_modal_statuses': [
            status for status in PITCHER_AVAILABILITY_STATUSES
            if status not in detail_seen
        ],
        'board_card_groups_with_no_current_cards': [
            status for status in BOARD_GROUP_STATUSES
            if board_status_counts.get(status, 0) == 0
        ],
        'team_readiness_statuses': [
            status for status in TEAM_READINESS_STATUSES
            if status not in readiness_seen
        ],
        'role_label_examples': (
            'Current board records produced no eligible visible pitcher cards, '
            'so Trust Arm, Bridge Arm, Coverage Arm, and Depth Arm role examples '
            'were not available from stored board data.'
        ),
        'team_shape_non_limited_examples': (
            'Current board rows produced Limited Read team-shape examples only.'
            if set(shape_label_counts) <= {'Limited Read'} else None
        ),
        'availability_read_errors': availability_errors,
        'team_readiness_errors': readiness_errors,
    }
    missing = {key: value for key, value in missing.items() if value}

    if not any(total > 0 for total in board_totals.values()):
        notes.append(
            'Current stored team board path returned zero eligible visible pitcher cards '
            'for every reviewed team; board card/group examples are documented as real '
            'fallback/no-card rows.'
        )
    if availability_errors:
        notes.append('Some pitcher availability explanation rows could not be read safely.')
    if readiness_errors:
        notes.append('Some team readiness explanation rows could not be read safely.')

    scanned = [_with_scans(example) for example in examples]
    return scanned, missing, notes, [int(team_id) for team_id in team_ids]


def _availability_explanation_example(pitcher, explanation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'surface_name': 'Pitcher V4 availability explanation',
        'team': _pitcher_team(pitcher),
        'pitcher': pitcher.full_name,
        'status': explanation.get('state_explained'),
        'role_or_classification': {
            'scope': explanation.get('scope'),
            'subject_type': explanation.get('subject_type'),
        },
        'source_path': (
            'api.explanations._availability_explanation_payload -> '
            'explanations.availability.serialize_availability_explanation'
        ),
        'fallback_status': _fallback_status_for_explanation(explanation),
        'rendered_public_copy': _explanation_copy(explanation),
        'structured_fields_used': _explanation_structured_fields(explanation),
        'evidence_sections': _evidence_sections(explanation),
    }


def _pitcher_detail_example(pitcher, payload: Mapping[str, Any]) -> dict[str, Any]:
    availability = payload.get('availability') or {}
    workload_signal = payload.get('workload_signal') or {}
    roster_status = payload.get('roster_status') or {}
    freshness = payload.get('freshness') or {}
    copy = _dedupe_strings([
        availability.get('availability_status'),
        *list(availability.get('reasons') or []),
        *list(availability.get('limitations') or []),
        workload_signal.get('availability_status'),
        *list(workload_signal.get('reasons') or []),
        *list(workload_signal.get('limitations') or []),
        roster_status.get('label'),
        *list(roster_status.get('limitations') or []),
        freshness.get('label'),
        *list(freshness.get('limitations') or []),
    ])
    return {
        'surface_name': 'Pitcher Context modal/detail route',
        'team': _pitcher_team(pitcher),
        'pitcher': pitcher.full_name,
        'status': availability.get('availability_status'),
        'role_or_classification': {
            'data_state': availability.get('data_state'),
            'confidence': availability.get('confidence'),
            'roster_status': roster_status.get('label'),
        },
        'source_path': 'api.bullpen.get_pitcher_fatigue',
        'fallback_status': _availability_fallback_status(availability),
        'rendered_public_copy': copy,
        'structured_fields_used': {
            'availability': _subset(
                availability,
                ('availability_status', 'confidence', 'data_state', 'reasons', 'limitations', 'inputs'),
            ),
            'workload_signal': _subset(
                workload_signal,
                ('availability_status', 'confidence', 'data_state', 'reasons', 'limitations', 'inputs'),
            ),
            'roster_status': _subset(
                roster_status,
                ('label', 'status', 'confidence', 'limitations', 'source'),
            ),
            'freshness': _subset(
                freshness,
                ('label', 'freshness_state', 'data_age_days', 'limitations', 'data_through'),
            ),
        },
        'evidence_sections': {
            'last_workload_appearance': payload.get('last_workload_appearance'),
            'recent_logs_reviewed': len(payload.get('recent_logs') or []),
            'fatigue_trend_points': len(payload.get('fatigue_trend') or []),
        },
    }


def _pitcher_label_example(pitcher, detail_payload: Mapping[str, Any], labels: Mapping[str, Any]) -> dict[str, Any]:
    availability = detail_payload.get('availability') or {}
    return {
        'surface_name': 'Pitcher public role/read labels',
        'team': _pitcher_team(pitcher),
        'pitcher': pitcher.full_name,
        'status': availability.get('availability_status'),
        'role_or_classification': {
            'role': (labels.get('role') or {}).get('label'),
            'read': (labels.get('read') or {}).get('label'),
        },
        'source_path': 'services.pitcher_public_labels.build_pitcher_labels',
        'fallback_status': (
            'limited_role_context'
            if (labels.get('role') or {}).get('key') == 'limited_read'
            else 'rendered'
        ),
        'rendered_public_copy': _dedupe_strings([
            (labels.get('role') or {}).get('label'),
            (labels.get('read') or {}).get('label'),
        ]),
        'structured_fields_used': {
            'availability_status': availability.get('availability_status'),
            'availability_data_state': availability.get('data_state'),
            'availability_confidence': availability.get('confidence'),
            'role_input': None,
            'roster_status': detail_payload.get('roster_status'),
            'labels': labels,
        },
        'evidence_sections': {},
    }


def _team_board_example(board: Mapping[str, Any]) -> dict[str, Any]:
    context = board.get('context') or {}
    health = context.get('health') or {}
    groups = board.get('groups') or []
    copy = _dedupe_strings([
        health.get('label'),
        *list(health.get('reasons') or []),
        *[
            item
            for group in groups
            for item in (group.get('label'), group.get('description'))
        ],
        *((board.get('freshness') or {}).get('limitations') or []),
    ])
    return {
        'surface_name': 'Team bullpen board context',
        'team': _team_label(board.get('team')),
        'pitcher': None,
        'status': health.get('state'),
        'role_or_classification': {
            'total_pitchers': board.get('total_pitchers'),
            'ungrouped_pitchers': board.get('ungrouped_pitchers'),
        },
        'source_path': 'api.bullpen._build_team_board -> services.bullpen_board.build_board_payload',
        'fallback_status': (
            'no_visible_pitcher_cards'
            if not board.get('total_pitchers') else 'rendered'
        ),
        'rendered_public_copy': copy,
        'structured_fields_used': {
            'context': context,
            'groups': [
                _subset(group, ('status', 'label', 'description', 'count'))
                for group in groups
            ],
            'freshness': board.get('freshness') or {},
            'limitations': board.get('limitations') or [],
        },
        'evidence_sections': {
            'group_counts': {
                group.get('status'): group.get('count')
                for group in groups
            },
            'roster_authority_summary': _subset(
                board.get('roster_authority') or {},
                ('summary', 'limitations', 'population'),
            ),
        },
    }


def _team_shape_example(board: Mapping[str, Any]) -> dict[str, Any]:
    shape = board.get('team_shape') or {}
    reads = shape.get('reads') or []
    copy = _dedupe_strings([
        item
        for read in reads
        for item in (
            read.get('label'),
            read.get('explanation'),
            *list(read.get('reasons') or []),
        )
    ])
    return {
        'surface_name': 'Team bullpen shape explanations',
        'team': _team_label(board.get('team')),
        'pitcher': None,
        'status': 'team_shape',
        'role_or_classification': {
            'read_labels': [read.get('label') for read in reads],
        },
        'source_path': 'services.team_bullpen_shape.build_team_bullpen_shape',
        'fallback_status': (
            'limited_read_shape'
            if reads and all(read.get('label') == 'Limited Read' for read in reads)
            else 'rendered'
        ),
        'rendered_public_copy': copy,
        'structured_fields_used': {
            'supportingCounts': shape.get('supportingCounts') or {},
            'reads': reads,
            'source': shape.get('source'),
        },
        'evidence_sections': {
            'read_count': len(reads),
            'read_keys': [read.get('key') for read in reads],
        },
    }


def _readiness_explanation_example(
    payload: Mapping[str, Any],
    explanation: Mapping[str, Any],
    scope: str,
) -> dict[str, Any]:
    team = payload.get('team') or {}
    readiness = payload.get('readiness') or {}
    return {
        'surface_name': 'Team Operations readiness V4 explanation',
        'team': _team_label(team),
        'pitcher': None,
        'status': explanation.get('state_explained'),
        'role_or_classification': {
            'scope': scope,
            'readiness_status_code': readiness.get('status_code'),
            'readiness_status': readiness.get('status'),
        },
        'source_path': (
            'api.explanations._team_readiness_payload_from_request -> '
            'explanations.readiness.serialize_readiness_explanation'
        ),
        'fallback_status': (
            'data_limited'
            if readiness.get('status_code') == 'data_limited' else 'rendered'
        ),
        'rendered_public_copy': _explanation_copy(explanation),
        'structured_fields_used': {
            'readiness': readiness,
            'constraints': payload.get('constraints') or [],
            'workload_pressure': payload.get('workload_pressure') or {},
            'availability_distribution': payload.get('availability_distribution') or {},
            'coverage_inventory': payload.get('coverage_inventory') or {},
            'handedness_coverage': payload.get('handedness_coverage') or {},
            'trust_metadata': payload.get('trust_metadata') or {},
            'freshness': payload.get('freshness') or {},
        },
        'evidence_sections': _evidence_sections(explanation),
    }


def _error_example(
    *,
    surface_name: str,
    team: str | None,
    source_path: str,
    error: str,
) -> dict[str, Any]:
    return {
        'surface_name': surface_name,
        'team': team,
        'pitcher': None,
        'status': 'export_error',
        'role_or_classification': {},
        'source_path': source_path,
        'fallback_status': 'export_error',
        'rendered_public_copy': [],
        'structured_fields_used': {},
        'evidence_sections': {'error': error},
    }


def _explanation_copy(explanation: Mapping[str, Any]) -> list[str]:
    copy = [explanation.get('summary')]
    copy.extend(
        reason.get('summary')
        for reason in explanation.get('primary_reasons') or []
        if isinstance(reason, Mapping)
    )
    copy.extend(
        limitation.get('summary')
        for limitation in explanation.get('limitations') or []
        if isinstance(limitation, Mapping)
    )
    freshness = explanation.get('freshness') or {}
    trust = explanation.get('trust') or {}
    confidence = explanation.get('confidence') or {}
    copy.extend([
        freshness.get('summary'),
        trust.get('summary'),
        confidence.get('summary'),
    ])
    return _dedupe_strings(copy)


def _explanation_structured_fields(explanation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'scope': explanation.get('scope'),
        'subject_type': explanation.get('subject_type'),
        'subject_id': explanation.get('subject_id'),
        'state_explained': explanation.get('state_explained'),
        'primary_reason_codes': [
            reason.get('code')
            for reason in explanation.get('primary_reasons') or []
            if isinstance(reason, Mapping)
        ],
        'freshness': explanation.get('freshness') or {},
        'trust': explanation.get('trust') or {},
        'confidence': explanation.get('confidence') or {},
        'governance': explanation.get('governance') or {},
    }


def _evidence_sections(explanation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        'primary_reasons': [
            _subset(reason, ('code', 'scope', 'label', 'summary'))
            for reason in explanation.get('primary_reasons') or []
            if isinstance(reason, Mapping)
        ],
        'supporting_evidence': [
            _subset(item, ('evidence_type', 'label', 'value', 'unit', 'source', 'impact'))
            for item in explanation.get('supporting_evidence') or []
            if isinstance(item, Mapping)
        ],
        'limitations': [
            _subset(item, ('limitation_type', 'severity', 'summary', 'affected_scopes'))
            for item in explanation.get('limitations') or []
            if isinstance(item, Mapping)
        ],
    }


def _with_scans(example: dict[str, Any]) -> dict[str, Any]:
    texts = _public_texts(example)
    text = '\n'.join(texts)
    example['banned_language_scan'] = {
        'status': 'pass' if not find_editorial_violations(text) else 'warn',
        'violation_count': len(find_editorial_violations(text)),
        'violations': find_editorial_violations(text),
    }
    retired = find_editorial_violations(text, terms=RETIRED_PUBLIC_PHRASES)
    example['retired_phrase_scan'] = {
        'status': 'pass' if not retired else 'warn',
        'violation_count': len(retired),
        'violations': retired,
        'terms': RETIRED_PUBLIC_PHRASES,
    }
    return example


def _scan_examples(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    banned = []
    retired = []
    for index, example in enumerate(examples, start=1):
        text = '\n'.join(_public_texts(example))
        for violation in find_editorial_violations(text):
            banned.append({
                'example_index': index,
                'surface_name': example.get('surface_name'),
                'team': example.get('team'),
                'pitcher': example.get('pitcher'),
                **violation,
            })
        for violation in find_editorial_violations(text, terms=RETIRED_PUBLIC_PHRASES):
            retired.append({
                'example_index': index,
                'surface_name': example.get('surface_name'),
                'team': example.get('team'),
                'pitcher': example.get('pitcher'),
                **violation,
            })
    return {
        'banned_language_scan': {
            'scope': 'rendered public context explanation copy only',
            'status': 'pass' if not banned else 'warn',
            'violation_count': len(banned),
            'violations': banned,
        },
        'retired_phrase_scan': {
            'scope': 'rendered public context explanation copy only',
            'status': 'pass' if not retired else 'warn',
            'violation_count': len(retired),
            'violations': retired,
            'terms': RETIRED_PUBLIC_PHRASES,
        },
    }


def _surface_summary(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    by_surface = Counter(str(example.get('surface_name') or 'unknown') for example in examples)
    by_status: dict[str, Counter[str]] = defaultdict(Counter)
    for example in examples:
        by_status[str(example.get('surface_name') or 'unknown')][str(example.get('status') or 'unknown')] += 1
    return {
        'examples_by_surface': dict(sorted(by_surface.items())),
        'statuses_by_surface': {
            surface: dict(sorted(counter.items()))
            for surface, counter in sorted(by_status.items())
        },
    }


def _coverage_summary(
    examples: Iterable[Mapping[str, Any]],
    missing: Mapping[str, Any],
) -> dict[str, Any]:
    examples = list(examples)
    return {
        'examples_exported': len(examples),
        'pitcher_availability_statuses_found': sorted({
            str(example.get('status'))
            for example in examples
            if example.get('surface_name') == 'Pitcher V4 availability explanation'
        }),
        'pitcher_context_statuses_found': sorted({
            str(example.get('status'))
            for example in examples
            if example.get('surface_name') == 'Pitcher Context modal/detail route'
        }),
        'team_readiness_states_found': sorted({
            str((example.get('role_or_classification') or {}).get('readiness_status_code'))
            for example in examples
            if example.get('surface_name') == 'Team Operations readiness V4 explanation'
        }),
        'missing_categories': dict(missing),
    }


def _fallback_summary(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(example.get('fallback_status') or 'unknown') for example in examples)
    rows = [
        {
            'surface_name': example.get('surface_name'),
            'team': example.get('team'),
            'pitcher': example.get('pitcher'),
            'status': example.get('status'),
            'fallback_status': example.get('fallback_status'),
        }
        for example in examples
        if str(example.get('fallback_status') or '') not in {'rendered', ''}
    ]
    return {
        'fallback_counts': dict(sorted(counter.items())),
        'fallback_rows': rows,
    }


def _example_lines(index: int, example: Mapping[str, Any]) -> list[str]:
    metadata = {
        key: example.get(key)
        for key in (
            'surface_name',
            'team',
            'pitcher',
            'status',
            'role_or_classification',
            'source_path',
            'fallback_status',
            'banned_language_scan',
            'retired_phrase_scan',
        )
    }
    copy = list(example.get('rendered_public_copy') or [])
    lines = [
        f"### Example {index}: {example.get('surface_name') or 'Unknown Surface'}",
        '',
        'Metadata:',
        '',
        _json_block(metadata),
        '',
        'Rendered public copy:',
        '```',
        '\n'.join(str(item) for item in copy) if copy else '(none)',
        '```',
        '',
        'Structured fields used:',
        '',
        _json_block(example.get('structured_fields_used') or {}),
        '',
        'Evidence sections:',
        '',
        _json_block(example.get('evidence_sections') or {}),
        '',
    ]
    return lines


def _metadata(report: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: report.get(key)
        for key in (
            'artifact',
            'review_label',
            'generated_at',
            'source_mode',
            'generation_path_used',
            'team_ids_reviewed',
            'example_count',
            'data_notes',
        )
    }


def _scan_status_line(scan: Mapping[str, Any] | None, label: str) -> str:
    scan = scan or {}
    status = scan.get('status') or 'unknown'
    count = int(scan.get('violation_count') or 0)
    if count:
        return f"Status: {status} - {count} {label} violation(s) found.\n\n{_json_block(scan)}"
    return f'Status: {status} - no {label} violations found.'


def _pitcher_collection_complete(
    availability_seen: set[str],
    detail_seen: set[str],
    label_seen: set[str],
) -> bool:
    if not {'Monitor', 'Limited', 'Unavailable'}.issubset(availability_seen):
        return False
    if not {'Monitor', 'Limited', 'Unavailable'}.issubset(detail_seen):
        return False
    return len(label_seen) >= 3


def _pitcher_detail_payload(client, pitcher_id: int) -> dict[str, Any] | None:
    response = client.get(f'/api/bullpen/fatigue/{pitcher_id}')
    if response.status_code != 200:
        return None
    payload = response.get_json(silent=True)
    return payload if isinstance(payload, dict) else None


def _fallback_status_for_explanation(explanation: Mapping[str, Any]) -> str:
    freshness = explanation.get('freshness') or {}
    trust = explanation.get('trust') or {}
    if freshness.get('status') and freshness.get('status') != 'current':
        return f"freshness_{freshness.get('status')}"
    if trust.get('status') and trust.get('status') != 'trusted':
        return f"trust_{trust.get('status')}"
    return 'rendered'


def _availability_fallback_status(availability: Mapping[str, Any]) -> str:
    data_state = availability.get('data_state')
    if data_state and data_state != 'fresh':
        return f'data_{data_state}'
    if availability.get('confidence') in {'low', 'unknown'}:
        return f"confidence_{availability.get('confidence')}"
    return 'rendered'


def _label_key(labels: Mapping[str, Any]) -> str:
    role = labels.get('role') or {}
    read = labels.get('read') or {}
    return f"{role.get('key')}::{read.get('key')}"


def _pitcher_team(pitcher) -> str:
    name = getattr(pitcher, 'team_name', None)
    abbreviation = getattr(pitcher, 'team_abbreviation', None)
    team_id = getattr(pitcher, 'team_id', None)
    if name and abbreviation:
        return f'{name} ({abbreviation}, {team_id})'
    if name:
        return f'{name} ({team_id})'
    return f'Team {team_id}'


def _team_label(team: Mapping[str, Any] | None) -> str:
    team = team or {}
    name = team.get('team_name') or team.get('name')
    abbreviation = team.get('team_abbreviation') or team.get('abbreviation')
    team_id = team.get('team_id')
    if name and abbreviation:
        return f'{name} ({abbreviation}, {team_id})'
    if name:
        return f'{name} ({team_id})'
    return f'Team {team_id}' if team_id is not None else 'Team unavailable'


def _public_texts(example: Mapping[str, Any]) -> list[str]:
    return _dedupe_strings(example.get('rendered_public_copy') or [])


def _dedupe_strings(values: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        output.append(text)
    return output


def _subset(payload: Mapping[str, Any] | None, keys: Iterable[str]) -> dict[str, Any]:
    payload = payload or {}
    return {key: payload.get(key) for key in keys if key in payload}


def _error_summary(exc: Exception) -> str:
    message = str(exc).splitlines()[0] if str(exc) else exc.__class__.__name__
    return f'{exc.__class__.__name__}: {message}'


def _json_block(value: Any) -> str:
    return '```json\n' + json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False, default=str) + '\n```'


def _isoformat(value: Any) -> str | None:
    if value is None:
        return None
    isoformat = getattr(value, 'isoformat', None)
    return isoformat() if callable(isoformat) else str(value)


__all__ = [
    'ARTIFACT_PATH',
    'RETIRED_PUBLIC_PHRASES',
    'REVIEW_LABEL',
    'build_context_explanation_editorial_review',
    'render_context_explanation_editorial_review_markdown',
    'write_context_explanation_editorial_review',
]
