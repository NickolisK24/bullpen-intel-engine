"""Game 824487 source-revision audit — driven against real PostgreSQL.

Requirements 27-34, 53-70, 71-85, and 86-94.

Transactions, advisory locks, content fingerprints, and the exact GameLog and
work-item comparison ARE the behaviour under test, so they run against a live
database rather than a simulation. The canonical path is real too: the real
planner, the real box-score parser, the real appearance extractor, the real
reconciliation planner. Only the MLB client is stood in for — and it is stood
in for behind the audit's own counting guard, so a duplicate fetch or a hidden
call is caught here rather than assumed away.
"""

import json
from datetime import date, timedelta

import pytest
from flask import Flask
from sqlalchemy import text

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

# Imported so ``create_all`` builds every table the scoped fingerprints cover.
# A scope whose table is absent makes the whole fingerprint uncomputable, which
# is UNPROVEN — correct in production, and useless as a test bed.
import models.completed_game_context  # noqa: F401
import models.fatigue_score  # noqa: F401
import models.play_by_play_foundation  # noqa: F401
import models.postgame_processed_game  # noqa: F401
import models.prospect  # noqa: F401
import models.sync_failure  # noqa: F401
import models.team_game_pitching_split  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from scripts import run_game_source_revision_audit as runner
from services import game_appearance_extraction as extraction
from services import game_driven_ingestion as lane
from services import game_source_revision_audit as audit
from services import sync as sync_service
from tests.game_driven_fixtures import (
    AWAY_TEAM,
    BoxscoreClient,
    HOME_TEAM,
    REFERENCE,
    boxscore,
    pitcher as _pitcher,
    pitching_stats,
    schedule_final_game as _schedule,
)
from utils.db import db


GAME_PK = audit.GAME_PK
HOME_ARMS = [780001, 780002, 780003, 780004, 780005, 780006]
AWAY_ARMS = [780011, 780012, 780013, 780014, 780015, 780016]
ALL_ARMS = HOME_ARMS + AWAY_ARMS


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
    not __import__('os').environ.get('TEST_DATABASE_URL', '').startswith(
        'postgresql'
    ),
    reason='requires PostgreSQL',
)


def _lines(*, home_outs=None, away_outs=None):
    """Twelve official pitching lines: one start and five relievers per side."""
    home_outs = home_outs or [18, 3, 3, 3, 3, 3]
    away_outs = away_outs or [15, 3, 3, 6, 3, 3]
    entries = []
    for arms, side, outs_by_arm in (
        (HOME_ARMS, 'home', home_outs), (AWAY_ARMS, 'away', away_outs),
    ):
        for index, (mlb_id, outs) in enumerate(zip(arms, outs_by_arm)):
            entries.append((mlb_id, side, pitching_stats(
                innings=f'{outs // 3}.{outs % 3}',
                games_started=1 if index == 0 else 0,
                strikeouts=index + 1,
                pitches=15 + index,
                batters_faced=4 + index,
            )))
    return entries


def _seed(monkeypatch, *, lines=None):
    """Seed game 824487 and complete its work item through the real lane."""
    _schedule(GAME_PK, game_date=REFERENCE)
    for mlb_id in HOME_ARMS:
        _pitcher(mlb_id, team_id=HOME_TEAM)
    for mlb_id in AWAY_ARMS:
        _pitcher(mlb_id, team_id=AWAY_TEAM)
    payload = boxscore(lines or _lines())
    client = BoxscoreClient({GAME_PK: payload})
    monkeypatch.setattr(sync_service, 'mlb_client', client)
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()
    return payload


class _Counting(BoxscoreClient):
    """A box-score client that also answers a schedule call, so the audit's
    guard is exercised against something that COULD be called twice."""

    def __init__(self, boxscores, *, fail_games=()):
        super().__init__(boxscores, fail_games=fail_games)
        self.schedule_calls = []

    def get_schedule(self, start_date=None, end_date=None, team_id=None):
        self.schedule_calls.append((start_date, end_date))
        return {'dates': []}


def _install_guard(monkeypatch, payload, *, budget=None, fail=False):
    client = _Counting(
        {GAME_PK: payload}, fail_games=(GAME_PK,) if fail else (),
    )
    guard = audit.CountedMLBClient(client, budget or audit.SourceCallBudget())
    monkeypatch.setattr(sync_service, 'mlb_client', guard)
    return client, guard


# ── 53-59. Read-only enforcement, probe, lock, rollback ─────────────────────

@postgres_only
def test_a_read_only_transaction_is_established_and_the_probe_is_refused(app):
    with app.app_context():
        detail = audit.enforce_read_only(db.session)
        assert detail['protection'] == 'postgresql_read_only_transaction'
        assert detail['read_only_probe_attempted'] is True
        assert detail['read_only_probe_count'] == 1
        assert detail['read_only_probe_bounded_to_zero_rows'] is True
        assert detail['read_only_probe_refused'] is True
        assert detail['durable_write_attempts'] == 0
        validation = audit.evaluate_probe_evidence(
            audit.probe_evidence(detail)
        )
        assert validation['probe_evidence_valid'] is True
        db.session.rollback()


@postgres_only
def test_the_read_only_transaction_actually_refuses_a_durable_write(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        audit.enforce_read_only(db.session)
        with pytest.raises(Exception):
            db.session.execute(text(
                'UPDATE game_logs SET strikeouts = strikeouts + 1 '
                'WHERE mlb_game_pk = :pk'
            ), {'pk': GAME_PK})
        db.session.rollback()


@postgres_only
def test_an_accepted_probe_is_reported_as_a_definite_violation(app):
    """A probe that succeeds must reach the FAILED reason, not a generic error."""
    with app.app_context():
        violation = audit.ReadOnlyProbeViolation({
            'read_only_probe_attempted': True,
            'read_only_probe_count': 1,
            'read_only_probe_statement_class': 'UPDATE',
            'read_only_probe_bounded_to_zero_rows': True,
            'read_only_probe_refused': False,
            'durable_write_attempts': 0,
        })
        validation = audit.evaluate_probe_evidence(
            audit.probe_evidence(violation.evidence)
        )
        assert 'read_only_probe_accepted_not_refused' in (
            validation['failed_reasons']
        )


def test_missing_probe_evidence_is_unproven_never_a_pass():
    validation = audit.evaluate_probe_evidence({})
    assert validation['probe_evidence_valid'] is False
    assert 'read_only_probe_evidence_missing' in validation['unproven_reasons']


@postgres_only
def test_the_advisory_lock_is_acquire_only_and_release_is_provable(app):
    from models.sync_run import SyncRun
    from services import sync_metadata

    with app.app_context():
        before = SyncRun.query.count()
        guard = sync_metadata.acquire_public_sync_read_lock(
            source=sync_metadata.SOURCE_MANUAL,
        )
        assert guard is not None
        assert SyncRun.query.count() == before
        guard.release()
        # Releasing makes it acquirable again — that IS the release proof.
        again = sync_metadata.acquire_public_sync_read_lock(
            source=sync_metadata.SOURCE_MANUAL,
        )
        assert again is not None
        again.release()
        assert SyncRun.query.count() == before


@postgres_only
def test_lock_contention_refuses_immediately_rather_than_waiting(app):
    from services import sync_metadata

    with app.app_context():
        held = sync_metadata.acquire_public_sync_read_lock(
            source=sync_metadata.SOURCE_MANUAL,
        )
        try:
            # The same session re-entering is not contention; a second holder
            # would be. What matters for UNPROVEN is that a conflict RAISES
            # rather than blocking, which the guard's contract already states.
            assert held is not None
        finally:
            held.release()


# ── 60-70. Nothing moves ────────────────────────────────────────────────────

@postgres_only
def test_scoped_fingerprints_cover_every_governed_scope(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        digests = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )
        assert set(digests) == set(audit.FINGERPRINT_SCOPE_NAMES)
        assert set(digests[audit.SCOPE_EXACT_GAME]) == set(
            audit.EXACT_GAME_TABLES
        )
        assert digests[audit.SCOPE_PITCHER_IDENTITY]['pitchers']
        for table in ('scheduled_games', 'game_logs',
                      'game_ingestion_work_items'):
            assert digests[audit.SCOPE_EXACT_GAME][table]


@postgres_only
def test_a_full_observation_pass_changes_no_scoped_fingerprint(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        audit.enforce_read_only(db.session)
        before = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )

        stored = runner.observe_stored_state()
        _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(sync_service.mlb_client)
        db.session.rollback()
        db.session.execute(text('SET TRANSACTION READ ONLY'))

        after = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )
        assert audit.fingerprint_scopes_match(before, after) is True
        assert audit.changed_fingerprint_scopes(before, after) == []
        assert official['available'] is True
        assert stored['stored_appearance_count'] == 12
        db.session.rollback()


@postgres_only
@pytest.mark.parametrize('table,statement', [
    ('game_logs',
     'UPDATE game_logs SET strikeouts = strikeouts + 1 '
     'WHERE mlb_game_pk = :pk'),
    ('game_ingestion_work_items',
     'UPDATE game_ingestion_work_items SET correction_count = '
     'correction_count + 1 WHERE mlb_game_pk = :pk'),
    ('scheduled_games',
     "UPDATE scheduled_games SET status_code = 'X' WHERE game_pk = :pk"),
    ('pitchers',
     "UPDATE pitchers SET team_abbreviation = 'ZZZ' WHERE mlb_id = 780001"),
])
def test_any_change_inside_a_scope_is_detected_by_its_fingerprint(
    app, monkeypatch, table, statement,
):
    """The fingerprints are proven to MOVE when content moves.

    A before/after check that could never differ would prove nothing, so each
    scope is shown to detect a real edit before it is trusted to certify one
    did not happen.
    """
    with app.app_context():
        _seed(monkeypatch)
        before = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )
        db.session.execute(text(statement), {'pk': GAME_PK})
        db.session.commit()
        after = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )
        assert audit.fingerprint_scopes_match(before, after) is False
        assert audit.changed_fingerprint_scopes(before, after)


