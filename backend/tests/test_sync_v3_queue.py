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


def test_expired_last_attempts_do_not_hide_ready_work():
    from contextlib import closing

    bindir = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not bindir:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    now = datetime(2026, 9, 1, tzinfo=timezone.utc)
    with isolated_cluster(bindir) as (owner, connect):
        with owner, owner.cursor() as cur:
            cur.execute(Path(queue.__file__).with_suffix('.sql').read_text())
        with closing(connect()) as worker:
            with worker, worker.cursor() as cur:
                for i in range(17):
                    job = queue.enqueue(cur, str(i), {}, now, max_attempts=1)
                    assert queue.claim(cur, now)[0] == job
                ready = queue.enqueue(cur, 'ready', {}, now)
            later = now + timedelta(minutes=6)
            with worker, worker.cursor() as cur:
                claim = queue.claim(cur, later)
                assert claim is not None and claim[0] == ready
                cur.execute("SELECT count(*) FROM candidate.jobs WHERE state='dead'")
                assert cur.fetchone() == (16,)
                queue.settle(cur, *claim[:2], later)
                assert queue.claim(cur, later) is None
                cur.execute('SELECT outcome,count(*) FROM candidate.attempts GROUP BY outcome')
                assert dict(cur) == {'done': 1, 'expired': 17}


def test_worker_exit_rolls_back_receipt_canonical_records_and_child_jobs():
    import json
    from contextlib import closing
    from multiprocessing import get_context
    from sync_v3 import evidence
    from sync_v3.cycle import plan_children
    from sync_v3.replay import install

    bindir = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not bindir:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    schedule = next(row for row in fixture['responses'] if row['endpoint'] == '/schedule')
    now = datetime.fromisoformat(fixture['observed_at'])
    day = datetime.fromisoformat(fixture['baseball_date']).date()
    payload = dict(endpoint='/schedule', params=schedule['params'])
    scope = dict(budget='current', product_date=day)

    with isolated_cluster(bindir) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            with db, db.cursor() as cur:
                job = queue.enqueue(cur, 'schedule', payload, now, **scope)

            def derive(cur, receipt, acquisition):
                plan_children(cur, receipt, acquisition, 'current', now, day)

            def interrupted_worker():
                connection = connect()
                with connection, connection.cursor() as cur:
                    claim = queue.claim(cur, now, **scope)
                def interrupt_after_derivation(cur, receipt, acquisition):
                    derive(cur, receipt, acquisition)
                    cur.execute("SELECT count(*) FROM candidate.revisions WHERE domain='schedule'")
                    assert cur.fetchone() == (1,)
                    cur.execute('SELECT count(*) FROM candidate.jobs')
                    assert cur.fetchone()[0] > 1
                    os._exit(77)
                evidence.execute(connection, claim, lambda *a, **kw: schedule['body'], lambda: now,
                                 on_received=interrupt_after_derivation)

            worker = get_context('fork').Process(target=interrupted_worker)
            worker.start()
            worker.join(20)
            if worker.is_alive():
                worker.terminate()
                worker.join()
            assert worker.exitcode == 77
            with db, db.cursor() as cur:
                for table in ('fetches', 'payloads', 'revisions', 'confirmations'):
                    cur.execute('SELECT count(*) FROM candidate.' + table)
                    assert cur.fetchone() == (0,)
                cur.execute('SELECT id,state FROM candidate.jobs')
                assert cur.fetchall() == [(job, 'running')]
                assert queue.claim(cur, now + timedelta(minutes=4), **scope) is None
                later = now + timedelta(minutes=5)
                claim = queue.claim(cur, later, **scope)
                assert claim[0] == job
            _, outcome = evidence.execute(db, claim, lambda *a, **kw: schedule['body'], lambda: later,
                                          on_received=derive)
            assert outcome == 'received'
            with db, db.cursor() as cur:
                cur.execute('SELECT outcome FROM candidate.attempts WHERE job_id=%s ORDER BY claimed_at', (job,))
                assert cur.fetchall() == [('expired',), ('done',)]
                cur.execute('SELECT count(*) FROM candidate.fetches')
                assert cur.fetchone() == (1,)
                cur.execute("SELECT count(*) FROM candidate.confirmations WHERE domain='schedule'")
                assert cur.fetchone() == (1,)
                cur.execute("SELECT count(*),count(DISTINCT payload->>'endpoint') FROM candidate.jobs WHERE state='pending'")
                assert cur.fetchone() == (3, 3)


