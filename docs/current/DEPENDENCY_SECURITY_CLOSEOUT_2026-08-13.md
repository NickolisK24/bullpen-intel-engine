# Dependency Security Closeout — DEP-001 (#601)

**Status:** Current dependency-security boundary
**Owner:** Nickolis Kacludis
**Effective:** August 13, 2026
**Repository basis:** `main` at `e3ad8bdf47a0bf6209917051df2070fba8eff417`
**Verification:** CI run `31729458591` — SUCCESS

This file records the dependency-security state BaseballOS actually operates
under today, and the standing obligations that outlive the issue. It is a
current boundary statement, not an audit. The point-in-time evidence produced
along the way stays where it was written and is not restated here as if it were
current.

DEP-001 (#601) closed August 13, 2026 across four bounded slices. It changed no
baseball semantics, no publication gate, no source authority, and no
game-driven authority posture.

## 1. What the boundary is now

### Backend runtime

`pip-audit -r backend/requirements.txt --strict` reports **no known
vulnerabilities**.

The advisory-bearing packages on the production request/startup path were
upgraded in one reviewed pass:

| Package | Before | After |
|---|---|---|
| Flask | 3.0.0 | 3.1.3 |
| Flask-CORS | 4.0.0 | 6.0.5 |
| gunicorn | 21.2.0 | 23.0.0 |
| requests | 2.31.0 | 2.34.2 |
| python-dotenv | 1.0.0 | 1.2.2 |

CORS behaviour was pinned by regression tests **before** the upgrade, then
re-verified after it. The allowlist in `backend/app.py` is unchanged and
`supports_credentials` is still not enabled — credentials were never turned on,
which is what bounded the Flask-CORS advisory class in the first place.

### Test dependencies are no longer production dependencies

`pytest` no longer ships to production. `backend/requirements.txt` is the
runtime set; `backend/requirements-dev.txt` pulls that set in and adds `pytest`
on top, so a development environment is a superset of production rather than a
different resolution.

- production and operational workflows: `pip install -r backend/requirements.txt`
- local development and test jobs: `pip install -r backend/requirements-dev.txt`

Nothing under `backend/` imports `pytest` outside `backend/tests/`.

### Frontend production

`recharts` and `clsx` were declared but had zero import sites. Removing them
deleted the only **high**-severity production advisory, because `lodash` entered
the graph solely through `recharts`. No override and no direct pin was added —
the dependency carrying the advisory was deleted instead.

`react-router-dom` was patched to **6.30.4**, which resolves `react-router`
to 6.30.4 and `@remix-run/router` to 1.23.3.

## 2. The residual risk, and when it expires

Three advisories remain in `npm audit --omit=dev`, all React Router family, all
at the post-patch versions:

| Advisory | Package |
|---|---|
| GHSA-wrjc-x8rr-h8h6 | `react-router` |
| GHSA-jjmj-jmhj-qwj2 | `react-router-dom` |
| GHSA-337j-9hxr-rhxg | `react-router` |

None has a fix in the 6.x line; npm's only offered remediation is a breaking
major version. The reasoning, the applicability analysis, and the compensating
control are recorded in
[`docs/decisions/2026-08-13-react-router-v7-security-defer.md`](../decisions/2026-08-13-react-router-v7-security-defer.md).

**This is an accepted risk with a hard expiry, not a suppression.**

- Expiry: **2026-11-13**. The acceptance is invalid from **00:00 UTC on
  2026-11-13** — that date is the first refused day, not the last accepted one.
- Tracking issue: **#645** — migrate frontend routing to React Router v7.
- The migration is blocked on the frontend test harness, not on the router: v7's
  CommonJS packaging does not expose named exports through Vite's SSR module
  loader, which is how every `frontend/tests/*.test.mjs` file loads components.

The compensating control is `safeVerifyRedirect()` in
`frontend/src/components/auth/VerifySignIn.jsx`, guarding the only URL-derived
navigation sink in the application. Its regression tests live in
`frontend/tests/signInFlow.test.mjs`.

**If those tests are deleted or weakened, the acceptance is void.** Widening the
guard is a security decision, not a refactor.

## 3. The standing CI control

The `dependency-audit` job in `.github/workflows/ci.yml` runs on every CI
invocation and audits both runtime surfaces.

- **Backend** is audited in requirements-file mode against
  `backend/requirements.txt` with a pinned scanner, so the job measures declared
  production dependencies rather than the runner's virtualenv furniture.
- **Frontend** production findings are checked against
  `.github/dependency-audit-accepted.json` by
  `backend/scripts/verify_dependency_audit.py`.
- **Dev/build** advisories are reported as information only and never gate the
  build. They must never appear in the accepted-risk file.

The gate refuses the build when a production advisory is:

- unknown — reported but not reviewed;
- expired — past its `expires_on`;
- stale — accepted but no longer reported, so a solved advisory's exception must
  be **deleted** rather than left behind to silently suppress a recurrence;
- mismatched — accepted for a different package than npm attributes it to;
- duplicated — listed more than once;
- under-documented — missing an advisory id, package, expiry, tracking issue, or
  a decision record that actually exists in the repository.

A scanner or network failure is distinguished from a clean audit and does not
pass silently.

The gate is **read-only**. It never upgrades, pins, or edits a dependency, and
there is no auto-merge or auto-upgrade path. It reports and refuses; a human
decides what to do.

Its behaviour is covered by `backend/tests/test_dependency_audit_gate.py`,
which tests the evaluator directly and asserts the workflow contract, so the job
cannot be quietly weakened without a failing test.

## 4. What this did not change

DEP-001 touched dependencies, CI, and documentation only. All of the following
are exactly as they were:

- the daily game-driven lane remains **shadow**;
- the postgame game-driven lane remains **shadow**;
- backfill remains **off by default**;
- the legacy sync/postgame path remains **authoritative** for baseball-data
  mutation;
- broader game-driven write authority remains **unapproved**;
- game-driven publication-authority transfer remains **unapproved**;
- D-051, D-052, and D-053 are unchanged;
- no application code, runtime configuration, production data, publication gate,
  threshold, vocabulary, or model behaviour changed.

## 5. Standing obligations

1. Before **2026-11-13**, either complete #645 or re-review the acceptance. CI
   turns red on that date whether or not anyone remembers.
2. When an accepted advisory is remediated, **delete** its entry from
   `.github/dependency-audit-accepted.json`. A stale entry is a gate failure by
   design.
3. Keep `safeVerifyRedirect()` and its regression tests intact for as long as the
   acceptance stands.
4. Install `backend/requirements-dev.txt` — never `requirements.txt` plus an ad
   hoc `pytest` — in any job that collects or runs the backend suite.

## 6. Evidence

| Item | Reference |
|---|---|
| Issue | #601 — [High][DEP-001] |
| Backend request-path remediation | PR #643 |
| Test/runtime dependency separation | PR #644 |
| Frontend runtime remediation | PR #646 |
| CI dependency-audit gate | PR #647 |
| Deferred router migration | Issue #645 |
| Post-merge CI on `main` | Run `31729458591` — SUCCESS at `e3ad8bd` |
| Accepted-risk decision record | `docs/decisions/2026-08-13-react-router-v7-security-defer.md` |
| Machine-enforced contract | `.github/dependency-audit-accepted.json` |
