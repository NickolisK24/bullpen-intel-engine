"""Hand-verifiable WP43 editorial ranking fixtures."""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from models.slate_game import SlateGame
from services import slate_editorial_ranker
from services.slate_editorial_ranker import (
    build_named_arms_evidence,
    classify_team_shape,
    load_ranker_config,
    rank_matchup,
    rank_slate,
    validate_fact_claims,
)
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from utils.db import db
import models.prospect  # noqa: F401 - load complete mapper registry


CONFIG = load_ranker_config()


@pytest.fixture
def ranker_app():
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


def arm_logs(pitches=(30, 25, 20), *, dates=('2026-07-17', '2026-07-16', '2026-07-15')):
    rows = []
    for index, (pitch_count, game_date) in enumerate(zip(pitches, dates), start=1):
        pitcher = SimpleNamespace(id=index, mlb_id=1000 + index, full_name=f'Arm {index}')
        rows.append(SimpleNamespace(
            pitcher_id=index,
            pitcher=pitcher,
            game_date=game_date,
            game_type='R',
            games_started=0,
            pitches_thrown=pitch_count,
            innings_pitched_outs=3,
            mlb_game_pk=9000 + index,
        ))
    return rows


def named_evidence(*, share=78.0, total=100, complete=True):
    pitches = [40, 22, 16]
    relievers = []
    for index, pitch_count in enumerate(pitches, start=1):
        relievers.append({
            'player_id': 1000 + index,
            'name': f'Arm {index}',
            'trailing_pitches': pitch_count,
            'workload_share_pct': round(pitch_count / total * 100, 1),
            'last_outing_date': f'2026-07-{18 - index:02d}',
            'last_outing_pitch_count': pitch_count,
            'appearances': [{
                'game_pk': 9000 + index,
                'date': f'2026-07-{18 - index:02d}',
                'pitch_count': pitch_count,
            }],
        })
    return {
        'window_days': 7,
        'total_relief_pitches': total,
        'top_three_share_pct': share,
        'top_relievers': relievers if complete else relievers[:2],
        'complete': complete,
    }


def team(team_id, *, state='stretched', clean=4, share=78.0, total=100,
         complete=True, recent=1, upcoming=3, consecutive=0, freshness='fresh',
         prior=None, rest=0, name=None):
    return {
        'team_id': team_id,
        'team_name': name or f'Team {team_id}',
        'team_abbreviation': f'T{team_id}',
        'bullpen_state': state,
        'clean_option_count': clean,
        'named_arms_evidence': named_evidence(share=share, total=total, complete=complete),
        'recent_games': recent,
        'upcoming_games': upcoming,
        'consecutive_usage_arms': consecutive,
        'data_freshness': {'state': freshness, 'data_through': '2026-07-17'},
        'prior_state': prior,
        'rest_days_accumulated': rest,
    }


def matchup(home, away, *, game_pk=1, schedule='fresh'):
    return {
        'game_pk': game_pk,
        'home_team': home,
        'away_team': away,
        'schedule_freshness': {'state': schedule, 'schedule_data_through': '2026-07-18T10:00:00Z'},
    }


def test_config_is_versioned_and_group_scores_are_capped_without_double_counting():
    candidate = rank_matchup(matchup(
        team(1, state='vulnerable', clean=0, share=100, recent=3, consecutive=3),
        team(2, state='fresh', clean=6, share=45, recent=0),
    ), as_of='2026-07-18T12:00:00')

    assert candidate['score_version'] == 'slate_editorial_v1'
    assert candidate['home_team_story_score'] == 82
    groups = candidate['component_breakdown']['home_team']
    assert groups['current_condition']['score'] == groups['current_condition']['cap'] == 35
    assert groups['evidence_strength']['score'] == groups['evidence_strength']['cap'] == 35
    assert groups['editorial_stakes']['score'] == 12
    assert 'upcoming_density' not in groups['current_condition']['components']


def test_narrow_is_high_concentration_with_low_recent_density_and_separate_stakes_sentence():
    candidate = rank_matchup(matchup(
        team(1, share=78, recent=1, consecutive=0, name='Houston Astros'),
        team(2, state='fresh', clean=6, share=45, recent=1),
    ), as_of='2026-07-18T12:00:00')

    assert candidate['shape'] == 'narrow'
    assert candidate['publishable'] is True
    assert candidate['featured_team']['team_id'] == 1
    assert candidate['plain_one_liner'].startswith("Houston Astros's top three relievers carried 78.0%")
    assert '. With 3 games scheduled' in candidate['plain_one_liner']
    assert 'because' not in candidate['plain_one_liner'].lower()


