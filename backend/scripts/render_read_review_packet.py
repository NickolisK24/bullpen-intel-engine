import argparse
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ['AUTO_SYNC'] = 'false'

from models.composed_read import ComposedRead  # noqa: E402
from models.legacy_read_audit import LegacyReadDivergence  # noqa: E402


INTERNAL_WATERMARK = (
    'INTERNAL ONLY - Phase 0E read review packet; not a public surface.'
)
READ_TYPES = ('reliever_daily_read', 'team_daily_read')
SCENARIO_BASE_DATE = date(2026, 7, 5)
SCENARIO_NAMES = (
    'opening_week_small_samples',
    'off_day_team',
    'doubleheader',
    'suspended_resumed_game',
    'incomplete_slate',
    'postponed_game',
    'trade_deadline_churn',
    'option_recall_churn',
    'il_placement_activation_timing',
    'september_call_up',
    'roster_snapshot_stale',
    'transaction_coverage_gap',
    'idle_team_trailing_windows',
    'relief_history_missing_membership',
    'rostered_cold_arm_gap',
    'missing_contributor_basis',
    'legacy_snapshot_missing',
    'composed_reads_missing',
    'conflict_state_evidence',
    'mid_window_correction_recompute',
    'locked_band_consumption_attempt',
    'legacy_factual_field_contradiction',
    'covered_window_zero_transactions',
)


@dataclass(frozen=True)
class PacketRows:
    reads: tuple[ComposedRead, ...]
    divergences: tuple[LegacyReadDivergence, ...]


FIXED_PACKET_TEXT = """
INTERNAL ONLY Phase 0E read review packet not a public surface
Phase 0E Read Review Packet
Scope
watermark
dates
scenario_mode
Read Samples
read_type
subject_type
subject_id
product_date
completeness_state
reason_codes
limitations
component
required
component_state
evidence
rule_id
evidence_type
cited_completeness_state
rendered_claim
Reconciliation Samples
category
is_material
escalation_state
comparison_basis
notes
legacy_capture
read_capture
none
true
false
"""


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Render an internal Phase 0E read review packet.'
    )
    selector = parser.add_mutually_exclusive_group(required=True)
    selector.add_argument('--date', dest='product_date', help='Product date, YYYY-MM-DD.')
    selector.add_argument(
        '--scenario',
        dest='scenario',
        help='Scenario name, comma-separated names, or all.',
    )
    parser.add_argument(
        '--output',
        required=True,
        dest='output_path',
        help='Markdown file path to write.',
    )
    return parser.parse_args(argv)


def scenario_product_dates(value: str) -> tuple[date, ...]:
    names = SCENARIO_NAMES if value == 'all' else tuple(
        item.strip() for item in str(value or '').split(',') if item.strip()
    )
    unknown = sorted(set(names) - set(SCENARIO_NAMES))
    if unknown:
        raise ValueError(f'unknown scenarios: {unknown}')
    return tuple(
        SCENARIO_BASE_DATE - timedelta(days=SCENARIO_NAMES.index(name) + 1)
        for name in SCENARIO_NAMES
        if name in names
    )


def collect_packet_rows(*, product_date=None, scenario=None) -> PacketRows:
    if product_date is not None:
        dates = (product_date if isinstance(product_date, date) else date.fromisoformat(str(product_date)),)
        reads = _date_mode_reads(dates[0])
    else:
        dates = scenario_product_dates(scenario)
        reads = _scenario_mode_reads(dates)
    return PacketRows(
        reads=tuple(reads),
        divergences=tuple(_sample_divergences(dates)),
    )


def render_packet_markdown(rows: PacketRows, *, product_date=None, scenario=None) -> str:
    dates = sorted({read.product_date for read in rows.reads} | {
        row.product_date for row in rows.divergences
    })
    if product_date is not None:
        dates = [product_date if isinstance(product_date, date) else date.fromisoformat(str(product_date))]
    lines = [
        INTERNAL_WATERMARK,
        '',
        '# Phase 0E Read Review Packet',
        '',
        '## Scope',
        f'- watermark: {INTERNAL_WATERMARK}',
        f'- dates: {",".join(day.isoformat() for day in dates)}',
        f'- scenario_mode: {str(scenario is not None).lower()}',
        '',
        '## Read Samples',
    ]
    if not rows.reads:
        lines.append('- none')
    for read in rows.reads:
        lines.append(
            '- '
            f'read_type={read.read_type}; '
            f'subject_type={read.subject_type}; '
            f'subject_id={read.subject_id}; '
            f'product_date={read.product_date.isoformat()}; '
            f'completeness_state={read.completeness_state}; '
            f'reason_codes={json.dumps(read.reason_codes or [], sort_keys=True)}; '
            f'limitations={json.dumps(read.limitations or [], sort_keys=True)}'
        )
        for component in sorted(read.components, key=lambda item: item.component_name):
            lines.append(
                '  - '
                f'component={component.component_name}; '
                f'required={str(bool(component.required)).lower()}; '
                f'component_state={component.component_state}; '
                f'reason_codes={json.dumps(component.reason_codes or [], sort_keys=True)}; '
                f'limitations={json.dumps(component.limitations or [], sort_keys=True)}'
            )
            for citation in sorted(component.evidence_citations, key=lambda item: item.id):
                evidence = citation.evidence_object
                if evidence is None:
                    continue
                lines.append(
                    '    - '
                    f'evidence={evidence.id}; '
                    f'rule_id={evidence.rule_id}; '
                    f'evidence_type={evidence.evidence_type}; '
                    f'cited_completeness_state={citation.cited_completeness_state}; '
                    f'rendered_claim={json.dumps(evidence.rendered_claim)}'
                )
    lines.extend(['', '## Reconciliation Samples'])
    if not rows.divergences:
        lines.append('- none')
    for row in rows.divergences:
        lines.append(
            '- '
            f'category={row.category}; '
            f'subject_type={row.subject_type}; '
            f'subject_id={row.subject_id}; '
            f'product_date={row.product_date.isoformat()}; '
            f'is_material={str(bool(row.is_material)).lower()}; '
            f'escalation_state={row.escalation_state}; '
            f'comparison_basis={row.comparison_basis}; '
            f'notes={json.dumps(row.notes)}; '
            f'legacy_capture={json.dumps(row.legacy_capture or {}, sort_keys=True)}; '
            f'read_capture={json.dumps(row.read_capture or {}, sort_keys=True)}'
        )
    lines.extend(['', INTERNAL_WATERMARK, ''])
    return '\n'.join(lines)


