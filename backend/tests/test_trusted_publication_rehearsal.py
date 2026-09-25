"""A bounded, isolated rehearsal of the installed trusted publication builder."""

from copy import deepcopy
from datetime import datetime, timedelta
import importlib
import json
import os
from time import perf_counter
from urllib.parse import urlparse

import pytest
from sqlalchemy import event, text

from models.dashboard_snapshot import DashboardSnapshot
from models.fatigue_score import FatigueScore
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.player_transaction import PlayerTransaction, PlayerTransactionSyncWindow
from models.postgame_processed_game import PostgameProcessedGame
from models.play_by_play_foundation import GamePlayByPlayEvent, PlayByPlayProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_run import SyncRun
from models.team_game_pitching_split import TeamGamePitchingSplit
from services.roster_status import STATUS_IL_15
from services import appearance_ledger, dashboard_snapshot, public_serving_authority
from services import public_team_relief_work
from scripts.rehearse_trusted_publication import assert_rehearsal_target
from services.team_board_delivery import (
    TeamBoardIdentityMismatch,
    build_team_board_identity,
    require_matching_team_board_identity,
)
from services.team_board_v2 import (
    build_team_board_core_payload,
    build_team_board_details_payload,
)
from services.team_board_snapshot_team_state import make_receipt
from services.team_board_what_changed import build_frozen_what_changed
from services.team_state_vnext_production_proof import EXPECTED_METHOD_VERSION
from services.what_changed_comparison_identity import build_comparison_identity
from tests.db_config import (
    assert_disposable_test_target,
    create_test_schema,
    drop_test_schema,
    test_database_url as _test_database_url,
)
from tests.roster_readiness_fixture import seed_roster_readiness_snapshots
from utils.db import db
from utils.time import utc_now_naive


TEAM_IDS = (
    108, 109, 110, 111, 112, 113, 114, 115, 116, 117, 118, 119, 120, 121,
    133, 134, 135, 136, 137, 138, 139, 140, 141, 142, 143, 144, 145, 146,
    147, 158,
)
NONCANONICAL_TEAM_IDS = (484, 531, 534, 5434)


def _seed_teams(reference_date):
    for index, team_id in enumerate(TEAM_IDS):
        pitcher = Pitcher(
            mlb_id=7900000 + index,
            full_name=f'Rehearsal Pitcher {index:02d}',
            team_id=team_id,
            team_name=f'Rehearsal Team {index:02d}',
            team_abbreviation=f'R{index:02d}',
            position='P', active=True, roster_status='active',
            roster_status_source='test_fixture',
            roster_status_updated_at=utc_now_naive(),
        )
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=7900000 + index,
            game_date=reference_date - timedelta(days=4 if index == 29 else 1),
            game_type='R',
            games_started=0, innings_pitched=1.0, innings_pitched_outs=3,
            pitches_thrown=18 + index,
            appearance_team_id=team_id,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
            leverage_index=1.5 if index == 0 else None,
        ))
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=7900000 + index,
            game_date=reference_date - timedelta(days=4 if index == 29 else 1),
            game_type='R', status_code='F',
            status_state=ScheduledGame.STATE_FINAL,
            game_number=1, home_away='home',
        ))
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=7900000 + index,
            game_date=reference_date - timedelta(days=4 if index == 29 else 1),
            game_type='R', home_team_id=team_id, away_team_id=TEAM_IDS[(index + 1) % 30],
            final_state='Final', pitching_lines_seen=1,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
        if index == 0:
            db.session.add(PlayByPlayProcessedGame(
                mlb_game_pk=7900000, game_date=reference_date - timedelta(days=1),
                game_type='R', home_team_id=team_id, away_team_id=TEAM_IDS[1],
                final_state='Final', processing_status=PlayByPlayProcessedGame.STATUS_FULLY_PROCESSED,
                source='test_fixture', source_endpoint='test_fixture',
            ))
            for event_index, fielding_team_id, pitcher_mlb_id, inning in (
                (1, TEAM_IDS[1], 7999999, 7),
                (2, team_id, pitcher.mlb_id, 8),
            ):
                db.session.add(GamePlayByPlayEvent(
                    mlb_game_pk=7900000, event_index=event_index,
                    game_date=reference_date - timedelta(days=1), game_type='R',
                    home_team_id=team_id, away_team_id=TEAM_IDS[1],
                    event_type='pitching_change', inning=inning, half_inning='top',
                    home_score_at_event=3, away_score_at_event=2,
                    pitcher_mlb_id=pitcher_mlb_id,
                    fielding_team_id=fielding_team_id, is_pitching_change=True,
                    source='test_fixture', source_endpoint='test_fixture',
                ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id, calculated_at=utc_now_naive(),
            raw_score=19.0, pitch_count_score=11.0, rest_days_score=9.0,
            appearances_score=13.0, leverage_score=7.0, innings_score=8.0,
            days_since_last_appearance=4 if index == 29 else 1,
            appearances_last_7=1,
            appearances_last_14=1, pitches_last_7_days=18 + index,
            innings_last_7_days=1.0, risk_level='LOW',
        ))
    starter = Pitcher(
        mlb_id=7999000, full_name='Rehearsal Coverage Starter',
        team_id=TEAM_IDS[0], team_name='Rehearsal Team 00',
        team_abbreviation='R00', position='P', active=True,
        roster_status='active', roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add(starter)
    db.session.flush()
    for offset in range(30):
        game_pk = 7800000 + offset
        game_date = reference_date - timedelta(days=offset + 1)
        db.session.add(ScheduledGame(
            team_id=TEAM_IDS[0], game_pk=game_pk, game_date=game_date,
            game_type='R', status_code='F', status_state=ScheduledGame.STATE_FINAL,
        ))
        db.session.add(PostgameProcessedGame(
            mlb_game_pk=game_pk, game_date=game_date, game_type='R',
            home_team_id=TEAM_IDS[0], away_team_id=TEAM_IDS[1],
            final_state='Final', pitching_lines_seen=1,
            processing_status=PostgameProcessedGame.STATUS_FULLY_PROCESSED,
        ))
        db.session.add(GameLog(
            pitcher_id=starter.id, mlb_game_pk=game_pk, game_date=game_date,
            game_type='R', games_started=1,
            innings_pitched=9.0 if offset == 5 else 5.0,
            innings_pitched_outs=27 if offset == 5 else 15, pitches_thrown=80,
            appearance_team_id=TEAM_IDS[0],
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        ))
    db.session.add(TeamGamePitchingSplit(
        team_id=TEAM_IDS[0], mlb_game_pk=7800005,
        game_date=reference_date - timedelta(days=6), game_type='R',
        starter_pitcher_id=starter.id, starter_mlb_id=starter.mlb_id,
        starter_identity_status=TeamGamePitchingSplit.STARTER_KNOWN,
        starter_outs_recorded=27, bullpen_outs_recorded=0,
        total_team_outs=27,
        split_completeness_status=TeamGamePitchingSplit.STATUS_COMPLETE,
        split_reason_codes=[],
        suspended_resumed_linkage_status=TeamGamePitchingSplit.LINKAGE_NONE,
        calendar_context_status=TeamGamePitchingSplit.STATUS_COMPLETE,
        calendar_reason_codes=[], source='test_fixture',
    ))
    off_active = Pitcher(
        mlb_id=7999001, full_name='Former Rehearsal Arm',
        team_id=TEAM_IDS[1], team_name='Rehearsal Team 01',
        team_abbreviation='R01', position='P', active=True,
        roster_status=STATUS_IL_15, roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    acquired = Pitcher(
        mlb_id=7999002, full_name='Acquired Rehearsal Arm',
        team_id=TEAM_IDS[0], team_name='Rehearsal Team 00',
        team_abbreviation='R00', position='P', active=True,
        roster_status='active', roster_status_source='test_fixture',
        roster_status_updated_at=utc_now_naive(),
    )
    db.session.add_all([off_active, acquired])
    db.session.flush()
    for pitcher, team_id, pitches, outs in (
        (off_active, TEAM_IDS[0], 12, 2),
        (acquired, TEAM_IDS[1], 99, 3),
    ):
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=7999000 + pitcher.mlb_id,
            game_date=reference_date - timedelta(days=1), game_type='R',
            games_started=0, innings_pitched=outs / 3,
            innings_pitched_outs=outs, pitches_thrown=pitches,
            appearance_team_id=team_id,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        ))
    db.session.commit()
    seed_roster_readiness_snapshots([reference_date])


def _seed_noncanonical_organizations(reference_date):
    for index, team_id in enumerate(NONCANONICAL_TEAM_IDS):
        pitcher = Pitcher(
            mlb_id=7950000 + index,
            full_name=f'Noncanonical Organization Pitcher {team_id}',
            team_id=team_id,
            team_name=f'Noncanonical Organization {team_id}',
            team_abbreviation=f'N{index}',
            position='P', active=True, roster_status='active',
            roster_status_source='test_fixture',
            roster_status_updated_at=utc_now_naive(),
        )
        db.session.add(pitcher)
        db.session.flush()
        db.session.add(GameLog(
            pitcher_id=pitcher.id, mlb_game_pk=7950000 + index,
            game_date=reference_date - timedelta(days=1), game_type='R',
            games_started=0, innings_pitched=1.0, innings_pitched_outs=3,
            pitches_thrown=12 + index, appearance_team_id=team_id,
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        ))
        db.session.add(FatigueScore(
            pitcher_id=pitcher.id, calculated_at=utc_now_naive(),
            raw_score=10.0, pitch_count_score=5.0, rest_days_score=5.0,
            appearances_score=5.0, leverage_score=5.0, innings_score=5.0,
            days_since_last_appearance=1, appearances_last_7=1,
            appearances_last_14=1, pitches_last_7_days=12 + index,
            innings_last_7_days=1.0, risk_level='LOW',
        ))
    db.session.commit()


def _assert_workload_carrier(snapshot, team_id):
    package = snapshot.payload['trusted_team_boards']['by_team_id'][str(team_id)]
    carrier = package['workload_windows']['overview']
    assert carrier['contract'] == 'team_board_workload_overview_v1'
    assert carrier['data_through'] == snapshot.data_through.isoformat()
    assert carrier['trend_status'] == 'unavailable'
    for days in (3, 7, 14, 30):
        window = carrier['windows'][f'window_{days}']
        assert window['through'] == snapshot.data_through.isoformat()
        assert window['start'] == (
            snapshot.data_through - timedelta(days=days - 1)
        ).isoformat()
        for name in ('pitches', 'appearances', 'outs'):
            metric = window[name]
            assert metric['status'] in ('complete', 'partial', 'unknown', 'unavailable')
            assert isinstance(metric['reason_codes'], list)
            assert metric['value'] is None or type(metric['value']) is int
            if metric['status'] != 'complete':
                assert metric['value'] is None
    concentration = carrier['concentration_7_day']
    assert concentration['status'] in ('complete', 'partial', 'unknown', 'unavailable')
    assert isinstance(concentration['contributors'], list)
    assert isinstance(concentration['top_3_contributors'], list)
    if concentration['status'] == 'complete':
        assert concentration['top_3_contributors'] == concentration['contributors'][:3]
        assert concentration['active_current_contribution'] is not None
        assert concentration['off_active_contribution'] is not None
    return carrier


