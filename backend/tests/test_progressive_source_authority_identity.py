"""Durable source-authority identity for progressive Team State publication.

The trusted SOURCE that authorized a Team State artifact must be identifiable
durably from the artifact itself — never inferred from the bare numeric
``source_snapshot_id`` (a league dashboard-snapshot id and a team-progressive
checkpoint id share one integer space and can collide). These tests prove:

* a progressive artifact carries the durable ``subject_type`` discriminator, which
  is part of the equivalence + integrity contract (tampering with it fails closed);
* a numeric id collision between a league snapshot and a team checkpoint keeps the
  two artifacts distinct and lets the league-scoped operations reads fail closed
  against the colliding progressive artifact/audit;
* the evidence-revision fingerprint is row-order independent and correction
  sensitive, so a genuine box-score correction mints a NEW immutable checkpoint and
  artifact while the prior one is never rewritten;
* doubleheader games and out-of-order publications resolve the chronologically
  latest artifact; the checkpoint unique constraint blocks duplicates; and one
  team's failure never blocks its opponent.

The real readiness/eligibility/generation path is exercised (SC-02 is never mocked)
except where a fault is deliberately injected to prove failure isolation.
"""

from datetime import date, datetime, timedelta

import pytest
import sqlalchemy as sa
from flask import Flask

import models.prospect  # noqa: F401
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.share_artifact import (
    SOURCE_AUTHORITY_LEAGUE_SNAPSHOT,
    SOURCE_AUTHORITY_TEAM_PROGRESSIVE,
    SUBJECT_TYPE_TEAM_PROGRESSIVE,
    ShareArtifact,
    source_authority_type,
)
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from models.team_progressive_publication import TeamProgressivePublication
from services.share_artifact_integrity import (
    ShareArtifactIntegrityError,
    compute_equivalence_key,
)
from services.share_artifact_repository import (
    audits_for_snapshot,
    get_latest_published_team_state_artifact,
    list_team_state_artifacts_for_snapshot,
)
from services.share_artifacts import verify_share_artifact_integrity
from utils.time import utc_now_naive
from services.team_progressive_publication import (
    PROGRESSIVE_REQUEST_SOURCE,
    _canonical_ledger_digest,
    build_team_progressive_checkpoint,
    publish_team_state_for_final_game,
)
import services.team_progressive_publication as progressive
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db


TODAY = date.today()
GAME_DATE = TODAY - timedelta(days=1)

HOME = 108
AWAY = 117

FINAL_GAME_PK = 781001
FINAL_GAME_PK_2 = 781002  # same-day second game (doubleheader)


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


def _add_relievers(team_id, base_mlb, count=8):
    for seed in range(count):
        pitcher = Pitcher(
            mlb_id=base_mlb + seed, full_name=f'Arm {team_id}-{seed}', team_id=team_id,
            team_name=f'Club {team_id}', team_abbreviation=f'T{team_id}',
            throws='L' if seed % 2 else 'R', active=True, roster_status='ACTIVE',
            roster_status_source='mlb_stats_api:roster_sync:active',
        )
        db.session.add(pitcher)
        db.session.flush()
        for offset in (2, 4):
            gd = TODAY - timedelta(days=offset)
            gpk = base_mlb * 10 + seed * 10 + offset
            db.session.add(GameLog(
                pitcher_id=pitcher.id, mlb_game_pk=gpk, game_date=gd,
                pitches_thrown=12, innings_pitched=1.0, innings_pitched_outs=3,
            ))
            db.session.add_all([
                ScheduledGame(team_id=team_id, game_pk=gpk, game_date=gd, status_state='final',
                              home_away='home', opponent_team_id=900000 + team_id),
                ScheduledGame(team_id=900000 + team_id, game_pk=gpk, game_date=gd, status_state='final',
                              home_away='away', opponent_team_id=team_id),
            ])
            db.session.add(PostgameProcessedGame(
                mlb_game_pk=gpk, game_date=gd,
                processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id, calculated_at=datetime(2026, 6, 3, 12, 0, seed),
            raw_score=20.0, pitch_count_score=0.0, rest_days_score=0.0,
            appearances_score=0.0, innings_score=0.0, leverage_score=0.0,
            days_since_last_appearance=2, appearances_last_7=2, appearances_last_14=2,
            pitches_last_7_days=24, innings_last_7_days=2.0, avg_leverage_last_7=None,
            risk_level='LOW',
        ))
    db.session.flush()


