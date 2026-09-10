// Public copy pass-through contract (H-5). Backend semantic owners author
// public meaning; frontend surfaces render clean copy or refuse blocked copy.

import assert from 'node:assert/strict'
import test, { after } from 'node:test'
import { createServer } from 'vite'

const server = await createServer({
  root: process.cwd(),
  server: { middlewareMode: true },
  appType: 'custom',
  logLevel: 'silent',
})

after(async () => server.close())

const { publicFramingCopy, BLOCKED_FRAMING_COPY_PATTERN } = await server.ssrLoadModule(
  '/src/components/trust/AvailabilityBacktestCard.jsx',
)

test('backtest framing copy renders verbatim when it is clean', () => {
  const claim = 'Arms classified Unavailable were used the next day far less often than arms classified Available.'
  assert.equal(publicFramingCopy(claim), claim)
})

test('framing copy no longer rewrites engine vocabulary', () => {
  assert.equal(publicFramingCopy('Arms classified Avoid were used less often.'),
    'Arms classified Avoid were used less often.')
  assert.equal(publicFramingCopy('The usage check ran nightly.'), 'The usage check ran nightly.')
})

test('prohibited framing is refused, never rewritten', () => {
  for (const banned of [
    'This predicts tomorrow’s usage.',
    'Accuracy was 91% against the model.',
    'Best bet: ride the closer.',
    'Teams are ranked by score.',
    'Computed deterministically from the endpoint snapshot.',
    'COIN V3 governance output.',
  ]) {
    assert.ok(BLOCKED_FRAMING_COPY_PATTERN.test(banned), `must be detected: ${banned}`)
    assert.equal(publicFramingCopy(banned), '', `must be withheld, not repaired: ${banned}`)
  }
})

test('withholding returns empty rather than a substitute sentence', () => {
  const refused = publicFramingCopy('Forecast: three arms unavailable.')
  assert.equal(refused, '')
  assert.equal(refused.length, 0)
})

test('ordinary baseball language is not over-refused', () => {
  for (const fine of [
    'Arms classified Unavailable were used the next day far less often.',
    'Observed next-day relief usage on completed games.',
    'Three relievers threw on back-to-back days.',
  ]) assert.equal(publicFramingCopy(fine), fine)
})

test('no public-copy component carries a vocabulary replacement table', async () => {
  const { readFile } = await import('node:fs/promises')
  const suspects = [
    '../src/components/dashboard/DashboardStorylines.jsx',
    '../src/components/dashboard/LeagueTeamStateLandscape.jsx',
    '../src/components/trust/AvailabilityBacktestCard.jsx',
    '../src/components/home/IntelligenceSurface.jsx',
  ]
  const forbidden = [
    "'On Watch')", "'Unavailable')", "'stretched')", "'Stretched')",
    "'consistently')", "'data feed')", "'data feeds')", "'BaseballOS service')",
    "'usage check')", "'Clean Options')", "'limited')", "'Limited')",
  ]
  for (const relative of suspects) {
    const source = await readFile(new URL(relative, import.meta.url), 'utf8')
    for (const swap of forbidden) {
      assert.equal(source.includes('.replace(') && source.includes(swap), false,
        `${relative} reintroduced a public-vocabulary substitution: ${swap}`)
    }
  }
})
