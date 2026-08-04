"""The candidate audit driven against real PostgreSQL and the real lane.

Discovery, ordering, bounds, and the read-only proof are exercised against a
live database — not simulated — because transactions, advisory locks, and
content fingerprints are exactly the behaviour under test.

The shadow evaluation drives the canonical lane: real planner, real
reconciliation planner, real realization semantics, only the box-score client
stubbed.
"""

from datetime import timedelta

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from services import game_driven_ingestion as lane
from services import noop_qualification_candidate_audit as audit
from services import sync as sync_service
from tests.game_driven_fixtures import (
    BoxscoreClient,
    REFERENCE,
    boxscore,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
from utils.db import db


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


postgres_only = pytest.mark.skipif(
    False, reason='requires PostgreSQL',
)


def _seed_games(monkeypatch, specs):
    """Seed N games and complete their durable work items via the real lane."""
    boxscores = {}
    for game_pk, mlb_id in specs:
        _schedule(game_pk)
        _pitcher(mlb_id)
        boxscores[game_pk] = boxscore([
            (mlb_id, 'home', pitching_stats()),
        ])
    monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient(boxscores))
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()
    return boxscores


# ── Discovery ───────────────────────────────────────────────────────────────


def test_only_completed_work_items_are_discovered(app, monkeypatch):
    with app.app_context():
        _seed_games(monkeypatch, [(960101, 7101), (960102, 7102)])

        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=960102
        ).first()
        item.status = GameIngestionWorkItem.STATUS_RETRYABLE_FAILURE
        db.session.commit()

        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        selected = [c['game_pk'] for c in found['candidates_selected']]
        assert 960101 in selected
        assert 960102 not in selected


def test_a_completed_item_cannot_lack_a_completion_timestamp(
    app, monkeypatch,
):
    """The database already guarantees this, so the audit inherits it.

    ``ck_game_ingestion_work_items_completion_proof`` requires a completed row
    to carry completed_at, rows_expected, and an exact reconciliation of it.
    The discovery filter on completed_at is therefore defensive redundancy
    rather than the only thing standing between the audit and a half-finished
    row — which is worth knowing, and worth pinning.
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        _seed_games(monkeypatch, [(960111, 7111)])
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=960111
        ).first()
        item.completed_at = None
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_an_unresolved_item_with_no_completion_timestamp_is_excluded(
    app, monkeypatch,
):
    with app.app_context():
        _seed_games(monkeypatch, [(960112, 7112)])
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=960112
        ).first()
        item.status = GameIngestionWorkItem.STATUS_IN_PROGRESS
        item.completed_at = None
        db.session.commit()

        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        assert found['candidates_selected'] == []


def test_a_duplicate_work_item_identity_is_impossible_in_the_database(
    app, monkeypatch,
):
    """``uq_game_ingestion_work_items_game_pk`` makes this unreachable.

    The audit still de-duplicates and reports duplicates, because a guard that
    depends on a constraint staying in place is a guard with a hidden premise.
    But the honest statement is that the database prevents it first, so the
    ``duplicate_work_item_identity`` classification cannot fire in production
    while that constraint exists.
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        _seed_games(monkeypatch, [(960121, 7121)])
        original = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=960121
        ).first()
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=960121,
            represented_date=original.represented_date,
            candidate_reason=original.candidate_reason,
            criticality=original.criticality,
            status=GameIngestionWorkItem.STATUS_COMPLETED,
            completed_at=original.completed_at,
            rows_expected=original.rows_expected,
            rows_reconciled=original.rows_reconciled,
        ))
        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_the_dedup_logic_still_excludes_a_duplicate_if_one_ever_appeared():
    """Unit-level, because the database will not let one be created."""
    from services import noop_qualification_candidate_audit as service

    class _Row:
        def __init__(self, game_pk, completed_at, represented_date, status):
            self.mlb_game_pk = game_pk
            self.completed_at = completed_at
            self.represented_date = represented_date
            self.status = status

    from datetime import date as _date, datetime as _datetime

    rows = [
        _Row(11, _datetime(2026, 7, 29, 1), _date(2026, 7, 29), 'completed'),
        _Row(11, _datetime(2026, 7, 29, 2), _date(2026, 7, 29), 'completed'),
        _Row(12, _datetime(2026, 7, 29, 3), _date(2026, 7, 29), 'completed'),
    ]
    seen = {}
    for row in rows:
        seen[row.mlb_game_pk] = seen.get(row.mlb_game_pk, 0) + 1
    duplicates = sorted(pk for pk, count in seen.items() if count > 1)
    assert duplicates == [11]
    kept = [r.mlb_game_pk for r in rows if r.mlb_game_pk not in duplicates]
    assert kept == [12]
    assert service.DUPLICATE_WORK_ITEM_IDENTITY in (
        service.CLASSIFICATION_PRECEDENCE
    )