def _add_final_game(game_pk, home, away, game_date, *, ledger=True):
    db.session.add_all([
        ScheduledGame(team_id=home, game_pk=game_pk, game_date=game_date, status_state='final',
                      home_away='home', opponent_team_id=away),
        ScheduledGame(team_id=away, game_pk=game_pk, game_date=game_date, status_state='final',
                      home_away='away', opponent_team_id=home),
    ])
    # A committed appearance line for the game so the ledger digest has content and a
    # correction has something to change.
    home_pitcher = (
        db.session.query(Pitcher).filter(Pitcher.team_id == home).order_by(Pitcher.id.asc()).first()
    )
    db.session.add(GameLog(
        pitcher_id=home_pitcher.id, mlb_game_pk=game_pk, game_date=game_date,
        pitches_thrown=15, innings_pitched=1.0, innings_pitched_outs=3,
    ))
    if ledger:
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk, game_date=game_date,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
    db.session.flush()


def _seed_two_teams():
    for tid, base in ((HOME, 810000), (AWAY, 820000)):
        _add_relievers(tid, base)
    _add_final_game(FINAL_GAME_PK, HOME, AWAY, GAME_DATE)
    db.session.commit()
    seed_roster_readiness_snapshots()


def _insert_league_artifact(*, public_id, source_snapshot_id, product_date, marker):
    """Insert a synthetic PUBLISHED league artifact (subject_type NULL) via a Core
    insert.

    A league artifact is normally minted by the generation path; here we only need a
    published row with a specific ``source_snapshot_id`` and NULL ``subject_type`` to
    exercise the durable-discriminator query filters and chronology ordering. A Core
    insert avoids the ORM unit-of-work re-touching already-published immutable rows
    (a raw double-publish quirk unrelated to this feature).
    """
    now = utc_now_naive()
    db.session.execute(
        sa.insert(ShareArtifact.__table__).values(
            public_id=public_id, artifact_type='team_state',
            render_version='team-state-1.1.0', team_id=HOME,
            source_snapshot_id=source_snapshot_id, subject_type=None, subject_key=None,
            lifecycle_state='published', payload={'league': marker}, trust_metadata={},
            equivalence_key=f'league-eqkey-{public_id}', integrity_hash='0' * 64,
            source='test', schema_version='1.0.0', product_date=product_date,
            created_at=now, updated_at=now, published_at=now,
        )
    )
    db.session.commit()
    return db.session.query(ShareArtifact).filter_by(public_id=public_id).one()


def _published_progressive_artifacts(game_pk=FINAL_GAME_PK):
    checkpoints = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.trigger_game_pk == game_pk,
        TeamProgressivePublication.trusted.is_(True),
    ).all()
    ids = {c.id for c in checkpoints}
    return db.session.query(ShareArtifact).filter(
        ShareArtifact.source_snapshot_id.in_(ids),
        ShareArtifact.subject_type == SUBJECT_TYPE_TEAM_PROGRESSIVE,
    ).all()


# ---------------------------------------------------------------------------
# Durable discriminator on the artifact
# ---------------------------------------------------------------------------


def test_artifact_carries_durable_source_authority_discriminator(app):
    _seed_two_teams()
    result = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    assert result.generated + result.reused >= 1
    artifacts = _published_progressive_artifacts()
    assert artifacts
    for artifact in artifacts:
        # Durable, immutable discriminator stamped on the artifact identity.
        assert artifact.subject_type == SUBJECT_TYPE_TEAM_PROGRESSIVE
        assert artifact.subject_key.startswith(f'{SUBJECT_TYPE_TEAM_PROGRESSIVE}:')
        # Source TYPE is resolved from the durable field, not the numeric id.
        assert source_authority_type(artifact) == SOURCE_AUTHORITY_TEAM_PROGRESSIVE


