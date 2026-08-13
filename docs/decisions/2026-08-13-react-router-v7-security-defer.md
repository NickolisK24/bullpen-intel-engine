# Decision: Time-Boxed Acceptance of the Residual React Router Advisories

- **Date:** 2026-08-13
- **Status:** Accepted, time-boxed. Expires **2026-11-13**.
- **Scope:** Frontend runtime dependency risk only (#601 Slice C). NOT a routing
  redesign, NOT an SSR adoption, and NOT a change to any public vocabulary,
  ranking, evidence boundary, or generated-content path.
- **Risk owner:** Nickolis Kacludis
- **Tracking issue:** #645 — [Security] Migrate frontend routing to React Router v7
- **Parent issue:** #601

## Context

#601 Slice C remediated the frontend production dependency advisories that could
be removed safely today:

- `recharts` and `clsx` were declared but had zero import sites anywhere in the
  frontend. Removing them deleted the only **high**-severity production advisory,
  because `lodash` (GHSA-r5fr-rjxr-66jc, GHSA-f23m-r3pf-42rh) entered the graph
  solely through `recharts`. No override was added; the dependency that carried
  the advisory was deleted instead.
- `react-router-dom` was patched 6.30.3 → 6.30.4, which resolves
  `@remix-run/router` to 1.23.3 and clears GHSA-2j2x-hqr9-3h42.

`npm audit --omit=dev` went from 4 advisory rows (3 moderate, 1 high) to 2 rows
(2 moderate). This decision covers what remains.

## The residual advisories

Three advisory IDs across two package rows, all React Router family, all at the
post-patch versions `react-router-dom` 6.30.4 / `react-router` 6.30.4:

| Advisory | Package | Class |
|---|---|---|
| GHSA-wrjc-x8rr-h8h6 | react-router | Open redirect via backslash in `<Link>` and `useNavigate` (CVE-2025-68470 bypass) |
| GHSA-jjmj-jmhj-qwj2 | react-router-dom | Open redirect leading to XSS |
| GHSA-337j-9hxr-rhxg | react-router | Arbitrary constructor injection via `deserializeErrors()` in SSR hydration |

**None has a fix in the 6.x line.** npm's only offered remediation is
`react-router-dom@7.18.2`, a breaking major version.

React Router is genuinely shipped: `@remix-run/router` is present in the emitted
production bundle. This is not a build-only dependency, and the acceptance below
is not "it isn't really installed."

## Applicability to BaseballOS

### GHSA-337j-9hxr-rhxg — not applicable

The advisory is SSR-hydration-scoped: `deserializeErrors()` runs when a
server-rendered error payload is hydrated on the client.

BaseballOS is a client-only Vite SPA:

- `src/App.jsx` uses `<BrowserRouter>`;
- `src/main.jsx` uses `ReactDOM.createRoot(...)`, **not** `hydrateRoot`;
- there is no `createBrowserRouter`, no `RouterProvider`, no loader or action,
  and no server rendering in the application entry path;
- `frontend/vercel.json` serves a static SPA and rewrites unknown paths to
  `index.html`.

The vulnerable code path does not exist in this application. Version-range
membership alone does not make it exploitable.

### GHSA-wrjc-x8rr-h8h6 and GHSA-jjmj-jmhj-qwj2 — applicable in principle, bounded in practice

Both are open-redirect classes reached when a navigation target derived from
untrusted input begins with `//` (protocol-relative) or `\` (backslash).

Every navigation target in the frontend was reviewed for this decision:

- all `<Link to>` targets are string literals or values built internally from
  application data (`link.to`, `story.href`, `card.href`, `view.ctaHref`,
  `entry.teamHref`);
- all `useNavigate()` calls in `Bullpen.jsx` pass hrefs produced by
  `buildTeamBoardHref`, `buildComparisonHref`, `buildAllPitchersHref` and
  `buildPitcherHref`;
- `<Navigate to={redirectTo}>` in `App.jsx` reads `redirectTo` from the static
  `APP_ROUTES` array;
- there is no `redirect(...)`, no `window.location` assignment, and no
  `location.assign` / `location.replace` in `src/`.

**The only URL-derived navigation sink is `VerifySignIn.jsx`**, where
`searchParams.get('next')` reaches `navigate()`.

## Compensating control

`safeVerifyRedirect()` in `frontend/src/components/auth/VerifySignIn.jsx`:

```js
export function safeVerifyRedirect(next, fallback = '/') {
  const value = String(next || '').trim()
  if (!value) return fallback
  if (!value.startsWith('/') || value.startsWith('//') || value.startsWith('/\\')) {
    return fallback
  }
  return value
}
```

It rejects empty input, anything not beginning with `/`, the protocol-relative
`//` form, and the `/\` backslash form — precisely the two published attack
shapes — and it trims before checking, so leading whitespace cannot smuggle a
prefix past the test.

### Regression test protecting the control

`frontend/tests/signInFlow.test.mjs` now enforces this contract explicitly, under
a comment naming this record. Four tests cover:

- **refused:** `//evil.example`, `//evil.example/path`, `/\evil.example`,
  `/\/evil.example`, `\\evil.example`, `https://evil.example`,
  `http://evil.example`, `HTTPS://evil.example`, `evil.example`,
  `javascript:alert(1)`, and a leading-whitespace `   //evil.example`;
- **preserved unchanged:** `/`, `/today`, `/bullpen`, `/dashboard`, `/stories`,
  `/auth/verify`, `/bullpen?view=pitchers`, `/stories?team=ACE`, `/team/NYY`;
- absent/blank input falling back;
- an explicit non-default fallback being honoured for refused input.

**If those tests are deleted or weakened, this acceptance is void.** Widening the
guard is a security decision, not a refactor.

## Why immediate upgrade is deferred

The v7 migration was attempted and measured in an isolated copy of `frontend/`
outside the repository, not estimated:

- `npm run build` **succeeds** (138 modules);
- `npm audit --omit=dev` **clears both react-router advisories**;
- `npm test` **fails — 36 entire test files fail at module load**, with only 429
  of 920 tests collected.

Error class:

```
SyntaxError: [vite] Named export 'Link' not found. The requested module
'react-router-dom' is a CommonJS module, which may not support all
module.exports as named exports.
```

The frontend test harness renders components through Vite's SSR module loader —
each `tests/*.test.mjs` calls `server.ssrLoadModule('/src/components/.../X.jsx')`.
React Router v7's CJS packaging does not expose named exports through that path.

The standard remedy was tried and **did not work**: adding
`ssr: { noExternal: ['react-router', 'react-router-dom'] }` to `vite.config.js`
in the trial copy changed the failure to `ReferenceError: module is not defined`
rather than resolving it.

Remediation therefore requires reworking how ~36 test files load modules, at a
cost that is not currently bounded. Forcing that into a dependency-security slice
would have mixed an unscoped test-harness migration into unrelated work and put
the whole frontend suite at risk. The migration is tracked separately as #645.

## Acceptance

BaseballOS accepts the residual risk of GHSA-wrjc-x8rr-h8h6,
GHSA-jjmj-jmhj-qwj2 and GHSA-337j-9hxr-rhxg on `react-router` /
`react-router-dom` 6.30.4 until **2026-11-13**, on the basis that the SSR
advisory is inapplicable to this client-only SPA and the open-redirect classes
are bounded at the single reachable sink by `safeVerifyRedirect()` and its
regression tests.

This is not a permanent suppression and no blanket ignore rule was created.

Since #601 Slice D this acceptance is machine-enforced. `.github/dependency-audit-accepted.json`
carries the three advisory ids, their packages, this expiry, the tracking issue
and a reference back to this record, and the `dependency-audit` CI job refuses
the build when an advisory here is unknown, expired, attributed to a different
package, duplicated, missing metadata, or no longer reported by npm — that last
case forcing the exception to be deleted once the risk is gone rather than left
behind. The substance of the decision below is unchanged; CI now checks it
instead of relying on someone remembering the date.

## Revisit conditions

This acceptance ends early if **any** of the following occur:

1. A React Router 6.x release fixes GHSA-wrjc-x8rr-h8h6 or GHSA-jjmj-jmhj-qwj2.
2. A new navigation target is derived from `location`, search params,
   `postMessage`, or an API response without `safeVerifyRedirect()` or an
   equivalent validation.
3. BaseballOS adopts SSR, hydration, `RouterProvider` / data-router framework
   mode, or server rendering — this makes GHSA-337j-9hxr-rhxg applicable
   immediately.
4. The frontend test harness changes such that React Router v7 no longer hits the
   module-load blocker recorded above.
5. Any of the three advisories has its severity revised upward.
6. A materially different exploit path is published for any of them.
7. **2026-11-13 is reached.**

## Scope

No backend change. No dependency-audit CI gate (Slice D). No React Router v7
installation. No Lodash override or direct pin. No Vite, PostCSS, esbuild, Babel,
nanoid or picomatch change — those are dev/build-only advisories outside the
`npm audit --omit=dev` acceptance view for #601 and remain deferred. No change to
`.github/workflows/baseballos-sync.yml`, generated-content publication, D-051,
D-052, D-053, or Vercel configuration.
