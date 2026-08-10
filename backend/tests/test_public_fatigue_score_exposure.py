"""SEC-001 / #595 — the public API publishes no internal fatigue scoring.

The internal workload model produces a 0-100 composite, component sub-scores,
and a risk tier, and it stores them on rows with their own database keys. None
of that is a BaseballOS public claim: the public product is evidence-first and
de-scored, and an anonymous caller must not be able to read the model's numbers
back out of the API — not directly, not renamed, and not nested somewhere deep
in a payload.

These tests seed a realistically populated bullpen (multiple relievers, several
appearances each, scores spanning the low and high ends of the composite so the
tier breakdown would be non-trivial if it were still published) and then walk
every affected unauthenticated response recursively.

The internal scored view is intentionally retained behind the repository's
existing admin-token authorization; the last test class is the explicit contract
for that split.
"""

from datetime import date, timedelta

import pytest
from flask import Flask

from api.bullpen import bullpen_bp
from api.explanations import explanations_bp
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services.roster_status import STATUS_ACTIVE
from services.public_fatigue_view import (
    FORBIDDEN_PUBLIC_SCORE_FIELDS,
    FORBIDDEN_PUBLIC_SCORE_IDENTIFIERS,
    install_public_score_boundary,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.auth import ADMIN_TOKEN_HEADER
from utils.db import db
from utils.time import utc_now_naive


# Every internal scoring artifact this issue removes, including the component
# sub-scores enumerated on the model. Kept as a literal list rather than reusing
# only the production constant so that deleting a name from the production set
# cannot silently shrink what these tests police.
FORBIDDEN_ANYWHERE = frozenset({
    'raw_score',
    'fatigue_score',
    'avg_fatigue_score',
    'pitch_count_score',
    'rest_days_score',
    'appearances_score',
    'leverage_score',
    'innings_score',
    'risk_level',
    'fatigue_risk_level',
    'risk_breakdown',
}) | FORBIDDEN_PUBLIC_SCORE_FIELDS


def forbidden_key_paths(payload, forbidden, path='$'):
    """Every location in ``payload`` where a forbidden key appears.

    Walks dicts and lists to arbitrary depth: the board nests cards inside
    groups, the dashboard nests boards inside teams, and a leak three levels
    down is the same leak.
    """
    found = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f'{path}.{key}'
            if key in forbidden:
                found.append(here)
            found.extend(forbidden_key_paths(value, forbidden, here))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            found.extend(forbidden_key_paths(item, forbidden, f'{path}[{index}]'))
    return found


def assert_no_internal_scoring(payload, *, where):
    leaks = forbidden_key_paths(payload, FORBIDDEN_ANYWHERE)
    assert leaks == [], f'{where} published internal scoring at: {leaks}'


@pytest.fixture
def app():
    app = Flask('test_public_fatigue_score_exposure')
    app.config['APP_ENV'] = 'development'
    app.config['ADMIN_API_TOKEN'] = 'test-admin-token'
    configure_test_database(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(explanations_bp, url_prefix='/api/explanations')
    db.init_app(app)
    install_public_score_boundary(app)
    with app.app_context():
        create_test_schema(app)
        _seed_bullpen()
        try:
            yield app
        finally:
            db.session.remove()
            drop_test_schema(app)


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def unguarded_client():
    """A client whose app never installs the response backstop.

    The narrowed view models are the actual fix; the backstop is defence in
    depth. Testing only through the guarded app would let a serializer that
    still emits the composite pass, because the boundary would quietly clean up
    after it. These routes have to be clean before anything scrubs them.
    """
    app = Flask('test_public_fatigue_score_exposure_unguarded')
    app.config['APP_ENV'] = 'development'
    app.config['ADMIN_API_TOKEN'] = 'test-admin-token'
    configure_test_database(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')
    app.register_blueprint(explanations_bp, url_prefix='/api/explanations')
    db.init_app(app)
    with app.app_context():
        create_test_schema(app)
        _seed_bullpen()
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


# Composites spanning every internal tier, so a published breakdown or league
# average would be non-zero and non-uniform if either survived.
SEEDED_RELIEVERS = (
    ('Low Usage Arm', 8001, 11.0, 'LOW', 1),
    ('Moderate Usage Arm', 8002, 38.5, 'MODERATE', 1),
    ('Heavy Usage Arm', 8003, 64.0, 'HIGH', 1),
    ('Maxed Usage Arm', 8004, 91.5, 'CRITICAL', 2),
)

TEAM_ID = 111


def _seed_bullpen():
    for index, (name, mlb_id, raw_score, risk_level, days_ago) in enumerate(SEEDED_RELIEVERS):
        pitcher = Pitcher(
            mlb_id=mlb_id,
            full_name=name,
            team_id=TEAM_ID,
            team_name='Contract Club',
            team_abbreviation='CON',
            active=True,
            position='P',
            throws='R',
            # The board's roster authority only renders confirmed-active arms;
            # without this the board would come back empty and the absence
            # proofs above would be proving nothing.
            roster_status=STATUS_ACTIVE,
            roster_status_source='test_fixture',
            roster_status_updated_at=utc_now_naive(),
        )
        db.session.add(pitcher)
        db.session.flush()

        # Three relief appearances each: enough real workload for the
        # availability read and the role authority to resolve normally.
        for appearance in range(3):
            db.session.add(GameLog(
                pitcher_id=pitcher.id,
                mlb_game_pk=90000 + index * 10 + appearance,
                game_date=date.today() - timedelta(days=days_ago + appearance * 2),
                games_started=0,
                innings_pitched=1.0,
                innings_pitched_outs=3,
                pitches_thrown=16 + appearance,
                game_type='R',
            ))

        db.session.add(FatigueScore(
            pitcher_id=pitcher.id,
            calculated_at=utc_now_naive(),
            raw_score=raw_score,
            pitch_count_score=raw_score,
            rest_days_score=raw_score,
            appearances_score=raw_score,
            innings_score=raw_score,
            leverage_score=0.0,
            days_since_last_appearance=days_ago,
            appearances_last_7=3,
            appearances_last_14=3,
            pitches_last_7_days=49,
            innings_last_7_days=3.0,
            risk_level=risk_level,
        ))
    db.session.commit()


def _pitcher_id(full_name):
    return Pitcher.query.filter_by(full_name=full_name).one().id


PUBLIC_ROUTES = (
    '/api/bullpen/fatigue',
    '/api/bullpen/fatigue?with_meta=true&limit=750&include_stale=true',
    f'/api/bullpen/teams/{TEAM_ID}/bullpen',
    f'/api/bullpen/teams/{TEAM_ID}/bullpen?include_stale=true',
    f'/api/bullpen/teams/{TEAM_ID}/board',
    f'/api/bullpen/teams/{TEAM_ID}/board?include_stale=true',
    '/api/bullpen/stats/overview',
    '/api/bullpen/dashboard',
    '/api/bullpen/landscape',
    f'/api/bullpen/teams/compare?team_a={TEAM_ID}&team_b={TEAM_ID}',
    '/api/bullpen/intelligence/tonight',
)


class TestNoInternalScoringInPublicResponses:
    @pytest.mark.parametrize('route', PUBLIC_ROUTES)
    def test_public_route_publishes_no_internal_scoring(self, client, route):
        response = client.get(route)

        assert response.status_code == 200, route
        assert_no_internal_scoring(response.get_json(), where=route)

    def test_pitcher_detail_publishes_no_internal_scoring(self, client, app):
        with app.app_context():
            pitcher_id = _pitcher_id('Maxed Usage Arm')

        response = client.get(f'/api/bullpen/fatigue/{pitcher_id}')

        assert response.status_code == 200
        assert_no_internal_scoring(response.get_json(), where='pitcher detail')

    def test_availability_explanation_publishes_no_internal_scoring(self, client, app):
        with app.app_context():
            pitcher_id = _pitcher_id('Heavy Usage Arm')

        response = client.get(f'/api/explanations/availability/{pitcher_id}')

        assert response.status_code == 200
        assert_no_internal_scoring(response.get_json(), where='availability explanation')

    @pytest.mark.parametrize('route', PUBLIC_ROUTES)
    def test_public_route_is_clean_at_the_serializer_not_only_at_the_boundary(
        self, unguarded_client, route,
    ):
        response = unguarded_client.get(route)

        assert response.status_code == 200, route
        assert_no_internal_scoring(response.get_json(), where=f'unguarded {route}')

    def test_pitcher_scoped_routes_are_clean_at_the_serializer(self, unguarded_client):
        with unguarded_client.application.app_context():
            pitcher_id = _pitcher_id('Maxed Usage Arm')

        for route in (
            f'/api/bullpen/fatigue/{pitcher_id}',
            f'/api/explanations/availability/{pitcher_id}',
        ):
            response = unguarded_client.get(route)
            assert response.status_code == 200, route
            assert_no_internal_scoring(response.get_json(), where=f'unguarded {route}')

    def test_seeded_population_is_actually_populated(self, client):
        """Absence proofs are worthless against an empty payload."""
        body = client.get('/api/bullpen/fatigue?with_meta=true&limit=750').get_json()

        assert len(body['data']) == len(SEEDED_RELIEVERS)
        assert body['meta']['total_scored_pitchers'] == len(SEEDED_RELIEVERS)

        board = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        cards = [card for group in board['groups'] for card in group['pitchers']]
        assert len(cards) == len(SEEDED_RELIEVERS)


class TestPublicFatigueViewModel:
    def test_reliever_row_carries_workload_facts_and_no_score_row_identifiers(self, client):
        rows = client.get('/api/bullpen/fatigue').get_json()

        assert rows
        for row in rows:
            # Approved public content: identity, the governed availability read,
            # counted workload, and the read's freshness stamp.
            assert row['pitcher']['full_name']
            assert row['pitcher']['team_abbreviation'] == 'CON'
            assert row['availability']['availability_status']
            assert row['pitches_last_7_days'] == 49
            assert row['appearances_last_7'] == 3
            assert row['days_since_last_appearance'] is not None
            assert row['calculated_at']

            # The score row's primary and foreign keys exist only to correlate
            # database rows. Public identity travels on the pitcher object.
            for identifier in FORBIDDEN_PUBLIC_SCORE_IDENTIFIERS:
                assert identifier not in row, identifier

    def test_pitcher_identity_stays_available_for_public_routing(self, client):
        """The MLB person ID is an externally meaningful identity, not a leak.

        #595 prohibits the internal sequential identifiers that correlate score
        rows. It does not prohibit addressing a pitcher: the public surfaces
        deep-link to a pitcher, and that identity travels on the pitcher object.
        """
        rows = client.get('/api/bullpen/fatigue').get_json()

        assert all(row['pitcher']['mlb_id'] for row in rows)
        assert all(row['pitcher']['id'] for row in rows)

    def test_team_bullpen_fatigue_block_is_the_narrowed_view_model(self, client):
        rows = client.get(f'/api/bullpen/teams/{TEAM_ID}/bullpen').get_json()

        assert rows
        for row in rows:
            fatigue = row['fatigue']
            assert set(fatigue) == {
                'calculated_at',
                'days_since_last_appearance',
                'appearances_last_7',
                'appearances_last_14',
                'pitches_last_7_days',
                'innings_last_7_days',
            }

    def test_pitcher_detail_trend_is_workload_history_not_score_history(self, client, app):
        with app.app_context():
            pitcher_id = _pitcher_id('Low Usage Arm')

        body = client.get(f'/api/bullpen/fatigue/{pitcher_id}').get_json()

        assert body['current_fatigue']['pitches_last_7_days'] == 49
        assert body['fatigue_trend']
        for entry in body['fatigue_trend']:
            assert 'raw_score' not in entry
            assert 'pitcher_id' not in entry
            assert 'id' not in entry

    def test_stats_overview_reports_coverage_not_tiers(self, client):
        body = client.get('/api/bullpen/stats/overview').get_json()

        assert body['scored_pitchers'] == len(SEEDED_RELIEVERS)
        assert body['total_pitchers'] == len(SEEDED_RELIEVERS)
        assert 'risk_breakdown' not in body
        assert 'avg_fatigue_score' not in body

    def test_board_card_keeps_public_labels_without_a_score(self, client):
        board = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
        cards = [card for group in board['groups'] for card in group['pitchers']]

        assert cards
        for card in cards:
            assert card['name']
            assert card['availability_status']
            assert 'fatigue_score' not in card
            assert card['data_state'] != 'missing'


class TestInternalTierIsNotReachableAnonymously:
    def test_risk_level_is_not_a_public_filter(self, client):
        """A tier filter is a tier oracle even when the tier is never printed."""
        unfiltered = client.get('/api/bullpen/fatigue?limit=750').get_json()
        attempted = client.get('/api/bullpen/fatigue?limit=750&risk_level=CRITICAL').get_json()

        assert len(unfiltered) == len(SEEDED_RELIEVERS)
        # The parameter is ignored rather than honoured: an anonymous caller
        # cannot partition the league by internal tier.
        assert len(attempted) == len(unfiltered)

    def test_public_list_meta_does_not_echo_a_tier_filter(self, client):
        body = client.get('/api/bullpen/fatigue?with_meta=true&risk_level=HIGH').get_json()

        assert 'risk_level' not in body['meta']['filters']
        assert body['meta']['filters']['team_id'] is None


class TestAuthorizedInternalScoredAccess:
    """The scored view is retained, explicitly authorized, and never anonymous."""

    def test_workload_snapshot_refuses_anonymous_callers(self, client):
        response = client.get('/api/bullpen/fatigue/snapshot')

        assert response.status_code == 401
        assert 'error' in response.get_json()

    def test_workload_snapshot_refuses_a_wrong_token(self, client):
        response = client.get(
            '/api/bullpen/fatigue/snapshot',
            headers={ADMIN_TOKEN_HEADER: 'not-the-admin-token'},
        )

        assert response.status_code == 401

    def test_authorized_snapshot_retains_the_internal_scored_view(self, client):
        response = client.get(
            '/api/bullpen/fatigue/snapshot',
            headers={ADMIN_TOKEN_HEADER: 'test-admin-token'},
        )

        assert response.status_code == 200
        rows = response.get_json()['data']
        assert rows

        # Internal analysis keeps the model's own numbers. This is the one place
        # they remain readable, and it takes an admin token to get here.
        seeded_scores = {score for _n, _m, score, _r, _d in SEEDED_RELIEVERS}
        assert {row['raw_score'] for row in rows} == seeded_scores
        assert all(row['risk_level'] for row in rows)
        assert all(row['pitcher_id'] for row in rows)

    def test_authorized_tier_filter_still_works(self, client):
        response = client.get(
            '/api/bullpen/fatigue/snapshot?risk_level=CRITICAL',
            headers={ADMIN_TOKEN_HEADER: 'test-admin-token'},
        )

        assert response.status_code == 200
        rows = response.get_json()['data']
        assert [row['risk_level'] for row in rows] == ['CRITICAL']


class TestResponseBoundaryBackstop:
    """A stored or future payload cannot reintroduce the exposure anonymously."""

    def test_anonymous_response_is_scrubbed_even_when_a_view_leaks(self, app):
        @app.route('/api/test-only/leaky-read')
        def _leaky_read():
            return {
                'name': 'Maxed Usage Arm',
                'raw_score': 91.5,
                'risk_level': 'CRITICAL',
                'nested': {'cards': [{'fatigue_score': 64.0, 'availability_status': 'Avoid'}]},
                # A real baseball fact that happens to end in _score. The boundary
                # is an explicit deny list precisely so this survives.
                'home_score': 4,
            }

        body = app.test_client().get('/api/test-only/leaky-read').get_json()

        assert_no_internal_scoring(body, where='leaky read')
        assert body['name'] == 'Maxed Usage Arm'
        assert body['home_score'] == 4
        assert body['nested']['cards'][0]['availability_status'] == 'Avoid'
