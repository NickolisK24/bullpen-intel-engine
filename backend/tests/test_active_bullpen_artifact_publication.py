"""Real-resolver immutable Share Artifact publication proof (SC-03B-07 completion).

These drive the FULL production generation flow with NO injected readiness resolver
and NO mocked eligibility/payload/generation: persisted production-shaped data ->
canonical active-roster + Role authorities -> fatigue/game-log/appearance-ledger ->
resolve_team_readiness_payload -> assemble_bullpen_readiness -> TeamStateSource ->
SC-02 eligibility -> canonical payload builder -> SC-03A generate_team_state_artifact
-> immutable publication -> integrity -> idempotent reuse -> compatibility projection.

Only the trusted-snapshot AUTHORITY is monkeypatched (external daily-publication
infrastructure that cannot be reasonably published in a unit test); every readiness,
eligibility, payload, generation, repository, audit, and integrity contract is real.
"""

from datetime import date, datetime, timedelta

import pytest
from flask import Flask

from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.share_artifact import ShareArtifact
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from models.sync_run import SyncRun
from services import team_state_source as source_module
from services.share_artifact_batch_generation import (
    BATCH_OUTCOME_GENERATED,
    BATCH_OUTCOME_REFUSED,
    BATCH_OUTCOME_REUSED,
    generate_team_state_artifacts_batch,
)
from services.share_artifact_generation import (
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
    generate_team_state_artifact,
)
from services.share_card_compatibility import (
    COMPATIBILITY_SOURCE,
    build_share_card_compatibility_view,
)
from services.share_artifacts import verify_share_artifact_integrity
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE, TEAM_STATE_V1_1
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db


SNAPSHOT_ID = 6001
PRODUCT_DATE = date.today()
SUPPORTED = {'operationally_stable', 'operationally_constrained', 'operationally_stressed'}


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


def _install_trusted_snapshot(monkeypatch, *, sync_run_id=None):
    class _Snap:
        pass
    snap = _Snap()
    snap.id = SNAPSHOT_ID
    snap.sync_run_id = sync_run_id
    snap.data_through = PRODUCT_DATE
    snap.published_at = datetime(2026, 7, 24, 13, 0, 0)
    monkeypatch.setattr(source_module, 'get_latest_dashboard_snapshot', lambda *a, **k: snap)
    monkeypatch.setattr(source_module, 'snapshot_unavailable_reason', lambda s, *a, **k: None)
    return snap


def _add_reliever(team_id, seed, *, usable=True, hand='R', roster_status='ACTIVE', starter=False):
    pitcher = Pitcher(
        mlb_id=970000 + seed, full_name=f'Arm {seed:03d}', team_id=team_id,
        team_name=f'Club {team_id}', team_abbreviation=f'C{team_id}', throws=hand,
        active=True, roster_status=roster_status,
        roster_status_source='mlb_stats_api:roster_sync:active',
    )
    db.session.add(pitcher)
    db.session.flush()

    def _game(offset, gpk, *, pitches=12, outs=3, ip=1.0, starts=0):
        gd = date.today() - timedelta(days=offset)
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd, pitches_thrown=pitches,
            innings_pitched=ip, innings_pitched_outs=outs, games_started=starts,
        ))
        db.session.add_all([
            ScheduledGame(team_id=team_id, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='home', opponent_team_id=800000 + team_id),
            ScheduledGame(team_id=800000 + team_id, game_pk=gpk, game_date=gd, status_state='final',
                          home_away='away', opponent_team_id=team_id),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=gpk, game_date=gd,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))

    base = team_id * 1000 + seed * 10
    if starter:
        # Long, started outings -> Role Authority classifies a Starter (excluded).
        _game(2, base + 2, pitches=95, outs=18, ip=6.0, starts=1)
        _game(7, base + 7, pitches=90, outs=18, ip=6.0, starts=1)
    else:
        _game(2, base + 2)
        _game(4, base + 4)
        if not usable:
            # Latest appearance carries incomplete source data (null pitch count) ->
            # data_state 'incomplete' -> unresolved, still a classified bullpen arm.
            gd = date.today() - timedelta(days=1)
            gpk = base + 1
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd,
                pitches_thrown=None, innings_pitched=1.0, innings_pitched_outs=3, games_started=0,
            ))
            db.session.add_all([
                ScheduledGame(team_id=team_id, game_pk=gpk, game_date=gd, status_state='final',
                              home_away='home', opponent_team_id=800000 + team_id),
                ScheduledGame(team_id=800000 + team_id, game_pk=gpk, game_date=gd, status_state='final',
                              home_away='away', opponent_team_id=team_id),
            ])
            db.session.add(PostgameProcessedGame(
                mlb_game_pk=gpk, game_date=gd,
                processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            ))

    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=datetime(2026, 6, 3, 12, 0, seed % 60),
        raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0, appearances_score=0.0,
        innings_score=0.0, leverage_score=0.0, days_since_last_appearance=1,
        appearances_last_7=2, appearances_last_14=2, pitches_last_7_days=24,
        innings_last_7_days=2.0, avg_leverage_last_7=None, risk_level='LOW',
    ))
    db.session.flush()
    return pitcher


