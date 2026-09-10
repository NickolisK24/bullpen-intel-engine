# Readiness Freshness — Serving-Snapshot Authority (SC-03B-08)

## Symptom (production)

The daily Share Artifact batch (source snapshot 271 / sync_run 467, `product_date`
2026-07-23) reached SC-02 for all 30 teams and refused every one:

```
attempted 30  generated 0  reused 0  refused 30  failed 0  missing 0  artifacts 0
refusal: stale_snapshot x30
per team:
  blocking: stale_snapshot / insufficient_trust / unsupported_team_state
  reasons:  freshness_state:stale, data_state:stale, confidence:low,
            status_code_unsupported:data_limited
```

Snapshot 271 published under the publication-critical contract (its overall `SyncRun`
may remain `partial` when only best-effort work was deferred). Share Artifact
generation ran. Yet the shared Team Operations Readiness layer classified every team
stale / low / `data_limited`.

## Root cause (traced, not assumed)

The founder's hypothesis — that the readiness layer still couples to
`sync_status == 'partial'` — was investigated and **disproven**. There is no
`partial`→stale coupling anywhere in the readiness freshness/trust path;
`determine_freshness_state` computes `is_current` purely from dates
(`latest_workload_date >= reference − ACTIVE_WINDOW_DAYS`), and `partial` only adds
diagnostic reason codes, never forces `is_current`.

The uniform `data_state:stale` is decisive: in `team_readiness_coverage.assess_team_coverage`
that value comes **only** from the source-stale gate (`if not source_current: → low /
stale`). The coverage-insufficient paths yield `incomplete`; no-records yields
`missing`. So `data_state:stale` proves `source_current = False`, i.e. the live
`sync_status['freshness']['is_current']` was False.

The actual defect is a **reference-date mismatch** in the batch's readiness
resolution (`share_artifact_generation.resolve_team_readiness_payload`):

- Active-bullpen **membership, availability classification, and appearance-ledger
  completeness** are anchored to the *data-derived* availability reference
  (`_availability_reference_date` = latest workload date + 1) — what the pitchers'
  records actually describe.
- **Freshness `is_current`** is computed by `sync_metadata.build_sync_status_payload`
  against the *wall-clock* `product_current_date()` and the global
  `max(GameLog.game_date)`.

When the live per-pitcher game-log recompute trails the schedule/appearance authority
the serving snapshot published on (the game-log lane lagging the snapshot), the two
references diverge: membership/coverage resolve fine at the data reference, but
`is_current` is False at the wall-clock reference — so `source_current=False` forces
**every** team stale, regardless of complete coverage. The read is produced FROM the
immutable serving snapshot (id 271) but its freshness was judged by a live global
recompute that can lag that snapshot.

## Decision (founder-approved)

Anchor the freshness **verdict** of a read produced from a serving trusted snapshot to
that snapshot's authoritative `data_through`, not to a live global game-log recompute.
A published, serving, trusted snapshot has, by construction, already passed the
publication-critical + finality + appearance-ledger + freshness + provenance publish
gates; when its `data_through` is within the freshness window, the read it authorizes
is current. Per-team coverage is untouched — a team whose own active-bullpen inputs are
insufficient still degrades through the unchanged high/medium/low classifier.

## Implementation (smallest correct fix)

### One deterministic authority — `services/readiness_snapshot_freshness.py` (new)

- `serving_snapshot_freshness_authority(snapshot, reference_date=None)` → a small
  authority dict, or `None` (fail closed). Not-None **only** when the snapshot's trust
  verdict (`dashboard_snapshot.snapshot_unavailable_reason`, the same verdict SC-02
  eligibility uses) is clean AND its `data_through` is within `ACTIVE_WINDOW_DAYS` of
  the reference (default `product_current_date()`). A missing / untrusted / unpublished
  / non-serving snapshot, a missing `data_through`, a `data_through` outside the window
  (a genuinely stale snapshot), or an unreadable trust verdict all return `None`. It
  introduces no second freshness engine and no second slate authority.
- `anchor_sync_status_to_serving_snapshot(sync_status, authority)` → a copy of the
  live sync status whose freshness verdict is `current` (and whose displayed
  data-through is the snapshot's), preserving every other field (overall `partial`
  status stays honest). Identity when `authority` is `None`.

### Batch/resolver wiring — `services/share_artifact_generation.py`

- `resolve_team_readiness_payload` gains `source_snapshot=None`. It computes the
  availability reference from the **live** sync status first (membership/coverage stay
  data-anchored), then anchors only the freshness verdict to the serving snapshot when
  an authority resolves. No snapshot ⇒ unchanged conservative live freshness.
- `generate_team_state_artifact` threads the shared, already-validated `snapshot` into
  the resolver (only when the resolver accepts `source_snapshot`, so injected/legacy
  resolvers are unaffected). The batch already resolves and validates one shared
  snapshot; this reuses it.

## What still fails closed (unchanged trust)

- Publication-critical incomplete → the snapshot would be untrusted/unpublished → no
  authority → live freshness (stale) → withheld.
- Unknown / missing snapshot authority → `None` → live freshness.
- `data_through` outside the freshness window → genuinely stale → `None` → withheld.
- Non-serving / unpublished / version- or date-mismatched snapshot → `None`.
- A team's own insufficient / conflicted / incomplete active-bullpen coverage still
  yields low / incomplete / unknown through the **unchanged** coverage classifier; a
  genuine finality/ledger gap still blocks; SC-02 vocabulary, thresholds, and the
  `data_limited`/low refusals are unchanged.

## Backward compatibility

- The live `GET /api/team-operations/bullpen-readiness` path passes no snapshot →
  `source_snapshot=None` → exact prior behavior.
- Older snapshots without publication-critical/coverage metadata that are untrusted or
  out-of-window simply yield no authority → prior conservative live freshness. No
  historical artifact changes; no snapshot is mutated; no current trust gate is
  bypassed.

## Diagnostics

The anchored read carries the reason code
`current_publication_critical_serving_snapshot`; superseded stale reason codes
(`workload_data_outside_active_window`, etc.) are dropped from the anchored copy. The
overall `SyncRun` status remains visible and honest on the live sync status.

## Fresh-verification procedure

1. Run the daily sync so a fresh trusted snapshot publishes (publication-critical
   complete).
2. Confirm the post-publication Share Artifact batch reports
   `missing = 0`, `generated + reused >= 1`, `integrity_failures = 0`, and that the
   universal `stale_snapshot` refusal caused only by best-effort partial status is
   gone (remaining refusals, if any, are governed team-specific issues).
3. Verify one `team-state-1.1.0` artifact (Fresh/Stretched/Vulnerable, baseball-native
   copy, current freshness, published, integrity verified) and that the legacy Arizona
   artifact remains unchanged.

## Relationship to SC-04B / SC-05

This unblocks SC-04B production generation (SC-04B code is already in `main`). SC-05
remains blocked and is not started.
