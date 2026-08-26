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

const {
  HistoryStateRow,
  TeamHistoryPageView,
  historyRowCategory,
} = await server.ssrLoadModule('/src/components/history/TeamHistoryPage.jsx')
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
        corrected_publication: false,
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

const ordinaryRow = {
  ...changedPayload.rows[0],
  represented_date: '2026-07-25',
  explanation: 'Ordinary frozen explanation remains available on demand.',
  limitations: ['Ordinary retained limitation.'],
  artifact: {
    ...changedPayload.rows[0].artifact,
    public_id: 'artifact-ordinary',
    citation_url: '/share/artifact-ordinary',
    corrected_publication: false,
  },
  comparison: {
    status: 'comparable',
    reason_code: null,
    boundary: false,
    transition: {
      from_code: 'fresh', from_state: 'Fresh',
      to_code: 'fresh', to_state: 'Fresh', changed: false,
    },
  },
  event_overlay: { status: 'available', outcome: 'unchanged', reason_code: null },
  events: [],
  transaction_overlay: { status: 'available', reason_code: null },
  transactions: [],
}

const ordinaryPayload = {
  ...payload,
  coverage: {
    ...payload.coverage,
    start: '2026-07-23',
    end: '2026-07-25',
    covered_date_count: 2,
    missing_dates: [],
  },
  rows: [ordinaryRow, payload.rows[1]],
}

const rosterOnlyRow = {
  ...ordinaryRow,
  artifact: {
    ...ordinaryRow.artifact,
    public_id: 'artifact-roster',
    citation_url: '/share/artifact-roster',
  },
  transactions: [{
    event_type: 'qualified_transaction',
    event_id: 'statsapi:roster-only',
    event_date: ordinaryRow.represented_date,
    label: 'Recalled',
    description: 'History Arm was recalled.',
    pitcher: { pitcher_id: 10, player_mlb_id: 910001, name: 'History Arm' },
    team_relationship: { relationship: 'incoming', from_team_id: 555, to_team_id: 147 },
  }],
}

const representativeRows = Array.from({ length: 34 }, (_, index) => {
  const date = new Date(Date.UTC(2026, 7, 25 - index)).toISOString().slice(0, 10)
  const artifact = {
    ...ordinaryRow.artifact,
    public_id: `artifact-representative-${index}`,
    citation_url: `/share/artifact-representative-${index}`,
    corrected_publication: index === 16,
  }
  if (index === 33) {
    return {
      ...payload.rows[1],
      represented_date: date,
      artifact,
      transaction_overlay: { status: 'available', reason_code: null },
    }
  }
  if ([4, 20].includes(index)) {
    return {
      ...changedPayload.rows[0],
      represented_date: date,
      artifact,
    }
  }
  if ([8, 24].includes(index)) {
    return {
      ...rosterOnlyRow,
      represented_date: date,
      artifact,
      transactions: rosterOnlyRow.transactions.map(event => ({ ...event, event_date: date, event_id: `${event.event_id}-${index}` })),
    }
  }
  if (index === 12) {
    return {
      ...ordinaryRow,
      represented_date: date,
      artifact,
      comparison: { status: 'comparison_unavailable', reason_code: 'comparison_authority_missing', boundary: true },
      event_overlay: { status: 'withheld', outcome: 'unavailable', reason_code: 'comparison_authority_missing' },
    }
  }
  return { ...ordinaryRow, represented_date: date, artifact }
})

const representativePayload = {
  ...payload,
  coverage: {
    ...payload.coverage,
    start: representativeRows.at(-1).represented_date,
    end: representativeRows[0].represented_date,
    covered_date_count: representativeRows.length,
    missing_dates: [],
  },
  rows: representativeRows,
}

const render = props => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(TeamHistoryPageView, props)),
)

