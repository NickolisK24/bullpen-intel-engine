from hashlib import sha256
import json
from zipfile import ZipFile

import pytest

from sync_v3.archived_share_pages import compare_share_pages


def test_frozen_pages_require_matching_archive_manifest_and_delivery_tree(tmp_path):
    root = tmp_path / 'share'
    route = root / 'abc' / 'index.html'
    route.parent.mkdir(parents=True)
    meta = {'representation': 'immutable_share_artifact', 'public-id': 'abc', 'artifact-type': 'team_state',
            'data-through': '2026-08-17'}
    body = '\n'.join(f'<meta name="baseballos:{k}" content="{v}" />' for k, v in meta.items()).encode()
    route.write_bytes(body)
    fallback = tmp_path / 'share-404.html'
    fallback.write_bytes(b'fallback')
    pages = tmp_path / 'pages.zip'
    report = tmp_path / 'report.zip'
    with ZipFile(pages, 'w') as z:
        z.writestr('abc/index.html', body)
    files = ['frontend/public/share/abc/index.html']
    rows = [dict(path=files[0], sha256=sha256(body).hexdigest()),
            dict(path='frontend/public/share-404.html', sha256=sha256(fallback.read_bytes()).hexdigest())]
    with ZipFile(report, 'w') as z:
        z.writestr('share-generated-digest.json', json.dumps(rows))
        z.writestr('share-export-result.json', json.dumps(dict(status='ok', output=dict(files=files),
                   artifacts=1, previews=1, artifact_type_counts={'team_state': 1},
                   publication_snapshot_id=42, publication_sync_run_id=24)))
    args = (pages, sha256(pages.read_bytes()).hexdigest(), report, sha256(report.read_bytes()).hexdigest(), root)
    assert compare_share_pages(*args)['export_snapshot'] == 42
    with pytest.raises(ValueError, match='GitHub digest'):
        compare_share_pages(pages, '0' * 64, *args[2:])
    route.write_bytes(body + b' ')
    with pytest.raises(ValueError, match='bytes differ'):
        compare_share_pages(*args)
    route.unlink()
    with pytest.raises(ValueError, match='inventory differs'):
        compare_share_pages(*args)
