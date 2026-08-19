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

after(async () => server.close())

const { default: TeamReliefWorkPanel, getReliefLedgerGroups } = await server.ssrLoadModule(
  '/src/components/bullpen/TeamReliefWorkPanel.jsx',
)

const reliefPayload = {
  capability: 'public_team_relief_work',
  data_through: '2026-08-18',
  scope_sentence: 'Covers appearances made for TST per official MLB game records.',
  relief_by_date: [
    {
      game_date: '2026-08-18',
      sentence: 'August 18 — 3 relief appearances across 2 games, 2.0 IP, 28 pitches.',
      games: [
        {
          mlb_game_pk: 802,
          game_number: 2,
          opponent_abbreviation: 'BOS',
          reconciled: true,
          starter_authority: 'official_completed_game_starter',
          context_label: 'Extended bullpen coverage',
          context_sentences: ['Three relievers covered the remaining six outs.'],
        },
        {
          mlb_game_pk: 801,
          game_number: 1,
          opponent_abbreviation: 'BOS',
          reconciled: true,
          starter_authority: 'official_completed_game_starter',
          context_label: null,
          context_sentences: [],
        },
      ],
      appearances: [
        {
          pitcher_id: 1,
          pitcher_full_name: 'First Game Arm',
          mlb_game_pk: 801,
          opponent_abbreviation: 'BOS',
          innings_pitched_outs: 0,
          pitches_thrown: 0,
        },
        {
          pitcher_id: 9,
          pitcher_full_name: 'Zachary Very Long Relief Pitcher Name',
          mlb_game_pk: 802,
          opponent_abbreviation: 'BOS',
          innings_pitched_outs: 3,
          pitches_thrown: null,
        },
        {
          pitcher_id: 8,
          pitcher_full_name: 'Second Game Arm',
          mlb_game_pk: 802,
          opponent_abbreviation: 'BOS',
          innings_pitched_outs: 3,
          pitches_thrown: 28,
        },
      ],
    },
    {
      game_date: '2026-08-16',
      sentence: 'August 16 — 1 relief appearance, 1.0 IP, 12 pitches.',
      appearances: [{
        pitcher_id: 7,
        pitcher_full_name: 'Older Arm',
        mlb_game_pk: 700,
        opponent: 'New York Club',
        innings_pitched_outs: 3,
        pitches_thrown: 12,
      }],
    },
  ],
  windows: {
    window_14: { sentence: 'A separate 14-day aggregate that belongs elsewhere.' },
  },
}

const recentReliefWork = {
  population_basis: 'official_appearance_team_relief_appearances',
  read: reliefPayload,
}

const read = {
  recentReliefWork,
  sectionStatus: {
    recent_relief_work: {
      status: 'available',
      reason_code: null,
      limitations: [],
      represented_date: '2026-08-18',
    },
  },
}

const renderPanel = props => renderToStaticMarkup(React.createElement(TeamReliefWorkPanel, props))

test('Recent Relief Work renders the Team Board v2 read as a game ledger', () => {
  const html = renderPanel({ read })

  assert.ok(html.includes('Recent Relief Work'))
  assert.ok(html.includes(reliefPayload.scope_sentence))
  assert.match(html, /date(?:T|t)ime="2026-08-18"/)
  assert.ok(html.includes('Game 2 · vs. BOS'))
  assert.ok(html.includes('Game 1 · vs. BOS'))
  assert.ok(html.includes('Zachary Very Long Relief Pitcher Name'))
  assert.ok(html.includes('3 outs · 1.0 IP'))
  assert.equal(html.includes(reliefPayload.windows.window_14.sentence), false)
  assert.equal(html.includes('<details'), false)
})

test('backend game and appearance order is preserved without frontend ranking', async () => {
  const groups = getReliefLedgerGroups(recentReliefWork)
  const html = renderPanel({ read })
  const componentSource = await readFile(
    new URL('../src/components/bullpen/TeamReliefWorkPanel.jsx', import.meta.url),
    'utf8',
  )

  assert.deepEqual(groups.map(group => group.gameDate), ['2026-08-18', '2026-08-16'])
  assert.deepEqual(groups[0].sections.map(section => section.gameId), [802, 801])
  assert.deepEqual(groups[0].sections[0].appearances.map(row => row.pitcher_id), [9, 8])
  assert.ok(html.indexOf('Zachary Very Long Relief Pitcher Name') < html.indexOf('Second Game Arm'))
  assert.ok(html.indexOf('Second Game Arm') < html.indexOf('First Game Arm'))
  assert.equal(componentSource.includes('.sort('), false)
})