def test_trusted_publication_rehearsal(monkeypatch, tmp_path):
    url = _test_database_url()
    assert url.startswith(('postgres://', 'postgresql://'))
    assert_disposable_test_target(url, operation='trusted publication rehearsal test')
    assert not os.environ.get('DATABASE_URL') or os.environ['DATABASE_URL'] == url
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', url)
    app = importlib.import_module('app').create_app('test')
    app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
    with app.app_context():
        assert_disposable_test_target(
            db.engine.url.render_as_string(hide_password=False),
            operation='trusted publication rehearsal engine',
        )
        assert db.session.execute(text('select current_database()')).scalar() == (
            urlparse(url).path.lstrip('/')
        )
        create_test_schema(app)
        try:
            reference_date = public_serving_authority.product_current_date()
            _seed_teams(reference_date)
            _seed_noncanonical_organizations(reference_date)
            represented_date = reference_date - timedelta(days=1)
            first_pitcher = Pitcher.query.filter_by(mlb_id=7900000).one()
            db.session.add(PlayerTransactionSyncWindow(
                source='mlb_stats_api:transactions', source_endpoint='/transactions',
                source_query_start_date=represented_date - timedelta(days=7),
                source_query_end_date=represented_date,
                attempted_at=utc_now_naive(), successful_at=utc_now_naive(),
                status='success', records_fetched=1, records_stored=1,
                records_created=1, records_corrected=0, records_unchanged=0,
                unknown_type_count=0, alignment_unknown_count=0,
                alignment_misaligned_count=0, alignment_no_snapshot_count=0,
                records_failed=0, created_at=utc_now_naive(),
            ))
            db.session.add(PlayerTransaction(
                transaction_key='rehearsal:recall:7900000', transaction_id='rehearsal-recall',
                pitcher_id=first_pitcher.id, player_mlb_id=first_pitcher.mlb_id,
                from_team_id=None, to_team_id=TEAM_IDS[0],
                transaction_date=represented_date, transaction_type_code='RECALL',
                normalized_category='recall', roster_snapshot_alignment='aligned',
                explanatory_linkage_eligible=True,
                source='mlb_stats_api:transactions', source_endpoint='/transactions',
                source_query_start_date=represented_date - timedelta(days=7),
                source_query_end_date=represented_date,
            ))
            run = SyncRun(
                job_name='daily_sync',
                started_at=utc_now_naive() - timedelta(minutes=2),
                completed_at=utc_now_naive(), status='success',
                stage='published', source='test',
                latest_game_date=reference_date - timedelta(days=1),
                latest_workload_date=reference_date - timedelta(days=1),
                latest_fatigue_calculated_at=utc_now_naive(),
            )
            db.session.add(run)
            db.session.commit()
            assert public_serving_authority.install_public_serving_authority(app)

            def forbidden_publish(*_args, **_kwargs):
                raise AssertionError('rehearsal attempted pointer movement')

            monkeypatch.setattr(dashboard_snapshot, 'publish_dashboard_snapshot', forbidden_publish)
            context_ms = []
            original_context_author = public_serving_authority.author_public_deployment_context
            def measured_context_author(*args, **kwargs):
                started = perf_counter()
                try:
                    return original_context_author(*args, **kwargs)
                finally:
                    context_ms.append((perf_counter() - started) * 1000)
            monkeypatch.setattr(
                public_serving_authority, 'author_public_deployment_context',
                measured_context_author,
            )
            performance_ms = []
            performance_appearance_queries = []
            original_performance_author = public_serving_authority.build_frozen_team_performance_payload
            def measured_performance_author(*args, **kwargs):
                started = perf_counter()
                before_queries = query_counts['appearance']
                try:
                    return original_performance_author(*args, **kwargs)
                finally:
                    performance_ms.append((perf_counter() - started) * 1000)
                    performance_appearance_queries.append(
                        query_counts['appearance'] - before_queries
                    )
            monkeypatch.setattr(
                public_serving_authority, 'build_frozen_team_performance_payload',
                measured_performance_author,
            )
            rotation_ms = []
            rotation_queries = []
            original_rotation_author = public_serving_authority.frozen_recent_rotation_games_by_team
            def measured_rotation_author(*args, **kwargs):
                started = perf_counter()
                before = query_counts['rotation_source']
                try:
                    return original_rotation_author(*args, **kwargs)
                finally:
                    rotation_ms.append((perf_counter() - started) * 1000)
                    rotation_queries.append(query_counts['rotation_source'] - before)
            monkeypatch.setattr(
                public_serving_authority, 'frozen_recent_rotation_games_by_team',
                measured_rotation_author,
            )
            roster_read_ms = []
            roster_projection_ms = []
            original_roster_read = public_serving_authority.build_public_recent_transactions_by_team
            original_roster_projection = public_serving_authority.author_frozen_roster_transactions
            def measured_roster_read(*args, **kwargs):
                started = perf_counter()
                try:
                    return original_roster_read(*args, **kwargs)
                finally:
                    roster_read_ms.append((perf_counter() - started) * 1000)
            def measured_roster_projection(*args, **kwargs):
                started = perf_counter()
                try:
                    return original_roster_projection(*args, **kwargs)
                finally:
                    roster_projection_ms.append((perf_counter() - started) * 1000)
            monkeypatch.setattr(public_serving_authority, 'build_public_recent_transactions_by_team', measured_roster_read)
            monkeypatch.setattr(public_serving_authority, 'author_frozen_roster_transactions', measured_roster_projection)
            relief_projection_ms = []
            relief_source_queries = []
            original_relief_author = public_serving_authority.author_frozen_recent_relief_work
            original_final_authority = public_serving_authority.load_final_game_authority
            original_unresolved_counts = public_serving_authority.load_unresolved_current_roster_counts
            def measured_relief_author(*args, **kwargs):
                started = perf_counter()
                try:
                    return original_relief_author(*args, **kwargs)
                finally:
                    relief_projection_ms.append((perf_counter() - started) * 1000)
            def measured_relief_source(operation):
                def measured(*args, **kwargs):
                    before = query_counts['all']
                    try:
                        return operation(*args, **kwargs)
                    finally:
                        relief_source_queries.append(query_counts['all'] - before)
                return measured
            monkeypatch.setattr(public_serving_authority, 'author_frozen_recent_relief_work', measured_relief_author)
            monkeypatch.setattr(public_serving_authority, 'load_final_game_authority', measured_relief_source(original_final_authority))
            monkeypatch.setattr(public_serving_authority, 'load_unresolved_current_roster_counts', measured_relief_source(original_unresolved_counts))
            query_counts = {'all': 0, 'appearance': 0, 'processed_game': 0, 'pbp_event': 0, 'rotation_source': 0, 'transactions': 0}
            def count_publication_reads(_conn, _cursor, statement, _params, _context, _many):
                sql = statement.lower()
                query_counts['all'] += 1
                if 'from game_logs' in sql:
                    query_counts['appearance'] += 1
                if 'from player_transactions' in sql:
                    query_counts['transactions'] += 1
                if 'from play_by_play_processed_games' in sql:
                    query_counts['processed_game'] += 1
                if 'from game_play_by_play_events' in sql:
                    query_counts['pbp_event'] += 1
                if any(name in sql for name in (
                    'from scheduled_games', 'from team_game_pitching_splits', 'from pitchers',
                )):
                    query_counts['rotation_source'] += 1
            event.listen(db.engine, 'before_cursor_execute', count_publication_reads)
            started = perf_counter()
            try:
                snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
                    sync_run_id=run.id, source='trusted_publication_rehearsal',
                    publish=False, raise_errors=True,
                )
            finally:
                publication_seconds = perf_counter() - started
                event.remove(db.engine, 'before_cursor_execute', count_publication_reads)
            assert snapshot is not None
            assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert snapshot.is_published is False
            assert snapshot.published_at is None
            assert dashboard_snapshot.payload_version_valid(snapshot)
            assert DashboardSnapshot.query.filter_by(is_published=True).count() == 0
            assert run.published_dashboard_snapshot_id is None
            # Rehearse the same pre-trust proof/admission step within an isolated
            # savepoint.  Rollback keeps the candidate unpublished and proves no
            # production-style pointer movement is needed for the receipt check.
            from services.team_state_vnext_production_proof import (
                OBSERVATION_PROOF_VALID,
                build_postcommit_observation,
                require_transactional_publication_proof,
                write_proof,
            )
            from scripts.validate_team_state_vnext_proof import validate_proof_file
            savepoint = db.session.begin_nested()
            try:
                snapshot.status = dashboard_snapshot.SNAPSHOT_STATUS_READY
                snapshot.is_published = True
                snapshot.published_at = utc_now_naive()
                no_predecessor = build_frozen_what_changed(
                    None, snapshot, TEAM_IDS[0],
                )
                assert no_predecessor['state'] == 'unavailable'
                assert no_predecessor['reason_code'] == 'no_prior_trusted_comparison'
                def governed_rehearsal_readiness(team_id, *, reference_dates_out,
                                                 **_kwargs):
                    # The publication fixture is intentionally sparse for the
                    # earlier Team Board slices.  Supply a complete governed
                    # readiness fixture only at the proof seam; production still
                    # uses the installed resolver.
                    reference_dates_out.update({
                        'membership_reference_date': snapshot.data_through,
                        'availability_reference_date': snapshot.availability_reference_date,
                    })
                    return {
                        'contract_version': 'v3_phase_5',
                        'team': {
                            'team_id': team_id, 'team_name': f'Rehearsal Team {team_id}',
                            'team_abbreviation': f'R{team_id}',
                        },
                        'readiness': {
                            'status_code': 'operationally_stable',
                            'summary': 'Current bullpen state.',
                        },
                        'freshness': {'data_through': snapshot.data_through.isoformat()},
                        'trust_metadata': {'confidence': 'high', 'data_state': 'fresh'},
                        'team_state_evidence': {
                            'method_version': 'v3_phase_5',
                            'contract': 'team_state_contract_a',
                            'basis': 'status_only',
                            'readiness_status_code': 'operationally_stable',
                            'active_pitcher_count': 8,
                            'clean_count': 6, 'moderate_count': 2,
                            'severe_count': 0, 'unknown_count': 0,
                            'clean_share': 0.75, 'moderate_share': 0.25,
                            'severe_share': 0.0, 'unknown_share': 0.0,
                            'decisive_rule': 'fresh_coverage',
                            'decisive_inputs': {'clean_count': 6},
                            'thresholds_applied': {
                                'clean_share_fresh_min': [3, 5],
                                'clean_share_fresh_min_value': 0.6,
                                'clean_count_fresh_min': 5,
                                'severe_count_fresh_max': 1,
                                'clean_count_vulnerable_max': 2,
                                'severe_share_vulnerable_min': [1, 3],
                                'severe_share_vulnerable_min_value': 1 / 3,
                            },
                            'trust_state': 'high', 'trust_data_state': 'fresh',
                            'freshness_state': 'current',
                            'material_limitations': [],
                            'evidence_references': {
                                'population_authority': 'resolve_readiness_population',
                            },
                        },
                    }

                # Provide one exact immutable predecessor inside disposable
                # storage. It is never made current; it exists only so the real
                # proof seam can freeze TB-09 against an exact trusted pair.
                previous = DashboardSnapshot(
                    snapshot_type=snapshot.snapshot_type,
                    sync_run_id=run.id,
                    status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                    is_published=False,
                    published_at=utc_now_naive() - timedelta(days=1),
                    payload=deepcopy(snapshot.payload),
                    payload_version=snapshot.payload_version,
                    data_through=snapshot.data_through - timedelta(days=1),
                    availability_reference_date=(
                        snapshot.availability_reference_date - timedelta(days=1)
                    ),
                    snapshot_generated_at=utc_now_naive() - timedelta(days=1),
                    source='trusted_rehearsal_previous',
                )
                db.session.add(previous)
                db.session.flush()
                previous_package = deepcopy(previous.payload['trusted_team_boards'])
                previous_package['data_through'] = previous.data_through.isoformat()
                for team_id, team in previous_package['by_team_id'].items():
                    state_code = (
                        'operationally_constrained'
                        if int(team_id) == TEAM_IDS[0]
                        else 'operationally_stable'
                    )
                    readiness = {
                        'readiness': {'status_code': state_code},
                        'freshness': {'data_through': previous.data_through.isoformat()},
                    }
                    team['frozen_team_state'] = make_receipt(
                        previous, int(team_id), readiness,
                        method_version=EXPECTED_METHOD_VERSION,
                    )
                previous.payload = {
                    **deepcopy(previous.payload),
                    'trusted_team_boards': previous_package,
                }
                current_payload = deepcopy(snapshot.payload)
                current_payload['what_changed_since_yesterday'] = {
                    'comparison': {
                        'identity': build_comparison_identity(snapshot, previous),
                    },
                }
                snapshot.payload = current_payload

                rehearsal_proof = require_transactional_publication_proof(
                    snapshot, readiness_resolver=governed_rehearsal_readiness,
                )
                assert len(rehearsal_proof['snapshot_team_state_generation_inputs']) == 30
                assert len(rehearsal_proof['snapshot_team_state_receipts']) == 30
                observation = build_postcommit_observation(snapshot, rehearsal_proof)
                assert observation['status'] == OBSERVATION_PROOF_VALID
                assert observation['receipt_digest'] == observation['expected_receipt_digest']
                exported_proof = deepcopy(rehearsal_proof)
                exported_proof['postcommit_observation'] = observation
                proof_path = tmp_path / 'team-state-vnext-production-proof.json'
                write_proof(exported_proof, str(proof_path))
                _, proof_valid, proof_reason = validate_proof_file(str(proof_path))
                assert (proof_valid, proof_reason) == (True, 'ok')
                assert set(
                    snapshot.payload['trusted_team_boards'][
                        'frozen_team_state_by_team_id'
                    ]
                ) == {str(team_id) for team_id in TEAM_IDS}
                assert all(
                    'frozen_team_state' in team
                    for team in snapshot.payload['trusted_team_boards']['by_team_id'].values()
                )
                first = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_IDS[0])]
                assert public_serving_authority._published_team_state(
                    snapshot, TEAM_IDS[0],
                ) == first['frozen_team_state']['value']
                changed = first['frozen_what_changed']
                assert changed['contract'] == 'team_board_what_changed_v1'
                assert changed['current_snapshot_id'] == snapshot.id
                assert changed['previous_snapshot_id'] == previous.id
                assert changed['events'][0]['event_type'] == 'team_state_changed'
                assert changed['events'][0]['previous_value'] == 'Stretched'
                assert changed['events'][0]['current_value'] == 'Fresh'
                assert changed['comparison_status'] == 'partial'
                quiet = snapshot.payload['trusted_team_boards']['by_team_id'][str(TEAM_IDS[1])]['frozen_what_changed']
                assert quiet['state'] == 'quiet'
                assert quiet['events'] == []
                assert quiet['quiet_message']
                rehearsal_board = public_serving_authority.build_published_team_board(
                    TEAM_IDS[0], snapshot_override=snapshot,
                    include_delivery_identity=True, include_recent_usage_rest=True,
                )
                rehearsal_identity = build_team_board_identity(snapshot, rehearsal_board)
                rehearsal_details = build_team_board_details_payload(
                    rehearsal_board, publication_identity=rehearsal_identity,
                    recent_relief_work=rehearsal_board['frozen_recent_relief_work'],
                    recent_transactions=rehearsal_board['frozen_roster_transactions'],
                    game_context=None, performance=rehearsal_board['frozen_performance'],
                    what_changed=rehearsal_board['frozen_what_changed'], section_errors={},
                )
                assert rehearsal_details['what_changed'] == changed
                relief = rehearsal_details['recent_relief_work']['read']
                assert relief['contract'] == 'team_board_recent_relief_work_v1'
                assert relief['team_id'] == TEAM_IDS[0]
                assert relief['data_through'] == snapshot.data_through.isoformat()
                assert relief['games'][0]['finality']['game_status'] == 'final'
                assert relief['games'][0]['appearances'][0]['appearance_team_id'] == TEAM_IDS[0]
                assert relief['games'][0]['appearances'][0]['current_roster']['active'] is True
            finally:
                savepoint.rollback()
                db.session.expire(snapshot)
            assert snapshot.is_published is False
            assert run.published_dashboard_snapshot_id is None
            failed_savepoint = db.session.begin_nested()
            try:
                snapshot.status = dashboard_snapshot.SNAPSHOT_STATUS_READY
                snapshot.is_published = True
                snapshot.published_at = utc_now_naive()

                def missing_team_readiness(team_id, **kwargs):
                    if team_id == TEAM_IDS[1]:
                        return None
                    return governed_rehearsal_readiness(team_id, **kwargs)

                with pytest.raises(ValueError, match='missing_team'):
                    require_transactional_publication_proof(
                        snapshot, readiness_resolver=missing_team_readiness,
                    )
            finally:
                failed_savepoint.rollback()
                db.session.expire(snapshot)
            assert snapshot.is_published is False
            assert run.published_dashboard_snapshot_id is None
            assert dashboard_snapshot._payload_slate_coverage_unavailable_reason(
                snapshot.payload
            ) is None
            ledger_reason, ledger = appearance_ledger.appearance_ledger_publish_block(
                end_date=snapshot.data_through,
            )
            assert ledger_reason is None
            assert ledger['complete'] is True
            package = snapshot.payload['trusted_team_boards']
            assert package['team_count'] == len(TEAM_IDS)
            assert len(performance_ms) == len(TEAM_IDS)
            assert rotation_queries == [3]
            assert query_counts['transactions'] == 1
            assert relief_source_queries == [1, 1]
            assert len(relief_projection_ms) == len(TEAM_IDS)
            assert performance_appearance_queries == [1] * len(TEAM_IDS)
            assert set(package['by_team_id']) == {str(team_id) for team_id in TEAM_IDS}
            assert package['data_through'] == snapshot.data_through.isoformat()
            for team_id in TEAM_IDS:
                team = package['by_team_id'][str(team_id)]
                roster_moves = team['frozen_roster_transactions']
                assert roster_moves['contract'] == 'team_board_roster_transactions_v1'
                assert roster_moves['team_id'] == team_id
                assert roster_moves['data_through'] == snapshot.data_through.isoformat()
                assert roster_moves['current_group']['active_pitcher_ids'] == team['default_pitcher_ids']
                if team_id == TEAM_IDS[0]:
                    assert roster_moves['status'] == 'available'
                    assert [item['event_id'] for item in roster_moves['events']] == ['rehearsal-recall']
                    assert roster_moves['events'][0]['direction'] == 'addition'
                    assert roster_moves['events'][0]['current_roster']['membership'] == 'active'
                else:
                    assert roster_moves['events'] == []
                rotation = team['frozen_rotation_impact']
                assert rotation['contract'] == 'team_board_recent_rotation_games_v1'
                assert rotation['team_id'] == team_id
                assert rotation['data_through'] == snapshot.data_through.isoformat()
                if team_id == TEAM_IDS[0]:
                    assert rotation['starts'][0]['starter_name'] == 'Rehearsal Coverage Starter'
                    assert rotation['starts'][0]['starter_outs'] == 27
                    assert rotation['starts'][0]['bullpen_outs'] == 0
                    assert rotation['starts'][0]['short_start'] is False
                assert public_serving_authority.is_valid_rest_status_carrier(
                    team['rest_status']
                )
                _assert_workload_carrier(snapshot, team_id)
                assert team['roles_deployment']['contract'] == 'team_board_public_deployment_context_v1'
                assert team['roles_deployment']['team_id'] == team_id
                assert team['roles_deployment']['data_through'] == snapshot.data_through.isoformat()
                carrier = team['performance']
                assert carrier['contract'] == 'team_board_performance_v1'
                assert carrier['team_id'] == team_id
                assert carrier['data_through'] == snapshot.data_through.isoformat()
                assert carrier['population_pitcher_ids'] == team['default_pitcher_ids']
                read = carrier['read']
                assert read['through'] == carrier['data_through']
                assert [metric['metric_id'] for metric in read['metrics']] == ['M-001', 'M-002']
                assert read['capabilities']['k_bb_percent']['status'] == 'unavailable'
                assert read['capabilities']['home_runs_allowed']['status'] == 'unavailable'
                assert read['capabilities']['inherited_runner_context']['status'] == 'unavailable'
                relief = team['recent_relief_work']
                assert relief['contract'] == 'team_board_recent_relief_work_v1'
                assert relief['team_id'] == team_id
                assert relief['data_through'] == snapshot.data_through.isoformat()
                assert relief['status'] in {'complete', 'partial'}
                assert all(
                    game['finality']['game_status'] == 'final'
                    for game in relief['games']
                )
            public_deployment = package['by_team_id'][str(TEAM_IDS[0])]['roles_deployment']
            assert query_counts['pbp_event'] <= len(TEAM_IDS)
            assert query_counts['processed_game'] <= len(TEAM_IDS)
            serialization_started = perf_counter()
            serialized_context = json.dumps(public_deployment, sort_keys=True)
            all_context = json.dumps({
                team_id: package['by_team_id'][str(team_id)]['roles_deployment']
                for team_id in TEAM_IDS
            }, sort_keys=True)
            serialization_ms = (perf_counter() - serialization_started) * 1000
            performance_serialization_started = perf_counter()
            performance_json = json.dumps({
                team_id: package['by_team_id'][str(team_id)]['performance']
                for team_id in TEAM_IDS
            }, sort_keys=True)
            performance_serialization_ms = (
                perf_counter() - performance_serialization_started
            ) * 1000
            rotation_serialization_started = perf_counter()
            rotation_json = json.dumps({
                team_id: package['by_team_id'][str(team_id)]['frozen_rotation_impact']
                for team_id in TEAM_IDS
            }, sort_keys=True)
            rotation_serialization_ms = (perf_counter() - rotation_serialization_started) * 1000
            roster_serialization_started = perf_counter()
            roster_json = json.dumps({
                team_id: package['by_team_id'][str(team_id)]['frozen_roster_transactions']
                for team_id in TEAM_IDS
            }, sort_keys=True)
            roster_serialization_ms = (perf_counter() - roster_serialization_started) * 1000
            relief_serialization_started = perf_counter()
            relief_json = json.dumps({
                team_id: package['by_team_id'][str(team_id)]['recent_relief_work']
                for team_id in TEAM_IDS
            }, sort_keys=True)
            relief_serialization_ms = (perf_counter() - relief_serialization_started) * 1000
            first_profile = next(item for item in public_deployment['profiles'] if item['pitcher_name'] == 'Rehearsal Pitcher 00')
            assert first_profile['context']['entry_inning']['by_inning'] == [{'inning': 8, 'appearances': 1}]
            assert first_profile['context']['score_context']['leading'] == 1
            assert first_profile['context']['leverage']['high'] == 1
            assert public_deployment['role_movement']['status'] == 'unavailable'
            first = _assert_workload_carrier(snapshot, TEAM_IDS[0])
            for days in (3, 7, 14, 30):
                window = first['windows'][f'window_{days}']
                assert window['pitches'] == {
                    'value': 30, 'status': 'complete', 'reason_codes': [],
                }
                assert window['appearances'] == {
                    'value': 2, 'status': 'complete', 'reason_codes': [],
                }
                assert window['outs'] == {
                    'value': 5, 'status': 'complete', 'reason_codes': [],
                }
            assert first['concentration_7_day']['total_pitches'] == 30
            assert first['concentration_7_day']['top_3_share'] == 1.0
            assert first['concentration_7_day']['active_current_contribution']['pitches'] == 18
            assert first['concentration_7_day']['off_active_contribution']['pitches'] == 12
            assert [item['pitches'] for item in first['concentration_7_day']['contributors']] == [18, 12]
            zero = _assert_workload_carrier(snapshot, TEAM_IDS[-1])['windows']['window_3']
            for name in ('pitches', 'appearances', 'outs'):
                assert zero[name] == {
                    'value': 0, 'status': 'complete', 'reason_codes': [],
                }

            # The serving composers operate on the exact candidate package. The
            # test-only timestamp supplies identity shape without publishing it.
            db.session.expunge(snapshot)
            snapshot.published_at = utc_now_naive()
            team_id = TEAM_IDS[0]
            def no_mutable_workload_read(_conn, _cursor, statement, _params, _context, _many):
                sql = statement.lower()
                if 'game_logs' in sql or 'player_transactions' in sql or 'player_transaction_sync_windows' in sql:
                    raise AssertionError('candidate serving queried mutable workload or transaction rows')

            event.listen(db.engine, 'before_cursor_execute', no_mutable_workload_read)
            try:
                board = public_serving_authority.build_published_team_board(
                    team_id, snapshot_override=snapshot,
                    include_delivery_identity=True, include_recent_usage_rest=True,
                )
                identity = build_team_board_identity(snapshot, board)
                core = build_team_board_core_payload(board, publication_identity=identity)
                details = build_team_board_details_payload(
                    board, publication_identity=identity,
                    recent_relief_work=None,
                    recent_transactions=board['frozen_roster_transactions'],
                    game_context=None, performance=board['frozen_performance'],
                    what_changed=board['frozen_what_changed'],
                    section_errors={},
                )
            finally:
                event.remove(db.engine, 'before_cursor_execute', no_mutable_workload_read)
            assert core['publication_identity'] == details['publication_identity']
            # Active Bullpen workload columns are the frozen governed bullpen
            # workload (the Recent Usage carrier), while the record's physical
            # FatigueScore facts stay exactly as published.
            team_package = package['by_team_id'][str(team_id)]
            usage = team_package['recent_usage_rest']
            assert usage['appearance_policy'] == (
                public_team_relief_work.RECENT_USAGE_REST_APPEARANCE_POLICY
            )
            usage_by_pitcher = {item['pitcher_id']: item for item in usage['active_pitchers']}
            frozen_records = {record['pitcher_id']: record for record in team_package['records']}
            assert core['active_bullpen']['arms']
            for arm in core['active_bullpen']['arms']:
                record = frozen_records[arm['pitcher_id']]
                display = record['bullpen_workload_display']
                assert display['contract'] == (
                    public_team_relief_work.ACTIVE_BULLPEN_WORKLOAD_DISPLAY_CONTRACT
                )
                window = usage_by_pitcher[arm['pitcher_id']]['windows']['last_7_days']
                assert arm['workload']['appearances_last_7'] == window['appearances']['value']
                assert arm['workload']['pitches_last_7_days'] == window['pitches']['value']
                assert arm['last_appearance'] == display['last_appearance']
                score = FatigueScore.query.filter_by(pitcher_id=arm['pitcher_id']).one()
                assert record['workload_facts']['appearances_last_7'] == score.appearances_last_7
                assert record['workload_facts']['pitches_last_7_days'] == score.pitches_last_7_days
            assert details['workload_overview']['frozen_team_workload'] == (
                _assert_workload_carrier(snapshot, team_id)
            )
            assert details['roles_deployment']['frozen_public_deployment'] == public_deployment
            assert details['rotation_impact']['frozen_recent_games'] == (
                package['by_team_id'][str(team_id)]['frozen_rotation_impact']
            )
            assert details['performance'] == package['by_team_id'][str(team_id)]['performance']['read']
            assert details['recent_transactions'] == package['by_team_id'][str(team_id)]['frozen_roster_transactions']
            require_matching_team_board_identity(identity, snapshot, board)
            changed = {**identity, 'snapshot_id': identity['snapshot_id'] + 1}
            try:
                require_matching_team_board_identity(changed, snapshot, board)
            except TeamBoardIdentityMismatch:
                pass
            else:
                raise AssertionError('mismatched publication identity attached')
            assert DashboardSnapshot.query.filter_by(is_published=True).count() == 0
            assert db.session.get(SyncRun, run.id).published_dashboard_snapshot_id is None
            # A pre-TB-04 frozen package remains readable, but cannot acquire
            # the new section from mutable rows at request time.
            older = dict(snapshot.payload)
            older_package = dict(older['trusted_team_boards'])
            older_teams = dict(older_package['by_team_id'])
            older_team = dict(older_teams[str(team_id)])
            older_team.pop('workload_windows')
            older_team.pop('workload_windows_authority')
            older_team.pop('roles_deployment')
            older_team.pop('roles_deployment_authority')
            older_team.pop('performance')
            older_team.pop('frozen_rotation_impact')
            older_team.pop('frozen_rotation_impact_authority')
            older_team.pop('frozen_roster_transactions')
            older_team.pop('frozen_roster_transactions_authority')
            older_team.pop('frozen_what_changed', None)
            older_teams[str(team_id)] = older_team
            older_package['by_team_id'] = older_teams
            older['trusted_team_boards'] = older_package
            snapshot.payload = older
            older_board = public_serving_authority.build_published_team_board(
                team_id, snapshot_override=snapshot, include_recent_usage_rest=True,
            )
            assert older_board['workload_overview'] is None
            assert older_board['frozen_roles_deployment'] is None
            assert older_board['frozen_performance'] is None
            assert older_board['frozen_rotation_impact'] is None
            assert older_board['frozen_roster_transactions'] is None
            assert older_board['frozen_what_changed'] is None
            assert older_board['recent_usage_rest'] is not None
            print(
                f'REHEARSAL candidate_snapshot_id={snapshot.id} sync_run_id={run.id} '
                f'team_count={package["team_count"]} data_through={package["data_through"]} '
                f'published_pointer_moves=0 appearance_queries={query_counts["appearance"]} '
                f'processed_game_queries={query_counts["processed_game"]} '
                f'pbp_event_queries={query_counts["pbp_event"]} '
                f'publication_ms={publication_seconds * 1000:.3f} '
                f'tb05_context_ms={sum(context_ms):.3f} '
                f'tb05_serialize_ms={serialization_ms:.3f} '
                f'tb05_team_bytes={len(serialized_context.encode("utf-8"))} '
                f'tb05_all_team_bytes={len(all_context.encode("utf-8"))}'
                f' tb06_performance_ms={sum(performance_ms):.3f}'
                f' tb06_appearance_queries={sum(performance_appearance_queries)}'
                f' tb06_team_bytes={len(json.dumps(package["by_team_id"][str(team_id)]["performance"]).encode("utf-8"))}'
                f' tb06_all_team_bytes={len(performance_json.encode("utf-8"))}'
                f' tb06_serialize_ms={performance_serialization_ms:.3f}'
                f' tb07_rotation_ms={sum(rotation_ms):.3f}'
                f' tb07_source_queries={sum(rotation_queries)}'
                f' tb07_all_team_bytes={len(rotation_json.encode("utf-8"))}'
                f' tb07_serialize_ms={rotation_serialization_ms:.3f}'
                f' tb08_transaction_queries={query_counts["transactions"]}'
                f' tb08_source_read_ms={sum(roster_read_ms):.3f}'
                f' tb08_projection_ms={sum(roster_projection_ms):.3f}'
                f' tb08_all_team_bytes={len(roster_json.encode("utf-8"))}'
                f' tb08_serialize_ms={roster_serialization_ms:.3f}'
                f' tb10_source_queries={sum(relief_source_queries)}'
                f' tb10_projection_ms={sum(relief_projection_ms):.3f}'
                f' tb10_team_bytes={len(json.dumps(package["by_team_id"][str(team_id)]["recent_relief_work"]).encode("utf-8"))}'
                f' tb10_all_team_bytes={len(relief_json.encode("utf-8"))}'
                f' tb10_serialize_ms={relief_serialization_ms:.3f}'
            )
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_rehearsal_persists_league_artifacts_from_frozen_receipts(monkeypatch):
    """The disposable rehearsal includes the League Board delivery seam."""
    from datetime import datetime

    from models.share_artifact import ShareArtifact
    from models.team_state_publication_proof import TeamStatePublicationProof
    from services import team_state_source
    from services.league_team_state_artifact_recovery import (
        repair_current_snapshot_artifacts,
    )
    from services.league_team_state_listing import build_league_team_state_listing
    from tests.test_share_artifact_batch_generation import _readiness

    url = _test_database_url()
    assert url.startswith(('postgres://', 'postgresql://'))
    assert_disposable_test_target(url, operation='League Board artifact rehearsal')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', url)
    app = importlib.import_module('app').create_app('test')
    with app.app_context():
        create_test_schema(app)
        try:
            product_date = public_serving_authority.product_current_date() - timedelta(days=1)
            run = SyncRun(
                job_name='daily_sync', status='success', stage='published', source='test',
            )
            db.session.add(run)
            db.session.flush()
            snapshot = DashboardSnapshot(
                snapshot_type='bullpen_dashboard', sync_run_id=run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY,
                is_published=True, published_at=datetime(2026, 9, 23, 12),
                payload={}, payload_version=1, data_through=product_date,
                snapshot_generated_at=datetime(2026, 9, 23, 11, 59),
                source='trusted_publication_rehearsal',
            )
            db.session.add(snapshot)
            db.session.flush()
            run.published_dashboard_snapshot_id = snapshot.id

            receipts = {}
            inputs = {}
            for index, team_id in enumerate(TEAM_IDS):
                db.session.add(Pitcher(
                    mlb_id=9800000 + index,
                    full_name=f'Rehearsal Arm {team_id}',
                    team_id=team_id,
                    team_name=f'Rehearsal Team {team_id}',
                    team_abbreviation=f'R{index:02d}',
                    position='P', active=True,
                ))
                readiness = _readiness(team_id)
                readiness['freshness']['data_through'] = product_date.isoformat()
                receipts[str(team_id)] = make_receipt(
                    snapshot, team_id, readiness,
                    method_version=EXPECTED_METHOD_VERSION,
                )
                inputs[str(team_id)] = {
                    'readiness': readiness,
                    'reference_dates': {},
                    'arm_reads': {
                        'team_id': team_id,
                        'membership_reference_date': product_date.isoformat(),
                        'availability_reference_date': (
                            product_date + timedelta(days=1)
                        ).isoformat(),
                        'member_pitcher_ids': [],
                        'missing_record_pitcher_ids': [],
                        'records': [],
                    },
                }
            snapshot.payload = {
                'trusted_team_boards': {
                    'contract': 'trusted_team_board_publication_v1',
                    'data_through': product_date.isoformat(),
                    'by_team_id': {},
                    'frozen_team_state_by_team_id': receipts,
                },
            }
            db.session.add(TeamStatePublicationProof(
                snapshot_id=snapshot.id,
                sync_run_id=run.id,
                data_through=product_date,
                proof={'snapshot_team_state_generation_inputs': inputs},
                overall_verdict='PASS', captured_team_count=30,
                method_version=EXPECTED_METHOD_VERSION,
            ))
            db.session.commit()

            monkeypatch.setattr(
                team_state_source, 'get_latest_dashboard_snapshot',
                lambda *_args, **_kwargs: snapshot,
            )
            monkeypatch.setattr(
                team_state_source, 'snapshot_unavailable_reason',
                lambda *_args, **_kwargs: None,
            )
            monkeypatch.setattr(
                'services.share_artifact_generation.resolve_team_readiness_payload',
                lambda *_args, **_kwargs: pytest.fail(
                    'rehearsal attempted mutable Team State recalculation'
                ),
            )

            first = repair_current_snapshot_artifacts(snapshot)
            second = repair_current_snapshot_artifacts(snapshot)
            assert first.outcome == 'repaired'
            assert first.generated_count == 30
            assert len(first.terminal_outcomes) == 30
            assert {item.outcome for item in first.terminal_outcomes} == {'generated'}
            assert first.reason_histogram == ()
            assert second.outcome == 'already_complete'
            artifacts = ShareArtifact.query.filter_by(
                artifact_type='team_state', source_snapshot_id=snapshot.id,
                lifecycle_state='published',
            ).all()
            assert len(artifacts) == 30
            assert {artifact.team_id for artifact in artifacts} == set(TEAM_IDS)
            assert all(artifact.source_sync_run_id == run.id for artifact in artifacts)

            listing = build_league_team_state_listing(
                snapshot_resolver=lambda: (snapshot, None),
            )
            assert listing['team_count'] == 30
            assert listing['represented_team_count'] == 30
            assert listing['withheld_team_count'] == 0
            for team_id in (110, 119, 147):
                league_state = next(
                    item['team_state'] for item in listing['teams']
                    if item['team_id'] == team_id
                )
                assert league_state['public_state'] == (
                    receipts[str(team_id)]['value']['public_state']
                )
        finally:
            db.session.remove()
            drop_test_schema(app)


