"""The real-mutation qualification, executed against the canonical lane.

These tests drive the real planner, the real comparator, the real writer and the
real work-item ledger through a real database. Nothing here stands in for
reconciliation: an official box score changes by exactly one statistic, and the
canonical path decides what that means.

The point is that the contract is proven against behaviour the production lane
actually has, not against a fixture that agrees with the contract by
construction.
"""

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import game_driven_ingestion as lane
from services import game_driven_realization as realization_service
from services import game_log_reconciliation as reconciliation
from services import real_mutation_qualification as qualification
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


GAME_PK = 952001
OTHER_GAME_PK = 952002
PITCHER_ID = 6701
SECOND_PITCHER_ID = 6702
SHA = 'd' * 40


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
        'confirmation': f'QUALIFY_REAL_MUTATION_GAME_{game_pk}',
    }
    base.update(overrides)
    return base


def _install(monkeypatch, boxscores):
    monkeypatch.setattr(sync_service, 'mlb_client', BoxscoreClient(boxscores))


def _lines(*, strikeouts=2, second=True, **overrides):
    lines = [(PITCHER_ID, 'home', pitching_stats(
        strikeouts=strikeouts, **overrides,
    ))]
    if second:
        lines.append((SECOND_PITCHER_ID, 'away', pitching_stats()))
    return lines


def _seed(monkeypatch, *, strikeouts=2, second=True, **overrides):
    """Write canonical state through the canonical writer, then return."""
    _schedule(GAME_PK)
    _pitcher(PITCHER_ID)
    if second:
        _pitcher(SECOND_PITCHER_ID)
    _install(monkeypatch, {
        GAME_PK: boxscore(_lines(
            strikeouts=strikeouts, second=second, **overrides,
        )),
    })
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()


def _revise(monkeypatch, *, strikeouts, second=True, **overrides):
    """Publish a revised official line — the real parity difference."""
    _install(monkeypatch, {
        GAME_PK: boxscore(_lines(
            strikeouts=strikeouts, second=second, **overrides,
        )),
    })


GUARD_OK = {'acquired': True, 'release_attempted': True, 'released': True}


def qualify(game_pk=GAME_PK, *, ctx=None, reviewed_fingerprint=None):
    """Run the qualification's two-phase sequence through the canonical lane."""
    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[game_pk],
    )
    candidate = qualification.evaluate_candidate_plan(shadow, game_pk=game_pk)
    fingerprint = shadow.get('reconciliation_plan_fingerprint')
    reviewed = candidate.get('reviewed_mutation')

    before = after = realized = None
    if reviewed:
        before = qualification.read_target_row_state(
            game_pk=game_pk,
            pitcher_mlb_id=reviewed['pitcher_mlb_id'],
            reviewed_field=reviewed['field'],
        )
    bookkeeping_before = qualification.read_lane_bookkeeping(game_pk)

    write = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[game_pk],
        expected_plan_fingerprint=fingerprint,
    )
    db.session.expire_all()

    if reviewed:
        after = qualification.read_target_row_state(
            game_pk=game_pk,
            pitcher_mlb_id=reviewed['pitcher_mlb_id'],
            reviewed_field=reviewed['field'],
        )
        realized = qualification.realized_target_digest(
            game_pk=game_pk,
            pitcher_mlb_id=reviewed['pitcher_mlb_id'],
            target_fields=reviewed['target_fields'],
        )
    bookkeeping_after = qualification.read_lane_bookkeeping(game_pk)
    proof = realization_service.build_daily_realization(write)

    decision = qualification.assess(
        context=ctx or context(game_pk),
        game_pk=game_pk,
        reviewed_fingerprint=reviewed_fingerprint or fingerprint,
        shadow_report=shadow,
        write_report=write,
        before_state=before,
        after_state=after,
        realized_digest=realized,
        realization=proof,
        bookkeeping_before=bookkeeping_before,
        bookkeeping_after=bookkeeping_after,
        writer_guard=dict(GUARD_OK),
    )
    return {
        'shadow': shadow,
        'write': write,
        'candidate': candidate,
        'decision': decision,
        'before': before,
        'after': after,
        'realized': realized,
        'bookkeeping_before': bookkeeping_before,
        'bookkeeping_after': bookkeeping_after,
    }


