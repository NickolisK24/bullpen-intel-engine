import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})
after(async () => server.close())

const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const {
  ShareArtifactOperationsAccessState,
  ShareArtifactOperationsView,
  SHARE_ARTIFACT_OPERATIONS_ROBOTS_CONTENT,
} = await server.ssrLoadModule('/src/components/admin/ShareArtifactOperations.jsx')
const {
  fetchOperationsOverview,
  fetchOperationsAudits,
  SHARE_ARTIFACT_OPERATIONS_PATH,
} = await server.ssrLoadModule('/src/utils/shareArtifactOperations.js')

const PAGE_SRC = readFileSync(new URL('../src/components/admin/ShareArtifactOperations.jsx', import.meta.url), 'utf8')
const UTIL_SRC = readFileSync(new URL('../src/utils/shareArtifactOperations.js', import.meta.url), 'utf8')

function render(element) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
}

function overviewFixture(overrides = {}) {
  return {
    status: 'complete',
    autogeneration_enabled: true,
    source_snapshot_id: 7001,
    product_date: '2026-07-20',
    snapshot_published_at: '2026-07-20T13:00:00Z',
    canonical_team_count: 3,
    accounted_team_count: 3,
    generated_team_count: 1,
    reused_team_count: 1,
    refused_team_count: 1,
    failed_team_count: 0,
    missing_team_count: 0,
    integrity_failure_count: 0,
    integrity_error_count: 0,
    artifact_count: 2,
    teams: [
      { team_id: 101, team_name: 'Alpha', state: 'generated', public_id: 'pub-101', reason_code: null, failure_code: null, attempt_at: '2026-07-20T13:05:00Z', integrity_state: 'verified' },
      { team_id: 102, team_name: 'Bravo', state: 'reused', public_id: 'pub-102', reason_code: null, failure_code: null, attempt_at: '2026-07-20T13:06:00Z', integrity_state: 'verified' },
      { team_id: 103, team_name: 'Charlie', state: 'refused', public_id: null, reason_code: 'insufficient_trust', failure_code: null, attempt_at: '2026-07-20T13:07:00Z', integrity_state: 'not_applicable' },
    ],
    ...overrides,
  }
}

const st = data => ({ data, loading: false, error: null })
const loadingState = { data: null, loading: true, error: null }

function asState(value, fallback) {
  if (!value) return fallback
  if ('data' in value || 'loading' in value || 'error' in value) return value
  return st(value) // a raw data object -> wrap as a loaded state
}

function view({ overview, artifacts, audits } = {}) {
  return ShareArtifactOperationsView({
    overview: asState(overview, st(overviewFixture())),
    artifacts: asState(artifacts, st({ artifacts: [], limit: 25, offset: 0, count: 0 })),
    audits: asState(audits, st({ audits: [], limit: 25, offset: 0, count: 0 })),
  })
}

// --- Security (19-27) ---

test('page and util never reference an admin token / privileged secret', () => {
  for (const src of [PAGE_SRC, UTIL_SRC]) {
    assert.equal(src.includes('ADMIN_API_TOKEN'), false)
    assert.equal(src.includes('X-Admin-Token'), false)
    assert.equal(src.includes('VITE_ADMIN_API_TOKEN'), false)
  }
})

test('util writes no privileged token to storage and uses only the Bearer session', () => {
  assert.equal(UTIL_SRC.includes('localStorage'), false)
  assert.equal(UTIL_SRC.includes('sessionStorage'), false)
  assert.ok(UTIL_SRC.includes('Authorization'))
  assert.ok(UTIL_SRC.includes('Bearer'))
  assert.ok(UTIL_SRC.includes('readAuthToken'))
})

test('fetch attaches the user Bearer token and hits the browser boundary, not the admin route', async () => {
  const calls = []
  const fetchImpl = async (url, opts) => {
    calls.push({ url, opts })
    return { ok: true, json: async () => ({ ok: true }) }
  }
  await fetchOperationsOverview({ fetchImpl, authToken: 'user-bearer', configuredBackendOrigin: '' })
  assert.equal(calls[0].opts.headers.Authorization, 'Bearer user-bearer')
  assert.ok(calls[0].url.includes('/api/internal-browser/share-artifacts/operations/overview'))
  assert.equal(calls[0].url.includes('/internal/share-artifacts/'), false) // not the admin path
  assert.equal(calls[0].url.includes('batch'), false)                      // never generation
  assert.deepEqual(Object.keys(calls[0].opts.headers).sort(), ['Authorization', 'Content-Type'])
})

