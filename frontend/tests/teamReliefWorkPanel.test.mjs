import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { populatedBoard } from './fixtures/bullpenBoardFixtures.mjs'

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
const { default: TonightsBullpenBoard } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TonightsBullpenBoard.jsx',
)
const { getTeamReliefWork } = await server.ssrLoadModule('/src/utils/api.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const detailsTagFor = (html, ariaLabel) => (
  html.match(new RegExp(`<details[^>]*aria-label="${escapeRegExp(ariaLabel)}"[^>]*>`))?.[0] || ''
)

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
      game_date: '2026-07-05',
      relief_appearances: 1,
      outs_total: 3,
      pitches_total: 20,
      appearances_with_pitches: 1,
      sentence: 'July 5 - 1 relief appearance, 1.0 IP, 20 pitches.',
      appearances: [
        {
          pitcher_id: 2,
          pitcher_mlb_id: 90002,
          pitcher_full_name: 'Beta Reliever',
          roster_status_sentence: 'On the active roster per MLB roster data.',
          game_date: '2026-07-05',
          innings_pitched: '1',
          innings_pitched_outs: 3,
          pitches_thrown: 20,
          strikeouts: 1,
          walks: 0,
          hits_allowed: 1,
          runs_allowed: 0,
          sentence: 'Beta Reliever - 1.0 IP, 20 pitches, 1 K, 0 BB, 1 H, 0 R.',
        },
        {
          pitcher_id: 3,
          pitcher_mlb_id: 90003,
          pitcher_full_name: 'Gamma Reliever',
          roster_status_sentence: 'On the active roster per MLB roster data.',
          game_date: '2026-07-05',
          innings_pitched: '1.3333333333333333',
          innings_pitched_outs: 4,
          pitches_thrown: 18,
          strikeouts: 1,
          walks: 1,
          hits_allowed: 0,
          runs_allowed: 1,
          sentence: 'Gamma Reliever - 1.1 IP, 18 pitches, 1 K, 1 BB, 0 H, 1 R.',
        },
        {
          pitcher_id: 4,
          pitcher_mlb_id: 90004,
          pitcher_full_name: 'Delta Reliever',
          roster_status_sentence: 'On the active roster per MLB roster data.',
          game_date: '2026-07-05',
          innings_pitched: '0.6666666666666666',
          innings_pitched_outs: 2,
          pitches_thrown: 14,
          strikeouts: 0,
          walks: 1,
          hits_allowed: 1,
          runs_allowed: 0,
          sentence: 'Delta Reliever - 0.2 IP, 14 pitches, 0 K, 1 BB, 1 H, 0 R.',
        },
      ],
      games: [
        {
          mlb_game_pk: 9601,
          opponent: 'New York Yankees',
          opponent_abbreviation: 'NYY',
          game_shape: 'short_start',
          context_label: 'Extended bullpen coverage',
          starter: {
            pitcher_id: 9,
            pitcher_mlb_id: 90009,
            pitcher_full_name: 'Delta Starter',
            outs: 6,
            innings: '2.0',
            pitches: 35,
          },
          relief: {
            pitcher_count: 6,
            outs: 21,
            innings: '7.0',
            pitches: 107,
          },
          total: {
            pitcher_count: 7,
            outs: 27,
            innings: '9.0',
            pitches: 142,
          },
          starter_assignment: {
            narrative_type: 'first_start_in_days_after_relief_run',
            sentence: (
              'Delta Starter made his first start in 38 days after '
              + '15 consecutive relief appearances.'
            ),
            previous_start_date: '2026-05-28',
            days_since_previous_start: 38,
            consecutive_relief_appearances: 15,
          },
          context_sentences: [
            (
              'Delta Starter made his first start in 38 days after '
              + '15 consecutive relief appearances.'
            ),
            'He recorded 6 outs (2.0 IP) on 35 pitches.',
            'Six relievers covered the remaining 21 outs (7.0 IP) on 107 pitches.',
          ],
        },
      ],
    },
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
          innings_pitched: '1.6666666666666667',
          innings_pitched_outs: 5,
          pitches_thrown: 24,
          strikeouts: 2,
          walks: 1,
          hits_allowed: 2,
          runs_allowed: 1,
          sentence: 'Alpha Reliever - 1.2 IP, 24 pitches, 2 K, 1 BB, 2 H, 1 R.',
        },
      ],
      games: [
        {
          mlb_game_pk: 9602,
          opponent: 'New York Yankees',
          opponent_abbreviation: 'NYY',
          game_shape: 'normal_start',
          context_label: null,
          starter: {
            pitcher_id: 10,
            pitcher_mlb_id: 90010,
            pitcher_full_name: 'Golf Starter',
            outs: 18,
            innings: '6.0',
            pitches: 92,
          },
          relief: {
            pitcher_count: 2,
            outs: 9,
            innings: '3.0',
            pitches: 35,
          },
          total: {
            pitcher_count: 3,
            outs: 27,
            innings: '9.0',
            pitches: 127,
          },
          context_sentences: [
            'Golf Starter started and recorded 18 outs (6.0 IP) on 92 pitches.',
            'Two relievers covered the remaining 9 outs (3.0 IP) on 35 pitches.',
          ],
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

function renderSelectedTeamBoard(props = {}) {
  return renderToStaticMarkup(
    React.createElement(TonightsBullpenBoard, {
      teams: {
        loading: false,
        data: [
          { team_id: 110, team_name: 'Test Club', team_abbreviation: 'TST' },
          { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
        ],
      },
      initialSelectedTeam: 147,
      boardPayload: {
        ...populatedBoard,
        team: { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
      },
      storyPayload: null,
      gameContextPayload: null,
      teamReliefWorkPayload: {
        ...teamReliefWorkPayload,
        team: { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
      },
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

test('fetch helper uses the selected MLB team id for team relief work', async (t) => {
  const originalFetch = globalThis.fetch
  const calls = []
  t.after(() => {
    globalThis.fetch = originalFetch
  })

  globalThis.fetch = async (url, options = {}) => {
    calls.push({ url, options })
    return { ok: true, json: async () => teamReliefWorkPayload }
  }

  await getTeamReliefWork(147)

  assert.equal(calls.length, 1)
  assert.equal(calls[0].url, '/api/bullpen/teams/147/relief-work')
  assert.equal(calls[0].url.includes('/api/bullpen/pitchers/147'), false)
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
    teamReliefWorkPayload.relief_by_date[0].appearances[1].sentence,
    teamReliefWorkPayload.relief_by_date[0].appearances[2].sentence,
    teamReliefWorkPayload.relief_by_date[1].sentence,
    teamReliefWorkPayload.relief_by_date[1].appearances[0].sentence,
    teamReliefWorkPayload.relief_by_date[1].appearances[0].roster_status_sentence,
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

test('renders relief work windows before date groups', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const windowsIndex = html.indexOf('Relief Work Windows')
  const byDateIndex = html.indexOf('Relief Work by Date')

  assert.notEqual(windowsIndex, -1)
  assert.notEqual(byDateIndex, -1)
  assert.ok(windowsIndex < byDateIndex)
})

test('date groups are collapsible with the latest date expanded', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const latestSentence = teamReliefWorkPayload.relief_by_date[0].sentence
  const olderSentence = teamReliefWorkPayload.relief_by_date[1].sentence
  const latestDetails = detailsTagFor(html, latestSentence)
  const olderDetails = detailsTagFor(html, olderSentence)

  assert.ok(htmlIncludes(html, latestSentence))
  assert.ok(htmlIncludes(html, olderSentence))
  assert.ok(latestDetails.includes('open'))
  assert.ok(!olderDetails.includes('open'))
})

test('date summary rows expose a stable header marker', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const matches = html.match(/data-testid="team-relief-date-summary"/g) || []

  assert.equal(matches.length, teamReliefWorkPayload.relief_by_date.length)
})

test('renders server-authored game context label and sentences verbatim', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const labeledGame = teamReliefWorkPayload.relief_by_date[0].games[0]

  assert.ok(htmlIncludes(html, labeledGame.context_label))
  for (const sentence of labeledGame.context_sentences) {
    assert.ok(htmlIncludes(html, sentence), sentence)
  }
  assert.equal(htmlIncludes(html, labeledGame.game_shape), false)
})

test('starter-assignment sentence renders first, before the game facts', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const labeledGame = teamReliefWorkPayload.relief_by_date[0].games[0]
  const [assignmentSentence, followupSentence, coverageSentence] = labeledGame.context_sentences

  const assignmentIndex = html.indexOf(assignmentSentence)
  const followupIndex = html.indexOf(followupSentence)
  const coverageIndex = html.indexOf(coverageSentence)

  assert.notEqual(assignmentIndex, -1)
  assert.notEqual(followupIndex, -1)
  assert.notEqual(coverageIndex, -1)
  assert.ok(assignmentIndex < followupIndex)
  assert.ok(followupIndex < coverageIndex)
})

test('raw starter-assignment identifiers never render', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const labeledGame = teamReliefWorkPayload.relief_by_date[0].games[0]

  assert.equal(htmlIncludes(html, labeledGame.starter_assignment.narrative_type), false)
  assert.equal(htmlIncludes(html, 'starter_assignment'), false)
  assert.equal(htmlIncludes(html, 'narrative_type'), false)
})

test('game context without a starter-assignment sentence renders as before', () => {
  const labeledGame = teamReliefWorkPayload.relief_by_date[0].games[0]
  const { starter_assignment, ...gameWithoutAssignment } = labeledGame
  const classicSentences = [
    'Delta Starter started and recorded 6 outs (2.0 IP) on 35 pitches.',
    'Six relievers covered the remaining 21 outs (7.0 IP) on 107 pitches.',
    '7 pitchers combined for 27 outs (9.0 IP) and 142 pitches.',
  ]
  const payload = {
    ...teamReliefWorkPayload,
    relief_by_date: [
      {
        ...teamReliefWorkPayload.relief_by_date[0],
        games: [{ ...gameWithoutAssignment, context_sentences: classicSentences }],
      },
      teamReliefWorkPayload.relief_by_date[1],
    ],
  }
  const html = renderPanel({ payload })

  assert.ok(htmlIncludes(html, labeledGame.context_label))
  for (const sentence of classicSentences) {
    assert.ok(htmlIncludes(html, sentence), sentence)
  }
  assert.equal(htmlIncludes(html, starter_assignment.sentence), false)
})

test('omits game context that has no server-authored label', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const unlabeledGame = teamReliefWorkPayload.relief_by_date[1].games[0]
  const matches = html.match(/data-testid="team-relief-game-context"/g) || []

  assert.equal(matches.length, 1)
  for (const sentence of unlabeledGame.context_sentences) {
    assert.equal(htmlIncludes(html, sentence), false, sentence)
  }
  assert.equal(htmlIncludes(html, unlabeledGame.game_shape), false)
})

test('date groups without games render no game context container', () => {
  const payload = {
    ...teamReliefWorkPayload,
    relief_by_date: teamReliefWorkPayload.relief_by_date.map((group) => {
      const { games, ...rest } = group
      return rest
    }),
  }
  const html = renderPanel({ payload })
  const matches = html.match(/data-testid="team-relief-game-context"/g) || []

  assert.equal(matches.length, 0)
})

test('formats pitcher IP from outs using baseball notation', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })

  for (const value of ['1.0', '1.1', '1.2', '0.2']) {
    assert.ok(htmlIncludes(html, value), value)
  }
  for (const rawDecimal of [
    '1.3333333333333333',
    '1.6666666666666667',
    '0.6666666666666666',
  ]) {
    assert.equal(htmlIncludes(html, rawDecimal), false, rawDecimal)
  }
})

test('appearance rows use payload facts without new interpretation', () => {
  const html = renderPanel({ payload: teamReliefWorkPayload })
  const appearance = teamReliefWorkPayload.relief_by_date[0].appearances[0]

  assert.ok(htmlIncludes(html, appearance.pitcher_full_name))
  assert.ok(htmlIncludes(html, 'IP'))
  assert.ok(htmlIncludes(html, 'P'))
  assert.ok(htmlIncludes(html, 'K'))
  assert.ok(htmlIncludes(html, 'BB'))
  assert.ok(htmlIncludes(html, 'H'))
  assert.ok(htmlIncludes(html, 'R'))
  assert.ok(htmlIncludes(html, '1.0'))
  assert.ok(htmlIncludes(html, String(appearance.pitches_thrown)))
  assert.ok(htmlIncludes(html, String(appearance.strikeouts)))
  assert.ok(htmlIncludes(html, String(appearance.walks)))
  assert.ok(htmlIncludes(html, String(appearance.hits_allowed)))
  assert.ok(htmlIncludes(html, String(appearance.runs_allowed)))
  assert.ok(htmlIncludes(html, appearance.sentence))
  assert.ok(htmlIncludes(html, appearance.roster_status_sentence))
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

  assert.ok(htmlIncludes(loadingHtml, 'Recent Bullpen Work'))
  assert.ok(htmlIncludes(loadingHtml, 'Loading recent bullpen work…'))
  assert.ok(htmlIncludes(errorHtml, 'Recent Bullpen Work'))
  assert.ok(htmlIncludes(errorHtml, 'Recent bullpen work is unavailable.'))
  assert.equal(htmlIncludes(errorHtml, 'network details must not render'), false)
})

test('selected team board renders Recent Bullpen Work in the visible board path', () => {
  const html = renderSelectedTeamBoard()

  assert.ok(htmlIncludes(html, 'Recent Bullpen Work'))
  assert.ok(htmlIncludes(html, 'Review pitcher lanes'))
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Board — New York Yankees'))
  assert.ok(htmlIncludes(html, teamReliefWorkPayload.scope_sentence))

  const operatingIndex = html.indexOf('Review pitcher lanes')
  const reliefIndex = html.indexOf('Recent Bullpen Work')
  const boardIndex = html.indexOf('Tonight&#x27;s Bullpen Board — New York Yankees')

  assert.ok(operatingIndex !== -1)
  assert.ok(reliefIndex !== -1)
  assert.ok(boardIndex !== -1)
  assert.ok(operatingIndex < reliefIndex)
  assert.ok(reliefIndex < boardIndex)
})

test('selected team board keeps relief work visible on endpoint failure', () => {
  const html = renderSelectedTeamBoard({
    teamReliefWorkPayload: undefined,
    teamReliefWorkError: 'request failed',
  })

  assert.ok(htmlIncludes(html, 'Recent Bullpen Work'))
  assert.ok(htmlIncludes(html, 'Recent bullpen work is unavailable.'))
  assert.equal(htmlIncludes(html, 'request failed'), false)
  assert.ok(htmlIncludes(html, 'Tonight&#x27;s Bullpen Board — New York Yankees'))
})

test('selected team board renders one Recent Bullpen Work panel', () => {
  const html = renderSelectedTeamBoard()
  const matches = html.match(/Recent Bullpen Work/g) || []

  assert.equal(matches.length, 1)
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
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  const source = `${panelSource}\n${bullpenSource}\n${boardSource}`

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

test('the relief work panel mounts once, on the team board only', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/Bullpen.jsx', import.meta.url),
    'utf8',
  )
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  // phase-0-clarity/03: the duplicate mount on the All Pitchers tab was
  // removed — the Phase 0G evidence panel renders once, on the Team Board.
  assert.equal(source.includes('TeamReliefWorkPanel'), false)
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  for (const legacyText of [
    'All Teams',
    'Availability',
    'P/7d',
    'Rest',
    'App/7d',
    'Show pitchers outside the freshness window',
  ]) {
    assert.ok(source.includes(legacyText), legacyText)
  }
  for (const removedLeaderboardText of [
    'Recent Load',
    "<th className={thStyle('score')}",
    '<RiskBadge',
  ]) {
    assert.equal(source.includes(removedLeaderboardText), false, removedLeaderboardText)
  }
})

test('team board mounts the panel between operating state and board lanes', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )
  const operatingIndex = source.indexOf('<BullpenOperatingStateCard')
  const mountIndex = source.indexOf('<TeamReliefWorkPanel')
  const boardIndex = source.indexOf('<BullpenBoardView')

  assert.notEqual(operatingIndex, -1)
  assert.notEqual(mountIndex, -1)
  assert.notEqual(boardIndex, -1)
  assert.ok(operatingIndex < mountIndex)
  assert.ok(mountIndex < boardIndex)
  assert.ok(source.includes('teamId={selectedTeam}'))
  assert.equal(source.includes('teamId={detailPitcherId}'), false)
})
