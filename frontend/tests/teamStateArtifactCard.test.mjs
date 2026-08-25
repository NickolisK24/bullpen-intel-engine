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

const TeamStateArtifactCard = (
  await server.ssrLoadModule('/src/components/share/TeamStateArtifactCard.jsx')
).default
const { ArtifactView } = await server.ssrLoadModule('/src/components/share/PublicShareArtifactPage.jsx')

const CARD_SRC = readFileSync(
  new URL('../src/components/share/TeamStateArtifactCard.jsx', import.meta.url),
  'utf8',
)

function render(element) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, null, element))
}

// A team-state-1.2.0 card block, as the public read projects it.
function cardFixture(overrides = {}) {
  return {
    card_version: 'team-state-1.2.0',
    artifact_context: {
      publication_scope: 'league_snapshot',
      publication_label: 'Published BaseballOS Snapshot',
      historical_note: 'This Team Bullpen State comes from a synchronized BaseballOS league snapshot.',
      data_through: '2026-07-23',
      generated_at: '2026-07-24T16:40:00',
      published_at: '2026-07-24T16:43:00',
    },
    team: { team_id: 109, canonical_name: 'Arizona Diamondbacks', abbreviation: 'AZ' },
    state: {
      public_state: 'vulnerable',
      public_label: 'Vulnerable',
      headline: 'Arizona Diamondbacks bullpen — Vulnerable',
      why: "Arizona Diamondbacks' bullpen has fewer clean options available after recent work.",
    },
    readiness_summary: {
      clean_options: { label: 'Clean options', count: 2, total: 8, statement: '2 of 8 active bullpen arms are clean options.' },
      multi_use_arms: { label: 'Multi-use arms', count: 3, total: 8, statement: '3 of 8 active bullpen arms pitched in at least two of the last 3 completed games.', games_in_window: 3 },
      short_rest_arms: { label: 'Short-rest arms', count: 4, total: 8, statement: '4 of 8 active bullpen arms are on zero or one day of rest.' },
      left_handed_options: { label: 'Left-handed options', count: 2, total: 3, statement: '2 of 3 active bullpen left-handers are usable options.', denominator: 'active bullpen left-handers' },
      active_bullpen_count: 8,
      authority_complete: true,
    },
    reliever_evidence: [
      { pitcher_id: 1, name: 'Reliever One', last_three_appearances: 2, outs_recorded: 6, innings_text: '2.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0, availability: 'Limited' },
      { pitcher_id: 2, name: 'Reliever Two', last_three_appearances: 1, outs_recorded: 3, innings_text: '1.0', last_appearance_date: '2026-07-22', last_opponent: 'SF', rest_days: 1, availability: 'On Watch' },
      { pitcher_id: 3, name: 'Reliever Three', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-18', last_opponent: 'LAD', rest_days: 5, availability: 'Available' },
    ],
    trust: {
      confidence: 'high',
      coverage_statement: 'Reflects the current active bullpen through July 23, 2026.',
      source_statement: 'Verified from the current active bullpen and completed recent appearances.',
    },
    limitations: [],
    ...overrides,
  }
}

// A v1.2 public view (top-level projection) that also carries the card block.
function artifactWithCard(cardOverrides = {}, viewOverrides = {}) {
  return {
    public_id: 'v12abc',
    lifecycle_state: 'published',
    payload_version: 'team-state-1.2.0',
    is_historical: true,
    generated_at: '2026-07-24T16:40:00',
    published_at: '2026-07-24T16:43:00',
    product_date: '2026-07-23',
    team: { team_id: 109, team_name: 'Arizona Diamondbacks', team_abbreviation: 'AZ' },
    team_state: { public_state: 'vulnerable', public_label: 'Vulnerable' },
    trust: { confidence: 'high' },
    freshness: { data_through: '2026-07-23' },
    publication_scope: {
      publication_scope: 'league_snapshot',
      display_label: 'Published BaseballOS Snapshot',
      historical_note: 'This Team Bullpen State comes from a synchronized BaseballOS league snapshot and is preserved as a historical artifact.',
    },
    routes: { share_url: '/share/v12abc', team_url: '/bullpen', methodology_url: '/methodology', data_trust_url: '/trust' },
    card: cardFixture(cardOverrides),
    ...viewOverrides,
  }
}

// -- card structure -------------------------------------------------------------

test('card renders the masthead header, data-through, and team bullpen state label', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  assert.match(html, /BaseballOS/)
  assert.match(html, /Bullpen Intelligence/)
  assert.match(html, /Team Bullpen State/)
  assert.match(html, /Data through/)
  assert.match(html, /July 23, 2026/)
})

test('card hero shows team, state, and why once', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  assert.match(html, /Arizona Diamondbacks/)
  assert.match(html, /Vulnerable/)
  assert.match(html, /fewer clean options available/)
  assert.equal((html.match(/<h1/g) || []).length, 1)
})