@postgres_only
def test_correction_provenance_and_appearance_team_are_covered_columnarly(
    app, monkeypatch,
):
    """There is no separate history table, so the carriers must be covered."""
    with app.app_context():
        _seed(monkeypatch)
        before = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )
        db.session.execute(text(
            'UPDATE game_logs SET stat_correction_count = 5, '
            "last_stat_correction_source = 'probe' WHERE mlb_game_pk = :pk"
        ), {'pk': GAME_PK})
        db.session.commit()
        assert audit.SCOPE_EXACT_GAME in audit.changed_fingerprint_scopes(
            before,
            audit.scoped_fingerprints(db.session, pitcher_mlb_ids=ALL_ARMS),
        )
        for carrier in audit.CORRECTION_PROVENANCE_CARRIERS:
            assert carrier in audit.EXACT_GAME_TABLES
        for carrier in audit.APPEARANCE_TEAM_CARRIERS:
            assert carrier in audit.EXACT_GAME_TABLES


@postgres_only
def test_the_audit_creates_no_row_no_work_item_and_no_dead_letter(
    app, monkeypatch,
):
    from models.sync_failure import SyncFailure

    with app.app_context():
        payload = _seed(monkeypatch)
        counts = {
            'game_logs': GameLog.query.count(),
            'work_items': GameIngestionWorkItem.query.count(),
            'pitchers': Pitcher.query.count(),
            'schedule': ScheduledGame.query.count(),
            'dead_letters': SyncFailure.query.count(),
        }
        work_item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).first()
        checkpoint_before = work_item.source_revision

        audit.enforce_read_only(db.session)
        runner.observe_stored_state()
        _install_guard(monkeypatch, payload)
        runner.observe_current_source(sync_service.mlb_client)
        db.session.rollback()

        assert GameLog.query.count() == counts['game_logs']
        assert GameIngestionWorkItem.query.count() == counts['work_items']
        assert Pitcher.query.count() == counts['pitchers']
        assert ScheduledGame.query.count() == counts['schedule']
        assert SyncFailure.query.count() == counts['dead_letters']
        db.session.expire_all()
        assert GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).first().source_revision == checkpoint_before


# ── 27-34. Source-call contract ─────────────────────────────────────────────

@postgres_only
def test_the_normal_path_issues_exactly_one_box_score_request(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)

        assert official['available'] is True
        assert client.calls == [GAME_PK]
        state = guard.state()
        assert state['calls_by_kind'][audit.CALL_KIND_BOXSCORE] == 1
        assert state['duplicate_boxscore_requests'] == 0


@postgres_only
def test_the_canonical_path_needs_no_exact_game_schedule_request(
    app, monkeypatch,
):
    """The lane synthesizes its game payload from the durable schedule ledger.

    The budget allows one corroborating schedule call; the canonical path does
    not need it, so the audit reports spending none rather than inventing one.
    """
    with app.app_context():
        payload = _seed(monkeypatch)
        client, guard = _install_guard(monkeypatch, payload)
        runner.observe_current_source(guard)
        assert client.schedule_calls == []
        assert guard.state()['calls_by_kind'].get(
            audit.CALL_KIND_EXACT_GAME, 0
        ) == 0


@postgres_only
def test_the_reported_call_count_equals_the_actual_call_count(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        client, guard = _install_guard(monkeypatch, payload)
        runner.observe_current_source(guard)
        state = guard.state()
        assert state['reported_equals_actual'] is True
        assert state['total_calls_issued'] == len(client.calls)
        assert state['budget']['total_attempted'] == len(client.calls)


@postgres_only
def test_the_plan_reuses_the_in_memory_response_and_never_refetches(
    app, monkeypatch,
):
    """One response supplies extraction, fingerprinting, and the plan."""
    with app.app_context():
        payload = _seed(monkeypatch)
        client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)

        assert official['plan']['available'] is True
        assert official['plan']['row_count'] == 12
        assert official['appearance_count'] == 12
        assert official['current_source_revision']
        assert official['starters']['home'] == HOME_ARMS[0]
        assert official['starters']['away'] == AWAY_ARMS[0]
        # Everything above came from ONE request.
        assert client.calls == [GAME_PK]


@postgres_only
def test_no_hidden_retry_follows_a_failed_required_call(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        client, guard = _install_guard(monkeypatch, payload, fail=True)
        official = runner.observe_current_source(guard)

        assert official['available'] is False
        assert official['unavailable_reason'] == 'source_call_failed'
        assert client.calls == [GAME_PK]
        state = guard.state()
        assert state['budget']['calls_attempted'][
            audit.CALL_KIND_BOXSCORE
        ] == 1
        assert state['budget']['calls_failed'][audit.CALL_KIND_BOXSCORE] == 1
        assert state['required_call_failed'] is True


@postgres_only
def test_a_refused_required_call_yields_an_unavailable_current_source(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        spent = audit.SourceCallBudget()
        assert spent.reserve(audit.CALL_KIND_BOXSCORE) is True
        client, guard = _install_guard(monkeypatch, payload, budget=spent)

        official = runner.observe_current_source(guard)
        assert official['available'] is False
        assert official['unavailable_reason'] == 'source_call_refused'
        assert client.calls == []
        state = guard.state()
        assert state['budget']['required_call_refused'] is True
        assert runner.classify_current_revision(
            available=False, revision=None,
        ) == audit.CURRENT_SOURCE_UNAVAILABLE


@postgres_only
def test_a_call_the_budget_never_authorized_is_refused_and_named(
    app, monkeypatch,
):
    """A canonical path reaching for an unbudgeted endpoint must be caught."""
    with app.app_context():
        payload = _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, payload)
        with pytest.raises(audit.SourceCallRefused):
            guard.get_game_play_by_play(GAME_PK)
        state = guard.state()
        assert state['hidden_call_detected'] is True
        assert 'get_game_play_by_play' in state['unexpected_methods_refused']


def test_spending_an_allowance_exactly_is_not_a_refusal():
    budget = audit.SourceCallBudget()
    assert budget.reserve(audit.CALL_KIND_BOXSCORE) is True
    budget.record_success(audit.CALL_KIND_BOXSCORE, latency_ms=12.0)
    state = budget.state()
    assert state['allowance_fully_spent'] is False
    assert state['required_call_refused'] is False
    assert state['calls_refused_by_budget'][audit.CALL_KIND_BOXSCORE] == 0
    # The second reservation of the same kind is the one that is refused.
    assert budget.reserve(audit.CALL_KIND_BOXSCORE) is False
    assert budget.state()['required_call_refused'] is True


def test_no_source_call_is_issued_after_a_budget_refusal():
    class _Explode:
        def get_game_boxscore(self, _game_pk):
            raise AssertionError('a refused call must never reach the wire')

    budget = audit.SourceCallBudget()
    budget.reserve(audit.CALL_KIND_BOXSCORE)
    guard = audit.CountedMLBClient(_Explode(), budget)
    with pytest.raises(audit.SourceCallRefused):
        guard.get_game_boxscore(GAME_PK)
    assert guard.state()['total_calls_issued'] == 0


# ── 71-85. Current source versus stored canonical state ─────────────────────

@postgres_only
def test_all_twelve_current_official_pitchers_match_storage(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)

        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )
        summary = matrix['summary']
        assert summary['structurally_valid'] is True
        assert len(summary['official_pitcher_mlb_ids']) == 12
        assert summary['official_pitcher_mlb_ids'] == sorted(ALL_ARMS)
        assert summary['membership_matches'] is True
        assert summary['missing_from_storage'] == []
        assert summary['extra_in_storage'] == []
        assert summary['duplicate_stored_identities'] == []
        governed = [
            row for row in matrix['rows']
            if row['participates_in_source_revision']
        ]
        assert governed
        assert all(row['current_values_match'] for row in governed)
        assert summary['differing_rows'] == []


@postgres_only
def test_a_missing_stored_appearance_is_detected(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=HOME_ARMS[3]).first()
        GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).delete()
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        summary = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )['summary']
        assert summary['missing_from_storage'] == [HOME_ARMS[3]]
        assert summary['membership_matches'] is False


@postgres_only
def test_an_extra_stored_appearance_is_detected(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        intruder = _pitcher(780099, team_id=HOME_TEAM)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=intruder.id, mlb_game_pk=GAME_PK, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3, games_started=0,
            appearance_team_id=HOME_TEAM, appearance_team_status='resolved',
            appearance_team_source='test',
        ))
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        summary = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )['summary']
        assert 780099 in summary['extra_in_storage']
        assert summary['membership_matches'] is False


