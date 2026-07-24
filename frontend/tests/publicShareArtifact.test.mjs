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
  ArtifactView,
  WithdrawnState,
  NotFoundState,
  IntegrityErrorState,
} = await server.ssrLoadModule('/src/components/share/PublicShareArtifactPage.jsx')
const { fetchPublicShareArtifact, SHARE_STATE, publicSharePath } =
  await server.ssrLoadModule('/src/utils/publicShareArtifact.js')

const PAGE_SRC = readFileSync(new URL('../src/components/share/PublicShareArtifactPage.jsx', import.meta.url), 'utf8')
const UTIL_SRC = readFileSync(new URL('../src/utils/publicShareArtifact.js', import.meta.url), 'utf8')

function render(element) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
}

function artifactFixture(overrides = {}) {
  return {
    public_id: 'abc123',
    lifecycle_state: 'published',
    is_historical: true,
    generated_at: '2026-07-24T04:08:00',
    published_at: '2026-07-24T04:08:00',
    product_date: '2026-07-23',
    team: { team_id: 147, team_name: 'Test Club', team_abbreviation: 'TST' },
    team_state: { status_code: 'operationally_constrained', status_label: 'Operationally Constrained', summary: 'Two arms down.' },
    trust: { confidence: 'medium', data_state: 'fresh', freshness_state: 'current' },
    freshness: { data_through: '2026-07-23' },
    evidence: [{ evidence_id: 'e1', kind: 'workload', label: 'Bullpen', detail: 'Heavy relief workload.', severity: 'caution' }],
    limitations: ['Current readiness reflects 6 of 8 active bullpen pitchers; 2 have incomplete current workload records.'],
    copy: { headline: 'Operationally Constrained', summary: 'Two arms down.' },
    routes: { share_url: '/share/abc123', team_url: '/bullpen', methodology_url: '/methodology', data_trust_url: '/trust' },
    ...overrides,
  }
}

// -- route registration --------------------------------------------------------

test('/share/:publicId route is registered', () => {
  assert.ok(APP_ROUTES.some((r) => r.path === '/share/:publicId'))
  assert.equal(publicSharePath('abc123'), '/share/abc123')
})

// -- published render -----------------------------------------------------------

test('published artifact renders historical read with all sections', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactFixture(), superseded: false }))
  assert.match(html, /Historical snapshot/)
  assert.match(html, /not a live current read/)
  assert.match(html, /Test Club/)
  assert.match(html, /Operationally Constrained/)
  assert.match(html, /Original read/)
  assert.match(html, /Evidence/)
  assert.match(html, /Heavy relief workload/)
  assert.match(html, /Trust &amp; freshness/)
  assert.match(html, /Limitations/)
  assert.match(html, /6 of 8 active bullpen pitchers/)
  assert.match(html, /Methodology/)
  assert.match(html, /Data &amp; Trust/)
  assert.match(html, /Current live bullpen surface/)
  assert.match(html, /the live destination; this page is historical/)
  // Exactly one h1.
  assert.equal((html.match(/<h1/g) || []).length, 1)
  // Timestamps use <time> with explicit datetime.
  assert.match(html, /<time datetime="2026-07-23"/i)
})

test('medium limitation counts and copy render exactly as frozen', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactFixture(), superseded: false }))
  assert.match(html, /6 of 8 active bullpen pitchers; 2 have incomplete current workload records/)
})

test('superseded renders original plus replacement link, original content intact', () => {
  const artifact = artifactFixture({
    lifecycle_state: 'superseded',
    superseded: { replacement_public_id: 'new1', replacement_url: '/share/new1' },
  })
  const html = render(React.createElement(ArtifactView, { artifact, superseded: true }))
  assert.match(html, /newer artifact has since\s+superseded it/)
  assert.match(html, /href="\/share\/new1"/)
  // Original claim still present.
  assert.match(html, /Operationally Constrained/)
})

test('missing values render as placeholders, never fabricated', () => {
  const artifact = artifactFixture({ team: {}, team_state: {}, trust: {}, evidence: [], limitations: [] })
  const html = render(React.createElement(ArtifactView, { artifact, superseded: false }))
  assert.match(html, /No evidence receipts were recorded/)
  assert.match(html, /No limitations were recorded/)
  assert.doesNotMatch(html, /Unknown/)  // no invented "Unknown" copy
})

// -- error/lifecycle states -----------------------------------------------------

test('withdrawn renders without the original claim', () => {
  const html = render(React.createElement(WithdrawnState, { artifact: { withdrawn_reason: 'source correction' } }))
  assert.match(html, /withdrawn/i)
  assert.match(html, /source correction/)
  assert.doesNotMatch(html, /Operationally/)
})

test('not-found and integrity states render safely without artifact data', () => {
  assert.match(render(React.createElement(NotFoundState)), /not found/i)
  const integrity = render(React.createElement(IntegrityErrorState))
  assert.match(integrity, /could not be verified/i)
  assert.doesNotMatch(integrity, /Operationally/)
})

// -- fetch util contract --------------------------------------------------------

function fakeFetch(status, body) {
  return async () => ({ status, json: async () => body })
}

test('fetch util maps lifecycle HTTP contract to honest states', async () => {
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: fakeFetch(200, { status: 'ok', artifact: {} }) })).state, SHARE_STATE.OK)
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: fakeFetch(200, { status: 'superseded', artifact: {} }) })).state, SHARE_STATE.SUPERSEDED)
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: fakeFetch(410, { status: 'withdrawn', artifact: {} }) })).state, SHARE_STATE.WITHDRAWN)
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: fakeFetch(404, {}) })).state, SHARE_STATE.NOT_FOUND)
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: fakeFetch(503, {}) })).state, SHARE_STATE.INTEGRITY_ERROR)
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: fakeFetch(500, {}) })).state, SHARE_STATE.API_ERROR)
  // Network failure -> honest api_error, no stale fallback.
  const boom = async () => { throw new Error('network') }
  assert.equal((await fetchPublicShareArtifact('x', { fetchImpl: boom })).state, SHARE_STATE.API_ERROR)
})

// -- boundary purity (source proofs) -------------------------------------------

test('page and util never touch live/current/internal/admin/generation paths', () => {
  const combined = PAGE_SRC + '\n' + UTIL_SRC
  for (const forbidden of [
    'team-operations', 'bullpen-readiness', 'internal-browser', 'internal/share-artifacts',
    'team-state/batch', 'team-state/generate', 'evidenceCardModel', 'evidenceCardStory',
    'Authorization', 'X-Admin-Token',
  ]) {
    assert.ok(!combined.includes(forbidden), `must not reference ${forbidden}`)
  }
  // Public util calls only the public share-artifacts endpoint, GET only.
  assert.match(UTIL_SRC, /share-artifacts\//)
  assert.match(UTIL_SRC, /method: 'GET'/)
})
