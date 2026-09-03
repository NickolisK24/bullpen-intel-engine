"""CU-07 atomic incremental publication and cache-handoff contracts."""

from copy import deepcopy
from datetime import date, datetime
from pathlib import Path
from threading import Barrier, Event, Thread
from types import SimpleNamespace

import pytest
from flask import Flask

from models.dashboard_snapshot import DashboardSnapshot
from models.pitcher import Pitcher
from models.slate_game import SlateGame
from models.sync_run import SyncRun
from services import change_impact_orchestration as orchestration
from services import game_change_detection as detection
from services import game_driven_ingestion
from services import incremental_arm_read_team_state as cu05
from services import incremental_publication as cu07
from services import incremental_read_model_rebuild as cu06
from services import incremental_workload_rest as cu04
from services import sync as sync_service
from tests.db_config import configure_test_database, create_test_schema, drop_test_schema
from tests.game_driven_fixtures import schedule_final_game
from tests.test_continuous_reliever_ingestion import (
    AWAY_TEAM,
    GAME_DATE,
    GAME_PK as REAL_GAME_PK,
    HOME_TEAM,
    _boxscore,
    _play_by_play,
    _seed_pitchers,
)
from tests.test_game_change_detection import _feed
from tests.test_incremental_arm_read_team_state import _fake_provider
from tests.test_incremental_read_model_rebuild import (
    _builders as _cu06_builders,
    _snapshot as _cu06_snapshot,
)
from utils.db import db


GAME_PK = 777001
TEAM_A = 10
TEAM_B = 20
TEAM_C = 30


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


class ProofCache:
    def __init__(self, *, fail=False):
        self.fail = fail
        self.payloads = {}
        self.calls = []

    def handoff(self, publication_id, payload, keys):
        self.calls.append((publication_id, tuple(keys)))
        if self.fail:
            raise RuntimeError('controlled cache failure')
        self.payloads[publication_id] = deepcopy(payload)

    def read(self, publication_id):
        return deepcopy(self.payloads.get(publication_id))


def _cu06(*, marker='new', teams=(TEAM_A, TEAM_B), game_pk=GAME_PK):
    boards = {team_id: {'team_id': team_id, 'state': marker} for team_id in teams}
    league = {team_id: {'team_id': team_id, 'state': marker} for team_id in teams}
    matchups = {game_pk: {'game_pk': game_pk, 'state': marker}} if game_pk else {}
    tonight = {game_pk: {'game_pk': game_pk, 'state': marker}} if game_pk else {}
    return SimpleNamespace(
        game_pk=game_pk,
        represented_date='2026-07-14',
        status='complete',
        reason_code='parity_match',
        requested_pitcher_ids=(1, 2),
        requested_team_ids=tuple(teams),
        team_boards_rebuilt=tuple(teams),
        league_rows_rebuilt=tuple(teams),
        matchups_rebuilt=(game_pk,) if game_pk else (),
        tonight_entries_rebuilt=(game_pk,) if game_pk else (),
        team_board_results=boards,
        league_row_results=league,
        matchup_results=matchups,
        tonight_results=tonight,
        parity_status='match',
        parity_mismatches=(),
        failures=(),
        rebuild_performed=True,
        publication_affected=False,
        cache_invalidation_triggered=False,
    )


def _sync_run():
    row = SyncRun(
        job_name='cu07_proof', status='success', stage='complete',
        source='cu07_proof', completed_at=datetime(2026, 7, 14, 23, 0, 0),
    )
    db.session.add(row)
    db.session.commit()
    return row.id


def _publish(cu06_result, *, order, expected, cache=None, hook=None, identity=None):
    return cu07.publish_incremental(
        cu06_result,
        source_identity=identity or f'canonical-run-{order}',
        source_order=order,
        sync_run_id=_sync_run(),
        expected_current_id=expected,
        cache_adapter=cache,
        failure_hook=hook,
    )


