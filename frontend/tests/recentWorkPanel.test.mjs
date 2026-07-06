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

const { default: RecentWorkPanel } = await server.ssrLoadModule(
  '/src/components/bullpen/RecentWorkPanel.jsx',
)
const { default: AvailabilitySummary } = await server.ssrLoadModule(
  '/src/components/bullpen/AvailabilitySummary.jsx',
)
const { getPitcherRecentWork } = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)

const recentWorkPayload = {
  capability: 'public_recent_work',
  pitcher: {
    id: 42,
    mlb_id: 12345,
    full_name: 'Test Reliever',
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
  roster_status: {
    status: 'Active',
    source: 'mlb_roster_data',
    sentence: 'On the active roster per MLB roster data.',
  },
  last_appearance: {
    game_date: '2026-07-03',
    opponent: 'Boston Red Sox',
    opponent_abbreviation: 'BOS',
    innings_pitched: 5 / 3,
    innings_pitched_outs: 5,
    pitches_thrown: 24,
    strikeouts: 2,
    walks: 1,
    hits_allowed: 2,
    runs_allowed: 1,
    save: true,
    hold: true,
    blown_save: true,
    win: true,
    loss: true,
    save_situation: true,
    sentence: 'Last appearance: July 3 vs BOS - 1.2 IP, 24 pitches, 2 K, 1 BB, 2 H, 1 R.',
    timing_sentence: 'That appearance came 2 days before July 5.',
    fact_sentences: [
      'Recorded a save (July 3).',
      'Recorded a hold (July 3).',
      'Charged with a blown save (July 3).',
      'Credited with the win (July 3).',
      'Charged with the loss (July 3).',
    ],
  },
  recent_appearances: [
    {
      game_date: '2026-07-03',
      opponent: 'Boston Red Sox',
      opponent_abbreviation: 'BOS',
      innings_pitched: 5 / 3,
      innings_pitched_outs: 5,
      pitches_thrown: 24,
      strikeouts: 2,
      walks: 1,
      hits_allowed: 2,
      runs_allowed: 1,
      save: true,
      hold: true,
      blown_save: true,
      win: true,
      loss: true,
      save_situation: true,
    },
  ],
  workload: {
    window_7: {
      through: '2026-07-05',
      appearances: 3,
      pitches_total: 61,
      appearances_with_pitches: 3,
      sentence: '3 appearances in the 7 days through July 5.',
      pitches_sentence: '61 pitches across those 3 appearances.',
    },
    window_14: {
      through: '2026-07-05',
      appearances: 5,
      pitches_total: null,
      appearances_with_pitches: 4,
      sentence: '5 appearances in the 14 days through July 5.',
      pitches_sentence: 'Pitch count unavailable for 1 of 5 appearances; 71 pitches across the other 4.',
    },
  },
}

function renderPanel(props = {}) {
  return renderToStaticMarkup(
    React.createElement(RecentWorkPanel, {
      pitcherId: 42,
      ...props,
    }),
  )
}

function headerKeys(headers = {}) {
  return Object.keys(headers).map(key => key.toLowerCase())
}

test('fetches the public pitcher recent-work route without privileged headers', async (t) => {
  const originalFetch = globalThis.fetch
  const calls = []
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return { ok: true, json: async () => recentWorkPayload }
  }

  const payload = await getPitcherRecentWork(42)

  assert.equal(payload, recentWorkPayload)
  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/bullpen/pitchers/42/recent-work')
  assert.equal(calls[0].url.includes('/api/system/internal/pitcher-evidence'), false)
  assert.equal(headerKeys(calls[0].options.headers).includes('x-admin-token'), false)
})

test('renders endpoint-authored sentences verbatim', () => {
  const html = renderPanel({ payload: recentWorkPayload })

  for (const sentence of [
    recentWorkPayload.roster_status.sentence,
    recentWorkPayload.freshness.label,
    recentWorkPayload.last_appearance.sentence,
    recentWorkPayload.last_appearance.timing_sentence,
    ...recentWorkPayload.last_appearance.fact_sentences,
    recentWorkPayload.workload.window_7.sentence,
    recentWorkPayload.workload.window_7.pitches_sentence,
    recentWorkPayload.workload.window_14.sentence,
    recentWorkPayload.workload.window_14.pitches_sentence,
  ]) {
    assert.ok(htmlIncludes(html, sentence), sentence)
  }
})

test('renders absence sentences verbatim when supplied', () => {
  const payload = {
    ...recentWorkPayload,
    last_appearance: null,
    recent_appearances: [],
    absence_sentence: 'No appearances in the 30 days through July 5.',
  }
  const html = renderPanel({ payload })

  assert.ok(htmlIncludes(html, payload.absence_sentence))
})

test('recent appearance rows stay factual and field-based', () => {
  const html = renderPanel({ payload: recentWorkPayload })

  for (const text of [
    '2026-07-03',
    'vs BOS',
    '1.2 IP',
    '24 P',
    '2 K',
    '1 BB',
    '2 H',
    '1 R',
    'SV',
    'HLD',
    'BS',
    'W',
    'L',
    'SV SIT',
  ]) {
    assert.ok(htmlIncludes(html, text), text)
  }
})

