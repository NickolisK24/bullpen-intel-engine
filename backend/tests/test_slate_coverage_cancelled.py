"""Authoritatively cancelled games are terminal, never-played slate exclusions.

Production parity: 2026-09-27 had 15 scheduled games; 14 were final and fully
ingested and game 823490 (teams 110 / 147) was cancelled by MLB (statusCode
``CR``, stored ``status_state='other'``). Slate coverage treated that ``other``
as a non-final game, so every candidate for the date was withheld with
``dashboard_snapshot_slate_coverage_incomplete``. A cancellation is excluded
only on positive schedule evidence; ``other`` alone keeps blocking.
"""

from datetime import date, datetime

import pytest

from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.slate_game import SlateGame
from services import dashboard_snapshot, slate_coverage
from services.game_finality import classify_status, normalize_schedule_status_state
from services.slate_coverage import is_cancelled_status
from tests.test_slate_coverage import _marker, _schedule_game, app  # noqa: F401
from utils.db import db


SLATE = date(2026, 9, 27)
CANCELLED_PK = 823490
CANCELLED_STATUS = {
    'statusCode': 'CR',
    'detailedState': 'Cancelled',
    'abstractGameState': 'Final',
}


def _slate_game(game_pk, *, code, detailed, abstract='Final', home_id=110, away_id=147):
    db.session.add(SlateGame(
        game_pk=game_pk,
        game_date_et=SLATE,
        game_time_utc=datetime(2026, 9, 27, 19, 10),
        home_team_id=home_id,
        away_team_id=away_id,
        status_abstract=abstract,
        status_detailed=detailed,
        status_code=code,
        normalized_state='cancelled',
    ))


def _final_slate(count=14, *, start=820000):
    for offset in range(count):
        _schedule_game(start + offset, SLATE, status='final', status_code='F')
        _marker(start + offset, SLATE)


def _cancelled_game(game_pk=CANCELLED_PK, *, status=CANCELLED_STATUS, slate=True):
    _schedule_game(
        game_pk, SLATE,
        status=normalize_schedule_status_state({'status': status}),
        status_code=status.get('statusCode'),
        home_id=110, away_id=147,
    )
    if slate:
        _slate_game(
            game_pk,
            code=status.get('statusCode'),
            detailed=status.get('detailedState'),
            abstract=status.get('abstractGameState'),
        )


def _gate_reason(coverage):
    return dashboard_snapshot._payload_slate_coverage_unavailable_reason({
        'freshness': {
            'data_through': SLATE.isoformat(),
            'availability_reference_date': '2026-09-28',
            'slate_coverage': coverage,
        },
    })


def _coverage():
    return slate_coverage.compute_slate_coverage(
        SLATE, publication_critical_complete=True, include_diagnostics=True,
    )


# ── Canonical semantics ─────────────────────────────────────────────────────

def test_cancellation_is_classified_by_the_shared_finality_authority():
    assert is_cancelled_status(CANCELLED_STATUS) is True
    assert is_cancelled_status({'statusCode': 'C'}) is True
    # Stored as 'other': cancelled is terminal but never final.
    assert normalize_schedule_status_state({'status': CANCELLED_STATUS}) == 'other'
    assert classify_status(CANCELLED_STATUS).final_status is False
    for status in (
        {'statusCode': 'CR'},  # a bare code this repo has never canonicalized
        {'statusCode': 'I', 'detailedState': 'In Progress', 'abstractGameState': 'Live'},
        {'statusCode': 'S', 'detailedState': 'Scheduled', 'abstractGameState': 'Preview'},
        {'statusCode': 'DR', 'detailedState': 'Postponed', 'abstractGameState': 'Final'},
        {'statusCode': 'U', 'detailedState': 'Suspended', 'abstractGameState': 'Live'},
        {'statusCode': 'F', 'detailedState': 'Final', 'abstractGameState': 'Final'},
        {},
        None,
    ):
        assert is_cancelled_status(status) is False, status


# ── Production parity: 14 final + game 823490 cancelled ─────────────────────

def test_production_parity_14_final_plus_cancelled_823490_is_complete(app):
    with app.app_context():
        _final_slate()
        _cancelled_game()
        db.session.commit()
        rows = ScheduledGame.query.filter_by(game_pk=CANCELLED_PK).all()
        assert {(row.team_id, row.opponent_team_id) for row in rows} == {(110, 147), (147, 110)}
        assert {(row.status_code, row.status_state) for row in rows} == {('CR', 'other')}

        coverage = _coverage()

    assert coverage['coverage_known'] is True
    assert coverage['games_scheduled'] == 15
    assert coverage['games_final'] == 14
    assert coverage['games_cancelled'] == 1
    assert coverage['cancelled_game_pks'] == [CANCELLED_PK]
    assert coverage['games_included'] == 14
    assert coverage['games_fully_ingested'] == 14
    assert coverage['games_incomplete'] == 0
    assert coverage['games_postponed'] == 0
    assert coverage['games_suspended'] == 0
    assert coverage['validations_passed'] is True
    assert coverage['complete_enough_to_publish'] is True
    assert coverage['reason_codes'] == ['slate_complete', 'cancelled_games_excluded']
    assert coverage['diagnostics']['non_final_game_count'] == 0
    assert coverage['diagnostics']['cancelled_game_pks'] == [CANCELLED_PK]
    assert _gate_reason(coverage) is None


