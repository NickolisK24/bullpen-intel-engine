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
  team_state_change: {
    type: 'team_state_change',
    from_state: 'stretched',
    from_label: 'Stretched',
    to_state: 'vulnerable',
    to_label: 'Vulnerable',
    from_date: '2026-08-16',
    to_date: '2026-08-18',
    summary: 'Team State changed from Stretched to Vulnerable.',
  },
  team_state_comparison: {
    status: 'changed',
    limitation: null,
  },
  rest_status_change: {
    type: 'rest_status_change',
    field: 'rested_arm_count',
    label: 'Rested Options',
    from_value: 5,
    to_value: 7,
    from_date: '2026-08-16',
    to_date: '2026-08-18',
    transition: '5 → 7',
    summary: 'Rested options moved from 5 to 7.',
  },
  rest_status_comparison: {
    status: 'changed',
    limitation: null,
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

  assert.deepEqual(view.groups.map(group => group.key), ['team-state', 'rest-status', 'arm-read', 'appearance'])
  assert.ok(html.indexOf('Team State') < html.indexOf('Rested Options'))
  assert.ok(html.indexOf('Rested Options') < html.indexOf('Arm Read movement'))
  assert.ok(html.indexOf('Arm Read movement') < html.indexOf('New appearance / workload'))
  assert.match(html, /date(?:T|t)ime="2026-08-17"/)
  assert.match(html, /date(?:T|t)ime="2026-08-18"/)
  assert.ok(html.includes('Monitor → Limited'))
  assert.ok(html.includes('Stretched → Vulnerable'))
  assert.ok(html.includes(changes.team_state_change.summary))
  assert.ok(html.includes(changes.rest_status_change.transition))
  assert.ok(html.includes(changes.rest_status_change.summary))
  assert.match(html, /date(?:T|t)ime="2026-08-16"/)
  assert.ok(html.includes(changes.pitcher_changes[0].summary))
  assert.ok(html.includes('0 pitches'))
})

test('unknown categories are omitted rather than converted into no-change rows', () => {
  const unsupported = {
    ...changes,
    team_state_change: null,
    rest_status_change: null,
    pitcher_changes: [{ type: 'roster_status', pitcher_name: 'Current Arm', current_status: 'Optioned' }],
  }
  const html = render({ changes: unsupported })

  assert.equal(getWhatChangedView(unsupported).groups.length, 0)
  assert.equal(html.includes('Current Arm'), false)
  assert.ok(html.includes('No supported structured change category'))
  assert.equal(html.includes('No material changes were detected'), false)
})

test('quiet, no-baseline, freshness-blocked, unavailable, and error states remain distinct', () => {
  const quiet = render({ changes: {
    ...changes,
    state: 'no_changes',
    team_state_change: null,
    team_state_comparison: { status: 'unchanged', limitation: null },
    pitcher_changes: [],
  } })
  const baseline = render({ changes: {
    ...changes,
    state: 'no_baseline',
    team_state_change: null,
    comparison: { anchor_game_date: null, current_game_date: '2026-08-18' },
    pitcher_changes: [],
    limitations: ['No earlier completed game is available for comparison.'],
  } })
  const stale = render({ changes: {
    ...changes,
    state: 'stale',
    team_state_change: null,
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

test('an unavailable Team State lane prevents a definitive quiet-day claim', () => {
  const limitation = 'Backend-authored Team State comparison limitation.'
  const unavailable = {
    ...changes,
    state: 'no_changes',
    team_state_change: null,
    team_state_comparison: {
      status: 'unavailable',
      reason_code: 'contract_incompatible',
      limitation,
    },
    pitcher_changes: [],
  }
  const html = render({ changes: unavailable })

  assert.equal(html.includes('No material changes were detected'), false)
  assert.ok(html.includes('Team State comparison unavailable'))
  assert.ok(html.includes(limitation))
  assert.equal(html.includes('contract_incompatible'), false)
})

test('an unavailable Team State lane remains disclosed beside proven status movement', () => {
  const limitation = 'Backend-authored Team State comparison limitation.'
  const statusOnly = {
    ...changes,
    team_state_change: null,
    team_state_comparison: { status: 'unavailable', limitation },
    pitcher_changes: [changes.pitcher_changes[0]],
  }
  const html = render({ changes: statusOnly })

  assert.ok(html.includes('Monitor → Limited'))
  assert.ok(html.includes(changes.pitcher_changes[0].summary))
  assert.ok(html.includes(limitation))
  assert.equal(html.includes('No material changes were detected'), false)
})

test('an unavailable Team State lane remains disclosed beside proven appearance movement', () => {
  const limitation = 'Backend-authored Team State comparison limitation.'
  const appearanceOnly = {
    ...changes,
    team_state_change: null,
    team_state_comparison: { status: 'unavailable', limitation },
    pitcher_changes: [changes.pitcher_changes[1]],
  }
  const html = render({ changes: appearanceOnly })

  assert.ok(html.includes('New appearance / workload'))
  assert.ok(html.includes(changes.pitcher_changes[1].summary))
  assert.ok(html.includes(limitation))
  assert.equal(html.includes('No material changes were detected'), false)
})

test('an unavailable Rest Status lane prevents a false quiet claim and stays scoped', () => {
  const limitation = 'Backend-authored Rest Status comparison limitation.'
  const unavailable = {
    ...changes,
    state: 'no_changes',
    team_state_change: null,
    team_state_comparison: { status: 'unchanged', limitation: null },
    rest_status_change: null,
    rest_status_comparison: { status: 'unavailable', limitation },
    pitcher_changes: [],
  }
  const html = render({ changes: unavailable })

  assert.equal(html.includes('No material changes were detected'), false)
  assert.ok(html.includes('Rest Status comparison unavailable'))
  assert.ok(html.includes(limitation))
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
    '.reduce(', '.sort(', 'roster_authority', 'bullpen_stability',
    'workload_7d', 'workload_14d', 'rotation_impact', 'role_movement',
    "'Fresh'", "'Stretched'", "'Vulnerable'", 'from_state ===', 'to_state ===',
    'contract_incompatible', 'method_version_mismatch', 'previous_missing',
    'from_value -', 'to_value -',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('Team Board consumes the composed What Changed contract', async () => {
  const source = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')

  assert.equal((source.match(/getTeamChanges\(selectedTeam\)/g) || []).length, 0)
  assert.equal((source.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.ok(source.includes('teamBoardRead?.whatChanged'))
  assert.ok(source.includes('<TeamBoardWhatChanged'))
  assert.equal(source.includes('getTeamStory'), false)
  assert.equal(source.includes('<StoryCard'), false)
  assert.ok(source.indexOf('<TeamBoardRecentTransactions') < source.indexOf('<TeamBoardWhatChanged'))
  assert.ok(source.indexOf('<TeamBoardWhatChanged') < source.indexOf('<TeamReliefWorkPanel'))
})