def test_rehearsal_accepts_30_accounted_teams_with_sparse_publishable_boards(
    monkeypatch,
):
    """Exercise real candidate assembly with 30 clubs but only 18 board reads."""
    url = _test_database_url()
    assert_disposable_test_target(url, operation='sparse trusted publication rehearsal')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', url)
    app = importlib.import_module('app').create_app('test')
    app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
    with app.app_context():
        create_test_schema(app)
        try:
            reference_date = public_serving_authority.product_current_date()
            _seed_teams(reference_date)
            represented_date = reference_date - timedelta(days=1)
            run = SyncRun(
                job_name='daily_sync', started_at=utc_now_naive(),
                completed_at=utc_now_naive(), status='success', stage='published',
                source='test', latest_game_date=represented_date,
                latest_workload_date=represented_date,
                latest_fatigue_calculated_at=utc_now_naive(),
            )
            db.session.add(run)
            db.session.commit()
            assert public_serving_authority.install_public_serving_authority(app)

            publishable_ids = set(TEAM_IDS[:18])
            original_contexts = public_serving_authority.eligible_bullpen_pitcher_contexts

            def sparse_contexts(*args, **kwargs):
                return [
                    context for context in original_contexts(*args, **kwargs)
                    if context['pitcher'].team_id in publishable_ids
                ]

            monkeypatch.setattr(
                public_serving_authority,
                'eligible_bullpen_pitcher_contexts', sparse_contexts,
            )
            snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
                sync_run_id=run.id, source='sparse_rehearsal',
                publish=False, raise_errors=True,
            )
            package = snapshot.payload['trusted_team_boards']
            assert package['team_count'] == 18
            assert set(package['by_team_id']) == {str(team_id) for team_id in TEAM_IDS[:18]}
            assert not set(package['by_team_id']).intersection(
                {str(team_id) for team_id in NONCANONICAL_TEAM_IDS}
            )
            assert package['team_accounting']['accounted_team_count'] == 30

            def readiness(team_id, *, reference_dates_out, **_kwargs):
                reference_dates_out.update({
                    'membership_reference_date': snapshot.data_through,
                    'availability_reference_date': snapshot.availability_reference_date,
                })
                return {
                    'contract_version': 'v3_phase_5',
                    'team': {
                        'team_id': team_id,
                        'team_name': f'Rehearsal Team {team_id}',
                        'team_abbreviation': f'R{team_id}',
                    },
                    'readiness': {
                        'status_code': 'operationally_stable',
                        'summary': 'Current bullpen state.',
                    },
                    'freshness': {'data_through': snapshot.data_through.isoformat()},
                    'trust_metadata': {'confidence': 'high', 'data_state': 'fresh'},
                    'team_state_evidence': {
                        'method_version': 'v3_phase_5',
                        'contract': 'team_state_contract_a', 'basis': 'status_only',
                        'readiness_status_code': 'operationally_stable',
                        'active_pitcher_count': 8, 'clean_count': 6,
                        'moderate_count': 2, 'severe_count': 0, 'unknown_count': 0,
                        'clean_share': 0.75, 'moderate_share': 0.25,
                        'severe_share': 0.0, 'unknown_share': 0.0,
                        'decisive_rule': 'fresh_coverage',
                        'decisive_inputs': {'clean_count': 6},
                        'thresholds_applied': {
                            'clean_share_fresh_min': [3, 5],
                            'clean_share_fresh_min_value': 0.6,
                            'clean_count_fresh_min': 5,
                            'severe_count_fresh_max': 1,
                            'clean_count_vulnerable_max': 2,
                            'severe_share_vulnerable_min': [1, 3],
                            'severe_share_vulnerable_min_value': 1 / 3,
                        },
                        'trust_state': 'high', 'trust_data_state': 'fresh',
                        'freshness_state': 'current', 'material_limitations': [],
                        'evidence_references': {
                            'population_authority': 'resolve_readiness_population',
                        },
                    },
                }

            from services.team_state_vnext_production_proof import (
                require_transactional_publication_proof,
            )
            savepoint = db.session.begin_nested()
            try:
                snapshot.status = dashboard_snapshot.SNAPSHOT_STATUS_READY
                snapshot.is_published = True
                snapshot.published_at = utc_now_naive()
                proof = require_transactional_publication_proof(
                    snapshot, readiness_resolver=readiness,
                )
                package = snapshot.payload['trusted_team_boards']
                assert len(proof['teams']) == 30
                assert len(package['frozen_team_state_by_team_id']) == 30
                assert len(package['by_team_id']) == 18
                assert set(package['frozen_team_state_by_team_id']) == {
                    str(team_id) for team_id in TEAM_IDS
                }
            finally:
                savepoint.rollback()
                db.session.expire(snapshot)
            assert DashboardSnapshot.query.filter_by(is_published=True).count() == 0
            assert db.session.get(SyncRun, run.id).published_dashboard_snapshot_id is None
        finally:
            db.session.rollback()
            db.session.remove()
            drop_test_schema(app)


