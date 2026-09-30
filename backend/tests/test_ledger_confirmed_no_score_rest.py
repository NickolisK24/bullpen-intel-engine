"""Unscored active-bullpen arms count for coverage only under ledger proof.

Production, membership 2026-09-29 / availability 2026-09-30: KC, ATH and TEX
each had three active relievers with no fatigue score, no open fetch failure and
no incomplete log (one had an appearance in 2024, two had none). They counted as
unresolved, three is above the two the medium bar allows, and publication was
withheld. A reliever with an OLD score and the same appearance record was usable
(ledger-confirmed rest). The score is never read for a stale arm, so the gap was
the missing row, not missing evidence.

These fixtures reproduce those shapes and every condition that must keep an
unscored arm unresolved. The coverage thresholds are untouched throughout.
"""

from datetime import date, datetime

import pytest

from api import team_operations
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services import ledger_confirmed_rest
from services.availability_snapshot import (
    CURRENT_AVAILABILITY_MODE,
    classify_latest_fatigue_rows,
    latest_fatigue_rows,
)
from services.team_readiness_coverage import (
    MAX_MEDIUM_UNRESOLVED,
    MIN_MEDIUM_USABLE,
)
from tests.test_slate_coverage import app  # noqa: F401
from utils.db import db


TEAM = 118
REF = date(2026, 9, 30)
SCORED_AT = datetime(2026, 9, 30, 10, 20)
CURRENT = {'freshness': {'is_current': True}}

_next_mlb_id = [800000]
_next_game_pk = [990000]


def _pitcher(name, *, team_id=TEAM, active=True, assignment='ASSIGNED', mlb_id=True):
    _next_mlb_id[0] += 1
    pitcher = Pitcher(
        mlb_id=_next_mlb_id[0] if mlb_id else None, full_name=name,
        team_id=team_id, active=active, team_abbreviation='KC', position='P',
        team_assignment_status=assignment,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _log(pitcher, game_date, pitches=15, outs=3):
    _next_game_pk[0] += 1
    db.session.add(GameLog(
        pitcher_id=pitcher.id, mlb_game_pk=_next_game_pk[0], game_date=game_date,
        innings_pitched=outs / 3, innings_pitched_outs=outs, pitches_thrown=pitches,
    ))


def _score(pitcher, calculated_at=SCORED_AT):
    db.session.add(FatigueScore(
        pitcher_id=pitcher.id, calculated_at=calculated_at, raw_score=20.0,
        risk_level='LOW',
    ))


def _scored_fresh(name):
    pitcher = _pitcher(name)
    _score(pitcher)
    _log(pitcher, date(2026, 9, 27))
    return pitcher


def _scored_stale(name):
    pitcher = _pitcher(name)
    _score(pitcher, datetime(2026, 9, 5, 10, 0))
    _log(pitcher, date(2026, 9, 4))
    return pitcher


def _debut(name):
    """Kudrna / Zobac shape: active, assigned, no score, no MLB appearance."""
    return _pitcher(name)


def _old_history(name):
    """McArthur shape: active, assigned, no score, last appearance 2024-09-16."""
    pitcher = _pitcher(name)
    _log(pitcher, date(2024, 9, 16))
    return pitcher


def _bullpen(unscored_builders, *, scored_fresh=10, scored_stale=3):
    arms = [_scored_fresh(f'fresh_{i}') for i in range(scored_fresh)]
    arms += [_scored_stale(f'stale_{i}') for i in range(scored_stale)]
    extra = [build(f'unscored_{i}') for i, build in enumerate(unscored_builders)]
    db.session.commit()
    return arms, extra


def _assess(member_ids, *, authority_complete=True):
    records = classify_latest_fatigue_rows(
        latest_fatigue_rows(team_id=TEAM, limit=team_operations.TEAM_OPERATIONS_DEFAULT_LIMIT),
        reference_date=REF, mode=CURRENT_AVAILABILITY_MODE,
    )
    return team_operations._assess_active_bullpen_coverage(
        records, sync_status=CURRENT, team_id=TEAM, reference_date=REF,
        membership=(frozenset(member_ids), authority_complete),
    )


def _triple(assessment):
    return (
        assessment.active_bullpen_count,
        assessment.usable_record_count,
        assessment.unresolved_record_count,
    )


def _ids(pitchers):
    return {pitcher.id for pitcher in pitchers}


def _reason(pitcher):
    return ledger_confirmed_rest.evaluate_unscored_rest(
        [pitcher.id], team_id=TEAM, reference_date=REF,
        ledger_complete=team_operations._appearance_ledger_complete(REF),
    )[pitcher.id]


def _break_ledger():
    """A final game in the ledger window with no appearance rows."""
    for team_id in (TEAM, 147):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=777001, game_date=date(2026, 9, 28),
            status_state=ScheduledGame.STATE_FINAL,
        ))
    db.session.commit()


