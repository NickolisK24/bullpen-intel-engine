from concurrent.futures import ThreadPoolExecutor
from datetime import date
import importlib.util
from pathlib import Path
from threading import Barrier

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from flask import Flask

from models.final_game_reconciliation import (
    FinalGameMutation,
    FinalGameVersion,
    FinalPitchingAppearanceVersion,
)
from models.game_log import GameLog
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.live_game_delta import ProvisionalPitchingAppearanceState
from models.pitcher import Pitcher
from models.source_observation import SourceObservation
from models.sync_job import SyncJob
from models.sync_run import SyncRun
from services.final_game_reconciliation import (
    FinalSourceBundle,
    acquire_final_game_sources,
    boxscore_source_identity,
    current_final_appearances,
    execute_final_game_job,
    finality_source_identity,
    play_by_play_source_identity,
    reconcile_final_game,
)
from services import game_appearance_extraction as appearance_extraction
from services import sync as sync_service
from services.source_observations import (
    ObservationCompleteness,
    PayloadKind,
    record_source_observation,
)
from services.sync_jobs import JobScopeType, JobType, claim_next_job, enqueue_job
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import (
    AWAY_TEAM,
    HOME_TEAM,
    boxscore,
    final_game,
    pitching_stats,
    schedule_final_game,
)
from utils.db import db
from utils.time import utc_now_naive


GAME_PK = 824900
GAME_DATE = date(2026, 9, 8)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


def _game(game_pk=GAME_PK, *, home_score=4, away_score=2, game_number=1):
    value = final_game(game_pk, game_date=GAME_DATE)
    value['gameNumber'] = game_number
    value['doubleHeader'] = 'Y' if game_number > 1 else 'N'
    value['teams']['home']['score'] = home_score
    value['teams']['away']['score'] = away_score
    return value


def _boxscore(*, home_reliever_pitches=18, include_home_reliever=True):
    lines = [
        (101, 'home', pitching_stats(innings='6.0', games_started=1, pitches=88, strikes=57)),
        (202, 'away', pitching_stats(innings='5.0', games_started=1, pitches=82, strikes=51)),
        (404, 'away', pitching_stats(innings='3.0', pitches=41, strikes=27)),
    ]
    if include_home_reliever:
        lines.append((303, 'home', pitching_stats(innings='3.0', pitches=home_reliever_pitches, strikes=12)))
    value = boxscore(lines)
    value['teams']['home']['teamStats'] = {'pitching': {'inningsPitched': '9.0'}}
    value['teams']['away']['teamStats'] = {'pitching': {'inningsPitched': '8.0'}}
    return value


def _play(index, inning, half, pitcher_id, home_score, away_score, outs=3):
    return {
        'playId': f'play-{index}',
        'about': {
            'atBatIndex': index,
            'inning': inning,
            'halfInning': half,
            'outs': outs,
            'isComplete': True,
            'isScoringPlay': False,
        },
        'result': {
            'eventType': 'field_out',
            'homeScore': home_score,
            'awayScore': away_score,
        },
        'matchup': {
            'pitcher': {'id': pitcher_id},
            'batter': {'id': 9000 + index},
        },
    }


def _pbp(*, game_pk=GAME_PK, extra=False, pitch_speed=95.0):
    last = 10 if extra else 9
    plays = [
        _play(0, 1, 'top', 101, 0, 0),
        _play(1, 1, 'bottom', 202, 0, 0),
        _play(2, 6, 'bottom', 404, 2, 2),
        _play(3, 7, 'top', 303, 2, 2),
        _play(4, last, 'bottom', 404, 4, 2),
    ]
    plays[0]['playEvents'] = [{
        'index': 0,
        'isPitch': True,
        'pitchNumber': 1,
        'details': {
            'type': {'code': 'FF', 'description': 'Four-Seam Fastball'},
            'call': {'code': 'C', 'description': 'Called Strike'},
            'isBall': False,
            'isStrike': True,
            'isInPlay': False,
            'isOut': False,
        },
        'count': {'balls': 0, 'strikes': 1, 'outs': 0},
        'pitchData': {'startSpeed': pitch_speed, 'zone': 5},
    }]
    return {'allPlays': plays}


