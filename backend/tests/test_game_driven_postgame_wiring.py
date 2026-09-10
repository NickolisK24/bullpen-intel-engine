"""The postgame refresh's game-driven appearance lane integration point.

Foundation 3C wired the game-driven lane into the daily sync only. The postgame
refresh — which is where completed games actually land overnight — had no
integration point at all, so the lane could not observe the cycle that produces
most of its candidates.

These tests own that integration point and the two properties that make it safe
to run there:

* it is invoked **exactly once** per postgame cycle, through the same service
  call the daily sync uses, and never as a second parallel ingestion command;
* it refuses a writing mode outright, because the postgame sweep has no
  ``skip_game_pks`` equivalent and therefore no way to stop two writers from
  touching the same canonical rows.

Nothing here activates the lane. The default remains ``off``.
"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest
from flask import Flask

from tests.db_config import configure_test_database, create_test_schema, drop_test_schema

import models.fatigue_score  # noqa: F401
import models.prospect  # noqa: F401
from models.game_ingestion_work_item import GameIngestionWorkItem
from models.game_log import GameLog
from models.pitcher import Pitcher
from models.postgame_processed_game import PostgameProcessedGame
from models.scheduled_game import ScheduledGame
from models.sync_failure import SyncFailure
from services import game_driven_ingestion
from services import sync as sync_service
from services import sync_metadata
from utils.db import db


SLATE = date(2026, 6, 20)
GAME_PK = 7001


@pytest.fixture
def app(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_service, 'STATUS_FILE', tmp_path / 'sync_status.json')
    monkeypatch.setattr(
        sync_service, 'recalculate_all_fatigue', lambda reference_date=None: 0,
    )
    monkeypatch.setattr(
        sync_service,
        '_prepare_canonical_public_roster_authority',
        lambda reference_date, **_kwargs: {
            'status': 'qualified',
            'qualified': True,
            'reference_date': reference_date.isoformat(),
            'reason_codes': [],
            'records_failed': 0,
            'errors': 0,
        },
    )

    def fake_complete(sync_run_id, **kwargs):
        run = sync_metadata.finish_sync_run(
            sync_run_id,
            status=kwargs['final_status'],
            records_processed=kwargs.get('records_processed', 0),
            records_failed=kwargs.get('records_failed', 0),
            new_logs_added=kwargs.get('new_logs_added', 0),
            pitchers_updated=kwargs.get('pitchers_updated', 0),
            errors=kwargs.get('errors', 0),
            api_calls_made=kwargs.get('api_calls_made', 0),
            retries_used=kwargs.get('retries_used', 0),
            error_message=kwargs.get('error_message'),
            source=kwargs.get('source', 'test'),
            started_at=kwargs.get('started_at'),
            job_name=kwargs.get('job_name', sync_metadata.JOB_POSTGAME_REFRESH),
        )
        return run, SimpleNamespace(id=123)

    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', fake_complete)

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


# ── Fixtures shared with the established postgame harness ───────────────────


def _seed_pitchers():
    db.session.add_all([
        Pitcher(
            mlb_id=101, full_name='Home Reliever', team_id=1,
            team_abbreviation='HME', active=True,
        ),
        Pitcher(
            mlb_id=202, full_name='Away Reliever', team_id=2,
            team_abbreviation='AWY', active=True,
        ),
    ])
    db.session.commit()


def _schedule_ledger(game_pk=GAME_PK, *, game_date=SLATE):
    """Durable schedule authority the game-driven planner reads from."""
    for team_id, opponent_id, side in ((1, 2, 'home'), (2, 1, 'away')):
        db.session.add(ScheduledGame(
            team_id=team_id, game_pk=game_pk, game_date=game_date,
            game_datetime=datetime(
                game_date.year, game_date.month, game_date.day, 19, 5,
            ),
            opponent_team_id=opponent_id, home_away=side, game_type='R',
            status_code='F', status_state=ScheduledGame.STATE_FINAL,
        ))
    db.session.commit()


def _game(game_pk=GAME_PK, status_code='F', detailed_state='Final',
          abstract_state='Final'):
    return {
        'gamePk': game_pk,
        'gameType': 'R',
        'officialDate': SLATE.isoformat(),
        'status': {
            'statusCode': status_code,
            'detailedState': detailed_state,
            'abstractGameState': abstract_state,
        },
        'teams': {
            'home': {'team': {'id': 1, 'name': 'Home Club'}},
            'away': {'team': {'id': 2, 'name': 'Away Club'}},
        },
    }


def _boxscore():
    return {
        'teams': {
            'home': {
                'team': {'id': 1, 'name': 'Home Club'},
                'pitchers': [101],
                'players': {
                    'ID101': {
                        'person': {'fullName': 'Home Reliever'},
                        'stats': {'pitching': {
                            'inningsPitched': '1.0', 'numberOfPitches': '14',
                            'strikes': '9', 'hits': '0', 'runs': '0',
                            'earnedRuns': '0', 'baseOnBalls': '0',
                            'strikeOuts': '2', 'homeRuns': '0',
                            'battersFaced': '3',
                        }},
                    },
                },
            },
            'away': {
                'team': {'id': 2, 'name': 'Away Club'},
                'pitchers': [202],
                'players': {
                    'ID202': {
                        'person': {'fullName': 'Away Reliever'},
                        'stats': {'pitching': {
                            'inningsPitched': '0.2', 'numberOfPitches': '11',
                            'strikes': '7', 'hits': '1', 'runs': '0',
                            'earnedRuns': '0', 'baseOnBalls': '0',
                            'strikeOuts': '1', 'homeRuns': '0',
                            'battersFaced': '3',
                        }},
                    },
                },
            },
        },
    }


def _patch_mlb(monkeypatch, schedule_games=None):
    calls = {'schedule': 0, 'boxscore': [], 'linescore': [], 'play_by_play': []}
    games = _game_list(schedule_games)

    def fake_schedule(start_date=None, end_date=None, team_id=None):
        calls['schedule'] += 1
        return games

    def fake_boxscore(game_pk):
        calls['boxscore'].append(game_pk)
        return _boxscore()

    def fake_linescore(game_pk):
        calls['linescore'].append(game_pk)
        return None

    def fake_play_by_play(game_pk):
        calls['play_by_play'].append(game_pk)
        return {'allPlays': []}

    monkeypatch.setattr(sync_service.mlb_client, 'get_schedule', fake_schedule)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_boxscore', fake_boxscore)
    monkeypatch.setattr(sync_service.mlb_client, 'get_game_linescore', fake_linescore)
    monkeypatch.setattr(
        sync_service.mlb_client, 'get_game_play_by_play', fake_play_by_play,
    )
    sync_service.mlb_client.metrics.reset()
    return calls


def _game_list(schedule_games):
    return [_game()] if schedule_games is None else schedule_games


def _run(app):
    return sync_service.run_postgame_refresh(
        app, schedule_date=SLATE, source='test',
    )


class _LaneSpy:
    """Records every game-driven service invocation the cycle makes."""

    def __init__(self, report=None, raises=None):
        self.calls = []
        self._report = report
        self._raises = raises

    def __call__(self, reference_date, **kwargs):
        self.calls.append({'reference_date': reference_date, **kwargs})
        if self._raises is not None:
            raise self._raises
        return self._report if self._report is not None else _clean_report(
            kwargs.get('mode'),
        )


def _clean_report(mode, **overrides):
    report = {
        'status': 'complete',
        'mode': mode,
        'reference_date': SLATE.isoformat(),
        'games_discovered': 0,
        'games_planned': 0,
        'games_attempted': 0,
        'games_fetched': 0,
        'games_completed': 0,
        'games_failed': 0,
        'games_remaining': 0,
        'rows_expected': 0,
        'rows_inserted': 0,
        'rows_updated': 0,
        'rows_unchanged': 0,
        'rows_blocked': 0,
        'pitcher_identity_mutations': 0,
        'appearance_team_mutations': 0,
        'complete_mutation_count': 0,
        'budget_stop_triggered': False,
        'failure_classes': {},
        'games': [],
        'reconciliation_plan_fingerprint': None,
        'complete_reconciliation_fingerprint': None,
        'parity_contract_version': '4',
        'elapsed_seconds': 0.1,
        'remaining_budget_seconds': 42.0,
    }
    report.update(overrides)
    return report


def _patch_lane(monkeypatch, spy):
    monkeypatch.setattr(
        game_driven_ingestion, 'run_game_driven_ingestion', spy,
    )


# ── The integration point exists, and is used exactly once ──────────────────


def test_the_postgame_cycle_has_a_game_driven_integration_point(app, monkeypatch):
    """The defect this file was written for: postgame never called the lane."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    _run(app)

    assert len(spy.calls) == 1


