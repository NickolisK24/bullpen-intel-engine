"""Tests for the SC-03A governed Team State Share Artifact generation cutover.

Covers the authoritative production path (readiness -> gather -> eligibility ->
canonical payload -> SC-01 immutable publication), the deterministic result
contract, durable generation audit, the internal repository/query layer, the
temporary compatibility adapter, the internal admin trigger security, and the
migration round-trip.
"""

import importlib.util
import re
from datetime import date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

import models.share_artifact  # noqa: F401  (registers ORM immutability listeners)
from models.pitcher import Pitcher
from models.share_artifact import ShareArtifact
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from models.sync_run import SyncRun
from services import share_artifact_generation as gen_module
from services import team_state_source as source_module
from services.share_artifact_generation import (
    FAILURE_PUBLICATION,
    FAILURE_READINESS_RESOLUTION,
    OUTCOME_FAILED_CLOSED,
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
    generate_team_state_artifact,
)
from services.share_artifact_integrity import ShareArtifactIntegrityError
from services.share_artifact_repository import (
    get_latest_published_team_state_artifact,
    get_share_artifact_by_public_id,
    get_team_state_artifact_for_date,
    get_team_state_artifact_for_version,
    inspect_share_artifact_lifecycle,
    list_generation_audits,
    list_recent_team_state_artifacts,
)
from services.share_artifacts import verify_share_artifact_integrity, withdraw_share_artifact
from services.share_card_compatibility import (
    COMPATIBILITY_SOURCE,
    build_share_card_compatibility_view,
    get_team_state_card,
)
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE, TEAM_STATE_V1
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


TEAM_ID = 147
SNAPSHOT_ID = 5001
MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / 'migrations' / 'versions'
GEN_REVISION = 'e2b8d5a3c9f1'
PRIOR_REVISION = 'c1a7f4e2b9d6'


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


# ---------------------------------------------------------------------------
# Governed readiness builder + trusted-snapshot install
# ---------------------------------------------------------------------------


def _readiness(*, team_id=TEAM_ID, status_code='operationally_constrained',
               confidence='high', data_state='fresh', freshness_state='current',
               contract_state='degraded'):
    return {
        'capability': 'team_operations_bullpen_readiness',
        'scope': 'team_bullpen_readiness',
        'contract': 'team_operations_bullpen_readiness_api_contract',
        'contract_version': 'v3_phase_4',
        'contract_state': contract_state,
        'ranking_applied': False,
        'selection_made': False,
        'generated_at': '2026-07-20T12:00:00Z',
        'team': {'team_id': team_id, 'team_name': 'Test Club', 'team_abbreviation': 'TST'},
        'readiness': {
            'status': 'Operationally Constrained',
            'status_code': status_code,
            'summary': 'Two late-inning arms are down.',
            'basis': [],
        },
        'constraints': [{
            'constraint_id': 'workload_high', 'category': 'workload', 'severity': 'caution',
            'affected_area': 'bullpen', 'count': 2, 'message': 'Heavy recent relief workload.',
            'evidence': [],
        }],
        'trust_metadata': {
            'confidence': confidence, 'confidence_reasons': [], 'data_state': data_state,
            'source_evidence_state': 'complete', 'governance_state': 'compliant',
            'generated_at': '2026-07-20T12:00:00Z', 'limitations': [], 'explanations': [],
            'refusal_reasons': [], 'trust_validation_errors': [],
            'ranking_applied': False, 'selection_made': False,
        },
        'freshness': {
            'freshness_state': freshness_state, 'data_through': '2026-07-20',
            'latest_workload_date': '2026-07-20', 'last_successful_sync': '2026-07-20T11:00:00Z',
            'latest_sync_status': 'success', 'latest_fatigue_calculated_at': '2026-07-20T11:30:00Z',
            'generated_at': '2026-07-20T12:00:00Z', 'stale_warning': None,
            'missing_data_warning': None, 'limitations': [],
        },
        'fail_closed': {'failed_closed': False, 'state': 'degraded_safe_output'},
        'refusal': {'refused': False},
    }


def _resolver(readiness):
    def _resolve(team_id, *, requested_date=None, session=None):
        return readiness
    return _resolve


