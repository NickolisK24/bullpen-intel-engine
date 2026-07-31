"""Foundation 3C — canonical innings semantics in the reconciliation planner.

D-008 is a permanent data rule: integer recorded outs are the semantic innings
authority and decimal innings are derived. Production validation found the
game-driven reconciliation planner treating the derived companion as an
independent official statistic:

    109-game shadow, reference date 2026-07-29
      946 rows expected, 325 projected updates, 621 unchanged
      changed fields: innings_pitched 323, earned_runs 4, hits_allowed 4

and, on the five games a controlled write had ALREADY reconciled:

      38 rows, 14 projected updates, 24 unchanged
      every one of the 14 had exactly one changed field: innings_pitched

A write that has already been applied must replay to zero changes. It did not,
because a stored float and a freshly derived float can differ in
representation while describing the same canonical number of recorded outs.
Repeating the write would re-apply the same non-correction and increment
correction provenance again.

These tests fix the rule in place: when stored outs equal official outs, a
decimal difference is not a baseball correction — not an update, not a
provenance event, not a fingerprint change.
"""

from datetime import date

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import appearance_team_authority
from services import game_log_reconciliation as reconciliation
from services import sync as sync_service
from tests.game_driven_fixtures import (
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
from utils.innings import outs_to_decimal_innings


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


def _innings_notation(outs):
    return f'{outs // 3}.{outs % 3}'


def _stored_row(pitcher_row, game_pk, *, outs=3, decimal_innings=None, **overrides):
    """A stored appearance whose decimal companion may be set independently.

    ``decimal_innings`` exists so a test can model exactly the production
    condition: authoritative outs agree, the stored float does not match a
    fresh Python division.
    """
    values = {
        'pitcher_id': pitcher_row.id,
        'mlb_game_pk': game_pk,
        'game_date': REFERENCE,
        'game_type': 'R',
        'opponent': 'Away Club',
        'opponent_abbreviation': 'AWY',
        'games_started': 0,
        'innings_pitched_outs': outs,
        'innings_pitched': (
            outs_to_decimal_innings(outs) if decimal_innings is None
            else decimal_innings
        ),
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


def _install(monkeypatch, boxscores):
    monkeypatch.setattr(
        sync_service, 'mlb_client', BoxscoreClient(boxscores),
    )


def _game_with(mlb_id, outs, **stat_overrides):
    return boxscore([(
        mlb_id, 'home',
        pitching_stats(innings=_innings_notation(outs), **stat_overrides),
    )])


# ═══════════════ Equal outs: a decimal difference is not a correction ═══════


@pytest.mark.parametrize('outs', [0, 1, 2, 3, 4, 5, 7, 8, 27])
def test_equal_outs_with_a_drifted_decimal_companion_is_unchanged(
    app, monkeypatch, outs,
):
    """The production condition, across every non-whole-inning shape.

    Five outs is the historically important one: 5/3 has no exact binary
    representation, so a stored float and a fresh division are the classic
    inequality this rule exists to absorb.
    """
    with app.app_context():
        game_pk = 950000 + outs
        _schedule(game_pk)
        arm = _pitcher(6300 + outs)
        db.session.flush()
        drifted = outs_to_decimal_innings(outs) + 1e-9
        _stored_row(arm, game_pk, outs=outs, decimal_innings=drifted)
        db.session.commit()
        _install(monkeypatch, {game_pk: _game_with(arm.mlb_id, outs)})

        plan, summary = _plan_game(game_pk)

        assert summary['rows_unchanged'] == 1
        assert summary['rows_updated'] == 0
        assert plan[0]['action'] == reconciliation.ACTION_UNCHANGED
        assert 'innings_pitched' not in plan[0]['changed_fields']
        assert plan[0]['is_statistical_correction'] is False


def test_a_materially_different_decimal_companion_cannot_be_stored_at_all(app):
    """The storage invariant bounds how far the companion can ever drift.

    ``ck_game_logs_innings_pitched_matches_outs`` requires the stored decimal to
    be within 1e-6 of outs/3. A materially inconsistent companion is therefore
    not a reachable state, and the only drift the reconciliation planner can
    ever encounter is float representation. Recording that here because it
    bounds the whole problem: there is no hidden population of badly wrong
    decimals for this path to "repair", so refusing to treat the companion as
    an official statistic loses nothing.
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        _schedule(950100)
        arm = _pitcher(6400)
        db.session.flush()
        _stored_row(arm, 950100, outs=5, decimal_innings=99.5)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_a_zeroed_decimal_companion_cannot_be_stored_either(app):
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        _schedule(950101)
        arm = _pitcher(6401)
        db.session.flush()
        _stored_row(arm, 950101, outs=4, decimal_innings=0.0)

        with pytest.raises(IntegrityError):
            db.session.commit()
        db.session.rollback()


def test_a_decimal_only_difference_never_touches_correction_provenance(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(950102)
        arm = _pitcher(6402)
        db.session.flush()
        _stored_row(
            arm, 950102, outs=5,
            decimal_innings=outs_to_decimal_innings(5) + 1e-9,
        )
        db.session.commit()
        _install(monkeypatch, {950102: _game_with(6402, 5)})

        _write_game(950102)

        row = GameLog.query.filter_by(mlb_game_pk=950102).one()
        assert row.stat_correction_count == 0
        assert row.last_stat_correction_at is None
        assert row.last_stat_correction_source is None
        assert row.last_stat_correction_sync_run_id is None


# ═══════════════ Genuine outs corrections still work ════════════════════════


def test_a_genuine_outs_correction_updates_outs_and_derives_the_companion(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(950200)
        arm = _pitcher(6500)
        db.session.flush()
        _stored_row(arm, 950200, outs=3)
        db.session.commit()
        _install(monkeypatch, {950200: _game_with(6500, 7)})

        plan, summary = _plan_game(950200)

        assert summary['rows_updated'] == 1
        assert 'innings_pitched_outs' in plan[0]['semantic_changed_fields']
        assert 'innings_pitched' not in plan[0]['semantic_changed_fields']
        assert 'innings_pitched' in plan[0]['applied_changed_fields']
        assert 'innings_pitched' in plan[0]['derived_companion_fields']

        write_plan, _ = _write_game(950200)
        assert write_plan[0]['semantic_changed_fields'] == (
            plan[0]['semantic_changed_fields']
        )

        row = GameLog.query.filter_by(mlb_game_pk=950200).one()
        assert row.innings_pitched_outs == 7
        assert row.innings_pitched == pytest.approx(outs_to_decimal_innings(7))
        assert row.stat_correction_count == 1

        # And it converges.
        _, replay = _plan_game(950200)
        assert replay['rows_updated'] == 0


def test_outs_and_earned_runs_together_are_one_update_and_one_provenance_event(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(950201)
        arm = _pitcher(6501)
        db.session.flush()
        _stored_row(arm, 950201, outs=3, earned_runs=0)
        db.session.commit()
        _install(monkeypatch, {950201: _game_with(6501, 8, earned_runs=2)})

        plan, summary = _plan_game(950201)

        assert summary['rows_updated'] == 1
        assert len(plan) == 1
        assert {'innings_pitched_outs', 'earned_runs'} <= set(
            plan[0]['semantic_changed_fields']
        )
        assert 'innings_pitched' in plan[0]['derived_companion_fields']

        _write_game(950201)
        row = GameLog.query.filter_by(mlb_game_pk=950201).one()
        assert row.innings_pitched_outs == 8
        assert row.earned_runs == 2
        assert row.stat_correction_count == 1

        _, replay = _plan_game(950201)
        assert replay['rows_updated'] == 0


@pytest.mark.parametrize('override,field', [
    # runs is pinned so only the named field moves.
    ({'earned_runs': 4, 'runs': 0}, 'earned_runs'),
    ({'hits': 6}, 'hits_allowed'),
])
def test_another_stat_correction_with_a_drifted_decimal_reports_only_that_stat(
    app, monkeypatch, override, field,
):
    """A real correction must not be inflated by the derived companion."""
    with app.app_context():
        game_pk = 950300 + abs(hash(field)) % 90
        _schedule(game_pk)
        arm = _pitcher(6600 + abs(hash(field)) % 90)
        db.session.flush()
        _stored_row(
            arm, game_pk, outs=5,
            decimal_innings=outs_to_decimal_innings(5) + 1e-9,
        )
        db.session.commit()
        _install(monkeypatch, {game_pk: _game_with(arm.mlb_id, 5, **override)})

        plan, summary = _plan_game(game_pk)

        assert summary['rows_updated'] == 1
        assert plan[0]['semantic_changed_fields'] == [field]
        assert 'innings_pitched' not in plan[0]['applied_changed_fields']

        _write_game(game_pk)
        row = GameLog.query.filter_by(mlb_game_pk=game_pk).one()
        assert row.stat_correction_count == 1
        _, replay = _plan_game(game_pk)
        assert replay['rows_updated'] == 0


def test_an_insert_parses_outs_once_and_derives_the_companion(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(950400)
        _pitcher(6700)
        db.session.commit()
        _install(monkeypatch, {950400: _game_with(6700, 5)})

        plan, summary = _plan_game(950400)
        assert summary['rows_inserted'] == 1
        assert plan[0]['action'] == reconciliation.ACTION_INSERT

        _write_game(950400)
        row = GameLog.query.filter_by(mlb_game_pk=950400).one()
        assert row.innings_pitched_outs == 5
        assert row.innings_pitched == pytest.approx(outs_to_decimal_innings(5))

        _, replay = _plan_game(950400)
        assert replay['rows_updated'] == 0
        assert replay['rows_unchanged'] == 1


# ═══════════════ Fingerprint semantics ══════════════════════════════════════


def test_a_decimal_representation_difference_does_not_change_the_fingerprint(
    app, monkeypatch,
):
    with app.app_context():
        _schedule(950500)
        _schedule(950501)
        exact = _pitcher(6800)
        drifted = _pitcher(6801)
        db.session.flush()
        _stored_row(exact, 950500, outs=5)
        _stored_row(
            drifted, 950501, outs=5,
            decimal_innings=outs_to_decimal_innings(5) + 1e-9,
        )
        db.session.commit()
        _install(monkeypatch, {
            950500: _game_with(6800, 5),
            950501: _game_with(6801, 5),
        })

        _, exact_summary = _plan_game(950500)
        _, drifted_summary = _plan_game(950501)

        # Different rows, same semantic decision: unchanged.
        assert exact_summary['rows_updated'] == 0
        assert drifted_summary['rows_updated'] == 0
        assert exact_summary['mutation_category_counts'] == (
            drifted_summary['mutation_category_counts']
        )


def test_a_genuine_outs_change_does_change_the_fingerprint(app, monkeypatch):
    with app.app_context():
        _schedule(950502)
        arm = _pitcher(6802)
        db.session.flush()
        _stored_row(arm, 950502, outs=5)
        db.session.commit()

        _install(monkeypatch, {950502: _game_with(6802, 5)})
        _, unchanged = _plan_game(950502)

        _install(monkeypatch, {950502: _game_with(6802, 8)})
        _, corrected = _plan_game(950502)

        assert unchanged['reconciliation_plan_fingerprint'] != (
            corrected['reconciliation_plan_fingerprint']
        )


def test_the_fingerprint_does_not_depend_on_row_order():
    rows = [
        {'game_pk': 1, 'pitcher_mlb_id': 2, 'action': 'update',
         'changed_fields': ['earned_runs'], 'mutation_categories': ['x']},
        {'game_pk': 1, 'pitcher_mlb_id': 1, 'action': 'unchanged',
         'changed_fields': [], 'mutation_categories': ['y']},
    ]
    assert reconciliation.plan_fingerprint(rows) == (
        reconciliation.plan_fingerprint(list(reversed(rows)))
    )


# ═══════════════ Production-shape regressions ═══════════════════════════════


def test_the_five_game_replay_converges_to_zero_updates(app, monkeypatch):
    """The exact observed shape: 38 rows, 14 decimal-only, 24 exact.

    Before this repair the 14 replayed as updates forever. They must now all
    be unchanged.
    """
    with app.app_context():
        game_pks = [950601, 950602, 950603, 950604, 950605]
        rows_per_game = [9, 6, 9, 7, 7]
        drifted_per_game = [4, 2, 4, 2, 2]
        assert sum(rows_per_game) == 38
        assert sum(drifted_per_game) == 14

        boxscores = {}
        mlb_id = 6900
        for game_pk, total, drifted in zip(
            game_pks, rows_per_game, drifted_per_game,
        ):
            _schedule(game_pk)
            lines = []
            for index in range(total):
                arm = _pitcher(mlb_id)
                db.session.flush()
                outs = 5 if index % 2 else 4
                if index < drifted:
                    _stored_row(
                        arm, game_pk, outs=outs,
                        decimal_innings=outs_to_decimal_innings(outs) + 1e-9,
                    )
                else:
                    _stored_row(arm, game_pk, outs=outs)
                lines.append((
                    mlb_id, 'home',
                    pitching_stats(innings=_innings_notation(outs)),
                ))
                mlb_id += 1
            boxscores[game_pk] = boxscore(lines)
        db.session.commit()
        _install(monkeypatch, boxscores)

        updated = unchanged = ignored = statistical = 0
        for game_pk in game_pks:
            _, summary = _plan_game(game_pk)
            updated += summary['rows_updated']
            unchanged += summary['rows_unchanged']
            ignored += summary['derived_companion_differences_ignored']
            statistical += summary['statistical_corrections']

        assert updated == 0
        assert unchanged == 38
        assert ignored == 14
        assert statistical == 0


def test_the_full_window_shape_suppresses_decimals_and_keeps_real_changes(
    app, monkeypatch,
):
    """Hundreds of decimal-only differences alongside genuine corrections.

    Models the 109-game shape, including rows where a real change and a
    decimal difference land on the SAME row — which must count once.
    """
    with app.app_context():
        game_pk = 950700
        _schedule(game_pk)
        lines = []
        mlb_id = 7000

        decimal_only = 30
        earned_run_changes = 4
        hit_changes = 4
        overlapping = 2      # real change AND a drifted decimal on one row
        exact = 20

        for _ in range(decimal_only):
            arm = _pitcher(mlb_id)
            db.session.flush()
            _stored_row(
                arm, game_pk, outs=5,
                decimal_innings=outs_to_decimal_innings(5) + 1e-9,
            )
            lines.append((mlb_id, 'home', pitching_stats(innings='1.2')))
            mlb_id += 1

        for _ in range(earned_run_changes):
            arm = _pitcher(mlb_id)
            db.session.flush()
            _stored_row(arm, game_pk, outs=5, earned_runs=0)
            lines.append((
                mlb_id, 'home', pitching_stats(innings='1.2', earned_runs=3),
            ))
            mlb_id += 1

        for _ in range(hit_changes):
            arm = _pitcher(mlb_id)
            db.session.flush()
            _stored_row(arm, game_pk, outs=5, hits_allowed=1)
            lines.append((
                mlb_id, 'home', pitching_stats(innings='1.2', hits=6),
            ))
            mlb_id += 1

        for _ in range(overlapping):
            arm = _pitcher(mlb_id)
            db.session.flush()
            _stored_row(
                arm, game_pk, outs=5, earned_runs=0,
                decimal_innings=outs_to_decimal_innings(5) + 1e-9,
            )
            lines.append((
                mlb_id, 'home', pitching_stats(innings='1.2', earned_runs=2),
            ))
            mlb_id += 1

        for _ in range(exact):
            arm = _pitcher(mlb_id)
            db.session.flush()
            _stored_row(arm, game_pk, outs=5)
            lines.append((mlb_id, 'home', pitching_stats(innings='1.2')))
            mlb_id += 1

        db.session.commit()
        _install(monkeypatch, {game_pk: boxscore(lines)})

        plan, summary = _plan_game(game_pk)

        total = decimal_only + earned_run_changes + hit_changes + overlapping + exact
        assert summary['rows_planned'] == total
        # Only the genuine changes are updates; the overlapping rows count ONCE.
        assert summary['rows_updated'] == (
            earned_run_changes + hit_changes + overlapping
        )
        assert summary['rows_unchanged'] == decimal_only + exact
        assert summary['rows_updated'] + summary['rows_unchanged'] == total
        # Ignored companion differences are counted on unchanged AND on
        # updated rows, never double-counted per row.
        assert summary['derived_companion_differences_ignored'] == (
            decimal_only + overlapping
        )
        assert 'innings_pitched' not in summary['changed_fields_counts']
        assert summary['changed_fields_counts']['earned_runs'] == (
            earned_run_changes + overlapping
        )
        assert summary['changed_fields_counts']['hits_allowed'] == hit_changes


def test_no_plan_entry_ever_reports_innings_pitched_as_a_semantic_change(
    app, monkeypatch,
):
    """The structural rule, asserted directly."""
    with app.app_context():
        _schedule(950800)
        arm = _pitcher(7200)
        db.session.flush()
        _stored_row(arm, 950800, outs=3)
        db.session.commit()
        _install(monkeypatch, {950800: _game_with(7200, 7, earned_runs=5)})

        plan, _ = _plan_game(950800)

        assert 'innings_pitched' not in plan[0]['semantic_changed_fields']
        assert 'innings_pitched' not in plan[0]['changed_fields']