def _sync_run():
    db.session.add(SyncRun(
        started_at=datetime(2026, 6, 3, 7, 30, 0), completed_at=datetime(2026, 6, 3, 7, 44, 27),
        status='success', source='scheduled', latest_game_date=date.today(),
        latest_workload_date=date.today(), latest_fatigue_calculated_at=datetime(2026, 6, 3, 7, 44, 27),
        records_processed=12, new_logs_added=6, pitchers_updated=2, errors=0,
        created_at=datetime(2026, 6, 3, 7, 30, 0),
    ))
    db.session.commit()


_SEED = [1000]


def _seed_team(team_id, *, usable, total, extra_inactive=True):
    start = _SEED[0]
    _SEED[0] += total + 5
    for i in range(total):
        _add_reliever(team_id, start + i, usable=(i < usable), hand='L' if i % 2 else 'R')
    if extra_inactive:
        # An inactive/IL/optioned reliever and a confirmed starter on the same team —
        # neither may collapse or count toward the active-bullpen read.
        _add_reliever(team_id, start + total + 1, usable=False, roster_status='IL_15')
        _add_reliever(team_id, start + total + 2, usable=True, starter=True)


def _publish(team_id):
    return generate_team_state_artifact(team_id)


# ============================ FIXTURE A — HIGH =================================


def test_fixture_a_high_confidence_publishes_verifies_reuses_projects(app, monkeypatch):
    _install_trusted_snapshot(monkeypatch)
    _seed_team(31, usable=8, total=8)
    _sync_run()
    seed_roster_readiness_snapshots()

    result = _publish(31)
    assert result.outcome == OUTCOME_PUBLISHED
    assert result.eligible is True and result.created_new is True
    artifact = result.artifact
    assert artifact is not None and artifact.public_id
    assert artifact.lifecycle_state == 'published'
    assert artifact.team_id == 31
    assert artifact.source_snapshot_id == SNAPSHOT_ID
    assert artifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    assert artifact.render_version == TEAM_STATE_V1_1
    doc = artifact.payload
    assert doc['team_state']['status_code'] in SUPPORTED
    assert doc['trust']['confidence'] == 'high'
    assert doc['trust']['data_state'] == 'fresh'
    assert doc['authority']['data_through'] == PRODUCT_DATE.isoformat()
    assert verify_share_artifact_integrity(artifact) is True

    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_PUBLISHED and audit.eligible is True

    # Idempotent reuse.
    rerun = _publish(31)
    assert rerun.outcome == OUTCOME_REUSED and rerun.reused_existing is True
    assert rerun.public_id == result.public_id
    assert db.session.query(ShareArtifact).filter_by(lifecycle_state='published').count() == 1

    # Compatibility projection consumes the immutable artifact (no recompute).
    view = build_share_card_compatibility_view(artifact)
    assert view['source'] == COMPATIBILITY_SOURCE
    assert view['public_id'] == artifact.public_id
    assert view['team']['team_id'] == 31
    assert view['status_code'] in SUPPORTED
    assert view['trust']['confidence'] == 'high'


# =========================== FIXTURE B — MEDIUM ===============================


def test_fixture_b_medium_confidence_publishes_with_limitation(app, monkeypatch):
    _install_trusted_snapshot(monkeypatch)
    _seed_team(32, usable=6, total=8)
    _sync_run()
    seed_roster_readiness_snapshots()

    result = _publish(32)
    assert result.outcome == OUTCOME_PUBLISHED
    artifact = result.artifact
    doc = artifact.payload
    assert doc['team_state']['status_code'] in SUPPORTED
    assert doc['trust']['confidence'] == 'medium'
    assert doc['trust']['data_state'] == 'fresh'

    # The bounded-partial-coverage limitation must survive publication (it is what
    # keeps a medium read honest). Preserved on the immutable document.
    limitations = doc['trust'].get('limitations') or []
    assert any('active bullpen pitchers' in str(item) for item in limitations)

    assert verify_share_artifact_integrity(artifact) is True
    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_PUBLISHED

    rerun = _publish(32)
    assert rerun.outcome == OUTCOME_REUSED and rerun.public_id == result.public_id
    assert db.session.query(ShareArtifact).filter_by(lifecycle_state='published').count() == 1

    view = build_share_card_compatibility_view(artifact)
    # Compatibility must not convert medium to high.
    assert view['trust']['confidence'] == 'medium'


