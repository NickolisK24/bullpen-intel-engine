"""D-055 workload facts survive the D-051 trusted publication carrier."""

from copy import deepcopy
from datetime import timedelta
import importlib
import json
from types import SimpleNamespace

import pytest
from sqlalchemy import event

from api.bullpen import _board_records_from_authority_records
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.sync_run import SyncRun
from services import bullpen_board as bullpen_board_service
from services import dashboard_snapshot
from services import public_serving_authority
from services import public_team_relief_work
from services import sync as sync_service
from services.availability_population import current_availability_records
from services.availability_snapshot import latest_fatigue_rows
from services.public_fatigue_view import PUBLIC_WORKLOAD_FACT_FIELDS, public_workload_facts
from tests.db_config import (
    create_test_schema,
    drop_test_schema,
    test_database_url as _test_database_url,
)
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db
from utils.time import utc_now_naive


TEAM_ID = 116
OTHER_TEAM_ID = 134
ZERO_TEAM_ID = 135


def _complete_slate_coverage(slate_date):
    return {
        'slate_date': slate_date.isoformat(),
        'games_scheduled': 0,
        'games_final': 0,
        'games_fully_ingested': 0,
        'games_incomplete': 0,
        'games_failed': 0,
        'games_postponed': 0,
        'games_suspended': 0,
        'games_included': 0,
        'validations_passed': True,
        'complete_enough_to_publish': True,
        'coverage_known': True,
        'reason_codes': ['no_scheduled_games', 'slate_complete'],
        'degradation_reasons': [],
        'marker_counts': {
            'fully_processed': 0,
            'incomplete': 0,
            'failed': 0,
            'missing': 0,
        },
    }


def _dashboard_payload(reference_date):
    data_through = reference_date - timedelta(days=1)
    coverage = _complete_slate_coverage(data_through)
    return {
        'capability': 'bullpen_dashboard',
        'generated_at': utc_now_naive().isoformat(),
        'ranking_applied': False,
        'selection_made': False,
        'scope': 'bullpen_eligible',
        'context': {},
        'roles': {'order': [], 'counts': {}, 'total': 0},
        'landscape': {},
        'freshness': {
            'data_through': data_through.isoformat(),
            'latest_workload_date': data_through.isoformat(),
            'availability_reference_date': reference_date.isoformat(),
            'reference_date': reference_date.isoformat(),
            'sync_status': 'success',
            'last_successful_sync': utc_now_naive().isoformat(),
            'slate_coverage': coverage,
            'validations_passed': True,
            'complete_enough_to_publish': True,
        },
        'availability_summary': {},
    }


def _seed_pitcher_with_workload(
    reference_date,
    *,
    mlb_id=5116001,
    full_name='Trusted Workload Arm',
    team_id=TEAM_ID,
    team_name='Detroit Tigers',
    team_abbreviation='DET',
    days_since_last_appearance=2,
    appearances_last_7=3,
    appearances_last_14=5,
    pitches_last_7_days=41,
    innings_last_7_days=3.0,
    with_score=True,
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=full_name,
        team_id=team_id,
        team_name=team_name,
        team_abbreviation=team_abbreviation,
        position='P',
        active=True,
        roster_status='active',
        roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(pitcher)
    db.session.flush()
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=90000000 + mlb_id,
        game_date=reference_date - timedelta(days=days_since_last_appearance),
        game_type='R',
        games_started=0,
        innings_pitched=1.0,
        innings_pitched_outs=3,
        pitches_thrown=18,
    ))
    score = None
    if with_score:
        score = FatigueScore(
            pitcher_id=pitcher.id,
            calculated_at=utc_now_naive(),
            raw_score=19.0,
            pitch_count_score=11.0,
            rest_days_score=9.0,
            appearances_score=13.0,
            leverage_score=7.0,
            innings_score=8.0,
            days_since_last_appearance=days_since_last_appearance,
            appearances_last_7=appearances_last_7,
            appearances_last_14=appearances_last_14,
            pitches_last_7_days=pitches_last_7_days,
            innings_last_7_days=innings_last_7_days,
            risk_level='LOW',
        )
        db.session.add(score)
    db.session.commit()
    if score is not None and pitches_last_7_days is None:
        score.pitches_last_7_days = None
        db.session.commit()
    return pitcher, score


