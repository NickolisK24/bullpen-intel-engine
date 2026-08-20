# Prospective frozen Arm Read delta substrate

Status: approved for prospective comparison authority only.

Public Arm Read cannot be reconstructed safely from historical availability
statuses. Evidence freshness and trust, roster authority, represented date,
and active-bullpen population also govern the reader-facing result. Historical
Team Board snapshots do not stamp those inputs with a compatible public-read
contract, so availability strings must not be mapped or recomputed after the
fact.

Beginning prospectively, a newly published immutable Team State Share Artifact
may carry Arm Read records in its existing `team_board_delta` sidecar. The
publication readiness cycle supplies the already-classified canonical active
bullpen; the canonical `pitcher_public_labels` owner projects and freezes each
available record's stable public key and exact public label. The Arm Read method
stamp is the compatibility boundary for governed availability, evidence,
roster, and public-label semantics and must advance when those meanings change.
The sidecar also records pitcher/team/date identity, public-read method and
contract versions, population and roster-authority versions, evidence state,
reference-date policy, and explicit population members without a frozen record.

Two frozen Arm Read domains are comparable only when envelope, team, ordered
represented dates, publication source identity, trust, public-read method and
contract versions, and population-authority semantics match. Individual arms
compare only when the pitcher belongs to both frozen populations and both
frozen records exist. Added or removed arms have no invented endpoint.
Movement exists only when the stable public-read key changes; an internal
availability change such as `Limited` to `Avoid` produces no movement when both
frozen public reads are `Limited Rest`.

`Limited Read` is a governed public Arm Read and is frozen and compared by its
stable key like every other read. It is distinct from a population member whose
record is missing, an absent snapshot, an incompatible comparison, and the
public `Unavailable` read.

This extension is append-only and prospective. It does not backfill, mutate, or
recompute historical snapshots. Older sidecars remain `not_yet_comparable` for
Arm Read while their existing Team State comparison remains valid. The public
`/changes` response, its legacy status transitions, and Team Board presentation
remain unchanged. Gap #29 stays blocked until two naturally created compatible
prospective endpoints exist, a read-only comparison certification succeeds,
and a separate public-contract migration is approved.