def test_thresholds_are_unchanged():
    assert (MIN_MEDIUM_USABLE, MAX_MEDIUM_UNRESOLVED) == (6, 2)


# ---------------------------------------------------------------------------
# League-level production regression: 16 active / 13 scored / 3 unscored.
# ---------------------------------------------------------------------------


def test_production_shape_no_longer_fails_for_want_of_a_score(app):
    with app.app_context():
        scored, unscored = _bullpen([_debut, _old_history, _debut])
        assessment = _assess(_ids(scored) | _ids(unscored))
        assert _triple(assessment) == (16, 16, 0)
        assert assessment.confidence == 'high'
        assert {_reason(p) for p in unscored} == {'ledger_confirmed_no_recent_workload'}


def test_production_shape_fails_exactly_as_before_without_the_proof(app, monkeypatch):
    """The before-fix verdict, reproduced by withholding only the new proof."""
    with app.app_context():
        scored, unscored = _bullpen([_debut, _old_history, _debut])
        monkeypatch.setattr(
            ledger_confirmed_rest, 'ledger_confirmed_rest_ids',
            lambda *args, **kwargs: frozenset(),
        )
        assessment = _assess(_ids(scored) | _ids(unscored))
        assert _triple(assessment) == (16, 13, 3)
        assert (assessment.confidence, assessment.data_state) == ('low', 'incomplete')


def test_three_genuinely_unresolved_arms_still_fail(app):
    """13 usable + 3 real unresolved: the bar still refuses, unchanged."""
    with app.app_context():
        scored, _ = _bullpen([])
        unresolved = []
        for index in range(3):
            pitcher = _pitcher(f'failed_{index}')
            db.session.add(SyncFailure(
                job_name='daily_sync', entity_type='pitcher_game_logs',
                entity_ref=str(pitcher.mlb_id), error='ReadTimeout', resolved=False,
            ))
            unresolved.append(pitcher)
        db.session.commit()
        assessment = _assess(_ids(scored) | _ids(unresolved))
        assert _triple(assessment) == (16, 13, 3)
        assert (assessment.confidence, assessment.data_state) == ('low', 'incomplete')


def test_two_unresolved_and_one_confirmed_is_medium(app):
    with app.app_context():
        scored, unscored = _bullpen([_debut])
        recent = [_pitcher(f'recent_unscored_{i}') for i in range(2)]
        for pitcher in recent:
            _log(pitcher, date(2026, 9, 26))
        db.session.commit()
        assessment = _assess(_ids(scored) | _ids(unscored) | _ids(recent))
        assert _triple(assessment) == (16, 14, 2)
        assert assessment.confidence == 'medium'


# ---------------------------------------------------------------------------
# Per-arm cases A-J.
# ---------------------------------------------------------------------------


def test_case_a_and_c_no_history_arms_are_usable_without_a_score(app):
    with app.app_context():
        scored, unscored = _bullpen([_debut, _debut])
        assessment = _assess(_ids(scored) | _ids(unscored))
        assert _triple(assessment) == (15, 15, 0)
        # No score or record was fabricated for them.
        for pitcher in unscored:
            assert FatigueScore.query.filter_by(pitcher_id=pitcher.id).count() == 0
        rows = latest_fatigue_rows(team_id=TEAM)
        assert _ids(unscored).isdisjoint({pitcher.id for _score, pitcher in rows})


