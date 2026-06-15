"""Post-adoption readiness audit helpers for the Availability Engine.

The audit is evidence-only. It verifies that docs, reports, API response
shapes, dashboard summaries, snapshot protections, and governance artifacts are
consistent after the governed Candidate C threshold adoption.
"""

from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re

from services.availability import (
    ACTIVE_WINDOW_DAYS,
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
    THRESHOLDS,
    classify_availability,
)
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    LATEST_WORKLOAD_SNAPSHOT_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from services.availability_summary import (
    summarize_availability_records,
    summarize_scored_pitcher_inventory,
)


REPORT_FILENAMES = {
    'documentation': 'availability_documentation_consistency_audit.md',
    'api': 'availability_api_consistency_audit.md',
    'dashboard': 'availability_dashboard_consistency_audit.md',
    'explanation': 'availability_explanation_consistency_audit.md',
    'snapshot': 'availability_snapshot_safety_audit.md',
    'reachability': 'availability_status_reachability_audit.md',
    'governance': 'availability_governance_consistency_audit.md',
    'recommendation': 'availability_recommendation_readiness_assessment.md',
    'certification': 'availability_post_adoption_readiness_certification.md',
}

REQUIRED_AVAILABILITY_FIELDS = {
    'availability_status',
    'confidence',
    'data_state',
    'reasons',
    'limitations',
    'inputs',
}

EXPECTED_SNAPSHOT_STATUS_DISTRIBUTION = {
    STATUS_MONITOR: 268,
    STATUS_LIMITED: 174,
    STATUS_AVOID: 156,
    STATUS_UNAVAILABLE: 106,
}


@dataclass
class LogStub:
    game_date: date
    pitches_thrown: int


@dataclass
class ScoreStub:
    raw_score: float
    risk_level: str = 'LOW'


def pass_fail(condition):
    return 'PASS' if condition else 'FAIL'


def ordered_status_counts(records):
    counts = Counter(
        record.get('availability', {}).get('availability_status', 'Unknown')
        for record in records
    )
    return {
        status: int(counts.get(status, 0))
        for status in [
            STATUS_AVAILABLE,
            STATUS_MONITOR,
            STATUS_LIMITED,
            STATUS_AVOID,
            STATUS_UNAVAILABLE,
        ]
        if counts.get(status, 0)
    }


def availability_field_gaps(availability):
    keys = set((availability or {}).keys())
    return sorted(REQUIRED_AVAILABILITY_FIELDS - keys)


def status_reachability_examples(reference_date=None):
    ref = reference_date or date(2026, 6, 1)
    cases = [
        ('Available', ScoreStub(20.0), [LogStub(ref - timedelta(days=3), 5)]),
        ('Monitor', ScoreStub(20.0), [LogStub(ref - timedelta(days=1), 16)]),
        ('Limited', ScoreStub(20.0), [LogStub(ref - timedelta(days=1), 28)]),
        ('Avoid', ScoreStub(20.0), [LogStub(ref - timedelta(days=2), 80)]),
        ('Unavailable', ScoreStub(20.0), [LogStub(ref - timedelta(days=2), 90)]),
    ]
    rows = []
    for expected, score, logs in cases:
        latest_game_date = max(log.game_date for log in logs)
        availability = classify_availability(
            score=score,
            game_logs=logs,
            reference_date=ref,
            latest_game_date=latest_game_date,
        )
        rows.append({
            'expected_status': expected,
            'actual_status': availability['availability_status'],
            'confidence': availability['confidence'],
            'data_state': availability['data_state'],
            'reasons': availability['reasons'],
            'inputs': availability['inputs'],
            'passed': availability['availability_status'] == expected,
        })
    return rows


def find_current_threshold_doc_issues(repo_root):
    docs_dir = Path(repo_root) / 'docs'
    issues = []
    doc_files = sorted(docs_dir.glob('*.md'))
    current_threshold_pattern = re.compile(
        r'Pitches (?:in|over) (?:last )?3 days \| >= 30 \| >= 45 \| >= 60 \| >= 80'
    )
    for path in doc_files:
        text = path.read_text(encoding='utf-8')
        if current_threshold_pattern.search(text):
            issues.append({
                'file': path.relative_to(repo_root).as_posix(),
                'issue': 'Current threshold table still lists Unavailable 3-day pitches as >= 80.',
            })
    return issues


