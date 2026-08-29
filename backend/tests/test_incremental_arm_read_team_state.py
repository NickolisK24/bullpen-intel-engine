"""CU-05 bounded Arm Read and Team State parity contracts."""

from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

import pytest
from flask import Flask

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.dashboard_snapshot import DashboardSnapshot
from models.game_log import GameLog
from models.pitcher import Pitcher
from services import incremental_arm_read_team_state as cu05
from services import incremental_workload_rest as cu04
from services import change_impact_orchestration as orchestration
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import sync as sync_service
from services.availability import classify_availability, classify_availability_inputs
from services.availability_reference_date import product_current_date
from services.pitcher_public_labels import build_public_arm_read
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.test_active_bullpen_readiness_resolver import TEAM_ID, _seed_team
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


def _cu04_result(*, pitchers=(), teams=(), pitcher_results=None, performed=True):
    represented = product_current_date() - timedelta(days=1)
    return cu04.IncrementalWorkloadRestResult(
        game_pk=99001,
        data_through=represented.isoformat(),
        availability_reference_date=(represented + timedelta(days=1)).isoformat(),
        status=cu04.STATUS_COMPLETE if performed else cu04.STATUS_NO_ACTION,
        reason_code='parity_match' if performed else 'no_canonical_mutation',
        requested_pitcher_ids=tuple(pitchers),
        requested_team_ids=tuple(teams),
        pitchers_recomputed=tuple(pitchers) if performed else (),
        teams_recomputed=tuple(teams) if performed else (),
        pitcher_results=pitcher_results or {},
        parity_status=cu04.PARITY_MATCH if performed else cu04.PARITY_NOT_COMPARABLE,
        recomputation_performed=performed,
    )


def _fake_workload(pitcher_id, *, pitches=18, freshness='fresh'):
    represented = product_current_date() - timedelta(days=1)
    days_rest = 5 if pitches == 0 else 1
    return {
        'pitcher_id': pitcher_id,
        'data_through': represented.isoformat(),
        'availability_reference_date': product_current_date().isoformat(),
        'fatigue_workload': {},
        'rest_workload_inputs': {
            'fatigue_score': 20.0,
            'fatigue_risk_level': 'LOW',
            'pitches_yesterday': pitches,
            'pitches_last_3_days': pitches,
            'pitches_last_5_days': pitches,
            'appearances_last_3_days': 1,
            'appearances_last_5_days': 1,
            'days_rest': days_rest,
            'back_to_back': False,
            'three_in_four': False,
            'four_in_five': False,
            'freshness_state': freshness,
            'latest_game_date': represented.isoformat(),
            'reference_date': product_current_date().isoformat(),
        },
    }


def _fake_provider(status='operationally_stable'):
    def provider(
        team_id, *, reference_dates_out, arm_reads_out,
        classified_record_overrides, represented_date_override, **_kwargs,
    ):
        reference_dates_out.update({
            'membership_reference_date': represented_date_override,
            'availability_reference_date': represented_date_override + timedelta(days=1),
        })
        records = []
        for pitcher_id, record in classified_record_overrides.items():
            pitcher = record['pitcher']
            if pitcher.team_id != team_id:
                continue
            records.append({
                'pitcher_id': pitcher_id,
                'team_id': team_id,
                'public_read': build_public_arm_read(record['availability']),
                'evidence_state': {
                    'data_state': record['availability']['data_state'],
                    'confidence': record['availability']['confidence'],
                },
                'roster_authority': {
                    'version': 'controlled', 'status': 'ACTIVE',
                    'is_authoritative': True, 'is_active_mlb': True,
                },
            })
        arm_reads_out.update({
            'member_pitcher_ids': sorted(item['pitcher_id'] for item in records),
            'missing_record_pitcher_ids': [],
            'records': records,
        })
        distribution = {
            'available': int(status == 'operationally_stable'),
            'monitor': int(status == 'operationally_constrained'),
            'limited': 0,
            'avoid': int(status == 'operationally_stressed'),
            'unavailable': 0,
            'unknown': 0,
            'total': 1,
        }
        return {
            'team': {'team_id': team_id},
            'readiness': {'status_code': status},
            'availability_distribution': distribution,
            'coverage_inventory': {'active_pitcher_count': 1},
            'team_state_evidence': {
                'readiness_status_code': status,
                'active_pitcher_count': 1,
                'decisive_rule': 'controlled_authoritative_shape',
            },
        }
    return provider


