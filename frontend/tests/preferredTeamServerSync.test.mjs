import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
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

const sync = await server.ssrLoadModule('/src/utils/preferredTeamServerSync.js')
const preferenceHook = await server.ssrLoadModule('/src/hooks/usePreferredTeamPreference.js')
const {
  claimLocalPreferredTeamOnSignIn,
  normalizeFollowedTeamsResponse,
  resolvePreferredTeamForAuthState,
  resolveServerPreferredTeam,
  setServerPreferredTeam,
  shouldClaimLocalPreferredTeam,
} = sync
const { serverStateForPreferredTeamPreference } = preferenceHook

const teams = [
  { team_id: 118, team_name: 'Dodgers', team_abbreviation: 'LAD' },
  { team_id: 147, team_name: 'Yankees', team_abbreviation: 'NYY' },
]

test('authenticated preferred team resolves from server primary_team_id', () => {
  const serverResponse = {
    teams: [
      { team_id: 118, is_primary: false },
      { team_id: 147, is_primary: true },
    ],
    primary_team_id: 147,
  }

  assert.deepEqual(resolveServerPreferredTeam(serverResponse, teams), teams[1])
  assert.deepEqual(
    resolvePreferredTeamForAuthState({
      authenticated: true,
      serverResponse,
      localPreference: teams[0],
      teamDirectory: teams,
    }),
    teams[1],
  )
})

test('anonymous and failed auth states fall back to the local preferred team', () => {
  const localPreference = { team_id: 118 }
  const serverResponse = {
    teams: [{ team_id: 147, is_primary: true }],
    primary_team_id: 147,
  }

  assert.deepEqual(
    resolvePreferredTeamForAuthState({
      authenticated: false,
      serverResponse,
      localPreference,
      teamDirectory: teams,
    }),
    teams[0],
  )
  assert.deepEqual(
    resolvePreferredTeamForAuthState({
      authenticated: true,
      serverResponse,
      serverError: new Error('auth failed'),
      localPreference,
      teamDirectory: teams,
    }),
    teams[0],
  )
})

test('authenticated id-only server primary keeps matching local display metadata', () => {
  const localPreference = { team_id: 118, team_name: 'Dodgers', team_abbreviation: 'LAD' }
  const serverResponse = {
    teams: [{ team_id: 118, is_primary: true }],
    primary_team_id: 118,
  }

  assert.deepEqual(
    resolvePreferredTeamForAuthState({
      authenticated: true,
      serverResponse,
      localPreference,
      teamDirectory: [],
    }),
    localPreference,
  )
})

test('followed-team response normalization accepts primary flags and ids', () => {
  assert.deepEqual(
    normalizeFollowedTeamsResponse({
      teams: [
        { team_id: '118', is_primary: false },
        { teamId: 147, isPrimary: true },
      ],
    }),
    {
      teams: [
        { team_id: 118, is_primary: false },
        { team_id: 147, is_primary: true },
      ],
      primary_team_id: 147,
    },
  )
})

test('setting preferred team follows it and marks it primary on the server', async () => {
  const calls = []
  const response = await setServerPreferredTeam(teams[1], {
    followTeam: async (teamId) => {
      calls.push(['POST /api/me/teams', teamId])
      return { teams: [{ team_id: teamId, is_primary: false }], primary_team_id: 118 }
    },
    setPrimaryTeam: async (teamId) => {
      calls.push(['PUT /api/me/primary-team', teamId])
      return { teams: [{ team_id: teamId, is_primary: true }], primary_team_id: teamId }
    },
  })

  assert.deepEqual(calls, [
    ['POST /api/me/teams', 147],
    ['PUT /api/me/primary-team', 147],
  ])
  assert.equal(response.primary_team_id, 147)
})

test('preferred-team event state updates sibling hook server primary without page refresh', () => {
  const previous = {
    loading: false,
    teams: [
      { team_id: 147, is_primary: true },
    ],
    primary_team_id: 147,
    error: null,
  }

  const next = serverStateForPreferredTeamPreference(previous, {
    team: { team_id: 118, team_name: 'Dodgers', team_abbreviation: 'LAD' },
  })

  assert.equal(next.primary_team_id, 118)
  assert.deepEqual(next.teams, [
    { team_id: 118, is_primary: true },
    { team_id: 147, is_primary: false },
  ])
  assert.equal(next.error, null)
})

test('localStorage team is claimed on sign-in when server has no teams', async () => {
  const calls = []
  const response = await claimLocalPreferredTeamOnSignIn({
    serverResponse: { teams: [], primary_team_id: null },
    localPreference: { team_abbreviation: 'LAD' },
    teamDirectory: teams,
    claimKey: 'test-user:118',
    clients: {
      followTeam: async (teamId) => {
        calls.push(['POST /api/me/teams', teamId])
        return { teams: [{ team_id: teamId, is_primary: false }], primary_team_id: null }
      },
      setPrimaryTeam: async (teamId) => {
        calls.push(['PUT /api/me/primary-team', teamId])
        return { teams: [{ team_id: teamId, is_primary: true }], primary_team_id: teamId }
      },
    },
  })

  assert.deepEqual(calls, [
    ['POST /api/me/teams', 118],
    ['PUT /api/me/primary-team', 118],
  ])
  assert.deepEqual(response, {
    teams: [{ team_id: 118, is_primary: true }],
    primary_team_id: 118,
  })
})

test('claim is skipped when server teams already exist or local team lacks an id', () => {
  assert.equal(
    shouldClaimLocalPreferredTeam(
      { teams: [{ team_id: 147, is_primary: true }], primary_team_id: 147 },
      { team_id: 118 },
      teams,
    ),
    null,
  )
  assert.equal(
    shouldClaimLocalPreferredTeam(
      { teams: [], primary_team_id: null },
      { team_abbreviation: 'NOPE' },
      teams,
    ),
    null,
  )
})

test('existing UI consumers stay on the preferred-team hook contract', async () => {
  const files = [
    'src/components/Sidebar.jsx',
    'src/components/home/LegacyMorningBullpenReport.jsx',
    'src/components/dashboard/FollowMyTeam.jsx',
    'src/components/bullpen/board/TonightsBullpenBoard.jsx',
  ]

  for (const file of files) {
    const source = await readFile(new URL(`../${file}`, import.meta.url), 'utf8')
    assert.match(source, /usePreferredTeamPreference|useFollowedTeamPreference/)
    assert.doesNotMatch(source, /getFollowedTeams|setPrimaryTeam|followTeam|\/api\/me\/teams/)
  }
})
