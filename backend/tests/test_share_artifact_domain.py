"""Domain tests for the immutable Share Artifact domain (Share Cards SC-01).

These tests validate the domain completely *before any rendering exists*:
canonical identity/authority fields, immutability, lifecycle, integrity-hash
stability, supersede, withdrawal, deduplication, and persistence. There is
deliberately no rendering, route, image, or Team State eligibility assertion
here — those belong to later SC phases.
"""

import importlib.util
import re
from datetime import date, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

import models.share_artifact  # noqa: F401  (registers ORM immutability listeners)
from models.share_artifact import (
    LIFECYCLE_DRAFT,
    LIFECYCLE_PUBLISHED,
    LIFECYCLE_SUPERSEDED,
    LIFECYCLE_WITHDRAWN,
    SHARE_ARTIFACT_SCHEMA_VERSION,
    ShareArtifact,
    ShareArtifactAsset,
    ShareArtifactEvidence,
    ShareArtifactImmutableError,
    ShareArtifactLifecycleError,
    ShareArtifactRelation,
)
from models.sync_run import SyncRun
from services.share_artifact_integrity import (
    ShareArtifactIntegrityError,
    canonical_json,
    compute_equivalence_key,
    compute_integrity_hash,
    to_json_safe,
)
from services.share_artifacts import (
    DEFAULT_RENDER_VERSION,
    ShareArtifactAssetInput,
    ShareArtifactBuildError,
    ShareArtifactEvidenceInput,
    _compute_integrity_hash_for,
    attach_share_artifact_asset,
    build_share_artifact_draft,
    find_published_equivalent,
    publish_new_share_artifact,
    publish_share_artifact,
    supersede_share_artifact,
    verify_share_artifact_integrity,
    withdraw_share_artifact,
)
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = REPO_ROOT / 'backend' / 'migrations' / 'versions'
SHARE_REVISION = 'c1a7f4e2b9d6'
PRIOR_REVISION = 'a1d8e4c6b2f0'


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


# ---------------------------------------------------------------------------
# Sample builders
# ---------------------------------------------------------------------------


def _sample_kwargs(**overrides):
    kwargs = dict(
        artifact_type='team_state_card',
        team_id=147,
        source_snapshot_id=5001,
        product_date=date(2026, 7, 20),
        payload={'headline': 'Bullpen rested', 'metrics': {'available': 5, 'gassed': 1}},
        evidence=[
            ShareArtifactEvidenceInput(
                evidence_key='ev:availability:NYY:2026-07-20',
                role='primary',
                claim='5 relievers available',
                completeness_state='complete',
                snapshot={'available': 5, 'gassed': 1},
            ),
        ],
        trust_metadata={'posture': 'public_candidate', 'completeness_state': 'complete'},
        source='share_cards:test',
    )
    kwargs.update(overrides)
    return kwargs


def _publish_sample(**overrides):
    return publish_new_share_artifact(**_sample_kwargs(**overrides))


def _build_draft(**overrides):
    return build_share_artifact_draft(**_sample_kwargs(**overrides))


# ---------------------------------------------------------------------------
# Integrity + equivalence hash stability (pure)
# ---------------------------------------------------------------------------


def _hash_inputs(**overrides):
    base = dict(
        artifact_type='team_state_card',
        render_version='team-state-1.0.0',
        team_id=147,
        source_snapshot_id=5001,
        subject_type=None,
        subject_key=None,
        product_date=date(2026, 7, 20),
        payload={'a': 1, 'b': {'c': 2, 'd': 3}},
        evidence_entries=[
            {'evidence_key': 'ev:1', 'role': 'primary', 'claim': 'x',
             'completeness_state': 'complete', 'snapshot': {'v': 1}, 'sort_index': 0},
        ],
        trust_metadata={'x': 1, 'y': 2},
        schema_version='1.0.0',
    )
    base.update(overrides)
    return base


def test_equivalence_key_is_deterministic():
    assert compute_equivalence_key(**_hash_inputs()) == compute_equivalence_key(**_hash_inputs())