const renderRow = (row, props = {}) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, React.createElement(HistoryStateRow, { row, ...props })),
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
  assert.ok(html.includes('aria-label="History months"'))
  assert.ok(html.includes('href="#history-month-2026-08"'))
  assert.ok(html.includes('href="#history-month-2026-07"'))
  assert.ok(html.includes('href="#history-top"'))
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
  assert.ok(html.includes('View previous observation'))
  assert.ok(html.includes('View published observation'))
  assert.equal(html.includes('View current observation'), false)
  assert.ok(html.includes('href="/share/artifact-old"'))
  assert.ok(html.includes('href="/share/artifact-new"'))
  assert.equal((html.match(/href="\/share\/artifact-new"/g) || []).length, 1)
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

test('ordinary comparable unchanged rows default compact without dropping date or Team State', () => {
  const html = render({ payload: ordinaryPayload })

  assert.ok(html.includes('data-row-category="ordinary-unchanged"'))
  assert.ok(html.includes('dateTime="2026-07-25"'))
  assert.ok(html.includes('Fresh'))
  assert.ok(html.includes('Unchanged'))
  assert.ok(html.includes('aria-expanded="false"'))
  assert.ok(html.includes('aria-label="View details for Jul 25, 2026"'))
  assert.ok(html.includes('min-h-11'))
  assert.equal(html.includes('Ordinary frozen explanation remains available on demand.'), false)
  assert.equal(html.includes('href="/share/artifact-ordinary"'), false)
})

test('ordinary row disclosure exposes the frozen explanation and exact immutable citation', () => {
  const html = renderRow(ordinaryRow, { defaultDetailsOpen: true })

  assert.ok(html.includes('aria-expanded="true"'))
  assert.ok(html.includes('aria-label="Hide details for Jul 25, 2026"'))
  assert.ok(html.includes('data-testid="history-row-details"'))
  assert.ok(html.includes('Ordinary frozen explanation remains available on demand.'))
  assert.ok(html.includes('Ordinary retained limitation.'))
  assert.ok(html.includes('View published observation'))
  assert.ok(html.includes('href="/share/artifact-ordinary"'))
})

test('row categories are deterministic projections of existing backend-owned fields', () => {
  assert.equal(historyRowCategory(ordinaryRow), 'ordinary-unchanged')
  assert.equal(historyRowCategory(changedPayload.rows[0]), 'meaningful-change')
  assert.equal(historyRowCategory(rosterOnlyRow), 'roster-context')
  assert.equal(historyRowCategory(payload.rows[0]), 'corrected')
  assert.equal(historyRowCategory(payload.rows[1]), 'standalone')
  assert.equal(historyRowCategory({
    ...ordinaryRow,
    comparison: { status: 'comparison_unavailable', boundary: true },
    event_overlay: { status: 'withheld', outcome: 'unavailable' },
  }), 'boundary')
})

test('meaningful, roster, boundary, correction, and standalone rows remain expanded', () => {
  const changed = renderRow(changedPayload.rows[0])
  const roster = renderRow(rosterOnlyRow)
  const boundary = renderRow({
    ...ordinaryRow,
    artifact: { ...ordinaryRow.artifact, public_id: 'artifact-boundary' },
    comparison: { status: 'comparison_unavailable', reason_code: 'comparison_authority_missing', boundary: true },
    event_overlay: { status: 'withheld', outcome: 'unavailable', reason_code: 'comparison_authority_missing' },
  })
  const unavailableComparison = renderRow({
    ...ordinaryRow,
    artifact: { ...ordinaryRow.artifact, public_id: 'artifact-comparison-unavailable' },
    comparison: { status: 'comparison_unavailable', reason_code: 'comparison_authority_missing', boundary: false },
    event_overlay: { status: 'withheld', outcome: 'unavailable', reason_code: 'comparison_authority_missing' },
  })
  const corrected = renderRow(payload.rows[0])
  const standalone = renderRow(payload.rows[1])

  assert.ok(changed.includes('data-row-category="meaningful-change"'))
  assert.ok(changed.includes('Team State changed'))
  assert.ok(changed.includes('The bullpen had strong rested coverage.'))
  assert.ok(roster.includes('data-row-category="roster-context"'))
  assert.ok(roster.includes('Roster moves'))
  assert.ok(roster.includes('History Arm was recalled.'))
  assert.ok(boundary.includes('data-row-category="boundary"'))
  assert.ok(boundary.includes('Comparison boundary — these adjacent publications are not proven comparable.'))
  assert.ok(unavailableComparison.includes('data-row-category="boundary"'))
  assert.ok(unavailableComparison.includes('Comparison unavailable'))
  assert.ok(corrected.includes('data-row-category="corrected"'))
  assert.ok(corrected.includes('Corrected publication'))
  assert.ok(standalone.includes('data-row-category="standalone"'))
  assert.ok(standalone.includes('Recent work narrowed the clean options.'))
  assert.equal(standalone.includes('Unchanged'), false)
  for (const html of [changed, roster, boundary, corrected, standalone]) {
    assert.equal(html.includes('aria-expanded="false"'), false)
    assert.ok(html.includes('View published observation'))
  }
})

