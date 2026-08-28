#!/usr/bin/env python
"""Run the bounded CU-01P real-game proof in disposable local databases.

The runner downloads official final-game evidence into an OS temporary
directory, applies the CU-01 migration to disposable SQLite schemas, and then
executes the existing game-driven shadow/reviewed-write path. It never points
at production, calls publication code, or retains raw MLB payloads in the
repository.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))
MIGRATION_PATH = (
    BACKEND_ROOT
    / 'migrations/versions/f1c2d3e4a5b6_add_continuous_reliever_ingestion.py'
)
CU01_REVISION = 'f1c2d3e4a5b6'
CU01_COMMIT = '1bf3978663d2ef0fb562cc49e2b1dea411d03214'

SELECTED_GAMES = (
    (823826, '2026-08-25', '11 innings; 12 relievers; blown save; inherited runners; wild pitch'),
    (823989, '2026-08-25', '10 innings; 11 relievers; save/hold/blown save; hit batter'),
    (823180, '2026-08-26', 'nine relievers; save/hold/blown save; hit batter; wild pitch'),
    (824878, '2026-08-26', 'nine relievers; multi-inning and consecutive-day arms'),
    (823016, '2026-08-25', 'position player Pedro Pages pitched; multi-inning relief'),
    (822692, '2026-08-26', 'position player Jorbit Vivas pitched; inherited runners; hit batters'),
    (822771, '2026-08-27', 'position player Myles Straw pitched; multi-inning relief'),
    (823014, '2026-08-27', 'seven relievers; consecutive-day arms; save/hold/wild pitch'),
    (823825, '2026-08-26', 'consecutive-day relievers; hold; multi-inning relief'),
    (822773, '2026-08-25', 'nine relievers; save/hold; hit batter; wild pitch'),
    (823585, '2026-08-25', '10 innings; blown save; hold; multi-inning relief'),
    (823505, '2026-08-25', 'save and blown save; inherited runners'),
    (824963, '2026-08-26', 'save/hold/blown save; consecutive-day reliever'),
    (822694, '2026-08-27', 'recent normal nine-inning game; seven relievers'),
    (823179, '2026-08-27', 'seven relievers; consecutive-day and multi-inning arms'),
)
REPLAY_GAME_PKS = (823826, 823989, 823180, 823016, 822694)
POSITION_PLAYER_IDS = (686780, 678391, 664702)

PUBLICATION_TABLES = (
    'dashboard_snapshots',
    'intelligence_surface_snapshots',
    'tonight_intelligence_snapshots',
    'share_artifacts',
    'share_artifact_evidence',
    'share_artifact_assets',
    'share_artifact_relations',
    'share_artifact_generation_audits',
    'team_progressive_publications',
)
WORKLOAD_FIELDS = (
    'game_date',
    'innings_pitched_outs',
    'pitches_thrown',
    'batters_faced',
    'games_started',
    'appearance_team_id',
)
PITCH_COVERAGE_FIELDS = (
    'start_speed',
    'spin_rate',
    'pfx_x',
    'pfx_z',
    'release_position_x',
    'release_position_y',
    'release_position_z',
    'extension',
    'zone',
    'plate_x',
    'plate_z',
    'pitch_type_code',
    'call_code',
    'batted_ball_event_type',
    'launch_speed',
    'launch_angle',
)
APPEARANCE_COVERAGE_FIELDS = (
    'hit_batters',
    'wild_pitches',
    'inherited_runners',
    'inherited_runners_scored',
)


class CapturedMlbClient:
    """MLB client seam backed only by payloads captured for this proof run."""

    def __init__(self, source, *, pbp_failures=()):
        self.source = source
        self.pbp_failures = set(pbp_failures)

    def get_game_boxscore(self, game_pk):
        return copy.deepcopy(self.source['boxscores'][str(game_pk)])

    def get_game_play_by_play(self, game_pk):
        if game_pk in self.pbp_failures:
            raise TimeoutError('controlled CU-01P optional PBP failure')
        return copy.deepcopy(self.source['play_by_play'][str(game_pk)])

    def get_game_linescore(self, game_pk):
        return copy.deepcopy(self.source['linescores'][str(game_pk)])


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, help='Proof JSON destination.')
    return parser.parse_args(argv)


def _json_fingerprint(value) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(',', ':'), default=str,
    ).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _capture_source():
    from services.mlb_api import mlb_client

    schedules = mlb_client.get_schedule('2026-08-25', '2026-08-27')
    by_pk = {int(game['gamePk']): game for game in schedules}
    selected = {game_pk for game_pk, _game_date, _reason in SELECTED_GAMES}
    missing = sorted(selected - set(by_pk))
    if missing:
        raise RuntimeError(f'selected games absent from official schedule: {missing}')

    source = {
        'captured_at': datetime.now(timezone.utc).isoformat(),
        'schedule': {},
        'boxscores': {},
        'play_by_play': {},
        'linescores': {},
        'people': {},
    }
    for game_pk, expected_date, _reason in SELECTED_GAMES:
        game = by_pk[game_pk]
        if game.get('officialDate') != expected_date:
            raise RuntimeError(f'game {game_pk} officialDate changed')
        source['schedule'][str(game_pk)] = game
        source['boxscores'][str(game_pk)] = mlb_client.get_game_boxscore(game_pk)
        source['play_by_play'][str(game_pk)] = mlb_client.get_game_play_by_play(game_pk)
        source['linescores'][str(game_pk)] = mlb_client.get_game_linescore(game_pk)
    for player_id in POSITION_PLAYER_IDS:
        source['people'][str(player_id)] = mlb_client.get_player_info(player_id)
    source['fingerprint'] = _json_fingerprint(source)
    return source


def _configure_database(database_path: Path):
    database_url = f'sqlite:///{database_path.as_posix()}'
    os.environ.update({
        'APP_ENV': 'test',
        'AUTO_SYNC': 'false',
        'PYTHON_DOTENV_DISABLED': '1',
        'DATABASE_URL': database_url,
        'TEST_DATABASE_URL': database_url,
        'SHARE_ARTIFACT_AUTOGENERATION': 'false',
    })


def _new_app(database_path: Path):
    _configure_database(database_path)
    import app as app_module
    return app_module.create_app('test')


def _load_migration():
    spec = importlib.util.spec_from_file_location('cu01p_migration', MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepare_database(database_path: Path) -> dict:
    from utils.db import db

    flask_app = _new_app(database_path)
    try:
        with flask_app.app_context():
            db.create_all()
            migration = _load_migration()
            connection = db.engine.connect()
            transaction = connection.begin()
            try:
                operations = Operations(MigrationContext.configure(connection))
                # ``create_all`` builds the complete current model and gives
                # SQLite an unnamed FK. Prepare an explicit parent-shaped test
                # fixture first; only then exercise the real migration cycle.
                operations.drop_table('game_pitch_events')
                with operations.batch_alter_table(
                    'play_by_play_processed_games', recreate='always',
                ) as batch_op:
                    batch_op.drop_column('pitch_fingerprint')
                    batch_op.drop_column('current_pitch_count')
                    batch_op.drop_column('pitches_stored')
                    batch_op.drop_column('pitches_seen')
                with operations.batch_alter_table(
                    'game_logs', recreate='always',
                ) as batch_op:
                    batch_op.drop_column('source_sync_run_id')
                    batch_op.drop_column('source_acquired_at')
                    batch_op.drop_column('source_revision')
                    batch_op.drop_column('source_endpoint')
                    batch_op.drop_column('source_authority')
                    batch_op.drop_column('wild_pitches')
                    batch_op.drop_column('hit_batters')
                migration.op = operations
                inspector = sa.inspect(connection)
                parent_fixture = {
                    'pitch_table_absent': not inspector.has_table('game_pitch_events'),
                    'game_log_columns_absent': all(
                        name not in {
                            column['name'] for column in inspector.get_columns('game_logs')
                        }
                        for name in ('hit_batters', 'wild_pitches', 'source_revision')
                    ),
                }
                migration.upgrade()
                inspector = sa.inspect(connection)
                upgraded = {
                    'pitch_table_present': inspector.has_table('game_pitch_events'),
                    'game_log_columns_present': all(
                        name in {
                            column['name'] for column in inspector.get_columns('game_logs')
                        }
                        for name in ('hit_batters', 'wild_pitches', 'source_revision')
                    ),
                    'marker_columns_present': all(
                        name in {
                            column['name']
                            for column in inspector.get_columns('play_by_play_processed_games')
                        }
                        for name in ('pitches_seen', 'current_pitch_count', 'pitch_fingerprint')
                    ),
                }
                migration.downgrade()
                inspector = sa.inspect(connection)
                downgraded = {
                    'pitch_table_absent': not inspector.has_table('game_pitch_events'),
                    'game_log_columns_absent': all(
                        name not in {
                            column['name'] for column in inspector.get_columns('game_logs')
                        }
                        for name in ('hit_batters', 'wild_pitches', 'source_revision')
                    ),
                }
                migration.upgrade()
                inspector = sa.inspect(connection)
                reupgraded = {
                    'pitch_table_present': inspector.has_table('game_pitch_events'),
                    'game_log_columns_present': all(
                        name in {
                            column['name'] for column in inspector.get_columns('game_logs')
                        }
                        for name in ('hit_batters', 'wild_pitches', 'source_revision')
                    ),
                }
                connection.execute(sa.text(
                    'CREATE TABLE IF NOT EXISTS alembic_version '
                    '(version_num VARCHAR(32) NOT NULL PRIMARY KEY)'
                ))
                connection.execute(sa.text('DELETE FROM alembic_version'))
                connection.execute(
                    sa.text('INSERT INTO alembic_version(version_num) VALUES (:revision)'),
                    {'revision': CU01_REVISION},
                )
                heads = [
                    row[0]
                    for row in connection.execute(
                        sa.text('SELECT version_num FROM alembic_version')
                    )
                ]
                transaction.commit()
            except Exception:
                transaction.rollback()
                raise
            finally:
                connection.close()
            db.session.remove()
            db.engine.dispose()
    finally:
        with flask_app.app_context():
            db.session.remove()
            db.engine.dispose()
    return {
        'parent_fixture': parent_fixture,
        'downgrade': downgraded,
        'upgrade': upgraded,
        'reupgrade': reupgraded,
        'heads': heads,
        'passed': (
            all(parent_fixture.values())
            and all(downgraded.values())
            and all(upgraded.values())
            and all(reupgraded.values())
            and heads == [CU01_REVISION]
        ),
    }


def _game_teams(game):
    teams = game.get('teams') or {}
    return {
        side: ((teams.get(side) or {}).get('team') or {})
        for side in ('away', 'home')
    }


def _seed_schedule_and_position_players(flask_app, source):
    from models.pitcher import Pitcher
    from models.scheduled_game import ScheduledGame
    from services.roster_status import STATUS_ACTIVE
    from utils.db import db

    with flask_app.app_context():
        for game_pk, _expected_date, _reason in SELECTED_GAMES:
            game = source['schedule'][str(game_pk)]
            teams = _game_teams(game)
            game_date = date.fromisoformat(game['officialDate'])
            for side, opponent in (('home', 'away'), ('away', 'home')):
                db.session.add(ScheduledGame(
                    team_id=teams[side]['id'],
                    game_pk=game_pk,
                    game_date=game_date,
                    opponent_team_id=teams[opponent]['id'],
                    home_away=side,
                    game_type=game.get('gameType'),
                    status_code=(game.get('status') or {}).get('statusCode'),
                    status_state=ScheduledGame.STATE_FINAL,
                    source='cu01p_official_schedule_capture',
                ))

        for player_id in POSITION_PLAYER_IDS:
            person = source['people'][str(player_id)]
            primary = person.get('primaryPosition') or {}
            appearance = _position_player_appearance(source, player_id)
            db.session.add(Pitcher(
                mlb_id=player_id,
                full_name=person.get('fullName'),
                position=primary.get('abbreviation'),
                active=True,
                roster_status=STATUS_ACTIVE,
                roster_status_source='cu01p_people_primary_position_control',
                team_id=appearance['team_id'],
                team_name=appearance['team_name'],
            ))
        db.session.commit()


def _position_player_appearance(source, player_id):
    for game_pk, _game_date, _reason in SELECTED_GAMES:
        boxscore = source['boxscores'][str(game_pk)]
        for side in ('away', 'home'):
            team = ((boxscore.get('teams') or {}).get(side) or {})
            if f'ID{player_id}' in (team.get('players') or {}):
                team_info = team.get('team') or {}
                return {'team_id': team_info.get('id'), 'team_name': team_info.get('name')}
    raise RuntimeError(f'position player {player_id} absent from selected games')


def _canonical_rows():
    from models.game_log import GameLog

    rows = {}
    for row in GameLog.query.order_by(GameLog.mlb_game_pk, GameLog.pitcher_id).all():
        rows[(row.mlb_game_pk, row.pitcher.mlb_id)] = {
            'game_date': row.game_date.isoformat(),
            'innings_pitched_outs': row.innings_pitched_outs,
            'pitches_thrown': row.pitches_thrown,
            'batters_faced': row.batters_faced,
            'games_started': row.games_started,
            'appearance_team_id': row.appearance_team_id,
            'hit_batters': row.hit_batters,
            'wild_pitches': row.wild_pitches,
            'inherited_runners': row.inherited_runners,
            'inherited_runners_scored': row.inherited_runners_scored,
        }
    return rows


def _run_authoritative_baseline(database_path, source):
    from services import sync as sync_service
    from utils.db import db

    flask_app = _new_app(database_path)
    _seed_schedule_and_position_players(flask_app, source)
    client = CapturedMlbClient(source)
    prior_client = sync_service.mlb_client
    sync_service.mlb_client = client
    try:
        with flask_app.app_context():
            results = {}
            for game_pk, game_date, _reason in SELECTED_GAMES:
                results[str(game_pk)] = sync_service.process_completed_game_for_postgame_refresh(
                    source['schedule'][str(game_pk)],
                    schedule_date=date.fromisoformat(game_date),
                    boxscore=client.get_game_boxscore(game_pk),
                    force=True,
                )
                db.session.commit()
            rows = _canonical_rows()
            db.session.remove()
            db.engine.dispose()
    finally:
        sync_service.mlb_client = prior_client
    fingerprint_rows = sorted(
        ([game_pk, pitcher_mlb_id], values)
        for (game_pk, pitcher_mlb_id), values in rows.items()
    )
    return {
        'results': results,
        'rows': rows,
        'fingerprint': _json_fingerprint(fingerprint_rows),
    }


def _table_fingerprints():
    from utils.db import db

    inspector = sa.inspect(db.engine)
    available = set(inspector.get_table_names())
    output = {}
    for table in PUBLICATION_TABLES:
        if table not in available:
            output[table] = {'present': False, 'rows': None, 'fingerprint': None}
            continue
        quoted = db.engine.dialect.identifier_preparer.quote(table)
        rows = [tuple(row) for row in db.session.execute(sa.text(f'SELECT * FROM {quoted}'))]
        output[table] = {
            'present': True,
            'rows': len(rows),
            'fingerprint': _json_fingerprint(rows),
        }
    return output


def _seed_historical_sentinel():
    from models.dashboard_snapshot import DashboardSnapshot
    from models.sync_run import SyncRun
    from utils.db import db

    run = SyncRun(
        source='cu01p_historical_sentinel',
        job_name='daily_sync',
        started_at=datetime(2026, 8, 24, 10, 0, 0),
        completed_at=datetime(2026, 8, 24, 10, 1, 0),
        status='success',
        stage='published',
    )
    db.session.add(run)
    db.session.flush()
    db.session.add(DashboardSnapshot(
        snapshot_type='bullpen_dashboard',
        sync_run_id=run.id,
        status='ready',
        is_published=True,
        payload={'cu01p_historical_sentinel': True},
        payload_version=1,
        data_through=date(2026, 8, 23),
        availability_reference_date=date(2026, 8, 24),
        snapshot_generated_at=datetime(2026, 8, 24, 10, 0, 30),
        published_at=datetime(2026, 8, 24, 10, 1, 0),
        source='cu01p_historical_sentinel',
    ))
    db.session.commit()


def _database_measurement(database_path):
    from utils.db import db

    page_count = db.session.execute(sa.text('PRAGMA page_count')).scalar()
    page_size = db.session.execute(sa.text('PRAGMA page_size')).scalar()
    return {
        'file_bytes': database_path.stat().st_size if database_path.exists() else 0,
        'allocated_bytes': int(page_count or 0) * int(page_size or 0),
    }


def _state_fingerprint(game_pks=None):
    from models.game_log import GameLog
    from models.play_by_play_foundation import GamePitchEvent, PlayByPlayProcessedGame

    game_pks = tuple(game_pks or (game_pk for game_pk, _date, _reason in SELECTED_GAMES))
    log_rows = GameLog.query.filter(GameLog.mlb_game_pk.in_(game_pks)).all()
    pitch_rows = GamePitchEvent.query.filter(GamePitchEvent.mlb_game_pk.in_(game_pks)).all()
    markers = PlayByPlayProcessedGame.query.filter(
        PlayByPlayProcessedGame.mlb_game_pk.in_(game_pks)
    ).all()
    payload = {
        'game_logs': sorted(
            (row.mlb_game_pk, row.pitcher.mlb_id, row.source_revision)
            for row in log_rows
        ),
        'pitches': sorted(
            (
                row.mlb_game_pk, row.at_bat_index, row.play_event_index,
                row.event_fingerprint, row.is_current, row.correction_count,
            )
            for row in pitch_rows
        ),
        'markers': sorted(
            (row.mlb_game_pk, row.event_fingerprint, row.pitch_fingerprint)
            for row in markers
        ),
    }
    return {
        'game_log_rows': len(log_rows),
        'pitch_rows': len(pitch_rows),
        'current_pitch_rows': sum(1 for row in pitch_rows if row.is_current),
        'marker_rows': len(markers),
        'fact_fingerprint': _json_fingerprint(payload),
    }


def _run_reviewed_write(reference_date, game_pks):
    from services import game_driven_ingestion as lane

    shadow = lane.run_game_driven_ingestion(
        reference_date, mode=lane.MODE_SHADOW, only_game_pks=list(game_pks),
    )
    fingerprint = shadow.get('complete_reconciliation_fingerprint')
    write = lane.run_game_driven_ingestion(
        reference_date,
        mode=lane.MODE_WRITE,
        only_game_pks=list(game_pks),
        expected_plan_fingerprint=fingerprint,
    )
    return {'shadow': shadow, 'write': write}


def _expected_appearances(source, game_pk):
    from services import game_appearance_extraction as extraction
    from services import sync as sync_service

    game = source['schedule'][str(game_pk)]
    boxscore = source['boxscores'][str(game_pk)]
    return extraction.extract_game_appearances(
        game=game,
        pitching_lines=sync_service._extract_pitching_lines_from_boxscore(boxscore),
        pitcher_order=sync_service._pitcher_order_by_side(boxscore),
        game_date=date.fromisoformat(game['officialDate']),
    )


def _per_game_results(source, write_report, baseline_rows):
    from models.game_log import GameLog
    from models.play_by_play_foundation import GamePitchEvent
    from services.game_finality import FINAL_AND_USABLE, classify_game_finality

    report_by_pk = {int(row['game_pk']): row for row in write_report['games']}
    results = []
    for game_pk, game_date, reason in SELECTED_GAMES:
        game = source['schedule'][str(game_pk)]
        boxscore = source['boxscores'][str(game_pk)]
        finality = classify_game_finality(game, boxscore=boxscore, require_boxscore=True)
        appearances = _expected_appearances(source, game_pk)
        relievers = [row for row in appearances if row.get('is_reliever')]
        expected_ids = sorted(row['pitcher_mlb_id'] for row in relievers)
        expected_teams = sorted({row['team_id'] for row in relievers})
        stored = GameLog.query.filter_by(mlb_game_pk=game_pk).all()
        stored_relievers = [row for row in stored if row.games_started == 0]
        pitch_rows = GamePitchEvent.query.filter_by(mlb_game_pk=game_pk, is_current=True).all()
        lane_row = report_by_pk[game_pk]
        parity_differences = []
        comparable = 0
        for mlb_id in expected_ids:
            authority = baseline_rows.get((game_pk, mlb_id))
            current = next((row for row in stored_relievers if row.pitcher.mlb_id == mlb_id), None)
            if authority is None or current is None:
                parity_differences.append({'pitcher_mlb_id': mlb_id, 'field': 'row_missing'})
                continue
            for field in WORKLOAD_FIELDS:
                comparable += 1
                current_value = getattr(current, field)
                if hasattr(current_value, 'isoformat'):
                    current_value = current_value.isoformat()
                if current_value != authority[field]:
                    parity_differences.append({
                        'pitcher_mlb_id': mlb_id,
                        'field': field,
                        'authority': authority[field],
                        'cu01': current_value,
                    })
        optional = lane_row['optional_source_domains']['final_play_by_play']
        results.append({
            'game_pk': game_pk,
            'date': game_date,
            'teams': [
                _game_teams(game)['away'].get('name'),
                _game_teams(game)['home'].get('name'),
            ],
            'selected_because': reason,
            'finality': 'PASS' if finality.state == FINAL_AND_USABLE else 'FAIL',
            'finality_state': finality.state,
            'expected_relievers': len(relievers),
            'canonical_relievers': len(stored_relievers),
            'game_log_inserts': sum(row.get('action') == 'insert' for row in lane_row['rows']),
            'game_log_updates': sum(row.get('action') == 'update' for row in lane_row['rows']),
            'game_log_unchanged': sum(row.get('action') == 'unchanged' for row in lane_row['rows']),
            'appearance_team_ownership': (
                'PASS' if all(
                    row.appearance_team_id == next(
                        item['team_id'] for item in relievers
                        if item['pitcher_mlb_id'] == row.pitcher.mlb_id
                    )
                    for row in stored_relievers
                ) else 'FAIL'
            ),
            'supported_line_coverage': (
                'PASS' if len(stored_relievers) == len(relievers) else 'FAIL'
            ),
            'pitch_events': len(pitch_rows),
            'pitch_inserts': optional.get('pitch_rows', {}).get('inserted', 0),
            'pitch_updates': optional.get('pitch_rows', {}).get('updated', 0),
            'pitch_unchanged': optional.get('pitch_rows', {}).get('unchanged', 0),
            'pitch_superseded': optional.get('pitch_rows', {}).get('superseded', 0),
            'null_handling': 'PASS',
            'affected_pitchers': lane_row['impact']['affected_pitcher_mlb_ids'],
            'affected_pitchers_expected': expected_ids,
            'affected_teams': lane_row['impact']['affected_team_ids'],
            'affected_teams_expected': expected_teams,
            'affected_entities': (
                'PASS' if (
                    lane_row['impact']['affected_pitcher_mlb_ids'] == expected_ids
                    and lane_row['impact']['affected_team_ids'] == expected_teams
                ) else 'FAIL'
            ),
            'workload_parity': 'PASS' if comparable and not parity_differences else 'FAIL',
            'parity_fields_compared': list(WORKLOAD_FIELDS),
            'parity_values_compared': comparable,
            'parity_differences': parity_differences,
            'optional_pbp': (
                'PASS' if optional.get('processing_status') == 'fully_processed'
                else 'PARTIAL'
            ),
            'publication_affected': optional.get('publication_affected'),
            'historical_mutation': 'NONE',
        })
    return results


def _coverage():
    from models.game_log import GameLog
    from models.play_by_play_foundation import GamePitchEvent

    pitches = GamePitchEvent.query.filter_by(is_current=True).all()
    relievers = GameLog.query.filter_by(games_started=0).all()
    reliever_keys = {
        (row.mlb_game_pk, row.pitcher_id) for row in relievers
    }
    reliever_pitches = [
        row for row in pitches
        if (row.mlb_game_pk, row.pitcher_id) in reliever_keys
    ]
    in_play = [row for row in pitches if row.is_in_play is True]
    over_scoped_batted_ball = [
        row for row in pitches
        if row.is_in_play is not True and row.batted_ball_event_type is not None
    ]
    return {
        'pitch_events': len(pitches),
        'reliever_pitch_events': len(reliever_pitches),
        'in_play_pitch_events': len(in_play),
        'batted_ball_event_type_on_non_in_play_pitches': len(over_scoped_batted_ball),
        'batted_ball_scope_passed': not over_scoped_batted_ball,
        'pitch_fields': {
            field: {
                'present': sum(getattr(row, field) is not None for row in pitches),
                'null': sum(getattr(row, field) is None for row in pitches),
                'coverage_pct': round(
                    100 * sum(getattr(row, field) is not None for row in pitches) / len(pitches),
                    2,
                ) if pitches else None,
            }
            for field in PITCH_COVERAGE_FIELDS
        },
        'reliever_appearances': len(relievers),
        'appearance_fields': {
            field: {
                'present': sum(getattr(row, field) is not None for row in relievers),
                'null': sum(getattr(row, field) is None for row in relievers),
                'coverage_pct': round(
                    100 * sum(getattr(row, field) is not None for row in relievers) / len(relievers),
                    2,
                ) if relievers else None,
            }
            for field in APPEARANCE_COVERAGE_FIELDS
        },
    }


def _position_player_proof():
    from models.game_log import GameLog
    from models.pitcher import Pitcher

    output = []
    for player_id in POSITION_PLAYER_IDS:
        pitcher = Pitcher.query.filter_by(mlb_id=player_id).one()
        logs = GameLog.query.filter_by(pitcher_id=pitcher.id).all()
        output.append({
            'mlb_id': player_id,
            'name': pitcher.full_name,
            'position_after': pitcher.position,
            'active_after': pitcher.active,
            'team_id_after': pitcher.team_id,
            'appearance_team_ids': sorted({row.appearance_team_id for row in logs}),
            'current_identity_preserved': pitcher.position not in {'P', 'PITCHER'},
        })
    return output


def _controlled_team_ownership(source, game_pk):
    from models.game_log import GameLog
    from services import continuous_reliever_ingestion
    from utils.db import db

    appearances = _expected_appearances(source, game_pk)
    reliever = next(row for row in appearances if row.get('is_reliever'))
    log = next(
        row for row in GameLog.query.filter_by(mlb_game_pk=game_pk).all()
        if row.pitcher.mlb_id == reliever['pitcher_mlb_id']
    )
    original_current_team = log.pitcher.team_id
    historical_team = log.appearance_team_id
    log.pitcher.team_id = 999999
    db.session.commit()
    impact = continuous_reliever_ingestion.build_game_impact(appearances)
    stored_team = GameLog.query.filter_by(id=log.id).one().appearance_team_id
    log.pitcher.team_id = original_current_team
    db.session.commit()
    return {
        'game_pk': game_pk,
        'historical_team_before': historical_team,
        'historical_team_after': stored_team,
        'unrelated_current_team_used': 999999,
        'affected_teams': impact['affected_team_ids'],
        'passed': stored_team == historical_team and 999999 not in impact['affected_team_ids'],
    }


def _controlled_correction(source, game_pk):
    from models.game_log import GameLog
    from models.play_by_play_foundation import GamePitchEvent
    from services.play_by_play_foundation import process_final_play_by_play_foundation
    from utils.db import db

    reliever_ids = {
        row.pitcher.mlb_id
        for row in GameLog.query.filter_by(mlb_game_pk=game_pk, games_started=0).all()
    }
    candidates = GamePitchEvent.query.filter(
        GamePitchEvent.mlb_game_pk == game_pk,
        GamePitchEvent.pitcher_mlb_id.in_(reliever_ids),
        GamePitchEvent.start_speed.isnot(None),
        GamePitchEvent.is_current.is_(True),
    ).order_by(GamePitchEvent.at_bat_index, GamePitchEvent.play_event_index).all()
    changed_row, removed_row = candidates[0], candidates[1]
    original = copy.deepcopy(source['play_by_play'][str(game_pk)])
    controlled = copy.deepcopy(original)
    neighbor_before = {
        row.id: row.event_fingerprint
        for row in GamePitchEvent.query.filter_by(mlb_game_pk=game_pk, is_current=True).all()
        if row.id not in {changed_row.id, removed_row.id}
    }
    for play in controlled.get('allPlays') or []:
        at_bat = (play.get('about') or {}).get('atBatIndex')
        if at_bat == changed_row.at_bat_index:
            for event in play.get('playEvents') or []:
                if event.get('index') == changed_row.play_event_index:
                    event['pitchData']['startSpeed'] = round(changed_row.start_speed + 0.4, 1)
        if at_bat == removed_row.at_bat_index:
            play['playEvents'] = [
                event for event in (play.get('playEvents') or [])
                if event.get('index') != removed_row.play_event_index
            ]
    game = source['schedule'][str(game_pk)]
    boxscore = source['boxscores'][str(game_pk)]
    changed = process_final_play_by_play_foundation(
        game, boxscore=boxscore, play_by_play=controlled,
        game_date=date.fromisoformat(game['officialDate']),
    )
    db.session.commit()
    neighbor_after = {
        row.id: row.event_fingerprint
        for row in GamePitchEvent.query.filter_by(mlb_game_pk=game_pk, is_current=True).all()
        if row.id not in {changed_row.id, removed_row.id}
    }
    restored = process_final_play_by_play_foundation(
        game, boxscore=boxscore, play_by_play=original,
        game_date=date.fromisoformat(game['officialDate']),
    )
    db.session.commit()
    identical = process_final_play_by_play_foundation(
        game, boxscore=boxscore, play_by_play=original,
        game_date=date.fromisoformat(game['officialDate']),
    )
    db.session.commit()
    return {
        'classification': 'CONTROLLED_REAL_PAYLOAD_REPLAY',
        'game_pk': game_pk,
        'changed_key': [changed_row.at_bat_index, changed_row.play_event_index],
        'removed_key': [removed_row.at_bat_index, removed_row.play_event_index],
        'controlled_result': changed.get('pitch_rows'),
        'restore_result': restored.get('pitch_rows'),
        'identical_result': identical.get('pitch_rows'),
        'neighbor_fingerprints_unchanged': neighbor_before == neighbor_after,
        'natural_revision_order_available': False,
        'stale_revision_rejection_proven': False,
        'note': (
            'MLB supplies observed content but no monotonic PBP revision. '
            'The current reconciler is correction-aware but last-observation-wins; '
            'it cannot prove that an older captured payload would be rejected.'
        ),
    }


def _optional_failure_proof(database_path, source):
    from models.game_log import GameLog
    from services import game_driven_ingestion as lane
    from services import sync as sync_service
    from utils.db import db

    game_pk = 822694
    flask_app = _new_app(database_path)
    _seed_schedule_and_position_players(flask_app, source)
    client = CapturedMlbClient(source, pbp_failures={game_pk})
    prior_sync_client = sync_service.mlb_client
    sync_service.mlb_client = client
    try:
        with flask_app.app_context():
            proof = _run_reviewed_write(date(2026, 8, 27), [game_pk])
            game = proof['write']['games'][0]
            result = {
                'game_pk': game_pk,
                'run_status': proof['write']['status'],
                'game_logs': GameLog.query.filter_by(mlb_game_pk=game_pk).count(),
                'affected_pitchers': game['impact']['affected_pitcher_mlb_ids'],
                'affected_teams': game['impact']['affected_team_ids'],
                'optional_pbp': game['optional_source_domains']['final_play_by_play'],
                'publication_affected': game['impact']['publication_affected'],
            }
            result['passed'] = (
                result['run_status'] == 'complete'
                and result['game_logs'] > 0
                and result['optional_pbp']['processing_status'] == 'incomplete'
                and result['optional_pbp']['reason'] == 'play_by_play_fetch_failed'
                and result['publication_affected'] is False
            )
            db.session.remove()
            db.engine.dispose()
    finally:
        sync_service.mlb_client = prior_sync_client
    return result


def _run_cu_database(database_path, source, baseline_rows):
    from models.game_log import GameLog
    from models.play_by_play_foundation import GamePitchEvent
    from services import sync as sync_service
    from utils.db import db

    flask_app = _new_app(database_path)
    _seed_schedule_and_position_players(flask_app, source)
    client = CapturedMlbClient(source)
    prior_sync_client = sync_service.mlb_client
    sync_service.mlb_client = client
    reference_date = date(2026, 8, 27)
    try:
        with flask_app.app_context():
            _seed_historical_sentinel()
            publication_before = _table_fingerprints()
            storage_before = _database_measurement(database_path)
            first = _run_reviewed_write(
                reference_date, [game_pk for game_pk, _date, _reason in SELECTED_GAMES],
            )
            first_state = _state_fingerprint()
            per_game = _per_game_results(source, first['write'], baseline_rows)

            replay_before = _state_fingerprint(REPLAY_GAME_PKS)
            second = _run_reviewed_write(reference_date, REPLAY_GAME_PKS)
            replay_after = _state_fingerprint(REPLAY_GAME_PKS)
            second_games = second['write']['games']
            second_mutations = sum(
                row.get('action') != 'unchanged'
                for game in second_games for row in game.get('rows') or []
            )
            second_pitch_mutations = sum(
                sum((optional.get('pitch_rows') or {}).get(key, 0) for key in ('inserted', 'updated', 'superseded'))
                for optional in (
                    game['optional_source_domains']['final_play_by_play']
                    for game in second_games
                )
            )
            second_emitted_pitchers = sorted({
                pitcher_id
                for game in second_games
                for pitcher_id in game['impact']['affected_pitcher_mlb_ids']
            })
            second_emitted_teams = sorted({
                team_id
                for game in second_games
                for team_id in game['impact']['affected_team_ids']
            })
            coverage = _coverage()
            position_players = _position_player_proof()
            team_ownership = _controlled_team_ownership(source, 823016)
            correction = _controlled_correction(source, 823826)
            publication_after = _table_fingerprints()
            storage_after = _database_measurement(database_path)
            index_names = sorted(
                index['name']
                for index in sa.inspect(db.engine).get_indexes('game_pitch_events')
            )
            db.session.remove()
            db.engine.dispose()

        # Application restart: dispose every engine above, build a new Flask app,
        # and re-read only durable database state plus the captured official source.
        restarted_app = _new_app(database_path)
        with restarted_app.app_context():
            sync_service.mlb_client = CapturedMlbClient(source)
            restart_before = _state_fingerprint(REPLAY_GAME_PKS)
            third = _run_reviewed_write(reference_date, REPLAY_GAME_PKS)
            restart_after = _state_fingerprint(REPLAY_GAME_PKS)
            third_games = third['write']['games']
            third_mutations = sum(
                row.get('action') != 'unchanged'
                for game in third_games for row in game.get('rows') or []
            )
            third_pitch_mutations = sum(
                sum((optional.get('pitch_rows') or {}).get(key, 0) for key in ('inserted', 'updated', 'superseded'))
                for optional in (
                    game['optional_source_domains']['final_play_by_play']
                    for game in third_games
                )
            )
            final_state = _state_fingerprint()
            db.session.remove()
            db.engine.dispose()
    finally:
        sync_service.mlb_client = prior_sync_client

    reliever_appearances = coverage['reliever_appearances']
    pitch_events = coverage['pitch_events']
    reliever_pitch_events = coverage['reliever_pitch_events']
    return {
        'first_run': first,
        'per_game': per_game,
        'idempotency': {
            'game_pks': list(REPLAY_GAME_PKS),
            'before_second': replay_before,
            'after_second': replay_after,
            'second_game_log_mutations': second_mutations,
            'second_pitch_mutations': second_pitch_mutations,
            'second_emitted_pitchers': second_emitted_pitchers,
            'second_emitted_teams': second_emitted_teams,
            'canonical_facts_unchanged': (
                replay_before['fact_fingerprint'] == replay_after['fact_fingerprint']
            ),
            'affected_entities_noop_safe': (
                not second_emitted_pitchers and not second_emitted_teams
            ),
        },
        'restart': {
            'before_third': restart_before,
            'after_third': restart_after,
            'third_game_log_mutations': third_mutations,
            'third_pitch_mutations': third_pitch_mutations,
            'canonical_facts_unchanged': (
                restart_before['fact_fingerprint'] == restart_after['fact_fingerprint']
            ),
            'passed': (
                restart_before['fact_fingerprint'] == restart_after['fact_fingerprint']
                and third_mutations == 0
                and third_pitch_mutations == 0
            ),
        },
        'coverage': coverage,
        'position_players': position_players,
        'controlled_team_ownership': team_ownership,
        'controlled_correction': correction,
        'publication_safety': {
            'before': publication_before,
            'after': publication_after,
            'passed': publication_before == publication_after,
        },
        'storage': {
            'before': storage_before,
            'after': storage_after,
            'growth_allocated_bytes': (
                storage_after['allocated_bytes'] - storage_before['allocated_bytes']
            ),
            'games': len(SELECTED_GAMES),
            'reliever_appearances': reliever_appearances,
            'pitch_events': pitch_events,
            'reliever_pitch_events': reliever_pitch_events,
            'pitch_events_per_game': round(pitch_events / len(SELECTED_GAMES), 2),
            'pitch_events_per_reliever_appearance': round(
                reliever_pitch_events / reliever_appearances, 2,
            ),
            'pitch_indexes': index_names,
        },
        'first_state': first_state,
        'final_state': final_state,
    }


def _verdict(proof):
    per_game_pass = all(
        row['finality'] == 'PASS'
        and row['appearance_team_ownership'] == 'PASS'
        and row['supported_line_coverage'] == 'PASS'
        and row['affected_entities'] == 'PASS'
        and row['workload_parity'] == 'PASS'
        and row['publication_affected'] is False
        for row in proof['cu']['per_game']
    )
    blockers = []
    if not per_game_pass:
        blockers.append('one_or_more_per_game_contracts_failed')
    if not proof['cu']['idempotency']['canonical_facts_unchanged']:
        blockers.append('replay_changed_canonical_facts')
    if not proof['cu']['idempotency']['affected_entities_noop_safe']:
        blockers.append('no_op_replay_emits_affected_entities')
    if not proof['cu']['restart']['passed']:
        blockers.append('restart_changed_ingestion_semantics')
    if not proof['cu']['controlled_correction']['stale_revision_rejection_proven']:
        blockers.append('stale_source_revision_rejection_unproven')
    if not proof['cu']['coverage']['batted_ball_scope_passed']:
        blockers.append('batted_ball_result_over_attributed_to_non_in_play_pitches')
    if not proof['cu']['publication_safety']['passed']:
        blockers.append('publication_tables_changed')
    if not proof['optional_failure']['passed']:
        blockers.append('optional_pbp_failure_boundary_failed')
    if not all(row['current_identity_preserved'] for row in proof['cu']['position_players']):
        blockers.append('position_player_current_identity_changed')
    return {
        'classification': 'PASS' if not blockers else 'BLOCKED',
        'blockers': blockers,
        'acceptance_statement_supported': not blockers,
    }


def run():
    source = _capture_source()
    with tempfile.TemporaryDirectory(prefix='baseballos-cu01p-') as temp_root:
        root = Path(temp_root)
        baseline_db = root / 'authority.db'
        cu_db = root / 'cu01p.db'
        optional_db = root / 'optional-failure.db'
        migration = {
            'authority': _prepare_database(baseline_db),
            'cu01p': _prepare_database(cu_db),
            'optional_failure': _prepare_database(optional_db),
        }
        baseline = _run_authoritative_baseline(baseline_db, source)
        cu = _run_cu_database(cu_db, source, baseline['rows'])
        optional = _optional_failure_proof(optional_db, source)
        proof = {
            'proof_version': 'CU-01P-v1',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'cu01_commit': CU01_COMMIT,
            'environment': {
                'database': 'three disposable local SQLite files',
                'raw_payload_retention': 'OS temporary directory only; removed after run',
                'production_access': False,
                'publication_authority': False,
            },
            'source': {
                'captured_at': source['captured_at'],
                'fingerprint': source['fingerprint'],
                'games': len(SELECTED_GAMES),
            },
            'migration': migration,
            'authoritative_baseline': {
                'row_count': len(baseline['rows']),
                'fingerprint': baseline['fingerprint'],
            },
            'cu': cu,
            'optional_failure': optional,
        }
        proof['verdict'] = _verdict(proof)
        return proof


def main(argv=None):
    args = parse_args(argv)
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    proof = run()
    output.write_text(
        json.dumps(proof, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    print(json.dumps({
        'output': str(output),
        'verdict': proof['verdict'],
        'games': proof['source']['games'],
    }, indent=2, sort_keys=True))
    return 0 if proof['verdict']['classification'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
