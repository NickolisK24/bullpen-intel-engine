import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

import { makeBoard } from './fixtures/bullpenBoardFixtures.mjs'

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
  default: BullpenOperatingStateCard,
  getBullpenOperatingStateView,
} = await server.ssrLoadModule('/src/components/bullpen/BullpenOperatingStateCard.jsx')
const {
  getBoardContextView,
  teamOperatingStateFreshnessIsDegraded,
} = await server.ssrLoadModule('/src/components/bullpen/board/tonightsBullpenBoardView.js')
const {
  toOperatingStateReadModel,
} = await server.ssrLoadModule('/src/adapters/operatingStateReadModel.js')

const escapeRegExp = (value) => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
const internalTerms = [
  'backend',
  'endpoint',
  'source',
  'snapshot',
  'COIN',
  'V2',
  'V3',
  'V4',
  '2.0',
  'deterministic',
  'recommendation engine',
  'baseline distribution',
  'baseline',
  'governance layer',
  'governance',
  'coverageSafetyVersion',
  'capacityState',
  'resourceHealthState',
  'thresholds',
]
const forbiddenPattern = (term) => {
  const escaped = escapeRegExp(term)
  return /^[a-z0-9]+$/i.test(term)
    ? new RegExp(`\\b${escaped}\\b`, 'i')
    : new RegExp(escaped, 'i')
}
const htmlIncludes = (html, text) => new RegExp(escapeRegExp(text)).test(html)
const render = (props) => renderToStaticMarkup(
  React.createElement(
    MemoryRouter,
    null,
    React.createElement(BullpenOperatingStateCard, props),
  ),
)

const currentFreshness = {
  data_through: '2026-06-26',
  last_successful_sync: '2026-06-26T10:04:00Z',
  is_current: true,
  sync_status: 'success',
}

function contextFor(cardsByStatus) {
  return getBoardContextView(makeBoard({ cardsByStatus }))
}

function teamOperatingBoard(overrides = {}) {
  return makeBoard({
    team: { team_id: 121, team_name: 'New York Mets', team_abbreviation: 'NYM' },
    cardsByStatus: {
      Available: Array.from({ length: 5 }, (_, i) => ({
        pitcher_id: i + 1,
        name: `Mets Available ${i}`,
        availability_status: 'Available',
      })),
      Monitor: [{ pitcher_id: 20, name: 'Mets Monitor', availability_status: 'Monitor' }],
    },
    rosterAuthority: {
      capability: 'roster_authority_v1',
      invariant: true,
      category_counts: { injured_list: 2 },
      counts: {
        bullpen_arms: 6,
        active_bullpen_arms: 6,
        inactive_roster_context_count: 3,
        roster_unknown_count: 0,
      },
      population: { total_candidates: 9, known_count: 9, unknown_count: 0, roster_status_coverage: 1 },
      evidence: {
        bullpen_arms: [],
        active_bullpen_arms: [],
        inactive_roster_context_count: [],
        roster_unknown_count: [],
      },
      limitations: ['Roster status reflects the latest loaded roster context.'],
    },
    ...overrides,
  })
}

function renderTeamOperatingCard(board, props = {}) {
  const density = props.density || 'full'
  const readModel = toOperatingStateReadModel(board, {
    scope: 'team',
    team: board?.team,
    cta: { href: '#pitcher-lanes', label: 'Review pitcher lanes' },
    density,
  })
  return render({
    readModel,
    staleWithError: teamOperatingStateFreshnessIsDegraded(readModel.freshness),
    lastSyncLabel: 'Bullpen read synced',
    density,
    ...props,
  })
}

function renderCompactTeamOperatingCard(board, props = {}) {
  return renderTeamOperatingCard(board, {
    density: 'compact',
    ...props,
  })
}

