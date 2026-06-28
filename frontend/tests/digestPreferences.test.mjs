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

after(async () => {
  await server.close()
})

const {
  DIGEST_SAVE_ERROR,
  DIGEST_SAVE_IDLE,
  DIGEST_SAVE_SAVED,
  FOLLOWED_TEAM_SAVE_SAVED,
  FollowedTeamPickerView,
  DigestPreferencesCardView,
  buildFollowedTeamOptions,
  digestPreferencesForCadence,
  digestPreferencesForEnabled,
  filterFollowedTeamOptions,
  normalizeDigestPreferences,
  saveDigestPreferenceSelection,
  saveFollowedTeamSelection,
} = await server.ssrLoadModule('/src/components/trust/DigestPreferencesCard.jsx')
const {
  getDigestPreferences,
  updateDigestPreferences,
} = await server.ssrLoadModule('/src/utils/api.js')

const render = (element) => renderToStaticMarkup(
  React.createElement(MemoryRouter, null, element),
)
const htmlIncludes = (html, text) => html.includes(text)

test('signed-out Digest Preferences card prompts sign-in without exposing controls', () => {
  const html = render(React.createElement(DigestPreferencesCardView, {
    authLoading: false,
    authenticated: false,
  }))

  assert.ok(htmlIncludes(html, 'Digest Preferences'))
  assert.ok(htmlIncludes(html, 'Sign in to manage digest emails for your followed team.'))
  assert.ok(htmlIncludes(html, 'href="/signin"'))
  assert.equal(htmlIncludes(html, 'Switch Team'), false)
  assert.equal(htmlIncludes(html, 'name="digest_enabled"'), false)
  assert.equal(htmlIncludes(html, 'Save preferences'), false)
})

test('signed-in Digest Preferences card renders loaded preferences and followed team', () => {
  const html = render(React.createElement(DigestPreferencesCardView, {
    authenticated: true,
    preferences: {
      digest_enabled: false,
      digest_cadence: 'off',
    },
    followedTeam: {
      team_id: 118,
      team_name: 'Kansas City Royals',
      team_abbreviation: 'KC',
    },
    saveStatus: DIGEST_SAVE_IDLE,
  }))

  assert.ok(htmlIncludes(html, 'Digest emails'))
  assert.ok(htmlIncludes(html, 'Off'))
  assert.ok(htmlIncludes(html, 'Cadence'))
  assert.ok(htmlIncludes(html, 'Followed Team'))
  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.ok(htmlIncludes(html, 'Your digest follows this team.'))
  assert.ok(htmlIncludes(html, 'Switch Team'))
  assert.ok(htmlIncludes(html, 'BaseballOS only sends a digest when there is something meaningful to report.'))
})

