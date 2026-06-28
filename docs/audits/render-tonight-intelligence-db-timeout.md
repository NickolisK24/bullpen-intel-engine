# Render Tonight Intelligence — DB EOF / Worker Timeout Diagnosis

> Backend / ops diagnosis pass only. No frontend change, no COIN change, no
> endpoint-contract change, no data-generation change, no UI change. This documents
> the root cause of the production 503 + worker timeout on
> `GET /api/bullpen/intelligence/tonight` and recommends the smallest safe fix.
> No code was changed in this pass (the recommended fix touches the global DB
> engine and warrants its own reviewed, tested branch).

Branch: `audit/render-tonight-intelligence-db-timeout`
Base commit: `d073363` (latest main)

## 1. Executive diagnosis

The failure is a **stale/dead pooled Postgres connection that was handed to a query
without validation**, because the SQLAlchemy engine has **no connection-pool hardening
configured at all** — no `pool_pre_ping`, no `pool_recycle`, and no
`connect_timeout` / `statement_timeout` / TCP keepalives. Render's managed Postgres
closed an idle pooled connection (idle timeout, brief network blip, or a failover);
the next request (`read_snapshot` → `.first()`) reused that dead connection and got
`psycopg2.OperationalError: SSL SYSCALL error: EOF detected`, which surfaced as a 503.

The **worker timeout** is a compounding second cause, not the same event: the app runs a
**single Gunicorn sync worker with the default 30s timeout** (`gunicorn app:app --bind …`
with no `--timeout`/`--workers`), and the Tonight snapshot for the day's slate is only
warmed by the 10:00 UTC daily job — so a 04:30 UTC request is a **cache miss** that falls
through to the **expensive synchronous Tonight build inside the request**. With no
statement/connect timeouts, a dead socket or a slow synchronous build on the lone
30s worker exceeds the limit → `WORKER TIMEOUT` → `SIGKILL` → worker reboot.

The single highest-leverage minimal fix is to add `SQLALCHEMY_ENGINE_OPTIONS`
(`pool_pre_ping=True`, a short `pool_recycle`, and connect/statement timeouts + keepalives).
That eliminates the EOF class **globally** (it also fixes the identical unguarded read on
`/intelligence/today`) and bounds any single query so a dead socket can no longer hang the
worker to SIGKILL. Two defense-in-depth follow-ups: make the snapshot read fail closed to
an honest unavailable state instead of propagating/rebuilding, and give Gunicorn an
explicit timeout + worker headroom.

## 2. Incident summary

```
2026-06-28 04:30:34 ERROR in bullpen: tonight intelligence build failed
GET /api/bullpen/intelligence/tonight → 503
  api/bullpen.py get_tonight_intelligence
    serve_tonight_cached(reference_date=reference_date)
      tonight_intelligence_snapshot.serve_tonight_cached → read_snapshot(ref) → .first()
        SELECT … FROM tonight_intelligence_snapshots
        WHERE reference_date = 2026-06-28 AND snapshot_version='tonight_v1' LIMIT 1
        psycopg2.OperationalError: SSL SYSCALL error: EOF detected
[CRITICAL] WORKER TIMEOUT → Worker exiting → SIGKILL → Booting worker (new pid)
```

The slate `2026-06-28` at 04:30 UTC had **not yet been warmed** (warm runs at 10:00 UTC),
so this date was a cache miss as well as hitting a dead connection.

## 3. Request path walkthrough

`get_tonight_intelligence` (`api/bullpen.py:1789`):
1. Resolves `reference_date` from the request (honest 400 on bad input).
2. Calls `serve_tonight_cached(reference_date=…)` inside a broad
   `try/except Exception` that logs `tonight intelligence build failed` and returns a
   **503** with an honest empty envelope (`status:'error'`, `cards:[]`,
   `empty_reason:'schedule_data_unavailable'`).

`serve_tonight_cached` (`tonight_intelligence_snapshot.py:36`):
1. `read_snapshot(ref)` → `TonightIntelligenceSnapshot.query.filter_by(...).first()`.
   - **On a dead connection this raises `OperationalError` and propagates** — the
     expensive build is *not* reached, so this path fast-fails to 503 (good), but the
     session is left needing rollback and no retry/fail-closed handling exists.
   - **On a genuine cache miss it returns `None`** → step 2.
