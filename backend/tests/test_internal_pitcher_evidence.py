from datetime import date, datetime
from pathlib import Path

import pytest
from flask import Flask

import models.composed_read  # noqa: F401
import models.evidence_contract  # noqa: F401
import models.legacy_read_audit  # noqa: F401
import models.pitcher  # noqa: F401
import models.sync_run  # noqa: F401
from models.composed_read import ComposedRead
from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.legacy_read_audit import LegacyReadDivergence
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from services.composed_read import ComponentInput, build_composed_read
from services.reliever_daily_read import READ_TYPE, READ_VERSION, register_reliever_daily_read
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DATE = date(2026, 7, 5)
ADMIN_HEADERS = {ADMIN_TOKEN_HEADER: 'admin-secret'}
ROUTE = '/api/system/internal/pitcher-evidence'


@pytest.fixture
def app():
    from api.pitchers import pitchers_bp
    from api.system import system_bp

    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    flask_app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    db.init_app(flask_app)
    flask_app.register_blueprint(system_bp, url_prefix='/api/system')
    flask_app.register_blueprint(pitchers_bp, url_prefix='/api/pitchers')

    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def client(app):
    return app.test_client()


def _sync_run():
    row = SyncRun(
        job_name='phase0f_internal_pitcher_evidence_test',
        started_at=datetime(2026, 7, 5, 12, 0, 0),
        completed_at=datetime(2026, 7, 5, 12, 0, 1),
        status='success',
        stage='complete',
        source='phase0f_test',
    )
    db.session.add(row)
    db.session.flush()
    return row


def _pitcher(*, mlb_id=660001, name='Review Pitcher'):
    row = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=147,
        team_name='Test Giants',
        team_abbreviation='TST',
        position='P',
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _evidence(
    pitcher,
    sync_run,
    *,
    key,
    evidence_type,
    rule_id,
    rendered_claim,
    state=EvidenceObject.COMPLETENESS_COMPLETE,
    reason_codes=(),
    limitations=(),
):
    row = EvidenceObject(
        evidence_key=f'phase0f:test:{key}',
        evidence_type=evidence_type,
        subject_type='pitcher',
        subject_id=str(pitcher.id),
        subject_key=f'pitcher:{pitcher.id}:{PRODUCT_DATE.isoformat()}:{key}',
        product_date=PRODUCT_DATE,
        claim_template_id=f'{rule_id}:test',
        rendered_claim=rendered_claim,
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash='phase0f-test',
        typed_cited_inputs=[{'fixture': key}],
        computation_trace={'fixture': key},
        completeness_state=state,
        reason_codes=list(reason_codes),
        limitations=list(limitations),
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='phase0f_test',
        sync_run_id=sync_run.id,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    row.citations = [
        EvidenceCitation(
            source_family='game_logs',
            source_table='game_logs',
            source_pk=f'fixture:{key}',
            source_field_names=['fixture'],
            citation_role='supporting_input',
            cited_values={'fixture': key},
            provenance={'source': 'phase0f_test', 'sync_run_id': sync_run.id},
        )
    ]
    db.session.add(row)
    db.session.flush()
    return row


def _read_fixture():
    sync_run = _sync_run()
    pitcher = _pitcher()
    workload = _evidence(
        pitcher,
        sync_run,
        key='workload',
        evidence_type='workload_recovery_fact',
        rule_id='workload_window_appearances',
        rendered_claim='Stored workload claim from the evidence object.',
    )
    recent = _evidence(
        pitcher,
        sync_run,
        key='entry',
        evidence_type='appearance_context_fact',
        rule_id='appearance_entry_context',
        rendered_claim='Stored entry context claim from the evidence object.',
    )
    roster = _evidence(
        pitcher,
        sync_run,
        key='roster',
        evidence_type='pitcher_roster_membership_context',
        rule_id='pitcher_roster_membership_context',
        rendered_claim='Stored roster context claim from the evidence object.',
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=('roster_membership_unknown',),
        limitations=('public roster snapshot missing',),
    )

    register_reliever_daily_read()
    read = build_composed_read(
        read_type=READ_TYPE,
        read_version=READ_VERSION,
        subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
        subject_id=pitcher.id,
        subject_key=f'pitcher:{pitcher.id}:{PRODUCT_DATE.isoformat()}:reliever-daily-read',
        product_date=PRODUCT_DATE,
        component_inputs={
            'workload_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
                evidence_objects=(workload,),
            ),
            'rest_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_UNKNOWN,
                reason_codes=('component_evidence_unavailable',),
            ),
            'recent_outing_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
                evidence_objects=(recent,),
            ),
            'roster_il_context': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_UNKNOWN,
                evidence_objects=(roster,),
                reason_codes=('roster_membership_unknown',),
                limitations=('public roster snapshot missing',),
            ),
            'data_completeness_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
            ),
        },
        source='phase0f_test',
        sync_run_id=sync_run.id,
    )
    divergence = LegacyReadDivergence(
        subject_type=LegacyReadDivergence.SUBJECT_PITCHER_DAY,
        subject_id=str(pitcher.id),
        product_date=PRODUCT_DATE,
        category=LegacyReadDivergence.CATEGORY_ACTIONABLE_ON_DEGRADED_READ,
        is_material=True,
        escalation_state=LegacyReadDivergence.ESCALATION_RECORDED,
        legacy_capture={'stored': 'legacy'},
        read_capture={'stored': 'read'},
        comparison_basis='phase0f_test_basis',
        notes='Stored reconciliation note.',
        source='phase0f_test',
        sync_run_id=sync_run.id,
    )
    db.session.add(divergence)
    db.session.commit()
    return pitcher, read