test('unknown work remains unavailable while legitimate zero remains zero', () => {
  const html = renderPanel({ read })
  const unknownStart = html.indexOf('Zachary Very Long Relief Pitcher Name')
  const unknownEnd = html.indexOf('Second Game Arm')
  const unknownRow = html.slice(unknownStart, unknownEnd)
  const zeroStart = html.indexOf('First Game Arm')
  const zeroRow = html.slice(zeroStart)

  assert.ok(unknownRow.includes('Unavailable'))
  assert.equal(unknownRow.includes('>0<'), false)
  assert.ok(zeroRow.includes('0 outs · 0.0 IP'))
  assert.ok(zeroRow.includes('>0<'))
})

test('game context remains fail-closed on reconciliation and starter authority', () => {
  const invalid = structuredClone(reliefPayload)
  invalid.relief_by_date[0].games[0].reconciled = false
  const invalidRead = {
    ...read,
    recentReliefWork: { ...recentReliefWork, read: invalid },
  }
  const invalidHtml = renderPanel({ read: invalidRead })
  const validHtml = renderPanel({ read })

  assert.ok(validHtml.includes('Extended bullpen coverage'))
  assert.ok(validHtml.includes('Three relievers covered the remaining six outs.'))
  assert.equal(invalidHtml.includes('Extended bullpen coverage'), false)
  assert.equal(invalidHtml.includes('Three relievers covered the remaining six outs.'), false)
})

test('loading, request error, unavailable, partial, and empty states stay scoped', () => {
  assert.ok(renderPanel({ loading: true }).includes('recent-relief-work-skeleton'))

  const errorHtml = renderPanel({ read, error: 'private exception' })
  assert.ok(errorHtml.includes('Recent relief-work records could not be loaded.'))
  assert.equal(errorHtml.includes('private exception'), false)

  assert.ok(renderPanel({ read: {
    ...read,
    sectionStatus: { recent_relief_work: { status: 'unavailable' } },
  } }).includes('Official recent relief-work records are unavailable.'))

  assert.ok(renderPanel({ read: {
    ...read,
    recentReliefWork: {
      ...recentReliefWork,
      read: { ...reliefPayload, unattributed_sentence: 'One official appearance remains unattributed.' },
    },
    sectionStatus: { recent_relief_work: { status: 'partial', limitations: [] } },
  } }).includes('One official appearance remains unattributed.'))

  assert.ok(renderPanel({ read: {
    ...read,
    recentReliefWork: {
      ...recentReliefWork,
      read: { ...reliefPayload, relief_by_date: [], absence_sentence: 'No relief appearances in the governed source window.' },
    },
  } }).includes('No relief appearances in the governed source window.'))
})

test('withheld date groups render no manufactured appearance rows', () => {
  const withheld = {
    ...reliefPayload,
    relief_by_date: [{
      game_date: '2026-08-17',
      unavailable: true,
      sentence: 'August 17 — relief work is unavailable because the records do not reconcile.',
      appearances: [],
    }],
  }
  const html = renderPanel({ read: {
    ...read,
    recentReliefWork: { ...recentReliefWork, read: withheld },
    sectionStatus: { recent_relief_work: { status: 'partial', limitations: [] } },
  } })

  assert.ok(html.includes('Game relief work unavailable'))
  assert.ok(html.includes('records do not reconcile'))
  assert.equal(html.includes('Pitcher unavailable'), false)
})

test('production consumes one shared v2 request and retires the relief-work request state', async () => {
  const boardSource = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )

  assert.equal((boardSource.match(/getTeamBoardV2\(/g) || []).length, 1)
  assert.equal(boardSource.includes('useTeamReliefWork'), false)
  assert.equal(boardSource.includes('getTeamReliefWork'), false)
  assert.equal(boardSource.includes('teamReliefWorkPayload'), false)
  assert.ok(boardSource.includes('read={teamBoardRead}'))
  assert.ok(boardSource.indexOf('<TeamBoardRecentUsage') < boardSource.indexOf('<TeamReliefWorkPanel'))
  assert.ok(boardSource.indexOf('<StoryCard') < boardSource.indexOf('<TeamReliefWorkPanel'))
  assert.equal(boardSource.includes('teamId={selectedTeam}'), false)
  assert.equal(boardSource.includes('teamId={detailPitcherId}'), false)
})

test('the evidence anchor remains focusable and TB-09 semantics are absent', async () => {
  const html = renderPanel({ read })
  const componentSource = await readFile(
    new URL('../src/components/bullpen/TeamReliefWorkPanel.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(html.includes('id="team-relief-work"'))
  assert.match(html, /tabindex="-1"/i)
  assert.ok(html.includes('aria-labelledby="team-relief-work-title"'))
  for (const forbidden of [
    'batters_faced', 'previous_value', 'current_value', 'daily_delta',
    'classifier_version', 'method_version', 'fatigue', 'availability',
  ]) {
    assert.equal(componentSource.includes(forbidden), false, forbidden)
  }
})
