from datetime import date
from types import SimpleNamespace

import pytest
from flask import Flask

from services import league_team_state_artifact_recovery as recovery
from services.mlb_club_directory import MLB_TEAM_IDS
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


SNAPSHOT_ID = 3435
SYNC_RUN_ID = 84413
PRODUCT_DATE = date(2026, 9, 22)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _snapshot():
    return SimpleNamespace(
        id=SNAPSHOT_ID,
        sync_run_id=SYNC_RUN_ID,
        data_through=PRODUCT_DATE,
        status='ready',
        is_published=True,
        payload={},
    )


def _artifacts():
    return [
        SimpleNamespace(
            id=index,
            team_id=team_id,
            lifecycle_state='published',
            subject_type=None,
            source_snapshot_id=SNAPSHOT_ID,
            source_sync_run_id=SYNC_RUN_ID,
            product_date=PRODUCT_DATE,
        )
        for index, team_id in enumerate(MLB_TEAM_IDS, 1)
    ]


@pytest.fixture
def governed_projection(monkeypatch):
    monkeypatch.setattr(
        recovery,
        'receipt_value',
        lambda _snapshot, team_id: (
            True,
            {
                'available': True,
                'public_state': 'fresh',
                'public_label': 'Fresh',
                'data_through': PRODUCT_DATE.isoformat(),
                'team_id': team_id,
            },
        ),
    )
    monkeypatch.setattr(
        recovery,
        'project_published_team_state_artifact',
        lambda _artifact, **_kwargs: {
            'available': True,
            'public_state': 'fresh',
            'public_label': 'Fresh',
            'data_through': PRODUCT_DATE.isoformat(),
        },
    )


def test_complete_set_is_a_zero_write_noop(monkeypatch, governed_projection):
    monkeypatch.setattr(
        recovery, 'list_team_state_artifacts_for_snapshot',
        lambda *_args, **_kwargs: _artifacts(),
    )
    result = recovery.repair_current_snapshot_artifacts(_snapshot())
    assert result.outcome == 'already_complete'
    assert result.artifact_count == 30
    assert result.team_ids == tuple(sorted(MLB_TEAM_IDS))


def test_missing_set_is_repaired_from_frozen_generator(
    monkeypatch, governed_projection,
):
    reads = iter(([], _artifacts()))
    monkeypatch.setattr(
        recovery, 'list_team_state_artifacts_for_snapshot',
        lambda *_args, **_kwargs: next(reads),
    )
    batch = SimpleNamespace(
        failed_count=0, refused_count=0, missing_count=0,
        generated_count=30, reused_count=0,
    )
    observed = {}

    def generate(snapshot, *, generator):
        observed.update(snapshot=snapshot, generator=generator)
        return batch

    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        generate,
    )
    frozen = object()
    monkeypatch.setattr(
        'services.team_state_vnext_production_proof.frozen_team_state_artifact_generator',
        lambda snapshot, generator=None: frozen,
    )

    result = recovery.repair_current_snapshot_artifacts(_snapshot())

    assert result.outcome == 'repaired'
    assert result.generated_count == 30
    assert observed == {'snapshot': observed['snapshot'], 'generator': frozen}
    assert observed['snapshot'].id == SNAPSHOT_ID


def test_incomplete_generation_fails_closed(monkeypatch, governed_projection):
    monkeypatch.setattr(
        recovery, 'list_team_state_artifacts_for_snapshot',
        lambda *_args, **_kwargs: [],
    )
    monkeypatch.setattr(
        'services.share_artifact_publication_hook.run_post_publication_generation',
        lambda *_args, **_kwargs: SimpleNamespace(
            failed_count=1, refused_count=0, missing_count=0,
            generated_count=29, reused_count=0,
        ),
    )
    monkeypatch.setattr(
        'services.team_state_vnext_production_proof.frozen_team_state_artifact_generator',
        lambda *_args, **_kwargs: object(),
    )
    with pytest.raises(
        recovery.LeagueTeamStateArtifactRecoveryError,
        match='generation_incomplete',
    ):
        recovery.repair_current_snapshot_artifacts(_snapshot())


@pytest.mark.parametrize('mutation', ['missing', 'duplicate', 'wrong_sync', 'noncanonical'])
def test_exact_artifact_identity_fails_closed(
    monkeypatch, governed_projection, mutation,
):
    artifacts = _artifacts()
    if mutation == 'missing':
        artifacts.pop()
    elif mutation == 'duplicate':
        artifacts.append(artifacts[0])
    elif mutation == 'wrong_sync':
        artifacts[0].source_sync_run_id += 1
    else:
        artifacts[-1].team_id = 484
    monkeypatch.setattr(
        recovery, 'list_team_state_artifacts_for_snapshot',
        lambda *_args, **_kwargs: artifacts,
    )
    with pytest.raises(recovery.LeagueTeamStateArtifactRecoveryError):
        recovery.require_complete_artifact_set(_snapshot())