def test_the_lane_runs_exactly_once_per_postgame_cycle(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    _run(app)

    assert len(spy.calls) == 1, 'a second invocation is a duplicate planning pass'


def test_the_lane_is_called_with_the_postgame_job_name(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    _run(app)

    assert spy.calls[0]['job_name'] == sync_metadata.JOB_POSTGAME_REFRESH


def test_the_lane_reads_the_primary_slate_date(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    _run(app)

    assert spy.calls[0]['reference_date'] == SLATE


def test_the_lane_receives_a_bounded_time_budget(app, monkeypatch):
    """Unbounded would risk the postgame command timeout killing the sync."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    _run(app)

    budget = spy.calls[0]['time_budget_seconds']
    assert budget is not None
    assert 0 < budget <= sync_service.POSTGAME_REFRESH_DEFAULT_INGESTION_BUDGET_SECONDS


def test_the_postgame_lane_budget_is_configurable_and_still_bounded(monkeypatch):
    monkeypatch.setenv('POSTGAME_REFRESH_INGESTION_BUDGET_SECONDS', '120')
    assert sync_service._postgame_refresh_ingestion_budget_seconds() == 120.0
    budget = sync_service._postgame_refresh_runtime_budget()
    assert budget['ingestion_budget_seconds'] == 120.0
    assert budget['total_budget_seconds'] is None


def test_an_unparseable_postgame_budget_falls_back_to_the_bounded_default(monkeypatch):
    monkeypatch.setenv('POSTGAME_REFRESH_INGESTION_BUDGET_SECONDS', 'not-a-number')
    assert sync_service._postgame_refresh_ingestion_budget_seconds() == (
        sync_service.POSTGAME_REFRESH_DEFAULT_INGESTION_BUDGET_SECONDS
    )


# ── Off by default ──────────────────────────────────────────────────────────


def test_the_lane_is_not_invoked_when_the_mode_is_unset(app, monkeypatch):
    monkeypatch.delenv(game_driven_ingestion.MODE_ENV_VAR, raising=False)
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert spy.calls == []
    assert status['game_driven_ingestion'] == {'status': 'disabled', 'mode': 'off'}


def test_an_invalid_mode_is_not_invoked_either(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'nonsense')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert spy.calls == []
    assert status['game_driven_ingestion']['mode'] == 'off'


def test_the_off_cycle_behaves_exactly_as_it_did_before(app, monkeypatch):
    monkeypatch.delenv(game_driven_ingestion.MODE_ENV_VAR, raising=False)
    with app.app_context():
        _seed_pitchers()
    calls = _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['status'] == 'success'
    assert status['games_processed'] == 1
    assert status['new_logs_added'] == 2
    assert calls['boxscore'] == [GAME_PK]
    # The integration point exists and reported itself off — not absent.
    assert status['game_driven_ingestion']['status'] == 'disabled'
    with app.app_context():
        assert PostgameProcessedGame.query.filter_by(mlb_game_pk=GAME_PK).count() == 1
        assert GameIngestionWorkItem.query.count() == 0


# ── The two-writer refusal ──────────────────────────────────────────────────


@pytest.mark.parametrize('mode', ['write', 'authoritative'])
def test_a_writing_mode_is_refused_on_the_postgame_cycle(app, monkeypatch, mode):
    """No skip_game_pks equivalent exists here, so two writers are impossible
    to prevent — the lane refuses rather than running anyway."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, mode)
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert spy.calls == [], 'a refused mode must not reach the planner'
    assert status['game_driven_ingestion']['status'] == 'refused'
    assert status['game_driven_ingestion']['reason'] == (
        sync_service.GAME_DRIVEN_WRITE_MODE_UNSUPPORTED
    )


@pytest.mark.parametrize('mode', ['write', 'authoritative'])
def test_a_refused_mode_never_becomes_publication_authoritative(
    app, monkeypatch, mode,
):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, mode)
    _patch_lane(monkeypatch, _LaneSpy())
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_lane_authoritative'] is False


@pytest.mark.parametrize('mode', ['write', 'authoritative'])
def test_a_refused_mode_writes_no_game_driven_control_state(app, monkeypatch, mode):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, mode)
    _patch_lane(monkeypatch, _LaneSpy())
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_ingestion']['status'] == 'refused'
    with app.app_context():
        assert GameIngestionWorkItem.query.count() == 0


def test_a_refused_mode_does_not_fail_the_postgame_cycle(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'write')
    _patch_lane(monkeypatch, _LaneSpy())
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_ingestion']['status'] == 'refused'
    assert status['status'] == 'success'
    assert status['new_logs_added'] == 2


def test_the_daily_cycle_still_supports_writing_modes(app, monkeypatch):
    """The refusal is per-cycle, not a global downgrade of the lane."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'write')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    status = {}
    with app.app_context():
        result = sync_service._run_game_driven_ingestion_stage(
            reference_date=SLATE,
            runtime_budget={'ingestion_budget_seconds': 100.0},
            sync_run_id=None,
            status=status,
            stage_timings={},
            run_logger=sync_service.logger,
        )

    assert len(spy.calls) == 1
    assert result['refused_reason'] is None
    assert status['game_driven_ingestion']['job_name'] == sync_metadata.JOB_DAILY_SYNC


# ── Shadow isolation ────────────────────────────────────────────────────────


def test_shadow_writes_no_game_driven_control_state(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    # The lane genuinely ran and projected real work — otherwise the absence
    # assertions below would hold vacuously.
    assert lane['status'] == 'complete'
    assert lane['games_planned'] == 1
    assert lane['games_completed'] == 1
    assert lane['rows_expected'] == 2
    with app.app_context():
        assert GameIngestionWorkItem.query.count() == 0
        assert SyncFailure.query.filter_by(
            entity_type=game_driven_ingestion.GAME_INGESTION_FAILURE_ENTITY_TYPE
        ).count() == 0


# ── Ordering: the lane observes the cycle's writer, it does not front-run it ─


def test_the_lane_reads_the_slate_after_the_legacy_sweep_has_written_it(
    app, monkeypatch,
):
    """Placed ahead of the sweep, shadow would project every row the sweep is
    about to insert. Placed after it, the projection is what it should be:
    the current path's own rows, unchanged."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    status = _run(app)
    lane = status['game_driven_ingestion']

    assert status['new_logs_added'] == 2, 'the legacy sweep must have written'
    assert lane['rows_expected'] == 2
    assert lane['rows_unchanged'] == 2
    assert lane['rows_inserted'] == 0
    assert lane['rows_updated'] == 0
    assert lane['rows_blocked'] == 0


def test_the_lane_projects_zero_mutations_over_rows_the_sweep_just_wrote(
    app, monkeypatch,
):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    assert lane['pitcher_identity_mutations'] == 0
    assert lane['appearance_team_mutations'] == 0
    assert lane['complete_mutation_count'] == 0
    assert lane['canonical_outs_corrections'] == 0
    assert lane['statistical_corrections'] == 0
    assert lane['provenance_only_updates'] == 0


def test_the_projection_produces_a_run_fingerprint_when_work_is_planned(
    app, monkeypatch,
):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    fingerprint = lane['reconciliation_plan_fingerprint']
    assert fingerprint is not None
    assert len(fingerprint) == 64
    assert fingerprint == fingerprint.lower()
    assert all(character in '0123456789abcdef' for character in fingerprint)
    assert lane['complete_reconciliation_fingerprint'] == fingerprint


def test_a_shadow_lane_failure_does_not_fail_the_postgame_cycle(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(monkeypatch, _LaneSpy(raises=RuntimeError('planner exploded')))
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_ingestion']['status'] == 'failed'
    assert status['status'] == 'success'
    assert status['games_processed'] == 1
    assert status['new_logs_added'] == 2


def test_a_shadow_lane_failure_is_reported_by_safe_class_only(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(
        monkeypatch,
        _LaneSpy(raises=RuntimeError('postgresql://user:pw@host/db exploded')),
    )
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    lane = status['game_driven_ingestion']
    assert lane['status'] == 'failed'
    assert lane['error_class'] == 'RuntimeError'
    assert 'postgresql://' not in repr(lane)
    assert 'exploded' not in repr(lane)


def test_a_shadow_lane_failure_creates_no_dead_letter(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(monkeypatch, _LaneSpy(raises=RuntimeError('boom')))
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_ingestion']['status'] == 'failed'
    with app.app_context():
        assert SyncFailure.query.filter_by(
            entity_type=game_driven_ingestion.GAME_INGESTION_FAILURE_ENTITY_TYPE
        ).count() == 0


def test_a_shadow_lane_failure_leaves_the_legacy_postgame_writes_intact(
    app, monkeypatch,
):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(monkeypatch, _LaneSpy(raises=RuntimeError('boom')))
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_ingestion']['status'] == 'failed'
    with app.app_context():
        assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 2
        assert PostgameProcessedGame.query.filter_by(mlb_game_pk=GAME_PK).count() == 1


def test_the_shadow_rollback_does_not_discard_committed_preflight_state(
    app, monkeypatch,
):
    """Shadow rolls its read transaction back. Anything committed before it
    must survive that rollback."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_ingestion']['status'] == 'complete'
    with app.app_context():
        assert ScheduledGame.query.filter_by(game_pk=GAME_PK).count() == 2
        assert Pitcher.query.count() == 2
        assert GameLog.query.filter_by(mlb_game_pk=GAME_PK).count() == 2


def test_shadow_never_becomes_publication_authoritative(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert status['game_driven_lane_authoritative'] is False


# ── Observability ───────────────────────────────────────────────────────────


def test_the_shadow_cycle_reports_its_identity_and_authority(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(monkeypatch, _LaneSpy())
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    assert lane['mode'] == 'shadow'
    assert lane['writes_enabled'] is False
    assert lane['publication_authoritative'] is False
    assert lane['job_name'] == sync_metadata.JOB_POSTGAME_REFRESH


def test_the_shadow_cycle_reports_every_mutation_target(app, monkeypatch):
    """A cycle must not be able to claim "no mutations" while a target is
    unaccounted for."""
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(monkeypatch, _LaneSpy())
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    for field in (
        'rows_inserted', 'rows_updated', 'rows_blocked',
        'pitcher_identity_mutations', 'pitcher_identity_creations',
        'pitcher_identity_reactivations', 'pitcher_identity_metadata_updates',
        'pitcher_identity_blocked', 'appearance_team_mutations',
        'complete_mutation_count', 'canonical_outs_corrections',
        'statistical_corrections', 'provenance_only_updates',
        'derived_companion_fields_applied',
    ):
        assert field in lane, f'{field} is not observable'


def test_the_shadow_cycle_reports_its_budget_allocation_and_headroom(
    app, monkeypatch,
):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    _patch_lane(monkeypatch, _LaneSpy())
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)
    lane = status['game_driven_ingestion']

    assert lane['allocated_budget_seconds'] is not None
    assert lane['remaining_budget_seconds'] == 42.0
    assert status['runtime_budget']['ingestion_budget_seconds'] == (
        sync_service.POSTGAME_REFRESH_DEFAULT_INGESTION_BUDGET_SECONDS
    )


def test_the_shadow_cycle_reports_the_version_constants(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    assert lane['reconciliation_plan_version'] == '3'
    assert lane['parity_contract_version'] == '4'
    assert lane['innings_semantics_version'] == '2'
    assert lane['complete_plan_version'] == '1'
    assert lane['identity_plan_version'] == '1'


def test_the_shadow_cycle_reports_a_fingerprint_field_as_evidence(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    lane = _run(app)['game_driven_ingestion']

    assert 'reconciliation_plan_fingerprint' in lane
    assert 'complete_reconciliation_fingerprint' in lane


def test_the_reported_lane_carries_no_credentials_or_paths(app, monkeypatch):
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    with app.app_context():
        _seed_pitchers()
        _schedule_ledger()
    _patch_mlb(monkeypatch)

    rendered = repr(_run(app)['game_driven_ingestion'])

    for forbidden in (
        'postgresql://', 'postgres://', 'password=', 'Authorization:',
        'ADMIN_API_TOKEN', 'SECRET_KEY', 'DATABASE_URL', 'token=',
        'api_key=', 'secret=', '/home/', 'Traceback',
    ):
        assert forbidden not in rendered


# ── No second ingestion path ────────────────────────────────────────────────


def test_the_postgame_cycle_invokes_no_game_driven_cli(app, monkeypatch):
    """The service integration point is the only allowed invocation."""
    import subprocess

    calls = []
    monkeypatch.setattr(
        subprocess, 'run', lambda *a, **k: calls.append(a) or SimpleNamespace(
            returncode=0,
        ),
    )
    monkeypatch.setenv(game_driven_ingestion.MODE_ENV_VAR, 'shadow')
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    _run(app)

    assert len(spy.calls) == 1, 'the service integration point must have run'
    assert calls == [], 'no game-driven CLI subprocess may be spawned'


# ── The backfill hazard the activation package must handle ──────────────────


def test_explicit_backfill_shares_the_postgame_entry_point(app, monkeypatch):
    """The workflow's explicit backfill step runs
    ``run_postgame_refresh.py --date``, which is this same function. Adding the
    lane here therefore put it on the backfill path too.

    That is inert today — the lane is ``off`` and this cycle refuses writing
    modes — but any future activation MUST set ``GAME_DRIVEN_INGESTION_MODE:
    'off'`` explicitly on the backfill step. This test exists so that
    requirement cannot be forgotten silently: it fails the moment the shared
    entry point stops being shared, which is the only thing that would make the
    requirement obsolete.
    """
    import pathlib

    workflow = pathlib.Path(__file__).resolve().parents[2] / (
        '.github/workflows/baseballos-sync.yml'
    )
    text = workflow.read_text(encoding='utf-8')
    assert 'run_postgame_refresh.py --date "$BACKFILL_DATE"' in text, (
        'backfill no longer routes through run_postgame_refresh — re-derive '
        'whether the game-driven lane still reaches the backfill path'
    )

    # And with the mode off — the current production value — a dated replay
    # runs the cycle without invoking the lane at all.
    monkeypatch.delenv(game_driven_ingestion.MODE_ENV_VAR, raising=False)
    spy = _LaneSpy()
    _patch_lane(monkeypatch, spy)
    with app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch)

    status = _run(app)

    assert spy.calls == []
    assert status['game_driven_ingestion']['status'] == 'disabled'


def test_the_lane_is_configured_only_by_a_reviewed_workflow_literal():
    """The reviewed workflow source is the activation authority.

    This test originally asserted that no workflow configured the lane at all,
    which was correct while nothing was activated. Automated shadow activation
    made that statement false on purpose, so the guarantee it protected is
    restated in the form that still holds and still matters: wherever the mode
    appears, it is a reviewed literal, and it is never a writing mode. A
    ``vars.*`` or ``inputs.*`` value here would move production without review.

    Placement and per-step eligibility are owned by
    ``test_game_driven_shadow_activation_workflow.py``.
    """
    import pathlib
    import re

    workflows = (
        pathlib.Path(__file__).resolve().parents[2] / '.github/workflows'
    )
    configured = 0
    for path in sorted(workflows.glob('*.yml')):
        text = path.read_text(encoding='utf-8')
        assert 'game_driven_ingestion.py' not in text, (
            f'{path.name} invokes the game-driven CLI as a second ingestion '
            f'command'
        )
        for value in re.findall(r'GAME_DRIVEN_INGESTION_MODE:\s*(.+)', text):
            configured += 1
            assert value.strip() in ("'shadow'", "'off'"), (
                f'{path.name} configures the lane with {value.strip()!r}; the '
                f'mode must be a reviewed literal and never a writing mode'
            )
    assert configured > 0, (
        'the lane is configured nowhere — if activation was reverted, revert '
        'this expectation with it rather than leaving a test that proves '
        'nothing'
    )


def test_the_stage_helper_is_the_single_call_site_in_the_sync_service():
    """A second call site would be a duplicate planning pass no test could see."""
    import pathlib

    source = (
        pathlib.Path(sync_service.__file__).read_text(encoding='utf-8')
    )
    invocations = source.count('game_driven_ingestion.run_game_driven_ingestion(')
    assert invocations == 1, (
        'services.sync must reach the lane through exactly one call site'
    )
    assert source.count('def _run_game_driven_ingestion_stage(') == 1
    stage_calls = source.count('= _run_game_driven_ingestion_stage(')
    assert stage_calls == 2, (
        'exactly two cycles integrate the lane: daily and postgame'
    )
