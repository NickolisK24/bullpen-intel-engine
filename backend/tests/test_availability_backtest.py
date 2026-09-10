from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.prospect  # noqa: F401
from api.methodology import methodology_bp
from models.availability_backtest_result import AvailabilityBacktestResult
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.availability import (
    STATUS_AVAILABLE,
    STATUS_AVOID,
    STATUS_LIMITED,
    STATUS_MONITOR,
    STATUS_UNAVAILABLE,
)
from services.availability_backtest import (
    CADENCE,
    METHOD_VERSION,
    compute_availability_backtest,
    latest_backtest_payload,
)
from utils.db import db


ROUTE = '/api/methodology/availability-backtest'
TIERS = [
    STATUS_AVAILABLE,
    STATUS_MONITOR,
    STATUS_LIMITED,
    STATUS_AVOID,
    STATUS_UNAVAILABLE,
]


@pytest.fixture
def client():
    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(methodology_bp, url_prefix='/api/methodology')
    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def add_pitcher(name, seed):
    pitcher = Pitcher(
        mlb_id=800000 + seed,
        full_name=name,
        team_id=seed,
        team_name=f'Team {seed}',
        team_abbreviation=f'T{seed}',
        position='P',
        active=True,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def add_log(pitcher, day, *, pitches=10, games_started=0, seed=1):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=(pitcher.mlb_id * 100) + seed,
        game_date=day,
        game_type='R',
        games_started=games_started,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=pitches,
    ))


def add_backtest_rows(*, computed_at, season, rates):
    for index, tier in enumerate(TIERS, start=1):
        rate = rates[tier]
        sample_size = 100 + index
        db.session.add(AvailabilityBacktestResult(
            method_version=METHOD_VERSION,
            cadence=CADENCE,
            computed_at=computed_at,
            data_through=date(season, 6, 15),
            season=season,
            window_label=f'{season} primary' if season == 2026 else f'{season} secondary',
            window_start=date(season, 3, 28),
            window_end=date(season, 6, 15),
            tier=tier,
            tier_order=index,
            sample_size=sample_size,
            next_day_appearances=round(sample_size * rate),
            next_day_rate=rate,
            no_appearance_days=500,
            no_appearance_tier_flips=25,
            no_appearance_tier_flip_rate=0.05,
            created_at=computed_at,
        ))


def tier_rates(payload, season):
    window = next(item for item in payload['windows'] if item['season'] == season)
    return {tier['tier']: tier for tier in window['tiers']}


def test_backtest_reconstructs_reliever_days_and_filters_start_outcomes(client):
    with client.application.app_context():
        start = date(2026, 1, 1)
        available = add_pitcher('Available Relief', seed=1)
        for offset, seed in [(0, 1), (2, 2), (4, 3), (6, 4)]:
            add_log(available, start + timedelta(days=offset), pitches=8, seed=seed)

        avoid = add_pitcher('Avoid Relief', seed=2)
        add_log(avoid, start, pitches=40, seed=1)

        swing_start = add_pitcher('Swing Start', seed=3)
        add_log(swing_start, start, pitches=8, games_started=0, seed=1)
        add_log(swing_start, start + timedelta(days=2), pitches=50, games_started=1, seed=2)
        db.session.commit()

        result = compute_availability_backtest(seasons=(2026,))[0]

    available_counts = result.tier_counts[STATUS_AVAILABLE]
    avoid_counts = result.tier_counts[STATUS_AVOID]

    assert available_counts['sample_size'] > 0
    assert avoid_counts['sample_size'] > 0
    available_rate = available_counts['next_day_appearances'] / available_counts['sample_size']
    avoid_rate = avoid_counts['next_day_appearances'] / avoid_counts['sample_size']
    assert avoid_rate < available_rate


def test_latest_payload_comes_from_stored_computation(client):
    with client.application.app_context():
        add_backtest_rows(
            computed_at=datetime(2026, 6, 14, 7, 0, 0),
            season=2026,
            rates={
                STATUS_AVAILABLE: 0.99,
                STATUS_MONITOR: 0.88,
                STATUS_LIMITED: 0.77,
                STATUS_AVOID: 0.66,
                STATUS_UNAVAILABLE: 0.55,
            },
        )
        add_backtest_rows(
            computed_at=datetime(2026, 6, 15, 7, 0, 0),
            season=2026,
            rates={
                STATUS_AVAILABLE: 0.41,
                STATUS_MONITOR: 0.31,
                STATUS_LIMITED: 0.21,
                STATUS_AVOID: 0.04,
                STATUS_UNAVAILABLE: 0.0,
            },
        )
        add_backtest_rows(
            computed_at=datetime(2026, 6, 15, 7, 0, 0),
            season=2025,
            rates={
                STATUS_AVAILABLE: 0.39,
                STATUS_MONITOR: 0.28,
                STATUS_LIMITED: 0.18,
                STATUS_AVOID: 0.03,
                STATUS_UNAVAILABLE: 0.0,
            },
        )
        db.session.commit()

        payload = latest_backtest_payload()

    assert payload['status'] == 'ok'
    assert payload['computed_at'] == '2026-06-15T07:00:00Z'
    rates_2026 = tier_rates(payload, 2026)
    assert rates_2026[STATUS_AVAILABLE]['next_day_rate_pct'] == 41.0
    assert rates_2026[STATUS_AVOID]['next_day_rate_pct'] == 4.0
    assert rates_2026[STATUS_UNAVAILABLE]['next_day_rate_pct'] == 0.0
    assert rates_2026[STATUS_AVAILABLE]['n'] == 101
    assert payload['framing']['caveat']


def test_backtest_route_serves_stored_rows(client):
    with client.application.app_context():
        add_backtest_rows(
            computed_at=datetime(2026, 6, 15, 8, 0, 0),
            season=2026,
            rates={
                STATUS_AVAILABLE: 0.35,
                STATUS_MONITOR: 0.25,
                STATUS_LIMITED: 0.15,
                STATUS_AVOID: 0.02,
                STATUS_UNAVAILABLE: 0.0,
            },
        )
        db.session.commit()

    response = client.get(ROUTE)
    payload = response.get_json()
    rates_2026 = tier_rates(payload, 2026)

    assert response.status_code == 200
    assert payload['method_version'] == METHOD_VERSION
    assert rates_2026[STATUS_AVAILABLE]['next_day_rate_pct'] == 35.0
    assert rates_2026[STATUS_AVOID]['next_day_rate_pct'] == 2.0
    assert 'association' in payload['framing']['caveat']
