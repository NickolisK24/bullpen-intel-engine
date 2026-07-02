import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => {
  await server.close()
})

const { DashboardView } = await server.ssrLoadModule('/src/components/dashboard/Dashboard.jsx')
const { FollowMyTeamCard } = await server.ssrLoadModule('/src/components/dashboard/FollowMyTeam.jsx')
const preference = await server.ssrLoadModule('/src/utils/followedTeamPreference.js')

const {
  FOLLOWED_TEAM_STORAGE_KEY,
  buildFollowedTeamHref,
  clearFollowedTeamPreference,
  readFollowedTeamPreference,
  resolveFollowedTeam,
  saveFollowedTeamPreference,
} = preference

const teams = [
  { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' },
  { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' },
]

const acesBoard = makeBoard({
  team: teams[0],
  cardsByStatus: {
    Available: [
      { pitcher_id: 1, name: 'Fresh Arm', availability_status: 'Available' },
      { pitcher_id: 2, name: 'Fresh Arm Two', availability_status: 'Available' },
      { pitcher_id: 3, name: 'Fresh Arm Three', availability_status: 'Available' },
      { pitcher_id: 4, name: 'Fresh Arm Four', availability_status: 'Available' },
    ],
    Monitor: [{ pitcher_id: 20, name: 'Watch Arm', availability_status: 'Monitor' }],
    Limited: [{ pitcher_id: 30, name: 'Limited Arm', availability_status: 'Limited' }],
  },
})

const htmlIncludes = (html, text) => html.includes(text)
const inRouter = (el) => renderToStaticMarkup(React.createElement(MemoryRouter, null, el))

function createMemoryStorage() {
  const values = new Map()
  return {
    getItem(key) {
      return values.has(key) ? values.get(key) : null
    },
    setItem(key, value) {
      values.set(key, String(value))
    },
    removeItem(key) {
      values.delete(key)
    },
  }
}

function createFailingStorage() {
  return {
    getItem() { throw new Error('storage unavailable') },
    setItem() { throw new Error('storage unavailable') },
    removeItem() { throw new Error('storage unavailable') },
  }
}

test('dashboard does not render Follow My Team before retention phase', () => {
  const html = inRouter(React.createElement(DashboardView, { data: null, loading: true }))

  assert.ok(!htmlIncludes(html, 'Follow My Team'))
  assert.ok(!htmlIncludes(html, 'Follow your team to make BaseballOS open with the bullpen you care about.'))
  assert.ok(!htmlIncludes(html, 'Loading team list...'))
})

test('first-time card lets the user choose a followed team', () => {
  const html = inRouter(React.createElement(FollowMyTeamCard, { teams }))

  assert.ok(htmlIncludes(html, 'Choose followed team'))
  assert.ok(htmlIncludes(html, 'ACE · Aces'))
  assert.ok(htmlIncludes(html, 'BEA · Bears'))
  assert.ok(!htmlIncludes(html, 'Clear followed team'))
})

test('followed team preference persists locally and can be changed', () => {
  const storage = createMemoryStorage()

  const savedAces = saveFollowedTeamPreference(teams[0], storage, () => '2026-06-08T12:00:00Z')
  assert.deepEqual(savedAces, {
    team_id: 1,
    team_abbreviation: 'ACE',
    team_name: 'Aces',
  })
  assert.equal(readFollowedTeamPreference(storage).team_abbreviation, 'ACE')

  saveFollowedTeamPreference(teams[1], storage, () => '2026-06-08T12:05:00Z')
  assert.equal(readFollowedTeamPreference(storage).team_abbreviation, 'BEA')

  const raw = JSON.parse(storage.getItem(FOLLOWED_TEAM_STORAGE_KEY))
  assert.equal(raw.saved_at, '2026-06-08T12:05:00Z')
})

test('returning card emphasizes the followed team and links to its board', () => {
  const html = inRouter(React.createElement(FollowMyTeamCard, {
    teams,
    followedTeam: teams[0],
    board: acesBoard,
  }))

  assert.ok(htmlIncludes(html, 'Aces'))
  assert.ok(htmlIncludes(html, 'What does my bullpen look like right now?'))
  assert.ok(htmlIncludes(html, 'Overall Availability: Manageable'))
  assert.ok(htmlIncludes(html, 'This pen has ordinary usable room right now.'))
  assert.ok(htmlIncludes(html, '4 of 6 relievers are classified Available.'))
  assert.equal(htmlIncludes(html, 'No relievers are marked Avoid or Unavailable.'), false)
  assert.ok(!htmlIncludes(html, 'Bullpen workload appears manageable.'))
  assert.ok(htmlIncludes(html, 'Available'))
  assert.ok(htmlIncludes(html, 'On Watch'))
  assert.ok(htmlIncludes(html, 'Open ACE Bullpen Board -&gt;'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board&amp;team=ACE&amp;source=follow-my-team"'))
  assert.ok(!htmlIncludes(html, 'Stress Score'))
})

test('followed team stress renders no-read copy when board data is stale', () => {
  const staleAcesBoard = makeBoard({
    team: teams[0],
    cardsByStatus: {
      Available: [
        { pitcher_id: 1, name: 'Old Fresh Arm', availability_status: 'Available' },
      ],
    },
    freshness: {
      data_through: '2026-04-01',
      latest_workload_date: '2026-04-01',
      last_successful_sync: null,
      sync_status: 'metadata_unavailable',
      is_current: false,
      label: 'Historical baseball data through 2026-04-01.',
      limitations: ['Latest game date is outside the 14-day freshness window.'],
    },
  })
  const html = inRouter(React.createElement(FollowMyTeamCard, {
    teams,
    followedTeam: teams[0],
    board: staleAcesBoard,
  }))

  assert.ok(htmlIncludes(html, 'Overall Availability: No Read'))
  assert.ok(htmlIncludes(html, 'Availability note is limited by data freshness.'))
  assert.ok(!htmlIncludes(html, 'Overall Availability: Manageable'))
})

test('returning card includes change and clear controls', () => {
  const html = inRouter(React.createElement(FollowMyTeamCard, {
    teams,
    followedTeam: teams[0],
    board: acesBoard,
  }))

  assert.ok(htmlIncludes(html, 'Change team'))
  assert.ok(htmlIncludes(html, 'Clear followed team'))
  assert.ok(htmlIncludes(html, 'ACE · Aces'))
  assert.ok(htmlIncludes(html, 'BEA · Bears'))
})

test('followed team preference can be cleared', () => {
  const storage = createMemoryStorage()

  saveFollowedTeamPreference(teams[0], storage, () => '2026-06-08T12:00:00Z')
  assert.equal(readFollowedTeamPreference(storage).team_abbreviation, 'ACE')
  assert.equal(clearFollowedTeamPreference(storage), true)
  assert.equal(readFollowedTeamPreference(storage), null)
})

test('localStorage unavailable does not crash preference handling', () => {
  const storage = createFailingStorage()

  assert.equal(readFollowedTeamPreference(storage), null)
  assert.deepEqual(saveFollowedTeamPreference(teams[0], storage), {
    team_id: 1,
    team_abbreviation: 'ACE',
    team_name: 'Aces',
  })
  assert.equal(clearFollowedTeamPreference(storage), false)
})

test('followed team helpers reconcile stored preferences and board links', () => {
  assert.equal(
    buildFollowedTeamHref({ team_id: 1, team_abbreviation: 'ACE' }),
    '/bullpen?view=board&team=ACE&source=follow-my-team',
  )

  assert.deepEqual(
    resolveFollowedTeam({ team_abbreviation: 'bea' }, teams),
    {
      team_id: 2,
      team_abbreviation: 'BEA',
      team_name: 'Bears',
    },
  )
})