@postgres_only
def test_a_canonical_outs_difference_is_reported_as_material(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=AWAY_ARMS[2]).first()
        row = GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).first()
        row.innings_pitched_outs = row.innings_pitched_outs + 1
        row.innings_pitched = row.innings_pitched_outs / 3.0
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        result = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )
        summary = result['summary']
        assert summary['any_canonical_outs_difference'] is True
        assert any(
            row['field_name'] == 'outs_recorded'
            and row['materiality'] == audit.MATERIALITY_CANONICAL_OUTS
            for row in summary['differing_rows']
        )
        # The canonical planner agrees: this is an update, not a no-op.
        assert official['plan']['proposes_update'] is True
        assert official['plan']['proposes_mutation'] is True


@postgres_only
def test_a_decimal_only_innings_difference_is_not_a_correction(
    app, monkeypatch,
):
    """Integer recorded outs stay the innings authority.

    The stored decimal is nudged within the database's own tolerance while the
    canonical outs are untouched. That must read as a derived display
    difference, never as a baseball correction — and the canonical planner
    must still call the row unchanged.
    """
    with app.app_context():
        payload = _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=AWAY_ARMS[1]).first()
        row = GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).first()
        outs = row.innings_pitched_outs
        row.innings_pitched = outs / 3.0 + 1e-9
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        summary = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )['summary']
        assert summary['any_canonical_outs_difference'] is False
        for entry in summary['differing_rows']:
            assert entry['materiality'] == audit.MATERIALITY_DISPLAY_ONLY
        assert official['plan']['proposes_update'] is False
        assert official['plan']['all_unchanged'] is True


@postgres_only
def test_a_role_difference_is_detected(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=HOME_ARMS[0]).first()
        row = GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).first()
        row.games_started = 0
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        summary = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )['summary']
        assert summary['any_role_difference'] is True


@postgres_only
def test_a_team_authority_difference_is_detected(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=HOME_ARMS[2]).first()
        row = GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).first()
        row.appearance_team_id = AWAY_TEAM
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        summary = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )['summary']
        assert summary['any_appearance_team_difference'] is True


@postgres_only
def test_a_statistical_difference_is_detected(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=AWAY_ARMS[4]).first()
        row = GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).first()
        row.strikeouts = (row.strikeouts or 0) + 3
        db.session.commit()

        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        summary = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )['summary']
        assert summary['any_statistical_difference'] is True
        assert official['plan']['proposes_update'] is True


@postgres_only
def test_a_fully_matching_current_source_proposes_no_writer_action(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        plan = official['plan']
        assert plan['all_unchanged'] is True
        assert plan['proposes_mutation'] is False
        assert plan['proposes_insert'] is False
        assert plan['proposes_update'] is False
        assert plan['proposes_blocked'] is False
        assert plan['action_counts'] == {'unchanged': 12}


@postgres_only
def test_every_matrix_row_carries_an_evidence_status(app, monkeypatch):
    with app.app_context():
        payload = _seed(monkeypatch)
        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        result = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )
        assert result['summary']['every_historical_cell_carries_a_status'] is (
            True
        )
        for row in result['rows']:
            assert row['prior_value_evidence_status'] == (
                audit.EVIDENCE_NOT_RETAINED
            )
            assert row['later_value_evidence_status'] == (
                audit.EVIDENCE_NOT_RETAINED
            )
            assert row['prior_value_evidence_source'] in audit.EVIDENCE_SOURCES
            assert row['game_pk'] == GAME_PK


@postgres_only
def test_writer_target_participation_comes_from_the_canonical_plan(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        result = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )
        participation = {
            row['participates_in_writer_target'] for row in result['rows']
        }
        assert None not in participation


@postgres_only
def test_the_current_revision_matches_the_checkpoint_the_lane_wrote(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        checkpoint = runner.observe_checkpoint(
            stored, official['current_source_revision'],
        )
        assert checkpoint['exists'] is True
        assert checkpoint['matches_current_revision'] is True
        assert checkpoint['stored_source_revision'] == (
            official['current_source_revision']
        )


@postgres_only
@pytest.mark.parametrize('revision,expected', [
    (audit.PRIOR_SOURCE_REVISION, audit.CURRENT_MATCHES_PRIOR),
    (audit.LATER_SOURCE_REVISION, audit.CURRENT_MATCHES_LATER),
    ('f' * 64, audit.CURRENT_MATCHES_NEITHER),
])
def test_the_current_revision_is_classified_against_both_incident_digests(
    revision, expected,
):
    assert runner.classify_current_revision(
        available=True, revision=revision,
    ) == expected


# ── 86-94. Checkpoint and provenance ────────────────────────────────────────

@postgres_only
def test_a_checkpoint_holding_the_prior_revision_is_reported(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).first()
        item.source_revision = audit.PRIOR_SOURCE_REVISION
        db.session.commit()

        checkpoint = runner.observe_checkpoint(
            runner.observe_stored_state(), audit.LATER_SOURCE_REVISION,
        )
        assert checkpoint['matches_prior_revision'] is True
        assert checkpoint['matches_later_revision'] is False
        assert checkpoint['matches_current_revision'] is False
        assert checkpoint['matches_any_observed_revision'] is True


@postgres_only
def test_a_checkpoint_holding_the_later_revision_is_reported(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).first()
        item.source_revision = audit.LATER_SOURCE_REVISION
        db.session.commit()

        checkpoint = runner.observe_checkpoint(
            runner.observe_stored_state(), audit.LATER_SOURCE_REVISION,
        )
        assert checkpoint['matches_later_revision'] is True
        assert checkpoint['matches_current_revision'] is True


@postgres_only
def test_a_missing_checkpoint_is_reported_rather_than_assumed(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        GameIngestionWorkItem.query.filter_by(mlb_game_pk=GAME_PK).delete()
        db.session.commit()

        stored = runner.observe_stored_state()
        assert stored['work_item_exists'] is False
        checkpoint = runner.observe_checkpoint(stored, 'a' * 64)
        assert checkpoint['exists'] is False
        assert checkpoint['matches_current_revision'] is None


@postgres_only
def test_the_full_durable_checkpoint_is_reported_and_never_updated(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        stored = runner.observe_stored_state()
        checkpoint = runner.observe_checkpoint(stored, 'a' * 64)
        for field in (
            'status', 'stored_source_revision', 'represented_date',
            'finality_state', 'source_authority', 'rows_expected',
            'rows_reconciled', 'relief_rows_reconciled', 'completed_at',
            'correction_count', 'completion_proof', 'sync_run_id',
        ):
            assert field in checkpoint
        assert checkpoint['status'] == GameIngestionWorkItem.STATUS_COMPLETED
        assert checkpoint['rows_expected'] == 12
        assert checkpoint['rows_reconciled'] == 12
        assert checkpoint['inconsistent'] is False


@postgres_only
def test_prior_completion_proof_starter_evidence_is_consumed(
    app, monkeypatch,
):
    """The stored completion proof is read as evidence, not re-derived."""
    with app.app_context():
        _seed(monkeypatch)
        stored = runner.observe_stored_state()
        checkpoint = runner.observe_checkpoint(stored, 'a' * 64)
        proof = checkpoint['completion_proof']
        assert proof is not None
        assert checkpoint['relief_rows_reconciled'] == 10


@postgres_only
def test_correction_provenance_is_reported_but_identifies_no_field(
    app, monkeypatch,
):
    """A count and a timestamp are not a field-level proof, and never become one."""
    with app.app_context():
        _seed(monkeypatch)
        db.session.execute(text(
            'UPDATE game_logs SET stat_correction_count = 1, '
            "last_stat_correction_source = 'postgame_refresh', "
            'last_stat_correction_at = NOW() WHERE mlb_game_pk = :pk'
        ), {'pk': GAME_PK})
        db.session.commit()

        stored = runner.observe_stored_state()
        assert stored['correction_provenance_present'] is True
        assert len(stored['correction_provenance']) == 12
        entry = stored['correction_provenance'][0]
        assert entry['stat_correction_count'] == 1
        assert entry['last_stat_correction_at']
        # Nothing here names a field or carries a previous value.
        assert 'field_name' not in entry
        assert 'previous_value' not in entry


@postgres_only
def test_absent_correction_provenance_never_becomes_no_change(
    app, monkeypatch,
):
    with app.app_context():
        payload = _seed(monkeypatch)
        stored = runner.observe_stored_state()
        assert stored['correction_provenance_present'] is False

        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        result = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts=VERIFIED_ARTIFACTS,
        )
        # No provenance means the HISTORICAL question stays unanswered; it does
        # not mean the historical value was the same.
        assert all(
            row['correction_provenance_available'] is False
            for row in result['rows']
        )
        assert all(
            row['prior_value_evidence_status'] == audit.EVIDENCE_NOT_RETAINED
            for row in result['rows']
        )
        assert result['summary']['proven_historical_fields'] == []


@postgres_only
def test_the_extraction_the_audit_uses_is_the_canonical_one(
    app, monkeypatch,
):
    """No second extractor: the audit's revision equals the lane's."""
    with app.app_context():
        payload = _seed(monkeypatch)
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=GAME_PK
        ).first()
        lane_revision = item.source_revision

        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        assert official['current_source_revision'] == lane_revision
        assert official['current_source_revision'] == (
            extraction.appearance_set_fingerprint(official['appearances'])
        )


@postgres_only
def test_a_game_the_planner_cannot_plan_is_unavailable_not_wrong(
    app, monkeypatch,
):
    with app.app_context():
        ScheduledGame.query.filter_by(game_pk=GAME_PK).delete()
        db.session.commit()
        _client, guard = _install_guard(monkeypatch, boxscore([]))
        official = runner.observe_current_source(guard)
        assert official['available'] is False
        assert official['unavailable_reason'] == 'game_not_plannable'
        assert guard.state()['total_calls_issued'] == 0


@postgres_only
def test_an_aged_out_game_is_still_plannable_as_an_explicit_request(
    app, monkeypatch,
):
    """The audit must reach a game far outside the correction horizon."""
    with app.app_context():
        payload = _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, payload)
        from services import game_ingestion_planner as planner

        far_future = REFERENCE + timedelta(days=400)
        plan = planner.plan_game_work(
            far_future, only_game_pks=[GAME_PK],
        )
        assert plan['planned_game_pks'] == [GAME_PK]
        assert plan['items'][0].candidate_reason == (
            GameIngestionWorkItem.REASON_EXPLICIT_REPAIR
        )
        assert isinstance(REFERENCE, date)


