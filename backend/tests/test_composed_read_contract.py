import glob
import importlib.util
import os
from datetime import date, datetime
from pathlib import Path
import re

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

import models.composed_read  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.game_log  # noqa: F401
import models.pitcher  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import (
    ComposedRead,
    ComposedReadComponent,
    ComposedReadEvidenceCitation,
)
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.sync_run import SyncRun
from services.composed_read import (
    ComponentInput,
    ComposedReadBuildError,
    build_composed_read,
    mark_dependent_reads_for_recompute,
    validate_composed_read_integrity,
)
from services.composed_read_registry import (
    ComponentSpec,
    ComposedReadRegistryError,
    ComposedReadTypeNotRegistered,
    ReadType,
    ReadTypeRegistry,
    read_type_registry,
    validate_read_type_registry,
)
from services.evidence_classification import EvidenceClassification
from services.source_correction_policies import (
    correction_policy,
    validate_correction_sensitive_model,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / 'backend' / 'migrations' / 'versions'
PHASE0E_REVISION = 'a9d4e7c2f6b1'
PHASE0E_AUDIT_REVISION = 'e4b7c9d2a6f0'
EXPECTED_ALEMBIC_HEAD = 'e6b4c2a8d1f3'
PHASE0D_REVISION = 'c8d2f4a1b6e9'
PRODUCT_DATE = date(2026, 7, 5)

PUBLIC_PAYLOAD_SURFACES = (
    REPO_ROOT / 'backend/api/bullpen.py',
    REPO_ROOT / 'backend/services/dashboard_snapshot.py',
    REPO_ROOT / 'backend/services/bullpen_board.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday.py',
    REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    REPO_ROOT / 'backend/services/tonight_intelligence_snapshot.py',
    REPO_ROOT / 'frontend/src',
    REPO_ROOT / 'frontend/public',
)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _registry(*, components=None, classification=EvidenceClassification.INTERNAL_ONLY_FOR_NOW):
    registry = ReadTypeRegistry()
    registry.register(ReadType(
        read_type='test_only_daily_bundle',
        read_version=1,
        subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
        plain_language_definition=(
            'Test-only read bundles cited workload and context evidence for one '
            'pitcher day and does not conclude status, role, forecast, or quality.'
        ),
        components=tuple(components or (
            ComponentSpec(
                name='workload_component',
                required=True,
                allowed_evidence_types=('workload_recovery_fact',),
                plain_language_definition='Cites stored workload recovery evidence.',
            ),
            ComponentSpec(
                name='context_component',
                required=True,
                allowed_evidence_types=('appearance_context_fact',),
                plain_language_definition='Cites stored appearance timing evidence.',
            ),
            ComponentSpec(
                name='optional_calendar_component',
                required=False,
                allowed_evidence_types=('team_calendar_density',),
                plain_language_definition='Optional schedule context note.',
            ),
        )),
        classification=classification,
    ))
    return registry


def _create_sync_run(*, source='phase0e_test'):
    run = SyncRun(
        job_name='phase0e_composed_read_test',
        started_at=datetime(2026, 7, 5, 12, 0, 0),
        completed_at=datetime(2026, 7, 5, 12, 0, 1),
        status='success',
        stage='complete',
        source=source,
    )
    db.session.add(run)
    db.session.flush()
    return run


def _evidence(
    evidence_type,
    *,
    key,
    completeness=EvidenceObject.COMPLETENESS_COMPLETE,
    sync_run_id=None,
):
    evidence = EvidenceObject(
        evidence_key=f'test:evidence:{key}',
        evidence_type=evidence_type,
        subject_type='pitcher',
        subject_id=str(key),
        subject_key=f'pitcher:{key}',
        product_date=PRODUCT_DATE,
        claim_template_id='test_claim',
        rendered_claim='Stored test evidence.',
        rule_id='workload_last_final_appearance',
        rule_version=1,
        rule_definition_hash='test-hash',
        typed_cited_inputs=[],
        computation_trace={'steps': ['test']},
        completeness_state=completeness,
        reason_codes=[],
        limitations=[],
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='test',
        sync_run_id=sync_run_id,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    evidence.citations = [
        EvidenceCitation(
            source_family='game_logs',
            source_table='game_logs',
            source_pk=str(key),
            source_field_names=['pitches_thrown'],
            citation_role='supporting_input',
            cited_values={'pitches_thrown': 18},
            provenance={'source': 'game_logs', 'sync_run_id': sync_run_id},
        )
    ]
    db.session.add(evidence)
    db.session.flush()
    return evidence


def test_registered_production_read_types_remain_internal_only():
    from services.reliever_daily_read import (
        READ_TYPE as RELIEVER_READ_TYPE,
        register_reliever_daily_read,
    )
    from services.team_daily_read import (
        READ_TYPE as TEAM_READ_TYPE,
        register_team_daily_read,
    )

    register_reliever_daily_read()
    register_team_daily_read()
    rows = read_type_registry.all_read_types()
    assert [row.read_type for row in rows] == [RELIEVER_READ_TYPE, TEAM_READ_TYPE]
    assert all(
        row.classification == EvidenceClassification.INTERNAL_ONLY_FOR_NOW
        for row in rows
    )
    assert validate_read_type_registry() == {
        'read_type_count': 2,
        'classified_count': 2,
    }


def test_contract_round_trip_reconstructs_components_citations_summary_and_provenance(app):
    with app.app_context():
        sync_run = _create_sync_run()
        workload = _evidence('workload_recovery_fact', key='workload', sync_run_id=sync_run.id)
        context = _evidence('appearance_context_fact', key='context', sync_run_id=sync_run.id)
        read = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id=42,
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_PARTIAL,
                    evidence_objects=(context,),
                    reason_codes=('component_evidence_unavailable',),
                    limitations=('context window partial',),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )
        db.session.commit()

        stored = ComposedRead.query.one()
        payload = stored.to_dict()
        sync_run_id = sync_run.id

    assert read.id == stored.id
    assert payload['read_type'] == 'test_only_daily_bundle'
    assert payload['subject_type'] == ComposedRead.SUBJECT_PITCHER_DAY
    assert payload['subject_id'] == '42'
    assert payload['product_date'] == '2026-07-05'
    assert payload['completeness_state'] == ComposedRead.COMPLETENESS_PARTIAL
    assert payload['posture'] == ComposedRead.POSTURE_INTERNAL_ONLY
    assert payload['source'] == 'phase0e:composed_read'
    assert payload['sync_run_id'] == sync_run_id
    assert payload['component_summary']['workload_component'] == {
        'state': ComposedRead.COMPLETENESS_COMPLETE,
        'required': True,
        'evidence_citation_count': 1,
    }
    assert payload['component_summary']['optional_calendar_component'] == {
        'state': ComposedReadComponent.COMPONENT_ABSENT,
        'required': False,
        'evidence_citation_count': 0,
    }
    assert sorted(component['component_name'] for component in payload['components']) == [
        'context_component',
        'optional_calendar_component',
        'workload_component',
    ]
    context_component = [
        component for component in payload['components']
        if component['component_name'] == 'context_component'
    ][0]
    assert context_component['evidence_citations'][0]['evidence_object_id'] == context.id
    assert (
        context_component['evidence_citations'][0]['cited_completeness_state']
        == EvidenceObject.COMPLETENESS_COMPLETE
    )
    assert 'context_component:component_evidence_unavailable' in payload['reason_codes']
    assert 'context_component:context window partial' in payload['limitations']
    assert 'headline' not in payload
    assert ComposedReadEvidenceCitation.query.count() == 2


@pytest.mark.parametrize('state', [
    ComposedRead.COMPLETENESS_COMPLETE,
    ComposedRead.COMPLETENESS_PARTIAL,
    ComposedRead.COMPLETENESS_UNKNOWN,
    ComposedRead.COMPLETENESS_CONFLICT,
    ComposedRead.COMPLETENESS_WITHHELD,
])
def test_degradation_calculus_required_component_severity_ordering(app, state):
    with app.app_context():
        sync_run = _create_sync_run(source=f'phase0e_test_{state}')
        workload = _evidence('workload_recovery_fact', key=f'workload-{state}', sync_run_id=sync_run.id)
        context = _evidence('appearance_context_fact', key=f'context-{state}', sync_run_id=sync_run.id)
        read = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id=f'pitcher-{state}',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=state,
                    evidence_objects=(workload,),
                    reason_codes=(
                        ('component_evidence_conflict',)
                        if state == ComposedRead.COMPLETENESS_CONFLICT else ()
                    ),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(context,),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )

    assert read.completeness_state == state
    if state == ComposedRead.COMPLETENESS_CONFLICT:
        assert 'workload_component:component_evidence_conflict' in read.reason_codes