def test_equivalence_key_is_dict_order_independent():
    ordered = _hash_inputs(payload={'a': 1, 'b': {'c': 2, 'd': 3}}, trust_metadata={'x': 1, 'y': 2})
    reordered = _hash_inputs(payload={'b': {'d': 3, 'c': 2}, 'a': 1}, trust_metadata={'y': 2, 'x': 1})
    assert compute_equivalence_key(**ordered) == compute_equivalence_key(**reordered)


def test_equivalence_key_changes_with_payload():
    a = compute_equivalence_key(**_hash_inputs())
    b = compute_equivalence_key(**_hash_inputs(payload={'a': 1, 'b': {'c': 2, 'd': 4}}))
    assert a != b


def test_equivalence_key_changes_with_render_version():
    a = compute_equivalence_key(**_hash_inputs(render_version='team-state-1.0.0'))
    b = compute_equivalence_key(**_hash_inputs(render_version='team-state-1.1.0'))
    assert a != b


def test_equivalence_key_changes_with_team_id():
    a = compute_equivalence_key(**_hash_inputs(team_id=147))
    b = compute_equivalence_key(**_hash_inputs(team_id=121))
    assert a != b


def test_equivalence_key_changes_with_source_snapshot_id():
    a = compute_equivalence_key(**_hash_inputs(source_snapshot_id=5001))
    b = compute_equivalence_key(**_hash_inputs(source_snapshot_id=5002))
    assert a != b


def test_integrity_hash_binds_published_at():
    common = _hash_inputs()
    a = compute_integrity_hash(public_id='pid', published_at=datetime(2026, 7, 20, 12, 0, 0), **common)
    b = compute_integrity_hash(public_id='pid', published_at=datetime(2026, 7, 20, 12, 0, 1), **common)
    assert a != b


def test_integrity_hash_binds_source_sync_run_id():
    common = _hash_inputs()
    published_at = datetime(2026, 7, 20, 12, 0, 0)
    a = compute_integrity_hash(public_id='pid', published_at=published_at, source_sync_run_id=1, **common)
    b = compute_integrity_hash(public_id='pid', published_at=published_at, source_sync_run_id=2, **common)
    assert a != b


def test_canonical_json_is_stable_and_sorted():
    text = canonical_json({'b': 1, 'a': {'d': 4, 'c': 3}})
    assert text == '{"a":{"c":3,"d":4},"b":1}'


def test_to_json_safe_normalizes_dates():
    assert to_json_safe({'d': date(2026, 7, 20)})['d'] == '2026-07-20'


# ---------------------------------------------------------------------------
# Lifecycle: build + publish
# ---------------------------------------------------------------------------


def test_build_creates_mutable_draft(app):
    draft = _build_draft()
    assert draft.id is not None
    assert draft.lifecycle_state == LIFECYCLE_DRAFT
    assert draft.integrity_hash is None
    assert draft.equivalence_key
    assert draft.public_id
    assert draft.team_id == 147
    assert draft.source_snapshot_id == 5001
    assert len(draft.evidence) == 1


def test_publish_seals_artifact(app):
    art = _publish_sample()
    assert art.lifecycle_state == LIFECYCLE_PUBLISHED
    assert art.published_at is not None
    assert art.integrity_hash
    assert verify_share_artifact_integrity(art) is True


def test_versions_are_semantic_strings(app):
    art = _publish_sample()
    assert art.schema_version == '1.0.0'
    assert SHARE_ARTIFACT_SCHEMA_VERSION == '1.0.0'
    assert art.render_version == DEFAULT_RENDER_VERSION == 'team-state-1.0.0'
    assert isinstance(art.render_version, str)
    assert isinstance(art.schema_version, str)


def test_publish_is_idempotent(app):
    draft = _build_draft()
    published = publish_share_artifact(draft)
    again = publish_share_artifact(published)
    assert again.id == published.id
    assert again.lifecycle_state == LIFECYCLE_PUBLISHED