function trustedTeamShape(overrides = {}) {
  return {
    source: 'backend:test_fixture',
    coverageSafetyVersion: 'V4',
    capacityState: 'available',
    resourceHealthState: 'strained',
    thresholds: { cleanOptions: 3 },
    supportingCounts: {
      cleanOptionCount: 2,
      activeBullpenArms: 7,
    },
    byKey: {
      cleanOptions: {
        key: 'cleanOptions',
        label: 'Thin Clean Options',
        explanation: 'Cleanly available options are limited right now.',
        reasons: ['2 clean options are available.'],
        supportingCounts: { cleanOptionCount: 2 },
        source: 'backend',
      },
      coverageSafety: {
        key: 'coverageSafety',
        label: 'Stable Coverage Safety',
        explanation: 'There is still enough coverage for ordinary bullpen length.',
        reasons: ['4 coverage arms are available.'],
        supportingCounts: { coverageArms: 4 },
        source: 'backend',
      },
      workloadConcentration: {
        key: 'workloadConcentration',
        label: 'Some Workload Concentration',
        explanation: 'Recent workload is carried by a small part of the bullpen.',
        reasons: ['The top three relief arms carried most recent relief work.'],
        supportingCounts: { topThreeShare: 0.58 },
        source: 'backend',
      },
      ...overrides,
    },
  }
}

function withTeamShape(board, teamShape) {
  board.team_shape = teamShape
  return board
}