def test_degradation_calculus_absent_required_unknown_and_optional_never_degrades(app):
    with app.app_context():
        sync_run = _create_sync_run()
        workload = _evidence('workload_recovery_fact', key='complete-required', sync_run_id=sync_run.id)
        optional = _evidence('team_calendar_density', key='optional-conflict', sync_run_id=sync_run.id)
        absent_required = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='missing-context',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )
        complete_with_optional_conflict = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='optional-conflict',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(_evidence('appearance_context_fact', key='context-complete', sync_run_id=sync_run.id),),
                ),
                'optional_calendar_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_CONFLICT,
                    evidence_objects=(optional,),
                    reason_codes=('component_evidence_conflict',),
                    limitations=('optional note only',),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )

    assert absent_required.completeness_state == ComposedRead.COMPLETENESS_UNKNOWN
    assert 'context_component:component_absent' in absent_required.reason_codes
    assert (
        absent_required.component_summary['context_component']['state']
        == ComposedReadComponent.COMPONENT_ABSENT
    )
    assert complete_with_optional_conflict.completeness_state == ComposedRead.COMPLETENESS_COMPLETE
    assert (
        complete_with_optional_conflict
        .component_summary['optional_calendar_component']['state']
        == ComposedRead.COMPLETENESS_CONFLICT
    )
    assert (
        'optional_calendar_component:optional note only'
        in complete_with_optional_conflict.limitations
    )


