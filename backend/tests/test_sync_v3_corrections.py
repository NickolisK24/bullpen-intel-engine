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
