# Governed Team State movement in What Changed

Status: approved for the reader-facing Team State delta lane.

What Changed may publish a Team State movement only from two compatible frozen
`team_board_delta` sidecars. The latest frozen publication is compared with the
nearest prior publication whose existing Team State domain contract proves
compatibility. Compatibility remains owned by the delta substrate and includes
the method, public and source contracts, population authority, team identity,
represented-date ordering, source identity, and publication trust gates.

The public `/changes` payload adds a separate `team_state_change` object and a
`team_state_comparison` status block. A movement carries the stable frozen state
keys, exact frozen public labels, represented dates, and backend-authored neutral
summary. It exists only when the stable public Team State key changes. Comparable
unchanged endpoints emit no movement; missing, incompatible, or untrusted
endpoints fail closed with no inferred state.

The only previously frozen What Changed service authorized to change is
`backend/services/team_changes.py`. The delta substrate supplies endpoint
selection and compatibility; the service only authors the additive public lane.

The Team State publication window is independent of the existing completed-game
window used by legacy arm-status and appearance lanes. Both date ranges remain
explicit. A valid frozen Team State movement is meaningful on its own and may
set the overall `/changes` state to `changes` even when another lane is missing
or freshness-blocked.

No classifier is rerun, no prior state or label is reconstructed, and no
historical sidecar is created or rewritten. Existing `pitcher_changes`,
`team_summary`, `from_status`, and `to_status` remain unchanged. Arm Read and
the other unpublished What Changed categories remain separate work.