2. On `None`, calls `serve_tonight(ref)` — the **expensive synchronous build**
   (schedule context for every team, a bullpen context per playing team, candidate
   selection, envelope shaping) **inside the request** — then best-effort persists.

So: read **failure** → 503 fast (no rebuild). Read **miss** → heavy synchronous rebuild in
the request path. Both are implicated in the incident (failure → 503; miss → worker-timeout
risk on the lone worker).

## 4. Database / session configuration findings

- `utils/db.py`: `db = SQLAlchemy()` — bare Flask-SQLAlchemy.
- `app.py:104`: `db.init_app(app)` — no engine options passed.
- `config.py`: `Config` sets only `SQLALCHEMY_DATABASE_URI` and
  `SQLALCHEMY_TRACK_MODIFICATIONS=False`; `DevelopmentConfig` / `TestingConfig` /
  `ProductionConfig` add **no `SQLALCHEMY_ENGINE_OPTIONS`**.
- **Result: defaults everywhere — no `pool_pre_ping`, no `pool_recycle`, no `pool_timeout`,
  no `connect_args` (`connect_timeout`, `statement_timeout`, keepalives).** A connection
  that Postgres has closed is never validated before use, and a hung socket has no
  client-side timeout. This is the direct cause of `SSL SYSCALL error: EOF detected`.
- Session teardown: Flask-SQLAlchemy registers an automatic `teardown_appcontext` that
  calls `db.session.remove()` per request, so sessions are removed at request end — but the
  endpoint does **not** `rollback()` on the OperationalError, and a dead connection returns
  to the pool where, without pre-ping, the next checkout can be the same dead connection.
- The only `statement_timeout` reference in the codebase is `SET LOCAL statement_timeout = 0`
  in `services/innings_backfill.py` (a batch job) — there is no global statement timeout.

## 5. Tonight snapshot cache findings

- `read_snapshot` / `write_snapshot` use `.first()` with **no `OperationalError` handling**.
- `_safe_write_snapshot` correctly wraps writes (`rollback()` + warn) — but **reads have no
  equivalent guard**, so a read EOF propagates.
- On cache miss, `serve_tonight_cached` rebuilds **synchronously in the request**.
- The snapshot is warmed by `scripts/run_tonight_refresh.py` →
  `generate_tonight_snapshot_for_date`, invoked **only** in the `0 10 * * *` daily-path step
  of `baseballos-sync.yml`. The other crons (`0 2,4,6`) run `run_postgame_refresh.py`, which
  does **not** warm Tonight. So between 00:00–10:00 UTC the current-day Tonight slate is
  **cold**, and any request in that window pays the full synchronous build.
- **Sibling risk:** `services/intelligence_surface_snapshot.py:read_snapshot` uses the same
  unguarded `.first()` pattern, so `/intelligence/today` is exposed to the identical EOF
  failure. This is **not** isolated to Tonight.

## 6. Gunicorn / Render timeout findings

- `scripts/render_start.sh` runs migrations then `exec gunicorn app:app --bind 0.0.0.0:$PORT`
  with **no `--timeout`, no `--workers`, no `--worker-class`, no `--threads`**.
- Gunicorn defaults: **1 sync worker, 30s timeout.** Implications:
  - A single in-flight request that blocks (dead DB socket with no client timeout, or a
    slow synchronous Tonight build) ties up the **only** worker and is **SIGKILLed at 30s**.
  - There is no statement/connect timeout to make the DB call fail fast *before* the 30s
    arbiter timeout, so the worker dies rather than returning an honest error.

## 7. Most likely root cause

**A stale/dead pooled SQLAlchemy connection used without `pool_pre_ping`, against Render
Postgres which closes idle connections** — producing `SSL SYSCALL error: EOF detected` on
the snapshot read and the 503. The missing connect/statement timeouts + single 30s sync
worker convert any slow or hung call (including the cold-slate synchronous rebuild) into a
worker timeout/SIGKILL.