test('renders the current bullpen state in baseball-facing language', () => {
  const context = contextFor({
    Available: Array.from({ length: 8 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Monitor: [{ pitcher_id: 20, name: 'M1', availability_status: 'Monitor' }],
    Limited: [{ pitcher_id: 30, name: 'L1', availability_status: 'Limited' }],
  })

  const html = render({
    teamLabel: 'League-Wide',
    scope: 'league',
    scopeLabel: 'Scope',
    context,
    freshness: currentFreshness,
    ctaHref: '/bullpen?view=board',
  })

  assert.ok(htmlIncludes(html, 'Scope'))
  assert.ok(htmlIncludes(html, 'data-density="full"'))
  assert.ok(htmlIncludes(html, 'League-Wide'))
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Stable Overall'))
  assert.ok(htmlIncludes(html, 'Most bullpen-eligible arms remain usable, with limited league-wide pressure.'))
  assert.ok(htmlIncludes(html, 'Primary Concern'))
  assert.ok(htmlIncludes(html, 'Not every arm is cleanly available'))
  assert.equal(htmlIncludes(html, 'clean board'), false)
  assert.equal(htmlIncludes(html, 'normal board'), false)
  assert.equal(htmlIncludes(html, 'less clean room'), false)
  assert.ok(htmlIncludes(html, 'Why BaseballOS Sees This'))
  assert.ok(htmlIncludes(html, 'Bullpen workload appears manageable.'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, '8 of 10 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'This is a league-wide read, not a team-specific diagnosis.'))
  assert.equal((html.match(/Availability classifications are workload-based only/g) || []).length, 1)
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board"'))
})

test('renders a fixed operating-state read model without raw context props', () => {
  const board = makeBoard({
    cardsByStatus: {
      Available: Array.from({ length: 5 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    },
    freshness: currentFreshness,
  })
  const readModel = toOperatingStateReadModel(board, {
    scope: 'league',
    cta: { href: '/bullpen?view=board', label: 'Open Bullpen Board' },
  })
  const html = render({ readModel })

  assert.ok(htmlIncludes(html, 'data-density="full"'))
  assert.ok(htmlIncludes(html, 'League-Wide'))
  assert.ok(htmlIncludes(html, 'Stable Overall'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'href="/bullpen?view=board"'))
})

test('handles missing bullpen data with an honest unavailable state', () => {
  const html = render({ context: null, freshness: null })

  assert.ok(htmlIncludes(html, 'No current bullpen read available.'))
  assert.ok(htmlIncludes(html, 'BaseballOS will show this card when enough current bullpen context is available.'))
  assert.ok(htmlIncludes(html, 'Freshness unavailable'))
})

test('omits concern rows when count fields are missing', () => {
  const html = render({
    context: {
      hasContext: true,
      state: 'manageable',
      label: 'Bullpen workload appears manageable.',
      reasons: ['Availability read is present, but lane counts were not included.'],
      limitations: [],
    },
    freshness: currentFreshness,
  })

  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Stable'))
  assert.ok(!htmlIncludes(html, 'Primary Concern'))
  assert.ok(!htmlIncludes(html, 'Secondary Concern'))
})

test('renders trusted freshness values without inventing per-card freshness', () => {
  const context = contextFor({
    Available: Array.from({ length: 4 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
  })
  const html = render({ context, freshness: currentFreshness })

  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 26'))
  assert.ok(htmlIncludes(html, 'Dashboard read synced 6:04 AM ET'))
})

test('renders league-wide Thin summary without implied baseline language', () => {
  const context = contextFor({
    Available: Array.from({ length: 6 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Monitor: [{ pitcher_id: 20, name: 'M1', availability_status: 'Monitor' }],
    Avoid: Array.from({ length: 2 }, (_, i) => ({ pitcher_id: 40 + i, name: `X${i}`, availability_status: 'Avoid' })),
    Unavailable: [{ pitcher_id: 60, name: 'U1', availability_status: 'Unavailable' }],
  })

  const html = render({
    teamLabel: 'League-Wide',
    scope: 'league',
    scopeLabel: 'Scope',
    context,
    freshness: currentFreshness,
  })

  assert.ok(htmlIncludes(html, 'Scope'))
  assert.ok(htmlIncludes(html, 'League-Wide'))
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Thin'))
  assert.ok(htmlIncludes(html, 'Fewer bullpen-eligible arms are cleanly available right now.'))
  assert.ok(htmlIncludes(html, 'Not every arm is cleanly available'))
  assert.equal(htmlIncludes(html, 'The bullpen has fewer cleanly available arms than usual.'), false)

  for (const phrase of ['than usual', 'normal board', 'baseline', 'expected']) {
    assert.equal(new RegExp(escapeRegExp(phrase), 'i').test(html), false, `rendered implied comparison: ${phrase}`)
  }

  for (const section of ['Evidence', 'Freshness', 'Limitations']) {
    assert.ok(htmlIncludes(html, section), `missing section: ${section}`)
  }

  for (const term of internalTerms) {
    assert.equal(forbiddenPattern(term).test(html), false, `leaked ${term}`)
  }
})

test('renders stale and sample freshness as distinct trust states', () => {
  const context = contextFor({
    Available: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: i + 1, name: `A${i}`, availability_status: 'Available' })),
    Limited: [{ pitcher_id: 50, name: 'L1', availability_status: 'Limited' }],
  })

  const stale = render({
    context,
    freshness: {
      data_through: '2026-06-25',
      last_successful_sync: '2026-06-25T10:04:00Z',
      is_current: false,
      is_stale: true,
      sync_status: 'failed',
    },
    staleWithError: true,
  })
  assert.ok(htmlIncludes(stale, 'Refresh delayed'))
  assert.ok(htmlIncludes(stale, 'showing last loaded data from Jun 25.'))

  const sample = render({
    context,
    freshness: {
      data_through: '2026-06-24',
      freshness_state: 'sample',
      sample: true,
    },
  })
  assert.ok(htmlIncludes(sample, 'Sample intelligence state'))
  assert.ok(htmlIncludes(sample, 'Not live MLB data.'))
})

test('renders a team operating card from a team-board fixture', () => {
  const board = teamOperatingBoard()
  const html = renderTeamOperatingCard(board)

  assert.ok(htmlIncludes(html, 'Team'))
  assert.ok(htmlIncludes(html, 'data-density="full"'))
  assert.ok(htmlIncludes(html, 'New York Mets'))
  assert.equal(htmlIncludes(html, 'Scope'), false)
  assert.equal(htmlIncludes(html, 'League-Wide'), false)
  assert.ok(htmlIncludes(html, 'Current Bullpen State'))
  assert.ok(htmlIncludes(html, 'Stable'))
  assert.ok(htmlIncludes(html, 'Why BaseballOS Sees This'))
  assert.ok(htmlIncludes(html, 'Evidence'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'Review pitcher lanes'))
  assert.ok(htmlIncludes(html, 'href="#pitcher-lanes"'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 4'))
  assert.ok(htmlIncludes(html, 'Bullpen read synced 8:00 AM ET'))
})

test('renders compact team operating card density with the core read intact', () => {
  const board = teamOperatingBoard()
  const html = renderCompactTeamOperatingCard(board)

  assert.ok(htmlIncludes(html, 'data-density="compact"'))
  assert.ok(htmlIncludes(html, 'Team'))
  assert.ok(htmlIncludes(html, 'New York Mets'))
  assert.ok(htmlIncludes(html, 'Current Bullpen State: Stable'))
  assert.ok(htmlIncludes(html, 'The current bullpen read shows enough usable coverage to avoid a clear pressure flag.'))
  assert.ok(htmlIncludes(html, 'Primary Concern'))
  assert.ok(htmlIncludes(html, 'Active workload is usable'))
  assert.ok(htmlIncludes(html, 'Secondary Concern'))
  assert.ok(htmlIncludes(html, 'Roster pressure remains part of the story'))
  assert.ok(htmlIncludes(html, '5 of 6 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, '3 bullpen arms are inactive or unavailable.'))
  assert.ok(htmlIncludes(html, 'Freshness'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 4'))
  assert.ok(htmlIncludes(html, 'Bullpen read synced 8:00 AM ET'))
  assert.ok(htmlIncludes(html, 'Limitations:'))
  assert.ok(htmlIncludes(html, 'workload-based only; excludes manager intent, bullpen phone activity, private medical availability, unreported injuries, and final game-day decisions.'))
  assert.ok(htmlIncludes(html, 'Review pitcher lanes'))
  assert.ok(htmlIncludes(html, 'href="#pitcher-lanes"'))
  assert.equal(htmlIncludes(html, 'BaseballOS does not know manager intent'), false)
  assert.equal(htmlIncludes(html, 'Why BaseballOS Sees This'), false)
})

test('renders safe team context reads without changing freshness or limitations', () => {
  const board = withTeamShape(teamOperatingBoard(), trustedTeamShape())
  const html = renderTeamOperatingCard(board)

  assert.ok(htmlIncludes(html, 'Clean options'))
  assert.ok(htmlIncludes(html, 'Thin Clean Options'))
  assert.ok(htmlIncludes(html, 'Cleanly available options are limited right now.'))
  assert.ok(htmlIncludes(html, '2 clean options are available.'))
  assert.ok(htmlIncludes(html, 'Coverage safety'))
  assert.ok(htmlIncludes(html, 'Stable Coverage Safety'))
  assert.ok(htmlIncludes(html, 'There is still enough coverage for ordinary bullpen length.'))
  assert.ok(htmlIncludes(html, '4 coverage arms are available.'))
  assert.ok(htmlIncludes(html, 'Workload concentration'))
  assert.ok(htmlIncludes(html, 'Some Workload Concentration'))
  assert.ok(htmlIncludes(html, 'Recent workload is carried by a small part of the bullpen.'))
  assert.ok(htmlIncludes(html, 'The top three relief arms carried most recent relief work.'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 4'))
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'BaseballOS does not know manager intent'))

  for (const term of internalTerms) {
    assert.equal(forbiddenPattern(term).test(html), false, `leaked ${term}`)
  }
  assert.equal(htmlIncludes(html, 'supportingCounts'), false)
})

test('renders compact team context reads without overwhelming the team board card', () => {
  const board = withTeamShape(teamOperatingBoard(), trustedTeamShape())
  const html = renderCompactTeamOperatingCard(board)

  assert.ok(htmlIncludes(html, 'data-density="compact"'))
  assert.ok(htmlIncludes(html, 'Clean options'))
  assert.ok(htmlIncludes(html, 'Thin Clean Options'))
  assert.ok(htmlIncludes(html, 'Coverage safety'))
  assert.ok(htmlIncludes(html, 'Stable Coverage Safety'))
  assert.ok(htmlIncludes(html, 'Workload concentration'))
  assert.ok(htmlIncludes(html, 'Some Workload Concentration'))
  assert.ok(htmlIncludes(html, 'Freshness: Current'))
  assert.ok(htmlIncludes(html, 'Limitations:'))
  assert.equal(htmlIncludes(html, '2 clean options are available.'), false)

  for (const term of internalTerms) {
    assert.equal(forbiddenPattern(term).test(html), false, `leaked compact ${term}`)
  }
})

test('omits limited and unsafe team context reads from visible card copy', () => {
  const board = withTeamShape(teamOperatingBoard(), trustedTeamShape({
    cleanOptions: {
      key: 'cleanOptions',
      label: 'Limited Read',
      explanation: 'Backend team bullpen shape was not returned.',
      reasons: ['Backend team bullpen shape was not returned.'],
    },
    coverageSafety: {
      key: 'coverageSafety',
      label: 'Stable Coverage Safety',
      explanation: 'backend endpoint source snapshot V4 deterministic detail',
      reasons: ['COIN source detail should not render.'],
      supportingCounts: { coverageArms: 4 },
    },
    workloadConcentration: {
      key: 'workloadConcentration',
      label: 'Some Workload Concentration',
    },
  }))
  const html = renderTeamOperatingCard(board)
  const compactHtml = renderCompactTeamOperatingCard(board)

  for (const phrase of [
    'Clean options',
    'Coverage safety',
    'Workload concentration',
    'Limited Read',
    'Backend team bullpen shape was not returned.',
    'Stable Coverage Safety',
    'COIN source detail should not render.',
  ]) {
    assert.equal(htmlIncludes(html, phrase), false, `rendered unsafe full copy: ${phrase}`)
    assert.equal(htmlIncludes(compactHtml, phrase), false, `rendered unsafe compact copy: ${phrase}`)
  }

  for (const term of internalTerms) {
    assert.equal(forbiddenPattern(term).test(html), false, `leaked ${term}`)
    assert.equal(forbiddenPattern(term).test(compactHtml), false, `leaked compact ${term}`)
  }
})

test('team card separates usable active workload from roster pressure', () => {
  const html = renderTeamOperatingCard(teamOperatingBoard())

  assert.ok(htmlIncludes(html, 'Active workload is usable'))
  assert.ok(htmlIncludes(html, '5 of 6 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, 'Roster pressure remains part of the story'))
  assert.ok(htmlIncludes(html, '3 bullpen arms are on the injured list or inactive.'))
  assert.ok(htmlIncludes(html, '2 bullpen arms are on the injured list.'))
  assert.ok(htmlIncludes(html, '3 bullpen arms are inactive or unavailable.'))
  assert.equal(htmlIncludes(html, 'Nobody is hurt'), false)
  assert.equal(htmlIncludes(html, 'No injuries'), false)
})

test('team card keeps factual evidence separate from limitations', () => {
  const html = renderTeamOperatingCard(teamOperatingBoard())
  const evidenceStart = html.indexOf('Evidence')
  const freshnessStart = html.indexOf('Freshness')
  const evidenceBlock = html.slice(evidenceStart, freshnessStart)

  assert.ok(htmlIncludes(evidenceBlock, '5 of 6 relievers are classified Available.'))
  assert.ok(htmlIncludes(evidenceBlock, '2 bullpen arms are on the injured list.'))
  assert.equal(htmlIncludes(evidenceBlock, 'BaseballOS does not know manager intent'), false)
  assert.equal(htmlIncludes(evidenceBlock, 'workload-based only'), false)
  assert.ok(htmlIncludes(html, 'BaseballOS does not know manager intent'))
  assert.ok(htmlIncludes(html, 'Roster status reflects the latest loaded roster context.'))
  assert.equal(htmlIncludes(html, 'This is a league-wide read, not a team-specific diagnosis.'), false)
})

test('team card carries degraded freshness limitations when freshness fails closed', () => {
  const board = teamOperatingBoard({
    freshness: {
      data_through: '2026-06-01',
      last_successful_sync: '2026-06-01T10:04:00Z',
      is_current: false,
      is_stale: true,
      fail_closed: true,
      freshness_state: 'stale',
      limitations: ['Latest workload data is outside the active freshness window.'],
    },
  })
  const html = renderTeamOperatingCard(board)

  assert.ok(htmlIncludes(html, 'Refresh delayed'))
  assert.ok(htmlIncludes(html, 'Bullpen data through Jun 1'))
  assert.ok(htmlIncludes(html, 'Latest workload data is outside the active freshness window.'))
  assert.equal(teamOperatingStateFreshnessIsDegraded(board.freshness), true)
})

test('team card omits unsupported rows and gates starter support by sample size', () => {
  const limitedStarterBoard = {
    ...teamOperatingBoard(),
    rotation_support_pressure: {
      status: 'limited_read',
      games_analyzed: 1,
      summary: 'Low-sample starter support should not render.',
      limitations: ['Rotation support sample is limited.'],
    },
  }
  const limitedHtml = renderTeamOperatingCard(limitedStarterBoard)

  const zeroMonitorBoard = teamOperatingBoard()
  zeroMonitorBoard.context = {
    ...zeroMonitorBoard.context,
    health: {
      ...zeroMonitorBoard.context.health,
      reasons: [
        ...zeroMonitorBoard.context.health.reasons,
        '0 of 6 relievers are in the Monitor group.',
      ],
    },
  }
  const zeroMonitorHtml = renderTeamOperatingCard(zeroMonitorBoard)
  const zeroMonitorCompactHtml = renderCompactTeamOperatingCard(zeroMonitorBoard)
  assert.equal(htmlIncludes(zeroMonitorHtml, '0 of 6 relievers are in the Monitor group.'), false)
  assert.equal(htmlIncludes(zeroMonitorCompactHtml, '0 of 6 relievers are in the Monitor group.'), false)
  assert.equal(htmlIncludes(zeroMonitorCompactHtml, 'No relievers are marked Avoid or Unavailable.'), false)

  for (const phrase of [
    'Clean Options',
    'Coverage Safety',
    'Workload Concentration',
    'Trend Since Yesterday',
    'Low-sample starter support should not render.',
    'Rotation support sample is limited.',
  ]) {
    assert.equal(htmlIncludes(limitedHtml, phrase), false, `rendered unsupported copy: ${phrase}`)
    assert.equal(htmlIncludes(renderCompactTeamOperatingCard(limitedStarterBoard), phrase), false, `rendered unsupported compact copy: ${phrase}`)
  }

  const supportedStarterBoard = {
    ...teamOperatingBoard(),
    rotation_support_pressure: {
      status: 'neutral',
      games_analyzed: 3,
      summary: 'The rotation averaged 5.4 innings per start over the last 7 days, requiring 8.2 bullpen innings.',
      limitations: ['Some recent team games are excluded because starter/relief workload data is incomplete or ambiguous.'],
    },
  }
  const supportedHtml = renderTeamOperatingCard(supportedStarterBoard)

  assert.ok(htmlIncludes(supportedHtml, 'Starter support: The rotation averaged 5.4 innings per start over the last 7 days, requiring 8.2 bullpen innings.'))
  assert.ok(htmlIncludes(supportedHtml, 'Some recent team games are excluded because starter/relief workload data is incomplete or ambiguous.'))
})

test('team operating card does not expose internal vocabulary', () => {
  const html = renderTeamOperatingCard(teamOperatingBoard())
  const compactHtml = renderCompactTeamOperatingCard(teamOperatingBoard())
  for (const term of [...internalTerms, 'sample state']) {
    assert.equal(forbiddenPattern(term).test(html), false, `leaked ${term}`)
    assert.equal(forbiddenPattern(term).test(compactHtml), false, `leaked compact ${term}`)
  }
})

test('omits internal language from visible card copy', () => {
  const context = {
    hasContext: true,
    state: 'manageable',
    label: 'backend COIN snapshot V2 deterministic endpoint',
    reasons: [
      'The existing snapshot moved after the latest completed games.',
      'COIN endpoint V4 detail should never render.',
      '5 of 8 relievers are classified Available.',
    ],
    limitations: [
      'governance layer detail should never render.',
      'Latest workload data is outside the active freshness window, so this snapshot may not reflect current bullpen planning.',
    ],
    metrics: { total: 8 },
    snapshot: [
      { status: 'Available', label: 'Available', count: 5 },
      { status: 'Monitor', label: 'Monitor', count: 1 },
      { status: 'Limited', label: 'Limited', count: 1 },
      { status: 'Avoid', label: 'Avoid', count: 1 },
      { status: 'Unavailable', label: 'Unavailable', count: 0 },
    ],
  }

  const html = render({ context, freshness: currentFreshness })

  assert.ok(htmlIncludes(html, 'BaseballOS is reading the current bullpen mix from available workload context.'))
  assert.ok(htmlIncludes(html, 'existing bullpen read moved'))
  assert.ok(htmlIncludes(html, '5 of 8 relievers are classified Available.'))
  assert.ok(htmlIncludes(html, 'this bullpen read may not reflect current bullpen planning.'))

  for (const term of internalTerms) {
    assert.equal(forbiddenPattern(term).test(html), false, `leaked ${term}`)
  }
})

test('separates limitation copy from evidence', () => {
  const context = {
    hasContext: true,
    state: 'manageable',
    label: 'Bullpen workload appears manageable.',
    reasons: [
      '5 of 8 relievers are classified Available.',
      'Availability classifications are workload-based only.',
    ],
    limitations: [],
    metrics: { total: 8 },
    snapshot: [
      { status: 'Available', label: 'Available', count: 5 },
      { status: 'Monitor', label: 'Monitor', count: 1 },
      { status: 'Limited', label: 'Limited', count: 1 },
      { status: 'Avoid', label: 'Avoid', count: 1 },
      { status: 'Unavailable', label: 'Unavailable', count: 0 },
    ],
  }
  const html = render({ teamLabel: 'NYY', context, freshness: currentFreshness })
  const evidenceStart = html.indexOf('Evidence')
  const freshnessStart = html.indexOf('Freshness')
  const evidenceBlock = html.slice(evidenceStart, freshnessStart)

  assert.ok(htmlIncludes(evidenceBlock, '5 of 8 relievers are classified Available.'))
  assert.equal(htmlIncludes(evidenceBlock, 'Availability classifications are workload-based only.'), false)
  assert.ok(htmlIncludes(html, 'Limitations'))
  assert.ok(htmlIncludes(html, 'Availability classifications are workload-based only.'))
})

test('deduplicates league-wide workload limitation copy', () => {
  const context = {
    hasContext: true,
    state: 'manageable',
    label: 'Bullpen workload appears manageable.',
    reasons: [
      '5 of 8 relievers are classified Available.',
      'Availability classifications are workload-based only.',
    ],
    limitations: [],
    metrics: { total: 8 },
    snapshot: [
      { status: 'Available', label: 'Available', count: 5 },
      { status: 'Monitor', label: 'Monitor', count: 1 },
      { status: 'Limited', label: 'Limited', count: 1 },
      { status: 'Avoid', label: 'Avoid', count: 1 },
      { status: 'Unavailable', label: 'Unavailable', count: 0 },
    ],
  }
  const html = render({
    teamLabel: 'League-Wide',
    scope: 'league',
    context,
    freshness: currentFreshness,
  })

  assert.equal((html.match(/Availability classifications are workload-based only/g) || []).length, 1)
})

test('view model exposes only supported operating state labels', () => {
  const view = getBullpenOperatingStateView({
    context: contextFor({
      Available: [{ pitcher_id: 1, name: 'A1', availability_status: 'Available' }],
      Avoid: Array.from({ length: 3 }, (_, i) => ({ pitcher_id: i + 20, name: `X${i}`, availability_status: 'Avoid' })),
    }),
    freshness: currentFreshness,
  })

  assert.equal(view.stateLabel, 'Constrained')
  assert.equal(view.primaryConcern.label, 'Clean options are tight')
})
