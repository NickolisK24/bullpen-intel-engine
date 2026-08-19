"""TB-09A prospective Team Board comparison-substrate contract."""

from copy import deepcopy
from datetime import date, datetime
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


def _snapshot(
    represented_date,
    *,
    snapshot_id,
    state='stretched',
    active_count=7,
):
    envelope = delta.build_prospective_envelope(
        source=_source(represented_date=represented_date, snapshot_id=100 + snapshot_id),
        readiness=_readiness(active_count=active_count),
        artifact=_artifact(artifact_id=200 + snapshot_id, state=state, label=state.title()),
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
    row = delta.stamp_prospective_snapshot(
        source=_source(),
        readiness=_readiness(),
        artifact=_artifact(),
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

    assert result['domains']['arm_read']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['role_movement']['status'] == delta.DOMAIN_NOT_READY
    assert result['domains']['roster_transactions']['status'] == delta.DOMAIN_NOT_INCLUDED


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