def _install_trusted_snapshot(monkeypatch, *, snapshot_id=SNAPSHOT_ID, sync_run_id=None,
                              data_through=date(2026, 7, 20), unavailable_reason=None):
    class _Snap:
        pass
    snap = _Snap()
    snap.id = snapshot_id
    snap.sync_run_id = sync_run_id
    snap.data_through = data_through
    snap.published_at = datetime(2026, 7, 20, 13, 0, 0)
    monkeypatch.setattr(source_module, 'get_latest_dashboard_snapshot', lambda *a, **k: snap)
    monkeypatch.setattr(source_module, 'snapshot_unavailable_reason', lambda s, *a, **k: unavailable_reason)
    return snap


def _seed_team(team_id=TEAM_ID, mlb_id=910001):
    db.session.add(Pitcher(mlb_id=mlb_id, full_name='Active Arm', team_id=team_id, active=True))
    db.session.flush()


def _eligible_env(monkeypatch, *, with_sync_run=False):
    _seed_team()
    sync_run_id = None
    if with_sync_run:
        run = SyncRun(job_name='sc03a_test')
        db.session.add(run)
        db.session.flush()
        sync_run_id = run.id
    _install_trusted_snapshot(monkeypatch, sync_run_id=sync_run_id)
    return sync_run_id


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------


def test_eligible_source_publishes_new_artifact(app, monkeypatch):
    _eligible_env(monkeypatch)
    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))

    assert result.outcome == OUTCOME_PUBLISHED
    assert result.eligible is True
    assert result.created_new is True
    assert result.reused_existing is False
    assert result.public_id
    assert result.artifact is not None
    assert result.artifact.lifecycle_state == 'published'
    assert verify_share_artifact_integrity(result.artifact) is True


def test_equivalent_source_reuses_existing(app, monkeypatch):
    _eligible_env(monkeypatch)
    first = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))
    second = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))

    assert first.outcome == OUTCOME_PUBLISHED and first.created_new is True
    assert second.outcome == OUTCOME_REUSED
    assert second.reused_existing is True and second.created_new is False
    assert second.public_id == first.public_id
    assert db.session.query(ShareArtifact).filter_by(lifecycle_state='published').count() == 1


def test_ineligible_source_refuses_without_publication(app, monkeypatch):
    _eligible_env(monkeypatch)
    # data_limited status is unsupported for Team State V1 -> refused.
    result = generate_team_state_artifact(
        TEAM_ID, readiness_resolver=_resolver(_readiness(status_code='data_limited')),
    )
    assert result.outcome == OUTCOME_REFUSED
    assert result.eligible is False
    assert result.public_id is None
    assert 'unsupported_team_state' in result.blocking_conditions
    assert db.session.query(ShareArtifact).count() == 0


def test_operational_exception_fails_closed(app, monkeypatch):
    _eligible_env(monkeypatch)

    def _boom(team_id, *, requested_date=None, session=None):
        raise RuntimeError('readiness pipeline exploded')

    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_boom)
    assert result.outcome == OUTCOME_FAILED_CLOSED
    assert result.failure_code == FAILURE_READINESS_RESOLUTION
    assert result.public_id is None
    assert db.session.query(ShareArtifact).count() == 0


def test_exact_authority_fields_are_persisted(app, monkeypatch):
    sync_run_id = _eligible_env(monkeypatch, with_sync_run=True)
    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))

    artifact = result.artifact
    assert artifact.team_id == TEAM_ID
    assert artifact.source_snapshot_id == SNAPSHOT_ID
    assert artifact.source_sync_run_id == sync_run_id
    assert artifact.render_version == TEAM_STATE_V1
    assert artifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    assert result.source_snapshot_id == SNAPSHOT_ID
    assert result.source_sync_run_id == sync_run_id
    assert result.product_date == date(2026, 7, 20)
    assert result.payload_version == TEAM_STATE_V1


def test_canonical_payload_is_published_unchanged(app, monkeypatch):
    from services.team_state_payload import build_team_state_payload
    from services.team_state_source import gather_team_state_source
    _eligible_env(monkeypatch)
    readiness = _readiness()

    # What the canonical builder would produce for this source.
    source = gather_team_state_source(TEAM_ID, readiness_payload=readiness)
    expected_document = build_team_state_payload(source).document

    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(readiness))
    assert result.artifact.payload == expected_document