@pytest.fixture
def trusted_app(tmp_path, monkeypatch):
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', _test_database_url())
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    app_module = importlib.import_module('app')
    app = app_module.create_app('test')
    app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True

    with app.app_context():
        create_test_schema(app)
        try:
            reference_date = public_serving_authority.product_current_date()
            pitcher, score = _seed_pitcher_with_workload(reference_date)
            other_pitcher, other_score = _seed_pitcher_with_workload(
                reference_date,
                mlb_id=5134001,
                full_name='Trusted Null Pitch Arm',
                team_id=OTHER_TEAM_ID,
                team_name='Pittsburgh Pirates',
                team_abbreviation='PIT',
                days_since_last_appearance=1,
                appearances_last_7=2,
                appearances_last_14=4,
                pitches_last_7_days=None,
                innings_last_7_days=2.0,
            )
            unscored_pitcher, _ = _seed_pitcher_with_workload(
                reference_date,
                mlb_id=5116002,
                full_name='Trusted Unscored Arm',
                days_since_last_appearance=3,
                with_score=False,
            )
            zero_pitcher, zero_score = _seed_pitcher_with_workload(
                reference_date,
                mlb_id=5135001,
                full_name='Trusted Zero Rest Arm',
                team_id=ZERO_TEAM_ID,
                team_name='San Diego Padres',
                team_abbreviation='SD',
                days_since_last_appearance=1,
                appearances_last_7=1,
                appearances_last_14=2,
                pitches_last_7_days=18,
                innings_last_7_days=1.0,
            )
            seed_roster_readiness_snapshots([reference_date])

            from api import bullpen as bullpen_api

            monkeypatch.setattr(
                bullpen_api,
                'build_bullpen_dashboard_payload',
                lambda **_kwargs: _dashboard_payload(reference_date),
            )
            assert public_serving_authority.install_public_serving_authority(app) is True

            run = SyncRun(
                job_name='trusted_workload_test',
                started_at=utc_now_naive() - timedelta(minutes=2),
                completed_at=utc_now_naive() - timedelta(minutes=1),
                status='success',
                stage='published',
                source='test',
                latest_game_date=reference_date - timedelta(days=1),
                latest_workload_date=reference_date - timedelta(days=1),
                latest_fatigue_calculated_at=utc_now_naive(),
            )
            db.session.add(run)
            db.session.flush()
            rest_status_calls = []
            relief_authority_calls = []
            original_build_rest_status = bullpen_board_service.build_rest_status
            original_author_public_team_relief_authority = (
                public_serving_authority.author_public_team_relief_authority
            )

            def tracked_build_rest_status(*args, **kwargs):
                rest_status_calls.append((args, kwargs))
                return original_build_rest_status(*args, **kwargs)

            monkeypatch.setattr(
                bullpen_board_service,
                'build_rest_status',
                tracked_build_rest_status,
            )

            def tracked_author_public_team_relief_authority(*args, **kwargs):
                relief_authority_calls.append((args, kwargs))
                return original_author_public_team_relief_authority(*args, **kwargs)

            monkeypatch.setattr(
                public_serving_authority,
                'author_public_team_relief_authority',
                tracked_author_public_team_relief_authority,
            )
            snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
                sync_run_id=run.id,
                source='trusted_workload_test',
                publish=True,
                raise_errors=True,
            )
            assert snapshot.is_published is True
            yield {
                'app': app,
                'pitcher': pitcher,
                'score': score,
                'other_pitcher': other_pitcher,
                'other_score': other_score,
                'unscored_pitcher': unscored_pitcher,
                'zero_pitcher': zero_pitcher,
                'zero_score': zero_score,
                'snapshot': snapshot,
                'reference_date': reference_date,
                'rest_status_calls': rest_status_calls,
                'relief_authority_calls': relief_authority_calls,
            }
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_trusted_public_board_endpoint_serves_frozen_workload_facts_and_rest_status(
    trusted_app,
):
    app = trusted_app['app']
    pitcher = trusted_app['pitcher']
    snapshot = trusted_app['snapshot']

    response = app.test_client().get(f'/api/bullpen/teams/{TEAM_ID}/board')
    assert response.status_code == 200
    body = response.get_json()
    cards = [card for group in body['groups'] for card in group['pitchers']]
    card = next(item for item in cards if item['pitcher_id'] == pitcher.id)

    assert body['served_from'] == 'trusted_dashboard_snapshot'
    assert body['publication_authority']['snapshot_id'] == snapshot.id
    assert (
        body['rest_status']['available'],
        body['rest_status']['reason_code'],
    ) == (True, None)
    assert card['workload_facts'] == {
        'days_since_last_appearance': 2,
        'appearances_last_7': 3,
        'pitches_last_7_days': 41,
        'back_to_back': False,
    }


