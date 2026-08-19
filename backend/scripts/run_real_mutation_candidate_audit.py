#!/usr/bin/env python
"""Read-only real-mutation qualification candidate audit.

Identifies completed durable game-driven work items whose CURRENT canonical
shadow plan is exactly one governed statistical correction, to one existing row,
on one field whose source authority the repository has resolved.

    python scripts/run_real_mutation_candidate_audit.py \
        --expected-head-sha <40 hex> \
        --confirmation AUDIT_REAL_MUTATION_CANDIDATES \
        --artifact-dir artifacts/real-mutation-candidate-audit

Read-only, three ways: the public sync advisory lock acquired but never used to
claim a run, a PostgreSQL read-only transaction with a refused write probe, and
before/after content fingerprints across every table the shadow path can reach.

Finding zero eligible candidates is a COMPLETED audit, not a failure. Nothing
here creates a work item, advances a checkpoint, commits, dispatches the write
qualification, or authorizes any write.

Exit codes: 0 complete (with or without an eligible candidate), 1 FAILED,
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

from services import real_mutation_candidate_audit as audit  # noqa: E402
from services import real_mutation_qualification as qualification  # noqa: E402


SUMMARY_JSON = 'candidate-audit-summary.json'
SUMMARY_MARKDOWN = 'candidate-audit-summary.md'
METADATA_JSON = 'candidate-audit-metadata.json'

REQUIRED_REPOSITORY = qualification.REQUIRED_REPOSITORY
REQUIRED_REF = qualification.REQUIRED_REF
REQUIRED_EVENT_NAME = qualification.REQUIRED_EVENT_NAME
REQUIRED_ACTOR = qualification.REQUIRED_ACTOR


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description='Read-only real-mutation candidate audit.',
    )
    parser.add_argument('--expected-head-sha', required=True)
    parser.add_argument('--confirmation', required=True)
    parser.add_argument('--lookback-days', default=None)
    parser.add_argument('--candidate-limit', default=None)
    parser.add_argument('--eligible-target-count', default=None)
    parser.add_argument('--operator-note', default='')
    parser.add_argument(
        '--artifact-dir',
        default='artifacts/real-mutation-candidate-audit',
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
    if raw:
        return date.fromisoformat(str(raw).strip())
    return datetime.now(timezone.utc).date()


def build_app():
    import app as app_module

    return app_module.create_app()


class _AuditHalt(Exception):
    """Stop collecting; the verdict is decided from what was proven."""


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
                # halt; the verdict reducer turns this into the definite
                # failure rather than a generic execution error.
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
        **audit.probe_evidence(collected.get('read_only_detail')),
        **guard_state,
    }
    probe = audit.evaluate_probe_evidence(read_only_proof)
    read_only_proof['failed_reasons'] = probe.get('failed_reasons') or []
    read_only_proof['unproven_reasons'] = probe.get('unproven_reasons') or []
    if not read_only_proof['fingerprints_match']:
        read_only_proof['failed_reasons'] = sorted(set(
            read_only_proof['failed_reasons'] + ['durable_write_attempted']
        ))
    if not read_only_proof['guard_acquired']:
        read_only_proof['unproven_reasons'] = sorted(set(
            read_only_proof['unproven_reasons'] + ['sync_read_lock_unavailable']
        ))

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
        'eligible_candidate_count': 0,
        'eligible_game_pks': [],
        'non_authorization_statement': audit.NON_AUTHORIZATION_STATEMENT,
        'unresolved_authority_fields': sorted(
            qualification.UNRESOLVED_SOURCE_AUTHORITY_FIELDS
        ),
        'permitted_ingestion_mode': audit.PERMITTED_INGESTION_MODE,
    }


def _document(*, context, note, bounds, discovery, candidates, read_only,
              stop_reason, decision, reference_date=None,
              evaluation=None) -> dict:
    eligible = [entry for entry in candidates if entry.get('eligible')]
    classification_counts: dict[str, int] = {}
    for entry in candidates:
        key = entry.get('classification') or 'unclassified'
        classification_counts[key] = classification_counts.get(key, 0) + 1

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
            'operator_note': note,
        },
        'bounds': dict(sorted((bounds or {}).items())),
        'reference_date': (
            reference_date.isoformat() if reference_date else None
        ),
        'discovery': discovery or {},
        'evaluation': {
            'stop_reason': stop_reason,
            'candidates_evaluated': (evaluation or {}).get(
                'candidates_evaluated', len(candidates)
            ),
            'candidates_selected': (evaluation or {}).get(
                'candidates_selected'
            ),
            'candidate_pool_size': (evaluation or {}).get(
                'candidate_pool_size'
            ),
            'configured_candidate_limit': (evaluation or {}).get(
                'configured_candidate_limit'
            ),
            'eligible_stop_position': (evaluation or {}).get(
                'eligible_stop_position'
            ),
            'classification_counts': dict(sorted(classification_counts.items())),
        },
        'read_only_proof': read_only or {},
        'candidates': candidates,
        'eligible_candidates': eligible,
        'verdict': {
            'result': decision['result'],
            'exit_code': decision['exit_code'],
            'failed_reasons': decision.get('failed_reasons') or [],
            'unproven_reasons': decision.get('unproven_reasons') or [],
            'eligible_candidate_count': decision.get(
                'eligible_candidate_count', len(eligible)
            ),
            'eligible_game_pks': decision.get('eligible_game_pks') or [],
            'unresolved_authority_fields': decision.get(
                'unresolved_authority_fields'
            ),
            'permitted_ingestion_mode': decision.get(
                'permitted_ingestion_mode'
            ),
            'suggestion_is_informational_only': True,
            'non_authorization_statement': (
                audit.NON_AUTHORIZATION_STATEMENT
            ),
        },
    }


def render_markdown(document) -> str:
    verdict = document['verdict']
    evaluation = document['evaluation']
    discovery = document['discovery']
    read_only = document['read_only_proof']

    lines = [
        '# Real-mutation qualification candidate audit',
        '',
        f"**Result: {verdict['result']}**",
        '',
        '| field | value |',
        '| :--- | :--- |',
        f"| audit type | `{document['identity']['audit_type']}` |",
        f"| commit | `{document['identity'].get('commit_sha')}` |",
        f"| reference date | {document.get('reference_date')} |",
        f"| work items considered | {discovery.get('work_items_considered')} |",
        f"| candidates evaluated | {evaluation.get('candidates_evaluated')} |",
        f"| eligible candidates | {verdict.get('eligible_candidate_count')} |",
        f"| stop reason | `{evaluation.get('stop_reason')}` |",
        f"| read-only enabled | {read_only.get('read_only_enabled')} |",
        f"| fingerprints match | {read_only.get('fingerprints_match')} |",
        f"| write probe refused | {read_only.get('read_only_probe_refused')} |",
        f"| durable write attempts | "
        f"{read_only.get('durable_write_attempts')} |",
        '',
        '**Eligible candidates**',
        '',
    ]

    if verdict.get('eligible_game_pks'):
        lines.extend([
            '| game | pitcher | field | stored value | source revision '
            '| plan fingerprint |',
            '| ---: | ---: | :--- | ---: | :--- | :--- |',
        ])
        for entry in document['eligible_candidates']:
            lines.append(
                f"| {entry.get('game_pk')} | {entry.get('pitcher_mlb_id')} "
                f"| `{entry.get('field')}` | {entry.get('stored_value')} "
                f"| `{(entry.get('source_revision') or '')[:16]}` "
                f"| `{(entry.get('plan_fingerprint') or '')[:16]}` |"
            )
    else:
        lines.append(
            'None. Zero eligible candidates is a completed audit, not a '
            'failure: a real-mutation candidate exists only while shadow has '
            'found a divergence the legacy writer has not yet resolved.'
        )

    lines.extend([
        '',
        '**Classification counts**',
        '',
        '| classification | count |',
        '| :--- | ---: |',
    ])
    for key, count in (evaluation.get('classification_counts') or {}).items():
        lines.append(f'| `{key}` | {count} |')

    for reason in verdict['failed_reasons']:
        lines.append(f'\n- FAILED: `{reason}`')
    for reason in verdict['unproven_reasons']:
        lines.append(f'\n- UNPROVEN: `{reason}`')

    lines.extend([
        '',
        'Source-authority fields refused while unresolved: '
        + ', '.join(
            f'`{field}`'
            for field in verdict.get('unresolved_authority_fields') or ()
        ),
        '',
        verdict['non_authorization_statement'],
        '',
    ])
    return '\n'.join(lines)


def write_artifacts(document, artifact_dir) -> dict:
    target = Path(artifact_dir)
    target.mkdir(parents=True, exist_ok=True)

    encoded = json.dumps(document, indent=2, sort_keys=True, default=str)
    (target / SUMMARY_JSON).write_text(encoded + '\n', encoding='utf-8')
    (target / SUMMARY_MARKDOWN).write_text(
        render_markdown(document), encoding='utf-8',
    )
    metadata = {
        'schema_version': audit.SCHEMA_VERSION,
        'audit_type': audit.AUDIT_TYPE,
        'result': document['verdict']['result'],
        'exit_code': document['verdict']['exit_code'],
        'eligible_candidate_count': document['verdict'][
            'eligible_candidate_count'
        ],
        'eligible_game_pks': document['verdict']['eligible_game_pks'],
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
