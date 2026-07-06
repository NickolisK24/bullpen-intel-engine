from datetime import date, datetime
from pathlib import Path
import json
import re

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
from services.reliever_daily_read import (
    READ_TYPE as RELIEVER_READ_TYPE,
    READ_VERSION as RELIEVER_READ_VERSION,
    register_reliever_daily_read,
)
from services.team_daily_read import (
    READ_TYPE as TEAM_READ_TYPE,
    READ_VERSION as TEAM_READ_VERSION,
    register_team_daily_read,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
PRODUCT_DATE = date(2026, 7, 5)
TEAM_ID = 147
ADMIN_HEADERS = {ADMIN_TOKEN_HEADER: 'admin-secret'}
ROUTE = '/api/system/internal/team-evidence'
POINTER_KEYS = {
    'read_id',
    'read_key',
    'pitcher_id',
    'pitcher_mlb_id',
    'pitcher_full_name',
    'completeness_state',
    'recompute_status',
}


@pytest.fixture
def app():
    from api.system import system_bp

    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    flask_app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    db.init_app(flask_app)
    flask_app.register_blueprint(system_bp, url_prefix='/api/system')

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
        job_name='phase0g_internal_team_evidence_test',
        started_at=datetime(2026, 7, 5, 12, 0, 0),
        completed_at=datetime(2026, 7, 5, 12, 0, 1),
        status='success',
        stage='complete',
        source='phase0g_test',
    )
    db.session.add(row)
    db.session.flush()
    return row


def _pitcher(*, mlb_id=670001, name='Review Reliever', team_id=TEAM_ID):
    row = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name='Test Giants',
        team_abbreviation='TST',
        position='P',
        active=True,
    )
    db.session.add(row)
    db.session.flush()
    return row


def _team_evidence(
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
        evidence_key=f'phase0g:team:{key}',
        evidence_type=evidence_type,
        subject_type='team',
        subject_id=str(TEAM_ID),
        subject_key=f'team:{TEAM_ID}:{PRODUCT_DATE.isoformat()}:{key}',
        product_date=PRODUCT_DATE,
        claim_template_id=f'{rule_id}:test',
        rendered_claim=rendered_claim,
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash='phase0g-test',
        typed_cited_inputs=[{'fixture': key}],
        computation_trace={'fixture': key},
        completeness_state=state,
        reason_codes=list(reason_codes),
        limitations=list(limitations),
        posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
        source='phase0g_test',
        sync_run_id=sync_run.id,
        recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
        recompute_reason_codes=[],
    )
    row.citations = [
        EvidenceCitation(
            source_family='team_review_fixture',
            source_table='team_review_rows',
            source_pk=f'fixture:{key}',
            source_field_names=['fixture'],
            citation_role='supporting_input',
            cited_values={'fixture': key},
            provenance={'source': 'phase0g_test', 'sync_run_id': sync_run.id},
        )
    ]
    db.session.add(row)
    db.session.flush()
    return row