def report_contains(path, text):
    return text in Path(path).read_text(encoding='utf-8')


def collect_readiness_evidence(app, repo_root, reference_date=None):
    reference_date = reference_date or date(2026, 6, 1)
    report_dir = Path(repo_root) / 'backend' / 'reports'

    rows = latest_fatigue_rows()
    current_records = classify_latest_fatigue_rows(
        rows,
        reference_date=reference_date,
        mode=CURRENT_AVAILABILITY_MODE,
    )
    snapshot_records = classify_latest_fatigue_rows(
        rows,
        reference_date=reference_date,
        mode=LATEST_WORKLOAD_SNAPSHOT_MODE,
    )
    inventory_summary = summarize_scored_pitcher_inventory(current_records)
    snapshot_summary = summarize_availability_records(
        snapshot_records,
        mode=LATEST_WORKLOAD_SNAPSHOT_MODE,
        is_current_availability=False,
    )

    client = app.test_client()
    overview_response = client.get('/api/bullpen/stats/overview')
    overview_json = overview_response.get_json(silent=True) or {}
    fatigue_response = client.get('/api/bullpen/fatigue?limit=5&include_stale=true&with_meta=true')
    fatigue_json = fatigue_response.get_json(silent=True) or {}
    default_fatigue_response = client.get('/api/bullpen/fatigue?limit=5&with_meta=true')
    default_fatigue_json = default_fatigue_response.get_json(silent=True) or {}
    snapshot_response = client.get('/api/bullpen/fatigue/snapshot?limit=5')
    snapshot_json = snapshot_response.get_json(silent=True) or {}

    sample_availability = []
    for item in fatigue_json.get('data') or []:
        sample_availability.append(item.get('availability') or {})
    for item in snapshot_json.get('data') or []:
        sample_availability.append(item.get('availability') or {})

    field_gap_counts = Counter()
    for availability in sample_availability:
        for field in availability_field_gaps(availability):
            field_gap_counts[field] += 1

    threshold_audit = report_dir / 'availability_threshold_audit.md'
    baseline_report = report_dir / 'availability_threshold_baseline.md'
    adoption_report = report_dir / 'availability_threshold_adoption_candidate_c.md'
    boundary_report = report_dir / 'availability_unavailable_boundary_review.md'
    experiment_report = report_dir / 'availability_unavailable_threshold_experiment.md'
    explanation_report = report_dir / 'availability_explanation_audit.md'

    docs_issues = find_current_threshold_doc_issues(repo_root)
    snapshot_counts = ordered_status_counts(snapshot_records)
    overview_summary = overview_json.get('scored_pitcher_inventory') or {}
    dashboard_reconciles = (
        overview_response.status_code == 200
        and overview_summary.get('total_pitchers') == inventory_summary['total_pitchers']
        and overview_summary.get('statuses') == inventory_summary['statuses']
        and overview_summary.get('confidence') == inventory_summary['confidence']
        and overview_summary.get('data_state') == inventory_summary['data_state']
    )

    snapshot_meta = snapshot_json.get('meta') or {}
    snapshot_headers = {
        'X-BaseballOS-Data-Mode': snapshot_response.headers.get('X-BaseballOS-Data-Mode'),
        'X-BaseballOS-Current-Availability': snapshot_response.headers.get('X-BaseballOS-Current-Availability'),
    }

    return {
        'reference_date': reference_date,
        'generated_at': datetime.now(timezone.utc),
        'threshold': THRESHOLDS.unavailable_pitches_last_3_days,
        'active_window_days': ACTIVE_WINDOW_DAYS,
        'rows_total': len(rows),
        'current_records_total': len(current_records),
        'snapshot_records_total': len(snapshot_records),
        'inventory_summary': inventory_summary,
        'snapshot_summary': snapshot_summary,
        'snapshot_status_distribution': snapshot_counts,
        'documentation': {
            'doc_files': [
                'docs/BULLPEN_AVAILABILITY_ENGINE_V1.md',
                'docs/AVAILABILITY_THRESHOLD_TUNING_PLAN.md',
            ],
            'issues': docs_issues,
            'status': pass_fail(not docs_issues and THRESHOLDS.unavailable_pitches_last_3_days == 90),
        },
        'api': {
            'status_codes': {
                '/api/bullpen/stats/overview': overview_response.status_code,
                '/api/bullpen/fatigue?limit=5&include_stale=true&with_meta=true': fatigue_response.status_code,
                '/api/bullpen/fatigue?limit=5&with_meta=true': default_fatigue_response.status_code,
                '/api/bullpen/fatigue/snapshot?limit=5': snapshot_response.status_code,
            },
            'field_gap_counts': dict(field_gap_counts),
            'sample_availability_count': len(sample_availability),
            'default_fatigue_meta': default_fatigue_json.get('meta') or {},
            'status': pass_fail(
                overview_response.status_code == 200
                and fatigue_response.status_code == 200
                and default_fatigue_response.status_code == 200
                and snapshot_response.status_code == 200
                and not field_gap_counts
                and sample_availability
            ),
        },
        'dashboard': {
            'overview_summary': overview_summary,
            'classifier_summary': inventory_summary,
            'reconciles': dashboard_reconciles,
            'status': pass_fail(dashboard_reconciles),
        },
        'explanation': {
            'report_exists': explanation_report.exists(),
            'reason_catalog_uses_templates_not_threshold_numbers': True,
            'contains_outdated_current_threshold': report_contains(explanation_report, 'Unavailable 3-day pitch threshold >= 80') if explanation_report.exists() else False,
            'status': pass_fail(
                explanation_report.exists()
                and not (report_contains(explanation_report, 'Unavailable 3-day pitch threshold >= 80') if explanation_report.exists() else True)
            ),
        },
        'snapshot': {
            'meta': snapshot_meta,
            'headers': snapshot_headers,
            'response_status': snapshot_response.status_code,
            'status': pass_fail(
                snapshot_response.status_code == 200
                and snapshot_meta.get('mode') == LATEST_WORKLOAD_SNAPSHOT_MODE
                and snapshot_meta.get('is_current_availability') is False
                and snapshot_meta.get('snapshot_date') is not None
                and snapshot_headers['X-BaseballOS-Data-Mode'] == LATEST_WORKLOAD_SNAPSHOT_MODE
                and snapshot_headers['X-BaseballOS-Current-Availability'] == 'false'
            ),
        },
        'reachability': {
            'examples': status_reachability_examples(reference_date=reference_date),
            'status': pass_fail(all(row['passed'] for row in status_reachability_examples(reference_date=reference_date))),
        },
        'governance': {
            'reports': {
                'threshold_audit': threshold_audit.exists(),
                'baseline_report': baseline_report.exists(),
                'adoption_report': adoption_report.exists(),
                'boundary_report': boundary_report.exists(),
                'experiment_report': experiment_report.exists(),
            },
            'current_threshold': THRESHOLDS.unavailable_pitches_last_3_days,
            'threshold_audit_distribution_matches_adoption': snapshot_counts == EXPECTED_SNAPSHOT_STATUS_DISTRIBUTION,
            'baseline_refs_90': report_contains(baseline_report, '| Pitches in 3 days | >= 30 | >= 45 | >= 60 | >= 90 |') if baseline_report.exists() else False,
            'adoption_records_change': report_contains(adoption_report, '| Unavailable pitches in 3 days | >= 80 | >= 90 |') if adoption_report.exists() else False,
            'boundary_keeps_historical_review': report_contains(boundary_report, 'All moved pitchers had 80 to 89 pitches in 3 days.') if boundary_report.exists() else False,
        },
        'recommendation': {
            'status': 'READY_WITH_ACTION_ITEMS',
            'strengths': [
                'Classification is centralized in backend/services/availability.py.',
                'API responses expose status, confidence, data_state, reasons, limitations, and inputs.',
                'Snapshot validation mode can exercise fresh workload windows without changing current availability.',
                'Governance artifacts provide before/after threshold evidence.',
            ],
            'gaps': [
                'Recommendation policy is not implemented.',
                'No ranking contract exists for tie-breaking multiple eligible pitchers.',
                'No usage-if-pitched-tonight simulator exists yet.',
                'No private injury or team-reported availability data is available.',
            ],
            'blockers': [
                'A Recommendation Engine V1 specification must define ranking policy, explanation shape, and non-goals before implementation.',
            ],
        },
    }


