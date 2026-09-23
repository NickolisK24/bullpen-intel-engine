import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const { default: TeamBoardRotationImpact, getRotationImpactMetrics } = await server.ssrLoadModule(
  '/src/components/bullpen/board/TeamBoardRotationImpact.jsx',
)
const { toOperatingStateReadModel } = await server.ssrLoadModule('/src/adapters/operatingStateReadModel.js')

const rotationImpact = {
  population_basis: 'stored_team_game_pitching_splits',
  read: {
    capability: 'rotation_support_pressure_v1',
    status: 'neutral',
    window_days: 7,
    reference_date: '2026-08-16',
    games_analyzed: 4,
    starter_avg_innings: 5.33,
    bullpen_innings_required: 8,
    short_start_count: 0,
    summary: 'The rotation averaged 5.3 innings per start over the last 7 days, requiring 8.0 bullpen innings.',
    relief_work_handoff: {
      target: 'team-relief-work',
      summary: 'View the matching Recent Relief Work receipts.',
      games: [{ mlb_game_pk: 123, game_date: '2026-08-16' }],
    },
    limitations: [],
    starter_outs: 64,
    bullpen_outs_required: 24,
    source_window: { source: 'team_game_pitching_splits' },
  },
}

const read = {
  rotationImpact,
  sectionStatus: {
    rotation_impact: { status: 'available', limitations: [], represented_date: '2026-08-16' },
  },
}

const renderRotation = props => renderToStaticMarkup(React.createElement(TeamBoardRotationImpact, props))

test('Rotation Impact renders the backend summary and supplied metrics verbatim', () => {
  const metrics = getRotationImpactMetrics(rotationImpact)
  const html = renderRotation({ read })

  assert.deepEqual(metrics.map(metric => [metric.label, metric.value]), [
    ['Average starter length', 5.33],
    ['Short starts', 0],
    ['Bullpen innings covered', 8],
  ])
  assert.ok(html.includes(rotationImpact.read.summary))
  assert.ok(html.includes('5.33 IP'))
  assert.ok(html.includes('0 of 4'))
  assert.ok(html.includes('4 starts analyzed'))
  assert.ok(html.includes('7-day window'))
  assert.match(html, /date(?:T|t)ime="2026-08-16"/)
  assert.ok(html.includes('href="#team-relief-work"'))
  assert.ok(html.includes('View the matching Recent Relief Work receipts.'))
})

test('Rotation Impact omits unknown metrics without converting them to zero', () => {
  const limited = {
    ...rotationImpact,
    read: {
      ...rotationImpact.read,
      starter_avg_innings: null,
      bullpen_innings_required: null,
      short_start_count: null,
      games_analyzed: 2,
    },
  }
  const metrics = getRotationImpactMetrics(limited)
  const html = renderRotation({ read: { ...read, rotationImpact: limited } })

  assert.deepEqual(metrics.map(metric => metric.label), [])
  assert.equal(html.includes('Average starter length'), false)
  assert.equal(html.includes('Bullpen innings required'), false)
  assert.equal(html.includes('Short starts'), false)
})

test('partial legacy rotation evidence never presents stored zeroes as certified facts', () => {
  const partialZero = {
    ...rotationImpact,
    read: {
      ...rotationImpact.read,
      games_analyzed: 0,
      games_in_window: 4,
      starter_avg_innings: 0,
      bullpen_innings_required: 0,
      short_start_count: 0,
      summary: null,
    },
  }
  const html = renderRotation({ read: {
    rotationImpact: partialZero,
    sectionStatus: { rotation_impact: { status: 'partial', limitations: ['0 of 4 starts have complete evidence.'] } },
  } })

  assert.equal(html.includes('0 IP'), false)
  assert.equal(html.includes('0 of 0'), false)
  assert.equal(html.includes('Average starter length'), false)
  assert.ok(html.includes('Limited evidence'))
  assert.ok(html.includes('0 of 4 starts have complete evidence.'))
})