def _observation(identity, payload, *, correction=False, completeness='complete'):
    records = (
        len(payload.get('allPlays') or [])
        if isinstance(payload, dict) and 'allPlays' in payload else 1
    )
    return record_source_observation(
        identity=identity,
        payload=payload,
        completeness=completeness,
        payload_schema_version=1,
        payload_kind=PayloadKind.RAW_JSON,
        record_count=records,
        correction=correction,
    ).observation


def _bundle(*, game=None, box=None, pbp=None, correction=False, pbp_completeness='complete', include_pbp=True):
    game = game or _game()
    box = box or _boxscore()
    pbp = (_pbp() if pbp is None else pbp) if include_pbp else None
    return FinalSourceBundle(
        game=game,
        boxscore=box,
        play_by_play=pbp,
        finality_observation=_observation(
            finality_source_identity(game['gamePk'], GAME_DATE), game,
            correction=correction,
        ),
        boxscore_observation=_observation(
            boxscore_source_identity(game['gamePk'], GAME_DATE), box,
            correction=correction,
        ),
        play_by_play_observation=(
            _observation(
                play_by_play_source_identity(game['gamePk'], GAME_DATE), pbp,
                correction=correction, completeness=pbp_completeness,
            ) if pbp is not None else None
        ),
        play_by_play_completeness=pbp_completeness,
        play_by_play_changed=correction,
    )


def _seed_schedule(game_pk=GAME_PK):
    schedule_final_game(game_pk, game_date=GAME_DATE)
    db.session.commit()


def _claimed_job(*, game_pk=GAME_PK, parent_run_id=None, suffix='one'):
    job = enqueue_job(
        job_type=JobType.RECONCILE_FINAL_GAME,
        scope_type=JobScopeType.GAME,
        scope_key=str(game_pk),
        product_date=GAME_DATE,
        dedupe_key=f'test-final:{game_pk}:{suffix}',
        sync_run_id=parent_run_id,
        payload_schema_version=1,
        payload={
            'game_pk': game_pk,
            'baseball_date': GAME_DATE.isoformat(),
            'schedule_observation_id': 1,
        },
    )
    return claim_next_job('sp07-test', job_types=[JobType.RECONCILE_FINAL_GAME])


def test_source_identities_are_stable_and_domain_specific():
    assert finality_source_identity(GAME_PK, GAME_DATE).identity_key == finality_source_identity(GAME_PK, GAME_DATE).identity_key
    assert boxscore_source_identity(GAME_PK, GAME_DATE).source_domain == 'boxscore'
    assert play_by_play_source_identity(GAME_PK, GAME_DATE).source_domain == 'play_by_play'
    assert len({
        finality_source_identity(GAME_PK, GAME_DATE).identity_key,
        boxscore_source_identity(GAME_PK, GAME_DATE).identity_key,
        play_by_play_source_identity(GAME_PK, GAME_DATE).identity_key,
    }) == 3


def test_first_final_reconciliation_versions_actual_appearances_and_gamelog(app):
    with app.app_context():
        _seed_schedule()
        result = reconcile_final_game(_bundle())
        assert result.game_version.version_number == 1
        assert result.game_version.home_score == 4
        assert result.game_version.innings_played == 9
        assert len(result.appearance_versions) == 4
        assert GameLog.query.count() == 4
        assert FinalPitchingAppearanceVersion.query.count() == 4
        assert {row.team_id_at_appearance for row in result.appearance_versions} == {HOME_TEAM, AWAY_TEAM}
        starters = [row for row in result.appearance_versions if row.appearance_role == 'starter']
        assert {row.pitcher_mlb_id for row in starters} == {101, 202}
        assert {row.appearance_order for row in starters} == {0}
        relievers = [row for row in result.appearance_versions if row.appearance_role == 'reliever']
        assert {row.appearance_order for row in relievers} == {1}
        assert all(row.boxscore_observation_id for row in result.appearance_versions)
        assert all(row.play_by_play_observation_id for row in result.appearance_versions)
        assert {'final_game_ingested', 'starter_appearance_added', 'reliever_appearance_added'} <= {row.mutation_type for row in result.mutations}
        assert result.affected_team_ids == (AWAY_TEAM, HOME_TEAM)
        assert len(result.affected_pitcher_ids) == 4


