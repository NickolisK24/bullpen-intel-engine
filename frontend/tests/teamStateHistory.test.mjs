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
  contract: 'team_state_history_v3',
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
  transaction_coverage: {
    status: 'partial',
    start: '2026-07-23',
    end: '2026-08-02',
    is_partial: true,
    retained_date_status_counts: { available: 1, partial: 0, unavailable: 1 },
    limitations: ['Transaction context includes only retained source windows.'],
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
      event_overlay: {
        status: 'withheld',
        outcome: 'unavailable',
        reason_code: 'contract_incompatible',
      },
      events: [],
      transaction_overlay: {
        status: 'unavailable',
        reason_code: 'transaction_source_unavailable',
      },
      transactions: [],
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
      event_overlay: {
        status: 'withheld',
        outcome: 'unavailable',
        reason_code: 'prior_publication_missing',
      },
      events: [],
      transaction_overlay: { status: 'available', reason_code: null },
      transactions: [],
    },
  ],
}

const changedPayload = {
  ...payload,
  coverage: {
    ...payload.coverage,
    start: '2026-07-23',
    end: '2026-07-24',
    covered_date_count: 2,
    missing_dates: [],
  },
  rows: [
    {
      ...payload.rows[0],
      represented_date: '2026-07-24',
      artifact: {
        ...payload.rows[0].artifact,
        public_id: 'artifact-new',
        citation_url: '/share/artifact-new',
      },
      comparison: {
        status: 'comparable',
        reason_code: null,
        boundary: false,
        transition: {
          from_code: 'stretched',
          from_state: 'Stretched',
          to_code: 'fresh',
          to_state: 'Fresh',
          changed: true,
        },
      },
      event_overlay: { status: 'available', outcome: 'changed', reason_code: null },
      events: [{
        event_type: 'team_state_change',
        event_id: 'team_state_change:147:artifact-old:artifact-new',
        event_date: '2026-07-24',
        from_date: '2026-07-23',
        to_date: '2026-07-24',
        label: 'Team State changed',
        from_state: { code: 'stretched', label: 'Stretched' },
        to_state: { code: 'fresh', label: 'Fresh' },
        citations: {
          previous: { public_id: 'artifact-old', citation_url: '/share/artifact-old' },
          current: { public_id: 'artifact-new', citation_url: '/share/artifact-new' },
        },
      }],
    },
    payload.rows[1],
  ],
}

const transactionPayload = {
  ...changedPayload,
  rows: [{
    ...changedPayload.rows[0],
    transaction_overlay: { status: 'available', reason_code: null },
    transactions: [
      {
        event_type: 'qualified_transaction',
        event_id: 'statsapi:100',
        event_date: '2026-07-24',
        transaction_key: 'statsapi:100',
        transaction_id: '100',
        normalized_category: 'recall',
        label: 'Recalled',
        description: 'History Arm was recalled.',
        pitcher: { pitcher_id: 10, player_mlb_id: 910001, name: 'History Arm' },
        team_relationship: { relationship: 'incoming', from_team_id: 555, to_team_id: 147 },
      },
      {
        event_type: 'qualified_transaction',
        event_id: 'statsapi:101',
        event_date: '2026-07-24',
        transaction_key: 'statsapi:101',
        transaction_id: '101',
        normalized_category: 'option',
        label: 'Optioned',
        description: 'Second Arm was optioned.',
        pitcher: { pitcher_id: 11, player_mlb_id: 910002, name: 'Second Arm' },
        team_relationship: { relationship: 'outgoing', from_team_id: 147, to_team_id: 555 },
      },
    ],
  }, changedPayload.rows[1]],
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
  assert.equal(source.includes('comparison.transition.from_state'), false)
  assert.equal(source.includes('comparison.transition.changed'), false)
  assert.equal(source.includes('rows[index - 1]'), false)
  assert.equal(source.includes('overflow-x-auto'), false)
  assert.equal(source.includes('min-w-['), false)
  assert.equal(source.includes('fixed inset'), false)
})