def test_gassed_requires_recent_density_and_complete_recent_outing_evidence():
    subject = team(1, recent=3, consecutive=2, share=65)
    assert classify_team_shape(subject, CONFIG) == 'gassed'
    subject['named_arms_evidence']['complete'] = False
    assert classify_team_shape(subject, CONFIG) is None


def test_thin_uses_low_clean_options_even_without_concentration_claim():
    subject = team(1, clean=1, share=50, complete=False, recent=0)
    candidate = rank_matchup(matchup(subject, team(2, state='fresh', clean=6, share=45)), as_of='2026-07-18')

    assert candidate['shape'] == 'thin'
    assert candidate['publishable'] is True
    assert '1 clean bullpen option' in candidate['plain_one_liner']
    assert '%' not in candidate['plain_one_liner']


def test_recovered_requires_comparable_fresh_prior_state_and_meaningful_rest():
    prior = {'comparable': True, 'freshness_state': 'fresh', 'bullpen_state': 'vulnerable'}
    subject = team(1, state='fresh', clean=6, share=45, recent=0, prior=prior, rest=2)
    assert classify_team_shape(subject, CONFIG) == 'recovered'


def test_recovered_is_refused_when_history_is_stale():
    prior = {'comparable': True, 'freshness_state': 'stale', 'bullpen_state': 'vulnerable'}
    subject = team(1, state='fresh', clean=6, share=45, recent=0, prior=prior, rest=3)
    assert classify_team_shape(subject, CONFIG) is None


def test_contrast_is_matchup_level_and_identifies_more_constrained_team():
    candidate = rank_matchup(matchup(
        team(1, state='vulnerable', clean=4, share=45, recent=0),
        team(2, state='fresh', clean=6, share=45, recent=0),
    ), as_of='2026-07-18')

    assert candidate['shape'] == 'contrast'
    assert candidate['matchup_contrast_score'] == 12
    assert candidate['featured_team']['team_id'] == 1
    assert candidate['final_editorial_score'] == max(candidate['home_team_story_score'], candidate['away_team_story_score']) + 12


def test_incomplete_named_arms_withholds_concentration_claim_and_candidate():
    subject = team(1, share=85, complete=False, recent=1)
    candidate = rank_matchup(matchup(subject, team(2, state='fresh', clean=6, share=45)), as_of='2026-07-18')

    assert candidate['shape'] is None
    assert candidate['publishable'] is False
    assert 'named_arms_evidence_incomplete' in candidate['withholding_reasons']
    assert candidate['plain_one_liner'] is None


def test_same_team_same_shape_has_stronger_repetition_penalty_than_other_shape():
    base = matchup(team(1, share=78, recent=1), team(2, state='fresh', clean=6, share=45))
    same = rank_matchup(base, history=[{'team_id': 1, 'story_shape': 'narrow', 'posted_at': '2026-07-16'}], as_of='2026-07-18')
    different = rank_matchup(base, history=[{'team_id': 1, 'story_shape': 'thin', 'posted_at': '2026-07-16'}], as_of='2026-07-18')

    same_penalty = same['component_breakdown']['home_team']['editorial_stakes']['components']['repetition_penalty']
    other_penalty = different['component_breakdown']['home_team']['editorial_stakes']['components']['repetition_penalty']
    assert same_penalty == -18
    assert other_penalty == -7
    assert same['home_team_story_score'] < different['home_team_story_score']


def test_no_distinct_signal_is_explicitly_non_publishable():
    candidate = rank_matchup(matchup(
        team(1, state='fresh', clean=6, share=45, recent=0),
        team(2, state='fresh', clean=6, share=45, recent=0),
    ), as_of='2026-07-18')

    assert candidate['shape'] is None
    assert candidate['publishable'] is False
    assert candidate['withholding_reasons'] == ['no_distinct_editorial_signal']


def test_deterministic_ties_use_team_id_then_game_pk():
    tied_a = matchup(team(9, share=78), team(8, share=78), game_pk=20)
    tied_b = matchup(team(7, share=78), team(6, share=78), game_pk=10)
    ranked = rank_slate([tied_a, tied_b], as_of='2026-07-18')

    assert ranked[0]['game_pk'] == 10
    assert rank_matchup(tied_a, as_of='2026-07-18')['featured_team']['team_id'] == 8


