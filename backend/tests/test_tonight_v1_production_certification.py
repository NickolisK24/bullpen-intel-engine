"""TN-12: final production certification of the Tonight v1 system.

These gates certify, end to end on real trusted publications, the properties
BaseballOS relies on when Tonight is the canonical homepage. Each test names
its certification-matrix row (docs/audits/tonight-v1-final-production-
certification-tn-12.md). Behaviour already pinned by a dedicated suite is
cross-referenced there; this module adds the cross-cutting gates:

* B  every served edition carries a complete, self-consistent identity whose
     ``content_sha256`` is recomputable from the stored payload;
* D  the serve-time overlay changes only the permitted game-state fields and
     never the frozen baseball intelligence;
* M  a withheld Dashboard publication creates no Tonight edition and leaves the
     current edition untouched;
* V  a normal serve is read-only and its query count is bounded;
* T  repo-wide legacy isolation counts are zero outside the explicit, deprecated
     public compatibility surface.
"""

from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path
import re

from sqlalchemy import event

from models.dashboard_snapshot import DashboardSnapshot
from models.slate_game import SlateGame
from models.tonight_publication import TonightPublication
from services import dashboard_snapshot
from services import tonight_read_model
from services import tonight_v1_serving
from tests.test_tonight_v1_read_model import (  # noqa: F401 - pytest fixtures
    _publish,
    tonight_app,
)
from utils.db import db


V1_URL = '/api/bullpen/intelligence/tonight?contract=tonight_v1'
DEFAULT_URL = '/api/bullpen/intelligence/tonight'
REPO = Path(__file__).resolve().parents[2]

# The only per-game fields the TN-03/TN-04 overlay may serve differently.
OVERLAY_GAME_FIELDS = frozenset({'state', 'first_pitch_utc', 'state_as_of', 'context'})


def _enable(env, *, today=None, monkeypatch=None):
    env.app.config['TONIGHT_V1_PROJECTION_ENABLED'] = True
    if monkeypatch is not None:
        monkeypatch.setattr(
            tonight_v1_serving, 'product_current_date',
            lambda: today or env.reference_date,
        )


def _get(env, url=V1_URL, **headers):
    return env.app.test_client().get(url, headers=headers)


def _assert_identity(body, response, row, snapshot):
    """Certification row B: the served edition identity is complete and exact."""
    edition = body['edition']
    publication = edition['publication']
    assert body['contract'] == row.contract == 'tonight_v1'
    assert edition['baseball_date'] == row.reference_date.isoformat()
    assert publication['dashboard_snapshot_id'] == row.dashboard_snapshot_id == snapshot.id
    assert publication['sync_run_id'] == row.sync_run_id == snapshot.sync_run_id
    assert edition['data_through'] == row.data_through.isoformat()
    assert row.data_through == snapshot.data_through
    # Preserved from the snapshot, never re-dated (TN-11.8).
    assert row.availability_reference_date == snapshot.availability_reference_date
    assert edition['availability_reference_date'] == (
        snapshot.availability_reference_date.isoformat()
    )
    assert edition['generated_at']
    assert row.generated_at is not None
    assert re.fullmatch(r'[0-9a-f]{64}', row.content_sha256)
    assert tonight_read_model.content_sha256(row.payload) == row.content_sha256
    assert response.headers['ETag'] == f'"{row.content_sha256}"'
    assert response.headers['X-BaseballOS-Snapshot-Id'] == str(snapshot.id)
    assert response.headers['X-BaseballOS-Contract'] == 'tonight_v1'
    assert body == row.payload, 'with no overlay the served body is the stored body'


# ── B. Publication identity ──────────────────────────────────────────────────

def test_b_publication_time_edition_identity_is_complete(tonight_app, monkeypatch):
    _enable(tonight_app, monkeypatch=monkeypatch)
    snapshot = tonight_app.snapshot
    result = tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='cert')
    row = db.session.get(TonightPublication, result['tonight_publication_id'])
    assert row.reference_date == snapshot.availability_reference_date

    for url in (DEFAULT_URL, V1_URL):
        response = _get(tonight_app, url)
        _assert_identity(response.get_json(), response, row, snapshot)


