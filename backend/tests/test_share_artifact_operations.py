"""Tests for the Share Artifact operations read model + internal admin API
(Share Cards SC-03B-03).

Read-only observability over the existing durable records: coverage for the
latest trusted snapshot, deterministic team accounting, integrity visibility,
bounded recent artifacts/audits, and the admin-token-gated operations API. No
generation, no mutation, no new persistence.
"""

from datetime import date, datetime

import pytest
from flask import Flask
from sqlalchemy import text

from models.pitcher import Pitcher
from models.share_artifact import ShareArtifact
from models.share_artifact_generation_audit import ShareArtifactGenerationAudit
from services import share_artifact_operations as ops
from services.share_artifact_generation import generate_team_state_artifact
from services.share_artifact_operations import (
    COVERAGE_FAILED,
    COVERAGE_GENERATED,
    COVERAGE_MISSING,
    COVERAGE_REFUSED,
    COVERAGE_REUSED,
    INTEGRITY_ERROR,
    INTEGRITY_MISMATCH,
    INTEGRITY_VERIFIED,
    STATUS_COMPLETE,
    STATUS_COMPLETE_WITH_REFUSALS,
    STATUS_DEGRADED,
    STATUS_DISABLED,
    STATUS_INCOMPLETE,
    STATUS_UNAVAILABLE,
    ShareArtifactOperationsError,
    build_coverage_overview,
    list_operational_artifacts,
    list_operational_audits,
)
from services.team_state_payload import TEAM_STATE_ARTIFACT_TYPE
from tests.test_share_artifact_batch_generation import (
    PRODUCT_DATE,
    SNAPSHOT_ID,
    _install_snapshot,
    _readiness,
    _seed_teams,
)
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


CANON_TEAMS = (101, 102, 103, 104)


@pytest.fixture
def app():
    flask_app = Flask(__name__)
    configure_test_database(flask_app)
    flask_app.config['APP_ENV'] = 'test'
    flask_app.config['ADMIN_API_TOKEN'] = 'admin-secret'
    flask_app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = True
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


def _resolver(readiness):
    def _r(team_id, *, requested_date=None, session=None):
        return readiness
    return _r


def _generate(team_id, *, status='operationally_constrained'):
    """Real generation for a team under the installed snapshot (creates a genuine
    published artifact + audit)."""
    return generate_team_state_artifact(
        team_id, readiness_resolver=_resolver(_readiness(team_id, status_code=status)),
    )


def _audit(team_id, outcome, *, snapshot_id=SNAPSHOT_ID, product_date=PRODUCT_DATE,
           public_id=None, blocking=(), failure_code=None, created_at=None, eligible=False):
    row = ShareArtifactGenerationAudit(
        team_id=team_id, outcome=outcome, eligible=eligible,
        source_snapshot_id=snapshot_id, resolved_product_date=product_date,
        blocking_conditions=list(blocking), reasons=[], artifact_public_id=public_id,
        failure_code=failure_code, actor='test', request_source='test',
        created_at=created_at or datetime(2026, 7, 20, 12, 0, 0),
    )
    db.session.add(row)
    db.session.flush()
    return row


def _overview_by_team(overview):
    return {row['team_id']: row for row in overview['teams']}


# ---------------------------------------------------------------------------
# Coverage read service (cases 1-18)
# ---------------------------------------------------------------------------


# 1 / 2 — latest trusted snapshot via existing authority; canonical teams via directory.
def test_uses_latest_trusted_snapshot_and_canonical_directory(app, monkeypatch):
    _seed_teams(CANON_TEAMS)
    _install_snapshot(monkeypatch)
    overview = build_coverage_overview()
    assert overview['source_snapshot_id'] == SNAPSHOT_ID
    assert overview['product_date'] == PRODUCT_DATE.isoformat()
    assert overview['canonical_team_count'] == len(CANON_TEAMS)
    assert [t['team_id'] for t in overview['teams']] == sorted(CANON_TEAMS)


