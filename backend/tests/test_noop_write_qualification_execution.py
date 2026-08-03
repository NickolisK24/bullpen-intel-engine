"""The no-op write qualification driven through the REAL canonical lane.

These tests run the actual entry point — ``run_game_driven_ingestion`` — with
the real planner, the real reconciliation planner, the real GameLog writer, and
the real realization validator. Only the MLB box-score client is stubbed. A
hand-rolled writer here would be a second implementation, which is the exact
drift this qualification exists to detect.

They run against PostgreSQL in CI (``TEST_DATABASE_URL``), so the transaction,
constraint, and advisory-lock behaviour under test is the real one.

The central measured fact, asserted rather than assumed: an exclusive write over
an already-matching game writes ZERO baseball rows and still advances the lane's
own completion ledger. Both halves are pinned.
"""

import pytest
from flask import Flask

from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.game_ingestion_work_item import GameIngestionWorkItem
from services import game_driven_ingestion as lane
from services import game_driven_realization as realization_service
from services import game_log_reconciliation as reconciliation
from services import noop_write_qualification as qualification
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


GAME_PK = 951001
OTHER_GAME_PK = 951002
PITCHER_ID = 6601
OTHER_PITCHER_ID = 6602
SHA = 'c' * 40


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


def context(game_pk=GAME_PK, **overrides):
    base = {
        'event_name': 'workflow_dispatch',
        'repository': 'NickolisK24/bullpen-intel-engine',
        'actor': 'NickolisK24',
        'ref': 'refs/heads/main',
        'github_sha': SHA,
        'expected_head_sha': SHA,
        'confirmation': f'QUALIFY_NOOP_GAME_{game_pk}',
    }
    base.update(overrides)
    return base


def _schedule_live_game(game_pk):
    """A scheduled game that is explicitly NOT final."""
    from datetime import datetime

    from models.scheduled_game import ScheduledGame
    from tests.game_driven_fixtures import AWAY_TEAM, HOME_TEAM

    for team_id, opponent_id, side in (
        (HOME_TEAM, AWAY_TEAM, 'home'),
        (AWAY_TEAM, HOME_TEAM, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id,
            game_pk=game_pk,
            game_date=REFERENCE,
            game_datetime=datetime(
                REFERENCE.year, REFERENCE.month, REFERENCE.day, 19, 5,
            ),
            opponent_team_id=opponent_id,
            home_away=side,
            game_type='R',
            status_code='I',
            status_state=ScheduledGame.STATE_SCHEDULED,
        ))
    db.session.commit()


def _install(monkeypatch, boxscores):
    client = BoxscoreClient(boxscores)
    monkeypatch.setattr(sync_service, 'mlb_client', client)
    return client


def _seed(monkeypatch, *, extra_game=False, **stat_overrides):
    """Create a game whose canonical rows already match the official line."""
    _schedule(GAME_PK)
    _pitcher(PITCHER_ID)
    boxscores = {
        GAME_PK: boxscore([
            (PITCHER_ID, 'home', pitching_stats(**stat_overrides)),
        ]),
    }
    if extra_game:
        _schedule(OTHER_GAME_PK)
        _pitcher(OTHER_PITCHER_ID)
        boxscores[OTHER_GAME_PK] = boxscore([
            (OTHER_PITCHER_ID, 'home', pitching_stats()),
        ])
    _install(monkeypatch, boxscores)

    # Seed canonical state through the canonical writer, so the qualification
    # afterwards genuinely faces an already-matching game.
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    return boxscores


def qualify(game_pk=GAME_PK, *, ctx=None):
    """Run the qualification's two-phase sequence through the canonical lane."""
    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[game_pk],
    )
    rows = qualification.plan_rows(shadow)
    fingerprint = shadow.get('reconciliation_plan_fingerprint')
    before = qualification.read_canonical_state(rows)

    write = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[game_pk],
        expected_plan_fingerprint=fingerprint,
    )
    after = qualification.read_canonical_state(
        qualification.plan_rows(write) or rows
    )
    proof = realization_service.build_daily_realization(write)
    decision = qualification.assess(
        context=ctx or context(game_pk),
        game_pk=game_pk,
        shadow_report=shadow,
        write_report=write,
        before_state=before,
        after_state=after,
        realization=proof,
    )
    return {
        'shadow': shadow, 'write': write, 'before': before, 'after': after,
        'realization': proof, 'decision': decision,
    }


# ── The core proof ──────────────────────────────────────────────────────────


