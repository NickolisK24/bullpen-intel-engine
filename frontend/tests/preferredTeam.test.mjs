import assert from 'node:assert/strict'
import test from 'node:test'
import {
  LEGACY_FOLLOWED_TEAM_STORAGE_KEY,
  LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY,
  PREFERRED_TEAM_STORAGE_KEY,
  PREFERRED_TEAM_CHANGED_EVENT,
  buildPreferredTeamHref,
  clearPreferredTeamPreference,
  dismissPreferredTeamPrompt,
  isPreferredTeamStorageEvent,
  preferredTeamLabel,
  preferredTeamLogoUrl,
  preferredTeamSelectionValue,
  preferredTeamShortLabel,
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

test('preferred team labels do not expose raw ids while metadata is loading', () => {
  const idOnlyTeam = { team_id: 147 }

  assert.equal(preferredTeamLabel(idOnlyTeam), 'your team')
  assert.equal(preferredTeamShortLabel(idOnlyTeam), 'Team')
  assert.equal(preferredTeamLabel(resolvePreferredTeam({ team_id: 1 }, teams)), 'Aces')
  assert.equal(preferredTeamLabel(teams[0]), 'Aces')
  assert.equal(preferredTeamShortLabel(teams[0]), 'ACE')
  assert.equal(preferredTeamLabel({ team_name: '147', team_abbreviation: '147' }), 'your team')
  assert.equal(preferredTeamShortLabel({ team_name: '147', team_abbreviation: '147' }), 'Team')
  assert.equal(buildPreferredTeamHref(idOnlyTeam, 'test-source'), '/bullpen?view=board&team=147&source=test-source')
})

test('preferred team storage refresh is limited to preference keys', () => {
  const authEvent = Object.create({ key: 'baseballos.authToken' })

  assert.equal(isPreferredTeamStorageEvent({ key: PREFERRED_TEAM_STORAGE_KEY }), true)
  assert.equal(isPreferredTeamStorageEvent({ key: LEGACY_FOLLOWED_TEAM_STORAGE_KEY }), true)
  assert.equal(isPreferredTeamStorageEvent({ key: LEGACY_WHAT_CHANGED_TEAM_STORAGE_KEY }), true)
  assert.equal(isPreferredTeamStorageEvent({ key: null }), true)
  assert.equal(isPreferredTeamStorageEvent({ key: 'baseballos.authToken' }), false)
  assert.equal(isPreferredTeamStorageEvent(authEvent), false)
})

test('preferred team change event is preserved for existing consumers', () => {
  const originalWindow = globalThis.window
  const originalCustomEvent = globalThis.CustomEvent
  const events = []
  globalThis.CustomEvent = class CustomEvent {
    constructor(type, init = {}) {
      this.type = type
      this.detail = init.detail
    }
  }
  globalThis.window = {
    dispatchEvent(event) {
      events.push(event)
      return true
    },
  }

  try {
    const storage = createStorage()
    savePreferredTeamPreference(teams[0], storage)
    clearPreferredTeamPreference(storage)

    assert.equal(events[0].type, PREFERRED_TEAM_CHANGED_EVENT)
    assert.equal(events[0].detail.team.team_id, 1)
    assert.equal(events[1].type, PREFERRED_TEAM_CHANGED_EVENT)
    assert.equal(events[1].detail.team, null)
  } finally {
    globalThis.window = originalWindow
    globalThis.CustomEvent = originalCustomEvent
  }
})
