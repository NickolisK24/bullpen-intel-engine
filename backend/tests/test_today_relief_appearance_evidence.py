"""Focused contract tests for transient Today relief-appearance evidence."""

from datetime import date

import pytest
from flask import Flask
from sqlalchemy import event, update

import models.dashboard_snapshot  # noqa: F401  (complete schema FK registry)
import models.prospect  # noqa: F401  (register the full model graph)
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import (
    GamePlayByPlayEvent,
    PlayByPlayProcessedGame,
)
from services.today_relief_appearance_evidence import (
    enrich_today_contexts_with_relief_appearances,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db


@pytest.fixture
def app():
    test_app = Flask(__name__)
    configure_test_database(test_app)
    db.init_app(test_app)
    with test_app.app_context():
        create_test_schema(test_app)
        try:
            yield test_app
        finally:
            db.session.remove()
            drop_test_schema(test_app)


def _pitcher(mlb_id, name, *, current_team_id=999):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=current_team_id,
        team_abbreviation='TST',
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _log(
    pitcher,
    *,
    game_pk,
    appearance_team_id,
    appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
    games_started=0,
    outs=3,
    pitches=12,
    runs=0,
):
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=date(2026, 8, 31),
        game_type='R',
        games_started=games_started,
        innings_pitched=outs / 3.0,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        runs_allowed=runs,
        appearance_team_id=appearance_team_id,
        appearance_team_status=appearance_team_status,
        appearance_team_source='test_official_game_side',
    )
    db.session.add(log)
    db.session.flush()
    if runs is None:
        # The model's insert default is zero, while the persisted column remains
        # nullable.  Force a real unknown official value for fail-closed proof.
        db.session.execute(
            update(GameLog)
            .where(GameLog.id == log.id)
            .values(runs_allowed=None)
        )
        db.session.expire(log, ['runs_allowed'])
    return log


def _processed_game(game_pk, *, team_id=137, opponent_id=147, events_count=4):
    marker = PlayByPlayProcessedGame(
        mlb_game_pk=game_pk,
        game_date=date(2026, 8, 31),
        game_type='R',
        home_team_id=team_id,
        away_team_id=opponent_id,
        final_state='Final',
        processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
        attempt_count=1,
        events_seen=events_count,
        events_stored=events_count,
        pitcher_events_seen=2,
        unresolved_pitcher_count=0,
        reconciliation_mismatch_count=0,
        event_fingerprint=f'pbp-{game_pk}',
        source='test_final_play_by_play',
        source_endpoint=f'/api/v1.1/game/{game_pk}/feed/live',
    )
    db.session.add(marker)
    return marker


def _event(
    game_pk,
    event_index,
    *,
    team_id=137,
    opponent_id=147,
    pitcher=None,
    home_score,
    away_score,
    inning,
    scoring=False,
    fielding_team_id=None,
):
    fielding_team_id = team_id if fielding_team_id is None else fielding_team_id
    row = GamePlayByPlayEvent(
        mlb_game_pk=game_pk,
        event_index=event_index,
        source_play_id=f'play-{game_pk}-{event_index}',
        at_bat_index=event_index,
        game_date=date(2026, 8, 31),
        game_type='R',
        home_team_id=team_id,
        away_team_id=opponent_id,
        event_type='scoring_play' if scoring else 'plate_appearance',
        event_type_code='single' if scoring else 'field_out',
        inning=inning,
        half_inning='top' if fielding_team_id == team_id else 'bottom',
        is_top_inning=fielding_team_id == team_id,
        outs_at_event=1,
        home_score_at_event=home_score,
        away_score_at_event=away_score,
        pitcher_mlb_id=pitcher.mlb_id if pitcher is not None else None,
        pitcher_id=pitcher.id if pitcher is not None else None,
        batter_mlb_id=800000 + event_index,
        batting_team_id=opponent_id if fielding_team_id == team_id else team_id,
        fielding_team_id=fielding_team_id,
        is_pitching_change=False,
        is_scoring_play=scoring,
        is_mound_visit=False,
        source='test_final_play_by_play',
        source_endpoint=f'/api/v1.1/game/{game_pk}/feed/live',
    )
    db.session.add(row)
    return row


def _late_pressure_fixture(game_pk=9071):
    first = _pitcher(707001, 'Seventh Inning Reliever')
    second = _pitcher(707002, 'Eighth Inning Reliever')
    _log(first, game_pk=game_pk, appearance_team_id=137, runs=1)
    _log(second, game_pk=game_pk, appearance_team_id=137, runs=3)
    _processed_game(game_pk)
    _event(
        game_pk, 0, home_score=3, away_score=0, inning=6,
        fielding_team_id=147, scoring=True,
    )
    _event(
        game_pk, 1, pitcher=first, home_score=3, away_score=1,
        inning=7, scoring=True,
    )
    _event(
        game_pk, 2, home_score=5, away_score=1, inning=7,
        fielding_team_id=147, scoring=True,
    )
    _event(
        game_pk, 3, pitcher=second, home_score=5, away_score=4,
        inning=8, scoring=True,
    )
    return first, second, {
        'team_id': 137,
        'game_pk': game_pk,
        'game_date': date(2026, 8, 31),
        'home_away': 'home',
        'bullpen_story_tag': 'late_pressure_accumulated',
        'final_score_for': 5,
        'final_score_against': 4,
        'late_runs_allowed': 4,
        'runs_allowed_innings_7_to_9': 4,
        'turning_inning': None,
    }


