from copy import deepcopy
from datetime import date, datetime, timedelta

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from sqlalchemy import inspect

import services.sync as sync_service
from models.fatigue_score import FatigueScore
from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.share_artifact import ShareArtifact
from models.sync_run import SyncRun
import models.prospect  # noqa: F401  (register on db.metadata)
from services.availability import ACTIVE_WINDOW_DAYS
from services import team_board_delta_substrate as delta_substrate
from services.roster_status import STATUS_ACTIVE
from services.team_state_public_vocabulary import PUBLIC_TEAM_STATE_CONTRACT
from team_operations import TEAM_STATE_METHOD_VERSION
from api.bullpen import bullpen_bp
from utils.db import db


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')

    app = Flask(__name__)
    configure_test_database(app)
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    app.register_blueprint(bullpen_bp, url_prefix='/api/bullpen')

    @app.before_request
    def _seed_ready_roster_snapshots_for_team_change_tests():
        seed_roster_readiness_snapshots()

    with app.app_context():
        create_test_schema(app)
        try:
            yield app.test_client()
        finally:
            db.session.remove()
            drop_test_schema(app)


def _pitcher(
    name,
    mlb_id,
    team_id=1,
    active=True,
    position='P',
    roster_status=STATUS_ACTIVE,
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name='Test Club',
        team_abbreviation='TST',
        position=position,
        active=active,
        roster_status=roster_status,
        roster_status_source='test_fixture' if roster_status else None,
        roster_status_updated_at=datetime.utcnow() if roster_status else None,
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _log(pitcher, game_date, game_pk, pitches=12, innings=1.0, hold=False, save=False):
    db.session.add(GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        pitches_thrown=pitches,
        innings_pitched=innings,
        innings_pitched_outs=round(innings * 3),
        games_started=1 if innings >= 3 else 0,
        hold=hold,
        save=save,
        game_type='R',
    ))
    _seed_complete_slate_game(pitcher.team_id or 1, game_date, game_pk)
    db.session.commit()


def _seed_complete_slate_game(team_id, game_date, game_pk):
    opponent_id = 900000 + int(team_id)
    if ScheduledGame.query.filter_by(team_id=team_id, game_pk=game_pk).first() is None:
        db.session.add_all([
            ScheduledGame(
                team_id=team_id,
                game_pk=game_pk,
                game_date=game_date,
                status_state='final',
                home_away='home',
                opponent_team_id=opponent_id,
            ),
            ScheduledGame(
                team_id=opponent_id,
                game_pk=game_pk,
                game_date=game_date,
                status_state='final',
                home_away='away',
                opponent_team_id=team_id,
            ),
        ])
    if PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).first() is None:
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk,
            game_date=game_date,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))


def _score(pitcher, raw_score, calculated_on, hour=12):
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id,
        calculated_at=datetime(
            calculated_on.year,
            calculated_on.month,
            calculated_on.day,
            hour,
            0,
            0,
        ),
        raw_score=raw_score,
        risk_level='LOW',
    ))
    db.session.commit()


def _successful_sync(game_date, started_offset=0):
    synced_at = datetime.utcnow() + timedelta(minutes=started_offset)
    db.session.add(SyncRun(
        started_at=synced_at - timedelta(seconds=40),
        completed_at=synced_at,
        status='success',
        source='github_actions',
        latest_game_date=game_date,
        latest_workload_date=game_date,
        latest_fatigue_calculated_at=synced_at,
        records_processed=12,
        new_logs_added=2,
        pitchers_updated=2,
        errors=0,
        created_at=synced_at - timedelta(seconds=40),
    ))
    db.session.commit()


def _failed_sync(started_offset=5):
    failed_at = datetime.utcnow() + timedelta(minutes=started_offset)
    db.session.add(SyncRun(
        started_at=failed_at,
        completed_at=failed_at + timedelta(seconds=20),
        status='failed',
        source='github_actions',
        errors=1,
        error_message='MLB API unavailable',
        created_at=failed_at,
    ))
    db.session.commit()


def _recent_dates():
    current = date.today() - timedelta(days=1)
    anchor = current - timedelta(days=1)
    return anchor, current