def test_repeat_identical_final_is_zero_mutation(app):
    with app.app_context():
        _seed_schedule()
        bundle = _bundle()
        first = reconcile_final_game(bundle)
        second = reconcile_final_game(bundle)
        assert second.created is False
        assert second.game_version.id == first.game_version.id
        assert second.mutations == ()
        assert FinalGameVersion.query.count() == 1
        assert FinalPitchingAppearanceVersion.query.count() == 4
        assert FinalGameMutation.query.count() == 5


def test_final_authority_supersedes_but_preserves_live_evidence(app):
    with app.app_context():
        _seed_schedule()
        bundle = _bundle()
        pitcher = Pitcher(mlb_id=303, full_name='Home Reliever', active=False, position='P')
        db.session.add(pitcher)
        db.session.flush()
        live = ProvisionalPitchingAppearanceState(
            game_pk=GAME_PK, baseball_date=GAME_DATE, pitcher_id=pitcher.id,
            pitcher_mlb_id=303, team_id_at_appearance=HOME_TEAM, side='home',
            appearance_role='reliever', outing_status='closed', outs_recorded=8,
            pitches_thrown=17, first_observation_id=bundle.boxscore_observation.id,
            latest_observation_id=bundle.boxscore_observation.id,
            fact_fingerprint='a' * 64, fingerprint_version='live-appearance-v1',
            completeness='complete_for_observation', authority_state='live',
            is_current=True, first_seen_at=utc_now_naive(), latest_seen_at=utc_now_naive(),
        )
        db.session.add(live)
        db.session.commit()
        result = reconcile_final_game(bundle)
        db.session.refresh(live)
        assert live.is_current is False
        assert live.pitches_thrown == 17
        assert live.superseded_by_final_game_version_id == result.game_version.id
        final = FinalPitchingAppearanceVersion.query.filter_by(
            game_pk=GAME_PK, pitcher_mlb_id=303, is_current=True,
        ).one()
        assert final.pitches_thrown == 18


def test_legacy_completed_game_bootstraps_versions_without_false_mutation(app):
    with app.app_context():
        _seed_schedule()
        game = _game()
        box = _boxscore()
        legacy = sync_service.process_completed_game_for_postgame_refresh(
            game, schedule_date=GAME_DATE, boxscore=box, force=True,
        )
        lines = sync_service._extract_pitching_lines_from_boxscore(box)
        appearances = appearance_extraction.extract_game_appearances(
            game=game,
            pitching_lines=lines,
            pitcher_order=sync_service._pitcher_order_by_side(box),
            game_date=GAME_DATE,
        )
        db.session.add(GameIngestionWorkItem(
            mlb_game_pk=GAME_PK,
            represented_date=GAME_DATE,
            game_date=GAME_DATE,
            candidate_reason='newly_final',
            criticality='publication_critical',
            status='completed',
            completed_at=utc_now_naive(),
            source_revision=appearance_extraction.appearance_set_fingerprint(appearances),
            rows_expected=len(appearances),
            rows_reconciled=len(appearances),
            relief_rows_reconciled=2,
        ))
        db.session.commit()
        result = reconcile_final_game(_bundle(game=game, box=box))
        assert result.created is True
        assert len(result.appearance_versions) == 4
        assert result.mutations == ()
        assert result.affected_pitcher_ids == ()
        assert FinalGameMutation.query.count() == 0


