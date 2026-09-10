"""CU-04 bounded workload/rest recomputation and parity contracts."""

from copy import deepcopy
from datetime import date
from pathlib import Path

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import change_impact_orchestration as orchestration
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import game_finality
from services import incremental_workload_rest as cu04
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import schedule_final_game
from tests.test_change_impact_orchestration import _change
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
from utils.db import db


DATA_THROUGH = date(2026, 9, 30)


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


def _seed_pitcher(
    mlb_id, name, team_id, *, position='P', active=True,
):
    pitcher = Pitcher(
        mlb_id=mlb_id,
        full_name=name,
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position=position,
        active=active,
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def _seed_log(
    pitcher,
    game_pk,
    game_date,
    *,
    team_id,
    pitches=18,
    outs=3,
    games_started=0,
):
    log = GameLog(
        pitcher_id=pitcher.id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        games_started=games_started,
        innings_pitched=outs / 3.0,
        innings_pitched_outs=outs,
        pitches_thrown=pitches,
        appearance_team_id=team_id,
        appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        appearance_team_source='controlled_official_game_side',
        appearance_team_reason='controlled_proof',
    )
    db.session.add(log)
    return log


def _impact(*, pitchers=(), teams=(), mutated=True, optional='fully_processed'):
    return orchestration.ChangeImpactResult(
        game_pk=GAME_PK,
        detection_classification=detection.FINALIZED,
        decision=orchestration.INGEST_FINAL_GAME,
        orchestration_status=orchestration.STATUS_RECONCILED,
        reason_code='cu01_canonical_reconciliation_complete',
        canonical_action_attempted=True,
        canonical_ingestion_mode='cu01_write_non_authoritative',
        cu01_invocations=1,
        finality_state=game_finality.FINAL_AND_USABLE,
        canonical_mutation_performed=mutated,
        affected_pitcher_ids=tuple(pitchers),
        affected_team_ids=tuple(teams),
        optional_pbp_status=optional,
    )


def test_no_canonical_mutation_performs_zero_derived_work(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            cu04, '_compute_pitcher_workload_rest',
            lambda *args, **kwargs: pytest.fail('pitcher recomputation ran'),
        )
        monkeypatch.setattr(
            cu04, 'author_workload_windows',
            lambda *args, **kwargs: pytest.fail('team recomputation ran'),
        )
        result = cu04.recompute_workload_rest_impact(
            _impact(mutated=False), data_through=DATA_THROUGH,
        )

        assert result.status == cu04.STATUS_NO_ACTION
        assert result.pitchers_recomputed == ()
        assert result.teams_recomputed == ()
        assert result.recomputation_performed is False
        assert result.downstream_recomputation_triggered is False
        assert result.publication_affected is False


def test_recomputes_only_mutation_scoped_pitcher_and_historical_team(app):
    with app.app_context():
        changed = _seed_pitcher(1001, 'Changed Arm', 999)
        unrelated = _seed_pitcher(1002, 'Unrelated Arm', 20)
        _seed_log(changed, 1, DATA_THROUGH, team_id=10, pitches=19)
        _seed_log(unrelated, 2, DATA_THROUGH, team_id=20, pitches=40)
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(changed.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )

        assert result.status == cu04.STATUS_COMPLETE
        assert result.pitchers_recomputed == (changed.id,)
        assert result.teams_recomputed == (10,)
        assert unrelated.id not in result.pitcher_results
        assert 20 not in result.team_results
        assert result.team_results[10]['windows']['window_7']['pitches_total'] == 19
        assert result.parity_status == cu04.PARITY_MATCH
        assert result.parity_mismatches == ()


def test_represented_date_split_matches_current_authority(app):
    with app.app_context():
        pitcher = _seed_pitcher(1101, 'Date Split', 10)
        _seed_log(pitcher, 11, DATA_THROUGH, team_id=10)
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )

        assert result.data_through == '2026-09-30'
        assert result.availability_reference_date == '2026-10-01'
        pitcher_result = result.pitcher_results[pitcher.id]
        assert pitcher_result['rest_workload_inputs']['days_rest'] == 1
        assert pitcher_result['rest_workload_inputs']['pitches_yesterday'] == 18
        assert result.team_results[10]['windows']['window_7']['through'] == '2026-09-30'


