#!/usr/bin/env python
"""Read-only audit for manual no-op write qualification candidates.

    python scripts/run_noop_qualification_candidate_audit.py \
        --expected-head-sha <40 hex> \
        --confirmation AUDIT_NOOP_QUALIFICATION_CANDIDATES \
        --lookback-days 30 --candidate-limit 20 --eligible-target-count 5

Manual only, read-only, bounded. Identifies completed durable game-driven work
items whose current canonical shadow plans are fully unchanged, and is therefore
the evidence source for choosing a no-op write qualification target — replacing
the operator guessing that produced the ``target_work_item_missing`` refusal in
production run 30862655470.

Finding a candidate is information. It authorizes nothing, creates no work item,
and dispatches nothing.

Exit codes: 0 COMPLETE (with or without an eligible candidate), 1 FAILED,
2 UNPROVEN.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services import noop_qualification_candidate_audit as audit  # noqa: E402
from services import noop_write_qualification as qualification  # noqa: E402


SUMMARY_JSON = 'candidate-audit-summary.json'
SUMMARY_MARKDOWN = 'candidate-audit-summary.md'
METADATA_JSON = 'candidate-audit-metadata.json'

REQUIRED_REPOSITORY = qualification.REQUIRED_REPOSITORY
REQUIRED_REF = qualification.REQUIRED_REF
REQUIRED_EVENT_NAME = qualification.REQUIRED_EVENT_NAME
REQUIRED_ACTOR = qualification.REQUIRED_ACTOR


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only no-op qualification candidate audit.',
    )
    parser.add_argument('--expected-head-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument('--lookback-days', default=None)
    parser.add_argument('--candidate-limit', default=None)
    parser.add_argument('--eligible-target-count', default=None)
    parser.add_argument('--operator-note', default='')
    parser.add_argument(
        '--artifact-dir',
        default='artifacts/noop-qualification-candidate-audit',
    )
    parser.add_argument('--reference-date', default=None)
    return parser.parse_args(argv)


def event_context(args, environ=None) -> dict:
    env = environ if environ is not None else os.environ
    return {
        'event_name': env.get('GITHUB_EVENT_NAME'),
        'repository': env.get('GITHUB_REPOSITORY'),
        'actor': env.get('GITHUB_ACTOR'),
        'ref': env.get('GITHUB_REF'),
        'github_sha': env.get('GITHUB_SHA'),
        'run_id': env.get('GITHUB_RUN_ID'),
        'run_attempt': env.get('GITHUB_RUN_ATTEMPT'),
        'workflow': env.get('GITHUB_WORKFLOW'),
        'expected_head_sha': args.expected_head_sha,
        'confirmation': args.confirmation,
    }


def validate_authorization(context) -> list[str]:
    """Every gate re-validated here; the workflow's gates are not trusted."""
    failures: list[str] = []
    if str(context.get('event_name') or '') != REQUIRED_EVENT_NAME:
        failures.append('event_not_workflow_dispatch')
    if str(context.get('repository') or '') != REQUIRED_REPOSITORY:
        failures.append('repository_not_authorized')
    if str(context.get('actor') or '') != REQUIRED_ACTOR:
        failures.append('actor_not_authorized')
    if str(context.get('ref') or '') != REQUIRED_REF:
        failures.append('ref_not_main')

    expected = qualification.normalize_sha(context.get('expected_head_sha'))
    actual = qualification.normalize_sha(context.get('github_sha'))
    if not qualification._SHA_PATTERN.match(expected):
        failures.append('expected_head_sha_malformed')
    elif not qualification._SHA_PATTERN.match(actual) or expected != actual:
        failures.append('expected_head_sha_mismatch')

    if str(context.get('confirmation') or '') != audit.CONFIRMATION:
        failures.append('confirmation_mismatch')
    return failures


def resolve_reference_date(raw):
    """Match the no-op qualification's reference-date behaviour exactly."""
    if raw:
        return date.fromisoformat(str(raw).strip())
    return datetime.now(timezone.utc).date()