def test_one_pitching_line_correction_versions_only_changed_pitcher(app):
    with app.app_context():
        _seed_schedule()
        first = reconcile_final_game(_bundle())
        corrected = reconcile_final_game(_bundle(
            box=_boxscore(home_reliever_pitches=19), correction=True,
        ))
        assert corrected.game_version.version_number == 2
        assert corrected.game_version.predecessor_version_id == first.game_version.id
        assert len(corrected.appearance_versions) == 1
        changed = corrected.appearance_versions[0]
        assert changed.pitcher_mlb_id == 303
        assert changed.pitches_thrown == 19
        assert changed.version_number == 2
        assert changed.predecessor_version_id is not None
        previous = db.session.get(FinalPitchingAppearanceVersion, changed.predecessor_version_id)
        assert previous.pitches_thrown == 18
        assert previous.is_current is False
        from models.pitcher import Pitcher
        assert (
            GameLog.query.join(Pitcher, Pitcher.id == GameLog.pitcher_id)
            .filter(Pitcher.mlb_id == 303).one().pitches_thrown
        ) == 19
        assert [row.mutation_type for row in corrected.mutations] == ['pitching_line_corrected']
        assert corrected.affected_pitcher_ids == (changed.pitcher_id,)


def test_complete_correction_can_remove_phantom_projection_without_losing_history(app):
    with app.app_context():
        _seed_schedule()
        first = reconcile_final_game(_bundle())
        removed = next(row for row in first.appearance_versions if row.pitcher_mlb_id == 303)
        corrected = reconcile_final_game(_bundle(
            box=_boxscore(include_home_reliever=False),
            pbp={'allPlays': [play for play in _pbp()['allPlays'] if (play['matchup']['pitcher']['id'] != 303)]},
            correction=True,
        ))
        assert removed.is_current is False
        assert not any(row.pitcher_mlb_id == 303 for row in current_final_appearances(GAME_PK))
        assert GameLog.query.filter_by(id=removed.game_log_id).one_or_none() is None
        mutation = next(row for row in corrected.mutations if row.pitcher_mlb_id == 303)
        assert mutation.details_json['removed_from_complete_official_appearance_set'] is True


def test_probable_starter_does_not_override_actual_starter(app):
    with app.app_context():
        _seed_schedule()
        from models.scheduled_game import ScheduledGame
        for row in ScheduledGame.query.filter_by(game_pk=GAME_PK):
            row.home_probable_pitcher_mlb_id = 999999
        db.session.commit()
        result = reconcile_final_game(_bundle())
        starter = next(row for row in result.appearance_versions if row.side == 'home' and row.appearance_role == 'starter')
        assert starter.pitcher_mlb_id == 101
        assert {row.home_probable_pitcher_mlb_id for row in ScheduledGame.query.filter_by(game_pk=GAME_PK)} == {999999}


def test_optional_pbp_failure_preserves_core_with_unknown_context(app):
    with app.app_context():
        _seed_schedule()
        bundle = _bundle(include_pbp=False, pbp_completeness='failed')
        result = reconcile_final_game(bundle)
        assert len(result.appearance_versions) == 4
        assert GameLog.query.count() == 4
        assert {row.context_completeness for row in result.appearance_versions} == {'unknown'}
        assert {row.appearance_order for row in result.appearance_versions if row.appearance_role == 'reliever'} == {None}
        assert result.game_version.pbp_completeness == 'failed'


def test_partial_pbp_cannot_supply_authoritative_order_or_context(app):
    with app.app_context():
        _seed_schedule()
        result = reconcile_final_game(_bundle(pbp_completeness='partial'))
        relievers = [
            row for row in result.appearance_versions
            if row.appearance_role == 'reliever'
        ]
        assert {row.appearance_order for row in relievers} == {None}
        assert {row.context_completeness for row in relievers} == {'unknown'}
        assert result.game_version.pbp_completeness == 'partial'