def test_subject_type_changes_equivalence_key(app):
    # The discriminator is part of the equivalence document: identical substance with
    # a different subject_type is a DIFFERENT identity, so a league artifact and a
    # progressive artifact can never dedup-collide.
    common = dict(
        artifact_type='team_state', render_version='team-state-1.1.0', team_id=HOME,
        source_snapshot_id=7, subject_key=None, product_date=GAME_DATE,
        payload={'k': 'v'}, evidence_entries=(), trust_metadata={}, schema_version='1.0.0',
    )
    league_key = compute_equivalence_key(subject_type=None, **common)
    progressive_key = compute_equivalence_key(
        subject_type=SUBJECT_TYPE_TEAM_PROGRESSIVE, **common
    )
    assert league_key != progressive_key


def test_source_discriminator_is_bound_into_integrity_hash(app):
    _seed_two_teams()
    publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    artifact = _published_progressive_artifacts()[0]
    art_id = artifact.id
    # Sanity: it verifies before tampering.
    assert verify_share_artifact_integrity(artifact) is True
    # Tamper the durable discriminator directly in the DB (bypassing the ORM guard).
    db.session.execute(
        sa.update(ShareArtifact).where(ShareArtifact.id == art_id).values(subject_type=None)
    )
    db.session.expire(artifact)
    with pytest.raises(ShareArtifactIntegrityError):
        verify_share_artifact_integrity(artifact)


# ---------------------------------------------------------------------------
# Numeric id collision — the core founder concern
# ---------------------------------------------------------------------------


def test_numeric_source_snapshot_id_collision_stays_distinct(app):
    _seed_two_teams()
    publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    progressive_artifact = _published_progressive_artifacts()[0]
    colliding_id = progressive_artifact.source_snapshot_id

    # A LEAGUE artifact whose source_snapshot_id is the SAME integer as the team
    # checkpoint id (the collision). It leaves subject_type NULL (league).
    league_artifact = _insert_league_artifact(
        public_id='league-collide', source_snapshot_id=colliding_id,
        product_date=GAME_DATE, marker='collide',
    )

    # Same integer, two different sources — distinct identities, distinct types.
    assert league_artifact.source_snapshot_id == progressive_artifact.source_snapshot_id
    assert league_artifact.public_id != progressive_artifact.public_id
    assert league_artifact.equivalence_key != progressive_artifact.equivalence_key
    assert source_authority_type(league_artifact) == SOURCE_AUTHORITY_LEAGUE_SNAPSHOT
    assert source_authority_type(progressive_artifact) == SOURCE_AUTHORITY_TEAM_PROGRESSIVE

    # The league-scoped coverage query fails closed against the colliding progressive
    # artifact: excluding the team-progressive scope returns ONLY the league one.
    league_only = list_team_state_artifacts_for_snapshot(
        colliding_id, exclude_subject_type=SUBJECT_TYPE_TEAM_PROGRESSIVE,
    )
    league_ids = {a.id for a in league_only}
    assert league_artifact.id in league_ids
    assert progressive_artifact.id not in league_ids

    # Without the discriminator filter, the bare id genuinely collides (both return),
    # proving the id alone is insufficient and the durable type is what saves it.
    both = list_team_state_artifacts_for_snapshot(colliding_id)
    both_ids = {a.id for a in both}
    assert {league_artifact.id, progressive_artifact.id}.issubset(both_ids)


