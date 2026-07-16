import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

import {
  differingComparison,
  makeComparison,
  similarComparison,
  staleComparison,
} from './fixtures/bullpenComparisonFixtures.mjs'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const cards = await server.ssrLoadModule('/src/utils/evidenceCardModel.js')
const renderer = await server.ssrLoadModule('/src/utils/evidenceCardRenderer.js')
const textLayout = await server.ssrLoadModule('/src/utils/evidenceCardText.js')
const operatingState = await server.ssrLoadModule('/src/adapters/operatingStateReadModel.js')
const comparison = await server.ssrLoadModule(
  '/src/components/bullpen/board/teamBullpenComparisonView.js',
)

function teamRead(overrides = {}) {
  return {
    teamName: 'Test Club',
    teamAbbreviation: 'TST',
    stateLabel: 'Monitor',
    stateSummary: 'Recent work is concentrated among a small part of the bullpen.',
    why: 'Three relievers have appeared on consecutive days.',
    workloadConcentration: {
      summary: 'Recent relief work has flowed through a smaller group of arms.',
    },
    evidence: [
      'Three relievers worked yesterday.',
      'Two relievers have appeared on consecutive days.',
      'Four relievers worked at least twice in four days.',
      'This fourth receipt must not appear.',
    ],
    freshness: { dataThrough: '2026-07-14', isCurrent: true, isStale: false },
    ...overrides,
  }
}

test('team card is built only from a current public read with bounded receipts', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  assert.equal(model.cardType, 'team')
  assert.equal(model.receipts.length <= 3, true)
  assert.equal(model.receipts.length > 0, true)
  assert.equal(model.dataThroughLabel, 'July 14, 2026')
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=board&team=TST')
  assert.equal(model.displayUrl, 'baseballos.app/team/TST')
  assert.equal(model.fileName, 'baseballos-tst-bullpen-2026-07-14.png')
  assert.match(model.altText, /Test Club bullpen/)
  assert.equal(model.altText.length <= 320, true)
})

test('team card drops zero-value filler and duplicate receipts', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    evidence: [
      '0 of 8 relievers are marked unavailable.',
      'Two relievers worked yesterday.',
      ' two relievers worked yesterday. ',
      'No relievers are classified on watch.',
    ],
  }))
  assert.deepEqual(model.receipts, ['Two relievers worked yesterday.'])
})

test('team card selects one precise active-availability receipt plus distinct workload and roster context', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    evidence: [
      'Nine relievers are available from the latest completed workload data.',
      '9 of 9 relievers are classified Available.',
      'Three relievers worked yesterday.',
      '5 bullpen arms are inactive or unavailable.',
      'Two relievers have appeared on consecutive days.',
    ],
  }))

  assert.deepEqual(model.receipts, [
    '9 of 9 active relievers are classified Available.',
    'Three relievers worked yesterday.',
    'Roster context: 5 bullpen arms are inactive or unavailable.',
  ])
  assert.equal(model.receipts.filter(receipt => /available from|classified Available/i.test(receipt)).length, 1)
  assert.equal(model.receipts[0].includes('5'), false)
})

test('team card does not pad one or two distinct evidence families with semantic duplicates', () => {
  assert.deepEqual(cards.selectTeamReceipts([
    'Nine relievers are available from the latest completed workload data.',
    '9 of 9 relievers are classified Available.',
  ]), ['9 of 9 active relievers are classified Available.'])
  assert.deepEqual(cards.selectTeamReceipts([
    '9 of 9 relievers are classified Available.',
    'Three relievers worked yesterday.',
    ' three relievers worked yesterday. ',
  ]), [
    '9 of 9 active relievers are classified Available.',
    'Three relievers worked yesterday.',
  ])
})

test('team card keeps the canonical starter average receipt complete and in its existing family', () => {
  const canonicalSummary = 'Across the seven-day window, starters averaged 4.1 innings per start. The bullpen covered 21 innings after those starts.'
  const model = cards.buildTeamEvidenceCard(teamRead({
    evidence: [
      '4 of 8 relievers are classified Available.',
      'Two relievers worked yesterday.',
      canonicalSummary,
      '3 of 5 analyzed starts ended before five innings.',
    ],
  }))

  assert.equal(cards.classifyTeamReceiptFamily(canonicalSummary), 'starter_support')
  assert.deepEqual(model.receipts, [
    '4 of 8 active relievers are classified Available.',
    'Two relievers worked yesterday.',
    'Across the seven-day window, starters averaged 4.1 innings per start.',
  ])
  assert.equal(model.receipts.filter(receipt => cards.classifyTeamReceiptFamily(receipt) === 'starter_support').length, 1)
})

