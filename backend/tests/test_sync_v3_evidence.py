from datetime import datetime, timezone
from pathlib import Path
import os

import psycopg2
import pytest

from sync_v3 import evidence, queue
from sync_v3.discovery import calendar_requests
from sync_v3.rehearse import isolated_cluster


def test_retry_capture_and_offline_replay():
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    now = datetime(2026, 11, 20, 10, tzinfo=timezone.utc)
    request = calendar_requests(now.date())[0]
    with isolated_cluster(pg) as (owner, connect):
        with owner, owner.cursor() as cur:
            for mod in (queue, evidence):
                cur.execute(Path(mod.__file__).with_suffix('.sql').read_text())
        worker = connect()
        try:
            for i, body in enumerate([{'totalGames': 0, 'dates': []}]*2 + [{'totalGames': 1, 'dates': []}]):
                with worker, worker.cursor() as cur:
                    queue.enqueue(cur, str(i), {'endpoint': request.endpoint, 'params': request.params()}, now)
                    claimed = queue.claim(cur, now)
                oid, status = evidence.execute(worker, claimed, lambda *a, **k: body, lambda: now)
                assert status == ('invalid' if i == 2 else 'received')
                with worker, worker.cursor() as cur:
                    if i < 2:
                        assert evidence.replay(cur, oid).body == body
                    else:
                        with pytest.raises(ValueError):
                            evidence.replay(cur, oid)
            with worker, worker.cursor() as cur:
                cur.execute('SELECT count(*) FROM candidate.fetches')
                assert cur.fetchone() == (3,)
                cur.execute('SELECT count(*) FROM candidate.payloads')
                assert cur.fetchone() == (2,)
            with pytest.raises(psycopg2.errors.InsufficientPrivilege):
                with worker, worker.cursor() as cur:
                    cur.execute("UPDATE candidate.payloads SET body='{}'")
        finally:
            worker.close()
