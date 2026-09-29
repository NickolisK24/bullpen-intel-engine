"""TN-11.7: legacy Tonight (v5) / Today backend retirement.

Operational jobs no longer generate or depend on the legacy tonight_v5 cache
or the legacy Today (Daily Edition) read model. Tonight is served from the
immutable tonight_v1 row bound to each trusted Dashboard publication; the
legacy surfaces remain only as explicit, deprecated public compatibility.
"""

from copy import deepcopy
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from models.slate_game import SlateGame
from models.tonight_publication import TonightPublication
from services import sync_due
from services import tonight_read_model
from services.sync_execution_context import (
    MODE_DAILY, MODE_MORNING, MODE_POSTGAME, SOURCE_EXTERNAL_SCHEDULE,
)
from tests.test_tonight_v1_read_model import (  # noqa: F401 - pytest fixtures
    _publish,
    tonight_app,
)
from utils.db import db


BACKEND = Path(__file__).resolve().parents[1]
REPO = BACKEND.parent
LEGACY_BUILDER_TOKENS = (
    'tonight_intelligence_snapshot',
    'tonight_intelligence_service',
    'generate_tonight_snapshot_for_date',
    'serve_tonight_cached',
    'refresh_schedule_and_tonight',
    'refresh_tonight_after_publication',
    'intelligence_surface_snapshot',
    'generate_snapshot_for_date',
)
# Every scheduler, publication, repair and continuous path TN-11.7 migrated.
INTERNAL_JOB_MODULES = (
    'services/sync_due.py',
    'services/continuous_production_publication.py',
    'services/intraday_repair.py',
    'services/intraday_completed_game_repair.py',
    'services/incremental_read_model_rebuild.py',
    'services/incremental_publication.py',
    'services/continuous_execution.py',
    'services/schedule_authority.py',
    'scripts/refresh_slate_schedule.py',
    'scripts/run_due_sync.py',
    'scripts/run_continuous_cycle.py',
    'scripts/render_start.sh',
)


# ── Lane semantics (Daily / Postgame / Morning / recovery) ───────────────────

def _context(mode, *, recovery=False):
    return SimpleNamespace(
        mode=mode,
        source=SOURCE_EXTERNAL_SCHEDULE,
        scheduled_for=datetime(2026, 9, 28, 10, 5, tzinfo=timezone.utc),
        recovery_reason='cancelled game blocked slate coverage' if recovery else None,
    )


@pytest.fixture
def lanes(monkeypatch):
    calls = []
    state = {
        'schedule_status': 'ok',
        'proof_verified': True,
        'ensure': {'status': 'reused', 'tonight_publication_id': 5},
        'published': SimpleNamespace(id=3972),
    }

    def forbidden(*_args, **_kwargs):
        raise AssertionError('a scheduled lane reached a legacy Tonight/Today builder')

    import services.intelligence_surface_snapshot as today
    import services.schedule_tonight_refresh as schedule_refresh
    import services.tonight_intelligence_snapshot as tonight_v5
    monkeypatch.setattr(tonight_v5, 'generate_tonight_snapshot_for_date', forbidden)
    monkeypatch.setattr(schedule_refresh, 'generate_tonight_snapshot_for_date', forbidden)
    monkeypatch.setattr(schedule_refresh, 'refresh_schedule_and_tonight', forbidden)
    monkeypatch.setattr(today, 'generate_snapshot_for_date', forbidden)

    def refresh(reference_date=None, *, source):
        calls.append(('schedule', reference_date, source))
        return {'status': state['schedule_status'], 'legacy_tonight_v5': 'not_generated'}

    monkeypatch.setattr(sync_due, 'refresh_schedule', refresh)
    monkeypatch.setattr(
        sync_due.sync_service, 'run_daily_sync',
        lambda *_a, **_k: calls.append(('daily',)) or {
            'status': 'success', 'dashboard_snapshot_id': 3972,
            'publication_critical': {'complete': True},
        },
    )
    monkeypatch.setattr(
        sync_due.sync_service, 'run_postgame_refresh',
        lambda *_a, **_k: calls.append(('postgame',)) or {
            'status': 'success', 'dashboard_snapshot_id': 3972,
            'new_logs_added': 3, 'logs_corrected': 0,
        },
    )
    monkeypatch.setattr(sync_due.sync_service, 'postgame_schedule_dates', lambda _t: [])
    monkeypatch.setattr(
        sync_due, 'reset_fully_processed_markers_without_appearance_rows',
        lambda **_k: {'reset': 0},
    )
    monkeypatch.setattr(
        sync_due, 'build_candidate_publication_proof',
        lambda *_a, **_k: {'verified': state['proof_verified']},
    )
    monkeypatch.setattr(sync_due, '_current_published_snapshot', lambda: state['published'])

    def ensure_publication(snapshot, *, source):
        calls.append(('tonight_v1_publication', snapshot.id, source))
        return {'status': 'reused', 'tonight_publication_id': 4}

    # TN-11.8: every lane ensures the edition for its own intended ET date.
    def ensure_date(snapshot, reference_date, *, source):
        calls.append(('tonight_v1', snapshot.id, reference_date, source))
        return dict(state['ensure'])

    monkeypatch.setattr(
        tonight_read_model, 'ensure_tonight_v1_for_publication', ensure_publication,
    )
    monkeypatch.setattr(tonight_read_model, 'ensure_tonight_v1_for_date', ensure_date)
    return SimpleNamespace(calls=calls, state=state)