def test_build_rejects_missing_team_id(app):
    with pytest.raises(ShareArtifactBuildError):
        _build_draft(team_id=None)


def test_build_rejects_missing_source_snapshot_id(app):
    with pytest.raises(ShareArtifactBuildError):
        _build_draft(source_snapshot_id=None)


def test_build_rejects_blank_render_version(app):
    with pytest.raises(ShareArtifactBuildError):
        _build_draft(render_version='   ')


def test_build_rejects_non_mapping_payload(app):
    with pytest.raises(ShareArtifactBuildError):
        _build_draft(payload=['not', 'a', 'mapping'])


def test_source_sync_run_id_is_optional_and_traceable(app):
    run = SyncRun(job_name='share_artifact_test')
    db.session.add(run)
    db.session.flush()

    art = _publish_sample(source_sync_run_id=run.id)
    assert art.source_sync_run_id == run.id
    assert verify_share_artifact_integrity(art) is True

    # Default sample carries no sync-run reference.
    other = _publish_sample(payload={'headline': 'no run ref'})
    assert other.source_sync_run_id is None


def test_source_sync_run_id_excluded_from_equivalence(app):
    # The traceability reference must not change dedup identity: two otherwise
    # identical drafts share an equivalence key regardless of the run reference.
    run = SyncRun(job_name='share_artifact_test')
    db.session.add(run)
    db.session.flush()

    without_run = _build_draft()
    with_run = _build_draft(source_sync_run_id=run.id)
    assert without_run.equivalence_key == with_run.equivalence_key


def test_subject_fields_are_optional_additive(app):
    art = _publish_sample(
        payload={'headline': 'additive'},
        subject_type='team_day',
        subject_key='NYY:2026-07-20',
    )
    assert art.subject_type == 'team_day'
    assert art.subject_key == 'NYY:2026-07-20'
    assert verify_share_artifact_integrity(art) is True


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


def test_equivalent_artifacts_deduplicate(app):
    first = _publish_sample()
    second = _publish_sample()
    assert first.id == second.id
    count = (
        db.session.query(ShareArtifact)
        .filter_by(equivalence_key=first.equivalence_key, lifecycle_state=LIFECYCLE_PUBLISHED)
        .count()
    )
    assert count == 1


def test_distinct_content_creates_distinct_artifacts(app):
    first = _publish_sample()
    second = _publish_sample(payload={'headline': 'Bullpen gassed', 'metrics': {'available': 1}})
    assert first.id != second.id
    assert first.equivalence_key != second.equivalence_key


def test_distinct_team_creates_distinct_artifacts(app):
    first = _publish_sample()
    second = _publish_sample(team_id=121)
    assert first.id != second.id
    assert first.equivalence_key != second.equivalence_key


def test_distinct_source_snapshot_creates_distinct_artifacts(app):
    # Same team + identical content but a different authorizing snapshot is a
    # distinct artifact (linked later by supersede), not a duplicate.
    first = _publish_sample()
    second = _publish_sample(source_snapshot_id=5002)
    assert first.id != second.id
    assert first.equivalence_key != second.equivalence_key


def test_publish_of_manual_draft_deduplicates_and_discards(app):
    canonical = _publish_sample()
    duplicate_draft = _build_draft()
    result = publish_share_artifact(duplicate_draft)
    assert result.id == canonical.id
    assert db.session.get(ShareArtifact, duplicate_draft.id) is None


def test_find_published_equivalent(app):
    art = _publish_sample()
    found = find_published_equivalent(art.equivalence_key)
    assert found is not None and found.id == art.id


# ---------------------------------------------------------------------------
# Immutability after publication
# ---------------------------------------------------------------------------