def test_transaction_rolls_back_and_no_success_audit_on_failure(app, monkeypatch):
    _eligible_env(monkeypatch)

    def _raise_integrity(artifact):
        raise ShareArtifactIntegrityError('simulated post-publish integrity failure')

    monkeypatch.setattr(gen_module, 'verify_share_artifact_integrity', _raise_integrity)
    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))

    assert result.outcome == OUTCOME_FAILED_CLOSED
    assert result.failure_code == FAILURE_PUBLICATION
    # Publication rolled back — no artifact persisted.
    assert db.session.query(ShareArtifact).count() == 0
    # No misleading success audit; only the failed_closed attempt.
    outcomes = {row.outcome for row in db.session.query(ShareArtifactGenerationAudit).all()}
    assert outcomes == {OUTCOME_FAILED_CLOSED}


# ---------------------------------------------------------------------------
# Durable audit
# ---------------------------------------------------------------------------


def test_published_attempt_is_audited(app, monkeypatch):
    _eligible_env(monkeypatch, with_sync_run=True)
    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))
    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_PUBLISHED
    assert audit.eligible is True
    assert audit.created_new is True
    assert audit.share_artifact_id == result.artifact.id
    assert audit.artifact_public_id == result.public_id
    assert audit.source_snapshot_id == SNAPSHOT_ID
    assert audit.payload_version == TEAM_STATE_V1
    assert audit.resolved_product_date == date(2026, 7, 20)


def test_reused_attempt_is_audited(app, monkeypatch):
    _eligible_env(monkeypatch)
    generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))
    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))
    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_REUSED
    assert audit.reused_existing is True
    assert audit.share_artifact_id is not None


def test_refused_attempt_is_audited_without_artifact_linkage(app, monkeypatch):
    _eligible_env(monkeypatch)
    result = generate_team_state_artifact(
        TEAM_ID, readiness_resolver=_resolver(_readiness(status_code='refused')),
    )
    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_REFUSED
    assert audit.eligible is False
    assert audit.share_artifact_id is None
    assert audit.artifact_public_id is None
    assert 'unsupported_team_state' in (audit.blocking_conditions or [])
    assert audit.reasons


def test_failed_closed_attempt_is_audited(app, monkeypatch):
    _eligible_env(monkeypatch)

    def _boom(team_id, *, requested_date=None, session=None):
        raise RuntimeError('kaboom')

    result = generate_team_state_artifact(TEAM_ID, readiness_resolver=_boom)
    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_FAILED_CLOSED
    assert audit.failure_code == FAILURE_READINESS_RESOLUTION
    assert audit.share_artifact_id is None


# ---------------------------------------------------------------------------
# Repository / query layer
# ---------------------------------------------------------------------------


def _publish_one(monkeypatch):
    _eligible_env(monkeypatch)
    return generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness())).artifact


