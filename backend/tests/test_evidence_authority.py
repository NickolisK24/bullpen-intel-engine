"""Tests for the canonical trusted-evidence authority (Share Cards SC-03B-01,
Workstream A).

Proves the single resolver owns the governed ``(subject, product_date)``
authority query — exact subject + date, trust/freshness filter, governed order,
no fallback — and that the two internal readers it centralizes still produce
equivalent behavior.
"""

from datetime import date, datetime

import pytest
from flask import Flask

from models.evidence_contract import EvidenceCitation, EvidenceObject
from models.sync_run import SyncRun
from services import internal_team_evidence
from services.evidence_authority import (
    EvidenceAuthorityError,
    cited_evidence_objects,
    resolve_current_pitcher_evidence,
    resolve_current_team_evidence,
    resolve_subject_current_evidence,
)
from tests.db_config import (
    configure_test_database,
    create_test_schema,
    drop_test_schema,
)
from utils.db import db


TEAM_ID = 321
PITCHER_ID = 9090
PRODUCT_DATE = date(2026, 7, 20)
OTHER_DATE = date(2026, 7, 19)


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


def _sync_run():
    row = SyncRun(job_name='sc03b_evidence_authority_test')
    db.session.add(row)
    db.session.flush()
    return row


def _evidence(
    sync_run,
    *,
    key,
    evidence_type,
    rule_id,
    subject_type='team',
    subject_id=TEAM_ID,
    product_date=PRODUCT_DATE,
    posture=EvidenceObject.POSTURE_INTERNAL_ONLY,
    recompute_status=EvidenceObject.RECOMPUTE_CURRENT,
):
    row = EvidenceObject(
        evidence_key=f'sc03b:{subject_type}:{key}',
        evidence_type=evidence_type,
        subject_type=subject_type,
        subject_id=str(subject_id),
        subject_key=f'{subject_type}:{subject_id}:{product_date.isoformat()}:{key}',
        product_date=product_date,
        claim_template_id=f'{rule_id}:test',
        rendered_claim=f'Stored {key} claim.',
        rule_id=rule_id,
        rule_version=1,
        rule_definition_hash='sc03b-test',
        typed_cited_inputs=[{'fixture': key}],
        computation_trace={'fixture': key},
        completeness_state=EvidenceObject.COMPLETENESS_COMPLETE,
        reason_codes=[],
        limitations=[],
        posture=posture,
        source='sc03b_test',
        sync_run_id=sync_run.id,
        recompute_status=recompute_status,
        recompute_reason_codes=[],
    )
    row.citations = [
        EvidenceCitation(
            source_family='sc03b_fixture',
            source_table='sc03b_rows',
            source_pk=f'fixture:{key}',
            source_field_names=['fixture'],
            citation_role='supporting_input',
            cited_values={'fixture': key},
            provenance={'source': 'sc03b_test'},
        )
    ]
    db.session.add(row)
    db.session.flush()
    return row


# 1 — returns trusted, date-aligned governed evidence for the exact subject/date.
def test_resolves_trusted_current_team_evidence(app):
    run = _sync_run()
    row = _evidence(run, key='workload', evidence_type='team_bullpen_outs_window',
                    rule_id='team_bullpen_outs_window')
    resolved = resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE)
    assert [r.id for r in resolved] == [row.id]


# 2 / 6 — never returns another date's rows, and never falls back to a different date.
def test_wrong_product_date_returns_nothing_no_fallback(app):
    run = _sync_run()
    _evidence(run, key='workload', evidence_type='team_bullpen_outs_window',
              rule_id='team_bullpen_outs_window', product_date=PRODUCT_DATE)
    # Asking for a different date must not silently serve the PRODUCT_DATE row.
    assert resolve_current_team_evidence(TEAM_ID, OTHER_DATE) == []
    # The exact date still resolves it (proves the row exists to fall back *from*).
    assert len(resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE)) == 1


# 3 — mismatched team / subject authority is not served.
def test_mismatched_subject_authority_returns_nothing(app):
    run = _sync_run()
    _evidence(run, key='workload', evidence_type='team_bullpen_outs_window',
              rule_id='team_bullpen_outs_window', subject_id=TEAM_ID)
    assert resolve_current_team_evidence(TEAM_ID + 1, PRODUCT_DATE) == []
    # A pitcher-subject query never returns a team row for the same numeric id.
    assert resolve_current_pitcher_evidence(TEAM_ID, PRODUCT_DATE) == []


