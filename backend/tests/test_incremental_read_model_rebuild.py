"""CU-06 bounded read-model rebuild contracts."""

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.pitcher import Pitcher
from models.slate_game import SlateGame
from services import incremental_read_model_rebuild as cu06
from services import incremental_arm_read_team_state as cu05
from services import incremental_workload_rest as cu04
from services import change_impact_orchestration as orchestration
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import sync as sync_service
from services.incremental_arm_read_team_state import (
    IncrementalArmReadTeamStateResult,
)
from services.incremental_workload_rest import PARITY_MATCH, PARITY_NOT_COMPARABLE
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import schedule_final_game
from tests.test_continuous_reliever_ingestion import (
    AWAY_TEAM,
    GAME_DATE,
    GAME_PK,
    HOME_TEAM,
    _boxscore,
    _play_by_play,
    _seed_pitchers,
)
from tests.test_game_change_detection import _feed
from tests.test_incremental_arm_read_team_state import _fake_provider
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


def _cu05(*, teams=(10, 20), pitchers=(1, 2), performed=True):
    status = 'complete' if performed else 'no_action'
    return IncrementalArmReadTeamStateResult(
        game_pk=777001,
        data_through='2026-07-14',
        availability_reference_date='2026-07-15',
        status=status,
        reason_code='parity_match' if performed else 'no_action',
        requested_pitcher_ids=tuple(pitchers),
        requested_team_ids=tuple(teams),
        arm_reads_recomputed=tuple(pitchers) if performed else (),
        teams_recomputed=tuple(teams) if performed else (),
        arm_read_results={pitcher_id: {'pitcher_id': pitcher_id} for pitcher_id in pitchers},
        team_state_results={
            team_id: {
                'team_id': team_id,
                'public_team_state': {
                    'available': True,
                    'state': 'Fresh',
                    'data_through': '2026-07-14',
                },
            }
            for team_id in teams
        },
        parity_status=PARITY_MATCH if performed else PARITY_NOT_COMPARABLE,
        recomputation_performed=performed,
    )


def _snapshot(team_ids=(10, 20, 30)):
    return SimpleNamespace(
        id=44,
        sync_run_id=45,
        data_through=date(2026, 7, 14),
        availability_reference_date=date(2026, 7, 15),
        snapshot_generated_at=datetime(2026, 7, 15, 4, 0, 0),
        payload={
            'freshness': {'data_through': '2026-07-14'},
            'trusted_team_boards': {
                'contract': cu06.public_serving_authority.TEAM_BOARD_PACKAGE_CONTRACT,
                'data_through': '2026-07-14',
                'availability_reference_date': '2026-07-15',
                'by_team_id': {
                    str(team_id): {
                        'team': {
                            'team_id': team_id,
                            'team_name': f'Team {team_id}',
                            'team_abbreviation': f'T{team_id}',
                        },
                        'records': [],
                        'default_pitcher_ids': [],
                        'roster_authority': {},
                    }
                    for team_id in team_ids
                },
            },
        },
    )


def _builders(calls):
    def board(team_id, snapshot, state):
        calls.append(('board', team_id))
        return {
            'team_id': team_id,
            'team_state': deepcopy(state),
            'represented_date': snapshot.data_through.isoformat(),
            'generated_at': f'incidental-{len(calls)}',
        }

    def listing(_snapshot, states):
        calls.append(('league', None))
        return {
            'teams': [
                {
                    'team_id': team_id,
                    'team_name': f'Team {team_id}',
                    'team_abbreviation': f'T{team_id}',
                    'team_state': deepcopy(state.get('public_team_state') or state),
                }
                for team_id, state in sorted(states.items())
            ]
        }

    def matchup(game, _snapshot, states):
        calls.append(('matchup', game.game_pk))
        return {
            'game_pk': game.game_pk,
            'teams': [game.away_team_id, game.home_team_id],
            'states': deepcopy(states),
        }

    def tonight(game, _snapshot, states, _records, _listing):
        calls.append(('tonight', game.game_pk))
        return {
            'games': [{
                'game_pk': game.game_pk,
                'away': {'team_state': deepcopy(states.get(game.away_team_id))},
                'home': {'team_state': deepcopy(states.get(game.home_team_id))},
            }]
        }
    return board, listing, matchup, tonight


def _seed_game():
    game = SlateGame(
        game_pk=777001,
        game_date_et=date(2026, 7, 14),
        game_time_utc=datetime(2026, 7, 14, 23, 10),
        home_team_id=20,
        away_team_id=10,
        normalized_state=SlateGame.STATE_COMPLETED,
    )
    db.session.add(game)
    db.session.commit()
    return game