def test_pitch_only_final_pbp_correction_is_not_hidden_by_same_boxscore(app):
    with app.app_context():
        _seed_schedule()
        first = reconcile_final_game(_bundle(pbp=_pbp(pitch_speed=95.0)))
        corrected = reconcile_final_game(_bundle(
            pbp=_pbp(pitch_speed=96.5), correction=True,
        ))
        assert corrected.game_version.version_number == 2
        assert corrected.game_version.predecessor_version_id == first.game_version.id
        assert corrected.appearance_versions == ()
        assert [row.mutation_type for row in corrected.mutations] == [
            'final_play_by_play_corrected'
        ]
        assert corrected.affected_pitcher_mlb_ids == (101,)
        assert corrected.game_version.play_by_play_observation_id != first.game_version.play_by_play_observation_id


def test_non_final_or_incomplete_boxscore_cannot_mutate_core(app):
    with app.app_context():
        _seed_schedule()
        nonfinal = _game()
        nonfinal['status'] = {'statusCode': 'I', 'detailedState': 'In Progress', 'abstractGameState': 'Live'}
        with pytest.raises(ValueError, match='not authoritative Final'):
            reconcile_final_game(_bundle(game=nonfinal))
        db.session.rollback()
        assert GameLog.query.count() == 0
        assert FinalGameVersion.query.count() == 0


def test_crash_rolls_back_core_and_retry_is_idempotent(app):
    with app.app_context():
        _seed_schedule()
        bundle = _bundle()
        with pytest.raises(RuntimeError, match='simulated failure'):
            reconcile_final_game(bundle, commit=False, fail_after_core=True)
        db.session.rollback()
        assert GameLog.query.count() == 0
        assert FinalGameVersion.query.count() == 0
        assert FinalGameMutation.query.count() == 0
        retry = reconcile_final_game(bundle)
        assert retry.game_version.version_number == 1
        assert FinalPitchingAppearanceVersion.query.count() == 4


def test_worker_creates_child_run_and_one_deduplicated_impact_handoff(app):
    with app.app_context():
        _seed_schedule()
        parent = SyncRun(
            job_name='fetch_schedule', source='adaptive_game_state',
            run_type='schedule_game_state', trigger_type='game_status_change',
            status='success', stage='complete', baseball_date=GAME_DATE,
            correlation_id='sp07-correlation',
        )
        db.session.add(parent)
        db.session.commit()
        job = _claimed_job(parent_run_id=parent.id)
        result = execute_final_game_job(job, acquirer=lambda *_args, **_kwargs: _bundle())
        run = db.session.get(SyncRun, result['sync_run_id'])
        assert run.run_type == 'final_game_reconciliation'
        assert run.parent_sync_run_id == parent.id
        assert run.correlation_id == parent.correlation_id
        assert run.status == 'success'
        assert run.canonical_mutations == 5
        assert SyncJob.query.filter_by(job_name='process_canonical_impact').count() == 1


def test_acquisition_records_failed_optional_pbp_without_fake_observation(app):
    class Client:
        def get_schedule(self, **_kwargs):
            return [_game()]

        def get_game_boxscore(self, _game_pk):
            return _boxscore()

        def get_game_play_by_play(self, _game_pk):
            raise TimeoutError('optional PBP unavailable')

    with app.app_context():
        bundle = acquire_final_game_sources(GAME_PK, GAME_DATE, client=Client())
        assert bundle.play_by_play is None
        assert bundle.play_by_play_observation is None
        assert bundle.play_by_play_completeness == 'failed'
        assert SourceObservation.query.count() == 2