test('History renders one backend-supplied change marker under the affected state row', () => {
  const html = render({ payload: changedPayload })
  assert.equal((html.match(/data-testid="team-state-change-marker"/g) || []).length, 1)
  assert.ok(html.includes('Team State changed'))
  assert.ok(html.includes('aria-label="Stretched to Fresh"'))
  assert.ok(html.includes('Open earlier published observation'))
  assert.ok(html.includes('Open later published observation'))
  assert.ok(html.includes('href="/share/artifact-old"'))
  assert.ok(html.includes('href="/share/artifact-new"'))
  assert.ok(html.indexOf('The bullpen had strong rested coverage.') < html.indexOf('Team State changed'))
})

test('History distinguishes comparable unchanged from unavailable comparison', () => {
  const unchangedPayload = {
    ...changedPayload,
    rows: [{
      ...changedPayload.rows[0],
      comparison: {
        ...changedPayload.rows[0].comparison,
        transition: {
          from_code: 'fresh', from_state: 'Fresh',
          to_code: 'fresh', to_state: 'Fresh', changed: false,
        },
      },
      event_overlay: { status: 'available', outcome: 'unchanged', reason_code: null },
      events: [],
    }, changedPayload.rows[1]],
  }
  const unchanged = render({ payload: unchangedPayload })
  const unavailable = render({ payload })

  assert.equal(unchanged.includes('Team State changed'), false)
  assert.ok(unchanged.includes('Published comparison · Team State unchanged'))
  assert.equal(unavailable.includes('Team State unchanged'), false)
  assert.ok(unavailable.includes('Comparison boundary'))
})

test('History renders backend-supplied qualified transactions beneath the exact state date', () => {
  const html = render({ payload: transactionPayload })
  assert.equal((html.match(/data-testid="qualified-transaction-overlay"/g) || []).length, 1)
  assert.ok(html.includes('Roster moves'))
  assert.ok(html.includes('Recalled'))
  assert.ok(html.includes('History Arm was recalled.'))
  assert.ok(html.includes('Optioned'))
  assert.ok(html.includes('Second Arm was optioned.'))
  assert.ok(html.indexOf('The bullpen had strong rested coverage.') < html.indexOf('Roster moves'))
  assert.ok(html.indexOf('Team State changed') < html.indexOf('Roster moves'))
})

test('History keeps successful zero-event dates quiet and distinguishes incomplete context', () => {
  const available = render({
    payload: {
      ...payload,
      rows: [{
        ...payload.rows[0],
        transaction_overlay: { status: 'available', reason_code: null },
        transactions: [],
      }],
    },
  })
  const partial = render({
    payload: {
      ...payload,
      rows: [{
        ...payload.rows[0],
        transaction_overlay: { status: 'partial', reason_code: 'transaction_source_partial' },
        transactions: [],
      }],
    },
  })
  const unavailable = render({ payload })

  assert.equal(available.includes('Roster moves'), false)
  assert.equal(available.includes('No transactions'), false)
  assert.ok(partial.includes('Transaction context is incomplete for this date.'))
  assert.ok(unavailable.includes('Transaction context is unavailable for this date.'))
})

test('History does not infer transaction meaning or historical team attribution in React', () => {
  const source = readFileSync(new URL('../src/components/history/TeamHistoryPage.jsx', import.meta.url), 'utf8')
  for (const forbidden of [
    'TRANSACTION_PUBLIC_LABELS',
    'normalized_category ===',
    'from_team_id ===',
    'to_team_id ===',
    'caused',
    'led to',
    'because of',
    'resulted in',
    'improved',
    'worsened',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('History change markers remain linear and do not add scroll-container geometry', () => {
  const source = readFileSync(new URL('../src/components/history/TeamHistoryPage.jsx', import.meta.url), 'utf8')
  assert.ok(source.includes('flex-wrap'))
  assert.ok(source.includes('tablet:grid-cols-[8rem_minmax(0,1fr)]'))
  assert.equal(source.includes('overflow-x-auto'), false)
  assert.equal(source.includes('min-w-['), false)
  assert.equal(source.includes('fixed inset'), false)
  assert.equal(source.includes('grid-cols-2'), false)
  assert.ok(source.includes('space-y-1'))
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