def render_review_packet(*, output_path, product_date=None, scenario=None) -> dict:
    rows = collect_packet_rows(product_date=product_date, scenario=scenario)
    markdown = render_packet_markdown(rows, product_date=product_date, scenario=scenario)
    assert_packet_tokens_allowed(markdown, rows)
    path = Path(output_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown, encoding='utf-8')
    return {
        'status': 'rendered',
        'output_path': str(path),
        'read_count': len(rows.reads),
        'divergence_count': len(rows.divergences),
    }


def assert_packet_tokens_allowed(markdown: str, rows: PacketRows) -> bool:
    allowed = _tokens(FIXED_PACKET_TEXT)
    for read in rows.reads:
        allowed.update(_tokens(_jsonish(read.read_type)))
        allowed.update(_tokens(_jsonish(read.subject_type)))
        allowed.update(_tokens(_jsonish(read.subject_id)))
        allowed.update(_tokens(read.product_date.isoformat()))
        allowed.update(_tokens(_jsonish(read.completeness_state)))
        allowed.update(_tokens(_jsonish(read.reason_codes or [])))
        allowed.update(_tokens(_jsonish(read.limitations or [])))
        for component in read.components:
            allowed.update(_tokens(_jsonish(component.component_name)))
            allowed.update(_tokens(_jsonish(component.component_state)))
            allowed.update(_tokens(_jsonish(component.reason_codes or [])))
            allowed.update(_tokens(_jsonish(component.limitations or [])))
            for citation in component.evidence_citations:
                allowed.update(_tokens(_jsonish(citation.cited_completeness_state)))
                evidence = citation.evidence_object
                if evidence is not None:
                    allowed.update(_tokens(_jsonish(evidence.id)))
                    allowed.update(_tokens(_jsonish(evidence.rule_id)))
                    allowed.update(_tokens(_jsonish(evidence.evidence_type)))
                    allowed.update(_tokens(_jsonish(evidence.rendered_claim)))
    for row in rows.divergences:
        allowed.update(_tokens(_jsonish(row.category)))
        allowed.update(_tokens(_jsonish(row.subject_type)))
        allowed.update(_tokens(_jsonish(row.subject_id)))
        allowed.update(_tokens(row.product_date.isoformat()))
        allowed.update(_tokens(_jsonish(row.escalation_state)))
        allowed.update(_tokens(_jsonish(row.comparison_basis)))
        allowed.update(_tokens(_jsonish(row.notes)))
        allowed.update(_tokens(_jsonish(row.legacy_capture or {})))
        allowed.update(_tokens(_jsonish(row.read_capture or {})))
    extra = sorted(_tokens(markdown) - allowed)
    if extra:
        raise AssertionError(f'review packet contains unapproved prose tokens: {extra[:20]}')
    return True


def _date_mode_reads(product_date: date) -> list[ComposedRead]:
    rows = []
    for read_type in READ_TYPES:
        rows.extend(
            ComposedRead.query
            .filter_by(
                product_date=product_date,
                read_type=read_type,
                recompute_status=ComposedRead.RECOMPUTE_CURRENT,
            )
            .order_by(ComposedRead.subject_id.asc(), ComposedRead.id.asc())
            .limit(3)
            .all()
        )
    return rows


def _scenario_mode_reads(product_dates: tuple[date, ...]) -> list[ComposedRead]:
    if not product_dates:
        return []
    return (
        ComposedRead.query
        .filter(ComposedRead.product_date.in_(product_dates))
        .order_by(ComposedRead.product_date.desc(), ComposedRead.read_type.asc(), ComposedRead.subject_id.asc())
        .all()
    )


def _sample_divergences(product_dates: tuple[date, ...]) -> list[LegacyReadDivergence]:
    if not product_dates:
        return []
    rows = (
        LegacyReadDivergence.query
        .filter(LegacyReadDivergence.product_date.in_(product_dates))
        .order_by(
            LegacyReadDivergence.category.asc(),
            LegacyReadDivergence.product_date.asc(),
            LegacyReadDivergence.id.asc(),
        )
        .all()
    )
    result = []
    counts = defaultdict(int)
    for row in rows:
        if counts[row.category] >= 3:
            continue
        result.append(row)
        counts[row.category] += 1
    return result


def _jsonish(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _tokens(value: str) -> set[str]:
    return set(re.findall(r'[A-Za-z_][A-Za-z0-9_]*|\d{4}-\d{2}-\d{2}|\d+', str(value)))


def main(argv=None):
    args = _parse_args(argv)
    from app import app
    from utils.db import db

    with app.app_context():
        if args.product_date:
            result = render_review_packet(
                product_date=date.fromisoformat(args.product_date),
                output_path=args.output_path,
            )
        else:
            result = render_review_packet(
                scenario=args.scenario,
                output_path=args.output_path,
            )
    db.session.remove()
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