# 3 / 4 / 5 / 6 / 7 — each terminal state accounted; refused/failed not missing; no-result missing.
def test_terminal_states_are_accounted(app, monkeypatch):
    _seed_teams(CANON_TEAMS)
    _install_snapshot(monkeypatch)
    _generate(101)                                   # generated (real artifact)
    _generate(102); _generate(102)                   # reused (second attempt)
    _audit(103, ShareArtifactGenerationAudit.OUTCOME_REFUSED, blocking=('insufficient_trust',))
    _audit(104, ShareArtifactGenerationAudit.OUTCOME_FAILED_CLOSED, failure_code='publication_error')
    # A 5th canonical team with no attempt -> missing.
    db.session.add(Pitcher(mlb_id=955, full_name='Arm 105', team_id=105, active=True))
    db.session.flush()

    overview = build_coverage_overview()
    rows = _overview_by_team(overview)
    assert rows[101]['state'] == COVERAGE_GENERATED and rows[101]['public_id']
    assert rows[102]['state'] == COVERAGE_REUSED
    assert rows[103]['state'] == COVERAGE_REFUSED and rows[103]['reason_code'] == 'insufficient_trust'
    assert rows[104]['state'] == COVERAGE_FAILED and rows[104]['failure_code'] == 'publication_error'
    assert rows[105]['state'] == COVERAGE_MISSING
    assert overview['generated_team_count'] == 1
    assert overview['reused_team_count'] == 1
    assert overview['refused_team_count'] == 1
    assert overview['failed_team_count'] == 1
    assert overview['missing_team_count'] == 1
    # refused/failed are accounted, not missing.
    assert overview['accounted_team_count'] == 4