def test_cancelled_game_is_counted_as_cancelled_never_as_final(app):
    with app.app_context():
        _final_slate(2)
        _cancelled_game()
        db.session.commit()
        coverage = _coverage()
        # No marker, game log or final state is fabricated for the cancelled game.
        assert PostgameProcessedGame.query.filter_by(mlb_game_pk=CANCELLED_PK).count() == 0
        assert {
            row.status_state
            for row in ScheduledGame.query.filter_by(game_pk=CANCELLED_PK)
        } == {'other'}

    assert coverage['games_final'] == 2
    assert coverage['games_cancelled'] == 1
    assert coverage['marker_counts'] == {
        'fully_processed': 2, 'incomplete': 0, 'failed': 0, 'missing': 0,
    }


def test_canonical_cancelled_code_alone_is_accepted(app):
    status = {'statusCode': 'C'}
    with app.app_context():
        _final_slate(3)
        _cancelled_game(status=status)
        db.session.commit()
        coverage = _coverage()
    assert coverage['games_cancelled'] == 1
    assert coverage['complete_enough_to_publish'] is True


def test_canonical_cancelled_detailed_state_is_accepted(app):
    status = {'statusCode': 'CR', 'detailedState': 'Cancelled'}
    with app.app_context():
        _final_slate(3)
        _cancelled_game(status=status)
        db.session.commit()
        coverage = _coverage()
    assert coverage['games_cancelled'] == 1
    assert coverage['complete_enough_to_publish'] is True


def test_multiple_cancelled_games_are_each_excluded(app):
    with app.app_context():
        _final_slate(5)
        _cancelled_game(CANCELLED_PK)
        _cancelled_game(CANCELLED_PK + 1)
        db.session.commit()
        coverage = _coverage()
    assert coverage['games_cancelled'] == 2
    assert coverage['cancelled_game_pks'] == [CANCELLED_PK, CANCELLED_PK + 1]
    assert coverage['games_final'] == 5
    assert coverage['games_included'] == 5
    assert coverage['complete_enough_to_publish'] is True


def test_stale_marker_on_a_cancelled_game_does_not_affect_the_result(app):
    with app.app_context():
        _final_slate(3)
        _cancelled_game()
        _marker(CANCELLED_PK, SLATE, status=PostgameProcessedGame.STATUS_FAILED)
        db.session.commit()
        coverage = _coverage()
    assert coverage['games_cancelled'] == 1
    assert coverage['games_failed'] == 0
    assert coverage['marker_counts']['failed'] == 0
    assert coverage['complete_enough_to_publish'] is True


# ── Negative: the gate is not weakened ─────────────────────────────────────

def _assert_blocks(coverage):
    assert coverage['games_cancelled'] == 0
    assert coverage['validations_passed'] is False
    assert coverage['complete_enough_to_publish'] is False
    assert 'cancelled_games_excluded' not in coverage['reason_codes']
    assert _gate_reason(coverage) == 'dashboard_snapshot_slate_coverage_incomplete'


@pytest.mark.parametrize('status', [
    # 'other' without any cancellation evidence (unknown code, no detail)
    {'statusCode': 'CR'},
    {'statusCode': 'ZZ', 'detailedState': 'Unknown', 'abstractGameState': 'Final'},
    # live / in progress also stores as 'other'
    {'statusCode': 'I', 'detailedState': 'In Progress', 'abstractGameState': 'Live'},
    {'statusCode': 'MA', 'detailedState': 'Manager challenge', 'abstractGameState': 'Live'},
])
def test_noncancelled_other_still_blocks(app, status):
    with app.app_context():
        _final_slate(3)
        _cancelled_game(status=status)
        db.session.commit()
        assert {
            row.status_state for row in ScheduledGame.query.filter_by(game_pk=CANCELLED_PK)
        } == {'other'}
        coverage = _coverage()
    _assert_blocks(coverage)
    assert 'scheduled_games_not_final' in coverage['reason_codes']
    assert coverage['diagnostics']['non_final_game_count'] == 1


def test_cancelled_scheduled_rows_without_slate_game_evidence_block(app):
    with app.app_context():
        _final_slate(3)
        _cancelled_game(slate=False)
        db.session.commit()
        coverage = _coverage()
    _assert_blocks(coverage)


