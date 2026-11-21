from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path

import pytest

from sync_v3.cycle import run_cycle
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install
from sync_v3.comparison import compare_finals


def test_changed_final_only_invalidates_affected_pitcher_and_club():
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent/'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime(2026,8,1,tzinfo=timezone.utc)
    sources = {(r['endpoint'],tuple(sorted(r['params'].items()))):r['body'] for r in fixture['responses']}
    def fetch(endpoint, params):
        return sources[endpoint,tuple(sorted(params.items()))]
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        db = connect()
        try:
            for i in range(4):
                box = sources['/game/12345/boxscore',()]
                if i == 1:
                    box['teams']['home']['players']['ID102']['stats']['pitching']['strikeOuts'] = 4
                if i == 3:
                    box['teams']['home']['teamStats']['pitching']['inningsPitched'] = '8.0'
                result = run_cycle(db, day, fetch, teams=[111], clock=lambda:at+timedelta(days=2*i))
                if i == 3:
                    assert [status for _,status in result].count('refused') == 1
                else:
                    assert all(status == 'received' for _,status in result)
                with db, db.cursor() as cur:
                    assert compare_finals(cur) == (1,3)
            with db, db.cursor() as cur:
                cur.execute("SELECT id,predecessor FROM candidate.revisions WHERE domain='final' ORDER BY revision")
                first,second = cur.fetchall()
                assert first[1] is None and second[1] == first[0]
                cur.execute('SELECT entity_type,entity_id FROM candidate.impacts WHERE revision_id=%s', (second[0],))
                assert set(cur) == {('pitcher',102),('team',147)}
        finally:
            db.close()


def test_missing_slate_is_unknown_and_a_proven_off_day_preserves_workload():
    from sync_v3.workload import pitcher_windows

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    folder = Path(__file__).parent/'fixtures/sync_v3'
    fixture = json.loads((folder/'played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime(2026,8,1,tzinfo=timezone.utc)
    sources = {(r['endpoint'],r['params'].get('rosterType')):r['body'] for r in fixture['responses']}
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            for offset in range(3):
                if offset:
                    sources['/schedule',None] = {'totalGames':0,'dates':[]}
                statuses = run_cycle(worker, day+timedelta(days=offset),
                                     lambda endpoint,params:sources[endpoint,params.get('rosterType')],
                                     teams=[111], clock=lambda:at+timedelta(days=offset))
                assert all(status=='received' for _,status in statuses)
            with worker, worker.cursor() as cur:
                windows = pitcher_windows(cur, 102, day+timedelta(days=2))
                assert windows[3]['facts'] == {'appearances':1,'multi_inning':1,'high_pitch_outings':0,
                    'batters_faced':4,'outs_recorded':9,'pitches_thrown':15}
                assert len(windows[3]['sources']) == 4
                assert windows[5]['facts'] is None and len(windows[5]['gaps'])==2
                assert pitcher_windows(cur, 999999, day+timedelta(days=2))[3]['facts'] is None
        finally:
            worker.close()
