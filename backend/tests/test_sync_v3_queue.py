from datetime import datetime, timedelta, timezone
import os
from pathlib import Path

import pytest

from sync_v3 import queue
from sync_v3.rehearse import isolated_cluster


def test_job_recovery_and_scope():
    bindir = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not bindir:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with isolated_cluster(bindir) as (owner, connect):
        with owner, owner.cursor() as cur:
            cur.execute(Path(queue.__file__).with_suffix('.sql').read_text())
        worker, second = connect(), connect()
        try:
            with worker, worker.cursor() as cur:
                parent = queue.enqueue(cur, 'a', {}, now)
                child = queue.enqueue(cur, 'b', {}, now, prerequisite=parent)
                queue.enqueue(cur, 'backfill', {}, now, budget='historical', priority=0)
                old = queue.claim(cur, now)
                assert old[0] == parent
                with second, second.cursor() as other:
                    assert queue.claim(other, now) is None
            with second, second.cursor() as cur:
                replacement = queue.claim(cur, now + timedelta(days=80))
                assert replacement[0] == parent and replacement[1] != old[1]
            later = now + timedelta(days=80)
            with pytest.raises(ValueError, match='superseded'):
                with worker, worker.cursor() as cur:
                    queue.enqueue(cur, 'rollback', {}, later)
                    queue.settle(cur, *old[:2], later)
            with worker, worker.cursor() as cur:
                cur.execute("SELECT count(*) FROM candidate.jobs WHERE identity='rollback'")
                assert cur.fetchone()[0] == 0
                queue.settle(cur, *replacement[:2], later)
                assert queue.enqueue(cur, 'a', {}, later) == parent
                assert queue.claim(cur, later)[0] == child
                assert queue.claim(cur, later) is None
                job = queue.claim(cur, later, budget='historical')
                queue.settle(cur, *job[:2], later, error=True)
                assert queue.claim(cur, later, budget='historical') is None
                job = queue.claim(cur, later + timedelta(seconds=30), budget='historical')
                queue.settle(cur, *job[:2], later + timedelta(seconds=30), error=True, retryable=False)
                cur.execute('SELECT state FROM candidate.jobs WHERE id=%s', (job[0],))
                assert cur.fetchone() == ('dead',)
        finally:
            worker.close()
            second.close()
