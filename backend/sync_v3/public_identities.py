"""A pinned, opt-in copy of the public Pitcher.id to MLB identity relation for offline reads."""
from datetime import datetime, timezone
from hashlib import sha256

from psycopg2.extras import Json
from sync_v3.evidence import encode_json


def load_reference(cur, reference):
    """Install a sanitized identity export while constructing a disposable reference environment."""
    if not isinstance(reference, dict) or reference.get('source') != 'BaseballOS.pitchers':
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