def _snapshot_copy(snapshot, **overrides):
    values = {
        'id': snapshot.id,
        'snapshot_type': snapshot.snapshot_type,
        'sync_run_id': snapshot.sync_run_id,
        'status': snapshot.status,
        'is_published': snapshot.is_published,
        'published_at': snapshot.published_at,
        'payload': deepcopy(snapshot.payload),
        'data_through': snapshot.data_through,
        'availability_reference_date': snapshot.availability_reference_date,
        'snapshot_generated_at': snapshot.snapshot_generated_at,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_phase1_publication_authors_one_d055_carrier_per_team(trusted_app):
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]

    assert len(trusted_app['rest_status_calls']) == package['team_count']
    assert public_serving_authority.qualify_rest_status_carrier(snapshot) == {
        'qualified': True,
        'reason_code': public_serving_authority.REST_STATUS_CARRIER_QUALIFIED,
        'snapshot': public_serving_authority.publication_authority(snapshot),
        'represented_date': snapshot.data_through.isoformat(),
        'represented_team_count': package['team_count'],
        'qualified_team_count': package['team_count'],
        'failed_team_id': None,
    }

    positive = package['by_team_id'][str(TEAM_ID)]['rest_status']
    zero = package['by_team_id'][str(ZERO_TEAM_ID)]['rest_status']
    assert positive['rested_arm_count'] > 0
    assert zero['available'] is True
    assert zero['rested_arm_count'] == 0


def test_workload_windows_are_authored_once_and_frozen_with_publication_authority(
    trusted_app,
):
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]

    assert len(trusted_app['relief_authority_calls']) == package['team_count']
    for team in package['by_team_id'].values():
        carrier = team['workload_windows']
        authority = team['workload_windows_authority']
        assert carrier['status'] == public_team_relief_work.WORKLOAD_WINDOWS_COMPLETE
        assert carrier['data_through'] == snapshot.data_through.isoformat()
        assert set(carrier['windows']) == {'window_7', 'window_14'}
        assert authority == {
            'method_version': (
                public_team_relief_work.WORKLOAD_WINDOWS_METHOD_VERSION
            ),
            'public_contract_version': (
                public_team_relief_work.WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
            ),
            'team_board_package_contract': (
                public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT
            ),
            'population_basis': {
                'basis': (
                    public_team_relief_work.WORKLOAD_WINDOWS_POPULATION_BASIS
                ),
                'population_authority': (
                    public_team_relief_work.WORKLOAD_WINDOWS_POPULATION_AUTHORITY
                ),
                'membership_authority': (
                    public_team_relief_work.WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY
                ),
            },
            'reference_date_policy': (
                public_team_relief_work.WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
            ),
            'data_through': snapshot.data_through.isoformat(),
        }
        assert team['bullpen_membership_authority'] == {
            'method_version': public_serving_authority.BULLPEN_MEMBERSHIP_METHOD_VERSION,
            'public_contract_version': public_serving_authority.BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION,
            'carrier_contract_version': public_serving_authority.BULLPEN_MEMBERSHIP_CARRIER_CONTRACT,
            'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
            'population_basis': {
                'basis': public_serving_authority.BULLPEN_MEMBERSHIP_POPULATION_BASIS,
                'population_authority': public_serving_authority.BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY,
                'membership_authority': public_serving_authority.BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY,
                'roster_authority_version': '2026-06-25.foundation',
            },
            'reference_date_policy': public_serving_authority.BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY,
            'membership_reference_date': trusted_app['reference_date'].isoformat(),
        }


