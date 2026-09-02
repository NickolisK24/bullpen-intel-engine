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

const {
  default: TeamBoardAnswerBlock,
  getBullpenSummaryView,
  getTeamBoardAnswerView,
  TeamBoardAnswerSkeleton,
} = await server.ssrLoadModule('/src/components/bullpen/board/TeamBoardAnswerBlock.jsx')
const { RESTED_AVAILABILITY_DISTINCTION } = await server.ssrLoadModule('/src/utils/bullpenConcepts.js')

const team = { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' }

function read(overrides = {}) {
  return {
    team,
    representedDate: '2026-08-16',
    freshness: { data_through: '2026-08-16', is_current: true },
    teamState: {
      available: true,
      public_state: 'fresh',
      public_label: 'Fresh',
      summary: 'The bullpen enters the next game with its core options rested.',
      unavailable_message: null,
      data_through: '2026-08-16',
    },
    summary: 'The bullpen enters the next game with its core options rested.',
    activeBullpen: { arm_count: 8, arms: [] },
    recentlyUsedArms: {
      contract: 'team_board_recently_used_arms_v1',
      status: 'available',
      value: 5,
      window_days: 3,
      window_label: 'Last 3 days',
      through: '2026-08-16',
    },
    offActiveCount: {
      contract: 'team_board_off_active_count_v1',
      status: 'available',
      value: 2,
      through: '2026-08-16',
      context_label: 'Current roster context',
    },
    restStatus: {
      available: true,
      active_arm_count: 8,
      rested_arm_count: 5,
      worked_yesterday_count: 2,
      back_to_back_count: 1,
    },
    workloadOverview: {
      windows: [{ window_days: 7, pitches_total: 0 }],
    },
    sectionStatus: {
      team_state: { status: 'available', limitations: [] },
      active_bullpen: { status: 'available', limitations: [] },
      recently_used_arms: { status: 'available', limitations: [] },
      off_active_count: { status: 'available', limitations: [] },
      rest_status: { status: 'available', limitations: [] },
    },
    ...overrides,
  }
}

const render = props => renderToStaticMarkup(React.createElement(TeamBoardAnswerBlock, props))
const text = html => html.replace(/<[^>]*>/g, ' ').replace(/\s+/g, ' ').trim()

test('renders each backend-owned Team State label and the canonical summary verbatim', () => {
  for (const [publicState, publicLabel] of [
    ['fresh', 'Fresh'],
    ['stretched', 'Stretched'],
    ['vulnerable', 'Vulnerable'],
  ]) {
    const summary = `Backend summary for ${publicLabel}.`
    const answer = read({
      teamState: {
        ...read().teamState,
        public_state: publicState,
        public_label: publicLabel,
        summary,
      },
      summary,
    })
    const html = render({ read: answer })
    assert.match(html, new RegExp(`aria-label="Team State: ${publicLabel}"`))
    assert.ok(text(html).includes(summary))
  }
})

test('fail-closed Team State renders the governed message and no manufactured state', () => {
  const governedMessage = 'A current Team State read is not available because current workload evidence is incomplete.'
  const answer = read({
    teamState: {
      available: false,
      public_state: null,
      public_label: null,
      summary: null,
      unavailable_message: governedMessage,
      data_through: '2026-08-16',
    },
    summary: null,
  })
  const html = render({ read: answer })

  assert.ok(text(html).includes(governedMessage))
  assert.equal(html.includes('aria-label="Team State:'), false)
  assert.equal((text(html).match(new RegExp(governedMessage, 'g')) || []).length, 1)
  for (const state of ['Fresh', 'Stretched', 'Vulnerable']) {
    assert.equal(text(html).includes(`Team State: ${state}`), false)
  }
})

test('Bullpen Summary publishes the backend-owned recent-use count and window', () => {
  const figures = getBullpenSummaryView(read())
  const publishedHtml = render({ read: read() })
  assert.deepEqual(figures.map(({ label, value }) => ({ label, value })), [
    { label: 'Active arms', value: 8 },
    { label: 'Rested options', value: 5 },
    { label: 'Recently used arms', value: 5 },
    { label: 'Off-active count', value: 2 },
    { label: '7-day workload', value: 0 },
  ])

  const missingRead = read({
    activeBullpen: { arm_count: null, arms: [] },
    restStatus: { available: false, active_arm_count: null },
    recentlyUsedArms: {
      status: 'unavailable',
      value: null,
      window_days: 3,
      window_label: 'Last 3 days',
    },
    offActiveCount: {
      status: 'unavailable',
      value: null,
      context_label: 'Current roster context',
    },
    workloadOverview: { windows: [{ window_days: 7, pitches_total: null }] },
    sectionStatus: {
      ...read().sectionStatus,
      active_bullpen: { status: 'partial', limitations: [] },
      recently_used_arms: { status: 'unavailable', limitations: [] },
      off_active_count: { status: 'unavailable', limitations: [] },
      rest_status: { status: 'unavailable', limitations: [] },
    },
  })
  assert.deepEqual(getBullpenSummaryView(missingRead).map(figure => figure.value), [null, null, null, null, null])
  const withheldHtml = render({ read: missingRead })
  const authoritativeZeroHtml = render({
    read: read({
      recentlyUsedArms: {
        ...read().recentlyUsedArms,
        value: 0,
      },
    }),
  })
  const restedZeroHtml = render({
    read: read({
      restStatus: {
        ...read().restStatus,
        rested_arm_count: 0,
      },
    }),
  })
  assert.equal(text(withheldHtml).includes('Active arms 0'), false)
  assert.equal(text(withheldHtml).includes('Rested options 0'), false)
  assert.ok(text(publishedHtml).includes('Recently used arms 5 Last 3 days'))
  assert.ok(text(authoritativeZeroHtml).includes('Recently used arms 0 Last 3 days'))
  assert.ok(text(restedZeroHtml).includes('Rested options 0 Time since last use'))
  assert.ok(text(publishedHtml).includes('Off-active count 2 Current roster context'))
  assert.ok(text(publishedHtml).includes('7-day workload 0 Pitches'))
  assert.ok(text(withheldHtml).includes('Recently used arms — Not published'))
  assert.ok(text(withheldHtml).includes('Off-active count — Not published'))
  assert.ok(text(publishedHtml).includes(RESTED_AVAILABILITY_DISTINCTION))
  assert.ok(publishedHtml.includes('aria-describedby="rested-availability-distinction"'))
  assert.equal(text(publishedHtml).includes('Backend rest read'), false)
})

test('header keeps one governed state, one currentness line, and the answer intact', () => {
  const answer = read()
  const html = render({ read: answer })
  assert.equal((html.match(/aria-label="Team State:/g) || []).length, 1)
  assert.equal((text(html).match(/Data through/g) || []).length, 1)
  assert.ok(text(html).includes(answer.summary))
})

test('desktop Team Header aligns the labeled selector surface with the Team State badge', () => {
  const teamSwitcher = React.createElement(
    'div',
    { 'data-testid': 'team-switcher' },
    React.createElement('label', { htmlFor: 'team-board-selector' }, 'Team'),
    React.createElement('select', { id: 'team-board-selector', defaultValue: '147' },
      React.createElement('option', { value: '147' }, 'New York Yankees')),
  )
  const html = render({ read: read(), teamSwitcher })

  assert.match(html, /tablet:flex-row tablet:items-end tablet:justify-between/)
  assert.ok(html.indexOf('data-testid="team-switcher"') < html.indexOf('aria-label="Team State: Fresh"'))
  assert.match(html, /<label for="team-board-selector">Team<\/label><select id="team-board-selector"/)
})

test('loading skeleton preserves the team identity and Answer Block hierarchy', () => {
  const html = renderToStaticMarkup(React.createElement(TeamBoardAnswerSkeleton, { team }))
  assert.ok(html.includes('data-testid="team-board-answer-skeleton"'))
  assert.match(html, /<h2[^>]*>\s*New York Yankees\s*<\/h2>/)
  assert.ok(html.includes('aria-busy="true"'))
  assert.ok(html.includes('foundation-skeleton'))
})

test('request failure is scoped, retryable, and keeps known team identity', () => {
  const html = render({ team, error: new Error('The v2 read could not load.'), onRetry: () => {} })
  assert.match(html, /<h2[^>]*>\s*New York Yankees\s*<\/h2>/)
  assert.ok(text(html).includes('Team Board answer unavailable'))
  assert.ok(text(html).includes('The current Team Board answer could not be loaded.'))
  assert.equal(text(html).includes('The v2 read could not load.'), false)
  assert.match(html, /<button[^>]*>Try again<\/button>/)
})

test('partial status shows one concise limitation and never leaks a reason code', () => {
  const limitation = 'Current active-roster coverage could not be verified.'
  const html = render({ read: read({
    sectionStatus: {
      team_state: { status: 'available', limitations: [] },
      active_bullpen: {
        status: 'partial',
        reason_code: 'current_population_counts_withheld',
        limitations: [limitation, 'Second limitation stays out of the Answer Block.'],
      },
    },
  }) })

  assert.ok(text(html).includes('Limited read'))
  assert.ok(text(html).includes(limitation))
  assert.equal(text(html).includes('Second limitation stays out'), false)
  assert.equal(text(html).includes('current_population_counts_withheld'), false)
})

test('identity, state, currentness, and color-independent labels are semantic', () => {
  const html = render({ read: read() })
  assert.match(html, /<section[^>]*aria-labelledby="team-board-answer-title"/)
  assert.match(html, /<h2 id="team-board-answer-title"/)
  assert.ok(html.includes('aria-label="Team State: Fresh"'))
  assert.ok(html.includes('aria-hidden="true"'))
  assert.match(html, /<time dateTime="2026-08-16">/)
  assert.ok(text(html).includes('Data through Aug 16'))
})

test('production adoption keeps the Answer Block and current package migrations intact', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url),
    'utf8',
  )

  assert.ok(source.includes('getTeamBoardCore(selectedTeam)'))
  assert.ok(source.includes('getTeamBoardDetails(selectedTeam, coreIdentity)'))
  assert.equal((source.match(/getTeamBoardCore\(/g) || []).length, 1)
  assert.equal(source.includes('getTeamGameContext('), false)
  assert.ok(source.includes('<TeamBoardAnswerBlock'))
  assert.ok(source.includes('<TeamBoardActiveBullpen'))
  assert.ok(source.includes('<TeamBoardRecentTransactions'))
  for (const legacySection of [
    '<TeamBoardWorkloadOverview',
    '<TeamBoardWhatChanged',
    '<TeamReliefWorkPanel',
    '<BullpenReadDisclosure',
  ]) {
    assert.ok(source.includes(legacySection), legacySection)
  }
  assert.ok(source.includes('<TeamBoardRecentUsage'))
  assert.ok(source.includes('<TeamBoardRestStatus'))
  assert.equal(source.includes('<BullpenBoardView'), false)
  assert.equal(source.includes('<BullpenOperatingStateCard'), false)
  assert.equal(source.includes('<BullpenAvailabilityDistribution'), false)
  assert.equal(source.includes('<FreshnessStamp'), false)
})

test('Answer Block source contains no legacy health fallback or browser arithmetic', async () => {
  const source = await readFile(
    new URL('../src/components/bullpen/board/TeamBoardAnswerBlock.jsx', import.meta.url),
    'utf8',
  )
  for (const forbidden of [
    'context.health',
    'fatigue_score',
    'Math.round',
    '.reduce(',
    'clean share',
    'severity',
  ]) {
    assert.equal(source.includes(forbidden), false, forbidden)
  }
})