# ============================ FIXTURE C — LOW =================================


def test_fixture_c_low_confidence_is_refused(app, monkeypatch):
    _install_trusted_snapshot(monkeypatch)
    _seed_team(33, usable=5, total=8)
    _sync_run()
    seed_roster_readiness_snapshots()

    result = _publish(33)
    assert result.outcome == OUTCOME_REFUSED
    assert result.eligible is False and result.public_id is None
    assert db.session.query(ShareArtifact).count() == 0

    assert set(result.blocking_conditions) >= {
        'incomplete_evidence', 'insufficient_trust', 'unsupported_team_state',
    }
    assert 'data_state:incomplete' in result.reasons
    assert 'confidence:low' in result.reasons
    assert 'status_code_unsupported:data_limited' in result.reasons

    audit = db.session.get(ShareArtifactGenerationAudit, result.audit_id)
    assert audit.outcome == OUTCOME_REFUSED
    assert audit.share_artifact_id is None


# ====================== FIXTURE D — MIXED REAL BATCH ==========================


def test_fixture_d_mixed_real_resolver_batch(app, monkeypatch):
    _install_trusted_snapshot(monkeypatch)
    _seed_team(41, usable=8, total=8)   # high
    _seed_team(42, usable=6, total=8)   # medium
    _seed_team(43, usable=5, total=8)   # low
    _sync_run()
    seed_roster_readiness_snapshots()

    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, team_ids=[41, 42, 43],
    )
    by_team = {r.team_id: r.outcome for r in result.results}
    assert by_team == {
        41: BATCH_OUTCOME_GENERATED, 42: BATCH_OUTCOME_GENERATED, 43: BATCH_OUTCOME_REFUSED,
    }
    # Accounting invariant + missing.
    assert result.attempted_count == (
        result.generated_count + result.reused_count + result.refused_count + result.failed_count
    )
    assert result.generated_count == 2 and result.refused_count == 1 and result.failed_count == 0
    assert result.missing_count == 0
    assert db.session.query(ShareArtifact).filter_by(lifecycle_state='published').count() == 2

    # Idempotent rerun: generated -> reused, refused stays refused, no duplicates.
    rerun = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, team_ids=[41, 42, 43],
    )
    rerun_by_team = {r.team_id: r.outcome for r in rerun.results}
    assert rerun_by_team == {
        41: BATCH_OUTCOME_REUSED, 42: BATCH_OUTCOME_REUSED, 43: BATCH_OUTCOME_REFUSED,
    }
    assert db.session.query(ShareArtifact).filter_by(lifecycle_state='published').count() == 2


# ===================== ROLE AUTHORITY / SCOPE VERIFICATION ====================


def test_role_authority_scopes_active_bullpen(app, monkeypatch):
    """active+Reliever included; active+Starter excluded; inactive+Reliever excluded;
    unknown roster fails closed. A complete active bullpen alongside inactive and
    starter records still resolves high (they do not collapse the read)."""
    _install_trusted_snapshot(monkeypatch)
    # 8 usable active relievers + 1 IL reliever + 1 active starter on the same team.
    _seed_team(51, usable=8, total=8, extra_inactive=True)
    _sync_run()
    seed_roster_readiness_snapshots()

    result = _publish(51)
    assert result.outcome == OUTCOME_PUBLISHED
    # High: the IL reliever and the starter neither counted toward nor collapsed the
    # active-bullpen coverage (else confidence would not be high with 8/8 usable arms).
    assert result.artifact.payload['trust']['confidence'] == 'high'


def test_unknown_roster_assignment_fails_closed(app, monkeypatch):
    """A team whose relievers have no authoritative active-roster status (no roster
    snapshots seeded) resolves to unknown -> data_limited -> refused, never eligible."""
    _install_trusted_snapshot(monkeypatch)
    _seed_team(52, usable=8, total=8, extra_inactive=False)
    _sync_run()
    # Intentionally do NOT seed roster readiness snapshots -> no active-bullpen authority.

    result = _publish(52)
    assert result.outcome == OUTCOME_REFUSED
    assert result.eligible is False
    assert 'unsupported_team_state' in result.blocking_conditions
