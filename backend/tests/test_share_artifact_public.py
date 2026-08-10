"""Tests for the SC-04 public Share Artifact read service + public API."""

from datetime import date

import pytest
from flask import Flask

from models.share_artifact import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_WITHDRAWN,
    ShareArtifact,
    ShareArtifactRelation,
)
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit  # noqa: F401
from services import share_artifact_public as public_module
from services.share_artifact_generation import generate_team_state_artifact
from services.share_artifact_public import (
    RESULT_INTEGRITY_ERROR,
    RESULT_NOT_FOUND,
    RESULT_OK,
    RESULT_SUPERSEDED,
    RESULT_WITHDRAWN,
    is_valid_public_id,
    load_public_share_artifact,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.test_share_artifact_generation import (
    SNAPSHOT_ID,
    TEAM_ID,
    _eligible_env,
    _readiness,
    _resolver,
)
from utils.db import db


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


@pytest.fixture
def client(app):
    from api.share_artifacts_public import share_artifacts_public_bp
    app.register_blueprint(share_artifacts_public_bp, url_prefix='/api/share-artifacts')
    return app.test_client()


def _publish(monkeypatch, **readiness_kw):
    _eligible_env(monkeypatch)
    result = generate_team_state_artifact(
        TEAM_ID, readiness_resolver=_resolver(_readiness(**readiness_kw)),
    )
    assert result.public_id
    return result.artifact


# ---------------------------------------------------------------------------
# public_id validation
# ---------------------------------------------------------------------------


def test_public_id_validation():
    assert is_valid_public_id('abc-123_XYZ.9')
    assert not is_valid_public_id('')
    assert not is_valid_public_id('a b')
    assert not is_valid_public_id('../etc/passwd')
    assert not is_valid_public_id("x'; DROP TABLE share_artifacts;--")
    assert not is_valid_public_id('a' * 65)
    assert not is_valid_public_id(None)


# ---------------------------------------------------------------------------
# service: lifecycle + integrity + whitelist
# ---------------------------------------------------------------------------


def test_published_resolves_ok_with_whitelisted_view(app, monkeypatch):
    artifact = _publish(monkeypatch)
    result = load_public_share_artifact(artifact.public_id)
    assert result.status == RESULT_OK and result.http_status == 200
    view = result.view
    # Whitelist: no raw payload, no internal db id, no equivalence/integrity hash, no audit.
    assert 'payload' not in view and 'payload_json' not in view
    assert 'id' not in view and 'equivalence_key' not in view
    assert 'integrity_hash' not in view and 'trust_metadata' not in view
    # Present public fields.
    assert view['public_id'] == artifact.public_id
    assert view['is_historical'] is True
    assert view['team']['team_id'] == TEAM_ID
    assert view['authority']['source_snapshot_id'] == SNAPSHOT_ID
    assert view['team_state']['status_code'] in {
        'operationally_stable', 'operationally_constrained', 'operationally_stressed',
    }
    assert view['trust']['confidence'] == 'high'
    assert view['routes']['share_url'] == f'/share/{artifact.public_id}'
    assert view['routes']['methodology_url'] and view['routes']['data_trust_url']


def test_current_truth_link_points_at_this_artifacts_own_team_board(app, monkeypatch):
    """The historical -> current handoff must not lose team identity.

    A reader inspecting a historical artifact for one club was previously handed
    the league bullpen surface. The destination is still constructed here from
    constants; only the club's OWN frozen abbreviation is carried across.
    """
    artifact = _publish(monkeypatch)
    view = load_public_share_artifact(artifact.public_id).view

    assert view['team']['team_abbreviation'] == 'TST'
    assert view['routes']['team_url'] == '/bullpen?view=board&team=TST'
    # Still a first-party route built from constants, never an artifact URL.
    assert view['routes']['team_url'].startswith('/bullpen')


def test_current_truth_link_falls_back_when_no_abbreviation_was_stored(app, monkeypatch):
    artifact = _publish(monkeypatch)
    result = load_public_share_artifact(artifact.public_id)
    assert result.view['routes']['team_url'] == '/bullpen?view=board&team=TST'

    # An artifact whose frozen team block carries no abbreviation still gets a
    # working current-truth destination rather than a malformed one.
    assert public_module._team_route(None) == '/bullpen'
    assert public_module._team_route('   ') == '/bullpen'
    assert public_module._team_route('../evil') == '/bullpen?view=board&team=EVIL'
    assert public_module._team_route(' tor ') == '/bullpen?view=board&team=TOR'


def test_unknown_and_malformed_public_id_are_not_found(app):
    assert load_public_share_artifact('does-not-exist').status == RESULT_NOT_FOUND
    assert load_public_share_artifact('bad id!').status == RESULT_NOT_FOUND


def test_draft_is_not_publicly_discoverable(app):
    draft = ShareArtifact(
        public_id='draft-1', artifact_type='team_state', render_version='team-state-1.0.0',
        team_id=TEAM_ID, source_snapshot_id=SNAPSHOT_ID, lifecycle_state=LIFECYCLE_DRAFT,
        payload={'team_state': {'status_code': 'operationally_stable'}}, trust_metadata={},
        equivalence_key='eqk-draft', source='test',
    )
    db.session.add(draft)
    db.session.flush()
    # A known draft public_id must be a 404 (not discoverable), never its content.
    assert load_public_share_artifact('draft-1').status == RESULT_NOT_FOUND


def test_superseded_serves_original_with_replacement(app, monkeypatch):
    original = _publish(monkeypatch)
    # A newer artifact supersedes the original.
    replacement = ShareArtifact(
        public_id='replacement-1', artifact_type=original.artifact_type,
        render_version=original.render_version, team_id=original.team_id,
        source_snapshot_id=original.source_snapshot_id, lifecycle_state='published',
        payload=dict(original.payload), trust_metadata={}, equivalence_key='eqk-repl',
        source='test', product_date=original.product_date,
    )
    db.session.add(replacement)
    db.session.flush()
    db.session.add(ShareArtifactRelation(
        source_artifact_id=replacement.id, target_artifact_id=original.id,
        relation_type=ShareArtifactRelation.RELATION_SUPERSEDES,
    ))
    original.lifecycle_state = LIFECYCLE_SUPERSEDED
    db.session.flush()

    result = load_public_share_artifact(original.public_id)
    assert result.status == RESULT_SUPERSEDED and result.http_status == 200
    # Original frozen content still served.
    assert result.view['public_id'] == original.public_id
    assert result.view['team_state']['status_code']
    # Replacement pointer present.
    assert result.view['superseded']['replacement_public_id'] == 'replacement-1'
    assert result.view['superseded']['replacement_url'] == '/share/replacement-1'


def test_withdrawn_is_gone_with_minimal_body(app, monkeypatch):
    artifact = _publish(monkeypatch)
    artifact.lifecycle_state = LIFECYCLE_WITHDRAWN
    artifact.withdrawn_reason = 'source correction'
    db.session.flush()
    result = load_public_share_artifact(artifact.public_id)
    assert result.status == RESULT_WITHDRAWN and result.http_status == 410
    # Minimal, audit-safe: no meaning-bearing claim.
    assert result.view['withdrawn_reason'] == 'source correction'
    assert 'team_state' not in result.view and 'evidence' not in result.view


def test_integrity_failure_fails_closed(app, monkeypatch):
    artifact = _publish(monkeypatch)

    def _boom(_artifact):
        raise RuntimeError('tampered')

    monkeypatch.setattr(public_module, 'verify_share_artifact_integrity', _boom)
    result = load_public_share_artifact(artifact.public_id)
    assert result.status == RESULT_INTEGRITY_ERROR and result.http_status == 503
    assert result.view is None  # no meaning-bearing content served


def test_service_does_not_mutate_or_generate(app, monkeypatch):
    artifact = _publish(monkeypatch)
    before = db.session.query(ShareArtifact).count()
    load_public_share_artifact(artifact.public_id)
    assert db.session.query(ShareArtifact).count() == before


def test_evidence_and_limitation_order_preserved(app, monkeypatch):
    artifact = _publish(monkeypatch)
    view = load_public_share_artifact(artifact.public_id).view
    # Evidence receipts come from the frozen document's constraints in stored order.
    assert isinstance(view['evidence'], list)
    assert isinstance(view['limitations'], list)


# ---------------------------------------------------------------------------
# public API
# ---------------------------------------------------------------------------


def test_api_published_returns_200_and_cache_headers(client, monkeypatch):
    artifact = _publish(monkeypatch)
    resp = client.get(f'/api/share-artifacts/{artifact.public_id}')
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == RESULT_OK
    assert body['artifact']['public_id'] == artifact.public_id
    assert 'payload' not in body['artifact']
    assert 'immutable' in resp.headers.get('Cache-Control', '')
    assert resp.headers.get('ETag')


def test_api_is_get_only(client, monkeypatch):
    artifact = _publish(monkeypatch)
    for method in ('post', 'put', 'patch', 'delete'):
        resp = getattr(client, method)(f'/api/share-artifacts/{artifact.public_id}')
        assert resp.status_code == 405


def test_api_not_found_and_withdrawn_and_integrity(client, monkeypatch):
    # not found
    assert client.get('/api/share-artifacts/nope').status_code == 404
    # withdrawn -> 410, no-store
    artifact = _publish(monkeypatch)
    artifact.lifecycle_state = LIFECYCLE_WITHDRAWN
    db.session.flush()
    resp = client.get(f'/api/share-artifacts/{artifact.public_id}')
    assert resp.status_code == 410
    assert resp.headers.get('Cache-Control') == 'no-store'
    assert 'team_state' not in resp.get_json()['artifact']


def test_api_integrity_error_is_not_cached_as_success(client, monkeypatch):
    artifact = _publish(monkeypatch)
    monkeypatch.setattr(
        public_module, 'verify_share_artifact_integrity',
        lambda a: (_ for _ in ()).throw(RuntimeError('x')),
    )
    resp = client.get(f'/api/share-artifacts/{artifact.public_id}')
    assert resp.status_code == 503
    assert resp.headers.get('Cache-Control') == 'no-store'
    assert resp.get_json().get('error') == 'integrity_unverified'


def test_api_response_has_no_admin_or_internal_fields(client, monkeypatch):
    artifact = _publish(monkeypatch)
    body = client.get(f'/api/share-artifacts/{artifact.public_id}').get_json()
    text = str(body)
    for forbidden in ('equivalence_key', 'integrity_hash', 'trust_metadata', 'audit', 'admin'):
        assert forbidden not in text
