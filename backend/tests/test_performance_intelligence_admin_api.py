"""Internal admin read for M-001 (Active Bullpen ERA).

Internal only, read-only, one team and one represented baseball date. These
tests exist mainly to prove what the route does NOT do: it adds no public
route, changes no public payload, opens no gate, and writes nothing.
"""

from datetime import date, timedelta

import pytest
from flask import Flask

from api.performance_intelligence_admin import performance_intelligence_admin_bp
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import performance_metrics
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db


TEAM_ID = 113
OTHER_TEAM_ID = 158
SEASON = 2026
REPRESENTED_DATE = '2026-07-30'
TOKEN = 'test-admin-token'
ENDPOINT = '/api/internal/performance/active-bullpen-era'


@pytest.fixture()
def app():
    application = Flask('test_performance_intelligence_admin_api')
    configure_test_database(application)
    application.config['ADMIN_API_TOKEN'] = TOKEN
    application.config['APP_ENV'] = 'test'
    application.register_blueprint(
        performance_intelligence_admin_bp, url_prefix='/api/internal/performance',
    )
    db.init_app(application)
    with application.app_context():
        create_test_schema(application)
        try:
            yield application
        finally:
            db.session.remove()
            drop_test_schema(application)


@pytest.fixture()
def client(app):
    return app.test_client()


def _auth(**kwargs):
    return {ADMIN_TOKEN_HEADER: TOKEN, **kwargs}


_next_mlb_id = [870000]
_next_pk = [970000]


def _pitcher(name, *, team_id=TEAM_ID):
    _next_mlb_id[0] += 1
    p = Pitcher(
        mlb_id=_next_mlb_id[0], full_name=name, team_id=team_id,
        team_name='Cincinnati Reds', team_abbreviation='CIN',
        active=True, roster_status='Active', position='P',
    )
    db.session.add(p)
    db.session.flush()
    return p


def _relief(arm, *, outs_each, appearances, earned_runs=0,
            end=date(2026, 7, 29), appearance_team_id=TEAM_ID):
    for index in range(appearances):
        _next_pk[0] += 1
        when = end - timedelta(days=index * 2)
        opponent_id = OTHER_TEAM_ID if appearance_team_id != OTHER_TEAM_ID else TEAM_ID
        for side in (appearance_team_id, opponent_id):
            db.session.add(ScheduledGame(
                team_id=side, game_pk=_next_pk[0], game_date=when,
                game_type='R', status_state=ScheduledGame.STATE_FINAL,
                status_code='F',
            ))
        db.session.add(GameLog(
            pitcher_id=arm.id, mlb_game_pk=_next_pk[0], game_date=when,
            game_type='R', opponent='Milwaukee Brewers', opponent_abbreviation='MIL',
            games_started=0, innings_pitched=outs_each / 3,
            innings_pitched_outs=outs_each,
            earned_runs=earned_runs if index == 0 else 0,
            runs_allowed=earned_runs if index == 0 else 0,
            pitches_thrown=15, appearance_team_id=appearance_team_id,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
            appearance_team_source='boxscore_side',
            appearance_team_reason='appearance_team_resolved_boxscore',
        ))


def _reviewable_team():
    arm = _pitcher('Reviewable Arm')
    _relief(arm, outs_each=3, appearances=36, earned_runs=12)   # 108 outs
    db.session.commit()
    return arm


# ── Authorization ──────────────────────────────────────────────────────────
def test_unauthenticated_request_is_rejected(client):
    response = client.get(f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}')
    assert response.status_code == 401
    assert 'read' not in response.get_json()


def test_wrong_token_is_rejected(client):
    response = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers={ADMIN_TOKEN_HEADER: 'not-the-token'},
    )
    assert response.status_code == 401


def test_configured_token_is_accepted(app, client):
    _reviewable_team()
    response = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    )
    assert response.status_code == 200


# ── Request contract ───────────────────────────────────────────────────────
@pytest.mark.parametrize('query,expected', [
    ('team_id=0&represented_date=2026-07-30', 'invalid_team_id'),
    ('represented_date=2026-07-30', 'invalid_team_id'),
    ('team_id=abc&represented_date=2026-07-30', 'invalid_team_id'),
    (f'team_id={TEAM_ID}', 'invalid_represented_date'),
    (f'team_id={TEAM_ID}&represented_date=yesterday', 'invalid_represented_date'),
    (f'team_id={TEAM_ID}&represented_date=2026-07-30&season=nope', 'invalid_season'),
])
def test_invalid_requests_fail_closed(client, query, expected):
    response = client.get(f'{ENDPOINT}?{query}', headers=_auth())
    assert response.status_code == 400
    assert response.get_json()['error'] == expected


def test_one_team_and_one_date_at_a_time(app, client):
    _reviewable_team()
    payload = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    ).get_json()
    read = payload['read']
    assert read['team_id'] == TEAM_ID
    assert read['represented_date'] == REPRESENTED_DATE
    assert read['season'] == SEASON
    assert isinstance(read, dict)