def test_untrusted_or_noop_cu05_performs_zero_cu06_work(app):
    with app.app_context():
        calls = []
        builders = _builders(calls)
        result = cu06.rebuild_read_model_impact(
            _cu05(performed=False), source_snapshot=_snapshot(),
            team_board_builder=builders[0], league_listing_builder=builders[1],
            matchup_builder=builders[2], tonight_builder=builders[3],
        )
        assert result.status == cu06.STATUS_NO_ACTION
        assert result.rebuild_performed is False
        assert result.team_boards_rebuilt == ()
        assert calls == []


def test_rebuild_is_bounded_deduplicated_and_matches(app):
    with app.app_context():
        _seed_game()
        calls = []
        builders = _builders(calls)
        source = _cu05(teams=(20, 10, 20), pitchers=(2, 1, 2))
        result = cu06.rebuild_read_model_impact(
            source, source_snapshot=_snapshot(),
            team_board_builder=builders[0], league_listing_builder=builders[1],
            matchup_builder=builders[2], tonight_builder=builders[3],
        )
        assert result.status == 'complete'
        assert result.parity_status == PARITY_MATCH
        assert result.requested_team_ids == (10, 20)
        assert result.requested_pitcher_ids == (1, 2)
        assert result.team_boards_rebuilt == (10, 20)
        assert result.league_rows_rebuilt == (10, 20)
        assert result.matchups_rebuilt == (777001,)
        assert result.tonight_entries_rebuilt == (777001,)
        assert result.pitcher_models_rebuilt == ()
        assert calls.count(('matchup', 777001)) == 2  # rebuild + parity
        assert calls.count(('tonight', 777001)) == 2


def test_incidental_metadata_is_excluded_but_baseball_values_are_not(app):
    with app.app_context():
        _seed_game()
        calls = []
        board, listing, matchup, tonight = _builders(calls)
        result = cu06.rebuild_read_model_impact(
            _cu05(), source_snapshot=_snapshot(),
            team_board_builder=board, league_listing_builder=listing,
            matchup_builder=matchup, tonight_builder=tonight,
        )
        assert result.parity_status == PARITY_MATCH
        assert all(
            entry['status'] == PARITY_MATCH
            for entry in result.parity_entries
        )


def test_unrelated_team_and_unrelated_game_are_not_rebuilt(app):
    with app.app_context():
        _seed_game()
        calls = []
        builders = _builders(calls)
        result = cu06.rebuild_read_model_impact(
            _cu05(teams=(30,), pitchers=()), source_snapshot=_snapshot(),
            team_board_builder=builders[0], league_listing_builder=builders[1],
            matchup_builder=builders[2], tonight_builder=builders[3],
        )
        assert result.team_boards_rebuilt == (30,)
        assert result.league_rows_rebuilt == (30,)
        assert result.matchups_rebuilt == ()
        assert result.tonight_entries_rebuilt == ()
        assert not any(call[0] in ('matchup', 'tonight') for call in calls)


def test_builder_failure_is_partial_and_never_publishes(app):
    with app.app_context():
        calls = []
        _board, listing, _matchup, _tonight = _builders(calls)
        result = cu06.rebuild_read_model_impact(
            _cu05(teams=(10,), pitchers=()), source_snapshot=_snapshot(),
            team_board_builder=lambda *_args: (_ for _ in ()).throw(RuntimeError()),
            league_listing_builder=listing,
        )
        assert result.status == cu06.STATUS_PARTIAL
        assert result.publication_affected is False
        assert result.cache_invalidation_triggered is False
        assert result.scheduling_affected is False
        assert result.frontend_affected is False
        assert result.what_changed_generated is False


def test_direct_rebuild_is_deterministic_across_fresh_service_calls(app):
    with app.app_context():
        _seed_game()
        builders = _builders([])
        kwargs = dict(
            source_snapshot=_snapshot(),
            team_board_builder=builders[0], league_listing_builder=builders[1],
            matchup_builder=builders[2], tonight_builder=builders[3],
        )
        first = cu06.rebuild_read_model_impact(_cu05(), **kwargs)
        second = cu06.rebuild_read_model_impact(_cu05(), **kwargs)
        assert cu06._semantic(first.team_board_results) == cu06._semantic(
            second.team_board_results
        )
        assert first.league_row_results == second.league_row_results
        assert first.matchup_results == second.matchup_results
        assert first.tonight_results == second.tonight_results


