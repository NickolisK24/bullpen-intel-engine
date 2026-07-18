"""Focused WP42 schedule authority and postability coverage."""

from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from flask import Flask

from models.slate_game import SlateGame
from services import schedule_authority, schedule_ingestion
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
import models.prospect  # noqa: F401 - load the complete mapper registry


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _game(
    game_pk=900001,
    *,
    game_date='2026-07-18T23:10:00Z',
    official_date='2026-07-18',
    home_id=135,
    away_id=116,
    code='S',
    detailed='Scheduled',
    abstract='Preview',
    doubleheader='N',
    game_number=1,
    scheduled_innings=9,
):
    return {
        'gamePk': game_pk,
        'gameDate': game_date,
        'officialDate': official_date,
        'doubleHeader': doubleheader,
        'gameNumber': game_number,
        'scheduledInnings': scheduled_innings,
        'status': {
            'statusCode': code,
            'detailedState': detailed,
            'abstractGameState': abstract,
        },
        'teams': {
            'home': {'team': {'id': home_id}},
            'away': {'team': {'id': away_id}},
        },
    }


def test_game_date_uses_eastern_conversion_not_official_or_utc_date(app):
    with app.app_context():
        # A 9:40 PM Pacific start is 04:40 UTC and 00:40 Eastern the next day.
        schedule_ingestion.ingest_games([
            _game(
                game_date='2026-07-19T04:40:00Z',
                official_date='2026-07-18',
            )
        ])

        row = db.session.get(SlateGame, 900001)
        assert row.game_time_utc == datetime(2026, 7, 19, 4, 40)
        assert row.game_date_et == date(2026, 7, 19)


@pytest.mark.parametrize(('code', 'detailed', 'abstract', 'expected'), [
    ('S', 'Scheduled', 'Preview', SlateGame.STATE_UPCOMING),
    ('P', 'Pre-Game', 'Preview', SlateGame.STATE_UPCOMING),
    ('I', 'In Progress', 'Live', SlateGame.STATE_LIVE),
    ('F', 'Final', 'Final', SlateGame.STATE_COMPLETED),
    ('DR', 'Postponed', 'Preview', SlateGame.STATE_CANCELLED),
    ('C', 'Cancelled', 'Final', SlateGame.STATE_CANCELLED),
    ('U', 'Suspended', 'Live', SlateGame.STATE_UNCERTAIN),
    ('I', 'Delayed', 'Live', SlateGame.STATE_UNCERTAIN),
    ('X', 'New MLB State', 'Other', SlateGame.STATE_UNCERTAIN),
])
def test_status_normalization_is_explicit_and_raw_status_is_preserved(
    app, code, detailed, abstract, expected
):
    with app.app_context():
        schedule_ingestion.ingest_games([
            _game(code=code, detailed=detailed, abstract=abstract)
        ])
        row = db.session.get(SlateGame, 900001)
        assert row.normalized_state == expected
        assert row.status_code == code
        assert row.status_detailed == detailed
        assert row.status_abstract == abstract


def test_reingest_is_duplicate_safe_and_full_upsert_updates_all_schedule_fields(app):
    with app.app_context():
        first = schedule_ingestion.ingest_games([_game()], source='first')
        first_synced = db.session.get(SlateGame, 900001).last_synced

        second = schedule_ingestion.ingest_games([
            _game(
                game_date='2026-07-19T00:10:00Z',
                home_id=116,
                away_id=135,
                code='F',
                detailed='Final',
                abstract='Final',
                doubleheader='Y',
                game_number=2,
                scheduled_innings=7,
            )
        ], source='second')

        assert first['slate_games_created'] == 1
        assert second['slate_games_updated'] == 1
        assert SlateGame.query.count() == 1
        row = db.session.get(SlateGame, 900001)
        assert row.home_team_id == 116
        assert row.away_team_id == 135
        assert row.game_time_utc == datetime(2026, 7, 19, 0, 10)
        assert row.normalized_state == SlateGame.STATE_COMPLETED
        assert row.doubleheader_flag == 'Y'
        assert row.game_number == 2
        assert row.scheduled_innings == 7
        assert row.last_synced >= first_synced


