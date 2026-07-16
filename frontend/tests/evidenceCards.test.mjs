import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
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
const story = await server.ssrLoadModule('/src/utils/evidenceCardStory.js')
const operatingState = await server.ssrLoadModule('/src/adapters/operatingStateReadModel.js')
const comparison = await server.ssrLoadModule(
  '/src/components/bullpen/board/teamBullpenComparisonView.js',
)

const WINNER_LANGUAGE = /\b(winner|wins?|advantage|better|best|stronger|edge|pick|prediction|likely|should)\b/i

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

function constrainedRead(overrides = {}) {
  return teamRead({
    stateLabel: 'Stretched',
    stateSummary: 'Clean Options are limited in the current bullpen read.',
    workloadConcentration: null,
    primaryConcern: { label: 'Clean Options are tight', body: '4 of 8 relievers are classified Available.' },
    evidence: [
      '4 of 8 relievers are classified Available.',
      'Three relievers worked yesterday.',
    ],
    ...overrides,
  })
}

test('team card is built only from a current public read with bounded receipts', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  assert.equal(model.cardType, 'team')
  assert.equal(model.cardVersion, 'team_story_v2')
  assert.equal(model.receipts.length <= 3, true)
  assert.equal(model.receipts.length > 0, true)
  assert.equal(model.dataThroughLabel, 'July 14, 2026')
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=board&team=TST#team-relief-work')
  assert.equal(model.displayUrl, 'baseballos.app/bullpen?view=board&team=TST#team-relief-work')
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

test('team card leads with the headline receipt and keeps one precise availability receipt', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    evidence: [
      'Nine relievers are available from the latest completed workload data.',
      '9 of 9 relievers are classified Available.',
      'Three relievers worked yesterday.',
      '5 bullpen arms are inactive or unavailable.',
      'Two relievers have appeared on consecutive days.',
    ],
  }))

  assert.equal(model.storyAngle, 'repeated_usage')
  assert.equal(model.headline, 'TWO TEST CLUB RELIEVERS HAVE APPEARED ON CONSECUTIVE DAYS')
  assert.deepEqual(model.receipts, [
    'Two relievers have appeared on consecutive days.',
    '9 of 9 active relievers are classified Available.',
    'Three relievers worked yesterday.',
  ])
  assert.equal(model.receipts.filter(receipt => /available from|classified Available/i.test(receipt)).length, 1)
  assert.equal(model.receipts[1].includes('5'), false)
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
  assert.equal(model.storyAngle, 'workload_concentration')
  assert.deepEqual(model.receipts, [
    'Two relievers worked yesterday.',
    '4 of 8 active relievers are classified Available.',
    'Across the seven-day window, starters averaged 4.1 innings per start.',
  ])
  assert.equal(model.receipts.filter(receipt => cards.classifyTeamReceiptFamily(receipt) === 'starter_support').length, 1)
})

test('Yankees positive read leads with an availability-depth headline supported by the first receipt', () => {
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

  assert.equal(model.storyAngle, 'availability_depth')
  assert.equal(model.headline, '9 OF 9 NEW YORK YANKEES RELIEVERS ARE AVAILABLE')
  assert.equal(model.supportingLine, 'Recent work is spread across the active relief group.')
  assert.deepEqual(model.receipts, [
    '9 of 9 active relievers are classified Available.',
    'Recent relief work was spread across 9 active relievers.',
    'Roster context: 5 bullpen arms are inactive or unavailable.',
  ])
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=board&team=NYY#pitcher-lanes')
  assert.equal(model.evidenceTarget, 'pitcher_lanes')
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

  // This production payload carries heavy short-start pressure (3 of 5), so the
  // corrected starter-support path now leads with the exact short-start count.
  assert.equal(model.stateLabel, readModel.stateLabel)
  assert.equal(model.summary, readModel.stateSummary)
  assert.equal(model.storyAngle, 'starter_support')
  assert.equal(model.headline, '3 OF 5 RECENT NEW YORK YANKEES STARTS ENDED BEFORE FIVE INNINGS')
  assert.equal(model.receipts[0], '3 of 5 analyzed starts ended before five innings.')
  assert.match(model.supportingLine, /starters averaged 4\.1 innings per start/)
  assert.deepEqual(model.receipts, [
    '3 of 5 analyzed starts ended before five innings.',
    '9 of 9 active relievers are classified Available.',
    'Recent relief work was spread across 9 active relievers.',
  ])
  assert.ok(model.destinationUrl.endsWith('#team-relief-work'))
  assert.match(readModel.starterSupportPressure.summary, /starters averaged 4\.1 innings per start\./)
  assert.equal(/starters averaged \d+\.[^012] innings per start/.test(readModel.starterSupportPressure.summary), false)
})