def test_named_arms_payload_carries_verified_ids_dates_and_pitch_counts():
    evidence = build_named_arms_evidence(arm_logs(), reference_date='2026-07-18', config=CONFIG)

    assert evidence['complete'] is True
    assert evidence['top_three_share_pct'] == 100.0
    assert evidence['total_relief_pitches'] == 75
    assert evidence['top_relievers'][0] == {
        'player_id': 1001,
        'name': 'Arm 1',
        'trailing_pitches': 30,
        'appearances': [{'game_pk': 9001, 'date': '2026-07-17', 'pitch_count': 30}],
        'workload_share_pct': 40.0,
        'last_outing_date': '2026-07-17',
        'last_outing_pitch_count': 30,
    }


def test_named_arms_payload_fails_closed_on_incomplete_pitch_row():
    logs = arm_logs()
    logs.append(SimpleNamespace(
        pitcher_id=4,
        pitcher=SimpleNamespace(id=4, mlb_id=1004, full_name='Arm 4'),
        game_date='2026-07-17', game_type='R', games_started=0,
        pitches_thrown=None, innings_pitched_outs=3, mlb_game_pk=9004,
    ))
    evidence = build_named_arms_evidence(logs, reference_date='2026-07-18', config=CONFIG)
    assert evidence['complete'] is False
    assert evidence['excluded_incomplete_rows'] == 1


def test_db_assembly_collapses_doubleheader_rows_into_one_matchup(ranker_app, monkeypatch):
    with ranker_app.app_context():
        for game_pk, hour in ((7001, 17), (7002, 23)):
            db.session.add(SlateGame(
                game_pk=game_pk,
                game_date_et=date(2026, 7, 18),
                game_time_utc=datetime(2026, 7, 18, hour),
                home_team_id=1,
                away_team_id=2,
                normalized_state=SlateGame.STATE_UPCOMING,
                doubleheader_flag='Y',
                game_number=1 if game_pk == 7001 else 2,
                last_synced=datetime(2026, 7, 18, 10),
            ))
        db.session.commit()
        monkeypatch.setattr(
            slate_editorial_ranker,
            'build_team_ranking_input',
            lambda team_id, **_kwargs: team(
                team_id,
                share=78 if team_id == 1 else 45,
                state='stretched' if team_id == 1 else 'fresh',
                clean=4 if team_id == 1 else 6,
            ),
        )
        monkeypatch.setattr(
            slate_editorial_ranker,
            'schedule_freshness',
            lambda **_kwargs: {'state': 'fresh'},
        )

        candidates = slate_editorial_ranker.build_ranked_slate(
            '2026-07-18', as_of='2026-07-18T12:00:00',
        )

    assert len(candidates) == 1
    assert candidates[0]['doubleheader'] is True
    assert candidates[0]['game_pks'] == [7001, 7002]


def test_structured_fact_guard_checks_names_dates_counts_percentages_teams_and_matchup():
    candidate = rank_matchup(matchup(
        team(1, share=78, name='Houston Astros'),
        team(2, state='fresh', clean=6, share=45, name='Seattle Mariners'),
    ), as_of='2026-07-18')
    valid = validate_fact_claims({
        'names': ['Arm 1'],
        'dates': ['2026-07-17'],
        'pitch_counts': [40],
        'percentages': [78.0],
        'teams': ['Houston Astros', 'Seattle Mariners'],
        'matchup_team_ids': [1, 2],
    }, candidate)
    invalid = validate_fact_claims({
        'names': ['Invented Reliever'],
        'dates': ['2026-07-01'],
        'pitch_counts': [99],
        'percentages': [91.2],
        'teams': ['New York Yankees'],
        'matchup_team_ids': [3],
    }, candidate)

    assert valid == {'checked': True, 'valid': True, 'violations': []}
    assert invalid['valid'] is False
    assert len(invalid['violations']) == 6


@pytest.mark.parametrize('freshness,reason', [
    ('stale', 'team_data_not_fresh'),
    ('unavailable', 'team_data_not_fresh'),
])
def test_ranker_never_overrides_freshness_refusal(freshness, reason):
    candidate = rank_matchup(matchup(
        team(1, clean=1, freshness=freshness),
        team(2, state='fresh', clean=6, share=45),
    ), as_of='2026-07-18')
    assert candidate['final_editorial_score'] > 0
    assert candidate['publishable'] is False
    assert reason in candidate['withholding_reasons']
