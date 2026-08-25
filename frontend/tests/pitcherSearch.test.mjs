import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
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

const {
  PitcherSearchPanel,
  getPitcherSearchResultView,
} = await server.ssrLoadModule('/src/components/bullpen/PitcherSearch.jsx')
const {
  SearchPageView,
  buildDiscoveryResultHref,
} = await server.ssrLoadModule('/src/components/search/SearchPage.jsx')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

const kimbrel = {
  player_id: 12345,
  player_name: 'Craig Kimbrel',
  team_id: 139,
  team_name: 'Tampa Bay Rays',
  position: 'P',
  roster_status: 'ACTIVE',
  availability: 'Available',
}

function renderPanel(props = {}) {
  return renderToStaticMarkup(
    React.createElement(PitcherSearchPanel, {
      query: '',
      results: [],
      loading: false,
      error: '',
      onQueryChange: () => {},
      onSelectPitcher: () => {},
      ...props,
    }),
  )
}

test('Pitcher Search input renders on the Bullpen Board surface', () => {
  const html = renderPanel()

  assert.ok(htmlIncludes(html, 'Pitcher Search'))
  assert.ok(htmlIncludes(html, 'type="search"'))
  assert.ok(htmlIncludes(html, 'aria-label="Search pitcher"'))
  assert.ok(htmlIncludes(html, 'placeholder="Search pitchers..."'))
})

test('Pitcher Search displays returned pitcher results with team status and availability', () => {
  const html = renderPanel({ query: 'kimbrel', results: [kimbrel] })

  assert.ok(htmlIncludes(html, 'Craig Kimbrel'))
  assert.ok(htmlIncludes(html, 'Tampa Bay Rays'))
  assert.ok(htmlIncludes(html, 'Active MLB'))
  assert.ok(htmlIncludes(html, 'Available'))
})

test('Pitcher Search renders an empty state for no returned results', () => {
  const html = renderPanel({ query: 'zz', results: [] })

  assert.ok(htmlIncludes(html, 'No pitchers found.'))
})

test('Pitcher Search keeps missing team ownership explicit', () => {
  const view = getPitcherSearchResultView({
    ...kimbrel,
    team_id: null,
    team_name: null,
    team_abbreviation: null,
    availability: 'Unavailable',
  })

  assert.equal(view.teamLabel, 'Team unavailable')
  assert.equal(view.availability, 'Unavailable')
})

test('Pitcher Search stays out of the Team Board primary path', async () => {
  const searchSource = await readFile(
    new URL('../src/components/bullpen/PitcherSearch.jsx', import.meta.url),
    'utf8',
  )
  const bullpenSource = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )
  const apiSource = await readFile(
    new URL('../src/utils/api.js', import.meta.url),
    'utf8',
  )

  assert.ok(searchSource.includes('onClick={() => onSelectPitcher(result)}'))
  assert.equal(bullpenSource.includes('<PitcherSearch'), false)
  assert.ok(bullpenSource.includes('id="reliever-finder-search"'))
  assert.ok(bullpenSource.includes('navigate(buildPitcherHref(pitcherId'))
  assert.equal(bullpenSource.includes('<PitcherDetail'), false)
  assert.ok(apiSource.includes('export const searchPitchers'))
  assert.ok(apiSource.includes('/pitchers/search'))
})

const discoveryPayload = {
  capability: 'unified_entity_search_v1',
  contract: 'unified_entity_search_carrier_v1',
  status: 'available',
  query: 'tampa',
  result_count: 3,
  groups: [
    {
      entity_type: 'team',
      status: 'available',
      results: [{
        entity_type: 'team',
        id: 139,
        primary_label: 'Tampa Bay Rays',
        secondary_label: 'TB',
        metadata: { team_id: 139, team_name: 'Tampa Bay Rays', team_abbreviation: 'TB' },
      }],
    },
    {
      entity_type: 'pitcher',
      status: 'available',
      results: [{
        entity_type: 'pitcher',
        id: 12345,
        primary_label: 'Tampa Relief',
        secondary_label: 'Tampa Bay Rays',
        metadata: { team_name: 'Tampa Bay Rays', position: 'P', roster_status: 'ACTIVE' },
      }],
    },
    {
      entity_type: 'matchup',
      status: 'available',
      results: [{
        entity_type: 'matchup',
        id: 880001,
        primary_label: 'Tampa Bay Rays at Minnesota Twins',
        secondary_label: '2026-08-25',
        metadata: {
          reference_date: '2026-08-25',
          game_time_utc: '2026-08-25T23:10:00Z',
          status: { detailed: 'Scheduled' },
        },
      }],
    },
  ],
}