test('fetch rethrows with the HTTP status so auth failures are distinguishable', async () => {
  const fetchImpl = async () => ({ ok: false, status: 403, json: async () => ({}) })
  await assert.rejects(
    () => fetchOperationsOverview({ fetchImpl, authToken: 't', configuredBackendOrigin: '' }),
    err => err.status === 403,
  )
})

test('audits fetch only sends supported backend filters', async () => {
  const calls = []
  const fetchImpl = async (url) => { calls.push(url); return { ok: true, json: async () => ({}) } }
  await fetchOperationsAudits(
    { limit: 25, offset: 25, team_id: 101, outcome: 'refused', source_snapshot_id: 7001, product_date: '2026-07-20' },
    { fetchImpl, authToken: 't', configuredBackendOrigin: '' },
  )
  const url = calls[0]
  for (const key of ['limit', 'offset', 'team_id', 'outcome', 'source_snapshot_id', 'product_date']) {
    assert.ok(url.includes(`${key}=`), `expected ${key} in query`)
  }
})

test('403 renders the forbidden access state and leaks no operational data', () => {
  const html = render(view({ overview: { data: overviewFixture(), loading: false, error: { status: 403 } } }))
  assert.ok(html.includes('not authorized'))
  assert.equal(html.includes('Alpha'), false)     // prior data not shown
  assert.equal(html.includes('Coverage'), false)
})

test('401 renders the unauthenticated access state with a sign-in link', () => {
  const html = render(view({ overview: { data: null, loading: false, error: { status: 401 } } }))
  assert.ok(html.includes('Sign in'))
  assert.ok(html.includes(encodeURIComponent(SHARE_ARTIFACT_OPERATIONS_PATH)))
})

test('route is registered but excluded from public navigation and footer', () => {
  assert.ok(APP_ROUTES.some(route => route.path === SHARE_ARTIFACT_OPERATIONS_PATH))
  const sidebar = readFileSync(new URL('../src/components/Sidebar.jsx', import.meta.url), 'utf8')
  const footer = readFileSync(new URL('../src/components/layout/Footer.jsx', import.meta.url), 'utf8')
  const nav = readFileSync(new URL('../src/utils/navigation.js', import.meta.url), 'utf8')
  assert.equal(sidebar.includes(SHARE_ARTIFACT_OPERATIONS_PATH), false)
  assert.equal(footer.includes(SHARE_ARTIFACT_OPERATIONS_PATH), false)
  assert.equal(nav.includes(SHARE_ARTIFACT_OPERATIONS_PATH), false)
})

test('page uses noindex robots meta and the useAuthState guard', () => {
  assert.equal(SHARE_ARTIFACT_OPERATIONS_ROBOTS_CONTENT, 'noindex,nofollow')
  assert.ok(PAGE_SRC.includes('useAuthState'))
  assert.ok(PAGE_SRC.includes("name', 'robots'") || PAGE_SRC.includes('"robots"'))
})

// --- Page (28-55) ---

test('authorized view renders header, coverage counts, and one row per canonical team', () => {
  const html = render(view())
  // 29 header metadata
  assert.ok(html.includes('Operational status'))
  assert.ok(html.includes('Latest trusted snapshot'))
  assert.ok(html.includes('7001'))
  assert.ok(html.includes('Automatic generation'))
  // 30 coverage counts
  assert.ok(html.includes('Canonical teams'))
  assert.ok(html.includes('Missing'))
  // 31/32 one deterministic row per team, in backend order
  const idxAlpha = html.indexOf('Alpha')
  const idxBravo = html.indexOf('Bravo')
  const idxCharlie = html.indexOf('Charlie')
  assert.ok(idxAlpha > -1 && idxBravo > idxAlpha && idxCharlie > idxBravo)
})

test('generated/reused/refused/failed/missing remain textually distinct', () => {
  const html = render(view({
    overview: overviewFixture({
      generated_team_count: 1, reused_team_count: 1, refused_team_count: 1, failed_team_count: 1, missing_team_count: 1,
      teams: [
        { team_id: 1, team_name: 'G', state: 'generated', public_id: 'p1', integrity_state: 'verified', attempt_at: null },
        { team_id: 2, team_name: 'R', state: 'reused', public_id: 'p2', integrity_state: 'verified', attempt_at: null },
        { team_id: 3, team_name: 'X', state: 'refused', reason_code: 'insufficient_trust', integrity_state: 'not_applicable', attempt_at: null },
        { team_id: 4, team_name: 'F', state: 'failed', failure_code: 'publication_error', integrity_state: 'not_applicable', attempt_at: null },
        { team_id: 5, team_name: 'M', state: 'missing', integrity_state: 'not_applicable', attempt_at: null },
      ],
    }),
  }))
  assert.ok(html.includes('Generated'))
  assert.ok(html.includes('Reused'))
  assert.ok(html.includes('Refused'))
  assert.ok(html.includes('Failed'))
  assert.ok(html.includes('Missing'))
  assert.ok(html.includes('insufficient_trust'))
  assert.ok(html.includes('publication_error'))
})