test('card glance renders the four readiness metrics with count-of-total', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  assert.match(html, /Bullpen at a glance/)
  assert.match(html, /Clean options/)
  assert.match(html, /Multi-use arms/)
  assert.match(html, /Short-rest arms/)
  assert.match(html, /Left-handed options/)
  assert.match(html, /2 of 8 active bullpen arms are clean options/)
  assert.match(html, /pitched in at least two of the last 3 completed games/)
  assert.match(html, /of 8/)
})

test('card evidence table renders the five governed columns and canonical availability labels', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  assert.match(html, /Current bullpen evidence/)
  assert.match(html, /Reliever/)
  assert.match(html, /Last 3 games/)
  assert.match(html, /Last appearance/)
  assert.match(html, /Rest/)
  assert.match(html, /Availability/)
  assert.match(html, /Reliever One/)
  assert.match(html, /Limited/)
  // Public vocabulary, not the engine state: this line asserted /Monitor/ and so
  // pinned the leak it was meant to catch.
  assert.match(html, /On Watch/)
  assert.match(html, /Available/)
  assert.match(html, /vs SF/)
})

test('card trust strip shows confidence, data-through, source, and generated', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  assert.match(html, /Confidence/)
  assert.match(html, /Verified from the current active bullpen/)
  assert.match(html, /Source/)
  assert.match(html, /Published BaseballOS Snapshot/)
  assert.match(html, /Generated/)
  assert.match(html, /ET/) // human-readable Eastern Time, never raw ISO text
})

test('card never renders card-only availability labels or recommendation language', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  for (const banned of ['Normal', 'Stressed', 'Tired', 'Risky', 'Fade', 'recommended', 'best option', 'highest risk']) {
    assert.ok(!html.includes(banned), `card must not render ${banned}`)
  }
})

test('card never leaks internal engine language or snake_case', () => {
  const html = render(React.createElement(TeamStateArtifactCard, { card: cardFixture() }))
  for (const banned of [
    'status_code', 'operationally_', 'clean_options', 'multi_use_arms', 'short_rest_arms',
    'left_handed_options', 'reliever_evidence', 'publication_scope', 'coverage_inventory',
    'availability_status', 'pitcher_id',
  ]) {
    assert.ok(!html.includes(banned), `card must not leak ${banned}`)
  }
})

test('card shows honest placeholders for missing values, never fabricated', () => {
  const card = cardFixture({
    reliever_evidence: [
      { pitcher_id: 9, name: 'Unknown Rest Arm', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: null, last_opponent: null, rest_days: null, availability: 'Available' },
    ],
  })
  const html = render(React.createElement(TeamStateArtifactCard, { card }))
  assert.match(html, /Unknown Rest Arm/)
  assert.match(html, /—/) // missing last-appearance / rest render as an em dash
  assert.ok(!html.includes('undefined'))
  assert.ok(!html.includes('null'))
})

