"""Check played-day delivery against the selection after the isolated handoff commits."""
from models.share_artifact import ShareArtifact
from models.tonight_publication import TonightPublication
from services.mlb_club_directory import MLB_TEAM_IDS
from services.team_state_vnext_production_proof import observe_committed_publication_proof
from services.tonight_read_model import content_sha256


def _get(client, path):
    response = client.get(path)
    if response.status_code != 200:
        raise ValueError(f'Public delivery returned {response.status_code} for {path}')
    return response.get_json()


def compare_slate(selected, served, binding):
    if (selected['status'] != 'represented' or selected['selection_revision'] != binding['revision']
            or selected['generation'] != binding['generation'] or selected['data_through'] != binding['data_through']
            or selected['availability_reference'] != binding['availability_reference']):
        raise ValueError('Tonight comparison requires the pinned schedule edition')

    def games(cards):
        indexed = {game['game_pk']: game for game in cards}
        if len(indexed) != len(cards):
            raise ValueError('Duplicate game in Tonight delivery')
        return indexed

    expected, actual = games(selected['games']), games(served['games'])
    if expected.keys() != actual.keys():
        raise ValueError('Tonight game inventory differs from the selected schedule')
    differences = {}
    for pk, game in expected.items():
        other = actual[pk]
        for field in ('game_number', 'first_pitch_utc', 'state'):
            if game[field] != other[field]:
                raise ValueError(f'Tonight game {pk} differs on {field}')
        for side in ('home', 'away'):
            team = game[side]['team_id']
            if (other[side]['team_id'] != team or other[side]['team_state'] != game[side]['team_state']
                    or other[side]['team_state']['public_state'] != binding['teams'][str(team)]['state']['public_state']):
                raise ValueError(f'Tonight game {pk} differs on its {side} club or Team State')
            for field in ('rest', 'workload_7d', 'multi_day_usage', 'rotation', 'key_arms', 'change_refs'):
                if game[side][field] != other[side][field]:
                    differences.setdefault(field, []).append(dict(game_pk=pk, side=side, team_id=team))
    return differences


def verify_delivery(client, snapshot, selected):
    ident = snapshot.id, snapshot.sync_run_id
    binding = snapshot.payload['v3_rehearsal_selection']
    states = {int(t): row['state'] for t, row in binding['teams'].items()}
    proof = observe_committed_publication_proof(snapshot)
    if proof['status'] != 'proof_valid' or set(states) != set(MLB_TEAM_IDS):
        raise ValueError('Selected publication lacks complete committed Team State proof')
    league = _get(client, '/api/bullpen/team-states')
    authority = league['publication_authority']
    rows = league['teams']
    if ((authority['snapshot_id'], authority['sync_run_id']) != ident
            or len(rows) != len(states) or {r['team_id']: r['team_state'] for r in rows} != states):
        raise ValueError('Public League listing differs from the selected Team States')

    artifacts = ShareArtifact.query.filter_by(artifact_type='team_state', source_snapshot_id=snapshot.id,
                                              lifecycle_state='published').all()
    if len(artifacts) != len(states) or {a.team_id for a in artifacts} != states.keys():
        raise ValueError('Missing or duplicate published Team State artifact')
    for artifact in artifacts:
        response = _get(client, f'/api/share-artifacts/{artifact.public_id}')
        view = response['artifact']
        src = view['authority']
        expected = states[artifact.team_id]
        if (view['lifecycle_state'] != 'published' or view['public_id'] != artifact.public_id
                or view['team']['team_id'] != artifact.team_id or (src['source_snapshot_id'], src['source_sync_run_id']) != ident
                or view['product_date'] != binding['data_through']
                or any(view['team_state'][k] != expected[k] for k in ('public_state', 'public_label'))):
            raise ValueError(f'Share Artifact differs for club {artifact.team_id}')

    row = TonightPublication.query.filter_by(dashboard_snapshot_id=snapshot.id, contract='tonight_v1',
                                            reference_date=snapshot.availability_reference_date).one()
    if (row.sync_run_id != snapshot.sync_run_id or content_sha256(row.payload) != row.content_sha256):
        raise ValueError('Stored Tonight edition disagrees with its identity or digest')
    tonight = _get(client, '/api/bullpen/intelligence/tonight?contract=tonight_v1')
    edition = tonight['edition']
    published = edition['publication']
    if ((published['dashboard_snapshot_id'], published['sync_run_id']) != ident
            or edition['data_through'] != binding['data_through']
            or edition['baseball_date'] != binding['availability_reference']):
        raise ValueError('Public Tonight edition differs from the selected publication')
    stored_differences = compare_slate(selected, row.payload, binding)
    served_differences = compare_slate(selected, tonight, binding)
    return dict(snapshot_id=snapshot.id, sync_run_id=snapshot.sync_run_id, generation=binding['generation'],
                league_clubs=len(rows), published_team_state_artifacts=len(artifacts), games=len(tonight['games']),
                supporting_fields_match=not (stored_differences or served_differences),
                stored_side_differences=stored_differences, served_side_differences=served_differences,
                tonight_publication_id=row.id, tonight_sha256=row.content_sha256, receipt_digest=proof['receipt_digest'])