def test_frozen_workload_windows_match_the_canonical_public_owner(trusted_app):
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    calls_before = len(trusted_app['relief_authority_calls'])

    for team_id, team in package['by_team_id'].items():
        direct = public_team_relief_work.author_workload_windows(
            int(team_id),
            data_through=snapshot.data_through,
        )
        assert team['workload_windows'] == direct

    # Direct parity probes above use the canonical owner, not the publication
    # wrapper tracked by this fixture. The package itself authored once/team.
    assert len(trusted_app['relief_authority_calls']) == calls_before


def test_deployment_profiles_are_authored_once_and_frozen_with_authority(trusted_app):
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]

    assert len(trusted_app['relief_authority_calls']) == package['team_count']
    for team_id, team in package['by_team_id'].items():
        carrier = team['deployment_profile']
        authority = team['deployment_profile_authority']
        assert carrier == public_team_relief_work.author_deployment_profile(
            int(team_id),
            data_through=snapshot.data_through,
        )
        assert authority == {
            'method_version': public_team_relief_work.DEPLOYMENT_PROFILE_METHOD_VERSION,
            'public_contract_version': (
                public_team_relief_work.DEPLOYMENT_PROFILE_PUBLIC_CONTRACT_VERSION
            ),
            'carrier_contract_version': (
                public_team_relief_work.DEPLOYMENT_PROFILE_CARRIER_CONTRACT
            ),
            'team_board_package_contract': (
                public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT
            ),
            'population_basis': {
                'basis': public_team_relief_work.DEPLOYMENT_PROFILE_POPULATION_BASIS,
                'population_authority': (
                    public_team_relief_work.DEPLOYMENT_PROFILE_POPULATION_AUTHORITY
                ),
                'membership_authority': (
                    public_team_relief_work.DEPLOYMENT_PROFILE_MEMBERSHIP_AUTHORITY
                ),
            },
            'reference_date_policy': (
                public_team_relief_work.DEPLOYMENT_PROFILE_REFERENCE_DATE_POLICY
            ),
            'data_through': snapshot.data_through.isoformat(),
        }


def test_phase1_governed_unavailable_carrier_is_valid_and_qualifies(trusted_app):
    snapshot = _snapshot_copy(trusted_app['snapshot'])
    team = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY][
        'by_team_id'
    ][str(OTHER_TEAM_ID)]
    unavailable = bullpen_board_service.author_rest_status(
        [],
        freshness={'fail_closed': True},
        roster_authority={},
    )
    team['rest_status'] = deepcopy(unavailable)

    result = public_serving_authority.qualify_rest_status_carrier(snapshot)

    assert unavailable == {
        'available': False,
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'summary': None,
        'reason_code': bullpen_board_service.REST_STATUS_BOARD_CONTEXT_UNAVAILABLE,
    }
    assert result['qualified'] is True


def test_phase1_frozen_carrier_matches_direct_canonical_d055(trusted_app):
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    team = package['by_team_id'][str(TEAM_ID)]
    default_ids = set(team['default_pitcher_ids'])
    records = [
        record for record in team['records']
        if record['pitcher_id'] in default_ids
    ]

    direct = bullpen_board_service.author_rest_status(
        records,
        freshness=snapshot.payload['freshness'],
        roster_authority=team['roster_authority'],
    )

    assert team['rest_status'] == direct


