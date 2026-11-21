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


def test_depth_directory_and_profile_cannot_grant_mlb_membership():
    from sync_v3.depth import _pitchers
    from sync_v3.discovery import affiliate_directory_request, depth_directory, depth_roster_requests
    from sync_v3.rosters import observe

    day = date(2024, 8, 5)
    req = affiliate_directory_request(day, 118)
    parent = {'id': 118, 'season': 2024, 'sport': {'id': 1}}
    farm = {'id': 541, 'season': 2024, 'sport': {'id': 11}, 'parentOrgId': 118}
    directory = depth_directory(req, {'teams': [parent, farm, dict(farm, id=3301, sport={'id': 21})]})
    requests = depth_roster_requests(day, directory)
    assert [r.endpoint for r in requests] == ['/teams/118/roster', '/teams/541/roster']
    for bad in [dict(farm, parentOrgId=111), dict(farm, season=2025), dict(farm, id=111)]:
        with pytest.raises(ValueError):
            depth_directory(req, {'teams': [parent, bad]})
    body = {'teamId': 541, 'rosterType': 'active', 'roster': [{
        'person': {'id': 12, 'pitchHand': {'code': 'R'}}, 'parentTeamId': 118,
        'position': {'code': '1'}, 'status': {'code': 'A'}}]}
    captured = inspect_response(requests[1], body, datetime.now(timezone.utc))
    assert observe(None, 1, captured) == set()
    observed, reason = _pitchers(body, 541, 118, 'active')
    assert not reason and observed[12]['profile_pitch_hand'] == 'R'
    entry = body['roster'][0]
    body['roster'].append(dict(entry, person={'id': 12, 'pitchHand': {'code': 'L'}}))
    assert _pitchers(body, 541, 118, 'active')[0][12]['profile_pitch_hand'] is None
    body['roster'].append(dict(entry, parentTeamId=111))
    assert _pitchers(body, 541, 118, 'active') == (None, 'parent_club_conflict')


def test_dated_affiliates_replay_independently_of_mlb_membership(tmp_path):
    import json
    import os
    from pathlib import Path

    from sync_v3.depth import club_depth
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated rehearsal')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/quiet.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    fixture['depth_teams'] = [111]
    affiliates = [{'id': 111, 'season': day.year, 'sport': {'id': 1}},
                  *[{'id': t, 'season': day.year, 'sport': {'id': 11}, 'parentOrgId': 111} for t in (414, 428)]]
    fixture['responses'].append({'endpoint': '/teams/affiliates', 'params': {'teamIds': 111, 'season': day.year},
                                 'body': {'teams': affiliates}})
    pitcher = {'person': {'id': 123, 'pitchHand': {'code': 'L'}}, 'position': {'code': '1'}, 'parentTeamId': 111}
    for team in (111, 414, 428):
        fixture['responses'].append({'endpoint': f'/teams/{team}/roster',
                                     'params': {'date': str(day), 'rosterType': 'active', 'hydrate': 'person'},
                                     'body': {'teamId': team, 'rosterType': 'active',
                                              'roster': [] if team == 111 else [pitcher]}})
    path = tmp_path / 'affiliate.json'
    path.write_text(json.dumps(fixture))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        worker = connect()
        try:
            run_fixture(worker, path)
            with worker, worker.cursor() as cur:
                report = club_depth(cur, 111, day)
                assert report['assignment_conflicts'] == {123: [414, 428]}
                assert report['affiliate_assignments'] == {}
                assert report['views']['active']['pitchers'] == {}
                assert report['affiliate_views'][414]['pitchers'][123]['profile_pitch_hand'] == 'L'
                cur.execute("SELECT identity FROM candidate.revisions WHERE domain='roster' ORDER BY identity")
                assert [key for key, in cur] == [f'111/40Man/{day}', f'111/active/{day}']
        finally:
            worker.close()