def _seed_pitcher(*, team_id=TEAM_ID, position='P', active=True):
    pitcher = Pitcher(
        mlb_id=880000 + int(team_id),
        full_name='CU-05 Arm',
        team_id=team_id,
        team_name=f'Team {team_id}',
        team_abbreviation=f'T{team_id}',
        position=position,
        throws='R',
        active=active,
        roster_status='ACTIVE',
        roster_status_source='controlled',
    )
    db.session.add(pitcher)
    db.session.flush()
    return pitcher


def test_no_cu04_work_performs_zero_cu05_work(app, monkeypatch):
    with app.app_context():
        monkeypatch.setattr(
            cu05, 'resolve_team_readiness_payload',
            lambda *args, **kwargs: pytest.fail('Team State ran'),
        )
        result = cu05.recompute_arm_reads_team_state(_cu04_result(performed=False))

        assert result.status == cu05.STATUS_NO_ACTION
        assert result.arm_reads_recomputed == ()
        assert result.teams_recomputed == ()
        assert result.recomputation_performed is False


def test_bounded_fake_provider_recomputes_only_requested_entities(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher()
        unrelated = _seed_pitcher(team_id=99)
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda team_id, _date: (
                frozenset({pitcher.id}) if team_id == TEAM_ID else frozenset(),
                team_id == TEAM_ID,
            ),
        )
        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
            ),
            readiness_provider=_fake_provider(),
        )

        assert result.status == cu05.STATUS_COMPLETE
        assert result.arm_reads_recomputed == (pitcher.id,)
        assert result.teams_recomputed == (TEAM_ID,)
        assert unrelated.id not in result.arm_read_results
        assert 99 not in result.team_state_results
        assert result.parity_status == cu05.PARITY_MATCH
        assert result.parity_mismatches == ()


def test_production_availability_input_seam_is_exact(app):
    with app.app_context():
        pitcher = _seed_pitcher()
        represented = product_current_date() - timedelta(days=1)
        log = GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=880001,
            game_date=represented,
            pitches_thrown=28,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            appearance_team_id=TEAM_ID,
        )
        db.session.add(log)
        db.session.commit()
        workload = cu04._compute_pitcher_workload_rest(
            pitcher.id,
            data_through=represented,
            availability_reference_date=product_current_date(),
        )
        direct = classify_availability(
            score={
                'raw_score': workload['rest_workload_inputs']['fatigue_score'],
                'risk_level': workload['rest_workload_inputs']['fatigue_risk_level'],
            },
            game_logs=[log],
            reference_date=product_current_date(),
            latest_game_date=represented,
        )
        incremental = classify_availability_inputs(
            workload['rest_workload_inputs']
        )

        assert incremental == direct


def test_real_production_resolver_reuses_membership_and_team_state(app):
    with app.app_context():
        _seed_team(usable_count=8, total_count=8)
        pitcher = Pitcher.query.filter_by(mlb_id=990001).one()
        represented = product_current_date() - timedelta(days=1)
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=889901,
            game_date=represented,
            pitches_thrown=24,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            appearance_team_id=TEAM_ID,
        ))
        db.session.commit()
        workload = cu04.recompute_workload_rest_impact(
            {
                'game_pk': 889901,
                'canonical_mutation_performed': True,
                'affected_pitcher_ids': (pitcher.id,),
                'affected_team_ids': (TEAM_ID,),
            },
            data_through=represented,
        )

        result = cu05.recompute_arm_reads_team_state(workload)

        assert result.status == cu05.STATUS_COMPLETE
        assert result.parity_status == cu05.PARITY_MATCH
        assert result.arm_reads_recomputed == (pitcher.id,)
        assert result.teams_recomputed == (TEAM_ID,)
        assert result.arm_read_results[pitcher.id]['public_read']['label'] in {
            'Clean Option', 'Watch Arm', 'Limited Rest',
            'Unavailable', 'Limited Read',
        }
        assert result.team_state_results[TEAM_ID]['public_team_state']['public_label'] in {
            'Fresh', 'Stretched', 'Vulnerable',
        }