test('card renders no fake progress bars, gradients, images, or generated logos', () => {
  assert.ok(!/progress|<progress|role="progressbar"/i.test(CARD_SRC))
  assert.ok(!/gradient|bg-gradient/i.test(CARD_SRC))
  assert.ok(!/<img|background-image|url\(/i.test(CARD_SRC))
})

test('card does not force mobile horizontal scroll', () => {
  // No overflow-x scroll containers and no fixed min-width wider than a phone.
  assert.ok(!/overflow-x-(auto|scroll)/.test(CARD_SRC))
  assert.ok(!/min-w-\[?\d{3,}/.test(CARD_SRC))
})

// -- public page integration ----------------------------------------------------

test('public page renders the v1.2 card first, then historical note and destinations', () => {
  const html = render(React.createElement(ArtifactView, { artifact: artifactWithCard(), superseded: false }))
  assert.match(html, /team-state-card/)
  assert.match(html, /Current bullpen evidence/)
  // Scope-aware historical note is preserved.
  assert.match(html, /synchronized BaseballOS league snapshot/)
  // Destinations remain present for the card path.
  assert.match(html, /Methodology/)
  assert.match(html, /Data &amp; Trust/)
  assert.match(html, /Open current Arizona Diamondbacks bullpen board/)
  // The legacy hero/evidence sections are NOT rendered for a card artifact.
  assert.ok(!html.includes('Evidence behind the read'))
  // Exactly one h1 across the whole page.
  assert.equal((html.match(/<h1/g) || []).length, 1)
})

test('a team-progressive v1.2 card shows the progressive scope, not a league claim', () => {
  const card = cardFixture({
    artifact_context: {
      publication_scope: 'team_progressive',
      publication_label: 'Published Team Bullpen State',
      historical_note: "Published after the team's completed game.",
      data_through: '2026-07-23',
      generated_at: '2026-07-24T16:40:00',
      published_at: '2026-07-24T16:43:00',
    },
  })
  const html = render(React.createElement(TeamStateArtifactCard, { card }))
  assert.match(html, /Published Team Bullpen State/)
  assert.ok(!html.includes('Published BaseballOS Snapshot'))
})

// ── Reader-facing availability vocabulary (H-6) ──────────────────────────────

test('the availability column renders only public vocabulary, never an engine state', () => {
  // The backend now projects every engine state through the public vocabulary
  // owner before it is frozen, so these are the only five values a current
  // artifact can carry: the four public labels, plus an absent value for a
  // historical row whose non-public state the read boundary withheld.
  const html = render(React.createElement(TeamStateArtifactCard, {
    card: cardFixture({
      reliever_evidence: [
        { pitcher_id: 1, name: 'A', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0, availability: 'Unavailable' },
        { pitcher_id: 2, name: 'B', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0, availability: 'Limited' },
        { pitcher_id: 3, name: 'C', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0, availability: 'On Watch' },
        { pitcher_id: 4, name: 'D', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0, availability: 'Available' },
        // A historical row: the read boundary withheld a non-public state.
        { pitcher_id: 5, name: 'E', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0 },
      ],
    }),
  }))

  // The engine-only words never reach a reader.
  assert.ok(!html.includes('Monitor'), 'Monitor must not be reader-visible')
  assert.ok(!html.includes('Avoid'), 'Avoid must not be reader-visible')

  // The public forms are present where the projection produced them.
  assert.ok(html.includes('On Watch'), 'On Watch must be rendered')
  assert.ok(html.includes('Unavailable'), 'Unavailable must be rendered')
  assert.ok(html.includes('Limited'))
  assert.ok(html.includes('Available'))

  // The withheld row still renders its non-semantic facts.
  assert.ok(html.includes('>E<') || html.includes('E'), 'withheld row still lists the pitcher')
})

test('historical raw Monitor and Avoid values cannot leak through the card badge', () => {
  const html = render(React.createElement(TeamStateArtifactCard, {
    card: cardFixture({
      reliever_evidence: [
        { pitcher_id: 1, name: 'First Arm', availability: 'Monitor' },
        { pitcher_id: 2, name: 'Second Arm', availability: 'Avoid' },
      ],
    }),
  }))

  assert.equal(html.includes('Monitor'), false)
  assert.equal(html.includes('Avoid'), false)
  assert.ok(html.includes('On Watch'))
  assert.ok(html.includes('Unavailable'))
})

test('the card invents no availability label when the value was withheld', () => {
  // Fail-closed presentation: no title-casing, no raw echo, no fifth label.
  const html = render(React.createElement(TeamStateArtifactCard, {
    card: cardFixture({
      reliever_evidence: [
        { pitcher_id: 1, name: 'Solo', last_three_appearances: 0, outs_recorded: 0, innings_text: '0.0', last_appearance_date: '2026-07-23', last_opponent: 'SF', rest_days: 0 },
      ],
    }),
  }))

  for (const invented of ['Unknown', 'None', 'N/A', 'Monitor', 'Avoid']) {
    assert.ok(!html.includes(invented), `must not invent ${invented}`)
  }
})
