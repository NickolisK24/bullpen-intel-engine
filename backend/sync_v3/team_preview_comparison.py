"""Offline contract comparison for the existing static Team Board handoff."""
from html import escape, unescape
import json
import re

from scripts.verify_generated_share_previews import CANONICAL_PATTERN, HREF_PATTERN
from scripts.verify_generated_team_previews import _claim_violations, _read_authority_meta, _read_open_graph
from services.team_story_previews import DEFAULT_SITE_URL, TEAM_PAGE_ROOT, TEAM_SHARE_SOURCE


def compare_team_page(text, club, *, publication=None):
    """Check club routing and the publication a rendered page can cite."""
    route = f'{DEFAULT_SITE_URL}{TEAM_PAGE_ROOT}/{club.abbreviation}'
    destination = f'/bullpen?view=board&team={club.abbreviation}&source={TEAM_SHARE_SOURCE}'
    links = [unescape(value) for value in HREF_PATTERN.findall(text)]
    redirects = re.findall(r'window\.location\.replace\(("[^"]*")\);', text)
    if (f'<h1>{escape(club.team_name)} Bullpen</h1>' not in text
            or CANONICAL_PATTERN.findall(text) != [route] or _read_open_graph(text).get('url') != route
            or links != [destination] or redirects != [json.dumps(destination)]):
        raise ValueError(f'Team preview route differs for {club.abbreviation}')
    meta = _read_authority_meta(text)
    if meta.get('representation') == 'withheld':
        if (not meta.get('withheld-reason') or any(key in meta for key in (
                'data-through', 'snapshot-id', 'sync-run-id', 'team-state', 'authority-contract',
                'unfurl-team-state', 'published-at', 'story-id')) or 'data-baseballos-team-state=' in text):
            raise ValueError(f'Withheld team preview carries a claim or lacks its reason: {club.abbreviation}')
    elif meta.get('representation') == 'dated_team_read' and publication:
        expected = {'data-through': publication['data_through'], 'snapshot-id': str(publication['publication_snapshot_id']),
                    'sync-run-id': str(publication['sync_run_id'])}
        if (any(meta.get(key) != value for key, value in expected.items()) or 'withheld-reason' in meta
                or meta.get('authority-contract') != 'trusted_dashboard_publication_v1'
                or f'<time datetime="{expected["data-through"]}">{expected["data-through"]}</time>' not in text
                or _claim_violations(club.abbreviation, meta, text)):
            raise ValueError(f'Team preview disagrees with the publication: {club.abbreviation}')
    else:
        raise ValueError(f'Team preview lacks publication evidence: {club.abbreviation}')
    return dict(team_id=club.team_id, representation=meta['representation'], withheld_reason=meta.get('withheld-reason'),
                team_state=meta.get('team-state'), snapshot_id=meta.get('snapshot-id'), sync_run_id=meta.get('sync-run-id'), data_through=meta.get('data-through'))


def compare_team_export(report_path, expected_digest, root, *, publication_proof=None):
    """Replay the owner delivery gate against the checkout corresponding to a pinned Actions export."""
    from hashlib import sha256
    from pathlib import Path
    from scripts.verify_generated_team_previews import verify
    from services.mlb_club_directory import MLB_CLUBS
    from sync_v3.archived_share_pages import _open_verified

    root = Path(root).resolve()
    with Path(report_path).open('rb') as stream, _open_verified(stream, expected_digest) as report:
        names = report.namelist()
        if len(names) != len(set(names)):
            raise ValueError('Duplicate team delivery evidence entries')
        if 'team-digest-postbuild.json' in names:
            manifest, export_name = 'team-digest-postbuild.json', 'team-export.json'
        else:
            manifest, export_name = 'generated-digest.json', 'export-result.json'
        rows = json.loads(report.read(manifest))
        export = json.loads(report.read(export_name))
        publication = json.loads(report.read('publication.json'))
    prefix = 'frontend/public/team/'
    fallback = prefix + 'index.html'
    files = {prefix + club.abbreviation + '/index.html': club for club in MLB_CLUBS}
    output = export['output']
    digests = {row['path']: row['sha256'] for row in rows}
    if (set(digests) != files.keys() | {fallback} or len(digests) != len(rows)
            or set(output['files']) != files.keys() or len(output['files']) != len(files)
            or output['fallback'] != fallback):
        raise ValueError('Team export does not account for all 30 clubs and the fallback')
    if (publication['status'] != 'ok' or publication['publication_snapshot_id'] != export['publication_snapshot_id']
            or publication['data_through'] != export['publication_data_through'] or not publication['sync_run_id']):
        raise ValueError('Team delivery report and publication disagree')
    observed = None
    if publication_proof is not None:
        from sync_v3.public_identities import from_observed_publication
        observed = from_observed_publication(*publication_proof)
        if any(observed.provenance[key] != publication[field] for key, field in (
                ('snapshot_id', 'publication_snapshot_id'), ('sync_run_id', 'sync_run_id'), ('data_through', 'data_through'))):
            raise ValueError('Observed Team State receipts belong to another publication')
    pages = []
    compared = 0
    for name, digest in digests.items():
        body = (root / name).read_bytes()
        if sha256(body).hexdigest() != digest:
            raise ValueError(f'Team delivery digest differs for {name}')
        if name != fallback:
            page = compare_team_page(body.decode('utf-8'), files[name], publication=publication)
            if observed is not None and page['representation'] == 'dated_team_read':
                state = observed.team_receipts[str(page['team_id'])]['value']
                if page['team_state'] != state.get('public_label') or (page['team_state'] is not None) != state['available']:
                    raise ValueError(f'Team preview differs from its observed Team State: {name}')
                compared += 1
            pages.append(page)
    local = dict(output, files=[str(root / name) for name in files], fallback=str(root / fallback))
    violations, _ = verify(dict(export, output=local), root / 'frontend/public', root)
    if violations:
        raise ValueError(violations)
    return dict(publication_snapshot_id=publication['publication_snapshot_id'], sync_run_id=publication['sync_run_id'],
                data_through=publication['data_through'], observed_team_states_compared=compared,
                pages=sorted(pages, key=lambda row: row['team_id']))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_path')
    parser.add_argument('expected_digest')
    parser.add_argument('root', help='Checkout or extracted delivery tree with frontend/public/team')
    parser.add_argument('--publication-proof', nargs=2, metavar=('ZIP', 'SHA256'))
    print(json.dumps(compare_team_export(**vars(parser.parse_args())), sort_keys=True))
