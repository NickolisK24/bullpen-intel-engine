# Share Cards — Automatic Generation After Publication (SC-03B-02)

Immutable Team State Share Artifacts are now part of the normal BaseballOS
publication lifecycle. When a Trusted Snapshot successfully becomes the canonical
published snapshot, league-wide Team State generation runs automatically as the
next step of the same lifecycle. This is operational automation only — **not**
scheduling, a renderer, Product Intelligence, or the public Share API.

## Where generation now occurs

```
<any committed publication of a trusted snapshot>
  -> db.session.commit()                            (the publication becomes durable)
  -> run_post_commit_snapshot_publication(snapshot) (services/dashboard_snapshot.py)
       ... gate: is_published=True, status=ready
       -> _maybe_generate_team_state_artifacts_after_publication(snapshot)   (config-gated)
            -> run_post_publication_generation(snapshot)   (services/share_artifact_publication_hook.py)
                 -> generate_team_state_artifacts_batch(...)   (SC-03B-01, unchanged)
                      -> generate_team_state_artifact(...) per team   (SC-03A, unchanged)
```

Generation fires from exactly one implementation —
`run_post_commit_snapshot_publication` — always **after** the publication
transaction has durably committed, and only for a committed, published, ready
snapshot. It never fires during validation, from a withheld/pending snapshot,
from an uncommitted (flushed-but-not-committed) publish, from rendering, or from a
page/browser/public request. There is no second generation pathway.

Two legitimate committed-publication paths reach that single completion function:

- **`publish_dashboard_snapshot(snapshot, commit=True)`** — when the publication
  function owns the commit, it calls `run_post_commit_snapshot_publication`
  immediately after its own `db.session.commit()`.
- **`sync.complete_sync_run_with_snapshot`** (the daily-sync path) — it publishes
  with `commit=False` and owns the commit itself, then calls
  `run_post_commit_snapshot_publication` after that commit.

The original SC-03B-02 wiring fired only on the `commit=True` branch. The canonical
production path publishes with `commit=False`, so generation never ran in
production — see `SHARE_CARDS_AUTOGENERATION_REPAIR.md` (SC-03B-04) for the root
cause and repair.

## Why generation belongs after publication

Publication is the moment a snapshot becomes the authoritative, trusted, canonical
truth for the day. Team State artifacts are derived from that exact authority, so
generating them is the natural next step of publication — not a separate schedule
to keep in sync, and never something a browser or public request should trigger.
Hooking at the single publication choke point means every successful publication
(and only a successful publication) produces artifacts.

## Publication vs generation responsibilities

| Concern | Owner |
| ------- | ----- |
| Deciding a snapshot is trusted and publishing it | `publish_dashboard_snapshot` (unchanged) |
| Providing the authoritative source context | the just-published snapshot's `id` + `data_through` |
| Enumerating teams, per-team eligibility/publish/dedup/audit/integrity | SC-03B-01 batch + SC-03A single-team (unchanged) |
| Firing generation after a committed publication | the SC-03B-02 hook |

The authoritative context is **passed directly** — the hook reads
`snapshot.id` (→ `source_snapshot_id`) and `snapshot.data_through` (→
`product_date`) from the snapshot that was just published and hands them straight
to the batch. It rediscovers nothing. The batch's own source-authority gate then
re-confirms the current canonical published snapshot matches that id/date and is
trusted (its existing SC-03B-01 contract), which is what makes the hook safe even
though it adds no lookups of its own.

## Failure semantics

Publication is authoritative and is already committed before the hook runs.
Generation is strictly downstream, so:

- A generation failure **never** rolls back or unpublishes the snapshot. The
  snapshot remains the canonical published snapshot.
- The hook fails closed and never raises: an untrusted/mismatched source
  (`BatchSourceAuthorityError`), malformed input (`BatchValidationError`), or any
  unexpected error is logged and returns `None`. The `publish_dashboard_snapshot`
  return value is unaffected.
- Each per-team attempt remains independently transactional exactly as SC-03A
  guarantees, so a failure leaves no partial artifact behind. Operational failure
  detail (per-team `failed`/`refused`, `missing` teams, counts) is available in
  the `BatchGenerationResult` the hook logs, ready for later operator tooling.

## Idempotent reruns

If the same authoritative snapshot is published/processed again, batch generation
safely reuses the already-published artifacts through the existing SC-01
deduplication: the rerun reports `reused` (not `generated`), creates no duplicate
artifacts, no duplicate publication, and no duplicate intelligence.

## Enablement

Automatic generation is enabled by default in the real application
(`create_app` sets `SHARE_ARTIFACT_AUTOGENERATION_ENABLED`, overridable via the
`SHARE_ARTIFACT_AUTOGENERATION` env var). This is an operational on/off switch,
**not** a scheduler. The flag is intentionally absent from bare-Flask unit apps,
so existing publication tests are unaffected.

## Downstream distribution

Share Artifact generation remains part of the post-commit publication lifecycle
described above. Static route delivery is separate: after a Render daily/postgame
publication advances, the due-window coordinator requests the GitHub generated-
content job for that exact snapshot. That job reads the immutable artifacts,
exports `/team/**` and `/share/**`, validates/builds the tree, and fast-forward
publishes only those generated paths. Its distribution-only manual retry never
reruns generation, synchronization, or snapshot publication.

## Deferred to later branches

- Operator dashboard / monitoring surfaces over the batch coverage summary and
  generation audit.
- The public Share API, `/share/{public_id}`, renderer replacement, PNG/Open
  Graph rendering, and Product Intelligence — all still out of scope.