def test_an_already_matching_one_game_plan_passes(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()

        decision = result['decision']
        assert decision['result'] == qualification.RESULT_PASS, (
            decision['failed_reasons'], decision['unproven_reasons']
        )
        assert decision['exit_code'] == 0


def test_the_write_phase_really_entered_the_write_capable_path(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        effects = result['write']['execution_effects']
        assert effects['writes_enabled'] is True
        assert result['write']['status'] == 'complete'


def test_publication_authority_stays_false_throughout(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        assert result['write']['execution_effects'][
            'publication_authoritative'
        ] is False


@pytest.mark.parametrize('field', qualification.BASEBALL_DATA_EFFECT_FIELDS)
def test_no_baseball_row_is_written(app, monkeypatch, field):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        assert result['write']['execution_effects'][field] == 0


def test_the_lane_completion_ledger_does_advance(app, monkeypatch):
    """Measured, not assumed. This is why PASS cannot require it to be zero.

    ``_process_one_game`` claims a work item before fetching and completes it
    after persisting, whenever writes are enabled — independently of whether the
    plan mutates anything. Pinning it here means a future change that made it
    conditional would show up as a failing test rather than as a silent shift in
    what "no-op" means.
    """
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        effects = result['write']['execution_effects']
        assert effects['work_items_updated'] == 1
        assert effects['work_items_completed'] == 1
        assert effects['checkpoints_advanced'] == 1
        assert effects['commits_performed'] >= 1


def test_the_canonical_state_is_identical_before_and_after(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        assert result['before']['available'] is True
        assert result['after']['available'] is True
        assert result['before']['digest'] == result['after']['digest']
        assert result['decision']['state_digest_match'] is True


def test_realization_reports_every_row_already_matching(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        proof = result['realization']
        assert proof['already_matching_rows'] >= 1
        assert proof['divergent_rows'] == 0
        assert proof['missing_rows'] == 0
        assert proof['duplicate_rows'] == 0
        assert proof['unresolved_rows'] == 0
        assert proof['all_projected_targets_realized'] is True


def test_every_planned_row_is_unchanged(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        governance = qualification.evaluate_plan_governance(result['write'])
        assert governance['planned_row_count'] >= 1
        assert governance['all_rows_already_matching'] is True
        assert governance['prohibited_actions'] == 0
        assert governance['planned_action_counts'] == {
            reconciliation.ACTION_UNCHANGED: governance['planned_row_count']
        }


def test_the_reviewed_fingerprint_authorized_the_write(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        assert result['decision']['plan_fingerprint_match'] is True
        assert result['write']['authorized_plan_fingerprint'] == (
            result['shadow']['reconciliation_plan_fingerprint']
        )


def test_the_source_revision_did_not_move(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        result = qualify()
        assert result['decision']['source_revision_match'] is True


# ── Exact scope ─────────────────────────────────────────────────────────────


def test_exactly_one_game_is_planned_fetched_and_completed(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch, extra_game=True)
        result = qualify()
        scope = result['decision']['scope']
        assert scope['planned_game_pks'] == [GAME_PK]
        assert scope['planned_game_count'] == 1
        assert scope['distinct_games_fetched'] == 1
        assert scope['games_attempted'] == 1
        assert scope['games_completed'] == 1
        assert scope['execution_scope_exact_match'] is True


def test_no_unrelated_row_is_touched(app, monkeypatch):
    """A second game's canonical rows must be byte-identical afterwards."""
    with app.app_context():
        _seed(monkeypatch, extra_game=True)

        def snapshot():
            return sorted(
                (
                    log.mlb_game_pk,
                    log.pitcher_id,
                    reconciliation.stored_state_digest(
                        log, qualification.STATE_DIGEST_FIELDS,
                    ),
                )
                for log in GameLog.query.filter(
                    GameLog.mlb_game_pk == OTHER_GAME_PK
                ).all()
            )

        before = snapshot()
        assert before, 'the unrelated game must actually have rows'
        qualify()
        db.session.expire_all()
        assert snapshot() == before


def test_the_unrelated_games_work_item_is_not_advanced(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch, extra_game=True)
        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=OTHER_GAME_PK
        ).first()
        before = (item.attempt_count, item.completed_at) if item else None

        qualify()
        db.session.expire_all()

        item = GameIngestionWorkItem.query.filter_by(
            mlb_game_pk=OTHER_GAME_PK
        ).first()
        after = (item.attempt_count, item.completed_at) if item else None
        assert after == before


# ── Refusals against the real lane ──────────────────────────────────────────


def test_a_changed_official_line_makes_the_plan_mutating_and_refuses(
    app, monkeypatch,
):
    """The shadow phase sees real work, so the qualification must refuse."""
    with app.app_context():
        _seed(monkeypatch)
        # The official line now disagrees with stored canonical state.
        _install(monkeypatch, {
            GAME_PK: boxscore([
                (PITCHER_ID, 'home', pitching_stats(strikeouts=9)),
            ]),
        })

        shadow = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
        )
        governance = qualification.evaluate_plan_governance(shadow)
        assert governance['all_rows_already_matching'] is False

        decision = qualification.assess(
            context=context(),
            game_pk=GAME_PK,
            shadow_report=shadow,
            write_report={},
            before_state=None,
            after_state=None,
            realization=None,
        )
        assert decision['result'] == qualification.RESULT_FAILED
        assert qualification.FAILED_PLAN_PROPOSES_MUTATION in (
            decision['failed_reasons']
        )


def test_a_mutating_plan_never_reaches_the_writer(app, monkeypatch):
    """Refusal happens before the write phase, so nothing is written at all."""
    with app.app_context():
        _seed(monkeypatch)
        _install(monkeypatch, {
            GAME_PK: boxscore([
                (PITCHER_ID, 'home', pitching_stats(strikeouts=9)),
            ]),
        })

        stored = GameLog.query.filter_by(mlb_game_pk=GAME_PK).first()
        before_digest = reconciliation.stored_state_digest(
            stored, qualification.STATE_DIGEST_FIELDS,
        )

        shadow = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
        )
        governance = qualification.evaluate_plan_governance(shadow)
        # The qualification refuses here; the write phase is not entered.
        assert governance['all_rows_already_matching'] is False

        db.session.expire_all()
        stored = GameLog.query.filter_by(mlb_game_pk=GAME_PK).first()
        assert reconciliation.stored_state_digest(
            stored, qualification.STATE_DIGEST_FIELDS,
        ) == before_digest


def test_a_stale_fingerprint_refuses_before_any_mutation(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        stored = GameLog.query.filter_by(mlb_game_pk=GAME_PK).first()
        before_digest = reconciliation.stored_state_digest(
            stored, qualification.STATE_DIGEST_FIELDS,
        )

        write = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[GAME_PK],
            expected_plan_fingerprint='0' * 64,
        )
        assert write['status'] == lane.STATUS_PLAN_FINGERPRINT_MISMATCH

        decision = qualification.assess(
            context=context(), game_pk=GAME_PK,
            shadow_report=lane.run_game_driven_ingestion(
                REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
            ),
            write_report=write,
            before_state=None, after_state=None, realization=None,
        )
        assert qualification.FAILED_PLAN_FINGERPRINT_CHANGED in (
            decision['failed_reasons']
        )

        db.session.expire_all()
        stored = GameLog.query.filter_by(mlb_game_pk=GAME_PK).first()
        assert reconciliation.stored_state_digest(
            stored, qualification.STATE_DIGEST_FIELDS,
        ) == before_digest


def test_an_unknown_game_cannot_be_planned_and_refuses(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        missing = 999999
        shadow = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[missing],
        )
        decision = qualification.assess(
            context=context(missing), game_pk=missing,
            shadow_report=shadow, write_report={},
            before_state=None, after_state=None, realization=None,
        )
        assert decision['result'] == qualification.RESULT_FAILED
        assert qualification.FAILED_GAME_NOT_PLANNABLE in (
            decision['failed_reasons']
        )


def test_a_non_final_game_is_excluded_by_the_canonical_planner(
    app, monkeypatch,
):
    with app.app_context():
        _seed(monkeypatch)
        live = 951099
        _schedule_live_game(live)
        shadow = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[live],
        )
        assert shadow['planned_game_pks'] == []
        decision = qualification.assess(
            context=context(live), game_pk=live,
            shadow_report=shadow, write_report={},
            before_state=None, after_state=None, realization=None,
        )
        assert qualification.FAILED_GAME_NOT_PLANNABLE in (
            decision['failed_reasons']
        )


# ── Readback honesty ────────────────────────────────────────────────────────


def test_the_readback_reads_real_canonical_rows(app, monkeypatch):
    with app.app_context():
        _seed(monkeypatch)
        shadow = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
        )
        state = qualification.read_canonical_state(
            qualification.plan_rows(shadow)
        )
        assert state['available'] is True
        assert state['row_count'] >= 1
        assert state['identity_count'] >= 1


def test_the_digest_moves_when_canonical_state_actually_moves(
    app, monkeypatch,
):
    """Otherwise a matching digest would prove nothing."""
    with app.app_context():
        _seed(monkeypatch)
        shadow = lane.run_game_driven_ingestion(
            REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
        )
        rows = qualification.plan_rows(shadow)
        before = qualification.read_canonical_state(rows)

        stored = GameLog.query.filter_by(mlb_game_pk=GAME_PK).first()
        stored.strikeouts = (stored.strikeouts or 0) + 5
        db.session.commit()

        after = qualification.read_canonical_state(rows)
        assert after['digest'] != before['digest']


def test_a_readback_with_no_rows_is_unavailable_not_a_silent_match(app):
    with app.app_context():
        assert qualification.read_canonical_state([]) is None