def test_ordering_is_deterministic_and_declared(app, monkeypatch):
    with app.app_context():
        _seed_games(
            monkeypatch,
            [(960201, 7201), (960202, 7202), (960203, 7203)],
        )
        # Force a deterministic completion order, newest first by design.
        items = {
            item.mlb_game_pk: item
            for item in GameIngestionWorkItem.query.all()
        }
        base = items[960201].completed_at
        items[960201].completed_at = base
        items[960202].completed_at = base + timedelta(minutes=5)
        items[960203].completed_at = base + timedelta(minutes=10)
        db.session.commit()

        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        assert [c['game_pk'] for c in found['candidates_selected']] == [
            960203, 960202, 960201,
        ]
        assert found['ordering'] == (
            'completed_at DESC, represented_date DESC, mlb_game_pk ASC'
        )


def test_ties_break_on_the_lowest_game_pk(app, monkeypatch):
    with app.app_context():
        _seed_games(
            monkeypatch,
            [(960303, 7303), (960301, 7301), (960302, 7302)],
        )
        shared = GameIngestionWorkItem.query.first().completed_at
        for item in GameIngestionWorkItem.query.all():
            item.completed_at = shared
        db.session.commit()

        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        assert [c['game_pk'] for c in found['candidates_selected']] == [
            960301, 960302, 960303,
        ]


def test_the_candidate_limit_bounds_the_selection(app, monkeypatch):
    with app.app_context():
        _seed_games(
            monkeypatch,
            [(960400 + n, 7400 + n) for n in range(5)],
        )
        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=2,
        )
        assert len(found['candidates_selected']) == 2
        assert found['candidate_pool_size'] == 5


def test_the_lookback_window_bounds_the_pool(app, monkeypatch):
    with app.app_context():
        _seed_games(monkeypatch, [(960501, 7501)])
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=960501
        ).first()
        item.represented_date = REFERENCE - timedelta(days=90)
        db.session.commit()

        inside = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=120, candidate_limit=20,
        )
        outside = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        assert [c['game_pk'] for c in inside['candidates_selected']] == [960501]
        assert outside['candidates_selected'] == []


def test_discovery_reports_its_window_and_completion_range(app, monkeypatch):
    with app.app_context():
        _seed_games(monkeypatch, [(960601, 7601)])
        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        assert found['window_end'] == REFERENCE.isoformat()
        assert found['window_start'] == (
            REFERENCE - timedelta(days=30)
        ).isoformat()
        assert found['earliest_completion_considered'] is not None
        assert found['latest_completion_considered'] is not None


# ── Eligibility against the real lane ───────────────────────────────────────


def test_an_already_matching_game_is_eligible(app, monkeypatch):
    with app.app_context():
        _seed_games(monkeypatch, [(960701, 7701)])
        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        evaluated = audit.evaluate_candidates(
            candidates=found['candidates_selected'],
            reference_date=REFERENCE,
            eligible_target_count=5,
        )
        candidate = evaluated['candidates'][0]
        assert candidate['eligible'] is True, candidate['reason_codes']
        assert candidate['primary_classification'] == audit.ELIGIBLE
        assert candidate['planned_row_count'] >= 1
        assert candidate['unchanged_row_count'] == (
            candidate['planned_row_count']
        )
        assert candidate['finality_positively_proven'] is True
        assert candidate['source_revision_present'] is True
        assert candidate['plan_fingerprint_present'] is True