def test_controlled_correction_recomputes_only_relevant_arm_and_team(app):
    with app.app_context():
        _seed_team(usable_count=8, total_count=8)
        pitcher = Pitcher.query.filter_by(mlb_id=990001).one()
        represented = product_current_date() - timedelta(days=1)
        corrected = GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=889902,
            game_date=represented,
            pitches_thrown=18,
            innings_pitched=1.0,
            innings_pitched_outs=3,
            appearance_team_id=TEAM_ID,
        )
        db.session.add(corrected)
        db.session.commit()
        impact = {
            'game_pk': 889902,
            'canonical_mutation_performed': True,
            'affected_pitcher_ids': (pitcher.id,),
            'affected_team_ids': (TEAM_ID,),
        }
        before_workload = cu04.recompute_workload_rest_impact(
            impact, data_through=represented,
        )
        before = cu05.recompute_arm_reads_team_state(before_workload)

        corrected.pitches_thrown = 52
        db.session.commit()
        after_workload = cu04.recompute_workload_rest_impact(
            impact, data_through=represented,
        )
        after = cu05.recompute_arm_reads_team_state(after_workload)

        assert before.parity_status == after.parity_status == cu05.PARITY_MATCH
        assert after.arm_reads_recomputed == (pitcher.id,)
        assert after.teams_recomputed == (TEAM_ID,)
        assert before.arm_read_results[pitcher.id] != after.arm_read_results[pitcher.id]
        assert after.arm_read_results[pitcher.id]['public_read']['label'] == 'Unavailable'
        assert before.team_state_results[TEAM_ID]['availability_distribution'] != (
            after.team_state_results[TEAM_ID]['availability_distribution']
        )


def test_position_player_is_not_promoted_into_current_arm_reads(app, monkeypatch):
    with app.app_context():
        player = _seed_pitcher(team_id=20, position='CF')
        before = (player.team_id, player.position, player.active)
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset(), False),
        )
        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(player.id,), teams=(10,),
                pitcher_results={player.id: _fake_workload(player.id)},
            ),
            readiness_provider=_fake_provider(),
        )
        db.session.refresh(player)

        assert player.id not in result.arm_reads_recomputed
        assert player.id in result.skipped_arm_read_pitcher_ids
        assert (player.team_id, player.position, player.active) == before


def test_historical_team_input_does_not_rewrite_current_membership(app):
    with app.app_context():
        pitcher = _seed_pitcher(team_id=20)
        db.session.commit()

        def membership(team_id, _date):
            if team_id == 20:
                return frozenset({pitcher.id}), True
            return frozenset(), False

        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(10,),
                pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
            ),
            readiness_provider=_fake_provider(),
            membership_provider=membership,
        )

        assert result.requested_team_ids == (10, 20)
        assert result.arm_read_results[pitcher.id]['team_id'] == 20
        assert pitcher.team_id == 20


def test_optional_pbp_failure_is_irrelevant_after_core_workload_exists(
    app, monkeypatch,
):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )
        workload = _cu04_result(
            pitchers=(pitcher.id,), teams=(TEAM_ID,),
            pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
        ).to_dict()
        workload['optional_pbp_status'] = 'failed_nonblocking'

        result = cu05.recompute_arm_reads_team_state(
            workload, readiness_provider=_fake_provider(),
        )

        assert result.status == cu05.STATUS_COMPLETE
        assert result.arm_reads_recomputed == (pitcher.id,)
        assert result.teams_recomputed == (TEAM_ID,)


def test_team_state_failure_is_structured_and_never_publishes(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )

        def fail(*_args, **_kwargs):
            raise RuntimeError('controlled failure')

        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
            ),
            readiness_provider=fail,
        )

        assert result.status == cu05.STATUS_PARTIAL
        assert result.teams_recomputed == ()
        assert result.parity_status == cu05.PARITY_NOT_COMPARABLE
        assert result.publication_affected is False
        assert result.downstream_recomputation_triggered is False


@pytest.mark.parametrize(
    ('pitches', 'expected'),
    [
        (0, 'Clean Option'),
        (12, 'Watch Arm'),
        (28, 'Limited Rest'),
        (52, 'Unavailable'),
    ],
)
def test_canonical_arm_read_vocabulary_is_preserved(
    app, monkeypatch, pitches, expected,
):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )
        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={
                    pitcher.id: _fake_workload(pitcher.id, pitches=pitches),
                },
            ),
            readiness_provider=_fake_provider(),
        )

        assert result.arm_read_results[pitcher.id]['public_read']['label'] == expected


def test_limited_read_preserves_unknown_input(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )
        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={
                    pitcher.id: _fake_workload(
                        pitcher.id, pitches=0, freshness='missing',
                    ),
                },
            ),
            readiness_provider=_fake_provider(),
        )

        assert result.arm_read_results[pitcher.id]['public_read']['label'] == 'Limited Read'