def test_league_coverage_audits_exclude_colliding_progressive_attempt(app):
    _seed_two_teams()
    publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    # A progressive audit exists tied to the checkpoint id, recorded under the
    # progressive request source.
    progressive_audit = db.session.query(ShareArtifactGenerationAudit).filter(
        ShareArtifactGenerationAudit.request_source == PROGRESSIVE_REQUEST_SOURCE,
    ).first()
    assert progressive_audit is not None
    colliding_id = progressive_audit.source_snapshot_id

    # A league audit against the SAME snapshot id (collision), different request source.
    league_audit = ShareArtifactGenerationAudit(
        team_id=HOME, source_snapshot_id=colliding_id,
        outcome=ShareArtifactGenerationAudit.OUTCOME_PUBLISHED, eligible=True,
        request_source='batch',
    )
    db.session.add(league_audit)
    db.session.commit()

    league_scoped = audits_for_snapshot(
        colliding_id, exclude_request_source=PROGRESSIVE_REQUEST_SOURCE,
    )
    ids = {a.id for a in league_scoped}
    assert league_audit.id in ids
    assert progressive_audit.id not in ids


# ---------------------------------------------------------------------------
# Evidence-revision canonicalization + corrections
# ---------------------------------------------------------------------------


def test_evidence_digest_is_row_order_independent(app):
    rows_a = [(5, 12, 3, 0), (9, 20, 6, 0), (3, 8, 2, 1)]
    rows_b = list(reversed(rows_a))
    assert _canonical_ledger_digest(rows_a) == _canonical_ledger_digest(rows_b)
    # A genuine content change (a corrected pitch count) changes the digest even
    # though the row COUNT is unchanged.
    rows_corrected = [(5, 18, 3, 1), (9, 20, 6, 0), (3, 8, 2, 1)]
    assert _canonical_ledger_digest(rows_a) != _canonical_ledger_digest(rows_corrected)


def test_box_score_correction_mints_new_checkpoint_and_artifact(app):
    _seed_two_teams()
    first = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    assert first.generated + first.reused >= 1
    before_checkpoints = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.team_id == HOME,
        TeamProgressivePublication.trigger_game_pk == FINAL_GAME_PK,
    ).all()
    assert len(before_checkpoints) == 1
    original_revision = before_checkpoints[0].evidence_revision
    prior_artifacts = {a.public_id for a in _published_progressive_artifacts()}

    # An authoritative box-score correction: a changed pitch count + a bumped
    # stat-correction counter on the game's committed line.
    db.session.execute(
        sa.update(GameLog)
        .where(GameLog.mlb_game_pk == FINAL_GAME_PK)
        .values(pitches_thrown=99, stat_correction_count=1)
    )
    db.session.commit()

    publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')

    home_checkpoints = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.team_id == HOME,
        TeamProgressivePublication.trigger_game_pk == FINAL_GAME_PK,
    ).all()
    revisions = {c.evidence_revision for c in home_checkpoints}
    # The correction minted a NEW immutable checkpoint with a new evidence revision.
    assert len(home_checkpoints) == 2
    assert original_revision in revisions
    assert len(revisions) == 2

    # A new immutable artifact exists; the prior one is untouched (still present).
    all_artifacts = _published_progressive_artifacts()
    all_ids = {a.public_id for a in all_artifacts}
    assert prior_artifacts.issubset(all_ids)
    assert len(all_ids - prior_artifacts) >= 1


# ---------------------------------------------------------------------------
# Chronology: doubleheaders + out-of-order publication
# ---------------------------------------------------------------------------


def test_doubleheader_games_are_distinct_and_latest_is_the_later_game(app):
    _seed_two_teams()
    # A second, same-day game for the same two teams (doubleheader Game 2).
    _add_final_game(FINAL_GAME_PK_2, HOME, AWAY, GAME_DATE)
    db.session.commit()

    publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')  # Game 1
    publish_team_state_for_final_game(FINAL_GAME_PK_2, actor='postgame')  # Game 2 (later)

    g1 = _published_progressive_artifacts(FINAL_GAME_PK)
    g2 = _published_progressive_artifacts(FINAL_GAME_PK_2)
    assert g1 and g2
    # Distinct game_pk -> distinct checkpoints -> distinct artifacts.
    assert {a.public_id for a in g1}.isdisjoint({a.public_id for a in g2})

    # Latest read for HOME resolves the later-published same-day game (Game 2).
    latest = get_latest_published_team_state_artifact(HOME)
    assert latest is not None
    assert latest.public_id in {a.public_id for a in g2}