def test_b_rolled_forward_edition_identity_is_complete(tonight_app, monkeypatch):
    """The same snapshot validly owns a second, later-dated edition."""
    next_day = tonight_app.reference_date + timedelta(days=1)
    _enable(tonight_app, today=next_day, monkeypatch=monkeypatch)
    snapshot = tonight_app.snapshot
    tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='cert')
    result = tonight_read_model.ensure_tonight_v1_for_date(snapshot, next_day, source='cert')
    row = db.session.get(TonightPublication, result['tonight_publication_id'])
    assert row.reference_date == next_day != snapshot.availability_reference_date
    assert TonightPublication.query.filter_by(dashboard_snapshot_id=snapshot.id).count() == 2

    for url in (DEFAULT_URL, V1_URL):
        response = _get(tonight_app, url)
        _assert_identity(response.get_json(), response, row, snapshot)


# ── D. Game-state overlay: permitted fields only ─────────────────────────────

def _allowed_difference(stored, served):
    """Assert ``served`` differs from ``stored`` only where the overlay may."""
    assert served.keys() == stored.keys()
    for key in stored:
        if key == 'games':
            assert [g['game_pk'] for g in served['games']] == [
                g['game_pk'] for g in stored['games']
            ], 'game membership and order are frozen'
            for before, after in zip(stored['games'], served['games']):
                changed = {k for k in before if before[k] != after.get(k)}
                assert changed <= OVERLAY_GAME_FIELDS, (before['game_pk'], changed)
                assert after.keys() == before.keys()
                for side in ('away', 'home'):
                    assert after[side] == before[side], 'frozen TeamSide changed'
        elif key == 'lead':
            if stored['lead'] is None:
                assert served['lead'] is None
            else:
                changed = {k for k in stored['lead'] if stored['lead'][k] != served['lead'][k]}
                assert changed <= {'reason_codes'}, changed
        elif key == 'summary':
            changed = {k for k in stored['summary'] if stored['summary'][k] != served['summary'][k]}
            assert changed <= {'games_by_state'}, changed
        elif key == 'limitations':
            assert set(stored['limitations']) <= set(served['limitations'])
        else:
            # edition, featured_game_pks, league_changes, quiet_day, contract.
            assert served[key] == stored[key], key


def test_d_overlay_changes_only_permitted_fields(tonight_app, monkeypatch):
    _enable(tonight_app, monkeypatch=monkeypatch)
    snapshot = tonight_app.snapshot
    result = tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='cert')
    row = db.session.get(TonightPublication, result['tonight_publication_id'])
    stored = deepcopy(row.payload)
    stored_pks = [game['game_pk'] for game in stored['games']]
    assert len(stored_pks) >= 3

    # scheduled -> live, scheduled -> final, scheduled -> postponed, and a
    # first-pitch time change on a still-scheduled game.
    transitions = {
        stored_pks[0]: (SlateGame.STATE_LIVE, 'In Progress'),
        stored_pks[1]: (SlateGame.STATE_COMPLETED, 'Final'),
        stored_pks[2]: (SlateGame.STATE_CANCELLED, 'Postponed'),
    }
    later = max(g.last_synced for g in SlateGame.query.all()) + timedelta(minutes=45)
    for game_pk, (state, detail) in transitions.items():
        game = db.session.get(SlateGame, game_pk)
        game.normalized_state = state
        game.status_detailed = detail
        game.last_synced = later
    moved = [pk for pk in stored_pks if pk not in transitions]
    if moved:
        game = db.session.get(SlateGame, moved[0])
        game.game_time_utc = game.game_time_utc + timedelta(minutes=30)
        game.last_synced = later
    db.session.commit()

    first, second = _get(tonight_app), _get(tonight_app)
    served = first.get_json()
    _allowed_difference(stored, served)
    states = {game['game_pk']: game['state'] for game in served['games']}
    assert states[stored_pks[0]] == 'live'
    assert states[stored_pks[1]] == 'final'
    assert states[stored_pks[2]] == 'postponed'
    # Deterministic, strong, overlay-aware validator; conditional GET works.
    assert first.headers['ETag'] == second.headers['ETag']
    assert first.headers['ETag'] != f'"{row.content_sha256}"'
    assert not first.headers['ETag'].startswith('W/')
    assert _get(tonight_app, **{'If-None-Match': first.headers['ETag']}).status_code == 304
    # The stored row never changes.
    db.session.expire_all()
    assert db.session.get(TonightPublication, row.id).payload == stored


