"""PI-02 exact-authority tests for immutable Since Yesterday change citations."""

from datetime import date, datetime

import pytest
from flask import Flask

from api.share_cards import share_cards_bp
from models.share_artifact import ShareArtifact
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services.share_artifact_public import RESULT_OK, project_public_share_artifact
from services.share_artifact_repository import (
    get_published_since_yesterday_change_artifact,
)
from services import share_artifact_batch_generation as batch_module
from services import share_artifact_publication_hook as hook_module
from services import share_artifact_since_yesterday as change_artifact_module
from services.share_artifacts import verify_share_artifact_integrity
from services.share_artifact_since_yesterday import (
    ARTIFACT_TYPE,
    RENDER_VERSION,
    SinceYesterdayArtifactUnavailable,
    publish_since_yesterday_change,
    publish_since_yesterday_changes_for_snapshot,
)
from services.what_changed_comparison_identity import build_comparison_identity
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
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


class Snapshot:
    def __init__(self, snapshot_id, data_through, payload, *, current=False):
        self.id = snapshot_id
        self.sync_run_id = snapshot_id + 1000
        self.data_through = data_through
        self.published_at = datetime.combine(data_through, datetime.min.time())
        self.payload = payload
        self.is_published = current
        self.status = 'ready'
        self.snapshot_type = 'bullpen_dashboard'
        self.payload_version = 1


def _snapshots(*, missing_delta=False):
    prior = Snapshot(900, date(2026, 8, 23), {})
    item = {
        'team_id': 147,
        'team_name': 'New York Yankees',
        'team_abbreviation': 'NYY',
        'movement_lane': 'tighter_today',
        'movement_label': 'Tighter today',
        'primary_delta': None if missing_delta else {
            'label': 'Rested options', 'previous': 4, 'current': 0, 'net_delta': -4,
        },
        'public_headline': 'New York has less bullpen room than yesterday.',
        'public_summary': 'New York has fewer rested options than yesterday.',
        'public_context': 'That leaves fewer ways through a close game.',
        'yesterday_rested_count': 4,
        'today_rested_count': 0,
        'workload_added': [],
        'public_evidence': [{
            'label': 'Rested options', 'yesterday': 4, 'today': 0,
        }, {
            'label': 'Arm Read movement',
            'yesterday': 'Watch Arm',
            'today': 'Limited Rest',
        }],
    }
    current = Snapshot(901, date(2026, 8, 24), {
        'what_changed_since_yesterday': {
            'state': 'changes_detected',
            'comparison': {
                'comparison_available': True,
                'previous_data_through': '2026-08-23',
                'current_data_through': '2026-08-24',
            },
            'items': [item],
            'limitations': ['Compared only across adjacent trusted publications.'],
        },
    }, current=True)
    current.payload['what_changed_since_yesterday']['comparison']['identity'] = (
        build_comparison_identity(current, prior)
    )
    return prior, current


def _persist_snapshot_sync_runs(*snapshots):
    """Honor the production FK when unit-like snapshot doubles are persisted."""
    for snapshot in snapshots:
        if db.session.get(SyncRun, snapshot.sync_run_id) is None:
            db.session.add(SyncRun(
                id=snapshot.sync_run_id,
                job_name='f019-share-fixture',
                status='success',
                stage='completed',
                source='test',
            ))
    db.session.flush()


def _publish(app, **kwargs):
    prior, current = _snapshots(**kwargs)
    _persist_snapshot_sync_runs(prior, current)
    return publish_since_yesterday_change(
        147,
        comparison_identity=build_comparison_identity(current, prior),
        current_snapshot=current,
        prior_snapshot=prior,
    )


