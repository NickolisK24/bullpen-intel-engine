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
  DigestPreferencesCardView,
  digestPreferencesForCadence,
  digestPreferencesForEnabled,
  normalizeDigestPreferences,
  saveDigestPreferenceSelection,
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
  assert.ok(htmlIncludes(html, 'Kansas City Royals'))
  assert.ok(htmlIncludes(html, 'BaseballOS only sends a digest when there is something meaningful to report.'))
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

test('Digest Preferences integration does not call the digest test-send endpoint', () => {
  const apiSource = readFileSync(new URL('../src/utils/api.js', import.meta.url), 'utf8')
  const cardSource = readFileSync(
    new URL('../src/components/trust/DigestPreferencesCard.jsx', import.meta.url),
    'utf8',
  )
  const dataTrustSource = readFileSync(new URL('../src/components/trust/DataTrust.jsx', import.meta.url), 'utf8')

  assert.ok(dataTrustSource.includes('DigestPreferencesCard'))
  assert.equal(apiSource.includes('digest-test-send'), false)
  assert.equal(cardSource.includes('digest-test-send'), false)
})
