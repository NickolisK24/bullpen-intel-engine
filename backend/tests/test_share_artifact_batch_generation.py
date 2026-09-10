"""Tests for batch Team State Share Artifact generation (Share Cards SC-03B-01,
Workstream B) and its internal admin invocation surface.

Proves the batch layer is a thin, deterministic orchestration around the
existing single-team service: shared source authority validated once and failed
closed before any team; canonical enumeration in stable order; independent
per-team outcomes; idempotent reuse; the accounting invariant; coverage / missing
detection; and an internal-only, authorized invocation surface.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from models.pitcher import Pitcher
from models.share_artifact import ShareArtifact
from models.sync_run import SyncRun
from services import team_state_source as source_module
from services.share_artifact_batch_generation import (
    BATCH_OUTCOME_FAILED,
    BATCH_OUTCOME_GENERATED,
    BATCH_OUTCOME_REFUSED,
    BATCH_OUTCOME_REUSED,
    BatchAccountingError,
    BatchGenerationResult,
    BatchSourceAuthorityError,
    BatchTeamResult,
    BatchValidationError,
    generate_team_state_artifacts_batch,
)
from services.share_artifact_generation import (
    OUTCOME_FAILED_CLOSED,
    OUTCOME_PUBLISHED,
    OUTCOME_REFUSED,
    OUTCOME_REUSED,
    TeamStateGenerationResult,
    generate_team_state_artifact,
)
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


SNAPSHOT_ID = 7001
PRODUCT_DATE = date(2026, 7, 20)
TEAM_IDS = (101, 102, 103)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    flask_app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    db.init_app(flask_app)
    with flask_app.app_context():
        create_test_schema(flask_app)
        try:
            yield flask_app
        finally:
            db.session.remove()
            drop_test_schema(flask_app)


@pytest.fixture
def admin_client(app):
    from api.share_artifacts_admin import share_artifacts_admin_bp
    app.register_blueprint(share_artifacts_admin_bp, url_prefix='/api/internal/share-artifacts')
    return app.test_client()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _install_snapshot(monkeypatch, *, snapshot_id=SNAPSHOT_ID, data_through=PRODUCT_DATE,
                      unavailable_reason=None, sync_run_id=None):
    class _Snap:
        pass
    snap = _Snap()
    snap.id = snapshot_id
    snap.sync_run_id = sync_run_id
    snap.data_through = data_through
    snap.published_at = datetime(2026, 7, 20, 13, 0, 0)
    monkeypatch.setattr(source_module, 'get_latest_dashboard_snapshot', lambda *a, **k: snap)
    monkeypatch.setattr(source_module, 'snapshot_unavailable_reason', lambda s, *a, **k: unavailable_reason)
    return snap


def _seed_teams(team_ids=TEAM_IDS):
    for index, team_id in enumerate(team_ids):
        db.session.add(Pitcher(mlb_id=930000 + index, full_name=f'Arm {team_id}',
                               team_id=team_id, active=True))
    db.session.flush()


def _readiness(team_id, *, status_code='operationally_constrained'):
    return {
        'capability': 'team_operations_bullpen_readiness',
        'scope': 'team_bullpen_readiness',
        'contract': 'team_operations_bullpen_readiness_api_contract',
        'contract_version': 'v3_phase_4',
        'contract_state': 'degraded',
        'ranking_applied': False,
        'selection_made': False,
        'generated_at': '2026-07-20T12:00:00Z',
        'team': {'team_id': team_id, 'team_name': f'Club {team_id}',
                 'team_abbreviation': f'C{team_id}'},
        'readiness': {'status': 'Operationally Constrained', 'status_code': status_code,
                      'summary': 'Two late-inning arms are down.', 'basis': []},
        'constraints': [{'constraint_id': 'workload_high', 'category': 'workload',
                         'severity': 'caution', 'affected_area': 'bullpen', 'count': 2,
                         'message': 'Heavy recent relief workload.', 'evidence': []}],
        'trust_metadata': {'confidence': 'high', 'confidence_reasons': [], 'data_state': 'fresh',
                           'source_evidence_state': 'complete', 'governance_state': 'compliant',
                           'generated_at': '2026-07-20T12:00:00Z', 'limitations': [],
                           'explanations': [], 'refusal_reasons': [], 'trust_validation_errors': [],
                           'ranking_applied': False, 'selection_made': False},
        'freshness': {'freshness_state': 'current', 'data_through': '2026-07-20',
                      'latest_workload_date': '2026-07-20',
                      'last_successful_sync': '2026-07-20T11:00:00Z', 'latest_sync_status': 'success',
                      'latest_fatigue_calculated_at': '2026-07-20T11:30:00Z',
                      'generated_at': '2026-07-20T12:00:00Z', 'stale_warning': None,
                      'missing_data_warning': None, 'limitations': []},
        'fail_closed': {'failed_closed': False, 'state': 'degraded_safe_output'},
        'refusal': {'refused': False},
    }


def _real_generator(status_by_team=None):
    """A generator seam that drives the REAL single-team service with a per-team
    readiness resolver (so batch tests exercise real eligibility/publish/dedup/audit)."""
    status_by_team = status_by_team or {}

    def _gen(team_id, **kwargs):
        status = status_by_team.get(team_id, 'operationally_constrained')

        def _resolver(tid, *, requested_date=None, session=None):
            return _readiness(tid, status_code=status)

        return generate_team_state_artifact(team_id, readiness_resolver=_resolver, **kwargs)

    return _gen


def _fixed_result(team_id, outcome, *, public_id=None, blocking=(), failure_code=None):
    return TeamStateGenerationResult(
        outcome=outcome, eligible=(outcome in (OUTCOME_PUBLISHED, OUTCOME_REUSED)),
        created_new=(outcome == OUTCOME_PUBLISHED), reused_existing=(outcome == OUTCOME_REUSED),
        team_id=team_id, requested_date=PRODUCT_DATE, product_date=PRODUCT_DATE,
        source_snapshot_id=SNAPSHOT_ID, source_sync_run_id=None, payload_version='team-state-1.0.0',
        public_id=public_id, blocking_conditions=tuple(blocking), reasons=(), audit_id=1,
        failure_code=failure_code,
    )


# ---------------------------------------------------------------------------
# 8 — full eligible set generates exactly one artifact per team (real path)
# ---------------------------------------------------------------------------


def test_full_eligible_set_generates_one_artifact_per_team(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_real_generator(),
    )
    assert result.attempted_count == len(TEAM_IDS)
    assert result.generated_count == len(TEAM_IDS)
    assert result.reused_count == 0 and result.refused_count == 0 and result.failed_count == 0
    assert result.is_complete and result.missing_count == 0
    # Exactly one published Team State artifact per team.
    published = ShareArtifact.query.filter(
        ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    ).all()
    assert sorted(a.team_id for a in published) == sorted(TEAM_IDS)
    assert all(r.public_id for r in result.results)


# 9 — an equivalent second run reuses the published artifacts (idempotent)
def test_equivalent_rerun_reuses_artifacts(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    kw = dict(source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, actor='admin_batch_api')
    first = generate_team_state_artifacts_batch(generator=_real_generator(), **kw)
    second = generate_team_state_artifacts_batch(generator=_real_generator(), **kw)
    assert first.generated_count == len(TEAM_IDS)
    assert second.generated_count == 0
    assert second.reused_count == len(TEAM_IDS)
    # No duplicate artifacts created on the rerun.
    assert ShareArtifact.query.filter(
        ShareArtifact.artifact_type == TEAM_STATE_ARTIFACT_TYPE
    ).count() == len(TEAM_IDS)


# 10 — mixed outcomes are reported separately (generated/reused/refused/failed)
def test_mixed_outcomes_reported_separately(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)

    def _gen(team_id, **kwargs):
        if team_id == 101:
            return _fixed_result(team_id, OUTCOME_PUBLISHED, public_id='pub-101')
        if team_id == 102:
            return _fixed_result(team_id, OUTCOME_REFUSED, blocking=('insufficient_trust',))
        return _fixed_result(team_id, OUTCOME_FAILED_CLOSED, failure_code='publication_error')

    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_gen,
    )
    assert result.generated_count == 1
    assert result.refused_count == 1
    assert result.failed_count == 1
    assert result.reused_count == 0
    by_team = {r.team_id: r for r in result.results}
    assert by_team[102].outcome == BATCH_OUTCOME_REFUSED
    assert by_team[102].reason_code == 'insufficient_trust'
    assert by_team[103].outcome == BATCH_OUTCOME_FAILED
    assert by_team[103].failure_code == 'publication_error'


# 11 — one refusal does not stop other teams
def test_refusal_does_not_stop_other_teams(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, actor='admin_batch_api',
        generator=_real_generator({102: 'data_limited'}),  # 102 refuses
    )
    assert result.attempted_count == len(TEAM_IDS)
    assert result.refused_count == 1
    assert result.generated_count == len(TEAM_IDS) - 1
    assert {r.team_id for r in result.results} == set(TEAM_IDS)


# 12 — one unexpected exception does not silently skip later teams
def test_unexpected_team_error_does_not_skip_later_teams(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)

    def _gen(team_id, **kwargs):
        if team_id == 102:
            raise RuntimeError('boom')
        return _fixed_result(team_id, OUTCOME_PUBLISHED, public_id=f'pub-{team_id}')

    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_gen,
    )
    assert result.attempted_count == len(TEAM_IDS)
    assert {r.team_id for r in result.results} == set(TEAM_IDS)
    failed = [r for r in result.results if r.outcome == BATCH_OUTCOME_FAILED]
    assert [r.team_id for r in failed] == [102]
    assert failed[0].failure_code == 'batch_team_error'
    # 103 still attempted and generated after 102 raised.
    assert any(r.team_id == 103 and r.outcome == BATCH_OUTCOME_GENERATED for r in result.results)


# 13 — a globally invalid snapshot fails the whole batch before any team
def test_global_invalid_snapshot_fails_before_any_team(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch, unavailable_reason='snapshot_stale')
    calls = []

    def _gen(team_id, **kwargs):
        calls.append(team_id)
        return _fixed_result(team_id, OUTCOME_PUBLISHED)

    with pytest.raises(BatchSourceAuthorityError) as exc:
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
            actor='admin_batch_api', generator=_gen,
        )
    assert exc.value.reason_code == 'snapshot_stale'
    assert calls == []  # no team was attempted


def test_snapshot_id_or_date_mismatch_fails_before_any_team(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    with pytest.raises(BatchSourceAuthorityError) as exc_id:
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID + 1, product_date=PRODUCT_DATE,
            actor='admin_batch_api', generator=_real_generator(),
        )
    assert exc_id.value.reason_code == 'snapshot_id_mismatch'
    with pytest.raises(BatchSourceAuthorityError) as exc_date:
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID, product_date=date(2026, 7, 19),
            actor='admin_batch_api', generator=_real_generator(),
        )
    assert exc_date.value.reason_code == 'product_date_mismatch'


def test_missing_snapshot_fails_closed(app, monkeypatch):
    _seed_teams()
    monkeypatch.setattr(source_module, 'get_latest_dashboard_snapshot', lambda *a, **k: None)
    monkeypatch.setattr(source_module, 'snapshot_unavailable_reason', lambda s, *a, **k: None)
    with pytest.raises(BatchSourceAuthorityError) as exc:
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
            actor='admin_batch_api', generator=_real_generator(),
        )
    assert exc.value.reason_code == 'snapshot_missing'


# 14 — results are in deterministic (stable ascending) team order
def test_results_are_in_deterministic_team_order(app, monkeypatch):
    _seed_teams(team_ids=(103, 101, 102))  # insert out of order
    _install_snapshot(monkeypatch)
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_real_generator(),
    )
    assert [r.team_id for r in result.results] == [101, 102, 103]
    assert result.expected_team_ids == (101, 102, 103)


# 15 — an explicit subset works and stays deterministic
def test_explicit_subset_is_used_and_deterministic(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, actor='admin_batch_api',
        team_ids=[103, 101], generator=_real_generator(),
    )
    assert [r.team_id for r in result.results] == [101, 103]
    assert result.attempted_count == 2
    assert result.canonical_team_count == len(TEAM_IDS)  # full-league size still reported
    assert result.missing_count == 0  # subset fully accounted


# 16 — unknown / duplicate requested ids handled explicitly
def test_duplicate_and_unknown_subset_ids_handled(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    # Duplicates are de-duplicated; an unknown (well-formed) id is attempted and
    # governed-refused by the single-team path (still accounted, never missing).
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, actor='admin_batch_api',
        team_ids=[101, 101, 999999], generator=_real_generator(),
    )
    assert [r.team_id for r in result.results] == [101, 999999]  # deduped, sorted
    unknown = next(r for r in result.results if r.team_id == 999999)
    assert unknown.outcome == BATCH_OUTCOME_REFUSED  # unknown team is refused, accounted
    assert result.missing_count == 0
    # Malformed ids are rejected outright.
    with pytest.raises(BatchValidationError):
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
            actor='admin_batch_api', team_ids=['abc'], generator=_real_generator(),
        )


# 17 — the accounting invariant always holds (and is enforced)
def test_accounting_invariant_holds(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_real_generator({102: 'data_limited'}),
    )
    assert result.attempted_count == (
        result.generated_count + result.reused_count
        + result.refused_count + result.failed_count
    )


def test_accounting_invariant_is_enforced_by_constructor():
    # A malformed result set (attempted != sum of outcomes) is rejected loudly.
    with pytest.raises(BatchAccountingError):
        BatchGenerationResult(
            source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
            results=(BatchTeamResult(team_id=1, outcome='not_a_real_outcome'),),
            canonical_team_count=1, expected_team_ids=(1,),
        )


# 18 — a full-league run identifies any unaccounted canonical team
def test_full_league_run_detects_unaccounted_team(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    # A generator that (pathologically) omits nothing still accounts for all teams;
    # to force a "missing" team we construct the result directly with a gap.
    partial = BatchGenerationResult(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        results=(BatchTeamResult(team_id=101, outcome=BATCH_OUTCOME_GENERATED, public_id='p'),),
        canonical_team_count=3, expected_team_ids=(101, 102, 103),
    )
    assert partial.missing_team_ids == (102, 103)
    assert partial.missing_count == 2
    assert partial.is_complete is False
    # And the real batch never leaves a canonical team unaccounted.
    real = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_real_generator(),
    )
    assert real.missing_count == 0 and real.canonical_team_count == len(TEAM_IDS)


# 20 — a refused team is accounted for (never counted as missing)
def test_refused_team_is_not_missing(app, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    result = generate_team_state_artifacts_batch(
        source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
        actor='admin_batch_api', generator=_real_generator({101: 'data_limited', 102: 'refused'}),
    )
    assert result.refused_count == 2
    assert result.missing_count == 0
    assert result.is_complete


# Malformed batch input is rejected before any snapshot work.
def test_batch_input_validation(app, monkeypatch):
    _install_snapshot(monkeypatch)
    with pytest.raises(BatchValidationError):
        generate_team_state_artifacts_batch(
            source_snapshot_id=None, product_date=PRODUCT_DATE, actor='a', generator=_real_generator())
    with pytest.raises(BatchValidationError):
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID, product_date='2026-07-20', actor='a',
            generator=_real_generator())
    with pytest.raises(BatchValidationError):
        generate_team_state_artifacts_batch(
            source_snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE, actor='a',
            team_ids=[], generator=_real_generator())


# ---------------------------------------------------------------------------
# Internal invocation surface (endpoint) — cases 21, 22, 23
# ---------------------------------------------------------------------------


# 22 — authorization is enforced for the internal invocation surface
def test_batch_endpoint_requires_admin_token(admin_client):
    resp = admin_client.post('/api/internal/share-artifacts/team-state/batch',
                             json={'source_snapshot_id': SNAPSHOT_ID, 'product_date': '2026-07-20'})
    assert resp.status_code in (401, 403)


def test_batch_endpoint_runs_and_summarizes(admin_client, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    resp = admin_client.post(
        '/api/internal/share-artifacts/team-state/batch',
        json={'source_snapshot_id': SNAPSHOT_ID, 'product_date': '2026-07-20'},
        headers={'X-Admin-Token': 'admin-secret'},
    )
    assert resp.status_code == 200
    body = resp.get_json()
    assert body['status'] == 'completed'
    assert body['attempted_count'] == len(TEAM_IDS)
    assert body['missing_count'] == 0
    assert (body['generated_count'] + body['reused_count']
            + body['refused_count'] + body['failed_count']) == body['attempted_count']
    assert len(body['results']) == len(TEAM_IDS)


def test_batch_endpoint_refuses_invalid_source_authority(admin_client, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch, unavailable_reason='snapshot_stale')
    resp = admin_client.post(
        '/api/internal/share-artifacts/team-state/batch',
        json={'source_snapshot_id': SNAPSHOT_ID, 'product_date': '2026-07-20'},
        headers={'X-Admin-Token': 'admin-secret'},
    )
    assert resp.status_code == 409
    body = resp.get_json()
    assert body['status'] == 'failed'
    assert body['reason'] == 'snapshot_stale'


def test_batch_endpoint_rejects_malformed_input(admin_client, monkeypatch):
    _install_snapshot(monkeypatch)
    resp = admin_client.post(
        '/api/internal/share-artifacts/team-state/batch',
        json={'source_snapshot_id': 'bad', 'product_date': '2026-07-20'},
        headers={'X-Admin-Token': 'admin-secret'},
    )
    assert resp.status_code == 400
    resp2 = admin_client.post(
        '/api/internal/share-artifacts/team-state/batch',
        json={'source_snapshot_id': SNAPSHOT_ID, 'product_date': 'not-a-date'},
        headers={'X-Admin-Token': 'admin-secret'},
    )
    assert resp2.status_code == 400
    resp3 = admin_client.post(
        '/api/internal/share-artifacts/team-state/batch',
        json={'source_snapshot_id': SNAPSHOT_ID, 'product_date': '2026-07-20', 'team_ids': 'nope'},
        headers={'X-Admin-Token': 'admin-secret'},
    )
    assert resp3.status_code == 400


# 23 — the response never leaks private payloads / internal objects / stack traces
def test_batch_endpoint_response_is_sanitized(admin_client, monkeypatch):
    _seed_teams()
    _install_snapshot(monkeypatch)
    resp = admin_client.post(
        '/api/internal/share-artifacts/team-state/batch',
        json={'source_snapshot_id': SNAPSHOT_ID, 'product_date': '2026-07-20'},
        headers={'X-Admin-Token': 'admin-secret'},
    )
    body = resp.get_json()
    allowed_top = {
        'source_snapshot_id', 'product_date', 'canonical_team_count', 'attempted_count',
        'generated_count', 'reused_count', 'refused_count', 'failed_count', 'missing_count',
        'missing_team_ids', 'is_complete', 'started_at', 'completed_at', 'duration_seconds',
        'results', 'status',
    }
    assert set(body).issubset(allowed_top)
    allowed_team = {
        'team_id', 'outcome', 'public_id', 'reason_code', 'failure_code',
        'audit_id', 'source_snapshot_id', 'product_date',
    }
    for row in body['results']:
        assert set(row).issubset(allowed_team)


# 21 — no PUBLIC route exposes the batch operation (only the internal admin one)
def test_no_public_route_exposes_batch(app):
    from app import create_app
    real_app = create_app('test')
    batch_rules = [str(r) for r in real_app.url_map.iter_rules() if 'batch' in str(r)]
    assert batch_rules == ['/api/internal/share-artifacts/team-state/batch']