def build_app():
    import app as app_module

    return app_module.create_app()


def run(args) -> dict:
    context = event_context(args)
    note = qualification.sanitize_note(args.operator_note)

    failures = validate_authorization(context)
    if failures:
        return _document(
            context=context, note=note, bounds={}, discovery={},
            candidates=[], read_only={}, stop_reason=None,
            decision=_refuse(failed=failures),
        )

    try:
        bounds = audit.resolve_bounds(
            lookback_days=args.lookback_days,
            candidate_limit=args.candidate_limit,
            eligible_target_count=args.eligible_target_count,
        )
    except audit.AuditInputError as exc:
        return _document(
            context=context, note=note, bounds={}, discovery={},
            candidates=[], read_only={}, stop_reason=None,
            decision=_refuse(failed=[exc.reason]),
        )

    reference_date = resolve_reference_date(args.reference_date)
    flask_app = build_app()

    from services import sync_metadata
    from utils.db import db

    with flask_app.app_context():
        guard_state = {
            'guard_acquired': False,
            'guard_release_attempted': False,
            'guard_released': False,
        }
        guard = None
        try:
            # Acquire-only guard: it takes the public sync advisory lock and
            # never creates, reclaims, or updates a SyncRun row.
            guard = sync_metadata.acquire_public_sync_read_lock(
                source=sync_metadata.SOURCE_GITHUB_ACTIONS,
            )
            guard_state['guard_acquired'] = guard is not None
        except Exception:  # noqa: BLE001 - a contended lock is UNPROVEN
            guard = None

        collected: dict = {}
        try:
            if not guard_state['guard_acquired']:
                raise _AuditHalt()

            try:
                read_only = audit.enforce_read_only(db.session)
            except audit.ReadOnlyProbeViolation as violation:
                # The bounded probe was ACCEPTED. Preserve its evidence and
                # halt: the verdict reducer turns this into the definite
                # read_only_probe_accepted_not_refused failure rather than a
                # generic execution error. The transaction is rolled back and
                # the guard released in the finally block below.
                collected['read_only_enabled'] = False
                collected['read_only_detail'] = violation.evidence
                collected['probe_violation'] = True
                raise _AuditHalt()
            collected['read_only_enabled'] = True
            collected['read_only_detail'] = read_only

            before = audit.table_fingerprints(db.session)
            collected['before_fingerprints'] = before
            if before is None:
                raise _AuditHalt()

            discovery = audit.discover_candidates(
                reference_date=reference_date,
                lookback_days=bounds['lookback_days'],
                candidate_limit=bounds['candidate_limit'],
            )
            collected['discovery'] = discovery

            evaluated = audit.evaluate_candidates(
                candidates=discovery['candidates_selected'],
                reference_date=reference_date,
                eligible_target_count=bounds['eligible_target_count'],
                candidate_limit=bounds['candidate_limit'],
                candidate_pool_size=discovery['candidate_pool_size'],
                session=db.session,
            )
            collected['candidates'] = evaluated['candidates']
            collected['stop_reason'] = evaluated['stop_reason']
            collected['evaluation'] = evaluated

            collected['after_fingerprints'] = audit.table_fingerprints(
                db.session
            )
        except _AuditHalt:
            pass
        except Exception:  # noqa: BLE001 - never leak exception text
            collected['audit_error'] = True
        finally:
            # Always end the read transaction, then release the guard and
            # record what actually happened.
            try:
                db.session.rollback()
            except Exception:  # noqa: BLE001
                pass
            if guard is not None:
                guard_state['guard_release_attempted'] = True
                try:
                    guard.release()
                    guard_state['guard_released'] = True
                except Exception:  # noqa: BLE001
                    guard_state['guard_released'] = False

    read_only_proof = {
        'read_only_enabled': bool(collected.get('read_only_enabled')),
        'read_only_detail': collected.get('read_only_detail') or {},
        'before_fingerprints': collected.get('before_fingerprints'),
        'after_fingerprints': collected.get('after_fingerprints'),
        'fingerprints_match': audit.fingerprints_match(
            collected.get('before_fingerprints'),
            collected.get('after_fingerprints'),
        ),
        'changed_tables': audit.changed_tables(
            collected.get('before_fingerprints'),
            collected.get('after_fingerprints'),
        ),
        'fingerprint_tables': list(audit.FINGERPRINT_TABLES),
        # Promoted to the top level so the verdict validates them directly.
        # Left only inside the nested detail object they were evidence nobody
        # checked.
        **audit.probe_evidence(collected.get('read_only_detail')),
        **guard_state,
    }

    decision = audit.decide(
        candidates=collected.get('candidates') or [],
        read_only_proof=read_only_proof,
        discovery_available='discovery' in collected,
    )
    if collected.get('audit_error'):
        decision['unproven_reasons'] = sorted(set(
            decision['unproven_reasons'] + ['audit_execution_error']
        ))
        decision['result'] = audit.RESULT_UNPROVEN
        decision['exit_code'] = audit.EXIT_CODES[audit.RESULT_UNPROVEN]

    return _document(
        context=context, note=note, bounds=bounds,
        discovery=collected.get('discovery') or {},
        candidates=collected.get('candidates') or [],
        read_only=read_only_proof,
        stop_reason=collected.get('stop_reason'),
        decision=decision,
        reference_date=reference_date,
        evaluation=collected.get('evaluation'),
    )