test('TB-07 renders frozen recent starts without classifying them in the browser', async () => {
  const html = renderRotation({ read: {
    ...read,
    frozenRotationGames: {
      dataThrough: '2026-08-16', status: 'partial', gamesExcluded: 1,
      windowDays: 7, gamesAnalyzed: 2, gamesInWindow: 3,
      summary: 'Backend-authored represented-date summary.',
      starts: [
        { gameId: 55, date: '2026-08-15', starterName: 'Source Starter', starterInnings: '4.2', bullpenInnings: '4.1', shortStart: true },
        { gameId: 54, date: '2026-08-14', starterName: null, starterInnings: '6.0', bullpenInnings: '3.0', shortStart: false },
      ],
    },
  } })
  assert.ok(html.includes('Source Starter'))
  assert.ok(html.includes('Backend-authored represented-date summary.'))
  assert.equal(html.includes(rotationImpact.read.summary), false)
  assert.ok(html.includes('Starter 4.2 IP · Bullpen 4.1 IP'))
  assert.ok(html.includes('Short start: fewer than 5 starter innings'))
  assert.ok(html.includes('Starter name unavailable'))
  assert.ok(html.includes('1 recent team game lacks a complete'))
  const source = await readFile(new URL('../src/components/bullpen/board/TeamBoardRotationImpact.jsx', import.meta.url), 'utf8')
  assert.equal(source.includes('starterOuts <'), false)
  assert.equal(source.includes('bullpenOuts +'), false)
  assert.equal(source.includes('.reduce('), false)
  assert.equal(source.includes('will pitch'), false)
})

test('TB-07 keeps one incomplete game metric independent of known bullpen innings', () => {
  const html = renderRotation({ read: {
    ...read,
    frozenRotationGames: {
      dataThrough: '2026-08-16', windowDays: 7,
      status: 'partial', gamesExcluded: 0, gamesAnalyzed: 1, gamesInWindow: 1,
      summary: null,
      starts: [{
        gameId: 99, date: '2026-08-15', starterName: null,
        starterInnings: null, bullpenInnings: '4.1', shortStart: null,
        starterEvidence: { status: 'partial' }, bullpenEvidence: { status: 'complete' },
        shortStartEvidence: { status: 'unknown' },
      }],
    },
  } })
  assert.ok(html.includes('Starter unknown · Bullpen 4.1 IP'))
  assert.ok(html.includes('Some game-level rotation evidence is incomplete.'))
  assert.equal(html.includes('Short start: fewer than 5 starter innings'), false)
  assert.equal(html.includes('Starter 0 IP'), false)
})

test('Rotation Impact keeps normal governed context visible and uses no browser threshold', async () => {
  const html = renderRotation({ read })
  const source = await readFile(new URL('../src/components/bullpen/board/TeamBoardRotationImpact.jsx', import.meta.url), 'utf8')

  assert.ok(html.includes(rotationImpact.read.summary))
  assert.equal(source.includes('games_analyzed >='), false)
  assert.equal(source.includes('games_analyzed <'), false)
  assert.equal(source.includes('short_start_rate'), false)
  assert.equal(source.includes('severity'), false)
})

test('Rotation Impact uses scoped loading, partial, unavailable, error, and empty states', () => {
  assert.ok(renderRotation({ loading: true }).includes('rotation-impact-skeleton'))
  assert.ok(renderRotation({ read: {
    rotationImpact,
    sectionStatus: { rotation_impact: { status: 'partial', limitations: ['One governed rotation limitation.'] } },
  } }).includes('One governed rotation limitation.'))
  assert.ok(renderRotation({ read: {
    rotationImpact,
    sectionStatus: { rotation_impact: { status: 'unavailable' } },
  } }).includes('backend-authored rotation read is not available'))
  const errorHtml = renderRotation({ read, error: 'private exception' })
  assert.ok(errorHtml.includes('Current rotation context could not be loaded.'))
  assert.equal(errorHtml.includes('private exception'), false)
  assert.ok(renderRotation({ read: {
    rotationImpact: { ...rotationImpact, read: {} },
    sectionStatus: { rotation_impact: { status: 'available' } },
  } }).includes('No recent rotation context'))
})

