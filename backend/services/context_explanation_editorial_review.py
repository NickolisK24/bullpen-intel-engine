"""Read-only editorial corpus for pitcher/team context explanation surfaces.

E2D-1 is an audit/export phase. This module reads current stored data through
the existing explanation, board, label, and readiness paths, then formats a
Markdown artifact for editorial review. It does not sync, mutate snapshots,
change thresholds, or migrate copy.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path
import json
import re
from types import SimpleNamespace
from typing import Any, Iterable, Mapping

from services.editorial_voice_contract_v1 import find_editorial_violations
from utils.time import utc_now_naive


ARTIFACT_PATH = 'artifacts/context_explanation_editorial_review_E2D1.md'
REVIEW_LABEL = 'E2D-1 Context Explanation Corpus'

STORED_DATA_EXAMPLE = 'stored-data example'
DETERMINISTIC_FIXTURE_EXAMPLE = 'deterministic fixture example'
SEEDED_INTEGRITY_EXAMPLE = 'seeded integrity example'

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
    'interpretation weighs',
    'weighs clean',
    'weighs trust',
    'weighs bridge',
    'late-inning pressure weighs',
    'trust arms above',
    'depth arms above',
    'classified available',
    '0 of 0',
    'clean arms',
    'short list of clean arms',
    'clean way',
    'clean ways',
    'usable group',
    'usable depth',
    'in good shape',
    'trusted-group',
    'top trust bucket',
    'coverage margin',
    'resource health',
    'active capacity',
    'trust structure',
    'trust hierarchy',
    'trust metadata',
    'explained state',
    'availability read',
    'bullpen planning read',
    'explanation confidence mirrors',
    'confidence mirrors',
    'governed availability evidence',
    'state reflects',
    'availability distributions',
    'practical path',
    'practical paths',
    '0 trusted',
)

RAW_COUNT_FORMULA_PATTERN = re.compile(r'(?<![\w-])\d+\s+of\s+\d+(?![\w-])', re.IGNORECASE)
PARENTHETICAL_UNKNOWN_FORMULA_PATTERN = re.compile(r'\([^)]*\bunknown\b[^)]*\)', re.IGNORECASE)
JARGON_COUPLED_RAW_COUNT_PATTERN = re.compile(
    r'(?<![\w-])\d+\s+of\s+\d+\s+'
    r'(?:trust|bridge|coverage|depth)\s+arms?\b',
    re.IGNORECASE,
)
PARENTHETICAL_RAW_BASIS_PATTERN = re.compile(
    r'\(\s*\d+\s+of\s+\d+\s*\)',
    re.IGNORECASE,
)
FORMULA_TERMS = (
    'trusted-group',
    'top trust bucket',
    'coverage margin',
    'resource health',
    'active capacity',
    'trust structure',
    'trust hierarchy',
    '0 trusted',
)
WEIGHTING_SCORING_TERMS = (
    'interpretation weighs',
    'weighs clean',
    'weighs trust',
    'weighs bridge',
    'late-inning pressure weighs',
    'trust arms above',
    'depth arms above',
    'raw score',
    'scoring weight',
    'weighted pressure',
)
CIRCULAR_META_TERMS = (
    'explanation confidence mirrors',
    'confidence mirrors',
    'visibility reflects existing availability confidence',
    'governed availability evidence',
    'state reflects',
    'explained state',
    'trust metadata',
    'readiness explanation confidence',
)
TRUST_FIRST_DISCLAIMERS = (
    'Readiness is based on public workload data, not private team information.',
    'Readiness is not injury or medical information.',
    'Readiness is not a performance forecast.',
    'Manager intent and bullpen warm-up state are not available.',
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
    include_fixture_examples: bool = False,
) -> dict[str, Any]:
    """Build a deterministic review payload from current stored data."""

    def _run() -> dict[str, Any]:
        if seed_examples is not None:
            examples = []
            for example in seed_examples:
                row = dict(example)
                row.setdefault('example_source', SEEDED_INTEGRITY_EXAMPLE)
                examples.append(_with_scans(row))
            missing = dict(seed_missing_categories or {})
            data_notes = ['seeded examples supplied by test/integrity path']
            team_ids: list[int] = []
        else:
            if app is None and include_fixture_examples:
                examples = []
                missing = _missing_categories_from_examples([])
                data_notes = [
                    'no app supplied; deterministic fixture-only integrity path used',
                ]
                team_ids = []
            else:
                examples, missing, data_notes, team_ids = _collect_current_examples(app)
            if include_fixture_examples:
                fixture_examples, fixture_notes = _collect_fixture_examples(examples)
                examples.extend(fixture_examples)
                data_notes.extend(fixture_notes)
                missing = _missing_categories_from_examples(examples, previous_missing=missing)

        scans = _scan_examples(examples)
        raw_count_formula_scan = _raw_count_formula_scan(examples)
        weighting_scoring_scan = _weighting_scoring_scan(examples)
        circular_meta_scan = _circular_meta_scan(examples)
        disclaimer_check = _disclaimer_preservation_check(examples)
        summary = _surface_summary(examples)
        coverage = _coverage_summary(examples, missing)

        return {
            'artifact': str(artifact_path or ARTIFACT_PATH),
            'review_label': review_label or REVIEW_LABEL,
            'generated_at': _isoformat(generated_at or utc_now_naive()),
            'source_mode': (
                'current stored DB data first; deterministic fixtures fill uncaptured '
                'healthy-state categories; exporter starts no sync'
                if include_fixture_examples and seed_examples is None
                else 'current stored DB data only; exporter starts no sync'
            ),
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
            'before_after_summary': _before_after_summary(
                scans=scans,
                raw_count_formula_scan=raw_count_formula_scan,
                weighting_scoring_scan=weighting_scoring_scan,
                circular_meta_scan=circular_meta_scan,
                disclaimer_check=disclaimer_check,
            ),
            'banned_language_scan': scans['banned_language_scan'],
            'retired_phrase_scan': scans['retired_phrase_scan'],
            'raw_count_formula_scan': raw_count_formula_scan,
            'weighting_scoring_scan': weighting_scoring_scan,
            'circular_meta_scan': circular_meta_scan,
            'disclaimer_preservation_check': disclaimer_check,
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
        'explanation copy for E2 Editorial Voice review.',
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
        '## Before / After Summary',
        '',
        _json_block(report.get('before_after_summary') or {}),
        '',
        '## Editorial Banned-Language Scan',
        '',
        _scan_status_line(report.get('banned_language_scan'), 'banned language'),
        '',
        '## Retired Phrase Scan',
        '',
        _scan_status_line(report.get('retired_phrase_scan'), 'retired phrase'),
        '',
        '## Raw-Count / Formula Scan',
        '',
        _scan_status_line(report.get('raw_count_formula_scan'), 'raw-count or formula'),
        '',
        '## Weighting / Scoring Narration Scan',
        '',
        _scan_status_line(report.get('weighting_scoring_scan'), 'weighting or scoring narration'),
        '',
        '## Circular-Meta Scan',
        '',
        _scan_status_line(report.get('circular_meta_scan'), 'circular-meta'),
        '',
        '## Disclaimer Preservation Check',
        '',
        _json_block(report.get('disclaimer_preservation_check') or {}),
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

    scanned = []
    for example in examples:
        example.setdefault('example_source', STORED_DATA_EXAMPLE)
        scanned.append(_with_scans(example))
    return scanned, missing, notes, [int(team_id) for team_id in team_ids]


def _collect_fixture_examples(
    current_examples: Iterable[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Collect deterministic fixture-backed examples for uncaptured categories."""

    current_examples = list(current_examples)
    examples: list[dict[str, Any]] = []
    notes = [
        'Deterministic fixture examples use existing backend test fixture shapes '
        'and production helper paths; they are labeled separately from stored data.',
    ]

    examples.extend(_fixture_pitcher_examples(current_examples))
    fixture_board = _fixture_board_payload()
    examples.append(_mark_fixture(_team_board_example(fixture_board)))
    examples.append(_mark_fixture(_team_shape_example(fixture_board)))
    examples.extend(_fixture_board_card_label_examples(fixture_board))
    examples.extend(_fixture_readiness_examples(current_examples))

    return [_with_scans(example) for example in examples], notes