def test_shadow_snapshot_overlays_only_affected_team_and_pitcher(app):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=880001, full_name='Affected Arm', team_id=10,
            team_name='Team 10', team_abbreviation='T10', position='P',
            active=True,
        )
        db.session.add(pitcher)
        db.session.flush()
        snapshot = _snapshot()
        snapshot.payload['trusted_team_boards']['by_team_id']['10'].update({
            'records': [{
                'pitcher_id': pitcher.id,
                'name': pitcher.full_name,
                'availability': {'availability_status': 'Available'},
                'workload_facts': {'pitches_last_7_days': 18},
                'visibility': {'is_visible_by_default': True},
            }],
            'default_pitcher_ids': [pitcher.id],
        })
        source = _cu05(teams=(10,), pitchers=(pitcher.id,))
        source = IncrementalArmReadTeamStateResult(
            **{
                **source.__dict__,
                'availability_results': {
                    pitcher.id: {'availability_status': 'Monitor'},
                },
                'workload_rest_pitcher_results': {
                    pitcher.id: {
                        'fatigue_workload': {'pitches_last_7_days': 32},
                        'rest_workload_inputs': {'fatigue_score': 44.0},
                    },
                },
            }
        )
        before = deepcopy(snapshot.payload)
        shadow = cu06.build_shadow_snapshot(snapshot, source)
        changed = shadow.payload['trusted_team_boards']['by_team_id']['10']['records'][0]
        assert changed['availability']['availability_status'] == 'Monitor'
        assert changed['workload_facts']['pitches_last_7_days'] == 32
        assert snapshot.payload == before
        assert shadow.payload['trusted_team_boards']['by_team_id']['30'] == (
            snapshot.payload['trusted_team_boards']['by_team_id']['30']
        )


def test_position_player_is_not_given_a_pitcher_read_model(app):
    with app.app_context():
        position_player = Pitcher(
            mlb_id=880099, full_name='Utility Player', team_id=10,
            team_name='Team 10', team_abbreviation='T10', position='2B',
            active=True,
        )
        db.session.add(position_player)
        db.session.commit()
        calls = []
        builders = _builders(calls)
        result = cu06.rebuild_read_model_impact(
            _cu05(teams=(10,), pitchers=(position_player.id,)),
            source_snapshot=_snapshot(),
            team_board_builder=builders[0], league_listing_builder=builders[1],
        )
        assert result.pitcher_models_rebuilt == ()
        assert position_player.position == '2B'


def test_shadow_result_has_hard_stop_flags(app):
    with app.app_context():
        calls = []
        builders = _builders(calls)
        result = cu06.rebuild_read_model_impact(
            _cu05(teams=(10,), pitchers=()), source_snapshot=_snapshot(),
            team_board_builder=builders[0], league_listing_builder=builders[1],
        )
        assert result.publication_affected is False
        assert result.cache_invalidation_triggered is False
        assert result.scheduling_affected is False
        assert result.frontend_affected is False
        assert result.what_changed_generated is False
        assert result.downstream_triggered is False