# ── What the read returns ──────────────────────────────────────────────────
def test_complete_structured_read_is_returned(app, client):
    _reviewable_team()
    payload = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    ).get_json()

    assert payload['context'] == 'internal_review_only'
    assert payload['public'] is False
    read = payload['read']
    assert read['metric_id'] == performance_metrics.METRIC_CURRENT_ACTIVE_PEN_ERA
    assert read['metric_name'] == 'Active Bullpen ERA'
    assert read['internal_name'] == 'Current Active-Pen ERA'
    assert read['value'] == '3.00'
    assert read['sample']['minimum_sample'] == 108
    assert read['sample']['minimum_sample_unit'] == 'recorded_outs'
    assert read['sample']['minimum_sample_authority'] == 'D-023'
    for level in ('summary', 'context', 'evidence', 'official_record'):
        assert level in read['evidence']


def test_response_reports_every_public_gate_as_blocked(app, client):
    _reviewable_team()
    read = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    ).get_json()['read']

    assert read['gates'] == {
        'public_reader_gate': 'blocked',
        'team_state_performance_gate': 'blocked',
        'share_card_performance_gate': 'blocked',
    }
    assert read['publication']['publishable'] is False


def test_readiness_is_reported_separately_from_publication(app, client):
    _reviewable_team()
    read = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    ).get_json()['read']

    assert read['metric_readiness']['ready_for_internal_review'] is True
    assert read['publication']['publishable'] is False
    assert read['publication']['reason'] == 'public_reader_gate_blocked'


def test_below_sample_team_returns_the_approved_wording(app, client):
    arm = _pitcher('Thin Arm')
    _relief(arm, outs_each=3, appearances=22, earned_runs=8)   # 66 outs
    db.session.commit()

    read = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    ).get_json()['read']

    assert read['metric_readiness']['ready_for_internal_review'] is False
    assert read['below_sample_read']['wording'] == 'Not Enough Innings Yet'
    assert read['below_sample_read']['current_innings'] == '22.0'
    assert read['below_sample_read']['required_innings'] == '36.0'


def test_a_team_with_no_group_refuses_rather_than_erroring(app, client):
    _pitcher('Elsewhere', team_id=OTHER_TEAM_ID)
    db.session.commit()

    response = client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    )
    assert response.status_code == 200
    read = response.get_json()['read']
    assert read['value'] is None
    assert read['reason_code'] == 'active_group_empty'


# ── The route stays internal and read-only ─────────────────────────────────
def test_the_route_writes_nothing(app, client):
    _reviewable_team()
    before = (db.session.query(GameLog).count(), db.session.query(Pitcher).count())
    client.get(
        f'{ENDPOINT}?team_id={TEAM_ID}&represented_date={REPRESENTED_DATE}',
        headers=_auth(),
    )
    db.session.expire_all()
    after = (db.session.query(GameLog).count(), db.session.query(Pitcher).count())
    assert before == after


def test_only_one_route_is_registered_and_it_is_internal(app):
    rules = [
        str(rule) for rule in app.url_map.iter_rules()
        if rule.endpoint.startswith('performance_intelligence_admin.')
    ]
    assert rules == [ENDPOINT]
    assert all(rule.startswith('/api/internal/') for rule in rules)


def test_no_mutating_method_is_exposed(client):
    for method in ('POST', 'PUT', 'PATCH', 'DELETE'):
        response = client.open(ENDPOINT, method=method, headers=_auth())
        assert response.status_code == 405


# ── No public surface consumes M-001 ───────────────────────────────────────
def test_no_public_surface_imports_the_performance_framework():
    """Only the internal admin route and the metric registry may consume it."""
    from pathlib import Path

    backend = Path(__file__).resolve().parents[1]
    allowed = {
        backend / 'services' / 'performance_intelligence.py',
        backend / 'services' / 'performance_metrics.py',
        backend / 'api' / 'performance_intelligence_admin.py',
    }
    offenders = []
    for path in list(backend.glob('api/*.py')) + list(backend.glob('services/*.py')):
        if path in allowed:
            continue
        text = path.read_text()
        if 'performance_intelligence' in text or 'performance_metrics' in text:
            offenders.append(path.name)
    assert offenders == []


def test_no_frontend_source_references_the_metric():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    frontend = repo / 'frontend' / 'src'
    if not frontend.exists():
        return
    for pattern in ('Active Bullpen ERA', 'Not Enough Innings Yet',
                    'performance_intelligence', 'active-bullpen-era'):
        hits = [
            str(path.relative_to(repo))
            for path in frontend.rglob('*')
            if path.is_file() and path.suffix in {'.js', '.jsx', '.ts', '.tsx'}
            and pattern in path.read_text(errors='ignore')
        ]
        assert hits == [], f'{pattern} reached the frontend: {hits}'
