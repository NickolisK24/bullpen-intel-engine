import assert from 'node:assert/strict'
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

const { WhatChangedCard } = await server.ssrLoadModule('/src/components/dashboard/WhatChangedCard.jsx')

const team = { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' }

const htmlIncludes = (html, text) => html.includes(text)

function renderCard(props = {}) {
  return renderToStaticMarkup(React.createElement(WhatChangedCard, props))
}

function makeChanges(overrides = {}) {
  return {
    state: 'changes',
    comparison: {
      anchor_game_date: '2026-06-06',
      current_game_date: '2026-06-07',
      global_latest_game_date: '2026-06-07',
      label: 'Compared with ACE: Jun 6 -> Jun 7',
      is_current: true,
      team_data_behind_league: false,
    },
    team_summary: null,
    pitcher_changes: [
      {
        type: 'status_change',
        pitcher_id: 1,
        pitcher_name: 'Shift Arm',
        from_status: 'Monitor',
        to_status: 'Limited',
        summary: 'Shift Arm moved from Monitor to Limited.',
      },
      {
        type: 'appearance',
        pitcher_id: 2,
        pitcher_name: 'Workload Arm',
        game_date: '2026-06-07',
        pitches: 24,
        summary: 'Pitched Sunday - 24 pitches.',
      },
    ],
    freshness: {
      latest_workload_date: '2026-06-07',
      is_current: true,
    },
    ...overrides,
  }
}

test('no followed team prompts without change data', () => {
  const html = renderCard()

  assert.ok(htmlIncludes(html, 'What Changed Since Last Game'))
  assert.ok(htmlIncludes(html, 'Follow your team to see how its bullpen changed after the last completed game.'))
})

test('loading state uses latest completed game language', () => {
  const html = renderCard({ followedTeam: team, loading: true })

  assert.ok(htmlIncludes(html, 'Checking how the bullpen moved after the latest completed game...'))
})

test('stale state shows paused workload copy with latest data date', () => {
  const html = renderCard({
    followedTeam: team,
    changes: makeChanges({
      state: 'stale',
      pitcher_changes: [],
      team_summary: null,
      freshness: {
        latest_workload_date: '2026-06-06',
        is_current: false,
      },
    }),
  })

  assert.ok(htmlIncludes(html, 'Bullpen movement is paused - latest data is from Jun 6.'))
  assert.ok(htmlIncludes(html, 'Jun 6'))
  assert.ok(!htmlIncludes(html, 'Shift Arm moved'))
})

test('no baseline state tells users to check after the next game', () => {
  const html = renderCard({
    followedTeam: team,
    changes: makeChanges({ state: 'no_baseline', pitcher_changes: [], team_summary: null }),
  })

  assert.ok(htmlIncludes(html, 'No earlier completed game is available for comparison yet. Check back after the next game.'))
})

test('no changes state renders a quiet empty summary', () => {
  const html = renderCard({
    followedTeam: team,
    changes: makeChanges({ state: 'no_changes', pitcher_changes: [], team_summary: null }),
  })

  assert.ok(htmlIncludes(html, 'No meaningful bullpen movement since the last completed game.'))
})

test('changes state renders pitcher summaries without team summary counts', () => {
  const html = renderCard({ followedTeam: team, changes: makeChanges() })

  assert.ok(htmlIncludes(html, 'Compared with ACE: Jun 6 -&gt; Jun 7'))
  assert.ok(!htmlIncludes(html, 'Available arms:'))
  assert.ok(!htmlIncludes(html, 'Bullpen condition moved from'))
  assert.ok(htmlIncludes(html, 'Shift Arm moved from Monitor to Limited.'))
  assert.ok(htmlIncludes(html, 'Pitched Sunday - 24 pitches.'))
})

test('comparison label is not vague weekday-only copy', () => {
  const html = renderCard({ followedTeam: team, changes: makeChanges() })

  assert.ok(!htmlIncludes(html, "since Saturday&#x27;s game"))
  assert.ok(!htmlIncludes(html, "since Saturday's game"))
  assert.ok(htmlIncludes(html, 'Jun 6'))
  assert.ok(htmlIncludes(html, 'Jun 7'))
})

test('team behind league limitation renders with both dates', () => {
  const html = renderCard({
    followedTeam: team,
    changes: makeChanges({
      state_reason_codes: ['meaningful_changes_detected', 'team_data_behind_league'],
      comparison: {
        anchor_game_date: '2026-06-03',
        current_game_date: '2026-06-05',
        global_latest_game_date: '2026-06-07',
        label: 'Compared with ACE: Jun 3 -> Jun 5',
        is_current: true,
        team_data_behind_league: true,
      },
      limitations: [
        'ACE latest game data is Jun 5 while league data is current through Jun 7.',
      ],
    }),
  })

  assert.ok(htmlIncludes(html, 'Compared with ACE: Jun 3 -&gt; Jun 5'))
  assert.ok(htmlIncludes(html, 'ACE latest game data is Jun 5 while league data is current through Jun 7.'))
})

test('error state can expose retry control', () => {
  const html = renderCard({
    followedTeam: team,
    error: 'API 500',
    onRetry: () => {},
  })

  assert.ok(htmlIncludes(html, 'The latest bullpen change read is unavailable right now.'))
  assert.ok(htmlIncludes(html, 'Retry'))
})