def _fixture_pitcher_examples(
    current_examples: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    from explanations import serialize_availability_explanation
    from services.availability import (
        STATUS_AVAILABLE,
        STATUS_AVOID,
        STATUS_LIMITED,
        STATUS_MONITOR,
        STATUS_UNAVAILABLE,
        classify_availability,
    )
    from services.pitcher_public_labels import build_pitcher_labels

    current_examples = list(current_examples)
    availability_seen = {
        str(example.get('status'))
        for example in current_examples
        if example.get('surface_name') == 'Pitcher V4 availability explanation'
    }
    detail_seen = {
        str(example.get('status'))
        for example in current_examples
        if example.get('surface_name') == 'Pitcher Context modal/detail route'
    }

    ref = date(2026, 6, 1)
    fixture_specs = {
        STATUS_AVAILABLE: {'raw_score': 20.0, 'days_ago': 3, 'pitches': 8},
        STATUS_MONITOR: {'raw_score': 20.0, 'days_ago': 1, 'pitches': 16},
        STATUS_LIMITED: {'raw_score': 30.0, 'days_ago': 1, 'pitches': 28},
        STATUS_AVOID: {'raw_score': 30.0, 'days_ago': 1, 'pitches': 42},
        STATUS_UNAVAILABLE: {'raw_score': 30.0, 'days_ago': 1, 'pitches': 52},
    }
    role_specs = (
        ('late_high_leverage', 'Trust Arm'),
        ('setup_bridge', 'Bridge Arm'),
        ('long_relief', 'Coverage Arm'),
        ('low_leverage', 'Depth Arm'),
        ('insufficient_data', 'Limited Read'),
    )

    examples: list[dict[str, Any]] = []
    availability_by_status: dict[str, Mapping[str, Any]] = {}
    for index, (status, spec) in enumerate(fixture_specs.items(), start=1):
        log = _fixture_log(ref - timedelta(days=int(spec['days_ago'])), int(spec['pitches']))
        availability = classify_availability(
            score=_fixture_score(float(spec['raw_score'])),
            game_logs=[log],
            reference_date=ref,
            latest_game_date=log.game_date,
        )
        availability_by_status[status] = availability
        pitcher = _fixture_pitcher(status, index)

        if status not in availability_seen:
            explanation = serialize_availability_explanation(
                availability,
                subject_id=f'fixture:{index}',
                generated_at='2026-06-03T12:00:00Z',
            )
            example = _availability_explanation_example(pitcher, explanation)
            example['source_path'] = (
                'backend/tests/test_v4_availability_explanation_integration.py fixture pattern -> '
                'services.availability.classify_availability -> '
                'explanations.availability.serialize_availability_explanation'
            )
            examples.append(_mark_fixture(example))

        if status not in detail_seen:
            detail_payload = _fixture_pitcher_detail_payload(availability, log)
            example = _pitcher_detail_example(pitcher, detail_payload)
            example['source_path'] = (
                'backend/tests/test_v4_availability_explanation_integration.py fixture pattern -> '
                'services.availability.classify_availability -> api.bullpen.get_pitcher_fatigue payload shape'
            )
            examples.append(_mark_fixture(example))

    for index, (role_key, expected_role_label) in enumerate(role_specs, start=1):
        status = list(fixture_specs)[index - 1]
        availability = availability_by_status[status]
        role = _fixture_role(role_key)
        labels = build_pitcher_labels(
            availability=availability,
            role=role,
            eligibility={'status': 'eligible'},
            roster_status={'status': 'active'},
        )
        detail_payload = _fixture_pitcher_detail_payload(
            availability,
            _fixture_log(ref - timedelta(days=1), 12),
            role=role,
        )
        pitcher = _fixture_pitcher(expected_role_label, index + 20)
        example = _pitcher_label_example(pitcher, detail_payload, labels)
        example['source_path'] = (
            'backend/tests/test_team_bullpen_shape.py role fixture pattern -> '
            'services.pitcher_public_labels.build_pitcher_labels'
        )
        examples.append(_mark_fixture(example))

    stale_availability = classify_availability(
        score=None,
        game_logs=[],
        reference_date=ref,
        latest_game_date=None,
    )
    stale_role = _fixture_role('insufficient_data')
    stale_labels = build_pitcher_labels(
        availability=stale_availability,
        role=stale_role,
        eligibility={'status': 'eligible'},
        roster_status={'status': 'active'},
    )
    stale_detail_payload = _fixture_pitcher_detail_payload(
        stale_availability,
        _fixture_log(ref - timedelta(days=30), 0),
        role=stale_role,
    )
    stale_example = _pitcher_label_example(
        _fixture_pitcher('Limited Read label', 99),
        stale_detail_payload,
        stale_labels,
    )
    stale_example['source_path'] = (
        'backend/tests/test_v4_availability_explanation_integration.py missing-data fixture pattern -> '
        'services.pitcher_public_labels.build_pitcher_labels'
    )
    examples.append(_mark_fixture(stale_example))

    return examples


def _fixture_board_payload() -> dict[str, Any]:
    from services.bullpen_board import build_board_payload
    from services.workload_concentration import summarize_workload_concentration

    ref = date(2026, 6, 1)
    records = [
        _fixture_board_record(
            name='Fixture Trust Arm',
            pitcher_id=9101,
            availability=_fixture_availability('Available', ref, raw_score=20.0, days_ago=3, pitches=8),
            role=_fixture_role('late_high_leverage'),
        ),
        _fixture_board_record(
            name='Fixture Bridge Arm',
            pitcher_id=9102,
            availability=_fixture_availability('Monitor', ref, raw_score=20.0, days_ago=1, pitches=16),
            role=_fixture_role('setup_bridge'),
        ),
        _fixture_board_record(
            name='Fixture Coverage Arm',
            pitcher_id=9103,
            availability=_fixture_availability('Limited', ref, raw_score=30.0, days_ago=1, pitches=28),
            role=_fixture_role('long_relief'),
        ),
        _fixture_board_record(
            name='Fixture Depth Arm',
            pitcher_id=9104,
            availability=_fixture_availability('Avoid', ref, raw_score=30.0, days_ago=1, pitches=42),
            role=_fixture_role('low_leverage'),
        ),
        _fixture_board_record(
            name='Fixture Unavailable Arm',
            pitcher_id=9105,
            availability=_fixture_availability('Unavailable', ref, raw_score=30.0, days_ago=1, pitches=52),
            role=_fixture_role('depth'),
        ),
        _fixture_board_record(
            name='Fixture Fresh Depth Arm',
            pitcher_id=9106,
            availability=_fixture_availability('Available', ref, raw_score=18.0, days_ago=4, pitches=6),
            role=_fixture_role('depth'),
        ),
    ]
    return build_board_payload(
        team={
            'team_id': 'fixture-context',
            'team_name': 'Deterministic Context Fixture',
            'team_abbreviation': 'FIX',
        },
        records=records,
        freshness={
            'is_current': True,
            'freshness_state': 'current',
            'data_through': '2026-06-01',
            'limitations': [],
        },
        workload_concentration=summarize_workload_concentration({
            9101: 42,
            9102: 28,
            9103: 14,
            9104: 10,
            9105: 6,
        }),
        generated_at='2026-06-03T12:05:00Z',
    )


def _fixture_readiness_examples(
    current_examples: Iterable[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    from explanations import serialize_readiness_explanation
    from team_operations import assemble_bullpen_readiness

    readiness_seen = {
        str((example.get('role_or_classification') or {}).get('readiness_status_code'))
        for example in current_examples
        if example.get('surface_name') == 'Team Operations readiness V4 explanation'
    }
    fixture_payloads = [
        assemble_bullpen_readiness(
            team=_fixture_team(),
            pitcher_records=_fixture_stable_readiness_records(),
            trust_metadata=_fixture_trust_metadata(),
            freshness=_fixture_freshness_metadata(),
            generated_at='2026-06-03T12:00:00Z',
        ),
        assemble_bullpen_readiness(
            team=_fixture_team(),
            pitcher_records=_fixture_constrained_readiness_records(),
            trust_metadata=_fixture_trust_metadata(),
            freshness=_fixture_freshness_metadata(),
            generated_at='2026-06-03T12:00:00Z',
        ),
        assemble_bullpen_readiness(
            team=_fixture_team(),
            pitcher_records=_fixture_stressed_readiness_records(),
            trust_metadata=_fixture_trust_metadata(),
            freshness=_fixture_freshness_metadata(),
            generated_at='2026-06-03T12:00:00Z',
        ),
        assemble_bullpen_readiness(
            team=_fixture_team(),
            pitcher_records=_fixture_stable_readiness_records(),
            trust_metadata=None,
            freshness=_fixture_freshness_metadata(),
            generated_at='2026-06-03T12:00:00Z',
        ),
    ]

    examples = []
    for payload in fixture_payloads:
        status = str((payload.get('readiness') or {}).get('status_code') or 'unknown')
        if status in readiness_seen:
            continue
        explanation = serialize_readiness_explanation(
            payload,
            scope='readiness_state',
            generated_at='2026-06-03T12:05:00Z',
        )
        example = _readiness_explanation_example(payload, explanation, 'readiness_state')
        example['source_path'] = (
            'backend/tests/test_v4_team_operations_readiness_explanation_integration.py fixture pattern -> '
            'team_operations.assemble_bullpen_readiness -> '
            'explanations.readiness.serialize_readiness_explanation'
        )
        examples.append(_mark_fixture(example))
    return examples


def _fixture_board_card_label_examples(board: Mapping[str, Any]) -> list[dict[str, Any]]:
    examples = []
    for group in board.get('groups') or []:
        pitchers = group.get('pitchers') or []
        if not pitchers:
            continue
        examples.append(_team_board_card_label_example(board, group, pitchers[0]))
    return examples


def _team_board_card_label_example(
    board: Mapping[str, Any],
    group: Mapping[str, Any],
    card: Mapping[str, Any],
) -> dict[str, Any]:
    labels = card.get('pitcher_labels') or {}
    return _mark_fixture({
        'surface_name': 'Team bullpen board card labels',
        'team': _team_label(board.get('team')),
        'pitcher': card.get('name'),
        'status': group.get('status'),
        'role_or_classification': {
            'group': group.get('label'),
            'role': (labels.get('role') or {}).get('label'),
            'read': (labels.get('read') or {}).get('label'),
        },
        'source_path': (
            'services.bullpen_board.build_board_payload -> '
            'services.pitcher_public_labels.build_pitcher_labels'
        ),
        'fallback_status': 'rendered',
        'rendered_public_copy': _dedupe_strings([
            group.get('label'),
            group.get('description'),
            card.get('short_reason'),
            (labels.get('role') or {}).get('label'),
            (labels.get('read') or {}).get('label'),
        ]),
        'structured_fields_used': {
            'group': _subset(group, ('status', 'label', 'description', 'count')),
            'card': _subset(
                card,
                (
                    'pitcher_id',
                    'availability_status',
                    'fatigue_score',
                    'confidence',
                    'short_reason',
                    'data_state',
                    'reasons',
                    'limitations',
                    'role',
                    'pitcher_labels',
                ),
            ),
        },
        'evidence_sections': {
            'last_workload_appearance': card.get('last_workload_appearance'),
        },
    })


def _mark_fixture(example: dict[str, Any]) -> dict[str, Any]:
    example['example_source'] = DETERMINISTIC_FIXTURE_EXAMPLE
    return example


def _fixture_score(raw_score: float) -> SimpleNamespace:
    return SimpleNamespace(raw_score=raw_score, risk_level='LOW')


def _fixture_log(game_date: date, pitches: int) -> SimpleNamespace:
    return SimpleNamespace(game_date=game_date, pitches_thrown=pitches)


def _fixture_pitcher(status: str, index: int) -> SimpleNamespace:
    return SimpleNamespace(
        id=f'fixture-{index}',
        full_name=f'Deterministic fixture pitcher - {status}',
        team_id='fixture-context',
        team_name='Deterministic Context Fixture',
        team_abbreviation='FIX',
    )


def _fixture_availability(
    status: str,
    ref: date,
    *,
    raw_score: float,
    days_ago: int,
    pitches: int,
) -> Mapping[str, Any]:
    from services.availability import classify_availability

    log = _fixture_log(ref - timedelta(days=days_ago), pitches)
    availability = classify_availability(
        score=_fixture_score(raw_score),
        game_logs=[log],
        reference_date=ref,
        latest_game_date=log.game_date,
    )
    if availability.get('availability_status') != status:
        raise RuntimeError(
            'deterministic availability fixture did not produce expected status '
            f'{status!r}: {availability.get("availability_status")!r}'
        )
    return availability


def _fixture_pitcher_detail_payload(
    availability: Mapping[str, Any],
    log: SimpleNamespace,
    *,
    role: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'availability': dict(availability),
        'workload_signal': dict(availability),
        'roster_status': {},
        'freshness': {},
        'role': dict(role or {}),
        'last_workload_appearance': {
            'game_date': log.game_date.isoformat(),
            'pitches': log.pitches_thrown,
        },
        'recent_logs': [
            {
                'game_date': log.game_date.isoformat(),
                'pitches_thrown': log.pitches_thrown,
            }
        ],
        'fatigue_trend': [],
    }


def _fixture_role(role_key: str) -> dict[str, Any]:
    return {
        'role_key': role_key,
        'sample_size': 5,
        'confidence': 'high',
    }


def _fixture_board_record(
    *,
    name: str,
    pitcher_id: int,
    availability: Mapping[str, Any],
    role: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        'name': name,
        'pitcher_id': pitcher_id,
        'fatigue_score': (availability.get('inputs') or {}).get('raw_score'),
        'availability': availability,
        'role': role,
        'eligibility': {'status': 'eligible'},
        'roster_status': {'status': 'active'},
        'last_workload_appearance': {
            'game_date': (availability.get('inputs') or {}).get('last_game_date'),
            'pitches': (availability.get('inputs') or {}).get('pitches_yesterday'),
        },
    }


def _fixture_team() -> dict[str, Any]:
    return {
        'team_id': 'fixture-context',
        'team_name': 'Deterministic Context Fixture',
        'team_abbreviation': 'FIX',
    }


def _fixture_trust_metadata(**overrides) -> dict[str, Any]:
    payload = {
        'confidence': 'high',
        'confidence_reasons': ['fresh_data', 'complete_metadata'],
        'data_state': 'fresh',
        'source_evidence_state': 'represented',
        'governance_state': 'compliant',
        'generated_at': '2026-06-03T12:00:00Z',
        'limitations': [],
        'explanations': [],
        'refusal_reasons': [],
        'trust_validation_errors': [],
        'ranking_applied': False,
        'selection_made': False,
    }
    payload.update(overrides)
    return payload


def _fixture_freshness_metadata(**overrides) -> dict[str, Any]:
    payload = {
        'freshness_state': 'current',
        'data_through': '2026-06-03',
        'latest_workload_date': '2026-06-03',
        'last_successful_sync': '2026-06-03T11:30:00Z',
        'latest_sync_status': 'success',
        'latest_fatigue_calculated_at': '2026-06-03T11:45:00Z',
        'generated_at': '2026-06-03T12:00:00Z',
        'stale_warning': None,
        'missing_data_warning': None,
        'limitations': [],
    }
    payload.update(overrides)
    return payload


def _fixture_stable_readiness_records() -> tuple[dict[str, str], ...]:
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'right',
        },
    )


def _fixture_constrained_readiness_records() -> tuple[dict[str, str], ...]:
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'monitor',
            'workload_category': 'moderate',
            'throwing_hand': 'right',
        },
        {
            'availability_status': 'limited',
            'workload_category': 'low',
            'throwing_hand': 'right',
        },
    )