def test_payload_is_frozen_after_publish(app):
    art = _publish_sample()
    art.payload = {'headline': 'tampered'}
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_trust_metadata_is_frozen_after_publish(app):
    art = _publish_sample()
    art.trust_metadata = {'posture': 'internal_only'}
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_render_version_is_frozen_after_publish(app):
    art = _publish_sample()
    art.render_version = 'team-state-2.0.0'
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_team_id_is_frozen_after_publish(app):
    art = _publish_sample()
    art.team_id = 121
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_source_snapshot_id_is_frozen_after_publish(app):
    art = _publish_sample()
    art.source_snapshot_id = 9999
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_published_at_is_frozen_after_publish(app):
    art = _publish_sample()
    art.published_at = datetime(2000, 1, 1, 0, 0, 0)
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_evidence_row_is_immutable(app):
    art = _publish_sample()
    art.evidence[0].claim = 'rewritten claim'
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_evidence_cannot_be_added_after_publish(app):
    art = _publish_sample()
    art.evidence.append(ShareArtifactEvidence(
        evidence_key='ev:sneaky', role='extra', sort_index=99,
    ))
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_published_artifact_cannot_be_deleted(app):
    art = _publish_sample()
    db.session.delete(art)
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_draft_can_be_deleted(app):
    draft = _build_draft()
    draft_id = draft.id
    db.session.delete(draft)
    db.session.flush()
    assert db.session.get(ShareArtifact, draft_id) is None


# ---------------------------------------------------------------------------
# Lifecycle transitions (legal + illegal)
# ---------------------------------------------------------------------------


def test_supersede_marks_previous_and_records_relation(app):
    previous = _publish_sample()
    replacement = _publish_sample(source_snapshot_id=5002, payload={'headline': 'v2', 'metrics': {'available': 4}})
    relation = supersede_share_artifact(previous, replacement)

    assert previous.lifecycle_state == LIFECYCLE_SUPERSEDED
    assert previous.superseded_at is not None
    assert relation.relation_type == ShareArtifactRelation.RELATION_SUPERSEDES
    assert relation.source_artifact_id == replacement.id
    assert relation.target_artifact_id == previous.id
    assert verify_share_artifact_integrity(previous) is True


def test_supersede_requires_published_previous(app):
    draft = _build_draft()
    replacement = _publish_sample(payload={'headline': 'other'})
    with pytest.raises(ShareArtifactLifecycleError):
        supersede_share_artifact(draft, replacement)


def test_supersede_requires_published_replacement(app):
    previous = _publish_sample()
    replacement_draft = _build_draft(payload={'headline': 'other'})
    with pytest.raises(ShareArtifactLifecycleError):
        supersede_share_artifact(previous, replacement_draft)


def test_withdraw_published_artifact(app):
    art = _publish_sample()
    withdraw_share_artifact(art, reason='factual_error')
    assert art.lifecycle_state == LIFECYCLE_WITHDRAWN
    assert art.withdrawn_at is not None
    assert art.withdrawn_reason == 'factual_error'


def test_withdraw_draft_artifact(app):
    draft = _build_draft()
    withdraw_share_artifact(draft)
    assert draft.lifecycle_state == LIFECYCLE_WITHDRAWN


def test_withdraw_superseded_artifact(app):
    previous = _publish_sample()
    replacement = _publish_sample(source_snapshot_id=5002, payload={'headline': 'v2'})
    supersede_share_artifact(previous, replacement)
    withdraw_share_artifact(previous, reason='retired')
    assert previous.lifecycle_state == LIFECYCLE_WITHDRAWN


def test_cannot_publish_withdrawn_artifact(app):
    art = _publish_sample()
    withdraw_share_artifact(art)
    with pytest.raises(ShareArtifactLifecycleError):
        publish_share_artifact(art, dedup=False)


def test_orm_guard_blocks_illegal_transition_to_draft(app):
    art = _publish_sample()
    art.lifecycle_state = LIFECYCLE_DRAFT
    with pytest.raises(ShareArtifactLifecycleError):
        db.session.flush()
    db.session.rollback()


# ---------------------------------------------------------------------------
# Integrity verification fails closed
# ---------------------------------------------------------------------------


def test_integrity_verification_matches_recompute(app):
    art = _publish_sample()
    assert _compute_integrity_hash_for(art) == art.integrity_hash