@pytest.mark.parametrize('env', [
    {},
    {'TEST_DATABASE_URL': 'sqlite:///:memory:'},
    {'TEST_DATABASE_URL': 'postgresql://test@db.example/baseballos_rehearsal_test'},
    {'TEST_DATABASE_URL': 'postgresql://test@localhost/baseballos_test'},
    {
        'TEST_DATABASE_URL': 'postgresql://test@localhost/baseballos_rehearsal_test',
        'DATABASE_URL': 'postgresql://production@db.example/baseballos',
    },
    {
        'TEST_DATABASE_URL': 'postgresql://test@localhost/baseballos_rehearsal_test',
        'APP_ENV': 'production',
    },
])
def test_rehearsal_refuses_unsafe_targets(env):
    with pytest.raises(RuntimeError):
        assert_rehearsal_target(env)


# ── Tonight v1: publication → projection → serving certification ─────────────
#
# The candidate rehearsal above never moves the trusted pointer. Tonight v1 is
# downstream of a *committed* trusted publication, so these rehearsals publish
# for real through the canonical publisher (with the mandatory Team State proof
# enabled, as in production) and then prove the tonight_v1 chain against that
# exact snapshot: post-commit projection, immutable row, Team Board parity,
# public serving, delivery identity, and failure isolation.