def test_daily_succeeds_on_publication_and_schedule_without_legacy_generation(lanes):
    status, proof, successful = sync_due._run_daily(
        None, _context(MODE_DAILY), None, days_back=7, public_only=True,
    )

    assert successful is True
    assert [call[0] for call in lanes.calls] == [
        'daily', 'schedule', 'tonight_v1_publication', 'tonight_v1',
    ]
    assert proof['schedule_refresh_verified'] is True
    assert proof['tonight_v1'] == {
        'status': 'reused', 'tonight_publication_id': 5,
        'publication_edition': {'status': 'reused', 'tonight_publication_id': 4},
    }
    assert lanes.calls[-1] == (
        'tonight_v1', 3972, date(2026, 9, 28), SOURCE_EXTERNAL_SCHEDULE,
    )
    assert status['schedule_refresh']['legacy_tonight_v5'] == 'not_generated'
    assert 'schedule_tonight_refresh' not in status
    assert 'schedule_tonight_verified' not in proof


def test_recovery_daily_uses_the_same_lane_without_legacy_generation(lanes):
    status, proof, successful = sync_due._run_daily(
        None, _context(MODE_DAILY, recovery=True), None, days_back=7, public_only=True,
    )
    assert successful is True
    assert proof['tonight_v1']['status'] == 'reused'


def test_tonight_v1_failure_never_fails_a_valid_publication(lanes):
    lanes.state['ensure'] = {'status': 'failed', 'error': 'RuntimeError'}

    _status, proof, successful = sync_due._run_daily(
        None, _context(MODE_DAILY), None, days_back=7, public_only=True,
    )

    assert successful is True
    assert proof['tonight_v1']['status'] == 'failed'


@pytest.mark.parametrize('lane', ['daily', 'postgame'])
def test_partial_schedule_refresh_still_fails_closed(lanes, lane):
    lanes.state['schedule_status'] = 'partial'
    if lane == 'daily':
        _s, proof, successful = sync_due._run_daily(
            None, _context(MODE_DAILY), None, days_back=7, public_only=True,
        )
    else:
        _s, proof, successful = sync_due._run_postgame(
            None, _context(MODE_POSTGAME), None, public_only=True,
        )
    assert successful is False
    assert proof['schedule_refresh_verified'] is False


def test_unverified_publication_still_fails_the_daily_window(lanes):
    lanes.state['proof_verified'] = False
    _s, _proof, successful = sync_due._run_daily(
        None, _context(MODE_DAILY), None, days_back=7, public_only=True,
    )
    assert successful is False