def test_integrity_verification_fails_closed_on_content_tamper(app):
    art = _publish_sample()
    art_id = art.id
    db.session.execute(
        sa.update(ShareArtifact)
        .where(ShareArtifact.id == art_id)
        .values(payload={'headline': 'tampered'})
    )
    db.session.expire(art)
    with pytest.raises(ShareArtifactIntegrityError):
        verify_share_artifact_integrity(art)


def test_integrity_verification_fails_closed_on_authority_tamper(app):
    art = _publish_sample()
    art_id = art.id
    db.session.execute(
        sa.update(ShareArtifact)
        .where(ShareArtifact.id == art_id)
        .values(source_snapshot_id=99999)
    )
    db.session.expire(art)
    with pytest.raises(ShareArtifactIntegrityError):
        verify_share_artifact_integrity(art)


def test_integrity_verification_fails_closed_on_hash_tamper(app):
    art = _publish_sample()
    art_id = art.id
    db.session.execute(
        sa.update(ShareArtifact)
        .where(ShareArtifact.id == art_id)
        .values(integrity_hash='0' * 64)
    )
    db.session.expire(art)
    with pytest.raises(ShareArtifactIntegrityError):
        verify_share_artifact_integrity(art)


def test_integrity_verification_rejects_draft(app):
    draft = _build_draft()
    with pytest.raises(ShareArtifactIntegrityError):
        verify_share_artifact_integrity(draft)


# ---------------------------------------------------------------------------
# Assets (forward hook for rendering; append-only, excluded from integrity)
# ---------------------------------------------------------------------------


def test_asset_can_be_attached_after_publish_without_changing_integrity(app):
    art = _publish_sample()
    original_hash = art.integrity_hash
    asset = attach_share_artifact_asset(
        art,
        ShareArtifactAssetInput(
            asset_role='og_image',
            media_type='image/png',
            content_hash='a' * 64,
            storage_uri='s3://cards/og.png',
            width=1200,
            height=630,
        ),
    )
    assert asset.id is not None
    assert asset.render_version == 'team-state-1.0.0'
    assert art.integrity_hash == original_hash
    assert verify_share_artifact_integrity(art) is True


def test_asset_is_immutable_once_created(app):
    art = _publish_sample()
    asset = attach_share_artifact_asset(
        art, ShareArtifactAssetInput(asset_role='og_image', media_type='image/png'),
    )
    asset.content_hash = 'b' * 64
    with pytest.raises(ShareArtifactImmutableError):
        db.session.flush()
    db.session.rollback()


def test_asset_cannot_be_attached_to_withdrawn_artifact(app):
    art = _publish_sample()
    withdraw_share_artifact(art)
    with pytest.raises(ShareArtifactLifecycleError):
        attach_share_artifact_asset(
            art, ShareArtifactAssetInput(asset_role='og_image', media_type='image/png'),
        )


def test_draft_assets_are_not_rendered(app):
    art = _publish_sample(
        assets=[ShareArtifactAssetInput(asset_role='og_image', media_type='image/png')],
    )
    assert len(art.assets) == 1
    assert art.assets[0].content_hash is None
    assert art.assets[0].storage_uri is None
    assert art.assets[0].render_version == 'team-state-1.0.0'


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persistence_round_trip(app):
    art = _publish_sample(
        assets=[ShareArtifactAssetInput(asset_role='og_image', media_type='image/png')],
    )
    art_id = art.id
    public_id = art.public_id
    integrity_hash = art.integrity_hash

    db.session.expunge_all()
    reloaded = db.session.get(ShareArtifact, art_id)

    assert reloaded is not None
    assert reloaded.public_id == public_id
    assert reloaded.team_id == 147
    assert reloaded.source_snapshot_id == 5001
    assert reloaded.lifecycle_state == LIFECYCLE_PUBLISHED
    assert reloaded.integrity_hash == integrity_hash
    assert len(reloaded.evidence) == 1
    assert reloaded.evidence[0].evidence_key == 'ev:availability:NYY:2026-07-20'
    assert len(reloaded.assets) == 1
    assert verify_share_artifact_integrity(reloaded) is True


