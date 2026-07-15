import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
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

test('Pitcher Search result clicks open existing Pitcher Detail from Bullpen', async () => {
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
  assert.ok(bullpenSource.includes("handlePitcherSelect(result.player_id, result, 'pitcher_search')"))
  assert.ok(bullpenSource.includes('navigate(buildPitcherHref(pitcherId'))
  assert.ok(bullpenSource.includes('<PitcherDetail pitcherId={selectedPitcher.pitcher_id} onClose={closeSelectedPitcher} />'))
  assert.ok(apiSource.includes('export const searchPitchers'))
  assert.ok(apiSource.includes('/pitchers/search'))
})
