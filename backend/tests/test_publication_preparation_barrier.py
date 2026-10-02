"""Canonical schedule preparation happens before the candidate is built.

Postgame Primary SyncRun 93277 (2026-10-02 ~04:05Z) built candidate 4190 for
slate 2026-10-01. Slate coverage correctly withheld it: three postseason
"if necessary" Game 3s (849840, 849847, 849850) were still stored as
``scheduled``/``S``. Later in the same execution, the governed runner's
schedule refresh (window Oct 1..Oct 5) made #904's confirming observation
and retired exactly those three games. The execution then ended without
reconsidering publication, so 4157 stayed served although canonical
authority had become publishable.

The postgame lane's only pre-candidate schedule work was the single-date
finality preflight. #904's reschedule lookahead can never confirm a
retirement on that, so the wide window only ran after the candidate. Daily
already refreshes the wide window before its candidate. The fix gives
Postgame the same preparation step and lets the runner reuse that refresh
instead of mutating schedule authority after the candidate was certified.
"""

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import services.sync as sync_service
from models.dashboard_snapshot import DashboardSnapshot
from models.sync_run import SyncRun
from services import schedule_absence, schedule_ingestion, slate_coverage, sync_due, sync_metadata
from tests.test_postgame_refresh import (  # noqa: F401  (postgame harness)
    _REAL_COMPLETE_SYNC_RUN_WITH_SNAPSHOT,
    _game,
    _patch_mlb,
    _run,
    _seed_pitchers,
    app as postgame_app,
)
from tests.test_postseason_conditional_game_retirement import (
    FINAL,
    _mlb_game,
    _response,
)
from tests.test_slate_coverage import _marker, app  # noqa: F401
from utils.db import db


SLATE = date(2026, 10, 1)
PRESENTED = date(2026, 10, 2)
GAME_A = 849845                      # the one real Oct 1 game: final
UNNEEDED = (849840, 849847, 849850)  # the three unneeded Game 3s
FIRST_SEEN = datetime(2026, 10, 1, 10, 39)
RUN_AT = datetime(2026, 10, 2, 4, 5)


def _oct1_games():
    """All four Oct 1 Game 3s as MLB listed them before the series ended."""
    return [_mlb_game(GAME_A, 144, 143)] + [
        _mlb_game(pk, 147 + i, 111 + i) for i, pk in enumerate(UNNEEDED)
    ]


def _ingest_at(response, now, monkeypatch):
    monkeypatch.setattr(schedule_ingestion, 'utc_now_naive', lambda: now)
    return schedule_ingestion.ingest_games(response, source='daily_slate_schedule')


def _seed_93277_state(monkeypatch):
    """Oct 1 as production held it when 93277 started.

    Game A is final and fully processed. The three unneeded Game 3s are
    scheduled, and #904 has already made its first absence observation.
    """
    window = (SLATE - timedelta(days=1), SLATE + timedelta(days=3))
    _ingest_at(_response(*window, _oct1_games()), FIRST_SEEN - timedelta(hours=12),
               monkeypatch)
    first = _ingest_at(_response(*window, [_mlb_game(GAME_A, 144, 143, status=FINAL)]),
                       FIRST_SEEN, monkeypatch)
    assert {g['action'] for g in first['absence_reconciliation']['absent_games']} == {
        'absence_observed'}
    _marker(GAME_A, SLATE)
    db.session.commit()


def _coverage():
    return slate_coverage.compute_slate_coverage(
        SLATE, sync_status='success', publication_critical_complete=True,
    )


def _stub_wide_schedule(monkeypatch):
    calls = []

    def get_schedule(start_date=None, end_date=None, team_id=None):
        calls.append((start_date, end_date))
        return _response(date.fromisoformat(start_date), date.fromisoformat(end_date),
                         [_mlb_game(GAME_A, 144, 143, status=FINAL)])

    monkeypatch.setattr(schedule_ingestion.mlb_client, 'get_schedule', get_schedule)
    return calls