def test_exact_pair_is_frozen_and_idempotent(app):
    first = _publish(app)
    second = _publish(app)
    assert first.id == second.id
    assert ShareArtifact.query.count() == 1
    assert first.artifact_type == ARTIFACT_TYPE
    assert first.render_version == RENDER_VERSION
    assert first.subject_key == 'team:147:prior:900:current:901'
    assert first.payload['authority']['prior_snapshot_id'] == 900
    assert first.payload['authority']['current_snapshot_id'] == 901
    assert first.payload['authority']['comparison_identity'] == (
        _snapshots()[1].payload['what_changed_since_yesterday']['comparison']['identity']
    )
    assert first.evidence[0].snapshot == {
        'label': 'Rested options', 'yesterday': 4, 'today': 0,
    }
    assert first.evidence[1].snapshot == {
        'label': 'Arm Read movement',
        'yesterday': 'Watch Arm',
        'today': 'Limited Rest',
    }
    assert not {'Available', 'Monitor', 'Avoid', 'Limited'} & {
        first.evidence[1].snapshot['yesterday'],
        first.evidence[1].snapshot['today'],
    }
    assert first.payload['limitations'] == [
        'Compared only across adjacent trusted publications.'
    ]
    verify_share_artifact_integrity(first)


def test_exact_repository_read_never_substitutes_another_pair(app):
    artifact = _publish(app)
    assert get_published_since_yesterday_change_artifact(
        147,
        comparison_identity=artifact.payload['authority']['comparison_identity'],
    ).id == artifact.id
    mismatched = dict(artifact.payload['authority']['comparison_identity'])
    mismatched['previous_snapshot_id'] = 899
    assert get_published_since_yesterday_change_artifact(
        147,
        comparison_identity=mismatched,
    ) is None


def test_publication_batch_uses_the_exact_frozen_comparison(app, monkeypatch):
    prior, current = _snapshots()
    _persist_snapshot_sync_runs(prior, current)
    identity = build_comparison_identity(current, prior)
    monkeypatch.setattr(
        change_artifact_module,
        'resolve_snapshot_pair',
        lambda requested, **kwargs: (prior, current, identity),
    )

    artifacts = publish_since_yesterday_changes_for_snapshot(current)

    assert [artifact.team_id for artifact in artifacts] == [147]
    assert artifacts[0].source_snapshot_id == current.id
    assert ShareArtifact.query.count() == 1


def test_publication_path_contains_no_independent_latest_date_reselection():
    from pathlib import Path

    source = Path(change_artifact_module.__file__).read_text(encoding='utf-8')
    assert 'get_latest_trusted_dashboard_snapshot_before' not in source
    assert 'get_latest_valid_dashboard_snapshot' not in source


def test_database_resolution_uses_exact_rendered_snapshot_ids(app):
    prior_fixture, current_fixture = _snapshots()
    prior_run = SyncRun(job_name='f019-prior')
    current_run = SyncRun(job_name='f019-current')
    db.session.add_all([prior_run, current_run])
    db.session.flush()
    prior = DashboardSnapshot(
        snapshot_type='bullpen_dashboard', sync_run_id=prior_run.id,
        status='ready', is_published=False,
        published_at=prior_fixture.published_at, payload={}, payload_version=1,
        data_through=prior_fixture.data_through,
        snapshot_generated_at=prior_fixture.published_at, source='test',
    )
    current = DashboardSnapshot(
        snapshot_type='bullpen_dashboard', sync_run_id=current_run.id,
        status='ready', is_published=True,
        published_at=current_fixture.published_at,
        payload=current_fixture.payload, payload_version=1,
        data_through=current_fixture.data_through,
        snapshot_generated_at=current_fixture.published_at, source='test',
    )
    db.session.add_all([prior, current])
    db.session.flush()
    identity = build_comparison_identity(current, prior)
    payload = dict(current.payload)
    payload['what_changed_since_yesterday'] = dict(
        payload['what_changed_since_yesterday']
    )
    payload['what_changed_since_yesterday']['comparison'] = dict(
        payload['what_changed_since_yesterday']['comparison'],
        identity=identity,
    )
    current.payload = payload
    db.session.commit()

    artifact = publish_since_yesterday_change(
        147,
        comparison_identity=identity,
    )

    assert artifact.source_snapshot_id == current.id
    assert artifact.subject_key == (
        f'team:147:prior:{prior.id}:current:{current.id}'
    )
    assert artifact.payload['authority']['comparison_identity'] == identity


