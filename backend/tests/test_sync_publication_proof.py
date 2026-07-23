from datetime import date, datetime
from types import SimpleNamespace

from services.sync_publication_proof import (
    PROOF_FAILED,
    PROOF_NO_CANDIDATE_EXPECTED,
    PROOF_VERIFIED,
    build_candidate_publication_proof,
)


def _snapshot(
    snapshot_id=12,
    *,
    status='ready',
    is_published=True,
    published_at=None,
    sync_run_id=7,
):
    return SimpleNamespace(
        id=snapshot_id,
        status=status,
        is_published=is_published,
        published_at=published_at or datetime(2026, 7, 23, 10, 15),
        sync_run_id=sync_run_id,
        data_through=date(2026, 7, 22),
        availability_reference_date=date(2026, 7, 23),
    )


def _proof(candidate, served=None, *, required=True, reason=None):
    served = candidate if served is None else served
    return build_candidate_publication_proof(
        getattr(candidate, 'id', None),
        candidate_required=required,
        snapshot_loader=lambda snapshot_id: candidate,
        served_snapshot_loader=lambda: served,
        availability_reason=lambda snapshot: reason,
    )


def test_candidate_is_verified_only_when_same_snapshot_is_serving():
    candidate = _snapshot()

    proof = _proof(candidate)

    assert proof['status'] == PROOF_VERIFIED
    assert proof['verified'] is True
    assert proof['candidate_snapshot_id'] == candidate.id
    assert proof['served_snapshot_id'] == candidate.id
    assert proof['candidate_sync_run_id'] == candidate.sync_run_id
    assert proof['reason_codes'] == []


def test_older_healthy_served_snapshot_does_not_hide_withheld_candidate():
    candidate = _snapshot(status='pending', is_published=False)
    candidate.published_at = None
    served = _snapshot(snapshot_id=11)

    proof = _proof(
        candidate,
        served,
        reason='dashboard_snapshot_appearance_ledger_incomplete',
    )

    assert proof['status'] == PROOF_FAILED
    assert proof['verified'] is False
    assert proof['candidate_snapshot_id'] == 12
    assert proof['served_snapshot_id'] == 11
    assert 'candidate_snapshot_not_ready' in proof['reason_codes']
    assert 'candidate_snapshot_not_published' in proof['reason_codes']
    assert 'candidate_snapshot_published_at_missing' in proof['reason_codes']
    assert 'dashboard_snapshot_appearance_ledger_incomplete' in proof['reason_codes']
    assert 'candidate_not_selected_for_serving' in proof['reason_codes']


def test_missing_required_candidate_fails_closed():
    proof = build_candidate_publication_proof(
        None,
        candidate_required=True,
        snapshot_loader=lambda snapshot_id: None,
        served_snapshot_loader=lambda: _snapshot(snapshot_id=11),
        availability_reason=lambda snapshot: None,
    )

    assert proof['status'] == PROOF_FAILED
    assert proof['verified'] is False
    assert proof['reason_codes'] == ['candidate_snapshot_missing']


def test_no_change_postgame_pass_may_keep_prior_trusted_snapshot():
    served = _snapshot(snapshot_id=11)
    proof = build_candidate_publication_proof(
        None,
        candidate_required=False,
        snapshot_loader=lambda snapshot_id: None,
        served_snapshot_loader=lambda: served,
        availability_reason=lambda snapshot: None,
    )

    assert proof['status'] == PROOF_NO_CANDIDATE_EXPECTED
    assert proof['verified'] is True
    assert proof['candidate_snapshot_id'] is None
    assert proof['served_snapshot_id'] == 11


def test_candidate_availability_failure_is_not_verified_even_when_selected():
    candidate = _snapshot()

    proof = _proof(
        candidate,
        reason='dashboard_snapshot_data_through_mismatch',
    )

    assert proof['status'] == PROOF_FAILED
    assert proof['verified'] is False
    assert proof['reason_codes'] == ['dashboard_snapshot_data_through_mismatch']