def test_artifact_must_match_frozen_receipt(monkeypatch, governed_projection):
    monkeypatch.setattr(
        recovery, 'list_team_state_artifacts_for_snapshot',
        lambda *_args, **_kwargs: _artifacts(),
    )
    monkeypatch.setattr(
        recovery,
        'project_published_team_state_artifact',
        lambda *_args, **_kwargs: {
            'available': True,
            'public_state': 'stretched',
            'public_label': 'Stretched',
            'data_through': PRODUCT_DATE.isoformat(),
        },
    )
    with pytest.raises(
        recovery.LeagueTeamStateArtifactRecoveryError,
        match='receipt_mismatch',
    ):
        recovery.require_complete_artifact_set(_snapshot())


def test_frozen_receipts_generate_persisted_artifacts_without_mutable_recalculation(
    app, monkeypatch,
):
    """Production-shaped seam: receipt/input -> immutable artifact -> reuse."""
    from datetime import datetime

    from models.dashboard_snapshot import DashboardSnapshot
    from models.pitcher import Pitcher
    from models.share_artifact import ShareArtifact
    from models.sync_run import SyncRun
    from models.team_state_publication_proof import TeamStatePublicationProof
    from services import share_artifact_batch_generation as batch_service
    from services import team_state_source
    from services.share_artifact_publication_hook import run_post_publication_generation
    from services.team_board_snapshot_team_state import make_receipt
    from services.team_state_vnext_production_proof import (
        EXPECTED_METHOD_VERSION,
        frozen_team_state_artifact_generator,
    )
    from tests.test_share_artifact_batch_generation import _readiness

    team_ids = tuple(MLB_TEAM_IDS[:3])
    run = SyncRun(job_name='league-artifact-recovery')
    db.session.add(run)
    db.session.flush()
    snapshot = DashboardSnapshot(
        snapshot_type='bullpen_dashboard', sync_run_id=run.id,
        status='ready', is_published=True, published_at=datetime(2026, 9, 23, 12),
        payload={}, payload_version=1, data_through=PRODUCT_DATE,
        snapshot_generated_at=datetime(2026, 9, 23, 11, 59), source='test',
    )
    db.session.add(snapshot)
    db.session.flush()
    for index, team_id in enumerate(team_ids):
        db.session.add(Pitcher(
            mlb_id=990000 + index, full_name=f'Arm {team_id}',
            team_id=team_id, active=True,
        ))

    receipts = {}
    inputs = {}
    for team_id in team_ids:
        readiness = _readiness(team_id)
        readiness['freshness']['data_through'] = PRODUCT_DATE.isoformat()
        receipts[str(team_id)] = make_receipt(
            snapshot, team_id, readiness, method_version=EXPECTED_METHOD_VERSION,
        )
        inputs[str(team_id)] = {
            'readiness': readiness,
            'reference_dates': {},
            'arm_reads': {},
        }
    snapshot.payload = {
        'trusted_team_boards': {
            'contract': 'trusted_team_board_publication_v1',
            'data_through': PRODUCT_DATE.isoformat(),
            'by_team_id': {},
            'frozen_team_state_by_team_id': receipts,
        },
    }
    db.session.add(TeamStatePublicationProof(
        snapshot_id=snapshot.id, sync_run_id=run.id, data_through=PRODUCT_DATE,
        proof={'snapshot_team_state_generation_inputs': inputs},
        overall_verdict='PASS', captured_team_count=len(team_ids),
        method_version=EXPECTED_METHOD_VERSION,
    ))
    db.session.commit()

    monkeypatch.setattr(batch_service, '_canonical_team_ids', lambda session=None: team_ids)
    monkeypatch.setattr(
        team_state_source, 'get_latest_dashboard_snapshot', lambda *a, **k: snapshot,
    )
    monkeypatch.setattr(
        team_state_source, 'snapshot_unavailable_reason', lambda *_a, **_k: None,
    )
    monkeypatch.setattr(
        'services.share_artifact_generation.resolve_team_readiness_payload',
        lambda *_a, **_k: pytest.fail('mutable Team State recalculation is forbidden'),
    )

    first = run_post_publication_generation(
        snapshot, generator=frozen_team_state_artifact_generator(snapshot),
    )
    second = run_post_publication_generation(
        snapshot, generator=frozen_team_state_artifact_generator(snapshot),
    )

    assert first.generated_count == len(team_ids)
    assert first.failed_count == first.refused_count == first.missing_count == 0
    assert second.reused_count == len(team_ids)
    artifacts = ShareArtifact.query.filter_by(
        artifact_type='team_state', source_snapshot_id=snapshot.id,
        lifecycle_state='published',
    ).all()
    assert {item.team_id for item in artifacts} == set(team_ids)
    assert all(item.source_sync_run_id == run.id for item in artifacts)
