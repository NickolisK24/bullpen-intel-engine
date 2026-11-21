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
                    cur.execute("UPDATE candidate.payloads SET encoded_json=''")
        finally:
            worker.close()


def test_distinct_offline_captures_in_one_poll_slot_keep_both_observations(tmp_path):
    from contextlib import closing
    from datetime import date
    import json
    from pathlib import Path
    from sync_v3.replay import install, run_fixture
    from sync_v3.rosters import roster_on

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    original = json.loads((Path(__file__).parent / 'fixtures/sync_v3/quiet.json').read_text())
    day = date.fromisoformat(original['baseball_date'])
    fixtures = []
    for minute in (1, 2):
        original['observed_at'] = f'{day}T10:0{minute}:00Z'
        roster = next(r for r in original['responses'] if r['params'].get('rosterType') == 'active')
        roster['body']['roster'] = [{'person': {'id': 100 + minute}, 'position': {'code': '1'}}]
        path = tmp_path / f'{minute}.json'
        path.write_text(json.dumps(original))
        fixtures.append(path)
    for order in (fixtures, list(reversed(fixtures))):
        with isolated_cluster(pg) as (owner, connect):
            install(owner)
            with closing(connect()) as db:
                for file in order:
                    run_fixture(db, file)
                assert run_fixture(db, order[-1]) == 0
                with db, db.cursor() as cur:
                    facts, _ = roster_on(cur, 111, 'active', day)
                    assert [member['id'] for member in facts['members']] == [102]
                    cur.execute("""SELECT extract(minute FROM received_at)::int FROM candidate.fetches
                                   WHERE parameters->>'rosterType'='active' ORDER BY received_at""")
                    assert cur.fetchall() == [(1,), (2,)]


def test_unadmitted_fixture_observation_is_recoverable_without_reconciling_it(tmp_path):
    from contextlib import closing
    from hashlib import sha256
    import json
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for an isolated PostgreSQL server')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/quiet.json').read_text())
    extra = {'endpoint': '/teams/147/roster', 'params': {'rosterType':'active', 'date': fixture['baseball_date']},
             'body': {'roster': [{'person': {'id': 102}, 'position': {'code': '1'}}]}}
    fixture['responses'].append(extra)
    path = tmp_path / 'retained.json'
    path.write_text(json.dumps(fixture))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            run_fixture(db, path)
            with db, db.cursor() as cur:
                cur.execute("""SELECT p.encoded_json,r.sha256 FROM candidate.captured_requests r
                               JOIN candidate.payloads p USING (sha256) WHERE r.endpoint=%s""", (extra['endpoint'],))
                body, digest = cur.fetchone()
                assert sha256(body).hexdigest() == digest and json.loads(bytes(body)) == extra['body']
                cur.execute("SELECT count(*) FROM candidate.fetches WHERE endpoint=%s", (extra['endpoint'],))
                assert cur.fetchone() == (0,)
                cur.execute("SELECT count(*) FROM candidate.revisions WHERE domain='roster' AND identity LIKE '147/%%'")
                assert cur.fetchone() == (0,)


def test_large_offline_capture_drains_successive_bounded_batches(tmp_path):
    from contextlib import closing
    from datetime import date
    import json
    import os
    from pathlib import Path
    from sync_v3.discovery import pitcher_requests
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated rehearsal')
    data = json.loads((Path(__file__).parent / 'fixtures/sync_v3/quiet.json').read_text())
    data['pitcher_ids'] = list(range(10001, 10130))
    for req in pitcher_requests(date.fromisoformat(data['baseball_date']), data['pitcher_ids']):
        data['responses'].append(dict(endpoint=req.endpoint, params=req.params(), body={'stats': []}))
    path = tmp_path / 'league.json'
    path.write_text(json.dumps(data))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            assert run_fixture(db, path) == len(data['responses']) > 256
            assert run_fixture(db, path) == 0
