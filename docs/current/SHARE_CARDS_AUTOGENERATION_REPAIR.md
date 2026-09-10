# Share Cards — Production Autogeneration Diagnosis & Publication-Path Repair (SC-03B-04)

## Symptom (production)

Trusted snapshot 205 (`product_date` 2026-07-23, published ~2026-07-24 04:08 ET)
showed automatic generation **Enabled** on the operator surface but with:

```
Accounted = 0   Generated = 0   Reused = 0   Refused = 0   Failed = 0   Missing = 30
recent generation attempts = 0   recent artifacts = 0
```

The snapshot published successfully, yet the Share Artifact batch created **not
even a single generation audit attempt**. Zero attempts — not zero *successes* —
is the tell: the post-publication generation hook was never invoked at all.

## Root cause

The canonical production publication path does **not** publish with `commit=True`.

The daily sync runs `scripts/run_daily_sync.py` → `services.sync.run_daily_sync`
→ `services.sync.complete_sync_run_with_snapshot`, which publishes the trusted
snapshot with:

```python
snapshot = build_bullpen_dashboard_snapshot(publish=True, commit=False, ...)
...
db.session.commit()   # the sync path owns the commit itself
```

The SC-03B-02 post-publication generation hook, however, fired only inside
`publish_dashboard_snapshot` **on the `commit=True` branch**:

```python
# pre-repair
if commit and snapshot.is_published and snapshot.status == SNAPSHOT_STATUS_READY:
    _maybe_generate_team_state_artifacts_after_publication(snapshot)
```

Because the production path publishes with `commit=False` and commits externally,
that branch was never taken. Generation was therefore never invoked in production:
zero audit attempts, zero artifacts, all 30 teams `missing`. This matches failure
boundary #2 — *"the snapshot publication call does not use `commit=True`."*

Config was ruled out: both the web process and the daily-sync script import the
single module-level `app = create_app()` from `app.py`, so they resolve one
identical `SHARE_ARTIFACT_AUTOGENERATION_ENABLED` flag, enabled by default. The
operator surface correctly showed "Enabled" — the flag was on; the hook just never
ran on the `commit=False` path. The defect was purely the `commit=True`-only gate,
not configuration.

## Repair (smallest correct fix)

One canonical post-commit completion function owns the "publication has durably
committed → attempt generation" step, and every legitimate committed-publication
path calls it after its own commit. No hook logic is duplicated; there is exactly
one completion implementation and one generation pathway.

`services/dashboard_snapshot.py`:

```python
def run_post_commit_snapshot_publication(snapshot):
    """Canonical post-commit publication completion. Call exactly once, AFTER the
    publication transaction has committed, from every committed-publication path."""
    if snapshot is None or not getattr(snapshot, 'is_published', False):
        return
    if getattr(snapshot, 'status', None) != SNAPSHOT_STATUS_READY:
        return
    _maybe_generate_team_state_artifacts_after_publication(snapshot)
```

- `publish_dashboard_snapshot(commit=True)` calls it right after its own
  `db.session.commit()`.
- `sync.complete_sync_run_with_snapshot` (publishes `commit=False`, owns the
  commit) calls it right after its own `db.session.commit()`.

This preserves every invariant: one canonical publication choke point; SC-03B-01
as the sole batch service; SC-03A audit as the sole audit; idempotent reuse;
fail-closed source authority; independently-transactional per-team attempts; and
publication-before-generation ordering with **no rollback of a valid snapshot when
generation fails** (the completion runs strictly after commit and never raises).

## Call path (after repair)

```
scripts/run_daily_sync.py  ->  from app import app  (the single create_app instance)
  -> services.sync.run_daily_sync(app)
    -> services.sync.complete_sync_run_with_snapshot(...)
         build_bullpen_dashboard_snapshot(publish=True, commit=False)  # publishes, no commit
         run.stage = STAGE_PUBLISHED
         db.session.commit()                                           # publication durable
         run_post_commit_snapshot_publication(snapshot)                # <-- SC-03B-04 repair
           -> _maybe_generate_team_state_artifacts_after_publication(snapshot)  (config-gated)
             -> run_post_publication_generation(snapshot)   (SC-03B-02 hook, unchanged)
               -> generate_team_state_artifacts_batch(...)  (SC-03B-01, unchanged)
                 -> generate_team_state_artifact(...) per team  (SC-03A, unchanged)
```

## Config authority

`create_app` in `app.py` is the **sole** site that maps the environment variable
to the config flag:

```python
app.config['SHARE_ARTIFACT_AUTOGENERATION_ENABLED'] = (
    os.environ.get('SHARE_ARTIFACT_AUTOGENERATION', 'true').lower()
    in ('1', 'true', 'yes')
)
```

- **Absent** → enabled (default; an operational off-switch, not a scheduler).
- `1` / `true` / `yes` (any case) → enabled.
- `false` / `0` / `no` / empty → disabled.
- Anything unrecognized → **fail-safe disabled**.

Web and daily-sync share this one authority (both import the module-level
`app = create_app()`); there is no second, sync-only config path. The operator
overview reads the identical flag via `share_artifact_operations.autogeneration_enabled()`,
so what the operator sees ("Enabled"/"Disabled") is exactly what the hook gates on.

## Hook skip / failure semantics & log messages

`_maybe_generate_team_state_artifacts_after_publication` emits a structured
decision on every committed publication and never raises:

- **Disabled** (flag off / no app context):
  ```
  Post-publication generation hook_skipped snapshot_id=<id> product_date=<date>
    automatic_generation_enabled=False reason=autogeneration_disabled.
  ```