@pytest.mark.parametrize(
    ('game_date', 'expected_pitcher_7', 'expected_team_7', 'expected_14'),
    [
        (date(2026, 9, 24), 1, 1, 1),
        (date(2026, 9, 23), 0, 0, 1),
        (date(2026, 9, 17), 0, 0, 1),
        (date(2026, 9, 16), 0, 0, 0),
    ],
)
def test_exact_rolling_window_boundaries(
    app, game_date, expected_pitcher_7, expected_team_7, expected_14,
):
    with app.app_context():
        pitcher = _seed_pitcher(
            1200 + game_date.day, f'Boundary {game_date.day}', 10,
        )
        _seed_log(pitcher, 1200 + game_date.day, game_date, team_id=10)
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )
        fatigue = result.pitcher_results[pitcher.id]['fatigue_workload']
        team = result.team_results[10]['windows']

        assert fatigue['appearances_last_7'] == expected_pitcher_7
        assert fatigue['appearances_last_14'] == expected_14
        assert team['window_7']['relief_appearances'] == expected_team_7
        assert team['window_14']['relief_appearances'] == expected_14


def test_rest_patterns_and_doubleheader_follow_existing_rules(app):
    with app.app_context():
        pitcher = _seed_pitcher(1301, 'Pattern Arm', 10)
        dates = (
            date(2026, 9, 30), date(2026, 9, 30),
            date(2026, 9, 29), date(2026, 9, 28), date(2026, 9, 27),
        )
        for index, represented in enumerate(dates):
            _seed_log(
                pitcher, 1300 + index, represented, team_id=10, pitches=10,
            )
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )
        inputs = result.pitcher_results[pitcher.id]['rest_workload_inputs']

        assert inputs['days_rest'] == 1
        assert inputs['back_to_back'] is True
        assert inputs['three_in_four'] is True
        assert inputs['four_in_five'] is True
        assert inputs['appearances_last_3_days'] == 3
        assert inputs['appearances_last_5_days'] == 5


def test_unknown_pitch_count_remains_unknown(app):
    with app.app_context():
        pitcher = _seed_pitcher(1401, 'Unknown Pitches', 10)
        _seed_log(
            pitcher, 1401, DATA_THROUGH, team_id=10, pitches=None, outs=3,
        )
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )
        pitcher_result = result.pitcher_results[pitcher.id]

        assert pitcher_result['fatigue_workload']['pitches_last_7_days'] is None
        assert pitcher_result['rest_workload_inputs']['pitches_yesterday'] is None
        assert result.team_results[10]['windows']['window_7']['pitches_total'] is None


@pytest.mark.parametrize(
    ('last_date', 'expected_days_rest'),
    [
        (date(2026, 9, 30), 1),
        (date(2026, 9, 29), 2),
        (date(2026, 9, 27), 4),
    ],
)
def test_days_rest_and_off_day_semantics(app, last_date, expected_days_rest):
    with app.app_context():
        pitcher = _seed_pitcher(
            1450 + last_date.day, f'Rest {last_date.day}', 10,
        )
        _seed_log(
            pitcher, 1450 + last_date.day, last_date, team_id=10,
        )
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )

        assert result.pitcher_results[pitcher.id]['rest_workload_inputs'][
            'days_rest'
        ] == expected_days_rest


def test_no_prior_appearance_remains_unknown_not_rested(app):
    with app.app_context():
        pitcher = _seed_pitcher(1499, 'No Prior Appearance', 10)
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=()),
            data_through=DATA_THROUGH,
        )
        inputs = result.pitcher_results[pitcher.id]['rest_workload_inputs']

        assert inputs['days_rest'] is None
        assert inputs['latest_game_date'] is None
        assert inputs['freshness_state'] == 'missing'


def test_controlled_correction_changes_only_requested_scope(app):
    with app.app_context():
        pitcher = _seed_pitcher(1501, 'Corrected Arm', 10)
        unrelated = _seed_pitcher(1502, 'Stable Arm', 20)
        corrected = _seed_log(
            pitcher, 1501, DATA_THROUGH, team_id=10, pitches=18,
        )
        _seed_log(unrelated, 1502, DATA_THROUGH, team_id=20, pitches=30)
        db.session.commit()
        impact = _impact(pitchers=(pitcher.id,), teams=(10,))

        before = cu04.recompute_workload_rest_impact(
            impact, data_through=DATA_THROUGH,
        )
        corrected.pitches_thrown = 19
        db.session.commit()
        after = cu04.recompute_workload_rest_impact(
            impact, data_through=DATA_THROUGH,
        )

        assert (
            after.pitcher_results[pitcher.id]['fatigue_workload']['pitches_last_7_days']
            - before.pitcher_results[pitcher.id]['fatigue_workload']['pitches_last_7_days']
        ) == 1
        assert (
            after.team_results[10]['windows']['window_7']['pitches_total']
            - before.team_results[10]['windows']['window_7']['pitches_total']
        ) == 1
        assert unrelated.id not in after.pitcher_results
        assert 20 not in after.team_results


