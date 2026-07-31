#!/usr/bin/env python
"""Emit the Foundation 3C Stage E cleanup manifest.

Every file the R1–R6 rollout introduced is classified here, with what happened
to it and why. Two properties make this worth generating rather than writing by
hand: it VERIFIES against the working tree rather than describing it from
memory, and it names the E2 action for anything still standing.

Classifications:

  permanent_runtime           production behaviour; never removed for cleanup
  permanent_regression        coverage that outlives the rollout
  unresolved_forensic_support kept because an open investigation still needs it
  removed_rollout_only        deleted in this pull request
  retain_until_stage_e2       still required by the Stage E verification itself

TEMPORARY. Removed by Stage E2 along with the Stage E workflow.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

PERMANENT_RUNTIME = 'permanent_runtime'
PERMANENT_REGRESSION = 'permanent_regression'
FORENSIC = 'unresolved_forensic_support'
REMOVED = 'removed_rollout_only'
RETAIN_E2 = 'retain_until_stage_e2'


ENTRIES = [
    # ── The six dangerous rollout workflows ─────────────────────────────────
    *[
        {
            'path': f'.github/workflows/foundation-3c-{name}.yml',
            'classification': REMOVED,
            'retained': False,
            'reason': (
                f'{label} is complete. The workflow could still be dispatched '
                'against production while it existed.'
            ),
            'permanent_behavior_extracted_to': None,
            'e2_action': None,
        }
        for name, label in (
            ('r1-shadow-validation', 'R1 shadow validation'),
            ('r2-full-window-shadow', 'R2 full-window review'),
            ('r3-controlled-sample-shadow', 'R3 controlled-sample shadow'),
            ('r4-controlled-write', 'R4 controlled write'),
            ('r5-remaining-window-shadow', 'R5 remaining-window shadow'),
            ('r6-full-remaining-window-write', 'R6 full remaining-window write'),
        )
    ],
    # ── A seventh Foundation 3C workflow, not in the original six ───────────
    {
        'path': '.github/workflows/foundation-3c-readonly-profile.yml',
        'classification': REMOVED,
        'retained': False,
        'reason': (
            'A temporary Foundation 3C diagnostic whose own header says to '
            'delete it once the Foundation 3C evidence has been reviewed. It '
            'accepted editable inputs and was dispatchable against production. '
            'Its read-only support script and test are retained.'
        ),
        'permanent_behavior_extracted_to': None,
        'e2_action': None,
    },
    # ── Rollout validators ──────────────────────────────────────────────────
    *[
        {
            'path': f'backend/scripts/{name}',
            'classification': REMOVED,
            'retained': False,
            'reason': (
                'Validated one retired rollout stage against one-time expected '
                'values. Nothing can invoke it now.'
            ),
            'permanent_behavior_extracted_to': (
                'backend/tests/test_exclusive_game_scope.py; '
                'backend/tests/test_pitcher_identity_authority.py; '
                'backend/tests/test_shadow_write_reconciliation_parity.py; '
                'backend/tests/test_canonical_innings_reconciliation.py; '
                'backend/tests/test_game_ingestion_completeness.py'
            ),
            'e2_action': None,
        }
        for name in (
            'validate_r1_shadow_report.py',
            'validate_r2_shadow_report.py',
            'validate_r3_shadow_report.py',
            'validate_r4_controlled_write.py',
            'validate_r5_remaining_shadow.py',
            'validate_r6_full_write.py',
        )
    ],
    # ── Rollout state inspectors ────────────────────────────────────────────
    *[
        {
            'path': f'backend/scripts/{name}',
            'classification': REMOVED,
            'retained': False,
            'reason': (
                'Snapshotted state for one retired rollout stage. The Stage E '
                'inspector supersedes it for the completed bootstrap.'
            ),
            'permanent_behavior_extracted_to': (
                'backend/scripts/inspect_stage_e_bootstrap_state.py'
            ),
            'e2_action': None,
        }
        for name in (
            'inspect_r4_controlled_state.py',
            'inspect_r5_remaining_state.py',
            'inspect_r6_full_write_state.py',
        )
    ],
    # ── Rollout workflow test files ─────────────────────────────────────────
    *[
        {
            'path': f'backend/tests/test_foundation_3c_{name}_workflow.py',
            'classification': REMOVED,
            'retained': False,
            'reason': (
                'Asserted temporary workflow structure, artifact names, step '
                'ordering, phone instructions, and one-time fingerprints. None '
                'of that describes production behaviour.'
            ),
            'permanent_behavior_extracted_to': (
                'backend/tests/test_game_driven_ingestion.py (per-game commit '
                'boundary, partial completion honesty, replay without '
                'mutation); the permanent suites already covering exclusive '
                'scope, identity-by-value fingerprinting, canonical innings, '
                'shadow/write parity, and completeness'
            ),
            'e2_action': None,
        }
        for name in ('r1', 'r2', 'r3', 'r4', 'r5', 'r6')
    ],
    # ── Retained until Stage E2 ─────────────────────────────────────────────
    {
        'path': '.github/workflows/foundation-3c-stage-e-bootstrap-closeout.yml',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': (
            'The Stage E verification itself. A workflow cannot verify '
            'production after merge and delete itself in the same merged '
            'commit.'
        ),
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Delete after the E1 production closeout passes.',
    },
    {
        'path': 'backend/scripts/stage_e_bootstrap_scope.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': 'Supplies the pinned 109-game scope to the Stage E workflow.',
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Delete with the Stage E workflow.',
    },
    {
        'path': 'backend/scripts/r5_remaining_window_scope.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': (
            'The Stage E scope helper imports the reviewed 99 from here rather '
            'than restating them.'
        ),
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Delete with the Stage E scope helper.',
    },
    {
        'path': 'backend/scripts/inspect_stage_e_bootstrap_state.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': 'Takes the Stage E before/after snapshots.',
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Delete with the Stage E workflow.',
    },
    {
        'path': 'backend/scripts/validate_stage_e_bootstrap_closeout.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': 'Produces the Stage E closeout decision and artifacts.',
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Delete with the Stage E workflow.',
    },
    {
        'path': 'backend/scripts/build_stage_e_cleanup_manifest.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': 'Generates this manifest inside the Stage E run.',
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Delete with the Stage E workflow.',
    },
    {
        'path': 'backend/tests/test_foundation_3c_stage_e_workflow.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': 'Guards the Stage E workflow and validator.',
        'permanent_behavior_extracted_to': (
            'The permanent-runtime presence assertions in this file must move '
            'to a permanent suite at E2 rather than being deleted with it.'
        ),
        'e2_action': (
            'Delete with the Stage E workflow, after relocating the '
            'permanent-runtime presence assertions.'
        ),
    },
    {
        'path': 'backend/scripts/profile_daily_ingestion_readonly.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': (
            'Read-only diagnostic whose dispatchable workflow was removed. '
            'Harmless without it, and possibly useful to the open provenance '
            'investigation.'
        ),
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Decide whether the open investigation still needs it.',
    },
    {
        'path': 'backend/tests/test_daily_ingestion_readonly_profile.py',
        'classification': RETAIN_E2,
        'retained': True,
        'reason': 'Covers the retained read-only profiling script.',
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Remove only if the script is removed.',
    },
    # ── Unresolved forensic support ─────────────────────────────────────────
    {
        'path': 'backend/scripts/inspect_first_write_pitcher_identity.py',
        'classification': FORENSIC,
        'retained': True,
        'reason': (
            'The first-write provenance question is unresolved: 14 false '
            'GameLog provenance events, possible historic Pitcher changes, and '
            'no reconstructible before-images. That work is outside Stage E.'
        ),
        'permanent_behavior_extracted_to': None,
        'e2_action': 'Keep. Not part of Stage E cleanup.',
    },
    # ── Permanent runtime ───────────────────────────────────────────────────
    *[
        {
            'path': path,
            'classification': PERMANENT_RUNTIME,
            'retained': True,
            'reason': reason,
            'permanent_behavior_extracted_to': None,
            'e2_action': 'Keep. Never removed for rollout cleanup.',
        }
        for path, reason in (
            ('backend/scripts/game_driven_ingestion.py',
             'The canonical ingestion entry point.'),
            ('backend/services/game_driven_ingestion.py',
             'The canonical runner, checkpointing, and failure classification.'),
            ('backend/services/game_ingestion_planner.py',
             'Planner authority and deterministic ordering.'),
            ('backend/services/game_ingestion_completeness.py',
             'Fail-closed publication completeness.'),
            ('backend/services/game_log_reconciliation.py',
             'Reconciliation planning, canonical innings, contract-4 '
             'fingerprinting.'),
            ('backend/services/pitcher_identity_reconciliation.py',
             'D-009 completed-game identity authority.'),
            ('backend/models/game_ingestion_work_item.py',
             'Durable checkpoint and work-item state.'),
        )
    ],
    # ── Permanent regression ────────────────────────────────────────────────
    *[
        {
            'path': f'backend/tests/{name}',
            'classification': PERMANENT_REGRESSION,
            'retained': True,
            'reason': reason,
            'permanent_behavior_extracted_to': None,
            'e2_action': 'Keep.',
        }
        for name, reason in (
            ('test_game_driven_ingestion.py',
             'Runner, checkpoint, resume, per-game commit boundary, partial '
             'completion honesty, replay without mutation.'),
            ('test_exclusive_game_scope.py',
             'Exact exclusive scope; a write refuses without a reviewed '
             'fingerprint and refuses before mutation on a mismatch.'),
            ('test_pitcher_identity_authority.py',
             'D-009 authority and identity-by-value fingerprint coverage '
             'under parity contract 4.'),
            ('test_canonical_innings_reconciliation.py',
             'Integer outs remain the semantic authority; decimal drift is '
             'ignored.'),
            ('test_shadow_write_reconciliation_parity.py',
             'Shadow and write plans agree; write and replay converge.'),
            ('test_game_ingestion_completeness.py',
             'Publication completeness fails closed.'),
            ('test_publication_criticality.py',
             'Publication-critical versus best-effort classification.'),
        )
    ],
]


def build_manifest() -> dict:
    """Classify every entry AND verify it against the working tree."""
    entries = []
    mismatches = []
    for entry in ENTRIES:
        exists = (REPO_ROOT / entry['path']).exists()
        record = dict(entry)
        record['exists_in_tree'] = exists
        # A manifest that merely asserts is a description. This checks.
        if exists != entry['retained']:
            record['verification'] = 'MISMATCH'
            mismatches.append(entry['path'])
        else:
            record['verification'] = 'ok'
        entries.append(record)

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry['classification']] = (
            counts.get(entry['classification'], 0) + 1
        )

    return {
        'document': 'foundation_3c_stage_e_cleanup_manifest',
        'stage': 'E1',
        'entries': sorted(entries, key=lambda item: item['path']),
        'counts_by_classification': dict(sorted(counts.items())),
        'total_entries': len(entries),
        'verification_mismatches': sorted(mismatches),
        'all_entries_verified': not mismatches,
        'rollout_workflows_remaining': sorted(
            path.name for path in (REPO_ROOT / '.github' / 'workflows').glob(
                'foundation-3c-*.yml'
            )
        ),
    }


def manifest_markdown(manifest) -> str:
    lines = [
        '## Foundation 3C Stage E1 cleanup manifest',
        '',
        f"- Total entries: {manifest['total_entries']}",
        f"- All entries verified against the tree: "
        f"{manifest['all_entries_verified']}",
        '- Foundation 3C workflows remaining: '
        f"{manifest['rollout_workflows_remaining'] or 'none beyond Stage E'}",
        '',
        '### Counts by classification',
        '',
        '| classification | files |',
        '|---|---:|',
    ]
    for name, count in manifest['counts_by_classification'].items():
        lines.append(f'| `{name}` | {count} |')
    lines += [
        '',
        '### Entries',
        '',
        '| path | classification | retained | E2 action |',
        '|---|---|---|---|',
    ]
    for entry in manifest['entries']:
        lines.append(
            f"| `{entry['path']}` | `{entry['classification']}` "
            f"| {'yes' if entry['retained'] else 'no'} "
            f"| {entry['e2_action'] or '—'} |"
        )
    lines.append('')
    return '\n'.join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description='Build the Foundation 3C Stage E cleanup manifest.',
    )
    parser.add_argument('--json', required=True)
    parser.add_argument('--markdown', required=True)
    args = parser.parse_args(argv)

    manifest = build_manifest()
    for path, payload in (
        (args.json,
         json.dumps(manifest, indent=2, sort_keys=True, default=str) + '\n'),
        (args.markdown, manifest_markdown(manifest)),
    ):
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding='utf-8')

    if not manifest['all_entries_verified']:
        print(
            '::error::Cleanup manifest does not match the working tree: '
            f"{', '.join(manifest['verification_mismatches'])}"
        )
        return 1
    print(f"Cleanup manifest verified: {manifest['total_entries']} entries.")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