test('renders safe loading and error states', () => {
  const loadingHtml = renderPanel({ loading: true })
  const errorHtml = renderPanel({ error: 'network details must not render' })

  assert.ok(htmlIncludes(loadingHtml, 'Loading recent work…'))
  assert.equal(htmlIncludes(loadingHtml, 'Recent Work'), false)
  assert.ok(htmlIncludes(errorHtml, 'Recent work is unavailable.'))
  assert.equal(htmlIncludes(errorHtml, 'network details must not render'), false)
  assert.equal(htmlIncludes(errorHtml, 'Recent Work'), false)
})

test('source guard keeps the panel out of frontend baseball prose composition', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/RecentWorkPanel.jsx', import.meta.url),
    'utf8',
  )
  const forbiddenTerms = [
    /\brested\b/i,
    /\bfresh\b/i,
    /\bavailable\b/i,
    /\bready\b/i,
    /\bhealthy\b/i,
    /\binjury-free\b/i,
    /\bfatigued\b/i,
    /\bworkload\s+risk\b/i,
    /\bclean\b/i,
    /\bmessy\b/i,
    /\bheavy\b/i,
    /\bstressful\b/i,
    /\befficient\b/i,
    /\bshort\s+rest\b/i,
    /\bback-to-back\b/i,
    /\b3-in-4\b/i,
    /\b4-in-6\b/i,
    /\bband\b/i,
    /\bobservation\b/i,
    /\bleaned\s+on\b/i,
    /\btrusted\b/i,
    /\bcloser\b/i,
    /\bsetup\b/i,
    /\bevidence\b/i,
    /\bcitation\b/i,
    /\bconfidence\b/i,
    /\bwill\b/i,
    /\bshould\b/i,
    /\blikely\b/i,
  ]

  for (const term of forbiddenTerms) {
    assert.equal(term.test(source), false, String(term))
  }
  assert.equal(/last\s+7\s+days/i.test(source), false)
  assert.equal(/last\s+14\s+days/i.test(source), false)
})

test('source guard blocks internal endpoint and private field references from the mount', async () => {
  const panelSource = await readFile(
    new URL('../src/components/bullpen/RecentWorkPanel.jsx', import.meta.url),
    'utf8',
  )
  const detailSource = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )
  const source = `${panelSource}\n${detailSource}`

  for (const forbidden of [
    '/api/system/internal/pitcher-evidence',
    'X-Admin-Token',
    'evidence_objects',
    'reliever_daily_read',
    'read_components',
    'reason_codes',
    'completeness_state',
    'rule_id',
    'evidence_key',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})

test('PitcherDetail mounts the panel additively before the raw logs table', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/PitcherDetail.jsx', import.meta.url),
    'utf8',
  )
  const summaryIndex = source.indexOf('<AvailabilitySummary')
  const explanationIndex = source.indexOf('<ExplanationDisclosure')
  const mountIndex = source.indexOf('<RecentWorkPanel pitcherId={pitcherId} />')
  const logsIndex = source.indexOf('{recent_logs?.length > 0')

  assert.notEqual(summaryIndex, -1)
  assert.notEqual(explanationIndex, -1)
  assert.notEqual(mountIndex, -1)
  assert.notEqual(logsIndex, -1)
  assert.ok(summaryIndex < mountIndex)
  assert.ok(explanationIndex < mountIndex)
  assert.ok(mountIndex < logsIndex)
  assert.ok(source.includes('Most Recent Workload Appearance'))
  assert.ok(source.includes('recent_logs.slice(0, 8).map(log =>'))
})

test('legacy availability/fatigue copy still renders with existing fixtures', () => {
  const html = renderToStaticMarkup(
    React.createElement(AvailabilitySummary, {
      availability: {
        availability_status: 'Unavailable',
        confidence: 'high',
        data_state: 'fresh',
        reasons: ['Roster status: 15-Day IL.'],
        limitations: ['Unavailable due to roster status; not available for bullpen planning.'],
        roster_status: {
          status: 'IL_15',
          label: '15-Day IL',
          confidence: 'high',
          is_authoritative: true,
          is_inactive_context: true,
        },
      },
      workloadSignal: {
        availability_status: 'Monitor',
        confidence: 'medium',
        data_state: 'fresh',
        reasons: ['Workload signal: Monitor.'],
        limitations: ['No injury information available'],
      },
    }),
  )

  assert.ok(htmlIncludes(html, 'Final availability: Unavailable'))
  assert.ok(htmlIncludes(html, 'Roster Status'))
  assert.ok(htmlIncludes(html, '15-Day IL'))
  assert.ok(htmlIncludes(html, 'Workload Signal'))
  assert.ok(htmlIncludes(html, 'Workload signal: On Watch'))
})
