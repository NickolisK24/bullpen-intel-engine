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


def test_replay_work_reports_scoped_leases_and_dependencies_without_claiming():
    from contextlib import closing
    from sync_v3.replay import install, read_replay_work

    bindir = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not bindir:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    capture = 'a' * 64
    with isolated_cluster(bindir) as (owner, connect):
        install(owner)
        with closing(connect()) as worker, closing(connect()) as reader:
            reader.set_session(readonly=True)
            with worker, worker.cursor() as cur:
                payload = dict(capture=capture, endpoint='/schedule', params={})
                scope = dict(budget='historical', product_date=now.date())
                parent = queue.enqueue(cur, 'schedule', payload, now, **scope)
                child = queue.enqueue(cur, 'dependent', payload, now, prerequisite=parent, **scope)
                queue.enqueue(cur, 'different capture', dict(payload, capture='b' * 64), now, **scope)
                queue.enqueue(cur, 'different budget', payload, now, product_date=now.date())
                claimed = queue.claim(cur, now, capture=capture, **scope)
                assert claimed[0] == parent
            running = read_replay_work(reader, now.date(), capture)
            assert running['job_states'] == {'running': 1, 'pending': 1}
            first, second = running['jobs']
            assert first['job_id'] == parent and first['receipt_id'] is None and first['attempts'] == 1
            assert datetime.fromisoformat(first['lease_until']) == now + timedelta(minutes=5)
            assert second['job_id'] == child and second['prerequisite'] == parent
            assert second['prerequisite_state'] == 'running' and second['attempts'] == 0
            with worker, worker.cursor() as cur:
                queue.settle(cur, *claimed[:2], now, error=True, retryable=False)
            failed = read_replay_work(reader, now.date(), capture)
            assert failed['job_states'] == {'dead': 1, 'pending': 1}
            assert failed['jobs'][1]['prerequisite_state'] == 'dead'
            assert read_replay_work(reader, now.date(), capture) == failed
            with worker, worker.cursor() as cur:
                for index in range(31):
                    queue.enqueue(cur, f'blocked-{index}', payload, now, prerequisite=parent, **scope)
            first_page = read_replay_work(reader, now.date(), capture)
            after = first_page['next_after_job_id']
            assert len(first_page['jobs']) == 32 and first_page['jobs'][-1]['job_id'] == after
            remaining = read_replay_work(reader, now.date(), capture, after_job_id=after)
            assert remaining['job_states'] == first_page['job_states'] == {'dead': 1, 'pending': 32}
            assert len(remaining['jobs']) == 1 and remaining['jobs'][0]['job_id'] > after
            assert remaining['next_after_job_id'] is None
            for invalid in (-1, True, 2**63):
                with pytest.raises(ValueError, match='job ID'):
                    read_replay_work(reader, now.date(), capture, after_job_id=invalid)
