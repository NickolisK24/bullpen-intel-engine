import importlib.util
import json
from collections import Counter
from datetime import date, datetime
from pathlib import Path
import re

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask
from sqlalchemy.exc import IntegrityError

import models.composed_read  # noqa: F401
import models.dashboard_snapshot  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.legacy_read_audit  # noqa: F401
import models.pitcher  # noqa: F401
import models.roster_status_snapshot  # noqa: F401
import models.sync_failure  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import (
    ComposedRead,
    ComposedReadComponent,
    ComposedReadEvidenceCitation,
)
from models.dashboard_snapshot import DashboardSnapshot
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.fatigue_score import FatigueScore
from models.legacy_read_audit import LegacyReadAuditRun, LegacyReadDivergence
from models.pitcher import Pitcher
from models.roster_status_snapshot import RosterStatusSnapshot
from models.sync_failure import SyncFailure
from models.sync_run import SyncRun
from services.evidence_classification import validate_evidence_classifications
from services.legacy_read_reconciliation import (
    CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
    CATEGORY_CONFIDENT_ON_STALE_INPUTS,
    CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING,
    CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING,
    CATEGORY_STATE_CONTRADICTS_FACT,
    CATEGORY_STRUCTURAL_VOCABULARY,
    CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ,
    CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION,
    CATEGORY_CODES,
    FORBIDDEN_NEUTRAL_WORDS,
    NO_ADJUDICATION_NOTE,
    REPORT_ESCALATION_PHRASE,
    render_reconciliation_report,
    run_reconciliation_audit,
    validate_neutral_text,
)
from utils.db import db

from db_config import configure_test_database, create_test_schema, drop_test_schema


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / 'backend' / 'migrations' / 'versions'
AUDIT_REVISION = 'e4b7c9d2a6f0'
EXPECTED_ALEMBIC_HEAD = 'e2b8d5a3c9f1'
PRIOR_REVISION = 'a9d4e7c2f6b1'
PRODUCT_DATE = date(2026, 7, 5)


@pytest.fixture()
def app():
    app = Flask('test_legacy_read_reconciliation')
    configure_test_database(app)
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        yield app
        db.session.remove()
        drop_test_schema(app)