def test_postgame_succeeds_without_legacy_generation(lanes):
    status, proof, successful = sync_due._run_postgame(
        None, _context(MODE_POSTGAME), None, public_only=True,
    )

    assert successful is True
    assert [call[0] for call in lanes.calls] == [
        'postgame', 'schedule', 'tonight_v1_publication', 'tonight_v1',
    ]
    assert proof['tonight_v1']['status'] == 'reused'


def test_morning_is_schedule_only(lanes):
    result, proof, successful = sync_due._run_morning(_context(MODE_MORNING))

    assert successful is True
    assert proof['verified'] is True
    assert proof['schedule_refresh_verified'] is True
    # TN-11.8: the refreshed ET date's edition only; no publication ensure.
    assert [call[0] for call in lanes.calls] == ['schedule', 'tonight_v1']
    assert lanes.calls[0][1] == date(2026, 9, 28)
    assert lanes.calls[1] == ('tonight_v1', 3972, date(2026, 9, 28), SOURCE_EXTERNAL_SCHEDULE)
    assert result['legacy_tonight_v5'] == 'not_generated'
    assert result['tonight_edition']['schedule_date'] == '2026-09-28'


def test_no_trusted_publication_skips_the_tonight_v1_ensure(lanes):
    lanes.state['published'] = None
    _s, proof, successful = sync_due._run_daily(
        None, _context(MODE_DAILY), None, days_back=7, public_only=True,
    )
    assert successful is True
    assert proof['tonight_v1'] == {
        'status': 'skipped', 'reason': 'no_trusted_publication',
        'reference_date': '2026-09-28',
    }


# ── Ensure: exactly one immutable tonight_v1 row per publication ─────────────

def test_ensure_creates_once_then_reuses_without_rebuilding(tonight_app):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    snapshot = tonight_app.snapshot

    first = tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='daily')
    assert first['status'] == 'created'
    row = TonightPublication.query.one()
    stored = (row.id, row.content_sha256, deepcopy(row.payload), row.generated_at)

    # A later schedule change would make a regenerated payload differ; the
    # ensure must reuse the stored row instead of rebuilding or conflicting.
    game = SlateGame.query.filter_by(game_date_et=tonight_app.reference_date).first()
    game.normalized_state = 'live'
    game.status_detailed = 'In Progress'
    db.session.commit()

    second = tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='postgame')
    assert second == {
        'status': 'reused', 'tonight_publication_id': row.id,
        'dashboard_snapshot_id': snapshot.id,
        'reference_date': tonight_app.reference_date.isoformat(),
    }
    assert TonightPublication.query.count() == 1
    again = db.session.get(TonightPublication, row.id)
    assert (again.id, again.content_sha256, again.payload, again.generated_at) == stored


def test_ensure_respects_the_projection_off_switch(tonight_app):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = False

    result = tonight_read_model.ensure_tonight_v1_for_publication(
        tonight_app.snapshot, source='daily',
    )

    assert result['status'] == 'skipped'
    assert result['reason'] == 'tonight_v1_projection_disabled'
    assert TonightPublication.query.count() == 0


def test_off_day_publication_gets_an_empty_tonight_v1_row(tonight_app):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    SlateGame.query.filter_by(game_date_et=tonight_app.reference_date).delete()
    db.session.commit()

    result = tonight_read_model.ensure_tonight_v1_for_publication(
        tonight_app.snapshot, source='daily',
    )

    assert result['status'] == 'created'
    row = TonightPublication.query.one()
    assert row.reference_date == tonight_app.reference_date
    assert row.payload['games'] == []
    assert row.payload['summary']['game_count'] == 0
    assert row.payload['featured_game_pks'] == []
    assert row.payload['lead'] is None


def test_ensure_never_raises_on_a_read_failure(tonight_app, monkeypatch):
    tonight_app.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True

    def boom(*_args, **_kwargs):
        raise RuntimeError('read failed')

    monkeypatch.setattr(tonight_read_model, 'read_tonight_v1', boom)
    result = tonight_read_model.ensure_tonight_v1_for_publication(
        tonight_app.snapshot, source='daily',
    )
    assert result['status'] == 'failed'
    assert result['error'] == 'RuntimeError'