def test_supersede_relation_persists(app):
    previous = _publish_sample()
    replacement = _publish_sample(source_snapshot_id=5002, payload={'headline': 'v2'})
    supersede_share_artifact(previous, replacement)

    prev_id, repl_id = previous.id, replacement.id
    db.session.expunge_all()

    relation = db.session.query(ShareArtifactRelation).one()
    assert relation.source_artifact_id == repl_id
    assert relation.target_artifact_id == prev_id
    assert relation.relation_type == ShareArtifactRelation.RELATION_SUPERSEDES

    reloaded_prev = db.session.get(ShareArtifact, prev_id)
    assert reloaded_prev.lifecycle_state == LIFECYCLE_SUPERSEDED
    assert len(reloaded_prev.incoming_relations) == 1


def test_to_dict_serializes_domain(app):
    art = _publish_sample()
    payload = art.to_dict()
    assert payload['public_id'] == art.public_id
    assert payload['team_id'] == 147
    assert payload['source_snapshot_id'] == 5001
    assert payload['render_version'] == 'team-state-1.0.0'
    assert payload['schema_version'] == '1.0.0'
    assert payload['lifecycle_state'] == LIFECYCLE_PUBLISHED
    assert payload['integrity_hash'] == art.integrity_hash
    assert payload['evidence'][0]['evidence_key'] == 'ev:availability:NYY:2026-07-20'
    assert 'assets' in payload


# ---------------------------------------------------------------------------
# Migration round-trip + single head
# ---------------------------------------------------------------------------


def _load_migration():
    matches = list(MIGRATIONS_DIR.glob(f'{SHARE_REVISION}_*.py'))
    assert len(matches) == 1, matches
    spec = importlib.util.spec_from_file_location('share_artifacts_migration', matches[0])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_exists(connection, table_name):
    result = connection.execute(sa.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=:table_name"
    ), {'table_name': table_name})
    return result.first() is not None


def test_migration_source_declares_canonical_fields():
    source = list(MIGRATIONS_DIR.glob(f'{SHARE_REVISION}_*.py'))[0].read_text(encoding='utf-8')
    assert f"revision = '{SHARE_REVISION}'" in source
    assert f"down_revision = '{PRIOR_REVISION}'" in source
    for column in (
        'public_id',
        'team_id',
        'source_snapshot_id',
        'source_sync_run_id',
    ):
        assert column in source
    for table in (
        'share_artifacts',
        'share_artifact_evidence',
        'share_artifact_assets',
        'share_artifact_relations',
    ):
        assert table in source


def test_migration_round_trip_and_single_head():
    revisions = {}
    for path in MIGRATIONS_DIR.glob('*.py'):
        text = path.read_text(encoding='utf-8')
        rev = re.search(r"^revision\s*=\s*['\"]([^'\"]+)", text, re.M)
        down = re.search(r"^down_revision\s*=\s*['\"]?([^'\"\n]+)", text, re.M)
        if rev:
            revisions[rev.group(1)] = down.group(1).strip() if down else None
    referenced = {down for down in revisions.values() if down and down != 'None'}
    assert set(revisions) - referenced == {SHARE_REVISION}

    engine = sa.create_engine('sqlite:///:memory:')
    # The share_artifacts.source_sync_run_id FK targets sync_runs, created by an
    # earlier migration in the real chain; provide a stand-in here.
    metadata = sa.MetaData()
    sa.Table('sync_runs', metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)

    with engine.begin() as connection:
        module = _load_migration()
        context = MigrationContext.configure(connection)
        module.op = Operations(context)
        module.upgrade()
        for table in (
            'share_artifacts',
            'share_artifact_evidence',
            'share_artifact_assets',
            'share_artifact_relations',
        ):
            assert _table_exists(connection, table)
        module.downgrade()
        for table in (
            'share_artifacts',
            'share_artifact_evidence',
            'share_artifact_assets',
            'share_artifact_relations',
        ):
            assert not _table_exists(connection, table)