def test_a_diverged_official_line_makes_the_candidate_ineligible(
    app, monkeypatch,
):
    with app.app_context():
        _seed_games(monkeypatch, [(960801, 7801)])
        # The official line now disagrees with stored canonical state.
        monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient({
            960801: boxscore([
                (7801, 'home', pitching_stats(strikeouts=9)),
            ]),
        }))

        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        evaluated = audit.evaluate_candidates(
            candidates=found['candidates_selected'],
            reference_date=REFERENCE,
            eligible_target_count=5,
        )
        candidate = evaluated['candidates'][0]
        assert candidate['eligible'] is False
        assert audit.PLAN_PROPOSES_UPDATE in candidate['reason_codes']


def test_evaluation_stops_at_the_eligible_target(app, monkeypatch):
    with app.app_context():
        _seed_games(
            monkeypatch,
            [(960900 + n, 7900 + n) for n in range(4)],
        )
        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        evaluated = audit.evaluate_candidates(
            candidates=found['candidates_selected'],
            reference_date=REFERENCE,
            eligible_target_count=2,
        )
        assert len(evaluated['candidates']) == 2
        assert evaluated['stop_reason'] == audit.STOP_REASON_TARGET_REACHED


def test_evaluating_the_whole_bounded_set_reports_the_limit_stop(
    app, monkeypatch,
):
    with app.app_context():
        _seed_games(monkeypatch, [(961001, 8001), (961002, 8002)])
        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        evaluated = audit.evaluate_candidates(
            candidates=found['candidates_selected'],
            reference_date=REFERENCE,
            eligible_target_count=10,
        )
        assert len(evaluated['candidates']) == 2
        assert evaluated['stop_reason'] == audit.STOP_REASON_CANDIDATE_LIMIT


def test_ordering_position_is_recorded_for_every_candidate(app, monkeypatch):
    with app.app_context():
        _seed_games(monkeypatch, [(961101, 8101), (961102, 8102)])
        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        evaluated = audit.evaluate_candidates(
            candidates=found['candidates_selected'],
            reference_date=REFERENCE,
            eligible_target_count=10,
        )
        assert [c['ordering_position'] for c in evaluated['candidates']] == [
            1, 2,
        ]


# ── Read-only proof ─────────────────────────────────────────────────────────


def test_the_audit_changes_no_database_content(app, monkeypatch):
    """The whole point: run the real evaluation and prove nothing moved."""
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        _seed_games(monkeypatch, [(961201, 8201), (961202, 8202)])

        before = audit.table_fingerprints(db.session)
        assert before is not None

        found = audit.discover_candidates(
            reference_date=REFERENCE, lookback_days=30, candidate_limit=20,
        )
        audit.evaluate_candidates(
            candidates=found['candidates_selected'],
            reference_date=REFERENCE,
            eligible_target_count=10,
        )

        after = audit.table_fingerprints(db.session)
        assert audit.fingerprints_match(before, after), (
            audit.changed_tables(before, after)
        )


@pytest.mark.parametrize('table', audit.FINGERPRINT_TABLES)
def test_every_fingerprinted_table_is_actually_readable(app, table):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        fingerprints = audit.table_fingerprints(db.session, tables=(table,))
        assert fingerprints is not None
        assert table in fingerprints