def test_current_worker_resumes_prior_day_without_replanning_or_changing_profile_scope():
    from contextlib import closing
    from datetime import date
    from sync_v3.cycle import run_cycle
    from sync_v3.replay import install

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    first = date(2026, 11, 21)
    second = first + timedelta(days=1)
    now = datetime(2026, 11, 21, 23, 59, tzinfo=timezone.utc)
    calls = []

    def fetch(endpoint, params):
        calls.append((endpoint, params))
        if endpoint == '/schedule':
            return {'dates': [], 'totalGames': 0}
        if endpoint == '/transactions':
            return {'transactions': []}
        if endpoint.startswith('/people/'):
            return {'stats': []}
        assert endpoint == '/teams/111/roster' and params['date'] == str(first)
        return {'teamId': 111, 'rosterType': params['rosterType'],
                'roster': [{'person': {'id': 9001}, 'position': {'code': '1'}}]}

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as worker:
            run_cycle(worker, first, fetch, teams=[111], active_roster_profiles=True,
                      postseason_rounds=['W'], round_totals=True, max_jobs=1, clock=lambda: now)
        with closing(connect()) as replacement:
            with replacement, replacement.cursor() as cur:
                cur.execute("SELECT count(*) FROM candidate.jobs WHERE product_date=%s AND state='pending'", (first,))
                pending, = cur.fetchone()
                assert pending > 0
                payload = {'endpoint': '/transactions', 'params': {}}
                queue.enqueue(cur, 'untagged-prior', payload, now, product_date=first)
                queue.enqueue(cur, 'future', dict(payload, continuation={}), now, product_date=second+timedelta(days=1))
                queue.enqueue(cur, 'historical', dict(payload, continuation={}), now, product_date=first, budget='historical')
            run_cycle(replacement, second, fetch, teams=[], clock=lambda: now + timedelta(minutes=4))
            with replacement, replacement.cursor() as cur:
                cur.execute("SELECT DISTINCT state FROM candidate.jobs WHERE product_date=%s AND budget='current' AND payload ? 'continuation'", (first,))
                assert cur.fetchall() == [('done',)]
                cur.execute("SELECT state FROM candidate.jobs WHERE identity IN ('untagged-prior','future','historical')")
                assert cur.fetchall() == [('pending',)] * 3
        assert [params['startDate'] for endpoint, params in calls if endpoint == '/schedule'] == [str(first), str(second)]
        assert sorted((p['gameType'], p['stats']) for endpoint, p in calls if endpoint == '/people/9001/stats') == [
            (stage, kind) for stage in ('R', 'W') for kind in ('byDateRange', 'gameLog')
        ]


