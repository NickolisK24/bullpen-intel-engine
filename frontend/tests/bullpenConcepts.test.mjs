import assert from 'node:assert/strict'
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

after(async () => {
  await server.close()
})

const { getBullpenReads, getReadsForLandscapeEntry, CONCEPT_DEFINITIONS, LIMITED_READ_LABEL } =
  await server.ssrLoadModule('/src/utils/bullpenConcepts.js')
const { default: TeamBullpenStoryPanel } =
  await server.ssrLoadModule('/src/components/bullpen/board/TeamBullpenStoryPanel.jsx')
const { HomeView } = await server.ssrLoadModule('/src/components/home/Home.jsx')
const { StoriesView } = await server.ssrLoadModule('/src/components/stories/Stories.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

const labelOf = (counts, key) => getBullpenReads(counts).byKey[key].label

// ── Tier derivations ────────────────────────────────────────────────────────

test('bullpen pressure covers high, elevated, manageable, low, and limited read', () => {
  assert.equal(labelOf({ total: 8, ready: 2, watch: 2, needRest: 3 }, 'pressure'), 'High')
  assert.equal(labelOf({ total: 5, ready: 2, watch: 0, needRest: 2 }, 'pressure'), 'High') // 40% share
  assert.equal(labelOf({ total: 8, ready: 4, watch: 1, needRest: 2 }, 'pressure'), 'Elevated')
  assert.equal(labelOf({ total: 8, ready: 5, watch: 2, needRest: 1 }, 'pressure'), 'Elevated')
  assert.equal(labelOf({ total: 8, ready: 6, watch: 1, needRest: 1 }, 'pressure'), 'Manageable')
  assert.equal(labelOf({ total: 8, ready: 6, watch: 2, needRest: 0 }, 'pressure'), 'Manageable')
  assert.equal(labelOf({ total: 8, ready: 7, watch: 1, needRest: 0 }, 'pressure'), 'Low')
  assert.equal(labelOf({ total: 0, ready: 0, watch: 0, needRest: 0 }, 'pressure'), LIMITED_READ_LABEL)
})

test('recovery window covers wide, stable, narrow, limited, and limited read', () => {
  assert.equal(labelOf({ total: 8, ready: 6, watch: 1, needRest: 1 }, 'recovery'), 'Wide')
  assert.equal(labelOf({ total: 8, ready: 4, watch: 2, needRest: 2 }, 'recovery'), 'Stable')
  assert.equal(labelOf({ total: 8, ready: 2, watch: 2, needRest: 4 }, 'recovery'), 'Narrow')
  assert.equal(labelOf({ total: 8, ready: 1, watch: 3, needRest: 4 }, 'recovery'), 'Limited')
  assert.equal(labelOf({ total: 0 }, 'recovery'), LIMITED_READ_LABEL)
})

test('workload concentration covers concentrated, some, spread-out, and limited read', () => {
  assert.equal(labelOf({ total: 8, ready: 4, watch: 4, needRest: 0 }, 'concentration'), 'Concentrated')
  assert.equal(labelOf({ total: 8, ready: 2, watch: 2, needRest: 3 }, 'concentration'), 'Concentrated')
  assert.equal(labelOf({ total: 8, ready: 6, watch: 2, needRest: 0 }, 'concentration'), 'Some Concentration')
  assert.equal(labelOf({ total: 8, ready: 6, watch: 1, needRest: 1 }, 'concentration'), 'Some Concentration')
  assert.equal(labelOf({ total: 8, ready: 7, watch: 1, needRest: 0 }, 'concentration'), 'Spread-Out')
  assert.equal(labelOf({ total: 0 }, 'concentration'), LIMITED_READ_LABEL)
})

test('clean options covers deep, enough, thin, very thin, and limited read', () => {
  assert.equal(labelOf({ total: 8, ready: 6, watch: 1, needRest: 1 }, 'cleanOptions'), 'Deep')
  assert.equal(labelOf({ total: 8, ready: 4, watch: 2, needRest: 2 }, 'cleanOptions'), 'Enough')
  assert.equal(labelOf({ total: 8, ready: 2, watch: 2, needRest: 4 }, 'cleanOptions'), 'Thin')
  assert.equal(labelOf({ total: 8, ready: 1, watch: 3, needRest: 4 }, 'cleanOptions'), 'Very Thin')
  assert.equal(labelOf({ total: 0 }, 'cleanOptions'), LIMITED_READ_LABEL)
})

test('every concept ships a visible name and definition', () => {
  for (const key of ['pressure', 'recovery', 'concentration', 'cleanOptions']) {
    assert.ok(CONCEPT_DEFINITIONS[key].name.length > 0)
    assert.ok(CONCEPT_DEFINITIONS[key].definition.length > 20)
  }
  const { reads } = getBullpenReads({ total: 8, ready: 4, watch: 2, needRest: 2 })
  assert.equal(reads.length, 4)
  for (const read of reads) {
    assert.ok(read.definition.length > 0)
    assert.ok(read.detail.length > 0)
  }
})

test('the landscape adapter maps entry counts onto the reads', () => {
  const entry = { total: 8, available: 2, monitor: 2, restricted: 4 }
  const { byKey } = getReadsForLandscapeEntry(entry)
  assert.equal(byKey.pressure.label, 'High')
  assert.equal(byKey.cleanOptions.label, 'Thin')
  assert.equal(getReadsForLandscapeEntry(null).byKey.pressure.label, LIMITED_READ_LABEL)
})

// ── Surfaces ────────────────────────────────────────────────────────────────

function makeBoard(metrics, state = 'constrained') {
  return {
    team: { team_id: 1, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL' },
    context: { health: { state, label: 'label', reasons: [] }, metrics, confidence: 'high', limitations: [] },
    groups: [],
    freshness: {},
    total_pitchers: metrics.total_relievers,
  }
}

const constrainedBoard = makeBoard({
  total_relievers: 8, available: 2, monitor: 2, limited: 0, avoid: 3, unavailable: 1,
  pct_available: 25, pct_restricted: 50,
})

test('the team story panel renders the BaseballOS Reads strip with definitions', () => {
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: constrainedBoard }))
  assert.ok(htmlIncludes(html, 'BaseballOS Reads'))
  // Milwaukee's counts: 3 needing rest, 2 on watch, 2 ready of 8.
  assert.ok(htmlIncludes(html, 'Bullpen Pressure'))
  assert.ok(htmlIncludes(html, 'High'))
  assert.ok(htmlIncludes(html, 'Recovery Window'))
  assert.ok(htmlIncludes(html, 'Narrow'))
  assert.ok(htmlIncludes(html, 'Workload Concentration'))
  assert.ok(htmlIncludes(html, 'Concentrated'))
  assert.ok(htmlIncludes(html, 'Clean Options'))
  assert.ok(htmlIncludes(html, 'Thin'))
  // The definitions are one disclosure away.
  assert.ok(htmlIncludes(html, 'What these mean'))
  assert.ok(htmlIncludes(html, CONCEPT_DEFINITIONS.pressure.definition))
  assert.ok(htmlIncludes(html, CONCEPT_DEFINITIONS.recovery.definition))
})