TONIGHT_STRETCHED_TEAM = TEAM_IDS[1]
TONIGHT_V1_URL = '/api/bullpen/intelligence/tonight?contract=tonight_v1'


def _tonight_rehearsal_readiness(original):
    """Governed readiness at the proof seam; one club reads Stretched.

    The partitions satisfy Contract A exactly (6/8 clean is fresh coverage,
    4/8 clean with no severe arms is residual stretched), so the real proof
    reproduces each decision rather than stamping it. Callers outside the
    proof seam (no ``source_snapshot``) keep the installed resolver.
    """
    def resolver(team_id, *args, reference_dates_out=None, source_snapshot=None,
                 **kwargs):
        if source_snapshot is None or reference_dates_out is None:
            return original(team_id, *args, **kwargs)
        return _governed_readiness(team_id, reference_dates_out, source_snapshot)
    return resolver


def _governed_readiness(team_id, reference_dates_out, source_snapshot):
    stretched = team_id == TONIGHT_STRETCHED_TEAM
    clean, moderate = (4, 4) if stretched else (6, 2)
    status_code = 'operationally_constrained' if stretched else 'operationally_stable'
    reference_dates_out.update({
        'membership_reference_date': source_snapshot.data_through,
        'availability_reference_date': source_snapshot.availability_reference_date,
    })
    return {
        'contract_version': 'v3_phase_5',
        'team': {
            'team_id': team_id, 'team_name': f'Rehearsal Team {team_id}',
            'team_abbreviation': f'R{team_id}',
        },
        'readiness': {'status_code': status_code, 'summary': 'Current bullpen state.'},
        'freshness': {'data_through': source_snapshot.data_through.isoformat()},
        'trust_metadata': {'confidence': 'high', 'data_state': 'fresh'},
        'team_state_evidence': {
            'method_version': 'v3_phase_5',
            'contract': 'team_state_contract_a', 'basis': 'status_only',
            'readiness_status_code': status_code,
            'active_pitcher_count': 8, 'clean_count': clean,
            'moderate_count': moderate, 'severe_count': 0, 'unknown_count': 0,
            'clean_share': clean / 8, 'moderate_share': moderate / 8,
            'severe_share': 0.0, 'unknown_share': 0.0,
            'decisive_rule': 'residual_stretched' if stretched else 'fresh_coverage',
            'decisive_inputs': {'clean_count': clean},
            'thresholds_applied': {
                'clean_share_fresh_min': [3, 5],
                'clean_share_fresh_min_value': 0.6,
                'clean_count_fresh_min': 5,
                'severe_count_fresh_max': 1,
                'clean_count_vulnerable_max': 2,
                'severe_share_vulnerable_min': [1, 3],
                'severe_share_vulnerable_min_value': 1 / 3,
            },
            'trust_state': 'high', 'trust_data_state': 'fresh',
            'freshness_state': 'current', 'material_limitations': [],
            'evidence_references': {
                'population_authority': 'resolve_readiness_population',
            },
        },
    }