def test_d_terminal_states_never_regress(tonight_app, monkeypatch):
    _enable(tonight_app, monkeypatch=monkeypatch)
    for row, current, allowed in (
        ('final', 'live', False), ('final', 'scheduled', False),
        ('live', 'scheduled', False), ('postponed', 'live', False),
        ('scheduled', 'live', True), ('live', 'final', True),
        ('suspended', 'live', True),
    ):
        assert (current in tonight_v1_serving.ALLOWED_TRANSITIONS[row]) is allowed, (row, current)


# ── M. Publication failure ───────────────────────────────────────────────────

def test_m_withheld_publication_creates_no_edition_and_changes_nothing(
    tonight_app, monkeypatch,
):
    _enable(tonight_app, monkeypatch=monkeypatch)
    snapshot = tonight_app.snapshot
    current = tonight_read_model.ensure_tonight_v1_for_publication(snapshot, source='cert')
    current_row = db.session.get(TonightPublication, current['tonight_publication_id'])
    frozen = (current_row.id, current_row.content_sha256, deepcopy(current_row.payload))
    served_before = _get(tonight_app).get_json()

    # A candidate withheld by a publication gate stays pending evidence. The
    # gate is forced only while the candidate is built, so serving afterwards
    # evaluates the real trusted publication.
    with monkeypatch.context() as gate:
        gate.setattr(
            dashboard_snapshot, '_payload_slate_coverage_unavailable_reason',
            lambda _payload: dashboard_snapshot.DASHBOARD_SNAPSHOT_SLATE_COVERAGE_INCOMPLETE,
        )
        withheld = _publish_withheld(tonight_app)
    assert withheld.is_published is False
    assert withheld.status == dashboard_snapshot.SNAPSHOT_STATUS_PENDING

    # No edition for the withheld candidate, by hook or by any ensure.
    assert TonightPublication.query.filter_by(dashboard_snapshot_id=withheld.id).count() == 0
    rolled = tonight_read_model.ensure_tonight_v1_for_date(
        withheld, tonight_app.reference_date, source='cert',
    )
    assert rolled['status'] == 'skipped'
    assert rolled['reason'] == 'publication_not_trusted'
    assert TonightPublication.query.filter_by(dashboard_snapshot_id=withheld.id).count() == 0

    # The trusted edition is untouched and still the one served.
    db.session.expire_all()
    again = db.session.get(TonightPublication, frozen[0])
    assert (again.id, again.content_sha256, again.payload) == frozen
    assert _get(tonight_app).get_json() == served_before


def _publish_withheld(env):
    from models.sync_run import SyncRun
    from utils.time import utc_now_naive
    run = SyncRun(
        job_name='tonight_cert_withheld', started_at=utc_now_naive(),
        completed_at=utc_now_naive(), status='success', stage='published',
        source='test',
        latest_game_date=env.reference_date - timedelta(days=1),
        latest_workload_date=env.reference_date - timedelta(days=1),
        latest_fatigue_calculated_at=utc_now_naive(),
    )
    db.session.add(run)
    db.session.flush()
    return dashboard_snapshot.build_bullpen_dashboard_snapshot(
        sync_run_id=run.id, source='tonight_cert_withheld', publish=True,
        raise_errors=True,
    )


# ── V. Serving performance and read-only proof ───────────────────────────────

def test_v_serve_is_read_only_and_query_bounded(tonight_app, monkeypatch):
    _enable(tonight_app, monkeypatch=monkeypatch)
    tonight_read_model.ensure_tonight_v1_for_publication(tonight_app.snapshot, source='cert')
    client = tonight_app.app.test_client()
    client.get(V1_URL)  # warm any one-time app initialisation

    statements = []

    def record(_conn, _cursor, statement, _params, _context, _many):
        statements.append(' '.join(statement.lower().split()))

    event.listen(db.engine, 'before_cursor_execute', record)
    try:
        response = client.get(V1_URL)
    finally:
        event.remove(db.engine, 'before_cursor_execute', record)
    assert response.status_code == 200
    reads = [sql for sql in statements if sql.startswith('select')]
    writes = [sql for sql in statements if sql.startswith(('insert', 'update', 'delete'))]
    assert writes == []
    # Trusted snapshot projection, the one edition row, one overlay read.
    assert len(reads) <= 4, reads
    for table in ('game_logs', 'fatigue_scores', 'pitchers', 'tonight_intelligence_snapshots'):
        assert not any(f'from {table}' in sql for sql in reads), table
    assert not any(
        'dashboard_snapshots.payload as ' in sql for sql in reads
    ), 'serving must never read the full Dashboard payload'