def test_phase1_carrier_stamps_exact_authority(trusted_app):
    package = trusted_app['snapshot'].payload[
        public_serving_authority.TEAM_BOARD_PACKAGE_KEY
    ]
    for team in package['by_team_id'].values():
        assert team['rest_status_authority'] == {
            'method_version': bullpen_board_service.REST_STATUS_METHOD_VERSION,
            'public_contract_version': (
                bullpen_board_service.REST_STATUS_PUBLIC_CONTRACT_VERSION
            ),
            'team_board_package_contract': (
                public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT
            ),
            'population_basis': {
                'basis': public_serving_authority.REST_STATUS_POPULATION_BASIS,
                'population_authority': (
                    public_serving_authority.REST_STATUS_POPULATION_AUTHORITY
                ),
                'membership_authority': (
                    public_serving_authority.REST_STATUS_MEMBERSHIP_AUTHORITY
                ),
            },
            'reference_date_policy': (
                public_serving_authority.REST_STATUS_REFERENCE_DATE_POLICY
            ),
            'availability_reference_date': trusted_app['reference_date'].isoformat(),
        }


def _forbid_trusted_d055_reauthoring(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('trusted reader attempted request-time D-055 authoring')

    monkeypatch.setattr(bullpen_board_service, 'build_rest_status', forbidden)
    monkeypatch.setattr(bullpen_board_service, 'author_rest_status', forbidden)
    monkeypatch.setattr(public_serving_authority, 'author_rest_status', forbidden)


def test_phase2_board_and_board_v2_share_frozen_carrier_without_reauthoring(
    trusted_app,
    monkeypatch,
):
    app = trusted_app['app']
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    frozen = deepcopy(package['by_team_id'][str(TEAM_ID)]['rest_status'])
    calls_after_publication = len(trusted_app['rest_status_calls'])
    _forbid_trusted_d055_reauthoring(monkeypatch)

    client = app.test_client()
    reads = [
        client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json(),
        client.get(f'/api/bullpen/teams/{TEAM_ID}/board-v2').get_json(),
        client.get(f'/api/bullpen/teams/{TEAM_ID}/board-v2').get_json(),
        client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json(),
    ]

    assert [read['rest_status'] for read in reads] == [frozen] * 4
    assert len(trusted_app['rest_status_calls']) == calls_after_publication


def test_phase2_governed_unavailable_is_verbatim_across_both_routes(
    trusted_app,
    monkeypatch,
):
    package = trusted_app['snapshot'].payload[
        public_serving_authority.TEAM_BOARD_PACKAGE_KEY
    ]
    frozen_team = deepcopy(package['by_team_id'][str(TEAM_ID)])
    frozen_team['rest_status'] = {
        'available': False,
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'summary': None,
        'reason_code': bullpen_board_service.REST_STATUS_WORKLOAD_EVIDENCE_INCOMPLETE,
    }
    monkeypatch.setattr(
        public_serving_authority,
        '_team_package',
        lambda _snapshot, _team_id: (frozen_team, None),
    )
    _forbid_trusted_d055_reauthoring(monkeypatch)

    client = trusted_app['app'].test_client()
    board = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
    board_v2 = client.get(f'/api/bullpen/teams/{TEAM_ID}/board-v2').get_json()

    assert board['rest_status'] == frozen_team['rest_status']
    assert board_v2['rest_status'] == frozen_team['rest_status']


def test_phase2_zero_and_positive_counts_remain_exact_across_both_routes(
    trusted_app,
    monkeypatch,
):
    package = trusted_app['snapshot'].payload[
        public_serving_authority.TEAM_BOARD_PACKAGE_KEY
    ]
    _forbid_trusted_d055_reauthoring(monkeypatch)
    client = trusted_app['app'].test_client()

    for team_id, expected_rested in ((TEAM_ID, 1), (ZERO_TEAM_ID, 0)):
        frozen = package['by_team_id'][str(team_id)]['rest_status']
        board = client.get(f'/api/bullpen/teams/{team_id}/board').get_json()
        board_v2 = client.get(f'/api/bullpen/teams/{team_id}/board-v2').get_json()
        assert frozen['rested_arm_count'] == expected_rested
        assert board['rest_status'] == frozen
        assert board_v2['rest_status'] == frozen


@pytest.mark.parametrize(
    ('mutation', 'expected_reason'),
    (
        (
            lambda team: (team.pop('rest_status', None), team.pop('rest_status_authority', None)),
            bullpen_board_service.REST_STATUS_FROZEN_VALUE_MISSING,
        ),
        (
            lambda team: team['rest_status_authority'].__setitem__(
                'method_version', 'wrong_method'
            ),
            bullpen_board_service.REST_STATUS_FROZEN_VALUE_INVALID,
        ),
        (
            lambda team: team['rest_status'].__setitem__('rested_arm_count', None),
            bullpen_board_service.REST_STATUS_FROZEN_VALUE_INVALID,
        ),
    ),
)
def test_phase2_legacy_or_invalid_carrier_fails_closed_on_both_routes(
    trusted_app,
    monkeypatch,
    mutation,
    expected_reason,
):
    package = trusted_app['snapshot'].payload[
        public_serving_authority.TEAM_BOARD_PACKAGE_KEY
    ]
    frozen_team = deepcopy(package['by_team_id'][str(TEAM_ID)])
    mutation(frozen_team)
    before = deepcopy(frozen_team)
    monkeypatch.setattr(
        public_serving_authority,
        '_team_package',
        lambda _snapshot, _team_id: (frozen_team, None),
    )
    _forbid_trusted_d055_reauthoring(monkeypatch)

    client = trusted_app['app'].test_client()
    board = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
    board_v2 = client.get(f'/api/bullpen/teams/{TEAM_ID}/board-v2').get_json()

    expected = {
        'available': False,
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'summary': None,
        'reason_code': expected_reason,
    }
    assert board['rest_status'] == expected
    assert board_v2['rest_status'] == expected
    assert frozen_team == before


def test_phase2_live_workload_changes_cannot_refresh_frozen_rest_status(
    trusted_app,
    monkeypatch,
):
    package = trusted_app['snapshot'].payload[
        public_serving_authority.TEAM_BOARD_PACKAGE_KEY
    ]
    frozen = deepcopy(package['by_team_id'][str(TEAM_ID)]['rest_status'])
    trusted_app['score'].days_since_last_appearance = 0
    trusted_app['score'].appearances_last_7 = 99
    trusted_app['score'].pitches_last_7_days = 999
    db.session.commit()
    _forbid_trusted_d055_reauthoring(monkeypatch)

    client = trusted_app['app'].test_client()
    board = client.get(f'/api/bullpen/teams/{TEAM_ID}/board').get_json()
    board_v2 = client.get(f'/api/bullpen/teams/{TEAM_ID}/board-v2').get_json()

    assert board['rest_status'] == frozen
    assert board_v2['rest_status'] == frozen


def test_workload_window_carrier_is_dormant_for_board_and_board_v2(trusted_app):
    app = trusted_app['app']
    package = trusted_app['snapshot'].payload[
        public_serving_authority.TEAM_BOARD_PACKAGE_KEY
    ]
    publication_calls = len(trusted_app['relief_authority_calls'])

    board_before = app.test_client().get(
        f'/api/bullpen/teams/{TEAM_ID}/board'
    ).get_json()
    v2_before = app.test_client().get(
        f'/api/bullpen/teams/{TEAM_ID}/board-v2'
    ).get_json()

    team = package['by_team_id'][str(TEAM_ID)]
    team.pop('workload_windows')
    team.pop('workload_windows_authority')

    board_after = app.test_client().get(
        f'/api/bullpen/teams/{TEAM_ID}/board'
    ).get_json()
    v2_after = app.test_client().get(
        f'/api/bullpen/teams/{TEAM_ID}/board-v2'
    ).get_json()

    assert board_after == board_before
    assert v2_after['workload_overview'] == v2_before['workload_overview']
    assert v2_after['recent_relief_work'] == v2_before['recent_relief_work']
    assert len(trusted_app['relief_authority_calls']) == publication_calls


@pytest.mark.parametrize(
    ('mutate', 'reason_code'),
    (
        (
            lambda snapshot: snapshot.payload[
                public_serving_authority.TEAM_BOARD_PACKAGE_KEY
            ]['by_team_id'][str(TEAM_ID)].pop('rest_status'),
            public_serving_authority.REST_STATUS_CARRIER_TEAM_MISSING,
        ),
        (
            lambda snapshot: snapshot.payload[
                public_serving_authority.TEAM_BOARD_PACKAGE_KEY
            ]['by_team_id'][str(TEAM_ID)]['rest_status_authority'].__setitem__(
                'method_version', 'future_method'
            ),
            public_serving_authority.REST_STATUS_CARRIER_AUTHORITY_INVALID,
        ),
        (
            lambda snapshot: snapshot.payload[
                public_serving_authority.TEAM_BOARD_PACKAGE_KEY
            ]['by_team_id'][str(TEAM_ID)].pop('rest_status_authority'),
            public_serving_authority.REST_STATUS_CARRIER_AUTHORITY_INVALID,
        ),
        (
            lambda snapshot: snapshot.payload[
                public_serving_authority.TEAM_BOARD_PACKAGE_KEY
            ]['by_team_id'][str(TEAM_ID)]['rest_status'].__setitem__(
                'rested_arm_count', None
            ),
            public_serving_authority.REST_STATUS_CARRIER_VALUE_INVALID,
        ),
        (
            lambda snapshot: snapshot.payload[
                public_serving_authority.TEAM_BOARD_PACKAGE_KEY
            ]['by_team_id'][str(TEAM_ID)]['rest_status'].__setitem__(
                'unexpected', True
            ),
            public_serving_authority.REST_STATUS_CARRIER_VALUE_INVALID,
        ),
    ),
)
def test_phase1_qualification_rejects_incomplete_carriers_deterministically(
    trusted_app,
    mutate,
    reason_code,
):
    snapshot = _snapshot_copy(trusted_app['snapshot'])
    mutate(snapshot)

    result = public_serving_authority.qualify_rest_status_carrier(snapshot)

    assert result['qualified'] is False
    assert result['reason_code'] == reason_code
    assert result['failed_team_id'] == TEAM_ID


def test_phase1_qualification_rejects_unpublished_candidate(trusted_app):
    snapshot = _snapshot_copy(
        trusted_app['snapshot'],
        is_published=False,
        published_at=None,
    )

    result = public_serving_authority.qualify_rest_status_carrier(snapshot)

    assert result['qualified'] is False
    assert result['reason_code'] == (
        public_serving_authority.REST_STATUS_CARRIER_SNAPSHOT_UNPUBLISHED
    )


def test_phase1_qualification_is_read_only_and_does_not_backfill(trusted_app):
    snapshot = _snapshot_copy(trusted_app['snapshot'])
    team = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY][
        'by_team_id'
    ][str(TEAM_ID)]
    team.pop('rest_status')
    before = deepcopy(snapshot.payload)

    first = public_serving_authority.qualify_rest_status_carrier(snapshot)
    second = public_serving_authority.qualify_rest_status_carrier(snapshot)
    first['qualified_team_count'] = 999

    assert snapshot.payload == before
    assert second['qualified'] is False
    assert second['qualified_team_count'] != 999


