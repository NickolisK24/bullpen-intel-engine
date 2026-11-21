"""A pinned, opt-in copy of the public Pitcher.id to MLB identity relation for offline reads."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from zipfile import ZipFile
from hashlib import file_digest, sha256

from psycopg2.extras import Json
from sync_v3.evidence import encode_json


@dataclass(frozen=True)
class ObservedIdentityExport:
    observed_at: str
    rows: list
    provenance: dict
    membership_reference: str
    availability_reference: str
    team_receipts: dict


def from_observed_publication(path, expected_sha256):
    """Read public identity pairs only from a digest-pinned, postcommit-observed proof archive."""
    from services.mlb_club_directory import MLB_TEAM_IDS
    from services.team_state_vnext_production_proof import _digest

    with Path(path).open('rb') as source:
        if file_digest(source, 'sha256').hexdigest() != expected_sha256:
            raise ValueError('Archive differs from the expected GitHub artifact digest')
        source.seek(0)
        with ZipFile(source) as archive:
            def read(name):
                entries = [entry for entry in archive.infolist() if entry.filename == name]
                if len(entries) != 1 or entries[0].file_size > 32 * 1024 * 1024:
                    raise ValueError('Missing, ambiguous or oversized proof member')
                return json.loads(archive.read(entries[0]))
            proof = read('team-state-vnext-production-proof.json')
            observation = read('observation.json')
    pub = proof['publication']
    receipts = proof['snapshot_team_state_receipts']
    inputs = proof['snapshot_team_state_generation_inputs']
    clubs = {str(team) for team in MLB_TEAM_IDS}
    digest = _digest(receipts)
    if (proof['contract'] != 'team_state_vnext_production_proof_v1'
            or proof['observation_mode'] != 'publisher_transaction_v1' or proof['reconstructed'] is not False
            or proof['overall_verdict'] not in ('PASS', 'PASS_WITH_INCONCLUSIVE')
            or not proof['assertions_expected'] or proof['failed_assertions'] or proof['assertions_evaluated'] != proof['assertions_expected']
            or pub['snapshot_is_published'] is not True or pub['snapshot_status'] != 'ready'
            or set(receipts) != clubs or set(inputs) != clubs
            or proof['postcommit_observation'] != observation or observation['status'] != 'proof_valid'
            or observation['publication_observed'] is not True or observation['differences']
            or observation['snapshot_id'] != pub['dashboard_snapshot_id'] or observation['data_through'] != pub['data_through']
            or observation['observed_team_count'] != len(clubs) or observation['canonical_team_count'] != len(clubs)
            or any(value != digest for value in (observation['expected_receipt_digest'], observation['receipt_digest'],
                                                 proof['snapshot_team_state_receipt_digest']))):
        raise ValueError('Archive lacks an aligned observed publication')
    pairs = {}
    for club in sorted(clubs):
        receipt = receipts[club]
        group = inputs[club]['arm_reads']
        if (receipt['dashboard_snapshot_id'] != pub['dashboard_snapshot_id'] or receipt['team_id'] != int(club)
                or receipt['represented_date'] != pub['data_through'] or group['team_id'] != int(club)
                or group['membership_reference_date'] != pub['expected_membership_reference_date']
                or group['availability_reference_date'] != pub['expected_availability_reference_date']):
            raise ValueError('Club identity scope differs from the observed publication')
        for row in group['records']:
            pid, mlb = row['pitcher_id'], row['mlb_id']
            if (row['team_id'] != int(club) or pid not in group['member_pitcher_ids']
                    or any(type(x) is not int or x < 1 for x in (pid, mlb)) or mlb in pairs):
                raise ValueError('Ambiguous pitcher in the observed publication')
            pairs[mlb] = pid
    if not pairs or len(set(pairs.values())) != len(pairs):
        raise ValueError('Archive lacks unique public pitcher identities')
    at = datetime.fromisoformat(pub['published_at'])
    # BaseballOS persists publication timestamps as UTC (including naive database values).
    if at.tzinfo is None:
        at = at.replace(tzinfo=timezone.utc)
    return ObservedIdentityExport(at.isoformat(), [dict(id=pid, mlb_id=mlb) for mlb, pid in sorted(pairs.items())],
                                  dict(archive_sha256=expected_sha256, receipt_digest=digest,
                                       snapshot_id=pub['dashboard_snapshot_id'], sync_run_id=pub['sync_run_id'],
                                       data_through=pub['data_through'], inconclusive_assertions=proof['inconclusive_assertions']),
                                  pub['expected_membership_reference_date'], pub['expected_availability_reference_date'], receipts)


def load_reference(cur, reference):
    """Install a sanitized identity export while constructing a disposable reference environment."""
    provenance = None
    if isinstance(reference, ObservedIdentityExport):
        provenance = reference.provenance
        reference = dict(source='BaseballOS.observed_team_state_publication', observed_at=reference.observed_at,
                         rows=reference.rows)
    elif not isinstance(reference, dict) or reference.get('source') != 'BaseballOS.pitchers':
        raise ValueError('Expected an isolated export of the BaseballOS pitchers identity columns')
    stamp = datetime.fromisoformat(reference['observed_at'])
    if stamp.utcoffset() is None:
        raise ValueError('Identity export requires a timezone')
    rows = reference.get('rows')
    if not isinstance(rows, list) or not rows:
        raise ValueError('Missing pitcher identity rows')
    players = {}
    public_ids = set()
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'mlb_id', 'id'}:
            raise ValueError('Expected only the canonical pitcher identity columns')
        mlb, public = row['mlb_id'], row['id']
        if any(type(value) is not int or value < 1 for value in (mlb, public)):
            raise ValueError('Invalid pitcher identity')
        if mlb in players or public in public_ids:
            raise ValueError('Ambiguous pitcher identity mapping')
        players[mlb] = public
        public_ids.add(public)
    payload = dict(source=reference['source'], observed_at=stamp.astimezone(timezone.utc).isoformat(),
                   rows=[dict(mlb_id=k, id=players[k]) for k in sorted(players)])
    if provenance:
        payload['publication_reference'] = provenance
    digest = sha256(encode_json(payload)).hexdigest()
    cur.execute('''INSERT INTO candidate.public_identity_export (digest,observed_at,payload) VALUES (%s,%s,%s)
                   ON CONFLICT (digest) DO NOTHING RETURNING digest''', (digest, stamp, Json(payload)))
    if cur.fetchone() is None:
        verify_reference(cur, digest)
        return digest
    # An export may omit a player. Neither public nor MLB identity can be reassigned
    # on that basis. The foreign key rejects a conflicting pair atomically.
    cur.executemany('''INSERT INTO candidate.public_pitcher_identity (mlb_id,pitcher_id) VALUES (%s,%s)
                       ON CONFLICT DO NOTHING''', sorted(players.items()))
    cur.executemany('INSERT INTO candidate.public_pitcher_ids VALUES (%s,%s,%s)',
                    [(digest, mlb, public) for mlb, public in players.items()])
    return digest


def verify_reference(cur, digest):
    cur.execute('SELECT payload,observed_at FROM candidate.public_identity_export WHERE digest=%s', (digest,))
    row = cur.fetchone()
    if (not row or sha256(encode_json(row[0])).hexdigest() != digest
            or datetime.fromisoformat(row[0]['observed_at']) != row[1]):
        raise ValueError('Invalid pinned public identity export')
    cur.execute('SELECT mlb_id,pitcher_id FROM candidate.public_pitcher_ids WHERE export=%s ORDER BY mlb_id', (digest,))
    if [dict(mlb_id=mlb,id=pid) for mlb,pid in cur] != row[0]['rows']:
        raise ValueError('Public pitcher identities disagree with the pinned export')