test('Yankees limited-support card omits the supporting line and keeps headline support first', () => {
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
    'Across the seven-day window, starters averaged 4.1 innings per start.',
  ])
  assert.equal(model.supportingLine, null)
  assert.equal(model.headline, '9 OF 9 NEW YORK YANKEES RELIEVERS ARE AVAILABLE')
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
  assert.equal(starterOnlyContext.receipts[0], '9 of 9 active relievers are classified Available.')
})

test('team card fails closed for stale, sample, incomplete, or internal text', () => {
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ freshness: { dataThrough: '2026-07-14', isCurrent: false } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ freshness: { dataThrough: '2026-07-14', isCurrent: true, isSample: true } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ evidence: [] })), null)
  const ignoredRawWhy = cards.buildTeamEvidenceCard(teamRead({ why: 'Backend model score threshold changed.' }))
  assert.equal(ignoredRawWhy.supportingLine, 'Recent relief work has flowed through a smaller group of arms.')
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ workloadConcentration: { summary: 'Backend model score threshold changed.' } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ stateSummary: 'Backend model score threshold changed.' })), null)
})

test('constrained availability reads produce a specific availability-constraint headline', () => {
  const model = cards.buildTeamEvidenceCard(constrainedRead())
  assert.equal(model.storyAngle, 'availability_constraint')
  assert.equal(model.headline, 'ONLY 4 OF 8 TEST CLUB RELIEVERS ARE AVAILABLE')
  assert.equal(model.receipts[0], '4 of 8 active relievers are classified Available.')
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=board&team=TST#pitcher-lanes')
  assert.equal(model.evidenceTarget, 'pitcher_lanes')
  assert.equal(model.shareText, 'Only 4 of 8 Test Club relievers are available. See the current BaseballOS evidence.')
})

test('neutral counts never become alarmist "only" copy and generic summaries never become headlines', () => {
  const positive = cards.buildTeamEvidenceCard(teamRead({
    stateLabel: 'Stable',
    stateSummary: 'The current bullpen read shows enough usable coverage without a clear pressure flag.',
    workloadConcentration: null,
    primaryConcern: null,
    evidence: ['8 of 8 relievers are classified Available.'],
  }))
  assert.equal(positive.storyAngle, 'availability_depth')
  assert.equal(positive.headline, '8 OF 8 TEST CLUB RELIEVERS ARE AVAILABLE')
  assert.equal(positive.headline.includes('ONLY'), false)
  assert.equal(positive.headline, positive.headline.toUpperCase())
  assert.notEqual(positive.headline, positive.summary.toUpperCase().replace(/\.$/, ''))

  const summaryOnly = cards.buildTeamEvidenceCard(teamRead({
    stateLabel: 'Monitor',
    workloadConcentration: null,
    primaryConcern: null,
    evidence: ['8 of 8 relievers are classified Available.'],
  }))
  assert.equal(summaryOnly, null)
})

test('workload concentration becomes the headline when no repeated-usage receipt exists', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({
    evidence: [
      'Three relievers worked yesterday.',
      '5 bullpen arms are inactive or unavailable.',
    ],
  }))
  assert.equal(model.storyAngle, 'workload_concentration')
  assert.equal(model.headline, 'RECENT TEST CLUB RELIEF WORK HAS RUN THROUGH A SMALLER GROUP OF ARMS')
  assert.equal(model.receipts[0], 'Three relievers worked yesterday.')
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=board&team=TST#team-relief-work')
  assert.equal(model.evidenceTarget, 'team_relief_work')
})