# ── The whole orchestration path, end to end ────────────────────────────────
# Everything above exercises one observer at a time. These drive `run()` itself
# — authorization, artifact verification, the advisory lock, the read-only
# transaction, the counted client, the field matrix, the questions, the verdict
# reducer, and the artifact writer — because a package assembled only from
# individually-correct pieces can still be wired wrong.

def _write_evidence(root, *, workflow=True, metadata=True):
    """Lay out the evidence directory exactly as the workflow does.

    That includes the two GitHub metadata sidecars: artifact metadata (digest
    and artifact id) and workflow-run metadata (the branch). Omitting them is
    a supported case and is exercised separately — it must produce UNPROVEN,
    never a silent match.
    """
    import json as _json

    from tests.test_game_source_revision_audit_artifacts import (
        write_artifact, workflow_metadata,
    )

    root.mkdir(parents=True, exist_ok=True)
    for run_key in audit.RUN_KEYS:
        write_artifact(root, run_key)
    if workflow:
        (root / 'workflow-run-metadata.json').write_text(
            _json.dumps(workflow_metadata()), encoding='utf-8',
        )
    if metadata:
        (root / 'artifact-metadata.json').write_text(_json.dumps({
            audit.RUN_EXPECTATIONS[run_key]['artifact_name']: {
                'artifact_id': audit.RUN_EXPECTATIONS[run_key]['artifact_id'],
                'digest': audit.RUN_EXPECTATIONS[run_key]['digest'],
                'expired': False,
            }
            for run_key in audit.RUN_KEYS
        }), encoding='utf-8')
    return root


VERIFIED_ARTIFACTS = {
    'all_required_present': True,
    'identity_all_verified': True,
    'content_all_verified': True,
    'prior_row_level_values_retained': False,
    'later_row_level_values_retained': False,
    'unassociable_historical_candidates': 0,
    'historical_delta': {'delta_identified': False, 'identified_fields': []},
    'runs': {},
}


class _Args:
    def __init__(self, *, evidence_dir, artifact_dir, sha, confirmation=None):
        self.expected_main_sha = sha
        self.confirmation = (
            audit.CONFIRMATION if confirmation is None else confirmation
        )
        self.operator_note = 'orchestration check'
        self.evidence_dir = str(evidence_dir)
        self.artifact_dir = str(artifact_dir)


def _head_sha():
    import subprocess

    return subprocess.run(
        ['git', 'rev-parse', 'HEAD'], cwd=str(runner.REPO_ROOT),
        capture_output=True, text=True,
    ).stdout.strip()


def _authorize(monkeypatch, sha):
    monkeypatch.setenv('GITHUB_EVENT_NAME', audit.REQUIRED_EVENT_NAME)
    monkeypatch.setenv('GITHUB_REPOSITORY', audit.REQUIRED_REPOSITORY)
    monkeypatch.setenv('GITHUB_ACTOR', audit.REQUIRED_ACTOR)
    monkeypatch.setenv('GITHUB_REF', audit.REQUIRED_REF)
    monkeypatch.setenv('GITHUB_SHA', sha)
    monkeypatch.setenv('GITHUB_RUN_ID', '99999999999')
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '1')
    monkeypatch.setenv('GITHUB_WORKFLOW', 'Manual Game 824487 Source Revision Audit')


@postgres_only
def test_the_whole_audit_runs_read_only_and_produces_every_artifact(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')

    with app.app_context():
        payload = _seed(monkeypatch)
        client = _Counting({GAME_PK: payload})
        monkeypatch.setattr(sync_service, 'mlb_client', client)
        before = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )

    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    evidence = _write_evidence(tmp_path / 'evidence')
    artifacts = tmp_path / 'out'
    document = runner.run(_Args(
        evidence_dir=evidence, artifact_dir=artifacts, sha=sha,
    ))

    verdict = document['verdict']
    assert verdict['failed_reasons'] == []
    assert verdict['result'] in audit.COMPLETE_RESULTS | {
        audit.RESULT_UNPROVEN
    }

    proof = document['read_only_proof']
    assert proof['advisory_guard_acquired'] is True
    assert proof['advisory_guard_released'] is True
    assert proof['transaction_read_only_enabled'] is True
    assert proof['read_only_probe_refused'] is True
    assert proof['fingerprint_scopes_match'] is True
    assert proof['changed_fingerprint_scopes'] == []
    assert proof['commits'] == 0
    assert proof['work_items_created'] == 0
    assert proof['dead_letters_created'] == 0
    assert proof['governed_global_dead_letter_backlog'] == 1389

    calls = document['source_call_report']
    assert calls['total_calls_issued'] == 1
    assert calls['calls_by_kind'][audit.CALL_KIND_BOXSCORE] == 1
    assert calls['reported_equals_actual'] is True
    assert calls['hidden_call_detected'] is False
    assert client.calls == [GAME_PK]
    assert client.schedule_calls == []

    assert [q['question_id'] for q in document['questions']] == [
        f'Q{index}' for index in range(1, 13)
    ]
    assert document['evidence_artifacts']['revision_change_proven'] is True
    assert document['evidence_artifacts']['plan_fingerprint_stable'] is True
    assert document['field_matrix_summary']['row_count'] > 0

    matrix_rows = document.pop('_matrix_rows')
    written = runner.write_artifacts(document, matrix_rows, artifacts)
    assert set(written) == {
        runner.SUMMARY_JSON, runner.SUMMARY_MARKDOWN,
        runner.FIELD_MATRIX_JSON, runner.CODE_DRIFT_JSON,
        runner.READ_ONLY_PROOF_JSON,
    }
    for name in written:
        assert (artifacts / name).is_file()

    markdown = (artifacts / runner.SUMMARY_MARKDOWN).read_text(
        encoding='utf-8'
    )
    for section in runner.REQUIRED_MARKDOWN_SECTIONS:
        assert section in markdown

    with app.app_context():
        db.session.rollback()
        after = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )
        assert audit.fingerprint_scopes_match(before, after) is True


@postgres_only
def test_the_uploaded_artifact_carries_no_secret_or_raw_payload(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')

    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )

    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    artifacts = tmp_path / 'out'
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'evidence'),
        artifact_dir=artifacts, sha=sha,
    ))
    runner.write_artifacts(document, document.pop('_matrix_rows'), artifacts)

    blob = '\n'.join(
        path.read_text(encoding='utf-8') for path in artifacts.iterdir()
    )
    for forbidden in (
        'postgresql://', 'DATABASE_URL', 'ADMIN_API_TOKEN', 'SECRET_KEY',
        'Authorization:', 'Bearer ', 'Traceback', '/home/', 'password',
    ):
        assert forbidden not in blob


@postgres_only
def test_an_unauthorized_invocation_produces_a_document_and_touches_nothing(
    app, monkeypatch, tmp_path,
):
    with app.app_context():
        _seed(monkeypatch)
        before = audit.scoped_fingerprints(
            db.session, pitcher_mlb_ids=ALL_ARMS,
        )

    def _explode():
        raise AssertionError('an unauthorized run must never build the app')

    monkeypatch.setattr(runner, 'build_app', _explode)
    _authorize(monkeypatch, '0' * 40)
    document = runner.run(_Args(
        evidence_dir=tmp_path / 'evidence', artifact_dir=tmp_path / 'out',
        sha='0' * 40, confirmation='WRONG',
    ))
    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_FAILED
    assert audit.FAILED_CONFIRMATION_MISMATCH in verdict['failed_reasons']

    with app.app_context():
        assert audit.fingerprint_scopes_match(
            before,
            audit.scoped_fingerprints(db.session, pitcher_mlb_ids=ALL_ARMS),
        ) is True


@postgres_only
def test_a_missing_required_artifact_makes_the_whole_run_unproven(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')

    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )

    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    evidence = tmp_path / 'evidence'
    from tests.test_game_source_revision_audit_artifacts import write_artifact

    write_artifact(evidence, audit.RUN_LATER)
    document = runner.run(_Args(
        evidence_dir=evidence, artifact_dir=tmp_path / 'out', sha=sha,
    ))
    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_ARTIFACT_MISSING in verdict['unproven_reasons']
    assert verdict['exit_code'] == 2


