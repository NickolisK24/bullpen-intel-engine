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

after(async () => {
  await server.close()
})

const { default: TeamReliefWorkPanel } = await server.ssrLoadModule(
  '/src/components/bullpen/TeamReliefWorkPanel.jsx',
)
const { getTeamReliefWork } = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

const teamReliefWorkPayload = {
  capability: 'public_team_relief_work',
  team: {
    team_id: 110,
    team_name: 'Test Club',
    team_abbreviation: 'TST',
  },
  data_through: '2026-07-05',
  freshness: {
    data_through: '2026-07-05',
    freshness_state: 'current',
    is_current: true,
    label: 'Public bullpen data is current through July 5, 2026.',
  },
  scope_sentence: 'Covers pitchers currently on the TST roster per MLB roster data.',
  relief_by_date: [
    {
      game_date: '2026-07-03',
      relief_appearances: 2,
      outs_total: 11,
      pitches_total: 61,
      appearances_with_pitches: 2,
      sentence: 'July 3 - 2 relief appearances, 3.2 IP, 61 pitches.',
      appearances: [
        {
          pitcher_id: 1,
          pitcher_mlb_id: 90001,
          pitcher_full_name: 'Alpha Reliever',
          roster_status_sentence: 'On the active roster per MLB roster data.',
          game_date: '2026-07-03',
          sentence: 'Alpha Reliever - 1.2 IP, 24 pitches, 2 K, 1 BB, 2 H, 1 R.',
        },
      ],
    },
  ],
  windows: {
    window_7: {
      through: '2026-07-05',
      relief_appearances: 3,
      pitchers_in_relief: 2,
      pitches_total: 81,
      appearances_with_pitches: 3,
      start_relief_unknown: 1,
      sentence: '3 relief appearances in the 7 days through July 5.',
      pitchers_sentence: '2 pitchers appeared in relief in the 7 days through July 5.',
      pitches_sentence: '81 pitches across those 3 relief appearances.',
      start_relief_unknown_sentence: (
        'Start/relief status unavailable for 1 of 4 appearances in the '
        + '7 days through July 5; relief totals cover the other 3.'
      ),
    },
    window_14: {
      through: '2026-07-05',
      relief_appearances: 4,
      pitchers_in_relief: 2,
      pitches_total: null,
      appearances_with_pitches: 3,
      start_relief_unknown: 2,
      sentence: '4 relief appearances in the 14 days through July 5.',
      pitchers_sentence: '2 pitchers appeared in relief in the 14 days through July 5.',
      pitches_sentence: (
        'Pitch count unavailable for 1 of 4 relief appearances; '
        + '81 pitches across the other 3.'
      ),
    },
  },
  absence_sentence: 'No relief appearances in the 30 days through July 5.',
}

function renderPanel(props = {}) {
  return renderToStaticMarkup(
    React.createElement(TeamReliefWorkPanel, {
      teamId: 110,
      ...props,
    }),
  )
}

function headerKeys(headers = {}) {
  return Object.keys(headers).map(key => key.toLowerCase())
}

test('fetches the public team relief-work route without privileged headers', async (t) => {
  const originalFetch = globalThis.fetch
  const calls = []
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return { ok: true, json: async () => teamReliefWorkPayload }
  }

  const payload = await getTeamReliefWork(110)

  assert.equal(payload, teamReliefWorkPayload)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/bullpen/teams/110/relief-work')
  assert.equal(calls[0].url.includes('/api/system/internal/team-evidence'), false)
  assert.equal(calls[0].url.includes('/api/system/internal/pitcher-evidence'), false)
  assert.equal(headerKeys(calls[0].options.headers).includes('x-admin-token'), false)
})

test('renders server-authored team relief-work sentences verbatim', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })

  for (const sentence of [
    teamReliefWorkPayload.scope_sentence,
    teamReliefWorkPayload.freshness.label,
    teamReliefWorkPayload.relief_by_date[0].sentence,
    teamReliefWorkPayload.relief_by_date[0].appearances[0].sentence,
    teamReliefWorkPayload.relief_by_date[0].appearances[0].roster_status_sentence,
    teamReliefWorkPayload.windows.window_7.sentence,
    teamReliefWorkPayload.windows.window_7.pitchers_sentence,
    teamReliefWorkPayload.windows.window_7.pitches_sentence,
    teamReliefWorkPayload.windows.window_7.start_relief_unknown_sentence,
    teamReliefWorkPayload.windows.window_14.sentence,
    teamReliefWorkPayload.windows.window_14.pitchers_sentence,
    teamReliefWorkPayload.windows.window_14.pitches_sentence,
    teamReliefWorkPayload.absence_sentence,
  ]) {
    assert.ok(htmlIncludes(html, sentence), sentence)
  }
})

test('degraded no-anchor payload renders only safe sections', () => {
  const payload = {
    capability: 'public_team_relief_work',
    team: teamReliefWorkPayload.team,
    data_through: null,
    freshness: {
      data_through: null,
      freshness_state: 'metadata_unavailable',
      label: 'Public relief-work metadata unavailable.',
    },
    scope_sentence: teamReliefWorkPayload.scope_sentence,
    relief_by_date: [],
  }
  const html = renderPanel({ payload })

  assert.ok(htmlIncludes(html, 'Recent Bullpen Work'))
  assert.ok(htmlIncludes(html, payload.scope_sentence))
  assert.ok(htmlIncludes(html, payload.freshness.label))
  assert.equal(htmlIncludes(html, 'Relief Work Windows'), false)
  assert.equal(htmlIncludes(html, 'Relief Work by Date'), false)
  assert.equal(htmlIncludes(html, 'through'), false)
  assert.equal(htmlIncludes(html, '7 days'), false)
  assert.equal(htmlIncludes(html, '14 days'), false)
})