test('team story angles stay allowlisted and the share text comes from the headline sentence', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  assert.equal(story.TEAM_STORY_ANGLES.includes(model.storyAngle), true)
  assert.equal(model.cardVersion, 'team_story_v2')
  assert.equal(model.storyAngle, 'repeated_usage')
  assert.equal(model.headline, 'TWO TEST CLUB RELIEVERS HAVE APPEARED ON CONSECUTIVE DAYS')
  assert.equal(model.shareText, 'Two Test Club relievers have appeared on consecutive days. See the current BaseballOS evidence.')
  assert.notEqual(model.shareText, model.shareText.toUpperCase())
  assert.equal(model.shareText.includes('#'), false)
  assert.equal(story.TEAM_STORY_EVIDENCE_SECTIONS[model.storyAngle], 'team-relief-work')
  assert.equal(model.evidenceTarget, 'team_relief_work')
  assert.ok(model.destinationUrl.endsWith('#team-relief-work'))
  assert.equal(model.supportingLine, 'Recent relief work has flowed through a smaller group of arms.')
  assert.notEqual(model.supportingLine.toUpperCase().replace(/\.$/, ''), model.headline)
})

test('every team story angle maps to a canonical evidence section', () => {
  for (const angle of story.TEAM_STORY_ANGLES) {
    const section = story.TEAM_STORY_EVIDENCE_SECTIONS[angle]
    assert.ok(['pitcher-lanes', 'team-relief-work'].includes(section), angle)
  }
  assert.deepEqual(Object.keys(story.TEAM_STORY_EVIDENCE_SECTIONS).sort(), [...story.TEAM_STORY_ANGLES].sort())
})

test('team alt text carries the headline, state, receipt count, freshness, and limitation', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  assert.match(model.altText, /Two Test Club relievers have appeared on consecutive days\./)
  assert.match(model.altText, /state: Monitor/)
  assert.match(model.altText, /3 receipts shown/)
  assert.match(model.altText, /July 14, 2026/)
  assert.match(model.altText, /does not predict usage/)
  assert.equal(model.altText.length <= 320, true)
})

test('comparison card preserves team order and all four public rows while leading with the largest difference', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model.teamA.abbreviation, 'ACE')
  assert.equal(model.teamB.abbreviation, 'BEA')
  assert.deepEqual(model.rows.map(row => row.label), ['Available', 'On Watch', 'Limited', 'Unavailable'])
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=compare&team_a=ACE&team_b=BEA#comparison-evidence')
  assert.equal(model.displayUrl, 'baseballos.app/bullpen?view=compare&team_a=ACE&team_b=BEA#comparison-evidence')
  assert.equal(model.fileName, 'baseballos-ace-vs-bea-2026-06-04.png')
  assert.equal(model.cardVersion, 'comparison_story_v2')
  assert.equal(model.storyAngle, 'comparison_availability')
  assert.equal(model.headline, 'THE ACES HAVE 3 MORE AVAILABLE ARMS THAN THE BEARS')
  assert.equal(model.supportingLine, 'The Bears have 5 unavailable arms; the Aces have 2.')
  assert.equal(model.shareText, 'The Aces have 3 more available arms than the Bears. See the current BaseballOS evidence.')
  assert.equal(model.evidenceTarget, 'comparison_evidence')
})