# 4 — stale / non-current (untrusted) rows are excluded by the trust filter.
def test_stale_evidence_is_excluded(app):
    run = _sync_run()
    _evidence(run, key='stale', evidence_type='team_bullpen_outs_window',
              rule_id='team_bullpen_outs_window',
              recompute_status=EvidenceObject.RECOMPUTE_NEEDED)
    _evidence(run, key='superseded', evidence_type='team_consecutive_game_days',
              rule_id='team_consecutive_game_days',
              recompute_status=EvidenceObject.RECOMPUTE_SUPERSEDED)
    assert resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE) == []


# 4b — non-eligible posture rows are excluded by the governed posture filter.
def test_out_of_posture_evidence_is_excluded(app):
    run = _sync_run()
    _evidence(run, key='public', evidence_type='team_bullpen_outs_window',
              rule_id='team_bullpen_outs_window',
              posture=EvidenceObject.POSTURE_PUBLIC_CANDIDATE)
    assert resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE) == []


# 5 — governed order preserved: (evidence_type, rule_id, id) ascending.
def test_governed_order_is_preserved(app):
    run = _sync_run()
    # Insert deliberately out of governed order.
    _evidence(run, key='z', evidence_type='team_zzz', rule_id='z_rule')
    _evidence(run, key='a', evidence_type='team_aaa', rule_id='a_rule')
    _evidence(run, key='m', evidence_type='team_mmm', rule_id='m_rule')
    resolved = resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE)
    assert [r.evidence_type for r in resolved] == ['team_aaa', 'team_mmm', 'team_zzz']


# 7 — the migrated internal reader produces behavior equivalent to the resolver.
def test_internal_reader_matches_central_resolver(app):
    run = _sync_run()
    _evidence(run, key='a', evidence_type='team_aaa', rule_id='a_rule')
    _evidence(run, key='b', evidence_type='team_bbb', rule_id='b_rule')
    via_resolver = resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE)
    via_reader = internal_team_evidence._evidence_objects(TEAM_ID, PRODUCT_DATE, read=None)
    assert [r.id for r in via_reader] == [r.id for r in via_resolver]


# Fail-closed on malformed input rather than masquerading as "no evidence".
def test_malformed_input_fails_closed(app):
    run = _sync_run()
    _evidence(run, key='workload', evidence_type='team_bullpen_outs_window',
              rule_id='team_bullpen_outs_window')
    with pytest.raises(EvidenceAuthorityError):
        resolve_subject_current_evidence('team', TEAM_ID, '2026-07-20')  # str, not date
    with pytest.raises(EvidenceAuthorityError):
        resolve_subject_current_evidence('', TEAM_ID, PRODUCT_DATE)
    with pytest.raises(EvidenceAuthorityError):
        resolve_subject_current_evidence('team', None, PRODUCT_DATE)


# The cited-read merge is deterministic, deduped, and additive.
def test_cited_read_merge_is_deterministic_and_deduped(app):
    run = _sync_run()
    base = _evidence(run, key='base', evidence_type='team_bbb', rule_id='b_rule')
    cited_only = _evidence(run, key='cited', evidence_type='team_aaa', rule_id='a_rule',
                           posture=EvidenceObject.POSTURE_PUBLIC_CANDIDATE)  # not in base query

    class _Citation:
        def __init__(self, cid, obj):
            self.id = cid
            self.evidence_object = obj

    class _Component:
        def __init__(self, name, citations):
            self.component_name = name
            self.evidence_citations = citations

    class _Read:
        components = [
            _Component('c1', [_Citation(2, cited_only), _Citation(1, base)]),
            _Component('c0', [_Citation(3, cited_only)]),  # duplicate object
        ]

    read = _Read()
    # cited_evidence_objects: distinct, components-by-name then citations-by-id.
    cited = cited_evidence_objects(read)
    assert [r.id for r in cited] == [cited_only.id, base.id]
    # Merged into the base query result, re-sorted by governed key; deduped.
    resolved = resolve_current_team_evidence(TEAM_ID, PRODUCT_DATE, read=read)
    assert [r.id for r in resolved] == [cited_only.id, base.id]  # team_aaa before team_bbb
    assert cited_evidence_objects(None) == []
