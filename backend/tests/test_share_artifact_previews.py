"""EO-2 route-specific unfurls for immutable ``/share/{public_id}`` citations."""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from services.share_artifact_generation import generate_team_state_artifact
from services.share_artifact_previews import (
    build_share_artifact_preview,
    build_share_artifact_preview_from_public_view,
    render_invalid_share_html,
    render_share_artifact_html,
    write_share_artifact_pages,
)
from scripts.verify_generated_share_previews import verify as verify_delivery
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.test_share_artifact_generation import (
    TEAM_ID,
    _eligible_env,
    _install_trusted_snapshot,
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


def _published(monkeypatch, *, status_code='operationally_constrained'):
    _eligible_env(monkeypatch, with_sync_run=True)
    result = generate_team_state_artifact(
        TEAM_ID,
        readiness_resolver=_resolver(_readiness(status_code=status_code)),
    )
    assert result.artifact is not None
    return result.artifact


def test_valid_artifact_metadata_comes_from_frozen_public_projection(app, monkeypatch):
    artifact = _published(monkeypatch)
    preview = build_share_artifact_preview(artifact)
    page = render_share_artifact_html(preview)

    assert preview['title'] == 'Test Club bullpen — Stretched'
    assert "Test Club's bullpen is Stretched" in preview['description']
    assert 'data through July 20, 2026' in preview['description']
    assert preview['canonical_url'] == f'https://baseballos.app/share/{artifact.public_id}'
    assert preview['public_id'] == artifact.public_id
    assert preview['data_through'] == '2026-07-20'
    assert preview['snapshot_id'] == artifact.source_snapshot_id
    assert preview['sync_run_id'] == artifact.source_sync_run_id
    assert '<meta property="og:image" content="https://baseballos.app/og/baseballos-card.png" />' in page
    assert '<meta name="twitter:card" content="summary_large_image" />' in page
    assert '<meta property="og:image:width" content="1200" />' in page
    assert '<meta property="og:image:height" content="630" />' in page
    assert '<meta property="og:image:type" content="image/png" />' in page
    assert f'<meta name="baseballos:public-id" content="{artifact.public_id}" />' in page
    assert '<meta name="baseballos:data-through" content="2026-07-20" />' in page


def test_static_share_handoff_is_meaningful_and_never_targets_itself(app, monkeypatch):
    artifact = _published(monkeypatch)
    frozen_payload = artifact.payload.copy()
    frozen_integrity_hash = artifact.integrity_hash

    preview = build_share_artifact_preview(artifact)
    page = render_share_artifact_html(preview)

    assert preview['canonical_url'] == f'https://baseballos.app/share/{artifact.public_id}'
    assert preview['live_destination_path'] == '/bullpen?view=board&team=TST&source=share'
    assert 'window.location' not in page
    assert f'/share/{artifact.public_id}/' not in page
    assert 'Test Club' in page
    assert 'Stretched' in page
    assert '2026-07-20' in page
    assert 'Evidence behind the read' in page
    assert 'href="/bullpen?view=board&amp;team=TST&amp;source=share"' in page
    assert artifact.payload == frozen_payload
    assert artifact.integrity_hash == frozen_integrity_hash


def test_static_projection_preserves_named_governed_evidence_without_team_state():
    view = {
        'public_id': 'change-abc123',
        'artifact_type': 'since_yesterday_change',
        'schema_version': '1.0.0',
        'render_version': 'since-yesterday-1.0.0',
        'payload_version': 'since-yesterday-1.0.0',
        'lifecycle_state': 'published',
        'product_date': '2026-07-21',
        'team': {
            'team_name': 'Test Club',
            'team_abbreviation': 'TST',
        },
        'freshness': {
            'previous_data_through': '2026-07-20',
            'current_data_through': '2026-07-21',
        },
        'copy': {
            'headline': 'Test Club bullpen changed since yesterday',
            'description': 'The published bullpen read changed after the latest completed game.',
        },
        'evidence': [{
            'label': 'Named arm',
            'detail': 'Jordan Example moved from Watch Arm to Limited Rest.',
        }],
        'routes': {
            'share_url': '/share/change-abc123',
            'team_url': '/bullpen?view=board&team=TST&source=share',
        },
    }

    preview = build_share_artifact_preview_from_public_view(view)
    page = render_share_artifact_html(preview)

    assert preview['canonical_url'] == 'https://baseballos.app/share/change-abc123'
    assert 'Test Club bullpen changed since yesterday' in page
    assert '2026-07-21' in page
    assert 'Jordan Example moved from Watch Arm to Limited Rest.' in page
    assert 'window.location' not in page


def test_older_preview_does_not_change_when_a_new_team_state_is_published(app, monkeypatch):
    original = _published(monkeypatch, status_code='operationally_constrained')
    original_preview = build_share_artifact_preview(original)

    _install_trusted_snapshot(
        monkeypatch,
        snapshot_id=5002,
        data_through=date(2026, 7, 21),
    )
    current_readiness = _readiness(status_code='operationally_stable')
    current_readiness['freshness']['data_through'] = '2026-07-21'
    newer = generate_team_state_artifact(
        TEAM_ID,
        readiness_resolver=_resolver(current_readiness),
    ).artifact
    assert newer is not None
    assert build_share_artifact_preview(newer)['title'] == 'Test Club bullpen — Fresh'

    frozen_again = build_share_artifact_preview(original)
    assert frozen_again == original_preview
    assert frozen_again['title'] == 'Test Club bullpen — Stretched'
    assert frozen_again['data_through'] == '2026-07-20'


def test_invalid_share_fallback_has_no_claim_identity():
    page = render_invalid_share_html()
    assert '<meta name="robots" content="noindex,nofollow" />' in page
    assert '<meta name="baseballos:representation" content="invalid_share_artifact" />' in page
    assert 'baseballos:public-id' not in page
    assert 'baseballos:team-state' not in page
    assert 'baseballos:data-through' not in page
    assert 'Test Club' not in page
    assert 'Fresh' not in page
    assert 'Stretched' not in page
    assert 'Vulnerable' not in page
    assert 'window.location' not in page
    assert 'rel="canonical"' not in page
    assert 'property="og:url"' not in page


def test_writer_is_deterministic_and_confined_to_share_root(app, monkeypatch, tmp_path):
    artifact = _published(monkeypatch)
    preview = build_share_artifact_preview(artifact)
    output_root = tmp_path / 'public'

    first = write_share_artifact_pages([preview], output_root)
    second = write_share_artifact_pages([preview], output_root)
    expected = output_root / 'share' / artifact.public_id / 'index.html'

    assert first['files'] == [str(expected)]
    assert expected.is_file()
    assert second['changed'] == []
    assert {path.relative_to(output_root).parts[0] for path in output_root.rglob('*')} == {
        '404.html', 'share',
    }
    assert first['fallback'] == str(output_root / '404.html')


@pytest.mark.parametrize('public_id', ['.', '..', '../escape', 'bad/id'])
def test_writer_rejects_paths_outside_generated_share_directory(tmp_path, public_id):
    preview = {
        'public_id': public_id,
        'title': 'Frozen title',
        'description': 'Frozen description',
        'canonical_url': f'https://baseballos.app/share/{public_id}',
        'og_image': 'https://baseballos.app/og/baseballos-card.png',
        'twitter_card': 'summary_large_image',
        'representation': 'immutable_share_artifact',
        'live_destination_path': '/bullpen',
        'evidence': [],
    }
    with pytest.raises(ValueError):
        write_share_artifact_pages([preview], tmp_path / 'public')
    assert not (tmp_path / 'escape').exists()


def test_writer_removes_only_stale_generator_shaped_pages(app, monkeypatch, tmp_path):
    artifact = _published(monkeypatch)
    preview = build_share_artifact_preview(artifact)
    share_root = tmp_path / 'public' / 'share'
    stale = share_root / 'old-public-id'
    stale.mkdir(parents=True)
    (stale / 'index.html').write_text('old frozen page', encoding='utf-8')

    output = write_share_artifact_pages([preview], tmp_path / 'public')
    assert not stale.exists()
    assert output['removed'] == [str(stale / 'index.html')]

    foreign = share_root / 'foreign'
    foreign.mkdir()
    (foreign / 'asset.txt').write_text('do not remove', encoding='utf-8')
    with pytest.raises(ValueError, match='non-generator'):
        write_share_artifact_pages([preview], tmp_path / 'public')
    assert (foreign / 'asset.txt').is_file()


def test_delivery_gate_proves_exact_generated_set_and_detects_corruption(app, monkeypatch, tmp_path):
    artifact = _published(monkeypatch)
    preview = build_share_artifact_preview(artifact)
    output_root = tmp_path / 'public'
    output = write_share_artifact_pages([preview], output_root)
    result = {
        'status': 'ok',
        'publication_snapshot_id': 1753,
        'artifacts': 1,
        'previews': 1,
        'output': output,
    }

    routing_config = Path(__file__).resolve().parents[2] / 'frontend' / 'vercel.json'
    violations, facts = verify_delivery(result, output_root, routing_config)
    assert violations == []
    assert facts['generated_file_count'] == 1

    page = Path(output['files'][0])
    corrupted = page.read_text(encoding='utf-8').replace(
        'baseballos-card.png', 'wrong-card.png', 1,
    )
    page.write_text(corrupted, encoding='utf-8')
    violations, _ = verify_delivery(result, output_root, routing_config)
    assert any('governed raster card' in violation for violation in violations)
