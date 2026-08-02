"""The 14:00 UTC lane's Tonight persistence, against real PostgreSQL.

CI-002: the existing coverage for this lane monkeypatched
``generate_tonight_snapshot_for_date``, so every test passed while production
failed on every run. A mocked writer cannot observe a column width. Nothing in
the suite ever asked PostgreSQL to store the value the lane actually composes.

These tests use the real model, the real writer, the real transaction, and a
real commit. Only the MLB schedule acquisition is stubbed, because that is the
network boundary; everything from composition through COMMIT through readback
is the production path.

They are written around the operation that failed. Production did not fail
inserting a new snapshot — it failed on

    UPDATE tonight_intelligence_snapshots SET response_json = ..., source = ...

for a slate that already had a row, which is the ordinary steady state for a
lane that reruns daily. So the update path is seeded first and exercised
explicitly rather than inferred from insert coverage.
"""

from datetime import date, timedelta

import psycopg2
import pytest
import sqlalchemy as sa
from flask import Flask

from tests.db_config import (
    configure_test_database, create_test_schema, drop_test_schema,
)
# Aliased on import: pytest would otherwise collect the helper as a test case
# because of its name, and a collected helper reports a spurious result.
from tests.db_config import test_database_url as _test_database_url

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.tonight_intelligence_snapshot import (
    TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH,
    TonightIntelligenceSnapshot,
)
from services import schedule_tonight_refresh
from services import tonight_intelligence_snapshot as snapshot_service
from services.tonight_intelligence_snapshot import (
    TONIGHT_SNAPSHOT_VERSION,
    TonightSnapshotSourceError,
)
from utils.db import db


REF_DATE = date(2026, 8, 2)
WORKFLOW_SOURCE = 'github_actions_morning'
PRODUCTION_SOURCE = 'github_actions_morning:schedule_coherence'

pytestmark = pytest.mark.skipif(
    not _test_database_url().startswith('postgresql'),
    reason='PROD-001 regression must be proven against PostgreSQL, not SQLite.',
)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def lane(app, monkeypatch):
    """The real lane with only the MLB schedule request stubbed."""
    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {
            'status': 'ok',
            'start_date': (reference_date - timedelta(days=10)).isoformat(),
            'end_date': (reference_date + timedelta(days=10)).isoformat(),
            'summary': {'errors': 0},
        },
    )
    return app


def _seed_existing_snapshot(*, source='on_demand'):
    """A snapshot row already present for the slate, as production had.

    Written through the ORM and committed so the lane's next run performs the
    UPDATE that failed, not an INSERT.
    """
    row = TonightIntelligenceSnapshot(
        reference_date=REF_DATE,
        snapshot_version=TONIGHT_SNAPSHOT_VERSION,
        status='empty',
        response_json={'reference_date': REF_DATE.isoformat(), 'status': 'empty'},
        card_count=0,
        empty_reason='seeded_for_regression',
        source=source,
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _stored_row():
    db.session.expire_all()
    return (
        TonightIntelligenceSnapshot.query
        .filter_by(reference_date=REF_DATE, snapshot_version=TONIGHT_SNAPSHOT_VERSION)
        .one()
    )


def _readback_source():
    """Read the stored value straight from PostgreSQL, past the ORM cache."""
    return db.session.execute(
        sa.text(
            'SELECT source FROM tonight_intelligence_snapshots '
            'WHERE reference_date = :ref AND snapshot_version = :version'
        ),
        {'ref': REF_DATE, 'version': TONIGHT_SNAPSHOT_VERSION},
    ).scalar()


def _column_length():
    return db.session.execute(
        sa.text(
            'SELECT character_maximum_length FROM information_schema.columns '
            "WHERE table_name = 'tonight_intelligence_snapshots' "
            "AND column_name = 'source'"
        )
    ).scalar()


def _narrow_source_column_to(length):
    """Put the live test column back to the shape production was running."""
    db.session.commit()
    db.session.execute(sa.text(
        'ALTER TABLE tonight_intelligence_snapshots '
        f'ALTER COLUMN source TYPE VARCHAR({length})'
    ))
    db.session.commit()


# ── The schema the model now declares ───────────────────────────────────────


def test_the_live_column_matches_the_shared_maximum(lane):
    """Model and database agree, checked rather than intended."""
    assert _column_length() == TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH == 128


# ── PROD-001, reproduced and repaired on the update path ────────────────────


def test_the_lane_updates_an_existing_snapshot_and_retains_the_full_source(lane):
    """The exact production sequence, end to end.

    Schedule succeeds, Tonight is rebuilt, the existing row is UPDATEd, the
    transaction commits, and the complete 41-character provenance survives a
    readback from PostgreSQL.
    """
    snapshot_id = _seed_existing_snapshot()

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE, source=WORKFLOW_SOURCE,
    )

    assert result['status'] == 'ok'
    assert result['tonight_snapshot']['verified'] is True

    row = _stored_row()
    assert row.id == snapshot_id, 'the lane must update the row, not insert a second'
    assert row.source == PRODUCTION_SOURCE
    assert len(row.source) == 41
    assert _readback_source() == PRODUCTION_SOURCE
    assert len(_readback_source()) == 41