def test_case_b_old_appearance_is_not_treated_as_recent(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_old_history])
        assert _reason(arm) == 'ledger_confirmed_no_recent_workload'
        assert _triple(_assess(_ids(scored) | {arm.id})) == (14, 14, 0)
        latest = db.session.query(db.func.max(GameLog.game_date)).filter(
            GameLog.pitcher_id == arm.id,
        ).scalar()
        assert latest == date(2024, 9, 16)


def test_case_d_incomplete_ledger_keeps_unscored_arms_unresolved(app):
    with app.app_context():
        scored, unscored = _bullpen([_debut, _old_history, _debut])
        _break_ledger()
        assert team_operations._appearance_ledger_complete(REF) is False
        assert {_reason(p) for p in unscored} == {'appearance_ledger_incomplete'}
        assessment = _assess(_ids(scored) | _ids(unscored))
        # Stale scored arms also lose ledger rest: 10 fresh of 16.
        assert _triple(assessment) == (16, 10, 6)
        assert assessment.confidence == 'low'


def test_case_d_a_partially_processed_game_breaks_the_ledger_too(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        game_pk = 777002
        db.session.add(ScheduledGame(
            team_id=147, game_pk=game_pk, game_date=date(2026, 9, 27),
            status_state=ScheduledGame.STATE_FINAL,
        ))
        other = _pitcher('other_club_arm', team_id=147)
        db.session.add(GameLog(
            pitcher_id=other.id, mlb_game_pk=game_pk, game_date=date(2026, 9, 27),
            innings_pitched=1.0, innings_pitched_outs=3, pitches_thrown=12,
        ))
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk, game_date=date(2026, 9, 27),
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
            pitching_lines_seen=5,
        ))
        db.session.commit()
        assert _reason(arm) == 'appearance_ledger_incomplete'
        # Stale scored arms lose ledger rest with it: only the 10 fresh remain.
        assert _triple(_assess(_ids(scored) | {arm.id}))[1] == 10


def test_case_e_open_fetch_failure_keeps_the_arm_unresolved(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type='pitcher_game_logs',
            entity_ref=str(arm.mlb_id), error='ReadTimeout', resolved=False,
        ))
        db.session.commit()
        assert _reason(arm) == 'workload_fetch_failure_open'
        assert _triple(_assess(_ids(scored) | {arm.id})) == (14, 13, 1)