# ── The exact 93277 topology ─────────────────────────────────────────────────

def test_93277_old_order_withholds_and_the_late_refresh_repairs_too_late(app, monkeypatch):
    with app.app_context():
        _seed_93277_state(monkeypatch)
        # What the candidate saw: three non-final games block the slate.
        before = _coverage()
        assert before['complete_enough_to_publish'] is False
        assert before['games_incomplete'] == 3
        blockers = slate_coverage.slate_game_evidence(SLATE)
        assert sorted(g['game_pk'] for g in blockers) == sorted(UNNEEDED)
        assert {g['blocker'] for g in blockers} == {'not_final'}

        # The runner's later wide refresh retires exactly those games.
        _stub_wide_schedule(monkeypatch)
        monkeypatch.setattr(schedule_ingestion, 'utc_now_naive', lambda: RUN_AT)
        late = sync_due.refresh_schedule(PRESENTED, source='postgame')
        assert sorted(late['schedule']['summary']['game_pks_retired']) == sorted(UNNEEDED)
        assert _coverage()['complete_enough_to_publish'] is True


def test_93277_preparation_before_the_candidate_makes_the_slate_publishable(app, monkeypatch):
    with app.app_context():
        _seed_93277_state(monkeypatch)
        calls = _stub_wide_schedule(monkeypatch)
        monkeypatch.setattr(schedule_ingestion, 'utc_now_naive', lambda: RUN_AT)

        prepared = sync_service._refresh_daily_slate_schedule_window(
            sync_service._postgame_slate_window_reference(RUN_AT.replace(tzinfo=timezone.utc)),
            source='postgame_slate_schedule',
        )

        # The same Oct 1..Oct 5 window the runner presents on Oct 2 (ET).
        assert calls == [('2026-10-01', '2026-10-05')]
        assert (prepared['start_date'], prepared['end_date']) == ('2026-10-01', '2026-10-05')
        evidence = sync_service.schedule_preparation_evidence(prepared)
        assert sorted(evidence['game_pks_retired']) == sorted(UNNEEDED)
        assert evidence['prepared_before_candidate'] is True
        # The candidate built next sees 1 final + 3 cancelled.
        coverage = _coverage()
        assert coverage['complete_enough_to_publish'] is True
        assert coverage['games_final'] == 1
        assert coverage['games_cancelled'] == 3
        assert coverage['games_incomplete'] == 0


def test_a_first_absence_observation_before_the_candidate_changes_nothing(app, monkeypatch):
    # #904's two-observation rule is untouched: preparation that only observes
    # leaves the slate blocked, and nothing later in the run retires.
    with app.app_context():
        window = (SLATE - timedelta(days=1), SLATE + timedelta(days=3))
        _ingest_at(_response(*window, _oct1_games()), FIRST_SEEN - timedelta(hours=12),
                   monkeypatch)
        _marker(GAME_A, SLATE)
        db.session.commit()
        _stub_wide_schedule(monkeypatch)
        monkeypatch.setattr(schedule_ingestion, 'utc_now_naive', lambda: RUN_AT)
        prepared = sync_service._refresh_daily_slate_schedule_window(
            PRESENTED, source='postgame_slate_schedule',
        )
        assert prepared['summary']['games_retired'] == 0
        assert _coverage()['complete_enough_to_publish'] is False


# ── Postgame orchestration order ─────────────────────────────────────────────