class _AuditHalt(Exception):
    """Stop collecting; the verdict is decided from what was proven."""


def _refuse(*, failed=(), unproven=()) -> dict:
    result = (
        audit.RESULT_FAILED if failed
        else audit.RESULT_UNPROVEN if unproven
        else audit.RESULT_NO_ELIGIBLE_CANDIDATE
    )
    return {
        'result': result,
        'exit_code': audit.EXIT_CODES[result],
        'failed_reasons': sorted(set(failed)),
        'unproven_reasons': sorted(set(unproven)),
        'eligible_count': 0,
        'ineligible_count': 0,
        'unproven_count': 0,
        'classification_counts': {},
        'ordered_eligible_game_pks': [],
        'suggested_candidate_game_pk': None,
        'suggestion_is_informational_only': True,
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }


def _document(*, context, note, bounds, discovery, candidates, read_only,
              stop_reason, decision, reference_date=None,
              evaluation=None) -> dict:
    evaluation = evaluation or {}
    detail = (read_only or {}).get('read_only_detail') or {}
    return {
        'identity': {
            'schema_version': audit.SCHEMA_VERSION,
            'audit_type': audit.AUDIT_TYPE,
            'repository': context.get('repository'),
            'workflow_name': context.get('workflow'),
            'workflow_run_id': context.get('run_id'),
            'workflow_run_attempt': context.get('run_attempt'),
            'commit_sha': qualification.normalize_sha(
                context.get('github_sha')
            ),
            'ref': context.get('ref'),
            'actor': context.get('actor'),
            'event_name': context.get('event_name'),
            'executed_at': datetime.now(timezone.utc).isoformat(),
        },
        'request': {
            'lookback_days': bounds.get('lookback_days'),
            'candidate_limit': bounds.get('candidate_limit'),
            'eligible_target_count': bounds.get('eligible_target_count'),
            'confirmation_valid': 'confirmation_mismatch' not in (
                decision['failed_reasons']
            ),
            'expected_head_sha_valid': not (
                {'expected_head_sha_malformed', 'expected_head_sha_mismatch'}
                & set(decision['failed_reasons'])
            ),
            'operator_note': note,
            'reference_date': (
                reference_date.isoformat() if reference_date else None
            ),
        },
        'discovery': {
            'work_items_considered': discovery.get('work_items_considered'),
            'completed_work_items_found': discovery.get(
                'completed_work_items_found'
            ),
            'duplicates_excluded': discovery.get('duplicates_excluded'),
            'duplicate_count': discovery.get('duplicate_count'),
            'candidates_selected': len(discovery.get(
                'candidates_selected'
            ) or []),
            'candidates_evaluated': evaluation.get('candidates_evaluated'),
            'eligible_stop_position': evaluation.get('eligible_stop_position'),
            'configured_candidate_limit': evaluation.get(
                'configured_candidate_limit'
            ),
            'candidate_pool_size': discovery.get('candidate_pool_size'),
            'deterministic_ordering': discovery.get('ordering'),
            'window_start': discovery.get('window_start'),
            'window_end': discovery.get('window_end'),
            'earliest_completion_considered': discovery.get(
                'earliest_completion_considered'
            ),
            'latest_completion_considered': discovery.get(
                'latest_completion_considered'
            ),
            'bounded_stop_reason': stop_reason,
        },
        'read_only_proof': {
            'advisory_guard_acquired': read_only.get('guard_acquired'),
            'advisory_guard_release_attempted': read_only.get(
                'guard_release_attempted'
            ),
            'advisory_guard_released': read_only.get('guard_released'),
            'transaction_read_only_enabled': read_only.get(
                'read_only_enabled'
            ),
            'write_probe_refused': detail.get('write_probe_refused'),
            'fingerprint_tables': read_only.get('fingerprint_tables'),
            'before_fingerprints': read_only.get('before_fingerprints'),
            'after_fingerprints': read_only.get('after_fingerprints'),
            'fingerprints_match': read_only.get('fingerprints_match'),
            'changed_tables': read_only.get('changed_tables'),
            # One bounded, refused proof statement is attempted. Zero durable
            # writes are attempted. These are different facts and are reported
            # as different fields.
            'read_only_probe_attempted': detail.get(
                'read_only_probe_attempted', False
            ),
            'read_only_probe_count': detail.get('read_only_probe_count', 0),
            'read_only_probe_statement_class': detail.get(
                'read_only_probe_statement_class'
            ),
            'read_only_probe_bounded_to_zero_rows': detail.get(
                'read_only_probe_bounded_to_zero_rows', False
            ),
            'read_only_probe_refused': detail.get(
                'read_only_probe_refused', False
            ),
            'durable_write_attempts': detail.get('durable_write_attempts', 0),
            'durable_rows_created': 0,
            'durable_rows_updated': 0,
            'durable_rows_deleted': 0,
            'commits_performed_by_audit': 0,
        },
        'candidate_summary': {
            'eligible_count': decision['eligible_count'],
            'ineligible_count': decision['ineligible_count'],
            'unproven_count': decision['unproven_count'],
            'classification_counts': decision['classification_counts'],
            'ordered_eligible_game_pks': decision[
                'ordered_eligible_game_pks'
            ],
            'suggested_candidate_game_pk': decision[
                'suggested_candidate_game_pk'
            ],
            'suggestion_is_informational_only': True,
            'suggestion_note': (
                'The suggested candidate is the first eligible game under the '
                'declared deterministic ordering. It is informational and does '
                'not authorize a dispatch.'
            ),
        },
        'candidates': candidates,
        'verdict': {
            'result': decision['result'],
            'exit_code': decision['exit_code'],
            'failed_reasons': decision['failed_reasons'],
            'unproven_reasons': decision['unproven_reasons'],
            'explanation': _explanation(decision),
            'non_authorization_statement': (
                audit.NON_AUTHORIZATION_STATEMENT
            ),
        },
    }