def test_cancelled_free_text_with_disagreeing_status_code_blocks(app):
    with app.app_context():
        _final_slate(3)
        _schedule_game(CANCELLED_PK, SLATE, status='other', status_code='I',
                       home_id=110, away_id=147)
        _slate_game(CANCELLED_PK, code='CR', detailed='Cancelled')
        db.session.commit()
        coverage = _coverage()
    _assert_blocks(coverage)


def test_reciprocal_rows_that_disagree_block(app):
    with app.app_context():
        _final_slate(3)
        db.session.add_all([
            ScheduledGame(team_id=110, opponent_team_id=147, home_away='home',
                          game_pk=CANCELLED_PK, game_date=SLATE,
                          status_code='CR', status_state='other'),
            ScheduledGame(team_id=147, opponent_team_id=110, home_away='away',
                          game_pk=CANCELLED_PK, game_date=SLATE,
                          status_code='F', status_state='final'),
        ])
        _slate_game(CANCELLED_PK, code='CR', detailed='Cancelled')
        db.session.commit()
        coverage = _coverage()
    _assert_blocks(coverage)


def test_unresolved_resumed_linkage_is_never_excused_as_cancelled(app):
    with app.app_context():
        _final_slate(3)
        _schedule_game(CANCELLED_PK, SLATE, status='other', status_code='CR',
                       home_id=110, away_id=147, resumed_to_game_pk=999999)
        _slate_game(CANCELLED_PK, code='CR', detailed='Cancelled')
        db.session.commit()
        coverage = _coverage()
    # resumed_to without a resumed date is unresolved linkage: it keeps blocking.
    assert coverage['games_unresolved'] == 1
    _assert_blocks(coverage)
    assert 'resumed_linkage_unresolved' in coverage['reason_codes']


@pytest.mark.parametrize('state,reason', [
    ('suspended', 'suspended_games_not_final'),
    ('scheduled', 'scheduled_games_not_final'),
])
def test_suspended_and_scheduled_still_block_even_with_cancelled_detail(app, state, reason):
    with app.app_context():
        _final_slate(3)
        _schedule_game(CANCELLED_PK, SLATE, status=state, status_code='CR',
                       home_id=110, away_id=147)
        _slate_game(CANCELLED_PK, code='CR', detailed='Cancelled')
        db.session.commit()
        coverage = _coverage()
    _assert_blocks(coverage)
    assert reason in coverage['reason_codes']


def test_postponed_exclusion_is_unchanged(app):
    with app.app_context():
        _final_slate(3)
        _schedule_game(CANCELLED_PK, SLATE, status='postponed', status_code='DR',
                       home_id=110, away_id=147)
        db.session.commit()
        coverage = _coverage()
    assert coverage['games_postponed'] == 1
    assert coverage['games_cancelled'] == 0
    assert coverage['games_included'] == 3
    assert coverage['reason_codes'] == ['slate_complete']
    assert coverage['complete_enough_to_publish'] is True


@pytest.mark.parametrize('marker_status', [
    PostgameProcessedGame.STATUS_FAILED,
    PostgameProcessedGame.STATUS_INCOMPLETE,
    None,  # missing
])
def test_final_game_marker_rules_are_unchanged_alongside_a_cancellation(app, marker_status):
    with app.app_context():
        _final_slate(3)
        _schedule_game(830001, SLATE, status='final', status_code='F')
        if marker_status is not None:
            _marker(830001, SLATE, status=marker_status)
        _cancelled_game()
        db.session.commit()
        coverage = _coverage()
    assert coverage['games_cancelled'] == 1
    assert coverage['validations_passed'] is False
    assert coverage['complete_enough_to_publish'] is False
    assert _gate_reason(coverage) == 'dashboard_snapshot_slate_coverage_incomplete'


def test_missing_schedule_evidence_still_blocks(app):
    with app.app_context():
        coverage = slate_coverage.compute_slate_coverage(
            SLATE, publication_critical_complete=True,
            schedule_material_available=False,
        )
    assert coverage['complete_enough_to_publish'] is False
    assert coverage['games_cancelled'] == 0
    assert _gate_reason(coverage) == 'dashboard_snapshot_slate_coverage_incomplete'


def test_the_rule_is_date_and_team_agnostic(app):
    other_date = date(2026, 5, 12)
    with app.app_context():
        _schedule_game(1, other_date, status='final', status_code='F',
                       home_id=121, away_id=143)
        _marker(1, other_date)
        _schedule_game(2, other_date, status='other', status_code='CR',
                       home_id=158, away_id=133)
        db.session.add(SlateGame(
            game_pk=2, game_date_et=other_date,
            game_time_utc=datetime(2026, 5, 12, 23, 5),
            home_team_id=158, away_team_id=133,
            status_abstract='Final', status_detailed='Cancelled', status_code='CR',
            normalized_state='cancelled',
        ))
        db.session.commit()
        coverage = slate_coverage.compute_slate_coverage(
            other_date, publication_critical_complete=True,
        )
    assert coverage['games_cancelled'] == 1
    assert coverage['complete_enough_to_publish'] is True
