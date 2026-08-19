"""The real-mutation candidate audit, executed against the canonical lane.

Classification is driven by real shadow runs over a real database, so a
candidate is judged by what the canonical planner actually says about it rather
than by a fixture that agrees with the classifier by construction.

The read-only proof itself needs PostgreSQL — `SET TRANSACTION READ ONLY` and
the refused write probe have no SQLite equivalent — so those tests skip on
other dialects exactly as the no-op candidate audit's do. Everything that does
not need them runs everywhere.
"""

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion as lane
from services import real_mutation_candidate_audit as audit
from services import sync as sync_service
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from tests.game_driven_fixtures import (
    BoxscoreClient,
    REFERENCE,
    boxscore,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
from utils.db import db


GAME_PK = 955001
SECOND_GAME_PK = 955002
PITCHER_ID = 6901
SECOND_PITCHER_ID = 6902


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


def _is_postgres():
    return db.session.get_bind().dialect.name == 'postgresql'


def _install(monkeypatch, boxscores):
    monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient(boxscores))


def _seed(monkeypatch, *, strikeouts=2, extra_stats=None):
    _schedule(GAME_PK)
    _pitcher(PITCHER_ID)
    stats = pitching_stats(strikeouts=strikeouts)
    if extra_stats:
        stats.update(extra_stats)
    _install(monkeypatch, {
        GAME_PK: boxscore([(PITCHER_ID, 'home', stats)]),
    })
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()


def _revise(monkeypatch, *, strikeouts=None, extra_stats=None, **overrides):
    stats = pitching_stats(
        **({'strikeouts': strikeouts} if strikeouts is not None else {}),
        **overrides,
    )
    if extra_stats:
        stats.update(extra_stats)
    _install(monkeypatch, {
        GAME_PK: boxscore([(PITCHER_ID, 'home', stats)]),
    })


def _classify(game_pk=GAME_PK):
    """Run the canonical shadow lane and classify what it actually planned."""
    before = audit.safe_work_item(
        GameIngestionWorkItem.query.filter_by(mlb_game_pk=game_pk).first()
    )
    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=audit.PERMITTED_INGESTION_MODE,
        only_game_pks=[game_pk],
    )
    after = audit.safe_work_item(
        GameIngestionWorkItem.query.filter_by(mlb_game_pk=game_pk).first()
    )
    return shadow, audit.classify_candidate(
        game_pk=game_pk,
        shadow_report=shadow,
        planner_executed=True,
        work_item_before=before,
        work_item_after=after,
    )


# ── Classification against the real planner ─────────────────────────────────


