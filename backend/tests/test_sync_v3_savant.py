from datetime import date, datetime, timezone
from hashlib import sha256

import pytest

from sync_v3 import savant
from sync_v3.discovery import Request
from sync_v3.sources import inspect_response, transport_endpoint


DAY = date(2017, 8, 28)


def body(*, day=DAY, duplicate=False):
    names = sorted(savant.FIELDS)
    row = dict.fromkeys(names, '')
    row.update(game_date=str(day), game_pk='492000', at_bat_number='21', pitch_number='2',
               pitcher='519301', batter='450000')
    line = ','.join(row[key] for key in names)
    raw = '\ufeff' + ','.join(names) + '\r\n' + line + '\r\n'
    if duplicate:
        raw += line + '\r\n'
    return dict(csv=raw, sha256=sha256(raw.encode()).hexdigest())


def test_final_discovers_one_day_without_changing_pitch_measurements():
    finals = [Request('/game/492000/boxscore', (), 900), Request('/game/492001/boxscore', (), 900)]
    req, = savant.after_final(DAY, finals)
    payload = body()
    result = inspect_response(req, payload, datetime.now(timezone.utc))
    assert result.body == payload and transport_endpoint(req) == savant.URL
    assert not savant.after_final(DAY, []) and not savant.after_final(date(2014, 8, 28), finals)


@pytest.mark.parametrize('payload', [body(day=date(2017, 8, 29)), body(duplicate=True),
                                     dict(body(), sha256='different'), dict(body(), csv='')])
def test_conflicting_or_damaged_capture_is_refused(payload):
    with pytest.raises(ValueError):
        savant.inspect(savant.day_request(DAY).params(), payload)


def test_wider_query_is_refused_before_transport():
    params = dict(savant.day_request(DAY).params(), game_date_lt='2017-08-29')
    with pytest.raises(ValueError):
        transport_endpoint(Request(savant.URL, tuple(sorted(params.items())), 0))


@pytest.mark.parametrize('outage', [False, True])
def test_capture_preserves_stats_api_when_provider_is_unavailable(tmp_path, monkeypatch, outage):
    import json
    from pathlib import Path
    from requests import Timeout
    from sync_v3 import capture_day

    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    responses = {(r['endpoint'], tuple(sorted(r['params'].items()))): r['body'] for r in fixture['responses']}
    monkeypatch.setattr(capture_day.MLBApiClient, '_get',
                        lambda self, path, params: responses[path, tuple(sorted(params.items()))])

    def provider(params):
        assert savant.request_day(params) == day
        if outage:
            raise Timeout()
        return body(day=day)

    monkeypatch.setattr(savant, 'fetch', provider)
    path = tmp_path / 'day.json'
    capture_day.capture(day, path, teams=fixture['team_ids'], statcast=True)
    archived = json.loads(path.read_text())
    assert archived['statcast'] is True
    assert {r['endpoint'] for r in archived['responses']} >= {r['endpoint'] for r in fixture['responses']}
    provider_rows = [r for r in archived['responses'] if r['endpoint'] == savant.URL]
    assert ('Baseball Savant' in archived['providers']) is (not outage)
    if outage:
        assert not provider_rows and archived['acquisition_failures'][0]['reason'] == 'Timeout'
    else:
        assert provider_rows[0]['body'] == body(day=day) and 'acquisition_failures' not in archived


def test_postgres_replays_provider_revisions_without_changing_official_game_lines(tmp_path):
    import json
    import os
    from contextlib import closing
    from pathlib import Path
    from sync_v3 import evidence
    from sync_v3.rehearse import isolated_cluster
    from sync_v3.replay import install, run_fixture

    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for the isolated PostgreSQL server')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    fixture['statcast'] = True
    first = body(day=day)
    item = dict(endpoint=savant.URL, params=savant.day_request(day).params(), body=first)
    fixture['responses'].append(item)
    path = tmp_path / 'fixture.json'
    path.write_text(json.dumps(fixture))
    with isolated_cluster(pg) as (owner, connect):
        install(owner)
        with closing(connect()) as worker:
            reviews = []
            assert run_fixture(worker, path, on_statcast_review=reviews.append) > 0
            assert run_fixture(worker, path, on_statcast_review=reviews.append) == 0
            assert reviews[0] == reviews[1]
            assert reviews[0]['status'] == 'unqualified'
            assert reviews[0]['provider_sha256'] == first['sha256']
            with worker, worker.cursor() as cur:
                cur.execute('SELECT count(*) FROM candidate.revisions')
                official_revisions, = cur.fetchone()
            raw = first['csv'].replace('519301', '519302')
            item['body'] = dict(csv=raw, sha256=sha256(raw.encode()).hexdigest())
            fixture['observed_at'] = '2026-07-31T12:00:00+00:00'
            path.write_text(json.dumps(fixture))
            assert run_fixture(worker, path) > 0
            with worker, worker.cursor() as cur:
                cur.execute('SELECT id FROM candidate.fetches WHERE endpoint=%s ORDER BY id', (savant.URL,))
                observations = [evidence.replay(cur, oid).body for oid, in cur.fetchall()]
                assert observations == [first, item['body']]
                assert savant.review_capture(cur, reviews[0]['capture']) == reviews[0]
                cur.execute('SELECT count(*) FROM candidate.revisions')
                assert cur.fetchone() == (official_revisions,)

def test_provider_count_preserves_untracked_pitches_and_separates_automatic_calls():
    raw = ('game_pk,pitcher,description,pitch_type\n'
           '42,1001,called_strike,\n42,1001,automatic_ball,\n42,1001,automatic_strike,\n')
    report = savant.compare_pitch_counts(raw, {(42, 1001): 1})
    assert report['status'] == 'pitch_counts_match'
    assert report['automatic_calls'] == 2 and report['thrown_pitch_rows'] == 1
    mismatched = savant.compare_pitch_counts(raw, {(42, 1002): None})
    assert mismatched['status'] == 'unqualified'
    assert len(mismatched['differences']) == 2
