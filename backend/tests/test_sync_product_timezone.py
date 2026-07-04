from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
import services.sync as sync_service
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability_reference_date import product_current_date
from utils.db import db


def _fixed_datetime_class(fixed_utc):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed_utc.replace(tzinfo=None)
            return fixed_utc.astimezone(tz)

    return FixedDateTime


def _host_local_date_class(host_today):
    class HostLocalDate(date):
        @classmethod
        def today(cls):
            return host_today

    return HostLocalDate


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        db.session.add(Pitcher(
            mlb_id=9001,
            full_name='Timezone Boundary Reliever',
            team_id=1,
            team_abbreviation='TBR',
            active=True,
        ))
        db.session.commit()
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.mark.parametrize(
    ('fixed_utc', 'expected_product_day'),
    [
        (
            datetime(2026, 6, 10, 3, 30, tzinfo=timezone.utc),
            date(2026, 6, 9),
        ),
        (
            datetime(2026, 6, 10, 4, 30, tzinfo=timezone.utc),
            date(2026, 6, 10),
        ),
    ],
)
def test_sync_recent_logs_cutoff_uses_product_timezone_day(
    app,
    monkeypatch,
    fixed_utc,
    expected_product_day,
):
    monkeypatch.setattr(sync_service, 'datetime', _fixed_datetime_class(fixed_utc))
    monkeypatch.setattr(
        sync_service,
        'date',
        _host_local_date_class(date(2099, 1, 1)),
    )
    monkeypatch.setattr(
        sync_service.mlb_client,
        'get_pitcher_game_logs',
        lambda mlb_id, season=None: [],
    )

    with app.app_context():
        result = sync_service.sync_recent_logs(days_back=7)

    assert product_current_date(now=fixed_utc) == expected_product_day
    assert result['reference_date'] == expected_product_day.isoformat()
    assert result['cutoff'] == (expected_product_day - timedelta(days=7)).isoformat()
    assert result['season'] == expected_product_day.year


@pytest.mark.parametrize(
    ('fixed_utc', 'expected_product_day'),
    [
        (
            datetime(2026, 6, 10, 3, 30, tzinfo=timezone.utc),
            date(2026, 6, 9),
        ),
        (
            datetime(2026, 6, 10, 4, 30, tzinfo=timezone.utc),
            date(2026, 6, 10),
        ),
    ],
)
def test_daily_sync_offseason_check_uses_product_timezone_day(
    app,
    monkeypatch,
    fixed_utc,
    expected_product_day,
):
    monkeypatch.setattr(sync_service, 'datetime', _fixed_datetime_class(fixed_utc))
    monkeypatch.setattr(
        sync_service,
        'date',
        _host_local_date_class(date(2099, 1, 1)),
    )
    monkeypatch.setattr(sync_service, 'sync_team_assignments', lambda: {
        'pitchers_refreshed': 0,
        'pitchers_changed': 0,
        'reassigned_count': 0,
        'no_organization_count': 0,
        'unknown_count': 0,
        'errors': 0,
        'by_status': {},
    })
    monkeypatch.setattr(sync_service, 'sync_roster_statuses', lambda **_kwargs: {
        'pitchers_refreshed': 0,
        'pitchers_changed': 0,
        'unknown_count': 0,
        'records_failed': 0,
        'errors': 0,
        'by_status': {},
    })
    monkeypatch.setattr(sync_service, 'sync_transactions', lambda **_kwargs: {
        'records_fetched': 0,
        'records_stored': 0,
        'unknown_type_count': 0,
        'records_failed': 0,
        'errors': 0,
        'error_details': [],
    })
    captured_pull_kwargs = {}

    def fake_sync_recent_logs(**kwargs):
        captured_pull_kwargs.update(kwargs)
        return {
            'new_logs_added': 0,
            'pitchers_touched': 0,
            'errors': 0,
            'records_failed': 0,
            'days_back': 7,
            'season': expected_product_day.year,
            'reference_date': expected_product_day.isoformat(),
            'cutoff': (expected_product_day - timedelta(days=7)).isoformat(),
        }

    monkeypatch.setattr(sync_service, 'sync_recent_logs', fake_sync_recent_logs)
    monkeypatch.setattr(sync_service, 'recalculate_all_fatigue', lambda: 0)
    monkeypatch.setattr(
        sync_service,
        'complete_sync_run_with_snapshot',
        lambda *args, **kwargs: (SimpleNamespace(id=1), SimpleNamespace(id=1)),
    )

    import services.availability_backtest as availability_backtest

    monkeypatch.setattr(
        availability_backtest,
        'refresh_availability_backtest',
        lambda: {'status': 'skipped', 'computed_at': None},
    )

    with app.app_context():
        pitcher = Pitcher.query.filter_by(mlb_id=9001).one()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=9901,
            game_date=expected_product_day - timedelta(days=7),
            pitches_thrown=12,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            game_type='R',
        ))
        db.session.commit()

    status = sync_service.run_daily_sync(app, days_back=7)

    assert captured_pull_kwargs['reference_date'] == expected_product_day
    assert status['status'] == 'success'
    assert 'No games found' not in status['message']
