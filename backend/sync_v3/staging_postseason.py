"""Retain the 18 dated schedules and 35 official decisions from shadow artifact 14993332403."""
import gzip
import json
from datetime import datetime
from hashlib import sha256
from pathlib import Path
from time import monotonic

from psycopg2.extras import Json

from sync_v3.evidence import encode_json


def retain(worker):
    start = monotonic()
    inserted = 0
    checked = 0
    directory = Path(__file__).parent / 'fixtures' / 'nov23-decisions'
    # Use the original full fixture's capture ID and each response's source timestamp.
    with worker, worker.cursor() as cur:
        for filename in sorted(directory.glob('*.json.gz')):
            fixture = json.loads(gzip.decompress(filename.read_bytes()))
            for row in fixture['responses']:
                body = encode_json(row['body'])
                digest = sha256(body).hexdigest()
                key = (fixture['capture'], row['endpoint'], Json(row['params']))
                received = datetime.fromisoformat(row['retrieved_at'])
                cur.execute('INSERT INTO candidate.payloads VALUES (%s,%s) ON CONFLICT DO NOTHING',
                            (digest, body))
                cur.execute('INSERT INTO candidate.captured_requests VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (*key, received, digest))
                inserted += cur.rowcount
                cur.execute("""SELECT r.received_at,r.sha256,encode(pg_catalog.sha256(p.encoded_json),'hex')
                               FROM candidate.captured_requests r JOIN candidate.payloads p USING (sha256)
                               WHERE r.capture=%s AND r.endpoint=%s AND r.parameters=%s""", key)
                if cur.fetchone() != (received, digest, digest):
                    raise ValueError('Archived response disagrees with persistent staging')
                checked += 1
        if checked != 53:
            raise ValueError('Incomplete November postseason archive')
    return dict(verified=checked, inserted=inserted, elapsed_seconds=monotonic()-start)