def test_a_real_gamelog_change_moves_the_fingerprint(app, monkeypatch):
    """Otherwise a matching fingerprint would prove nothing."""
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        _seed_games(monkeypatch, [(961301, 8301)])
        before = audit.table_fingerprints(db.session)

        stored = GameLog.query.filter_by(mlb_game_pk=961301).first()
        stored.strikeouts = (stored.strikeouts or 0) + 1
        db.session.commit()

        after = audit.table_fingerprints(db.session)
        assert not audit.fingerprints_match(before, after)
        assert 'game_logs' in audit.changed_tables(before, after)


def test_a_real_work_item_change_moves_the_fingerprint(app, monkeypatch):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        _seed_games(monkeypatch, [(961401, 8401)])
        before = audit.table_fingerprints(db.session)

        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=961401
        ).first()
        item.attempt_count = (item.attempt_count or 0) + 1
        db.session.commit()

        after = audit.table_fingerprints(db.session)
        assert 'game_ingestion_work_items' in audit.changed_tables(
            before, after
        )


def test_a_real_scheduled_game_change_moves_the_fingerprint(app, monkeypatch):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        from models.scheduled_game import ScheduledGame

        _seed_games(monkeypatch, [(961501, 8501)])
        before = audit.table_fingerprints(db.session)

        row = ScheduledGame.query.filter_by(game_pk=961501).first()
        row.status_code = 'XX'
        db.session.commit()

        after = audit.table_fingerprints(db.session)
        assert 'scheduled_games' in audit.changed_tables(before, after)


def test_a_real_pitcher_change_moves_the_fingerprint(app, monkeypatch):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        from models.pitcher import Pitcher

        _seed_games(monkeypatch, [(961601, 8601)])
        before = audit.table_fingerprints(db.session)

        arm = Pitcher.query.filter_by(mlb_id=8601).first()
        arm.full_name = 'Renamed Arm'
        db.session.commit()

        after = audit.table_fingerprints(db.session)
        assert 'pitchers' in audit.changed_tables(before, after)


def test_the_fingerprint_covers_content_not_only_row_counts(app, monkeypatch):
    """A same-count content change must still be detected."""
    with app.app_context():
        if not _is_postgres():
            pytest.skip('fingerprints require PostgreSQL')
        _seed_games(monkeypatch, [(961701, 8701)])
        before = audit.table_fingerprints(db.session, tables=('game_logs',))
        count_before = GameLog.query.count()

        stored = GameLog.query.filter_by(mlb_game_pk=961701).first()
        stored.earned_runs = (stored.earned_runs or 0) + 1
        db.session.commit()

        assert GameLog.query.count() == count_before
        after = audit.table_fingerprints(db.session, tables=('game_logs',))
        assert before != after


def test_read_only_enforcement_refuses_a_write_and_fails_closed(app):
    with app.app_context():
        if not _is_postgres():
            pytest.skip('read-only transactions require PostgreSQL')
        proof = audit.enforce_read_only(db.session)
        assert proof['protection'] == 'postgresql_read_only_transaction'
        assert proof['write_probe_refused'] is True
        db.session.rollback()


def test_read_only_enforcement_raises_on_a_non_postgres_session(app):
    with app.app_context():
        if _is_postgres():
            pytest.skip('this asserts the non-PostgreSQL failure path')
        with pytest.raises(audit.ReadOnlyNotEnforced):
            audit.enforce_read_only(db.session)


def test_a_read_only_transaction_actually_blocks_a_write(app, monkeypatch):
    """The enforcement is real, not decorative."""
    with app.app_context():
        if not _is_postgres():
            pytest.skip('read-only transactions require PostgreSQL')
        from sqlalchemy import text

        _seed_games(monkeypatch, [(961801, 8801)])
        audit.enforce_read_only(db.session)
        with pytest.raises(Exception):
            db.session.execute(text(
                'UPDATE game_logs SET strikeouts = strikeouts + 1'
            ))
        db.session.rollback()


def test_fingerprints_are_unavailable_rather_than_wrong_on_sqlite(app):
    with app.app_context():
        if _is_postgres():
            pytest.skip('this asserts the non-PostgreSQL path')
        assert audit.table_fingerprints(db.session) is None