def test_phase1_valid_qualification_does_not_reauthor_or_mutate_carrier(trusted_app):
    snapshot = trusted_app['snapshot']
    calls_before = len(trusted_app['rest_status_calls'])
    payload_before = deepcopy(snapshot.payload)

    first = public_serving_authority.qualify_rest_status_carrier(snapshot)
    second = public_serving_authority.qualify_rest_status_carrier(snapshot)
    first['snapshot']['snapshot_id'] = 999

    assert first['qualified'] is True
    assert second['qualified'] is True
    assert second['snapshot']['snapshot_id'] == snapshot.id
    assert len(trusted_app['rest_status_calls']) == calls_before
    assert snapshot.payload == payload_before


def test_frozen_team_board_package_carries_exact_public_projection_and_nulls(trusted_app):
    snapshot = trusted_app['snapshot']
    package = snapshot.payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    records = {
        record['pitcher_id']: record
        for team in package['by_team_id'].values()
        for record in team['records']
    }

    assert records[trusted_app['pitcher'].id]['workload_facts'] == public_workload_facts(
        trusted_app['score']
    )
    assert records[trusted_app['other_pitcher'].id]['workload_facts'] == public_workload_facts(
        trusted_app['other_score']
    )
    assert records[trusted_app['other_pitcher'].id]['workload_facts'][
        'pitches_last_7_days'
    ] is None
    assert records[trusted_app['unscored_pitcher'].id]['workload_facts'] is None
    assert json.dumps(package)


