"""Foundation 3C — shadow/write reconciliation parity.

A controlled production Stage C run exposed the defect these tests exist to
prevent: shadow projected 38 unchanged rows across five games, and the writer
then applied 14 updates to those same rows. Shadow owned an eight-field
comparator; the canonical writer reconciled a much broader governed record and
additionally reconciled team-at-appearance authority. Two authorities, one of
which was wrong.

There is now one canonical planner. These tests assert that shadow and write
reach byte-identical decisions from the same database state and the same
official evidence, and that shadow writes nothing while proving it.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from services import appearance_team_authority
from services import game_driven_ingestion
from services import game_log_reconciliation as reconciliation
from services import sync as sync_service
from tests.game_driven_fixtures import (
    AWAY_TEAM,
    BoxscoreClient,
    HOME_TEAM,
    REFERENCE,
    boxscore,
    final_game,
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


def _stored_row(pitcher_row, game_pk, **overrides):
    values = {
        'pitcher_id': pitcher_row.id,
        'mlb_game_pk': game_pk,
        'game_date': REFERENCE,
        'game_type': 'R',
        'opponent': 'Away Club',
        'opponent_abbreviation': 'AWY',
        'games_started': 0,
        'innings_pitched': 1.0,
        'innings_pitched_outs': 3,
        'pitches_thrown': 15,
        'strikes': 10,
        'hits_allowed': 1,
        'runs_allowed': 0,
        'earned_runs': 0,
        'walks': 0,
        'strikeouts': 2,
        'home_runs_allowed': 0,
        'batters_faced': 4,
        'appearance_team_id': HOME_TEAM,
        'appearance_team_source': appearance_team_authority.SOURCE_BOXSCORE,
        'appearance_team_status': GameLog.APPEARANCE_TEAM_RESOLVED,
        'appearance_team_reason': (
            appearance_team_authority.REASON_RESOLVED_BOXSCORE
        ),
        'stat_correction_count': 0,
    }
    values.update(overrides)
    row = GameLog(**values)
    db.session.add(row)
    return row


def _plan_game(game_pk):
    """The canonical plan, read-only, exactly as shadow obtains it."""
    result = sync_service.process_completed_game_for_postgame_refresh(
        final_game(game_pk), schedule_date=REFERENCE, plan_only=True,
    )
    return result['reconciliation_plan'], result['reconciliation_summary']


def _write_game(game_pk):
    result = sync_service.process_completed_game_for_postgame_refresh(
        final_game(game_pk), schedule_date=REFERENCE, force=True,
    )
    db.session.commit()
    return result['reconciliation_plan'], result['reconciliation_summary']


def _parity_view(plan):
    """The comparable decision: action, key, changed fields, categories."""
    return sorted(
        (
            entry['game_pk'],
            entry['pitcher_mlb_id'],
            entry['action'],
            tuple(entry['changed_fields']),
            tuple(entry['mutation_categories']),
            entry.get('blocked_reason'),
        )
        for entry in plan
    )


def _fingerprint_all_tables():
    """Row counts plus a content digest for every table shadow must not touch."""
    return {
        'game_logs': [
            (
                row.id, row.pitcher_id, row.mlb_game_pk, row.innings_pitched_outs,
                row.earned_runs, row.runs_allowed, row.hits_allowed, row.walks,
                row.strikeouts, row.home_runs_allowed, row.batters_faced,
                row.strikes, row.pitches_thrown, row.games_started,
                row.opponent, row.opponent_abbreviation, row.game_date,
                row.game_type, row.appearance_team_id, row.appearance_team_source,
                row.appearance_team_status, row.appearance_team_reason,
                row.stat_correction_count, row.last_stat_correction_at,
                row.last_stat_correction_source,
                row.last_stat_correction_sync_run_id,
            )
            for row in GameLog.query.order_by(GameLog.id).all()
        ],
        'pitchers': [
            (
                row.id, row.mlb_id, row.full_name, row.team_id, row.team_name,
                row.team_abbreviation, row.position, row.active,
                row.roster_status, row.roster_status_source,
                row.roster_status_updated_at, row.team_assignment_status,
                row.team_assignment_source, row.team_assignment_updated_at,
            )
            for row in Pitcher.query.order_by(Pitcher.id).all()
        ],
        'game_ingestion_work_items': [
            row.to_dict()
            for row in GameIngestionWorkItem.query.order_by(
                GameIngestionWorkItem.id
            ).all()
        ],
        'postgame_processed_games': [
            row.to_dict()
            for row in PostgameProcessedGame.query.order_by(
                PostgameProcessedGame.id
            ).all()
        ],
        'scheduled_games': [
            row.to_dict()
            for row in ScheduledGame.query.order_by(ScheduledGame.id).all()
        ],
    }


# ═══════════════ 1. Reproduction of the production defect ═══════════════════


def test_a_row_differing_only_outside_the_old_comparator_is_now_projected(
    app, monkeypatch,
):
    """The exact class of discrepancy that produced 14 unprojected updates.

    Every field the retired eight-field comparator inspected matches. Fields it
    never inspected — strikes, pitches, batters faced, opponent metadata — do
    not. The old shadow called this unchanged; the writer corrected it.
    """
    with app.app_context():
        _schedule(940001)
        arm = _pitcher(6001)
        db.session.flush()
        _stored_row(
            arm, 940001,
            strikes=8,                      # differs
            pitches_thrown=12,              # differs
            batters_faced=3,                # differs
            opponent_abbreviation='OLD',    # differs
            # Every field the retired comparator looked at is identical:
            innings_pitched_outs=3, earned_runs=0, runs_allowed=0,
            hits_allowed=1, walks=0, strikeouts=2, home_runs_allowed=0,
            games_started=0,
        )
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940001: boxscore([
                (6001, 'home', pitching_stats()),
            ])}),
        )

        plan, summary = _plan_game(940001)

        assert summary['rows_updated'] == 1
        assert summary['rows_unchanged'] == 0
        changed = set(plan[0]['changed_fields'])
        assert {'strikes', 'pitches_thrown', 'batters_faced'} <= changed
        assert plan[0]['action'] == reconciliation.ACTION_UPDATE

        # And the writer, from the identical state, does exactly that.
        write_plan, write_summary = _write_game(940001)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert write_summary['rows_updated'] == 1


def test_the_retired_comparator_field_list_no_longer_exists(app):
    """Structural guard: shadow may not regrow an independent field list."""
    assert not hasattr(game_driven_ingestion, '_PROJECTION_FIELDS')
    assert not hasattr(game_driven_ingestion, '_row_differs')
    assert not hasattr(game_driven_ingestion, '_project_reconciliation')


# ═══════════════ 2. Row-level parity across every action ════════════════════


def test_an_exactly_unchanged_row_is_unchanged_in_both_modes(app, monkeypatch):
    with app.app_context():
        _schedule(940002)
        arm = _pitcher(6002)
        db.session.flush()
        _stored_row(arm, 940002)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940002: boxscore([(6002, 'home', pitching_stats())])}),
        )

        plan, summary = _plan_game(940002)
        assert summary['rows_unchanged'] == 1
        assert summary['rows_updated'] == 0

        write_plan, write_summary = _write_game(940002)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert write_summary['rows_unchanged'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=940002).one().stat_correction_count == 0


def test_a_new_row_is_an_insert_in_both_modes(app, monkeypatch):
    with app.app_context():
        _schedule(940003)
        _pitcher(6003)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940003: boxscore([(6003, 'home', pitching_stats())])}),
        )

        plan, summary = _plan_game(940003)
        assert summary['rows_inserted'] == 1
        assert plan[0]['natural_key']['mlb_game_pk'] == 940003

        write_plan, write_summary = _write_game(940003)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert write_summary['rows_inserted'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=940003).count() == 1


@pytest.mark.parametrize('override,expected_field', [
    ({'earned_runs': 3}, 'earned_runs'),
    ({'runs': 5}, 'runs_allowed'),
    ({'hits': 7}, 'hits_allowed'),
    ({'walks': 4}, 'walks'),
    ({'strikeouts': 9}, 'strikeouts'),
    ({'home_runs': 2}, 'home_runs_allowed'),
    ({'batters_faced': 11}, 'batters_faced'),
    ({'pitches': 40}, 'pitches_thrown'),
    ({'innings': '2.1'}, 'innings_pitched_outs'),
    ({'strikes': 33}, 'strikes'),
])
def test_an_official_stat_correction_agrees_field_for_field(
    app, monkeypatch, override, expected_field,
):
    with app.app_context():
        game_pk = 940100 + abs(hash(expected_field)) % 800
        _schedule(game_pk)
        arm = _pitcher(6100 + abs(hash(expected_field)) % 800)
        db.session.flush()
        _stored_row(arm, game_pk)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({game_pk: boxscore([
                (arm.mlb_id, 'home', pitching_stats(**override)),
            ])}),
        )

        plan, summary = _plan_game(game_pk)
        assert summary['rows_updated'] == 1
        assert expected_field in plan[0]['changed_fields']
        assert plan[0]['is_statistical_correction'] is True
        assert reconciliation.CATEGORY_STATISTICAL_CORRECTION in (
            plan[0]['mutation_categories']
        )

        write_plan, _ = _write_game(game_pk)
        assert _parity_view(plan) == _parity_view(write_plan)

        row = GameLog.query.filter_by(mlb_game_pk=game_pk).one()
        assert row.stat_correction_count == 1
        assert row.last_stat_correction_source is not None


def test_a_role_signal_correction_is_its_own_category(app, monkeypatch):
    with app.app_context():
        _schedule(940004)
        arm = _pitcher(6004)
        db.session.flush()
        _stored_row(arm, 940004, games_started=0)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940004: boxscore([
                (6004, 'home', pitching_stats(games_started=1)),
            ])}),
        )

        plan, summary = _plan_game(940004)
        assert 'games_started' in plan[0]['changed_fields']
        assert reconciliation.CATEGORY_ROLE_SIGNAL in plan[0]['mutation_categories']

        write_plan, _ = _write_game(940004)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert GameLog.query.filter_by(mlb_game_pk=940004).one().games_started == 1


def test_game_metadata_reconciliation_is_its_own_category(app, monkeypatch):
    with app.app_context():
        _schedule(940005)
        arm = _pitcher(6005)
        db.session.flush()
        _stored_row(arm, 940005, opponent='Stale Name', opponent_abbreviation='STL')
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940005: boxscore([(6005, 'home', pitching_stats())])}),
        )

        plan, _ = _plan_game(940005)
        assert reconciliation.CATEGORY_GAME_METADATA in plan[0]['mutation_categories']
        assert 'opponent' in plan[0]['changed_fields']

        write_plan, _ = _write_game(940005)
        assert _parity_view(plan) == _parity_view(write_plan)


def test_appearance_team_authority_reconciliation_agrees(app, monkeypatch):
    """A legacy unattributed row is attributed only alongside a real correction."""
    with app.app_context():
        _schedule(940006)
        arm = _pitcher(6006)
        db.session.flush()
        _stored_row(
            arm, 940006,
            earned_runs=1,                      # forces a genuine correction
            appearance_team_id=None,
            appearance_team_source=None,
            appearance_team_status=None,
            appearance_team_reason=None,
        )
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940006: boxscore([(6006, 'home', pitching_stats())])}),
        )

        plan, _ = _plan_game(940006)
        assert reconciliation.CATEGORY_APPEARANCE_TEAM_AUTHORITY in (
            plan[0]['mutation_categories']
        )
        assert 'appearance_team_id' in plan[0]['changed_fields']
        assert plan[0]['appearance_team_reason'] is not None

        write_plan, _ = _write_game(940006)
        assert _parity_view(plan) == _parity_view(write_plan)
        row = GameLog.query.filter_by(mlb_game_pk=940006).one()
        assert row.appearance_team_id == HOME_TEAM
        assert row.appearance_team_status == GameLog.APPEARANCE_TEAM_RESOLVED


def test_multiple_changes_on_one_row_are_one_update(app, monkeypatch):
    with app.app_context():
        _schedule(940007)
        arm = _pitcher(6007)
        db.session.flush()
        _stored_row(arm, 940007, earned_runs=0, strikeouts=0, hits_allowed=0)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940007: boxscore([
                (6007, 'home', pitching_stats(earned_runs=2, strikeouts=6, hits=4)),
            ])}),
        )

        plan, summary = _plan_game(940007)
        assert summary['rows_updated'] == 1
        assert len(plan) == 1
        assert {'earned_runs', 'strikeouts', 'hits_allowed'} <= set(
            plan[0]['changed_fields']
        )
        assert plan[0]['changed_field_count'] == len(plan[0]['changed_fields'])

        write_plan, write_summary = _write_game(940007)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert write_summary['rows_updated'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=940007).one().stat_correction_count == 1


def test_an_unsafe_correction_is_blocked_in_both_modes(app, monkeypatch):
    with app.app_context():
        _schedule(940008)
        arm = _pitcher(6008)
        db.session.flush()
        _stored_row(arm, 940008)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940008: boxscore([
                (6008, 'home', pitching_stats(earned_runs=9, complete=False)),
            ])}),
        )

        plan, summary = _plan_game(940008)
        assert summary['rows_blocked'] == 1
        assert plan[0]['action'] == reconciliation.ACTION_BLOCKED
        assert plan[0]['governed_and_safe'] is False
        assert plan[0]['blocked_reason'] == reconciliation.BLOCKED_PARTIAL_SOURCE_LINE

        write_plan, write_summary = _write_game(940008)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert write_summary['rows_blocked'] == 1
        # The row was NOT mutated by a blocked correction.
        assert GameLog.query.filter_by(mlb_game_pk=940008).one().earned_runs == 0


def test_a_blocked_row_prevents_the_game_checkpoint_from_completing(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(940009)
        arm = _pitcher(6009)
        db.session.flush()
        _stored_row(arm, 940009)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940009: boxscore([
                (6009, 'home', pitching_stats(earned_runs=9, complete=False)),
            ])}),
        )

        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_WRITE,
        )

        assert report['games_completed'] == 0
        assert report['rows_blocked'] == 1
        item = GameIngestionWorkItem.query.filter_by(mlb_game_pk=940009).one()
        assert item.status != GameIngestionWorkItem.STATUS_COMPLETED
        assert item.completed_at is None


def test_an_unresolved_pitcher_identity_is_classified_identically(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(940010)
        db.session.commit()
        # A box-score line whose player identity conflicts with its person id
        # cannot be resolved by either mode.
        payload = boxscore([(6010, 'home', pitching_stats())])
        payload['teams']['home']['players']['ID6010']['person']['id'] = 99999
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient({940010: payload}),
        )

        plan, summary = _plan_game(940010)
        assert summary['rows_blocked'] == 1
        assert plan[0]['blocked_reason'] == 'pitcher_identity_unresolved'

        write_plan, write_summary = _write_game(940010)
        assert _parity_view(plan) == _parity_view(write_plan)
        assert write_summary['rows_blocked'] == 1
        assert GameLog.query.filter_by(mlb_game_pk=940010).count() == 0


# ═══════════════ 3. Shadow is read-only ═════════════════════════════════════


def test_shadow_changes_nothing_anywhere(app, monkeypatch):
    """Before/after fingerprints across every table shadow could touch."""
    with app.app_context():
        _schedule(940011)
        _schedule(940012)
        arm = _pitcher(6011)
        db.session.flush()
        _stored_row(arm, 940011, earned_runs=0)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({
                # An update, an insert for an unknown pitcher, and a new game.
                940011: boxscore([(6011, 'home', pitching_stats(earned_runs=4))]),
                940012: boxscore([(6099, 'home', pitching_stats())]),
            }),
        )

        before = _fingerprint_all_tables()
        report = game_driven_ingestion.run_game_driven_ingestion(
            REFERENCE, mode=game_driven_ingestion.MODE_SHADOW,
        )
        db.session.rollback()
        after = _fingerprint_all_tables()

        assert report['rows_updated'] >= 1
        assert report['rows_inserted'] >= 1
        for table in before:
            assert before[table] == after[table], table


def test_shadow_does_not_create_a_pitcher_it_would_have_created(app, monkeypatch):
    with app.app_context():
        _schedule(940013)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940013: boxscore([(6013, 'home', pitching_stats())])}),
        )

        plan, summary = _plan_game(940013)

        assert summary['rows_inserted'] == 1
        assert plan[0]['pitcher_identity_action'] == 'create'
        assert reconciliation.CATEGORY_PITCHER_IDENTITY in (
            plan[0]['mutation_categories']
        )
        assert Pitcher.query.filter_by(mlb_id=6013).count() == 0


def test_shadow_does_not_dead_letter_an_unresolved_line(app, monkeypatch):
    from models.sync_failure import SyncFailure

    with app.app_context():
        _schedule(940014)
        db.session.commit()
        payload = boxscore([(6014, 'home', pitching_stats())])
        payload['teams']['home']['players']['ID6014']['person']['id'] = 12345
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient({940014: payload}),
        )

        _plan_game(940014)
        db.session.rollback()

        assert SyncFailure.query.count() == 0


# ═══════════════ 4. Parity contract over a mixed fixture ════════════════════


def test_a_mixed_fixture_reaches_identical_shadow_and_write_decisions(
    app, monkeypatch,
):
    """Insert, update, unchanged, and blocked in one plan — byte-identical."""
    with app.app_context():
        _schedule(940020)
        unchanged_arm = _pitcher(6020)
        update_arm = _pitcher(6021)
        blocked_arm = _pitcher(6022)
        db.session.flush()
        _stored_row(unchanged_arm, 940020)
        _stored_row(update_arm, 940020, earned_runs=0)
        _stored_row(blocked_arm, 940020)
        db.session.commit()

        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940020: boxscore([
                (6020, 'home', pitching_stats()),
                (6021, 'home', pitching_stats(earned_runs=5)),
                (6022, 'home', pitching_stats(earned_runs=6, complete=False)),
                (6023, 'home', pitching_stats()),        # insert, unknown pitcher
            ])}),
        )

        plan, summary = _plan_game(940020)
        assert summary['rows_inserted'] == 1
        assert summary['rows_updated'] == 1
        assert summary['rows_unchanged'] == 1
        assert summary['rows_blocked'] == 1

        write_plan, write_summary = _write_game(940020)

        assert _parity_view(plan) == _parity_view(write_plan)
        assert summary['reconciliation_plan_fingerprint'] == (
            write_summary['reconciliation_plan_fingerprint']
        )
        for key in (
            'rows_inserted', 'rows_updated', 'rows_unchanged', 'rows_blocked',
            'changed_fields_counts', 'mutation_category_counts',
            'statistical_corrections', 'authority_reconciliations',
            'provenance_only_updates',
        ):
            assert summary[key] == write_summary[key], key


def test_the_five_game_production_discrepancy_class_is_now_projected(
    app, monkeypatch,
):
    """Regression fixture modelling the observed Stage C shape.

    Five games, 38 appearance rows, 14 of which differ only in fields the
    retired comparator never inspected. The repaired projection must predict
    all 14 updates BEFORE any write happens.
    """
    with app.app_context():
        game_pks = [940101, 940102, 940103, 940104, 940105]
        # 4, 2, 4, 2, 2 rows differing — the observed per-game update shape.
        differing_per_game = [4, 2, 4, 2, 2]
        rows_per_game = [9, 6, 9, 7, 7]
        assert sum(rows_per_game) == 38
        assert sum(differing_per_game) == 14

        boxscores = {}
        mlb_id = 6200
        for game_pk, total, differing in zip(
            game_pks, rows_per_game, differing_per_game,
        ):
            _schedule(game_pk)
            lines = []
            for index in range(total):
                arm = _pitcher(mlb_id)
                db.session.flush()
                if index < differing:
                    # Differs ONLY outside the retired eight-field comparator.
                    _stored_row(
                        arm, game_pk, strikes=7, pitches_thrown=11,
                        batters_faced=3,
                    )
                else:
                    _stored_row(arm, game_pk)
                lines.append((mlb_id, 'home', pitching_stats()))
                mlb_id += 1
            boxscores[game_pk] = boxscore(lines)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client', BoxscoreClient(boxscores),
        )

        projected_updates = projected_unchanged = 0
        plans = {}
        for game_pk in game_pks:
            plan, summary = _plan_game(game_pk)
            plans[game_pk] = plan
            projected_updates += summary['rows_updated']
            projected_unchanged += summary['rows_unchanged']

        assert projected_updates == 14
        assert projected_unchanged == 24

        applied_updates = applied_unchanged = 0
        for game_pk in game_pks:
            write_plan, write_summary = _write_game(game_pk)
            assert _parity_view(plans[game_pk]) == _parity_view(write_plan)
            applied_updates += write_summary['rows_updated']
            applied_unchanged += write_summary['rows_unchanged']

        assert applied_updates == projected_updates
        assert applied_unchanged == projected_unchanged


def test_a_post_write_replay_projects_everything_unchanged(app, monkeypatch):
    """Stage C4: after a controlled write, shadow must see nothing to do."""
    with app.app_context():
        _schedule(940030)
        arm = _pitcher(6030)
        db.session.flush()
        _stored_row(arm, 940030, earned_runs=0)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940030: boxscore([
                (6030, 'home', pitching_stats(earned_runs=3)),
            ])}),
        )

        _write_game(940030)
        plan, summary = _plan_game(940030)

        assert summary['rows_updated'] == 0
        assert summary['rows_inserted'] == 0
        assert summary['rows_unchanged'] == 1
        assert plan[0]['action'] == reconciliation.ACTION_UNCHANGED


# ═══════════════ 5. Classifier contract ═════════════════════════════════════


def test_every_governed_field_has_a_category():
    governed = (
        reconciliation.STATISTICAL_FIELDS
        + reconciliation.ROLE_SIGNAL_FIELDS
        + reconciliation.GAME_METADATA_FIELDS
        + reconciliation.APPEARANCE_TEAM_FIELDS
        + reconciliation.PROVENANCE_FIELDS
    )
    for field in governed:
        assert reconciliation.field_category(field) in reconciliation.CATEGORIES
        assert reconciliation.field_category(field) != (
            reconciliation.CATEGORY_BLOCKED
        )


def test_an_ungoverned_field_fails_closed():
    assert reconciliation.field_category('something_new') == (
        reconciliation.CATEGORY_BLOCKED
    )


def test_the_writer_cannot_correct_a_field_the_classifier_does_not_know(app):
    """Every field the canonical writer may touch must be categorizable."""
    with app.app_context():
        values = {
            field: 0 for field in
            reconciliation.STATISTICAL_FIELDS
            + reconciliation.ROLE_SIGNAL_FIELDS
            + reconciliation.GAME_METADATA_FIELDS
        }
        stats = {key: 1 for key in reconciliation.REQUIRED_CORRECTION_STAT_KEYS}
        stats.update({
            source for source, _ in ()
        } or {})
        for source_key, _field in reconciliation.OPTIONAL_BOOL_STAT_FIELDS:
            stats[source_key] = 1
        for _field, source_keys in reconciliation.OPTIONAL_INT_STAT_FIELDS:
            stats[source_keys[0]] = 1
        values['leverage_index'] = 1.0

        for field in reconciliation.correctable_fields(
            values, stats, include_leverage_index=True,
        ):
            assert reconciliation.field_category(field) != (
                reconciliation.CATEGORY_BLOCKED
            ), field


def test_provenance_is_a_separate_category_from_a_stat_correction():
    """Provenance columns are classified apart from baseball evidence.

    In the current canonical writer the provenance stamp only ever accompanies
    a real field correction, so a provenance-ONLY update is not reachable and
    its run-level count is legitimately zero. The category exists and is
    separable so a provenance-only mutation could never be misreported as an
    official statistical correction if one were ever introduced.
    """
    for field in reconciliation.PROVENANCE_FIELDS:
        assert reconciliation.field_category(field) == (
            reconciliation.CATEGORY_PROVENANCE_ONLY
        )
        assert field not in reconciliation.PUBLISHED_EVIDENCE_FIELDS
    for field in reconciliation.STATISTICAL_FIELDS:
        assert reconciliation.field_category(field) == (
            reconciliation.CATEGORY_STATISTICAL_CORRECTION
        )
        assert field in reconciliation.PUBLISHED_EVIDENCE_FIELDS


def test_a_correction_stamps_provenance_without_calling_it_evidence(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(940040)
        arm = _pitcher(6040)
        db.session.flush()
        _stored_row(arm, 940040, earned_runs=0)
        db.session.commit()
        monkeypatch.setattr(
            sync_service, 'mlb_client',
            BoxscoreClient({940040: boxscore([
                (6040, 'home', pitching_stats(earned_runs=2)),
            ])}),
        )

        plan, summary = _plan_game(940040)

        assert plan[0]['provenance_update'] is True
        assert plan[0]['is_provenance_only'] is False
        assert plan[0]['affects_published_evidence'] is True
        # The provenance columns are not reported as changed baseball fields.
        assert not set(plan[0]['changed_fields']) & set(
            reconciliation.PROVENANCE_FIELDS
        )
        assert summary['provenance_only_updates'] == 0
