"""Daily realization and postgame convergence, end to end.

The two cycles observe different moments, and these tests exercise both against
a real database rather than a hand-built report.

DAILY — the lane projects first, the legacy writer runs second, and the proof
asks whether the writer put the canonical rows into the projected state.

POSTGAME — the writer runs first and the lane projects second, so a healthy
cycle projects nothing at all.
"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.scheduled_game import ScheduledGame
from services import game_driven_realization as realization
from services import game_log_reconciliation as reconciliation
from services import pitcher_identity_reconciliation as pitcher_identity
from utils.db import db


SLATE = date(2026, 6, 20)
GAME_PK = 930101


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


# ── Fixtures ────────────────────────────────────────────────────────────────


def _pitcher(mlb_id):
    pitcher = Pitcher(
        mlb_id=mlb_id, full_name=f'Arm {mlb_id}', team_id=147,
        team_abbreviation='TST', position='P', active=True,
        roster_status='ACTIVE',
    )
    db.session.add(pitcher)
    db.session.commit()
    return pitcher


def _game_log(pitcher, *, game_pk=GAME_PK, outs=3, earned_runs=0, **overrides):
    row = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=SLATE,
        game_type='R',
        innings_pitched_outs=outs,
        innings_pitched=round(outs / 3.0, 10),
        pitches_thrown=14,
        strikes=9,
        earned_runs=earned_runs,
        runs_allowed=earned_runs,
        hits_allowed=0,
        walks=0,
        strikeouts=1,
        home_runs_allowed=0,
        games_started=0,
    )
    for field, value in overrides.items():
        setattr(row, field, value)
    db.session.add(row)
    db.session.commit()
    return row


def _values(*, outs=3, earned_runs=0, **overrides):
    # Covers every field ``correctable_fields`` unconditionally names, so the
    # planner reconciles against a complete governed record rather than raising
    # on an absent key.
    values = {
        'mlb_game_pk': GAME_PK,
        'game_date': SLATE,
        'game_type': 'R',
        'innings_pitched_outs': outs,
        'innings_pitched': round(outs / 3.0, 10),
        'pitches_thrown': 14,
        'strikes': 9,
        'earned_runs': earned_runs,
        'runs_allowed': earned_runs,
        'hits_allowed': 0,
        'walks': 0,
        'strikeouts': 1,
        'home_runs_allowed': 0,
        'games_started': 0,
    }
    values.update(overrides)
    return values


def _stats(**overrides):
    stats = {
        'inningsPitched': '1.0',
        'strikes': 9,
        'hits': 0,
        'runs': 0,
        'earnedRuns': 0,
        'baseOnBalls': 0,
        'strikeOuts': 1,
        'homeRuns': 0,
    }
    stats.update(overrides)
    return stats


def _plan(*, existing, values, stats=None, pitcher_mlb_id=7001,
          local_pitcher_id=None, identity_plan=None):
    return reconciliation.plan_row(
        existing=existing,
        values=values,
        stats=stats if stats is not None else _stats(),
        game_pk=GAME_PK,
        pitcher_mlb_id=pitcher_mlb_id,
        local_pitcher_id=local_pitcher_id,
        identity_plan=identity_plan or {'action': pitcher_identity.ACTION_UNCHANGED},
    )


def _work_item(*, source_revision):
    return GameIngestionWorkItem(
        mlb_game_pk=GAME_PK,
        represented_date=SLATE,
        game_date=SLATE,
        game_type='R',
        candidate_reason='newly_final',
        criticality=GameIngestionWorkItem.CRITICALITY_PUBLICATION_CRITICAL,
        finality_state='final',
        source_authority='scheduled_games',
        source_revision=source_revision,
        status=GameIngestionWorkItem.STATUS_COMPLETED,
        # The completion-proof CHECK constraint: a completed row must carry a
        # timestamp, a determined expectation, and a matching reconciled count.
        completed_at=datetime(2026, 6, 21, 4, 0, 0),
        rows_expected=1,
        rows_reconciled=1,
        relief_rows_reconciled=1,
    )


def _report(plans, *, game_pk=GAME_PK, source_revision='rev-1'):
    """A run report shaped exactly as the lane produces one."""
    from services import game_driven_ingestion

    rows = game_driven_ingestion._safe_row_entries(plans)
    return {
        'games': [{
            'game_pk': game_pk,
            'source_revision': source_revision,
            'rows': rows,
        }],
    }


# ── The plan carries its own target state ───────────────────────────────────


def test_an_insert_plan_names_the_fields_it_intends_to_determine():
    plan = _plan(existing=None, values=_values())
    assert plan['action'] == reconciliation.ACTION_INSERT
    assert 'innings_pitched_outs' in plan['target_fields']
    assert 'earned_runs' in plan['target_fields']


def test_an_insert_target_excludes_the_derived_companion():
    """D-008: the decimal companion is derived, never an independent target."""
    plan = _plan(existing=None, values=_values())
    assert 'innings_pitched' not in plan['target_fields']


def test_an_insert_target_excludes_provenance_columns():
    plan = _plan(existing=None, values=_values())
    for field in reconciliation.PROVENANCE_FIELDS:
        assert field not in plan['target_fields']


def test_an_update_plan_targets_only_its_changed_fields(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher, outs=3, earned_runs=0)
        plan = _plan(
            existing=stored,
            values=_values(outs=3, earned_runs=2),
            stats=_stats(earnedRuns=2, runs=2),
            local_pitcher_id=pitcher.id,
        )
        assert plan['action'] == reconciliation.ACTION_UPDATE
        assert plan['target_fields'] == sorted(plan['changed_fields'])


def test_an_unchanged_plan_targets_nothing(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher)
        plan = _plan(
            existing=stored, values=_values(), local_pitcher_id=pitcher.id,
        )
        assert plan['action'] == reconciliation.ACTION_UNCHANGED
        assert plan['target_fields'] == []


def test_the_target_digest_is_deterministic():
    first = _plan(existing=None, values=_values())
    second = _plan(existing=None, values=_values())
    assert first['target_state_digest'] == second['target_state_digest']


def test_a_different_target_value_changes_the_digest():
    one = _plan(existing=None, values=_values(earned_runs=1))
    seven = _plan(existing=None, values=_values(earned_runs=7))
    assert one['target_state_digest'] != seven['target_state_digest']


def test_the_target_contract_did_not_move_the_plan_fingerprint(app):
    """Adding target state must not invalidate reviewed fingerprints."""
    with app.app_context():
        plan = _plan(existing=None, values=_values())
        with_target = reconciliation.plan_fingerprint([plan])
        stripped = dict(plan)
        stripped.pop('target_fields')
        stripped.pop('target_state_digest')
        assert reconciliation.plan_fingerprint([stripped]) == with_target


# ── Daily realization ───────────────────────────────────────────────────────


def test_a_no_candidate_daily_cycle_is_clean(app):
    with app.app_context():
        proof = realization.build_daily_realization({'games': []})
        assert proof['applicable'] is False
        assert proof['work_state'] == 'no_candidates'
        assert proof['all_projected_targets_realized'] is True


def test_a_fully_realized_insert_passes(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values(earned_runs=2))
        # The legacy writer then stores exactly what was projected.
        _game_log(pitcher, outs=3, earned_runs=2, runs_allowed=2)

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['projected_inserts'] == 1
        assert proof['realized_inserts'] == 1
        assert proof['missing_rows'] == 0
        assert proof['divergent_rows'] == 0
        assert proof['all_projected_targets_realized'] is True


def test_a_fully_realized_update_passes(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher, outs=3, earned_runs=0)
        plan = _plan(
            existing=stored,
            values=_values(outs=3, earned_runs=2),
            stats=_stats(earnedRuns=2, runs=2),
            local_pitcher_id=pitcher.id,
        )
        # The writer applies the correction.
        stored.earned_runs = 2
        stored.runs_allowed = 2
        db.session.commit()

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['projected_updates'] == 1
        assert proof['realized_updates'] == 1
        assert proof['all_projected_targets_realized'] is True


def test_a_mixed_cycle_realizes_each_row_on_its_own_terms(app):
    with app.app_context():
        inserted_arm = _pitcher(7001)
        updated_arm = _pitcher(7002)
        unchanged_arm = _pitcher(7003)

        stored_update = _game_log(updated_arm, outs=3, earned_runs=0)
        stored_unchanged = _game_log(unchanged_arm, outs=3, earned_runs=0)

        plans = [
            _plan(existing=None, values=_values(earned_runs=1),
                  pitcher_mlb_id=7001),
            _plan(existing=stored_update, values=_values(earned_runs=2),
                  stats=_stats(earnedRuns=2, runs=2),
                  pitcher_mlb_id=7002, local_pitcher_id=updated_arm.id),
            _plan(existing=stored_unchanged, values=_values(),
                  pitcher_mlb_id=7003, local_pitcher_id=unchanged_arm.id),
        ]

        _game_log(inserted_arm, outs=3, earned_runs=1, runs_allowed=1)
        stored_update.earned_runs = 2
        stored_update.runs_allowed = 2
        db.session.commit()

        proof = realization.build_daily_realization(_report(plans))

        assert proof['projected_rows'] == 3
        assert proof['realized_rows'] == 2
        assert proof['already_matching_rows'] == 1
        assert proof['all_projected_targets_realized'] is True


def test_a_missing_realized_row_fails(app):
    with app.app_context():
        _pitcher(7001)
        plan = _plan(existing=None, values=_values())
        # The writer never wrote it.

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['missing_rows'] == 1
        assert proof['all_projected_targets_realized'] is False
        assert proof['unresolved_identities'][0]['game_pk'] == GAME_PK


def test_a_divergent_target_fails(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values(earned_runs=2))
        # The writer stored a different number than the plan projected.
        _game_log(pitcher, outs=3, earned_runs=5, runs_allowed=5)

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['divergent_rows'] == 1
        assert proof['safe_digest_match'] is False
        assert proof['all_projected_targets_realized'] is False


def test_a_partially_applied_update_fails(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher, outs=3, earned_runs=0, strikeouts=1)
        plan = _plan(
            existing=stored,
            values=_values(outs=6, earned_runs=2),
            stats=_stats(inningsPitched='2.0', earnedRuns=2, runs=2),
            local_pitcher_id=pitcher.id,
        )
        # The writer applied one of the two projected fields.
        stored.earned_runs = 2
        stored.runs_allowed = 2
        db.session.commit()

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['divergent_rows'] == 1
        assert proof['all_projected_targets_realized'] is False


def test_the_schema_forbids_a_duplicate_canonical_appearance(app):
    """The duplicate branch is a backstop the schema already prevents.

    ``game_logs`` carries a UNIQUE constraint on ``(pitcher_id, mlb_game_pk)``,
    so a second appearance row for one pitcher in one game cannot be stored at
    all. That constraint is the real guarantee and is asserted here rather than
    assumed; the classifier's duplicate branch is exercised separately below,
    because a defence that has never been executed is not a defence.
    """
    from sqlalchemy.exc import IntegrityError

    with app.app_context():
        pitcher = _pitcher(7001)
        _game_log(pitcher, outs=3)
        with pytest.raises(IntegrityError):
            _game_log(pitcher, outs=3)
        db.session.rollback()


def test_the_duplicate_backstop_refuses_to_call_a_row_realized(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher, outs=3)
        plan = _plan(existing=None, values=_values())
        row = _report([plan])['games'][0]['rows'][0]

        entry = realization._classify_row(
            row,
            local_ids={7001: pitcher.id},
            # Two rows under one natural key — the state the schema forbids.
            stored={(pitcher.id, GAME_PK): [stored, stored]},
        )

        assert entry['result'] == realization.RESULT_DUPLICATE
        assert entry['result'] in realization.UNRESOLVED_RESULTS


def test_an_unresolvable_identity_fails(app):
    with app.app_context():
        # No Pitcher row exists for the projected appearance.
        plan = _plan(existing=None, values=_values(), pitcher_mlb_id=9999)

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['missing_rows'] == 1
        assert proof['all_projected_targets_realized'] is False


def test_a_realized_minimal_identity_creation_passes(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(
            existing=None, values=_values(),
            identity_plan={
                'action': pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
                'requires_creation': True,
            },
        )
        _game_log(pitcher, outs=3)

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['identity_creations_projected'] == 1
        assert proof['identity_creations_realized'] == 1
        assert proof['prohibited_identity_actions'] == 0
        assert proof['all_projected_targets_realized'] is True


def test_an_unrealized_identity_creation_fails(app):
    with app.app_context():
        plan = _plan(
            existing=None, values=_values(), pitcher_mlb_id=9999,
            identity_plan={
                'action': pitcher_identity.ACTION_CREATE_MINIMAL_IDENTITY,
                'requires_creation': True,
            },
        )

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['identity_creations_projected'] == 1
        assert proof['identity_creations_realized'] == 0
        assert proof['all_projected_targets_realized'] is False


def test_a_prohibited_identity_action_fails(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(
            existing=None, values=_values(),
            identity_plan={'action': 'reactivate_existing_pitcher'},
        )
        _game_log(pitcher, outs=3)

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['prohibited_identity_actions'] == 1
        assert proof['all_projected_targets_realized'] is False


def test_a_blocked_identity_action_fails(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(
            existing=None, values=_values(),
            identity_plan={'action': pitcher_identity.ACTION_BLOCKED},
        )
        _game_log(pitcher, outs=3)

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['prohibited_identity_actions'] == 1
        assert proof['all_projected_targets_realized'] is False


def test_a_suppressed_current_state_difference_is_recorded_not_penalised(app):
    """D-009 refusing a current-state write is correct behaviour."""
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher)
        plan = _plan(
            existing=stored, values=_values(), local_pitcher_id=pitcher.id,
            identity_plan={
                'action': pitcher_identity.ACTION_UNCHANGED,
                'current_authority_mutation_refused': True,
            },
        )

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['current_state_mutations_refused'] == 1
        assert proof['prohibited_identity_actions'] == 0
        assert proof['all_projected_targets_realized'] is True


def test_a_canonical_outs_correction_is_tracked_to_realization(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher, outs=3)
        plan = _plan(
            existing=stored,
            values=_values(outs=6),
            stats=_stats(inningsPitched='2.0'),
            local_pitcher_id=pitcher.id,
        )
        stored.innings_pitched_outs = 6
        stored.innings_pitched = 2.0
        db.session.commit()

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['canonical_outs_corrections_projected'] == 1
        assert proof['canonical_outs_corrections_realized'] == 1
        assert proof['all_projected_targets_realized'] is True


def test_a_changed_source_revision_against_a_checkpoint_fails(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher)
        plan = _plan(
            existing=stored, values=_values(), local_pitcher_id=pitcher.id,
        )
        db.session.add(_work_item(source_revision='rev-OLD'))
        db.session.commit()

        proof = realization.build_daily_realization(
            _report([plan], source_revision='rev-NEW')
        )

        assert proof['source_revision_match'] is False
        assert proof['all_projected_targets_realized'] is False


def test_a_matching_source_revision_passes(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher)
        plan = _plan(
            existing=stored, values=_values(), local_pitcher_id=pitcher.id,
        )
        db.session.add(_work_item(source_revision='rev-1'))
        db.session.commit()

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['source_revision_match'] is True
        assert proof['source_revisions'][0]['state'] == (
            realization.SOURCE_REVISION_MATCHED
        )


def test_a_game_without_a_checkpoint_is_reported_honestly(app):
    """No checkpoint means nothing to compare — not a silent match."""
    with app.app_context():
        pitcher = _pitcher(7001)
        stored = _game_log(pitcher)
        plan = _plan(
            existing=stored, values=_values(), local_pitcher_id=pitcher.id,
        )

        proof = realization.build_daily_realization(_report([plan]))

        assert proof['source_revisions'][0]['state'] == (
            realization.SOURCE_REVISION_NO_CHECKPOINT
        )
        assert proof['source_revision_match'] is True


# ── The proof itself is safe ────────────────────────────────────────────────


def test_the_proof_performs_no_write(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values())
        _game_log(pitcher, outs=3)
        before = GameLog.query.count(), Pitcher.query.count()

        realization.build_daily_realization(_report([plan]))

        assert (GameLog.query.count(), Pitcher.query.count()) == before


def test_the_proof_calls_no_mlb_endpoint_and_never_replans():
    source = realization.__file__
    with open(source, encoding='utf-8') as handle:
        text = handle.read()
    for forbidden in (
        'mlb_client', 'plan_game_work', 'run_game_driven_ingestion',
        'get_game_boxscore', 'requests.', 'plan_row(',
    ):
        assert forbidden not in text, (
            f'the realization proof must not {forbidden!r} — it consumes the '
            f'plan the lane already produced'
        )


def test_the_proof_serializes_no_raw_row_or_value(app):
    import json

    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values(earned_runs=2))
        _game_log(pitcher, outs=3, earned_runs=5, runs_allowed=5)

        proof = realization.build_daily_realization(_report([plan]))
        body = json.dumps(proof, sort_keys=True, default=str)

        # Field names are safe; the values behind them never travel.
        assert 'earned_runs' in body
        assert '"before"' not in body
        assert '"after"' not in body
        for forbidden in (
            'postgresql://', 'password=', 'Authorization:', 'ADMIN_API_TOKEN',
            'SECRET_KEY', 'DATABASE_URL', 'Traceback', '/home/',
        ):
            assert forbidden not in body


def test_the_proof_is_deterministic(app):
    import json

    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values())
        _game_log(pitcher, outs=3)

        first = realization.build_daily_realization(_report([plan]))
        second = realization.build_daily_realization(_report([plan]))

        assert json.dumps(first, sort_keys=True, default=str) == json.dumps(
            second, sort_keys=True, default=str
        )


def test_a_plan_that_declared_no_target_cannot_be_called_realized(app):
    """Fail closed: an unprovable row is unresolved, never a silent pass."""
    with app.app_context():
        pitcher = _pitcher(7001)
        _game_log(pitcher, outs=3)
        plan = _plan(existing=None, values=_values())
        report = _report([plan])
        report['games'][0]['rows'][0]['target_fields'] = []

        proof = realization.build_daily_realization(report)

        assert proof['unresolved_rows'] == 1
        assert proof['all_projected_targets_realized'] is False


# ── Stored-state digest reuses the canonical encoder ────────────────────────


def test_the_stored_digest_matches_the_plan_digest_for_a_realized_insert(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values(earned_runs=2))
        stored = _game_log(pitcher, outs=3, earned_runs=2, runs_allowed=2)

        assert reconciliation.stored_state_digest(
            stored, plan['target_fields']
        ) == plan['target_state_digest']


def test_the_stored_digest_of_a_missing_row_is_empty():
    assert reconciliation.stored_state_digest(None, ['earned_runs']) == ''


def test_the_digest_is_order_independent():
    assert reconciliation.target_state_digest(
        [('a', 1), ('b', 2)]
    ) == reconciliation.target_state_digest([('b', 2), ('a', 1)])


# ── The attach point: after the writer, fail-closed, never fatal ────────────


def _lane_status(**overrides):
    status = {'game_driven_ingestion': {'status': 'complete', 'mode': 'shadow'}}
    status['game_driven_ingestion'].update(overrides)
    return status


def _attach(app, *, game_lane, status):
    import logging

    import services.sync as sync_service

    with app.app_context():
        sync_service._attach_daily_realization(
            game_lane=game_lane,
            status=status,
            stage_timings={},
            run_logger=logging.getLogger('test'),
        )
    return status


def test_the_proof_is_attached_to_the_lane_status(app):
    with app.app_context():
        pitcher = _pitcher(7001)
        plan = _plan(existing=None, values=_values())
        _game_log(pitcher, outs=3)
        report = _report([plan])

    status = _lane_status()
    _attach(app, game_lane={'report': report}, status=status)

    attached = status['game_driven_ingestion']['realization']
    assert attached['available'] is True
    assert attached['all_projected_targets_realized'] is True


def test_nothing_is_attached_when_the_lane_is_disabled(app):
    status = {'game_driven_ingestion': {'status': 'disabled', 'mode': 'off'}}
    _attach(app, game_lane={'report': None}, status=status)
    assert 'realization' not in status['game_driven_ingestion']


def test_nothing_is_attached_when_the_lane_never_ran(app):
    status = {}
    _attach(app, game_lane={'report': None}, status=status)
    assert status == {}


def test_a_missing_report_is_reported_as_unavailable_not_omitted(app):
    """A missing proof and a passing proof must never look alike."""
    status = _lane_status()
    _attach(app, game_lane={'report': None}, status=status)

    attached = status['game_driven_ingestion']['realization']
    assert attached['available'] is False
    assert attached['all_projected_targets_realized'] is False


def test_a_failing_proof_fails_closed_with_a_safe_class(app, monkeypatch):
    import services.game_driven_realization as module

    def explode(report):
        raise RuntimeError('postgresql://user:pw@host/db exploded')

    monkeypatch.setattr(module, 'build_daily_realization', explode)
    status = _lane_status()
    _attach(app, game_lane={'report': {'games': []}}, status=status)

    attached = status['game_driven_ingestion']['realization']
    assert attached['available'] is False
    assert attached['error_class'] == 'RuntimeError'
    assert attached['all_projected_targets_realized'] is False
    assert 'postgresql://' not in repr(attached)
    assert 'exploded' not in repr(attached)


def test_the_proof_runs_after_the_legacy_writer_in_the_daily_sync():
    """Ordering is the whole basis of the daily contract."""
    import pathlib

    import services.sync as sync_service

    source = pathlib.Path(sync_service.__file__).read_text(encoding='utf-8')
    # The CALL site, not the definition — ``def _attach_daily_realization``
    # appears far earlier in the module and would make this assertion
    # meaningless.
    lane_at = source.index('game_lane = _run_game_driven_ingestion_stage(')
    writer_at = source.index('pull = sync_recent_logs(')
    proof_at = source.index('            _attach_daily_realization(')

    assert lane_at < writer_at, 'daily shadow must project before the writer'
    assert writer_at < proof_at, (
        'the realization proof must read the database after the writer, or it '
        'proves nothing'
    )


def test_the_daily_sync_has_exactly_one_realization_attach_point():
    import pathlib

    import services.sync as sync_service

    source = pathlib.Path(sync_service.__file__).read_text(encoding='utf-8')
    assert source.count('_attach_daily_realization(') == 2  # 1 def + 1 call