def test_doubleheaders_remain_independent_and_split_slate_is_postable(app):
    now = datetime(2026, 7, 18, 18, 0)
    with app.app_context():
        schedule_ingestion.ingest_games([
            _game(
                game_pk=900101,
                game_date='2026-07-18T17:10:00Z',
                code='F',
                detailed='Final',
                abstract='Final',
                doubleheader='Y',
                game_number=1,
            ),
            _game(
                game_pk=900102,
                game_date='2026-07-18T23:10:00Z',
                doubleheader='Y',
                game_number=2,
            ),
        ])
        for row in SlateGame.query.all():
            row.last_synced = now - timedelta(minutes=5)
        db.session.commit()

        contract = schedule_authority.build_postability_schedule_contract(
            date(2026, 7, 18), as_of=now
        )
        team = contract['teams']['135']
        assert [game['game_pk'] for game in contract['games']] == [900101, 900102]
        assert team['doubleheader'] is True
        assert team['postable'] is True
        assert team['state'] == SlateGame.STATE_UPCOMING
        assert [game['game_number'] for game in team['games']] == [1, 2]


def test_stale_schedule_fails_closed(app):
    now = datetime(2026, 7, 18, 18, 0)
    with app.app_context():
        schedule_ingestion.ingest_games([_game()])
        row = db.session.get(SlateGame, 900001)
        row.last_synced = now - timedelta(hours=25)
        db.session.commit()

        contract = schedule_authority.build_postability_schedule_contract(
            date(2026, 7, 18), as_of=now, max_age_hours=24
        )
        assert contract['freshness']['state'] == 'stale'
        assert contract['teams']['135'] == {
            'postable': False,
            'state': SlateGame.STATE_UNCERTAIN,
            'reason': 'schedule_stale',
            'doubleheader': False,
            'games': [row.to_dict()],
        }


def test_preview_after_scheduled_start_fails_closed_until_status_refresh(app):
    now = datetime(2026, 7, 18, 23, 30)
    with app.app_context():
        schedule_ingestion.ingest_games([
            _game(game_date='2026-07-18T23:10:00Z')
        ])
        row = db.session.get(SlateGame, 900001)
        row.last_synced = now - timedelta(minutes=30)
        db.session.commit()

        team = schedule_authority.build_postability_schedule_contract(
            date(2026, 7, 18), as_of=now
        )['teams']['135']
        assert team['postable'] is False
        assert team['state'] == SlateGame.STATE_UNCERTAIN
        assert team['reason'] == 'scheduled_start_passed_without_status_update'


def test_rolling_refresh_fetches_yesterday_through_plus_three_with_full_upserts(
    app, monkeypatch
):
    calls = []
    responses = [[_game()], [_game(code='F', detailed='Final', abstract='Final')]]

    def fake_schedule(**kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', fake_schedule)
    with app.app_context():
        first = schedule_authority.ingest_rolling_window(date(2026, 7, 18))
        second = schedule_authority.ingest_rolling_window(date(2026, 7, 18))

        assert calls == [
            {'start_date': '2026-07-17', 'end_date': '2026-07-21'},
            {'start_date': '2026-07-17', 'end_date': '2026-07-21'},
        ]
        assert first['summary']['slate_games_created'] == 1
        assert second['summary']['slate_games_updated'] == 1
        assert db.session.get(SlateGame, 900001).normalized_state == 'completed'


def test_morning_refresh_reuses_singleton_workflow_and_schedule_only_command():
    workflow = (
        Path(__file__).resolve().parents[2]
        / '.github'
        / 'workflows'
        / 'baseballos-sync.yml'
    ).read_text(encoding='utf-8')
    assert "- cron: '0 14 * * *'" in workflow
    assert 'concurrency:\n  group: baseballos-sync\n  cancel-in-progress: false' in workflow
    block = workflow.split('      - name: Run morning slate schedule refresh\n', 1)[1]
    block = block.split('\n      - name:', 1)[0]
    assert "github.event.schedule == '0 14 * * *'" in block
    assert 'python backend/scripts/refresh_slate_schedule.py' in block
    assert 'run_daily_sync.py' not in block
    assert 'run_postgame_refresh.py' not in block