def test_complete_multi_team_candidate_commits_as_one_manifest(app):
    with app.app_context():
        cache = ProofCache()
        result = _publish(_cu06(), order=1, expected=None, cache=cache)

        assert result.status == cu07.RESULT_COMMITTED
        assert result.committed is True
        assert result.affected_team_ids == (TEAM_A, TEAM_B)
        assert result.affected_game_ids == (GAME_PK,)
        assert result.cache_handoff_status == 'complete'
        assert set(result.cache_keys) == {
            f'team_board:{TEAM_A}', f'team_board:{TEAM_B}',
            f'league_row:{TEAM_A}', f'league_row:{TEAM_B}',
            f'matchup:{GAME_PK}', f'tonight:{GAME_PK}',
        }
        current = cu07.get_current_publication()
        assert current.id == result.new_publication_id
        surfaces = cu07.read_current_cohort(cache_adapter=cache)['surfaces']
        assert set(surfaces['team_boards']) == {str(TEAM_A), str(TEAM_B)}
        assert set(surfaces['league_rows']) == {str(TEAM_A), str(TEAM_B)}
        assert set(surfaces['matchups']) == {str(GAME_PK)}
        assert set(surfaces['tonight_entries']) == {str(GAME_PK)}


def test_strongest_cu02_through_cu07_chain_commits_then_stops(app, monkeypatch):
    class Client:
        def get_game_boxscore(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return _boxscore()

        def get_game_play_by_play(self, game_pk):
            assert game_pk == REAL_GAME_PK
            return _play_by_play()

    def observation(*, timestamp, status='Live', code='I', inning=8, outs=1):
        payload = deepcopy(_feed(
            timestamp=timestamp, status=status, code=code,
            inning=inning, outs=outs,
        ))
        payload['gamePk'] = REAL_GAME_PK
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
        schedule_final_game(REAL_GAME_PK, game_date=GAME_DATE)
        monkeypatch.setattr(sync_service, 'mlb_client', Client())
        detection.observe_game_change(
            REAL_GAME_PK, payload=observation(timestamp='20260827_220000'),
        )
        changed = detection.observe_game_change(
            REAL_GAME_PK,
            payload=observation(
                timestamp='20260827_230000', status='Final', code='F',
                inning=9, outs=3,
            ),
        )
        reviewed = game_driven_ingestion.run_game_driven_ingestion(
            GAME_DATE,
            mode=game_driven_ingestion.MODE_SHADOW,
            only_game_pks=[REAL_GAME_PK],
        )
        canonical = orchestration.orchestrate_game_change(
            changed,
            allow_canonical_write=True,
            expected_plan_fingerprint=reviewed['complete_reconciliation_fingerprint'],
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
        db.session.merge(SlateGame(
            game_pk=REAL_GAME_PK,
            game_date_et=GAME_DATE,
            game_time_utc=datetime.combine(GAME_DATE, datetime.min.time()),
            home_team_id=HOME_TEAM,
            away_team_id=AWAY_TEAM,
            normalized_state=SlateGame.STATE_COMPLETED,
        ))
        db.session.commit()
        builders = _cu06_builders([])
        source_snapshot = _cu06_snapshot(team_ids=(AWAY_TEAM, HOME_TEAM, TEAM_C))
        source_snapshot.data_through = GAME_DATE
        source_snapshot.availability_reference_date = date.fromisoformat(
            state.availability_reference_date
        )
        source_snapshot.payload['freshness']['data_through'] = GAME_DATE.isoformat()
        source_snapshot.payload['trusted_team_boards']['data_through'] = GAME_DATE.isoformat()
        source_snapshot.payload['trusted_team_boards']['availability_reference_date'] = (
            state.availability_reference_date
        )
        read_models = cu06.rebuild_read_model_impact(
            state,
            source_snapshot=source_snapshot,
            team_board_builder=builders[0],
            league_listing_builder=builders[1],
            matchup_builder=builders[2],
            tonight_builder=builders[3],
        )
        cache = ProofCache()
        publication = cu07.publish_incremental(
            read_models,
            source_identity=changed.current_observation_identity,
            source_order=2,
            sync_run_id=_sync_run(),
            expected_current_id=None,
            cache_adapter=cache,
        )

        assert canonical.game_log_inserted == 4
        assert canonical.pitch_inserted == 4
        assert workload.parity_status == 'match'
        assert state.parity_status == 'match'
        assert read_models.parity_status == 'match'
        assert publication.status == cu07.RESULT_COMMITTED
        assert publication.affected_team_ids == tuple(
            sorted(canonical.affected_team_ids)
        )
        assert publication.affected_game_ids == (REAL_GAME_PK,)
        assert publication.production_authority_affected is False
        assert cu07.read_current_cohort(cache_adapter=cache) == (
            cu07.get_current_publication().payload
        )
        assert DashboardSnapshot.query.filter_by(
            snapshot_type='bullpen_dashboard', is_published=True,
        ).count() == 0


@pytest.mark.parametrize(
    ('field', 'expected_error'),
    (
        ('team_board_results', 'team_board_cohort_incomplete'),
        ('league_row_results', 'league_cohort_incomplete'),
        ('matchup_results', 'matchup_cohort_incomplete'),
        ('tonight_results', 'tonight_cohort_incomplete'),
    ),
)
def test_missing_required_surface_aborts_before_stage(app, field, expected_error):
    with app.app_context():
        result_value = _cu06()
        setattr(result_value, field, {})
        result = _publish(result_value, order=1, expected=None)
        assert result.status == cu07.RESULT_ABORTED
        assert expected_error in result.errors
        assert DashboardSnapshot.query.count() == 0


def test_parity_mismatch_aborts_before_stage(app):
    with app.app_context():
        value = _cu06()
        value.parity_status = 'mismatch'
        result = _publish(value, order=1, expected=None)
        assert result.reason_code == 'cohort_validation_failed'
        assert result.validation_passed is False
        assert cu07.get_current_publication() is None


def test_staged_candidate_is_invisible_until_atomic_commit(app):
    with app.app_context():
        first = _publish(_cu06(marker='old'), order=1, expected=None)
        candidate = cu07.build_candidate(
            _cu06(marker='new'), source_identity='canonical-run-2', source_order=2,
        )
        staged = cu07.stage_candidate(candidate, sync_run_id=_sync_run())
        assert staged.is_published is False
        assert cu07.read_current_cohort()['surfaces']['team_boards'][str(TEAM_A)]['state'] == 'old'

        previous, current = cu07._commit_candidate(
            staged.id, expected_current_id=first.new_publication_id,
        )
        assert previous == first.new_publication_id
        assert current == staged.id
        assert cu07.read_current_cohort()['surfaces']['team_boards'][str(TEAM_A)]['state'] == 'new'


def test_semantically_identical_retry_is_no_action(app):
    with app.app_context():
        first = _publish(_cu06(), order=1, expected=None)
        count = DashboardSnapshot.query.count()
        retry = _publish(
            _cu06(), order=2, expected=first.new_publication_id,
            identity='different-run-same-semantics',
        )
        assert retry.status == cu07.RESULT_NO_ACTION
        assert retry.new_publication_id is None
        assert DashboardSnapshot.query.count() == count


def test_stale_and_ambiguous_candidates_cannot_replace_current(app):
    with app.app_context():
        first = _publish(_cu06(marker='old'), order=2, expected=None)
        stale = _publish(_cu06(marker='stale'), order=1, expected=first.new_publication_id)
        ambiguous = _publish(
            _cu06(marker='ambiguous'), order=2,
            expected=first.new_publication_id, identity='other-observation',
        )
        assert stale.status == cu07.RESULT_STALE
        assert ambiguous.status == cu07.RESULT_CONFLICT
        assert cu07.get_current_publication().id == first.new_publication_id
        assert cu07.read_current_cohort()['surfaces']['team_boards'][str(TEAM_A)]['state'] == 'old'


def test_expected_current_conflict_rejects_overlapping_candidate(app):
    with app.app_context():
        first = _publish(_cu06(marker='old'), order=1, expected=None)
        conflict = _publish(_cu06(marker='new'), order=2, expected=None)
        assert conflict.status == cu07.RESULT_CONFLICT
        assert conflict.reason_code == 'expected_current_mismatch'
        assert conflict.previous_publication_id == first.new_publication_id
        assert cu07.get_current_publication().id == first.new_publication_id


@pytest.mark.parametrize('failure_point', ('before_pointer_swap', 'before_commit'))
def test_commit_failure_rolls_back_pointer_and_preserves_history(app, failure_point):
    with app.app_context():
        first = _publish(_cu06(marker='old'), order=1, expected=None)
        historical = db.session.get(DashboardSnapshot, first.new_publication_id)
        historical_payload = deepcopy(historical.payload)

        def fail(point, *_args):
            if point == failure_point:
                raise RuntimeError('controlled transaction failure')

        failed = _publish(
            _cu06(marker='new'), order=2,
            expected=first.new_publication_id, hook=fail,
        )
        db.session.expire_all()
        assert failed.status == cu07.RESULT_ABORTED
        assert failed.rollback_performed is True
        assert cu07.get_current_publication().id == first.new_publication_id
        assert db.session.get(DashboardSnapshot, first.new_publication_id).payload == historical_payload
        assert DashboardSnapshot.query.filter_by(is_published=True).count() == 1


def test_pre_commit_failure_leaves_staged_candidate_unserved_and_retryable(app):
    with app.app_context():
        first = _publish(_cu06(marker='old'), order=1, expected=None)

        def fail(point, *_args):
            if point == 'after_stage':
                raise RuntimeError('controlled pre-commit failure')

        failed = _publish(
            _cu06(marker='new'), order=2,
            expected=first.new_publication_id, hook=fail,
        )
        assert failed.reason_code == 'pre_commit_failed'
        assert cu07.get_current_publication().id == first.new_publication_id
        staged_count = DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE,
            status=cu07.STATUS_STAGED,
            is_published=False,
        ).count()
        assert staged_count == 1

        retry = _publish(
            _cu06(marker='new'), order=2, expected=first.new_publication_id,
        )
        assert retry.status == cu07.RESULT_COMMITTED
        assert DashboardSnapshot.query.filter_by(is_published=True).count() == 1


def test_cache_failure_occurs_after_commit_and_retry_is_idempotent(app):
    with app.app_context():
        cache = ProofCache(fail=True)
        result = _publish(_cu06(), order=1, expected=None, cache=cache)
        assert result.status == cu07.RESULT_CACHE_PENDING
        assert result.committed is True
        assert result.cache_handoff_status == 'retry_required'
        assert cu07.get_current_publication().id == result.new_publication_id
        assert cu07.read_current_cohort(cache_adapter=cache) == cu07.get_current_publication().payload

        cache.fail = False
        first_keys = cu07.retry_cache_handoff(result.new_publication_id, cache)
        second_keys = cu07.retry_cache_handoff(result.new_publication_id, cache)
        assert first_keys == second_keys == result.cache_keys
        assert cu07.read_current_cohort(cache_adapter=cache) == cu07.get_current_publication().payload


def test_cache_retry_rejects_mismatched_durable_candidate_receipt(app):
    with app.app_context():
        cache = ProofCache(fail=True)
        result = _publish(_cu06(), order=1, expected=None, cache=cache)

        with pytest.raises(
            ValueError, match='proof publication identity mismatch',
        ):
            cu07.retry_cache_handoff(
                result.new_publication_id,
                cache,
                expected_candidate_id='wrong-candidate',
            )

        assert len(cache.calls) == 1
        assert DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE,
        ).count() == 1

        row = db.session.get(DashboardSnapshot, result.new_publication_id)
        row.payload_version = 2
        db.session.commit()
        with pytest.raises(ValueError, match='proof publication version mismatch'):
            cu07.retry_cache_handoff(
                result.new_publication_id,
                cache,
                expected_candidate_id=result.candidate_id,
                expected_payload_version=1,
            )