test('integrity mismatch and error are both visible and distinct', () => {
  const html = render(view({
    overview: overviewFixture({
      integrity_failure_count: 1, integrity_error_count: 1,
      teams: [
        { team_id: 1, team_name: 'M1', state: 'generated', public_id: 'p1', integrity_state: 'mismatch', attempt_at: null },
        { team_id: 2, team_name: 'E1', state: 'generated', public_id: 'p2', integrity_state: 'error', attempt_at: null },
      ],
    }),
  }))
  assert.ok(html.includes('Integrity mismatch'))
  assert.ok(html.includes('Verification error'))
})

for (const [status, label] of [
  ['complete', 'Complete'],
  ['complete_with_refusals', 'with refusals'],
  ['degraded', 'Degraded'],
  ['incomplete', 'Incomplete'],
  ['disabled', 'Automatic generation disabled'],
]) {
  test(`status "${status}" renders its label`, () => {
    const html = render(view({ overview: overviewFixture({ status }) }))
    assert.ok(html.includes(label), `expected label for ${status}`)
  })
}

test('unavailable status renders an honest no-snapshot message and no coverage table', () => {
  const html = render(view({
    overview: overviewFixture({ status: 'unavailable', reason: 'snapshot_stale', teams: [] }),
  }))
  assert.ok(html.includes('No trusted published snapshot'))
  assert.ok(html.includes('snapshot_stale'))
  assert.equal(html.includes('Team Coverage'), false)
})

test('empty artifacts and audits render honest messages', () => {
  const html = render(view())
  assert.ok(html.includes('No immutable artifacts recorded'))
  assert.ok(html.includes('No generation attempts recorded'))
})

test('overview API failure renders a safe error state with retry', () => {
  const html = render(view({ overview: { data: null, loading: false, error: new Error('boom') } }))
  assert.ok(html.includes('unavailable'))
  assert.ok(html.includes('Retry'))
  assert.equal(html.includes('boom'), false) // raw error text not shown
})

test('loading state shows no fabricated numbers', () => {
  const html = render(ShareArtifactOperationsView({ overview: loadingState, artifacts: loadingState, audits: loadingState }))
  assert.ok(html.includes('Loading'))
  assert.equal(/>\s*0\s*</.test(html), false) // no placeholder zeros
})

test('the page is read-only: no mutation/generation controls', () => {
  for (const forbidden of ['Generate', 'Regenerate', 'Retry generation', 'Publish', 'Withdraw', 'Supersede', 'Delete', 'Repair', 'Recalculate']) {
    assert.equal(PAGE_SRC.includes(`>${forbidden}<`), false, `no ${forbidden} control`)
  }
  // No mutating HTTP verbs anywhere in the page or util.
  for (const src of [PAGE_SRC, UTIL_SRC]) {
    assert.equal(/method:\s*'(POST|PUT|PATCH|DELETE)'/.test(src), false)
  }
  // Automatic-generation state is display-only (no toggle/POST for it).
  assert.equal(PAGE_SRC.includes('setAutogeneration'), false)
})

test('page has one h1, semantic tables with scoped headers, and text-based status', () => {
  const html = render(view())
  assert.equal((html.match(/<h1/g) || []).length, 1)
  assert.ok(html.includes('scope="col"'))
  assert.ok(html.includes('scope="row"'))
  assert.ok(html.includes('<caption'))
  // status conveyed as text (not color alone)
  assert.ok(html.includes('Complete'))
})

test('pagination uses accessible buttons bounded at the start', () => {
  const html = render(view({
    audits: st({ audits: [{ id: 1, team_id: 101, outcome: 'published', created_at: '2026-07-20T13:00:00Z' }], limit: 25, offset: 0, count: 1 }),
  }))
  assert.ok(html.includes('Previous'))
  assert.ok(html.includes('Next'))
  assert.ok(html.includes('disabled')) // Previous disabled at offset 0
})