def _fixture_stressed_readiness_records() -> tuple[dict[str, str], ...]:
    return (
        {
            'availability_status': 'available',
            'workload_category': 'low',
            'throwing_hand': 'left',
        },
        {
            'availability_status': 'unavailable',
            'workload_category': 'elevated',
            'throwing_hand': 'right',
        },
    )


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
    banned = find_editorial_violations(text)
    example['banned_language_scan'] = {
        'status': 'pass' if not banned else 'warn',
        'violation_count': len(banned),
        'violations': banned,
    }
    retired = find_editorial_violations(text, terms=RETIRED_PUBLIC_PHRASES)
    example['retired_phrase_scan'] = {
        'status': 'pass' if not retired else 'warn',
        'violation_count': len(retired),
        'violations': retired,
        'terms': RETIRED_PUBLIC_PHRASES,
    }
    example['raw_count_formula_scan'] = _raw_count_formula_scan([example])
    example['weighting_scoring_scan'] = _weighting_scoring_scan([example])
    example['circular_meta_scan'] = _circular_meta_scan([example])
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


def _raw_count_formula_scan(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    violations = []
    for index, example in enumerate(examples, start=1):
        text = '\n'.join(_public_texts(example))
        for match in RAW_COUNT_FORMULA_PATTERN.finditer(text):
            if match.group(0).strip().lower() == '0 of 0':
                violations.append(_scan_row(index, example, match.group(0), 'raw empty arithmetic pattern', match.start()))
        for match in JARGON_COUPLED_RAW_COUNT_PATTERN.finditer(text):
            violations.append(_scan_row(index, example, match.group(0), 'jargon-coupled raw arithmetic pattern', match.start()))
        for match in PARENTHETICAL_RAW_BASIS_PATTERN.finditer(text):
            violations.append(_scan_row(index, example, match.group(0), 'parenthetical raw basis', match.start()))
        for match in PARENTHETICAL_UNKNOWN_FORMULA_PATTERN.finditer(text):
            violations.append(_scan_row(index, example, match.group(0), 'parenthetical unknown formula', match.start()))
        lowered = text.lower()
        for term in FORMULA_TERMS:
            start = lowered.find(term)
            if start >= 0:
                violations.append(_scan_row(index, example, text[start:start + len(term)], term, start))
    return {
        'scope': 'rendered public context explanation copy only',
        'status': 'pass' if not violations else 'warn',
        'violation_count': len(violations),
        'violations': violations,
        'terms': FORMULA_TERMS,
        'patterns': {
            'raw_empty_arithmetic': RAW_COUNT_FORMULA_PATTERN.pattern,
            'jargon_coupled_raw_count': JARGON_COUPLED_RAW_COUNT_PATTERN.pattern,
            'parenthetical_raw_basis': PARENTHETICAL_RAW_BASIS_PATTERN.pattern,
            'parenthetical_unknown_formula': PARENTHETICAL_UNKNOWN_FORMULA_PATTERN.pattern,
        },
    }


def _weighting_scoring_scan(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    violations = []
    for index, example in enumerate(examples, start=1):
        text = '\n'.join(_public_texts(example))
        lowered = text.lower()
        for term in WEIGHTING_SCORING_TERMS:
            start = lowered.find(term)
            if start >= 0:
                violations.append(_scan_row(index, example, text[start:start + len(term)], term, start))
    return {
        'scope': 'rendered public context explanation copy only',
        'status': 'pass' if not violations else 'warn',
        'violation_count': len(violations),
        'violations': violations,
        'terms': WEIGHTING_SCORING_TERMS,
    }


def _circular_meta_scan(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    violations = []
    for index, example in enumerate(examples, start=1):
        text = '\n'.join(_public_texts(example))
        lowered = text.lower()
        for term in CIRCULAR_META_TERMS:
            start = lowered.find(term)
            if start >= 0:
                violations.append(_scan_row(index, example, text[start:start + len(term)], term, start))
    return {
        'scope': 'rendered public context explanation copy only',
        'status': 'pass' if not violations else 'warn',
        'violation_count': len(violations),
        'violations': violations,
        'terms': CIRCULAR_META_TERMS,
    }


def _scan_row(
    index: int,
    example: Mapping[str, Any],
    match: str,
    term: str,
    start: int,
) -> dict[str, Any]:
    return {
        'example_index': index,
        'surface_name': example.get('surface_name'),
        'team': example.get('team'),
        'pitcher': example.get('pitcher'),
        'term': term,
        'match': match,
        'start': start,
    }


def _disclaimer_preservation_check(examples: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    readiness_text = '\n'.join(
        text
        for example in examples
        if example.get('surface_name') == 'Team Operations readiness V4 explanation'
        for text in _public_texts(example)
    )
    missing = [
        disclaimer for disclaimer in TRUST_FIRST_DISCLAIMERS
        if disclaimer not in readiness_text
    ]
    return {
        'scope': 'Team Operations readiness V4 rendered public copy',
        'status': 'pass' if not missing else 'warn',
        'required_disclaimers': TRUST_FIRST_DISCLAIMERS,
        'missing_disclaimers': missing,
    }


def _before_after_summary(
    *,
    scans: Mapping[str, Any],
    raw_count_formula_scan: Mapping[str, Any],
    weighting_scoring_scan: Mapping[str, Any],
    circular_meta_scan: Mapping[str, Any],
    disclaimer_check: Mapping[str, Any],
) -> dict[str, Any]:
    prior_path = Path('artifacts/context_explanation_editorial_review_E2D1.md')
    prior_text = prior_path.read_text(encoding='utf-8') if prior_path.exists() else ''
    prior_flags = {
        'raw_arithmetic_examples': len(RAW_COUNT_FORMULA_PATTERN.findall(prior_text)),
        'formula_term_examples': sum(prior_text.lower().count(term) for term in FORMULA_TERMS),
        'circular_meta_examples': sum(prior_text.lower().count(term) for term in CIRCULAR_META_TERMS),
    } if prior_text else {}
    return {
        'prior_artifact': str(prior_path) if prior_text else None,
        'prior_artifact_string_counts': prior_flags,
        'current_banned_language_status': (scans.get('banned_language_scan') or {}).get('status'),
        'current_retired_phrase_status': (scans.get('retired_phrase_scan') or {}).get('status'),
        'current_raw_count_formula_status': raw_count_formula_scan.get('status'),
        'current_weighting_scoring_status': weighting_scoring_scan.get('status'),
        'current_circular_meta_status': circular_meta_scan.get('status'),
        'disclaimer_preservation_status': disclaimer_check.get('status'),
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
    by_source = Counter(str(example.get('example_source') or 'unknown') for example in examples)
    board_groups_found = _board_groups_found(examples)
    role_read = _role_and_read_labels_found(examples)
    shape_labels = sorted({
        str(label)
        for example in examples
        if example.get('surface_name') == 'Team bullpen shape explanations'
        for label in ((example.get('role_or_classification') or {}).get('read_labels') or [])
    })
    return {
        'examples_exported': len(examples),
        'examples_by_source': dict(sorted(by_source.items())),
        'stored_data_examples': by_source.get(STORED_DATA_EXAMPLE, 0),
        'fixture_backed_examples': by_source.get(DETERMINISTIC_FIXTURE_EXAMPLE, 0),
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
        'board_card_groups_found': {
            status: count
            for status, count in sorted(board_groups_found.items())
            if count > 0
        },
        'role_labels_found': role_read['role_labels_found'],
        'read_labels_found': role_read['read_labels_found'],
        'team_shape_read_labels_found': shape_labels,
        'missing_categories': dict(missing),
    }


def _missing_categories_from_examples(
    examples: Iterable[Mapping[str, Any]],
    *,
    previous_missing: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    examples = list(examples)
    previous_missing = previous_missing or {}
    availability_found = {
        str(example.get('status'))
        for example in examples
        if example.get('surface_name') == 'Pitcher V4 availability explanation'
    }
    detail_found = {
        str(example.get('status'))
        for example in examples
        if example.get('surface_name') == 'Pitcher Context modal/detail route'
    }
    board_groups = _board_groups_found(examples)
    readiness_found = {
        str((example.get('role_or_classification') or {}).get('readiness_status_code'))
        for example in examples
        if example.get('surface_name') == 'Team Operations readiness V4 explanation'
    }
    role_read = _role_and_read_labels_found(examples)
    shape_has_non_limited = any(
        label and label != 'Limited Read'
        for example in examples
        if example.get('surface_name') == 'Team bullpen shape explanations'
        for label in ((example.get('role_or_classification') or {}).get('read_labels') or [])
    )

    missing: dict[str, Any] = {}
    missing_availability = [
        status for status in PITCHER_AVAILABILITY_STATUSES
        if status not in availability_found
    ]
    if missing_availability:
        missing['pitcher_availability_statuses'] = missing_availability

    missing_detail = [
        status for status in PITCHER_AVAILABILITY_STATUSES
        if status not in detail_found
    ]
    if missing_detail:
        missing['pitcher_context_modal_statuses'] = missing_detail

    missing_board_groups = [
        status for status in BOARD_GROUP_STATUSES
        if board_groups.get(status, 0) == 0
    ]
    if missing_board_groups:
        missing['board_card_groups_with_no_current_cards'] = missing_board_groups

    missing_readiness = [
        status for status in TEAM_READINESS_STATUSES
        if status not in readiness_found
    ]
    if missing_readiness:
        missing['team_readiness_statuses'] = missing_readiness

    missing_role_keys = [
        key for key in ('trust_arm', 'bridge_arm', 'coverage_arm', 'depth_arm', 'limited_read')
        if key not in role_read['role_keys_found']
    ]
    missing_read_keys = [
        key for key in ('clean_option', 'watch_arm', 'rest_restricted', 'unavailable', 'limited_read')
        if key not in role_read['read_keys_found']
    ]
    if missing_role_keys or missing_read_keys:
        missing['role_label_examples'] = {
            'missing_role_keys': missing_role_keys,
            'missing_read_keys': missing_read_keys,
        }

    if not shape_has_non_limited:
        missing['team_shape_non_limited_examples'] = (
            'No non-limited team-shape examples were captured.'
        )

    for key in ('availability_read_errors', 'team_readiness_errors'):
        if previous_missing.get(key):
            missing[key] = previous_missing[key]

    return missing


def _board_groups_found(examples: Iterable[Mapping[str, Any]]) -> Counter[str]:
    groups_found: Counter[str] = Counter()
    for example in examples:
        if example.get('surface_name') != 'Team bullpen board context':
            continue
        fields = example.get('structured_fields_used') or {}
        for group in fields.get('groups') or []:
            status = group.get('status')
            if status:
                groups_found[str(status)] += int(group.get('count') or 0)
    return groups_found


def _role_and_read_labels_found(examples: Iterable[Mapping[str, Any]]) -> dict[str, list[str]]:
    role_labels = set()
    read_labels = set()
    role_keys = set()
    read_keys = set()
    for example in examples:
        if example.get('surface_name') not in {
            'Pitcher public role/read labels',
            'Team bullpen board card labels',
        }:
            continue
        fields = example.get('structured_fields_used') or {}
        labels = fields.get('labels') or {}
        card = fields.get('card') or {}
        if card:
            labels = card.get('pitcher_labels') or {}
        role = labels.get('role') or {}
        read = labels.get('read') or {}
        if role.get('label'):
            role_labels.add(str(role.get('label')))
        if read.get('label'):
            read_labels.add(str(read.get('label')))
        if role.get('key'):
            role_keys.add(str(role.get('key')))
        if read.get('key'):
            read_keys.add(str(read.get('key')))
    return {
        'role_labels_found': sorted(role_labels),
        'read_labels_found': sorted(read_labels),
        'role_keys_found': sorted(role_keys),
        'read_keys_found': sorted(read_keys),
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
            'example_source',
            'surface_name',
            'team',
            'pitcher',
            'status',
            'role_or_classification',
            'source_path',
            'fallback_status',
            'banned_language_scan',
            'retired_phrase_scan',
            'raw_count_formula_scan',
            'weighting_scoring_scan',
            'circular_meta_scan',
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
            'before_after_summary',
            'weighting_scoring_scan',
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