def test_a_real_single_field_correction_is_eligible(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    _, entry = _classify()

    assert entry['eligible'] is True
    assert entry['field'] == 'strikeouts'
    assert entry['pitcher_mlb_id'] == PITCHER_ID
    assert entry['stored_value'] == 2
    assert entry['plan_fingerprint']
    assert entry['source_revision']


def test_a_clean_game_is_reported_as_having_no_mutation(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)

    _, entry = _classify()

    assert entry['eligible'] is False
    assert entry['classification'] == audit.NO_MUTATION_CANDIDATE


def test_a_two_field_revision_is_refused(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3, hits=4)

    _, entry = _classify()

    assert entry['eligible'] is False
    assert audit.MULTI_FIELD_MUTATION in entry['reasons']


def test_an_inherited_runners_revision_is_refused(app, monkeypatch):
    """The historical 824969 design case, as a negative authority example."""
    _seed(monkeypatch, extra_stats={'inheritedRunners': 1})
    _revise(monkeypatch, extra_stats={'inheritedRunners': 2})

    _, entry = _classify()

    assert entry['field'] == 'inherited_runners'
    assert entry['eligible'] is False
    assert audit.FIELD_AUTHORITY_UNRESOLVED in entry['reasons']
    assert entry['field_authority']['authority_resolved'] is False


def test_a_game_with_no_work_item_is_refused(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _schedule(SECOND_GAME_PK)

    _, entry = _classify(SECOND_GAME_PK)

    assert entry['eligible'] is False
    assert audit.TARGET_WORK_ITEM_MISSING in entry['reasons']


# ── The audit writes nothing ────────────────────────────────────────────────


def test_classification_never_changes_the_stored_row(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    shadow, entry = _classify()
    db.session.expire_all()

    pitcher = Pitcher.query.filter_by(mlb_id=PITCHER_ID).one()
    row = GameLog.query.filter_by(
        mlb_game_pk=GAME_PK, pitcher_id=pitcher.id,
    ).one()
    assert row.strikeouts == 2
    assert shadow['execution_effects']['game_log_rows_written'] == 0
    assert shadow['execution_effects']['commits_performed'] == 0
    assert entry['eligible'] is True


def test_classification_never_changes_the_work_item(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)
    item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=GAME_PK).one()
    before = (item.status, item.attempt_count, item.correction_count)

    _classify()
    db.session.expire_all()

    item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=GAME_PK).one()
    assert (item.status, item.attempt_count, item.correction_count) == before


def test_the_shadow_lane_never_advances_a_checkpoint(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    shadow, _ = _classify()

    assert shadow['execution_effects']['work_items_created'] == 0
    assert shadow['execution_effects']['work_items_updated'] == 0
    assert shadow['execution_effects']['checkpoints_advanced'] == 0
    assert shadow['execution_effects']['writes_enabled'] is False


# ── Discovery ───────────────────────────────────────────────────────────────


def test_discovery_finds_completed_work_items_in_the_window(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)

    discovery = audit.discover_candidates(
        reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
    )

    assert discovery['completed_work_items_found'] >= 1
    assert GAME_PK in [
        entry['game_pk'] for entry in discovery['candidates_selected']
    ]


def test_discovery_is_bounded_by_the_candidate_limit(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _schedule(SECOND_GAME_PK)
    _pitcher(SECOND_PITCHER_ID)
    _install(monkeypatch, {
        GAME_PK: boxscore([(PITCHER_ID, 'home', pitching_stats())]),
        SECOND_GAME_PK: boxscore([
            (SECOND_PITCHER_ID, 'home', pitching_stats()),
        ]),
    })
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()

    discovery = audit.discover_candidates(
        reference_date=REFERENCE, lookback_days=30, candidate_limit=1,
    )

    assert len(discovery['candidates_selected']) == 1
    assert discovery['candidate_pool_size'] >= 2


def test_discovery_declares_its_ordering(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)

    discovery = audit.discover_candidates(
        reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
    )

    assert discovery['ordering'] == (
        'completed_at DESC, represented_date DESC, mlb_game_pk ASC'
    )


# ── Bounds ──────────────────────────────────────────────────────────────────


def test_bounds_default_to_the_shared_values():
    bounds = audit.resolve_bounds()
    assert bounds['lookback_days'] == 30
    assert bounds['candidate_limit'] == 20
    assert bounds['eligible_target_count'] == 5


@pytest.mark.parametrize('kwargs', [
    {'lookback_days': '0'},
    {'lookback_days': '121'},
    {'candidate_limit': '51'},
    {'eligible_target_count': '11'},
    {'candidate_limit': '2', 'eligible_target_count': '3'},
    {'lookback_days': 'thirty'},
    {'candidate_limit': '-1'},
])
def test_out_of_bounds_input_is_refused(kwargs):
    with pytest.raises(audit.AuditInputError):
        audit.resolve_bounds(**kwargs)


# ── Read-only enforcement (PostgreSQL only) ─────────────────────────────────


def test_read_only_enforcement_requires_postgresql(app):
    if _is_postgres():
        proof = audit.enforce_read_only(db.session)
        assert proof['read_only_probe_refused'] is True
        assert proof['durable_write_attempts'] == 0
        db.session.rollback()
    else:
        with pytest.raises(Exception):
            audit.enforce_read_only(db.session)


def test_table_fingerprints_cover_every_table_the_shadow_path_reaches(app):
    if not _is_postgres():
        pytest.skip('fingerprints require PostgreSQL')
    before = audit.table_fingerprints(db.session)
    assert before is not None
    assert set(before) == set(audit.FINGERPRINT_TABLES)


def test_an_unchanged_database_fingerprints_identically(app, monkeypatch):
    if not _is_postgres():
        pytest.skip('fingerprints require PostgreSQL')
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    before = audit.table_fingerprints(db.session)
    _classify()
    after = audit.table_fingerprints(db.session)

    assert audit.fingerprints_match(before, after)
    assert audit.changed_tables(before, after) == []


def test_the_full_audit_completes_read_only(app, monkeypatch):
    if not _is_postgres():
        pytest.skip('read-only transactions require PostgreSQL')
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    proof = audit.enforce_read_only(db.session)
    before = audit.table_fingerprints(db.session)
    discovery = audit.discover_candidates(
        reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
    )
    evaluated = audit.evaluate_candidates(
        candidates=discovery['candidates_selected'],
        reference_date=REFERENCE,
        eligible_target_count=5,
        candidate_limit=discovery.get('configured_candidate_limit', 20),
        candidate_pool_size=discovery['candidate_pool_size'],
        session=db.session,
    )
    after = audit.table_fingerprints(db.session)

    decision = audit.decide(
        candidates=evaluated['candidates'],
        read_only_proof={
            'failed_reasons': [], 'unproven_reasons': [], **proof,
        },
    )
    assert audit.fingerprints_match(before, after)
    assert decision['result'] in (
        audit.RESULT_ELIGIBLE_FOUND, audit.RESULT_NO_ELIGIBLE_CANDIDATE,
    )
    assert decision['exit_code'] == 0
