# Tonight v1 legacy retirement (TN-11)

## Outcome

The legacy frontend Home tree is deleted: Home, Intelligence Surface, Daily
Edition, Since Yesterday rail and legacy Tonight rail. Every deletion is
dependency-proven.

The legacy Tonight v5 backend is retained for compatibility (Outcome B),
because it still has live operational and public-API consumers.

There is no backend code change, no migration, no schema change, and no change
to current Tonight v1 behavior.

## Dependency audit

Classes: A = live production consumer, B = test-only, C = dormant/dead,
D = compatibility-only, E = unclear.

| Item | References before TN-11 | Class | Action |
| --- | --- | --- | --- |
| `frontend/src/components/home/Home.jsx` | Unrouted since TN-10. Consumers: tests only (`pageHierarchyDedupe`, `privatePosts`, `teamBoardStoryRetirement`, `tonightRootCutover`) | C, with B tests | Deleted |
| `frontend/src/components/home/IntelligenceSurface.jsx` (2,693 lines; contains the Home-only view builders `getDailyEditionView`, `getSinceYesterdayView`, `getBullpenPictureView`, `getTonightCards`, `getTonightGames`) | Only `Home.jsx` in `src`. Tests: `intelligenceSurface`, `mobileNavigation`, `dataThroughAuthority`, `publicSurfaceDelivery`, `navigationRoutes`, `canonicalEvidenceLinks`, `publicCopyPassThrough`, `vocabularyFreshnessContract`. Backend governance tests: `test_product_roadmap_current_state`, `test_editorial_voice_inventory_e2a`, `freeze_policy` (path list only) | C, with B tests | Deleted |
| `getHomeProjection` (`api.js`) | Only IntelligenceSurface; tests | C | Deleted |
| `getTodayIntelligence` (`api.js`) | Only IntelligenceSurface; tests | C | Deleted |
| `getTonightIntelligence` (`api.js`, the frontend v5 client) | Only IntelligenceSurface; tests | C | Deleted |
| `signupAudience` (`api.js`) | Only IntelligenceSurface (the Home signup form); tests | C | Deleted. The backend `/audience/signup` is untouched. |
| `frontend/src/utils/sinceYesterdayArtifact.js` | Only IntelligenceSurface; `sinceYesterdayArtifact.test.mjs`; `freeze_policy` path list | C | Deleted |
| `getSinceYesterdayShareArtifact` (`api.js`) | Only `sinceYesterdayArtifact.js` | C | Deleted. The backend share-card route is untouched. |
| `frontend/src/components/dashboard/bullpenLandscapeView.js` | No `src` consumer after Home is deleted, but four contract test files (`dashboardStorylines`, `landscapeTeamDrilldown`, `canonicalEvidenceLinks`, `vocabularyFreshnessContract`) pin its Landscape publication-authority behavior | E (dormant, but with governed contract tests) | Retained; flagged for a later decision |
| Shared imports of the Home tree: `Freshness`/UI kit, `Disclosure`, `EvidenceShareMenu`, `syncStatusView`, `evidenceLinks`, `useFetch`, `dateDisplay`, `getTeams` | Used by Dashboard, Stories, Team Board, Trust, Compare and Tonight | A | Kept |
| Backend `tonight_v5` (default `GET /api/bullpen/intelligence/tonight`, `trusted_tonight_view`, `tonight_intelligence_service`, `tonight_intelligence_snapshot`, `TonightIntelligenceSnapshot` model and table) | See below | A / D | Retained |
| Backend `/api/bullpen/intelligence/today` and `IntelligenceSurfaceSnapshot` | Built by the publication pipeline; public endpoint | A / D | Retained |

## Why v5 is retained (Outcome B)

Live consumers still exist:

1. **Scheduler:** `services/sync_due.py` calls
   `schedule_tonight_refresh.refresh_schedule_and_tonight`, which builds v5
   snapshots on every due sync. `scripts/refresh_slate_schedule.py` does the
   same.
2. **Publication pipeline:** `continuous_production_publication._refresh_tonight`
   and `intraday_repair.refresh_tonight_after_publication` both generate v5
   snapshots. `incremental_read_model_rebuild` also references the v5
   snapshot.
3. **Public API default:** `GET /api/bullpen/intelligence/tonight` (no contract,
   or `contract=tonight_v5`) serves v5 through `trusted_tonight_view`. It is an
   unauthenticated public endpoint, so the absence of external callers cannot
   be proven from the repository.
4. **Test and rehearsal coverage:** `test_tonight_intelligence_snapshot`,
   `test_tonight_authority_hardening`, `test_trusted_publication_rehearsal` and
   the `freeze_policy` guards cover the v5 behavior.

Retiring v5 would therefore mean a broad backend refactor of the scheduler, the
publication pipeline and intraday repair, plus a public-contract change. That
is a stop condition for this package.

The frontend is now v5-free:

- `getTonightIntelligence` is deleted.
- The only Tonight client is `getTonightV1()`, which is unchanged and requests
  `?contract=tonight_v1`.