def _team_state_sidecar(
    represented_date,
    state,
    label,
    *,
    team_id=1,
    artifact_id,
    method_version=TEAM_STATE_METHOD_VERSION,
    public_contract_version=PUBLIC_TEAM_STATE_CONTRACT,
    population_basis=None,
    trusted=True,
    rested_arm_count=None,
    arm_read_capture=None,
):
    population_basis = population_basis or {
        'basis': 'status_only',
        'population_authority': 'resolve_readiness_population',
        'membership_authority': 'resolve_active_bullpen_membership',
    }
    published_at = datetime.combine(represented_date, datetime.min.time())
    db.session.add(ShareArtifact(
        id=artifact_id,
        public_id=f'team-state-{artifact_id}',
        artifact_type='team_state',
        render_version='team-state-1.2.0',
        team_id=team_id,
        source_snapshot_id=1000 + artifact_id,
        product_date=represented_date,
        lifecycle_state='published',
        payload={},
        trust_metadata={},
        equivalence_key=f'team-state-{artifact_id}',
        integrity_hash=f'integrity-{artifact_id}',
        source='test',
        published_at=published_at,
    ))
    domains = {
        'team_state': {
            'method_version': method_version,
            'contract_version': TEAM_STATE_METHOD_VERSION,
            'public_contract_version': public_contract_version,
            'population_basis': population_basis,
            'trust_state': 'trusted',
            'trust_data_state': 'current',
            'freshness_state': 'current',
            'trusted': trusted,
        },
    }
    values = {
        'team_state': {
            'public_state': state,
            'public_label': label,
        },
    }
    if rested_arm_count is not None:
        domains['rest_status'] = {
            'method_version': delta_substrate.REST_STATUS_METHOD_VERSION,
            'contract_version': delta_substrate.TEAM_BOARD_PACKAGE_CONTRACT,
            'public_contract_version': delta_substrate.REST_STATUS_PUBLIC_CONTRACT_VERSION,
            'population_basis': delta_substrate._canonical_rest_status_population_basis(),
            'reference_date_policy': delta_substrate.REST_STATUS_REFERENCE_DATE_POLICY,
            'availability_reference_date': (represented_date + timedelta(days=1)).isoformat(),
            'source_authority': delta_substrate.FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
            'trusted': trusted,
        }
        values['rest_status'] = {
            'available': True,
            'active_arm_count': 8,
            'rested_arm_count': rested_arm_count,
            'worked_yesterday_count': 2,
            'back_to_back_count': 1,
            'summary': f'{rested_arm_count} rested options.',
            'reason_code': None,
        }
    if arm_read_capture is not None:
        domains['arm_read'] = {
            'method_version': arm_read_capture.get('method_version'),
            'public_contract_version': arm_read_capture.get('public_contract_version'),
            'population_basis': deepcopy(arm_read_capture.get('population_basis')),
            'membership_reference_date': arm_read_capture.get('membership_reference_date'),
            'availability_reference_date': arm_read_capture.get('availability_reference_date'),
            'trusted': arm_read_capture.get('trusted', trusted),
        }
        values['arm_read'] = {
            'member_pitcher_ids': deepcopy(
                arm_read_capture.get('member_pitcher_ids') or []
            ),
            'missing_record_pitcher_ids': deepcopy(
                arm_read_capture.get('missing_record_pitcher_ids') or []
            ),
            'records': deepcopy(arm_read_capture.get('records') or []),
        }
    row = DashboardSnapshot(
        snapshot_type=delta_substrate.SNAPSHOT_TYPE,
        status='ready',
        is_published=False,
        published_at=published_at,
        payload_version=delta_substrate.SNAPSHOT_PAYLOAD_VERSION,
        data_through=represented_date,
        snapshot_generated_at=datetime.combine(represented_date, datetime.min.time()),
        source=f'{delta_substrate.SNAPSHOT_SOURCE_PREFIX}{team_id}',
        payload={
            'capability': delta_substrate.CAPABILITY,
            'envelope_version': delta_substrate.ENVELOPE_VERSION,
            'team_id': team_id,
            'represented_date': represented_date.isoformat(),
            'source': {
                'frozen_value_source': 'team_state_share_artifact',
                'artifact_id': artifact_id,
                'artifact_payload_version': 'team-state-1.2.0',
                'snapshot_authority': 'dashboard_snapshot',
                'snapshot_id': 1000 + artifact_id,
                'sync_run_id': artifact_id,
                'subject_key': None,
            },
            'domains': domains,
            'values': values,
        },
    )
    db.session.add(row)
    db.session.commit()
    return row