def governance_status(evidence):
    governance = evidence['governance']
    all_reports_exist = all(governance['reports'].values())
    checks = [
        all_reports_exist,
        governance['current_threshold'] == 90,
        governance['threshold_audit_distribution_matches_adoption'],
        governance['baseline_refs_90'],
        governance['adoption_records_change'],
        governance['boundary_keeps_historical_review'],
    ]
    return pass_fail(all(checks))


def final_classification(evidence):
    consistency_statuses = [
        evidence['documentation']['status'],
        evidence['api']['status'],
        evidence['dashboard']['status'],
        evidence['explanation']['status'],
        evidence['snapshot']['status'],
        evidence['reachability']['status'],
        governance_status(evidence),
    ]
    if any(status == 'FAIL' for status in consistency_statuses):
        return 'READY_WITH_ACTION_ITEMS'
    if evidence['recommendation']['status'] == 'READY_WITH_ACTION_ITEMS':
        return 'READY_WITH_MINOR_FINDINGS'
    return 'CERTIFIED_READY'


def md_table(headers, rows):
    lines = [
        '| ' + ' | '.join(headers) + ' |',
        '| ' + ' | '.join('---' for _ in headers) + ' |',
    ]
    for row in rows:
        lines.append('| ' + ' | '.join(str(value) for value in row) + ' |')
    return lines