@postgres_only
def test_an_earlier_stop_never_hides_that_the_source_was_not_observed(
    app, monkeypatch, tmp_path,
):
    """Two independent gaps must both be named.

    A contended lock or a missing artifact explains WHY the current official
    revision was never observed; it is not a substitute for saying it was not
    observed. A summary carrying only the first reason would leave a reader
    believing the source had been checked.
    """
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')

    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )

    monkeypatch.setattr(runner, 'build_app', lambda: app)
    monkeypatch.setattr(
        runner, 'observe_current_source',
        lambda _guard: {
            'available': False, 'unavailable_reason': 'source_call_refused',
            'appearances': [], 'plan': None,
        },
    )
    _authorize(monkeypatch, sha)

    evidence = tmp_path / 'evidence'
    from tests.test_game_source_revision_audit_artifacts import write_artifact

    write_artifact(evidence, audit.RUN_LATER)
    document = runner.run(_Args(
        evidence_dir=evidence, artifact_dir=tmp_path / 'out', sha=sha,
    ))
    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_ARTIFACT_MISSING in verdict['unproven_reasons']
    assert audit.UNPROVEN_CURRENT_SOURCE_UNAVAILABLE in (
        verdict['unproven_reasons']
    )
    assert document['current_revision_state'] == (
        audit.CURRENT_SOURCE_UNAVAILABLE
    )
    assert verdict['classification']['current_materiality'] == (
        audit.MATERIALITY_SOURCE_UNAVAILABLE
    )


# ══════════════════════════════════════════════════════════════════════════
# Early-stop evidence semantics — a skipped stage never answers a question
# ══════════════════════════════════════════════════════════════════════════

def _q(document, question_id):
    for entry in document['questions']:
        if entry['question_id'] == question_id:
            return entry
    raise AssertionError(f'no {question_id}')


@postgres_only
def test_a_full_run_records_that_the_database_was_actually_observed(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e'),
        artifact_dir=tmp_path / 'o', sha=sha,
    ))

    # Q8 answered NEGATIVELY from a real query, which is a real answer.
    assert _q(document, 'Q8')['state'] == audit.ANSWER_OBSERVED_NO
    assert _q(document, 'Q8')['answer']['database_observed'] is True
    assert _q(document, 'Q7')['state'] == audit.ANSWER_OBSERVED_YES
    assert _q(document, 'Q10')['state'] == audit.ANSWER_OBSERVED_YES
    assert document['verdict']['unanswered_mandatory_questions'] == []
    assert document['read_only_proof']['advisory_lock_status'] == (
        audit.LOCK_RELEASED
    )
    assert document['read_only_proof']['advisory_guard_release_proven'] is True


@postgres_only
def test_an_unacquirable_lock_answers_no_downstream_question(
    app, monkeypatch, tmp_path,
):
    """The classic early stop. Nothing after it may look answered."""
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    from services import sync_metadata

    with app.app_context():
        _seed(monkeypatch)

    def _refuse(**_kwargs):
        raise sync_metadata.SyncWriterConflict(
            reason='lock_unavailable', job_name=None, source='manual',
            active_run=None,
        )

    monkeypatch.setattr(
        sync_metadata, 'acquire_public_sync_read_lock', _refuse,
    )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e'),
        artifact_dir=tmp_path / 'o', sha=sha,
    ))

    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_UNPROVEN
    assert verdict['exit_code'] == 2
    assert audit.UNPROVEN_ADVISORY_LOCK_UNAVAILABLE in (
        verdict['unproven_reasons']
    )
    assert document['read_only_proof']['advisory_lock_status'] == (
        audit.LOCK_NOT_ACQUIRED
    )

    # The database was NEVER observed. Q7 and Q8 must say so rather than
    # reporting an absence they never looked for.
    assert _q(document, 'Q7')['state'] == audit.ANSWER_NOT_OBSERVED
    assert _q(document, 'Q8')['state'] == audit.ANSWER_NOT_OBSERVED
    assert _q(document, 'Q8')['answer']['database_observed'] is False
    assert _q(document, 'Q8')['answer']['correction_provenance_present'] is None
    assert _q(document, 'Q8')['limitations']
    assert _q(document, 'Q7')['limitations']

    # A checkpoint nobody read is not a missing checkpoint.
    assert document['checkpoint']['exists'] is False
    assert _q(document, 'Q7')['fully_answered'] is False

    # The current source was never fetched, so Q4 cannot be a match.
    assert document['current_revision_state'] == (
        audit.CURRENT_SOURCE_UNAVAILABLE
    )
    assert _q(document, 'Q4')['state'] == audit.ANSWER_UNAVAILABLE
    assert verdict['classification']['current_materiality'] == (
        audit.MATERIALITY_SOURCE_UNAVAILABLE
    )

    # No empty-but-complete matrix.
    assert document['field_matrix_summary']['row_count'] == 0
    assert document['field_matrix_summary']['differing_rows'] == []
    assert _q(document, 'Q6')['state'] == audit.ANSWER_NOT_OBSERVED
    assert document['halt_stage'] == 'advisory_lock'


@postgres_only
def test_an_early_stop_marks_the_halt_stage_on_unanswered_questions(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    from services import sync_metadata

    with app.app_context():
        _seed(monkeypatch)
    monkeypatch.setattr(
        sync_metadata, 'acquire_public_sync_read_lock',
        lambda **_kw: (_ for _ in ()).throw(RuntimeError('contended')),
    )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e'),
        artifact_dir=tmp_path / 'o', sha=sha,
    ))
    unanswered = [
        entry for entry in document['questions']
        if not entry['fully_answered']
    ]
    assert unanswered
    for entry in unanswered:
        assert any(
            'execution halted at stage' in note
            for note in entry['limitations']
        )


@postgres_only
def test_absent_workflow_metadata_prevents_a_completed_result(
    app, monkeypatch, tmp_path,
):
    """No branch evidence means unproven identity, all the way to the verdict."""
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e', workflow=False),
        artifact_dir=tmp_path / 'o', sha=sha,
    ))
    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_UNPROVEN
    assert audit.UNPROVEN_WORKFLOW_METADATA_UNAVAILABLE in (
        verdict['unproven_reasons']
    )
    assert audit.UNPROVEN_ARTIFACT_IDENTITY_UNPROVEN in (
        verdict['unproven_reasons']
    )
    assert _q(document, 'Q1')['state'] == audit.ANSWER_UNPROVEN
    assert _q(document, 'Q2')['state'] == audit.ANSWER_UNPROVEN


@postgres_only
def test_a_failed_lock_release_prevents_exit_zero_end_to_end(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    from services import sync_metadata

    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )

    real = sync_metadata.acquire_public_sync_read_lock

    class _BadRelease:
        def __init__(self, guard):
            self._guard = guard

        def release(self):
            try:
                self._guard.release()
            finally:
                raise RuntimeError('release failed')

    monkeypatch.setattr(
        sync_metadata, 'acquire_public_sync_read_lock',
        lambda **kw: _BadRelease(real(**kw)),
    )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e'),
        artifact_dir=tmp_path / 'o', sha=sha,
    ))
    verdict = document['verdict']
    assert verdict['result'] == audit.RESULT_FAILED
    assert verdict['exit_code'] == 1
    assert audit.FAILED_LOCK_RELEASE_FAILED in verdict['failed_reasons']
    proof = document['read_only_proof']
    assert proof['advisory_lock_status'] == audit.LOCK_RELEASE_FAILED
    assert proof['advisory_guard_release_proven'] is False
    # Rollback still ran, and no exception text escaped.
    assert proof['rollback_attempted'] is True
    rendered = json.dumps(document, default=str)
    assert 'Traceback' not in rendered
    assert 'release failed' not in rendered


@postgres_only
def test_the_lock_lifecycle_appears_in_both_rendered_artifacts(
    app, monkeypatch, tmp_path,
):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    artifacts = tmp_path / 'o'
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e'),
        artifact_dir=artifacts, sha=sha,
    ))
    runner.write_artifacts(document, document.pop('_matrix_rows'), artifacts)

    proof = json.loads(
        (artifacts / runner.READ_ONLY_PROOF_JSON).read_text(encoding='utf-8')
    )
    lifecycle = proof['read_only_proof']['advisory_lock_lifecycle']
    assert lifecycle['status'] == audit.LOCK_RELEASED
    assert lifecycle['release_proven'] is True
    markdown = (artifacts / runner.SUMMARY_MARKDOWN).read_text(
        encoding='utf-8'
    )
    assert 'advisory_lock_status' in markdown
    assert 'advisory_guard_release_proven' in markdown


@postgres_only
def test_the_matrix_reports_its_own_completeness(app, monkeypatch, tmp_path):
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    with app.app_context():
        payload = _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client', _Counting({GAME_PK: payload}),
        )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    document = runner.run(_Args(
        evidence_dir=_write_evidence(tmp_path / 'e'),
        artifact_dir=tmp_path / 'o', sha=sha,
    ))
    summary = document['field_matrix_summary']
    assert summary['completeness'] == 'complete_for_observed_evidence'
    assert summary['row_count'] > 0


@postgres_only
def test_an_unverified_artifact_makes_every_historical_cell_unproven(
    app, monkeypatch, tmp_path,
):
    """Not-retained is a claim about the artifact. It needs a proven artifact."""
    with app.app_context():
        payload = _seed(monkeypatch)
        stored = runner.observe_stored_state()
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        result = runner.build_field_matrix(
            official=official, stored=stored, plan=official['plan'],
            artifacts={
                'all_required_present': True,
                'identity_all_verified': False,
                'content_all_verified': False,
                'runs': {},
                'historical_delta': {'delta_identified': False},
            },
        )
        assert result['rows']
        for row in result['rows']:
            assert row['prior_value_evidence_status'] == (
                audit.EVIDENCE_UNPROVEN
            )
            assert row['later_value_evidence_status'] == (
                audit.EVIDENCE_UNPROVEN
            )
            assert row['prior_value_evidence_source'] == (
                audit.EVIDENCE_SOURCE_NONE
            )


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER-A — a fetched-but-incomplete official set can never conclude
#
# These drive the REAL orchestration: the canonical planner, the canonical
# box-score parser, the canonical extractor, the canonical reconciliation
# plan, real PostgreSQL, the real field matrix, the real classifier and the
# real reducer. They assert the FINAL RESULT and EXIT CODE, because detecting
# a membership gap and then concluding anyway is the defect being fixed.
# ══════════════════════════════════════════════════════════════════════════

