"""PI-02 exact-authority tests for immutable Since Yesterday change citations."""

from datetime import date, datetime

import pytest
from flask import Flask

from api.share_cards import share_cards_bp
from models.share_artifact import ShareArtifact
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
    def __init__(self, snapshot_id, data_through, payload):
        self.id = snapshot_id
        self.sync_run_id = None
        self.data_through = data_through
        self.published_at = datetime.combine(data_through, datetime.min.time())
        self.payload = payload
        self.is_published = True


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
    })
    return prior, current


def _publish(app, **kwargs):
    prior, current = _snapshots(**kwargs)
    return publish_since_yesterday_change(
        147,
        current_date='2026-08-24',
        prior_date='2026-08-23',
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
    assert first.evidence[0].snapshot == {
        'label': 'Rested options', 'yesterday': 4, 'today': 0,
    }
    assert first.payload['limitations'] == [
        'Compared only across adjacent trusted publications.'
    ]
    verify_share_artifact_integrity(first)


def test_exact_repository_read_never_substitutes_another_pair(app):
    artifact = _publish(app)
    assert get_published_since_yesterday_change_artifact(
        147,
        current_date='2026-08-24',
        prior_date='2026-08-23',
    ).id == artifact.id
    assert get_published_since_yesterday_change_artifact(
        147,
        current_date='2026-08-24',
        prior_date='2026-08-22',
    ) is None


def test_publication_batch_uses_the_exact_frozen_comparison(app, monkeypatch):
    prior, current = _snapshots()
    monkeypatch.setattr(
        change_artifact_module.dashboard_snapshot_service,
        'get_latest_trusted_dashboard_snapshot_before',
        lambda current_date: prior,
    )

    artifacts = publish_since_yesterday_changes_for_snapshot(current)

    assert [artifact.team_id for artifact in artifacts] == [147]
    assert artifacts[0].source_snapshot_id == current.id
    assert ShareArtifact.query.count() == 1


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


def test_lazy_route_returns_the_canonical_public_citation(app, monkeypatch):
    artifact = _publish(app)
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')
    monkeypatch.setattr(
        'services.share_artifact_repository.get_published_since_yesterday_change_artifact',
        lambda team_id, **kwargs: artifact,
    )

    response = app.test_client().get(
        '/api/share-cards/since-yesterday/147'
        '?current_date=2026-08-24&prior_date=2026-08-23'
    )

    assert response.status_code == 200
    body = response.get_json()
    assert body['available'] is True
    assert body['artifact']['artifact_type'] == ARTIFACT_TYPE
    assert body['artifact']['routes']['share_url'] == f'/share/{artifact.public_id}'


def test_lazy_route_fails_closed_when_exact_artifact_is_unavailable(app, monkeypatch):
    app.register_blueprint(share_cards_bp, url_prefix='/api/share-cards')

    monkeypatch.setattr(
        'services.share_artifact_repository.get_published_since_yesterday_change_artifact',
        lambda *args, **kwargs: None,
    )
    response = app.test_client().get(
        '/api/share-cards/since-yesterday/147'
        '?current_date=2026-08-24&prior_date=2026-08-23'
    )

    assert response.status_code == 200
    assert response.get_json() == {
        'available': False,
        'reason': 'no_published_artifact',
    }


def test_corrected_same_date_artifact_supersedes_original_without_mutating_it(app):
    original = _publish(app)
    original_hash = original.integrity_hash
    prior, corrected = _snapshots()
    corrected.id = 902
    corrected.payload['what_changed_since_yesterday']['items'][0]['public_summary'] = (
        'Corrected published change summary.'
    )
    replacement = publish_since_yesterday_change(
        147,
        current_date='2026-08-24',
        prior_date='2026-08-23',
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


@pytest.mark.parametrize('current_date,prior_date', [
    ('2026-08-24', '2026-08-22'),
    (None, '2026-08-23'),
])
def test_non_adjacent_or_missing_dates_fail_closed(app, current_date, prior_date):
    prior, current = _snapshots()
    with pytest.raises(SinceYesterdayArtifactUnavailable):
        publish_since_yesterday_change(
            147,
            current_date=current_date,
            prior_date=prior_date,
            current_snapshot=current,
            prior_snapshot=prior,
        )
    assert ShareArtifact.query.count() == 0