def _section_keys(payload):
    return {
        'reliever_daily_read',
        'read_components',
        'states',
        'reasons',
        'limitations',
        'cited_evidence_rendered_claims',
        'evidence_objects',
        'workload_evidence_references',
        'entry_exit_context_references',
        'roster_depth_il_context',
        'other_pitcher_evidence_references',
        'reconciliation_divergences',
        'source_readiness_notes',
    } & set(payload)


def test_internal_pitcher_evidence_requires_admin_token(client):
    response = client.get(f'{ROUTE}?pitcher_id=1&date={PRODUCT_DATE.isoformat()}')
    assert response.status_code == 401

    wrong = client.get(
        f'{ROUTE}?pitcher_id=1&date={PRODUCT_DATE.isoformat()}',
        headers={ADMIN_TOKEN_HEADER: 'wrong'},
    )
    assert wrong.status_code == 401


def test_internal_pitcher_evidence_returns_stored_pitcher_read_payload(app, client):
    with app.app_context():
        pitcher, read = _read_fixture()
        pitcher_id = pitcher.id
        mlb_id = pitcher.mlb_id
        read_id = read.id

    response = client.get(
        f'{ROUTE}?pitcher_id={pitcher_id}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['capability'] == 'phase0f_internal_pitcher_evidence_review'
    assert payload['route_status'] == 'internal_admin_only'
    assert payload['internal_only_watermark'] == {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }
    assert payload['request'] == {
        'pitcher_id': pitcher_id,
        'mlb_id': mlb_id,
        'date': PRODUCT_DATE.isoformat(),
        'data_through': PRODUCT_DATE.isoformat(),
    }
    assert payload['pitcher']['full_name'] == 'Review Pitcher'
    assert payload['reliever_daily_read']['id'] == read_id
    assert payload['reliever_daily_read']['read_type'] == 'reliever_daily_read'
    assert _section_keys(payload) == {
        'reliever_daily_read',
        'read_components',
        'states',
        'reasons',
        'limitations',
        'cited_evidence_rendered_claims',
        'evidence_objects',
        'workload_evidence_references',
        'entry_exit_context_references',
        'roster_depth_il_context',
        'other_pitcher_evidence_references',
        'reconciliation_divergences',
        'source_readiness_notes',
    }
    component_names = {row['component_name'] for row in payload['read_components']}
    assert {
        'workload_component',
        'recent_outing_component',
        'roster_il_context',
        'data_completeness_component',
    }.issubset(component_names)
    assert payload['workload_evidence_references'][0]['rendered_claim'] == (
        'Stored workload claim from the evidence object.'
    )
    assert payload['entry_exit_context_references'][0]['rendered_claim'] == (
        'Stored entry context claim from the evidence object.'
    )
    assert payload['roster_depth_il_context'][0]['rendered_claim'] == (
        'Stored roster context claim from the evidence object.'
    )
    assert payload['reconciliation_divergences'][0]['notes'] == 'Stored reconciliation note.'


def test_internal_pitcher_evidence_handles_missing_optional_sections(app, client):
    with app.app_context():
        pitcher = _pitcher(mlb_id=660002, name='Missing Sections Pitcher')
        pitcher_id = pitcher.id
        db.session.commit()

    response = client.get(
        f'{ROUTE}?pitcher_id={pitcher_id}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['reliever_daily_read'] is None
    assert payload['read_components'] == []
    assert payload['cited_evidence_rendered_claims'] == []
    assert payload['evidence_objects'] == []
    assert payload['workload_evidence_references'] == []
    assert payload['entry_exit_context_references'] == []
    assert payload['roster_depth_il_context'] == []
    assert payload['reconciliation_divergences'] == []
    assert set(payload['source_readiness_notes']['missing_optional_sections']) >= {
        'reliever_daily_read',
        'read_components',
        'cited_evidence_rendered_claims',
        'workload_evidence_references',
        'entry_exit_context_references',
        'roster_depth_il_context',
        'reconciliation_divergences',
    }


def test_internal_pitcher_evidence_is_quote_only_for_rendered_claims(app, client):
    with app.app_context():
        pitcher, _read = _read_fixture()
        pitcher_id = pitcher.id

    response = client.get(
        f'{ROUTE}?pitcher_id={pitcher_id}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    payload = response.get_json()
    assert sorted(payload['cited_evidence_rendered_claims']) == sorted([
        'Stored entry context claim from the evidence object.',
        'Stored roster context claim from the evidence object.',
        'Stored workload claim from the evidence object.',
    ])
    body = str(payload).lower()
    assert 'generated_summary' not in body
    assert 'recommendation' not in body
    assert 'prediction' not in body


def test_public_pitcher_search_remains_open_with_admin_token_configured(app, client):
    with app.app_context():
        _pitcher(name='Public Search Pitcher')
        db.session.commit()

    response = client.get('/api/pitchers/search?q=Public')

    assert response.status_code == 200
    payload = response.get_json()
    assert 'results' in payload
    assert str(payload).find('internal_only_watermark') == -1
    assert str(payload).find('cited_evidence_rendered_claims') == -1


def test_internal_pitcher_evidence_service_is_not_imported_by_public_routes():
    public_sources = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/api/pitchers.py',
        REPO_ROOT / 'backend/api/recommendations.py',
        REPO_ROOT / 'backend/api/explanations.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    )
    for path in public_sources:
        source = path.read_text(encoding='utf-8')
        assert 'internal_pitcher_evidence' not in source
        assert 'internal/pitcher-evidence' not in source
