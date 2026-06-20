import assert from 'node:assert/strict'
import test from 'node:test'
import {
  LEGACY_FOLLOWED_TEAM_STORAGE_KEY,
  LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY,
  PREFERRED_TEAM_STORAGE_KEY,
  buildPreferredTeamHref,
  clearPreferredTeamPreference,
  dismissPreferredTeamPrompt,
  preferredTeamLogoUrl,
  preferredTeamSelectionValue,
  readPreferredTeamPreference,
  readPreferredTeamState,
  resolvePreferredTeam,
  savePreferredTeamPreference,
  savePreferredTeamSelectionValue,
} from '../src/utils/preferredTeam.js'

function createStorage() {
  const values = new Map()
  return {
    getItem: key => values.get(key) || null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
    has: key => values.has(key),
  }
}

const teams = [
  { team_id: 1, team_name: 'Aces', team_abbreviation: 'ACE' },
  { team_id: 2, team_name: 'Bears', team_abbreviation: 'BEA' },
]

test('preferred team writes one canonical storage key', () => {
  const storage = createStorage()

  const saved = savePreferredTeamPreference(teams[0], storage, () => '2026-06-20T12:00:00Z')

  assert.deepEqual(saved, {
    team_id: 1,
    team_abbreviation: 'ACE',
    team_name: 'Aces',
  })
  assert.equal(storage.has(PREFERRED_TEAM_STORAGE_KEY), true)
  assert.equal(storage.has(LEGACY_FOLLOWED_TEAM_STORAGE_KEY), false)
  assert.equal(storage.has(LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY), false)
  assert.equal(readPreferredTeamPreference(storage).team_abbreviation, 'ACE')
  assert.equal(preferredTeamSelectionValue(readPreferredTeamPreference(storage)), 'team:1')
})

test('preferred team migrates legacy Follow My Team storage', () => {
  const storage = createStorage()
  storage.setItem(LEGACY_FOLLOWED_TEAM_STORAGE_KEY, JSON.stringify({
    team_id: 2,
    team_abbreviation: 'BEA',
    team_name: 'Bears',
    saved_at: '2026-06-19T12:00:00Z',
  }))

  const team = readPreferredTeamPreference(storage)

  assert.equal(team.team_abbreviation, 'BEA')
  assert.equal(storage.has(PREFERRED_TEAM_STORAGE_KEY), true)
  assert.equal(storage.has(LEGACY_FOLLOWED_TEAM_STORAGE_KEY), false)
})

test('preferred team migrates legacy What Changed selection values', () => {
  const storage = createStorage()
  storage.setItem(LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY, 'team:1')

  const team = resolvePreferredTeam(readPreferredTeamPreference(storage), teams)

  assert.equal(team.team_name, 'Aces')
  assert.equal(storage.has(PREFERRED_TEAM_STORAGE_KEY), true)
  assert.equal(storage.has(LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY), false)
})

test('prompt dismissal uses the same preferred-team state', () => {
  const storage = createStorage()

  dismissPreferredTeamPrompt(storage, () => '2026-06-20T13:00:00Z')
  const state = readPreferredTeamState(storage)

  assert.equal(state.team, null)
  assert.equal(state.promptDismissed, true)
  assert.equal(storage.has(PREFERRED_TEAM_STORAGE_KEY), true)

  savePreferredTeamSelectionValue('abbr:BEA', storage, () => '2026-06-20T13:05:00Z')
  assert.equal(readPreferredTeamState(storage).promptDismissed, false)
  assert.equal(resolvePreferredTeam(readPreferredTeamPreference(storage), teams).team_id, 2)
})

test('preferred team helpers build the team board path and clear state', () => {
  const storage = createStorage()

  savePreferredTeamPreference(teams[0], storage)
  assert.equal(
    buildPreferredTeamHref(teams[0], 'test-source'),
    '/bullpen?view=board&team=ACE&source=test-source',
  )
  assert.equal(preferredTeamLogoUrl(teams[0]), 'https://www.mlbstatic.com/team-logos/1.svg')
  assert.equal(clearPreferredTeamPreference(storage), true)
  assert.equal(readPreferredTeamPreference(storage), null)
})
