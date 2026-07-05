"""Internal Phase 0E legacy-read reconciliation audit."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import json
from pathlib import Path
import re
from typing import Mapping

from sqlalchemy import asc, desc

from models.composed_read import ComposedRead
from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.legacy_read_audit import LegacyReadAuditRun, LegacyReadDivergence
from models.roster_status_snapshot import RosterStatusSnapshot
from services import dashboard_snapshot as dashboard_snapshot_service
from utils.db import db
from utils.time import utc_now_naive


CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING = (
    LegacyReadDivergence.CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING
)
CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING = (
    LegacyReadDivergence.CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING
)
CATEGORY_ACTIONABLE_ON_DEGRADED_READ = (
    LegacyReadDivergence.CATEGORY_ACTIONABLE_ON_DEGRADED_READ
)
CATEGORY_CONFIDENT_ON_STALE_INPUTS = (
    LegacyReadDivergence.CATEGORY_CONFIDENT_ON_STALE_INPUTS
)
CATEGORY_STATE_CONTRADICTS_FACT = (
    LegacyReadDivergence.CATEGORY_STATE_CONTRADICTS_FACT
)
CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ = (
    LegacyReadDivergence.CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ
)
CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION = (
    LegacyReadDivergence.CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION
)
CATEGORY_STRUCTURAL_VOCABULARY = 'legacy_vocabulary_blocked_for_evidence_reads'

CATEGORY_CODES = (
    CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING,
    CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING,
    CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
    CATEGORY_CONFIDENT_ON_STALE_INPUTS,
    CATEGORY_STATE_CONTRADICTS_FACT,
    CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ,
    CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION,
    CATEGORY_STRUCTURAL_VOCABULARY,
)

LEGACY_VOCABULARY_MAP = {
    'Available': 'decisive_positive',
    'Monitor': 'decisive_caution',
    'Limited': 'decisive_caution',
    'Avoid': 'decisive_negative',
    'Unavailable': 'decisive_negative',
    'Trust Arm': 'informational_role_display',
    'Bridge Arm': 'informational_role_display',
    'Coverage Arm': 'informational_role_display',
    'Depth Arm': 'informational_role_display',
    'Limited Read': 'informational_degraded_display',
    'fresh': 'informational',
}

DECISIVE_MAPPINGS = {
    'decisive_positive',
    'decisive_caution',
    'decisive_negative',
}

FORBIDDEN_NEUTRAL_WORDS = (
    'wrong',
    'incorrect',
    'broken',
    'defective',
    'misleading',
)

NO_ADJUDICATION_NOTE = 'Absence of evidence does not adjudicate the legacy label.'
INTERNAL_WATERMARK = (
    'INTERNAL ONLY - legacy read reconciliation audit; not a public surface.'
)
REPORT_ESCALATION_PHRASE = 'candidate for legacy-engine defect review'
EVIDENCE_SOURCE = 'phase0e:legacy_read_reconciliation_audit'
LEGACY_AUDIT_FAILURE_ENTITY_TYPE = 'phase0e_legacy_read_reconciliation_audit'

_REPO_ROOT = Path(__file__).resolve().parents[2]


def phase0e_reconciliation_audit_enabled(env=None) -> bool:
    env = env or {}
    value = env.get('PHASE0E_RECONCILIATION_AUDIT')
    if value is None:
        import os
        value = os.environ.get('PHASE0E_RECONCILIATION_AUDIT', 'true')
    return str(value).strip().lower() not in {'0', 'false', 'no', 'off'}


def run_reconciliation_audit(
    product_date,
    *,
    subject_type=None,
    sync_run_id=None,
    source='manual',
    commit=False,
    force_skip_reads_missing=False,
) -> dict:
    ref = _as_date(product_date)
    subject_types = _subject_types(subject_type)
    results = {}
    for current_subject_type in subject_types:
        results[current_subject_type] = _run_subject_audit(
            ref,
            current_subject_type,
            sync_run_id=sync_run_id,
            source=source,
            force_skip_reads_missing=force_skip_reads_missing,
        )
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return {
        'status': 'completed',
        'product_date': ref.isoformat(),
        'subjects': results,
    }


def render_reconciliation_report(start_date, end_date=None, *, output_path) -> dict:
    start = _as_date(start_date)
    end = _as_date(end_date or start_date)
    if end < start:
        raise ValueError('end_date must be on or after start_date')
    md_path, json_path = _report_paths(output_path)

    runs = (
        LegacyReadAuditRun.query
        .filter(LegacyReadAuditRun.product_date >= start)
        .filter(LegacyReadAuditRun.product_date <= end)
        .order_by(
            asc(LegacyReadAuditRun.product_date),
            asc(LegacyReadAuditRun.subject_type),
        )
        .all()
    )
    rows = (
        LegacyReadDivergence.query
        .filter(LegacyReadDivergence.product_date >= start)
        .filter(LegacyReadDivergence.product_date <= end)
        .order_by(
            asc(LegacyReadDivergence.product_date),
            asc(LegacyReadDivergence.id),
        )
        .all()
    )
    payload = _report_payload(start, end, runs, rows)
    markdown = _render_markdown(payload)
    validate_neutral_text(markdown, allow_report_escalation=True)

    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text(markdown, encoding='utf-8')
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding='utf-8')
    return {
        'status': 'rendered',
        'markdown_path': str(md_path),
        'json_path': str(json_path),
        'divergence_count': len(rows),
        'run_count': len(runs),
    }


def validate_neutral_text(text, *, allow_report_escalation=False) -> bool:
    checked = str(text or '')
    if allow_report_escalation:
        checked = checked.replace(REPORT_ESCALATION_PHRASE, '')
    for word in FORBIDDEN_NEUTRAL_WORDS:
        if re.search(rf'\b{re.escape(word)}\b', checked, flags=re.I):
            raise AssertionError(f'non-neutral audit language: {word}')
    return True


def _run_subject_audit(
    product_date,
    subject_type,
    *,
    sync_run_id,
    source,
    force_skip_reads_missing=False,
) -> dict:
    _replace_existing(product_date, subject_type)

    reads = _read_captures(product_date, subject_type)
    if force_skip_reads_missing or not reads:
        run = _audit_run(
            product_date,
            subject_type,
            run_status=LegacyReadAuditRun.STATUS_SKIPPED_READS_MISSING,
            source=source,
            sync_run_id=sync_run_id,
        )
        db.session.add(run)
        db.session.flush()
        return run.to_dict()

    snapshot = _published_snapshot_for_date(product_date)
    if snapshot is None:
        run = _audit_run(
            product_date,
            subject_type,
            run_status=LegacyReadAuditRun.STATUS_SKIPPED_LEGACY_MISSING,
            source=source,
            sync_run_id=sync_run_id,
        )
        db.session.add(run)
        db.session.flush()
        return run.to_dict()

    legacy = _legacy_captures(snapshot, subject_type)
    subjects = _subject_population(product_date, subject_type, reads, legacy)
    divergences = []
    aligned_count = 0
    for subject_id in subjects:
        subject_divergences = _subject_divergences(
            subject_type=subject_type,
            subject_id=str(subject_id),
            product_date=product_date,
            legacy_capture=legacy.get(str(subject_id)),
            read_capture=reads.get(str(subject_id)),
            source=source,
            sync_run_id=sync_run_id,
        )
        if subject_divergences:
            divergences.extend(subject_divergences)
        else:
            aligned_count += 1

    for row in divergences:
        db.session.add(row)
    counts = Counter(row.category for row in divergences)
    run = _audit_run(
        product_date,
        subject_type,
        subjects_compared=len(subjects),
        aligned_count=aligned_count,
        divergence_count_by_category=dict(sorted(counts.items())),
        skipped_count=0,
        run_status=LegacyReadAuditRun.STATUS_COMPLETED,
        structural_findings=_structural_findings(legacy.values()),
        source=source,
        sync_run_id=sync_run_id,
    )
    db.session.add(run)
    db.session.flush()
    return run.to_dict()


def _replace_existing(product_date, subject_type):
    (
        LegacyReadDivergence.query
        .filter_by(product_date=product_date, subject_type=subject_type)
        .delete(synchronize_session=False)
    )
    (
        LegacyReadAuditRun.query
        .filter_by(product_date=product_date, subject_type=subject_type)
        .delete(synchronize_session=False)
    )
    db.session.flush()


def _audit_run(
    product_date,
    subject_type,
    *,
    subjects_compared=0,
    aligned_count=0,
    divergence_count_by_category=None,
    skipped_count=0,
    run_status,
    structural_findings=None,
    source,
    sync_run_id,
):
    return LegacyReadAuditRun(
        product_date=product_date,
        subject_type=subject_type,
        subjects_compared=subjects_compared,
        aligned_count=aligned_count,
        divergence_count_by_category=divergence_count_by_category or {},
        skipped_count=skipped_count,
        run_status=run_status,
        structural_findings=structural_findings or [],
        source=source or EVIDENCE_SOURCE,
        sync_run_id=sync_run_id,
        created_at=utc_now_naive(),
    )


def _published_snapshot_for_date(product_date):
    return (
        DashboardSnapshot.query
        .filter_by(
            snapshot_type=dashboard_snapshot_service.SNAPSHOT_TYPE_BULLPEN_DASHBOARD,
            status=dashboard_snapshot_service.SNAPSHOT_STATUS_READY,
            is_published=True,
            payload_version=dashboard_snapshot_service.DASHBOARD_PAYLOAD_VERSION,
        )
        .filter(
            (DashboardSnapshot.data_through == product_date)
            | (DashboardSnapshot.availability_reference_date == product_date)
        )
        .order_by(desc(DashboardSnapshot.published_at), desc(DashboardSnapshot.id))
        .first()
    )


def _read_captures(product_date, subject_type):
    read_type = (
        'reliever_daily_read'
        if subject_type == LegacyReadDivergence.SUBJECT_PITCHER_DAY
        else 'team_daily_read'
    )
    rows = (
        ComposedRead.query
        .filter_by(
            read_type=read_type,
            subject_type=subject_type,
            product_date=product_date,
            recompute_status=ComposedRead.RECOMPUTE_CURRENT,
        )
        .order_by(asc(ComposedRead.subject_id), desc(ComposedRead.id))
        .all()
    )
    result = {}
    for read in rows:
        if read.subject_id is not None and read.subject_id not in result:
            result[str(read.subject_id)] = _capture_read(read)
    return result


def _capture_read(read):
    required_states = {}
    key_reason_codes = []
    fact_values = {}
    for component in read.components:
        if component.required:
            required_states[component.component_name] = component.component_state
        key_reason_codes.extend(component.reason_codes or [])
        for citation in component.evidence_citations:
            evidence = citation.evidence_object
            if evidence is None:
                continue
            _capture_fact_values(fact_values, evidence)
    return {
        'read_key': read.read_key,
        'composed_read_id': read.id,
        'read_type': read.read_type,
        'completeness_state': read.completeness_state,
        'required_component_states': required_states,
        'key_reason_codes': _dedupe(key_reason_codes),
        'fact_check_values': fact_values,
    }


def _capture_fact_values(fact_values, evidence):
    payload = {
        'typed_cited_inputs': evidence.typed_cited_inputs,
        'computation_trace': evidence.computation_trace,
        'citations': [
            citation.cited_values for citation in (evidence.citations or [])
        ],
        'rendered_claim': evidence.rendered_claim,
        'reason_codes': evidence.reason_codes,
    }
    if evidence.rule_id == 'pitcher_roster_membership_context':
        value = _first_found(payload, (
            'roster_membership_state',
            'membership_state',
            'roster_status',
            'active_roster',
        ))
        if value is not None:
            fact_values['roster_membership_state'] = value
    if evidence.rule_id == 'workload_last_final_appearance':
        value = _first_found(payload, (
            'last_final_appearance',
            'last_final_appearance_date',
            'last_appearance_date',
            'game_date',
        ))
        if value is not None:
            fact_values['last_final_appearance'] = value
    if evidence.rule_id == 'workload_days_of_rest':
        value = _first_found(payload, ('days_rest', 'days_of_rest'))
        if value is not None:
            fact_values['days_rest'] = value
    if evidence.rule_id == 'team_relief_contributor_basis':
        value = _first_found(payload, (
            'relief_contributor_count',
            'appearance_evidenced_count',
            'contributor_count',
            'count',
        ))
        if value is not None:
            fact_values['team_relief_contributor_count'] = value


def _legacy_captures(snapshot, subject_type):
    payload = snapshot.payload if isinstance(snapshot.payload, Mapping) else {}
    captures = {}
    for item in _walk_dicts(payload):
        subject_id = _legacy_subject_id(item, subject_type)
        if subject_id is None:
            continue
        capture = _capture_legacy_item(
            item,
            subject_type=subject_type,
            subject_id=str(subject_id),
            snapshot=snapshot,
        )
        if _legacy_present(capture):
            captures.setdefault(str(subject_id), capture)
    return captures


def _capture_legacy_item(item, *, subject_type, subject_id, snapshot):
    labels = _legacy_labels(item)
    facts = _legacy_facts(item)
    capture = {
        'source': 'published_dashboard_snapshot',
        'capture_kind': 'legacy',
        'published_snapshot_id': snapshot.id,
        'subject_type': subject_type,
        'subject_id': str(subject_id),
        'labels': labels,
        'factual_fields': facts,
        'freshness_flags': _legacy_freshness_flags(item),
        'engine_provenance': _engine_provenance(subject_type, subject_id, snapshot),
    }
    return capture


def _legacy_labels(item):
    labels = []
    candidates = [
        ('availability_status', item.get('availability_status')),
        ('confidence', item.get('confidence')),
        ('role_public_label', item.get('role_public_label')),
        ('read_label', item.get('read_label')),
        ('status_label', item.get('status_label')),
        ('usage_string', item.get('usage_string')),
    ]
    role = item.get('role')
    if isinstance(role, Mapping):
        candidates.extend((
            ('role.label', role.get('label')),
            ('role.public_label', role.get('public_label')),
        ))
    public_labels = item.get('public_labels')
    if isinstance(public_labels, Mapping):
        for key, value in public_labels.items():
            if isinstance(value, Mapping):
                candidates.append((f'public_labels.{key}.label', value.get('label')))
            else:
                candidates.append((f'public_labels.{key}', value))
    seen = set()
    for field, value in candidates:
        if value in (None, ''):
            continue
        text = str(value)
        key = (field, text)
        if key in seen:
            continue
        seen.add(key)
        labels.append({
            'field': field,
            'value': text,
            'legacy': True,
            'mapping': _map_legacy_value(text),
        })
    return labels


def _legacy_facts(item):
    fields = (
        'days_rest',
        'days_since_last_appearance',
        'last_appearance_date',
        'last_final_appearance_date',
        'team_reliever_count',
        'active_reliever_count',
        'total_relievers',
        'relief_contributor_count',
        'appearance_evidenced_count',
    )
    return {
        field: item.get(field)
        for field in fields
        if item.get(field) not in (None, '')
    }


def _legacy_freshness_flags(item):
    flags = []
    for field in ('freshness_state', 'data_freshness', 'freshness'):
        value = item.get(field)
        if isinstance(value, Mapping):
            value = value.get('freshness_state') or value.get('state')
        if value not in (None, ''):
            flags.append({'field': field, 'value': str(value), 'legacy': True})
    if item.get('is_stale') is True:
        flags.append({'field': 'is_stale', 'value': 'true', 'legacy': True})
    return flags


def _engine_provenance(subject_type, subject_id, snapshot):
    result = {
        'published_snapshot_id': snapshot.id,
        'engine_rows': {},
    }
    if subject_type != LegacyReadDivergence.SUBJECT_PITCHER_DAY:
        return result
    row = (
        FatigueScore.query
        .filter(FatigueScore.pitcher_id == int(subject_id))
        .order_by(desc(FatigueScore.calculated_at), desc(FatigueScore.id))
        .first()
    )
    if row is not None:
        result['engine_rows']['fatigue_scores'] = {
            'id': row.id,
            'calculated_at': row.calculated_at.isoformat() if row.calculated_at else None,
            'raw_score_opaque': row.raw_score,
            'risk_level_legacy': row.risk_level,
        }
    return result


def _subject_population(product_date, subject_type, reads, legacy):
    if subject_type == LegacyReadDivergence.SUBJECT_TEAM_DAY:
        snapshot_teams = _snapshot_authority_teams(product_date)
        return tuple(sorted(set(snapshot_teams) | {int(item) for item in reads} | {int(item) for item in legacy}))
    return tuple(sorted({int(item) for item in reads} | {int(item) for item in legacy}))


def _snapshot_authority_teams(product_date):
    rows = (
        RosterStatusSnapshot.query
        .filter(RosterStatusSnapshot.snapshot_date <= product_date)
        .order_by(
            asc(RosterStatusSnapshot.team_id),
            desc(RosterStatusSnapshot.snapshot_date),
            asc(RosterStatusSnapshot.id),
        )
        .all()
    )
    latest_by_team = {}
    for row in rows:
        current = latest_by_team.get(row.team_id)
        if current is None or row.snapshot_date > current:
            latest_by_team[row.team_id] = row.snapshot_date
    return tuple(sorted(latest_by_team))


def _subject_divergences(
    *,
    subject_type,
    subject_id,
    product_date,
    legacy_capture,
    read_capture,
    source,
    sync_run_id,
):
    rows = []
    legacy_present = _legacy_present(legacy_capture)
    read_present = bool(read_capture)
    if legacy_present and not read_present:
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING,
            legacy_capture,
            read_capture,
            'presence:legacy_present_read_missing',
            'Legacy display was captured; matching internal read was absent.',
            source=source,
            sync_run_id=sync_run_id,
        ))
        return rows
    if read_present and not legacy_present:
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING,
            legacy_capture,
            read_capture,
            'presence:read_present_legacy_label_missing',
            'Internal read was captured; matching legacy display was absent.',
            source=source,
            sync_run_id=sync_run_id,
        ))
        return rows
    if not legacy_present and not read_present:
        return rows

    if subject_type == LegacyReadDivergence.SUBJECT_PITCHER_DAY:
        rows.extend(_pitcher_divergences(
            subject_type,
            subject_id,
            product_date,
            legacy_capture,
            read_capture,
            source=source,
            sync_run_id=sync_run_id,
        ))
    else:
        rows.extend(_team_divergences(
            subject_type,
            subject_id,
            product_date,
            legacy_capture,
            read_capture,
            source=source,
            sync_run_id=sync_run_id,
        ))
    return rows


def _pitcher_divergences(
    subject_type,
    subject_id,
    product_date,
    legacy_capture,
    read_capture,
    *,
    source,
    sync_run_id,
):
    rows = []
    read_state = read_capture.get('completeness_state')
    decisive = _decisive_legacy_labels(legacy_capture)
    degraded = read_state != ComposedRead.COMPLETENESS_COMPLETE
    if decisive and degraded:
        degradation_kind, component_name = _degradation_basis(read_capture)
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
            legacy_capture,
            read_capture,
            f'component={component_name};degradation={degradation_kind}',
            _note_for_degradation(degradation_kind),
            source=source,
            sync_run_id=sync_run_id,
            material=degradation_kind == ComposedRead.COMPLETENESS_CONFLICT,
        ))
    if _confident_legacy_label(legacy_capture) and _legacy_stale(legacy_capture):
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_CONFIDENT_ON_STALE_INPUTS,
            legacy_capture,
            read_capture,
            'confidence_with_stale_legacy_input',
            'Legacy confidence was captured with stale published input flags.',
            source=source,
            sync_run_id=sync_run_id,
        ))
    stored_fact = _stored_fact_divergence_basis(legacy_capture, read_capture)
    if stored_fact is not None:
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_STATE_CONTRADICTS_FACT,
            legacy_capture,
            read_capture,
            stored_fact,
            'Published field diverges from cited stored fact.',
            source=source,
            sync_run_id=sync_run_id,
            material=True,
        ))
    return rows


def _team_divergences(
    subject_type,
    subject_id,
    product_date,
    legacy_capture,
    read_capture,
    *,
    source,
    sync_run_id,
):
    rows = []
    if read_capture.get('completeness_state') != ComposedRead.COMPLETENESS_COMPLETE:
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ,
            legacy_capture,
            read_capture,
            'team_aggregate_display_with_degraded_team_read',
            _note_for_degradation(_degradation_basis(read_capture)[0]),
            source=source,
            sync_run_id=sync_run_id,
        ))
    count_basis = _team_count_divergence_basis(legacy_capture, read_capture)
    if count_basis is not None:
        rows.append(_divergence(
            subject_type,
            subject_id,
            product_date,
            CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION,
            legacy_capture,
            read_capture,
            count_basis,
            'Published team count diverges from cited composition fact.',
            source=source,
            sync_run_id=sync_run_id,
        ))
    return rows


def _divergence(
    subject_type,
    subject_id,
    product_date,
    category,
    legacy_capture,
    read_capture,
    comparison_basis,
    notes,
    *,
    source,
    sync_run_id,
    material=False,
):
    validate_neutral_text(notes)
    return LegacyReadDivergence(
        subject_type=subject_type,
        subject_id=str(subject_id),
        product_date=product_date,
        category=category,
        is_material=bool(material),
        escalation_state=(
            LegacyReadDivergence.ESCALATION_RECOMMENDED
            if material
            else LegacyReadDivergence.ESCALATION_RECORDED
        ),
        legacy_capture=legacy_capture or {},
        read_capture=read_capture or {},
        comparison_basis=comparison_basis,
        notes=notes,
        source=source or EVIDENCE_SOURCE,
        sync_run_id=sync_run_id,
        first_seen_at=utc_now_naive(),
        correction_count=0,
        created_at=utc_now_naive(),
        updated_at=utc_now_naive(),
    )


def _structural_findings(legacy_captures):
    terms = sorted({
        label['value']
        for capture in legacy_captures
        for label in capture.get('labels', [])
        if label.get('mapping') in DECISIVE_MAPPINGS
        or label.get('mapping', '').startswith('informational')
    })
    if not terms:
        return []
    return [{
        'category': CATEGORY_STRUCTURAL_VOCABULARY,
        'comparison_basis': 'legacy_vocabulary_mapped_for_internal_review',
        'legacy_terms': terms,
    }]


def _report_payload(start, end, runs, rows):
    counts = defaultdict(int)
    for row in rows:
        key = '|'.join((row.product_date.isoformat(), row.subject_type, row.category))
        counts[key] += 1
    examples = defaultdict(list)
    for row in sorted(rows, key=lambda item: (item.product_date, item.id)):
        if len(examples[row.category]) < 3:
            examples[row.category].append(row.to_dict())
    material_rows = [
        row.to_dict()
        for row in rows
        if row.escalation_state == LegacyReadDivergence.ESCALATION_RECOMMENDED
    ]
    return {
        'watermark': INTERNAL_WATERMARK,
        'start_date': start.isoformat(),
        'end_date': end.isoformat(),
        'run_denominators': [run.to_dict() for run in runs],
        'counts_by_day_subject_category': dict(sorted(counts.items())),
        'examples_by_category': dict(sorted(examples.items())),
        'escalations': material_rows,
        'structural_findings': [
            finding
            for run in runs
            for finding in (run.structural_findings or [])
        ],
    }


def _render_markdown(payload):
    lines = [
        INTERNAL_WATERMARK,
        '',
        '# Legacy Read Reconciliation Audit',
        '',
        f"Date range: {payload['start_date']} to {payload['end_date']}",
        '',
        '## Denominators',
    ]
    for run in payload['run_denominators']:
        lines.append(
            '- '
            f"{run['product_date']} {run['subject_type']}: "
            f"subjects_compared={run['subjects_compared']}; "
            f"aligned_count={run['aligned_count']}; "
            f"skipped_count={run['skipped_count']}; "
            f"run_status={run['run_status']}"
        )
    lines.extend(['', '## Counts'])
    for key, count in payload['counts_by_day_subject_category'].items():
        lines.append(f'- {key}: {count}')
    lines.extend(['', '## Examples'])
    for category, rows in payload['examples_by_category'].items():
        lines.append(f'### {category}')
        for row in rows:
            lines.append(
                '- '
                f"{row['product_date']} {row['subject_type']} "
                f"{row['subject_id']} basis={row['comparison_basis']} "
                f"legacy_capture={json.dumps(row['legacy_capture'], sort_keys=True)} "
                f"read_capture={json.dumps(row['read_capture'], sort_keys=True)}"
            )
    lines.extend(['', '## Escalations'])
    if payload['escalations']:
        for row in payload['escalations']:
            lines.append(
                '- '
                f"{row['product_date']} {row['subject_type']} {row['subject_id']} "
                f"{REPORT_ESCALATION_PHRASE}; category={row['category']}; "
                f"legacy_capture={json.dumps(row['legacy_capture'], sort_keys=True)}; "
                f"read_capture={json.dumps(row['read_capture'], sort_keys=True)}"
            )
    else:
        lines.append('- none')
    lines.extend(['', '## Structural Findings'])
    if payload['structural_findings']:
        for finding in payload['structural_findings']:
            lines.append(f"- {json.dumps(finding, sort_keys=True)}")
    else:
        lines.append('- none')
    lines.extend(['', INTERNAL_WATERMARK, ''])
    return '\n'.join(lines)


def _report_paths(output_path):
    path = Path(output_path).expanduser().resolve()
    _assert_report_path_outside_repo(path)
    if path.suffix:
        if path.suffix.lower() == '.json':
            return path.with_suffix('.md'), path
        return path, path.with_suffix('.json')
    path.mkdir(parents=True, exist_ok=True)
    return (
        path / 'legacy_read_reconciliation_audit.md',
        path / 'legacy_read_reconciliation_audit.json',
    )


def _assert_report_path_outside_repo(path):
    try:
        path.relative_to(_REPO_ROOT)
    except ValueError:
        return
    raise ValueError('report output path must be outside the repository')


def _legacy_subject_id(item, subject_type):
    if subject_type == LegacyReadDivergence.SUBJECT_PITCHER_DAY:
        for key in ('pitcher_id', 'player_id'):
            if item.get(key) is not None:
                return item.get(key)
        pitcher = item.get('pitcher')
        if isinstance(pitcher, Mapping):
            return pitcher.get('id') or pitcher.get('pitcher_id')
        if item.get('availability_status') and item.get('id') is not None:
            return item.get('id')
        return None
    for key in ('team_id',):
        if item.get(key) is not None:
            return item.get(key)
    team = item.get('team')
    if isinstance(team, Mapping):
        return team.get('id') or team.get('team_id')
    return None


def _legacy_present(capture):
    if not capture:
        return False
    return bool(capture.get('labels') or capture.get('factual_fields'))


def _decisive_legacy_labels(capture):
    return [
        label
        for label in (capture or {}).get('labels', [])
        if label.get('mapping') in DECISIVE_MAPPINGS
    ]


def _confident_legacy_label(capture):
    for label in (capture or {}).get('labels', []):
        if label.get('field') == 'confidence' and str(label.get('value')).lower() in {
            'high',
            'strong',
            'trusted',
        }:
            return True
    return False


def _legacy_stale(capture):
    for flag in (capture or {}).get('freshness_flags', []):
        if 'stale' in str(flag.get('value')).lower():
            return True
    return False


def _degradation_basis(read_capture):
    states = (read_capture or {}).get('required_component_states') or {}
    for state in (
        ComposedRead.COMPLETENESS_CONFLICT,
        ComposedRead.COMPLETENESS_WITHHELD,
        ComposedRead.COMPLETENESS_UNKNOWN,
        ComposedRead.COMPLETENESS_PARTIAL,
    ):
        for component, value in states.items():
            if value == state:
                return state, component
    return (read_capture or {}).get('completeness_state'), 'read'


def _note_for_degradation(degradation_kind):
    if degradation_kind == ComposedRead.COMPLETENESS_UNKNOWN:
        return NO_ADJUDICATION_NOTE
    if degradation_kind == ComposedRead.COMPLETENESS_CONFLICT:
        return 'Conflict-state evidence requires human review.'
    return 'Legacy display is recorded beside a degraded internal read.'


def _stored_fact_divergence_basis(legacy_capture, read_capture):
    facts = (legacy_capture or {}).get('factual_fields') or {}
    read_facts = (read_capture or {}).get('fact_check_values') or {}
    if _has_display_label(legacy_capture) and _roster_membership_not_active(read_facts):
        return 'roster_membership:not_active_with_displayed_label'
    legacy_last = facts.get('last_final_appearance_date') or facts.get('last_appearance_date')
    read_last = read_facts.get('last_final_appearance')
    if legacy_last is not None and read_last is not None and str(legacy_last) != str(read_last):
        return 'published_last_appearance_date_vs_cited_fact'
    legacy_days = facts.get('days_rest') or facts.get('days_since_last_appearance')
    read_days = read_facts.get('days_rest')
    if legacy_days is not None and read_days is not None and str(legacy_days) != str(read_days):
        return 'published_days_rest_vs_cited_fact'
    return None


def _team_count_divergence_basis(legacy_capture, read_capture):
    facts = (legacy_capture or {}).get('factual_fields') or {}
    read_facts = (read_capture or {}).get('fact_check_values') or {}
    legacy_count = (
        facts.get('relief_contributor_count')
        or facts.get('appearance_evidenced_count')
        or facts.get('team_reliever_count')
        or facts.get('active_reliever_count')
        or facts.get('total_relievers')
    )
    read_count = read_facts.get('team_relief_contributor_count')
    if legacy_count is not None and read_count is not None and str(legacy_count) != str(read_count):
        return 'published_team_count_vs_composition_fact'
    return None


def _has_display_label(capture):
    return bool((capture or {}).get('labels'))


def _roster_membership_not_active(read_facts):
    value = read_facts.get('roster_membership_state')
    if value is None:
        return False
    if isinstance(value, bool):
        return value is False
    normalized = str(value).lower()
    return normalized in {
        'inactive',
        'not_active',
        'not_on_active_roster',
        'not active',
        'false',
    }


def _map_legacy_value(value):
    text = str(value)
    if text in LEGACY_VOCABULARY_MAP:
        return LEGACY_VOCABULARY_MAP[text]
    if 'fresh' in text.lower():
        return LEGACY_VOCABULARY_MAP['fresh']
    return 'unmapped_legacy_display'


def _walk_dicts(value):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child)


def _first_found(payload, keys):
    for key in keys:
        found = _find_key(payload, key)
        if found is not None:
            return found
    return None


def _find_key(value, key):
    if isinstance(value, Mapping):
        if key in value and value[key] is not None:
            return value[key]
        for child in value.values():
            found = _find_key(child, key)
            if found is not None:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_key(child, key)
            if found is not None:
                return found
    return None


def _subject_types(subject_type):
    if subject_type in (None, 'all'):
        return (
            LegacyReadDivergence.SUBJECT_PITCHER_DAY,
            LegacyReadDivergence.SUBJECT_TEAM_DAY,
        )
    if subject_type not in {
        LegacyReadDivergence.SUBJECT_PITCHER_DAY,
        LegacyReadDivergence.SUBJECT_TEAM_DAY,
    }:
        raise ValueError(f'unsupported subject_type: {subject_type}')
    return (subject_type,)


def _as_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _dedupe(values):
    result = []
    seen = set()
    for value in values or []:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