def test_acquisition_selects_requested_date_when_rescheduled_game_pk_has_two_rows(app):
    postponed = _game()
    # MLB retains the makeup date as officialDate on both rows while gameDate
    # preserves the original postponed slot on the non-final row.
    postponed['officialDate'] = GAME_DATE.isoformat()
    postponed['gameDate'] = '2026-06-18T23:15:00Z'
    postponed['status'] = {
        'statusCode': 'DR',
        'detailedState': 'Postponed',
        'abstractGameState': 'Preview',
    }

    class Client:
        def get_schedule(self, **_kwargs):
            return [postponed, _game()]

        def get_game_boxscore(self, _game_pk):
            return _boxscore()

        def get_game_play_by_play(self, _game_pk):
            return _pbp()

    with app.app_context():
        bundle = acquire_final_game_sources(GAME_PK, GAME_DATE, client=Client())

        assert bundle.game['officialDate'] == GAME_DATE.isoformat()
        assert bundle.game['status']['abstractGameState'] == 'Final'
        assert bundle.finality_observation.completeness == 'complete'


def test_doubleheaders_and_extra_innings_remain_game_pk_scoped(app):
    with app.app_context():
        _seed_schedule(GAME_PK)
        _seed_schedule(GAME_PK + 1)
        first = reconcile_final_game(_bundle())
        second_game = _game(GAME_PK + 1, game_number=2)
        second = reconcile_final_game(_bundle(
            game=second_game,
            pbp=_pbp(game_pk=GAME_PK + 1, extra=True),
        ))
        assert first.game_version.game_pk != second.game_version.game_pk
        assert second.game_version.innings_played == 10
        assert second.game_version.extra_innings is True


def test_same_game_concurrent_reconciliation_creates_one_version_on_postgresql(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL final-game concurrency contract')
        _seed_schedule()
        bundle = _bundle()
        ids = {
            'finality': bundle.finality_observation.id,
            'boxscore': bundle.boxscore_observation.id,
            'pbp': bundle.play_by_play_observation.id,
        }
        payloads = (bundle.game, bundle.boxscore, bundle.play_by_play)
    barrier = Barrier(2)

    def persist():
        with app.app_context():
            local = FinalSourceBundle(
                game=payloads[0], boxscore=payloads[1], play_by_play=payloads[2],
                finality_observation=db.session.get(SourceObservation, ids['finality']),
                boxscore_observation=db.session.get(SourceObservation, ids['boxscore']),
                play_by_play_observation=db.session.get(SourceObservation, ids['pbp']),
                play_by_play_completeness='complete',
            )
            barrier.wait(timeout=10)
            result = reconcile_final_game(local)
            version_id = result.game_version.id
            db.session.remove()
            return version_id

    with ThreadPoolExecutor(max_workers=2) as pool:
        version_ids = list(pool.map(lambda _index: persist(), range(2)))
    with app.app_context():
        assert version_ids[0] == version_ids[1]
        assert FinalGameVersion.query.count() == 1
        assert FinalPitchingAppearanceVersion.query.count() == 4
        assert FinalGameMutation.query.count() == 5


def test_migration_round_trip_preserves_existing_rows():
    engine = sa.create_engine('sqlite:///:memory:')
    metadata = sa.MetaData()
    for name in ('source_observations', 'sync_runs', 'game_logs', 'pitchers'):
        sa.Table(name, metadata, sa.Column('id', sa.Integer(), primary_key=True))
    metadata.create_all(engine)
    path = (
        Path(__file__).resolve().parents[1] / 'migrations' / 'versions'
        / 'e8b4c2d6f1a9_add_final_game_reconciliation.py'
    )
    spec = importlib.util.spec_from_file_location('sp07_migration', path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    with engine.begin() as connection:
        connection.execute(sa.text('INSERT INTO game_logs (id) VALUES (1)'))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        assert 'final_game_versions' in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text('SELECT id FROM game_logs')).scalar_one() == 1
        migration.downgrade()
        assert 'final_game_versions' not in sa.inspect(connection).get_table_names()
        assert connection.execute(sa.text('SELECT id FROM game_logs')).scalar_one() == 1