def _stored(field, game_pk=GAME_PK, mlb_id=PITCHER_ID):
    pitcher = Pitcher.query.filter_by(mlb_id=mlb_id).one()
    row = GameLog.query.filter_by(
        mlb_game_pk=game_pk, pitcher_id=pitcher.id,
    ).one()
    return getattr(row, field)


# ── The happy path ──────────────────────────────────────────────────────────


def test_one_field_correction_passes(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()

    assert result['decision']['failed_reasons'] == []
    assert result['decision']['unproven_reasons'] == []
    assert result['decision']['result'] == qualification.RESULT_PASS


def test_the_shadow_plan_is_exactly_one_statistical_correction(
    app, monkeypatch,
):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(shadow, game_pk=GAME_PK)

    assert candidate['is_valid_candidate'] is True
    assert candidate['planned_update_row_count'] == 1
    reviewed = candidate['reviewed_mutation']
    assert reviewed['field'] == 'strikeouts'
    assert reviewed['pitcher_mlb_id'] == PITCHER_ID
    assert reviewed['game_pk'] == GAME_PK
    assert candidate['field_authority']['authority_resolved'] is True


def test_the_stored_value_actually_changes(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    assert _stored('strikeouts') == 2

    _revise(monkeypatch, strikeouts=3)
    result = qualify()

    assert result['decision']['result'] == qualification.RESULT_PASS
    assert _stored('strikeouts') == 3
    assert result['before']['reviewed_field_value'] == 2
    assert result['after']['reviewed_field_value'] == 3


def test_exactly_one_game_log_row_is_written(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    effects = result['write']['execution_effects']

    assert effects['game_log_rows_written'] == 1
    assert effects['pitcher_rows_written'] == 0
    assert effects['appearance_team_rows_written'] == 0
    # Measured: the correction stamps provenance on the row it corrects.
    assert effects['correction_provenance_rows_written'] == 1
    assert effects['dead_letters_created'] == 0
    assert {
        field: effects[field]
        for field in qualification.EXPECTED_BASEBALL_DATA_EFFECTS
    } == qualification.EXPECTED_BASEBALL_DATA_EFFECTS


def test_the_target_reaches_the_canonical_value(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    integrity = result['decision']['integrity']

    assert integrity['target_reached_canonical_value'] is True
    assert integrity['expected_target_state_digest'] == (
        integrity['observed_target_state_digest']
    )


def test_unreviewed_fields_on_the_target_row_do_not_move(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    integrity = result['decision']['integrity']

    assert integrity['target_unreviewed_fields_unchanged'] is True
    assert result['before']['target_unreviewed_digest'] == (
        result['after']['target_unreviewed_digest']
    )
    # The whole row legitimately differs; that is the point of this stage.
    assert result['before']['target_row_digest'] != (
        result['after']['target_row_digest']
    )


def test_other_rows_in_the_same_game_do_not_move(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()

    assert result['decision']['integrity']['other_rows_unchanged'] is True
    assert result['before']['other_rows_digest'] == (
        result['after']['other_rows_digest']
    )
    assert _stored('strikeouts', mlb_id=SECOND_PITCHER_ID) == 2


def test_publication_authority_stays_false(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    effects = result['write']['execution_effects']

    assert effects['writes_enabled'] is True
    assert effects['publication_authoritative'] is False


def test_realization_positively_reports_the_correction(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    proof = realization_service.build_daily_realization(result['write'])

    assert proof['all_projected_targets_realized'] is True
    assert proof['divergent_rows'] == 0
    assert proof['missing_rows'] == 0
    assert proof['duplicate_rows'] == 0
    assert proof['unresolved_rows'] == 0


# ── Lane bookkeeping ────────────────────────────────────────────────────────


def test_the_work_item_stays_completed_and_records_the_correction(
    app, monkeypatch,
):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    before = result['bookkeeping_before']['target']
    after = result['bookkeeping_after']['target']

    assert before['status'] == GameIngestionWorkItem.STATUS_COMPLETED
    assert after['status'] == GameIngestionWorkItem.STATUS_COMPLETED
    assert after['correction_count'] - before['correction_count'] == 1
    assert after['attempt_count'] - before['attempt_count'] == 1


def test_the_measured_ledger_delta_matches_the_pinned_contract(
    app, monkeypatch,
):
    """The expected delta is measured through the canonical path, not assumed."""
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    effects = result['write']['execution_effects']

    observed = {
        field: effects[field]
        for field in qualification.EXPECTED_LANE_BOOKKEEPING_DELTA
    }
    assert observed == qualification.EXPECTED_LANE_BOOKKEEPING_DELTA


def test_every_moved_work_item_field_is_inside_the_permitted_set(
    app, monkeypatch,
):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    changed = set(
        result['decision']['lane_bookkeeping'][
            'lane_bookkeeping_changed_fields'
        ]
    )

    assert changed <= qualification.BOOKKEEPING_ALLOWED_CHANGED_FIELDS
    assert result['decision']['lane_bookkeeping'][
        'lane_bookkeeping_unexpected_changed_fields'
    ] == []


def test_unrelated_work_items_do_not_move(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _schedule(OTHER_GAME_PK)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    ledger = result['decision']['lane_bookkeeping']

    assert ledger['unrelated_bookkeeping_unchanged'] is True
    assert ledger['unrelated_work_items_digest_before'] == (
        ledger['unrelated_work_items_digest_after']
    )
    assert ledger['unrelated_checkpoints_digest_before'] == (
        ledger['unrelated_checkpoints_digest_after']
    )


# ── Preconditions ───────────────────────────────────────────────────────────


def test_a_game_with_no_work_item_has_no_durable_target(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)

    bookkeeping = qualification.read_lane_bookkeeping(OTHER_GAME_PK)

    assert bookkeeping is not None
    assert bookkeeping['target_present'] is False


def test_a_pending_work_item_is_not_a_completed_target(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=GAME_PK).one()
    item.status = GameIngestionWorkItem.STATUS_PLANNED
    db.session.commit()

    bookkeeping = qualification.read_lane_bookkeeping(GAME_PK)

    assert bookkeeping['target_present'] is True
    assert bookkeeping['target']['status'] != (
        qualification.REQUIRED_WORK_ITEM_STATUS_BEFORE
    )


def test_a_non_final_game_is_not_plannable(app, monkeypatch):
    from datetime import datetime

    from models.scheduled_game import ScheduledGame
    from tests.game_driven_fixtures import AWAY_TEAM, HOME_TEAM

    for team_id, opponent_id, side in (
        (HOME_TEAM, AWAY_TEAM, 'home'),
        (AWAY_TEAM, HOME_TEAM, 'away'),
    ):
        db.session.add(ScheduledGame(
            team_id=team_id,
            game_pk=OTHER_GAME_PK,
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
    _install(monkeypatch, {})

    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[OTHER_GAME_PK],
    )
    scope = qualification.evaluate_scope(shadow, game_pk=OTHER_GAME_PK)

    assert scope['planned_game_count'] == 0


# ── Drift ───────────────────────────────────────────────────────────────────


def test_a_stale_fingerprint_refuses_before_the_first_mutation(
    app, monkeypatch,
):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    write = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[GAME_PK],
        expected_plan_fingerprint='0' * 64,
    )

    assert write['status'] == lane.STATUS_PLAN_FINGERPRINT_MISMATCH
    assert write['execution_effects']['game_log_rows_written'] == 0
    assert write['execution_effects']['commits_performed'] == 0
    assert _stored('strikeouts') == 2


def test_an_exclusive_write_without_a_fingerprint_refuses(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    write = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_WRITE, only_game_pks=[GAME_PK],
    )

    assert write['status'] == lane.STATUS_PLAN_AUTHORIZATION_REQUIRED
    assert write['execution_effects']['game_log_rows_written'] == 0
    assert _stored('strikeouts') == 2


def test_a_plan_the_operator_did_not_review_fails_the_assessment(
    app, monkeypatch,
):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify(reviewed_fingerprint='1' * 64)

    assert qualification.FAILED_REVIEWED_FINGERPRINT_MISMATCH in (
        result['decision']['failed_reasons']
    )
    assert result['decision']['result'] == qualification.RESULT_FAILED


# ── Refused candidate shapes, through the real planner ──────────────────────


def test_a_two_field_revision_is_refused_as_a_candidate(app, monkeypatch):
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3, hits=4)

    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(shadow, game_pk=GAME_PK)

    assert candidate['is_valid_candidate'] is False
    assert qualification.FAILED_PLAN_MULTI_FIELD_MUTATION in (
        candidate['failed_reasons']
    )


def test_an_inherited_runners_revision_is_refused_as_a_candidate(
    app, monkeypatch,
):
    """The historical 824969 design case, encoded as a negative example.

    The lane correctly plans the correction; the qualification refuses it,
    because `inherited_runners` field authority is recorded UNRESOLVED.
    """
    _schedule(GAME_PK)
    _pitcher(PITCHER_ID)
    seeded = pitching_stats()
    seeded['inheritedRunners'] = 1
    _install(monkeypatch, {
        GAME_PK: boxscore([(PITCHER_ID, 'home', seeded)]),
    })
    lane.run_game_driven_ingestion(REFERENCE, mode=lane.MODE_WRITE)
    db.session.expire_all()

    revised = pitching_stats()
    revised['inheritedRunners'] = 2
    _install(monkeypatch, {
        GAME_PK: boxscore([(PITCHER_ID, 'home', revised)]),
    })

    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(shadow, game_pk=GAME_PK)

    assert candidate['mutation_present'] is True
    assert candidate['reviewed_mutation']['field'] == 'inherited_runners'
    assert candidate['is_valid_candidate'] is False
    assert qualification.FAILED_FIELD_AUTHORITY_UNRESOLVED in (
        candidate['failed_reasons']
    )
    # And nothing was written by the refusal.
    assert _stored('inherited_runners') == 1


def test_a_missing_appearance_row_plans_an_insert_and_is_refused(
    app, monkeypatch,
):
    _seed(monkeypatch, strikeouts=2, second=False)
    _pitcher(SECOND_PITCHER_ID)
    _install(monkeypatch, {
        GAME_PK: boxscore(_lines(strikeouts=2, second=True)),
    })

    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(shadow, game_pk=GAME_PK)

    assert candidate['is_valid_candidate'] is False
    assert qualification.FAILED_PLAN_PROPOSES_INSERT in (
        candidate['failed_reasons']
    )


def test_the_qualification_never_writes_a_refused_candidate(app, monkeypatch):
    """A refused candidate must not reach the writer at all."""
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3, hits=4)

    shadow = lane.run_game_driven_ingestion(
        REFERENCE, mode=lane.MODE_SHADOW, only_game_pks=[GAME_PK],
    )
    candidate = qualification.evaluate_candidate_plan(shadow, game_pk=GAME_PK)

    assert candidate['is_valid_candidate'] is False
    # The runner raises its preflight refusal here; nothing was written.
    assert _stored('strikeouts') == 2
    assert _stored('hits_allowed') == 1
    assert shadow['execution_effects']['game_log_rows_written'] == 0


# ── The reviewed plan is the canonical plan ─────────────────────────────────


def test_the_reviewed_digest_comes_from_the_canonical_encoder(
    app, monkeypatch,
):
    """The realization proof and the qualification agree by construction."""
    _seed(monkeypatch, strikeouts=2)
    _revise(monkeypatch, strikeouts=3)

    result = qualify()
    reviewed = result['decision']['reviewed_mutation']

    pitcher = Pitcher.query.filter_by(mlb_id=PITCHER_ID).one()
    row = GameLog.query.filter_by(
        mlb_game_pk=GAME_PK, pitcher_id=pitcher.id,
    ).one()
    assert reconciliation.stored_state_digest(
        row, reviewed['target_fields'],
    ) == reviewed['target_state_digest']