## 8. Secondary contributing factors

1. **Cold cache in the request path** — the day's Tonight slate isn't warmed until 10:00 UTC,
   so early traffic triggers the expensive synchronous build on the request.
2. **Single 30s sync worker** — no headroom; one slow/blocked request kills the only worker.
3. **No fail-closed read handling** — a read EOF propagates (and is not rolled back at the
   endpoint); on a miss the code rebuilds synchronously rather than serving an honest
   unavailable/stale state.
4. **Identical unguarded pattern on `/intelligence/today`** — same failure mode latent there.
5. Not OOM/schema: the SQL is a single indexed `filter_by(reference_date, snapshot_version)
   LIMIT 1`; the error is a transport-level SSL EOF, not a query-plan, lock, or memory issue.
   The table/index is healthy.

## 9. Safety impact on public UI

- The endpoint already returns an **honest** envelope on failure (no stack trace leaked,
  no live-looking stale data), but with a **503** and `status:'error'` rather than a calm
  "unavailable / check back" state, and only **after** potentially burning a worker.
- The real user-facing harm is the **worker timeout/SIGKILL**: while a worker is hung and
  rebooting, *other* requests on the single worker stall — a brief site-wide hiccup, not
  just a Tonight blip. The desired behavior (fail fast + honest unavailable, no worker
  death) is not met today.

## 10. Recommended minimal fix

Smallest change that resolves the actual error class, in priority order:

1. **Add `SQLALCHEMY_ENGINE_OPTIONS` (primary — fixes the EOF globally).** In
   `ProductionConfig` (or base `Config`):
   ```python
   SQLALCHEMY_ENGINE_OPTIONS = {
       'pool_pre_ping': True,        # validate a connection before use → no EOF reuse
       'pool_recycle': 300,          # recycle below Render's idle cutoff
       'connect_args': {
           'connect_timeout': 10,
           'options': '-c statement_timeout=15000',  # 15s hard cap < gunicorn 30s
           'keepalives': 1, 'keepalives_idle': 30,
           'keepalives_interval': 10, 'keepalives_count': 5,
       },
   }
   ```
   This alone removes the `SSL SYSCALL EOF` failure on **both** Tonight and Today reads and
   bounds any query so a dead socket fails fast instead of hanging to SIGKILL.
2. **Fail closed on snapshot read error (defense-in-depth).** Wrap `read_snapshot` (Tonight
   and Intelligence Surface) so an `OperationalError` does `db.session.rollback()`, logs, and
   returns a sentinel that makes `serve_*_cached` return an **honest unavailable/stale
   envelope** (within the existing contract) **without** triggering the heavy synchronous
   rebuild on a connection-level failure.
3. **Give Gunicorn headroom (ops).** In `render_start.sh`, set an explicit
   `--timeout 60`, `--workers 2` (or `--threads`), so a single slow request can't kill the
   only worker. (Keep within Render instance memory limits.)
4. **Warm earlier (ops).** Run `run_tonight_refresh.py` on an earlier pass (e.g. add the
   Tonight warm to the `0 2,4,6` postgame step or warm on app startup) so the current-day
   slate isn't cold for early-morning traffic — removing the in-request synchronous build.

Fix #1 is mandatory and sufficient to stop the incident error; #2–#4 harden the path.
Do **not** change the public response shape — the contract already expresses empty/error.

## 11. Recommended tests

- Engine config: assert `SQLALCHEMY_ENGINE_OPTIONS` contains `pool_pre_ping=True` and a
  finite `pool_recycle` (and `connect_args` timeouts) under the production config.
- `read_snapshot` OperationalError: monkeypatch the query to raise `OperationalError`; assert
  the service rolls back, does **not** attempt the synchronous rebuild, and returns the honest
  unavailable envelope (status/empty_reason), not a propagated 500/hang.
- Endpoint: a simulated transient read failure returns the documented honest envelope (and a
  clear freshness limitation), with no stack-trace leak and unchanged response shape.
- Cache-miss build still works (regression): a cold slate with a healthy connection still
  builds and persists.
- Apply the same OperationalError read test to `intelligence_surface_snapshot`.