test('Rotation Impact does not expose raw diagnostic split fields or predictive copy', () => {
  const html = renderRotation({ read })

  for (const forbidden of [
    'starter_outs', 'bullpen_outs_required', 'team_game_pitching_splits',
    'expected bullpen', 'will need', 'likely short start', 'starter risk',
  ]) {
    assert.equal(html.toLowerCase().includes(forbidden), false, forbidden)
  }
})

test('Rotation Impact withholds the receipts handoff when governed game identities are absent', () => {
  const withoutReceipts = {
    ...rotationImpact,
    read: {
      ...rotationImpact.read,
      relief_work_handoff: {
        ...rotationImpact.read.relief_work_handoff,
        games: [],
      },
    },
  }
  const html = renderRotation({ read: { ...read, rotationImpact: withoutReceipts } })

  assert.equal(html.includes('View the matching Recent Relief Work receipts.'), false)
})

test('Team Board retires its legacy browser-authored rotation evidence only', () => {
  const board = makeBoard()
  board.rotation_support_pressure = rotationImpact.read

  const legacy = toOperatingStateReadModel(board, { scope: 'team' })
  const teamBoardDisclosure = toOperatingStateReadModel(board, {
    scope: 'team',
    includeRotationSupport: false,
  })

  assert.ok(legacy.starterSupportPressure)
  assert.ok(legacy.evidence.includes(legacy.starterSupportPressure.summary))
  assert.equal(teamBoardDisclosure.starterSupportPressure, null)
  assert.equal(teamBoardDisclosure.evidence.includes(legacy.starterSupportPressure.summary), false)
})

test('production keeps one v2 request, correct placement, and later-package boundaries', async () => {
  const boardSource = await readFile(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const componentSource = await readFile(new URL('../src/components/bullpen/board/TeamBoardRotationImpact.jsx', import.meta.url), 'utf8')
  const gameContextSource = await readFile(new URL('../src/components/bullpen/board/TeamGameContextCard.jsx', import.meta.url), 'utf8')

  assert.equal((boardSource.match(/getTeamBoardCore\(/g) || []).length, 1)
  assert.ok(boardSource.includes('<TeamBoardRotationImpact'))
  assert.ok(boardSource.indexOf('<TeamBoardRolesDeployment') < boardSource.indexOf('<TeamBoardRotationImpact'))
  assert.ok(boardSource.indexOf('<TeamBoardPerformance') < boardSource.indexOf('<TeamBoardRotationImpact'))
  assert.ok(boardSource.indexOf('<TeamBoardWhatChanged') < boardSource.indexOf('<TeamBoardRolesDeployment'))
  assert.ok(boardSource.indexOf('<TeamBoardWhatChanged') < boardSource.indexOf('<TeamBoardRotationImpact'))
  assert.ok(boardSource.includes('<SectionPair label="Rotation and transactions">'))
  assert.ok(boardSource.includes('<TeamBoardPerformance'))
  assert.ok(boardSource.includes('<TeamReliefWorkPanel'))
  assert.ok(boardSource.includes('includeRotationSupport: false'))
  assert.equal(gameContextSource.includes('starter_avg_innings'), false)
  for (const forbidden of [
    'Math.', '.reduce(', 'starter_outs', 'bullpen_outs_required', 'short_start_rate',
    'team_game_pitching_splits', 'performance', 'transaction',
  ]) {
    assert.equal(componentSource.toLowerCase().includes(forbidden.toLowerCase()), false, forbidden)
  }
})
