"""EO-2 route-specific unfurls for immutable ``/share/{public_id}`` citations."""

from datetime import date
from pathlib import Path

import pytest
from flask import Flask

from services.share_artifact_generation import generate_team_state_artifact
from services.share_artifact_previews import (
    build_share_artifact_preview,
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
    assert {path.relative_to(output_root).parts[0] for path in output_root.rglob('*')} == {'share'}


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
        'handoff_path': f'/share/{public_id}/',
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
        'artifacts': 1,
        'previews': 1,
        'output': output,
    }

    violations, facts = verify_delivery(result, output_root)
    assert violations == []
    assert facts['generated_file_count'] == 1

    page = Path(output['files'][0])
    corrupted = page.read_text(encoding='utf-8').replace(
        'baseballos-card.png', 'wrong-card.png', 1,
    )
    page.write_text(corrupted, encoding='utf-8')
    violations, _ = verify_delivery(result, output_root)
    assert any('governed raster card' in violation for violation in violations)