def _read_fixture():
    sync_run = _sync_run()
    pitcher = _pitcher()
    contributor = _team_evidence(
        sync_run,
        key='contributor',
        evidence_type='team_relief_contributor_basis',
        rule_id='team_relief_contributor_basis',
        rendered_claim='Stored contributor composition claim.',
        state=EvidenceObject.COMPLETENESS_PARTIAL,
        reason_codes=('basis_lower_bound',),
    )
    exposure = _team_evidence(
        sync_run,
        key='exposure',
        evidence_type='team_bullpen_outs_window',
        rule_id='team_bullpen_outs_window',
        rendered_claim='Stored exposure claim.',
    )
    calendar = _team_evidence(
        sync_run,
        key='calendar',
        evidence_type='team_consecutive_game_days',
        rule_id='team_consecutive_game_days',
        rendered_claim='Stored calendar claim.',
    )
    roster = _team_evidence(
        sync_run,
        key='roster',
        evidence_type='team_active_pitcher_census',
        rule_id='team_active_pitcher_census',
        rendered_claim='Stored roster churn claim.',
        state=EvidenceObject.COMPLETENESS_UNKNOWN,
        reason_codes=('roster_snapshot_missing',),
        limitations=('Stored roster limitation.',),
    )
    slate = _team_evidence(
        sync_run,
        key='slate',
        evidence_type='inherited_traffic_fact',
        rule_id='outing_context_unknown',
        rendered_claim='Stored slate completeness claim.',
    )

    register_team_daily_read()
    read = build_composed_read(
        read_type=TEAM_READ_TYPE,
        read_version=TEAM_READ_VERSION,
        subject_type=ComposedRead.SUBJECT_TEAM_DAY,
        subject_id=TEAM_ID,
        subject_key=f'team:{TEAM_ID}:{PRODUCT_DATE.isoformat()}:team-daily-read',
        product_date=PRODUCT_DATE,
        component_inputs={
            'contributor_composition_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_PARTIAL,
                evidence_objects=(contributor,),
                reason_codes=('basis_lower_bound',),
                limitations=('Stored denominator disclaimer.',),
            ),
            'exposure_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
                evidence_objects=(exposure,),
            ),
            'calendar_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
                evidence_objects=(calendar,),
            ),
            'roster_churn_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_UNKNOWN,
                evidence_objects=(roster,),
                reason_codes=('roster_snapshot_missing',),
                limitations=('Stored roster limitation.',),
            ),
            'slate_data_completeness_component': ComponentInput(
                component_state=ComposedRead.COMPLETENESS_COMPLETE,
                evidence_objects=(slate,),
                limitations=('Stored slate limitation.',),
            ),
        },
        source='phase0g_test',
        sync_run_id=sync_run.id,
    )

    register_reliever_daily_read()
    reliever_read = build_composed_read(
        read_type=RELIEVER_READ_TYPE,
        read_version=RELIEVER_READ_VERSION,
        subject_type=ComposedRead.SUBJECT_PITCHER_DAY,
        subject_id=pitcher.id,
        subject_key=f'pitcher:{pitcher.id}:{PRODUCT_DATE.isoformat()}:reliever-daily-read',
        product_date=PRODUCT_DATE,
        component_inputs={},
        source='phase0g_test',
        sync_run_id=sync_run.id,
    )

    divergence = LegacyReadDivergence(
        subject_type=LegacyReadDivergence.SUBJECT_TEAM_DAY,
        subject_id=str(TEAM_ID),
        product_date=PRODUCT_DATE,
        category=LegacyReadDivergence.CATEGORY_TEAM_AGGREGATE_ON_DEGRADED_READ,
        is_material=True,
        escalation_state=LegacyReadDivergence.ESCALATION_RECORDED,
        legacy_capture={'stored': 'legacy'},
        read_capture={'stored': 'read'},
        comparison_basis='phase0g_test_basis',
        notes='Stored team reconciliation note.',
        source='phase0g_test',
        sync_run_id=sync_run.id,
    )
    db.session.add(divergence)
    db.session.commit()
    return pitcher, read, reliever_read


def _json_keys(value):
    if isinstance(value, dict):
        keys = set(value)
        for child in value.values():
            keys.update(_json_keys(child))
        return keys
    if isinstance(value, list):
        keys = set()
        for child in value:
            keys.update(_json_keys(child))
        return keys
    return set()


def _component(payload, name):
    return next(row for row in payload['read_components'] if row['component_name'] == name)