def test_position_player_pitching_does_not_rewrite_current_identity(app):
    with app.app_context():
        player = _seed_pitcher(
            1601, 'Position Player', 20, position='CF', active=True,
        )
        _seed_log(player, 1601, DATA_THROUGH, team_id=10, pitches=12)
        db.session.commit()
        before = (player.team_id, player.position, player.active)

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(player.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )
        db.session.refresh(player)

        assert result.pitchers_recomputed == (player.id,)
        assert result.team_results[10]['windows']['window_7']['relief_appearances'] == 1
        assert (player.team_id, player.position, player.active) == before


def test_optional_pbp_failure_does_not_block_core_workload(app):
    with app.app_context():
        pitcher = _seed_pitcher(1701, 'Core Facts', 10)
        _seed_log(pitcher, 1701, DATA_THROUGH, team_id=10, pitches=22)
        db.session.commit()

        result = cu04.recompute_workload_rest_impact(
            _impact(
                pitchers=(pitcher.id,), teams=(10,), optional='incomplete',
            ),
            data_through=DATA_THROUGH,
        )

        assert result.status == cu04.STATUS_COMPLETE
        assert result.parity_status == cu04.PARITY_MATCH
        assert result.pitcher_results[pitcher.id]['fatigue_workload'][
            'pitches_last_7_days'
        ] == 22


def test_shadow_recompute_writes_no_fatigue_snapshot_or_public_state(app):
    with app.app_context():
        pitcher = _seed_pitcher(1801, 'Pure Result', 10)
        _seed_log(pitcher, 1801, DATA_THROUGH, team_id=10)
        sentinel = DashboardSnapshot(
            snapshot_type='cu04_sentinel', status='ready', is_published=False,
            payload={'immutable': True}, data_through=DATA_THROUGH,
        )
        db.session.add(sentinel)
        db.session.commit()
        sentinel_id = sentinel.id

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=(10,)),
            data_through=DATA_THROUGH,
        )

        assert FatigueScore.query.count() == 0
        assert DashboardSnapshot.query.count() == 1
        stored = db.session.get(DashboardSnapshot, sentinel_id)
        assert stored.payload == {'immutable': True}
        assert stored.is_published is False
        assert result.team_state_recomputed is False
        assert result.read_models_rebuilt is False
        assert result.publication_affected is False
        assert result.cache_invalidation_triggered is False


def test_direct_recompute_is_deterministic_after_session_restart(app):
    with app.app_context():
        pitcher = _seed_pitcher(1851, 'Restart Arm', 10)
        _seed_log(pitcher, 1851, DATA_THROUGH, team_id=10, pitches=21)
        db.session.commit()
        impact = _impact(pitchers=(pitcher.id,), teams=(10,))

        before = cu04.recompute_workload_rest_impact(
            impact, data_through=DATA_THROUGH,
        )
        db.session.remove()
        after = cu04.recompute_workload_rest_impact(
            impact, data_through=DATA_THROUGH,
        )

        assert after.pitcher_results == before.pitcher_results
        assert after.team_results == before.team_results
        assert after.parity_entries == before.parity_entries
        assert after.parity_status == cu04.PARITY_MATCH


def test_parity_mismatch_is_explicit_and_partial(app):
    with app.app_context():
        pitcher = _seed_pitcher(1901, 'Mismatch Proof', 10)
        _seed_log(pitcher, 1901, DATA_THROUGH, team_id=10)
        db.session.commit()

        def mismatching_provider(pitcher_id, **kwargs):
            value = cu04._compute_pitcher_workload_rest(pitcher_id, **kwargs)
            value['fatigue_workload']['appearances_last_7'] += 1
            return value

        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(pitcher.id,), teams=()),
            data_through=DATA_THROUGH,
            authoritative_pitcher_provider=mismatching_provider,
        )

        assert result.status == cu04.STATUS_PARTIAL
        assert result.parity_status == cu04.PARITY_MISMATCH
        assert [row['field'] for row in result.parity_mismatches] == [
            'fatigue_workload.appearances_last_7'
        ]