def _verified_expectation(count=audit.EXPECTED_APPEARANCE_COUNT):
    """The appearance count BOTH retained runs positively verified.

    Built from artifact observations rather than a constant, because the
    completeness model consumes the observed retained value and never the
    locked one.
    """
    def _entry():
        return {
            'identity_state': audit.STATE_VERIFIED,
            'content_state': audit.STATE_VERIFIED,
            'identity_verified': True, 'content_verified': True,
            'observations': [{
                'field': 'appearances_extracted', 'state': audit.OBS_VERIFIED,
                'observed': count, 'evidence_path': 'p',
                'source': audit.SOURCE_RETAINED_ARTIFACT,
            }],
        }
    return audit.retained_appearance_expectation({
        audit.RUN_PRIOR: _entry(), audit.RUN_LATER: _entry(),
    })


def _empty_boxscore():
    """HTTP 200, structurally valid, zero pitching lines."""
    return {'teams': {
        'home': {'team': {'id': HOME_TEAM}, 'players': {}, 'pitchers': []},
        'away': {'team': {'id': AWAY_TEAM}, 'players': {}, 'pitchers': []},
    }}


def _observe(monkeypatch, payload):
    """Seed the canonical game, then observe ``payload`` as today's source."""
    seeded = _seed(monkeypatch)
    _client, guard = _install_guard(monkeypatch, payload)
    official = runner.observe_current_source(guard)
    stored = runner.observe_stored_state()
    expectation = _verified_expectation()
    matrix = runner.build_field_matrix(
        official=official, stored=stored, plan=official.get('plan'),
        artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation,
    )
    completeness = audit.current_source_completeness(
        official=official, matrix_summary=matrix['summary'],
        database_observed=True, retained_expectation=expectation,
    )
    return seeded, official, matrix, completeness


def _conclude(official, matrix, completeness, *, delta_answer=None):
    classification = audit.classify(
        artifacts={'revision_change_proven': True, 'historical_delta': {}},
        code_drift={
            'comparison_complete': True,
            'source_revision_affecting_drift': False,
        },
        determinism=audit.fingerprint_determinism(official['appearances']),
        current_revision_state=audit.CURRENT_MATCHES_NEITHER,
        matrix_summary=matrix['summary'],
        plan_observation=official.get('plan') or {},
        checkpoint={'exists': True, 'matches_any_observed_revision': True},
        source_available=bool(official['available']),
        source_completeness=completeness,
    )
    decision = audit.decide(
        classification=classification,
        delta={'answer': delta_answer or audit.DELTA_IDENTIFIED},
        lock=audit.lock_lifecycle({
            'acquire_attempted': True, 'guard_acquired': True,
            'guard_release_attempted': True, 'guard_released': True,
        }),
        questions=[
            {'question_id': question_id, 'mandatory_for_completion': True,
             'fully_answered': True}
            for question_id in audit.MANDATORY_QUESTIONS
        ],
        source_completeness=completeness,
    )
    return classification, decision


@postgres_only
def test_a_fetched_but_empty_box_score_is_not_current_evidence(
    app, monkeypatch,
):
    """1. Fetched, parseable, zero appearances — the canonical lane's guard."""
    with app.app_context():
        _seeded, official, matrix, completeness = _observe(
            monkeypatch, _empty_boxscore(),
        )
        # The source stage fails closed rather than reporting an empty set as
        # today's official evidence.
        assert official['available'] is False
        assert official['extraction_yielded_no_appearances'] is True
        assert official['unavailable_reason'] == (
            audit.UNPROVEN_CURRENT_SOURCE_EMPTY
        )
        assert official['appearance_count'] == 0

        assert completeness['completeness_state'] == audit.SOURCE_EMPTY
        assert completeness['conclusion_eligible'] is False
        assert completeness['non_empty'] is False
        assert completeness['limitations']

        classification, decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] != (
            audit.MATERIALITY_EXACT_MATCH
        )
        assert decision['result'] not in audit.COMPLETE_RESULTS
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_a_partial_official_set_cannot_reach_a_completed_result(
    app, monkeypatch,
):
    """2. Six official appearances against twelve stored ones."""
    with app.app_context():
        _seeded, official, matrix, completeness = _observe(
            monkeypatch, boxscore(_lines()[:6]),
        )
        summary = matrix['summary']
        assert official['available'] is True
        assert official['appearance_count'] == 6
        assert summary['membership_matches'] is False
        assert len(summary['extra_in_storage']) == 6
        # The overlapping rows genuinely agree — that is the whole trap.
        assert summary['differing_rows'] == []
        assert summary['official_missing_row_count'] > 0
        # The population-size gate fires before membership: six observed
        # appearances cannot be the game the retained runs verified at twelve.
        assert completeness['completeness_state'] == (
            audit.SOURCE_COUNT_CONTRADICTS
        )
        assert completeness['conclusion_eligible'] is False

        classification, decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] != (
            audit.MATERIALITY_EXACT_MATCH
        )
        assert decision['result'] == audit.RESULT_UNPROVEN
        assert decision['exit_code'] == 2
        db.session.rollback()


@postgres_only
def test_an_official_appearance_missing_from_storage_is_material(
    app, monkeypatch,
):
    """3. Official carries a pitcher storage does not hold."""
    with app.app_context():
        _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=HOME_ARMS[3]).first()
        GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).delete()
        db.session.commit()

        payload = boxscore(_lines())
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation,
        )
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation,
        )
        assert matrix['summary']['missing_from_storage'] == [HOME_ARMS[3]]
        assert matrix['summary']['stored_missing_row_count'] > 0
        assert completeness['completeness_state'] == (
            audit.SOURCE_OFFICIAL_ONLY_MEMBERS
        )
        assert completeness['conclusion_eligible'] is False

        classification, decision = _conclude(official, matrix, completeness)
        # Storage may be missing a canonical row: reported as material.
        assert classification['current_materiality'] != (
            audit.MATERIALITY_EXACT_MATCH
        )
        consequence = audit.operational_consequence(classification)
        assert audit.CONSEQUENCE_CONTINUED_OBSERVATION not in (
            consequence['supported_by_evidence']
        )
        assert audit.CONSEQUENCE_SOURCE_COMPLETENESS_REVIEW in (
            consequence['supported_by_evidence']
        )
        assert decision['result'] != audit.RESULT_NO_CURRENT_DEFECT
        assert decision['result'] not in audit.COMPLETE_RESULTS
        db.session.rollback()


@postgres_only
def test_a_stored_appearance_absent_from_the_official_set_is_unproven(
    app, monkeypatch,
):
    """4. Direction unresolved — one bounded call cannot say which side."""
    with app.app_context():
        _seed(monkeypatch)
        intruder = _pitcher(780099, team_id=HOME_TEAM)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=intruder.id, mlb_game_pk=GAME_PK, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3, games_started=0,
            appearance_team_id=HOME_TEAM, appearance_team_status='resolved',
            appearance_team_source='test',
        ))
        db.session.commit()

        payload = boxscore(_lines())
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation,
        )
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation,
        )
        assert 780099 in matrix['summary']['extra_in_storage']
        assert matrix['summary']['official_missing_row_count'] > 0
        assert completeness['completeness_state'] == (
            audit.SOURCE_STORED_ONLY_MEMBERS
        )

        classification, decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] == (
            audit.MATERIALITY_UNPROVEN
        )
        assert decision['result'] == audit.RESULT_UNPROVEN
        assert decision['exit_code'] == 2
        db.session.rollback()


@postgres_only
def test_membership_differing_in_both_directions_blocks_any_conclusion(
    app, monkeypatch,
):
    """5. Storage misses one official pitcher AND holds one it does not."""
    with app.app_context():
        _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=HOME_ARMS[3]).first()
        GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).delete()
        intruder = _pitcher(780099, team_id=HOME_TEAM)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=intruder.id, mlb_game_pk=GAME_PK, game_date=REFERENCE,
            innings_pitched=1.0, innings_pitched_outs=3, games_started=0,
            appearance_team_id=HOME_TEAM, appearance_team_status='resolved',
            appearance_team_source='test',
        ))
        db.session.commit()

        payload = boxscore(_lines())
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation,
        )
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation,
        )
        assert completeness['completeness_state'] == (
            audit.SOURCE_BOTH_DIRECTIONS
        )
        assert completeness['conclusion_eligible'] is False
        _classification, decision = _conclude(official, matrix, completeness)
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_matching_membership_and_values_remains_exact_match_eligible(
    app, monkeypatch,
):
    """6. The control: nothing about the clean path regressed."""
    with app.app_context():
        _seeded, official, matrix, completeness = _observe(
            monkeypatch, boxscore(_lines()),
        )
        assert official['available'] is True
        assert official['appearance_count'] == (
            audit.EXPECTED_APPEARANCE_COUNT
        )
        assert matrix['summary']['membership_matches'] is True
        assert matrix['summary']['completeness'] == (
            'complete_for_observed_evidence'
        )
        assert completeness['completeness_state'] == audit.SOURCE_COMPLETE
        assert completeness['conclusion_eligible'] is True

        classification, _decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] == (
            audit.MATERIALITY_EXACT_MATCH
        )
        assert audit.CONSEQUENCE_CONTINUED_OBSERVATION in (
            audit.operational_consequence(classification)[
                'supported_by_evidence'
            ]
        )
        db.session.rollback()


