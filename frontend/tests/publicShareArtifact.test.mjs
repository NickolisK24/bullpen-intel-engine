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

// A revised (team-state-1.1.0) Arizona-shaped public view.
function artifactFixture(overrides = {}) {
  return {
    public_id: 'abc123',
    lifecycle_state: 'published',
    revised: true,
    payload_version: 'team-state-1.1.0',
    is_historical: true,
    generated_at: '2026-07-24T16:40:00',
    published_at: '2026-07-24T16:43:00',
    product_date: '2026-07-23',
    team: { team_id: 109, team_name: 'Arizona Diamondbacks', team_abbreviation: 'AZ' },
    team_state: {
      status_code: 'operationally_stressed',
      public_state: 'vulnerable',
      public_label: 'Vulnerable',
      summary: 'Team-level bullpen readiness is stressed by current workload or availability constraints.',
      contract_state: 'degraded',
    },
    trust: { confidence: 'high', data_state: 'fresh', freshness_state: 'current', trust_state: 'trusted' },
    freshness: { data_through: '2026-07-23', published_at: '2026-07-24T16:43:00' },
    evidence: [
      { evidence_id: 'availability_constrained', kind: 'availability', label: 'Available bullpen options', detail: '2 relievers are limited or unavailable.', severity: 'caution', count: 2 },
      { evidence_id: 'workload_elevated', kind: 'workload', label: 'Recent bullpen workload', detail: '3 relievers are carrying elevated recent workload.', severity: 'caution', count: 3 },
    ],
    limitations: [],
    copy: {
      headline: 'Arizona Diamondbacks bullpen — Vulnerable',
      why: "Arizona Diamondbacks' bullpen is carrying a heavier recent workload, leaving fewer clean options available.",
      summary: "Arizona Diamondbacks' bullpen is carrying a heavier recent workload, leaving fewer clean options available.",
      freshness_line: 'Reflects the current active bullpen through July 23, 2026.',
      trust_line: 'Verified from the current active bullpen and completed recent appearances.',
      alt_text: 'Arizona Diamondbacks bullpen is Vulnerable.',
      description: "Arizona Diamondbacks' bullpen is Vulnerable.",
    },
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

test('published artifact renders a designed historical read with public copy', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactFixture(), superseded: false }))
  // A. Historical context bar — league fallback label when no scope is present.
  assert.match(html, /Published BaseballOS Snapshot/)
  assert.match(html, /Data through/)
  assert.match(html, /July 23, 2026/)
  // B. Hero — public state + why (once), team.
  assert.match(html, /Arizona Diamondbacks/)
  assert.match(html, /Vulnerable/)
  assert.match(html, /carrying a heavier recent workload/)
  // D. Evidence receipts — reader-facing labels + details.
  assert.match(html, /Evidence behind the read/)
  assert.match(html, /Recent bullpen workload/)
  assert.match(html, /3 relievers are carrying elevated recent workload/)
  // E. Trust & freshness — reader-facing.
  assert.match(html, /Trust &amp; freshness/)
  assert.match(html, /Verified from the current active bullpen/)
  // G. Destinations — historical vs live distinct.
  assert.match(html, /Methodology/)
  assert.match(html, /Data &amp; Trust/)
  assert.match(html, /current bullpen surface/)
  assert.match(html, /live, not this historical snapshot/)
  // Exactly one h1.
  assert.equal((html.match(/<h1/g) || []).length, 1)
})

