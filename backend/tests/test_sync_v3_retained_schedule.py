from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from flask import Flask
import pytest
from sqlalchemy import text

from models.slate_game import SlateGame
from scripts.rehearse_selected_schedule import reconcile_schedule
from services.schedule_authority import schedule_freshness
from sync_v3.rehearse import isolated_cluster
from tests.test_schedule_ingestion import _game
from utils.db import db


def test_retained_schedule_preserves_source_time_and_refuses_conflicting_replay():
    pg = os.getenv('SYNC_V3_TEST_PG_BIN')
    if not pg:
        pytest.skip('Set SYNC_V3_TEST_PG_BIN for isolated PostgreSQL')
    day = date(2026, 6, 25)
    acquired = datetime(2026, 6, 26, 4, 15, 12, 123456, tzinfo=timezone.utc)
    body = dict(totalGames=1, dates=[dict(date=str(day), totalGames=1, games=[_game()])])
    observation = SimpleNamespace(body=body, retrieved_at=acquired)
    with isolated_cluster(pg) as (owner, _):
        owner.autocommit = True
        with owner.cursor() as cur:
            cur.execute('CREATE DATABASE schedule_clock_rehearsal_test')
        url = f'postgresql://rehearsal_owner@localhost/schedule_clock_rehearsal_test?host={owner.info.host}'
        env = {k: os.environ[k] for k in ('PATH', 'LANG', 'LD_LIBRARY_PATH') if k in os.environ}
        env.update(APP_ENV='test', AUTO_SYNC='false', DATABASE_MIGRATION_MODE='owner',
                   DATABASE_URL=url, TEST_DATABASE_URL=url, PYTHONPATH='.')
        subprocess.run([sys.executable, '-m', 'flask', '--app', 'app', 'db', 'upgrade'],
                       cwd=Path(__file__).resolve().parents[1], env=env, check=True)
        app = Flask(__name__)
        app.config['SQLALCHEMY_DATABASE_URI'] = url
        db.init_app(app)
        with app.app_context():
            with pytest.raises(RuntimeError, match='injected'), db.session.begin():
                reconcile_schedule(day, observation)
                raise RuntimeError('injected')
            with db.session.begin():
                assert SlateGame.query.count() == 0
                reconcile_schedule(day, observation)
            with db.session.begin():
                reconcile_schedule(day, observation)
                assert schedule_freshness(as_of=acquired + timedelta(days=2))['state'] == 'stale'
            contradictory = deepcopy(body)
            contradictory['dates'][0]['games'][0]['seriesGameNumber'] = 99
            for invalid in (SimpleNamespace(body=body, retrieved_at=acquired - timedelta(hours=1)),
                            SimpleNamespace(body=contradictory, retrieved_at=acquired),
                            SimpleNamespace(body=dict(body, totalGames=2), retrieved_at=acquired)):
                with pytest.raises(ValueError), db.session.begin():
                    reconcile_schedule(day, invalid)
            with db.session.begin():
                reconcile_schedule(day, observation, verify_only=True)
                assert SlateGame.query.one().last_synced == acquired.replace(tzinfo=None)
                assert db.session.execute(text('SELECT count(*) FROM scheduled_games')).scalar_one() == 2
                assert db.session.execute(text('SELECT count(*) FROM dashboard_snapshots')).scalar_one() == 0


def test_makeup_requires_matching_game_clubs_and_reciprocal_mlb_times():
    from scripts.rehearse_selected_schedule import retained_makeups

    original_day = date(2017, 8, 16)
    makeup_day = date(2017, 8, 17)
    original_time = '2017-08-17T00:10:00Z'
    makeup_time = '2017-08-17T23:10:00Z'
    common = dict(game_pk=491893, official_date=str(makeup_day))
    original = dict(_game(**common, game_date=original_time, detailed_state='Postponed',
                          status_code='DR', abstract_state='Preview'), rescheduleDate=makeup_time)
    final = dict(_game(**common, game_date=makeup_time, detailed_state='Final', status_code='F',
                       abstract_state='Final'), rescheduledFrom=original_time, rescheduledFromDate=str(original_day))

    def observation(day, game):
        body = dict(totalGames=1, dates=[dict(date=str(day), totalGames=1, games=[game])])
        return SimpleNamespace(body=body, retrieved_at=datetime(2026, 11, 25, tzinfo=timezone.utc))

    def resolve(game):
        return retained_makeups({original_day: observation(original_day, original),
                                 makeup_day: observation(makeup_day, game)})

    earlier, _, later, _ = resolve(final)[491893]
    assert (earlier, later) == (original_day, makeup_day)
    wrong_club = deepcopy(final)
    wrong_club['teams']['away']['team']['id'] = 999
    for conflict in (wrong_club, dict(final, rescheduledFrom=None), dict(final, rescheduledFromDate=str(makeup_day))):
        with pytest.raises(ValueError, match='Conflicting dated schedule listings'):
            resolve(conflict)