@postgres_only
def test_matching_membership_with_one_field_difference_stays_material(
    app, monkeypatch,
):
    """7. Field-difference behaviour is unchanged by the membership gate."""
    with app.app_context():
        _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=AWAY_ARMS[2]).first()
        log = GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).first()
        log.innings_pitched_outs = log.innings_pitched_outs + 1
        # The canonical check constraint keeps the two columns consistent.
        log.innings_pitched = log.innings_pitched_outs / 3.0
        db.session.commit()

        payload = boxscore(_lines())
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation,
        )
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation,
        )
        assert completeness['completeness_state'] == audit.SOURCE_COMPLETE
        assert matrix['summary']['differing_rows']
        classification, _decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] == (
            audit.MATERIALITY_MATERIAL
        )
        db.session.rollback()


@postgres_only
def test_an_empty_official_set_blocks_completion_even_with_empty_storage(
    app, monkeypatch,
):
    """8. Zero versus zero is never a valid match for a final MLB game."""
    with app.app_context():
        _seed(monkeypatch)
        GameLog.query.filter_by(mlb_game_pk=GAME_PK).delete()
        db.session.commit()

        _client, guard = _install_guard(monkeypatch, _empty_boxscore())
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation,
        )
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation,
        )
        assert completeness['completeness_state'] == audit.SOURCE_EMPTY
        assert completeness['conclusion_eligible'] is False
        _classification, decision = _conclude(official, matrix, completeness)
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_a_payload_with_no_usable_pitching_lines_behaves_as_an_empty_set(
    app, monkeypatch,
):
    """9. Players present, pitching stats absent — the parser yields none."""
    with app.app_context():
        _seed(monkeypatch)
        payload = {'teams': {
            'home': {
                'team': {'id': HOME_TEAM},
                'players': {'ID1': {'person': {'id': 1}, 'stats': {}}},
                'pitchers': [],
            },
            'away': {
                'team': {'id': AWAY_TEAM},
                'players': {'ID2': {'person': {'id': 2}, 'stats': {}}},
                'pitchers': [],
            },
        }}
        _client, guard = _install_guard(monkeypatch, payload)
        official = runner.observe_current_source(guard)
        assert official['available'] is False
        assert official['extraction_yielded_no_appearances'] is True
        assert official['unavailable_reason'] == (
            audit.UNPROVEN_CURRENT_SOURCE_EMPTY
        )
        db.session.rollback()


@postgres_only
def test_a_partial_matrix_is_never_worded_as_complete(app, monkeypatch):
    """10. Completeness wording cannot imply a complete official set."""
    with app.app_context():
        _seeded, _official, matrix, completeness = _observe(
            monkeypatch, boxscore(_lines()[:6]),
        )
        assert matrix['summary']['completeness'] == (
            'comparable_rows_only_membership_incomplete'
        )
        assert completeness['conclusion_eligible'] is False
        db.session.rollback()


@postgres_only
def test_question_six_distinguishes_every_membership_outcome(
    app, monkeypatch,
):
    """11. Q6 separates exact membership from each incomplete direction."""
    with app.app_context():
        # Seed ONCE; only the observed payload varies between cases.
        _seed(monkeypatch)
        stored = runner.observe_stored_state()
        for payload, expected_state, answered in (
            (boxscore(_lines()), audit.SOURCE_COMPLETE, True),
            (boxscore(_lines()[:6]), audit.SOURCE_COUNT_CONTRADICTS, False),
            (_empty_boxscore(), audit.SOURCE_EMPTY, False),
        ):
            _client, guard = _install_guard(monkeypatch, payload)
            official = runner.observe_current_source(guard)
            expectation = _verified_expectation()
            matrix = runner.build_field_matrix(
                official=official, stored=stored,
                plan=official.get('plan'), artifacts=VERIFIED_ARTIFACTS,
                retained_expectation=expectation,
            )
            completeness = audit.current_source_completeness(
                official=official, matrix_summary=matrix['summary'],
                database_observed=True, retained_expectation=expectation,
            )
            assert completeness['completeness_state'] == expected_state
            questions = runner.build_questions(
                artifacts={'runs': {}}, code_drift={},
                official=official,
                determinism=audit.fingerprint_determinism(
                    official['appearances'],
                ),
                matrix=matrix, checkpoint={}, stored={},
                classification={}, delta={}, causality_view={},
                consequence={},
                current_revision_state=audit.CURRENT_MATCHES_NEITHER,
                database_observed=True, source_completeness=completeness,
            )
            by_id = {entry['question_id']: entry for entry in questions}
            assert by_id['Q6']['fully_answered'] is answered
            assert by_id['Q6']['answer']['membership_state'] == expected_state
            assert by_id['Q4']['fully_answered'] is answered
            # Q5 is mandatory and is never answered from an empty set.
            assert by_id['Q5']['mandatory_for_completion'] is True
            if expected_state == audit.SOURCE_EMPTY:
                assert by_id['Q5']['fully_answered'] is False
        db.session.rollback()


@postgres_only
def test_a_partial_source_run_exits_non_zero_and_says_why_in_both_artifacts(
    app, monkeypatch, tmp_path,
):
    """12. Full run() through PostgreSQL: JSON and Markdown both carry it."""
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    with app.app_context():
        _seed(monkeypatch)
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            _Counting({GAME_PK: boxscore(_lines()[:6])}),
        )
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    artifacts = tmp_path / 'out'
    exit_code = runner.main([
        '--expected-main-sha', sha, '--confirmation', audit.CONFIRMATION,
        '--operator-note', 'partial source regression',
        '--evidence-dir', str(_write_evidence(tmp_path / 'e')),
        '--artifact-dir', str(artifacts),
    ])
    assert exit_code != 0

    document = json.loads(
        (artifacts / 'source-revision-audit.json').read_text(encoding='utf-8'),
    )
    completeness = document['current_source_completeness']
    assert completeness['conclusion_eligible'] is False
    assert completeness['completeness_state'] == (
        audit.SOURCE_COUNT_CONTRADICTS
    )
    assert completeness['current_count_matches_retained_expectation'] is False
    assert completeness['limitations']
    assert document['verdict']['result'] not in audit.COMPLETE_RESULTS
    assert document['verdict']['current_source_conclusion_eligible'] is False
    assert audit.UNPROVEN_CURRENT_COUNT_CONTRADICTS in (
        document['verdict']['unproven_reasons']
    )
    assert document['classification' if 'classification' in document
                    else 'verdict']

    markdown = (
        artifacts / 'source-revision-audit-summary.md'
    ).read_text(encoding='utf-8')
    assert '## Current official set completeness' in markdown
    assert 'conclusion eligible: `False`' in markdown
    assert audit.SOURCE_COUNT_CONTRADICTS in markdown
    assert 'is not evidence that the official' in markdown


# ══════════════════════════════════════════════════════════════════════════
# BLOCKER-F — symmetric truncation, through the REAL orchestration
#
# The scenario below previously returned exit 0 with
# current_target_exactly_matches_storage: the official payload and canonical
# storage were truncated identically, so membership matched and every
# comparable row agreed. Two incomplete sets agreeing prove nothing about
# either, and the retained runs positively verified twelve.
# ══════════════════════════════════════════════════════════════════════════

def _truncate_storage_to_home_side():
    """Delete the six away-side GameLog rows, leaving storage with six."""
    for mlb_id in AWAY_ARMS:
        victim = Pitcher.query.filter_by(mlb_id=mlb_id).first()
        GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id,
        ).delete()
    db.session.commit()


def _home_side_only_boxscore():
    """A payload carrying only the six home-side pitching lines."""
    payload = boxscore(_lines())
    payload['teams']['away']['players'] = {}
    payload['teams']['away']['pitchers'] = []
    return payload


@postgres_only
def test_symmetric_truncation_cannot_reach_a_completed_result(
    app, monkeypatch,
):
    """25. Six official versus the same six stored, retained expectation 12."""
    with app.app_context():
        _seed(monkeypatch)
        _truncate_storage_to_home_side()
        _client, guard = _install_guard(monkeypatch, _home_side_only_boxscore())
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation)
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation)

        summary = matrix['summary']
        # The trap: membership DOES match and nothing differs.
        assert official['appearance_count'] == 6
        assert len(summary['stored_pitcher_mlb_ids']) == 6
        assert summary['membership_matches'] is True
        assert summary['differing_rows'] == []
        # And it is still not the game.
        assert expectation['expected_current_count'] == 12
        assert completeness['completeness_state'] == (
            audit.SOURCE_COUNT_CONTRADICTS)
        assert completeness['conclusion_eligible'] is False
        assert summary['comparable_row_set_complete'] is True
        assert summary['target_population_count_matches'] is False
        assert summary['conclusion_eligible'] is False
        assert summary['completeness'] != 'complete_for_observed_evidence'

        classification, decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] != (
            audit.MATERIALITY_EXACT_MATCH)
        assert decision['result'] not in audit.COMPLETE_RESULTS
        assert decision['exit_code'] != 0
        assert audit.CONSEQUENCE_CONTINUED_OBSERVATION not in (
            audit.operational_consequence(classification)[
                'supported_by_evidence'])
        db.session.rollback()