def _governed_arm_read_capture(
    represented_date,
    pitcher_reads,
    *,
    member_pitchers=None,
    missing_pitchers=(),
    method_version=delta_substrate.ARM_READ_METHOD_VERSION,
    public_contract_version=delta_substrate.ARM_READ_PUBLIC_CONTRACT_VERSION,
    trusted=True,
):
    pitcher_reads = list(pitcher_reads)
    member_pitchers = list(member_pitchers or [pitcher for pitcher, _ in pitcher_reads])
    missing_pitchers = list(missing_pitchers)
    member_ids = sorted({
        pitcher.id for pitcher in [*member_pitchers, *missing_pitchers]
    })
    records = []
    for pitcher, read_key in pitcher_reads:
        records.append({
            'pitcher_id': pitcher.id,
            'mlb_id': pitcher.mlb_id,
            'pitcher_name': pitcher.full_name,
            'team_id': pitcher.team_id,
            'public_read': deepcopy(delta_substrate.READ_PUBLIC_LABELS[read_key]),
            'evidence_state': {
                'data_state': 'current',
                'confidence': 'high',
            },
            'roster_authority': {
                'version': delta_substrate.ROSTER_AUTHORITY_VERSION,
                'status': STATUS_ACTIVE,
                'is_authoritative': True,
                'is_active_mlb': True,
            },
        })
    return {
        'team_id': 1,
        'membership_reference_date': represented_date.isoformat(),
        'availability_reference_date': (
            represented_date + timedelta(days=1)
        ).isoformat(),
        'method_version': method_version,
        'public_contract_version': public_contract_version,
        'population_basis': {
            'basis': 'canonical_current_active_bullpen',
            'population_authority': 'resolve_readiness_population',
            'membership_authority': 'resolve_active_bullpen_membership',
            'roster_authority_version': delta_substrate.ROSTER_AUTHORITY_VERSION,
            'availability_mode': delta_substrate.CURRENT_AVAILABILITY_MODE,
            'reference_date_policy': 'membership_slate_availability_next_day_v1',
        },
        'member_pitcher_ids': member_ids,
        'missing_record_pitcher_ids': sorted(
            pitcher.id for pitcher in missing_pitchers
        ),
        'records': records,
        'trusted': trusted,
    }


def _seed_quiet_game_lane(anchor, current):
    reliever = _pitcher('Stable Delta Arm', mlb_id=301)
    starter = _pitcher('Date Marker Starter', mlb_id=302, position='SP')
    _log(reliever, anchor, 3010, pitches=9)
    _score(reliever, 35.0, anchor)
    _score(reliever, 35.0, current)
    _log(starter, current, 3020, pitches=88, innings=6.0)
    _successful_sync(current)
    return reliever


def _change_ids(body, change_type=None):
    changes = body.get('pitcher_changes') or []
    if change_type:
        changes = [change for change in changes if change['type'] == change_type]
    return {change['pitcher_id'] for change in changes}