test('Yankees full-support card selects state proof, distinct WHY proof, then one context receipt', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    teamName: 'New York Yankees',
    teamAbbreviation: 'NYY',
    stateLabel: 'Stable',
    stateSummary: 'The current bullpen read shows enough usable coverage without a clear pressure flag.',
    why: 'Recent work is spread across the active relief group.',
    workloadConcentration: {
      summary: 'Recent work is spread across the active relief group.',
    },
    evidence: [
      'Nine relievers are available from the latest completed workload data.',
      '9 of 9 relievers are classified Available.',
      'Recent relief work was spread across 9 active relievers.',
      '5 bullpen arms are inactive or unavailable.',
      'Across the seven-day window, starters averaged 4.1 innings per start.',
      'A second workload is concentrated receipt.',
      'A second roster status receipt.',
      'Starters averaged 4.2 innings per start.',
    ],
  }))

  assert.deepEqual(model.receipts, [
    '9 of 9 active relievers are classified Available.',
    'Recent relief work was spread across 9 active relievers.',
    'Roster context: 5 bullpen arms are inactive or unavailable.',
  ])
  assert.equal(model.why, 'Recent work is spread across the active relief group.')
  assert.equal(cards.classifyTeamReceiptRole(model.receipts[0], teamRead({ stateLabel: 'Stable' })), 'primary_state')
  assert.equal(model.receipts.filter(item => cards.classifyTeamReceiptFamily(item) === 'availability').length, 1)
  assert.equal(model.receipts.filter(item => cards.classifyTeamReceiptFamily(item) === 'workload_concentration').length, 1)
  assert.equal(model.receipts.filter(item => cards.classifyTeamReceiptFamily(item) === 'roster_context').length, 1)
  assert.equal(model.receipts.filter(item => cards.classifyTeamReceiptFamily(item) === 'starter_support').length, 0)
})

test('production-shaped Yankees read keeps Team Board claims and card receipts aligned', () => {
  const payload = {
    hasContext: true,
    state: 'stable',
    label: 'Recent work is spread across the active relief group.',
    reasons: ['Recent relief work was spread across 9 active relievers.'],
    metrics: { total: 9 },
    snapshot: [{ status: 'Available', label: 'Available', count: 9 }],
    team: { team_id: 147, team_name: 'New York Yankees', team_abbreviation: 'NYY' },
    freshness: {
      data_through: '2026-07-14',
      last_successful_sync: '2026-07-14T10:04:00Z',
      is_current: true,
      sync_status: 'success',
    },
    team_shape: {
      workloadConcentration: {
        key: 'workloadConcentration',
        label: 'No Workload Concentration',
        reasons: [],
      },
    },
    roster_authority: {
      capability: 'roster_authority_v1',
      invariant: true,
      category_counts: { injured_list: 0 },
      counts: {
        bullpen_arms: 9,
        active_bullpen_arms: 9,
        inactive_roster_context_count: 5,
        roster_unknown_count: 0,
      },
      population: { total_candidates: 14, known_count: 14, unknown_count: 0, roster_status_coverage: 1 },
      limitations: [],
    },
    rotation_support_pressure: {
      capability: 'rotation_support_pressure_v1',
      status: 'heavy_pressure',
      games_in_window: 5,
      games_analyzed: 5,
      window_days: 7,
      starter_outs: 65,
      starter_avg_innings: 4.8,
      bullpen_outs_required: 63,
      short_start_count: 3,
      limitations: [],
    },
  }
  const readModel = operatingState.toOperatingStateReadModel(payload, { scope: 'team' })
  const model = cards.buildTeamEvidenceCard(readModel)

  assert.equal(model.stateLabel, readModel.stateLabel)
  assert.equal(model.summary, readModel.stateSummary)
  assert.equal(model.why, readModel.workloadConcentration.summary)
  assert.deepEqual(model.receipts, [
    '9 of 9 active relievers are classified Available.',
    'Recent relief work was spread across 9 active relievers.',
    'Roster context: 5 bullpen arms are inactive or unavailable.',
  ])
  assert.match(readModel.starterSupportPressure.summary, /starters averaged 4\.1 innings per start\./)
  assert.equal(/starters averaged \d+\.[^012] innings per start/.test(readModel.starterSupportPressure.summary), false)
})

