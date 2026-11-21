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


def reproduce_competition_page(body, page, club, state, publication, export):
    """Replay the Board-only branch where the observed state excludes every current baseball point."""
    from services.public_serving_authority import PUBLICATION_AUTHORITY_CONTRACT
    from services.team_state_public_vocabulary import is_competition_withholding
    from services.team_story_previews import build_team_story_preview, render_team_story_html

    if page['representation'] == 'withheld':
        return 'withheld_delivery'
    if export.get('story_previews') != 0 or not is_competition_withholding(state):
        return 'additional_story_or_board_inputs_required'
    if not export.get('generated_at') or not publication.get('published_at'):
        raise ValueError('Historical rendering requires both export and publication timestamps')
    team = dict(team_id=club.team_id, team_name=club.team_name, team_abbreviation=club.abbreviation)
    authority = dict(contract=PUBLICATION_AUTHORITY_CONTRACT, snapshot_id=publication['publication_snapshot_id'],
                     sync_run_id=publication['sync_run_id'], data_through=publication['data_through'],
                     published_at=publication['published_at'])
    preview = build_team_story_preview(team, board=dict(publication_authority=authority, team_state=state),
                                      generated_at=export['generated_at'], expected_snapshot_id=authority['snapshot_id'])
    if render_team_story_html(preview).encode('utf-8') != body:
        raise ValueError(f'Observed publication inputs do not reproduce the archived page: {club.abbreviation}')
    return 'reproduced'


def reproduce_available_state(inputs, observed, team_id):
    """Recompute a historical status-only state from its recorded counts and thresholds."""
    from services.team_state_public_vocabulary import public_team_state
    from services.team_state_vnext_production_proof import _reproduce_contract_a
    from services.publication_truth_certification import contract_a_state
    from sync_v3.evidence import encode_json

    if not all(inputs.get(key) for key in ('readiness', 'reference_dates', 'arm_reads')):
        return dict(status='missing_archived_readiness_inputs')
    readiness = inputs['readiness']
    evidence = readiness['team_state_evidence']
    dates = inputs['reference_dates']
    group = inputs['arm_reads']
    if (readiness['team']['team_id'] != team_id or group['team_id'] != team_id
            or dates['membership_reference_date'] != group['membership_reference_date']
            or dates['availability_reference_date'] != group['availability_reference_date']
            or encode_json(public_team_state(readiness)) != encode_json(observed)):
        raise ValueError(f'Frozen readiness does not reproduce the observed state for {team_id}')
    if evidence.get('basis') != 'status_only':
        return dict(status='partition_basis_outside_replay')
    dist = readiness['availability_distribution']
    buckets = ('available', 'monitor', 'limited', 'avoid', 'unavailable', 'unknown')
    if any(type(dist[k]) is not int or dist[k] < 0 for k in (*buckets, 'total')):
        raise ValueError(f'Invalid availability counts for {team_id}')
    counts = dict(active_pitcher_count=dist['total'], clean_count=dist['available'],
                  moderate_count=dist['monitor'] + dist['limited'], severe_count=dist['avoid'] + dist['unavailable'],
                  unknown_count=dist['unknown'])
    recorded = [row['pitcher_id'] for row in group['records']]
    missing = group['missing_record_pitcher_ids']
    members = group['member_pitcher_ids']
    if (sum(dist[k] for k in buckets) != dist['total'] or len(recorded) != dist['total']
            or len(set(recorded + missing)) != len(recorded) + len(missing)
            or sorted(recorded + missing) != sorted(members)
            or any(type(evidence[k]) is not int or counts[k] != evidence[k] for k in counts)):
        raise ValueError(f'Archived readiness partition differs for {team_id}')
    rule = _reproduce_contract_a(evidence)
    if rule['reproduced'] is not True or rule['status_code'] != readiness['readiness']['status_code']:
        raise ValueError(f'Archived Team State decision differs for {team_id}')
    current_state, current_rule = contract_a_state(counts['clean_count'], counts['severe_count'], counts['active_pitcher_count'])
    agrees = current_state == observed['public_state'] and current_rule == {
        'status_code': rule['status_code'], 'decisive_rule': rule['decisive_rule']}
    return dict(status='reproduced', team_state=observed['public_label'], decisive_rule=rule['decisive_rule'],
                current_partition_rule_matches=agrees,
                counted_pitchers=len(recorded), members_without_records=sorted(missing))


def compare_team_export(report_path, expected_digest, root, *, publication_proof=None, competition=None):
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
        observed = from_observed_publication(*publication_proof, include_available_inputs=True)
        if any(observed.provenance[key] != publication[field] for key, field in (
                ('snapshot_id', 'publication_snapshot_id'), ('sync_run_id', 'sync_run_id'), ('data_through', 'data_through'))):
            raise ValueError('Observed Team State receipts belong to another publication')
    contexts = None
    if competition is not None:
        from sync_v3.archived_comparisons import compare_archived_competition
        from services.team_state_public_vocabulary import public_team_state
        comparison = compare_archived_competition(competition, observed)
        if comparison['status'] != 'competition_fields_match':
            raise ValueError(f"Competition replay cannot establish this edition: {comparison['status']}")
        contexts = {int(team): context for team, context in competition['clubs'].items()}
    pages = []
    compared = 0
    reproduced = 0
    for name, digest in digests.items():
        body = (root / name).read_bytes()
        if sha256(body).hexdigest() != digest:
            raise ValueError(f'Team delivery digest differs for {name}')
        if name != fallback:
            page = compare_team_page(body.decode('utf-8'), files[name], publication=publication)
            if observed is not None:
                state = observed.team_receipts[str(page['team_id'])]['value']
                if page['representation'] == 'dated_team_read':
                    if page['team_state'] != state.get('public_label') or (page['team_state'] is not None) != state['available']:
                        raise ValueError(f'Team preview differs from its observed Team State: {name}')
                    if state['available']:
                        page['available_state_replay'] = reproduce_available_state(
                            observed.available_inputs[str(page['team_id'])], state, page['team_id'])
                    compared += 1
                if contexts is not None:
                    context = contexts[page['team_id']]
                    state = None
                    if context['status'] == 'season_complete':
                        state = public_team_state(dict(season_context=context,
                                                       freshness=dict(data_through=publication['data_through'])))
                page['reproduction'] = reproduce_competition_page(body, page, files[name], state, publication, export)
                reproduced += int(page['reproduction'] == 'reproduced')
            else:
                page['reproduction'] = 'no_observed_publication_proof'
            pages.append(page)
    local = dict(output, files=[str(root / name) for name in files], fallback=str(root / fallback))
    violations, _ = verify(dict(export, output=local), root / 'frontend/public', root)
    if violations:
        raise ValueError(violations)
    return dict(publication_snapshot_id=publication['publication_snapshot_id'], sync_run_id=publication['sync_run_id'],
                data_through=publication['data_through'], observed_team_states_compared=compared,
                pages_reproduced=reproduced, competition_replayed=competition is not None,
                pages=sorted(pages, key=lambda row: row['team_id']))


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('report_path')
    parser.add_argument('expected_digest')
    parser.add_argument('root', help='Checkout or extracted delivery tree with frontend/public/team')
    parser.add_argument('--publication-proof', nargs=2, metavar=('ZIP', 'SHA256'))
    print(json.dumps(compare_team_export(**vars(parser.parse_args())), sort_keys=True))