- Browser tests assert exactly one Tonight request with that exact URL.

## Endpoint behavior after TN-11 (unchanged)

| Request | Behavior |
| --- | --- |
| `GET /api/bullpen/intelligence/tonight?contract=tonight_v1` | Stored publication-bound v1 edition with the TN-03 overlay |
| `GET /api/bullpen/intelligence/tonight` or `?contract=tonight_v5` | Legacy v5 (compatibility) |
| Any other `contract` value | 400 |
| `GET /api/bullpen/intelligence/today` | Legacy lead story (compatibility) |

## Database

No migration was added and no schema changed. The
`tonight_intelligence_snapshots` and `intelligence_surface_snapshots` tables
remain because live code writes to them.

## Pageview vocabulary

The root pageview surface is still named `today`. That vocabulary is validated
by the backend (`services/traffic_measurement.py`), so renaming it is not an
isolated frontend change. It is left for a later coordinated package.

## Tests

Deleted, because they only tested retired code:

- `frontend/tests/intelligenceSurface.test.mjs`
- `frontend/tests/sinceYesterdayArtifact.test.mjs`
- two Home-only first-use entry-area tests in `mobileNavigation.test.mjs`
- the Today entry in the `dataThroughAuthority.test.mjs` surface matrix

Retargeted to the live Tonight home, with the same intent:

- `canonicalEvidenceLinks`, `navigationRoutes` and `privatePosts`: file lists.
- `publicCopyPassThrough` and `vocabularyFreshnessContract`: now scan the
  Tonight sources.
- `teamBoardStoryRetirement`: retargeted to the Tonight home.
- `pageHierarchyDedupe`: the home route renders `TonightPage`, not a legacy
  report.
- `publicDeliveryCache`: the projection cache is exercised through
  `getStoriesProjection`.
- `publicSurfaceDelivery`: the Tonight home reads only v1, and the retired
  clients are absent.
- `tonightRootCutover`: the Home files are deleted.

Backend governance tests:

- `test_product_roadmap_current_state`: TODAY-01 now asserts that the backend
  owner remains and that the Home consumer and clients are retired.
- `test_editorial_voice_inventory_e2a`: the retired frontend path is dropped
  from the inventory rows, following the existing WhatChangedCard precedent.

Kept as regressions: `/` renders Tonight, `/tonight`, `/today` → `/`, legacy Home
absence, one v1 request with no v5 request, lead, featured and slate lifecycle,
What Changed, Team Board and Matchup handoffs, and the quiet, unavailable and
error/retry states. These are all in the existing TN-08 through TN-11.6 suites.

## Remaining references

| Reference | Where | Why it remains |
| --- | --- | --- |
| `IntelligenceSurface`, `Daily Edition`, `Since Yesterday` | backend services and models, their tests | Backend `/intelligence/today` and What Changed / share-artifact services are retained |
| `Since Yesterday` | `PublicShareArtifactPage`, `operatingStateReadModel`, `TrafficIntelligenceAdmin` | Live features: public share artifacts, the Team Board operating state, and the admin traffic view |
| `getTodayIntelligence`, `getTonightIntelligence`, `getHomeProjection`, `Home.jsx` | frontend tests | Negative guards asserting these stay absent |
| `tonight_v5` | `api.js` comment; backend; docs | v1 documents that it never falls back; v5 is retained |
| `trusted_tonight_view` | `public_serving_authority`, tests, docs | Serves the retained v5 default |
| `home/IntelligenceSurface.jsx`, `sinceYesterdayArtifact.js` | `backend/tests/freeze_policy.py` F-019 allowlist | A historical, decision-linked path allowlist. It does not require the files to exist and is pinned by `test_freeze_policy` |
| Home, Daily Edition and Today as the root | `docs/canonical/03_PRODUCT_EXPERIENCE_STANDARD.md` (route table, section 11), `docs/canonical/05_PRODUCT_ROADMAP_DECISION_LEDGER.md` | Governed, versioned canonical documents that need a governed revision, not an ad hoc edit in a cleanup package |
| Dated audit and design docs | `docs/audits/*`, `docs/archive/*`, `docs/design/*` | Historical records |

## Bundle

| Asset | Before | After | Change |
| --- | --- | --- | --- |
| JS | 703.74 kB (192.08 kB gzip) | 703.74 kB | Unchanged; Home was already unreachable and tree-shaken since TN-10 |
| CSS | 65.43 kB (12.09 kB gzip) | 63.78 kB (11.91 kB gzip) | −1.65 kB; Tailwind no longer emits Home-only classes |

## Recommended follow-ups

- **TN-12, v5 and legacy Today retirement:** migrate the scheduler, publication
  and intraday-repair consumers off v5 and Today snapshot generation. Then
  decide the public default-contract semantics, remove the v5 and Today
  builders, and plan table retention separately.
- **Governed canonical documentation revision** for the Tonight home (03 and
  05).
- **Decision on the dormant `bullpenLandscapeView`** and its contract tests.
- **Coordinated rename of the `today` pageview surface.**