def _seed_tonight_extras(reference_date):
    """Minimum Tonight inputs: a B2B / 3-in-4 reliever and a small slate.

    Team 0's reliever also worked two and four days before the reference
    date, inside Team 0's already-final games, so the ledger stays complete.
    """
    from models.slate_game import SlateGame

    reliever = Pitcher.query.filter_by(mlb_id=7900000).one()
    for offset, game_pk in ((2, 7800001), (4, 7800003)):
        db.session.add(GameLog(
            pitcher_id=reliever.id, mlb_game_pk=game_pk,
            game_date=reference_date - timedelta(days=offset), game_type='R',
            games_started=0, innings_pitched=1.0, innings_pitched_outs=3,
            pitches_thrown=14, appearance_team_id=TEAM_IDS[0],
            appearance_team_status=GameLog.APPEARANCE_TEAM_RESOLVED,
        ))
        PostgameProcessedGame.query.filter_by(mlb_game_pk=game_pk).one().pitching_lines_seen = 2
    first = utc_now_naive().replace(
        year=reference_date.year, month=reference_date.month, day=reference_date.day,
        hour=23, minute=5, second=0, microsecond=0,
    )
    db.session.add_all([
        SlateGame(game_pk=7600001, game_date_et=reference_date, game_time_utc=first,
                  away_team_id=TEAM_IDS[1], home_team_id=TEAM_IDS[0],
                  normalized_state='upcoming', status_detailed='Scheduled', game_number=1),
        SlateGame(game_pk=7600002, game_date_et=reference_date,
                  game_time_utc=first - timedelta(hours=3),
                  away_team_id=TEAM_IDS[3], home_team_id=TEAM_IDS[2],
                  normalized_state='cancelled', status_detailed='Postponed', game_number=1),
    ])
    db.session.commit()


def _tonight_pointer():
    current = dashboard_snapshot.get_latest_valid_dashboard_snapshot()
    published = [
        (row.id, row.published_at)
        for row in DashboardSnapshot.query.filter_by(is_published=True).all()
    ]
    runs = sorted(
        (run.id, run.published_dashboard_snapshot_id) for run in SyncRun.query.all()
    )
    return (current.id if current is not None else None, published, runs)


class _TonightRehearsal:
    """A disposable app with the canonical publisher and production gates."""

    def __init__(self, monkeypatch, *, name):
        from services import share_artifact_generation

        self.monkeypatch = monkeypatch
        url = _test_database_url()
        assert url.startswith(('postgres://', 'postgresql://'))
        assert_disposable_test_target(url, operation=name)
        monkeypatch.setenv('APP_ENV', 'test')
        monkeypatch.setenv('DATABASE_URL', url)
        self.app = importlib.import_module('app').create_app('test')
        self.app.config['TRUSTED_PUBLIC_SERVING_ENABLED'] = True
        # Production gates: publication requires the Team State proof and runs
        # the tonight_v1 projection after commit.
        self.app.config['TEAM_STATE_PUBLICATION_PROOF_REQUIRED'] = True
        self.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
        monkeypatch.setattr(
            share_artifact_generation, 'resolve_team_readiness_payload',
            _tonight_rehearsal_readiness(
                share_artifact_generation.resolve_team_readiness_payload,
            ),
        )

    def setup(self):
        create_test_schema(self.app)
        self.reference_date = public_serving_authority.product_current_date()
        _seed_teams(self.reference_date)
        _seed_tonight_extras(self.reference_date)
        assert public_serving_authority.install_public_serving_authority(self.app)

    def publish(self, source):
        represented = self.reference_date - timedelta(days=1)
        run = SyncRun(
            job_name='daily_sync', started_at=utc_now_naive() - timedelta(minutes=2),
            completed_at=utc_now_naive(), status='success', stage='published',
            source='test', latest_game_date=represented,
            latest_workload_date=represented,
            latest_fatigue_calculated_at=utc_now_naive(),
        )
        db.session.add(run)
        db.session.commit()
        snapshot = dashboard_snapshot.build_bullpen_dashboard_snapshot(
            sync_run_id=run.id, source=source, publish=True, raise_errors=True,
        )
        assert snapshot.is_published is True, (snapshot.status, snapshot.error_message)
        assert snapshot.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
        assert dashboard_snapshot.get_latest_valid_dashboard_snapshot().id == snapshot.id
        assert db.session.get(SyncRun, run.id).published_dashboard_snapshot_id == snapshot.id
        return snapshot


def _forbid_live_tonight_engines(monkeypatch, active):
    """Live engines raise while ``active['on']``; otherwise they run normally."""
    import services.bullpen_context as bullpen_context
    import services.tonight_candidate_selection as candidate_selection
    import services.tonight_intelligence_service as tonight_service
    from services import tonight_intelligence_snapshot

    def guard(module, name):
        original = getattr(module, name)

        def guarded(*args, **kwargs):
            if active['on']:
                raise AssertionError(f'tonight_v1 reached {module.__name__}.{name}')
            return original(*args, **kwargs)
        monkeypatch.setattr(module, name, guarded)

    guard(bullpen_context, 'build_team_bullpen_context')
    guard(candidate_selection, 'build_tonight_candidates')
    guard(tonight_service, 'serve_tonight')
    guard(tonight_intelligence_snapshot, 'serve_tonight_cached')


class _SqlRecorder:
    def __init__(self):
        self.statements = []

    def __enter__(self):
        event.listen(db.engine, 'before_cursor_execute', self._record)
        return self

    def __exit__(self, *_exc):
        event.remove(db.engine, 'before_cursor_execute', self._record)

    def _record(self, _conn, _cursor, statement, _params, _context, _many):
        self.statements.append(statement.lower())

    def count(self, *needles):
        return sum(1 for sql in self.statements if any(n in sql for n in needles))

    def writes(self):
        return [
            sql for sql in self.statements
            if sql.lstrip().startswith(('insert', 'update', 'delete'))
        ]


