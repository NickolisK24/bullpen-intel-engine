"""Official pitching-line repair CLOSEOUT verification (2026) — strictly read-only.

The approved 675-action repair committed. This module proves that after the fact, from the
durable record and from live evidence, and writes nothing.

It exists because the apply run's own post-commit wrapper returned a FALSE NEGATIVE. Every
underlying check passed — completeness, local-only aggregation, and official validation — but
the wrapper required every boolean reconciliation to be true in BOTH audit modes, and the
canonical aggregation defines ``all_mandatory_metrics_match`` as
``include_official_validation and ...``. That reconciliation is therefore false by design in
local-only mode: it is an official-validation reconciliation local-only cannot evaluate, not a
local reconciliation that failed. The wrapper turned that intentional non-applicability into a
failure and reported the committed repair as unverified.

The historical apply artifact is NOT rewritten. It accurately records the decision the workflow
made with the vocabulary it had, and it stays immutable. This is a separate, later, read-only
verification that reaches its own conclusion from current evidence.

This module never mutates anything. It does not import or call the apply entrypoint, it opens
no write transaction, it takes no advisory lock, and it creates, updates, or deletes no row.
Re-running the apply is forbidden and unnecessary: the ledger already records exactly one
completed execution for the approved fingerprint, and the apply path refuses a second one.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

from models.game_log import GameLog
from models.official_pitching_line_repair_execution import (
    OfficialPitchingLineRepairExecution as RepairExecution,
)
from models.pitcher import Pitcher
from services import official_pitching_line_completeness_2026 as completeness
from services import official_pitching_line_repair_apply_2026 as apply_service
from services import season_bullpen_aggregation_2026 as aggregation
from services.mlb_api import mlb_client
from utils.db import db


CAPABILITY = 'official_pitching_line_repair_closeout_2026_v1'
CLOSEOUT_CONTRACT_VERSION = 'official_pitching_line_repair_closeout_2026.v1'
MODE_CLOSEOUT = 'closeout_verification'

# Distinct from the apply confirmation on purpose: a read-only closeout must never be
# confirmable with the phrase that authorises a write, and vice versa.
CONFIRMATION_PHRASE = 'VERIFY-2026-PITCHING-LINE-REPAIR-CLOSEOUT'

RESULT_PASS = 'pass'
RESULT_FAIL = 'fail'
RESULT_INCONCLUSIVE = 'inconclusive'
EXIT_BY_RESULT = {RESULT_PASS: 0, RESULT_FAIL: 1, RESULT_INCONCLUSIVE: 2}

DECISION_READY_FOR_REVIEW = 'foundation_3a_repair_closeout_ready_for_review'
DECISION_LEDGER_NOT_PROVEN = 'execution_ledger_does_not_prove_the_approved_repair'
DECISION_AMENDMENT_NOT_PROVEN = 'reviewed_amendment_row_does_not_match_the_approved_result'
DECISION_POST_COMMIT_FAILED = 'post_commit_checks_failed'
DECISION_EVIDENCE_UNAVAILABLE = 'required_read_only_evidence_could_not_be_observed'

# The single reviewed amendment line, restated here so a change elsewhere cannot silently
# redefine what closeout accepts as proof.
EXPECTED_EXECUTION_LEDGER_ID = 1
EXPECTED_AMENDMENT = {
    'local_game_log_id': 43765,
    'stable_key': '825058:805299:109',
    'mlb_game_pk': 825058,
    'official_mlb_person_id': 805299,
    'appearance_team_id': 109,
    'field': 'hits_allowed',
    'value_before': 1,
    'value_after': 0,
    'stat_correction_count_after': 1,
}

# Every downstream gate stays blocked. A passing closeout makes Foundation 3A ELIGIBLE for a
# separate gate decision; it never opens a gate itself.
GATE_BLOCKED = apply_service.GATE_BLOCKED
DOWNSTREAM_GATES = apply_service.DOWNSTREAM_GATES

CLOSEOUT_CHECKS = (
    'execution_ledger_proves_the_approved_repair',
    'reviewed_amendment_row_matches_the_approved_result',
    'official_pitching_line_completeness_2026',
    'canonical_season_bullpen_aggregation_local_only',
    'canonical_season_bullpen_aggregation_official_validation',
)


def _executed(passed, **payload) -> dict:
    return {'executed': True, 'execution_state': apply_service.CHECK_EXECUTED,
            'passed': bool(passed), **payload}


def _not_executed(exc) -> dict:
    """A check that never produced a result. An absence, not a failure verdict."""
    return {'executed': False, 'execution_state': apply_service.CHECK_NOT_EXECUTED,
            'passed': False, 'checks': {}, 'error_type': type(exc).__name__}


# ── 1. The durable execution record ───────────────────────────────────────────
def verify_execution_ledger(session, *, contract=None, approved_fingerprint=None) -> dict:
    """Read-only proof that exactly one completed execution applied the approved manifest."""
    contract = dict(contract or apply_service.APPROVED_EXECUTION_CONTRACT)
    approved_fingerprint = (
        approved_fingerprint
        or apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026)
    counts = contract['action_counts']

    rows = (session.query(RepairExecution)
            .filter(RepairExecution.approved_manifest_fingerprint == approved_fingerprint)
            .order_by(RepairExecution.id)
            .all())
    completed = [row for row in rows
                 if row.status == RepairExecution.STATUS_COMPLETED]

    checks = {
        'exactly_one_ledger_row_for_the_approved_fingerprint': len(rows) == 1,
        'exactly_one_completed_ledger_row': len(completed) == 1,
    }
    observed: Dict[str, object] = {
        'ledger_row_count': len(rows),
        'completed_row_count': len(completed),
        'expected_execution_ledger_id': EXPECTED_EXECUTION_LEDGER_ID,
        'observed_execution_ledger_id': None,
    }
    if len(completed) != 1:
        checks.update({
            'status_is_completed': False,
            'approved_fingerprint_matches': False,
            'regenerated_fingerprint_matches_the_approved_fingerprint': False,
            'season_matches': False,
            'as_of_date_matches': False,
            'accepted_baseline_version_matches': False,
            'amendment_id_matches': False,
            'identity_action_count_matches': False,
            'insert_action_count_matches': False,
            'update_action_count_matches': False,
            'total_action_count_matches': False,
            'committed_at_is_populated': False,
        })
        return _executed(False, checks=checks, observed=observed)

    row = completed[0]
    observed['observed_execution_ledger_id'] = int(row.id)
    # The ledger id is a surrogate key, not a governed contract value. The expected value is
    # recorded and the observed value is reported authoritatively; what PROVES the repair is
    # the fingerprint pair, the status, and the action counts below.
    observed['execution_ledger_id_matches_expected'] = (
        int(row.id) == EXPECTED_EXECUTION_LEDGER_ID)
    observed.update({
        'status': row.status,
        'season': row.season,
        'as_of_date': row.as_of_date.isoformat() if row.as_of_date else None,
        'accepted_baseline_version': row.accepted_baseline_version,
        'amendment_id': row.amendment_id,
        'identity_action_count': row.identity_action_count,
        'insert_action_count': row.insert_action_count,
        'update_action_count': row.update_action_count,
        'total_action_count': row.total_action_count,
        'committed_at': row.committed_at.isoformat() if row.committed_at else None,
        'capability': row.capability,
    })
    checks.update({
        'status_is_completed': row.status == RepairExecution.STATUS_COMPLETED,
        'approved_fingerprint_matches':
            row.approved_manifest_fingerprint == approved_fingerprint,
        'regenerated_fingerprint_matches_the_approved_fingerprint':
            row.regenerated_manifest_fingerprint == approved_fingerprint,
        'season_matches': int(row.season) == int(contract['season']),
        'as_of_date_matches':
            row.as_of_date == date.fromisoformat(contract['as_of_date']),
        'accepted_baseline_version_matches':
            row.accepted_baseline_version == contract['accepted_defect_baseline_version'],
        'amendment_id_matches': row.amendment_id == contract['amendment_id'],
        'identity_action_count_matches':
            row.identity_action_count == counts[apply_service.planner.ACTION_IDENTITY_CREATE],
        'insert_action_count_matches':
            row.insert_action_count == counts[apply_service.planner.ACTION_GAME_LOG_INSERT],
        'update_action_count_matches':
            row.update_action_count == counts[apply_service.planner.ACTION_GAME_LOG_UPDATE],
        'total_action_count_matches':
            row.total_action_count == contract['total_action_count'],
        'committed_at_is_populated': row.committed_at is not None,
    })
    return _executed(all(checks.values()), checks=checks, observed=observed)


# ── 2. The reviewed Brandyn Garcia line, as committed ─────────────────────────
def verify_reviewed_amendment_row(session) -> dict:
    """Read-only proof that the one reviewed amendment line holds its corrected state."""
    expected = EXPECTED_AMENDMENT
    log = (session.query(GameLog)
           .filter(GameLog.id == expected['local_game_log_id'])
           .one_or_none())
    observed: Dict[str, object] = {
        'local_game_log_id': expected['local_game_log_id'],
        'stable_key': expected['stable_key'],
        'row_exists': log is not None,
    }
    if log is None:
        return _executed(False, checks={'reviewed_amendment_row_exists': False},
                         observed=observed)

    pitcher = (session.query(Pitcher)
               .filter(Pitcher.id == log.pitcher_id).one_or_none())
    observed.update({
        'mlb_game_pk': log.mlb_game_pk,
        'official_mlb_person_id': int(pitcher.mlb_id) if pitcher is not None else None,
        'appearance_team_id': log.appearance_team_id,
        'hits_allowed': log.hits_allowed,
        'stat_correction_count': log.stat_correction_count,
        'last_stat_correction_source': log.last_stat_correction_source,
        'last_stat_correction_at_is_populated': log.last_stat_correction_at is not None,
        'last_stat_correction_sync_run_id': log.last_stat_correction_sync_run_id,
    })
    checks = {
        'reviewed_amendment_row_exists': True,
        'mlb_game_pk_matches': int(log.mlb_game_pk) == expected['mlb_game_pk'],
        'official_person_matches':
            pitcher is not None
            and int(pitcher.mlb_id) == expected['official_mlb_person_id'],
        'appearance_team_matches':
            log.appearance_team_id == expected['appearance_team_id'],
        'hits_allowed_is_the_corrected_value':
            log.hits_allowed == expected['value_after'],
        'stat_correction_count_is_exactly_one':
            int(log.stat_correction_count or 0)
            == expected['stat_correction_count_after'],
        'correction_source_is_the_governed_repair':
            log.last_stat_correction_source == apply_service.CORRECTION_SOURCE,
        'correction_timestamp_is_populated': log.last_stat_correction_at is not None,
        'governed_operation_id_is_populated':
            log.last_stat_correction_sync_run_id is not None,
    }
    return _executed(all(checks.values()), checks=checks, observed=observed)


# ── 3-5. Live read-only evidence ──────────────────────────────────────────────
def _completeness_check(*, season, as_of_date, generated_at, client, session) -> dict:
    diagnostic = completeness.run_diagnostic(
        season=season, as_of_date=as_of_date, detail_limit=0, generated_at=generated_at,
        client=client, session=session)
    checks = {
        'result_is_pass': diagnostic.get('result') == completeness.RESULT_PASS,
        'exit_code_is_zero': diagnostic.get('exit_code') == 0,
        'zero_missing_lines': diagnostic.get('missing_local_line_count') == 0,
        'zero_stat_mismatches': (diagnostic.get('stat_mismatch_count') or 0) == 0,
        'zero_role_mismatches': (diagnostic.get('role_mismatch_count') or 0) == 0,
        'zero_extra_local_lines': diagnostic.get('extra_local_line_count') == 0,
        'zero_duplicate_local_lines': diagnostic.get('duplicate_local_line_count') == 0,
        'zero_appearance_team_mismatches':
            diagnostic.get('appearance_team_mismatch_count') == 0,
    }
    return _executed(
        all(checks.values()), result=diagnostic.get('result'),
        exit_code=diagnostic.get('exit_code'), checks=checks,
        observed={
            'missing_local_line_count': diagnostic.get('missing_local_line_count'),
            'stat_mismatch_count': diagnostic.get('stat_mismatch_count'),
            'role_mismatch_count': diagnostic.get('role_mismatch_count'),
            'extra_local_line_count': diagnostic.get('extra_local_line_count'),
            'duplicate_local_line_count': diagnostic.get('duplicate_local_line_count'),
            'appearance_team_mismatch_count': diagnostic.get(
                'appearance_team_mismatch_count'),
        })


def _aggregation_check(*, season, as_of_date, official, generated_at, client,
                       session) -> dict:
    """One aggregation mode, judged with ITS OWN reconciliation vocabulary."""
    audit = aggregation.run_aggregation(
        season=season, as_of_date=as_of_date, include_official_validation=official,
        team_detail_limit=0, mismatch_detail_limit=0, generated_at=generated_at,
        client=client, session=session)
    local = audit.get('local_aggregation') or {}
    validation = audit.get('official_validation') or {}
    reconciliation = apply_service.evaluate_mode_reconciliations(
        audit.get('reconciliations') or {}, include_official_validation=official)

    checks = {
        'result_is_pass': audit.get('result') == aggregation.RESULT_PASS,
        'exit_code_is_zero': audit.get('exit_code') == 0,
        'every_applicable_reconciliation_is_present': not reconciliation['missing'],
        'every_applicable_reconciliation_is_true': not reconciliation['failed'],
        'no_unexpected_false_reconciliation': not reconciliation['unexpected_false'],
        'thirty_complete_teams': local.get('teams_complete') == 30,
        'zero_partial_teams': local.get('teams_partial') == 0,
        'zero_unavailable_teams': local.get('teams_unavailable') == 0,
    }
    if official:
        checks.update({
            'all_thirty_teams_matched': validation.get('teams_matched') == 30,
            'zero_teams_mismatched': validation.get('teams_mismatched') == 0,
            'zero_mandatory_metric_mismatches':
                validation.get('mandatory_metric_mismatches') == 0,
            'zero_unavailable_official_evidence':
                validation.get('unavailable_evidence_count') == 0,
            'zero_official_games_missing_a_unique_starter':
                validation.get('official_games_missing_unique_starter') == 0,
            'zero_official_games_with_multiple_starters':
                validation.get('official_games_with_multiple_starters') == 0,
        })
    return _executed(
        all(checks.values()), result=audit.get('result'),
        exit_code=audit.get('exit_code'), mode=audit.get('mode'), checks=checks,
        reconciliations=reconciliation,
        observed={
            'teams_complete': local.get('teams_complete'),
            'teams_partial': local.get('teams_partial'),
            'teams_unavailable': local.get('teams_unavailable'),
            'teams_matched': validation.get('teams_matched'),
            'teams_mismatched': validation.get('teams_mismatched'),
            'mandatory_metric_mismatches': validation.get('mandatory_metric_mismatches'),
            'unavailable_evidence_count': validation.get('unavailable_evidence_count'),
            'official_games_missing_unique_starter': validation.get(
                'official_games_missing_unique_starter'),
            'official_games_with_multiple_starters': validation.get(
                'official_games_with_multiple_starters'),
        })


# ── Entry point ───────────────────────────────────────────────────────────────
def run_closeout_verification(*, generated_at: Optional[str] = None,
                              closeout_git_sha: Optional[str] = None,
                              client=mlb_client, session=None) -> dict:
    """Prove the committed repair, read-only, and reach an independent closeout verdict.

    Writes nothing: no insert, update, delete, advisory lock, migration, or commit. Never
    calls ``apply_reviewed_repair`` and never re-applies any of the 675 committed actions.
    """
    session = session or db.session
    contract = dict(apply_service.APPROVED_EXECUTION_CONTRACT)
    approved_fingerprint = (
        apply_service.APPROVED_OFFICIAL_PITCHING_LINE_REPAIR_MANIFEST_FINGERPRINT_2026)
    season = int(contract['season'])
    as_of_date = date.fromisoformat(contract['as_of_date'])

    payload = _base_payload(contract, approved_fingerprint, generated_at, closeout_git_sha)
    try:
        payload['migration_head'] = completeness._migration_head(session)
    except Exception as exc:  # noqa: BLE001 — never leak a database message
        payload['error_type'] = type(exc).__name__

    results: Dict[str, dict] = {}
    for name, runner in (
        (CLOSEOUT_CHECKS[0],
         lambda: verify_execution_ledger(
             session, contract=contract, approved_fingerprint=approved_fingerprint)),
        (CLOSEOUT_CHECKS[1], lambda: verify_reviewed_amendment_row(session)),
        (CLOSEOUT_CHECKS[2],
         lambda: _completeness_check(season=season, as_of_date=as_of_date,
                                     generated_at=generated_at, client=client,
                                     session=session)),
        (CLOSEOUT_CHECKS[3],
         lambda: _aggregation_check(season=season, as_of_date=as_of_date, official=False,
                                    generated_at=generated_at, client=client,
                                    session=session)),
        (CLOSEOUT_CHECKS[4],
         lambda: _aggregation_check(season=season, as_of_date=as_of_date, official=True,
                                    generated_at=generated_at, client=client,
                                    session=session)),
    ):
        try:
            results[name] = runner()
        except Exception as exc:  # noqa: BLE001 — a check that could not run has not passed
            results[name] = _not_executed(exc)

    present = [name for name in CLOSEOUT_CHECKS if name in results]
    executed = [name for name in present if results[name].get('executed') is True]
    not_executed = [name for name in CLOSEOUT_CHECKS if name not in executed]
    failed = sorted(name for name in executed if not results[name].get('passed'))

    payload['checks'] = results
    payload['present_checks'] = present
    payload['executed_checks'] = executed
    payload['not_executed_checks'] = not_executed
    payload['failed_checks'] = failed
    payload['check_states'] = {
        name: {
            'present': name in results,
            'executed': (results.get(name) or {}).get('executed') is True,
            'passed': (results.get(name) or {}).get('passed') is True,
            # Skipped measures execution and presence, never outcome. A check that ran and
            # failed is a failure, not a skip.
            'skipped': name not in executed,
        }
        for name in CLOSEOUT_CHECKS
    }
    payload['execution_ledger_verification'] = results.get(CLOSEOUT_CHECKS[0])
    payload['reviewed_amendment_verification'] = results.get(CLOSEOUT_CHECKS[1])
    payload['completeness_verification'] = results.get(CLOSEOUT_CHECKS[2])
    payload['local_only_aggregation_verification'] = results.get(CLOSEOUT_CHECKS[3])
    payload['official_validation_aggregation_verification'] = results.get(
        CLOSEOUT_CHECKS[4])
    local_reconciliation = (results.get(CLOSEOUT_CHECKS[3]) or {}).get(
        'reconciliations') or {}
    official_reconciliation = (results.get(CLOSEOUT_CHECKS[4]) or {}).get(
        'reconciliations') or {}
    payload['local_only_applicable_reconciliations'] = local_reconciliation.get(
        'applicable', {})
    payload['local_only_non_applicable_reconciliations'] = local_reconciliation.get(
        'non_applicable', {})
    payload['official_validation_applicable_reconciliations'] = (
        official_reconciliation.get('applicable', {}))
    payload['official_validation_non_applicable_reconciliations'] = (
        official_reconciliation.get('non_applicable', {}))

    # A check that could not run leaves the question open; it never becomes a pass, and it is
    # not reported as a contradiction either.
    if not_executed:
        payload['result'] = RESULT_INCONCLUSIVE
        payload['decision_reasons'] = [DECISION_EVIDENCE_UNAVAILABLE]
        payload['unresolved_issues'] = sorted(set(not_executed) | set(failed))
    elif failed:
        payload['result'] = RESULT_FAIL
        payload['decision_reasons'] = sorted({
            DECISION_LEDGER_NOT_PROVEN if name == CLOSEOUT_CHECKS[0]
            else DECISION_AMENDMENT_NOT_PROVEN if name == CLOSEOUT_CHECKS[1]
            else DECISION_POST_COMMIT_FAILED
            for name in failed
        })
        payload['unresolved_issues'] = list(failed)
    else:
        payload['result'] = RESULT_PASS
        payload['decision_reasons'] = [DECISION_READY_FOR_REVIEW]
        payload['unresolved_issues'] = []
    payload['exit_code'] = EXIT_BY_RESULT[payload['result']]
    return payload


def _base_payload(contract, approved_fingerprint, generated_at, closeout_git_sha) -> dict:
    return {
        'capability': CAPABILITY,
        'mode': MODE_CLOSEOUT,
        'contracts': {
            'closeout_contract_version': CLOSEOUT_CONTRACT_VERSION,
            'apply_contract_version': apply_service.APPLY_CONTRACT_VERSION,
            'closeout_checks': list(CLOSEOUT_CHECKS),
            'local_only_required_reconciliations': list(
                apply_service.LOCAL_ONLY_REQUIRED_RECONCILIATIONS),
            'official_validation_required_reconciliations': list(
                apply_service.OFFICIAL_VALIDATION_REQUIRED_RECONCILIATIONS),
            'local_only_non_applicable_reconciliations': list(
                apply_service.LOCAL_ONLY_NON_APPLICABLE_RECONCILIATIONS),
        },
        'result': RESULT_INCONCLUSIVE,
        'exit_code': EXIT_BY_RESULT[RESULT_INCONCLUSIVE],
        'generated_at': generated_at,
        'git_sha': closeout_git_sha or completeness._git_sha(),
        'migration_head': None,
        'approved_manifest_fingerprint': approved_fingerprint,
        'season': contract['season'],
        'as_of_date': contract['as_of_date'],
        'expected_execution_ledger_id': EXPECTED_EXECUTION_LEDGER_ID,
        'reviewed_amendment_expectation': dict(EXPECTED_AMENDMENT),
        'checks': {},
        'check_states': {},
        'present_checks': [],
        'executed_checks': [],
        'not_executed_checks': [],
        'failed_checks': [],
        'execution_ledger_verification': None,
        'reviewed_amendment_verification': None,
        'completeness_verification': None,
        'local_only_aggregation_verification': None,
        'official_validation_aggregation_verification': None,
        'local_only_applicable_reconciliations': {},
        'local_only_non_applicable_reconciliations': {},
        'official_validation_applicable_reconciliations': {},
        'official_validation_non_applicable_reconciliations': {},
        'decision_reasons': [],
        'unresolved_issues': [],
        # Strictly read-only, and the artifact says so unconditionally.
        'database_writes_performed': False,
        'repair_reapplied': False,
        # A passing closeout makes Foundation 3A eligible for a SEPARATE gate decision. It
        # never opens a gate, and no closeout outcome can change these.
        **{gate: GATE_BLOCKED for gate in DOWNSTREAM_GATES},
        'downstream_gate_statuses': {gate: GATE_BLOCKED for gate in DOWNSTREAM_GATES},
    }