def test_strongest_cu02_through_cu06_chain_rebuilds_then_stops(app, monkeypatch):
    class Client:
        def get_game_boxscore(self, game_pk):
            assert game_pk == GAME_PK
            return _boxscore()

        def get_game_play_by_play(self, game_pk):
            assert game_pk == GAME_PK
            return _play_by_play()

    def observation(*, timestamp, status='Live', code='I', inning=8, outs=1):
        payload = deepcopy(_feed(
            timestamp=timestamp, status=status, code=code,
            inning=inning, outs=outs,
        ))
        payload['gamePk'] = GAME_PK
        payload['gameData']['datetime'].update({
            'dateTime': f'{GAME_DATE.isoformat()}T19:00:00Z',
            'originalDate': GAME_DATE.isoformat(),
            'officialDate': GAME_DATE.isoformat(),
        })
        payload['gameData']['teams'] = {
            'away': {'id': AWAY_TEAM}, 'home': {'id': HOME_TEAM},
        }
        return payload

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(GAME_PK, game_date=GAME_DATE)
        monkeypatch.setattr(sync_service, 'mlb_client', Client())
        detection.observe_game_change(
            GAME_PK, payload=observation(timestamp='20260827_220000'),
        )
        changed = detection.observe_game_change(
            GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        reviewed = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[GAME_PK],
        )
        canonical = orchestration.orchestrate_game_change(
            changed,
            allow_canonical_write=True,
            expected_plan_fingerprint=reviewed[
                'complete_reconciliation_fingerprint'
            ],
        )
        workload = cu04.recompute_workload_rest_impact(
            canonical, data_through=GAME_DATE,
        )
        active_by_team = {
            team_id: frozenset(
                pitcher_id
                for pitcher_id in canonical.affected_pitcher_ids
                if db.session.get(Pitcher, pitcher_id).team_id == team_id
            )
            for team_id in canonical.affected_team_ids
        }
        state = cu05.recompute_arm_reads_team_state(
            workload,
            readiness_provider=_fake_provider(),
            membership_provider=lambda team_id, _date: (
                active_by_team.get(team_id, frozenset()),
                bool(active_by_team.get(team_id)),
            ),
        )
        game = SlateGame(
            game_pk=GAME_PK,
            game_date_et=GAME_DATE,
            game_time_utc=datetime.combine(GAME_DATE, datetime.min.time()),
            home_team_id=HOME_TEAM,
            away_team_id=AWAY_TEAM,
            normalized_state=SlateGame.STATE_COMPLETED,
        )
        db.session.merge(game)
        db.session.commit()
        calls = []
        builders = _builders(calls)
        snapshot = _snapshot(team_ids=(AWAY_TEAM, HOME_TEAM, 30))
        snapshot.data_through = GAME_DATE
        snapshot.availability_reference_date = (
            date.fromisoformat(state.availability_reference_date)
        )
        snapshot.payload['freshness']['data_through'] = GAME_DATE.isoformat()
        snapshot.payload['trusted_team_boards']['data_through'] = GAME_DATE.isoformat()
        snapshot.payload['trusted_team_boards']['availability_reference_date'] = (
            state.availability_reference_date
        )
        result = cu06.rebuild_read_model_impact(
            state,
            source_snapshot=snapshot,
            team_board_builder=builders[0],
            league_listing_builder=builders[1],
            matchup_builder=builders[2],
            tonight_builder=builders[3],
        )

        assert canonical.game_log_inserted == 4
        assert canonical.pitch_inserted == 4
        assert workload.parity_status == PARITY_MATCH
        assert state.parity_status == PARITY_MATCH
        assert result.parity_status == PARITY_MATCH
        assert result.team_boards_rebuilt == tuple(
            sorted(canonical.affected_team_ids)
        )
        assert result.league_rows_rebuilt == tuple(
            sorted(canonical.affected_team_ids)
        )
        assert result.matchups_rebuilt == (GAME_PK,)
        assert result.tonight_entries_rebuilt == (GAME_PK,)
        assert result.publication_affected is False
        assert result.cache_invalidation_triggered is False


def test_controlled_correction_changes_only_requested_read_models(app):
    with app.app_context():
        calls = []
        builders = _builders(calls)
        before = _cu05(teams=(10,), pitchers=(1,))
        corrected_projection = deepcopy(before.team_state_results)
        corrected_projection[10]['public_team_state']['state'] = 'Vulnerable'
        after = IncrementalArmReadTeamStateResult(
            **{**before.__dict__, 'team_state_results': corrected_projection}
        )
        kwargs = dict(
            source_snapshot=_snapshot(),
            team_board_builder=builders[0],
            league_listing_builder=builders[1],
        )
        first = cu06.rebuild_read_model_impact(before, **kwargs)
        second = cu06.rebuild_read_model_impact(after, **kwargs)
        assert first.team_board_results[10] != second.team_board_results[10]
        assert first.league_row_results[10] != second.league_row_results[10]
        assert 30 not in first.team_board_results
        assert 30 not in second.team_board_results
        assert first.parity_status == second.parity_status == PARITY_MATCH


def test_cu06_source_has_no_publication_cache_or_scheduler_calls():
    source = Path(cu06.__file__).read_text(encoding='utf-8')
    forbidden_calls = (
        'publish_snapshot(', 'publish_share_artifact(', 'invalidate_cache(',
        'run_daily_sync(', 'serve_tonight_cached(', 'while True',
    )
    assert [token for token in forbidden_calls if token in source] == []


def test_existing_board_and_matchup_builders_accept_shadow_overrides():
    from services.current_bullpen_comparison import build_current_bullpen_comparison
    from tests.test_current_bullpen_comparison import _snapshot as comparison_snapshot

    snapshot = comparison_snapshot()
    states = {
        1: {
            'available': True, 'state': 'Fresh', 'public_label': 'Fresh',
            'contract': 'team-state-v1', 'data_through': '2026-08-24',
        },
        2: {
            'available': True, 'state': 'Stretched', 'public_label': 'Stretched',
            'contract': 'team-state-v1', 'data_through': '2026-08-24',
        },
    }
    board = cu06.public_serving_authority.build_published_team_board(
        1, snapshot_override=snapshot, team_state_override=states[1],
    )
    comparison, reason = build_current_bullpen_comparison(
        snapshot, 1, 2, team_state_overrides=states,
    )
    assert board['team_state'] == states[1]
    assert reason is None
    assert comparison['domains']['team_state']['team_a'] == states[1]
    assert comparison['domains']['team_state']['team_b'] == states[2]