def test_case_e_a_resolved_fetch_failure_does_not_block(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        db.session.add(SyncFailure(
            job_name='daily_sync', entity_type='pitcher_game_logs',
            entity_ref=str(arm.mlb_id), error='ReadTimeout', resolved=True,
        ))
        db.session.commit()
        assert _reason(arm) == 'ledger_confirmed_no_recent_workload'


def test_case_f_recent_appearance_with_incomplete_workload_stays_unresolved(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        _log(arm, date(2026, 9, 28), pitches=None)
        db.session.commit()
        assert _reason(arm) == 'window_game_log_incomplete'
        assert _triple(_assess(_ids(scored) | {arm.id})) == (14, 13, 1)


def test_case_f_recent_complete_appearance_without_a_score_stays_unresolved(app):
    """Recent workload that was never modeled is not rest."""
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        _log(arm, date(2026, 9, 20), pitches=22)
        db.session.commit()
        assert _reason(arm) == 'recent_appearance_unscored'
        assert _triple(_assess(_ids(scored) | {arm.id})) == (14, 13, 1)


def test_the_active_window_edge_matches_the_stale_rule(app):
    """An appearance exactly ACTIVE_WINDOW_DAYS back is fresh, not rest."""
    with app.app_context():
        scored, (edge, beyond) = _bullpen([_debut, _debut])
        _log(edge, date(2026, 9, 16))
        _log(beyond, date(2026, 9, 15))
        db.session.commit()
        assert _reason(edge) == 'recent_appearance_unscored'
        assert _reason(beyond) == 'ledger_confirmed_no_recent_workload'


def test_case_g_debut_call_up_counts_for_coverage_but_gains_no_read(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        assert _reason(arm) == 'ledger_confirmed_no_recent_workload'
        records = classify_latest_fatigue_rows(
            latest_fatigue_rows(team_id=TEAM), reference_date=REF,
        )
        assert arm.id not in {record['pitcher'].id for record in records}


def test_case_h_il_return_gains_nothing_from_the_roster_transition(app):
    with app.app_context():
        scored, _ = _bullpen([])
        rested = _pitcher('il_return_rested')
        rested.roster_status = 'ACTIVE'
        _log(rested, date(2026, 8, 20))
        recent = _pitcher('il_return_recent')
        recent.roster_status = 'ACTIVE'
        _log(recent, date(2026, 9, 24), pitches=None, outs=0)
        db.session.commit()
        assert _reason(rested) == 'ledger_confirmed_no_recent_workload'
        assert _reason(recent) == 'window_game_log_incomplete'
        assert _triple(_assess(_ids(scored) | {rested.id, recent.id})) == (15, 14, 1)


def test_case_i_uncertain_roster_authority_fails_closed(app):
    with app.app_context():
        scored, unscored = _bullpen([_debut, _debut])
        assessment = _assess(_ids(scored) | _ids(unscored), authority_complete=False)
        assert assessment.confidence == 'unknown'


@pytest.mark.parametrize('kwargs, reason', [
    ({'assignment': 'UNKNOWN'}, 'team_assignment_unconfirmed'),
    ({'assignment': None}, 'team_assignment_unconfirmed'),
    ({'team_id': 147}, 'pitcher_other_team'),
    ({'active': False}, 'pitcher_inactive'),
])
def test_case_i_uncertain_arm_evidence_fails_closed(app, kwargs, reason):
    with app.app_context():
        scored, _ = _bullpen([])
        arm = _pitcher('uncertain', **kwargs)
        db.session.commit()
        assert _reason(arm) == reason
        assert _triple(_assess(_ids(scored) | {arm.id})) == (14, 13, 1)


@pytest.mark.parametrize('state', [
    ScheduledGame.STATE_SUSPENDED, ScheduledGame.STATE_OTHER, ScheduledGame.STATE_SCHEDULED,
])
def test_an_unsettled_team_game_keeps_unscored_arms_unresolved(app, state):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        db.session.add(ScheduledGame(
            team_id=TEAM, game_pk=778001, game_date=date(2026, 9, 27),
            status_state=state,
        ))
        db.session.commit()
        assert _reason(arm) == 'team_game_not_final'
        assert _triple(_assess(_ids(scored) | {arm.id})) == (14, 13, 1)


def test_settled_and_upcoming_team_games_do_not_block(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_debut])
        db.session.add(ScheduledGame(
            team_id=TEAM, game_pk=778002, game_date=date(2026, 9, 26),
            status_state=ScheduledGame.STATE_POSTPONED,
        ))
        db.session.add(ScheduledGame(
            team_id=TEAM, game_pk=778003, game_date=REF,
            status_state=ScheduledGame.STATE_SCHEDULED,
        ))
        db.session.commit()
        assert _reason(arm) == 'ledger_confirmed_no_recent_workload'


def test_case_j_stale_scored_rest_is_unchanged_and_consistent(app):
    with app.app_context():
        scored, (arm,) = _bullpen([_old_history], scored_fresh=5, scored_stale=3)
        members = _ids(scored) | {arm.id}
        assert _triple(_assess(members)) == (9, 9, 0)
        _break_ledger()
        # Both kinds of rest need the same ledger proof, and lose it together.
        assert _triple(_assess(members)) == (9, 5, 4)


def test_the_proof_writes_nothing(app):
    with app.app_context():
        scored, unscored = _bullpen([_debut, _old_history, _debut])
        models = (Pitcher, FatigueScore, GameLog, SyncFailure, ScheduledGame)
        before = {model.__tablename__: model.query.count() for model in models}
        _assess(_ids(scored) | _ids(unscored))
        assert {model.__tablename__: model.query.count() for model in models} == before