test('followed team picker renders team names, marks current team, and filters directory options', () => {
  const teams = [
    { team_id: 118, team_name: 'Kansas City Royals', team_abbreviation: 'KC' },
    { team_id: 110, team_name: 'Baltimore Orioles', team_abbreviation: 'BAL' },
    { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
  ]
  const options = buildFollowedTeamOptions(teams)
  const filtered = filterFollowedTeamOptions(options, 'yank')
  const html = render(React.createElement(FollowedTeamPickerView, {
    options,
    currentValue: 'team:118',
    selectedValue: 'team:110',
  }))

  assert.deepEqual(options.map(option => option.label), [
    'Baltimore Orioles',
    'Kansas City Royals',
    'New York Yankees',
  ])
  assert.deepEqual(filtered.map(option => option.label), ['New York Yankees'])
  assert.ok(htmlIncludes(html, 'Baltimore Orioles'))
  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.ok(htmlIncludes(html, 'New York Yankees'))
  assert.ok(htmlIncludes(html, 'Current'))
  assert.equal(htmlIncludes(html, '>118<'), false)
  assert.equal(htmlIncludes(html, 'team:118'), false)
})

test('signed-in Digest Preferences card opens an inline followed-team picker', () => {
  const html = render(React.createElement(DigestPreferencesCardView, {
    authenticated: true,
    preferences: {
      digest_enabled: true,
      digest_cadence: 'daily',
    },
    followedTeam: {
      team_id: 118,
      team_name: 'Kansas City Royals',
      team_abbreviation: 'KC',
    },
    teams: [
      { team_id: 118, team_name: 'Kansas City Royals', team_abbreviation: 'KC' },
      { team_id: 110, team_name: 'Baltimore Orioles', team_abbreviation: 'BAL' },
    ],
    teamPickerOpen: true,
    selectedTeamValue: 'team:118',
  }))

  assert.ok(htmlIncludes(html, 'Search teams'))
  assert.ok(htmlIncludes(html, 'Save team'))
  assert.ok(htmlIncludes(html, 'Cancel'))
  assert.ok(htmlIncludes(html, 'Baltimore Orioles'))
  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.equal(htmlIncludes(html, '>110<'), false)
})

test('followed team picker save calls setPreferredTeam with selected team and returns saved display state', async () => {
  const teams = [
    { team_id: 118, team_name: 'Kansas City Royals', team_abbreviation: 'KC' },
    { team_id: 110, team_name: 'Baltimore Orioles', team_abbreviation: 'BAL' },
  ]
  const options = buildFollowedTeamOptions(teams)
  const statuses = []
  let selectedTeam = null
  let displayTeam = null

  const saved = await saveFollowedTeamSelection({
    selectedValue: 'team:110',
    options,
    setPreferredTeam: (team) => {
      selectedTeam = team
      return team
    },
    setFollowedTeam: (team) => {
      displayTeam = team
    },
    setStatus: status => statuses.push(status),
  })

  assert.equal(selectedTeam.team_name, 'Baltimore Orioles')
  assert.equal(saved.team_name, 'Baltimore Orioles')
  assert.equal(displayTeam.team_name, 'Baltimore Orioles')
  assert.deepEqual(statuses, ['loading', FOLLOWED_TEAM_SAVE_SAVED])
})

test('followed team picker cancel has a visible escape path and does not save by itself', async () => {
  let called = false
  const html = render(React.createElement(FollowedTeamPickerView, {
    options: buildFollowedTeamOptions([
      { team_id: 118, team_name: 'Kansas City Royals', team_abbreviation: 'KC' },
    ]),
  }))
  const saved = await saveFollowedTeamSelection({
    selectedValue: '',
    options: [],
    setPreferredTeam: () => {
      called = true
    },
  })

  assert.ok(htmlIncludes(html, 'Cancel'))
  assert.equal(saved, null)
  assert.equal(called, false)
})

test('digest preference helpers enable, disable, and save cadence changes', async () => {
  assert.deepEqual(normalizeDigestPreferences({
    notification_prefs: {
      digest_enabled: false,
      digest_cadence: 'daily',
    },
  }), {
    digest_enabled: false,
    digest_cadence: 'off',
  })
  assert.deepEqual(digestPreferencesForEnabled({
    digest_enabled: false,
    digest_cadence: 'off',
  }, true), {
    digest_enabled: true,
    digest_cadence: 'daily',
  })
  assert.deepEqual(digestPreferencesForEnabled({
    digest_enabled: true,
    digest_cadence: 'weekly',
  }, false), {
    digest_enabled: false,
    digest_cadence: 'off',
  })
  assert.deepEqual(digestPreferencesForCadence({
    digest_enabled: true,
    digest_cadence: 'daily',
  }, 'weekly'), {
    digest_enabled: true,
    digest_cadence: 'weekly',
  })
  assert.deepEqual(digestPreferencesForCadence({
    digest_enabled: true,
    digest_cadence: 'daily',
  }, 'off'), {
    digest_enabled: false,
    digest_cadence: 'off',
  })

  let payload = null
  const statuses = []
  const saved = await saveDigestPreferenceSelection({
    draftPreferences: { digest_enabled: true, digest_cadence: 'weekly' },
    savePreferences: async (preferences) => {
      payload = preferences
      return { notification_prefs: preferences }
    },
    setStatus: status => statuses.push(status),
  })

  assert.deepEqual(payload, { digest_enabled: true, digest_cadence: 'weekly' })
  assert.deepEqual(saved, { digest_enabled: true, digest_cadence: 'weekly' })
  assert.deepEqual(statuses, ['loading', DIGEST_SAVE_SAVED])
})

test('digest preference save exposes a clear API error state', async () => {
  const statuses = []
  let capturedError = null
  const saved = await saveDigestPreferenceSelection({
    draftPreferences: { digest_enabled: true, digest_cadence: 'daily' },
    savePreferences: async () => {
      throw new Error('failed')
    },
    setStatus: status => statuses.push(status),
    setError: error => {
      capturedError = error
    },
  })
  const html = render(React.createElement(DigestPreferencesCardView, {
    authenticated: true,
    preferences: { digest_enabled: true, digest_cadence: 'daily' },
    saveStatus: DIGEST_SAVE_ERROR,
    saveError: capturedError,
  }))

  assert.equal(saved, null)
  assert.equal(capturedError.message, 'failed')
  assert.deepEqual(statuses, ['loading', DIGEST_SAVE_ERROR])
  assert.ok(htmlIncludes(html, 'We could not save digest preferences. Please try again.'))
})

test('digest preference API helpers use authenticated preference endpoints only', async () => {
  const originalFetch = globalThis.fetch
  const calls = []
  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return {
      ok: true,
      status: 200,
      statusText: 'OK',
      json: async () => ({ notification_prefs: { digest_enabled: true, digest_cadence: 'daily' } }),
    }
  }

  try {
    assert.deepEqual(normalizeDigestPreferences(await getDigestPreferences()), {
      digest_enabled: true,
      digest_cadence: 'daily',
    })
    await updateDigestPreferences({ digest_enabled: false, digest_cadence: 'off' })
  } finally {
    globalThis.fetch = originalFetch
  }

  assert.deepEqual(calls.map(call => call.url), [
    '/api/digest/preferences',
    '/api/digest/preferences',
  ])
  assert.equal(calls[1].options.method, 'PUT')
  assert.deepEqual(JSON.parse(calls[1].options.body), {
    digest_enabled: false,
    digest_cadence: 'off',
  })
})

test('Digest Preferences module stays isolated from Data & Trust and the test-send endpoint', () => {
  const apiSource = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  const cardSource = readFileSync(
    new URL('../src/components/trust/DigestPreferencesCard.jsx', import.meta.url),
    'utf8',
  )
  const dataTrustSource = readFileSync(new URL('../src/components/trust/DataTrust.jsx', import.meta.url), 'utf8')

  assert.equal(dataTrustSource.includes('DigestPreferencesCard'), false)
  assert.equal(apiSource.includes('digest-test-send'), false)
  assert.equal(cardSource.includes('digest-test-send'), false)
})
