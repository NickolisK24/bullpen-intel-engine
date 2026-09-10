"""SC-04B v1.2 semantic/trust correctness fixes.

Four production-flagged defects on public Team State artifacts:
  1. scope label was hardcoded "Published BaseballOS Snapshot" for every artifact;
  2. a transient "sync currently running" limitation was frozen into immutable artifacts;
  3. confidence=High coexisted with an "N active bullpen records are missing current
     data" evidence sentence (two different populations);
  4. the LEAGUE readiness read used the advanced global reference date (slate+1) while
     roster snapshots are dated at the slate, refusing all 30 teams — the same
     slate/reference-date mismatch already fixed for the progressive read.
"""

from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from flask import Flask

import models.prospect  # noqa: F401
import api.team_operations as team_ops
import services.share_artifact_generation as gen
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.share_artifact import ShareArtifact
from models.sync_run import SyncRun
from services.share_artifact_public import _public_view, _publication_scope
from services.sync_metadata import SYNC_RUNNING_LIMITATION_TEXT
from services.team_state_payload import _durable_limitations
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
from utils.time import utc_now_naive


# ---------------------------------------------------------------------------
# Defect 1 — scope label from the durable discriminator (no DB needed)
# ---------------------------------------------------------------------------


def _artifact(subject_type, *, source_snapshot_id=7, payload=None):
    return SimpleNamespace(
        public_id='pub', artifact_type='team_state', schema_version='1.0.0',
        render_version='team-state-1.1.0', subject_type=subject_type, team_id=108,
        source_snapshot_id=source_snapshot_id, lifecycle_state='published',
        product_date=date(2026, 7, 24), created_at=None, published_at=None,
        superseded_at=None, withdrawn_at=None,
        payload=payload if payload is not None else {'team': {}, 'team_state': {}, 'trust': {}},
    )


def test_scope_label_is_team_progressive_for_progressive_artifact():
    scope = _publication_scope(_artifact('team_progressive'))
    assert scope['publication_scope'] == 'team_progressive'
    assert scope['display_label'] == 'Published Team Bullpen State'
    assert 'completed game' in scope['historical_note']


def test_scope_label_is_league_for_null_subject_type():
    scope = _publication_scope(_artifact(None))
    assert scope['publication_scope'] == 'league_snapshot'
    assert scope['display_label'] == 'Published BaseballOS Snapshot'
    assert 'synchronized BaseballOS league snapshot' in scope['historical_note']


def test_numeric_source_id_collision_cannot_alter_scope():
    # Same numeric source_snapshot_id, different durable subject_type -> different scope.
    progressive = _publication_scope(_artifact('team_progressive', source_snapshot_id=5))
    league = _publication_scope(_artifact(None, source_snapshot_id=5))
    assert progressive['display_label'] != league['display_label']


def test_public_view_projects_scope_aware_label():
    view = _public_view(_artifact('team_progressive'), None)
    assert view['publication_scope']['display_label'] == 'Published Team Bullpen State'
    view_league = _public_view(_artifact(None), None)
    assert view_league['publication_scope']['display_label'] == 'Published BaseballOS Snapshot'


# ---------------------------------------------------------------------------
# Defect 2 — transient runtime limitation never frozen into an artifact
# ---------------------------------------------------------------------------


def test_durable_limitations_drops_transient_sync_running():
    durable = 'Based on the current active bullpen and its completed recent appearances.'
    result = _durable_limitations([SYNC_RUNNING_LIMITATION_TEXT, durable])
    assert SYNC_RUNNING_LIMITATION_TEXT not in result
    assert durable in result


def test_durable_limitations_keeps_all_durable():
    durable = ['Bounded partial active-bullpen coverage.', 'Stale source restriction.']
    assert _durable_limitations(durable) == durable


def test_durable_limitations_handles_none():
    assert _durable_limitations(None) == []


# ---------------------------------------------------------------------------
# Defect 3 — trust/evidence contradiction: coverage receipt gated on trust
# ---------------------------------------------------------------------------


def _public_evidence_ids(confidence, *, count=3):
    from services.team_state_public_copy import build_public_copy
    coverage_constraint = {
        'constraint_id': 'coverage_partial', 'category': 'coverage',
        'affected_area': 'coverage_inventory', 'count': count, 'severity': 'caution',
    }
    copy = build_public_copy(
        team_name='Test Club', team_abbreviation='TST', status_code='operationally_stable',
        confidence=confidence, constraints=[coverage_constraint], limitations=(),
        active_bullpen_coverage=None, product_date=date(2026, 7, 24),
    )
    return {item.get('evidence_id') for item in copy.get('evidence', [])}, copy