def test_live_and_frozen_board_records_match_on_workload_facts(trusted_app):
    reference_date = trusted_app['reference_date']
    authority_records = current_availability_records(
        latest_fatigue_rows(),
        reference_date=reference_date,
    )
    live_records, _ = _board_records_from_authority_records(
        authority_records,
        reference_date=reference_date,
    )
    live_by_pitcher = {record['pitcher_id']: record for record in live_records}

    package = trusted_app['snapshot'].payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    frozen_by_pitcher = {
        record['pitcher_id']: record
        for team in package['by_team_id'].values()
        for record in team['records']
    }

    for pitcher_id, live_record in live_by_pitcher.items():
        assert frozen_by_pitcher[pitcher_id]['workload_facts'] == live_record['workload_facts']


def test_trusted_compare_retains_workload_facts_for_both_teams(trusted_app):
    response = trusted_app['app'].test_client().get(
        f'/api/bullpen/teams/compare?team_a={TEAM_ID}&team_b={OTHER_TEAM_ID}'
    )
    assert response.status_code == 200
    body = response.get_json()

    for side, pitcher, expected_days, expected_appearances, expected_pitches in (
        ('team_a', trusted_app['pitcher'], 2, 3, 41),
        ('team_b', trusted_app['other_pitcher'], 1, 2, None),
    ):
        board = body[side]
        cards = [card for group in board['groups'] for card in group['pitchers']]
        card = next(item for item in cards if item['pitcher_id'] == pitcher.id)
        assert board['served_from'] == 'trusted_dashboard_snapshot'
        assert card['workload_facts']['days_since_last_appearance'] == expected_days
        assert card['workload_facts']['appearances_last_7'] == expected_appearances
        assert card['workload_facts']['pitches_last_7_days'] == expected_pitches
        assert isinstance(card['workload_facts']['back_to_back'], bool)


