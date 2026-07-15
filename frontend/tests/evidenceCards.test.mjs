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
})

test('comparison card preserves the selected order and all four public rows', () => {
  const view = comparison.getComparisonView(differingComparison)
  const model = cards.buildComparisonEvidenceCard(view, { teamA: 'ACE', teamB: 'BEA' })
  assert.equal(model.teamA.abbreviation, 'ACE')
  assert.equal(model.teamB.abbreviation, 'BEA')
  assert.deepEqual(model.rows.map(row => row.label), ['Available', 'On Watch', 'Limited', 'Unavailable'])
  assert.equal(model.destinationUrl, 'https://baseballos.app/bullpen?view=compare&team_a=ACE&team_b=BEA#comparison-evidence')
  assert.equal(model.fileName, 'baseballos-ace-vs-bea-2026-06-04.png')
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

test('unusually long public text is bounded without changing the fixed layout', () => {
  const long = 'A very long public explanation '.repeat(20)
  const model = cards.buildTeamEvidenceCard(teamRead({ stateSummary: long, why: long, evidence: [long] }))
  assert.equal(model.summary.length <= 105, true)
  assert.equal(model.why.length <= 135, true)
  assert.equal(model.receipts[0].length <= 150, true)
  assert.match(renderer.renderEvidenceCardSvg(model), /viewBox="0 0 1200 630"/)
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