def test_registry_validation_guards_classification_birth_locked_band_and_vocabulary():
    valid_registry = _registry()
    assert validate_read_type_registry(valid_registry) == {
        'read_type_count': 1,
        'classified_count': 1,
    }
    with pytest.raises(ComposedReadRegistryError, match='duplicate read type'):
        valid_registry.register(valid_registry.get('test_only_daily_bundle', 1))

    with pytest.raises(ComposedReadRegistryError, match='unknown evidence types'):
        _registry(components=(
            ComponentSpec(
                name='workload_component',
                required=True,
                allowed_evidence_types=('missing_evidence_type',),
                plain_language_definition='Invalid unknown evidence type.',
            ),
        ))
    with pytest.raises(ComposedReadRegistryError, match='locked band evidence'):
        _registry(components=(
            ComponentSpec(
                name='workload_component',
                required=True,
                allowed_evidence_types=('appearance_entry_band',),
                plain_language_definition='Invalid locked band evidence.',
            ),
        ))
    with pytest.raises(ComposedReadRegistryError, match='public-facing'):
        _registry(classification=EvidenceClassification.PUBLIC_CANDIDATE_WITH_REQUIRED_LANGUAGE)
    with pytest.raises(ComposedReadRegistryError, match='requires classification'):
        _registry(classification=None)
    with pytest.raises(ComposedReadRegistryError, match='forbidden'):
        _registry(components=(
            ComponentSpec(
                name='fresh_component',
                required=True,
                allowed_evidence_types=('workload_recovery_fact',),
                plain_language_definition='Invalid vocabulary.',
            ),
        ))
    with pytest.raises(ComposedReadRegistryError, match='forbidden'):
        registry = ReadTypeRegistry()
        registry.register(ReadType(
            read_type='headline',
            read_version=1,
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            plain_language_definition=(
                'Test-only read bundles cited evidence and does not conclude status.'
            ),
            components=(
                ComponentSpec(
                    name='workload_component',
                    required=True,
                    allowed_evidence_types=('workload_recovery_fact',),
                    plain_language_definition='Cites stored workload evidence.',
                ),
            ),
            classification=EvidenceClassification.INTERNAL_ONLY_FOR_NOW,
        ))


def test_unregistered_read_type_cannot_build(app):
    with app.app_context():
        with pytest.raises(ComposedReadTypeNotRegistered):
            build_composed_read(
                read_type='missing_read_type',
                subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
                subject_id=1,
                product_date=PRODUCT_DATE,
                component_inputs={},
                registry=ReadTypeRegistry(),
            )