def test_rehearsal_certifies_tonight_v1_publication_and_serving(monkeypatch):
    from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot
    from models.tonight_publication import TonightPublication, TonightPublicationImmutable
    from services import public_delivery, tonight_intelligence_snapshot, tonight_read_model

    rehearsal = _TonightRehearsal(monkeypatch, name='Tonight v1 rehearsal')
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            # Legacy tonight_v5 storage exists before publication and must not move.
            tonight_intelligence_snapshot.write_snapshot(
                {'status': 'empty', 'reference_date': rehearsal.reference_date.isoformat(),
                 'cards': [], 'card_count': 0, 'games': [], 'game_count': 0,
                 'empty_reason': 'no_tonight_signals', 'limitations': []},
                source='legacy_rehearsal',
            )
            legacy_before = [
                (row.id, row.response_json, row.generated_at)
                for row in TonightIntelligenceSnapshot.query.all()
            ]

            # Phases 3/5/10: wrap the real post-commit projection so its SQL,
            # engine calls and pointer effect are measured inside publication.
            engines = {'on': False}
            _forbid_live_tonight_engines(monkeypatch, engines)
            generation = {}
            original_generate = tonight_read_model.generate_tonight_v1_after_publication

            def measured_generate(snapshot):
                generation['pointer_before'] = _tonight_pointer()
                engines['on'] = True
                try:
                    with _SqlRecorder() as sql:
                        result = original_generate(snapshot)
                finally:
                    engines['on'] = False
                generation.update(result=result, sql=sql)
                generation['pointer_after'] = _tonight_pointer()
                return result

            monkeypatch.setattr(
                tonight_read_model, 'generate_tonight_v1_after_publication',
                measured_generate,
            )

            # Phase 2: one real trusted publication through the canonical path.
            snapshot = rehearsal.publish('tonight_rehearsal')
            receipts = snapshot.payload['trusted_team_boards']['frozen_team_state_by_team_id']
            assert set(receipts) == {str(team_id) for team_id in TEAM_IDS}
            identity = {
                'dashboard_snapshot_id': snapshot.id,
                'sync_run_id': snapshot.sync_run_id,
                'data_through': snapshot.data_through,
                'availability_reference_date': snapshot.availability_reference_date,
                'published_at': snapshot.published_at,
            }
            assert identity['availability_reference_date'] == rehearsal.reference_date

            # Phase 3: exactly one immutable row, bound to that snapshot.
            assert generation['result']['status'] == 'created'
            rows = TonightPublication.query.all()
            assert len(rows) == 1
            row = rows[0]
            assert generation['result']['tonight_publication_id'] == row.id
            assert (row.contract, row.dashboard_snapshot_id, row.sync_run_id,
                    row.data_through, row.reference_date,
                    row.availability_reference_date) == (
                'tonight_v1', snapshot.id, snapshot.sync_run_id, snapshot.data_through,
                snapshot.availability_reference_date, snapshot.availability_reference_date,
            )
            assert len(row.content_sha256) == 64
            assert row.content_sha256 == tonight_read_model.content_sha256(row.payload)
            edition = row.payload['edition']
            assert edition['publication']['dashboard_snapshot_id'] == snapshot.id
            assert edition['publication']['sync_run_id'] == snapshot.sync_run_id
            assert edition['data_through'] == snapshot.data_through.isoformat()
            assert edition['baseball_date'] == row.reference_date.isoformat()
            assert row.payload['summary']['games_by_state']['postponed'] == 1
            assert row.payload['summary']['game_count'] == 2

            # Phase 5: no second bullpen engine during generation.
            gen_sql = generation['sql']
            assert gen_sql.count('game_logs') == 0
            assert gen_sql.count('fatigue_scores') == 0
            generation_query_count = len(gen_sql.statements)

            # Phase 10: projection moved no trusted pointer.
            assert generation['pointer_before'] == generation['pointer_after']
            assert generation['pointer_after'][0] == snapshot.id

            # Phase 4: TeamSide parity with the served Team Board of this snapshot.
            client = rehearsal.app.test_client()
            sides = {}
            for game in row.payload['games']:
                for key in ('away', 'home'):
                    sides[game[key]['team_id']] = game[key]
            parity_teams = (TEAM_IDS[0], TEAM_IDS[1], TEAM_IDS[2], TEAM_IDS[3])
            for team_id in parity_teams:
                side = sides[team_id]
                core = client.get(f'/api/bullpen/teams/{team_id}/board-v2/core').get_json()
                assert core['publication_identity']['snapshot_id'] == snapshot.id
                board = public_serving_authority.build_published_team_board(
                    team_id, snapshot_override=snapshot, include_recent_usage_rest=True,
                )
                assert side['available'] is True
                assert side['team_state']['public_state'] == core['team_state']['public_state']
                assert side['team_state']['public_label'] == core['team_state']['public_label']
                rest = core['rest_status']
                for name in ('active_arm_count', 'rested_arm_count',
                             'worked_yesterday_count', 'back_to_back_count'):
                    assert side['rest'][name] == rest[name]
                assert side['rest']['active_arm_count'] == core['active_bullpen']['arm_count']
                window = board['workload_overview']['windows']['window_7']
                for name in ('appearances', 'pitches', 'outs'):
                    assert side['workload_7d'][name] == window[name]['value']
                arms = core['active_bullpen']['arms']
                arm_ids = {arm['pitcher_id'] for arm in arms}
                assert side['multi_day_usage']['three_in_four_count'] == sum(
                    1 for item in board['recent_usage_rest']['active_pitchers']
                    if item['pitcher_id'] in arm_ids and item['three_in_four']['value'] is True
                )
                governed = sorted(
                    (arm for arm in arms
                     if (arm.get('public_role_read') or {}).get('key') in ('trust_arm', 'bridge_arm')),
                    key=lambda arm: (
                        ('trust_arm', 'bridge_arm').index(arm['public_role_read']['key']),
                        str(arm['name']).casefold(), arm['pitcher_id'],
                    ),
                )[:3]
                assert [arm['pitcher_id'] for arm in side['key_arms']] == [
                    arm['pitcher_id'] for arm in governed
                ]
                rotation = board['frozen_rotation_impact']
                if (rotation or {}).get('short_start_count'):
                    assert side['rotation']['short_start_count'] == rotation['short_start_count']
                else:
                    assert side['rotation'] is None
            # The fixture carries the facts the rehearsal is meant to exercise.
            assert sides[TEAM_IDS[0]]['team_state']['public_state'] == 'fresh'
            assert sides[TONIGHT_STRETCHED_TEAM]['team_state']['public_state'] == 'stretched'
            assert sides[TEAM_IDS[0]]['rest']['back_to_back_count'] == 1
            assert sides[TEAM_IDS[0]]['multi_day_usage']['three_in_four_count'] == 1
            assert row.payload['summary']['clubs_with_back_to_back_arms'] == 1

            # Phase 6: same-publication rebuild reuses the row; no ORM rewrite.
            again, outcome = tonight_read_model.generate_tonight_v1_for_snapshot(snapshot)
            assert (outcome, again.id, again.content_sha256) == (
                'reused', row.id, row.content_sha256,
            )
            stored_payload = deepcopy(row.payload)
            row.payload = {'contract': 'tampered'}
            with pytest.raises(TonightPublicationImmutable):
                db.session.commit()
            db.session.rollback()
            assert db.session.get(TonightPublication, row.id).payload == stored_payload
            assert TonightPublication.query.count() == 1

            # Phases 7/8: public serving returns the stored row, identified.
            pointer_before_serving = _tonight_pointer()
            engines['on'] = True
            monkeypatch.setattr(tonight_read_model, 'build_tonight_v1', lambda *a, **k: pytest.fail('build'))
            monkeypatch.setattr(tonight_read_model, 'generate_tonight_v1_for_snapshot', lambda *a, **k: pytest.fail('generate'))
            with _SqlRecorder() as serve_sql:
                response = client.get(TONIGHT_V1_URL)
            assert response.status_code == 200
            body = response.get_json()
            assert body == stored_payload
            assert body['edition']['publication']['dashboard_snapshot_id'] == snapshot.id
            assert response.headers['X-BaseballOS-Snapshot-ID'] == str(snapshot.id)
            assert response.headers['X-BaseballOS-Sync-Run-ID'] == str(snapshot.sync_run_id)
            assert response.headers['X-BaseballOS-Data-Through'] == snapshot.data_through.isoformat()
            assert response.headers['X-BaseballOS-Contract'] == 'tonight_v1'
            assert response.headers['ETag'] == f'"{row.content_sha256}"'
            assert response.headers['Cache-Control'] == public_delivery.CURRENT_ALIAS_CACHE_CONTROL
            assert serve_sql.count('game_logs') == 0
            assert serve_sql.count('fatigue_scores') == 0
            assert serve_sql.writes() == []
            serving_query_count = len(serve_sql.statements)
            # Trusted snapshot + tonight_publications row + one slate_games overlay read.
            assert serving_query_count <= 3, serve_sql.statements

            with _SqlRecorder() as not_modified_sql:
                not_modified = client.get(
                    TONIGHT_V1_URL, headers={'If-None-Match': response.headers['ETag']},
                )
            engines['on'] = False
            assert not_modified.status_code == 304
            assert not_modified.get_data() == b''
            assert not_modified_sql.count('game_logs', 'fatigue_scores') == 0
            assert not_modified_sql.writes() == []
            assert _tonight_pointer() == pointer_before_serving

            # Phase 9 (TN-03): only canonical slate_games moves; the served card's
            # game state follows it while every bullpen fact stays frozen.
            from models.slate_game import SlateGame
            engines['on'] = True
            stored_game = next(g for g in stored_payload['games'] if g['game_pk'] == 7600001)
            assert stored_game['state'] == 'scheduled'
            # TN-04: one frozen, descriptive sentence authored from the two TeamSides.
            stored_context = stored_game['context']
            assert stored_context == tonight_read_model.present_matchup_context(
                tonight_read_model.build_matchup_context(stored_game['away'], stored_game['home']),
                'scheduled',
            )
            assert stored_context['sentence'] is not None
            assert stored_context['reason_codes'][0] in tonight_read_model.CONTEXT_PRIORITY
            assert next(
                g for g in body['games'] if g['game_pk'] == 7600001
            )['context'] == stored_context
            stored_as_of = datetime.fromisoformat(stored_game['state_as_of'].rstrip('Z'))
            overlay_etags = [response.headers['ETag']]
            for minutes, normalized, detailed, public_state in (
                (5, 'live', 'In Progress', 'live'),
                (190, 'completed', 'Final', 'final'),
            ):
                slate_row = db.session.get(SlateGame, 7600001)
                slate_row.normalized_state, slate_row.status_detailed = normalized, detailed
                slate_row.last_synced = stored_as_of + timedelta(minutes=minutes)
                db.session.commit()
                with _SqlRecorder() as overlay_sql:
                    overlay = client.get(TONIGHT_V1_URL)
                served_game = next(
                    g for g in overlay.get_json()['games'] if g['game_pk'] == 7600001
                )
                assert overlay.status_code == 200
                assert served_game['state'] == public_state
                assert {key: value for key, value in served_game.items()
                        if key not in ('state', 'state_as_of', 'context')} == {
                    key: value for key, value in stored_game.items()
                    if key not in ('state', 'state_as_of', 'context')
                }
                if public_state == 'live':
                    assert served_game['context']['sentence'] == stored_context['sentence']
                    assert served_game['context']['reason_codes'][-1] == 'pregame_context'
                else:
                    assert served_game['context']['sentence'] is None
                    assert served_game['context']['reason_codes'][-1] == 'pregame_context_hidden'
                assert served_game['context']['evidence_state'] == stored_context['evidence_state']
                assert overlay.headers['X-BaseballOS-Snapshot-ID'] == str(snapshot.id)
                assert overlay_sql.count('game_logs', 'fatigue_scores') == 0
                assert overlay_sql.writes() == []
                assert len(overlay_sql.statements) <= 3, overlay_sql.statements
                overlay_etags.append(overlay.headers['ETag'])
            engines['on'] = False
            assert len(set(overlay_etags)) == 3
            db.session.expire_all()
            assert db.session.get(TonightPublication, row.id).payload == stored_payload
            assert db.session.get(TonightPublication, row.id).content_sha256 == row.content_sha256
            assert _tonight_pointer() == pointer_before_serving

            # Phase 11: legacy tonight_v5 storage untouched.
            assert [
                (row_.id, row_.response_json, row_.generated_at)
                for row_ in TonightIntelligenceSnapshot.query.all()
            ] == legacy_before

            print(
                'REHEARSAL tonight_v1 '
                f'status={generation["result"]["status"]} row_id={row.id} '
                f'contract={row.contract} dashboard_snapshot_id={row.dashboard_snapshot_id} '
                f'sync_run_id={row.sync_run_id} reference_date={row.reference_date} '
                f'data_through={row.data_through} content_sha256={row.content_sha256} '
                f'generation_queries={generation_query_count} '
                f'serving_queries={serving_query_count} '
                f'game_log_queries=0 fatigue_score_queries=0 '
                f'tonight_pointer_moves=0 parity_teams={len(parity_teams)} '
                f'delivery_headers=PASS etag=PASS not_modified=PASS '
                f'overlay=scheduled->live->final overlay_etags_distinct={len(set(overlay_etags))} '
                f'context_reason={stored_context["reason_codes"][0]} '
                f'context_sentence="{stored_context["sentence"]}" '
                'context_live=pregame context_final=hidden'
            )
        finally:
            db.session.rollback()
            db.session.remove()
            drop_test_schema(rehearsal.app)