- **Invoked** (flag on):
  ```
  Post-publication generation hook_invoked snapshot_id=<id> product_date=<date>
    automatic_generation_enabled=True.
  ```
- **Downstream generation failure** (batch/hook raised): logged via
  `logger.exception("Post-publication Team State generation hook failed
  non-fatally snapshot_id=<id>.")` and swallowed — the committed, authoritative
  publication is never disturbed.

A withheld/pending/None snapshot is a silent no-op in
`run_post_commit_snapshot_publication` before any logging (it was never a
published-ready snapshot).

## Regression coverage (fails before the repair, passes after)

`backend/tests/test_share_artifact_autogeneration_repair.py`:

- `test_sync_completion_triggers_generation_after_commit` — the exact production
  symptom: `complete_sync_run_with_snapshot` commits a trusted snapshot and must
  invoke the canonical completion **exactly once** after commit. **Fails before the
  repair** (sync path never invoked generation); passes after.
- Post-commit completion guards: fires for committed+published+ready; no-op for
  withheld / pending / `None`; gated off when the flag is absent; never raises when
  generation explodes.
- `test_publish_dashboard_snapshot_commit_true_still_fires_once` — the original
  `commit=True` path still fires exactly once (no double-fire).
- Config authority: `create_app` env-var matrix (default enabled; affirmatives
  enable; negatives/empty/unrecognized fail safe to disabled); web and daily-sync
  resolve one authority; the operator overview reports the same flag.

`backend/tests/test_share_artifact_operations.py`:

- `test_zero_attempts_with_autogeneration_enabled_is_not_healthy` — reproduces the
  operator-surface reading of the symptom: autogeneration Enabled + zero attempts
  for every team ⇒ status `incomplete` (never `complete`/`disabled`), accounted=0,
  missing = team count. The surface never reports the zero-attempt state as healthy.

## Deployment verification procedure (run after this branch deploys)

1. Confirm the flag is on in the deployed environment: `SHARE_ARTIFACT_AUTOGENERATION`
   unset or set to a truthy value → operator overview shows automatic generation
   **Enabled**.
2. Let the next daily sync publish a trusted snapshot (or trigger the sync job).
3. In the deploy logs, confirm the decision line for that snapshot:
   `Post-publication generation hook_invoked snapshot_id=<new id> product_date=<date>
   automatic_generation_enabled=True.` (Its **absence**, or a `hook_skipped ...
   reason=autogeneration_disabled` on an enabled environment, means the path did not
   run — investigate before proceeding.)
4. Load the internal operator surface (`/internal/share-artifacts/operations`) for
   the new snapshot and confirm **Accounted = 30, Missing = 0** (generated + reused
   + refused + failed = 30; refusals/failures are accounted, not missing), status
   `complete` or `complete_with_refusals`, and non-zero recent generation attempts /
   recent artifacts.

## Controlled backfill procedure for snapshot 205 (NOT executed here)

Snapshot 205 published before this repair, so it has zero attempts. Backfilling it
requires production credentials, which are **not available in this environment** —
so no backfill was performed and no cards were manually created (the failure is not
hidden; it is fixed on the automatic path). When ready, run the backfill against
production through the **existing** SC-03B-01 batch service on the **existing**
internal admin boundary — never a browser/page/public path, and never by hand-
authoring cards:

1. Confirm snapshot 205 is still the latest trusted published snapshot (source
   authority); if a newer trusted snapshot exists, backfill that one instead.
2. Invoke the admin-token batch endpoint
   (`POST /api/internal/share-artifacts/team-state/batch` on
   `share_artifacts_admin_bp`, `X-Admin-Token`) with the authoritative
   `source_snapshot_id` + `product_date` in the JSON body (an optional `team_ids`
   subset is supported). This is the full-league batch route that delegates to the
   SC-03B-01 `generate_team_state_artifacts_batch` service — not the single-team
   `/team-state/generate` route. The batch's own source-authority gate re-confirms
   the canonical snapshot (a globally invalid source is refused 409 before any team
   is attempted); idempotent reuse means re-runs report `reused`, create no
   duplicates, and never double-audit. This admin blueprint is registered only at
   `/api/internal/share-artifacts` and is never reachable from the browser operator
   page (which uses the separate read-only `/api/internal-browser/share-artifacts`
   boundary).
3. Verify on the operator surface: **Accounted = 30, Missing = 0** for that
   snapshot, integrity `verified`, status `complete` / `complete_with_refusals`.

## How to confirm Accounted = 30 / Missing = 0

On the operator overview for the target snapshot:
`generated + reused + refused + failed == 30` (canonical team count) and
`missing == 0`. Refused and failed teams are **accounted** (a governed terminal
decision was reached) — only a team with no terminal attempt *and* no equivalent
published artifact for this same authority is missing. The accounting invariant
`canonical_team_count == generated + reused + refused + failed + missing` is
enforced server-side and fails closed.

## Production verification status

Production verification was **not performed** — this environment has no production
database or credentials, and the operator surface cannot be read here. The repair
is verified by the regression suite (the reproduction test fails pre-repair, passes
post-repair) and by tracing the single production call path. Verification in
production must be completed using the procedure above before relying on automatic
coverage for a given day.

## Scope

SC-04 remains blocked until this repair is verified in production (a
`hook_invoked` log for a freshly published trusted snapshot and Accounted = 30 /
Missing = 0 on the operator surface). This branch does not begin SC-04, adds no
browser/page/public generation trigger, and does not hide the failure by manually
creating cards.