def test_the_same_lane_fails_on_the_old_forty_character_column(lane):
    """The regression this suite exists to prevent.

    Narrow the live column back to what production was running and the
    identical real path fails again — proving the test exercises the schema and
    not a Python-side length check.
    """
    _seed_existing_snapshot()
    _narrow_source_column_to(40)
    assert _column_length() == 40

    with pytest.raises(sa.exc.DataError) as excinfo:
        schedule_tonight_refresh.refresh_schedule_and_tonight(
            REF_DATE, source=WORKFLOW_SOURCE,
        )
    db.session.rollback()

    # The production failure class, named exactly rather than matched loosely.
    assert isinstance(excinfo.value.orig, psycopg2.errors.StringDataRightTruncation)
    assert 'character varying(40)' in str(excinfo.value)


def test_the_stored_provenance_is_never_truncated_or_abbreviated(lane):
    _seed_existing_snapshot()
    schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE, source=WORKFLOW_SOURCE,
    )

    stored = _readback_source()
    assert stored == PRODUCTION_SOURCE
    assert stored.startswith(WORKFLOW_SOURCE)
    assert stored.endswith('schedule_coherence')
    assert '…' not in stored and '...' not in stored
    assert len(stored) == len(PRODUCTION_SOURCE)


def test_the_embedded_response_provenance_carries_the_complete_source(lane):
    """The served payload records the same authority as the column."""
    _seed_existing_snapshot()
    schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE, source=WORKFLOW_SOURCE,
    )

    snapshot_block = (_stored_row().response_json or {}).get('snapshot') or {}
    assert snapshot_block.get('source') == PRODUCTION_SOURCE


def test_the_lane_also_inserts_correctly_when_no_snapshot_exists(lane):
    """The cold-start path, kept alongside the update path rather than instead."""
    assert TonightIntelligenceSnapshot.query.count() == 0

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE, source=WORKFLOW_SOURCE,
    )

    assert result['status'] == 'ok'
    assert _readback_source() == PRODUCTION_SOURCE


def test_unrelated_snapshot_fields_are_governed_by_the_rebuild_alone(lane):
    """Widening the column changed capacity, not the writer's behaviour."""
    _seed_existing_snapshot()
    before = _stored_row()
    identity = (before.id, before.reference_date, before.snapshot_version,
                before.created_at)

    schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE, source=WORKFLOW_SOURCE,
    )

    after = _stored_row()
    assert (after.id, after.reference_date, after.snapshot_version,
            after.created_at) == identity
    assert after.status in {'ok', 'empty'}
    assert after.generated_at is not None


# ── Fail-closed behaviour is unchanged ──────────────────────────────────────


def test_an_incomplete_schedule_refresh_still_writes_no_snapshot(lane, monkeypatch):
    monkeypatch.setattr(
        schedule_tonight_refresh.schedule_authority,
        'ingest_rolling_window',
        lambda reference_date, source: {'status': 'failed', 'summary': {'errors': 3}},
    )

    result = schedule_tonight_refresh.refresh_schedule_and_tonight(
        REF_DATE, source=WORKFLOW_SOURCE,
    )

    assert result['status'] != 'ok'
    assert result['tonight_snapshot']['status'] == 'skipped'
    assert TonightIntelligenceSnapshot.query.count() == 0


def test_an_unstorable_source_fails_before_the_row_is_touched(lane):
    """Fail closed, and fail early.

    An oversized value raises a named application error at composition, so the
    lane never opens a write it cannot finish and the existing snapshot is left
    exactly as it was.
    """
    _seed_existing_snapshot(source='on_demand')
    oversized_base = 'x' * TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH

    with pytest.raises(TonightSnapshotSourceError):
        schedule_tonight_refresh.refresh_schedule_and_tonight(
            REF_DATE, source=oversized_base,
        )
    db.session.rollback()

    assert _readback_source() == 'on_demand'


def test_the_writer_rejects_an_oversized_source_before_commit(lane):
    """Defense in depth for callers that compose their own value."""
    with pytest.raises(TonightSnapshotSourceError):
        snapshot_service.write_snapshot(
            {'reference_date': REF_DATE.isoformat(), 'status': 'empty',
             'card_count': 0},
            source='y' * (TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH + 1),
        )
    db.session.rollback()

    assert TonightIntelligenceSnapshot.query.count() == 0


def test_a_source_at_the_governed_maximum_persists_intact(lane):
    at_limit = 'z' * TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH
    snapshot_service.write_snapshot(
        {'reference_date': REF_DATE.isoformat(), 'status': 'empty',
         'card_count': 0},
        source=at_limit,
    )

    assert _readback_source() == at_limit
    assert len(_readback_source()) == TONIGHT_SNAPSHOT_SOURCE_MAX_LENGTH