@pytest.mark.parametrize(
    ('status', 'label'),
    [
        ('operationally_stable', 'Fresh'),
        ('operationally_constrained', 'Stretched'),
        ('operationally_stressed', 'Vulnerable'),
    ],
)
def test_canonical_team_state_vocabulary_is_preserved(app, monkeypatch, status, label):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )
        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
            ),
            readiness_provider=_fake_provider(status),
        )

        assert result.team_state_results[TEAM_ID]['public_team_state'][
            'public_label'
        ] == label


def test_parity_mismatch_is_explicit_and_partial(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )
        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
            ),
            readiness_provider=_fake_provider('operationally_stable'),
            authoritative_readiness_provider=_fake_provider(
                'operationally_constrained'
            ),
        )

        assert result.status == cu05.STATUS_PARTIAL
        assert result.parity_status == cu05.PARITY_MISMATCH
        assert any(
            row['field'] == 'readiness.status_code'
            for row in result.parity_mismatches
        )


def test_direct_recompute_is_deterministic_after_restart(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher()
        db.session.commit()
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )
        workload = _cu04_result(
            pitchers=(pitcher.id,), teams=(TEAM_ID,),
            pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
        )
        before = cu05.recompute_arm_reads_team_state(
            workload, readiness_provider=_fake_provider(),
        )
        db.session.remove()
        after = cu05.recompute_arm_reads_team_state(
            workload, readiness_provider=_fake_provider(),
        )

        assert after.arm_read_results == before.arm_read_results
        assert after.team_state_results == before.team_state_results
        assert after.parity_entries == before.parity_entries


def test_shadow_recompute_mutates_no_public_state(app, monkeypatch):
    with app.app_context():
        pitcher = _seed_pitcher()
        sentinel = DashboardSnapshot(
            snapshot_type='cu05_sentinel', status='ready', is_published=False,
            payload={'immutable': True}, data_through=date(2026, 8, 27),
        )
        db.session.add(sentinel)
        db.session.commit()
        sentinel_id = sentinel.id
        monkeypatch.setattr(
            cu05, 'resolve_active_bullpen_membership',
            lambda *_args: (frozenset({pitcher.id}), True),
        )

        result = cu05.recompute_arm_reads_team_state(
            _cu04_result(
                pitchers=(pitcher.id,), teams=(TEAM_ID,),
                pitcher_results={pitcher.id: _fake_workload(pitcher.id)},
            ),
            readiness_provider=_fake_provider(),
        )
        stored = db.session.get(DashboardSnapshot, sentinel_id)

        assert stored.payload == {'immutable': True}
        assert stored.is_published is False
        assert result.read_models_rebuilt is False
        assert result.publication_affected is False
        assert result.cache_invalidation_triggered is False
        assert result.scheduling_affected is False
        assert result.downstream_recomputation_triggered is False


def test_strongest_cu02_through_cu05_chain_stops_after_team_state(app, monkeypatch):
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

        result = cu05.recompute_arm_reads_team_state(
            workload,
            readiness_provider=_fake_provider(),
            membership_provider=lambda team_id, _date: (
                active_by_team.get(team_id, frozenset()),
                bool(active_by_team.get(team_id)),
            ),
        )

        assert canonical.game_log_inserted == 4
        assert canonical.pitch_inserted == 4
        assert len(canonical.affected_pitcher_ids) == 2
        assert workload.parity_status == cu04.PARITY_MATCH
        assert result.arm_reads_recomputed == canonical.affected_pitcher_ids
        assert result.teams_recomputed == canonical.affected_team_ids
        assert result.parity_status == cu05.PARITY_MATCH
        assert result.read_models_rebuilt is False
        assert result.publication_affected is False
        assert result.cache_invalidation_triggered is False

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
        no_workload = cu04.recompute_workload_rest_impact(
            replay, data_through=GAME_DATE,
        )
        no_state = cu05.recompute_arm_reads_team_state(
            no_workload,
            readiness_provider=lambda *args, **kwargs: pytest.fail(
                'CU-05 resolver must not run for unchanged observation'
            ),
        )

        assert replay.cu01_invocations == 0
        assert no_workload.status == cu04.STATUS_NO_ACTION
        assert no_state.status == cu05.STATUS_NO_ACTION
        assert no_state.arm_reads_recomputed == ()
        assert no_state.teams_recomputed == ()


def test_cu05_source_is_non_scheduled_and_stops_before_publication():
    source = Path(cu05.__file__).read_text(encoding='utf-8')
    forbidden = (
        'run_daily_sync', 'publish_snapshot', 'publish_share_artifact',
        'invalidate_cache', 'while True', 'apscheduler', 'TeamBoard',
        'WhatChanged',
    )
    assert [token for token in forbidden if token in source] == []