def _sync_run():
    row = SyncRun(
        job_name='daily_sync',
        status='success',
        stage='published',
        source='test',
        started_at=datetime(2026, 7, 5, 8, 0),
        completed_at=datetime(2026, 7, 5, 8, 5),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _pitcher(pid, *, team_id=100):
    pitcher = Pitcher(
        id=pid,
        mlb_id=100000 + pid,
        full_name=f'Pitcher {pid}',
        team_id=team_id,
        team_name=f'Team {team_id}',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _snapshot(sync_run, team_id, pitcher_id):
    row = RosterStatusSnapshot(
        pitcher_id=pitcher_id,
        mlb_id=100000 + pitcher_id,
        team_id=team_id,
        snapshot_date=PRODUCT_DATE,
        roster_status='Active',
        active_roster=True,
        forty_man_roster=True,
        position_code='1',
        position_name='Pitcher',
        position_type='Pitcher',
        source='test',
        sync_run_id=sync_run.id,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _dashboard(sync_run, payload):
    row = DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        sync_run_id=sync_run.id,
        status='ready',
        is_published=True,
        published_at=datetime(2026, 7, 5, 8, 6),
        payload=payload,
        payload_version=1,
        data_through=PRODUCT_DATE,
        availability_reference_date=PRODUCT_DATE,
        snapshot_generated_at=datetime(2026, 7, 5, 8, 6),
        source='test',
    )
    db.session.add(row)
    db.session.flush()
    return row


def _evidence(rule_id, subject_type, subject_id, *, typed=None, state='complete'):
    evidence = EvidenceObject(
        evidence_key=f'{rule_id}:{subject_type}:{subject_id}:{len(str(typed))}',
        evidence_type=rule_id,
        subject_type='pitcher' if subject_type == 'pitcher_day' else 'team',
        subject_id=str(subject_id),
        subject_key=f'{subject_type}:{subject_id}',
        product_date=PRODUCT_DATE,
        claim_template_id=f'{rule_id}:template',
        rendered_claim=f'{rule_id} stored fact',
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash='hash',
        typed_cited_inputs=[typed or {}],
        computation_trace=typed or {},
        completeness_state=state,
        reason_codes=[],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='test',
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    evidence.citations = [
        EvidenceCitation(
            source_family='test',
            source_table='test_table',
            source_pk=f'{rule_id}:{subject_id}',
            source_field_names=list((typed or {}).keys()),
            citation_role='supporting_input',
            cited_values=typed or {},
            provenance={'source': 'test'},
        )
    ]
    db.session.add(evidence)
    db.session.flush()
    return evidence


def _read(subject_type, subject_id, *, state='complete', component_state=None, evidence=None):
    read_type = 'reliever_daily_read' if subject_type == 'pitcher_day' else 'team_daily_read'
    component_name = 'roster_il_context' if subject_type == 'pitcher_day' else 'contributor_composition_component'
    component_state = component_state or state
    component = ComposedReadComponent(
        component_name=component_name,
        required=True,
        component_state=component_state,
        reason_codes=[],
        limitations=[],
    )
    if evidence is not None:
        component.evidence_citations = [
            ComposedReadEvidenceCitation(
                evidence_object_id=evidence.id,
                citation_role='read_component',
                cited_completeness_state=evidence.completeness_state,
            )
        ]
    read = ComposedRead(
        read_key=f'{read_type}:{subject_id}:{state}:{component_state}',
        read_type=read_type,
        read_version=1,
        subject_type=subject_type,
        subject_id=str(subject_id),
        subject_key=f'{subject_type}:{subject_id}',
        product_date=PRODUCT_DATE,
        completeness_state=state,
        reason_codes=[],
        limitations=[],
        component_summary={component_name: {'state': component_state, 'required': True}},
        posture=ComposedRead.POSTURE_INTERNAL_ONLY,
        source='test',
        first_seen_at=datetime(2026, 7, 5, 8, 10),
        recompute_status=ComposedRead.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
        components=[component],
    )
    db.session.add(read)
    db.session.flush()
    return read


def _seed_taxonomy_fixture():
    sync_run = _sync_run()
    for pid in range(101, 107):
        _pitcher(pid)
    _pitcher(201, team_id=1)
    _snapshot(sync_run, 1, 201)
    for team_id in range(2, 31):
        pid = 2000 + team_id
        _pitcher(pid, team_id=team_id)
        _snapshot(sync_run, team_id, pid)

    inactive = _evidence(
        'pitcher_roster_membership_context',
        'pitcher_day',
        105,
        typed={'roster_membership_state': 'not_active'},
    )
    team_basis = _evidence(
        'team_relief_contributor_basis',
        'team_day',
        1,
        typed={'relief_contributor_count': 3},
    )
    _read('pitcher_day', 102)
    _read('pitcher_day', 103, state='unknown', component_state='unknown')
    _read('pitcher_day', 104, state='conflict', component_state='conflict')
    _read('pitcher_day', 105, evidence=inactive)
    _read('pitcher_day', 106)
    _read('team_day', 1, state='unknown', component_state='unknown', evidence=team_basis)

    _dashboard(sync_run, {
        'capability': 'bullpen_dashboard',
        'pitchers': [
            {'pitcher_id': 101, 'availability_status': 'Available'},
            {'pitcher_id': 103, 'availability_status': 'Available'},
            {'pitcher_id': 104, 'availability_status': 'Monitor'},
            {'pitcher_id': 105, 'availability_status': 'Available'},
            {
                'pitcher_id': 106,
                'availability_status': 'Limited',
                'confidence': 'high',
                'freshness_state': 'stale',
            },
        ],
        'teams': [
            {'team_id': 1, 'team_reliever_count': 4, 'status_label': 'fresh'},
        ],
    })
    db.session.flush()
    return sync_run


def test_legacy_read_audit_migration_round_trip_single_head_and_uniqueness(app):
    path = _migration_file()
    source = path.read_text(encoding='utf-8')
    assert f"revision = '{AUDIT_REVISION}'" in source
    assert f"down_revision = '{PRIOR_REVISION}'" in source
    assert source.count('op.create_table(') == 2

    revisions = {}
    for migration_path in MIGRATIONS_DIR.glob('*.py'):
        text = migration_path.read_text(encoding='utf-8')
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = down.group(1).strip() if down else None
    referenced = {down for down in revisions.values() if down and down != 'None'}
    assert set(revisions) - referenced == {EXPECTED_ALEMBIC_HEAD}

    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        module = _load_migration()
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()
        assert _table_exists(connection, 'legacy_read_divergences')
        assert _table_exists(connection, 'legacy_read_audit_runs')
        module.downgrade()
        assert not _table_exists(connection, 'legacy_read_audit_runs')
        assert not _table_exists(connection, 'legacy_read_divergences')

    with app.app_context():
        sync_run = _sync_run()
        row = LegacyReadDivergence(
            subject_type='pitcher_day',
            subject_id='1',
            product_date=PRODUCT_DATE,
            category=CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING,
            is_material=False,
            escalation_state='recorded',
            legacy_capture={},
            read_capture={'read_key': 'r'},
            comparison_basis='presence',
            notes='Internal read was captured; matching legacy display was absent.',
            source='test',
            sync_run_id=sync_run.id,
        )
        db.session.add(row)
        db.session.flush()
        db.session.add(LegacyReadDivergence(
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            product_date=row.product_date,
            category=row.category,
            is_material=False,
            escalation_state='recorded',
            legacy_capture={},
            read_capture={'read_key': 'r2'},
            comparison_basis='presence',
            notes=row.notes,
            source='test',
            sync_run_id=sync_run.id,
        ))
        with pytest.raises(IntegrityError):
            db.session.flush()
        db.session.rollback()


def test_audit_taxonomy_materiality_idempotency_and_neutral_language(app):
    with app.app_context():
        _seed_taxonomy_fixture()
        result = run_reconciliation_audit(PRODUCT_DATE, source='test')
        db.session.commit()
        rows = LegacyReadDivergence.query.order_by(LegacyReadDivergence.category).all()
        runs = LegacyReadAuditRun.query.order_by(LegacyReadAuditRun.subject_type).all()
        counts = Counter(row.category for row in rows)
        material = {row.category: row for row in rows if row.is_material}

        assert result['subjects']['pitcher_day']['run_status'] == 'completed'
        assert result['subjects']['team_day']['run_status'] == 'completed'
        assert counts[CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING] == 1
        assert counts[CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING] == 1
        assert counts[CATEGORY_ACTIONABLE_ON_DEGRADED_READ] == 2
        assert counts[CATEGORY_CONFIDENT_ON_STALE_INPUTS] == 1
        assert counts[CATEGORY_STATE_CONTRADICTS_FACT] == 1
        assert counts[CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ] == 1
        assert counts[CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION] == 1
        assert material[CATEGORY_STATE_CONTRADICTS_FACT].escalation_state == (
            'escalation_recommended'
        )
        conflict_row = [
            row for row in rows
            if row.category == CATEGORY_ACTIONABLE_ON_DEGRADED_READ
            and 'degradation=conflict' in row.comparison_basis
        ][0]
        unknown_row = [
            row for row in rows
            if row.category == CATEGORY_ACTIONABLE_ON_DEGRADED_READ
            and 'degradation=unknown' in row.comparison_basis
        ][0]
        assert conflict_row.is_material is True
        assert unknown_row.is_material is False
        assert unknown_row.notes == NO_ADJUDICATION_NOTE
        assert all(row.escalation_state in {'recorded', 'escalation_recommended'} for row in rows)
        assert all(validate_neutral_text(row.notes) for row in rows)
        assert any(
            finding['category'] == CATEGORY_STRUCTURAL_VOCABULARY
            for run in runs
            for finding in run.structural_findings
        )

        run_reconciliation_audit(PRODUCT_DATE, source='test')
        db.session.commit()
        assert LegacyReadDivergence.query.count() == len(rows)
        assert LegacyReadAuditRun.query.count() == len(runs)


def test_skip_semantics_capture_fidelity_and_score_opacity(app):
    with app.app_context():
        sync_run = _sync_run()
        _dashboard(sync_run, {'capability': 'bullpen_dashboard', 'pitchers': []})
        skipped_reads = run_reconciliation_audit(
            PRODUCT_DATE,
            subject_type='pitcher_day',
            source='test',
        )
        assert skipped_reads['subjects']['pitcher_day']['run_status'] == (
            'skipped_reads_missing'
        )

        LegacyReadAuditRun.query.delete()
        LegacyReadDivergence.query.delete()
        DashboardSnapshot.query.delete()
        _pitcher(301)
        db.session.add(FatigueScore(
            pitcher_id=301,
            raw_score=77.7,
            risk_level='HIGH',
            calculated_at=datetime(2026, 7, 5, 7, 0),
        ))
        _read('pitcher_day', 301)
        skipped_legacy = run_reconciliation_audit(
            PRODUCT_DATE,
            subject_type='pitcher_day',
            source='test',
        )
        assert skipped_legacy['subjects']['pitcher_day']['run_status'] == (
            'skipped_legacy_missing'
        )

        _dashboard(sync_run, {
            'capability': 'bullpen_dashboard',
            'pitchers': [{'pitcher_id': 301, 'availability_status': 'Available'}],
        })
        forced_skip = run_reconciliation_audit(
            PRODUCT_DATE,
            subject_type='pitcher_day',
            source='test',
            force_skip_reads_missing=True,
        )
        assert forced_skip['subjects']['pitcher_day']['run_status'] == (
            'skipped_reads_missing'
        )

        source = (REPO_ROOT / 'backend/services/legacy_read_reconciliation.py').read_text(
            encoding='utf-8'
        )
        assert 'raw_score_opaque' in source
        assert not re.search(r'raw_score\s*(==|!=|<=|>=|<|>)', source)


def test_report_counts_denominators_examples_escalations_and_language(app, tmp_path):
    with app.app_context():
        _seed_taxonomy_fixture()
        run_reconciliation_audit(PRODUCT_DATE, source='test')
        db.session.commit()
        result = render_reconciliation_report(
            PRODUCT_DATE,
            output_path=tmp_path / 'legacy-audit',
        )
        md = Path(result['markdown_path']).read_text(encoding='utf-8')
        payload = json.loads(Path(result['json_path']).read_text(encoding='utf-8'))

    assert '%' not in md
    assert REPORT_ESCALATION_PHRASE in md
    assert 'INTERNAL ONLY' in md
    assert payload['run_denominators']
    assert payload['counts_by_day_subject_category']
    assert len(payload['examples_by_category'][CATEGORY_ACTIONABLE_ON_DEGRADED_READ]) <= 3
    for word in FORBIDDEN_NEUTRAL_WORDS:
        assert not re.search(rf'\b{word}\b', md, re.I)


def test_sync_stage_kill_switch_dead_letter_and_order(monkeypatch, app):
    from services import sync as sync_service

    with app.app_context():
        monkeypatch.setenv('PHASE0E_RECONCILIATION_AUDIT', 'false')
        skipped = sync_service._safe_run_legacy_read_reconciliation_audit_stage(
            [PRODUCT_DATE],
            source='test',
        )
        assert skipped == {
            'status': 'skipped',
            'reason': 'disabled',
            'dates': [PRODUCT_DATE.isoformat()],
        }

        def _boom(*args, **kwargs):
            raise RuntimeError('audit failed for test')

        monkeypatch.setenv('PHASE0E_RECONCILIATION_AUDIT', 'true')
        import services.legacy_read_reconciliation as audit_service
        monkeypatch.setattr(audit_service, 'run_reconciliation_audit', _boom)
        failed = sync_service._safe_run_legacy_read_reconciliation_audit_stage(
            [PRODUCT_DATE],
            source='test',
            sync_run_id=None,
        )
        failure = SyncFailure.query.filter_by(
            entity_type=sync_service.LEGACY_READ_AUDIT_FAILURE_ENTITY_TYPE
        ).one()

    assert failed['status'] == 'failed'
    assert failure.payload['stage'] == sync_service.STAGE_LEGACY_READ_RECONCILIATION_AUDIT
    source = (REPO_ROOT / 'backend/services/sync.py').read_text(encoding='utf-8')
    assert source.index('_safe_build_composed_reads_stage(') < source.index(
        '_safe_run_legacy_read_reconciliation_audit_stage('
    )


def test_isolation_classification_and_public_surfaces_unchanged():
    classification = validate_evidence_classifications()
    assert classification['rule_count'] == 65
    assert classification['tallies']['PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE'] == 44
    assert classification['tallies']['ELIGIBLE_PUBLIC_CANDIDATE_LATER'] == 9
    assert classification['tallies']['INTERNAL_ONLY_FOR_NOW'] == 4
    assert classification['tallies']['PERMANENTLY_INTERNAL'] == 8
    assert set(CATEGORY_CODES) == {
        CATEGORY_LEGACY_LABEL_PRESENT_READ_MISSING,
        CATEGORY_READ_PRESENT_LEGACY_LABEL_MISSING,
        CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
        CATEGORY_CONFIDENT_ON_STALE_INPUTS,
        CATEGORY_STATE_CONTRADICTS_FACT,
        CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ,
        CATEGORY_TEAM_COUNT_CONTRADICTS_COMPOSITION,
        CATEGORY_STRUCTURAL_VOCABULARY,
    }

    blocked = (
        'legacy_read_reconciliation',
        'LegacyReadDivergence',
        'legacy_read_divergences',
        'legacy_read_audit_runs',
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


def _migration_file():
    matches = list(MIGRATIONS_DIR.glob(f'{AUDIT_REVISION}_*.py'))
    assert len(matches) == 1, matches
    return matches[0]


def _load_migration():
    spec = importlib.util.spec_from_file_location('phase0e_legacy_read_audit', _migration_file())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_exists(connection, table_name):
    result = connection.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
    ), {'table_name': table_name})
    return result.first() is not None