def test_post_publication_hook_invokes_change_generation_once(app, monkeypatch):
    prior, current = _snapshots()
    calls = []

    class BatchResult:
        attempted_count = generated_count = reused_count = 0
        refused_count = failed_count = missing_count = 0

    monkeypatch.setattr(
        batch_module,
        'generate_team_state_artifacts_batch',
        lambda **kwargs: BatchResult(),
    )
    monkeypatch.setattr(
        change_artifact_module,
        'publish_since_yesterday_changes_for_snapshot',
        lambda snapshot: calls.append(snapshot) or [],
    )

    assert hook_module.run_post_publication_generation(current) is not None
    assert calls == [current]


def test_public_projection_preserves_exact_zero_and_omits_internal_ids(app):
    artifact = _publish(app)
    result = project_public_share_artifact(artifact)
    assert result.status == RESULT_OK
    view = result.view
    assert view['change']['today_rested_count'] == 0
    assert view['change']['primary_delta']['current'] == 0
    assert view['evidence'][0]['today'] == 0
    assert view['freshness'] == {
        'previous_data_through': '2026-08-23',
        'current_data_through': '2026-08-24',
        'published_at': artifact.published_at.isoformat(),
    }
    assert view['routes']['share_url'] == f'/share/{artifact.public_id}'
    assert view['routes']['team_url'].startswith('/bullpen?view=board&team=NYY')
    assert 'current_snapshot_id' not in view['authority']
    assert 'prior_snapshot_id' not in view['authority']


def test_missing_delta_remains_missing_not_zero(app):
    artifact = _publish(app, missing_delta=True)
    view = project_public_share_artifact(artifact).view
    assert view['change']['primary_delta'] is None


def test_artifact_freezes_the_same_governed_arm_read_evidence(app):
    artifact = _publish(app)
    rendered = _snapshots()[1].payload['what_changed_since_yesterday']['items'][0]
    assert artifact.payload['evidence'] == rendered['public_evidence']
    assert artifact.payload['evidence'][1] == {
        'label': 'Arm Read movement',
        'yesterday': 'Watch Arm',
        'today': 'Limited Rest',
    }


def test_missing_rendered_identity_withholds_generation(app):
    _, current = _snapshots()
    current.payload['what_changed_since_yesterday']['comparison'].pop('identity')
    assert publish_since_yesterday_changes_for_snapshot(current) == []
    assert ShareArtifact.query.count() == 0


def test_team_not_present_in_rendered_comparison_fails_closed(app):
    prior, current = _snapshots()
    with pytest.raises(SinceYesterdayArtifactUnavailable) as exc:
        publish_since_yesterday_change(
            999,
            comparison_identity=build_comparison_identity(current, prior),
            current_snapshot=current,
            prior_snapshot=prior,
        )
    assert str(exc.value) == 'team_change_unavailable'


@pytest.mark.parametrize('mutation', ['unpublished', 'payload_version', 'team_type'])
def test_untrusted_or_incompatible_publication_pair_fails_closed(app, mutation):
    prior, current = _snapshots()
    identity = build_comparison_identity(current, prior)
    if mutation == 'unpublished':
        current.is_published = False
    elif mutation == 'payload_version':
        prior.payload_version = 2
    else:
        prior.snapshot_type = 'other'
    with pytest.raises(SinceYesterdayArtifactUnavailable):
        publish_since_yesterday_change(
            147,
            comparison_identity=identity,
            current_snapshot=current,
            prior_snapshot=prior,
        )