def test_batch_enriches_exact_game_team_pairs_in_stable_order(app):
    lower_id = _pitcher(700001, 'First Reliever', current_team_id=888)
    higher_id = _pitcher(700002, 'Second Reliever', current_team_id=777)
    other_side = _pitcher(700003, 'Other Side Reliever', current_team_id=137)

    # Insert in reverse MLB-id order; the result is stable by official identity,
    # not insertion order or mutable current team.
    _log(
        higher_id,
        game_pk=9001,
        appearance_team_id=137,
        outs=3,
        pitches=11,
        runs=None,
    )
    _log(
        lower_id,
        game_pk=9001,
        appearance_team_id=137,
        outs=6,
        pitches=24,
        runs=2,
    )
    _log(
        other_side,
        game_pk=9002,
        appearance_team_id=147,
        outs=3,
        pitches=9,
        runs=0,
    )
    db.session.commit()

    contexts = [
        {
            'team_id': 137,
            'game_pk': 9001,
            'bullpen_story_tag': 'bullpen_overexposed',
            'marker': 'first',
            'key_relief_appearances': [{'name': 'Untrusted Existing Value'}],
        },
        {
            'team_id': 147,
            'game_pk': 9002,
            'bullpen_story_tag': 'protected_game_shape',
            'marker': 'second',
        },
    ]
    original_first_evidence = list(contexts[0]['key_relief_appearances'])

    statements = []

    def _capture_statement(conn, cursor, statement, parameters, context, executemany):
        if 'game_logs' in statement.lower() and statement.lstrip().lower().startswith('select'):
            statements.append(statement)

    event.listen(db.engine, 'before_cursor_execute', _capture_statement)
    try:
        enriched = enrich_today_contexts_with_relief_appearances(contexts)
    finally:
        event.remove(db.engine, 'before_cursor_execute', _capture_statement)

    assert len(statements) == 1
    assert [item['marker'] for item in enriched] == ['first', 'second']
    assert [
        item['pitcher_mlb_id']
        for item in enriched[0]['key_relief_appearances']
    ] == [700001, 700002]
    assert enriched[0]['key_relief_appearances'] == [
        {
            'pitcher_id': lower_id.id,
            'pitcher_mlb_id': 700001,
            'name': 'First Reliever',
            'game_pk': 9001,
            'appearance_team_id': 137,
            'innings': 2.0,
            'innings_pitched_outs': 6,
            'pitches_thrown': 24,
            'runs_allowed': 2,
            'claim_evidence_role': 'claim_supporting_relief_participant',
        },
        {
            'pitcher_id': higher_id.id,
            'pitcher_mlb_id': 700002,
            'name': 'Second Reliever',
            'game_pk': 9001,
            'appearance_team_id': 137,
            'innings': 1.0,
            'innings_pitched_outs': 3,
            'pitches_thrown': 11,
            'runs_allowed': None,
            'claim_evidence_role': 'claim_supporting_relief_participant',
        },
    ]
    assert [
        item['name'] for item in enriched[1]['key_relief_appearances']
    ] == ['Other Side Reliever']
    assert contexts[0]['key_relief_appearances'] == original_first_evidence
    assert enriched[0] is not contexts[0]


