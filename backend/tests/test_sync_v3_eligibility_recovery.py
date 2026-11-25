from contextlib import closing
from datetime import date, datetime, timedelta
import json
import os
from pathlib import Path

import pytest

from sync_v3 import eligibility_recovery as recovery, queue
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install


@pytest.mark.parametrize('team_id,expected_box,interrupt', [(147, True, False), (112, False, False), (147, True, True)])
def test_dated_recovery_obeys_the_official_slate_and_leaves_other_jobs_pending(monkeypatch, team_id, expected_box, interrupt):
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at']) + timedelta(days=1)
    gap = dict(reason='eligibility_game_not_confirmed',
               evidence=dict(game_date=str(day), game_type='R', game_pk=12345, team_id=team_id))
    def readiness(cur, club, through):
        assert club == 111 and through == day
        return dict(reason='incomplete_eligibility_sample', eligibility_gaps={102: gap, 103: gap})
    monkeypatch.setattr(recovery, 'represented_readiness', readiness)
    calls = []
    def fetch(endpoint, params):
        calls.append(endpoint)
        return next(row['body'] for row in fixture['responses'] if row['endpoint'] == endpoint and row['params'] == params)

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as worker, worker, worker.cursor() as cur:
            unrelated = queue.enqueue(cur, 'unrelated', dict(endpoint='/transactions', params={}),
                                      at, priority=200, budget='historical', product_date=day)
        if interrupt:
            def unavailable(endpoint, params):
                raise ConnectionError('fixture outage')
            with closing(connect()) as worker:
                failed = recovery.recover(worker, 111, day, max_jobs=1, fetch=unavailable, clock=lambda: at)
                assert failed['status'] == 'acquisition_failed'
                waiting = recovery.recover(worker, 111, day, max_jobs=1, fetch=fetch, clock=lambda: at)
                assert waiting['status'] == 'awaiting_retry_or_lease' and not calls
            at += timedelta(seconds=30)
            with closing(connect()) as other, other.cursor() as cur:
                assert queue.claim(cur, at, budget='historical', product_date=day)[0] == unrelated
                other.rollback()
        with closing(connect()) as worker:
            first = recovery.recover(worker, 111, day, max_jobs=1, fetch=fetch, clock=lambda: at)
            assert first['receipts'] == ['received'] and calls == ['/schedule']
        with closing(connect()) as worker:
            second = recovery.recover(worker, 111, day, max_jobs=3, fetch=fetch, clock=lambda: at)
            assert second['receipts'] == (['received'] if expected_box else [])
            assert second['status'] == 'withheld'
            assert calls == (['/schedule', '/game/12345/boxscore'] if expected_box else ['/schedule'])
            assert recovery.recover(worker, 111, day, max_jobs=3, fetch=fetch, clock=lambda: at)['receipts'] == []
            with worker, worker.cursor() as cur:
                cur.execute('SELECT state FROM candidate.jobs WHERE id=%s', (unrelated,))
                assert cur.fetchone() == ('pending',)
                cur.execute('SELECT count(*) FROM candidate.core_selections')
                assert cur.fetchone() == (0,)
        with pytest.raises(ValueError):
            recovery.recover(owner, 111, day, max_jobs=3, fetch=fetch, clock=lambda: at)