def test_lazy_route_returns_the_canonical_public_citation(app, monkeypatch):
    artifact = _publish(app)
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')
    monkeypatch.setattr(
        'services.share_artifact_repository.get_published_since_yesterday_change_artifact',
        lambda team_id, **kwargs: artifact,
    )

    response = app.test_client().get(
        '/api/share-cards/since-yesterday/147'
        '?' + _identity_query(artifact.payload['authority']['comparison_identity'])
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body['available'] is True
    assert body['artifact']['artifact_type'] == ARTIFACT_TYPE
    assert body['artifact']['routes']['share_url'] == f'/share/{artifact.public_id}'


def test_rendered_comparison_identity_resolves_the_same_citation(app):
    """The share read must accept the identity the rendered comparison owns.

    Before F-019 this exact request was rejected as ``comparison_dates_invalid``
    because the route understood only its separate current_date/prior_date
    convention, even though the artifact already carried snapshots 900 -> 901.
    """
    artifact = _publish(app)
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')

    response = app.test_client().get(
        '/api/share-cards/since-yesterday/147'
        '?comparison_contract=what_changed_comparison_identity_v1'
        '&comparison_authority=what_changed_since_yesterday_public_v1'
        '&comparison_method_version=2026-06-19.v1'
        '&previous_snapshot_id=900&current_snapshot_id=901'
        '&previous_sync_run_id=1900&current_sync_run_id=1901'
        '&previous_payload_version=1&current_payload_version=1'
        '&previous_data_through=2026-08-23&current_data_through=2026-08-24'
        '&previous_publication_state=trusted_published'
        '&current_publication_state=current_published'
    )

    assert response.status_code == 200
    assert response.get_json()['available'] is True


def test_lazy_route_fails_closed_when_exact_artifact_is_unavailable(app, monkeypatch):
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')

    monkeypatch.setattr(
        'services.share_artifact_repository.get_published_since_yesterday_change_artifact',
        lambda *args, **kwargs: None,
    )
    response = app.test_client().get(
        '/api/share-cards/since-yesterday/147'
        '?' + _identity_query(build_comparison_identity(*reversed(_snapshots())))
    )

    assert response.status_code == 200
    assert response.get_json() == {
        'available': False,
        'reason': 'no_published_artifact',
    }


def test_date_only_share_request_cannot_reselect_a_comparison(app):
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')
    response = app.test_client().get(
        '/api/share-cards/since-yesterday/147'
        '?current_date=2026-08-24&prior_date=2026-08-23'
    )
    assert response.status_code == 200
    assert response.get_json() == {
        'available': False,
        'reason': 'comparison_identity_invalid',
    }


def test_corrected_same_date_artifact_supersedes_original_without_mutating_it(app):
    original = _publish(app)
    original_hash = original.integrity_hash
    prior, corrected = _snapshots()
    corrected.id = 902
    corrected.sync_run_id = 1902
    _persist_snapshot_sync_runs(corrected)
    corrected.payload['what_changed_since_yesterday']['comparison']['identity'] = (
        build_comparison_identity(corrected, prior)
    )
    corrected.payload['what_changed_since_yesterday']['items'][0]['public_summary'] = (
        'Corrected published change summary.'
    )
    replacement = publish_since_yesterday_change(
        147,
        comparison_identity=build_comparison_identity(corrected, prior),
        current_snapshot=corrected,
        prior_snapshot=prior,
    )
    db.session.refresh(original)
    assert replacement.id != original.id
    assert original.lifecycle_state == 'superseded'
    assert original.integrity_hash == original_hash
    projected = project_public_share_artifact(original)
    assert projected.status == 'superseded'
    assert projected.view['superseded']['replacement_public_id'] == replacement.public_id


@pytest.mark.parametrize('field,value', [
    ('previous_data_through', '2026-08-22'),
    ('previous_snapshot_id', None),
    ('method_version', 'incompatible'),
    ('current_snapshot_id', 900),
])
def test_forged_or_incompatible_identity_fails_closed(app, field, value):
    prior, current = _snapshots()
    identity = build_comparison_identity(current, prior)
    identity[field] = value
    with pytest.raises(SinceYesterdayArtifactUnavailable):
        publish_since_yesterday_change(
            147,
            comparison_identity=identity,
            current_snapshot=current,
            prior_snapshot=prior,
        )
    assert ShareArtifact.query.count() == 0


def _identity_query(identity):
    from urllib.parse import urlencode

    return urlencode({
        'comparison_contract': identity['contract'],
        'comparison_authority': identity['comparison_authority'],
        'comparison_method_version': identity['method_version'],
        **{key: value for key, value in identity.items() if key not in {
            'contract', 'comparison_authority', 'method_version',
        }},
    })