def _all_keys(value):
    if isinstance(value, dict):
        yield from value.keys()
        for child in value.values():
            yield from _all_keys(child)
    elif isinstance(value, list):
        for child in value:
            yield from _all_keys(child)


def test_trusted_team_board_response_and_workload_projection_do_not_leak_scores(trusted_app):
    body = trusted_app['app'].test_client().get(
        f'/api/bullpen/teams/{TEAM_ID}/board'
    ).get_json()
    forbidden = {
        'raw_score',
        'fatigue_score',
        'risk_level',
        'usage_score',
        'recovery_score',
        'workload_score',
        'breakdown',
        'breakdowns',
        'subscores',
        'pitch_count_score',
        'rest_days_score',
        'appearances_score',
        'leverage_score',
        'innings_score',
    }
    assert forbidden.isdisjoint(set(_all_keys(body)))

    package = trusted_app['snapshot'].payload[public_serving_authority.TEAM_BOARD_PACKAGE_KEY]
    record = next(
        record
        for team in package['by_team_id'].values()
        for record in team['records']
        if record['pitcher_id'] == trusted_app['pitcher'].id
    )
    assert set(record['workload_facts']) == {'calculated_at', *PUBLIC_WORKLOAD_FACT_FIELDS}


def test_public_workload_projection_executes_no_sql(trusted_app):
    score = trusted_app['score']
    expected = public_workload_facts(score)
    statements = []

    def capture(_conn, _cursor, statement, _params, _context, _executemany):
        statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        assert public_workload_facts(score) == expected
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)

    assert statements == []


def test_trusted_package_contract_and_dashboard_payload_version_are_unchanged():
    assert (
        public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT
        == 'trusted_team_board_publication_v1'
    )
    assert dashboard_snapshot.DASHBOARD_PAYLOAD_VERSION == 1