def test_fetch_by_public_id(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    fetched = get_share_artifact_by_public_id(artifact.public_id, require_active=True)
    assert fetched is not None and fetched.id == artifact.id


def test_latest_published_by_team(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    latest = get_latest_published_team_state_artifact(TEAM_ID)
    assert latest is not None and latest.id == artifact.id


def test_exact_team_date_query(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    exact = get_team_state_artifact_for_date(TEAM_ID, date(2026, 7, 20))
    assert exact is not None and exact.id == artifact.id
    # A different date does not substitute a different artifact.
    assert get_team_state_artifact_for_date(TEAM_ID, date(2026, 7, 19)) is None


def test_version_query(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    versioned = get_team_state_artifact_for_version(TEAM_ID, TEAM_STATE_V1)
    assert versioned is not None and versioned.id == artifact.id
    assert get_team_state_artifact_for_version(TEAM_ID, 'team-state-9.9.9') is None


def test_list_recent(app, monkeypatch):
    _publish_one(monkeypatch)
    recent = list_recent_team_state_artifacts(team_id=TEAM_ID)
    assert len(recent) == 1


def test_withdrawn_artifact_not_served_as_active(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    withdraw_share_artifact(artifact, reason='factual_error')
    db.session.flush()

    assert get_share_artifact_by_public_id(artifact.public_id, require_active=True) is None
    assert get_latest_published_team_state_artifact(TEAM_ID) is None
    # Inspection still reports the lifecycle without serving it as active.
    info = inspect_share_artifact_lifecycle(artifact.public_id)
    assert info['lifecycle_state'] == 'withdrawn'


def test_integrity_mismatch_fails_closed(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    art_id = artifact.id
    db.session.execute(
        sa.update(ShareArtifact).where(ShareArtifact.id == art_id).values(payload={'tampered': True})
    )
    db.session.expire(artifact)
    with pytest.raises(ShareArtifactIntegrityError):
        get_latest_published_team_state_artifact(TEAM_ID)


def test_list_generation_audits(app, monkeypatch):
    _eligible_env(monkeypatch)
    generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness()))
    generate_team_state_artifact(TEAM_ID, readiness_resolver=_resolver(_readiness(status_code='refused')))
    audits = list_generation_audits(team_id=TEAM_ID)
    assert len(audits) == 2
    assert {a.outcome for a in audits} == {OUTCOME_PUBLISHED, OUTCOME_REFUSED}


# ---------------------------------------------------------------------------
# Compatibility adapter (canonical artifact is the single source of truth)
# ---------------------------------------------------------------------------


def test_compatibility_view_is_projected_from_artifact(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    view = build_share_card_compatibility_view(artifact)

    document = artifact.payload
    assert view['source'] == COMPATIBILITY_SOURCE
    assert view['public_id'] == artifact.public_id
    assert view['team']['team_id'] == TEAM_ID
    # Every field is a projection of the immutable payload — nothing composed.
    assert view['headline'] == document['team_state']['status_label']
    assert view['summary'] == document['team_state']['summary']
    assert view['status_code'] == document['team_state']['status_code']
    assert [r['detail'] for r in view['receipts']] == [
        c['message'] for c in document['team_state']['constraints']
    ]


def test_compatibility_entry_point_uses_canonical_artifact(app, monkeypatch):
    _publish_one(monkeypatch)
    card = get_team_state_card(TEAM_ID)
    assert card is not None
    assert card['source'] == COMPATIBILITY_SOURCE
    assert card['team']['team_id'] == TEAM_ID


def test_compatibility_returns_none_without_artifact(app):
    # No published artifact -> no fabricated card (fail honest, no legacy composition).
    assert get_team_state_card(TEAM_ID) is None


def test_compatibility_view_is_deterministic(app, monkeypatch):
    artifact = _publish_one(monkeypatch)
    assert build_share_card_compatibility_view(artifact) == build_share_card_compatibility_view(artifact)


# ---------------------------------------------------------------------------
# Admin trigger security
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client():
    flask_app = Flask(__name__)
    flask_app.config['ADMIN_API_TOKEN'] = 'secret-token'
    from api.share_artifacts_admin import share_artifacts_admin_bp
    flask_app.register_blueprint(
        share_artifacts_admin_bp, url_prefix='/api/internal/share-artifacts',
    )
    return flask_app.test_client()


GEN_PATH = '/api/internal/share-artifacts/team-state/generate'


def test_admin_requires_token(admin_client):
    resp = admin_client.post(GEN_PATH, json={'team_id': TEAM_ID})
    assert resp.status_code == 401


def test_admin_rejects_wrong_token(admin_client):
    resp = admin_client.post(GEN_PATH, json={'team_id': TEAM_ID}, headers={'X-Admin-Token': 'nope'})
    assert resp.status_code == 401


def test_admin_rejects_invalid_team_id(admin_client):
    resp = admin_client.post(GEN_PATH, json={'team_id': 'abc'}, headers={'X-Admin-Token': 'secret-token'})
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_team_id'


def test_admin_rejects_invalid_date(admin_client):
    resp = admin_client.post(
        GEN_PATH,
        json={'team_id': TEAM_ID, 'requested_date': 'not-a-date'},
        headers={'X-Admin-Token': 'secret-token'},
    )
    assert resp.status_code == 400
    assert resp.get_json()['error'] == 'invalid_requested_date'


def test_admin_returns_result_contract(admin_client, monkeypatch):
    class _FakeResult:
        outcome = OUTCOME_REFUSED

        def to_dict(self):
            return {'outcome': OUTCOME_REFUSED, 'eligible': False, 'public_id': None}

    monkeypatch.setattr(gen_module, 'generate_team_state_artifact', lambda *a, **k: _FakeResult())
    resp = admin_client.post(GEN_PATH, json={'team_id': TEAM_ID}, headers={'X-Admin-Token': 'secret-token'})
    assert resp.status_code == 200
    assert resp.get_json()['outcome'] == OUTCOME_REFUSED


def test_admin_sanitizes_internal_errors(admin_client, monkeypatch):
    def _boom(*a, **k):
        raise RuntimeError('secret internal detail')

    monkeypatch.setattr(gen_module, 'generate_team_state_artifact', _boom)
    resp = admin_client.post(GEN_PATH, json={'team_id': TEAM_ID}, headers={'X-Admin-Token': 'secret-token'})
    assert resp.status_code == 503
    body = resp.get_json()
    assert body['outcome'] == OUTCOME_FAILED_CLOSED
    assert body['failure_code'] == 'internal_error'
    assert 'secret internal detail' not in str(body)


# ---------------------------------------------------------------------------
# Migration round-trip + single head
# ---------------------------------------------------------------------------


def _load_migration():
    matches = list(MIGRATIONS_DIR.glob(f'{GEN_REVISION}_*.py'))
    assert len(matches) == 1, matches
    spec = importlib.util.spec_from_file_location('sa_gen_audit_migration', matches[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_exists(connection, table_name):
    result = connection.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:t"
    ), {'t': table_name})
    return result.first() is not None


def test_migration_round_trip_and_single_head():
    source = list(MIGRATIONS_DIR.glob(f'{GEN_REVISION}_*.py'))[0].read_text(encoding='utf-8')
    assert f"revision = '{GEN_REVISION}'" in source
    assert f"down_revision = '{PRIOR_REVISION}'" in source

    revisions = {}
    for path in MIGRATIONS_DIR.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = down.group(1).strip() if down else None
    referenced = {down for down in revisions.values() if down and down != 'None'}
    assert set(revisions) - referenced == {GEN_REVISION}

    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    sa.Table('share_artifacts', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        module = _load_migration()
        module.op = Operations(MigrationContext.configure(connection))
        module.upgrade()
        assert _table_exists(connection, 'share_artifact_generation_audits')
        module.downgrade()
        assert not _table_exists(connection, 'share_artifact_generation_audits')


# ---------------------------------------------------------------------------
# Transitional artifact-backed read endpoint (cutover)
# ---------------------------------------------------------------------------


@pytest.fixture
def share_card_client(app):
    from api.share_cards import share_cards_bp
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')
    return app.test_client()


def _card_path(team_id=TEAM_ID):
    return f'/api/share-cards/team-state/{team_id}'


def test_share_card_endpoint_unavailable_without_artifact(share_card_client):
    resp = share_card_client.get(_card_path())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['available'] is False
    assert body['reason'] == 'no_published_artifact'


def test_share_card_endpoint_serves_published_artifact(share_card_client, monkeypatch):
    _publish_one(monkeypatch)
    resp = share_card_client.get(_card_path())
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['available'] is True
    assert body['card']['source'] == COMPATIBILITY_SOURCE
    assert body['card']['team']['team_id'] == TEAM_ID


def test_share_card_endpoint_fails_closed_on_integrity_mismatch(share_card_client, monkeypatch):
    artifact = _publish_one(monkeypatch)
    db.session.execute(
        sa.update(ShareArtifact).where(ShareArtifact.id == artifact.id).values(payload={'tampered': True})
    )
    db.session.commit()
    resp = share_card_client.get(_card_path())
    assert resp.status_code == 503
    assert resp.get_json()['available'] is False


def test_share_card_endpoint_does_not_serve_withdrawn(share_card_client, monkeypatch):
    artifact = _publish_one(monkeypatch)
    withdraw_share_artifact(artifact, reason='factual_error')
    db.session.commit()
    resp = share_card_client.get(_card_path())
    assert resp.status_code == 200
    assert resp.get_json()['available'] is False
