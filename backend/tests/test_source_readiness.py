from datetime import date, datetime

import pytest
from flask import Flask
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.postgame_processed_game import PostgameProcessedGame
from models.roster_status_snapshot import RosterStatusSnapshot
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from models.sync_failure import SyncFailure
from models.team_game_pitching_split import TeamGamePitchingSplit
from services import slate_coverage, source_readiness, sync_metadata
from utils.db import db
import models.prospect  # noqa: F401  (full model registry for create_all)


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


def test_classify_ready_source():
    readiness = source_readiness.classify_source_readiness(
        'fixture',
        last_successful_at=date(2026, 6, 1),
        last_attempted_at=datetime(2026, 6, 1, 12, 0, 0),
        stale_after_days=2,
        reference_date=date(2026, 6, 2),
        sync_run_id=10,
        source='test',
    )

    assert readiness.status == source_readiness.READY
    assert readiness.fail_closed is False
    assert readiness.to_dict()['sync_run_id'] == 10


@pytest.mark.parametrize(
    ('kwargs', 'expected_status', 'expected_reason'),
    [
        ({}, source_readiness.NEVER_FETCHED, 'source_never_fetched'),
        (
            {'last_attempted_at': datetime(2026, 6, 1, 12, 0, 0)},
            source_readiness.UNAVAILABLE,
            'source_unavailable',
        ),
        (
            {
                'last_successful_at': date(2026, 6, 1),
                'last_attempted_at': datetime(2026, 6, 1, 12, 0, 0),
                'stale_after_days': 2,
                'reference_date': date(2026, 6, 5),
            },
            source_readiness.STALE,
            'source_stale',
        ),
        (
            {
                'last_successful_at': date(2026, 6, 1),
                'dead_letter_count': 1,
                'reference_date': date(2026, 6, 2),
            },
            source_readiness.DEGRADED,
            'dead_letters_unresolved',
        ),
        (
            {
                'last_successful_at': date(2026, 6, 1),
                'provenance_present': False,
                'reference_date': date(2026, 6, 2),
            },
            source_readiness.UNAVAILABLE,
            'provenance_missing',
        ),
    ],
)
def test_non_ready_states_fail_closed(kwargs, expected_status, expected_reason):
    readiness = source_readiness.classify_source_readiness('fixture', **kwargs)

    assert readiness.status == expected_status
    assert readiness.fail_closed is True
    assert expected_reason in readiness.reason_codes


def _add_team_game_split(
    *,
    team_id,
    game_pk,
    game_date,
    sync_run_id=None,
    split_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    calendar_status=TeamGamePitchingSplit.STATUS_COMPLETE,
    split_reasons=None,
    calendar_reasons=None,
):
    timestamp = datetime(2026, 6, 2, 9, 0, 0)
    db.session.add(TeamGamePitchingSplit(
        team_id=team_id,
        mlb_game_pk=game_pk,
        game_date=game_date,
        game_type='R',
        opponent_team_id=142 if team_id == 116 else 116,
        home_away='home' if team_id == 116 else 'away',
        starter_identity_status=(
            TeamGamePitchingSplit.STARTER_KNOWN
            if split_status == TeamGamePitchingSplit.STATUS_COMPLETE
            else TeamGamePitchingSplit.STARTER_UNKNOWN
        ),
        starter_outs_recorded=15 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        starter_pitches_thrown=80 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        starter_batters_faced=20 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        starter_balls=30 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        starter_games_started=1 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        bullpen_outs_recorded=12 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        bullpen_pitches_thrown=45 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        bullpen_batters_faced=13 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        bullpen_balls=18 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        relievers_used_count=1 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        total_team_outs=27 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        total_team_pitches=125 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        total_team_batters_faced=33 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        total_team_balls=48 if split_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        split_completeness_status=split_status,
        split_reason_codes=list(split_reasons or []),
        off_day_before=False if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        off_day_after=False if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        consecutive_game_day_count_entering=1 if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        series_game_number=1 if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        games_in_series=3 if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        doubleheader_flag=False if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        doubleheader_code='N',
        game_number=1 if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        postponed_or_makeup_indicator=False if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        suspended_resumed_linkage_status=TeamGamePitchingSplit.LINKAGE_NONE,
        extra_inning_indicator=False if calendar_status == TeamGamePitchingSplit.STATUS_COMPLETE else None,
        calendar_context_status=calendar_status,
        calendar_reason_codes=list(calendar_reasons or []),
        source='derived:game_logs_schedule',
        sync_run_id=sync_run_id,
        first_seen_at=timestamp,
        last_derived_at=timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    ))


