# Phantom GameLog reconciliation production runbook

This runbook applies only to GameLog `41040` after the repository capability is merged.

## 1. Dry run

Dispatch **Phantom GameLog Reconciliation** with the defaults:

- mode: `dry_run`
- game_log_id: `41040`
- game_pk: `824262`
- game_date: `2026-06-23`
- pitcher_mlb_id: `445276`
- confirmation: blank
- expected_fingerprint: blank

Required acceptance:

- result `pass`, exit `0`;
- reason `verified_phantom_non_appearance_plan_ready`;
- stored all-zero signature shown;
- official pitching sections present for both teams;
- target pitcher absent from official pitching lines;
- proposed action `delete_phantom_game_log`;
- rows deleted `0`;
- database writes `false`;
- a 64-character fingerprint.

## 2. Apply

After reviewing and approving the dry-run artifact, dispatch the same workflow with:

- mode: `apply`;
- confirmation: `RUN_PHANTOM_GAME_LOG_RECONCILIATION`;
- expected_fingerprint: the exact approved dry-run fingerprint;
- all identity guards unchanged.

Required acceptance:

- result `pass`, exit `0`;
- reason `verified_phantom_non_appearance_deleted`;
- rows deleted `1`;
- database writes `true`.

Any different result stops the sequence.

## 3. Verification order

1. Run the Foundation 1 Appearance-Team Production Audit and require 2026 unresolved `0`, conflict `0`, invalid stored states `0`, and coverage reconciliation true.
2. Run Foundation 3A `local_only` for season 2026 through July 25 and require PASS before any official validation.
3. Only after local-only PASS, run Foundation 3A `official_validation` and review all mandatory team/league comparisons.

Foundation 3B and Share Card performance context remain blocked until these production gates pass.
