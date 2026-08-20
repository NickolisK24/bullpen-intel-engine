"""TB-09A prospective Team Board comparison-substrate contract."""

from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask
from sqlalchemy import event

from models.dashboard_snapshot import DashboardSnapshot
from services import team_board_delta_substrate as delta
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
                'public_state': state,
                'public_label': label,
            },
        },
    )


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
):
    envelope = delta.build_prospective_envelope(
        source=_source(represented_date=represented_date, snapshot_id=100 + snapshot_id),
        readiness=_readiness(active_count=active_count),
        artifact=_artifact(artifact_id=200 + snapshot_id, state=state, label=state.title()),
        arm_read_capture=arm_capture,
    )
    return SimpleNamespace(id=snapshot_id, payload=envelope)


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


def test_prospective_envelope_refuses_a_method_stamp_that_drifted_from_owner():
    readiness = _readiness()
    readiness['team_state_evidence']['method_version'] = 'v3_phase_4'

    with pytest.raises(delta.DeltaStampError, match='method_version_unproven'):
        delta.build_prospective_envelope(
            source=_source(),
            readiness=readiness,
            artifact=_artifact(),
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
    first = delta.stamp_prospective_snapshot(
        source=_source(), readiness=_readiness(), artifact=_artifact(),
        arm_read_capture=original_capture,
    )
    db.session.commit()
    original_payload = deepcopy(first.payload)

    changed_capture = _arm_capture(date(2026, 8, 18), ((1, 'Monitor'),))
    repeated = delta.stamp_prospective_snapshot(
        source=_source(), readiness=_readiness(), artifact=_artifact(),
        arm_read_capture=changed_capture,
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
    assert result['domains']['role_movement']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['roster_transactions']['status'] == delta.DOMAIN_NOT_INCLUDED


def test_missing_prior_prospective_arm_domain_does_not_block_team_state():
    previous = _snapshot(date(2026, 8, 17), snapshot_id=1)
    current = _snapshot(
        date(2026, 8, 18), snapshot_id=2,
        arm_capture=_arm_capture(date(2026, 8, 18), ((1, 'Available'),)),
    )

    result = delta.compare_snapshots(previous, current)

    assert result['domains']['arm_read']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['team_state']['status'] == delta.COMPARABLE


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
    ):
        assert forbidden not in source