def test_historical_roster_events_require_both_full_club_lists(tmp_path):
    import json
    import os
    from contextlib import closing
    from pathlib import Path

    from sync_v3.change_history import record_changes, roster_changes
    from sync_v3.intelligence_history import record_intelligence
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated rehearsal')
    quiet = (Path(__file__).parent / 'fixtures/sync_v3/quiet.json').read_text()
    team = 111
    end = date(2026, 11, 22)

    def archive(db, day, participants, hour):
        data = json.loads(quiet.replace('2026-11-21', day.isoformat()))
        data['observed_at'] = f'{day}T{hour}:00:00Z'
        active = next(row for row in data['responses'] if row['params'].get('rosterType') == 'active')
        active['body']['roster'] = [
            {'person': {'id': pid, 'fullName': str(pid)}, 'position': {'code': code}}
            for pid, code in participants]
        path = tmp_path / 'club.json'
        path.write_text(json.dumps(data))
        run_fixture(db, path)
        record_intelligence(db, 'depth', team, day)

    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            archive(db, date(2026, 11, 21), [(101, '1'), (102, '1'), (104, '3')], '10')
            archive(db, end, [(101, '3'), (103, '1'), (104, '1')], '10')
            with db, db.cursor() as cur:
                first = roster_changes(cur, team, end)
                assert first['status'] == 'complete'
                assert [(e['kind'], e['player']) for e in first['events']] == [
                    ('active_roster_removed', 102), ('active_roster_added', 103)]
            frozen = record_changes(db, 'depth', team, end)
            archive(db, date(2026, 11, 21), [(101, '1'), (104, '3')], '12')
            with db, db.cursor() as cur:
                cur.execute("""SELECT predecessor,facts->'events' FROM candidate.workload_history
                               WHERE methodology='candidate_depth_changes_v1' ORDER BY revision DESC LIMIT 1""")
                pred, events = cur.fetchone()
                assert pred == frozen[0] and [event['player'] for event in events] == [103]
            archive(db, end, [], '12')
            with db, db.cursor() as cur:
                revised = roster_changes(cur, team, end)
                assert revised['status'] == 'missing_complete_club_list' and revised['events'] == []
                assert roster_changes(cur, team, end, revisions=(1, 1)) == first


def test_generation_detects_new_roster_receipt_before_snapshot_rebuild(tmp_path):
    from contextlib import closing
    import json
    import os
    from pathlib import Path

    from sync_v3.generation import freeze_generation
    from sync_v3.history import record_workload, METHODOLOGY
    from sync_v3.intelligence_history import record_intelligence
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated rehearsal')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/quiet.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    path = tmp_path / 'club.json'
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as db:
            record_intelligence(db, 'depth', 111, day)
            record_workload(db, 'team', 111, day)
            first = freeze_generation(db, day)
            path.write_text(json.dumps(fixture))
            run_fixture(db, path)
            second = freeze_generation(db, day)
            record_intelligence(db, 'depth', 111, day)
            record_workload(db, 'team', 111, day)
            third = freeze_generation(db, day)
            with db, db.cursor() as cur:
                for generation, stale in [(first, []), (second, [['team', 111, METHODOLOGY],
                                                        ['team', 111, 'candidate_roster_depth_v1']]),
                                          (third, [])]:
                    cur.execute("SELECT manifest->'stale_inputs' FROM candidate.generations WHERE digest=%s",
                                (generation,))
                    assert cur.fetchone()[0] == stale

            # The club and slate were observed again with identical source bodies.
            fixture['observed_at'] = '2026-11-21T12:00:00Z'
            path.write_text(json.dumps(fixture))
            run_fixture(db, path)
            depth = record_intelligence(db, 'depth', 111, day)
            workload = record_workload(db, 'team', 111, day)
            rebuilt = freeze_generation(db, day)
            with db, db.cursor() as cur:
                cur.execute("SELECT manifest->'stale_inputs' FROM candidate.generations WHERE digest=%s", (rebuilt,))
                assert cur.fetchone()[0] == []
            assert record_intelligence(db, 'depth', 111, day) == depth
            assert record_workload(db, 'team', 111, day) == workload


def test_candidate_membership_requires_matching_entities_dates_and_official_roster_receipt():
    from sync_v3.cohort import _club_membership

    day = '2024-08-07'
    reads = dict(readiness=dict(team=118, membership_date=day, team_state={'public_code': 'stretched'},
                                reason=None, arms={'102': {}}),
                 depth=dict(team=118, represented=day, views={'active': {'pitchers': {'102': {}, '103': {}},
                                                                          'reason': None}}),
                 group_performance=dict(team=118, through=day, members=[{'player': 102}], reason=None))
    receipts = {key: {7} for key in reads}
    assert _club_membership(118, day, reads, receipts) == 'matched'
    assert _club_membership(118, day, reads, dict(receipts, depth={8})) == 'dated_roster_receipts_differ_or_missing'
    reads['group_performance']['members'][0]['player'] = 103
    assert _club_membership(118, day, reads, receipts) == 'active_bullpen_identity_conflict'
    reads['depth']['represented'] = '2024-08-06'
    assert _club_membership(118, day, reads, receipts) == 'misaligned_population_snapshot'