class TestTeamChangesEndpoint:
    def test_raw_availability_change_does_not_publish_when_governed_read_is_unchanged(
        self, client,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('Governed Stable Arm', mlb_id=91)
            marker = _pitcher('Current Date Starter', mlb_id=92, position='SP')
            _log(pitcher, anchor, 910, pitches=6)
            _log(marker, current, 920, pitches=88, innings=6.0)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 65.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=471,
                arm_read_capture=_governed_arm_read_capture(
                    anchor, ((pitcher, 'watch_arm'),),
                ),
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=472,
                arm_read_capture=_governed_arm_read_capture(
                    current, ((pitcher, 'watch_arm'),),
                ),
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['arm_read_comparison']['status'] == 'unchanged'
        assert not [
            change for change in body['pitcher_changes']
            if change['type'] in {'arm_read_change', 'status_change'}
        ]

    def test_governed_arm_read_change_publishes_explicit_read_fields(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('Governed Shift Arm', mlb_id=93)
            marker = _pitcher('Current Date Starter', mlb_id=94, position='SP')
            _log(pitcher, anchor, 930, pitches=6)
            _log(marker, current, 940, pitches=88, innings=6.0)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 65.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=473,
                arm_read_capture=_governed_arm_read_capture(
                    anchor, ((pitcher, 'watch_arm'),),
                ),
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=474,
                arm_read_capture=_governed_arm_read_capture(
                    current, ((pitcher, 'rest_restricted'),),
                ),
            )
            pitcher_id = pitcher.id

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['arm_read_comparison']['status'] == 'changed'
        assert [
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        ] == [{
            'type': 'arm_read_change',
            'semantic_family': 'public_arm_read',
            'pitcher_id': pitcher_id,
            'pitcher_name': 'Governed Shift Arm',
            'from_read': {'key': 'watch_arm', 'label': 'Watch Arm'},
            'to_read': {'key': 'rest_restricted', 'label': 'Limited Rest'},
            'from_date': anchor.isoformat(),
            'to_date': current.isoformat(),
            'summary': 'Governed Shift Arm moved from Watch Arm to Limited Rest.',
        }]

    def test_raw_and_governed_read_changes_publish_only_the_governed_transition(
        self, client,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('Different Semantic Arm', mlb_id=95)
            marker = _pitcher('Current Date Starter', mlb_id=96, position='SP')
            _log(pitcher, anchor, 950, pitches=6)
            _log(marker, current, 960, pitches=88, innings=6.0)
            # This is the same raw-score shape that the legacy path exposed as
            # Monitor -> Limited. The frozen governed reads intentionally move
            # on a different public path.
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 65.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=475,
                arm_read_capture=_governed_arm_read_capture(
                    anchor, ((pitcher, 'clean_option'),),
                ),
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=476,
                arm_read_capture=_governed_arm_read_capture(
                    current, ((pitcher, 'watch_arm'),),
                ),
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()
        arm_changes = [
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        ]

        assert [(change['from_read'], change['to_read']) for change in arm_changes] == [(
            {'key': 'clean_option', 'label': 'Clean Option'},
            {'key': 'watch_arm', 'label': 'Watch Arm'},
        )]
        assert all('from_status' not in change and 'to_status' not in change
                   for change in arm_changes)
        assert 'Monitor' not in str(arm_changes)
        assert 'Limited' not in str(arm_changes)

    @pytest.mark.parametrize('missing_side', ('previous', 'current'))
    def test_missing_governed_read_withholds_only_that_arm_transition(
        self, client, missing_side,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _seed_quiet_game_lane(anchor, current)
            previous_capture = _governed_arm_read_capture(
                anchor,
                () if missing_side == 'previous' else ((pitcher, 'watch_arm'),),
                member_pitchers=(pitcher,),
                missing_pitchers=(pitcher,) if missing_side == 'previous' else (),
            )
            current_capture = _governed_arm_read_capture(
                current,
                () if missing_side == 'current' else ((pitcher, 'rest_restricted'),),
                member_pitchers=(pitcher,),
                missing_pitchers=(pitcher,) if missing_side == 'current' else (),
            )
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=477,
                arm_read_capture=previous_capture,
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=478,
                arm_read_capture=current_capture,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['arm_read_comparison']['status'] == 'partial'
        assert body['arm_read_comparison']['withheld_pitcher_count'] == 1
        assert not [
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        ]

    @pytest.mark.parametrize(
        ('to_key', 'to_label'),
        (
            ('limited_read', 'Limited Read'),
            ('unavailable', 'Unavailable'),
        ),
    )
    def test_explicit_special_public_reads_are_preserved_as_governed_endpoints(
        self, client, to_key, to_label,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=479,
                arm_read_capture=_governed_arm_read_capture(
                    anchor, ((pitcher, 'watch_arm'),),
                ),
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=480,
                arm_read_capture=_governed_arm_read_capture(
                    current, ((pitcher, to_key),),
                ),
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()
        arm_change = next(
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        )

        assert arm_change['to_read'] == {
            'key': to_key,
            'label': to_label,
        }

    def test_incompatible_arm_read_method_withholds_the_dependent_lane(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=487,
                arm_read_capture=_governed_arm_read_capture(
                    anchor, ((pitcher, 'watch_arm'),),
                ),
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=488,
                arm_read_capture=_governed_arm_read_capture(
                    current, ((pitcher, 'rest_restricted'),),
                    method_version='future_arm_read_method',
                ),
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['arm_read_comparison']['status'] == 'unavailable'
        assert body['arm_read_comparison']['reason_code'] == 'method_version_mismatch'
        assert not [
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        ]

    def test_governed_arm_read_changes_preserve_backend_identity_order(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            first = _pitcher('First Governed Arm', mlb_id=97)
            second = _pitcher('Second Governed Arm', mlb_id=98)
            marker = _pitcher('Current Date Starter', mlb_id=99, position='SP')
            for index, pitcher in enumerate((first, second), start=1):
                _log(pitcher, anchor, 970 + index, pitches=6)
                _score(pitcher, 35.0, anchor)
                _score(pitcher, 35.0, current)
            _log(marker, current, 990, pitches=88, innings=6.0)
            _successful_sync(current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=489,
                arm_read_capture=_governed_arm_read_capture(
                    anchor,
                    ((second, 'watch_arm'), (first, 'clean_option')),
                ),
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=490,
                arm_read_capture=_governed_arm_read_capture(
                    current,
                    ((second, 'limited_read'), (first, 'watch_arm')),
                ),
            )
            expected = [
                (first.id, 'First Governed Arm'),
                (second.id, 'Second Governed Arm'),
            ]

        body = client.get('/api/bullpen/teams/1/changes').get_json()
        arm_changes = [
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        ]

        assert [(change['pitcher_id'], change['pitcher_name'])
                for change in arm_changes] == expected


    @pytest.mark.parametrize(('previous_count', 'current_count'), ((5, 7), (7, 5)))
    def test_frozen_rested_options_change_is_a_meaningful_public_lane(
        self, client, previous_count, current_count,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=481,
                rested_arm_count=previous_count,
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=482,
                rested_arm_count=current_count,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['team_state_change'] is None
        assert body['rest_status_comparison'] == {
            'status': 'changed',
            'reason_code': None,
            'from_represented_date': anchor.isoformat(),
            'to_represented_date': current.isoformat(),
            'limitation': None,
        }
        assert body['rest_status_change'] == {
            'type': 'rest_status_change',
            'field': 'rested_arm_count',
            'label': 'Rested Options',
            'from_value': previous_count,
            'to_value': current_count,
            'from_date': anchor.isoformat(),
            'to_date': current.isoformat(),
            'transition': f'{previous_count} → {current_count}',
            'summary': (
                f'Rested options moved from {previous_count} to {current_count}.'
            ),
        }

    def test_unchanged_rested_options_remains_quiet(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=483,
                rested_arm_count=5,
            )
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=484,
                rested_arm_count=5,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['rest_status_change'] is None
        assert body['rest_status_comparison']['status'] == 'unchanged'

    def test_rest_status_failure_does_not_suppress_team_state_change(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=485,
                rested_arm_count=5,
            )
            row = _team_state_sidecar(
                current, 'vulnerable', 'Vulnerable', artifact_id=486,
                rested_arm_count=7,
            )
            payload = deepcopy(row.payload)
            payload['domains']['rest_status']['method_version'] = 'wrong-method'
            row.payload = payload
            db.session.commit()

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['team_state_change']['to_label'] == 'Vulnerable'
        assert body['rest_status_change'] is None
        assert body['rest_status_comparison']['status'] == 'unavailable'

    @pytest.mark.parametrize(
        ('from_state', 'from_label', 'to_state', 'to_label'),
        (
            ('fresh', 'Fresh', 'stretched', 'Stretched'),
            ('stretched', 'Stretched', 'vulnerable', 'Vulnerable'),
            ('vulnerable', 'Vulnerable', 'stretched', 'Stretched'),
            ('stretched', 'Stretched', 'fresh', 'Fresh'),
            ('vulnerable', 'Vulnerable', 'fresh', 'Fresh'),
        ),
    )
    def test_frozen_team_state_change_is_a_meaningful_public_lane(
        self, client, from_state, from_label, to_state, to_label,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, from_state, from_label, artifact_id=501,
            )
            _team_state_sidecar(
                current, to_state, to_label, artifact_id=502,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['pitcher_changes'] == []
        assert body['team_summary'] is None
        assert body['team_state_comparison'] == {
            'status': 'changed',
            'reason_code': None,
            'from_represented_date': anchor.isoformat(),
            'to_represented_date': current.isoformat(),
            'limitation': None,
        }
        assert body['team_state_change'] == {
            'type': 'team_state_change',
            'from_state': from_state,
            'from_label': from_label,
            'to_state': to_state,
            'to_label': to_label,
            'from_date': anchor.isoformat(),
            'to_date': current.isoformat(),
            'summary': f'Team State changed from {from_label} to {to_label}.',
        }

    @pytest.mark.parametrize(
        ('state', 'label'),
        (
            ('fresh', 'Fresh'),
            ('stretched', 'Stretched'),
            ('vulnerable', 'Vulnerable'),
        ),
    )
    def test_unchanged_frozen_team_state_emits_no_movement(self, client, state, label):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(anchor, state, label, artifact_id=511)
            _team_state_sidecar(current, state, label, artifact_id=512)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['team_state_change'] is None
        assert body['team_state_comparison']['status'] == 'unchanged'
        assert body['team_state_comparison']['limitation'] is None

    @pytest.mark.parametrize(
        ('override', 'reason'),
        (
            ({'method_version': 'other-method'}, 'method_version_mismatch'),
            ({'public_contract_version': 'other-contract'}, 'contract_incompatible'),
            ({'population_basis': {
                'basis': 'other-basis',
                'population_authority': 'resolve_readiness_population',
                'membership_authority': 'resolve_active_bullpen_membership',
            }}, 'population_basis_mismatch'),
            ({'trusted': False}, 'freshness_untrusted'),
        ),
    )
    def test_incompatible_frozen_team_state_fails_closed(self, client, override, reason):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=521, **override,
            )
            _team_state_sidecar(
                current, 'vulnerable', 'Vulnerable', artifact_id=522,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['team_state_change'] is None
        assert body['team_state_comparison']['status'] == 'unavailable'
        assert body['team_state_comparison']['reason_code'] == reason
        assert body['team_state_comparison']['limitation'] == (
            'Team State comparison is unavailable for this publication window.'
        )

    def test_missing_frozen_team_state_endpoints_fail_closed_without_recompute(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            _seed_quiet_game_lane(anchor, current)

        missing_current = client.get('/api/bullpen/teams/1/changes').get_json()
        assert missing_current['team_state_comparison']['reason_code'] == 'current_missing'
        assert missing_current['team_state_comparison']['limitation'] == (
            'Team State comparison is unavailable for this publication window.'
        )

        with client.application.app_context():
            _team_state_sidecar(
                current, 'vulnerable', 'Vulnerable', artifact_id=531,
            )

        missing_previous = client.get('/api/bullpen/teams/1/changes').get_json()
        assert missing_previous['team_state_comparison']['reason_code'] == 'previous_missing'
        assert missing_previous['team_state_change'] is None

    def test_team_state_window_remains_independent_when_game_baseline_is_missing(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            reliever = _pitcher('Single Game Arm', mlb_id=303)
            _log(reliever, current, 3030, pitches=10)
            _score(reliever, 35.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=541,
            )
            _team_state_sidecar(
                current, 'vulnerable', 'Vulnerable', artifact_id=542,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['comparison']['anchor_game_date'] is None
        assert body['team_state_change']['from_date'] == anchor.isoformat()
        assert body['team_state_change']['to_date'] == current.isoformat()
        assert 'previous_team_game_missing' in body['state_reason_codes']

    def test_team_state_change_preserves_governed_arm_read_rest_and_appearance(
        self, client,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('Shift Arm', mlb_id=101)
            _log(pitcher, anchor, 1010, pitches=6)
            _log(pitcher, current, 1011, pitches=24)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 65.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                anchor, 'stretched', 'Stretched', artifact_id=551,
                rested_arm_count=5,
                arm_read_capture=_governed_arm_read_capture(
                    anchor, ((pitcher, 'watch_arm'),),
                ),
            )
            _team_state_sidecar(
                current, 'vulnerable', 'Vulnerable', artifact_id=552,
                rested_arm_count=7,
                arm_read_capture=_governed_arm_read_capture(
                    current, ((pitcher, 'rest_restricted'),),
                ),
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['capability'] == 'what_changed_since_last_game'
        assert body['ranking_applied'] is False
        assert body['selection_made'] is False
        assert body['state'] == 'changes'
        assert body['team_state_change']['summary'] == (
            'Team State changed from Stretched to Vulnerable.'
        )
        assert body['comparison']['anchor_game_date'] == anchor.isoformat()
        assert body['comparison']['current_game_date'] == current.isoformat()
        assert body['comparison']['label'] == (
            f'Compared with TST: {anchor:%b} {anchor.day} -> {current:%b} {current.day}'
        )

        arm_read_changes = [
            change for change in body['pitcher_changes']
            if change['type'] == 'arm_read_change'
        ]
        appearances = [
            change for change in body['pitcher_changes']
            if change['type'] == 'appearance'
        ]
        assert arm_read_changes[0]['from_read']['label'] == 'Watch Arm'
        assert arm_read_changes[0]['to_read']['label'] == 'Limited Rest'
        assert body['rest_status_change']['transition'] == '5 → 7'
        assert appearances[0]['pitcher_name'] == 'Shift Arm'
        assert appearances[0]['pitches'] == 24
        assert 'Pitched' in appearances[0]['summary']
        assert '24 pitches' in appearances[0]['summary']

    def test_missing_publication_comparison_does_not_fall_back_to_raw_status(
        self, client,
    ):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('Status Only Arm', mlb_id=111)
            marker = _pitcher('Current Date Starter', mlb_id=112, position='SP')
            _log(pitcher, anchor, 1110, pitches=6)
            _log(marker, current, 1120, pitches=88, innings=6.0)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 65.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                current, 'vulnerable', 'Vulnerable', artifact_id=561,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['team_state_change'] is None
        assert body['team_state_comparison']['status'] == 'unavailable'
        assert body['team_state_comparison']['reason_code'] == 'previous_missing'
        assert body['team_state_comparison']['limitation'] == (
            'Team State comparison is unavailable for this publication window.'
        )
        assert body['arm_read_comparison']['status'] == 'unavailable'
        assert body['arm_read_comparison']['reason_code'] == 'previous_missing'
        assert body['pitcher_changes'] == []

    def test_unavailable_team_state_preserves_appearance_movement(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            marker = _pitcher('Anchor Date Starter', mlb_id=121, position='SP')
            pitcher = _pitcher('Appearance Only Arm', mlb_id=122)
            _log(marker, anchor, 1210, pitches=88, innings=6.0)
            _log(pitcher, current, 1220, pitches=6)
            _score(pitcher, 20.0, anchor)
            _score(pitcher, 20.0, current)
            _successful_sync(current)
            _team_state_sidecar(
                current, 'stretched', 'Stretched', artifact_id=571,
            )

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['team_state_change'] is None
        assert body['team_state_comparison']['status'] == 'unavailable'
        assert body['team_state_comparison']['reason_code'] == 'previous_missing'
        assert body['team_state_comparison']['limitation'] == (
            'Team State comparison is unavailable for this publication window.'
        )
        assert [change['type'] for change in body['pitcher_changes']] == ['appearance']

    def test_no_changes_state_ignores_fatigue_drift_without_label_change(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            stable = _pitcher('Stable Arm', mlb_id=102)
            marker = _pitcher('Inactive Game Marker', mlb_id=103, active=False)
            _log(stable, anchor, 1020, pitches=12)
            _log(marker, current, 1030, pitches=12)
            _score(stable, 43.0, anchor)
            _score(stable, 45.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['pitcher_changes'] == []
        assert body['team_summary'] is None

    def test_no_baseline_state_when_team_has_only_one_completed_game_date(self, client):
        current = date.today() - timedelta(days=1)
        with client.application.app_context():
            pitcher = _pitcher('First Game Arm', mlb_id=104)
            _log(pitcher, current, 1040, pitches=18)
            _score(pitcher, 42.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_baseline'
        assert body['pitcher_changes'] == []
        assert body['state_reason_codes'] == ['previous_team_game_missing']

    def test_stale_state_does_not_compute_deltas(self, client):
        current = date.today() - timedelta(days=ACTIVE_WINDOW_DAYS + 5)
        anchor = current - timedelta(days=1)
        with client.application.app_context():
            pitcher = _pitcher('Old Shift Arm', mlb_id=105)
            _log(pitcher, anchor, 1050, pitches=12)
            _log(pitcher, current, 1051, pitches=35)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 80.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'stale'
        assert body['pitcher_changes'] == []
        assert body['team_summary'] is None
        assert 'workload_data_not_current' in body['state_reason_codes']

    def test_sync_metadata_unavailable_fails_closed_without_deltas(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            pitcher = _pitcher('No Metadata Arm', mlb_id=106)
            _log(pitcher, anchor, 1060, pitches=12)
            _log(pitcher, current, 1061, pitches=35)
            _score(pitcher, 43.0, anchor)
            _score(pitcher, 80.0, current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'stale'
        assert body['pitcher_changes'] == []
        assert 'durable_sync_metadata_unavailable' in body['state_reason_codes']
        assert 'successful_sync_missing' in body['state_reason_codes']

    def test_latest_sync_failure_is_reported_when_current_data_is_comparable(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            stable = _pitcher('Failure Window Arm', mlb_id=107)
            marker = _pitcher('Failed Sync Marker', mlb_id=108, active=False)
            _log(stable, anchor, 1070, pitches=12)
            _log(marker, current, 1080, pitches=12)
            _score(stable, 43.0, anchor)
            _score(stable, 45.0, current)
            _successful_sync(current)
            _failed_sync()

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'no_changes'
        assert body['freshness']['sync_status'] == 'failed'
        assert any('latest sync attempt failed' in limitation.lower()
                   for limitation in body['limitations'])

    def test_endpoint_does_not_require_new_tables(self, client):
        with client.application.app_context():
            table_names = set(inspect(db.engine).get_table_names())

        assert 'availability_snapshots' not in table_names
        assert 'team_change_snapshots' not in table_names
        assert 'what_changed_events' not in table_names

        res = client.get('/api/bullpen/teams/1/changes')
        assert res.status_code == 200

    def test_clear_starter_is_excluded_while_reliever_appearance_remains(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            starter = _pitcher('Clear Starter', mlb_id=201, position='SP')
            reliever = _pitcher('Bullpen Reliever', mlb_id=202)

            _log(starter, anchor, 2010, pitches=92, innings=6.0)
            _log(starter, current, 2011, pitches=88, innings=6.0)
            _score(starter, 35.0, anchor)
            _score(starter, 80.0, current)

            _log(reliever, anchor, 2020, pitches=8, innings=1.0, hold=True)
            _log(reliever, current, 2021, pitches=18, innings=1.0, hold=True)
            _score(reliever, 30.0, anchor)
            _score(reliever, 42.0, current)
            _successful_sync(current)
            reliever_id = reliever.id

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        change_names = {change['pitcher_name'] for change in body['pitcher_changes']}
        assert 'Clear Starter' not in change_names
        assert 'Bullpen Reliever' in change_names
        assert _change_ids(body, 'appearance') == {reliever_id}

    def test_board_and_changes_use_same_default_eligible_population(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            starter = _pitcher('Board Starter', mlb_id=211, position='SP')
            reliever = _pitcher('Board Reliever', mlb_id=212)
            _log(starter, anchor, 2110, pitches=80, innings=5.0)
            _log(starter, current, 2111, pitches=82, innings=5.0)
            _score(starter, 30.0, anchor)
            _score(starter, 65.0, current)

            _log(reliever, anchor, 2120, pitches=8, innings=1.0, hold=True)
            _log(reliever, current, 2121, pitches=20, innings=1.0, hold=True)
            _score(reliever, 30.0, anchor)
            _score(reliever, 45.0, current)
            _successful_sync(current)

        board = client.get('/api/bullpen/teams/1/board').get_json()
        changes = client.get('/api/bullpen/teams/1/changes').get_json()

        board_ids = {
            card['pitcher_id']
            for group in board['groups']
            for card in group['pitchers']
        }
        assert board_ids == _change_ids(changes, 'appearance')

    def test_team_summary_is_suppressed_until_current_counts_are_board_safe(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            stable = _pitcher('Stable Current Reliever', mlb_id=215)
            new_arm = _pitcher('New Current Reliever', mlb_id=216)

            _log(stable, anchor, 2150, pitches=6, innings=1.0, hold=True)
            _log(stable, current, 2151, pitches=8, innings=1.0, hold=True)
            _score(stable, 20.0, anchor)
            _score(stable, 22.0, current)

            _log(new_arm, current, 2160, pitches=7, innings=1.0, hold=True)
            _score(new_arm, 21.0, current)
            _successful_sync(current)

        board = client.get('/api/bullpen/teams/1/board').get_json()
        changes = client.get('/api/bullpen/teams/1/changes').get_json()

        assert board['total_pitchers'] == 2
        assert changes['team_summary'] is None
        assert 'Available arms' not in str(changes)
        assert _change_ids(changes, 'appearance') == {
            card['pitcher_id']
            for group in board['groups']
            for card in group['pitchers']
        }

    def test_roster_inactive_reliever_is_excluded_from_changes(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            il_arm = _pitcher('Unavailable Reliever', mlb_id=221, roster_status='IL_15')
            _log(il_arm, anchor, 2210, pitches=8, innings=1.0, hold=True)
            _log(il_arm, current, 2211, pitches=18, innings=1.0, hold=True)
            _score(il_arm, 30.0, anchor)
            _score(il_arm, 65.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert 'Unavailable Reliever' not in {
            change['pitcher_name'] for change in body['pitcher_changes']
        }

    def test_team_date_inference_uses_unfiltered_team_game_evidence(self, client):
        anchor, current = _recent_dates()
        with client.application.app_context():
            reliever = _pitcher('Date Reliever', mlb_id=231)
            starter = _pitcher('Date Starter', mlb_id=232, position='SP')
            _log(reliever, anchor, 2310, pitches=12, innings=1.0, hold=True)
            _score(reliever, 35.0, anchor)
            _score(reliever, 36.0, current)

            _log(starter, current, 2320, pitches=88, innings=6.0)
            _score(starter, 30.0, current)
            _successful_sync(current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['comparison']['current_game_date'] == current.isoformat()
        assert body['comparison']['anchor_game_date'] == anchor.isoformat()
        assert body['pitcher_changes'] == []

    def test_team_local_current_date_reports_when_team_trails_league_data(self, client):
        anchor, current = _recent_dates()
        league_current = current + timedelta(days=1)
        with client.application.app_context():
            reliever = _pitcher('Behind Reliever', mlb_id=241, team_id=1)
            _log(reliever, anchor, 2410, pitches=8, innings=1.0, hold=True)
            _log(reliever, current, 2411, pitches=18, innings=1.0, hold=True)
            _score(reliever, 30.0, anchor)
            _score(reliever, 45.0, current)

            league_marker = _pitcher('League Marker', mlb_id=242, team_id=2)
            _log(league_marker, league_current, 2420, pitches=12, innings=1.0)
            _successful_sync(league_current)

        body = client.get('/api/bullpen/teams/1/changes').get_json()

        assert body['state'] == 'changes'
        assert body['comparison']['current_game_date'] == current.isoformat()
        assert body['comparison']['global_latest_game_date'] == league_current.isoformat()
        assert body['comparison']['team_data_behind_league'] is True
        assert 'team_data_behind_league' in body['state_reason_codes']
        assert any(
            f'TST latest game data is {current:%b} {current.day}' in limitation
            and f'league data is current through {league_current:%b} {league_current.day}' in limitation
            for limitation in body['limitations']
        )
