from contextlib import closing
from datetime import date, datetime
import json
import os
from pathlib import Path

import pytest

from sync_v3 import savant
from sync_v3.acquisition_receipt import played_day_acquisition
from sync_v3.cycle import run_cycle
from sync_v3.rehearse import isolated_cluster
from sync_v3.replay import install
from test_sync_v3_competition import season
from test_sync_v3_savant import body as savant_response


def test_acquisition_requires_qualified_completions_and_full_played_day_scope():
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    fixture = json.loads((Path(__file__).parent / 'fixtures/sync_v3/played.json').read_text())
    day = date.fromisoformat(fixture['baseball_date'])
    at = datetime.fromisoformat(fixture['observed_at'])
    responses = {row['endpoint']: row['body'] for row in fixture['responses']}

    def fetch(endpoint, params):
        if endpoint == savant.URL:
            return savant_response(day=day)
        if endpoint == '/schedule' and 'season' in params:
            return json.loads(json.dumps(season()).replace('2024', str(day.year)))
        if endpoint.endswith('/roster'):
            return dict(teamId=int(endpoint.split('/')[2]), rosterType=params['rosterType'], roster=[])
        if endpoint == '/transactions':
            return dict(transactions=[])
        return responses[endpoint]

    with isolated_cluster(pg) as (owner, connect), closing(connect()) as worker:
        install(owner)
        run_cycle(worker, day, fetch, max_jobs=256, active_roster_profiles=True, statcast=True,
                  competition=True, clock=lambda: at)
        with owner, owner.cursor() as cur:
            receipt = played_day_acquisition(cur, day)
            assert receipt['jobs'] >= 156 and receipt['represented'] == str(day)
            cur.execute("SET LOCAL timezone='America/New_York'")
            assert played_day_acquisition(cur, day) == receipt
            assert receipt['attempts'] == receipt['jobs']
            for tamper in (
                "DELETE FROM candidate.confirmations WHERE domain='final'",
                "UPDATE candidate.confirmations SET context_id=NULL WHERE domain='final'",
                "UPDATE candidate.jobs SET state='pending',product_date=product_date-1 WHERE id=1",
                "UPDATE candidate.jobs SET attempts=2 WHERE id=1",
                """UPDATE candidate.jobs SET payload=jsonb_set(payload,'{continuation,profile_teams}','[]'::jsonb)
                   WHERE payload->>'endpoint'='/teams/111/roster' AND payload->'params'->>'rosterType'='active'""",
                "UPDATE candidate.jobs SET state='pending' WHERE id=1",
                "UPDATE candidate.jobs SET payload=jsonb_set(payload,'{capture}',to_jsonb('fixture'::text)) WHERE id=1",
                "UPDATE candidate.jobs SET product_date=product_date-1 WHERE payload->>'endpoint'='/game/12345/boxscore'",
                "UPDATE candidate.fetches SET endpoint='/transactions' WHERE id=1",
                "INSERT INTO candidate.refusals VALUES (1,'unresolved')",
                "UPDATE candidate.payloads SET encoded_json='{}' WHERE sha256=(SELECT sha256 FROM candidate.fetches WHERE id=1)",
            ):
                cur.execute('SAVEPOINT invalid_source')
                cur.execute(tamper)
                with pytest.raises(ValueError, match='acquisition|completion'):
                    played_day_acquisition(cur, day)
                cur.execute('ROLLBACK TO SAVEPOINT invalid_source')