test('every retained state date and explicit gap remains represented', () => {
  const html = render({ payload })
  for (const date of ['2026-08-02', '2026-08-01', '2026-07-23']) {
    assert.equal((html.match(new RegExp(`dateTime="${date}"`, 'g')) || []).length, 1, date)
  }
  assert.equal((html.match(/data-testid="history-state-row"/g) || []).length, payload.rows.length)
})

test('representative retained range compresses only ordinary rows and preserves all 34 dates', () => {
  const html = render({ payload: representativePayload })

  assert.equal((html.match(/data-testid="history-state-row"/g) || []).length, 34)
  assert.equal((html.match(/data-row-category="ordinary-unchanged"/g) || []).length, 27)
  assert.equal((html.match(/aria-expanded="false"/g) || []).length, 27)
  assert.equal((html.match(/data-row-category="meaningful-change"/g) || []).length, 2)
  assert.equal((html.match(/data-row-category="roster-context"/g) || []).length, 2)
  assert.equal((html.match(/data-row-category="boundary"/g) || []).length, 1)
  assert.equal((html.match(/data-row-category="corrected"/g) || []).length, 1)
  assert.equal((html.match(/data-row-category="standalone"/g) || []).length, 1)
  for (const row of representativeRows) {
    assert.equal((html.match(new RegExp(`dateTime="${row.represented_date}"`, 'g')) || []).length, 1, row.represented_date)
  }
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

test('History disclosure remains local, keyboard-native, and request-free', () => {
  const source = readFileSync(new URL('../src/components/history/TeamHistoryPage.jsx', import.meta.url), 'utf8')

  assert.ok(source.includes("const [detailsOpen, setDetailsOpen] = useState(defaultDetailsOpen)"))
  assert.ok(source.includes("aria-expanded={detailsOpen ? 'true' : 'false'}"))
  assert.ok(source.includes('aria-controls={detailId}'))
  assert.ok(source.includes('onClick={() => setDetailsOpen(open => !open)}'))
  assert.ok(source.includes("type=\"button\""))
  assert.ok(source.includes('detailsOpen &&'))
  assert.equal((source.match(/getTeamStateHistory\(teamAbbreviation, 2026\)/g) || []).length, 1)
  for (const forbidden of ['getPublicShareArtifact', 'getTeamBoardV2', 'fetch(', 'axios', 'overflow-x-auto', 'fixed inset']) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('History responsive structure keeps compact and meaningful rows aligned without nested scrolling', () => {
  const source = readFileSync(new URL('../src/components/history/TeamHistoryPage.jsx', import.meta.url), 'utf8')

  assert.ok(source.includes('tablet:grid-cols-[8rem_minmax(0,1fr)]'))
  assert.ok(source.includes("isOrdinary ? 'border-line-subtle py-3' : 'border-line-default py-5'"))
  assert.ok(source.includes('flex-wrap'))
  assert.ok(source.includes('break-words'))
  assert.ok(source.includes('min-h-11'))
  assert.equal(source.includes('overflow-x-auto'), false)
  assert.equal(source.includes('overflow-y-auto'), false)
  assert.equal(source.includes('min-w-['), false)
  assert.equal(source.includes('grid-cols-2'), false)
  assert.equal(source.includes('h-screen'), false)
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