test('comparison story avoids winner language and stays inside the bounded angle list', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(story.COMPARISON_STORY_ANGLES.includes(model.storyAngle), true)
  for (const text of [model.headline, model.supportingLine, model.shareText, model.altText]) {
    assert.equal(WINNER_LANGUAGE.test(text), false, text)
  }
  assert.notEqual(model.shareText, model.shareText.toUpperCase())
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
  assert.equal(candidates.headline, 'THE ALPHA CLUB HAVE 3 MORE AVAILABLE ARMS THAN THE BETA CLUB')
  assert.equal(candidates.supportingLine, 'The Alpha Club have 3 limited arms; the Beta Club have 1.')
  assert.equal(candidates.headline.includes('ON WATCH'), false)

  const equalDifferences = cards.buildComparisonEvidenceCard({
    ...comparison.getComparisonView(differingComparison),
    snapshot: [
      { label: 'Available', valueA: 5, valueB: 3 },
      { label: 'On Watch', valueA: 4, valueB: 2 },
      { label: 'Limited', valueA: 1, valueB: 3 },
      { label: 'Unavailable', valueA: 2, valueB: 2 },
    ],
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(equalDifferences.headline, 'THE ACES HAVE 2 MORE AVAILABLE ARMS THAN THE BEARS')
  assert.equal(equalDifferences.supportingLine, 'The Bears have 3 limited arms; the Aces have 1.')
  assert.equal(equalDifferences.headline.includes('ON WATCH'), false)
})

test('Cleveland versus Boston leads with the 7-to-4 Available difference before the tied On Watch row', () => {
  const payload = makeComparison(
    { team: { team_id: 1, team_name: 'Cleveland Guardians', team_abbreviation: 'CLE' }, counts: { Available: 4, Monitor: 1, Limited: 3 } },
    { team: { team_id: 2, team_name: 'Boston Red Sox', team_abbreviation: 'BOS' }, counts: { Available: 7, Monitor: 1, Limited: 1 } },
  )
  const view = comparison.getComparisonView(payload)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'CLE', teamB: 'BOS' })

  assert.equal(model.headline, 'THE BOSTON RED SOX HAVE 3 MORE AVAILABLE ARMS THAN THE CLEVELAND GUARDIANS')
  assert.equal(model.storyAngle, 'comparison_availability')
  assert.equal(model.supportingLine, 'The Cleveland Guardians have 3 limited arms; the Boston Red Sox have 1.')
  assert.equal(model.headline.includes('ON WATCH'), false)
  assert.equal(view.summary.statement, view.featuredObservation)
})

test('identical comparisons fail closed instead of publishing a bland card', () => {
  const view = comparison.getComparisonView(similarComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model, null)
  assert.equal(view.summary.statement, 'The bullpens match across every availability group in the current read.')
})