test('a thin dataset reads as Limited across the strip', () => {
  const emptyBoard = makeBoard({
    total_relievers: 0, available: 0, monitor: 0, limited: 0, avoid: 0, unavailable: 0,
    pct_available: 0, pct_restricted: 0,
  }, 'no_data')
  const html = render(React.createElement(TeamBullpenStoryPanel, { board: emptyBoard }))
  const limitedCount = (html.match(new RegExp(escapeRegExp(LIMITED_READ_LABEL), 'g')) || []).length
  assert.ok(limitedCount >= 4, `expected all four reads limited, saw ${limitedCount}`)
})

const dashboard = {
  context: {
    health: { state: 'strained', label: 'label', reasons: [] },
    metrics: { total_relievers: 64, available: 38, monitor: 14, restricted: 9, pct_available: 59, pct_restricted: 14 },
    confidence: 'high',
  },
  landscape: {
    reference_date: '2026-06-06',
    teams_evaluated: 8,
    games: { available: true, data_state: 'historical', today_count: 0, as_of_date: '2026-06-05', as_of_count: 6, is_today: false, message: null },
    constrained_bullpens: [
      { team_id: 158, team_name: 'Milwaukee Brewers', team_abbreviation: 'MIL', total_relievers: 8, available: 2, monitor: 2, restricted: 4, pct_available: 25, pct_restricted: 50 },
      { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM', total_relievers: 8, available: 3, monitor: 2, restricted: 3, pct_available: 37, pct_restricted: 37 },
    ],
    available_bullpens: [
      { team_id: 120, team_name: 'Washington Nationals', team_abbreviation: 'WSH', total_relievers: 8, available: 6, monitor: 1, restricted: 1, pct_available: 75, pct_restricted: 12 },
    ],
    monitoring_concentration: [
      { team_id: 141, team_name: 'Toronto Blue Jays', team_abbreviation: 'TOR', total_relievers: 8, available: 4, monitor: 4, restricted: 0, pct_available: 50, pct_restricted: 0 },
    ],
    notes: [],
  },
  freshness: { data_through: '2026-06-05', last_successful_sync: '2026-06-06T08:00:00Z', is_current: true, sync_status: 'success' },
}

test('today stays light: exactly one concept chip, on the hero', () => {
  const html = render(React.createElement(HomeView, { dashboard }))
  // Count chips by their unique tooltip marker so the visible label and its
  // own title attribute are not double-counted.
  const chips = (html.match(/title="High Bullpen Pressure:/g) || []).length
  assert.equal(chips, 1, 'the hero carries one pressure chip; story cards on Today stay untagged')
  assert.ok(htmlIncludes(html, 'High Bullpen Pressure'))
})

test('stories feed cards render four-beat sections instead of compact concept tags', () => {
  const html = render(React.createElement(StoriesView, {
    dashboard: {
      ...dashboard,
      four_beat_stories: {
        items: [
          {
            story_id: '141:stress_transfer',
            team_id: 141,
            team_name: 'Toronto Blue Jays',
            team_abbreviation: 'TOR',
            kicker: 'Stress Transfer',
            tone: 'stress',
            category: 'stressed',
            title: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.',
            href: '/bullpen?view=board&team=TOR&source=four-beat-stories',
            beats: [
              { key: 'signal', label: 'Signal', text: 'The Toronto Blue Jays are transferring bullpen pressure onto a smaller group tonight.' },
              { key: 'evidence', label: 'Evidence', text: 'The top three arms have carried most of the recent relief work.' },
              { key: 'mechanism', label: 'Mechanism', text: 'That shape leaves less room behind the clean late-inning path.' },
              { key: 'implication', label: 'Implication', text: 'The next read is whether support appears behind that group.' },
            ],
          },
        ],
      },
    },
  }))
  assert.ok(htmlIncludes(html, 'Signal'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Mechanism'))
  assert.ok(htmlIncludes(html, 'Implication'))
  assert.ok(!htmlIncludes(html, 'Concentrated Workload'))
  assert.ok(!htmlIncludes(html, 'Wide Recovery Window'))
})

// ── Definition polish ───────────────────────────────────────────────────────

test('definitions stay short and plain', () => {
  for (const key of ['pressure', 'recovery', 'concentration', 'cleanOptions']) {
    const { definition } = CONCEPT_DEFINITIONS[key]
    assert.ok(definition.length > 20, `${key} definition too short`)
    assert.ok(definition.length <= 80, `${key} definition should stay a single plain sentence`)
    assert.ok(definition.split('.').filter(Boolean).length === 1, `${key} definition should be one sentence`)
  }
})

test('the concept set stays at four — no new concepts were added', () => {
  assert.equal(Object.keys(CONCEPT_DEFINITIONS).length, 4)
  const { reads } = getBullpenReads({ total: 8, ready: 4, watch: 2, needRest: 2 })
  assert.equal(reads.length, 4)
})

test('Clean Options keeps its name and avoids health-tinted alternatives', () => {
  assert.equal(CONCEPT_DEFINITIONS.cleanOptions.name, 'Clean Options')
  // No display label anywhere should drift to a fresh/health-flavored term.
  const tiers = [
    { total: 8, ready: 6, watch: 1, needRest: 1 },
    { total: 8, ready: 4, watch: 2, needRest: 2 },
    { total: 8, ready: 2, watch: 2, needRest: 4 },
    { total: 8, ready: 1, watch: 3, needRest: 4 },
  ]
  for (const counts of tiers) {
    const display = getBullpenReads(counts).byKey.cleanOptions.display
    assert.ok(/Clean Options$/.test(display), `unexpected clean-options display: ${display}`)
    assert.ok(!/Fresh|Clean Arms/.test(display))
  }
})

test('read detail leads with the counts that drive it', () => {
  const { byKey } = getBullpenReads({ total: 8, ready: 2, watch: 2, needRest: 3 })
  assert.match(byKey.pressure.detail, /^3 of 8 arms need rest/)
  assert.match(byKey.recovery.detail, /^2 of 8 arms come in rested/)
  assert.match(byKey.concentration.detail, /^2 of 8 on the watch list/)
  assert.match(byKey.cleanOptions.detail, /^2 of 8 arms enter without restriction/)
  // Singular counts read grammatically.
  const single = getBullpenReads({ total: 8, ready: 1, watch: 1, needRest: 1 })
  assert.match(single.byKey.recovery.detail, /^1 of 8 arm comes in rested/)
})

// ── Language guardrails ─────────────────────────────────────────────────────

test('the vocabulary never reaches for prediction, betting, injury, or advice', () => {
  const fixtures = [
    { total: 8, ready: 2, watch: 2, needRest: 3 },
    { total: 8, ready: 4, watch: 2, needRest: 2 },
    { total: 8, ready: 6, watch: 1, needRest: 1 },
    { total: 8, ready: 7, watch: 1, needRest: 0 },
    { total: 8, ready: 1, watch: 3, needRest: 4 },
    { total: 0 },
  ]
  for (const fixture of fixtures) {
    const { reads } = getBullpenReads(fixture)
    const text = reads.map(read => `${read.display} ${read.detail} ${read.definition}`).join(' ').toLowerCase()
    for (const term of [
      'will ', 'guarantee', 'collapse', 'injur', 'predict', 'bet ', 'betting',
      'odds', 'should use', 'recommend', 'best arm', 'best option', 'projected',
    ]) {
      assert.ok(!text.includes(term), `leaked "${term}" for ${JSON.stringify(fixture)}`)
    }
  }
})
