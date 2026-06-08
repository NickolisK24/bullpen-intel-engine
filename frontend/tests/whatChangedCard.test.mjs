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
      label: "since Saturday's game",
      is_current: true,
    },
    team_summary: {
      summary: 'Available arms: 4 -> 2; Bullpen condition moved from manageable to elevated.',
    },
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
  assert.ok(htmlIncludes(html, 'Follow your team to see what changed since their last game.'))
})

test('loading state uses latest completed game language', () => {
  const html = renderCard({ followedTeam: team, loading: true })

  assert.ok(htmlIncludes(html, 'Loading what changed since the latest completed game...'))
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

  assert.ok(htmlIncludes(html, 'Bullpen updates are paused'))
  assert.ok(htmlIncludes(html, 'Jun 6'))
  assert.ok(!htmlIncludes(html, 'Shift Arm moved'))
})

test('no baseline state tells users to check after the next game', () => {
  const html = renderCard({
    followedTeam: team,
    changes: makeChanges({ state: 'no_baseline', pitcher_changes: [], team_summary: null }),
  })

  assert.ok(htmlIncludes(html, 'No earlier game to compare yet. Check back after the next game.'))
})

test('no changes state renders a quiet empty summary', () => {
  const html = renderCard({
    followedTeam: team,
    changes: makeChanges({ state: 'no_changes', pitcher_changes: [], team_summary: null }),
  })

  assert.ok(htmlIncludes(html, 'No meaningful bullpen changes since the last completed game.'))
})

test('changes state renders backend team summary and pitcher summaries', () => {
  const html = renderCard({ followedTeam: team, changes: makeChanges() })

  assert.ok(htmlIncludes(html, 'Available arms: 4 -&gt; 2'))
  assert.ok(htmlIncludes(html, 'Bullpen condition moved from manageable to elevated.'))
  assert.ok(htmlIncludes(html, 'Shift Arm moved from Monitor to Limited.'))
  assert.ok(htmlIncludes(html, 'Pitched Sunday - 24 pitches.'))
})

test('error state can expose retry control', () => {
  const html = renderCard({
    followedTeam: team,
    error: 'API 500',
    onRetry: () => {},
  })

  assert.ok(htmlIncludes(html, 'What changed is unavailable right now.'))
  assert.ok(htmlIncludes(html, 'Retry'))
})