def test_high_confidence_suppresses_coverage_receipt_in_public_copy():
    # High trust already means the canonical active bullpen is fully covered, so the
    # coarse coverage_inventory count must NOT surface as a public "missing current
    # data" receipt beside the verified trust line.
    ids, copy = _public_evidence_ids('high')
    assert 'coverage_partial' not in ids
    assert all('missing current data' not in (item.get('detail') or '')
               for item in copy.get('evidence', []))


def test_medium_confidence_suppresses_coverage_receipt_in_public_copy():
    ids, _ = _public_evidence_ids('medium')
    assert 'coverage_partial' not in ids


def test_low_confidence_keeps_coverage_receipt_in_public_copy():
    # A low team (SC-02 refuses it anyway) keeps the coarse coverage caveat.
    ids, _ = _public_evidence_ids('low')
    assert 'coverage_partial' in ids


# ---------------------------------------------------------------------------
# Defect 4 — league read anchors to the snapshot slate (30-team refusal fix)
# ---------------------------------------------------------------------------


TODAY = date.today()
SLATE = TODAY - timedelta(days=1)
LEAGUE_TEAM = 108


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


def _seed_team_with_slate_roster():
    for s in range(8):
        p = Pitcher(mlb_id=770000 + s, full_name=f'A{s}', team_id=LEAGUE_TEAM, team_name='C',
                    team_abbreviation='T108', throws='R', active=True, roster_status='ACTIVE',
                    roster_status_source='mlb_stats_api:roster_sync:active')
        db.session.add(p); db.session.flush()
        for off in (2, 4):
            gd = TODAY - timedelta(days=off)
            db.session.add(GameLog(pitcher_id=p.id, mlb_game_pk=770000 * 10 + s * 10 + off,
                                   game_date=gd, pitches_thrown=12, innings_pitched=1.0,
                                   innings_pitched_outs=3))
        db.session.add(FatigueScore(pitcher_id=p.id, calculated_at=datetime(2026, 6, 3, 12, 0, s),
            raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0, appearances_score=0.0,
            innings_score=0.0, leverage_score=0.0, days_since_last_appearance=2, appearances_last_7=2,
            appearances_last_14=2, pitches_last_7_days=24, innings_last_7_days=2.0,
            avg_leverage_last_7=None, risk_level='LOW'))
    db.session.commit()
    ts = utc_now_naive()
    run = SyncRun(job_name='r', started_at=ts, completed_at=ts, status='success',
                  stage='roster_status', source='r', created_at=ts)
    db.session.add(run); db.session.flush()
    for p in Pitcher.query.filter(Pitcher.active.is_(True)).all():
        db.session.add(RosterStatusSnapshot(pitcher_id=p.id, mlb_id=p.mlb_id, team_id=p.team_id,
            snapshot_date=SLATE, roster_status='ACTIVE', active_roster=True, forty_man_roster=True,
            source='mlb_stats_api:roster_sync:active', sync_run_id=run.id,
            first_seen_at=ts, updated_at=ts))
    db.session.commit()


def test_league_read_anchors_to_trusted_snapshot_slate(app, monkeypatch):
    # A trusted LEAGUE serving snapshot (data_through = slate) must anchor the roster
    # authority to the slate, not the advanced global reference date, so the team
    # resolves instead of refusing authority-missing (the 30-team refusal fix).
    _seed_team_with_slate_roster()
    # Global availability reference date advanced to slate+1 (post-slate).
    monkeypatch.setattr(team_ops, '_availability_reference_date',
                        lambda sync_status: SLATE + timedelta(days=1))
    # A trusted, current league snapshot whose data_through is the slate.
    league_snapshot = SimpleNamespace(
        id=275, data_through=SLATE, sync_run_id=99, published_at=utc_now_naive(),
        subject_type=None,
    )
    import services.readiness_snapshot_freshness as freshness_mod
    monkeypatch.setattr(freshness_mod, 'serving_snapshot_freshness_authority',
                        lambda snap, **kw: {'data_through': SLATE,
                                            'availability_reference_date': SLATE + timedelta(days=1),
                                            'reference_date': SLATE, 'active_window_days': 14,
                                            'reason_code': 'x', 'source_scope': 'league_snapshot'})
    readiness = gen.resolve_team_readiness_payload(LEAGUE_TEAM, source_snapshot=league_snapshot)
    # The roster authority resolved for the slate -> a real readiness payload (not None,
    # not authority-missing).
    assert readiness is not None
    trust = readiness.get('trust_metadata') or {}
    assert trust.get('data_state') != 'missing'
    assert trust.get('confidence') != 'unknown'
