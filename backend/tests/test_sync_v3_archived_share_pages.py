from hashlib import sha256
import json
from zipfile import ZipFile

import pytest

from sync_v3.archived_share_pages import compare_share_pages
from tests.test_share_artifact_previews import app


def test_frozen_pages_require_matching_archive_manifest_and_delivery_tree(app, monkeypatch, tmp_path):
    from services.share_artifact_previews import build_share_artifact_preview, write_share_artifact_pages
    from tests.test_share_artifact_previews import _published

    artifact = _published(monkeypatch)
    preview = build_share_artifact_preview(artifact)
    write_share_artifact_pages([preview], tmp_path / 'public')
    route = tmp_path / 'public' / 'share' / artifact.public_id / 'index.html'
    body = route.read_bytes()
    args = archive(tmp_path, route, 'team_state')
    assert compare_share_pages(*args)['export_snapshot'] == 42
    with pytest.raises(ValueError, match='GitHub digest'):
        compare_share_pages(args[0], '0' * 64, *args[2:])
    route.write_bytes(body + b' ')
    with pytest.raises(ValueError, match='bytes differ'):
        compare_share_pages(*args)
    route.unlink()
    with pytest.raises(ValueError, match='inventory differs'):
        compare_share_pages(*args)


def archive(tmp_path, route, kind, *, export_snapshot=42, run=24, through=None, publication=None):
    root = route.parents[1]
    name = route.relative_to(root).as_posix()
    body = route.read_bytes()
    fallback = root.parent / 'share-404.html'
    pages = tmp_path / 'pages.zip'
    report = tmp_path / 'report.zip'
    with ZipFile(pages, 'w') as z:
        z.writestr(name, body)
    files = [f'frontend/public/share/{name}']
    rows = [dict(path=files[0], sha256=sha256(body).hexdigest()),
            dict(path='frontend/public/share-404.html', sha256=sha256(fallback.read_bytes()).hexdigest())]
    with ZipFile(report, 'w') as z:
        if publication is not None:
            z.writestr('publication.json', json.dumps(publication))
        z.writestr('share-generated-digest.json', json.dumps(rows))
        z.writestr('share-export-result.json', json.dumps(dict(status='ok', output=dict(files=files, count=1, fallback='frontend/public/share-404.html'),
                   artifacts=1, previews=1, artifact_type_counts={kind: 1},
                   publication_snapshot_id=export_snapshot, publication_sync_run_id=run, publication_data_through=through)))
    return pages, sha256(pages.read_bytes()).hexdigest(), report, sha256(report.read_bytes()).hexdigest(), root


def test_matching_bytes_require_public_delivery_identity(app, monkeypatch, tmp_path):
    from services.share_artifact_previews import build_share_artifact_preview, write_share_artifact_pages
    from tests.test_share_artifact_previews import _published

    artifact = _published(monkeypatch)
    write_share_artifact_pages([build_share_artifact_preview(artifact)], tmp_path / 'public')
    route = tmp_path / 'public' / 'share' / artifact.public_id / 'index.html'
    # A historical candidate digest identifies a rehearsal, even if both archives and the delivery tree agree.
    for identity in (None, 'b' * 64, 0, True):
        with pytest.raises(ValueError, match='no authorizing publication snapshot'):
            compare_share_pages(*archive(tmp_path, route, 'team_state', export_snapshot=identity))
    body = route.read_text()
    wrong = body.replace(f'https://baseballos.app/share/{artifact.public_id}', 'https://baseballos.app/share/another')
    assert wrong != body
    route.write_text(wrong)
    with pytest.raises(ValueError, match='does not match its public_id'):
        compare_share_pages(*archive(tmp_path, route, 'team_state'))
    route.write_text(body)
    fallback = tmp_path / 'public' / 'share-404.html'
    fallback.write_text(body)
    with pytest.raises(ValueError, match='fallback'):
        compare_share_pages(*archive(tmp_path, route, 'team_state'))


@pytest.mark.parametrize('kind', ['team_state', 'since_yesterday_change'])
def test_reproduce_frozen_share_from_stored_record(app, monkeypatch, tmp_path, kind):
    from services.share_artifact_previews import build_share_artifact_preview, write_share_artifact_pages
    from services.share_artifact_repository import get_share_artifact_by_public_id
    from tests.test_share_artifact_previews import _published
    from tests.test_since_yesterday_share_artifact import _publish
    from utils.db import db

    original = _published(monkeypatch) if kind == 'team_state' else _publish(app)
    public_id = original.public_id
    preview = build_share_artifact_preview(original)
    output = write_share_artifact_pages([preview], tmp_path / 'public')
    route = tmp_path / 'public' / 'share' / public_id / 'index.html'
    assert output['count'] == 1
    args = archive(tmp_path, route, kind)
    db.session.expunge_all()
    retained = get_share_artifact_by_public_id(public_id)
    assert retained is not original
    result = compare_share_pages(*args, stored_artifacts=[retained])
    assert result['stored_records_compared'] == result['pages_with_source_pair'] == 1
    assert result['pages_without_record_comparison'] == 0
    assert compare_share_pages(*args)['pages_without_record_comparison'] == 1
    with pytest.raises(ValueError, match='Unexpected stored share identity'):
        compare_share_pages(*args, stored_artifacts=[retained, retained])

    # Both delivery copies and the manifest agree on bytes that the original record cannot reproduce.
    route.write_bytes(route.read_bytes() + b' ')
    changed = archive(tmp_path, route, kind)
    assert compare_share_pages(*changed)['stored_records_compared'] == 0
    with pytest.raises(ValueError, match='does not reproduce'):
        compare_share_pages(*changed, stored_artifacts=[retained])

    with monkeypatch.context() as patch:
        patch.setattr(retained, 'integrity_hash', '0' * 64)
        with db.session.no_autoflush, pytest.raises(ValueError, match='not safely previewable'):
            compare_share_pages(*changed, stored_artifacts=[retained])


def test_share_export_must_agree_with_delivery_and_observed_publication(app, monkeypatch, tmp_path):
    from services.share_artifact_previews import build_share_artifact_preview, write_share_artifact_pages
    from tests.test_share_artifact_previews import _published
    from tests.test_sync_v3_observed_identities import write_proof

    artifact = _published(monkeypatch)
    write_share_artifact_pages([build_share_artifact_preview(artifact)], tmp_path / 'public')
    route = tmp_path / 'public' / 'share' / artifact.public_id / 'index.html'
    proof = tmp_path / 'proof.zip'
    reference = (proof, write_proof(proof))
    through = '2026-10-28'
    publication = dict(publication_snapshot_id=12, sync_run_id=15, data_through=through, status='ok')

    def inputs(record, run=15):
        return archive(tmp_path, route, 'team_state', export_snapshot=12, run=run, through=through, publication=record)

    result = compare_share_pages(*inputs(publication), publication_proof=reference)
    assert result['delivery_publication_compared'] and result['observed_publication']['snapshot_id'] == 12
    assert result['stored_records_compared'] == 0
    for record in (None, dict(publication, status='failed'), dict(publication, publication_snapshot_id=13),
                   dict(publication, data_through='2026-10-27'), dict(publication, sync_run_id=16)):
        with pytest.raises(ValueError, match='delivery publication'):
            compare_share_pages(*inputs(record), publication_proof=reference)
    with pytest.raises(ValueError, match='differs from the observed publication'):
        compare_share_pages(*inputs(dict(publication, sync_run_id=16), run=16), publication_proof=reference)
