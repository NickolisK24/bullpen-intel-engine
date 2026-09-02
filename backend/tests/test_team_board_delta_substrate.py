"""TB-09A prospective Team Board comparison-substrate contract."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

from models.dashboard_snapshot import DashboardSnapshot
from models.share_artifact import ShareArtifact
from services import team_board_delta_substrate as delta
from services import public_team_relief_work
from services import public_serving_authority
from services import rotation_support_pressure
from team_operations import TEAM_STATE_METHOD_VERSION
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


TEAM_ID = 147
REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _readiness(*, state='operationally_constrained', active_count=7):
    return {
        'contract_version': TEAM_STATE_METHOD_VERSION,
        'contract_state': 'available',
        'team_state_evidence': {
            'method_version': TEAM_STATE_METHOD_VERSION,
            'contract': 'team_state_contract_a',
            'basis': 'status_only',
            'readiness_status_code': state,
            'active_pitcher_count': active_count,
            'evidence_references': {
                'population_authority': 'resolve_readiness_population',
                'membership_authority': 'resolve_active_bullpen_membership',
            },
        },
    }


def _source(*, represented_date=date(2026, 8, 18), snapshot_id=90, sync_run_id=12):
    authority = SimpleNamespace(
        data_through=represented_date,
        snapshot_id=snapshot_id,
        sync_run_id=sync_run_id,
        subject_type=None,
        subject_key=None,
        is_trusted=True,
    )
    return SimpleNamespace(team_id=TEAM_ID, snapshot=authority)


def _artifact(*, artifact_id=44, state='stretched', label='Stretched'):
    return SimpleNamespace(
        id=artifact_id,
        render_version='team-state-1.2.0',
        lifecycle_state='published',
        published_at=datetime(2026, 8, 18, 12, 30),
        payload={
            'team_state': {
                'public_state': {
                    'public_code': state,
                    'public_label': label,
                },
            },
        },
    )


def _persist_artifact(artifact_id, represented_date, *, lifecycle_state='published'):
    row = ShareArtifact(
        id=artifact_id,
        public_id=f'team-state-{artifact_id}',
        artifact_type='team_state',
        render_version='team-state-1.2.0',
        team_id=TEAM_ID,
        source_snapshot_id=100 + artifact_id,
        product_date=represented_date,
        lifecycle_state=lifecycle_state,
        payload={},
        trust_metadata={},
        equivalence_key=f'team-state-{artifact_id}',
        integrity_hash=f'integrity-{artifact_id}',
        source='test',
        published_at=datetime.combine(represented_date, datetime.min.time()),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _arm_record(
    pitcher_id,
    availability_status,
    *,
    data_state='fresh',
    confidence='high',
    roster_status='ACTIVE',
):
    pitcher = SimpleNamespace(
        id=pitcher_id,
        mlb_id=600000 + pitcher_id,
        full_name=f'Pitcher {pitcher_id}',
        team_id=TEAM_ID,
        active=True,
        roster_status=roster_status,
        roster_status_source='mlb_stats_api:roster_sync:active:test',
        roster_status_raw_code=None,
        roster_status_raw_description=None,
        roster_status_updated_at=datetime(2026, 8, 18, 9, 0),
        team_assignment_status=None,
        team_assignment_source=None,
        team_assignment_updated_at=None,
    )
    return {
        'pitcher': pitcher,
        'availability': {
            'availability_status': availability_status,
            'data_state': data_state,
            'confidence': confidence,
        },
    }


def _arm_capture(represented_date, statuses, *, member_ids=None):
    records = tuple(
        _arm_record(pitcher_id, status)
        for pitcher_id, status in statuses
    )
    if member_ids is None:
        member_ids = tuple(pitcher_id for pitcher_id, _status in statuses)
    return delta.build_arm_read_capture(
        records=records,
        team_id=TEAM_ID,
        membership=(set(member_ids), True),
        membership_reference_date=represented_date,
        availability_reference_date=represented_date + timedelta(days=1),
    )


def _snapshot(
    represented_date,
    *,
    snapshot_id,
    state='stretched',
    active_count=7,
    arm_capture=None,
    workload_capture=None,
    rotation_capture=None,
    membership_capture=None,
    rest_status_capture=None,
):
    envelope = delta.build_prospective_envelope(
        source=_source(represented_date=represented_date, snapshot_id=100 + snapshot_id),
        readiness=_readiness(active_count=active_count),
        artifact=_artifact(artifact_id=200 + snapshot_id, state=state, label=state.title()),
        arm_read_capture=arm_capture,
        workload_window_capture=workload_capture,
        rotation_impact_capture=rotation_capture,
        bullpen_membership_capture=membership_capture,
        rest_status_capture=rest_status_capture,
    )
    return SimpleNamespace(id=snapshot_id, payload=envelope)


def _retained_malformed_team_state_sidecar(snapshot):
    payload = deepcopy(snapshot.payload)
    value = payload['values']['team_state']
    payload['values']['team_state'] = {
        'public_state': {
            'public_code': value['public_state'],
            'public_label': value['public_label'],
        },
        'public_label': None,
    }
    return SimpleNamespace(id=snapshot.id, payload=payload)


def _rest_status_capture(represented_date, rested_arm_count=5):
    return {
        'team_id': TEAM_ID,
        'represented_date': represented_date.isoformat(),
        'availability_reference_date': (represented_date + timedelta(days=1)).isoformat(),
        'method_version': delta.REST_STATUS_METHOD_VERSION,
        'public_contract_version': delta.REST_STATUS_PUBLIC_CONTRACT_VERSION,
        'contract_version': delta.TEAM_BOARD_PACKAGE_CONTRACT,
        'population_basis': delta._canonical_rest_status_population_basis(),
        'reference_date_policy': delta.REST_STATUS_REFERENCE_DATE_POLICY,
        'source_authority': delta.FROZEN_TEAM_BOARD_SOURCE_AUTHORITY,
        'value': {
            'available': True,
            'active_arm_count': 8,
            'rested_arm_count': rested_arm_count,
            'worked_yesterday_count': 2,
            'back_to_back_count': 1,
            'summary': f'{rested_arm_count} rested options.',
            'reason_code': None,
        },
    }


def _workload_window(
    represented_date,
    *,
    relief_appearances,
    pitchers_in_relief=None,
    pitches_total=None,
    appearances_with_pitches=None,
    start_relief_unknown=0,
):
    pitchers_in_relief = (
        relief_appearances if pitchers_in_relief is None else pitchers_in_relief
    )
    appearances_with_pitches = (
        relief_appearances
        if appearances_with_pitches is None
        else appearances_with_pitches
    )
    return {
        'through': represented_date.isoformat(),
        'relief_appearances': relief_appearances,
        'pitchers_in_relief': pitchers_in_relief,
        'pitches_total': pitches_total,
        'appearances_with_pitches': appearances_with_pitches,
        'start_relief_unknown': start_relief_unknown,
        'sentence': f'{relief_appearances} relief appearances.',
        'pitchers_sentence': f'{pitchers_in_relief} pitchers appeared in relief.',
        'pitches_sentence': (
            f'{pitches_total} pitches.'
            if pitches_total is not None
            else 'Pitch count unavailable.'
        ),
        **(
            {'start_relief_unknown_sentence': 'One appearance is unclassified.'}
            if start_relief_unknown
            else {}
        ),
    }


def _workload_capture(
    represented_date,
    *,
    window_7=None,
    window_14=None,
):
    return {
        'team_id': TEAM_ID,
        'represented_date': represented_date.isoformat(),
        'method_version': public_team_relief_work.WORKLOAD_WINDOWS_METHOD_VERSION,
        'public_contract_version': (
            public_team_relief_work.WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
        ),
        'carrier_contract_version': (
            public_team_relief_work.WORKLOAD_WINDOWS_CARRIER_CONTRACT
        ),
        'contract_version': 'trusted_team_board_publication_v1',
        'population_basis': {
            'basis': public_team_relief_work.WORKLOAD_WINDOWS_POPULATION_BASIS,
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
        'source_authority': 'trusted_team_board_publication',
        'windows': {
            'window_7': window_7 or _workload_window(
                represented_date,
                relief_appearances=2,
                pitches_total=36,
            ),
            'window_14': window_14 or _workload_window(
                represented_date,
                relief_appearances=4,
                pitches_total=72,
            ),
        },
    }


def _rotation_value(represented_date, *, bullpen_outs=18, short_starts=1):
    return {
        'capability': rotation_support_pressure.CAPABILITY,
        'version': rotation_support_pressure.VERSION,
        'source': 'backend',
        'team_id': TEAM_ID,
        'status': 'neutral',
        'window_days': 7,
        'reference_date': represented_date.isoformat(),
        'window_start': (represented_date - timedelta(days=6)).isoformat(),
        'games_in_window': 3,
        'games_analyzed': 3,
        'games_excluded': 0,
        'opener_bulk_games': 0,
        'bullpen_games': 0,
        'starter_outs': 45,
        'starter_innings': 15.0,
        'starter_avg_outs': 15.0,
        'starter_avg_innings': 5.0,
        'bullpen_outs_required': bullpen_outs,
        'bullpen_innings_required': round(bullpen_outs / 3, 1),
        'bullpen_avg_innings_required': round(bullpen_outs / 9, 2),
        'short_start_count': short_starts,
        'short_start_rate': round(short_starts / 3, 2),
        'bulk_follower_outs': 0,
        'bulk_follower_innings': 0.0,
        'bullpen_game_outs': 0,
        'bullpen_game_innings': 0.0,
        'game_shape_distribution': {'normal_start': 3},
        'excluded_game_reasons': {},
        'source_reason_codes': {},
        'limitation_reasons': [],
        'rows_without_game_pk': 0,
        'definitions': {},
        'thresholds': {},
        'methodology_notes': [],
        'source_limitations': [],
        'source_window': {'source': 'team_game_pitching_splits'},
        'relief_work_handoff': {'target': 'team-relief-work', 'summary': 'View receipts.', 'games': []},
        'summary': 'Rotation burden summary.',
        'limitations': [],
    }


def _rotation_capture(represented_date, **value_overrides):
    return {
        'team_id': TEAM_ID,
        'represented_date': represented_date.isoformat(),
        'method_version': rotation_support_pressure.VERSION,
        'public_contract_version': rotation_support_pressure.PUBLIC_CONTRACT_VERSION,
        'carrier_contract_version': rotation_support_pressure.DELTA_CARRIER_CONTRACT,
        'contract_version': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
        'population_basis': {
            'basis': rotation_support_pressure.POPULATION_BASIS,
            'population_authority': rotation_support_pressure.POPULATION_AUTHORITY,
            'membership_authority': rotation_support_pressure.MEMBERSHIP_AUTHORITY,
        },
        'reference_date_policy': rotation_support_pressure.REFERENCE_DATE_POLICY,
        'reference_date': represented_date.isoformat(),
        'source_authority': 'trusted_team_board_publication',
        'value': _rotation_value(represented_date, **value_overrides),
    }


def _membership_capture(represented_date, members):
    records = [
        {'pitcher_id': pitcher_id, 'pitcher_name': name}
        for pitcher_id, name in members
    ]
    return {
        'team_id': TEAM_ID,
        'represented_date': represented_date.isoformat(),
        'method_version': public_serving_authority.BULLPEN_MEMBERSHIP_METHOD_VERSION,
        'public_contract_version': public_serving_authority.BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION,
        'carrier_contract_version': public_serving_authority.BULLPEN_MEMBERSHIP_CARRIER_CONTRACT,
        'contract_version': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
        'population_basis': {
            'basis': public_serving_authority.BULLPEN_MEMBERSHIP_POPULATION_BASIS,
            'population_authority': public_serving_authority.BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY,
            'membership_authority': public_serving_authority.BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY,
            'roster_authority_version': public_serving_authority.ROSTER_AUTHORITY_VERSION,
        },
        'reference_date_policy': public_serving_authority.BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY,
        'membership_reference_date': represented_date.isoformat(),
        'source_authority': 'trusted_team_board_publication',
        'member_pitcher_ids': [item['pitcher_id'] for item in records],
        'members': records,
    }


def _workload_carrier_snapshot(represented_date, *, team_id=TEAM_ID, carrier=None):
    carrier = carrier or {
        'contract': public_team_relief_work.WORKLOAD_WINDOWS_CARRIER_CONTRACT,
        'status': public_team_relief_work.WORKLOAD_WINDOWS_COMPLETE,
        'reason_code': None,
        'data_through': represented_date.isoformat(),
        'windows': _workload_capture(represented_date)['windows'],
    }
    return SimpleNamespace(
        id=501,
        data_through=represented_date,
        payload={
            'trusted_team_boards': {
                'contract': 'trusted_team_board_publication_v1',
                'data_through': represented_date.isoformat(),
                'availability_reference_date': represented_date.isoformat(),
                'by_team_id': {
                    str(team_id): {
                        'team': {'team_id': team_id},
                        'workload_windows': carrier,
                        'workload_windows_authority': {
                            'method_version': (
                                public_team_relief_work.WORKLOAD_WINDOWS_METHOD_VERSION
                            ),
                            'public_contract_version': (
                                public_team_relief_work
                                .WORKLOAD_WINDOWS_PUBLIC_CONTRACT_VERSION
                            ),
                            'team_board_package_contract': (
                                'trusted_team_board_publication_v1'
                            ),
                            'population_basis': {
                                'basis': (
                                    public_team_relief_work
                                    .WORKLOAD_WINDOWS_POPULATION_BASIS
                                ),
                                'population_authority': (
                                    public_team_relief_work
                                    .WORKLOAD_WINDOWS_POPULATION_AUTHORITY
                                ),
                                'membership_authority': (
                                    public_team_relief_work
                                    .WORKLOAD_WINDOWS_MEMBERSHIP_AUTHORITY
                                ),
                            },
                            'reference_date_policy': (
                                public_team_relief_work
                                .WORKLOAD_WINDOWS_REFERENCE_DATE_POLICY
                            ),
                            'data_through': represented_date.isoformat(),
                        },
                    },
                },
            },
        },
    )


def _rotation_membership_carrier_snapshot(represented_date):
    snapshot = _workload_carrier_snapshot(represented_date)
    team = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    team.update({
        'records': [
            {'pitcher_id': 1, 'name': 'First Arm'},
            {'pitcher_id': 2, 'name': 'Second Arm'},
        ],
        'default_pitcher_ids': [1, 2],
        'bullpen_membership_authority': {
            'method_version': public_serving_authority.BULLPEN_MEMBERSHIP_METHOD_VERSION,
            'public_contract_version': public_serving_authority.BULLPEN_MEMBERSHIP_PUBLIC_CONTRACT_VERSION,
            'carrier_contract_version': public_serving_authority.BULLPEN_MEMBERSHIP_CARRIER_CONTRACT,
            'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
            'population_basis': {
                'basis': public_serving_authority.BULLPEN_MEMBERSHIP_POPULATION_BASIS,
                'population_authority': public_serving_authority.BULLPEN_MEMBERSHIP_POPULATION_AUTHORITY,
                'membership_authority': public_serving_authority.BULLPEN_MEMBERSHIP_MEMBERSHIP_AUTHORITY,
                'roster_authority_version': public_serving_authority.ROSTER_AUTHORITY_VERSION,
            },
            'reference_date_policy': public_serving_authority.BULLPEN_MEMBERSHIP_REFERENCE_DATE_POLICY,
            'membership_reference_date': represented_date.isoformat(),
        },
        'rotation_support_pressure': _rotation_value(represented_date),
        'rotation_support_pressure_authority': {
            'method_version': rotation_support_pressure.VERSION,
            'public_contract_version': rotation_support_pressure.PUBLIC_CONTRACT_VERSION,
            'carrier_contract_version': rotation_support_pressure.DELTA_CARRIER_CONTRACT,
            'team_board_package_contract': public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
            'population_basis': {
                'basis': rotation_support_pressure.POPULATION_BASIS,
                'population_authority': rotation_support_pressure.POPULATION_AUTHORITY,
                'membership_authority': rotation_support_pressure.MEMBERSHIP_AUTHORITY,
            },
            'reference_date_policy': rotation_support_pressure.REFERENCE_DATE_POLICY,
            'reference_date': represented_date.isoformat(),
        },
    })
    return snapshot


def _rest_status_carrier_snapshot(represented_date, rested_arm_count=5):
    reference_date = represented_date + timedelta(days=1)
    value = _rest_status_capture(represented_date, rested_arm_count)['value']
    return SimpleNamespace(
        id=601,
        status='ready',
        is_published=True,
        published_at=datetime.combine(represented_date, datetime.min.time()),
        data_through=represented_date,
        availability_reference_date=reference_date,
        payload={
            'trusted_team_boards': {
                'contract': delta.TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': represented_date.isoformat(),
                'availability_reference_date': reference_date.isoformat(),
                'by_team_id': {
                    str(TEAM_ID): {
                        'team': {'team_id': TEAM_ID},
                        'rest_status': value,
                        'rest_status_authority': {
                            'method_version': delta.REST_STATUS_METHOD_VERSION,
                            'public_contract_version': delta.REST_STATUS_PUBLIC_CONTRACT_VERSION,
                            'team_board_package_contract': delta.TEAM_BOARD_PACKAGE_CONTRACT,
                            'population_basis': delta._canonical_rest_status_population_basis(),
                            'reference_date_policy': delta.REST_STATUS_REFERENCE_DATE_POLICY,
                            'availability_reference_date': reference_date.isoformat(),
                        },
                    },
                },
            },
        },
    )


def test_prospective_envelope_uses_canonical_team_state_method_owner():
    envelope = delta.build_prospective_envelope(
        source=_source(),
        readiness=_readiness(),
        artifact=_artifact(),
    )

    assert envelope['domains']['team_state']['method_version'] == TEAM_STATE_METHOD_VERSION
    assert envelope['domains']['team_state']['contract_version'] == TEAM_STATE_METHOD_VERSION
    assert envelope['represented_date'] == '2026-08-18'
    assert envelope['source']['snapshot_id'] == 90
    assert envelope['source']['sync_run_id'] == 12
    assert envelope['source']['artifact_id'] == 44
    assert envelope['domains']['team_state']['trusted'] is True
    assert envelope['values']['team_state'] == {
        'public_state': 'stretched',
        'public_label': 'Stretched',
    }


def test_prospective_envelope_refuses_a_method_stamp_that_drifted_from_owner():
    readiness = _readiness()
    readiness['team_state_evidence']['method_version'] = 'v3_phase_4'

    with pytest.raises(delta.DeltaStampError, match='method_version_unproven'):
        delta.build_prospective_envelope(
            source=_source(),
            readiness=readiness,
            artifact=_artifact(),
        )


def test_prospective_envelope_refuses_incomplete_team_state_1_2_public_value():
    artifact = _artifact()
    artifact.payload['team_state']['public_state']['public_label'] = None

    with pytest.raises(delta.DeltaStampError, match='team_state_value_missing'):
        delta.build_prospective_envelope(
            source=_source(),
            readiness=_readiness(),
            artifact=artifact,
        )


def test_naturally_generated_sidecar_is_append_only_and_inspectable(app):
    arm_capture = _arm_capture(date(2026, 8, 18), ((1, 'Monitor'),))
    row = delta.stamp_prospective_snapshot(
        source=_source(),
        readiness=_readiness(),
        artifact=_artifact(),
        arm_read_capture=arm_capture,
    )
    db.session.commit()
    stored = db.session.get(DashboardSnapshot, row.id)

    assert stored.snapshot_type == delta.SNAPSHOT_TYPE
    assert stored.source == f'{delta.SNAPSHOT_SOURCE_PREFIX}{TEAM_ID}'
    assert stored.sync_run_id is None
    assert stored.data_through == date(2026, 8, 18)
    assert stored.published_at == datetime(2026, 8, 18, 12, 30)
    assert stored.payload['source']['sync_run_id'] == 12
    assert stored.payload['domains']['team_state']['method_version'] == TEAM_STATE_METHOD_VERSION
    assert stored.payload['domains']['team_state']['population_basis'] == {
        'basis': 'status_only',
        'population_authority': 'resolve_readiness_population',
        'membership_authority': 'resolve_active_bullpen_membership',
    }
    assert stored.payload['values']['team_state']['public_state'] == 'stretched'
    assert stored.payload['values']['team_state']['public_label'] == 'Stretched'
    assert stored.payload['values']['arm_read']['records'][0]['public_read'] == {
        'kind': 'read',
        'key': 'watch_arm',
        'label': 'Watch Arm',
        'source': 'backend:availability_status',
    }


def test_stamping_new_sidecar_does_not_rewrite_existing_dashboard_history(app):
    historical = DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        status='ready',
        is_published=False,
        published_at=datetime(2026, 8, 17, 12, 30),
        payload={'legacy': {'value': 'unchanged'}},
        payload_version=1,
        data_through=date(2026, 8, 17),
        snapshot_generated_at=datetime(2026, 8, 17, 12, 30),
        source='test',
    )
    db.session.add(historical)
    db.session.commit()
    historical_id = historical.id
    historical_payload = deepcopy(historical.payload)

    delta.stamp_prospective_snapshot(
        source=_source(),
        readiness=_readiness(),
        artifact=_artifact(),
    )
    db.session.commit()
    db.session.expire_all()

    unchanged = db.session.get(DashboardSnapshot, historical_id)
    assert unchanged.payload == historical_payload
    assert unchanged.snapshot_type == 'bullpen_dashboard'


def test_reentry_for_same_publication_identity_reuses_immutable_sidecar(app):
    original_capture = _arm_capture(date(2026, 8, 18), ((1, 'Available'),))
    original_workload = _workload_capture(date(2026, 8, 18))
    first = delta.stamp_prospective_snapshot(
        source=_source(), readiness=_readiness(), artifact=_artifact(),
        arm_read_capture=original_capture,
        workload_window_capture=original_workload,
    )
    db.session.commit()
    original_payload = deepcopy(first.payload)

    changed_capture = _arm_capture(date(2026, 8, 18), ((1, 'Monitor'),))
    changed_workload = _workload_capture(date(2026, 8, 18))
    changed_workload['windows']['window_7']['pitches_total'] = 999
    repeated = delta.stamp_prospective_snapshot(
        source=_source(), readiness=_readiness(), artifact=_artifact(),
        arm_read_capture=changed_capture,
        workload_window_capture=changed_workload,
    )
    db.session.commit()

    assert repeated.id == first.id
    assert DashboardSnapshot.query.filter_by(
        snapshot_type=delta.SNAPSHOT_TYPE,
    ).count() == 1
    assert repeated.payload == original_payload
    assert repeated.payload['values']['arm_read']['records'][0][
        'public_read'
    ]['label'] == 'Clean Option'
    assert repeated.payload['values']['workload_7d']['pitches_total'] == 36


def test_capture_failure_does_not_fail_the_authoritative_publication(app):
    readiness = _readiness()
    readiness['team_state_evidence'].pop('method_version')

    captured = delta.try_stamp_prospective_snapshot(
        source=_source(),
        readiness=readiness,
        artifact=_artifact(),
    )

    assert captured is None
    assert DashboardSnapshot.query.filter_by(snapshot_type=delta.SNAPSHOT_TYPE).count() == 0


def test_same_version_team_state_transition_is_comparable():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1, state='stretched')
    current = _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')

    result = delta.compare_snapshots(previous, current)

    comparison = result['domains']['team_state']
    assert comparison['status'] == delta.COMPARABLE
    assert comparison['previous']['public_state'] == 'stretched'
    assert comparison['current']['public_state'] == 'fresh'


def test_retained_team_state_1_2_shape_normalizes_without_mutating_sidecars():
    previous = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 17), snapshot_id=1, state='stretched')
    )
    current = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    )
    previous_before = deepcopy(previous.payload)
    current_before = deepcopy(current.payload)

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['previous'] == {
        'public_state': 'stretched', 'public_label': 'Stretched',
    }
    assert comparison['current'] == {
        'public_state': 'fresh', 'public_label': 'Fresh',
    }
    assert previous.payload == previous_before
    assert current.payload == current_before


def test_retained_team_state_1_2_unchanged_pair_is_comparable():
    previous = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 17), snapshot_id=1, state='fresh')
    )
    current = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['previous'] == comparison['current']


def test_retained_team_state_1_2_missing_sibling_label_normalizes():
    previous = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 17), snapshot_id=1)
    )
    current = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    )
    previous.payload['values']['team_state'].pop('public_label')

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['previous']['public_label'] == 'Stretched'


@pytest.mark.parametrize(
    'mutation',
    (
        lambda value: value['public_state'].__setitem__('public_code', None),
        lambda value: value['public_state'].__setitem__('public_label', None),
        lambda value: value.__setitem__('public_state', None),
    ),
)
def test_retained_team_state_1_2_true_missing_values_stay_withheld(mutation):
    previous = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 17), snapshot_id=1)
    )
    current = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    )
    mutation(previous.payload['values']['team_state'])

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.VALUE_MISSING


def test_retained_team_state_1_2_contradictory_flat_value_stays_withheld():
    previous = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 17), snapshot_id=1)
    )
    current = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    )
    previous.payload['values']['team_state']['public_label'] = 'Fresh'

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.VALUE_MISSING


def test_unknown_artifact_version_cannot_use_retained_shape_compatibility():
    previous = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 17), snapshot_id=1)
    )
    current = _retained_malformed_team_state_sidecar(
        _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    )
    previous.payload['source']['artifact_payload_version'] = 'team-state-unknown'

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.VALUE_MISSING


def test_method_version_mismatch_is_withheld():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)
    previous.payload['domains']['team_state']['method_version'] = 'v3_phase_4'

    assert delta.compare_snapshots(previous, current)['domains']['team_state'] == {
        'readiness': delta.READINESS_COMPARABLE_WHEN_STAMPED,
        'status': delta.METHOD_VERSION_MISMATCH,
        'reason_code': delta.METHOD_VERSION_MISMATCH,
    }


@pytest.mark.parametrize('side', ('previous', 'current'))
def test_unstamped_snapshot_is_withheld(side):
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)
    target = previous if side == 'previous' else current
    target.payload['domains']['team_state'].pop('method_version')

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.METHOD_VERSION_MISSING
    assert 'previous' not in comparison
    assert 'current' not in comparison


def test_incompatible_population_basis_is_withheld():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)
    current.payload['domains']['team_state']['population_basis']['membership_authority'] = (
        'different_membership_authority'
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.POPULATION_BASIS_MISMATCH


def test_missing_population_identity_is_withheld():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)
    previous.payload['domains']['team_state']['population_basis'][
        'population_authority'
    ] = None

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.POPULATION_BASIS_MISSING


def test_comparison_envelope_version_mismatch_is_withheld():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)
    previous.payload['envelope_version'] = 'team_board_delta_envelope_v0'

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.CONTRACT_INCOMPATIBLE


def test_missing_previous_snapshot_is_withheld():
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)

    comparison = delta.compare_snapshots(None, current)['domains']['team_state']

    assert comparison['status'] == delta.PREVIOUS_MISSING


def test_missing_current_snapshot_is_withheld():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)

    comparison = delta.compare_snapshots(previous, None)['domains']['team_state']

    assert comparison['status'] == delta.CURRENT_MISSING


def test_team_state_comparison_rejects_wrong_team_and_date_order():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    wrong_team = _snapshot(date(2026, 8, 18), snapshot_id=2)
    wrong_team.payload['team_id'] = TEAM_ID + 1
    reversed_date = _snapshot(date(2026, 8, 17), snapshot_id=3)

    assert delta.compare_snapshots(previous, wrong_team)['domains']['team_state'][
        'status'
    ] == delta.TEAM_ID_MISMATCH
    assert delta.compare_snapshots(previous, reversed_date)['domains']['team_state'][
        'status'
    ] == delta.REPRESENTED_DATE_INVALID


def test_untrusted_team_state_endpoint_is_withheld():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2)
    current.payload['domains']['team_state']['trusted'] = False

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.FRESHNESS_UNTRUSTED


def test_same_state_is_comparable_and_unchanged_is_not_authored_as_prose():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1, state='fresh')
    current = _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')

    comparison = delta.compare_snapshots(previous, current)['domains']['team_state']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['previous'] == comparison['current']
    assert 'changed' not in comparison
    assert 'improved' not in str(comparison).lower()
    assert 'worsened' not in str(comparison).lower()


def test_comparison_does_not_mutate_either_frozen_input():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    previous_before = deepcopy(previous.payload)
    current_before = deepcopy(current.payload)

    delta.compare_snapshots(previous, current)

    assert previous.payload == previous_before
    assert current.payload == current_before


def test_null_active_arm_count_is_withheld_not_normalized_to_zero():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1, active_count=None)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2, active_count=7)

    comparison = delta.compare_snapshots(previous, current)['domains']['active_arm_count']

    assert comparison['status'] == delta.VALUE_MISSING
    assert 'previous' not in comparison


def test_unready_domains_are_explicitly_withheld():
    result = delta.compare_snapshots(
        _snapshot(date(2026, 8, 17), snapshot_id=1),
        _snapshot(date(2026, 8, 18), snapshot_id=2),
    )

    assert result['domains']['team_state']['status'] == delta.COMPARABLE
    assert result['domains']['arm_read']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['workload_7d']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['workload_14d']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['rotation_impact']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['bullpen_membership']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['role_movement']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['roster_transactions']['status'] == delta.DOMAIN_NOT_INCLUDED


def test_rotation_impact_compares_frozen_outs_without_directional_judgment():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date, snapshot_id=1,
        rotation_capture=_rotation_capture(previous_date, bullpen_outs=18),
    )
    current = _snapshot(
        current_date, snapshot_id=2,
        rotation_capture=_rotation_capture(current_date, bullpen_outs=24),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['rotation_impact']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement'] is True
    assert 'bullpen_outs_required' in comparison['changed_fields']
    assert 'better' not in str(comparison).lower()
    assert 'worse' not in str(comparison).lower()


def test_rotation_impact_preserves_zero_and_fails_closed_on_contract_mismatch():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date, snapshot_id=1,
        rotation_capture=_rotation_capture(previous_date, bullpen_outs=0, short_starts=0),
    )
    current = _snapshot(
        current_date, snapshot_id=2,
        rotation_capture=_rotation_capture(current_date, bullpen_outs=0, short_starts=0),
    )
    comparison = delta.compare_snapshots(previous, current)['domains']['rotation_impact']
    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement'] is False
    assert comparison['previous']['bullpen_outs_required'] == 0

    current.payload['domains']['rotation_impact']['carrier_contract_version'] = 'v2'
    assert delta.compare_snapshots(previous, current)['domains']['rotation_impact'][
        'status'
    ] == delta.CONTRACT_INCOMPATIBLE


def test_bullpen_membership_reports_additions_and_removals_without_inventing_reasons():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date, snapshot_id=1,
        membership_capture=_membership_capture(
            previous_date, ((1, 'Stayed Arm'), (2, 'Removed Arm'))
        ),
    )
    current = _snapshot(
        current_date, snapshot_id=2,
        membership_capture=_membership_capture(
            current_date, ((1, 'Stayed Arm'), (3, 'Added Arm'))
        ),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['bullpen_membership']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement'] is True
    assert comparison['added'] == [{'pitcher_id': 3, 'pitcher_name': 'Added Arm'}]
    assert comparison['removed'] == [{'pitcher_id': 2, 'pitcher_name': 'Removed Arm'}]
    assert 'reason' not in comparison['added'][0]
    assert 'reason' not in comparison['removed'][0]


def test_membership_unchanged_and_empty_populations_are_comparable():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date, snapshot_id=1,
        membership_capture=_membership_capture(previous_date, ()),
    )
    current = _snapshot(
        current_date, snapshot_id=2,
        membership_capture=_membership_capture(current_date, ()),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['bullpen_membership']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement'] is False
    assert comparison['added'] == []
    assert comparison['removed'] == []


@pytest.mark.parametrize(
    ('before', 'after', 'added_count', 'removed_count'),
    (
        (((1, 'Stayed Arm'),), ((1, 'Stayed Arm'), (2, 'Added Arm')), 1, 0),
        (((1, 'Stayed Arm'), (2, 'Removed Arm')), ((1, 'Stayed Arm'),), 0, 1),
    ),
)
def test_membership_addition_and_removal_are_independently_descriptive(
    before, after, added_count, removed_count,
):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        membership_capture=_membership_capture(previous_date, before),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        membership_capture=_membership_capture(current_date, after),
    )

    comparison = delta.compare_snapshots(previous, current)['domains'][
        'bullpen_membership'
    ]

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement'] is True
    assert len(comparison['added']) == added_count
    assert len(comparison['removed']) == removed_count


def test_rotation_and_membership_domains_fail_independently():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date, snapshot_id=1,
        rotation_capture=_rotation_capture(previous_date),
        membership_capture=_membership_capture(previous_date, ((1, 'Arm'),)),
    )
    current = _snapshot(
        current_date, snapshot_id=2,
        rotation_capture=_rotation_capture(current_date),
        membership_capture=_membership_capture(current_date, ((1, 'Arm'),)),
    )
    current.payload['values'].pop('rotation_impact')

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['rotation_impact']['status'] == delta.VALUE_MISSING
    assert result['bullpen_membership']['status'] == delta.COMPARABLE


def test_missing_membership_value_leaves_rotation_comparable():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        rotation_capture=_rotation_capture(previous_date),
        membership_capture=_membership_capture(previous_date, ((1, 'Arm'),)),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        rotation_capture=_rotation_capture(current_date),
        membership_capture=_membership_capture(current_date, ((1, 'Arm'),)),
    )
    current.payload['values'].pop('bullpen_membership')

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['bullpen_membership']['status'] == delta.VALUE_MISSING
    assert result['rotation_impact']['status'] == delta.COMPARABLE


@pytest.mark.parametrize(
    ('field', 'bad_value', 'expected_status'),
    (
        ('roster_authority_version', None, delta.POPULATION_BASIS_MISMATCH),
        (
            'roster_authority_version',
            'wrong_roster_authority_version',
            delta.POPULATION_BASIS_MISMATCH,
        ),
        ('basis', 'wrong_population', delta.POPULATION_BASIS_MISMATCH),
        (
            'population_authority',
            'wrong_population_authority',
            delta.POPULATION_BASIS_MISMATCH,
        ),
        (
            'membership_authority',
            'wrong_membership_authority',
            delta.POPULATION_BASIS_MISMATCH,
        ),
    ),
)
def test_equally_malformed_membership_endpoints_never_compare(
    field, bad_value, expected_status,
):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        membership_capture=_membership_capture(previous_date, ((1, 'Arm'),)),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        membership_capture=_membership_capture(current_date, ((1, 'Arm'),)),
    )
    for endpoint in (previous, current):
        population = endpoint.payload['domains']['bullpen_membership'][
            'population_basis'
        ]
        if bad_value is None:
            population.pop(field)
        else:
            population[field] = bad_value

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['bullpen_membership']['status'] == expected_status
    assert result['rotation_impact']['status'] == delta.DOMAIN_NOT_READY


def test_equally_malformed_membership_reference_policy_never_compares():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        membership_capture=_membership_capture(previous_date, ((1, 'Arm'),)),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        membership_capture=_membership_capture(current_date, ((1, 'Arm'),)),
    )
    for endpoint in (previous, current):
        endpoint.payload['domains']['bullpen_membership'][
            'reference_date_policy'
        ] = 'wrong_reference_policy'

    comparison = delta.compare_snapshots(previous, current)['domains'][
        'bullpen_membership'
    ]

    assert comparison['status'] == delta.CONTRACT_INCOMPATIBLE


def test_equally_malformed_rotation_endpoints_never_compare():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        rotation_capture=_rotation_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        rotation_capture=_rotation_capture(current_date),
    )
    for endpoint in (previous, current):
        metadata = endpoint.payload['domains']['rotation_impact']
        metadata['population_basis']['basis'] = 'wrong_population'
        metadata['reference_date_policy'] = 'wrong_reference_policy'

    comparison = delta.compare_snapshots(previous, current)['domains'][
        'rotation_impact'
    ]

    assert comparison['status'] == delta.CONTRACT_INCOMPATIBLE


def test_missing_prior_prospective_arm_domain_does_not_block_team_state():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Available'),)),
    )

    result = delta.compare_snapshots(previous, current)

    assert result['domains']['arm_read']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['team_state']['status'] == delta.COMPARABLE


def test_workload_capture_copies_exact_same_cycle_carrier_without_calculation():
    represented_date = date(2026, 8, 18)
    snapshot = _workload_carrier_snapshot(represented_date)

    capture = delta.build_workload_window_capture(
        snapshot=snapshot,
        team_id=TEAM_ID,
    )

    assert capture['represented_date'] == represented_date.isoformat()
    assert capture['windows'] == snapshot.payload['trusted_team_boards'][
        'by_team_id'
    ][str(TEAM_ID)]['workload_windows']['windows']
    assert capture['windows'] is not snapshot.payload['trusted_team_boards'][
        'by_team_id'
    ][str(TEAM_ID)]['workload_windows']['windows']
    capture['windows']['window_7']['pitches_total'] = 999
    assert snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)][
        'workload_windows'
    ]['windows']['window_7']['pitches_total'] == 36
    assert capture['population_basis']['basis'] == (
        'official_appearance_team_relief_appearances'
    )
    assert capture['carrier_contract_version'] == (
        public_team_relief_work.WORKLOAD_WINDOWS_CARRIER_CONTRACT
    )


def test_rest_status_capture_copies_exact_frozen_carrier_without_recalculation():
    represented_date = date(2026, 8, 18)
    snapshot = _rest_status_carrier_snapshot(represented_date, rested_arm_count=6)

    capture = delta.build_rest_status_capture(snapshot=snapshot, team_id=TEAM_ID)

    frozen = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)][
        'rest_status'
    ]
    assert capture['value'] == frozen
    assert capture['value'] is not frozen
    assert capture['method_version'] == delta.REST_STATUS_METHOD_VERSION
    assert capture['availability_reference_date'] == '2026-08-19'


def test_rest_status_capture_fails_closed_for_wrong_authority():
    snapshot = _rest_status_carrier_snapshot(date(2026, 8, 18))
    snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)][
        'rest_status_authority'
    ]['public_contract_version'] = 'wrong-contract'

    with pytest.raises(delta.DeltaStampError, match='rest_status_authority_unproven'):
        delta.build_rest_status_capture(snapshot=snapshot, team_id=TEAM_ID)


def test_rotation_and_membership_capture_copy_same_cycle_publication_values():
    represented_date = date(2026, 8, 18)
    snapshot = _rotation_membership_carrier_snapshot(represented_date)
    frozen_team = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]

    rotation = delta.build_rotation_impact_capture(snapshot=snapshot, team_id=TEAM_ID)
    membership = delta.build_bullpen_membership_capture(snapshot=snapshot, team_id=TEAM_ID)

    assert rotation['value'] == frozen_team['rotation_support_pressure']
    assert rotation['value'] is not frozen_team['rotation_support_pressure']
    assert membership['member_pitcher_ids'] == [1, 2]
    assert membership['members'] == [
        {'pitcher_id': 1, 'pitcher_name': 'First Arm'},
        {'pitcher_id': 2, 'pitcher_name': 'Second Arm'},
    ]
    rotation['value']['bullpen_outs_required'] = 999
    membership['members'][0]['pitcher_name'] = 'Mutated'
    assert frozen_team['rotation_support_pressure']['bullpen_outs_required'] == 18
    assert frozen_team['records'][0]['name'] == 'First Arm'


@pytest.mark.parametrize(
    ('field', 'bad_value'),
    (
        ('basis', 'wrong_population'),
        ('population_authority', 'wrong_population_authority'),
        ('membership_authority', 'wrong_membership_authority'),
        ('roster_authority_version', None),
        ('roster_authority_version', 'wrong_roster_authority_version'),
    ),
)
def test_membership_capture_requires_exact_canonical_population_authority(
    field, bad_value,
):
    snapshot = _rotation_membership_carrier_snapshot(date(2026, 8, 18))
    authority = snapshot.payload['trusted_team_boards']['by_team_id'][
        str(TEAM_ID)
    ]['bullpen_membership_authority']
    population = authority['population_basis']
    if bad_value is None:
        population.pop(field)
    else:
        population[field] = bad_value

    with pytest.raises(delta.DeltaStampError, match='membership_population_basis_unproven'):
        delta.build_bullpen_membership_capture(snapshot=snapshot, team_id=TEAM_ID)
    assert delta.try_build_bullpen_membership_capture(
        snapshot=snapshot, team_id=TEAM_ID
    ) is None


@pytest.mark.parametrize('bad_value', (None, 'wrong_reference_policy'))
def test_membership_capture_requires_exact_reference_policy(bad_value):
    snapshot = _rotation_membership_carrier_snapshot(date(2026, 8, 18))
    authority = snapshot.payload['trusted_team_boards']['by_team_id'][
        str(TEAM_ID)
    ]['bullpen_membership_authority']
    if bad_value is None:
        authority.pop('reference_date_policy')
    else:
        authority['reference_date_policy'] = bad_value

    with pytest.raises(delta.DeltaStampError, match='membership_reference_date_unproven'):
        delta.build_bullpen_membership_capture(snapshot=snapshot, team_id=TEAM_ID)


@pytest.mark.parametrize(
    ('field', 'bad_value'),
    (
        ('basis', None),
        ('basis', 'wrong_population'),
        ('population_authority', 'wrong_population_authority'),
        ('membership_authority', 'wrong_membership_authority'),
    ),
)
def test_rotation_capture_requires_exact_canonical_population_authority(
    field, bad_value,
):
    snapshot = _rotation_membership_carrier_snapshot(date(2026, 8, 18))
    authority = snapshot.payload['trusted_team_boards']['by_team_id'][
        str(TEAM_ID)
    ]['rotation_support_pressure_authority']
    population = authority['population_basis']
    if bad_value is None:
        population.pop(field)
    else:
        population[field] = bad_value

    with pytest.raises(delta.DeltaStampError, match='rotation_population_basis_unproven'):
        delta.build_rotation_impact_capture(snapshot=snapshot, team_id=TEAM_ID)
    assert delta.try_build_rotation_impact_capture(
        snapshot=snapshot, team_id=TEAM_ID
    ) is None


@pytest.mark.parametrize('bad_value', (None, 'wrong_reference_policy'))
def test_rotation_capture_requires_exact_reference_policy(bad_value):
    snapshot = _rotation_membership_carrier_snapshot(date(2026, 8, 18))
    authority = snapshot.payload['trusted_team_boards']['by_team_id'][
        str(TEAM_ID)
    ]['rotation_support_pressure_authority']
    if bad_value is None:
        authority.pop('reference_date_policy')
    else:
        authority['reference_date_policy'] = bad_value

    with pytest.raises(delta.DeltaStampError, match='rotation_reference_date_unproven'):
        delta.build_rotation_impact_capture(snapshot=snapshot, team_id=TEAM_ID)


def test_missing_rotation_or_membership_carrier_is_not_reconstructed():
    snapshot = _rotation_membership_carrier_snapshot(date(2026, 8, 18))
    team = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]
    team.pop('rotation_support_pressure')
    team.pop('default_pitcher_ids')

    assert delta.build_rotation_impact_capture(snapshot=snapshot, team_id=TEAM_ID) is None
    assert delta.build_bullpen_membership_capture(snapshot=snapshot, team_id=TEAM_ID) is None


def test_workload_capture_preserves_legitimate_zero_values():
    represented_date = date(2026, 8, 18)
    zero = _workload_window(
        represented_date,
        relief_appearances=0,
        pitchers_in_relief=0,
        pitches_total=0,
        appearances_with_pitches=0,
    )
    carrier = {
        'contract': public_team_relief_work.WORKLOAD_WINDOWS_CARRIER_CONTRACT,
        'status': public_team_relief_work.WORKLOAD_WINDOWS_COMPLETE,
        'reason_code': None,
        'data_through': represented_date.isoformat(),
        'windows': {'window_7': zero, 'window_14': deepcopy(zero)},
    }

    capture = delta.build_workload_window_capture(
        snapshot=_workload_carrier_snapshot(represented_date, carrier=carrier),
        team_id=TEAM_ID,
    )

    assert capture['windows']['window_7']['relief_appearances'] == 0
    assert capture['windows']['window_7']['pitches_total'] == 0


def test_missing_or_withheld_workload_carrier_is_not_reconstructed():
    represented_date = date(2026, 8, 18)
    missing = _workload_carrier_snapshot(represented_date)
    missing.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)].pop(
        'workload_windows'
    )
    withheld = _workload_carrier_snapshot(represented_date)
    withheld.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)][
        'workload_windows'
    ].update({'status': 'withheld', 'reason_code': 'data_through_missing'})

    assert delta.build_workload_window_capture(
        snapshot=missing,
        team_id=TEAM_ID,
    ) is None
    assert delta.try_build_workload_window_capture(
        snapshot=withheld,
        team_id=TEAM_ID,
    ) is None


def test_workload_capture_rejects_wrong_team_identity():
    snapshot = _workload_carrier_snapshot(date(2026, 8, 18))
    snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_ID)]['team'][
        'team_id'
    ] = 999

    with pytest.raises(delta.DeltaStampError, match='team_identity_mismatch'):
        delta.build_workload_window_capture(snapshot=snapshot, team_id=TEAM_ID)


def test_workload_windows_freeze_into_sidecar_domains_independently():
    represented_date = date(2026, 8, 18)
    capture = _workload_capture(represented_date)

    envelope = delta.build_prospective_envelope(
        source=_source(represented_date=represented_date),
        readiness=_readiness(),
        artifact=_artifact(),
        workload_window_capture=capture,
    )

    assert envelope['domains']['workload_7d']['window_days'] == 7
    assert envelope['domains']['workload_14d']['window_days'] == 14
    assert envelope['domains']['workload_7d']['carrier_contract_version'] == (
        public_team_relief_work.WORKLOAD_WINDOWS_CARRIER_CONTRACT
    )
    assert envelope['domains']['workload_14d']['carrier_contract_version'] == (
        public_team_relief_work.WORKLOAD_WINDOWS_CARRIER_CONTRACT
    )
    assert envelope['values']['workload_7d'] == capture['windows']['window_7']
    assert envelope['values']['workload_14d'] == capture['windows']['window_14']


@pytest.mark.parametrize(
    ('previous_pitches', 'current_pitches', 'movement'),
    ((2, 4, True), (4, 2, True), (3, 3, False), (0, 2, True), (2, 0, True), (0, 0, False)),
)
def test_workload_comparison_preserves_changed_unchanged_and_zero(
    previous_pitches,
    current_pitches,
    movement,
):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(
            previous_date,
            window_7=_workload_window(
                previous_date,
                relief_appearances=2,
                pitches_total=previous_pitches,
            ),
        ),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(
            current_date,
            window_7=_workload_window(
                current_date,
                relief_appearances=2,
                pitches_total=current_pitches,
            ),
        ),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['workload_7d']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement'] is movement
    assert ('pitches_total' in comparison['changed_fields']) is movement


def test_workload_7d_and_14d_compare_independently():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current_capture = _workload_capture(current_date)
    current_capture['windows']['window_14']['pitches_total'] = 90
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=current_capture,
    )

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['workload_7d']['movement'] is False
    assert result['workload_14d']['movement'] is True
    assert result['workload_14d']['changed_fields'] == ['pitches_total']


def test_workload_7d_change_leaves_unchanged_14d_comparable():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current_capture = _workload_capture(current_date)
    current_capture['windows']['window_7']['pitches_total'] = 54
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=current_capture,
    )

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['workload_7d']['status'] == delta.COMPARABLE
    assert result['workload_7d']['movement'] is True
    assert result['workload_7d']['changed_fields'] == ['pitches_total']
    assert result['workload_14d']['status'] == delta.COMPARABLE
    assert result['workload_14d']['movement'] is False


@pytest.mark.parametrize(
    ('missing_domain', 'comparable_domain'),
    (
        ('workload_7d', 'workload_14d'),
        ('workload_14d', 'workload_7d'),
    ),
)
def test_domain_local_missing_workload_value_leaves_sibling_comparable(
    missing_domain,
    comparable_domain,
):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(current_date),
    )
    current.payload['values'].pop(missing_domain)

    result = delta.compare_snapshots(previous, current)['domains']

    assert result[missing_domain]['status'] == delta.VALUE_MISSING
    assert result[comparable_domain]['status'] == delta.COMPARABLE
    assert result[comparable_domain]['movement'] is False


def test_matching_workload_carrier_versions_compare_successfully():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(current_date),
    )

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['workload_7d']['status'] == delta.COMPARABLE
    assert result['workload_14d']['status'] == delta.COMPARABLE


def test_mismatched_workload_carrier_version_invalidates_both_domains():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(current_date),
    )
    for domain in ('workload_7d', 'workload_14d'):
        current.payload['domains'][domain]['carrier_contract_version'] = (
            'team_board_workload_windows_carrier_v2'
        )

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['workload_7d']['status'] == delta.CONTRACT_INCOMPATIBLE
    assert result['workload_14d']['status'] == delta.CONTRACT_INCOMPATIBLE


@pytest.mark.parametrize('endpoint', ('previous', 'current'))
def test_missing_workload_carrier_version_fails_closed(endpoint):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(current_date),
    )
    selected = previous if endpoint == 'previous' else current
    for domain in ('workload_7d', 'workload_14d'):
        selected.payload['domains'][domain].pop('carrier_contract_version')

    result = delta.compare_snapshots(previous, current)['domains']

    assert result['workload_7d']['status'] == delta.CONTRACT_INCOMPATIBLE
    assert result['workload_14d']['status'] == delta.CONTRACT_INCOMPATIBLE


def test_partial_pitch_coverage_compares_the_frozen_known_pitch_claim():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous_window = _workload_window(
        previous_date,
        relief_appearances=2,
        pitches_total=None,
        appearances_with_pitches=1,
    )
    current_window = _workload_window(
        current_date,
        relief_appearances=2,
        pitches_total=None,
        appearances_with_pitches=1,
    )
    previous_window['pitches_sentence'] = (
        'Pitch count unavailable for 1 of 2 relief appearances; '
        '18 pitches across the other 1.'
    )
    current_window['pitches_sentence'] = (
        'Pitch count unavailable for 1 of 2 relief appearances; '
        '24 pitches across the other 1.'
    )
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(
            previous_date,
            window_7=previous_window,
        ),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(
            current_date,
            window_7=current_window,
        ),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['workload_7d']

    assert comparison['movement'] is True
    assert comparison['changed_fields'] == ['pitches_sentence']


@pytest.mark.parametrize(
    ('field', 'reason'),
    (
        ('method_version', delta.METHOD_VERSION_MISMATCH),
        ('public_contract_version', delta.CONTRACT_INCOMPATIBLE),
        ('population_basis', delta.POPULATION_BASIS_MISMATCH),
    ),
)
def test_workload_compatibility_fails_closed_on_authority_mismatch(field, reason):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(current_date),
    )
    current.payload['domains']['workload_7d'][field] = (
        {'basis': 'different', 'population_authority': 'different', 'membership_authority': 'different'}
        if field == 'population_basis'
        else 'different'
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['workload_7d']

    assert comparison['status'] == reason


def test_untrusted_or_invalidly_ordered_workload_endpoints_fail_closed():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date,
        snapshot_id=1,
        workload_capture=_workload_capture(previous_date),
    )
    current = _snapshot(
        current_date,
        snapshot_id=2,
        workload_capture=_workload_capture(current_date),
    )
    current.payload['domains']['workload_7d']['trusted'] = False

    assert delta.compare_snapshots(previous, current)['domains']['workload_7d'][
        'status'
    ] == delta.FRESHNESS_UNTRUSTED
    assert delta.compare_snapshots(current, previous)['domains']['workload_7d'][
        'status'
    ] == delta.REPRESENTED_DATE_INVALID


@pytest.mark.parametrize(
    ('previous_status', 'current_status', 'previous_label', 'current_label'),
    (
        ('Available', 'Monitor', 'Clean Option', 'Watch Arm'),
        ('Monitor', 'Limited', 'Watch Arm', 'Limited Rest'),
        ('Avoid', 'Available', 'Limited Rest', 'Clean Option'),
    ),
)
def test_frozen_public_read_key_changes_produce_movement_candidates(
    previous_status, current_status, previous_label, current_label,
):
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, previous_status),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, current_status),)),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.COMPARABLE
    assert len(comparison['movement_candidates']) == 1
    movement = comparison['movement_candidates'][0]
    assert movement['previous']['public_read']['label'] == previous_label
    assert movement['current']['public_read']['label'] == current_label


def test_internal_status_change_without_public_read_change_produces_no_movement():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Limited'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Avoid'),)),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['movement_candidates'] == []
    assert comparison['arm_comparisons'][0]['movement'] is False
    assert comparison['arm_comparisons'][0]['previous']['public_read']['key'] == 'rest_restricted'
    assert comparison['arm_comparisons'][0]['current']['public_read']['key'] == 'rest_restricted'


def test_capture_freezes_limited_read_when_evidence_is_not_current():
    record = _arm_record(1, 'Available', data_state='stale', confidence='low')
    capture = delta.build_arm_read_capture(
        records=(record,), team_id=TEAM_ID, membership=({1}, True),
        membership_reference_date=date(2026, 8, 18),
        availability_reference_date=date(2026, 8, 19),
    )

    assert capture['records'][0]['public_read']['key'] == 'limited_read'
    assert capture['records'][0]['public_read']['label'] == 'Limited Read'


def test_capture_freezes_roster_authority_unavailable_as_unavailable():
    record = _arm_record(1, 'Available', roster_status='IL_15')
    record['roster_status'] = {
        'status': 'IL_15',
        'is_authoritative': True,
        'is_active_mlb': False,
        'is_inactive_context': True,
        'source': 'governed_test_roster_authority',
    }
    capture = delta.build_arm_read_capture(
        records=(record,), team_id=TEAM_ID, membership=({1}, True),
        membership_reference_date=date(2026, 8, 18),
        availability_reference_date=date(2026, 8, 19),
    )

    assert capture['records'][0]['public_read']['key'] == 'unavailable'
    assert capture['records'][0]['public_read']['label'] == 'Unavailable'
    assert capture['records'][0]['roster_authority']['status'] == 'IL_15'


def test_limited_read_to_watch_arm_is_a_legitimate_frozen_movement():
    previous_record = _arm_record(1, 'Available', data_state='stale', confidence='low')
    previous_capture = delta.build_arm_read_capture(
        records=(previous_record,), team_id=TEAM_ID, membership=({1}, True),
        membership_reference_date=date(2026, 8, 17),
        availability_reference_date=date(2026, 8, 18),
    )
    current_capture = _arm_capture(date(2026, 8, 18), ((1, 'Monitor'),))
    comparison = delta.compare_snapshots(
        _snapshot(date(2026, 8, 17), snapshot_id=1, arm_capture=previous_capture),
        _snapshot(date(2026, 8, 18), snapshot_id=2, arm_capture=current_capture),
    )['domains']['arm_read']

    movement = comparison['movement_candidates'][0]
    assert movement['previous']['public_read']['label'] == 'Limited Read'
    assert movement['current']['public_read']['label'] == 'Watch Arm'


def test_watch_arm_to_limited_read_is_a_legitimate_frozen_movement():
    current_record = _arm_record(
        1, 'Available', data_state='incomplete', confidence='low',
    )
    current_capture = delta.build_arm_read_capture(
        records=(current_record,), team_id=TEAM_ID, membership=({1}, True),
        membership_reference_date=date(2026, 8, 18),
        availability_reference_date=date(2026, 8, 19),
    )
    comparison = delta.compare_snapshots(
        _snapshot(
            date(2026, 8, 17), snapshot_id=1,
            arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Monitor'),)),
        ),
        _snapshot(date(2026, 8, 18), snapshot_id=2, arm_capture=current_capture),
    )['domains']['arm_read']

    movement = comparison['movement_candidates'][0]
    assert movement['previous']['public_read']['label'] == 'Watch Arm'
    assert movement['current']['public_read']['label'] == 'Limited Read'


def test_limited_read_to_limited_read_produces_no_movement():
    captures = []
    for represented_date in (date(2026, 8, 17), date(2026, 8, 18)):
        record = _arm_record(
            1, 'Available', data_state='stale', confidence='low',
        )
        captures.append(delta.build_arm_read_capture(
            records=(record,), team_id=TEAM_ID, membership=({1}, True),
            membership_reference_date=represented_date,
            availability_reference_date=represented_date + timedelta(days=1),
        ))

    comparison = delta.compare_snapshots(
        _snapshot(date(2026, 8, 17), snapshot_id=1, arm_capture=captures[0]),
        _snapshot(date(2026, 8, 18), snapshot_id=2, arm_capture=captures[1]),
    )['domains']['arm_read']

    assert comparison['movement_candidates'] == []
    assert comparison['arm_comparisons'][0]['movement'] is False
    assert comparison['arm_comparisons'][0]['current']['public_read']['key'] == 'limited_read'


def test_arm_read_contract_version_mismatch_is_not_comparable():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['domains']['arm_read']['public_contract_version'] = 'future_v2'

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.CONTRACT_INCOMPATIBLE


def test_arm_read_method_version_mismatch_is_not_comparable():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['domains']['arm_read']['method_version'] = 'future_method_v2'

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.METHOD_VERSION_MISMATCH
    assert delta.compare_snapshots(previous, current)['domains']['team_state'][
        'status'
    ] == delta.COMPARABLE


def test_arm_read_noncanonical_public_label_is_withheld():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['values']['arm_read']['records'][0]['public_read'][
        'label'
    ] = 'Monitor'

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.VALUE_MISSING
    assert 'movement_candidates' not in comparison


def test_arm_read_reference_dates_must_match_the_published_representation():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['domains']['arm_read'][
        'availability_reference_date'
    ] = '2026-08-18'

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.REPRESENTED_DATE_INVALID


def test_arm_read_missing_public_pitcher_name_withholds_only_that_arm():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['values']['arm_read']['records'][0]['pitcher_name'] = None

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.COMPARABLE
    assert comparison['movement_candidates'] == []
    assert comparison['arm_comparisons'][0]['comparable'] is False
    assert comparison['arm_comparisons'][0]['reason_code'] == delta.VALUE_MISSING


def test_arm_read_nonincreasing_snapshot_dates_are_not_comparable():
    previous = _snapshot(
        date(2026, 8, 18), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.REPRESENTED_DATE_INVALID


def test_arm_read_untrusted_publication_is_not_comparable():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['domains']['arm_read']['trusted'] = False

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.FRESHNESS_UNTRUSTED


def test_label_change_under_bumped_public_contract_is_not_reinterpreted():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Available'),)),
    )
    current.payload['domains']['arm_read']['public_contract_version'] = 'future_copy_v2'
    current.payload['values']['arm_read']['records'][0]['public_read'][
        'label'
    ] = 'Future Clean Label'

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.CONTRACT_INCOMPATIBLE
    assert 'movement_candidates' not in comparison


def test_arm_read_population_authority_mismatch_is_not_comparable():
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), ((1, 'Available'),)),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Monitor'),)),
    )
    current.payload['domains']['arm_read']['population_basis'][
        'membership_authority'
    ] = 'future_membership_authority'

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['status'] == delta.POPULATION_BASIS_MISMATCH


def test_missing_frozen_read_is_not_comparable_for_that_arm():
    previous_capture = _arm_capture(date(2026, 8, 17), (), member_ids=(1,))
    current_capture = _arm_capture(date(2026, 8, 18), ((1, 'Available'),))
    comparison = delta.compare_snapshots(
        _snapshot(date(2026, 8, 17), snapshot_id=1, arm_capture=previous_capture),
        _snapshot(date(2026, 8, 18), snapshot_id=2, arm_capture=current_capture),
    )['domains']['arm_read']

    assert comparison['movement_candidates'] == []
    assert comparison['arm_comparisons'][0]['comparable'] is False
    assert comparison['arm_comparisons'][0]['reason_code'] == delta.VALUE_MISSING


@pytest.mark.parametrize(
    ('previous_statuses', 'current_statuses', 'population_change', 'reason'),
    (
        ((), ((1, 'Available'),), 'added', delta.PREVIOUS_MISSING),
        (((1, 'Available'),), (), 'removed', delta.CURRENT_MISSING),
    ),
)
def test_population_changes_do_not_invent_a_public_read_endpoint(
    previous_statuses, current_statuses, population_change, reason,
):
    previous = _snapshot(
        date(2026, 8, 17), snapshot_id=1,
        arm_capture=_arm_capture(date(2026, 8, 17), previous_statuses),
    )
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), current_statuses),
    )

    comparison = delta.compare_snapshots(previous, current)['domains']['arm_read']

    assert comparison['movement_candidates'] == []
    assert comparison['arm_comparisons'][0]['population_change'] == population_change
    assert comparison['arm_comparisons'][0]['reason_code'] == reason


def test_capture_preserves_represented_and_reference_dates():
    capture = _arm_capture(date(2026, 8, 18), ((1, 'Available'),))
    envelope = delta.build_prospective_envelope(
        source=_source(represented_date=date(2026, 8, 18)),
        readiness=_readiness(), artifact=_artifact(), arm_read_capture=capture,
    )

    assert envelope['represented_date'] == '2026-08-18'
    assert capture['membership_reference_date'] == '2026-08-18'
    assert capture['availability_reference_date'] == '2026-08-19'


def test_previous_snapshot_resolver_uses_nearest_prior_represented_date(app):
    for represented_date, artifact_id in (
        (date(2026, 8, 14), 41),
        (date(2026, 8, 17), 42),
    ):
        delta.stamp_prospective_snapshot(
            source=_source(represented_date=represented_date, snapshot_id=artifact_id),
            readiness=_readiness(),
            artifact=_artifact(artifact_id=artifact_id),
        )
    # Another team must not enter this team's candidate set.
    other = _source(represented_date=date(2026, 8, 17), snapshot_id=99)
    other.team_id = 999
    delta.stamp_prospective_snapshot(
        source=other,
        readiness=_readiness(),
        artifact=_artifact(artifact_id=99),
    )
    db.session.commit()

    previous = delta.get_previous_snapshot(
        team_id=TEAM_ID,
        represented_date=date(2026, 8, 18),
    )

    assert previous.data_through == date(2026, 8, 17)
    assert previous.payload['source']['artifact_id'] == 42


def test_previous_snapshot_resolution_is_one_bounded_query(app):
    delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 17), snapshot_id=41),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=41),
    )
    db.session.commit()
    statements = []

    def _capture(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture)
    try:
        previous = delta.get_previous_snapshot(
            team_id=TEAM_ID,
            represented_date=date(2026, 8, 18),
        )
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture)

    assert previous is not None
    assert len(statements) == 1
    assert 'LIMIT' in statements[0].upper()


def test_latest_team_state_resolver_uses_nearest_compatible_publication(app):
    _persist_artifact(41, date(2026, 8, 16))
    _persist_artifact(42, date(2026, 8, 17))
    _persist_artifact(43, date(2026, 8, 18))
    older = delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 16), snapshot_id=41),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=41, state='stretched', label='Stretched'),
    )
    incompatible = delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 17), snapshot_id=42),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=42, state='fresh', label='Fresh'),
    )
    current = delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 18), snapshot_id=43),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=43, state='vulnerable', label='Vulnerable'),
    )
    payload = deepcopy(incompatible.payload)
    payload['domains']['team_state']['method_version'] = 'incompatible-method'
    incompatible.payload = payload
    db.session.commit()

    result = delta.resolve_latest_team_state_comparison(team_id=TEAM_ID)

    assert result['comparison'] == {
        'team_id': TEAM_ID,
        'from_represented_date': '2026-08-16',
        'to_represented_date': '2026-08-18',
        'previous_delta_snapshot_id': older.id,
        'current_delta_snapshot_id': current.id,
    }
    assert result['domains']['team_state']['status'] == delta.COMPARABLE
    assert result['domains']['team_state']['previous']['public_label'] == 'Stretched'
    assert result['domains']['team_state']['current']['public_label'] == 'Vulnerable'


def test_latest_team_state_resolver_returns_nearest_failure_when_none_compare(app):
    _persist_artifact(41, date(2026, 8, 17))
    _persist_artifact(42, date(2026, 8, 18))
    previous = delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 17), snapshot_id=41),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=41),
    )
    delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 18), snapshot_id=42),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=42, state='fresh', label='Fresh'),
    )
    payload = deepcopy(previous.payload)
    payload['domains']['team_state']['public_contract_version'] = 'incompatible-contract'
    previous.payload = payload
    db.session.commit()

    result = delta.resolve_latest_team_state_comparison(team_id=TEAM_ID)

    assert result['domains']['team_state']['status'] == delta.CONTRACT_INCOMPATIBLE
    assert result['comparison']['from_represented_date'] == '2026-08-17'
    assert result['comparison']['to_represented_date'] == '2026-08-18'


def test_latest_team_state_resolver_never_falls_back_to_a_superseded_artifact(app):
    superseded = _persist_artifact(41, date(2026, 8, 17))
    replacement = _persist_artifact(42, date(2026, 8, 17))
    _persist_artifact(43, date(2026, 8, 18))
    older = delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 17), snapshot_id=41),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=superseded.id, state='fresh', label='Fresh'),
    )
    corrected = delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 17), snapshot_id=42),
        readiness=_readiness(),
        artifact=_artifact(
            artifact_id=replacement.id, state='stretched', label='Stretched',
        ),
    )
    delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 18), snapshot_id=43),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=43, state='vulnerable', label='Vulnerable'),
    )
    superseded.lifecycle_state = 'superseded'
    superseded.superseded_at = datetime(2026, 8, 18, 13, 0)
    payload = deepcopy(corrected.payload)
    payload['domains']['team_state']['method_version'] = 'incompatible-method'
    corrected.payload = payload
    db.session.commit()

    result = delta.resolve_latest_team_state_comparison(team_id=TEAM_ID)

    assert result['domains']['team_state']['status'] == delta.METHOD_VERSION_MISMATCH
    assert result['comparison']['previous_delta_snapshot_id'] == corrected.id
    assert result['comparison']['previous_delta_snapshot_id'] != older.id


def test_latest_team_state_resolver_does_not_roll_back_a_withdrawn_current_date(app):
    _persist_artifact(41, date(2026, 8, 16))
    withdrawn = _persist_artifact(42, date(2026, 8, 17))
    delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 16), snapshot_id=41),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=41, state='fresh', label='Fresh'),
    )
    delta.stamp_prospective_snapshot(
        source=_source(represented_date=date(2026, 8, 17), snapshot_id=42),
        readiness=_readiness(),
        artifact=_artifact(artifact_id=42, state='stretched', label='Stretched'),
    )
    withdrawn.lifecycle_state = 'withdrawn'
    withdrawn.withdrawn_at = datetime(2026, 8, 18, 13, 0)
    withdrawn.withdrawn_reason = 'source correction'
    db.session.commit()

    result = delta.resolve_latest_team_state_comparison(team_id=TEAM_ID)

    assert result['domains']['team_state']['status'] == delta.CURRENT_MISSING
    assert result['comparison']['from_represented_date'] is None
    assert result['comparison']['to_represented_date'] is None


def test_latest_team_state_resolver_uses_one_bounded_source_select_for_legacy_rest(app):
    _persist_artifact(41, date(2026, 8, 17))
    _persist_artifact(42, date(2026, 8, 18))
    for represented_date, artifact_id in (
        (date(2026, 8, 17), 41),
        (date(2026, 8, 18), 42),
    ):
        delta.stamp_prospective_snapshot(
            source=_source(
                represented_date=represented_date, snapshot_id=artifact_id,
            ),
            readiness=_readiness(),
            artifact=_artifact(artifact_id=artifact_id),
        )
    db.session.commit()
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', capture)
    try:
        result = delta.resolve_latest_team_state_comparison(team_id=TEAM_ID)
    finally:
        event.remove(db.engine, 'before_cursor_execute', capture)

    assert result['domains']['team_state']['status'] == delta.COMPARABLE
    assert len(statements) == 3
    assert sum('FROM dashboard_snapshots' in statement for statement in statements) == 2


@pytest.mark.parametrize(('previous_count', 'current_count'), ((5, 7), (7, 5)))
def test_rest_status_compares_frozen_rested_options(previous_count, current_count):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(
        previous_date, snapshot_id=1,
        rest_status_capture=_rest_status_capture(previous_date, previous_count),
    )
    current = _snapshot(
        current_date, snapshot_id=2,
        rest_status_capture=_rest_status_capture(current_date, current_count),
    )

    result = delta.compare_snapshots(previous, current)['domains']['rest_status']

    assert result['status'] == delta.COMPARABLE
    assert result['movement'] is True
    assert result['changed_fields'] == ['rested_arm_count']
    assert result['previous']['rested_arm_count'] == previous_count
    assert result['current']['rested_arm_count'] == current_count


def test_rest_status_same_value_is_comparable_without_movement():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    result = delta.compare_snapshots(
        _snapshot(previous_date, snapshot_id=1, rest_status_capture=_rest_status_capture(previous_date)),
        _snapshot(current_date, snapshot_id=2, rest_status_capture=_rest_status_capture(current_date)),
    )['domains']['rest_status']

    assert result['status'] == delta.COMPARABLE
    assert result['movement'] is False


@pytest.mark.parametrize(
    ('mutation', 'reason'),
    (
        (lambda payload: payload['domains']['rest_status'].__setitem__('method_version', 'wrong'), delta.METHOD_VERSION_MISMATCH),
        (lambda payload: payload['domains']['rest_status'].__setitem__('population_basis', {'basis': 'wrong'}), delta.POPULATION_BASIS_MISSING),
        (lambda payload: payload['domains']['rest_status'].__setitem__('trusted', False), delta.FRESHNESS_UNTRUSTED),
        (lambda payload: payload['values'].__setitem__('rest_status', None), delta.VALUE_MISSING),
    ),
)
def test_rest_status_comparison_fails_closed_for_incompatible_authority(mutation, reason):
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    previous = _snapshot(previous_date, snapshot_id=1, rest_status_capture=_rest_status_capture(previous_date))
    current = _snapshot(current_date, snapshot_id=2, rest_status_capture=_rest_status_capture(current_date))
    mutation(previous.payload)

    result = delta.compare_snapshots(previous, current)['domains']['rest_status']

    assert result['status'] == reason


def test_governed_unavailable_rest_status_is_not_a_comparable_zero():
    previous_date = date(2026, 8, 17)
    current_date = date(2026, 8, 18)
    capture = _rest_status_capture(previous_date)
    capture['value'] = {
        'available': False,
        'active_arm_count': None,
        'rested_arm_count': None,
        'worked_yesterday_count': None,
        'back_to_back_count': None,
        'summary': None,
        'reason_code': 'roster_authority_unavailable',
    }

    result = delta.compare_snapshots(
        _snapshot(previous_date, snapshot_id=1, rest_status_capture=capture),
        _snapshot(current_date, snapshot_id=2, rest_status_capture=_rest_status_capture(current_date)),
    )['domains']['rest_status']

    assert result['status'] == delta.VALUE_MISSING


def test_team_state_comparison_requires_both_frozen_public_labels():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(date(2026, 8, 18), snapshot_id=2, state='fresh')
    previous.payload['values']['team_state']['public_label'] = None

    result = delta.compare_snapshots(previous, current)

    assert result['domains']['team_state']['status'] == delta.VALUE_MISSING


def test_comparison_source_contains_no_historical_recompute_path():
    source = (REPO_ROOT / 'backend/services/team_board_delta_substrate.py').read_text(
        encoding='utf-8'
    )

    for forbidden in (
        'resolve_team_readiness_payload',
        'assemble_bullpen_readiness',
        'classify_latest_fatigue_rows',
        'recalculate_all_fatigue',
        'author_workload_windows',
        'build_public_team_relief_work_payload',
        'author_rest_status',
        'build_rest_status(',
        'GameLog.query',
    ):
        assert forbidden not in source