test('a team-progressive artifact renders the scope-aware label and historical note', () => {
  const scope = {
    publication_scope: 'team_progressive',
    display_label: 'Published Team Bullpen State',
    context_label: "Updated after the team's completed game",
    historical_note:
      "This Team Bullpen State was published after the team's completed game and is preserved as a historical artifact.",
  }
  const html = render(
    React.createElement(ArtifactView, {
      artifact: artifactFixture({ publication_scope: scope }),
      superseded: false,
    }),
  )
  assert.match(html, /Published Team Bullpen State/)
  assert.match(html, /published after the team&#x27;s completed game/)
  // It must NOT claim to be a league snapshot.
  assert.ok(!html.includes('Published BaseballOS Snapshot'))
})

test('a league-scope artifact renders the synchronized-snapshot label and note', () => {
  const scope = {
    publication_scope: 'league_snapshot',
    display_label: 'Published BaseballOS Snapshot',
    context_label: null,
    historical_note:
      'This Team Bullpen State comes from a synchronized BaseballOS league snapshot and is preserved as a historical artifact.',
  }
  const html = render(
    React.createElement(ArtifactView, {
      artifact: artifactFixture({ publication_scope: scope }),
      superseded: false,
    }),
  )
  assert.match(html, /Published BaseballOS Snapshot/)
  assert.match(html, /synchronized BaseballOS league snapshot/)
})

test('no internal engine language or snake_case reaches the public page', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactFixture(), superseded: false }))
  for (const banned of [
    'Operationally Stressed', 'operationally_stressed', 'team-level bullpen readiness',
    'constrained inventory', 'availability_distribution', 'coverage_inventory',
    'workload_pressure', 'handedness_coverage', 'status_code',
  ]) {
    assert.ok(!html.includes(banned), `public page must not show ${banned}`)
  }
})

test('timestamps render human-readable Eastern Time, never raw ISO text', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactFixture(), superseded: false }))
  // Explicit ET, human-readable.
  assert.match(html, /ET/)
  // Semantic <time> retains the exact machine value.
  assert.match(html, /<time datetime="2026-07-23"/i)
  assert.match(html, /<time datetime="2026-07-24T16:43:00"/i)
  // Raw ISO is never rendered as visible text (only inside datetime attributes).
  assert.ok(!html.includes('>2026-07-24T16:43:00'), 'ISO must not be visible text')
  assert.ok(!html.includes('>2026-07-24T16:40:00'), 'ISO must not be visible text')
})

test('empty limitations section is omitted entirely', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactFixture({ limitations: [] }), superseded: false }))
  assert.ok(!/id="share-limitations"/.test(html))
  assert.ok(!html.includes('No limitations were recorded'))
})

test('a real limitation renders exactly as frozen', () => {
  const artifact = artifactFixture({
    trust: { confidence: 'medium', data_state: 'fresh', freshness_state: 'current' },
    limitations: ['This read covers 6 of 8 active bullpen pitchers. Two current workload records remain incomplete.'],
  })
  const html = render(React.createElement(ArtifactView, { artifact, superseded: false }))
  assert.match(html, /id="share-limitations"/)
  assert.match(html, /6 of 8 active bullpen pitchers/)
  assert.match(html, /Two current workload records remain incomplete/)
})

test('superseded renders original plus replacement link, original content intact', () => {
  const artifact = artifactFixture({
    lifecycle_state: 'superseded',
    superseded: { replacement_public_id: 'new1', replacement_url: '/share/new1' },
  })
  const html = render(React.createElement(ArtifactView, { artifact, superseded: true }))
  assert.match(html, /superseded it/)
  assert.match(html, /href="\/share\/new1"/)
  assert.match(html, /Vulnerable/)
})

test('missing values render as honest placeholders, never fabricated', () => {
  const artifact = artifactFixture({ team: {}, team_state: {}, trust: {}, copy: {}, evidence: [], limitations: [] })
  const html = render(React.createElement(ArtifactView, { artifact, superseded: false }))
  assert.match(html, /No evidence receipts were recorded/)
  assert.ok(!html.includes('Unknown'))
  // No fabricated public state — falls back to the neutral "Team State" label.
  assert.match(html, /Team State/)
})

// -- error/lifecycle states -----------------------------------------------------

test('withdrawn renders without the original claim', () => {
  const html = render(React.createElement(WithdrawnState, { artifact: { withdrawn_reason: 'source correction' } }))
  assert.match(html, /withdrawn/i)
  assert.match(html, /source correction/)
  assert.doesNotMatch(html, /Vulnerable/)
})

test('not-found and integrity states render safely without artifact data', () => {
  assert.match(render(React.createElement(NotFoundState)), /not found/i)
  const integrity = render(React.createElement(IntegrityErrorState))
  assert.match(integrity, /could not be verified/i)
  assert.doesNotMatch(integrity, /Vulnerable/)
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
  assert.match(UTIL_SRC, /share-artifacts\//)
  assert.match(UTIL_SRC, /method: 'GET'/)
})