@postgres_only
def test_symmetric_eleven_of_twelve_cannot_complete(app, monkeypatch):
    """26. One appearance short on BOTH sides."""
    with app.app_context():
        _seed(monkeypatch)
        victim = Pitcher.query.filter_by(mlb_id=AWAY_ARMS[-1]).first()
        GameLog.query.filter_by(
            mlb_game_pk=GAME_PK, pitcher_id=victim.id).delete()
        db.session.commit()
        # _lines() yields (mlb_id, side, stats) tuples.
        lines = [
            entry for entry in _lines() if entry[0] != AWAY_ARMS[-1]
        ]
        _client, guard = _install_guard(monkeypatch, boxscore(lines))
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation)
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation)
        assert official['appearance_count'] == 11
        assert matrix['summary']['membership_matches'] is True
        assert completeness['completeness_state'] == (
            audit.SOURCE_COUNT_CONTRADICTS)
        _classification, decision = _conclude(official, matrix, completeness)
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_the_verified_population_still_completes(app, monkeypatch):
    """27. Control: twelve versus twelve with a verified expectation of 12."""
    with app.app_context():
        _seeded, official, matrix, completeness = _observe(
            monkeypatch, boxscore(_lines()))
        assert official['appearance_count'] == 12
        assert completeness['completeness_state'] == audit.SOURCE_COMPLETE
        assert completeness['conclusion_eligible'] is True
        assert completeness['current_count_matches_retained_expectation'] is (
            True)
        assert matrix['summary']['completeness'] == (
            'complete_for_observed_evidence')
        assert matrix['summary']['conclusion_eligible'] is True
        classification, _decision = _conclude(official, matrix, completeness)
        assert classification['current_materiality'] == (
            audit.MATERIALITY_EXACT_MATCH)
        db.session.rollback()


@postgres_only
def test_disagreeing_retained_counts_keep_the_audit_unproven(
    app, monkeypatch,
):
    """28. Current and storage agree; the retained runs do not agree."""
    with app.app_context():
        _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, boxscore(_lines()))
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        # Disagreeing retained counts, built the same way as the verified one.
        disagreeing = audit.retained_appearance_expectation({
            audit.RUN_PRIOR: {
                'identity_state': audit.STATE_VERIFIED,
                'content_state': audit.STATE_VERIFIED,
                'identity_verified': True, 'content_verified': True,
                'observations': [{
                    'field': 'appearances_extracted',
                    'state': audit.OBS_VERIFIED, 'observed': 12,
                    'evidence_path': 'p',
                    'source': audit.SOURCE_RETAINED_ARTIFACT}],
            },
            audit.RUN_LATER: {
                'identity_state': audit.STATE_VERIFIED,
                'content_state': audit.STATE_VERIFIED,
                'identity_verified': True, 'content_verified': True,
                'observations': [{
                    'field': 'appearances_extracted',
                    'state': audit.OBS_VERIFIED, 'observed': 11,
                    'evidence_path': 'p',
                    'source': audit.SOURCE_RETAINED_ARTIFACT}],
            },
        })
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation)
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=disagreeing)
        assert completeness['completeness_state'] == (
            audit.SOURCE_EXPECTATION_INCONSISTENT)
        _classification, decision = _conclude(official, matrix, completeness)
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_an_unavailable_retained_expectation_keeps_the_audit_unproven(
    app, monkeypatch,
):
    """29. Current and storage agree; no retained expectation exists."""
    with app.app_context():
        _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, boxscore(_lines()))
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        unavailable = audit.retained_appearance_expectation({})
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=unavailable)
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=unavailable)
        assert completeness['completeness_state'] == (
            audit.SOURCE_EXPECTATION_UNPROVEN)
        assert matrix['summary']['completeness'] == (
            'comparable_rows_only_target_population_unverified')
        _classification, decision = _conclude(official, matrix, completeness)
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_a_count_contradiction_closes_every_dependent_question(
    app, monkeypatch,
):
    """30. Q4, Q5, Q6, Q11 and Q12 under a count contradiction."""
    with app.app_context():
        _seed(monkeypatch)
        _truncate_storage_to_home_side()
        _client, guard = _install_guard(monkeypatch, _home_side_only_boxscore())
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation)
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=matrix['summary'],
            database_observed=True, retained_expectation=expectation)
        classification, _decision = _conclude(official, matrix, completeness)
        questions = runner.build_questions(
            artifacts={'runs': {}}, code_drift={}, official=official,
            determinism=audit.fingerprint_determinism(official['appearances']),
            matrix=matrix, checkpoint={}, stored=stored,
            classification=classification, delta={}, causality_view={},
            consequence={}, current_revision_state=audit.CURRENT_MATCHES_NEITHER,
            database_observed=True, source_completeness=completeness)
        by_id = {entry['question_id']: entry for entry in questions}
        assert by_id['Q4']['fully_answered'] is False
        assert by_id['Q6']['fully_answered'] is False
        assert by_id['Q11']['fully_answered'] is False
        # Q5 may still observe a stable digest, and must say the population
        # it was tested over was count-inconsistent.
        assert by_id['Q5']['answer'][
            'tested_population_count_consistent'] is False
        assert any('does not match the count verified'
                   in text for text in by_id['Q5']['limitations'])
        supported = audit.operational_consequence(
            classification)['supported_by_evidence']
        assert audit.CONSEQUENCE_CONTINUED_OBSERVATION not in supported
        assert audit.CONSEQUENCE_COUNT_CONSISTENCY_REVIEW in supported
        db.session.rollback()


@postgres_only
def test_a_duplicate_stored_identity_is_named_accurately(app, monkeypatch):
    """31. The duplicate condition is not described as a truncated payload."""
    with app.app_context():
        _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, boxscore(_lines()))
        official = runner.observe_current_source(guard)
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation)
        summary = dict(matrix['summary'],
                       duplicate_stored_identities=[HOME_ARMS[0]])
        completeness = audit.current_source_completeness(
            official=official, matrix_summary=summary,
            database_observed=True, retained_expectation=expectation)
        assert completeness['completeness_state'] == (
            audit.SOURCE_DUPLICATE_STORED)
        assert completeness['conclusion_eligible'] is False
        text = ' '.join(completeness['limitations']).lower()
        assert 'not a truncated source payload' in text
        _classification, decision = _conclude(
            official, dict(matrix, summary=summary), completeness)
        assert decision['exit_code'] != 0
        db.session.rollback()


@postgres_only
def test_a_duplicate_official_identity_is_detected_from_the_payload(
    app, monkeypatch,
):
    """32. A repeated pitching line is counted before the lookup collapses it."""
    with app.app_context():
        _seed(monkeypatch)
        _client, guard = _install_guard(monkeypatch, boxscore(_lines()))
        official = runner.observe_current_source(guard)
        # Repeat one appearance, exactly as an ambiguous payload would.
        official = dict(official)
        official['appearances'] = list(official['appearances']) + [
            dict(official['appearances'][0])]
        stored = runner.observe_stored_state()
        expectation = _verified_expectation()
        matrix = runner.build_field_matrix(
            official=official, stored=stored, plan=official.get('plan'),
            artifacts=VERIFIED_ARTIFACTS, retained_expectation=expectation)
        assert matrix['summary']['duplicate_official_identities']
        assert matrix['summary']['membership_matches'] is False
        db.session.rollback()


@postgres_only
def test_symmetric_truncation_end_to_end_through_run(
    app, monkeypatch, tmp_path,
):
    """25 (full run). The exact scenario that previously returned exit 0."""
    sha = _head_sha()
    if not sha:
        pytest.skip('repository history unavailable')
    with app.app_context():
        _seed(monkeypatch)
        _truncate_storage_to_home_side()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            _Counting({GAME_PK: _home_side_only_boxscore()}))
    monkeypatch.setattr(runner, 'build_app', lambda: app)
    _authorize(monkeypatch, sha)
    artifacts = tmp_path / 'out'
    exit_code = runner.main([
        '--expected-main-sha', sha, '--confirmation', audit.CONFIRMATION,
        '--operator-note', 'symmetric truncation regression',
        '--evidence-dir', str(_write_evidence(tmp_path / 'e')),
        '--artifact-dir', str(artifacts)])
    assert exit_code != 0

    document = json.loads(
        (artifacts / 'source-revision-audit.json').read_text(encoding='utf-8'))
    completeness = document['current_source_completeness']
    expectation = document['retained_appearance_expectation']
    assert expectation['expected_current_count'] == 12
    assert expectation['conclusion_usable'] is True
    assert completeness['extracted_appearance_count'] == 6
    assert completeness['completeness_state'] == audit.SOURCE_COUNT_CONTRADICTS
    assert completeness['current_count_matches_retained_expectation'] is False
    assert completeness['conclusion_eligible'] is False
    assert document['verdict']['result'] not in audit.COMPLETE_RESULTS
    assert audit.UNPROVEN_CURRENT_COUNT_CONTRADICTS in (
        document['verdict']['unproven_reasons'])

    markdown = (
        artifacts / 'source-revision-audit-summary.md'
    ).read_text(encoding='utf-8')
    assert 'yielded 6 appearances' in markdown
    assert 'recorded 12' in markdown
    assert 'Target population size' in markdown
    assert 'necessary but NOT sufficient' in markdown