def test_postgame_prepares_the_schedule_window_before_building_the_candidate(
    postgame_app, monkeypatch,
):
    monkeypatch.setenv('SYNC_SCHEDULE_FINALITY_PREFLIGHT', '1')
    events = []
    with postgame_app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])
    monkeypatch.setattr(
        sync_service, '_refresh_postgame_schedule_finality',
        lambda dates, **_k: events.append('finality_preflight') or {
            'status': 'ok', 'results': [], 'slates_checked': 0, 'slates_refreshed': 0,
        },
    )
    prepared = {
        'status': 'ok', 'start_date': '2026-06-19', 'end_date': '2026-06-23',
        'summary': {'games_seen': 4, 'games_retired': 3, 'game_pks_retired': [1, 2, 3],
                    'absence_reconciliation': {'status': 'reconciled'}},
    }
    seen = {}

    def refresh_window(reference_date, *, source):
        events.append(('slate_schedule', reference_date, source))
        return dict(prepared)

    def complete(sync_run_id, **kwargs):
        events.append('candidate')
        seen.update(kwargs)
        run = sync_metadata.finish_sync_run(
            sync_run_id, status=kwargs['final_status'], source='test',
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        return run, SimpleNamespace(id=4191, is_published=True, status='ready')

    monkeypatch.setattr(sync_service, '_refresh_daily_slate_schedule_window', refresh_window)
    monkeypatch.setattr(sync_service, 'complete_sync_run_with_snapshot', complete)

    status = sync_service.run_postgame_refresh(
        postgame_app, schedule_date=date(2026, 6, 20), source='test',
        window_time=datetime(2026, 6, 21, 4, 5, tzinfo=timezone.utc),
    )

    order = [e if isinstance(e, str) else e[0] for e in events]
    assert order.index('finality_preflight') < order.index('slate_schedule') < order.index(
        'candidate')
    assert events[1] == ('slate_schedule', date(2026, 6, 21), 'postgame_slate_schedule')
    assert status['slate_schedule_refresh']['status'] == 'ok'
    assert seen['preparation']['game_pks_retired'] == [1, 2, 3]
    assert seen['preparation']['prepared_before_candidate'] is True


def test_postgame_without_preflight_prepares_nothing(postgame_app, monkeypatch):
    monkeypatch.setenv('SYNC_SCHEDULE_FINALITY_PREFLIGHT', '0')
    with postgame_app.app_context():
        _seed_pitchers()
    _patch_mlb(monkeypatch, [_game()])
    monkeypatch.setattr(
        sync_service, '_refresh_daily_slate_schedule_window',
        lambda *_a, **_k: pytest.fail('preparation ran with the preflight disabled'),
    )
    status = _run(postgame_app)
    assert status['slate_schedule_refresh'] == {'status': 'skipped', 'reason': 'disabled'}


# ── The governed runner reuses the preparation ───────────────────────────────

def _context(scheduled_for):
    return SimpleNamespace(mode='postgame', source='github_schedule', scheduled_for=scheduled_for)


@pytest.mark.parametrize('prepared, refreshed_after', [
    ({'status': 'ok', 'start_date': '2026-10-01', 'end_date': '2026-10-05'}, False),
    ({'status': 'partial', 'start_date': '2026-10-01', 'end_date': '2026-10-05'}, True),
    ({'status': 'failed', 'start_date': '2026-10-01', 'end_date': '2026-10-05'}, True),
    ({'status': 'ok', 'start_date': '2026-09-30', 'end_date': '2026-10-04'}, True),
    ({'status': 'skipped', 'reason': 'disabled'}, True),
    (None, True),
])
def test_runner_refreshes_after_the_candidate_only_without_matching_preparation(
    monkeypatch, prepared, refreshed_after,
):
    calls = []
    monkeypatch.setattr(
        sync_due, 'refresh_schedule',
        lambda reference_date=None, *, source: calls.append(source) or {'status': 'ok'},
    )
    status = {} if prepared is None else {'slate_schedule_refresh': prepared}
    proof = {}
    schedule = sync_due._refresh_schedule_proof(
        proof, status, _context(datetime(2026, 10, 2, 4, 5, tzinfo=timezone.utc)),
    )
    assert bool(calls) is refreshed_after
    assert schedule['status'] == 'ok'
    assert schedule['prepared_before_candidate'] is (not refreshed_after)
    assert proof['schedule_refresh_verified'] is True
    assert status['schedule_refresh'] is schedule


def test_run_postgame_never_mutates_schedule_after_a_prepared_candidate(monkeypatch):
    events = []
    monkeypatch.setattr(
        sync_due.sync_service, 'run_postgame_refresh',
        lambda *_a, **_k: events.append('postgame') or {
            'status': 'success', 'dashboard_snapshot_id': 4191,
            'new_logs_added': 3, 'logs_corrected': 0,
            'slate_schedule_refresh': {
                'status': 'ok', 'start_date': '2026-10-01', 'end_date': '2026-10-05',
            },
        },
    )
    monkeypatch.setattr(sync_due.sync_service, 'postgame_schedule_dates', lambda _t: [])
    monkeypatch.setattr(
        sync_due, 'reset_fully_processed_markers_without_appearance_rows',
        lambda **_k: {'reset': 0},
    )
    monkeypatch.setattr(sync_due, 'build_candidate_publication_proof',
                        lambda *_a, **_k: {'verified': True})
    monkeypatch.setattr(
        sync_due, 'refresh_schedule',
        lambda *_a, **_k: pytest.fail('schedule authority mutated after the candidate'),
    )
    monkeypatch.setattr(
        sync_due, '_ensure_current_tonight_v1',
        lambda context, **_k: events.append('tonight') or {'status': 'reused'},
    )

    status, proof, successful = sync_due._run_postgame(
        None, _context(datetime(2026, 10, 2, 4, 5, tzinfo=timezone.utc)), None,
        public_only=True,
    )

    assert events == ['postgame', 'tonight']
    assert successful is True
    assert proof['schedule_refresh_verified'] is True
    assert status['schedule_refresh']['prepared_before_candidate'] is True


# ── WP-1: the outcome records what the candidate was prepared on ────────────

@pytest.mark.parametrize('published', [False, True])
def test_outcome_records_the_canonical_preparation(postgame_app, monkeypatch, published):
    from services import dashboard_snapshot as dashboard_snapshot_service

    preparation = sync_service.schedule_preparation_evidence({
        'status': 'ok', 'start_date': '2026-10-01', 'end_date': '2026-10-05',
        'summary': {'games_retired': 3, 'game_pks_retired': list(UNNEEDED),
                    'absence_reconciliation': {'status': 'reconciled'}},
    })
    with postgame_app.app_context():
        sync_run_id = sync_metadata.start_sync_run(
            source='test', job_name=sync_metadata.JOB_POSTGAME_REFRESH,
        )
        candidate = SimpleNamespace(
            id=4191, status='ready' if published else 'pending',
            is_published=published, published_at=None,
            error_message=None if published else (
                dashboard_snapshot_service.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE),
        )
        monkeypatch.setattr(dashboard_snapshot_service, 'build_bullpen_dashboard_snapshot',
                            lambda **_k: candidate)
        monkeypatch.setattr(dashboard_snapshot_service, 'run_post_commit_snapshot_publication',
                            lambda *_a, **_k: None)
        monkeypatch.setattr(sync_service, 'is_trusted_publication', lambda s: published)
        _REAL_COMPLETE_SYNC_RUN_WITH_SNAPSHOT(
            sync_run_id, final_status='success', source='test',
            job_name=sync_metadata.JOB_POSTGAME_REFRESH,
            raise_on_withheld=False, preparation=preparation,
        )
        run = db.session.get(SyncRun, sync_run_id)
        outcome = run.publication_outcome
        assert outcome['status'] == ('published' if published else 'withheld')
        assert outcome['canonical_preparation']['game_pks_retired'] == list(UNNEEDED)
        assert outcome['canonical_preparation']['window'] == ['2026-10-01', '2026-10-05']
        assert outcome['canonical_preparation']['prepared_before_candidate'] is True
        assert DashboardSnapshot.query.count() == 0   # the stub was never stored


def test_no_preparation_leaves_the_outcome_contract_unchanged():
    assert sync_service._preparation_for({}) is None
    assert sync_service._preparation_for(
        {'slate_schedule_refresh': {'status': 'skipped', 'reason': 'disabled'}}) is None
    assert sync_service._with_preparation({'status': 'withheld'}, None) == {'status': 'withheld'}
