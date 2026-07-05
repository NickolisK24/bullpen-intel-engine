import subprocess
from pathlib import Path
import re

import pytest
from flask import Flask

import models.composed_read  # noqa: F401
import models.dashboard_snapshot  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.game_log  # noqa: F401
import models.legacy_read_audit  # noqa: F401
import models.pitcher  # noqa: F401
import models.player_transaction  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.scheduled_game  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import ComposedRead, ComposedReadComponent, ComposedReadEvidenceCitation
from models.legacy_read_audit import LegacyReadAuditRun, LegacyReadDivergence
from scripts.render_read_review_packet import (
    INTERNAL_WATERMARK,
    assert_packet_tokens_allowed,
    collect_packet_rows,
    render_review_packet,
)
from services.evidence_classification import (
    PERMANENTLY_INTERNAL_RULE_IDS,
    validate_evidence_classifications,
)
from services.legacy_read_reconciliation import (
    CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
    CATEGORY_STATE_CONTRADICTS_FACT,
    CATEGORY_STRUCTURAL_VOCABULARY,
    NO_ADJUDICATION_NOTE,
    render_reconciliation_report,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.qa_scenarios import (
    composed_reads_missing,
    conflict_state_evidence,
    legacy_factual_field_contradiction,
    legacy_snapshot_missing,
)
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / 'backend/migrations/versions'
EXPECTED_ALEMBIC_HEAD = 'e4b7c9d2a6f0'
FORBIDDEN_HEADLINE_TERMS = (
    'headline',
    'read_label',
    'state_label',
    'grade',
    'score',
    'rank',
    'tier',
    'color',
)


@pytest.fixture()
def app():
    flask_app = Flask('test_qa_reconciliation_scenarios')
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        yield flask_app
        db.session.remove()
        drop_test_schema(flask_app)


def test_audit_skip_rows_are_typed(app):
    with app.app_context():
        legacy_missing = legacy_snapshot_missing()
        reads_missing = composed_reads_missing()

    assert legacy_missing.expected_state_map['audit_run_status'] == (
        LegacyReadAuditRun.STATUS_SKIPPED_LEGACY_MISSING
    )
    assert reads_missing.expected_state_map['audit_run_status'] == (
        LegacyReadAuditRun.STATUS_SKIPPED_READS_MISSING
    )
    assert legacy_missing.audit_run_ids
    assert reads_missing.audit_run_ids


def test_audit_material_categories_and_unknown_note(app):
    with app.app_context():
        conflict = conflict_state_evidence()
        contradiction = legacy_factual_field_contradiction()
        rows = LegacyReadDivergence.query.order_by(LegacyReadDivergence.category).all()
        categories = {row.category for row in rows}
        material = {row.category for row in rows if row.is_material}

    assert CATEGORY_ACTIONABLE_ON_DEGRADED_READ in conflict.expected_state_map['audit_categories']
    assert CATEGORY_STATE_CONTRADICTS_FACT in contradiction.expected_state_map['audit_categories']
    assert CATEGORY_ACTIONABLE_ON_DEGRADED_READ in categories
    assert CATEGORY_STATE_CONTRADICTS_FACT in categories
    assert material == {CATEGORY_ACTIONABLE_ON_DEGRADED_READ, CATEGORY_STATE_CONTRADICTS_FACT}
    assert all(row.notes != NO_ADJUDICATION_NOTE for row in rows if row.is_material)


def test_report_counts_denominators_no_percent_and_quoted_legacy_vocabulary(app, tmp_path):
    with app.app_context():
        conflict_state_evidence()
        legacy_factual_field_contradiction()
        report = render_reconciliation_report(
            '2026-06-15',
            '2026-06-17',
            output_path=tmp_path / 'legacy-report',
        )
        md = Path(report['markdown_path']).read_text(encoding='utf-8')
        runs = LegacyReadAuditRun.query.all()

    assert '%' not in md
    assert 'subjects_compared=' in md
    assert 'aligned_count=' in md
    assert any(
        finding['category'] == CATEGORY_STRUCTURAL_VOCABULARY
        for run in runs
        for finding in (run.structural_findings or [])
    )
    assert '"legacy": true' in md


def test_review_packet_renderer_watermark_sampling_and_no_new_prose_guard(app, tmp_path):
    with app.app_context():
        conflict_state_evidence()
        legacy_factual_field_contradiction()
        output = tmp_path / 'packet.md'
        result = render_review_packet(
            scenario='conflict_state_evidence,legacy_factual_field_contradiction',
            output_path=output,
        )
        rows = collect_packet_rows(
            scenario='conflict_state_evidence,legacy_factual_field_contradiction',
        )
        markdown = output.read_text(encoding='utf-8')

    assert result['status'] == 'rendered'
    assert result['output_path'] == str(output.resolve())
    assert markdown.count(INTERNAL_WATERMARK) == 3
    assert 'rendered_claim=' in markdown
    assert len(rows.divergences) <= 6
    assert assert_packet_tokens_allowed(markdown, rows)


def test_quoting_rule_lint_for_fixture_output_reports_and_new_docs(app, tmp_path):
    with app.app_context():
        conflict_state_evidence()
        legacy_factual_field_contradiction()
        report = render_reconciliation_report(
            '2026-06-13',
            '2026-06-16',
            output_path=tmp_path / 'legacy-report',
        )
        packet_path = tmp_path / 'packet.md'
        render_review_packet(
            scenario='conflict_state_evidence,legacy_factual_field_contradiction',
            output_path=packet_path,
        )
        fixture_text = '\n'.join(
            '\n'.join(read.reason_codes or []) + '\n'.join(read.limitations or [])
            for read in ComposedRead.query.all()
        )
        audit_notes = '\n'.join(row.notes for row in LegacyReadDivergence.query.all())

    docs = [
        REPO_ROOT / 'docs/phase0e/README.md',
        REPO_ROOT / 'docs/phase0e/qa_fixture_corpus.md',
        REPO_ROOT / 'docs/phase0e/editorial_review_guide.md',
        REPO_ROOT / 'docs/phase0e/headline_state_decision.md',
        REPO_ROOT / 'docs/phase0e/member_read_rollup_decision.md',
        REPO_ROOT / 'docs/phase0e/decision_register.md',
    ]
    lint_targets = {
        'fixture_content': fixture_text,
        'audit_notes': audit_notes,
        'report': Path(report['markdown_path']).read_text(encoding='utf-8'),
        'packet': packet_path.read_text(encoding='utf-8'),
    }
    lint_targets.update({
        str(path.relative_to(REPO_ROOT)): path.read_text(encoding='utf-8')
        for path in docs
    })

    for name, text in lint_targets.items():
        _assert_legacy_vocabulary_quoted_legally(name, text)
        _assert_bullpen_usage_legally_scoped(name, text)


def test_renderer_isolation_from_public_routes_and_serializers():
    blocked = (
        'render_read_review_packet',
        'render_review_packet',
        'qa_scenarios',
        'Phase 0E read review packet',
    )
    public_paths = (
        REPO_ROOT / 'backend/api',
        REPO_ROOT / 'frontend/src',
        REPO_ROOT / 'frontend/public',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    )
    scanned = []
    for path in public_paths:
        files = [file for file in path.rglob('*') if file.is_file()] if path.is_dir() else [path]
        for file in files:
            if file.suffix not in {'.py', '.js', '.jsx', '.ts', '.tsx', '.json'}:
                continue
            scanned.append(file)
            text = file.read_text(encoding='utf-8', errors='ignore')
            for token in blocked:
                assert token not in text, f'{token} leaked into {file}'
    assert scanned


def test_no_migration_new_evidence_rule_or_classification_drift():
    revisions = {}
    for path in MIGRATIONS_DIR.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = down.group(1).strip() if down else None
    referenced = {down for down in revisions.values() if down and down != 'None'}
    assert set(revisions) - referenced == {EXPECTED_ALEMBIC_HEAD}

    classification = validate_evidence_classifications()
    assert classification['rule_count'] == 65
    assert classification['tallies']['PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE'] == 44
    assert classification['tallies']['ELIGIBLE_PUBLIC_CANDIDATE_LATER'] == 9
    assert classification['tallies']['INTERNAL_ONLY_FOR_NOW'] == 4
    assert classification['tallies']['PERMANENTLY_INTERNAL'] == 8
    assert {
        'appearance_entry_band',
        'pitcher_entry_band_distribution',
        'team_active_reliever_count',
    }.issubset(PERMANENTLY_INTERNAL_RULE_IDS)


def test_no_headline_or_read_citation_mechanism_contract():
    for model in (ComposedRead, ComposedReadComponent, ComposedReadEvidenceCitation):
        for column in model.__table__.columns:
            if column.name in {'completeness_state', 'component_state'}:
                continue
            assert not any(term in column.name for term in FORBIDDEN_HEADLINE_TERMS), (
                model.__name__,
                column.name,
            )
    assert 'allowed_read_types' not in ComposedReadComponent.__table__.columns
    fk_targets = {
        fk.column.table.name
        for fk in ComposedReadEvidenceCitation.__table__.foreign_keys
    }
    assert fk_targets == {'composed_read_components', 'evidence_objects'}
    assert not any(
        table.name == 'composed_read_read_citations'
        for table in ComposedRead.metadata.tables.values()
    )


def test_phase0e_switches_and_legacy_public_files_not_modified():
    changed = _changed_files_vs_main()
    if not changed:
        pytest.skip('git diff against origin/main unavailable')
    forbidden_prefixes = (
        'backend/api/',
        'frontend/src/',
        'frontend/public/',
        'backend/services/dashboard_snapshot.py',
        'backend/services/bullpen_board.py',
        'backend/services/tonight_intelligence_snapshot.py',
        'backend/services/what_changed_since_yesterday.py',
        'backend/services/what_changed_since_yesterday_public.py',
        'backend/migrations/',
    )
    assert not [
        path for path in changed
        if any(path.replace('\\', '/').startswith(prefix) for prefix in forbidden_prefixes)
    ]
    if 'backend/services/sync.py' in [path.replace('\\', '/') for path in changed]:
        diff = _diff_vs_main('backend/services/sync.py')
        forbidden_sync_terms = (
            'PHASE0D_EVIDENCE_BUILD',
            'PHASE0E_READ_BUILD',
            'PHASE0E_RECONCILIATION_AUDIT',
            'phase0d_evidence_build_enabled',
            'phase0e_read_build_enabled',
            'phase0e_reconciliation_audit_enabled',
        )
        changed_sync_lines = [
            line for line in diff.splitlines()
            if line[:1] in {'+', '-'} and not line.startswith(('+++', '---'))
        ]
        assert not [
            line for line in changed_sync_lines
            if any(term in line for term in forbidden_sync_terms)
        ]


def _changed_files_vs_main():
    try:
        tracked = subprocess.run(
            ['git', 'diff', '--name-only', 'origin/main'],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        untracked = subprocess.run(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return []
    values = tracked.stdout.splitlines() + untracked.stdout.splitlines()
    return [line.strip() for line in values if line.strip()]


def _diff_vs_main(path):
    try:
        result = subprocess.run(
            ['git', 'diff', 'origin/main', '--', path],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    except Exception:
        return ''
    return result.stdout


def _assert_legacy_vocabulary_quoted_legally(name, text):
    checked = _strip_legal_quote_contexts(name, text)
    terms = (
        'Available',
        'Avoid',
        'Trust Arm',
        'Bridge Arm',
        'Coverage Arm',
        'Depth Arm',
        'Limited Read',
        'fresh',
        'Fresh',
        'Stretched',
        'Vulnerable',
    )
    for term in terms:
        assert not re.search(rf'(?<![A-Za-z]){re.escape(term)}(?![A-Za-z])', checked), (
            name,
            term,
        )


def _strip_legal_quote_contexts(name, text):
    normalized_name = str(name).replace('\\', '/')
    stripped = str(text or '')
    stripped = re.sub(
        r'```FORBIDDEN-PATTERN EXAMPLE\n.*?\n```',
        '',
        stripped,
        flags=re.S,
    )
    stripped = re.sub(
        r'legacy_capture=\{.*?\}; read_capture=',
        'legacy_capture={}; read_capture=',
        stripped,
        flags=re.S,
    )
    stripped = re.sub(
        r'("legacy_capture": \{.*?\}, "read_capture":)',
        r'"legacy_capture": {}, "read_capture":',
        stripped,
        flags=re.S,
    )
    stripped = re.sub(r'"legacy_terms": \[[^\]]*\]', '"legacy_terms": []', stripped)
    if normalized_name.endswith('docs/phase0e/headline_state_decision.md'):
        stripped = re.sub(
            r'HEADLINE-STATE RULING.*?\n\n',
            '',
            stripped,
            flags=re.S,
        )
        stripped = re.sub(
            r'## REJECTED LEGACY VOCABULARY.*?(?=\n## )',
            '',
            stripped,
            flags=re.S,
        )
        stripped = re.sub(
            r'## QUOTED LEGACY VOCABULARY.*',
            '',
            stripped,
            flags=re.S,
        )
    return stripped


def _assert_bullpen_usage_legally_scoped(name, text):
    checked = _strip_legal_quote_contexts(name, text)
    checked = re.sub(
        r'\b(?!bullpen\b)[A-Za-z0-9_]*bullpen[A-Za-z0-9_]*\b',
        '',
        checked,
        flags=re.I,
    )
    assert not re.search(r'\bbullpen\b', checked, re.I), name
