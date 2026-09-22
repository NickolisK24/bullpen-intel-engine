"""A bounded, isolated rehearsal of the installed trusted publication builder."""

from datetime import timedelta
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


def test_trusted_publication_rehearsal(monkeypatch):
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
            query_counts = {'appearance': 0, 'processed_game': 0, 'pbp_event': 0, 'rotation_source': 0, 'transactions': 0}
            def count_publication_reads(_conn, _cursor, statement, _params, _context, _many):
                sql = statement.lower()
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
                    game_context=None, performance=board['frozen_performance'], what_changed=None,
                    section_errors={},
                )
            finally:
                event.remove(db.engine, 'before_cursor_execute', no_mutable_workload_read)
            assert core['publication_identity'] == details['publication_identity']
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
            )
        finally:
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