def test_no_headline_state_columns_or_registry_fields_exist():
    forbidden = ('headline', 'read_label', 'state_label', 'label', 'grade', 'score', 'rank')
    for model in (ComposedRead, ComposedReadComponent, ComposedReadEvidenceCitation):
        names = set(model.__table__.columns.keys())
        for name in names:
            if name in {'completeness_state', 'component_state'}:
                continue
            assert not any(term in name for term in forbidden), (model.__name__, name)
    fields = set(ReadType.__dataclass_fields__) | set(ComponentSpec.__dataclass_fields__)
    assert 'classification' in fields
    for field_name in fields:
        assert field_name not in forbidden


def test_citation_integrity_and_black_box_audit(app):
    with app.app_context():
        sync_run = _create_sync_run()
        workload = _evidence('workload_recovery_fact', key='audit-workload', sync_run_id=sync_run.id)
        context = _evidence('appearance_context_fact', key='audit-context', sync_run_id=sync_run.id)
        build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='audit',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(context,),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )
        assert validate_composed_read_integrity(registry=_registry()) == {
            'read_rows_checked': 1,
            'citation_rows_checked': 2,
        }

        missing = EvidenceObject(
            id=999999,
            evidence_key='missing',
            evidence_type='workload_recovery_fact',
            subject_type='pitcher',
            subject_key='missing',
            product_date=PRODUCT_DATE,
            claim_template_id='missing',
            rendered_claim='Missing test row.',
            rule_id='workload_last_final_appearance',
            rule_version=1,
            rule_definition_hash='missing',
            typed_cited_inputs=[],
            computation_trace={},
            completeness_state=EvidenceObject.COMPLETENESS_COMPLETE,
            posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
            source='test',
        )
        with pytest.raises(ComposedReadBuildError, match='missing evidence object'):
            build_composed_read(
                read_type='test_only_daily_bundle',
                subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
                subject_id='bad-citation',
                product_date=PRODUCT_DATE,
                component_inputs={
                    'workload_component': ComponentInput(
                        component_state=ComposedRead.COMPLETENESS_COMPLETE,
                        evidence_objects=(missing,),
                    ),
                    'context_component': ComponentInput(
                        component_state=ComposedRead.COMPLETENESS_COMPLETE,
                        evidence_objects=(context,),
                    ),
                },
                registry=_registry(),
            )
        with pytest.raises(ComposedReadBuildError, match='evidence_type_not_allowed'):
            build_composed_read(
                read_type='test_only_daily_bundle',
                subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
                subject_id='bad-type',
                product_date=PRODUCT_DATE,
                component_inputs={
                    'workload_component': ComponentInput(
                        component_state=ComposedRead.COMPLETENESS_COMPLETE,
                        evidence_objects=(context,),
                    ),
                    'context_component': ComponentInput(
                        component_state=ComposedRead.COMPLETENESS_COMPLETE,
                        evidence_objects=(context,),
                    ),
                },
                registry=_registry(),
            )


def test_test_only_read_lifecycle_degrade_recompute_and_rebuild_supersedes(app):
    with app.app_context():
        sync_run = _create_sync_run()
        workload = _evidence('workload_recovery_fact', key='life-workload', sync_run_id=sync_run.id)
        context = _evidence('appearance_context_fact', key='life-context', sync_run_id=sync_run.id)
        unrelated = _evidence('workload_recovery_fact', key='unrelated', sync_run_id=sync_run.id)
        first = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='life',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_UNKNOWN,
                    evidence_objects=(context,),
                    reason_codes=('component_evidence_unavailable',),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )
        unrelated_read = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='unrelated',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(unrelated,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(context,),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )
        db.session.commit()

        marked = mark_dependent_reads_for_recompute(
            evidence_object_ids=(workload.id,),
            reason_code='component_evidence_superseded',
            batch_size=10,
            sync_run_id=sync_run.id,
        )
        db.session.commit()
        assert marked == {'marked_count': 1, 'read_ids': [first.id]}
        assert db.session.get(ComposedRead, first.id).recompute_status == (
            ComposedRead.RECOMPUTE_NEEDED
        )
        assert db.session.get(ComposedRead, unrelated_read.id).recompute_status == (
            ComposedRead.RECOMPUTE_CURRENT
        )

        rebuilt = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='life',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(context,),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )
        db.session.commit()
        old = db.session.get(ComposedRead, first.id)
        new = db.session.get(ComposedRead, rebuilt.id)

    assert old.recompute_status == ComposedRead.RECOMPUTE_SUPERSEDED
    assert old.superseded_by_read_id == new.id
    assert old.read_key.endswith(f':superseded:{old.id}')
    assert new.completeness_state == ComposedRead.COMPLETENESS_COMPLETE
    assert ComposedRead.query.filter_by(read_key=new.read_key).count() == 1


