"""Unit tests for the publication-critical vs best-effort classification and the
publication-critical completeness result (daily-sync trust contract)."""

from services import publication_criticality as pc
from services.roster_status import (
    STATUS_ACTIVE,
    STATUS_DFA,
    STATUS_IL_10,
    STATUS_MINORS,
    STATUS_OPTIONED,
    STATUS_UNKNOWN,
)


# --- criticality classification ----------------------------------------------


def test_active_mlb_roster_is_publication_critical():
    assert pc.criticality_for_roster_status(STATUS_ACTIVE) == pc.CRITICALITY_PUBLICATION_CRITICAL


def test_off_active_roster_statuses_are_best_effort():
    for status in (STATUS_IL_10, STATUS_OPTIONED, STATUS_MINORS, STATUS_DFA):
        assert pc.criticality_for_roster_status(status) == pc.CRITICALITY_BEST_EFFORT


def test_missing_or_unrecognized_roster_status_fails_closed_to_unknown():
    assert pc.criticality_for_roster_status(None) == pc.CRITICALITY_UNKNOWN
    assert pc.criticality_for_roster_status(STATUS_UNKNOWN) == pc.CRITICALITY_UNKNOWN
    assert pc.criticality_for_roster_status('NOT_A_REAL_CODE') == pc.CRITICALITY_UNKNOWN


# --- completeness result ------------------------------------------------------


def test_best_effort_only_shortfall_is_complete():
    result = pc.build_publication_critical_result(
        critical_total=400, critical_completed=400, critical_failed=0,
        critical_unresolved=0, unknown_criticality=0,
        best_effort_total=389, best_effort_completed=155, best_effort_deferred=234,
        non_gamelog_critical_failed=0, authority_available=True,
    )
    assert result['status'] == pc.PUBLICATION_CRITICAL_COMPLETE
    assert result['complete'] is True
    assert result['best_effort_deferred'] == 234
    assert result['publication_critical_failed'] == 0


def test_critical_failure_is_incomplete():
    result = pc.build_publication_critical_result(
        critical_total=400, critical_completed=398, critical_failed=2,
        critical_unresolved=0, unknown_criticality=0,
        best_effort_total=100, best_effort_completed=100, best_effort_deferred=0,
        authority_available=True,
    )
    assert result['status'] == pc.PUBLICATION_CRITICAL_INCOMPLETE
    assert result['complete'] is False
    assert pc.REASON_CRITICAL_FAILED in result['reason_codes']


def test_unknown_criticality_fails_closed():
    result = pc.build_publication_critical_result(
        critical_total=0, critical_failed=0, critical_unresolved=0,
        unknown_criticality=5, best_effort_total=0, best_effort_deferred=0,
        authority_available=True,
    )
    assert result['complete'] is False
    assert pc.REASON_UNKNOWN_CRITICALITY in result['reason_codes']


def test_non_gamelog_failure_is_publication_critical():
    result = pc.build_publication_critical_result(
        critical_total=400, critical_failed=0, critical_unresolved=0,
        unknown_criticality=0, best_effort_total=100, best_effort_deferred=10,
        non_gamelog_critical_failed=1, authority_available=True,
    )
    assert result['complete'] is False
    assert result['publication_critical_failed'] == 1
    assert pc.REASON_NON_GAMELOG_FAILURE in result['reason_codes']


def test_unresolved_critical_work_is_incomplete():
    result = pc.build_publication_critical_result(
        critical_total=400, critical_failed=0, critical_unresolved=3,
        unknown_criticality=0, best_effort_total=0, authority_available=True,
    )
    assert result['complete'] is False
    assert pc.REASON_CRITICAL_UNRESOLVED in result['reason_codes']


def test_authority_unavailable_never_completes():
    result = pc.build_publication_critical_result(
        critical_total=0, critical_failed=0, critical_unresolved=0,
        unknown_criticality=0, best_effort_total=0, authority_available=False,
    )
    assert result['status'] == pc.PUBLICATION_CRITICAL_UNAVAILABLE
    assert result['complete'] is False
    assert pc.REASON_AUTHORITY_UNAVAILABLE in result['reason_codes']