def test_rehearsal_tonight_v1_never_serves_a_stale_row(monkeypatch):
    from models.tonight_publication import TonightPublication
    from services import tonight_read_model

    rehearsal = _TonightRehearsal(monkeypatch, name='Tonight v1 stale-row rehearsal')
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            client = rehearsal.app.test_client()
            snapshot_a = rehearsal.publish('tonight_rehearsal_a')
            row_a = tonight_read_model.read_tonight_v1(
                snapshot_a.availability_reference_date, snapshot_a.id,
            )
            assert row_a is not None
            row_a_identity = (row_a.id, row_a.content_sha256, deepcopy(row_a.payload))
            assert client.get(TONIGHT_V1_URL).headers['ETag'] == f'"{row_a.content_sha256}"'

            # B is published for the same date without its projection.
            rehearsal.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = False
            snapshot_b = rehearsal.publish('tonight_rehearsal_b')
            assert snapshot_b.id != snapshot_a.id
            assert snapshot_b.availability_reference_date == snapshot_a.availability_reference_date
            assert TonightPublication.query.count() == 1

            stale = client.get(TONIGHT_V1_URL)
            assert stale.status_code == 200
            body = stale.get_json()
            assert body['status'] == 'unavailable'
            assert body['reason_codes'] == ['tonight_v1_publication_missing']
            assert body['current_publication']['dashboard_snapshot_id'] == snapshot_b.id
            assert body['games'] == []
            assert 'ETag' not in stale.headers

            # B's projection through the real hook; B serves, A is preserved.
            rehearsal.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
            dashboard_snapshot.run_post_commit_snapshot_publication(snapshot_b)
            row_b = tonight_read_model.read_tonight_v1(
                snapshot_b.availability_reference_date, snapshot_b.id,
            )
            assert row_b is not None and row_b.id != row_a.id
            current = client.get(TONIGHT_V1_URL)
            assert current.get_json()['edition']['publication']['dashboard_snapshot_id'] == snapshot_b.id
            assert current.headers['ETag'] == f'"{row_b.content_sha256}"'
            preserved = db.session.get(TonightPublication, row_a.id)
            assert (preserved.id, preserved.content_sha256, preserved.payload) == row_a_identity
            print(
                'REHEARSAL tonight_v1_stale_row '
                f'snapshot_a={snapshot_a.id} snapshot_b={snapshot_b.id} '
                f'row_a={row_a.id} row_b={row_b.id} stale_served=False'
            )
        finally:
            db.session.rollback()
            db.session.remove()
            drop_test_schema(rehearsal.app)


def test_rehearsal_tonight_v1_failure_never_invalidates_publication(monkeypatch, caplog):
    from models.tonight_publication import TonightPublication
    from services import tonight_read_model

    rehearsal = _TonightRehearsal(monkeypatch, name='Tonight v1 failure rehearsal')
    with rehearsal.app.app_context():
        try:
            rehearsal.setup()
            snapshot_a = rehearsal.publish('tonight_rehearsal_prior')
            prior = tonight_read_model.read_tonight_v1(
                snapshot_a.availability_reference_date, snapshot_a.id,
            )
            prior_identity = (prior.id, prior.content_sha256, deepcopy(prior.payload))

            def failing_build(*_args, **_kwargs):
                raise RuntimeError('rehearsal tonight_v1 projection failure')

            monkeypatch.setattr(tonight_read_model, 'build_tonight_v1', failing_build)
            with caplog.at_level('ERROR'):
                snapshot_b = rehearsal.publish('tonight_rehearsal_fail')

            # The publication committed and is the trusted pointer.
            refreshed = db.session.get(DashboardSnapshot, snapshot_b.id)
            assert refreshed.is_published is True
            assert refreshed.status == dashboard_snapshot.SNAPSHOT_STATUS_READY
            assert dashboard_snapshot.snapshot_unavailable_reason(refreshed) is None
            assert _tonight_pointer()[0] == snapshot_b.id
            # No partial row; the prior row is untouched; the failure is logged.
            assert tonight_read_model.read_tonight_v1(
                snapshot_b.availability_reference_date, snapshot_b.id,
            ) is None
            assert TonightPublication.query.count() == 1
            kept = db.session.get(TonightPublication, prior.id)
            assert (kept.id, kept.content_sha256, kept.payload) == prior_identity
            assert f'tonight_v1 projection failed non-fatally snapshot_id={snapshot_b.id}' in caplog.text
            # Current v1 fails closed rather than serving the prior snapshot's row.
            body = rehearsal.app.test_client().get(TONIGHT_V1_URL).get_json()
            assert body['reason_codes'] == ['tonight_v1_publication_missing']
        finally:
            db.session.rollback()
            db.session.remove()
            drop_test_schema(rehearsal.app)


def test_rehearsal_withheld_candidate_never_becomes_a_publication(monkeypatch):
    """SyncRun 92585 rehearsal: the real completion path, the real candidate
    store, and the real slate-coverage gate withhold a candidate whose final game
    is not fully ingested. The pending row survives as evidence, the trusted
    pointer never moves, and the run reports the slate reason instead of a League
    Board artifact failure."""
    from datetime import datetime

    from api import bullpen as bullpen_api
    from models.share_artifact import ShareArtifact
    from models.team_state_publication_proof import TeamStatePublicationProof
    from models.tonight_publication import TonightPublication
    from services import sync as sync_service
    from services import sync_metadata

    url = _test_database_url()
    assert url.startswith(('postgres://', 'postgresql://'))
    assert_disposable_test_target(url, operation='withheld publication rehearsal')
    monkeypatch.setenv('APP_ENV', 'test')
    monkeypatch.setenv('DATABASE_URL', url)
    app = importlib.import_module('app').create_app('test')
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
    app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    with app.app_context():
        create_test_schema(app)
        try:
            data_through = public_serving_authority.product_current_date() - timedelta(days=1)
            prior_run = SyncRun(
                job_name='daily_sync', status='success', stage='published', source='test',
            )
            db.session.add(prior_run)
            db.session.flush()
            trusted = DashboardSnapshot(
                snapshot_type='bullpen_dashboard', sync_run_id=prior_run.id,
                status=dashboard_snapshot.SNAPSHOT_STATUS_READY, is_published=True,
                published_at=datetime(2026, 9, 24, 6, 3), payload={'trusted': True},
                payload_version=1, data_through=data_through - timedelta(days=1),
                snapshot_generated_at=datetime(2026, 9, 24, 6, 2),
                source='scheduled_sync',
            )
            db.session.add(trusted)
            db.session.flush()
            prior_run.published_dashboard_snapshot_id = trusted.id
            # One final game on the represented slate with no postgame marker:
            # final_games_not_fully_ingested -> the slate gate must withhold.
            for team_id, opponent_id, side in ((147, 141, 'home'), (141, 147, 'away')):
                db.session.add(ScheduledGame(
                    team_id=team_id, opponent_team_id=opponent_id, home_away=side,
                    game_pk=776001, game_date=data_through, game_type='R',
                    status_code='F', status_state=ScheduledGame.STATE_FINAL,
                ))
            run = SyncRun(
                job_name='daily_sync', status='running', stage='started',
                source='scheduled', started_at=utc_now_naive(),
            )
            db.session.add(run)
            db.session.commit()
            trusted_id, run_id, prior_run_id = trusted.id, run.id, prior_run.id
            published_before = {
                row.id for row in DashboardSnapshot.query.filter_by(is_published=True)
            }

            # The heavy league payload is not under test; the gate reads only the
            # represented date, then computes coverage from the seeded schedule.
            monkeypatch.setattr(
                bullpen_api, 'build_bullpen_dashboard_payload',
                lambda *_args, **_kwargs: {
                    'freshness': {
                        'data_through': data_through.isoformat(),
                        'availability_reference_date': (
                            data_through + timedelta(days=1)
                        ).isoformat(),
                    },
                },
            )
            side_effects = []
            monkeypatch.setattr(
                'services.league_team_state_artifact_recovery.require_complete_artifact_set',
                lambda *_a, **_k: side_effects.append('artifact_gate'),
            )
            monkeypatch.setattr(
                'services.tonight_read_model.generate_tonight_v1_after_publication',
                lambda *_a, **_k: side_effects.append('tonight_v1'),
            )
            monkeypatch.setattr(
                'services.team_state_vnext_production_proof.capture_publication_proof',
                lambda *_a, **_k: side_effects.append('team_state_generation'),
            )

            with pytest.raises(sync_service.DashboardSnapshotPublicationWithheld) as raised:
                sync_service.complete_sync_run_with_snapshot(
                    run_id, final_status='success', source='scheduled',
                    snapshot_source='scheduled_sync',
                )

            reason = dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE
            assert str(raised.value) == reason
            assert side_effects == []
            db.session.remove()

            candidate = DashboardSnapshot.query.filter_by(sync_run_id=run_id).one()
            assert raised.value.snapshot_id == candidate.id
            assert candidate.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING
            assert candidate.is_published is False
            assert candidate.published_at is None
            assert candidate.error_message == reason
            assert candidate.data_through == data_through
            coverage = candidate.payload['freshness']['slate_coverage']
            assert coverage['validations_passed'] is False
            assert 'final_games_not_fully_ingested' in coverage['reason_codes']

            published_after = {
                row.id for row in DashboardSnapshot.query.filter_by(is_published=True)
            }
            assert published_after == published_before == {trusted_id}
            assert db.session.get(DashboardSnapshot, trusted_id).is_published is True
            assert dashboard_snapshot.get_latest_dashboard_snapshot().id == trusted_id

            assert TeamStatePublicationProof.query.filter_by(
                snapshot_id=candidate.id,
            ).count() == 0
            assert ShareArtifact.query.filter_by(
                source_snapshot_id=candidate.id,
            ).count() == 0
            assert TonightPublication.query.filter_by(
                dashboard_snapshot_id=candidate.id,
            ).count() == 0

            completed = db.session.get(SyncRun, run_id)
            assert completed.status == sync_metadata.STATUS_FAILED
            assert completed.stage == sync_metadata.STAGE_FAILED
            assert completed.failed_stage == sync_metadata.STAGE_DASHBOARD_SNAPSHOT
            assert completed.error_message == reason
            assert completed.published_dashboard_snapshot_id is None
            assert db.session.get(SyncRun, prior_run_id).published_dashboard_snapshot_id == (
                trusted_id
            )
        finally:
            db.session.remove()
            drop_test_schema(app)