def test_unrelated_team_and_production_pointer_remain_unchanged(app):
    with app.app_context():
        production = DashboardSnapshot(
            snapshot_type='bullpen_dashboard', sync_run_id=_sync_run(),
            status='ready', is_published=True,
            payload={'teams': {str(TEAM_C): {'state': 'sentinel'}}},
            payload_version=1, source='sync',
        )
        db.session.add(production)
        db.session.commit()
        result = _publish(_cu06(), order=1, expected=None)
        db.session.expire_all()
        stored = db.session.get(DashboardSnapshot, production.id)
        assert result.production_authority_affected is False
        assert stored.is_published is True
        assert stored.payload == {'teams': {str(TEAM_C): {'state': 'sentinel'}}}
        assert DashboardSnapshot.query.filter_by(
            snapshot_type='bullpen_dashboard', is_published=True,
        ).one().id == production.id


def test_correction_creates_new_immutable_publication_and_old_payload_survives(app):
    with app.app_context():
        first = _publish(_cu06(marker='18-pitches'), order=1, expected=None)
        old_payload = deepcopy(db.session.get(DashboardSnapshot, first.new_publication_id).payload)
        corrected = _publish(
            _cu06(marker='19-pitches'), order=2,
            expected=first.new_publication_id,
        )
        assert corrected.status == cu07.RESULT_COMMITTED
        old = db.session.get(DashboardSnapshot, first.new_publication_id)
        assert old.is_published is False
        assert old.payload == old_payload
        assert cu07.get_current_publication().id == corrected.new_publication_id


