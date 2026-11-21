"""Compare retained historical share pages with the separately archived delivery manifest."""
import argparse
from datetime import date
from hashlib import file_digest, sha256
import json
from pathlib import Path
from zipfile import ZipFile

from scripts.verify_generated_share_previews import _meta, verify as verify_delivery
from services.share_artifact_public import is_valid_public_id
from services.share_artifact_previews import build_share_artifact_preview, render_share_artifact_html


def _open_verified(source, digest):
    if file_digest(source, 'sha256').hexdigest() != digest:
        raise ValueError('Archive differs from its expected GitHub digest')
    source.seek(0)
    return ZipFile(source)


def compare_share_pages(pages_path, pages_digest, report_path, report_digest, share_root, *, stored_artifacts=()):
    """Compare delivery bytes and, when supplied, reproduce pages from isolated historical artifact records."""
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
        if (export['status'] != 'ok' or export['output'].get('fallback') != fallback or not names or len(names) != len(paths)
                or len(declared) != len(names) or set(declared) != paths or local != paths
                or len(rows) != len(digests) or set(digests) != paths | {fallback}
                or export['artifacts'] != len(names) or export['previews'] != len(names)):
            raise ValueError('Historical share inventory differs')
        if sha256((root.parent / 'share-404.html').read_bytes()).hexdigest() != digests[fallback]:
            raise ValueError('Share fallback differs from its delivery digest')
        snapshot = export.get('publication_snapshot_id')
        if type(snapshot) is not int or snapshot < 1:
            raise ValueError('Historical share export has no authorizing publication snapshot ID')
        types = {}
        dates = []
        source_pairs = set()
        pages_with_source_pair = 0
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
            if meta.get('snapshot-id') and meta.get('sync-run-id'):
                source_pairs.add((meta['snapshot-id'], meta['sync-run-id']))
                pages_with_source_pair += 1
            kind = meta['artifact-type']
            types[kind] = types.get(kind, 0) + 1
            dates.append(date.fromisoformat(meta['data-through']))
        if types != export['artifact_type_counts']:
            raise ValueError('Historical share artifact types differ')
        # The report names paths in the exporting checkout. Use only the enumerated,
        # validated local files when repeating its public delivery checks.
        output = dict(export['output'], files=[str(root / name) for name in names],
                      fallback=str(root.parent / 'share-404.html'))
        violations, _ = verify_delivery(dict(export, output=output), root.parent)
        if violations:
            raise ValueError(f'Historical share delivery failed verification: {violations[0]}')
        compared = set()
        for artifact in stored_artifacts:
            public_id = artifact.public_id
            path = f'{prefix}{public_id}/index.html'
            if public_id in compared or path not in paths:
                raise ValueError(f'Unexpected stored share identity: {public_id}')
            preview = build_share_artifact_preview(artifact)
            rendered = render_share_artifact_html(preview).encode('utf-8')
            if sha256(rendered).hexdigest() != digests[path]:
                raise ValueError(f'Stored share record does not reproduce {public_id}')
            compared.add(public_id)
        return dict(scope='historical_rendered_pages', stored_records_compared=len(compared),
                    pages_without_record_comparison=len(names) - len(compared), distinct_source_pairs=len(source_pairs),
                    pages_with_source_pair=pages_with_source_pair, pages=len(names), artifact_types=types,
                    earliest_data_through=min(dates).isoformat(), latest_data_through=max(dates).isoformat(),
                    export_snapshot=export['publication_snapshot_id'], export_sync_run=export['publication_sync_run_id'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ('pages_path', 'pages_digest', 'report_path', 'report_digest', 'share_root'):
        parser.add_argument(arg)
    print(json.dumps(compare_share_pages(**vars(parser.parse_args())), sort_keys=True))