function renderDiscovery(props = {}) {
  return renderToStaticMarkup(
    React.createElement(
      MemoryRouter,
      null,
      React.createElement(SearchPageView, {
        query: 'tampa',
        payload: discoveryPayload,
        loading: false,
        error: '',
        onQueryChange: () => {},
        onRetry: () => {},
        ...props,
      }),
    ),
  )
}

test('unified discovery renders grouped team pitcher and matchup identities', () => {
  const html = renderDiscovery()

  for (const text of [
    'Search BaseballOS',
    'Teams',
    'Relievers',
    'Today&#x27;s Matchups',
    'Tampa Bay Rays',
    'Tampa Relief',
    'Tampa Bay Rays at Minnesota Twins',
  ]) {
    assert.ok(htmlIncludes(html, text), text)
  }
  assert.ok(htmlIncludes(html, 'aria-label="Search results"'))
})

test('unified discovery routes every entity to its canonical destination', () => {
  const [team, pitcher, matchup] = discoveryPayload.groups.map(group => group.results[0])

  assert.equal(buildDiscoveryResultHref(team), '/bullpen?view=board&team=TB&source=search')
  assert.equal(buildDiscoveryResultHref(pitcher), '/pitcher/12345')
  assert.equal(buildDiscoveryResultHref(matchup), '/matchup/880001')
})

test('unified discovery preserves duplicate-name identities instead of choosing one', () => {
  const duplicatePayload = structuredClone(discoveryPayload)
  duplicatePayload.result_count = 2
  duplicatePayload.groups[0].results = []
  duplicatePayload.groups[1].results = [
    { ...duplicatePayload.groups[1].results[0], id: 1, primary_label: 'Alex Same', metadata: { team_name: 'Tampa Bay Rays', roster_status: 'ACTIVE' } },
    { ...duplicatePayload.groups[1].results[0], id: 2, primary_label: 'Alex Same', metadata: { team_name: 'Minnesota Twins', roster_status: 'ACTIVE' } },
  ]
  duplicatePayload.groups[2].results = []
  const html = renderDiscovery({ query: 'alex', payload: duplicatePayload })

  assert.equal((html.match(/Alex Same/g) || []).length, 4)
  assert.ok(htmlIncludes(html, 'Tampa Bay Rays'))
  assert.ok(htmlIncludes(html, 'Minnesota Twins'))
  assert.ok(htmlIncludes(html, 'href="/pitcher/1"'))
  assert.ok(htmlIncludes(html, 'href="/pitcher/2"'))
})

test('unified discovery distinguishes no results from a locally unavailable group', () => {
  const noResults = renderDiscovery({ payload: { ...discoveryPayload, result_count: 0 } })
  assert.ok(htmlIncludes(noResults, 'No teams, relievers, or today&#x27;s matchups match'))

  const partial = structuredClone(discoveryPayload)
  partial.status = 'partial'
  partial.result_count = 2
  partial.groups[1] = { entity_type: 'pitcher', status: 'unavailable', results: [] }
  const partialHtml = renderDiscovery({ payload: partial })
  assert.ok(htmlIncludes(partialHtml, 'This result group is temporarily unavailable.'))
  assert.ok(htmlIncludes(partialHtml, 'Tampa Bay Rays at Minnesota Twins'))
})

test('unified discovery is labeled keyboard reachable debounced and request bounded', async () => {
  const html = renderDiscovery()
  const source = await readFile(
    new URL('../src/components/search/SearchPage.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(htmlIncludes(html, 'id="global-discovery-search"'))
  assert.ok(htmlIncludes(html, 'aria-describedby="global-discovery-search-help"'))
  assert.ok(source.includes("event.key === 'Escape'"))
  assert.ok(source.includes('SEARCH_DEBOUNCE_MS = 250'))
  assert.equal(source.match(/searchFn\(/g)?.length, 1)
  assert.equal(source.includes('getTeamBoardV2'), false)
  assert.equal(source.includes('getPitcherFatigue'), false)
  assert.equal(source.includes('getScheduledGameMatchup'), false)
})

test('unified discovery keeps a linear mobile flow and a bounded desktop grid', async () => {
  const source = await readFile(
    new URL('../src/components/search/SearchPage.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('grid min-w-0 gap-5 lg:grid-cols-3'))
  assert.ok(source.includes('min-w-0'))
  assert.equal(source.includes('overflow-x-auto'), false)
  assert.equal(source.includes('min-w-['), false)
})