test('Yankees limited-support card omits unsupported WHY and keeps one primary plus one context receipt', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    teamName: 'New York Yankees',
    teamAbbreviation: 'NYY',
    stateLabel: 'Stable',
    stateSummary: 'The current bullpen read shows enough usable coverage without a clear pressure flag.',
    why: 'Recent work is spread across the active relief group.',
    workloadConcentration: null,
    primaryConcern: null,
    evidence: [
      '9 of 9 relievers are classified Available.',
      '5 bullpen arms are inactive or unavailable.',
      'Across the seven-day window, starters averaged 4.1 innings per start.',
    ],
  }))

  assert.deepEqual(model.receipts, [
    '9 of 9 active relievers are classified Available.',
    'Roster context: 5 bullpen arms are inactive or unavailable.',
  ])
  assert.equal(model.why, null)
  assert.equal(model.receipts.length, 2)
  const svg = renderer.renderEvidenceCardSvg(model)
  assert.equal(svg.includes('>WHY</text>'), false)
  assert.equal(svg.includes('Recent work is spread'), false)
})

test('context-only Team card fails closed instead of publishing unrelated receipts', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    stateLabel: 'Stable',
    why: 'Recent work is spread across the active relief group.',
    workloadConcentration: null,
    primaryConcern: null,
    evidence: [
      '5 bullpen arms are inactive or unavailable.',
      'Across the seven-day window, starters averaged 4.1 innings per start.',
    ],
  }))
  assert.equal(model, null)
})

test('starter and roster context never displace or precede direct Team-card support', () => {
  const starterOnlyContext = cards.buildTeamEvidenceCard(teamRead({
    stateLabel: 'Stable',
    workloadConcentration: null,
    primaryConcern: null,
    evidence: [
      'Across the seven-day window, starters averaged 4.1 innings per start.',
      '9 of 9 relievers are classified Available.',
    ],
  }))
  assert.deepEqual(starterOnlyContext.receipts, [
    '9 of 9 active relievers are classified Available.',
    'Across the seven-day window, starters averaged 4.1 innings per start.',
  ])
  assert.equal(starterOnlyContext.receipts.length, 2)
})

test('team card fails closed for stale, sample, incomplete, or internal text', () => {
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ freshness: { dataThrough: '2026-07-14', isCurrent: false } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ freshness: { dataThrough: '2026-07-14', isCurrent: true, isSample: true } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ evidence: [] })), null)
  const ignoredRawWhy = cards.buildTeamEvidenceCard(teamRead({ why: 'Backend model score threshold changed.' }))
  assert.equal(ignoredRawWhy.why, 'Recent relief work has flowed through a smaller group of arms.')
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ workloadConcentration: { summary: 'Backend model score threshold changed.' } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ stateSummary: 'Backend model score threshold changed.' })), null)
})

test('comparison card preserves team order and all four public rows while selecting visible differences', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model.teamA.abbreviation, 'ACE')
  assert.equal(model.teamB.abbreviation, 'BEA')
  assert.deepEqual(model.rows.map(row => row.label), ['Available', 'On Watch', 'Limited', 'Unavailable'])
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=compare&team_a=ACE&team_b=BEA#comparison-evidence')
  assert.equal(model.displayUrl, 'baseballos.app · Compare ACE vs BEA')
  assert.equal(model.fileName, 'baseballos-ace-vs-bea-2026-06-04.png')
  assert.match(model.observation, /^The Aces have 6 available arms; the Bears have 3\./)
  assert.match(model.observation, /The Bears have 5 unavailable arms; the Aces have 2\./)
})

