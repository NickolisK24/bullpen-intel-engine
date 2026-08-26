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

const { TeamHistoryPageView } = await server.ssrLoadModule('/src/components/history/TeamHistoryPage.jsx')
const { APP_ROUTES } = await server.ssrLoadModule('/src/App.jsx')
const { buildTeamHistoryHref } = await server.ssrLoadModule('/src/utils/evidenceLinks.js')

const payload = {
  capability: 'team_state_history',
  contract: 'team_state_history_v1',
  status: 'available',
  team: {
    team_id: 147,
    team_name: 'Test Club',
    team_abbreviation: 'TST',
    team_board_href: '/bullpen?view=board&team=TST',
  },
  season: 2026,
  coverage: {
    start: '2026-07-23',
    end: '2026-08-02',
    covered_date_count: 2,
    missing_dates: ['2026-08-01'],
    is_partial: true,
  },
  rows: [
    {
      represented_date: '2026-08-02',
      team_state: { public_code: 'fresh', public_label: 'Fresh' },
      headline: 'Test Club bullpen — Fresh',
      explanation: 'The bullpen had strong rested coverage.',
      limitations: [],
      artifact: {
        public_id: 'artifact-new',
        citation_url: '/share/artifact-new',
        render_version: 'team-state-1.2.0',
        corrected_publication: true,
      },
      comparison: {
        status: 'comparison_unavailable',
        reason_code: 'contract_incompatible',
        boundary: true,
        transition: null,
      },
    },
    {
      represented_date: '2026-07-23',
      team_state: { public_code: 'stretched', public_label: 'Stretched' },
      explanation: 'Recent work narrowed the clean options.',
      limitations: ['One retained source was limited.'],
      artifact: {
        public_id: 'artifact-old',
        citation_url: '/share/artifact-old',
        render_version: 'team-state-1.0.0',
      },
      comparison: null,
    },
  ],
}

const render = props => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(TeamHistoryPageView, props)),
)

test('History has a canonical standalone team route and helper', () => {
  assert.equal(APP_ROUTES.find(route => route.path === '/history/team/:abbr')?.Component?.name, 'TeamHistoryPage')
  assert.equal(buildTeamHistoryHref('tst'), '/history/team/TST')
  assert.equal(buildTeamHistoryHref(null), null)
})

test('History renders one h1, coverage, month groups, newest-first rows, and citations', () => {
  const html = render({ payload })
  assert.equal((html.match(/<h1/g) || []).length, 1)
  assert.ok(html.includes('Test Club Team State History'))
  assert.ok(html.includes('Retained coverage'))
  assert.ok(html.indexOf('August 2026') < html.indexOf('July 2026'))
  assert.ok(html.indexOf('Fresh') < html.indexOf('Stretched'))
  assert.ok(html.includes('href="/share/artifact-new"'))
  assert.ok(html.includes('href="/share/artifact-old"'))
  assert.ok(html.includes('Corrected publication'))
})

test('History shows gaps and comparison boundaries without inferring transitions', () => {
  const html = render({ payload })
  assert.ok(html.includes('Historical Team State unavailable. No state is carried forward.'))
  assert.ok(html.includes('Comparison boundary'))
  assert.equal(html.includes('Stretched → Fresh'), false)
  const source = readFileSync(new URL('../src/components/history/TeamHistoryPage.jsx', import.meta.url), 'utf8')
  assert.equal(source.includes('comparison.transition.from_state'), true)
  assert.equal(source.includes('rows[index - 1]'), false)
  assert.equal(source.includes('overflow-x-auto'), false)
  assert.equal(source.includes('min-w-['), false)
  assert.equal(source.includes('fixed inset'), false)
})

test('History keeps current Team Board context separate', () => {
  const html = render({ payload })
  assert.ok(html.includes('Open current Test Club Team Board'))
  assert.ok(html.includes('href="/bullpen?view=board&amp;team=TST"'))
})

test('History preserves loading, empty, and retryable error states', () => {
  assert.ok(render({ loading: true }).includes('Loading Team State history'))
  assert.ok(render({ error: 'History request failed', onRetry: () => {} }).includes('History request failed'))
  assert.ok(render({ payload: { ...payload, rows: [], coverage: { ...payload.coverage, missing_dates: [] } } })
    .includes('Historical Team State is not available'))
})

test('History owns one eager request and no Team Board or per-artifact fan-out', () => {
  const page = readFileSync(new URL('../src/components/history/TeamHistoryPage.jsx', import.meta.url), 'utf8')
  const api = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  assert.equal((page.match(/getTeamStateHistory\(teamAbbreviation, 2026\)/g) || []).length, 1)
  assert.ok(api.includes('request(`/bullpen/teams/${encodeURIComponent(teamAbbreviation)}/history'))
  for (const forbidden of ['getTeamBoardV2', 'getPublicShareArtifact', 'getTeamChanges', 'getTeamReliefWork']) {
    assert.equal(page.includes(forbidden), false, forbidden)
  }
})

test('Team Board exposes a direct History handoff without loading History', () => {
  const board = readFileSync(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const answer = readFileSync(new URL('../src/components/bullpen/board/TeamBoardAnswerBlock.jsx', import.meta.url), 'utf8')
  assert.ok(board.includes('buildTeamHistoryHref'))
  assert.ok(board.includes('historyHref={buildTeamHistoryHref'))
  assert.ok(answer.includes('View History'))
  assert.equal(board.includes('getTeamStateHistory'), false)
})