def test_private_current_worker_admits_only_acquisition_and_reports_partial_progress(monkeypatch):
    from contextlib import closing
    from datetime import date
    from sync_v3 import current_worker
    from sync_v3.replay import install

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    calls = []
    def official(self, endpoint, params):
        calls.append(endpoint)
        return {'totalGames': 0, 'dates': []}
    monkeypatch.setattr(current_worker.MLBApiClient, '_get', official)

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect(reviewer=True)) as reviewer, closing(connect()) as worker:
            for unauthorized in (owner, reviewer):
                with pytest.raises(ValueError, match='restricted acquisition worker'):
                    current_worker.process(unauthorized, date(2026, 11, 23), max_jobs=1)
            assert not calls
            with owner, owner.cursor() as cur:
                cur.execute('CREATE TABLE public.unrelated (value int)')
                cur.execute('GRANT UPDATE(value) ON public.unrelated TO sync_v3_worker')
            with pytest.raises(ValueError, match='restricted acquisition worker'):
                current_worker.process(worker, date(2026, 11, 23), max_jobs=1)
            assert not calls
            with owner, owner.cursor() as cur:
                cur.execute('REVOKE UPDATE(value) ON public.unrelated FROM sync_v3_worker')
                cur.execute('GRANT UPDATE(generation) ON candidate.core_selections TO sync_v3_worker')
            with pytest.raises(ValueError, match='restricted acquisition worker'):
                current_worker.process(worker, date(2026, 11, 23), max_jobs=1)
            assert not calls
            with owner, owner.cursor() as cur:
                cur.execute('REVOKE UPDATE(generation) ON candidate.core_selections FROM sync_v3_worker')
            with owner, owner.cursor() as cur:
                cur.execute("UPDATE candidate.schema_installation SET digest=repeat('0',64)")
                cur.execute('SELECT digest FROM candidate.schema_installation')
                assert cur.fetchone() == ('0' * 64,)
            with pytest.raises(ValueError, match='schema installation'):
                current_worker.process(worker, date(2026, 11, 23), max_jobs=1)
            assert not calls
            with owner, owner.cursor() as cur:
                cur.execute('UPDATE candidate.schema_installation SET digest=%s',
                            (current_worker.schema_digest(current_worker.schema_scripts()),))
            report = current_worker.process(worker, date(2026, 11, 23), max_jobs=1)
            assert calls == ['/schedule']
            assert report['receipts'] == {'received': 1} and report['jobs_for_date']['pending'] > 0
            assert report['publication_attempted'] is False
            with worker, worker.cursor() as cur:
                cur.execute('SELECT count(*) FROM candidate.core_selections')
                assert cur.fetchone() == (0,)


def test_private_worker_acquires_scoped_depth_and_rounds(monkeypatch):
    from contextlib import closing
    from datetime import date
    from test_sync_v3_competition import season
    from sync_v3 import current_worker
    from sync_v3.replay import install

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    day = date(2024, 10, 28)
    calls = []

    def official(self, endpoint, params):
        calls.append((endpoint, params))
        if endpoint == '/schedule' and 'season' in params:
            return season()
        if endpoint == '/schedule':
            return {'dates': [], 'totalGames': 0}
        if endpoint == '/transactions':
            return {'transactions': []}
        if endpoint == '/teams/affiliates':
            assert params['teamIds'] == 111
            return {'teams': [
                {'id': 111, 'season': 2024, 'sport': {'id': 1}},
                {'id': 533, 'season': 2024, 'sport': {'id': 11}, 'parentOrgId': 111},
            ]}
        if endpoint.startswith('/people/'):
            return {'stats': []}
        club = int(endpoint.split('/')[2])
        rows = [{'person': {'id': 9001}, 'position': {'code': '1'}}] if club == 111 else []
        return {'teamId': club, 'rosterType': params['rosterType'], 'roster': rows}

    monkeypatch.setattr(current_worker.MLBApiClient, '_get', official)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as worker:
            with pytest.raises(ValueError, match='active profiles'):
                current_worker.process(worker, day, max_jobs=1, postseason_rounds=['W'])
            with pytest.raises(ValueError, match='postseason round'):
                current_worker.process(worker, day, max_jobs=1, profiles=True, round_totals=True)
            assert not calls
            report = current_worker.process(worker, day, max_jobs=256, profiles=True,
                                            depth_teams=[111], postseason_rounds=['W'], round_totals=True)
            with owner, owner.cursor() as cur:
                cur.execute("SELECT endpoint,reason FROM candidate.fetches WHERE outcome <> 'received' LIMIT 4")
                assert set(report['jobs_for_date']) == {'done'}, cur.fetchall()
            assert report['publication_attempted'] is False
    assert [params for endpoint, params in calls if endpoint == '/teams/533/roster'] == [
        {'date': str(day), 'rosterType': 'active', 'hydrate': 'person'}]
    assert sorted((p['gameType'], p['stats']) for end, p in calls if end == '/people/9001/stats') == [
        (stage, kind) for stage in ('R', 'W') for kind in ('byDateRange', 'gameLog')]