test('all-tied comparisons only produce a card when another specific safe observation exists', () => {
  const view = comparison.getComparisonView(similarComparison)
  const model = cards.buildComparisonEvidenceCard({
    ...view,
    observations: [
      ...view.observations,
      { statement: 'Both bullpens rested their full relief groups yesterday, with 0 appearances on each side.' },
    ],
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model.storyAngle, 'comparison_no_separation')
  assert.equal(model.headline, 'THE ACES AND BEARS BULLPENS MATCH ACROSS EVERY AVAILABILITY GROUP')
  assert.equal(model.supportingLine, 'Both bullpens rested their full relief groups yesterday, with 0 appearances on each side.')
  assert.equal(WINNER_LANGUAGE.test(model.headline), false)
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

test('unfittable comparison headlines fail closed instead of truncating', () => {
  const view = comparison.getComparisonView(differingComparison)
  const noFitModel = cards.buildComparisonEvidenceCard({
    ...view,
    labelA: 'A'.repeat(42),
    labelB: 'B'.repeat(42),
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(noFitModel, null)
})

test('SVG output is deterministic, escaped, and fixed at 1200 by 630', () => {
  const model = cards.buildTeamEvidenceCard(teamRead({ teamName: 'Test & Club <One>' }))
  const first = renderer.renderEvidenceCardSvg(model)
  assert.equal(first, renderer.renderEvidenceCardSvg(model))
  assert.match(first, /width="1200" height="630"/)
  assert.ok(first.includes('TEST &amp; CLUB &lt;ONE&gt; BULLPEN'))
  assert.equal(first.includes('<ONE>'), false)
})

test('team SVG leads with the story headline and demotes the state to a compact badge', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  const svg = renderer.renderEvidenceCardSvg(model)
  const headlineIndex = svg.indexOf('TWO TEST CLUB RELIEVERS')
  const badgeIndex = svg.indexOf('BASEBALLOS STATE · MONITOR')
  assert.equal(headlineIndex > -1, true)
  assert.equal(badgeIndex > -1, true)
  assert.equal(headlineIndex < badgeIndex, true)
  assert.equal(svg.includes('font-size="44"'), false)
  assert.equal(svg.includes('>WHY</text>'), false)
  assert.ok(svg.includes('font-size="34" font-weight="800"'))
  assert.ok(svg.includes(`Data through ${model.dataThroughLabel}`))
  assert.ok(svg.includes(model.limitation))
  assert.ok(svg.includes('SEE THE RECENT RELIEF WORK EVIDENCE'))
  assert.ok(svg.includes('baseballos.app/bullpen?view=board&amp;team=TST#team-relief-work'))
})

test('team layout keeps story copy and receipts in independent bounded columns', () => {
  const model = cards.buildTeamEvidenceCard(teamRead())
  const svg = renderer.renderEvidenceCardSvg(model)
  assert.ok(svg.includes('<rect x="668" y="132" width="476" height="342"'))
  assert.ok(svg.includes('<text x="56" y="210"'))
  assert.ok(svg.includes('<text x="700" y="220"'))
  assert.ok(textLayout.wrapCardText(model.headline, story.TEAM_HEADLINE_LAYOUT))
  assert.ok(textLayout.wrapCardText(model.supportingLine, story.TEAM_SUPPORTING_LAYOUT))
  for (const receipt of model.receipts) {
    assert.ok(textLayout.wrapCardText(receipt, { maxWidth: 404, maxLines: 2, fontSize: 18 }))
  }
})

test('long team names keep complete headlines and one-, two-, and three-receipt cards stay complete', () => {
  const longName = cards.buildTeamEvidenceCard(teamRead({
    teamName: 'Arizona Diamondbacks',
    teamAbbreviation: 'ARI',
  }))
  assert.equal(longName.headline, 'TWO ARIZONA DIAMONDBACKS RELIEVERS HAVE APPEARED ON CONSECUTIVE DAYS')
  assert.ok(textLayout.wrapCardText(longName.headline, story.TEAM_HEADLINE_LAYOUT))

  const evidenceSets = [
    ['Two relievers have appeared on consecutive days.'],
    ['Two relievers have appeared on consecutive days.', '9 of 9 relievers are classified Available.'],
    ['Two relievers have appeared on consecutive days.', '9 of 9 relievers are classified Available.', '5 bullpen arms are inactive or unavailable.'],
  ]
  evidenceSets.forEach((evidence, index) => {
    const model = cards.buildTeamEvidenceCard(teamRead({ evidence }))
    assert.equal(model.receipts.length, index + 1)
    const svg = renderer.renderEvidenceCardSvg(model)
    assert.equal(svg.includes('…'), false)
    assert.equal(svg.includes('...'), false)
    for (const receipt of model.receipts) {
      assert.ok(svg.includes(receipt.split(' ')[0]))
    }
  })
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
  assert.ok(svg.includes('baseballos.app/bullpen?view=board&amp;team=TST#team-relief-work'))
})

test('comparison SVG leads with the headline, keeps rows intact, and drops the generic differs panel', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  const svg = renderer.renderEvidenceCardSvg(model)
  const headlineIndex = svg.indexOf('THE ACES HAVE 3 MORE AVAILABLE ARMS')
  const rowsIndex = svg.indexOf('>AVAILABLE</text>')
  assert.equal(headlineIndex > -1, true)
  assert.equal(rowsIndex > -1, true)
  assert.equal(headlineIndex < rowsIndex, true)
  assert.equal(svg.includes('WHAT DIFFERS'), false)
  assert.ok(svg.includes('ALSO IN THIS READ'))
  for (const line of textLayout.wrapCardText(model.supportingLine, story.COMPARISON_SUPPORTING_LAYOUT)) {
    assert.ok(svg.includes(line), line)
  }
  assert.ok(svg.includes(`Data through ${model.freshnessALabel}`))
  assert.ok(svg.includes(model.limitation))
  assert.ok(svg.includes('SEE THE SIDE-BY-SIDE EVIDENCE'))
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
  assert.ok(textLayout.wrapCardText(model.headline, story.COMPARISON_HEADLINE_LAYOUT))
  const svg = renderer.renderEvidenceCardSvg(model)
  assert.ok(svg.includes('x="360" text-anchor="middle"'))
  assert.ok(svg.includes('x="500" text-anchor="middle"'))
  assert.ok(svg.includes('>VS</text>'))
  assert.ok(svg.includes('x="640" text-anchor="middle"'))
  assert.equal([...svg.matchAll(/x="360" text-anchor="middle"/g)].length >= 6, true)
  assert.equal([...svg.matchAll(/x="640" text-anchor="middle"/g)].length >= 6, true)
  assert.ok(svg.includes('baseballos.app/bullpen?view=compare&amp;team_a=ARI&amp;team_b=LAA#comparison-evidence'))
  assert.equal(svg.includes('…'), false)
})

test('comparison alt text carries the headline, both teams, freshness, and the non-predictive limitation', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.match(model.altText, /The Aces have 3 more available arms than the Bears\./)
  assert.match(model.altText, /Aces and Bears/)
  assert.match(model.altText, /Available, On Watch, Limited, and Unavailable/)
  assert.match(model.altText, /data through/)
  assert.match(model.altText, /Descriptive current workload only/)
  assert.equal(model.altText.length <= 320, true)
})

test('share controls use the card-selected destination, target, and share text', () => {
  const board = readFileSync(new URL('../src/components/bullpen/board/TonightsBullpenBoard.jsx', import.meta.url), 'utf8')
  const menu = readFileSync(new URL('../src/components/share/EvidenceShareMenu.jsx', import.meta.url), 'utf8')
  const comparisonView = readFileSync(new URL('../src/components/bullpen/board/BullpenComparisonView.jsx', import.meta.url), 'utf8')

  assert.ok(board.includes('buildTeamEvidenceCard(teamOperatingRead)'))
  assert.ok(board.includes('teamCard?.destinationUrl'))
  assert.ok(board.includes('teamCard?.evidenceTarget'))
  assert.ok(board.includes('teamCard?.shareText'))
  assert.ok(board.includes('evidence_target: teamEvidenceTarget'))
  assert.equal(board.includes("current bullpen read, with the recent-work receipts"), false)

  assert.ok(menu.includes('cardModel?.destinationUrl || destinationUrl'))
  assert.ok(menu.includes('cardModel?.shareText || shareText'))
  assert.ok(menu.includes('destinationUrl: shareDestination'))
  assert.ok(menu.includes('shareText: nativeShareText'))

  assert.ok(comparisonView.includes('buildComparisonEvidenceCard(view, { teamA, teamB })'))
  assert.ok(comparisonView.includes('cardModel?.shareText'))
  assert.ok(comparisonView.includes("evidence_target: 'comparison_evidence'"))
  assert.equal(comparisonView.includes("current bullpen workload comparison.'"), false)
})

test('distinct receipt subtypes survive candidate normalization instead of collapsing to one per family', () => {
  const availability = cards.distinctTeamReceiptCandidates([
    '4 of 9 relievers are classified Available.',
    '3 of 9 relievers are in the On Watch group.',
    '2 of 9 relievers are Limited or Unavailable.',
  ])
  assert.deepEqual(availability.map(candidate => candidate.subtype), [
    'availability_available',
    'availability_on_watch',
    'availability_limited_unavailable',
  ])

  const starter = cards.distinctTeamReceiptCandidates([
    'Across the seven-day window, starters averaged 4.1 innings per start.',
    '3 of 5 analyzed starts ended before five innings.',
  ])
  assert.deepEqual(starter.map(candidate => candidate.subtype).sort(), ['starter_short_starts', 'starter_summary'])

  const roster = cards.distinctTeamReceiptCandidates([
    '5 bullpen arms are on the injured list.',
    '3 bullpen arms are inactive or unavailable.',
    '2 bullpen arms have unconfirmed roster status.',
  ])
  assert.deepEqual(roster.map(candidate => candidate.subtype).sort(), [
    'roster_inactive',
    'roster_injured_list',
    'roster_unknown',
  ])

  const duplicates = cards.distinctTeamReceiptCandidates([
    '3 of 9 relievers are in the On Watch group.',
    ' 3 of 9 relievers are in the On Watch group. ',
  ])
  assert.equal(duplicates.length, 1)
  assert.equal(duplicates[0].subtype, 'availability_on_watch')
})

test('a Worth Watching read produces a specific On Watch headline supported by its receipt', () => {
  const payload = {
    hasContext: true,
    state: 'monitoring',
    label: 'Enough yellow flags to keep this bullpen on the board.',
    reasons: [],
    metrics: { total: 9 },
    snapshot: [
      { status: 'Available', label: 'Available', count: 4 },
      { status: 'Monitor', label: 'On Watch', count: 3 },
      { status: 'Limited', label: 'Limited', count: 2 },
    ],
    team: { team_id: 114, team_name: 'Cleveland Guardians', team_abbreviation: 'CLE' },
    freshness: { data_through: '2026-07-14', is_current: true, sync_status: 'success' },
  }
  const readModel = operatingState.toOperatingStateReadModel(payload, { scope: 'team' })
  assert.equal(readModel.stateLabel, 'Worth Watching')
  const model = cards.buildTeamEvidenceCard(readModel)

  assert.equal(model.storyAngle, 'availability_watch')
  assert.equal(model.headline, '3 OF 9 CLEVELAND GUARDIANS RELIEVERS ARE ON WATCH')
  assert.equal(model.headline.includes('ONLY'), false)
  assert.equal(model.receipts[0], '3 of 9 relievers are in the On Watch group.')
  assert.equal(model.evidenceTarget, 'pitcher_lanes')
  assert.ok(model.destinationUrl.endsWith('#pitcher-lanes'))
  assert.equal(model.shareText, '3 of 9 Cleveland Guardians relievers are On Watch. See the current BaseballOS evidence.')
  assert.equal(story.TEAM_STORY_ANGLES.includes(model.storyAngle), true)
})

test('a production starter-support read leads with the exact short-start count and keeps the summary as support', () => {
  const payload = {
    hasContext: true,
    state: 'stable',
    label: 'Short starts have leaned on the bullpen.',
    reasons: [],
    metrics: { total: 8 },
    snapshot: [{ status: 'Available', label: 'Available', count: 6 }],
    team: { team_id: 119, team_name: 'Los Angeles Dodgers', team_abbreviation: 'LAD' },
    freshness: { data_through: '2026-07-14', is_current: true, sync_status: 'success' },
    team_shape: {
      workloadConcentration: { key: 'workloadConcentration', label: 'No Workload Concentration', reasons: [] },
    },
    rotation_support_pressure: {
      capability: 'rotation_support_pressure_v1',
      status: 'heavy_pressure',
      games_in_window: 5,
      games_analyzed: 5,
      window_days: 7,
      starter_outs: 63,
      bullpen_outs_required: 63,
      short_start_count: 3,
      limitations: [],
    },
  }
  const readModel = operatingState.toOperatingStateReadModel(payload, { scope: 'team' })
  const model = cards.buildTeamEvidenceCard(readModel)

  assert.equal(model.storyAngle, 'starter_support')
  assert.equal(model.headline, '3 OF 5 RECENT LOS ANGELES DODGERS STARTS ENDED BEFORE FIVE INNINGS')
  assert.equal(model.receipts[0], '3 of 5 analyzed starts ended before five innings.')
  assert.match(model.supportingLine, /starters averaged 4\.1 innings per start/)
  assert.ok(model.receipts.some(receipt => /starters averaged 4\.1 innings per start/.test(receipt)))
  assert.equal(model.evidenceTarget, 'team_relief_work')
  assert.ok(model.destinationUrl.endsWith('#team-relief-work'))
})

function rosterPayload(counts, overrides = {}) {
  return {
    hasContext: true,
    state: 'recovering',
    label: 'The bullpen is working back toward a cleaner read.',
    reasons: [],
    metrics: { total: 8 },
    snapshot: [{ status: 'Available', label: 'Available', count: 5 }],
    team: { team_id: 112, team_name: 'Chicago Cubs', team_abbreviation: 'CHC' },
    freshness: { data_through: '2026-07-14', is_current: true, sync_status: 'success' },
    roster_authority: {
      capability: 'roster_authority_v1',
      category_counts: { injured_list: counts.injured_list || 0 },
      counts: {
        bullpen_arms: 8,
        active_bullpen_arms: 5,
        inactive_roster_context_count: counts.inactive || 0,
        roster_unknown_count: counts.unknown || 0,
      },
      population: { total_candidates: 8, known_count: 8, unknown_count: 0, roster_status_coverage: 1 },
      limitations: [],
    },
    ...overrides,
  }
}

test('each roster subtype can independently support a specific roster-context headline', () => {
  const inactive = cards.buildTeamEvidenceCard(operatingState.toOperatingStateReadModel(rosterPayload({ inactive: 3 }), { scope: 'team' }))
  assert.equal(inactive.storyAngle, 'roster_context')
  assert.equal(inactive.headline, '3 CHICAGO CUBS BULLPEN ARMS ARE INACTIVE OR UNAVAILABLE')
  assert.equal(inactive.receipts[0], 'Roster context: 3 bullpen arms are inactive or unavailable.')
  assert.ok(inactive.destinationUrl.endsWith('#pitcher-lanes'))
  assert.equal(inactive.evidenceTarget, 'pitcher_lanes')

  const injured = cards.buildTeamEvidenceCard(operatingState.toOperatingStateReadModel(rosterPayload({ injured_list: 5 }), { scope: 'team' }))
  assert.equal(injured.storyAngle, 'roster_context')
  assert.equal(injured.headline, '5 CHICAGO CUBS BULLPEN ARMS ARE ON THE INJURED LIST')
  assert.equal(injured.receipts[0], 'Roster context: 5 bullpen arms are on the injured list.')

  const unknown = cards.buildTeamEvidenceCard(operatingState.toOperatingStateReadModel(rosterPayload({ unknown: 2 }), { scope: 'team' }))
  assert.equal(unknown.storyAngle, 'roster_context')
  assert.equal(unknown.headline, '2 CHICAGO CUBS BULLPEN ARMS HAVE UNCONFIRMED ROSTER STATUS')
  assert.equal(unknown.receipts[0], 'Roster context: 2 bullpen arms have unconfirmed roster status.')
})

test('roster storytelling prefers inactive when multiple roster subtypes are present', () => {
  const model = cards.buildTeamEvidenceCard(operatingState.toOperatingStateReadModel(
    rosterPayload({ injured_list: 2, inactive: 3, unknown: 1 }),
    { scope: 'team' },
  ))
  assert.equal(model.storyAngle, 'roster_context')
  assert.equal(model.headline, '3 CHICAGO CUBS BULLPEN ARMS ARE INACTIVE OR UNAVAILABLE')
  assert.equal(model.receipts[0], 'Roster context: 3 bullpen arms are inactive or unavailable.')
})

test('printed evidence destination matches the exact anchored shared destination', () => {
  const teamModel = cards.buildTeamEvidenceCard(teamRead())
  assert.equal(teamModel.displayUrl, teamModel.destinationUrl.replace(/^https:\/\//, ''))
  const teamSvg = renderer.renderEvidenceCardSvg(teamModel)
  assert.ok(teamSvg.includes('#team-relief-work'))
  assert.equal(teamSvg.includes('/team/TST'), false)

  const pitcherLaneModel = cards.buildTeamEvidenceCard(constrainedRead())
  assert.equal(pitcherLaneModel.displayUrl, pitcherLaneModel.destinationUrl.replace(/^https:\/\//, ''))
  assert.ok(renderer.renderEvidenceCardSvg(pitcherLaneModel).includes('#pitcher-lanes'))

  const view = comparison.getComparisonView(differingComparison)
  const comparisonModel = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(comparisonModel.displayUrl, comparisonModel.destinationUrl.replace(/^https:\/\//, ''))
  const comparisonSvg = renderer.renderEvidenceCardSvg(comparisonModel)
  assert.ok(comparisonSvg.includes('#comparison-evidence'))
  assert.equal(comparisonSvg.includes(' · Compare '), false)
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
