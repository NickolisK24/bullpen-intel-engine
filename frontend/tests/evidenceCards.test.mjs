import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

import { differingComparison, staleComparison } from './fixtures/bullpenComparisonFixtures.mjs'

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
  assert.equal(model.receipts.length, 3)
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

test('team card fails closed for stale, sample, incomplete, or internal text', () => {
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ freshness: { dataThrough: '2026-07-14', isCurrent: false } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ freshness: { dataThrough: '2026-07-14', isCurrent: true, isSample: true } })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ evidence: [] })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ why: 'Backend model score threshold changed.' })), null)
  assert.equal(cards.buildTeamEvidenceCard(teamRead({ stateSummary: 'Backend model score threshold changed.' })), null)
})

test('comparison card preserves the selected order and all four public rows', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model.teamA.abbreviation, 'ACE')
  assert.equal(model.teamB.abbreviation, 'BEA')
  assert.deepEqual(model.rows.map(row => row.label), ['Available', 'On Watch', 'Limited', 'Unavailable'])
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=compare&team_a=ACE&team_b=BEA#comparison-evidence')
  assert.equal(model.displayUrl, 'baseballos.app · Compare ACE vs BEA')
  assert.equal(model.fileName, 'baseballos-ace-vs-bea-2026-06-04.png')
  assert.equal(model.observation, view.observations[0].statement)
  assert.match(model.observation, /^The Aces currently have/)
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
  assert.equal(model.receipts.length, 2)
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
  assert.equal(shorterModel.observation, short)

  const fallbackModel = cards.buildComparisonEvidenceCard({
    ...view,
    observations: [{ statement: long }],
    summary: { statement: long },
  }, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(fallbackModel.observation, 'The current side-by-side counts are shown at left.')
  assert.equal(/[.!?]$/.test(fallbackModel.observation), true)
  assert.equal(fallbackModel.observation.endsWith('...'), false)
  assert.equal(fallbackModel.observation.endsWith('…'), false)
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