# ── Today: deprecated compatibility only ─────────────────────────────────────

def test_today_endpoint_is_deprecated_compatibility(tonight_app, monkeypatch):
    from api import bullpen as bullpen_api

    monkeypatch.setattr(
        bullpen_api, 'serve_today_lead_story',
        lambda **_kwargs: {'status': 'empty', 'lead_story': None},
    )
    response = tonight_app.app.test_client().get('/api/bullpen/intelligence/today')

    assert response.status_code == 200
    assert response.headers['Deprecation'] == 'true'
    assert 'contract=tonight_v1' in response.headers['Link']


def test_today_is_no_longer_a_publication_or_startup_prerequisite():
    import importlib

    app = importlib.import_module('app').create_app('test')
    assert app.config['DAILY_EDITION_PUBLICATION_REQUIRED'] is False
    source = (BACKEND / 'app.py').read_text(encoding='utf-8')
    assert "app.config['DAILY_EDITION_PUBLICATION_REQUIRED'] = False" in source


# ── Repo-wide call-graph proof ───────────────────────────────────────────────

def _code(path):
    text = (BACKEND / path).read_text(encoding='utf-8')
    comment = '#'
    return '\n'.join(
        line for line in text.splitlines() if not line.lstrip().startswith(comment)
    )


@pytest.mark.parametrize('module', INTERNAL_JOB_MODULES)
def test_no_internal_job_depends_on_legacy_tonight_or_today(module):
    code = _code(module)
    for token in LEGACY_BUILDER_TOKENS:
        assert token not in code, f'{module} still references {token}'


def test_frontend_and_static_generators_have_no_legacy_consumer():
    offenders = []
    roots = [REPO / 'frontend' / 'src', BACKEND / 'scripts']
    for root in roots:
        for path in root.rglob('*'):
            if path.suffix not in {'.js', '.jsx', '.mjs', '.py', '.sh'}:
                continue
            if path.name in {
                # Explicit operator tools for the deprecated compatibility
                # caches, never scheduled (see the TN-11.7 audit).
                'run_tonight_refresh.py',
                'prepare_daily_edition_snapshot.py',
                'repair_daily_edition_context.py',
                'run_cu01p_proof.py',
            }:
                continue
            text = path.read_text(encoding='utf-8', errors='ignore')
            for token in ('contract=tonight_v5', '/intelligence/today', 'getTonightIntelligence'):
                if token in text:
                    offenders.append((str(path.relative_to(REPO)), token))
    assert offenders == []


def test_workflows_schedule_no_legacy_generation():
    for workflow in (REPO / '.github' / 'workflows').glob('*.yml'):
        text = workflow.read_text(encoding='utf-8')
        for token in (
            'run_tonight_refresh', 'refresh_schedule_and_tonight',
            'prepare_daily_edition_snapshot', 'contract=tonight_v5',
        ):
            assert token not in text, f'{workflow.name} schedules {token}'


def test_no_schema_drop_for_retained_legacy_tables():
    from models.intelligence_surface_snapshot import IntelligenceSurfaceSnapshot
    from models.tonight_intelligence_snapshot import TonightIntelligenceSnapshot

    assert TonightIntelligenceSnapshot.__tablename__ == 'tonight_intelligence_snapshots'
    assert IntelligenceSurfaceSnapshot.__tablename__ == 'intelligence_surface_snapshots'
    versions = BACKEND / 'migrations' / 'versions'
    for migration in versions.glob('*.py'):
        text = migration.read_text(encoding='utf-8')
        if 'def upgrade' not in text:
            continue
        upgrade = text.split('def upgrade', 1)[1].split('def downgrade', 1)[0]
        for table in ('tonight_intelligence_snapshots', 'intelligence_surface_snapshots'):
            assert f"drop_table('{table}')" not in upgrade, migration.name