def test_bounded_failure_is_structured_and_stops(app):
    with app.app_context():
        result = cu04.recompute_workload_rest_impact(
            _impact(pitchers=(999999,), teams=()),
            data_through=DATA_THROUGH,
        )

        assert result.status == cu04.STATUS_PARTIAL
        assert result.parity_status == cu04.PARITY_NOT_COMPARABLE
        assert result.failures == ({
            'scope': 'pitcher', 'entity_id': 999999, 'error': 'LookupError',
        },)
        assert result.downstream_recomputation_triggered is False


def test_explicit_represented_date_is_required_when_work_is_needed(app):
    with app.app_context():
        with pytest.raises(ValueError, match='explicit represented baseball date'):
            cu04.recompute_workload_rest_impact(
                _impact(pitchers=(1,), teams=()), data_through=None,
            )


def test_strongest_cu02_cu03_cu01_cu04_finality_chain(app, monkeypatch):
    class Client:
        def get_game_boxscore(self, game_pk):
            assert game_pk == GAME_PK
            return _boxscore()

        def get_game_play_by_play(self, game_pk):
            assert game_pk == GAME_PK
            return _play_by_play()

    with app.app_context():
        _seed_pitchers()
        schedule_final_game(GAME_PK, game_date=GAME_DATE)
        monkeypatch.setattr(sync_service, 'mlb_client', Client())

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

        detection.observe_game_change(
            GAME_PK, payload=observation(timestamp='20260827_220000'),
        )
        change = detection.observe_game_change(
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
            change,
            allow_canonical_write=True,
            expected_plan_fingerprint=reviewed[
                'complete_reconciliation_fingerprint'
            ],
        )
        cu04_calls = []

        def route_derived(impact):
            if not impact.canonical_mutation_performed:
                return None
            cu04_calls.append(impact.game_pk)
            return cu04.recompute_workload_rest_impact(
                impact, data_through=GAME_DATE,
            )

        derived = route_derived(canonical)

        assert canonical.game_log_inserted == 4
        assert canonical.pitch_inserted == 4
        assert len(canonical.affected_pitcher_ids) == 2
        assert canonical.affected_team_ids == (AWAY_TEAM, HOME_TEAM)
        assert derived.pitchers_recomputed == canonical.affected_pitcher_ids
        assert derived.teams_recomputed == canonical.affected_team_ids
        assert derived.parity_status == cu04.PARITY_MATCH
        assert derived.parity_mismatches == ()
        assert derived.team_state_recomputed is False
        assert derived.publication_affected is False

        db.session.remove()
        unchanged = detection.observe_game_change(
            GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        replay = orchestration.orchestrate_game_change(
            unchanged,
            allow_canonical_write=True,
            expected_plan_fingerprint='must-not-be-used',
            canonical_ingestor=lambda *args, **kwargs: pytest.fail(
                'CU-01 must not run for unchanged observation'
            ),
        )
        after_restart = route_derived(replay)

        assert replay.cu01_invocations == 0
        assert after_restart is None
        assert cu04_calls == [GAME_PK]


def test_cu04_source_and_entrypoint_are_non_scheduled_and_non_publishing():
    source = cu04.__file__
    text = open(source, encoding='utf-8').read()
    forbidden = (
        'TeamState', 'team_state_engine', 'publish_snapshot',
        'invalidate_cache', 'while True', 'apscheduler', 'run_daily_sync',
    )
    assert [token for token in forbidden if token in text] == []

    scripts = [
        (
            Path(__file__).resolve().parents[1]
            / 'scripts/prove_incremental_workload_rest.py'
        ).read_text(encoding='utf-8'),
        (
            Path(__file__).resolve().parents[1]
            / 'scripts/run_cu04_proof.py'
        ).read_text(encoding='utf-8'),
    ]
    assert scripts[0].index("os.environ['AUTO_SYNC'] = 'false'") < scripts[0].index(
        'from app import app'
    )
    assert '--data-through' in scripts[0]
    for script in scripts:
        assert 'while True' not in script
        assert 'apscheduler' not in script.lower()