def test_lost_game_uses_exact_lead_loss_event_not_aggregate_run_lines(app):
    earlier = _pitcher(705001, 'Earlier Run Reliever')
    decisive = _pitcher(705002, 'Lead Loss Reliever')
    scoreless = _pitcher(705003, 'Scoreless Reliever')
    _log(earlier, game_pk=9051, appearance_team_id=137, runs=1)
    # The on-mound pitcher can have a scoreless charged line when inherited
    # runners score.  Event linkage, not aggregate runs_allowed, owns the claim.
    _log(decisive, game_pk=9051, appearance_team_id=137, runs=0)
    _log(scoreless, game_pk=9051, appearance_team_id=137, runs=0)
    _processed_game(9051)
    # The team first builds a 4-0 lead.  An earlier run does not erase it;
    # only event 3 crosses from 4-1 to 4-5 and is therefore claim-driving.
    _event(
        9051, 0, home_score=0, away_score=0, inning=1,
        fielding_team_id=147,
    )
    _event(
        9051, 1, home_score=4, away_score=0, inning=5,
        fielding_team_id=147, scoring=True,
    )
    _event(
        9051, 2, pitcher=earlier, home_score=4, away_score=1,
        inning=7, scoring=True,
    )
    _event(
        9051, 3, pitcher=decisive, home_score=4, away_score=5,
        inning=8, scoring=True,
    )
    db.session.commit()

    enriched, unsupported = enrich_today_contexts_with_relief_appearances([
        {
            'team_id': 137,
            'game_pk': 9051,
            'game_date': date(2026, 8, 31),
            'home_away': 'home',
            'bullpen_story_tag': 'lost_game_shape',
            'final_score_for': 4,
            'final_score_against': 5,
            'late_runs_allowed': 5,
            'runs_allowed_innings_7_to_9': 5,
            'turning_inning': 8,
        },
        {
            'team_id': 137,
            'game_pk': 9051,
            'bullpen_story_tag': 'insufficient_context',
        },
    ])

    assert [
        item['name'] for item in enriched['key_relief_appearances']
    ] == ['Lead Loss Reliever']
    receipt = enriched['key_relief_appearances'][0]
    assert receipt['claim_evidence_role'] == 'claim_scoring_event_pitcher'
    assert receipt['claim_event_indexes'] == [3]
    assert receipt['claim_event_innings'] == [8]
    assert receipt['claim_source_play_ids'] == ['play-9051-3']
    assert unsupported['key_relief_appearances'] == []


def test_negative_claim_without_fully_processed_pbp_fails_closed(app):
    pitcher = _pitcher(706001, 'Aggregate Line Only')
    _log(pitcher, game_pk=9061, appearance_team_id=137, runs=4)
    db.session.commit()

    [enriched] = enrich_today_contexts_with_relief_appearances([{
        'team_id': 137,
        'game_pk': 9061,
        'bullpen_story_tag': 'lost_game_shape',
    }])

    assert enriched['key_relief_appearances'] == []


def test_late_pressure_requires_two_exact_relief_scoring_innings(app):
    _first, _second, context = _late_pressure_fixture()
    db.session.commit()

    [enriched] = enrich_today_contexts_with_relief_appearances([context])

    receipts = enriched['key_relief_appearances']
    assert [item['name'] for item in receipts] == [
        'Seventh Inning Reliever',
        'Eighth Inning Reliever',
    ]
    assert [item['claim_event_indexes'] for item in receipts] == [[1], [3]]
    assert all(
        item['claim_evidence_role'] == 'claim_scoring_event_pitcher'
        for item in receipts
    )


def test_late_pressure_with_one_unresolved_driver_fails_as_a_whole(app):
    _first, second, context = _late_pressure_fixture(game_pk=9072)
    GameLog.query.filter_by(
        pitcher_id=second.id,
        mlb_game_pk=9072,
    ).delete(synchronize_session=False)
    db.session.commit()

    [enriched] = enrich_today_contexts_with_relief_appearances([context])

    assert enriched['key_relief_appearances'] == []


def test_scoring_event_link_rejects_stale_completed_context_facts(app):
    _first, _second, context = _late_pressure_fixture(game_pk=9073)
    context['late_runs_allowed'] = 3
    db.session.commit()

    [enriched] = enrich_today_contexts_with_relief_appearances([context])

    assert enriched['key_relief_appearances'] == []


def test_excludes_starts_unknown_roles_and_unresolved_or_wrong_identity_rows(app):
    starter = _pitcher(710001, 'Starter', current_team_id=137)
    unknown_role = _pitcher(710002, 'Unknown Role', current_team_id=137)
    wrong_team = _pitcher(710003, 'Wrong Team', current_team_id=137)
    wrong_game = _pitcher(710004, 'Wrong Game', current_team_id=137)
    unresolved = _pitcher(710005, 'Unresolved', current_team_id=137)

    _log(starter, game_pk=9101, appearance_team_id=137, games_started=1)
    _log(unknown_role, game_pk=9101, appearance_team_id=137, games_started=None)
    _log(wrong_team, game_pk=9101, appearance_team_id=147)
    _log(wrong_game, game_pk=9102, appearance_team_id=137)
    _log(
        unresolved,
        game_pk=9101,
        appearance_team_id=None,
        appearance_team_status=GameLog.APPEARANCE_TEAM_UNRESOLVED,
    )
    db.session.commit()

    [enriched] = enrich_today_contexts_with_relief_appearances([
        {'team_id': 137, 'game_pk': 9101}
    ])

    assert enriched['key_relief_appearances'] == []


def test_missing_context_identity_fails_closed_and_non_dicts_are_rejected(app):
    contexts = [
        {'team_id': 137},
        {'game_pk': 9201},
        {'team_id': '137', 'game_pk': 9201},
        {},
    ]

    enriched = enrich_today_contexts_with_relief_appearances(contexts)

    assert len(enriched) == 4
    assert all(item['key_relief_appearances'] == [] for item in enriched)
    assert all(item is not source for item, source in zip(enriched, contexts))
    with pytest.raises(TypeError, match='context dictionaries'):
        enrich_today_contexts_with_relief_appearances([None])
