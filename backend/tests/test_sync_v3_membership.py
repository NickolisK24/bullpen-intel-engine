from datetime import date, datetime, timezone

import pytest

from sync_v3.canonical import Refused
from sync_v3.discovery import Request
from sync_v3.rosters import roster_facts
from sync_v3.sources import inspect_response


def view(team, members, kind='active'):
    req = Request(f'/teams/{team}/roster', (('date','2026-09-26'), ('rosterType',kind)), 0)
    return inspect_response(req, {'teamId': team, 'rosterType':kind, 'roster':members},
                            datetime(2026,10,3,tzinfo=timezone.utc))


def test_old_club_evidence_is_scoped_by_represented_day_and_membership_class():
    person = {'person': {'id': 670103}}
    assert roster_facts(view(111, []))['represented'] == date(2026,9,26).isoformat()
    assert roster_facts(view(111, [person], '40Man'))['members'][0]['id'] == 670103
    with pytest.raises(Refused, match='Affiliate'):
        roster_facts(view(999, [person]))
    conflicted = roster_facts(view(111, [dict(person,status={'code':'A'}),dict(person,status={'code':'D60'})]))
    assert len(conflicted['members']) == 1
    assert conflicted['members'][0]['status'] is None
    assert conflicted['members'][0]['source_statuses'] == ['A','D60']
    with pytest.raises(Refused, match='scope conflict'):
        roster_facts(view(111, [dict(person,parentTeamId=6052)]))


def test_rejected_new_source_withholds_prior_membership_and_keeps_other_days():
    import json
    import os
    from datetime import timedelta
    from pathlib import Path

    from sync_v3.cycle import run_cycle
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install
    from sync_v3.rosters import membership_on

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated server rehearsal')
    fixture = json.loads((Path(__file__).parent/'fixtures/sync_v3/quiet.json').read_text())
    bodies = {(r['endpoint'],r['params'].get('rosterType')):r['body'] for r in fixture['responses']}
    team = 111
    pid = 667356
    day = date(2024,8,5)
    now = datetime(2026,11,21,tzinfo=timezone.utc)
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            for i in range(2):
                body = bodies[('/teams/111/roster','40Man')]
                body['roster'] = [{'person':{'id':pid}, 'parentTeamId':6052 if i else team}]
                results = run_cycle(worker, day, lambda endpoint,params:bodies[endpoint,params.get('rosterType')],
                                    teams=[team], clock=lambda:now+timedelta(days=i))
                with worker, worker.cursor() as cur:
                    assert membership_on(cur, team, '40Man', day, pid) is (None if i else True)
                    assert membership_on(cur, team, 'active', day, pid) is False
                    assert membership_on(cur, team, '40Man', day-timedelta(days=1), pid) is None
                    assert sum(status=='refused' for _,status in results) == i
            with worker, worker.cursor() as cur:
                cur.execute("SELECT count(*) FROM candidate.revisions WHERE domain='roster' AND identity=%s",
                            ('111/40Man/2024-08-05',))
                assert cur.fetchone() == (1,)
        finally:
            worker.close()