def test_internal_team_evidence_requires_admin_token(app, client):
    with app.app_context():
        _pitcher()
        db.session.commit()

    response = client.get(f'{ROUTE}?team_id={TEAM_ID}&date={PRODUCT_DATE.isoformat()}')
    assert response.status_code == 401

    wrong = client.get(
        f'{ROUTE}?team_id={TEAM_ID}&date={PRODUCT_DATE.isoformat()}',
        headers={ADMIN_TOKEN_HEADER: 'wrong'},
    )
    assert wrong.status_code == 401

    allowed = client.get(
        f'{ROUTE}?team_id={TEAM_ID}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )
    assert allowed.status_code == 200


def test_internal_team_evidence_returns_stored_team_read_payload(app, client):
    with app.app_context():
        pitcher, read, reliever_read = _read_fixture()
        pitcher_id = pitcher.id
        pitcher_mlb_id = pitcher.mlb_id
        read_id = read.id
        reliever_read_id = reliever_read.id

    response = client.get(
        f'{ROUTE}?team_id={TEAM_ID}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['capability'] == 'phase0g_internal_team_evidence_review'
    assert payload['route_status'] == 'internal_admin_only'
    assert payload['internal_only_watermark'] == {
        'internal_only': True,
        'admin_gated': True,
        'phase0b_public_evidence_gate': 'closed',
        'public_evidence_exposure': False,
        'quote_only_rendered_claims': True,
    }
    assert payload['request'] == {
        'team_id': TEAM_ID,
        'date': PRODUCT_DATE.isoformat(),
        'data_through': PRODUCT_DATE.isoformat(),
    }
    assert payload['team'] == {
        'team_id': TEAM_ID,
        'team_name': 'Test Giants',
        'team_abbreviation': 'TST',
    }
    assert payload['team_daily_read']['id'] == read_id
    assert payload['team_daily_read']['read_type'] == TEAM_READ_TYPE
    assert payload['team_daily_read']['subject_type'] == ComposedRead.SUBJECT_TEAM_DAY
    assert payload['states'] == {
        'read_completeness_state': ComposedRead.COMPLETENESS_UNKNOWN,
        'read_recompute_status': ComposedRead.RECOMPUTE_CURRENT,
    }

    component_names = {row['component_name'] for row in payload['read_components']}
    assert component_names == {
        'contributor_composition_component',
        'exposure_component',
        'calendar_component',
        'roster_churn_component',
        'slate_data_completeness_component',
    }
    contributor = _component(payload, 'contributor_composition_component')
    assert contributor['component_state'] == ComposedRead.COMPLETENESS_PARTIAL
    assert contributor['reason_codes'] == ['basis_lower_bound']
    assert contributor['limitations'] == ['Stored denominator disclaimer.']
    roster = _component(payload, 'roster_churn_component')
    assert roster['component_state'] == ComposedRead.COMPLETENESS_UNKNOWN
    assert roster['reason_codes'] == ['roster_snapshot_missing']
    assert roster['limitations'] == ['Stored roster limitation.']

    assert sorted(payload['cited_evidence_rendered_claims']) == sorted([
        'Stored calendar claim.',
        'Stored contributor composition claim.',
        'Stored exposure claim.',
        'Stored roster churn claim.',
        'Stored slate completeness claim.',
    ])
    assert {row['rendered_claim'] for row in payload['evidence_objects']} == {
        'Stored calendar claim.',
        'Stored contributor composition claim.',
        'Stored exposure claim.',
        'Stored roster churn claim.',
        'Stored slate completeness claim.',
    }
    evidence = payload['evidence_objects'][0]
    assert {'source_family', 'source_table', 'cited_values'} <= set(evidence['citations'][0])
    assert payload['reconciliation_divergences'][0]['notes'] == (
        'Stored team reconciliation note.'
    )

    assert payload['reliever_daily_read_pointers'] == [{
        'read_id': reliever_read_id,
        'read_key': payload['reliever_daily_read_pointers'][0]['read_key'],
        'pitcher_id': pitcher_id,
        'pitcher_mlb_id': pitcher_mlb_id,
        'pitcher_full_name': 'Review Reliever',
        'completeness_state': ComposedRead.COMPLETENESS_UNKNOWN,
        'recompute_status': ComposedRead.RECOMPUTE_CURRENT,
    }]
    assert set(payload['reliever_daily_read_pointers'][0]) == POINTER_KEYS
    assert payload['source_readiness_notes']['optional_sections_present'] == {
        'team_daily_read': True,
        'read_components': True,
        'cited_evidence_rendered_claims': True,
        'evidence_objects': True,
        'reliever_daily_read_pointers': True,
        'reconciliation_divergences': True,
    }
    assert payload['source_readiness_notes']['missing_optional_sections'] == []


def test_internal_team_evidence_pointers_have_no_components_or_rollup(app, client):
    with app.app_context():
        _read_fixture()

    response = client.get(
        f'{ROUTE}?teamId={TEAM_ID}&dataThrough={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    pointer = payload['reliever_daily_read_pointers'][0]
    assert set(pointer) == POINTER_KEYS
    assert 'components' not in pointer
    assert 'evidence_citations' not in pointer
    assert 'component_summary' not in pointer
    assert not any(re.search(r'rollup', key, flags=re.I) for key in _json_keys(payload))


def test_internal_team_evidence_handles_missing_optional_sections(app, client):
    with app.app_context():
        _pitcher(mlb_id=670002, name='Missing Sections Reliever')
        db.session.commit()

    response = client.get(
        f'{ROUTE}?team_id={TEAM_ID}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert payload['team_daily_read'] is None
    assert payload['read_components'] == []
    assert payload['cited_evidence_rendered_claims'] == []
    assert payload['evidence_objects'] == []
    assert payload['reliever_daily_read_pointers'] == []
    assert payload['reconciliation_divergences'] == []
    assert set(payload['source_readiness_notes']['missing_optional_sections']) == {
        'team_daily_read',
        'read_components',
        'cited_evidence_rendered_claims',
        'evidence_objects',
        'reliever_daily_read_pointers',
        'reconciliation_divergences',
    }


def test_internal_team_evidence_not_found(client):
    response = client.get(
        f'{ROUTE}?team_id=999999&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 404
    payload = response.get_json()
    assert payload['error'] == 'team_not_found'
    assert payload['http_status'] == 404
    assert payload['internal_only_watermark']['phase0b_public_evidence_gate'] == 'closed'


def test_internal_team_evidence_is_quote_only(app, client):
    with app.app_context():
        _read_fixture()

    response = client.get(
        f'{ROUTE}?team_id={TEAM_ID}&date={PRODUCT_DATE.isoformat()}',
        headers=ADMIN_HEADERS,
    )

    assert response.status_code == 200
    payload_text = json.dumps(response.get_json()).lower()
    assert 'generated_summary' not in payload_text
    assert 'recommendation' not in payload_text
    assert 'prediction' not in payload_text


def test_internal_team_evidence_service_is_not_imported_by_public_routes():
    public_sources = (
        REPO_ROOT / 'backend/api/bullpen.py',
        REPO_ROOT / 'backend/api/pitchers.py',
        REPO_ROOT / 'backend/api/recent_work.py',
        REPO_ROOT / 'backend/api/recommendations.py',
        REPO_ROOT / 'backend/api/explanations.py',
        REPO_ROOT / 'backend/services/dashboard_snapshot.py',
        REPO_ROOT / 'backend/services/bullpen_board.py',
        REPO_ROOT / 'backend/services/what_changed_since_yesterday_public.py',
    )
    for path in public_sources:
        source = path.read_text(encoding='utf-8')
        assert 'internal_team_evidence' not in source
        assert 'internal/team-evidence' not in source

    for path in (REPO_ROOT / 'frontend/src').rglob('*'):
        if path.is_file():
            source = path.read_text(encoding='utf-8')
            assert 'internal_team_evidence' not in source, path
            assert 'internal/team-evidence' not in source, path


def test_internal_team_evidence_service_import_surface():
    source = (REPO_ROOT / 'backend/services/internal_team_evidence.py').read_text(
        encoding='utf-8',
    )

    assert 'internal_pitcher_evidence' not in source
    assert 'public_recent_work' not in source
    assert not re.search(r'from\s+services\s+import\s+sync\b', source)
    assert not re.search(r'import\s+services\.sync\b', source)
    assert not re.search(r'\bimport\s+sync\b', source)
    assert 'request.args' not in source
    assert 'from flask import request' not in source