test('comparison selection prefers the largest non-tied row and applies the display-order tie break', () => {
  const candidates = cards.buildComparisonEvidenceCard({
    ...comparison.getComparisonView(differingComparison),
    labelA: 'Alpha Club',
    labelB: 'Beta Club',
    snapshot: [
      { label: 'Available', valueA: 7, valueB: 4 },
      { label: 'On Watch', valueA: 1, valueB: 1 },
      { label: 'Limited', valueA: 3, valueB: 1 },
      { label: 'Unavailable', valueA: 2, valueB: 2 },
    ],
  }, { teamA: 'ALP', teamB: 'BET' })
  assert.match(candidates.observation, /^The Alpha Club have 7 available arms; the Beta Club have 4\./)
  assert.equal(candidates.observation.includes('On Watch'), false)

  const equalDifferences = cards.buildComparisonEvidenceCard({
    ...comparison.getComparisonView(differingComparison),
    snapshot: [
      { label: 'Available', valueA: 5, valueB: 3 },
      { label: 'On Watch', valueA: 4, valueB: 2 },
      { label: 'Limited', valueA: 1, valueB: 3 },
      { label: 'Unavailable', valueA: 2, valueB: 2 },
    ],
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.match(equalDifferences.observation, /^The Aces have 5 available arms/)
  assert.match(equalDifferences.observation, /The Bears have 3 limited arms/)
  assert.equal(equalDifferences.observation.includes('On Watch'), false)
})

test('Cleveland versus Boston selects the 7-to-4 Available difference before the tied On Watch row', () => {
  const payload = makeComparison(
    { team: { team_id: 1, team_name: 'Cleveland Guardians', team_abbreviation: 'CLE' }, counts: { Available: 4, Monitor: 1, Limited: 3 } },
    { team: { team_id: 2, team_name: 'Boston Red Sox', team_abbreviation: 'BOS' }, counts: { Available: 7, Monitor: 1, Limited: 1 } },
  )
  const view = comparison.getComparisonView(payload)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'CLE', teamB: 'BOS' })

  assert.match(model.observation, /^The Boston Red Sox have 7 available arms; the Cleveland Guardians have 4\./)
  assert.match(model.observation, /The Cleveland Guardians have 3 limited arms; the Boston Red Sox have 1\./)
  assert.equal(model.observation.includes('On Watch'), false)
  assert.equal(view.summary.statement, view.featuredObservation)
})

test('all-tied comparisons use one neutral complete summary', () => {
  const view = comparison.getComparisonView(similarComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model.observation, 'The bullpens match across every availability group in the current read.')
  assert.equal(view.summary.statement, model.observation)
  assert.equal(/advantage|better|edge|winner/i.test(model.observation), false)
})

test('comparison card fails closed for degraded, same-team, incomplete, or predictive reads', () => {
  assert.equal(cards.buildComparisonEvidenceCard(
    comparison.getComparisonView(staleComparison),
    { teamA: 'ACE', teamB: 'BEA' },
  ), null)
  const view = comparison.getComparisonView(differingComparison)
  assert.equal(cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'ACE' }), null)
  assert.equal(cards.buildComparisonEvidenceCard({ ...view, snapshot: view.snapshot.slice(0, 3) }, { teamA: 'ACE', teamB: 'BEA' }), null)
  assert.equal(cards.buildComparisonEvidenceCard({ ...view, summary: { statement: 'Aces have the winning edge.' } }, { teamA: 'ACE', teamB: 'BEA' }), null)
})

test('SVG output is deterministic, escaped, and fixed at 1200 by 630', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({ teamName: 'Test & Club <One>' }))
  const first = renderer.renderEvidenceCardSvg(model)
  assert.equal(first, renderer.renderEvidenceCardSvg(model))
  assert.match(first, /width="1200" height="630"/)
  assert.ok(first.includes('TEST &amp; CLUB &lt;ONE&gt; BULLPEN'))
  assert.equal(first.includes('<ONE>'), false)
})

test('team layout keeps state copy and receipts in independent bounded columns', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  const svg = renderer.renderEvidenceCardSvg(model)
  assert.ok(svg.includes('<rect x="668" y="132" width="476" height="342"'))
  assert.ok(svg.includes('<text x="56" y="263"'))
  assert.ok(svg.includes('<text x="700" y="220"'))
  assert.equal(textLayout.measureCardText(model.summary, 23) <= 548 * 3, true)
  assert.ok(textLayout.wrapCardText(model.summary, { maxWidth: 548, maxLines: 3, fontSize: 23 }))
  for (const receipt of model.receipts) {
    assert.ok(textLayout.wrapCardText(receipt, { maxWidth: 404, maxLines: 2, fontSize: 18 }))
  }
})

test('long team copy keeps complete fields and omits receipts that cannot fit', () => {
  const tooLong = `${'A very long evidence phrase '.repeat(30).trim()}.`
  const model = cards.buildTeamEvidenceCard(teamRead({
    stateSummary: 'Recent work is concentrated. This extra sentence is intentionally long but remains secondary.',
    why: 'Three relievers have appeared on consecutive days. Additional context stays outside the bounded card when needed.',
    evidence: [
      tooLong,
      'Two relievers have appeared on consecutive days.',
      'Four relievers worked at least twice in four days.',
    ],
  }))
  assert.equal(model.summary, 'Recent work is concentrated. This extra sentence is intentionally long but remains secondary.')
  assert.equal(model.receipts.includes(tooLong), false)
  assert.equal(model.receipts.length, 1)
  const svg = renderer.renderEvidenceCardSvg(model)
  assert.equal(svg.includes('…'), false)
  assert.ok(svg.includes('baseballos.app/team/TST'))
  assert.equal(svg.includes('view=board'), false)
})