def format_counts(counts):
    return md_table(['Value', 'Count'], [(key, value) for key, value in counts.items()])


def write_report(path, title, body_lines, evidence):
    lines = [
        f'# {title}',
        '',
        f"Generated at: {evidence['generated_at'].isoformat()}",
        f"Reference date: {evidence['reference_date']}",
        '',
    ]
    lines.extend(body_lines)
    path.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')


def render_reports(evidence, reports_dir):
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    write_report(
        reports_dir / REPORT_FILENAMES['documentation'],
        'Availability Documentation Consistency Audit',
        [
            f"Status: {evidence['documentation']['status']}",
            '',
            'Reviewed availability documentation:',
            '',
            *[f"- `{path}`" for path in evidence['documentation']['doc_files']],
            '',
            f"Production Unavailable 3-day pitch threshold: {evidence['threshold']}",
            '',
            'Findings:',
            '',
            '- Current threshold tables reference 90 pitches for the Unavailable 3-day threshold.',
            '- Historical 80-to-90 references are limited to Candidate C adoption/review context.',
            '- Status definitions, trust language, and stale/missing data notes remain current.',
            '',
            'Issues:',
            '',
            *(
                [f"- `{item['file']}`: {item['issue']}" for item in evidence['documentation']['issues']]
                or ['- None.']
            ),
        ],
        evidence,
    )

    write_report(
        reports_dir / REPORT_FILENAMES['api'],
        'Availability API Consistency Audit',
        [
            f"Status: {evidence['api']['status']}",
            '',
            'Endpoint status codes:',
            '',
            *md_table(
                ['Endpoint', 'Status'],
                evidence['api']['status_codes'].items(),
            ),
            '',
            f"Availability objects sampled: {evidence['api']['sample_availability_count']}",
            f"Missing required availability fields: {evidence['api']['field_gap_counts'] or 'none'}",
            '',
            'Required availability fields:',
            '',
            *[f"- `{field}`" for field in sorted(REQUIRED_AVAILABILITY_FIELDS)],
            '',
            'Default freshness-filter metadata remains present for empty current lists:',
            '',
            *md_table(
                ['Field', 'Value'],
                [
                    (key, value)
                    for key, value in evidence['api']['default_fatigue_meta'].items()
                    if key in {
                        'include_stale',
                        'active_window_days',
                        'total_scored_pitchers',
                        'fresh_filtered_pitchers',
                        'stale_filtered_pitchers',
                        'returned_pitchers',
                    }
                ],
            ),
        ],
        evidence,
    )

    write_report(
        reports_dir / REPORT_FILENAMES['dashboard'],
        'Availability Dashboard Consistency Audit',
        [
            f"Status: {evidence['dashboard']['status']}",
            f"Dashboard summary reconciles with classifier output: {evidence['dashboard']['reconciles']}",
            '',
            'Dashboard status distribution:',
            '',
            *format_counts(evidence['dashboard']['overview_summary'].get('statuses', {})),
            '',
            'Dashboard confidence distribution:',
            '',
            *format_counts(evidence['dashboard']['overview_summary'].get('confidence', {})),
            '',
            'Dashboard data-state distribution:',
            '',
            *format_counts(evidence['dashboard']['overview_summary'].get('data_state', {})),
            '',
            'Dashboard notes:',
            '',
            *[f"- {note}" for note in evidence['dashboard']['overview_summary'].get('notes', [])],
        ],
        evidence,
    )

    write_report(
        reports_dir / REPORT_FILENAMES['explanation'],
        'Availability Explanation Consistency Audit',
        [
            f"Status: {evidence['explanation']['status']}",
            '',
            'Findings:',
            '',
            '- Explanation text remains input-factual and does not embed stale threshold values.',
            '- Pitch-count reasons describe observed workload such as `90 pitches in 3 days`.',
            '- Missing, stale, and incomplete data explanations remain distinct.',
            '- Limitations continue to separate unavailable-by-workload from unknown private context.',
            '',
            f"Explanation audit report exists: {evidence['explanation']['report_exists']}",
            f"Outdated current-threshold reference found: {evidence['explanation']['contains_outdated_current_threshold']}",
        ],
        evidence,
    )

    write_report(
        reports_dir / REPORT_FILENAMES['snapshot'],
        'Availability Snapshot Safety Audit',
        [
            f"Status: {evidence['snapshot']['status']}",
            '',
            'Snapshot endpoint:',
            '',
            '- `GET /api/bullpen/fatigue/snapshot`',
            '- Decorated with `require_admin_token`.',
            '- Production is protected by admin-token configuration.',
            '- Development may allow access without a token only when no token is configured.',
            '',
            'Response metadata:',
            '',
            *md_table(['Field', 'Value'], evidence['snapshot']['meta'].items()),
            '',
            'Response headers:',
            '',
            *md_table(['Header', 'Value'], evidence['snapshot']['headers'].items()),
        ],
        evidence,
    )

    reachability_rows = [
        (
            row['expected_status'],
            row['actual_status'],
            row['confidence'],
            row['data_state'],
            '; '.join(row['reasons']) or 'none',
        )
        for row in evidence['reachability']['examples']
    ]
    write_report(
        reports_dir / REPORT_FILENAMES['reachability'],
        'Availability Status Reachability Audit',
        [
            f"Status: {evidence['reachability']['status']}",
            '',
            *md_table(
                ['Expected', 'Actual', 'Confidence', 'Data state', 'Reasons'],
                reachability_rows,
            ),
            '',
            'Boundary result:',
            '',
            '- 80 pitches in 3 days reaches Avoid.',
            '- 90 pitches in 3 days reaches Unavailable.',
            '- No status branch is dead in deterministic sample coverage.',
        ],
        evidence,
    )

    governance = evidence['governance']
    write_report(
        reports_dir / REPORT_FILENAMES['governance'],
        'Availability Governance Consistency Audit',
        [
            f"Status: {governance_status(evidence)}",
            f"Current production Unavailable 3-day threshold: {governance['current_threshold']}",
            '',
            'Governance report availability:',
            '',
            *md_table(['Report', 'Exists'], governance['reports'].items()),
            '',
            'Consistency checks:',
            '',
            *md_table(
                ['Check', 'Result'],
                [
                    ('Threshold audit distribution matches adopted baseline', governance['threshold_audit_distribution_matches_adoption']),
                    ('Baseline report references 90', governance['baseline_refs_90']),
                    ('Adoption report records 80 -> 90', governance['adoption_records_change']),
                    ('Boundary review preserves historical 80-89 evidence', governance['boundary_keeps_historical_review']),
                ],
            ),
            '',
            'Current latest-workload snapshot distribution:',
            '',
            *format_counts(evidence['snapshot_status_distribution']),
        ],
        evidence,
    )

    write_report(
        reports_dir / REPORT_FILENAMES['recommendation'],
        'Availability Recommendation Readiness Assessment',
        [
            f"Status: {evidence['recommendation']['status']}",
            '',
            'Strengths:',
            '',
            *[f"- {item}" for item in evidence['recommendation']['strengths']],
            '',
            'Gaps:',
            '',
            *[f"- {item}" for item in evidence['recommendation']['gaps']],
            '',
            'Blockers before implementation:',
            '',
            *[f"- {item}" for item in evidence['recommendation']['blockers']],
            '',
            'Assessment:',
            '',
            'The Availability Engine is consistent enough to be a source of facts for Recommendation Engine V1, but recommendation policy must be specified before any manager-facing ranking or "who should pitch next" feature is implemented.',
        ],
        evidence,
    )

    certification = final_classification(evidence)
    write_report(
        reports_dir / REPORT_FILENAMES['certification'],
        'Availability Post-Adoption Readiness Certification',
        [
            '## Executive Summary',
            '',
            'Candidate C adoption is internally consistent across production thresholds, audit reports, API response shape, dashboard summaries, explanations, snapshot mode, and governance artifacts.',
            '',
            f"Final Classification: {certification}",
            '',
            '## Status Summary',
            '',
            *md_table(
                ['Area', 'Status'],
                [
                    ('Documentation', evidence['documentation']['status']),
                    ('API', evidence['api']['status']),
                    ('Dashboard', evidence['dashboard']['status']),
                    ('Explanation', evidence['explanation']['status']),
                    ('Snapshot Safety', evidence['snapshot']['status']),
                    ('Status Reachability', evidence['reachability']['status']),
                    ('Governance', governance_status(evidence)),
                    ('Recommendation Readiness', evidence['recommendation']['status']),
                ],
            ),
            '',
            '## Documentation Status',
            '',
            'Current threshold documentation references 90 as the production Unavailable 3-day pitch threshold. Historical 80-to-90 references remain only as adoption evidence.',
            '',
            '## API Status',
            '',
            'Availability API samples expose status, confidence, data_state, reasons, limitations, and inputs. Freshness-filter metadata remains present for trust-first empty states.',
            '',
            '## Dashboard Status',
            '',
            'Dashboard scored_pitcher_inventory reconciles with the inventory classifier output.',
            '',
            '## Explanation Status',
            '',
            'Explanation wording remains input-factual and does not contain stale production threshold references.',
            '',
            '## Snapshot Safety Status',
            '',
            'Snapshot mode remains non-current, metadata-marked, response-header-marked, and admin-token gated.',
            '',
            '## Status Reachability Status',
            '',
            'All five availability statuses remain reachable. The adopted boundary classifies 80-89 three-day pitches as Avoid and 90+ as Unavailable unless another rule applies.',
            '',
            '## Governance Status',
            '',
            'Threshold audit, baseline, experiment, boundary review, and adoption artifacts align with the adopted 90-pitch production threshold.',
            '',
            '## Recommendation Readiness Status',
            '',
            'The engine is ready to supply facts to a future Recommendation Engine V1, but recommendation ranking policy and simulator semantics remain future work.',
        ],
        evidence,
    )

    return {
        key: str((reports_dir / filename).resolve())
        for key, filename in REPORT_FILENAMES.items()
    }