def _explanation(decision) -> str:
    result = decision['result']
    if result == audit.RESULT_ELIGIBLE_FOUND:
        return (
            'The audit completed read-only and found at least one completed '
            'durable work item whose current canonical shadow plan is fully '
            'unchanged. This identifies a qualification target; it does not '
            'authorize dispatching one.'
        )
    if result == audit.RESULT_NO_ELIGIBLE_CANDIDATE:
        return (
            'The audit completed read-only and found no eligible candidate '
            'within the requested bounds. This is a successful completed '
            'audit, not a failure. The next step is a separately reviewed '
            'decision, not a widening of this audit.'
        )
    if result == audit.RESULT_FAILED:
        return (
            'A contract violation was observed — the audit either changed '
            'database content or evaluated a candidate that did. This is a '
            'definite negative result.'
        )
    return (
        'Trustworthy evidence could not be completed, so the audit is '
        'unproven. UNPROVEN is not a pass: absent evidence is the state most '
        'easily mistaken for success.'
    )


def render_markdown(document) -> str:
    identity = document['identity']
    verdict = document['verdict']
    proof = document['read_only_proof']
    discovery = document['discovery']
    summary = document['candidate_summary']

    lines = [
        '# No-op qualification candidate audit',
        '',
        f"**Result: {verdict['result']}**",
        '',
        verdict['explanation'],
        '',
        '## Identity',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| audit type | `{identity['audit_type']}` |",
        f"| schema version | {identity['schema_version']} |",
        f"| repository | {identity.get('repository')} |",
        f"| run | {identity.get('workflow_run_id')} "
        f"(attempt {identity.get('workflow_run_attempt')}) |",
        f"| commit | `{identity.get('commit_sha')}` |",
        f"| ref | {identity.get('ref')} |",
        f"| actor | {identity.get('actor')} |",
        f"| executed at | {identity.get('executed_at')} |",
        '',
        '## Read-only proof',
        '',
        '| check | value |',
        '| :--- | :--- |',
        f"| advisory guard acquired | {proof.get('advisory_guard_acquired')} |",
        f"| release attempted | "
        f"{proof.get('advisory_guard_release_attempted')} |",
        f"| release confirmed | {proof.get('advisory_guard_released')} |",
        f"| transaction read-only | "
        f"{proof.get('transaction_read_only_enabled')} |",
        f"| fingerprints match | {proof.get('fingerprints_match')} |",
        f"| changed tables | {proof.get('changed_tables')} |",
        '',
        '### Write accounting',
        '',
        'The audit issues exactly one bounded proof statement, expected to be '
        'refused and rolled back. It attempts zero durable writes. Those are '
        'different facts and are reported as different rows.',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| read-only probe attempted | "
        f"{proof.get('read_only_probe_attempted')} |",
        f"| read-only probe count | {proof.get('read_only_probe_count')} |",
        f"| read-only probe statement class | "
        f"`{proof.get('read_only_probe_statement_class')}` |",
        f"| read-only probe bounded to zero rows | "
        f"{proof.get('read_only_probe_bounded_to_zero_rows')} |",
        f"| read-only probe refused | "
        f"{proof.get('read_only_probe_refused')} |",
        f"| durable write attempts | {proof.get('durable_write_attempts')} |",
        f"| durable rows created | {proof.get('durable_rows_created')} |",
        f"| durable rows updated | {proof.get('durable_rows_updated')} |",
        f"| durable rows deleted | {proof.get('durable_rows_deleted')} |",
        f"| commits performed by audit | "
        f"{proof.get('commits_performed_by_audit')} |",
        '',
        '## Discovery',
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| lookback days | {document['request'].get('lookback_days')} |",
        f"| candidate limit | {document['request'].get('candidate_limit')} |",
        f"| eligible target | "
        f"{document['request'].get('eligible_target_count')} |",
        f"| completed work items found | "
        f"{discovery.get('completed_work_items_found')} |",
        f"| duplicates excluded | {discovery.get('duplicate_count')} |",
        f"| candidates selected | {discovery.get('candidates_selected')} |",
        f"| candidates evaluated | {discovery.get('candidates_evaluated')} |",
        f"| configured limit | {discovery.get('configured_candidate_limit')} |",
        f"| ordering | `{discovery.get('deterministic_ordering')}` |",
        f"| stop reason | {discovery.get('bounded_stop_reason')} |",
        '',
        '## Candidates',
        '',
        '| # | game | classification | rows | unchanged | eligible |',
        '| ---: | ---: | :--- | ---: | ---: | :--- |',
    ]
    for candidate in document['candidates']:
        lines.append(
            f"| {candidate.get('ordering_position')} "
            f"| {candidate['game_pk']} "
            f"| `{candidate['primary_classification']}` "
            f"| {candidate['planned_row_count']} "
            f"| {candidate['unchanged_row_count']} "
            f"| {candidate['eligible']} |"
        )

    lines += [
        '',
        '## Summary',
        '',
        f"- eligible: {summary['eligible_count']}",
        f"- ineligible: {summary['ineligible_count']}",
        f"- unproven: {summary['unproven_count']}",
        f"- ordered eligible games: {summary['ordered_eligible_game_pks']}",
        f"- suggested candidate: {summary['suggested_candidate_game_pk']}",
        '',
        summary['suggestion_note'],
        '',
    ]

    if verdict['failed_reasons']:
        lines += ['## Failed reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['failed_reasons']]
        lines.append('')
    if verdict['unproven_reasons']:
        lines += ['## Unproven reasons', '']
        lines += [f'- `{reason}`' for reason in verdict['unproven_reasons']]
        lines.append('')

    lines += ['---', '', verdict['non_authorization_statement'], '']
    return '\n'.join(lines)


def write_artifacts(document, artifact_dir) -> dict:
    target = Path(artifact_dir)
    target.mkdir(parents=True, exist_ok=True)

    (target / SUMMARY_JSON).write_text(
        json.dumps(document, indent=2, sort_keys=True, default=str) + '\n',
        encoding='utf-8',
    )
    (target / SUMMARY_MARKDOWN).write_text(
        render_markdown(document), encoding='utf-8',
    )
    metadata = {
        'schema_version': audit.SCHEMA_VERSION,
        'audit_type': audit.AUDIT_TYPE,
        'result': document['verdict']['result'],
        'exit_code': document['verdict']['exit_code'],
        'eligible_count': document['candidate_summary']['eligible_count'],
        'suggested_candidate_game_pk': document['candidate_summary'][
            'suggested_candidate_game_pk'
        ],
        'commit_sha': document['identity'].get('commit_sha'),
        'workflow_run_id': document['identity'].get('workflow_run_id'),
        'summary_filename': SUMMARY_JSON,
        'markdown_filename': SUMMARY_MARKDOWN,
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
    }
    (target / METADATA_JSON).write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + '\n', encoding='utf-8',
    )
    return metadata


def main(argv=None) -> int:
    args = parse_args(argv)
    try:
        document = run(args)
    except Exception:  # noqa: BLE001 - never leak exception text
        document = _document(
            context=event_context(args),
            note=qualification.sanitize_note(args.operator_note),
            bounds={}, discovery={}, candidates=[], read_only={},
            stop_reason=None,
            decision=_refuse(unproven=['audit_execution_error']),
        )

    try:
        write_artifacts(document, args.artifact_dir)
    except Exception:  # noqa: BLE001 - an unwritable artifact is UNPROVEN
        document['verdict']['unproven_reasons'] = sorted(set(
            list(document['verdict']['unproven_reasons'])
            + ['artifact_construction_failed']
        ))
        document['verdict']['result'] = audit.RESULT_UNPROVEN
        document['verdict']['exit_code'] = audit.EXIT_CODES[
            audit.RESULT_UNPROVEN
        ]

    print(json.dumps(document, indent=2, sort_keys=True, default=str))
    return int(document['verdict']['exit_code'])


if __name__ == '__main__':
    os.environ.setdefault('AUTO_SYNC', 'false')
    raise SystemExit(main())
