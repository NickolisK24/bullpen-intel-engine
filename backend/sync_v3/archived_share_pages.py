"""Compare retained historical share pages with the separately archived delivery manifest."""
import argparse
from datetime import date
from hashlib import file_digest, sha256
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.verify_generated_share_previews import _meta
from services.share_artifact_public import is_valid_public_id


def _open_verified(source, digest):
    if file_digest(source, 'sha256').hexdigest() != digest:
        raise ValueError('Archive differs from its expected GitHub digest')
    source.seek(0)
    return ZipFile(source)


def compare_share_pages(pages_path, pages_digest, report_path, report_digest, share_root):
    """Verify archived HTML and the offline delivery tree without accessing application state."""
    prefix = 'frontend/public/share/'
    with Path(pages_path).open('rb') as pages_file, Path(report_path).open('rb') as report_file, \
            _open_verified(pages_file, pages_digest) as pages, _open_verified(report_file, report_digest) as report:
        if len(report.namelist()) != len(set(report.namelist())):
            raise ValueError('Ambiguous delivery report entries')
        export = json.loads(report.read('share-export-result.json'))
        rows = json.loads(report.read('share-generated-digest.json'))
        digests = {row['path']: row['sha256'] for row in rows}
        fallback = 'frontend/public/share-404.html'
        names = pages.namelist()
        declared = export['output']['files']
        paths = {prefix + name for name in names}
        root = Path(share_root)
        local = {prefix + p.relative_to(root).as_posix() for p in root.glob('*/index.html')}
        if (export['status'] != 'ok' or not names or len(names) != len(paths)
                or len(declared) != len(names) or set(declared) != paths or local != paths
                or len(rows) != len(digests) or set(digests) != paths | {fallback}
                or export['artifacts'] != len(names) or export['previews'] != len(names)):
            raise ValueError('Historical share inventory differs')
        if sha256((root.parent / 'share-404.html').read_bytes()).hexdigest() != digests[fallback]:
            raise ValueError('Share fallback differs from its delivery digest')
        types = {}
        dates = []
        for name in names:
            public_id, separator, filename = name.partition('/')
            if not is_valid_public_id(public_id) or public_id in ('.', '..') or not separator or filename != 'index.html':
                raise ValueError('Invalid historical share route')
            page = pages.read(name)
            if sha256(page).hexdigest() != digests[prefix + name] or (root / name).read_bytes() != page:
                raise ValueError(f'Historical share bytes differ for {public_id}')
            meta = _meta(page.decode('utf-8'))
            if meta.get('representation') != 'immutable_share_artifact' or meta.get('public-id') != public_id:
                raise ValueError(f'Historical share identity differs for {public_id}')
            kind = meta['artifact-type']
            types[kind] = types.get(kind, 0) + 1
            dates.append(date.fromisoformat(meta['data-through']))
        if types != export['artifact_type_counts']:
            raise ValueError('Historical share artifact types differ')
        return dict(scope='historical_rendered_pages', pages=len(names), artifact_types=types,
                    earliest_data_through=min(dates).isoformat(), latest_data_through=max(dates).isoformat(),
                    export_snapshot=export['publication_snapshot_id'], export_sync_run=export['publication_sync_run_id'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('pages_path', 'pages_digest', 'report_path', 'report_digest', 'share_root'):
        parser.add_argument(arg)
    print(json.dumps(compare_share_pages(**vars(parser.parse_args())), sort_keys=True))