def test_posture_immutability_and_correction_policy_registration(app):
    with app.app_context():
        assert validate_correction_sensitive_model(ComposedRead)
        assert correction_policy('composed_read_corrections').source_family == (
            'phase0e_composed_read_contract'
        )
        sync_run = _create_sync_run()
        workload = _evidence('workload_recovery_fact', key='posture-workload', sync_run_id=sync_run.id)
        context = _evidence('appearance_context_fact', key='posture-context', sync_run_id=sync_run.id)
        read = build_composed_read(
            read_type='test_only_daily_bundle',
            subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
            subject_id='posture',
            product_date=PRODUCT_DATE,
            component_inputs={
                'workload_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(workload,),
                ),
                'context_component': ComponentInput(
                    component_state=ComposedRead.COMPLETENESS_COMPLETE,
                    evidence_objects=(context,),
                ),
            },
            sync_run_id=sync_run.id,
            registry=_registry(),
        )

    assert read.posture == ComposedRead.POSTURE_INTERNAL_ONLY
    assert not hasattr(ComposedRead, 'POSTURE_PUBLIC_CANDIDATE')


def test_behavior_freeze_public_modules_do_not_import_or_query_composed_reads():
    blocked_references = (
        'ComposedRead',
        'composed_reads',
        'composed_read_registry',
        'services.composed_read',
        'test_only_daily_bundle',
    )
    scanned = []
    for path in PUBLIC_PAYLOAD_SURFACES:
        files = (
            [file for file in path.rglob('*') if file.is_file()]
            if path.is_dir()
            else [path]
        )
        for file in files:
            if file.suffix not in {'.py', '.js', '.jsx', '.ts', '.tsx', '.json'}:
                continue
            scanned.append(file)
            text = file.read_text(encoding='utf-8', errors='ignore')
            for reference in blocked_references:
                assert reference not in text, f'{reference} leaked into {file}'
    assert scanned


def test_phase0e_migration_round_trip_and_single_head_static():
    path = _migration_file()
    source = path.read_text(encoding='utf-8')
    assert f"revision = '{PHASE0E_REVISION}'" in source
    assert f"down_revision = '{PHASE0D_REVISION}'" in source
    assert 'composed_reads' in source
    assert 'composed_read_components' in source
    assert 'composed_read_evidence_citations' in source

    revisions = {}
    for migration_path in glob.glob(os.path.join(MIGRATIONS_DIR, '*.py')):
        text = Path(migration_path).read_text(encoding='utf-8')
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = (down.group(1).strip() if down else None)
    referenced = {down for down in revisions.values() if down and down != 'None'}
    assert set(revisions) - referenced == {EXPECTED_ALEMBIC_HEAD}

    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    sa.Table('evidence_objects', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    with engine.begin() as connection:
        module = _load_migration()
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()
        assert _table_exists(connection, 'composed_reads')
        assert _table_exists(connection, 'composed_read_components')
        assert _table_exists(connection, 'composed_read_evidence_citations')
        module.downgrade()
        assert not _table_exists(connection, 'composed_read_evidence_citations')
        assert not _table_exists(connection, 'composed_read_components')
        assert not _table_exists(connection, 'composed_reads')


def _migration_file():
    matches = list(MIGRATIONS_DIR.glob(f'{PHASE0E_REVISION}_*.py'))
    assert len(matches) == 1, matches
    return matches[0]


def _load_migration():
    spec = importlib.util.spec_from_file_location('phase0e_composed_reads', _migration_file())
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_exists(connection, table_name):
    result = connection.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
    ), {'table_name': table_name})
    return result.first() is not None