def test_restart_style_session_reset_preserves_current_and_idempotency(app):
    with app.app_context():
        first = _publish(_cu06(), order=1, expected=None)
        db.session.remove()
        assert cu07.get_current_publication().id == first.new_publication_id
        replay = _publish(_cu06(), order=1, expected=first.new_publication_id)
        assert replay.status == cu07.RESULT_NO_ACTION


def test_source_excludes_schedulers_public_routes_and_external_work():
    source = Path(cu07.__file__).read_text(encoding='utf-8')
    forbidden = (
        'run_daily_sync(', 'serve_tonight_cached(', 'publish_share_artifact(',
        'invalidate_cache(', 'requests.', 'while True',
    )
    assert [token for token in forbidden if token in source] == []
    assert cu07.PROOF_SNAPSHOT_TYPE != 'bullpen_dashboard'


def test_postgresql_readers_see_old_then_new_never_staged_mix(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL transactional visibility proof')
        first = _publish(_cu06(marker='old'), order=1, expected=None)
        candidate = cu07.build_candidate(
            _cu06(marker='new'), source_identity='canonical-run-2', source_order=2,
        )
        staged = cu07.stage_candidate(candidate, sync_run_id=_sync_run())
        staged_id = staged.id
        old_id = first.new_publication_id
        at_commit = Event()
        release_commit = Event()
        errors = []

        def hold_before_commit(point, *_args):
            if point == 'before_commit':
                at_commit.set()
                if not release_commit.wait(timeout=10):
                    raise TimeoutError('reader did not release controlled commit')

        def commit_in_thread():
            try:
                with app.app_context():
                    cu07._commit_candidate(
                        staged_id,
                        expected_current_id=old_id,
                        failure_hook=hold_before_commit,
                    )
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        worker = Thread(target=commit_in_thread)
        worker.start()
        assert at_commit.wait(timeout=10)
        db.session.remove()
        during = cu07.get_current_publication()
        assert during.id == old_id
        assert during.payload['surfaces']['team_boards'][str(TEAM_A)]['state'] == 'old'
        release_commit.set()
        worker.join(timeout=10)
        assert worker.is_alive() is False
        assert errors == []
        db.session.remove()
        after = cu07.get_current_publication()
        assert after.id == staged_id
        assert after.payload['surfaces']['team_boards'][str(TEAM_A)]['state'] == 'new'


def test_postgresql_overlapping_candidates_have_one_expected_current_winner(app):
    with app.app_context():
        if db.engine.dialect.name != 'postgresql':
            pytest.skip('PostgreSQL concurrency proof')
        first = _publish(_cu06(marker='old'), order=1, expected=None)
        a = cu07.stage_candidate(
            cu07.build_candidate(
                _cu06(marker='candidate-a'),
                source_identity='canonical-run-2', source_order=2,
            ),
            sync_run_id=_sync_run(),
        )
        b = cu07.stage_candidate(
            cu07.build_candidate(
                _cu06(marker='candidate-b'),
                source_identity='canonical-run-3', source_order=3,
            ),
            sync_run_id=_sync_run(),
        )
        ids = (a.id, b.id)
        expected = first.new_publication_id
        barrier = Barrier(2)
        outcomes = []

        def compete(staged_id):
            with app.app_context():
                barrier.wait(timeout=10)
                try:
                    _previous, winner = cu07._commit_candidate(
                        staged_id, expected_current_id=expected,
                    )
                    outcomes.append(('committed', winner))
                except cu07.PublicationRejected as exc:
                    db.session.rollback()
                    outcomes.append((exc.status, exc.current_id))

        workers = [Thread(target=compete, args=(staged_id,)) for staged_id in ids]
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=15)
            assert worker.is_alive() is False

        assert {status for status, _value in outcomes} == {
            cu07.RESULT_CONFLICT, 'committed',
        }
        db.session.remove()
        current = cu07.get_current_publication()
        assert current.id in ids
        assert DashboardSnapshot.query.filter_by(
            snapshot_type=cu07.PROOF_SNAPSHOT_TYPE, is_published=True,
        ).count() == 1