# ── T. Legacy isolation ──────────────────────────────────────────────────────

LEGACY_BUILDERS = (
    'generate_tonight_snapshot_for_date', 'refresh_schedule_and_tonight',
    'serve_tonight_cached', 'prepare_snapshot_for_publication',
    'generate_snapshot_for_date', 'prepare_daily_edition_snapshot',
)
# The explicit, deprecated public compatibility surface (and the legacy
# modules that implement it) plus operator-only maintenance tools.
PUBLIC_COMPATIBILITY_OR_OPERATOR = {
    'backend/api/bullpen.py',
    'backend/services/public_serving_authority.py',
    'backend/services/tonight_intelligence_service.py',
    'backend/services/tonight_intelligence_snapshot.py',
    'backend/services/intelligence_surface_snapshot.py',
    'backend/services/schedule_tonight_refresh.py',
    'backend/services/dashboard_snapshot.py',  # config-off branch, digest-pinned
    'backend/services/sync.py',  # dead helper, never called (TN-11.7 class E)
    'backend/scripts/run_tonight_refresh.py',
    'backend/scripts/prepare_daily_edition_snapshot.py',
    'backend/scripts/repair_daily_edition_context.py',
    'backend/scripts/run_cu01p_proof.py',
}


def _repo_files(*globs):
    for pattern in globs:
        yield from (path for path in REPO.glob(pattern) if path.is_file())


def _code(path):
    # Comment-only lines document retirements ("no longer calls X"); they are
    # not consumers, so the scan reads executable lines only.
    lines = path.read_text(encoding='utf-8', errors='ignore').splitlines()
    return '\n'.join(
        line for line in lines
        if not line.lstrip().startswith(('#', '//', '*', '/*'))
    )


def _consumers(paths):
    found = set()
    for path in paths:
        relative = path.relative_to(REPO).as_posix()
        if '/tests/' in relative or relative.startswith('backend/tests/'):
            continue
        text = _code(path)
        if any(token in text for token in LEGACY_BUILDERS):
            found.add(relative)
    return found


def test_t_legacy_isolation_counts_are_zero():
    internal = _consumers(_repo_files('backend/services/*.py', 'backend/scripts/*.py'))
    internal -= PUBLIC_COMPATIBILITY_OR_OPERATOR
    scheduler = _consumers(_repo_files(
        'backend/services/sync_due.py', 'backend/scripts/run_due_sync.py',
        'backend/scripts/render_start.sh', '.github/workflows/*.yml',
    ))
    publication = _consumers(_repo_files(
        'backend/services/sync_publication_proof.py',
        'backend/services/team_state_vnext_production_proof.py',
        'backend/services/continuous_production_publication.py',
        'backend/services/intraday_repair.py',
        'backend/services/intraday_completed_game_repair.py',
        'backend/services/incremental_publication.py',
        'backend/services/incremental_read_model_rebuild.py',
        'backend/services/tonight_read_model.py',
    ))
    frontend_sources = list(_repo_files('frontend/src/**/*.js', 'frontend/src/**/*.jsx'))
    frontend = {
        path.relative_to(REPO).as_posix() for path in frontend_sources
        if re.search(r'tonight_v5|getTonightIntelligence|getTodayIntelligence|/intelligence/today',
                     _code(path))
    }
    static = _consumers(_repo_files(
        'backend/scripts/export_*.py', 'backend/scripts/*static*.py',
        'backend/scripts/*preview*.py',
    ))

    counts = {
        'internal': sorted(internal), 'scheduler': sorted(scheduler),
        'publication': sorted(publication), 'frontend': sorted(frontend),
        'static_generator': sorted(static),
    }
    assert counts == {key: [] for key in counts}, counts


def test_t_public_v5_compatibility_stays_explicit_and_deprecated(tonight_app):
    response = _get(tonight_app, DEFAULT_URL + '?contract=tonight_v5')
    assert response.status_code == 200
    assert response.headers['Deprecation'] == 'true'
    assert response.headers['X-BaseballOS-Contract'] == 'tonight_v5'
    assert 'successor-version' in response.headers['Link']
    default = _get(tonight_app, DEFAULT_URL).get_json()
    assert default['contract'] == 'tonight_v1'