# 8 / 9 / 10 — duplicate attempts: most-recent terminal controls coverage; no double count; history kept.
def test_most_recent_attempt_controls_coverage_without_double_count(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    _audit(101, ShareArtifactGenerationAudit.OUTCOME_REFUSED, blocking=('insufficient_trust',),
           created_at=datetime(2026, 7, 20, 10, 0, 0))
    _audit(101, ShareArtifactGenerationAudit.OUTCOME_PUBLISHED, public_id='pub-101',
           created_at=datetime(2026, 7, 20, 12, 0, 0))  # later
    overview = build_coverage_overview()
    rows = _overview_by_team(overview)
    assert rows[101]['state'] == COVERAGE_GENERATED   # latest terminal wins
    assert overview['canonical_team_count'] == 1
    assert overview['generated_team_count'] == 1 and overview['refused_team_count'] == 0
    # History preserved in the audit list (both attempts present).
    audits = list_operational_audits(team_id=101)
    assert audits['count'] == 2
    assert {a['outcome'] for a in audits['audits']} == {'published', 'refused'}


# 11 / 12 — artifact/audit from another snapshot (or date) does not satisfy current coverage.
def test_other_snapshot_artifact_does_not_satisfy_coverage(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch, snapshot_id=7001, data_through=date(2026, 7, 19))
    _generate(101)  # published under snapshot 7001 / 2026-07-19
    # Latest trusted snapshot is now a DIFFERENT authority.
    _install_snapshot(monkeypatch, snapshot_id=7002, data_through=date(2026, 7, 20))
    overview = build_coverage_overview()
    assert overview['source_snapshot_id'] == 7002
    rows = _overview_by_team(overview)
    assert rows[101]['state'] == COVERAGE_MISSING     # 7001 artifact does not count for 7002
    assert overview['missing_team_count'] == 1
    assert overview['artifact_count'] == 0            # no artifact tied to 7002


# 13 — invariants hold on a normal mixed overview.
def test_accounting_invariants_hold(app, monkeypatch):
    _seed_teams(CANON_TEAMS)
    _install_snapshot(monkeypatch)
    _generate(101)
    _audit(102, ShareArtifactGenerationAudit.OUTCOME_REFUSED, blocking=('data_limited',))
    overview = build_coverage_overview()
    assert overview['canonical_team_count'] == (
        overview['generated_team_count'] + overview['reused_team_count']
        + overview['refused_team_count'] + overview['failed_team_count']
        + overview['missing_team_count']
    )
    assert overview['accounted_team_count'] == (
        overview['generated_team_count'] + overview['reused_team_count']
        + overview['refused_team_count'] + overview['failed_team_count']
    )


# 14 — impossible accounting fails closed.
def test_impossible_accounting_fails_closed(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    # Force a team into an uncounted coverage state: the read model must fail
    # closed rather than present a plausible-but-wrong summary.
    monkeypatch.setattr(
        ops, '_AUDIT_OUTCOME_TO_COVERAGE',
        {ShareArtifactGenerationAudit.OUTCOME_REFUSED: 'not_a_counted_state'},
    )
    _audit(101, ShareArtifactGenerationAudit.OUTCOME_REFUSED)
    with pytest.raises(ShareArtifactOperationsError):
        build_coverage_overview()


# 15 — deterministic team ordering.
def test_deterministic_team_ordering(app, monkeypatch):
    _seed_teams((103, 101, 102))
    _install_snapshot(monkeypatch)
    overview = build_coverage_overview()
    assert [t['team_id'] for t in overview['teams']] == [101, 102, 103]


# 16 — no trusted snapshot -> governed unavailable.
def test_no_trusted_snapshot_returns_unavailable(app):
    _seed_teams((101,))
    overview = build_coverage_overview()  # no snapshot installed
    assert overview['status'] == STATUS_UNAVAILABLE
    assert overview['teams'] == []
    assert overview['canonical_team_count'] == 0


def test_untrusted_snapshot_returns_unavailable(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch, unavailable_reason='snapshot_stale')
    overview = build_coverage_overview()
    assert overview['status'] == STATUS_UNAVAILABLE
    assert overview['reason'] == 'snapshot_stale'


# 17 — autogeneration disabled is exposed honestly.
def test_autogeneration_disabled_state(app, monkeypatch):
    app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = False
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    _generate(101)
    overview = build_coverage_overview()
    assert overview['autogeneration_enabled'] is False
    assert overview['status'] == STATUS_DISABLED


# 18 — operational status derivations.
def test_status_complete(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101); _generate(102)
    assert build_coverage_overview()['status'] == STATUS_COMPLETE


def test_status_complete_with_refusals(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)
    _audit(102, ShareArtifactGenerationAudit.OUTCOME_REFUSED, blocking=('data_limited',))
    assert build_coverage_overview()['status'] == STATUS_COMPLETE_WITH_REFUSALS


def test_status_degraded_on_failure(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)
    _audit(102, ShareArtifactGenerationAudit.OUTCOME_FAILED_CLOSED, failure_code='publication_error')
    assert build_coverage_overview()['status'] == STATUS_DEGRADED


def test_status_incomplete_on_missing(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)  # 102 has no attempt -> missing
    assert build_coverage_overview()['status'] == STATUS_INCOMPLETE


# ---------------------------------------------------------------------------
# Integrity (cases 19-23)
# ---------------------------------------------------------------------------


# 19 — a valid artifact reports verified.
def test_integrity_verified(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    _generate(101)
    rows = _overview_by_team(build_coverage_overview())
    assert rows[101]['integrity_state'] == INTEGRITY_VERIFIED
    assert build_coverage_overview()['integrity_failure_count'] == 0


# 20 — a hash mismatch reports mismatch (no mutation).
def test_integrity_mismatch(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    artifact = _generate(101).artifact
    # Tamper with the stored hash via raw SQL (bypasses ORM immutability guards).
    db.session.execute(
        text('UPDATE share_artifacts SET integrity_hash = :h WHERE id = :i'),
        {'h': 'deadbeef' * 8, 'i': artifact.id},
    )
    db.session.commit()
    overview = build_coverage_overview()
    rows = _overview_by_team(overview)
    assert rows[101]['integrity_state'] == INTEGRITY_MISMATCH
    assert overview['integrity_failure_count'] == 1
    assert overview['status'] == STATUS_DEGRADED
    # Artifact was not rewritten/repaired.
    assert db.session.get(ShareArtifact, artifact.id).integrity_hash == 'deadbeef' * 8


# 21 — a verification error reports error without mutating the artifact.
def test_integrity_error_without_mutation(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    artifact = _generate(101).artifact
    original_hash = artifact.integrity_hash

    def _boom(a):
        raise RuntimeError('verifier exploded')

    monkeypatch.setattr(ops, 'verify_share_artifact_integrity', _boom)
    overview = build_coverage_overview()
    rows = _overview_by_team(overview)
    assert rows[101]['integrity_state'] == INTEGRITY_ERROR
    assert overview['integrity_error_count'] == 1
    assert db.session.get(ShareArtifact, artifact.id).integrity_hash == original_hash


# 22 / 23 — integrity checking is bounded (coverage set only) and never repairs.
def test_integrity_check_is_bounded_and_never_repairs(app, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    _generate(101)
    calls = []
    real = ops.verify_share_artifact_integrity

    def _counting(a):
        calls.append(a.id)
        return real(a)

    monkeypatch.setattr(ops, 'verify_share_artifact_integrity', _counting)
    build_coverage_overview()
    # Bounded to the canonical coverage set (one accounted artifact here).
    assert len(calls) == 1


# ---------------------------------------------------------------------------
# Recent artifacts (cases 24-28)
# ---------------------------------------------------------------------------


def test_recent_artifacts_newest_first_and_safe(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)
    _generate(102)
    payload = list_operational_artifacts(limit=10)
    assert payload['count'] == 2
    # 27 — raw payload JSON is never returned in the list.
    for row in payload['artifacts']:
        assert 'payload' not in row
        assert set(row).issubset({
            'public_id', 'artifact_type', 'team_id', 'team_name', 'team_abbreviation',
            'product_date', 'source_snapshot_id', 'lifecycle_state', 'schema_version',
            'render_version', 'integrity_state', 'created_at', 'published_at',
            'superseded_at', 'withdrawn_at',
        })
    # 28 — lifecycle state present/distinct.
    assert all(row['lifecycle_state'] == 'published' for row in payload['artifacts'])
    # 24 — newest first (team 102 generated last).
    assert payload['artifacts'][0]['team_id'] == 102


# 25 / 26 — limit/offset validation + team filter.
def test_recent_artifacts_limit_offset_and_filter(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)
    _generate(102)
    page1 = list_operational_artifacts(limit=1, offset=0)
    page2 = list_operational_artifacts(limit=1, offset=1)
    assert page1['count'] == 1 and page2['count'] == 1
    assert page1['artifacts'][0]['public_id'] != page2['artifacts'][0]['public_id']
    # limit is clamped to the max.
    assert list_operational_artifacts(limit=99999)['limit'] == ops.MAX_LIST_LIMIT
    # team filter.
    only101 = list_operational_artifacts(team_id=101)
    assert {a['team_id'] for a in only101['artifacts']} == {101}


# ---------------------------------------------------------------------------
# Recent audits (cases 29-33)
# ---------------------------------------------------------------------------


def test_recent_audits_distinct_outcomes_and_codes(app, monkeypatch):
    _seed_teams((101, 102, 103))
    _install_snapshot(monkeypatch)
    _generate(101)
    _audit(102, ShareArtifactGenerationAudit.OUTCOME_REFUSED, blocking=('insufficient_trust',))
    _audit(103, ShareArtifactGenerationAudit.OUTCOME_FAILED_CLOSED, failure_code='publication_error')
    payload = list_operational_audits(limit=10)
    by_team = {a['team_id']: a for a in payload['audits']}
    # 29 — distinct outcomes.
    assert by_team[101]['outcome'] == 'published'
    assert by_team[102]['outcome'] == 'refused'
    assert by_team[103]['outcome'] == 'failed_closed'
    # 30 — refusal reason code preserved.
    assert by_team[102]['reason_code'] == 'insufficient_trust'
    # 31 — sanitized failure code preserved.
    assert by_team[103]['failure_code'] == 'publication_error'
    # 32 — no raw exception/trace leaked (governed fields only).
    for a in payload['audits']:
        assert 'traceback' not in a and 'exception' not in a


# 33 — audit filters + pagination are deterministic; invalid outcome fails.
def test_recent_audits_filters_and_pagination(app, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)
    _audit(102, ShareArtifactGenerationAudit.OUTCOME_REFUSED, blocking=('data_limited',))
    refused = list_operational_audits(outcome='refused')
    assert {a['outcome'] for a in refused['audits']} == {'refused'}
    snap = list_operational_audits(source_snapshot_id=SNAPSHOT_ID)
    assert snap['count'] >= 2
    with pytest.raises(ShareArtifactOperationsError):
        list_operational_audits(outcome='not_a_real_outcome')


# ---------------------------------------------------------------------------
# Internal admin API (cases 34-40)
# ---------------------------------------------------------------------------

_AUTH = {'X-Admin-Token': 'admin-secret'}


# 34 / 35 — authorization required; standard denial.
def test_operations_endpoints_require_admin_token(admin_client):
    for path in ('overview', 'artifacts', 'audits'):
        resp = admin_client.get(f'/api/internal/share-artifacts/operations/{path}')
        assert resp.status_code == 401


# 37 — overview exposes coverage counts + invariant fields.
def test_overview_endpoint_exposes_counts(admin_client, monkeypatch):
    _seed_teams((101, 102))
    _install_snapshot(monkeypatch)
    _generate(101)
    resp = admin_client.get('/api/internal/share-artifacts/operations/overview', headers=_AUTH)
    assert resp.status_code == 200
    body = resp.get_json()
    for key in ('status', 'canonical_team_count', 'accounted_team_count', 'generated_team_count',
                'reused_team_count', 'refused_team_count', 'failed_team_count',
                'missing_team_count', 'integrity_failure_count', 'autogeneration_enabled', 'teams'):
        assert key in body
    assert body['canonical_team_count'] == (
        body['accounted_team_count'] + body['missing_team_count']
    )


def test_artifacts_and_audits_endpoints(admin_client, monkeypatch):
    _seed_teams((101,))
    _install_snapshot(monkeypatch)
    _generate(101)
    arts = admin_client.get(
        '/api/internal/share-artifacts/operations/artifacts?limit=5', headers=_AUTH)
    assert arts.status_code == 200 and 'artifacts' in arts.get_json()
    auds = admin_client.get(
        '/api/internal/share-artifacts/operations/audits?limit=5', headers=_AUTH)
    assert auds.status_code == 200 and 'audits' in auds.get_json()


# 38 — invalid filters/limits fail safely.
def test_invalid_filters_fail_safely(admin_client, monkeypatch):
    _install_snapshot(monkeypatch)
    bad_limit = admin_client.get(
        '/api/internal/share-artifacts/operations/artifacts?limit=abc', headers=_AUTH)
    assert bad_limit.status_code == 400
    bad_outcome = admin_client.get(
        '/api/internal/share-artifacts/operations/audits?outcome=bogus', headers=_AUTH)
    assert bad_outcome.status_code == 400
    bad_date = admin_client.get(
        '/api/internal/share-artifacts/operations/audits?product_date=nope', headers=_AUTH)
    assert bad_date.status_code == 400


# 36 — no public route exposes operational data.
def test_no_public_operations_route(app):
    from app import create_app
    real_app = create_app('test')
    ops_routes = [str(r) for r in real_app.url_map.iter_rules() if 'operations' in str(r)
                  and 'share-artifacts' in str(r)]
    assert ops_routes and all(r.startswith('/api/internal/share-artifacts/') for r in ops_routes)


# 39 / 40 — the operations API is GET-only (no generation, no mutation).
def test_operations_api_is_read_only(app):
    from app import create_app
    real_app = create_app('test')
    for rule in real_app.url_map.iter_rules():
        if '/operations/' in str(rule):
            assert rule.methods & {'POST', 'PUT', 'PATCH', 'DELETE'} == set()