def test_latest_read_prefers_newer_product_date_over_publish_time(app):
    _seed_two_teams()
    older_day = GAME_DATE - timedelta(days=1)
    newer_day = GAME_DATE
    # Publish the NEWER product date FIRST, then the OLDER one (out of publish order):
    # the older row therefore has the later published_at timestamp.
    newer = _insert_league_artifact(
        public_id='chron-newer', source_snapshot_id=5001, product_date=newer_day,
        marker='new',
    )
    older = _insert_league_artifact(
        public_id='chron-older', source_snapshot_id=5002, product_date=older_day,
        marker='old',
    )
    assert older.published_at >= newer.published_at  # older-day row published later
    # Baseball chronology wins: the newer PRODUCT DATE is latest despite publishing
    # first. (verify=False — these synthetic rows carry a placeholder integrity hash;
    # the ordering, not integrity, is under test here.)
    latest = get_latest_published_team_state_artifact(HOME, verify=False)
    assert latest.public_id == newer.public_id


# ---------------------------------------------------------------------------
# Concurrency idempotency + failure isolation
# ---------------------------------------------------------------------------


def test_checkpoint_unique_constraint_blocks_duplicate(app):
    _seed_two_teams()
    checkpoint = build_team_progressive_checkpoint(HOME, FINAL_GAME_PK)
    db.session.commit()
    assert checkpoint is not None

    # A second row with the identical idempotency key must be rejected by the DB.
    duplicate = TeamProgressivePublication(
        team_id=checkpoint.team_id,
        trigger_type=TeamProgressivePublication.TRIGGER_GAME_FINAL,
        trigger_game_pk=checkpoint.trigger_game_pk,
        data_through=checkpoint.data_through,
        game_final=True, ledger_complete=True, evidence_complete=True, trusted=True,
        evidence_revision=checkpoint.evidence_revision,
        status=TeamProgressivePublication.STATUS_TRUSTED,
    )
    db.session.add(duplicate)
    with pytest.raises(sa.exc.IntegrityError):
        db.session.flush()
    db.session.rollback()


def test_build_checkpoint_is_idempotent_under_reentry(app):
    _seed_two_teams()
    first = build_team_progressive_checkpoint(HOME, FINAL_GAME_PK)
    db.session.commit()
    second = build_team_progressive_checkpoint(HOME, FINAL_GAME_PK)
    assert first.id == second.id
    count = db.session.query(TeamProgressivePublication).filter(
        TeamProgressivePublication.team_id == HOME,
        TeamProgressivePublication.trigger_game_pk == FINAL_GAME_PK,
    ).count()
    assert count == 1


def test_one_team_failure_does_not_block_opponent(app, monkeypatch):
    _seed_two_teams()
    real_generate = progressive.generate_team_state_artifact

    def flaky_generate(team_id, **kwargs):
        if team_id == HOME:
            raise RuntimeError('injected fault for HOME only')
        return real_generate(team_id, **kwargs)

    monkeypatch.setattr(progressive, 'generate_team_state_artifact', flaky_generate)

    result = publish_team_state_for_final_game(FINAL_GAME_PK, actor='postgame')
    # Both participants accounted; the failure is contained to HOME, AWAY still runs.
    assert result.attempted == 2
    assert result.accounted == 2
    assert result.to_dict()['missing'] == 0
    assert result.failed == 1
    assert result.team_outcomes[HOME] == progressive.OUTCOME_FAILED_CLOSED
    assert result.team_outcomes[AWAY] in (
        progressive.OUTCOME_PUBLISHED, progressive.OUTCOME_REUSED,
    )
    # AWAY's artifact was really published despite HOME's failure.
    away_artifacts = db.session.query(ShareArtifact).filter(
        ShareArtifact.team_id == AWAY,
        ShareArtifact.subject_type == SUBJECT_TYPE_TEAM_PROGRESSIVE,
    ).count()
    assert away_artifacts >= 1