test('empty relief work renders absence copy verbatim', () => {
  const payload = {
    ...teamReliefWorkPayload,
    relief_by_date: [],
    windows: {
      window_7: teamReliefWorkPayload.windows.window_7,
      window_14: teamReliefWorkPayload.windows.window_14,
    },
    absence_sentence: 'No relief appearances in the 30 days through July 5.',
  }
  const html = renderPanel({ payload })

  assert.ok(htmlIncludes(html, payload.absence_sentence))
})

test('renders exact loading and error states', () => {
  const loadingHtml = renderPanel({ loading: true })
  const errorHtml = renderPanel({ error: 'network details must not render' })

  assert.ok(htmlIncludes(loadingHtml, 'Loading recent bullpen work…'))
  assert.equal(htmlIncludes(loadingHtml, 'Recent Bullpen Work'), false)
  assert.ok(htmlIncludes(errorHtml, 'Recent bullpen work is unavailable.'))
  assert.equal(htmlIncludes(errorHtml, 'network details must not render'), false)
  assert.equal(htmlIncludes(errorHtml, 'Recent Bullpen Work'), false)
})

test('source guard blocks private routes and fields from the new panel and mount', async () => {
  const panelSource = await readFile(
    new URL('../src/components/bullpen/TeamReliefWorkPanel.jsx', import.meta.url),
    'utf8',
  )
  const bullpenSource = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )
  const source = `${panelSource}\n${bullpenSource}`

  for (const forbidden of [
    '/api/system/internal/team-evidence',
    '/api/system/internal/pitcher-evidence',
    'X-Admin-Token',
    'evidence_objects',
    'composed_read',
    'read_components',
    'reason_codes',
    'completeness_state',
    'rule_id',
    'evidence_key',
    'source_readiness_notes',
    'reconciliation_divergences',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('new panel source does not author forbidden public vocabulary', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/TeamReliefWorkPanel.jsx', import.meta.url),
    'utf8',
  )
  const forbiddenTerms = [
    /\bevidence\b/i,
    /\bcitation\b/i,
    /\bcomposed\b/i,
    /\bread\b/i,
    /\bcompleteness\b/i,
    /\breason code\b/i,
    /\brecompute\b/i,
    /\breconciliation\b/i,
    /\baudit\b/i,
    /\binternal\b/i,
    /\bclean\b/i,
    /\btraffic\b/i,
    /\bentry band\b/i,
    /\binherited\b/i,
    /\bleverage\b/i,
    /\bpressure\b/i,
    /\btrust\b/i,
    /\brole\b/i,
    /\bsetup\b/i,
    /\bcloser\b/i,
    /\bavailability\b/i,
    /\bavailable\b/i,
    /\breadiness\b/i,
    /\bfatigue\b/i,
    /\bconfidence\b/i,
    /\bscore\b/i,
    /\bgrade\b/i,
    /\brank\b/i,
    /\btier\b/i,
    /\binjury\b/i,
    /\bhealth\b/i,
    /\bconcentration\b/i,
    /\bdistribution\b/i,
    /\bleaned\b/i,
    /\bfresh\b/i,
    /\brested\b/i,
    /\btaxed\b/i,
    /\bgassed\b/i,
    /\bburned\b/i,
    /\boverexposed\b/i,
    /\blikely\b/i,
    /\bshould\b/i,
    /\bwill\b/i,
    /\bexpect\b/i,
    /\bpredict\b/i,
    /\bodds\b/i,
    /\bbet\b/i,
    /\block\b/i,
    /\bof the bullpen\b/i,
    /\barms\b/i,
  ]

  for (const term of forbiddenTerms) {
    assert.equal(term.test(source), false, String(term))
  }
  assert.equal(/last\s+7\s+days/i.test(source), false)
  assert.equal(/last\s+14\s+days/i.test(source), false)
})

test('Bullpen mounts the panel additively before the existing table', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )
  const teamFilterIndex = source.indexOf('{/* Team filter pills */}')
  const tableIndex = source.indexOf('{/* Main table */}')
  const mountIndex = source.indexOf('<TeamReliefWorkPanel teamId={selectedTeam} />')
  const detailIndex = source.indexOf('{/* Detail panel')

  assert.notEqual(teamFilterIndex, -1)
  assert.notEqual(tableIndex, -1)
  assert.notEqual(mountIndex, -1)
  assert.notEqual(detailIndex, -1)
  assert.ok(teamFilterIndex < mountIndex)
  assert.ok(mountIndex < tableIndex)
  assert.ok(mountIndex < detailIndex)
  for (const legacyText of [
    'All Teams',
    'Recent Load',
    'Availability',
    'P/7d',
    'Rest',
    'App/7d',
    'Risk',
    'Show pitchers outside the freshness window',
  ]) {
    assert.ok(source.includes(legacyText), legacyText)
  }
})
