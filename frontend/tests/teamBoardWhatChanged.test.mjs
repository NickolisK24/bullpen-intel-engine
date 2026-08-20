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

after(async () => server.close())

const { default: TeamBoardWhatChanged } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardWhatChanged.jsx',
)
const { getWhatChangedView } = await server.ssrLoadModule(
  '/src/components/bullpen/board/whatChangedView.js',
)

const changes = {
  capability: 'what_changed_since_last_game',
  state: 'changes',
  comparison: {
    anchor_game_date: '2026-08-17',
    current_game_date: '2026-08-18',
  },
  pitcher_changes: [
    {
      type: 'status_change',
      pitcher_id: 9,
      pitcher_name: 'Shift Arm',
      from_status: 'Monitor',
      to_status: 'Limited',
      summary: 'Shift Arm moved from Monitor to Limited.',
    },
    {
      type: 'appearance',
      pitcher_id: 7,
      pitcher_name: 'Work Arm',
      game_date: '2026-08-18',
      pitches: 0,
      summary: 'Pitched Tuesday - 0 pitches.',
    },
  ],
  limitations: [],
}

const render = props => renderToStaticMarkup(React.createElement(TeamBoardWhatChanged, props))

test('supported change groups render in materiality order with governed endpoints and copy', () => {
  const view = getWhatChangedView(changes)
  const html = render({ changes })

  assert.deepEqual(view.groups.map(group => group.key), ['arm-read', 'appearance'])
  assert.ok(html.indexOf('Arm Read movement') < html.indexOf('New appearance / workload'))
  assert.match(html, /date(?:T|t)ime="2026-08-17"/)
  assert.match(html, /date(?:T|t)ime="2026-08-18"/)
  assert.ok(html.includes('Monitor → Limited'))
  assert.ok(html.includes(changes.pitcher_changes[0].summary))
  assert.ok(html.includes('0 pitches'))
})

test('unknown categories are omitted rather than converted into no-change rows', () => {
  const unsupported = {
    ...changes,
    pitcher_changes: [{ type: 'roster_status', pitcher_name: 'Current Arm', current_status: 'Optioned' }],
  }
  const html = render({ changes: unsupported })

  assert.equal(getWhatChangedView(unsupported).groups.length, 0)
  assert.equal(html.includes('Current Arm'), false)
  assert.ok(html.includes('No supported structured change category'))
  assert.equal(html.includes('No material changes were detected'), false)
})

test('quiet, no-baseline, freshness-blocked, unavailable, and error states remain distinct', () => {
  const quiet = render({ changes: { ...changes, state: 'no_changes', pitcher_changes: [] } })
  const baseline = render({ changes: {
    ...changes,
    state: 'no_baseline',
    comparison: { anchor_game_date: null, current_game_date: '2026-08-18' },
    pitcher_changes: [],
    limitations: ['No earlier completed game is available for comparison.'],
  } })
  const stale = render({ changes: {
    ...changes,
    state: 'stale',
    pitcher_changes: [],
    limitations: ['Current workload data is not fresh enough to compare safely.'],
  } })
  const error = render({ changes, error: 'private exception', onRetry: () => {} })

  assert.ok(quiet.includes('data-state="quiet"'))
  assert.ok(quiet.includes('No material changes were detected'))
  assert.ok(baseline.includes('No comparison baseline'))
  assert.equal(baseline.includes('data-state="error"'), false)
  assert.ok(stale.includes('Comparison freshness blocked'))
  assert.equal(stale.includes('data-state="error"'), false)
  assert.ok(error.includes('data-state="error"'))
  assert.equal(error.includes('private exception'), false)
})

test('arm subjects reuse the existing pitcher handoff without making whole rows interactive', () => {
  const html = render({ changes, onSelectPitcher: () => {} })

  assert.equal((html.match(/type="button"/g) || []).length, 2)
  assert.ok(html.includes('focus-visible:ring-line-focus'))
  assert.equal(html.includes('role="button"'), false)
})

test('the view model presents the public contract without client snapshot or category derivation', async () => {
  const source = await readFile(new URL('../src/components/bullpen/board/whatChangedView.js', import.meta.url), 'utf8')

  for (const forbidden of [
    '.reduce(', '.sort(', 'team_state', 'roster_authority', 'bullpen_stability',
    'workload_7d', 'workload_14d', 'rotation_impact', 'role_movement',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('Team Board replaces its story request with the existing changes contract', async () => {
  const source = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')

  assert.equal((source.match(/getTeamChanges\(selectedTeam\)/g) || []).length, 1)
  assert.equal((source.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(source.includes('<TeamBoardWhatChanged'))
  assert.equal(source.includes('getTeamStory'), false)
  assert.equal(source.includes('<StoryCard'), false)
  assert.ok(source.indexOf('<TeamBoardRecentTransactions') < source.indexOf('<TeamBoardWhatChanged'))
  assert.ok(source.indexOf('<TeamBoardWhatChanged') < source.indexOf('<TeamReliefWorkPanel'))
})