## 12. Recommended logging / observability

`serve_tonight_cached` already logs `served_from`, `reference_date`, `elapsed_ms`, `status`,
`card_count`. Add: `snapshot_version`; an explicit `cache_hit`/`cache_miss`/`read_error`
discriminator; the fallback path taken (`served_from=snapshot|on_demand|unavailable`); and a
one-line warn on read OperationalError with `reference_date` + `snapshot_version`. Optionally
emit `elapsed_ms` for the build step separately so cold-slate synchronous builds are visible
before they become timeouts.

## 13. Out of scope (do not build)

No new intelligence, no candidate-selection/signal/copy changes, no public response-shape
change (the contract already represents empty/unavailable), no UI change, no COIN change, no
data-generation change. No broad architecture change (no async job queue / background worker
framework) — the targeted engine-options + fail-closed read + gunicorn timeout resolve the
incident without it. No endpoint-contract change.

## 14. Whether this should go to Claude or Codex next

**Claude.** The primary fix (engine options) plus the fail-closed read semantics require
careful reasoning about the fallback path (must not rebuild on connection failure, must stay
within contract) and touch the **global** DB engine shared by every query — best done in one
tightly-scoped, well-tested branch with the regression coverage above. The Gunicorn/warm
items are small ops follow-ups that can ride along or land separately.

## 15. Exact implementation prompt (for the next pass)

> Branch `fix/db-pool-pre-ping-and-snapshot-failclosed` from latest main (author Nickolis
> Kacludis; no AI trailers). Backend reliability fix for the Render `SSL SYSCALL error: EOF
> detected` + worker timeout on `/api/bullpen/intelligence/tonight`.
> 1. Add `SQLALCHEMY_ENGINE_OPTIONS` to `backend/config.py` (production; safe defaults for
>    dev/test) with `pool_pre_ping=True`, `pool_recycle=300`, and `connect_args`
>    (`connect_timeout=10`, `options='-c statement_timeout=15000'`, TCP keepalives). Confirm
>    it flows through `db.init_app(app)`.
> 2. Harden `read_snapshot` in `services/tonight_intelligence_snapshot.py` **and**
>    `services/intelligence_surface_snapshot.py`: catch `sqlalchemy.exc.OperationalError`,
>    `db.session.rollback()`, log a warn with `reference_date`+`snapshot_version`, and signal
>    the caller to return an honest unavailable envelope **without** running the expensive
>    synchronous build on a connection-level failure. Do not change the response shape.
> 3. In `backend/scripts/render_start.sh`, set explicit `gunicorn … --timeout 60 --workers 2`
>    (verify against Render instance memory).
> 4. Move/duplicate the Tonight warm so the current-day slate is warmed before early traffic
>    (add to the `0 2,4,6` postgame step or warm at startup).
> 5. Add the tests in §11. Do not change COIN, endpoint contracts, data generation, or the UI.
> Run the full backend suite green; push; do not merge without Nickolis.

## Validation / status checks

- Branch starts from latest main (`d073363`). ✔
- No frontend implementation made (audit doc only). ✔
- No backend logic changed (diagnosis only; recommended fix deferred to its own branch). ✔
- No COIN changes. ✔
- No endpoint contract changes. ✔
- No data-generation changes. ✔
- `git diff --check` / `git diff --cached --check` clean; only the audit doc staged. ✔

## Decision

The incident is a missing-`pool_pre_ping` stale-connection EOF, compounded by a single 30s
Gunicorn sync worker and a cold-slate synchronous rebuild in the request path. It is **not**
isolated to Tonight — `/intelligence/today` shares the unguarded read pattern. The smallest
safe fix is `SQLALCHEMY_ENGINE_OPTIONS` (pool_pre_ping + recycle + connect/statement
timeouts), with fail-closed snapshot reads, an explicit Gunicorn timeout/worker headroom, and
earlier warming as hardening. No public-contract or UI change is needed. Implement on a
dedicated, tested branch — not in this audit.

ready for implementation: YES (one tightly-scoped backend branch; primary fix is low-risk).
ready to merge: this audit doc is docs-only and safe to merge; no code changed.
