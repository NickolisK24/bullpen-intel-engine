import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

const server = await createServer({ root: process.cwd(), server: { middlewareMode: true }, appType: 'custom', logLevel: 'silent' })
after(async () => server.close())

const { default: TeamBoardWhatChanged } = await server.ssrLoadModule('/src/components/bullpen/board/TeamBoardWhatChanged.jsx')
const { getWhatChangedView } = await server.ssrLoadModule('/src/components/bullpen/board/whatChangedView.js')

const changes = {
  contract: 'team_board_what_changed_v1',
  state: 'changes',
  comparisonStatus: 'partial',
  currentRepresentedDate: '2026-09-22',
  previousRepresentedDate: '2026-09-21',
  quietMessage: null,
  domains: {
    team_state: { status: 'complete' }, roster: { status: 'complete' },
    workload_rest: { status: 'complete' }, transactions: { status: 'complete' },
    rotation: { status: 'complete' },
    roles_deployment: { status: 'not_comparable', reason_code: 'role_movement_not_governed' },
    performance: { status: 'not_comparable', reason_code: 'performance_materiality_not_governed' },
  },
  events: [
    { key: 'state', type: 'team_state_changed', domain: 'team_state', subjectId: null, eventDate: null, previousValue: 'Fresh', currentValue: 'Stretched', facts: {}, summary: 'Team State changed from Fresh to Stretched.' },
    { key: 'roster', type: 'active_bullpen_joined', domain: 'roster', subjectId: 44, eventDate: null, previousValue: null, currentValue: 'active', facts: { pitcher_name: 'Joined Arm' }, summary: 'Joined Arm joined the active bullpen.' },
    { key: 'usage', type: 'back_to_back_started', domain: 'workload_rest', subjectId: 55, eventDate: '2026-09-22', previousValue: false, currentValue: true, facts: { pitcher_name: 'Used Arm' }, summary: 'Used Arm now has back-to-back usage.' },
  ],
}

const render = props => renderToStaticMarkup(React.createElement(TeamBoardWhatChanged, props))

test('renders backend-authored events in their supplied deterministic order', () => {
  const html = render({ changes })
  assert.ok(html.indexOf(changes.events[0].summary) < html.indexOf(changes.events[1].summary))
  assert.ok(html.indexOf(changes.events[1].summary) < html.indexOf(changes.events[2].summary))
  assert.match(html, /Since/)
  assert.match(html, /Partial comparison/)
  assert.match(html, /Roles deployment, Performance/i)
})

test('quiet, missing-predecessor, partial, loading, and error states remain distinct', () => {
  const quiet = render({ changes: {
    ...changes, state: 'quiet', events: [], quietMessage: 'No material bullpen changes since the previous trusted update.',
    domains: { ...changes.domains, team_state: { status: 'complete', outcome: 'unchanged' } },
  } })
  const missing = render({ changes: { ...changes, state: 'unavailable', comparisonStatus: 'unavailable', previousRepresentedDate: null, events: [] } })
  const loading = render({ changes: null, loading: true })
  const error = render({ changes, error: 'private error', onRetry: () => {} })
  const legacy = render({ changes: null })
  assert.match(quiet, /No material bullpen changes/)
  assert.match(quiet, /Team State was unchanged/)
  assert.match(quiet, /data-state="quiet"/)
  assert.match(missing, /No prior trusted comparison/)
  assert.match(loading, /Loading governed bullpen changes/)
  assert.match(error, /What Changed unavailable/)
  assert.equal(error.includes('private error'), false)
  assert.match(legacy, /does not contain a frozen comparison/)
  assert.equal(legacy.includes('No prior trusted comparison'), false)
})

test('the view preserves backend text and values without diffing or baseball interpretation', async () => {
  const view = getWhatChangedView(changes)
  assert.deepEqual(view.events.map(event => event.summary), changes.events.map(event => event.summary))
  assert.equal(view.events[0].previousValue, 'Fresh')
  assert.equal(view.events[0].currentValue, 'Stretched')
  const source = await readFile(new URL('../src/components/bullpen/board/whatChangedView.js', import.meta.url), 'utf8')
  assert.equal(source.includes('ERA'), false)
  assert.equal(source.includes('previousValue !== currentValue'), false)
})

test('pitcher and section handoffs are keyboard-native controls', () => {
  const selected = []
  const html = render({ changes, onSelectPitcher: id => selected.push(id) })
  assert.match(html, /<button[^>]*>Review Joined Arm<\/button>/)
  assert.match(html, /href="#active-bullpen"/)
  assert.match(html, /href="#recent-usage"/)
  assert.equal(html.includes('onClick'), false)
})

test('no predictive, evaluative, role-movement, or performance-delta copy is introduced', () => {
  const html = render({ changes }).toLowerCase()
  for (const forbidden of ['will pitch', 'manager intent', 'era improved', 'whip worsened', 'moved into setup', 'major concern']) {
    assert.equal(html.includes(forbidden), false)
  }
})
