import assert from 'node:assert/strict'
import { existsSync } from 'node:fs'
import test from 'node:test'
import {
  buildTeamSharePath,
  buildTeamShareUrl,
  normalizeTeamShareAbbreviation,
  shareTeamUrl,
} from '../src/utils/teamShare.js'

test('team share helper builds the canonical pre-rendered team URL', () => {
  assert.equal(normalizeTeamShareAbbreviation({ team_abbreviation: ' tor ' }), 'TOR')
  assert.equal(buildTeamSharePath({ teamAbbreviation: 'sd' }), '/team/SD')
  assert.equal(
    buildTeamShareUrl({ team_abbreviation: 'TOR' }),
    'https://baseballos.app/team/TOR',
  )
  assert.equal(
    buildTeamShareUrl({ abbr: 'SD' }),
    'https://baseballos.app/team/SD',
  )
  assert.equal(existsSync(new URL('../public/team/TOR/index.html', import.meta.url)), true)
  assert.equal(existsSync(new URL('../public/team/SD/index.html', import.meta.url)), true)
})

test('native share receives only the clean team URL', async () => {
  const calls = []
  const result = await shareTeamUrl(
    { team_abbreviation: 'SD' },
    {
      navigator: {
        share: async payload => calls.push(payload),
        clipboard: { writeText: async value => calls.push({ clipboard: value }) },
      },
    },
  )

  assert.equal(result.status, 'shared')
  assert.deepEqual(calls, [{ url: 'https://baseballos.app/team/SD' }])
  assert.notEqual(calls[0].url, 'https://baseballos.app/bullpen?view=board&team=SD')
})

test('clipboard fallback copies the clean team URL when native share is unavailable', async () => {
  const copied = []
  const result = await shareTeamUrl(
    { team_abbreviation: 'TOR' },
    {
      navigator: {
        clipboard: { writeText: async value => copied.push(value) },
      },
    },
  )

  assert.equal(result.status, 'copied')
  assert.deepEqual(copied, ['https://baseballos.app/team/TOR'])
})

test('cancelled native share and failed clipboard fallback do not throw', async () => {
  const abort = new Error('Share cancelled')
  abort.name = 'AbortError'
  const cancelled = await shareTeamUrl('TOR', {
    navigator: {
      share: async () => {
        throw abort
      },
    },
  })

  assert.equal(cancelled.status, 'cancelled')
  assert.equal(cancelled.url, 'https://baseballos.app/team/TOR')

  const failed = await shareTeamUrl('TOR', {
    navigator: {
      clipboard: {
        writeText: async () => {
          throw new Error('clipboard unavailable')
        },
      },
    },
  })

  assert.equal(failed.status, 'unavailable')
  assert.equal(failed.url, 'https://baseballos.app/team/TOR')
})