def test_source_readiness_payload_reports_existing_foundations(app):
    with app.app_context():
        pitcher = Pitcher(
            mlb_id=1,
            full_name='A',
            team_id=116,
            active=True,
            roster_status='ACTIVE',
            roster_status_source='mlb_stats_api:roster_sync:active',
            roster_status_updated_at=datetime(2026, 6, 2, 9, 0, 0),
        )
        db.session.add(pitcher)
        db.session.commit()
        db.session.add(GameLog(
            pitcher_id=pitcher.id,
            mlb_game_pk=31,
            game_date=date(2026, 6, 1),
            innings_pitched=1.0,
            innings_pitched_outs=3,
        ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id,
            raw_score=42.0,
            calculated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.add_all([
            ScheduledGame(
                team_id=116,
                game_pk=31,
                game_date=date(2026, 6, 1),
                status_state='final',
                home_away='home',
                opponent_team_id=142,
            ),
            ScheduledGame(
                team_id=142,
                game_pk=31,
                game_date=date(2026, 6, 1),
                status_state='final',
                home_away='away',
                opponent_team_id=116,
            ),
        ])
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=31,
            game_date=date(2026, 6, 1),
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
        run = SyncRun(
            job_name='daily_sync',
            started_at=datetime(2026, 6, 2, 8, 59, 0),
            completed_at=datetime(2026, 6, 2, 9, 1, 0),
            status='success',
            source='github_actions',
            latest_game_date=date(2026, 6, 1),
            latest_workload_date=date(2026, 6, 1),
            latest_fatigue_calculated_at=datetime(2026, 6, 2, 9, 0, 0),
        )
        db.session.add(run)
        db.session.commit()
        db.session.add(RosterStatusSnapshot(
            pitcher_id=pitcher.id,
            mlb_id=pitcher.mlb_id,
            team_id=pitcher.team_id,
            snapshot_date=date(2026, 6, 2),
            roster_status='ACTIVE',
            active_roster=True,
            forty_man_roster=True,
            position_code='P',
            source='mlb_stats_api:roster_sync:active',
            sync_run_id=run.id,
            first_seen_at=datetime(2026, 6, 2, 9, 0, 0),
            created_at=datetime(2026, 6, 2, 9, 0, 0),
            updated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.add(PlayerTransaction(
            transaction_key='statsapi:tx-ready',
            transaction_id='tx-ready',
            pitcher_id=pitcher.id,
            player_mlb_id=pitcher.mlb_id,
            to_team_id=pitcher.team_id,
            transaction_date=date(2026, 6, 2),
            transaction_type_code='RECALL',
            normalized_category='recall',
            is_il_placement=False,
            is_il_activation=False,
            roster_snapshot_alignment='aligned',
            alignment_reason_code='roster_snapshot_team_match',
            explanatory_linkage_eligible=True,
            source='mlb_stats_api:transactions',
            source_endpoint='/transactions',
            source_query_start_date=date(2026, 5, 26),
            source_query_end_date=date(2026, 6, 2),
            sync_run_id=run.id,
            first_seen_at=datetime(2026, 6, 2, 9, 0, 0),
            created_at=datetime(2026, 6, 2, 9, 0, 0),
            updated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.add(PlayerTransactionSyncWindow(
            source='mlb_stats_api:transactions',
            source_endpoint='/transactions',
            source_query_start_date=date(2026, 5, 26),
            source_query_end_date=date(2026, 6, 2),
            attempted_at=datetime(2026, 6, 2, 9, 0, 0),
            successful_at=datetime(2026, 6, 2, 9, 0, 0),
            status='success',
            records_fetched=1,
            records_stored=1,
            records_created=1,
            sync_run_id=run.id,
            created_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.add(PlayByPlayProcessedGame(
            mlb_game_pk=31,
            game_date=date(2026, 6, 1),
            game_type='R',
            home_team_id=116,
            away_team_id=142,
            final_state='final_and_usable',
            processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
            attempt_count=1,
            last_attempted_at=datetime(2026, 6, 2, 9, 0, 0),
            events_seen=1,
            events_stored=1,
            pitcher_events_seen=1,
            event_fingerprint='fixture',
            source='mlb_stats_api:final_play_by_play',
            source_endpoint='/game/31/playByPlay',
            sync_run_id=run.id,
            first_seen_at=datetime(2026, 6, 2, 9, 0, 0),
            processed_at=datetime(2026, 6, 2, 9, 0, 0),
            created_at=datetime(2026, 6, 2, 9, 0, 0),
            updated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.add(GamePlayByPlayEvent(
            mlb_game_pk=31,
            event_index=0,
            source_play_id='fixture-play',
            at_bat_index=0,
            game_date=date(2026, 6, 1),
            game_type='R',
            home_team_id=116,
            away_team_id=142,
            event_type='plate_appearance',
            event_type_code='field_out',
            inning=1,
            half_inning='top',
            is_top_inning=True,
            outs_at_event=0,
            home_score_at_event=0,
            away_score_at_event=0,
            pitcher_mlb_id=pitcher.mlb_id,
            pitcher_id=pitcher.id,
            batter_mlb_id=900,
            batting_team_id=142,
            fielding_team_id=116,
            is_pitching_change=False,
            is_scoring_play=False,
            is_mound_visit=False,
            source='mlb_stats_api:final_play_by_play',
            source_endpoint='/game/31/playByPlay',
            sync_run_id=run.id,
            first_seen_at=datetime(2026, 6, 2, 9, 0, 0),
            created_at=datetime(2026, 6, 2, 9, 0, 0),
            updated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        _add_team_game_split(
            team_id=116,
            game_pk=31,
            game_date=date(2026, 6, 1),
            sync_run_id=run.id,
        )
        _add_team_game_split(
            team_id=142,
            game_pk=31,
            game_date=date(2026, 6, 1),
            sync_run_id=run.id,
        )
        db.session.add(DashboardSnapshot(
            snapshot_type='bullpen_dashboard',
            sync_run_id=run.id,
            status='ready',
            is_published=True,
            payload={},
            data_through=date(2026, 6, 1),
            availability_reference_date=date(2026, 6, 2),
            snapshot_generated_at=datetime(2026, 6, 2, 9, 2, 0),
            source='sync',
        ))
        db.session.commit()

        coverage = slate_coverage.compute_slate_coverage(date(2026, 6, 1))
        payload = source_readiness.source_readiness_payload(
            metadata=sync_metadata.collect_data_metadata(),
            sync_status='success',
            slate_coverage_payload=coverage,
            reference_date=date(2026, 6, 2),
        )

    assert payload['overall_status'] == source_readiness.READY
    assert payload['fail_closed'] is False
    families = payload['families']
    assert families['finality_authority']['status'] == source_readiness.READY
    assert families['statsapi_core']['status'] == source_readiness.READY
    assert families['game_logs']['status'] == source_readiness.READY
    assert families['slate_coverage']['status'] == source_readiness.READY
    assert families['dashboard_snapshots']['status'] == source_readiness.READY
    assert families['roster_status_snapshots']['status'] == source_readiness.READY
    assert families['player_transactions']['status'] == source_readiness.READY
    assert families['final_play_by_play']['status'] == source_readiness.READY
    assert families['team_game_pitching_splits']['status'] == source_readiness.READY
    assert families['calendar_context']['status'] == source_readiness.READY


def test_source_readiness_payload_blocks_incomplete_slate(app):
    with app.app_context():
        db.session.add(SyncRun(
            job_name='daily_sync',
            started_at=datetime(2026, 6, 2, 8, 59, 0),
            completed_at=datetime(2026, 6, 2, 9, 1, 0),
            status='success',
            source='github_actions',
        ))
        db.session.add(SyncFailure(
            job_name='daily_sync',
            entity_type='pitcher_game_logs',
            entity_ref='1',
            error='shape failure',
            resolved=False,
        ))
        db.session.commit()
        coverage = slate_coverage.unknown_slate_coverage(date(2026, 6, 1))
        payload = source_readiness.source_readiness_payload(
            metadata={},
            sync_status='success',
            slate_coverage_payload=coverage,
            reference_date=date(2026, 6, 2),
        )

    assert payload['fail_closed'] is True
    assert 'slate_coverage' in payload['blocking_source_families']
    assert payload['families']['slate_coverage']['status'] == source_readiness.DEGRADED
    assert payload['families']['game_logs']['status'] != source_readiness.READY


def test_final_play_by_play_readiness_degrades_on_incomplete_marker(app):
    with app.app_context():
        db.session.add(PlayByPlayProcessedGame(
            mlb_game_pk=99,
            game_date=date(2026, 6, 1),
            game_type='R',
            home_team_id=116,
            away_team_id=142,
            final_state='final_and_usable',
            processing_status=PlayByPlayProcessedGame.STATUS_INCOMPLETE,
            attempt_count=1,
            last_attempted_at=datetime(2026, 6, 2, 9, 0, 0),
            incomplete_reason='pitcher_reconciliation_mismatch',
            events_seen=4,
            events_stored=4,
            pitcher_events_seen=1,
            reconciliation_mismatch_count=1,
            event_fingerprint='fixture',
            source='mlb_stats_api:final_play_by_play',
            source_endpoint='/game/99/playByPlay',
            first_seen_at=datetime(2026, 6, 2, 9, 0, 0),
            created_at=datetime(2026, 6, 2, 9, 0, 0),
            updated_at=datetime(2026, 6, 2, 9, 0, 0),
        ))
        db.session.commit()

        payload = source_readiness.source_readiness_payload(
            metadata={},
            sync_status='success',
            slate_coverage_payload=slate_coverage.unknown_slate_coverage(date(2026, 6, 1)),
            reference_date=date(2026, 6, 2),
        )
        family = payload['families']['final_play_by_play']

    assert family['status'] == source_readiness.UNAVAILABLE
    assert family['fail_closed'] is True
    assert family['coverage']['games_incomplete'] == 1
    assert family['details']['reconciliation_mismatch_count'] == 1
    assert 'final_pbp_reconciliation_mismatch' in family['reason_codes']


def test_team_game_split_and_calendar_readiness_degrade_on_partial_rows(app):
    with app.app_context():
        game_date = date(2026, 6, 3)
        db.session.add_all([
            ScheduledGame(
                team_id=116,
                game_pk=41,
                game_date=game_date,
                status_state='final',
                home_away='home',
                opponent_team_id=142,
            ),
            ScheduledGame(
                team_id=142,
                game_pk=41,
                game_date=game_date,
                status_state='final',
                home_away='away',
                opponent_team_id=116,
            ),
        ])
        _add_team_game_split(
            team_id=116,
            game_pk=41,
            game_date=game_date,
        )
        _add_team_game_split(
            team_id=142,
            game_pk=41,
            game_date=game_date,
            split_status=TeamGamePitchingSplit.STATUS_PARTIAL,
            calendar_status=TeamGamePitchingSplit.STATUS_UNKNOWN,
            split_reasons=('starter_identity_unknown',),
            calendar_reasons=('schedule_missing',),
        )
        db.session.commit()

        payload = source_readiness.source_readiness_payload(
            metadata={},
            sync_status='success',
            slate_coverage_payload=slate_coverage.unknown_slate_coverage(game_date),
            reference_date=date(2026, 6, 4),
        )

    split_family = payload['families']['team_game_pitching_splits']
    calendar_family = payload['families']['calendar_context']
    assert split_family['status'] == source_readiness.DEGRADED
    assert split_family['coverage']['team_game_splits_complete'] == 1
    assert split_family['coverage']['team_game_splits_partial'] == 1
    assert 'team_game_pitching_splits_partial_or_unknown' in split_family['reason_codes']
    assert calendar_family['status'] == source_readiness.DEGRADED
    assert calendar_family['coverage']['calendar_context_complete'] == 1
    assert calendar_family['coverage']['calendar_context_unknown'] == 1
    assert calendar_family['details']['travel_context_inferred'] is False
    assert 'calendar_context_partial_or_unknown' in calendar_family['reason_codes']