test('comparison statement selection preserves complete sentences and uses bounded fallbacks', () => {
  const view = comparison.getComparisonView(differingComparison)
  const long = `${'The current bullpen comparison carries a deliberately long neutral clause '.repeat(12).trim()}.`
  const short = 'The current counts differ across the two bullpens.'
  const shorterModel = cards.buildComparisonEvidenceCard({
    ...view,
    observations: [{ statement: long }, { statement: short }],
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.match(shorterModel.observation, /^The Aces have 6 available arms/)

  const fallbackModel = cards.buildComparisonEvidenceCard({
    ...view,
    snapshot: [],
    observations: [{ statement: long }],
    summary: { statement: long },
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(fallbackModel, null)

  const noFitModel = cards.buildComparisonEvidenceCard({
    ...view,
    labelA: 'A'.repeat(42),
    labelB: 'B'.repeat(42),
    observations: [{ statement: long }],
    summary: { statement: long },
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(noFitModel.observation, 'The current side-by-side counts are shown at left.')
  assert.equal(/[.!?]$/.test(noFitModel.observation), true)
  assert.equal(noFitModel.observation.endsWith('...'), false)
  assert.equal(noFitModel.observation.endsWith('…'), false)
})

test('long comparison headings stay in separate regions around centered VS', () => {
  const view = comparison.getComparisonView(differingComparison)
  for (const teamName of [
    'Los Angeles Angels', 'Los Angeles Dodgers', 'Arizona Diamondbacks',
    'Cleveland Guardians', 'Philadelphia Phillies', 'Minnesota Twins',
    'New York Yankees', 'Kansas City Royals',
  ]) {
    assert.ok(textLayout.wrapCardText(teamName.toUpperCase(), {
      maxWidth: 220, maxLines: 2, fontSize: 22,
    }), teamName)
  }
  const model = cards.buildComparisonEvidenceCard({
    ...view,
    labelA: 'Arizona Diamondbacks',
    labelB: 'Los Angeles Angels',
  }, { teamA: 'ARI', teamB: 'LAA' })
  const svg = renderer.renderEvidenceCardSvg(model)
  assert.ok(svg.includes('x="360" text-anchor="middle"'))
  assert.ok(svg.includes('x="500" text-anchor="middle"'))
  assert.ok(svg.includes('>VS</text>'))
  assert.ok(svg.includes('x="640" text-anchor="middle"'))
  assert.equal([...svg.matchAll(/x="360" text-anchor="middle"/g)].length >= 6, true)
  assert.equal([...svg.matchAll(/x="640" text-anchor="middle"/g)].length >= 6, true)
  assert.equal(svg.includes('team_a='), false)
  assert.ok(svg.includes('baseballos.app · Compare ARI vs LAA'))
  assert.equal(svg.includes('…'), false)
})

test('PNG renderer draws the fixed canvas and revokes its temporary URL', async () => {
  const calls = []
  class FakeImage {
    set src(value) { calls.push(['image', value]); queueMicrotask(() => this.onload()) }
  }
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ({ drawImage: (...args) => calls.push(['draw', ...args.slice(1)]) }),
    toBlob: callback => callback({ type: 'image/png' }),
  }
  const env = {
    Blob,
    Image: FakeImage,
    document: { createElement: name => (name === 'canvas' ? canvas : null) },
    URL: {
      createObjectURL: () => 'blob:card-svg',
      revokeObjectURL: value => calls.push(['revoke', value]),
    },
  }
  const blob = await renderer.renderEvidenceCardPng(cards.buildTeamEvidenceCard(teamRead()), env)
  assert.equal(blob.type, 'image/png')
  assert.equal(canvas.width, 1200)
  assert.equal(canvas.height, 630)
  assert.deepEqual(calls.find(call => call[0] === 'draw').slice(1), [0, 0, 1200, 630])
  assert.ok(calls.some(call => call[0] === 'revoke' && call[1] === 'blob:card-svg'))
})
